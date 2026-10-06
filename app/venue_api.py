"""Протокол внешних заведений v1: проект, геометрия и задания агенту. Без аккаунтов."""
import asyncio
import hashlib
import json
import math
import secrets
import time
from collections import deque
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app import db, log

# Участки вне домов и дорог; зал и вход используют существующий каркас 8 × 8.
PLOTS = {
    "west_north": {"ox": -22.0, "oy": 0.0, "junction": [-26.0, 16.6]},
    "west_south": {"ox": -22.0, "oy": 19.5, "junction": [-26.0, 16.6]},
}
KINDS = {"table": [1.1, 1.1], "chair": [0.5, 0.5], "plant": [0.5, 0.5],
         "equipment": [0.8, 0.8], "shelf": [1.2, 0.5], "decor": [0.5, 0.5]}
COLOR = r"^#[0-9a-fA-F]{6}$"
IDENT = r"^[a-z][a-z0-9_-]{0,31}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class Furniture(Strict):
    id: str = Field(pattern=IDENT)
    kind: Literal["table", "chair", "plant", "equipment", "shelf", "decor"]
    x: float = Field(ge=0.25, le=7.75, allow_inf_nan=False)
    y: float = Field(ge=3.8, le=7.75, allow_inf_nan=False)
    color: str = Field(default="#8b6546", pattern=COLOR)
    face: Literal["n", "w"] = "n"


class Interior(Strict):
    floor_color: str = Field(default="#bd905c", pattern=COLOR)
    wall_color: str = Field(default="#507568", pattern=COLOR)
    accent_color: str = Field(default="#d7b466", pattern=COLOR)
    objects: list[Furniture] = Field(default_factory=list, max_length=30)


class Product(Strict):
    id: str = Field(pattern=IDENT)
    name: str = Field(min_length=2, max_length=24)
    price: int = Field(ge=50, le=900)
    minutes: int = Field(ge=1, le=8)


class Employee(Strict):
    id: str = Field(pattern=IDENT)
    name: str = Field(min_length=2, max_length=40)
    personality: str = Field(default="Говорит спокойно и по делу.", max_length=1000)


class Controller(Strict):
    mode: Literal["agent", "openai"] = "agent"
    model: str = Field(default="external-agent", min_length=1, max_length=100)
    base_url: str = Field(default="", max_length=300)
    api_key: str = Field(default="", max_length=500)
    timeout: int = Field(default=10, ge=2, le=20)

    @model_validator(mode="after")
    def url(self):
        if self.mode == "openai":
            from urllib.parse import urlsplit
            parsed = urlsplit(self.base_url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Нужен HTTP(S) base_url без логина и пароля в адресе")
            if parsed.query or parsed.fragment:
                raise ValueError("base_url без query и fragment")
        return self


class Project(Strict):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=IDENT)
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(min_length=2, max_length=2000)
    plot_id: Literal["west_north", "west_south"]
    open_min: int = Field(default=480, ge=0, le=1439)
    close_min: int = Field(default=1200, ge=1, le=1440)
    interior: Interior = Field(default_factory=Interior)
    items: list[Product] = Field(min_length=1, max_length=10)
    staff: list[Employee] = Field(min_length=1, max_length=2)
    manager_personality: str = Field(default="Развивает заведение по отзывам гостей.", max_length=1000)
    controller: Controller = Field(default_factory=Controller)

    @model_validator(mode="after")
    def distinct(self):
        if self.close_min <= self.open_min:
            raise ValueError("close_min должен быть позже open_min; ночной интервал через полночь пока не поддержан")
        if self.id in ("cafe", "neuraldeep"):
            raise ValueError("Зарезервированный id")
        for rows in (self.items, self.staff, self.interior.objects):
            if len({r.id for r in rows}) != len(rows):
                raise ValueError("Повторяющиеся id")
        if len({r.name.strip().casefold() for r in self.items}) != len(self.items):
            raise ValueError("Названия позиций должны различаться")
        return self


def init_tables():
    with db.tx() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS external_venues (
            place_id TEXT PRIMARY KEY REFERENCES places(id), plot_id TEXT NOT NULL UNIQUE,
            project_json TEXT NOT NULL, controller_json TEXT NOT NULL, token_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ready', last_seen REAL, last_error TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS agent_jobs (
            id TEXT PRIMARY KEY, place_id TEXT NOT NULL REFERENCES places(id),
            payload_json TEXT NOT NULL, status TEXT NOT NULL, deadline REAL NOT NULL,
            response_json TEXT, created_at REAL NOT NULL
        );
        """)
        conn.execute("UPDATE agent_jobs SET status='cancelled' WHERE status='pending'")


def external(place_id=None):
    return db.one("SELECT * FROM external_venues WHERE place_id=?", (place_id or db.current_place(),))


def public_place(row):
    extra = external(row["id"])
    if not extra:
        return row
    project = json.loads(extra["project_json"])
    controller = json.loads(extra["controller_json"])
    return {**row, "room": {**PLOTS[extra["plot_id"]], **project["interior"]},
            "controller": {"mode": controller["mode"], "model": controller["model"],
                           "status": extra["status"], "last_seen": extra["last_seen"], "error": extra["last_error"]}}


def geometry(interior):
    objects = [o.model_dump() for o in interior.objects]
    blocks = []
    for o in objects:
        w, d = KINDS[o["kind"]]
        # Все координаты — центр объекта.
        rect = (o["x"]-w/2, o["x"]+w/2, o["y"]-d/2, o["y"]+d/2)
        if rect[0] < 0.15 or rect[1] > 7.85 or rect[2] < 3.55 or rect[3] > 7.85:
            raise ValueError(f"{o['id']}: объект выходит за зону мебели")
        for other, r in blocks:
            if min(rect[1], r[1])-max(rect[0], r[0]) > 0 and min(rect[3], r[3])-max(rect[2], r[2]) > 0:
                raise ValueError(f"{o['id']}: пересечение с {other['id']}")
        blocks.append((o, rect))
    seats = [{"at": [o["x"], o["y"]], "face": o["face"], "id": o["id"]} for o in objects if o["kind"] == "chair"]
    if len(seats) > 6:
        raise ValueError("Не больше шести кресел")
    # Сетка полклетки: маршруты рассчитывает сервер, браузер только проходит точки по часам.
    def free(p):
        x, y = p[0]/2, p[1]/2
        return 0.25 <= x <= 7.75 and 2 <= y <= 7.75 and not any(
            o["kind"] != "chair" and r[0]-0.18 < x < r[1]+0.18 and r[2]-0.18 < y < r[3]+0.18
            for o, r in blocks)
    grid = [(x,y) for x in range(1,16) for y in range(4,16) if free((x,y))]
    anchors = {"door": [0.35,5.9], "counter": [4.05,2.5],
               **{f"q{i}": p for i,p in enumerate([[3.3,3.05],[2.5,3.05],[1.7,3.05],[0.9,3.05],[0.35,3.05]])},
               **{f"s{i}": seat["at"] for i,seat in enumerate(seats)}}
    def segment_free(a,b):
        n = max(1, math.ceil(math.dist(a,b)/0.08))
        for k in range(n+1):
            x, y = a[0]+(b[0]-a[0])*k/n, a[1]+(b[1]-a[1])*k/n
            if any(o["kind"] != "chair" and r[0]-0.15 < x < r[1]+0.15 and r[2]-0.15 < y < r[3]+0.15 for o,r in blocks):
                return False
        return True
    endpoints = {}
    for name, point in anchors.items():
        candidates = sorted(grid, key=lambda g: math.dist(point, [g[0]/2,g[1]/2]))
        endpoint = next((g for g in candidates if math.dist(point,[g[0]/2,g[1]/2]) <= 0.75 and segment_free(point,[g[0]/2,g[1]/2])), None)
        if endpoint is None:
            raise ValueError(f"Нет подхода к {name}")
        endpoints[name] = endpoint
    pairs = [("door","counter")]+[("door",f"q{i}") for i in range(5)]+[(f"q{i}","counter") for i in range(5)]+[("counter",f"s{i}") for i in range(len(seats))]+[(f"s{i}","door") for i in range(len(seats))]
    routes = {}
    allowed = set(grid)
    for a,b in pairs:
        start, goal = endpoints[a], endpoints[b]
        prev = {start: None}
        todo = deque([start])
        while todo and goal not in prev:
            p = todo.popleft()
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                q = (p[0]+dx,p[1]+dy)
                if q in allowed and q not in prev:
                    prev[q]=p
                    todo.append(q)
        if goal not in prev:
            raise ValueError(f"Нет прохода {a} → {b}")
        path=[]
        p=goal
        while p is not None:
            path.append([p[0]/2,p[1]/2]); p=prev[p]
        points=[anchors[a],*reversed(path),anchors[b]]
        routes[f"{a}:{b}"]=points
        routes[f"{b}:{a}"]=list(reversed(points))
    return {**interior.model_dump(), "seats": seats, "paths": routes}


def validate_project(project):
    interior = geometry(project.interior)
    if db.place(project.id):
        raise ValueError("Такой id заведения уже занят")
    if db.one("SELECT place_id FROM external_venues WHERE plot_id=?", (project.plot_id,)):
        raise ValueError("Участок уже занят")
    return interior


def create(project):
    try:
        interior = validate_project(project)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    token = secrets.token_urlsafe(32)
    plot = PLOTS[project.plot_id]
    data = project.model_dump(exclude={"controller"})
    data["interior"] = interior
    # Повторная проверка внутри транзакции защищает одновременную публикацию на один участок.
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM external_venues WHERE plot_id=?", (project.plot_id,)).fetchone() or conn.execute("SELECT 1 FROM places WHERE id=?", (project.id,)).fetchone():
            raise HTTPException(409, "Участок или id уже занят")
        conn.execute("INSERT INTO places(id,type,name,open_min,close_min,door_x,door_y,note) VALUES(?,?,?,?,?,?,?,?)",
                     (project.id,"custom",project.name,project.open_min,project.close_min,plot["ox"]-0.7,plot["oy"]+5.9,project.description))
        conn.execute("INSERT INTO external_venues(place_id,plot_id,project_json,controller_json,token_hash) VALUES(?,?,?,?,?)",
                     (project.id,project.plot_id,json.dumps(data,ensure_ascii=False),project.controller.model_dump_json(),hashlib.sha256(token.encode()).hexdigest()))
        for item in project.items:
            conn.execute("INSERT INTO items(id,name,price,minutes,available,place_id) VALUES(?,?,?,?,1,?)",
                         (f"{project.id}:{item.id}",item.name,item.price,item.minutes,project.id))
        for person in project.staff:
            conn.execute("INSERT INTO staff(id,name,speed,on_shift,place_id,mood) VALUES(?,?,1,1,?,'спокойствие')",
                         (f"{project.id}:{person.id}",person.name,project.id))
    log.event("venue.create", place=project.id, plot=project.plot_id, mode=project.controller.mode, objects=len(interior["objects"]))
    return {"place": public_place(db.place(project.id)), "agent_token": token,
            "items": {item.id:f"{project.id}:{item.id}" for item in project.items}}


def authorize(place_id, request):
    row=external(place_id)
    if not row:
        raise HTTPException(404,"Внешнее заведение не найдено")
    value=request.headers.get("authorization","")
    token=value[7:] if value.startswith("Bearer ") else ""
    if not token or not secrets.compare_digest(hashlib.sha256(token.encode()).hexdigest(),row["token_hash"]):
        raise HTTPException(403,"Нужен токен этого заведения")
    return row


class JobAnswer(Strict):
    response: dict


class StatusChange(Strict):
    enabled: bool


router=APIRouter(prefix="/api/venues",tags=["Внешние заведения"])


@router.get("/capabilities")
def capabilities():
    return {"schema_version":1,"project_schema":Project.model_json_schema(),"room_size":[8,8],
            "fixed": {"door":[0.35,5.9],"counter":[4.05,2.5],"furniture_zone":[0.15,3.55,7.85,7.85]},
            "objects":KINDS,"roles":["staff","manager"],"limits":{"plots":2,"seats":6,"objects":30},
            "notes":["Координаты объектов — центр; кресла не блокируют проход.","Оборудование и декор пока визуальные; обслуживание по каталогу.","Гости, очередь, вердикты, критик и мир управляются общей моделью.","Заведения обслуживаются по очереди; таймаут внешней модели ограничен 20 секундами."]}


@router.get("/plots")
def plots():
    occupied={r["plot_id"]:r["place_id"] for r in db.q("SELECT plot_id,place_id FROM external_venues")}
    return [{"id":key,**value,"place_id":occupied.get(key)} for key,value in PLOTS.items()]


@router.post("/validate")
def api_validate(project:Project):
    try:
        return {"ok":True,"interior":validate_project(project)}
    except ValueError as exc:
        return {"ok":False,"errors":[str(exc)]}


@router.post("",status_code=201)
async def api_create(project:Project,request:Request):
    result=create(project)
    request.app.state.engine.city.set_places(db.places())
    request.app.state.engine.notify({"type":"venue"})
    return result


@router.get("/{place_id}/project")
def api_project(place_id:str):
    row=external(place_id)
    if not row: raise HTTPException(404,"Заведение не найдено")
    return json.loads(row["project_json"])


@router.get("/{place_id}/jobs")
def jobs(place_id:str,request:Request):
    authorize(place_id,request)
    now=time.time()
    with db.tx() as conn:
        conn.execute("UPDATE agent_jobs SET status='expired' WHERE place_id=? AND status='pending' AND deadline<=?",(place_id,now))
        conn.execute("UPDATE external_venues SET last_seen=? WHERE place_id=?",(now,place_id))
    return {"jobs":[json.loads(r["payload_json"]) for r in db.q("SELECT payload_json FROM agent_jobs WHERE place_id=? AND status='pending' ORDER BY created_at",(place_id,))]}


@router.post("/{place_id}/jobs/{job_id}/answer")
def answer(place_id:str,job_id:str,body:JobAnswer,request:Request):
    authorize(place_id,request)
    row=db.one("SELECT * FROM agent_jobs WHERE id=? AND place_id=?",(job_id,place_id))
    if not row: raise HTTPException(404,"Задание не найдено")
    encoded=json.dumps(body.response,ensure_ascii=False,sort_keys=True)
    if len(encoded)>16000: raise HTTPException(422,"Слишком большой ответ")
    # Ответы принимаются по той же схеме, что запросы к LLM.
    from app.llm import check_schema, validate, SchemaError
    payload=json.loads(row["payload_json"])
    try:
        check_schema(body.response,payload["response_schema"],raw=encoded)
        validate(payload["role"],dict(body.response),final_staff=payload["final_staff"])
    except SchemaError as exc:
        raise HTTPException(422,exc.message) from exc
    with db.tx() as conn:
        current=conn.execute("SELECT status,deadline,response_json FROM agent_jobs WHERE id=?",(job_id,)).fetchone()
        if current["status"]=="answered" and current["response_json"]==encoded:
            return {"ok":True,"duplicate":True}
        if current["status"]!="pending" or current["deadline"]<=time.time():
            raise HTTPException(409,"Задание уже завершено или просрочено")
        conn.execute("UPDATE agent_jobs SET status='answered',response_json=? WHERE id=?",(encoded,job_id))
    log.event("agent.answer",place=place_id,job=job_id,role=payload["role"])
    return {"ok":True}


@router.post("/{place_id}/status")
async def status(place_id:str,body:StatusChange,request:Request):
    authorize(place_id,request)
    db.execute("UPDATE external_venues SET status=?,last_error='' WHERE place_id=?",("ready" if body.enabled else "offline",place_id))
    engine = request.app.state.engine
    state = db.run()
    if body.enabled and state["day"] and not state["day_closed"]:
        with db.at_place(place_id):
            if not db.scheduled_left(state["day"]):
                engine._plan_next(state["day"], max(engine._live_minutes(), db.place(place_id)["open_min"]))
    engine.notify({"type":"venue"})
    log.event("venue.status",place=place_id,enabled=body.enabled)
    return {"ok":True}


async def agent_request(place_id,payload,timeout):
    ident=secrets.token_hex(16)
    now=time.time()
    payload={**payload,"schema_version":1,"request_id":ident,"place_id":place_id,"deadline":now+timeout}
    with db.tx() as conn:
        conn.execute("DELETE FROM agent_jobs WHERE status!='pending' AND created_at<?",(now-86400,))
        conn.execute("INSERT INTO agent_jobs(id,place_id,payload_json,status,deadline,created_at) VALUES(?,?,?,'pending',?,?)",
                     (ident,place_id,json.dumps(payload,ensure_ascii=False),now+timeout,now))
    log.event("agent.request",place=place_id,job=ident,role=payload["role"])
    try:
        while time.time()<now+timeout:
            row=db.one("SELECT status,response_json FROM agent_jobs WHERE id=?",(ident,))
            if not row or row["status"] not in ("pending","answered"):
                raise TimeoutError("Задание отменено")
            if row["status"]=="answered":
                return json.loads(row["response_json"])
            await asyncio.sleep(0.1)
        raise TimeoutError("Внешний агент не ответил вовремя")
    finally:
        db.execute("UPDATE agent_jobs SET status='expired' WHERE id=? AND status='pending'",(ident,))
