import json
import time

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import app.db as db
from app import log
from app.config import IDLE_PAUSE_S, SPEEDS, STATIC
from app.digest import digest as make_digest
from app.engine import Engine
from app.hub import Hub
from app.llm import LLM
from app.view import snapshot

app = FastAPI(title="SimCheck")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def watch_requests(request: Request, call_next):
    """Без входа: страница открыта всем в сети. Ошибки и медленные запросы пишутся в журнал."""
    path = request.url.path
    began = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        log.event("http.error", "error", method=request.method, path=path, **log.exc_fields(exc))
        return JSONResponse({"detail": "Внутренняя ошибка, подробности в журнале"}, status_code=500)
    took = int((time.perf_counter() - began) * 1000)
    if path.startswith("/api/") and (response.status_code >= 400 or (took > 800 and path != "/api/director")):
        log.event("http.slow" if response.status_code < 400 else "http.status",
                  "warn", method=request.method, path=path, status=response.status_code, ms=took)
    if path == "/" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


HEALTH = {"at": 0.0, "payload": {"ok": False, "detail": "ещё не проверяли"}}


def pause_when_empty() -> None:
    """Зрителей не осталось: прогон ставится на паузу, чтобы симуляция не шла впустую."""
    if db.run()["status"] != "running":
        return
    app.state.engine.pause()
    db.set_run(message="Нет зрителей: прогон поставлен на паузу")
    log.event("run.autopause", idle_s=hub.idle_seconds)
    hub.changed()


async def full_snapshot() -> dict:
    data = snapshot()
    data["llm_health"] = await llm_health()
    data["viewers"] = hub.count
    return data


hub = Hub(full_snapshot, IDLE_PAUSE_S, pause_when_empty)


def notify(payload: dict) -> None:
    """Движок сообщает об изменении: всем зрителям уйдёт свежий снимок."""
    hub.changed()


@app.on_event("startup")
async def startup() -> None:
    db.connect()
    if db.run()["status"] == "running":
        db.set_run(status="paused", phase="")
    app.state.llm = LLM()
    app.state.engine = Engine(app.state.llm, notify)
    app.state.engine.recover()
    hub.start()
    run = db.run()
    log.event("app.start", db=str(db.DB_PATH) if hasattr(db, "DB_PATH") else None, log=str(log.path()),
              model=db.setting("llm_model"), llm_url=db.setting("llm_base_url"),
              day=run["day"], clock=run["clock"], status=run["status"], idle_pause_s=IDLE_PAUSE_S)


@app.on_event("shutdown")
async def shutdown() -> None:
    log.event("app.stop")
    await hub.stop()
    await app.state.llm.aclose()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/login")
def old_login():
    """Входа больше нет: старые закладки ведут на страницу."""
    return RedirectResponse("/", status_code=303)


async def llm_health() -> dict:
    now = time.time()
    if now - HEALTH["at"] < 10:
        return HEALTH["payload"]
    payload = await app.state.llm.health()
    if bool(payload.get("ok")) != bool(HEALTH["payload"].get("ok")) or HEALTH["at"] == 0.0:
        log.event("llm.health", "info" if payload.get("ok") else "warn", ok=payload.get("ok"), detail=payload.get("detail"))
    HEALTH["at"] = now
    HEALTH["payload"] = payload
    return payload


@app.get("/api/health")
async def health():
    return {"app": "ok", "llm": await llm_health()}


@app.get("/api/snapshot")
async def api_snapshot():
    return await full_snapshot()


@app.get("/api/visits/{visit_id}")
def api_visit(visit_id: int):
    row = db.visit(visit_id)
    if row is None:
        raise HTTPException(404, "Визит не найден")
    return row


@app.get("/api/llm/{call_id}")
def api_llm(call_id: int):
    row = db.llm_call(call_id)
    if row is None:
        raise HTTPException(404, "Запрос не найден")
    return row


class Control(BaseModel):
    action: str
    speed: float | None = None


class Settings(BaseModel):
    base_url: str = Field(min_length=8)
    model: str = Field(min_length=1)
    timeout: int = Field(ge=5, le=180)
    critic_base_url: str = ""
    critic_model: str = ""
    api_key: str = ""


class Direct(BaseModel):
    text: str = Field(min_length=2, max_length=200)


class CommandError(Exception):
    """Команда не принята: код как у HTTP и текст для зрителя."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


async def do_control(action: str, speed: float | None = None) -> None:
    engine: Engine = app.state.engine
    log.event("api.control", action=action, speed=speed)
    if action == "pause":
        engine.pause()
    elif action == "reset":
        await engine.reset()
        HEALTH["at"] = 0
    elif action == "speed":
        if speed not in SPEEDS:
            raise CommandError(400, "Темп: 1, 2, 4 или 8")
        engine.set_speed(speed)
    elif action in ("step", "day", "auto", "resume"):
        goal = db.run()["goal"] if action == "resume" else action
        if goal == "idle":
            goal = "step"
        engine.kick(goal)
    else:
        raise CommandError(400, "Неизвестное действие")
    hub.changed()


async def do_director(text: str) -> None:
    log.event("api.director", text=text)
    try:
        await app.state.engine.direct(text)
    except ValueError as exc:
        raise CommandError(409, str(exc)) from exc
    hub.changed()


def do_end_event(event_id) -> None:
    try:
        ident = int(event_id)
    except (TypeError, ValueError) as exc:
        raise CommandError(422, "Нужен номер события") from exc
    if not app.state.engine.end_event(ident):
        raise CommandError(404, "Такого действующего события нет")
    hub.changed()


def do_settings(body: Settings) -> None:
    log.event("settings.save", base_url=body.base_url, model=body.model, timeout=body.timeout,
              critic_url=body.critic_base_url or None, critic_model=body.critic_model or None,
              key_changed=bool(body.api_key.strip()))
    db.save_settings(body.base_url, body.model, body.timeout, body.critic_base_url, body.critic_model, body.api_key)
    HEALTH["at"] = 0
    hub.changed()


@app.post("/api/control")
async def control(body: Control):
    try:
        await do_control(body.action, body.speed)
    except CommandError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    return await full_snapshot()


@app.post("/api/director")
async def api_director(body: Direct):
    """Режиссёр: владелец вбрасывает событие словами, модель переводит его в эффекты из каталога."""
    try:
        await do_director(body.text)
    except CommandError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    return await full_snapshot()


@app.post("/api/settings")
async def save_settings(body: Settings):
    do_settings(body)
    return await full_snapshot()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Сокет зрителя. Сервер присылает снимок при подключении и при каждом изменении. От зрителя приходят команды
    `{"id": 1, "cmd": "control" | "director" | "settings" | "ping", ...}`, в ответ `{"type": "reply", "id": 1, "ok": true}`."""
    await hub.connect(websocket)
    try:
        while True:
            try:
                msg = json.loads(await websocket.receive_text())
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            ident, cmd = msg.get("id"), msg.get("cmd")
            try:
                if cmd == "control":
                    await do_control(str(msg.get("action") or ""), msg.get("speed"))
                elif cmd == "director":
                    await do_director(Direct(text=str(msg.get("text") or "")).text)
                elif cmd == "end_event":
                    do_end_event(msg.get("event_id"))
                elif cmd == "settings":
                    do_settings(Settings(**{k: msg.get(k) for k in Settings.model_fields if k in msg}))
                elif cmd == "ping":
                    pass
                else:
                    raise CommandError(400, "Неизвестная команда")
            except CommandError as exc:
                await hub.reply(websocket, ident, False, status=exc.status, error=exc.detail)
                continue
            except ValueError as exc:
                await hub.reply(websocket, ident, False, status=422, error=str(exc)[:200])
                continue
            await hub.reply(websocket, ident, True)
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket)


class ClientLog(BaseModel):
    kind: str = Field(max_length=20)
    message: str = Field(default="", max_length=600)
    source: str = Field(default="", max_length=200)
    line: int | None = None
    col: int | None = None
    stack: str = Field(default="", max_length=1500)
    ms: int | None = None


CLIENT_RATE = {"minute": 0, "count": 0}


@app.post("/api/clientlog")
async def client_log(body: ClientLog, request: Request):
    """Ошибки страницы: консоль браузера агенту недоступна, поэтому страница шлёт их сюда."""
    minute = int(time.time() // 60)
    if CLIENT_RATE["minute"] != minute:
        CLIENT_RATE.update(minute=minute, count=0)
    CLIENT_RATE["count"] += 1
    if CLIENT_RATE["count"] > 30:
        return {"ok": False}
    log.event(f"client.{body.kind}", "warn" if body.kind == "slow" else "error", message=body.message,
              source=body.source or None, line=body.line, col=body.col, stack=body.stack or None, ms=body.ms,
              ua=(request.headers.get("user-agent") or "")[:80])
    return {"ok": True}


@app.get("/api/log")
def api_log(n: int = 200, level: str | None = None, ev: str | None = None, since: str | None = None,
            visit: int | None = None, q: str | None = None):
    """Журнал событий: `level` минимальный (debug, info, warn, error), `ev` префиксы через запятую,
    `since` как `10m`, `2h` или ISO-время, `visit` номер визита, `q` подстрока."""
    rows = log.read(n=n, level=level, ev=ev, since=since, visit=visit, q=q)
    return {"count": len(rows), "file": str(log.path()), "lines": rows}


@app.get("/api/digest")
async def api_digest():
    return make_digest(await llm_health())
