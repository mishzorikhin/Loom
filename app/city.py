"""Город: квартал вокруг заведений. Состояние живёт на сервере, страница только рисует кадры.

Физика мира здесь прописана и от событий не зависит: графы тротуаров и полос, светофоры, переходы, парковка,
препятствия, скорости и дистанции. Поведение людей и машин зависит от окружения: пешеход идёт по маршруту, который
учитывает препятствия и опасность вокруг, переходит дорогу, только когда машины стоят, останавливается поговорить со
знакомым, пережидает, если путь закрыт. Машины держат правую полосу и дистанцию, уступают пешеходам на переходе,
паркуются на свободное место и выезжают с него, когда есть просвет.

Что значит необычное событие, код не знает. Ведущий (`app/mind.py`) переводит событие в патч из
общих примитивов (`apply_patch`): создать объект с радиусом, проходимостью и опасностью, нанести урон, сообщить факт.
Остальное получается из той же физики и восприятия: путь в обход, остановка, бегство.

Шаг фиксированный (`DT` минут симуляции), случайность из зерна: прогон повторяем. Часы берутся из часов симуляции:
пауза замораживает город, новые сутки продолжают тот же город.
"""

import heapq
import math
import random
from dataclasses import dataclass, field

DT = 0.05
START, END = -30.0, 38.0
LENGTH = END - START
ROAD_X0, ROAD_X1 = 11.5, 15.5
CYCLE = 36
MAX_SPEED, ACCEL, BRAKE, GAP = 5.2, 1.8, 3.6, 0.8
VAN_SPEED = 4.4
BOUNDS = (-34.0, 40.0)

# Полосы: правостороннее движение. Номер полосы стабилен: страница рисует по нему направление.
LANES = (
    {"axis": "x", "fixed": 14.4, "dir": 1},
    {"axis": "x", "fixed": 12.6, "dir": -1},
    {"axis": "y", "fixed": 12.6, "dir": 1},
    {"axis": "y", "fixed": 14.4, "dir": -1},
)
CAR_KINDS = {"sedan": 2.8, "hatch": 2.45, "van": 3.2}
KIND_CODE = {"sedan": 0, "hatch": 1, "van": 2}

# Парковка: пять мест слева от поперечной улицы к югу от главной. Машина едет по полосе 2 и встаёт боком к дороге.
SLOT_X = 9.2
SLOT_WALK_X = 10.4
SLOT_Y = tuple(20.0 + 2.4 * i for i in range(5))

# Тротуары. Точки линий заданы по порядку; в пересечениях линий узлы общие.
SIDEWALK_LINES = (
    ((-3.6, -3.5), (-3.6, 2.2), (-3.6, 4.0), (-3.6, 9.6), (-3.6, 10.4)),                       # левее кофейни
    ((-3.6, -3.5), (1.2, -3.5), (6.8, -3.5), (10.4, -3.5)),                                    # над кофейней
    ((10.4, -3.5), (10.4, 10.4)),                                                               # правее кофейни
    ((-3.6, 10.4), (10.4, 10.4), (16.6, 10.4)),                                                 # перед кофейней
    ((16.6, -26.0), (16.6, -9.5), (16.6, -2.5), (16.6, 4.25), (16.6, 9.6), (16.6, 10.4), (16.6, 16.6), (16.6, 34.0)),
    ((-26.0, 16.6), (-7.6, 16.6), (10.4, 16.6), (16.6, 16.6), (21.0, 16.6), (34.0, 16.6)),
    ((-7.6, 16.6), (-7.6, 21.7), (-7.6, 29.1), (-7.6, 31.0)),                                   # тротуар у NeuralDeep
    ((10.4, 10.4), (10.4, 16.6)),                                                               # переход через главную улицу
    ((10.4, 16.6), (10.4, 18.0)) + tuple((SLOT_WALK_X, y) for y in SLOT_Y),                     # дорожка к парковке
)
# Переходы: (откуда, куда, ось перекрываемого движения). Остальные рёбра — обычные тротуары.
CROSSINGS = (
    ((10.4, 10.4), (10.4, 16.6), "x"),
    ((16.6, 10.4), (16.6, 16.6), "x"),
    ((10.4, 10.4), (16.6, 10.4), "y"),
    ((10.4, 16.6), (16.6, 16.6), "y"),
)
# Зона зебры вдоль полосы (координата u на оси движения) для машин перекрываемой оси.
ZEBRA = {
    ((10.4, 10.4), (10.4, 16.6)): (10.1, 10.8),
    ((16.6, 10.4), (16.6, 16.6)): (16.2, 16.9),
    ((10.4, 10.4), (16.6, 10.4)): (10.1, 10.8),
    ((10.4, 16.6), (16.6, 16.6)): (16.2, 16.9),
}
# Двери: входы в дома-жилища и заведения (спуры от тротуара). Двери заведений стоят в таблице `places`.
HOMES = {
    "h1": ((21.0, 17.3), (21.0, 16.6)),
    "h2": ((17.3, -9.5), (16.6, -9.5)),
    "h3": ((17.3, -2.5), (16.6, -2.5)),
    "h4": ((17.3, 4.25), (16.6, 4.25)),
    "h5": ((17.3, 9.6), (16.6, 9.6)),
    "h6": ((-6.5, 4.0), (-3.6, 4.0)),
    "h7": ((-6.5, 9.6), (-3.6, 9.6)),
    "h8": ((1.2, -6.5), (1.2, -3.5)),
    "h9": ((6.8, -6.5), (6.8, -3.5)),
}
# Входы заведений: юг и север. От этих точек страница ведёт гостя к двери зала по тротуару слева от стены.
# Зал каждого заведения одинаковой планировки и стоит в мире со сдвигом (`ROOM_AT`): входы сдвинуты так же.
ROOM_AT = {"cafe": (0.0, 0.0), "neuraldeep": (-4.0, 19.5)}
ALLEY_X, ENTRY_SOUTH_Y, ENTRY_NORTH_Y, DOOR_Y = -3.6, 9.6, 2.2, 5.9
ENTRIES = {
    place: ((ox + ALLEY_X, oy + ENTRY_SOUTH_Y), (ox + ALLEY_X, oy + ENTRY_NORTH_Y)) for place, (ox, oy) in ROOM_AT.items()
}
CAFE_ENTRIES = ENTRIES["cafe"]
EDGE_NODES = ((-26.0, 16.6), (34.0, 16.6), (16.6, -26.0), (16.6, 34.0))

PERCEPTION = 6.0
KINDS_OF_FLIP = (-1, 1)


def signal(minute: float, axis: str) -> str:
    """Свет для оси движения: та же формула, что на странице (`traffic.js`)."""
    t = (minute - 480) % CYCLE
    phase = t if axis == "x" else (t + 18) % CYCLE
    return "green" if phase < 12 else "yellow" if phase < 15 else "red"


def red_left(minute: float, axis: str) -> tuple[float, float]:
    """Сколько минут ось стоит на красном и сколько ещё простоит (0, 0, если свет не красный)."""
    t = (minute - 480) % CYCLE
    phase = t if axis == "x" else (t + 18) % CYCLE
    if phase < 15:
        return 0.0, 0.0
    return phase - 15, CYCLE - phase


def lane_s(lane: dict, u: float) -> float:
    return u - START if lane["dir"] > 0 else END - u


def lane_u(lane: dict, s: float) -> float:
    return START + s if lane["dir"] > 0 else END - s


def dist_point_segment(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


@dataclass
class Ent:
    """Объект мира: кратер, огонь, лужа, толпа, сцена. Что это такое, решает ведущий, физике важны только свойства."""
    id: int
    kind: str
    x: float
    y: float
    r: float = 1.0
    blocks: bool = False
    hazard: float = 0.0          # урон в минуту в центре, к краю убывает
    until: float | None = None   # абсолютная минута города, когда исчезнет
    glyph: dict = field(default_factory=dict)
    label: str = ""
    src: str = ""


@dataclass
class Ped:
    id: int
    name: str
    x: float
    y: float
    look: str
    client_id: int | None = None
    home: str | None = None
    speed: float = 2.0
    risk: float = 0.0
    trait: str = ""
    state: str = "walk"          # walk, wait, cross, chat, linger, inside, flee, down
    route: list = field(default_factory=list)       # оставшиеся узлы пути (координаты)
    prev: tuple | None = None
    goal: dict = field(default_factory=dict)
    agenda: list = field(default_factory=list)       # дела на сутки: {at, kind, ...}
    until: float = 0.0           # до какой минуты стоит (chat, linger, inside, wait-повтор)
    waited: float = 0.0
    hp: float = 1.0
    mood: str = "спокойствие"
    heading: int = 1
    chat_with: int | None = None
    inside: str | None = None
    seen: set = field(default_factory=set)
    alerts: list = field(default_factory=list)       # id новых объектов, которые агент заметил
    said: str = ""
    said_until: float = 0.0
    stuck: float = 0.0
    car: int | None = None       # машина, к которой он идёт или из которой вышел
    extra: bool = False
    started: bool = False        # уже вышел с узла `prev` на отрезок к `route[0]`
    plan_ver: int = 0            # версия мира, при которой построен маршрут


@dataclass
class Car:
    id: int
    lane: int
    s: float
    kind: str
    color: int
    taxi: bool = False
    v: float = 3.4
    brake: bool = False
    committed: bool = False
    state: str = "drive"         # drive, pull_in, parked, pull_out
    slot: int | None = None
    owner: int | None = None     # id пешехода-хозяина
    off: float = 0.0             # боковое смещение от полосы (0 — на полосе, 1 — на месте парковки)
    timer: float = 0.0
    stalled: float = 0.0
    wheel: float = 0.0

    @property
    def length(self) -> float:
        return CAR_KINDS[self.kind]

    @property
    def vmax(self) -> float:
        return VAN_SPEED if self.kind == "van" else MAX_SPEED


def _key(p) -> tuple:
    return (round(p[0], 2), round(p[1], 2))


class Graph:
    """Тротуары: узлы и рёбра. Рёбра-переходы помечены осью перекрываемого движения."""

    def __init__(self, doors: dict[str, tuple]):
        self.nodes: dict[tuple, dict] = {}
        self.adj: dict[tuple, list] = {}
        self.cross: dict[frozenset, dict] = {}
        crossing_keys = {frozenset((_key(a), _key(b))): (axis, (_key(a), _key(b))) for a, b, axis in CROSSINGS}
        for line in SIDEWALK_LINES:
            for a, b in zip(line, line[1:]):
                self._edge(a, b, crossing_keys)
        for door, junction in HOMES.values():
            self._edge(door, junction, crossing_keys)

    def _node(self, p):
        key = _key(p)
        self.adj.setdefault(key, [])
        return key

    def _edge(self, a, b, crossing_keys):
        ka, kb = self._node(a), self._node(b)
        if ka == kb or kb in {n for n, _ in self.adj[ka]}:
            return
        length = math.hypot(ka[0] - kb[0], ka[1] - kb[1])
        info = crossing_keys.get(frozenset((ka, kb)))
        edge = {"len": length, "axis": info[0] if info else None, "zebra": ZEBRA.get(info[1]) if info else None}
        self.adj[ka].append((kb, edge))
        self.adj[kb].append((ka, edge))
        if info:
            self.cross[frozenset((ka, kb))] = {**edge, "ids": set()}

    def edge(self, a, b) -> dict | None:
        for n, e in self.adj.get(a, []):
            if n == b:
                return e
        return None

    def nearest(self, x: float, y: float) -> tuple:
        return min(self.adj, key=lambda n: (n[0] - x) ** 2 + (n[1] - y) ** 2)

    def route(self, start: tuple, goal: tuple, blocked, penalty=None) -> list | None:
        """Кратчайший путь по узлам. `blocked(a, b)` закрывает ребро, `penalty(a, b)` добавляет цену (опасность, переход)."""
        if start == goal:
            return []
        heap = [(0.0, start)]
        best = {start: 0.0}
        came: dict[tuple, tuple] = {}
        while heap:
            cost, node = heapq.heappop(heap)
            if node == goal:
                out = [node]
                while out[-1] in came:
                    out.append(came[out[-1]])
                out.reverse()
                return out[1:]
            if cost > best.get(node, 1e18):
                continue
            for nxt, edge in self.adj[node]:
                if blocked(node, nxt):
                    continue
                add = edge["len"] + (3.0 if edge["axis"] else 0.0) + (penalty(node, nxt) if penalty else 0.0)
                total = cost + add
                if total < best.get(nxt, 1e18):
                    best[nxt] = total
                    came[nxt] = node
                    heapq.heappush(heap, (total, nxt))
        return None


NAMES = (
    "Аня", "Борис", "Вика", "Гриша", "Дана", "Егор", "Жанна", "Захар", "Ирина", "Костя", "Люба", "Миша", "Нина", "Оскар",
    "Поля", "Рита", "Саша", "Тоня", "Ульяна", "Фёдор", "Хаим", "Цветана", "Чарли", "Шура",
)
MOODS_QUIET = ("спокойствие", "бодрость", "усталость", "радость")
TRAITS_STREET = ("торопится", "гуляет не спеша", "любопытный", "осторожный", "общительный", "рассеянный")


class City:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)
        self.doors = {key: (ox + ALLEY_X + 2.9, oy + DOOR_Y) for key, (ox, oy) in ROOM_AT.items()}
        self.entries = dict(ENTRIES)
        self.graph = Graph({})
        self.t = 0.0                  # абсолютная минута города
        self.day: int | None = None
        self.minute = 0.0             # минута суток
        self.peds: dict[int, Ped] = {}
        self.cars: dict[int, Car] = {}
        self.ents: dict[int, Ent] = {}
        self.slots: list[int | None] = [None] * len(SLOT_Y)
        self.next_id = 1
        self.version = 0              # растёт при смене объектов мира: страница знает, когда перечитать
        self.roster_version = 0
        self.events: list[dict] = []  # прибытия и уходы для движка: {kind, client_id, place, minute, side}
        self.log: list[tuple] = []    # (уровень, событие, поля) для журнала
        self.known: dict[tuple, int] = {}    # пара пешеходов -> сколько раз разговаривали
        self.met: dict[tuple, float] = {}    # пара -> минута последней встречи (чтобы не бросать кубик на каждом шаге)
        self.facts: list[dict] = []   # сообщённые факты: {id, text, x, y, r, t}
        self.places: dict[str, dict] = {}    # id -> {open_min, close_min, status}
        self.inside: dict[str, dict[int, str]] = {}
        self._spawn_clock = 0.0
        self._agenda_day = -1

    def clear(self, seed: int | None = None) -> None:
        """Новый прогон: город пустой, как при создании."""
        self.__init__(seed)

    # ---------- общие ----------

    def new_id(self) -> int:
        self.next_id += 1
        return self.next_id - 1

    def note(self, level: str, event: str, **fields) -> None:
        self.log.append((level, event, fields))

    def set_places(self, rows: list[dict]) -> None:
        previous = self.places
        self.places = {row["id"]: {**row, **({"status": previous[row["id"]]["status"]} if row["id"] in previous and "status" in previous[row["id"]] else {})} for row in rows}
        from app.venue_api import PLOTS, external
        for row in rows:
            if row.get("type") != "custom":
                continue
            extra = external(row["id"])
            if not extra:
                continue
            plot = PLOTS[extra["plot_id"]]
            ox, oy = plot["ox"], plot["oy"]
            entries = ((ox + ALLEY_X, oy + ENTRY_SOUTH_Y), (ox + ALLEY_X, oy + ENTRY_NORTH_Y))
            self.entries[row["id"]] = entries
            self.doors[row["id"]] = (row["door_x"], row["door_y"])
            self.graph._edge(entries[0], entries[1], {})
            near = min(entries, key=lambda p: math.dist(p, plot["junction"]))
            self.graph._edge(near, tuple(plot["junction"]), {})

    def place_open(self, place_id: str, minute: float | None = None) -> bool:
        row = self.places.get(place_id)
        if row is None:
            return True
        if row.get("type") == "custom":
            from app.venue_api import external
            ext = external(place_id)
            if ext and ext["status"] == "offline":
                return False
        m = self.minute if minute is None else minute
        return row.get("status", "open") == "open" and row["open_min"] <= m < row["close_min"]

    # ---------- время ----------

    def advance(self, day: int, minute: float) -> int:
        """Довести город до `minute` суток `day` шагами по `DT`. Возвращает число шагов.
        Первый вызов только ставит часы. Если часы ушли назад (новый прогон), город подстраивается без доливки."""
        target = day * 1440 + minute
        if self.day is None:
            self.t, self.day, self.minute = target, day, minute
            self._plan_day()
            return 0
        if target < self.t:
            self.t, self.day, self.minute = target, day, minute
            return 0
        if day != self.day:
            self.day = day
            self._plan_day()
        steps = 0
        while self.t + DT <= target + 1e-9 and steps < 4000:
            self.step()
            steps += 1
        if steps == 4000:
            self.t = target  # слишком большой скачок (долгая пауза): без доливки
        self.minute = self.t % 1440
        return steps

    def step(self) -> None:
        self.t += DT
        self.minute = self.t % 1440
        self._expire()
        self._spawn()
        self._agendas()
        self._move_cars()
        self._move_peds()
        self._encounters()
        self._hazards()

    def _expire(self) -> None:
        gone = [e.id for e in self.ents.values() if e.until is not None and self.t >= e.until]
        for ident in gone:
            self.ents.pop(ident)
        if gone:
            self.version += 1
            self.note("info", "city.entity.end", ids=gone)

    # ---------- население и сутки ----------

    def populate(self, count: int = 14) -> None:
        """Постоянные жители без записи гостя: у каждого дом, имя и дела на сутки."""
        homes = list(HOMES)
        for i in range(count):
            home = homes[i % len(homes)]
            ped = self._new_ped(self.rng.choice(NAMES), home=home, extra=True)
            ped.state = "inside"
            ped.inside = home
            door = HOMES[home][0]
            ped.x, ped.y = door
        self._agenda_day = -1
        if self.day is not None:
            self._plan_day()
        self.roster_version += 1

    def _new_ped(self, name: str, home: str | None = None, client_id: int | None = None, extra: bool = False) -> Ped:
        ident = self.new_id()
        ped = Ped(
            id=ident, name=name, x=0.0, y=0.0, look=name if client_id else f"прохожий{ident}", client_id=client_id,
            home=home, speed=1.5 + self.rng.random() * 0.9, risk=1.0 if self.rng.random() < 0.08 else 0.0,
            trait=self.rng.choice(TRAITS_STREET), mood=self.rng.choice(MOODS_QUIET), extra=extra,
        )
        self.peds[ident] = ped
        return ped

    def _plan_day(self) -> None:
        """Дела жителей на сутки. Случайно, но по сезону суток: людей на улице больше утром, в обед и вечером."""
        if self._agenda_day == self.day:
            return
        self._agenda_day = self.day
        for ped in self.peds.values():
            if not ped.extra:
                continue
            ped.agenda = []
            for _ in range(self.rng.choice((1, 2, 2, 3))):
                at = self.rng.choice((7.5, 9.0, 12.5, 13.5, 17.0, 18.5, 20.0, 21.5)) * 60 + self.rng.uniform(-40, 40)
                roll = self.rng.random()
                if roll < 0.4:
                    kind = {"kind": "stroll", "to": self.rng.choice(list(self.graph.adj)), "linger": self.rng.uniform(1, 6)}
                elif roll < 0.7:
                    kind = {"kind": "visit", "place": "neuraldeep", "linger": self.rng.uniform(4, 12)}
                else:
                    kind = {"kind": "stroll", "to": self.rng.choice(EDGE_NODES), "linger": 0.0}
                ped.agenda.append({"at": at, **kind})
            ped.agenda.sort(key=lambda row: row["at"])

    def _agendas(self) -> None:
        for ped in self.peds.values():
            if not ped.extra or ped.state != "inside" or ped.inside not in HOMES or not ped.agenda:
                continue
            if self.minute < ped.agenda[0]["at"]:
                continue
            row = ped.agenda.pop(0)
            if self.minute - row["at"] > 120:
                continue
            self._leave_home(ped, row)

    def _leave_home(self, ped: Ped, row: dict) -> None:
        door, junction = HOMES[ped.home]
        ped.x, ped.y = door
        ped.prev = _key(door)
        ped.state = "walk"
        ped.inside = None
        if row["kind"] == "visit":
            target = self._entry_node(row["place"], _key(junction))
            if target is None or not self.place_open(row["place"]):
                row = {"kind": "stroll", "to": self.graph.nearest(*junction), "linger": 2.0}
            else:
                ped.goal = {"kind": "visit", "place": row["place"], "linger": row["linger"], "to": target}
        if row["kind"] == "stroll":
            ped.goal = {"kind": "stroll", "to": _key(row["to"]), "linger": row["linger"]}
        self._plan_route(ped)

    def _spawn(self) -> None:
        """Приезжающие машины и прохожие с краёв карты: число зависит от времени суток."""
        self._spawn_clock += DT
        if self._spawn_clock < 0.5:
            return
        self._spawn_clock = 0.0
        hour = self.minute / 60
        day = 0.12 + 0.88 * max(0.0, math.sin(math.pi * (hour - 5) / 17)) if 5 <= hour <= 22 else 0.12
        for index, lane in enumerate(LANES):
            if self.rng.random() < 0.07 * day:
                self._spawn_car(index)
        if self.rng.random() < 0.10 * day and len([p for p in self.peds.values() if not p.extra]) < 30:
            node = self.rng.choice(EDGE_NODES)
            other = self.rng.choice([n for n in EDGE_NODES if n != node])
            ped = self._new_ped(self.rng.choice(NAMES))
            ped.x, ped.y = node
            ped.prev = _key(node)
            ped.goal = {"kind": "exit", "to": _key(other), "linger": 0.0}
            self._plan_route(ped)

    def _spawn_car(self, lane_index: int, owner: int | None = None, slot: int | None = None, kind: str | None = None) -> Car | None:
        cars = [c for c in self.cars.values() if c.lane == lane_index and c.state in ("drive", "pull_in", "pull_out")]
        if any(c.s < c.length + 3.5 for c in cars):
            return None
        car = Car(id=self.new_id(), lane=lane_index, s=0.0, kind=kind or self.rng.choice(("sedan", "sedan", "hatch", "van")),
                  color=self.rng.randrange(8), taxi=self.rng.random() < 0.08, owner=owner, slot=slot)
        self.cars[car.id] = car
        self.roster_version += 1
        return car

    # ---------- машины ----------

    def _lane_cars(self, lane_index: int) -> list[Car]:
        return sorted((c for c in self.cars.values() if c.lane == lane_index and c.state != "parked"), key=lambda c: c.s)

    def _stop_s(self, lane: dict, car: Car) -> float:
        line = ROAD_X0 - 2.4 - car.length / 2 if lane["dir"] > 0 else ROAD_X1 + 2.4 + car.length / 2
        return line - START if lane["dir"] > 0 else END - line

    def _cross_span(self, lane: dict, length: float = 0.0) -> tuple[float, float]:
        return (ROAD_X0 - START, ROAD_X1 - START) if lane["dir"] > 0 else (END - ROAD_X1, END - ROAD_X0)

    def _blockers(self, lane: dict, car: Car) -> float | None:
        """Ближайшая преграда впереди на полосе: объект с `blocks`, лежащий на ней. Возвращает расстояние до заднего края."""
        best = None
        for e in self.ents.values():
            if not e.blocks:
                continue
            across = abs((e.y if lane["axis"] == "x" else e.x) - lane["fixed"])
            if across > e.r + 0.9:
                continue
            half = math.sqrt(max(0.0, (e.r + 0.4) ** 2 - across ** 2))
            u = e.x if lane["axis"] == "x" else e.y
            s0 = lane_s(lane, u - half) if lane["dir"] > 0 else lane_s(lane, u + half)
            gap = s0 - car.s - car.length / 2
            if gap >= -0.5 and (best is None or gap < best):
                best = gap
        return best

    def _zebras(self, lane: dict) -> list[tuple[float, set]]:
        out = []
        for key, info in self.graph.cross.items():
            if info["axis"] != lane["axis"] or not info["zebra"]:
                continue
            u0, u1 = info["zebra"]
            s0 = lane_s(lane, u0) if lane["dir"] > 0 else lane_s(lane, u1)
            out.append((s0, info["ids"]))
        return out

    def _move_cars(self) -> None:
        by_lane = {i: self._lane_cars(i) for i in range(len(LANES))}
        old = {c.id: (c.s, c.v) for c in self.cars.values()}
        gone = []
        for lane_index, cars in by_lane.items():
            lane = LANES[lane_index]
            color = signal(self.minute, lane["axis"])
            for car in cars:
                s0, v0 = old[car.id]
                if car.state == "pull_in":
                    car.off = min(1.0, car.off + DT / 0.5)
                    car.v = 0.0
                    if car.off >= 1.0:
                        self._park(car)
                    continue
                if car.state == "pull_out" and car.off > 0:
                    car.off = max(0.0, car.off - DT / 0.5)
                    car.v = 0.0
                    if car.off <= 0.0:
                        car.state = "drive"
                        car.slot = None
                    continue
                gap, lead_v = math.inf, 0.0
                for other in cars:
                    if other is car or other.s <= s0:
                        continue
                    free = other.s - s0 - (car.length + other.length) / 2
                    if free < gap:
                        gap, lead_v = free, old[other.id][1]
                limit = math.inf
                stop = self._stop_s(lane, car)
                distance = stop - s0
                if color == "yellow" and distance >= 0 and distance <= v0 * v0 / (2 * BRAKE) + v0 * DT + 0.15:
                    car.committed = True
                if not car.committed and distance >= -0.01 and color != "green":
                    limit = max(0.0, distance)
                entry, exit_ = self._cross_span(lane)
                if distance >= -0.01:
                    for other_lane_index, others in by_lane.items():
                        other_lane = LANES[other_lane_index]
                        if other_lane["axis"] == lane["axis"]:
                            continue
                        e2, x2 = self._cross_span(other_lane)
                        if any(o.s + o.length / 2 > e2 and o.s - o.length / 2 < x2 for o in others):
                            limit = min(limit, max(0.0, distance))
                            break
                for zone_s, ids in self._zebras(lane):
                    to = zone_s - car.length / 2 - 0.3 - s0
                    if ids and to >= -0.2:
                        limit = min(limit, max(0.0, to))
                block = self._blockers(lane, car)
                if block is not None:
                    limit = min(limit, max(0.0, block))
                if car.slot is not None and car.owner is not None and car.state == "drive":
                    slot_s = SLOT_Y[car.slot] - START
                    to = slot_s - s0
                    if to >= -0.1:
                        limit = min(limit, max(0.0, to))
                        if to < 0.3 and v0 < 0.4:
                            car.state, car.v, car.brake = "pull_in", 0.0, True
                            continue
                effective = min(gap, limit + GAP)
                ahead = 0.0 if limit + GAP < gap else lead_v
                closing = max(0.0, v0 * (v0 - ahead) / (2 * math.sqrt(ACCEL * BRAKE)))
                desired = GAP + v0 * 0.65 + closing
                acc = ACCEL * (1 - (v0 / car.vmax) ** 4 - (desired / max(0.01, effective)) ** 2)
                acc = max(-BRAKE, min(ACCEL, acc))
                v1 = max(0.0, v0 + acc * DT)
                if v1 < 0.03 and effective < GAP + 0.05:
                    v1 = 0.0
                travel = (v0 + v1) / 2 * DT
                max_travel = max(0.0, min(limit, gap - GAP))
                if travel >= max_travel:
                    travel, v1 = max_travel, 0.0
                car.s = s0 + travel
                if car.s > entry:
                    car.committed = False
                car.v = v1
                car.brake = acc < -0.3 or v1 < 0.08
                car.wheel += travel
                car.stalled = car.stalled + DT if v1 < 0.05 and block is not None else 0.0
                if car.s >= LENGTH or car.stalled > 12:
                    gone.append(car.id)
        for car in self.cars.values():
            if car.state == "pull_out" and car.off <= 0:
                pass
        for ident in gone:
            car = self.cars.pop(ident)
            if car.stalled > 12:
                self.note("warn", "city.car.turned_back", car=ident, lane=car.lane)
            if car.slot is not None and self.slots[car.slot] == ident:
                self.slots[car.slot] = None
            self.roster_version += 1

    def _park(self, car: Car) -> None:
        car.state = "parked"
        car.timer = 0.0         # станет временем возвращения хозяина, когда он сядет обратно
        ped = self.peds.get(car.owner) if car.owner else None
        if ped is not None and ped.state == "inside" and ped.inside == f"car{car.id}":
            ped.inside = None
            ped.state = "walk"
            ped.x, ped.y = SLOT_WALK_X, SLOT_Y[car.slot]
            ped.prev = _key((SLOT_WALK_X, SLOT_Y[car.slot]))
            self._plan_route(ped)

    def _unpark(self, car: Car) -> bool:
        """Выезд с места: нужен просвет на полосе позади."""
        lane = LANES[car.lane]
        slot_s = SLOT_Y[car.slot] - START
        for other in self.cars.values():
            if other.lane == car.lane and other.state != "parked" and slot_s - 7.0 < other.s < slot_s + other.length:
                return False
        car.state, car.v, car.s = "pull_out", 0.0, slot_s
        self.slots[car.slot] = None
        return True

    # ---------- пешеходы ----------

    def _hazard_cost(self, a: tuple, b: tuple) -> float:
        cost = 0.0
        for e in self.ents.values():
            if e.hazard > 0 or e.blocks:
                d = dist_point_segment(e.x, e.y, a[0], a[1], b[0], b[1])
                if d < e.r + 1.5:
                    cost += 30.0 * (e.hazard + 0.3)
        return cost

    def _blocked(self, a: tuple, b: tuple) -> bool:
        for e in self.ents.values():
            if e.blocks and dist_point_segment(e.x, e.y, a[0], a[1], b[0], b[1]) < e.r:
                return True
        return False

    def _plan_route(self, ped: Ped) -> bool:
        goal = ped.goal.get("to")
        if goal is None:
            return False
        if ped.prev is None:
            ped.prev = self.graph.nearest(ped.x, ped.y)
        midway = ped.started and ped.route
        start = ped.route[0] if midway else ped.prev
        route = self.graph.route(start, goal, self._blocked, self._hazard_cost)
        ped.plan_ver = self.version
        if route is None:
            ped.route = [start] if midway else []
            if not midway:
                ped.state = "wait"
                ped.until = self.t + 2.0
            return False
        ped.route = ([start] if midway else []) + route
        if ped.state == "wait" and ped.route:
            ped.state = "walk"
        return True

    def _crossing_ok(self, ped: Ped, info: dict) -> bool:
        axis = info["axis"]
        red, left = red_left(self.minute, axis)
        need = info["len"] / max(0.5, ped.speed) + 0.6
        if red >= 1.0 and left >= need:
            return True
        if ped.risk and ped.waited > 3.0:
            # нетерпеливый идёт и без света, если на подходах нет движущихся машин
            for car in self.cars.values():
                lane = LANES[car.lane]
                if lane["axis"] != axis or car.state == "parked":
                    continue
                zone = info["zebra"]
                u = lane_u(lane, car.s)
                toward = zone[0] - u if lane["dir"] > 0 else u - zone[1]
                if -2.0 < toward < 9.0 and car.v > 0.3:
                    return False
            return True
        return False

    def _move_peds(self) -> None:
        for ped in list(self.peds.values()):
            if ped.said and self.t >= ped.said_until:
                ped.said = ""
            if ped.state == "inside":
                self._inside(ped)
                continue
            if ped.state in ("chat", "linger", "down"):
                if self.t >= ped.until:
                    self._end_pause(ped)
                continue
            if not ped.route:
                if ped.state == "wait":
                    if self.t >= ped.until:
                        ped.waited += 2.0
                        ped.until = self.t + 2.0
                        if self._plan_route(ped):
                            ped.waited = 0.0
                        elif ped.waited > 24:
                            self._give_up(ped)
                    continue
                self._arrived(ped)
                continue
            if ped.prev is None:
                ped.prev = self.graph.nearest(ped.x, ped.y)
            target = ped.route[0]
            if not ped.started:
                info = self.graph.edge(ped.prev, target)
                if info and info["axis"]:
                    if self._crossing_ok(ped, info):
                        ped.state = "cross"
                        self.graph.cross[frozenset((ped.prev, target))]["ids"].add(ped.id)
                        ped.waited = 0.0
                    else:
                        ped.state = "wait"
                        ped.waited += DT
                        continue
                elif ped.state == "wait":
                    ped.state = "walk"
                ped.started = True
            speed = ped.speed * (1.6 if ped.state == "flee" else 1.0) * (0.5 if ped.hp < 0.4 else 1.0)
            step = speed * DT
            dx, dy = target[0] - ped.x, target[1] - ped.y
            dist = math.hypot(dx, dy)
            if dist > 1e-9:
                ped.heading = 1 if dx - dy >= 0 else -1
            if dist > step:
                ped.x += dx / dist * step
                ped.y += dy / dist * step
                continue
            ped.x, ped.y = target
            ped.route.pop(0)
            if ped.state == "cross":
                key = frozenset((ped.prev, target))
                if key in self.graph.cross:
                    self.graph.cross[key]["ids"].discard(ped.id)
                ped.state = "walk"
            ped.prev = target
            ped.started = False
            if ped.route and ped.plan_ver != self.version:
                self._plan_route(ped)

    def _end_pause(self, ped: Ped) -> None:
        ped.chat_with = None
        if ped.state == "down":
            ped.hp = 0.45
        ped.state = "walk"
        goal = ped.goal.get("to")
        if goal is None or (ped.x, ped.y) == goal:
            ped.route = []
            self._arrived(ped)
        elif not ped.route:
            self._plan_route(ped)

    def _arrived(self, ped: Ped) -> None:
        goal = ped.goal
        kind = goal.get("kind")
        if kind == "visit" and not goal.get("arrived"):
            place = goal["place"]
            entries = self.entries.get(place)
            side = 0 if entries and _key((ped.x, ped.y)) == _key(entries[0]) else 1
            if ped.client_id:
                # человек у двери: дальше визит ведёт движок, он же вернёт человека в город командой `release`
                self.events.append({"kind": "arrived", "client_id": ped.client_id, "place": place, "minute": self.minute, "side": side,
                                    "ped": ped.id, "t": self.t})
                ped.state, ped.inside = "inside", place
                ped.goal = {**goal, "arrived": True, "side": side}
                self.inside.setdefault(place, {})[ped.id] = ped.name
                self.note("info", "city.arrive", ped=ped.id, client=ped.client_id, place=place, side=side)
                return
            if not self.place_open(place):
                self.note("info", "city.closed", ped=ped.id, place=place)
                self._depart(ped, reason="closed")
                return
            ped.state, ped.inside = "inside", place
            ped.until = self.t + goal.get("linger", 6.0)
            ped.goal = {**goal, "arrived": True, "side": side}
            self.inside.setdefault(place, {})[ped.id] = ped.name
            return
        if kind in ("stroll",) and goal.get("linger", 0) > 0 and not goal.get("lingered"):
            ped.state = "linger"
            ped.until = self.t + goal["linger"]
            ped.goal = {**goal, "lingered": True}
            return
        if kind == "car":
            car = self.cars.get(goal.get("car"))
            if car is not None and car.state == "parked":
                ped.state, ped.inside = "inside", f"car{car.id}"
                car.timer = max(self.t, 1e-6)
                return
        if kind == "exit":
            self.peds.pop(ped.id, None)
            self.roster_version += 1
            return
        if kind == "flee":
            ped.goal = goal.get("resume") or {}
            ped.state = "walk"
            if ped.goal.get("to") and (ped.x, ped.y) != ped.goal["to"]:
                self._plan_route(ped)
                return
            if ped.goal.get("kind") and ped.goal.get("kind") != "flee":
                self._arrived(ped)
                return
        self._depart(ped)

    def _depart(self, ped: Ped, reason: str = "") -> None:
        """Человек закончил дело: домой, к машине или за край карты."""
        ped.goal = {"kind": "home" if ped.home else "exit"}
        if ped.car is not None and ped.car in self.cars and self.cars[ped.car].state == "parked":
            car = self.cars[ped.car]
            ped.goal = {"kind": "car", "car": car.id, "to": _key((SLOT_WALK_X, SLOT_Y[car.slot]))}
        elif ped.home:
            ped.goal = {"kind": "home", "to": _key(HOMES[ped.home][1])}
        else:
            ped.goal = {"kind": "exit", "to": _key(self.rng.choice(EDGE_NODES))}
        ped.state = "walk"
        ped.inside = None
        self._plan_route(ped)

    def _inside(self, ped: Ped) -> None:
        where = ped.inside
        if where in HOMES:
            return                      # выходит по делам из `_agendas`
        if ped.client_id and where in self.places and ped.goal.get("arrived"):
            return                      # внутри заведения: выходит по команде движка (`release`)
        if isinstance(where, str) and where.startswith("car"):
            car = self.cars.get(int(where[3:]))
            if car is None:
                self.peds.pop(ped.id, None)
                return
            if car.state == "parked" and car.timer and self.t - car.timer >= 0.3 and self._unpark(car):
                car.owner = None
                self.peds.pop(ped.id, None)
                self.roster_version += 1
                self.note("info", "city.car.leave", car=car.id, ped=ped.id)
            return
        if where in self.places and self.t >= ped.until:
            self.inside.get(where, {}).pop(ped.id, None)
            ped.state = "walk"
            node = self.entries[where][ped.goal.get("side", 0)]
            ped.x, ped.y = node
            ped.prev = _key(node)
            self._depart(ped)

    def _give_up(self, ped: Ped) -> None:
        self.note("warn", "city.gave_up", ped=ped.id, client=ped.client_id, goal=ped.goal.get("kind"))
        if ped.client_id and ped.goal.get("kind") == "visit":
            self.events.append({"kind": "gave_up", "client_id": ped.client_id, "place": ped.goal.get("place"), "minute": self.minute,
                                "why": "путь закрыт", "t": self.t})
        ped.waited = 0.0
        self._depart(ped)

    # ---------- встречи, опасность ----------

    def _encounters(self) -> None:
        """Знакомые и случайные люди останавливаются поговорить. Решение по паре принимается один раз за встречу."""
        if int(self.t / DT) % 4:
            return
        walkers = [p for p in self.peds.values() if p.state == "walk" and p.route and p.hp > 0.5]
        for i, a in enumerate(walkers):
            for b in walkers[i + 1:]:
                if abs(a.x - b.x) > 0.9 or abs(a.y - b.y) > 0.9:
                    continue
                key = (min(a.id, b.id), max(a.id, b.id))
                if self.t - self.met.get(key, -999) < 25:
                    continue
                self.met[key] = self.t
                friends = self.known.get(key, 0)
                chance = min(0.9, 0.35 + 0.1 * friends) if friends else 0.04 + (0.1 if "общительный" in (a.trait, b.trait) else 0.0)
                if "торопится" in (a.trait, b.trait):
                    chance *= 0.3
                if a.goal.get("kind") == "visit" and a.client_id and not friends:
                    chance *= 0.5
                if self.rng.random() < chance:
                    length = self.rng.uniform(2.0, 6.0)
                    for p, q in ((a, b), (b, a)):
                        p.state, p.chat_with, p.until = "chat", q.id, self.t + length
                    self.known[key] = friends + 1
                    self.note("info", "city.chat", a=a.id, b=b.id, names=[a.name, b.name], known=friends + 1, minutes=round(length, 1))

    def _hazards(self) -> None:
        if not self.ents or int(self.t / DT) % 2:
            return
        for ped in self.peds.values():
            if ped.state in ("inside", "down"):
                continue
            hurt = 0.0
            for e in self.ents.values():
                d = math.hypot(ped.x - e.x, ped.y - e.y)
                if e.hazard > 0 and d < e.r:
                    hurt += e.hazard * (1 - d / max(e.r, 0.1)) * DT * 2
                if d < PERCEPTION and e.id not in ped.seen:
                    ped.seen.add(e.id)
                    ped.alerts.append(e.id)
            if hurt:
                ped.hp = max(0.0, ped.hp - hurt)
                if ped.hp <= 0.25:
                    ped.state, ped.until = "down", self.t + 25.0
                    ped.route = []
                elif ped.state != "flee":
                    self._flee(ped)

    def _flee(self, ped: Ped) -> None:
        """Выбраться из опасной зоны: ближайший узел вне радиусов опасности, подальше от центра."""
        bad = [e for e in self.ents.values() if e.hazard > 0]
        best, score = None, 1e9
        for node in self.graph.adj:
            if any(math.hypot(node[0] - e.x, node[1] - e.y) < e.r + 1.5 for e in bad):
                continue
            cost = math.hypot(node[0] - ped.x, node[1] - ped.y)
            if cost < score:
                best, score = node, cost
        if best is None:
            return
        keep = dict(ped.goal)
        ped.goal = {"kind": "flee", "to": best, "resume": keep}
        ped.state = "flee"
        ped.prev = self.graph.nearest(ped.x, ped.y) if ped.prev is None else ped.prev
        self._plan_route(ped)

    # ---------- команды для движка ----------

    def dispatch(self, client_id: int, name: str, place: str, mode: str, home: str | None = None) -> dict:
        """Отправить человека в заведение. `mode`: `walk` (из дома или с края карты) или `car` (на парковку).
        Возвращает {ok, ped} или {ok: False, why}."""
        for ped in self.peds.values():
            if ped.client_id == client_id:
                return {"ok": False, "why": "уже в пути"}
        if place not in self.entries:
            return {"ok": False, "why": "нет входа"}
        ped = self._new_ped(name, home=home, client_id=client_id)
        ped.goal = {"kind": "visit", "place": place, "linger": 5.0}
        if mode == "car":
            slot = next((i for i, s in enumerate(self.slots) if s is None), None)
            if slot is None:
                self.peds.pop(ped.id)
                return {"ok": False, "why": "нет места на парковке"}
            car = self._spawn_car(2, owner=ped.id, slot=slot)
            if car is None:
                self.peds.pop(ped.id)
                return {"ok": False, "why": "полоса занята"}
            self.slots[slot] = car.id
            ped.car = car.id
            ped.state, ped.inside = "inside", f"car{car.id}"
            ped.x, ped.y = SLOT_WALK_X, SLOT_Y[slot]
            ped.prev = _key((ped.x, ped.y))
        elif mode == "walk" and home in HOMES:
            ped.x, ped.y = HOMES[home][0]
            ped.prev = _key(HOMES[home][0])
        else:
            node = self.rng.choice(EDGE_NODES)
            ped.x, ped.y = node
            ped.prev = _key(node)
        ped.goal["to"] = self._entry_node(place, ped.prev)
        if ped.goal["to"] is None:
            self.peds.pop(ped.id)
            return {"ok": False, "why": "путь к двери закрыт"}
        if ped.state != "inside":
            self._plan_route(ped)
        self.roster_version += 1
        self.note("info", "city.dispatch", ped=ped.id, client=client_id, place=place, mode=mode, home=home)
        return {"ok": True, "ped": ped.id}

    def _entry_node(self, place: str, start: tuple | None = None) -> tuple | None:
        """Вход, до которого ближе: юг или север. Без стартовой точки — южный."""
        entries = self.entries.get(place)
        if not entries:
            return None
        if start is None:
            return _key(entries[0])
        best, cost = None, 1e18
        for entry in entries:
            route = self.graph.route(start, _key(entry), self._blocked, self._hazard_cost)
            if route is None:
                continue
            length = sum(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip([start] + route, route))
            if length < cost:
                best, cost = _key(entry), length
        return best

    def release(self, client_id: int) -> bool:
        """Человек вышел из заведения и идёт дальше: домой, к машине или за край карты."""
        for ped in self.peds.values():
            if ped.client_id == client_id and ped.state == "inside" and ped.goal.get("arrived"):
                place = ped.goal.get("place")
                self.inside.get(place, {}).pop(ped.id, None)
                node = self.entries[place][ped.goal.get("side", 0)]
                ped.x, ped.y = node
                ped.prev = _key(node)
                self._depart(ped)
                return True
        return False

    def forget(self, client_id: int) -> None:
        for ped in [p for p in self.peds.values() if p.client_id == client_id]:
            self.peds.pop(ped.id, None)

    # ---------- патч мира ----------

    def apply_patch(self, ops: list, source: str = "") -> tuple[list[dict], list[str]]:
        """Применить патч из общих примитивов. Код проверяет только границы и бюджет, смысла не проверяет.
        Операции: spawn (объект), modify, remove, area (урон, настроение, толчок людям в круге), fact (факт всем в радиусе)."""
        applied: list[dict] = []
        notes: list[str] = []
        lo, hi = BOUNDS
        for raw in list(ops or [])[:12]:
            if not isinstance(raw, dict):
                continue
            op = raw.get("op")
            try:
                x, y = float(raw.get("x", 0)), float(raw.get("y", 0))
            except (TypeError, ValueError):
                notes.append(f"{op}: координаты не числа")
                continue
            if not (lo <= x <= hi and lo <= y <= hi):
                notes.append(f"{op}: ({x:.0f}, {y:.0f}) вне карты")
                continue
            r = max(0.3, min(9.0, _num(raw.get("r"), 1.5)))
            if op == "spawn":
                if len(self.ents) >= 40:
                    notes.append("spawn: на карте уже 40 объектов")
                    continue
                life = max(1.0, min(1440.0, _num(raw.get("minutes"), 180.0)))
                glyph = _glyph(raw.get("glyph"))
                ent = Ent(id=self.new_id(), kind=str(raw.get("kind") or "объект")[:24], x=x, y=y, r=r,
                          blocks=bool(raw.get("blocks")), hazard=max(0.0, min(2.0, _num(raw.get("hazard"), 0.0))),
                          until=self.t + life, glyph=glyph, label=str(raw.get("label") or "")[:30], src=source)
                self.ents[ent.id] = ent
                self.version += 1
                applied.append({"op": op, "id": ent.id, "kind": ent.kind, "x": x, "y": y, "r": r, "blocks": ent.blocks, "hazard": ent.hazard})
            elif op == "modify":
                ent = self.ents.get(int(_num(raw.get("id"), -1)))
                if ent is None:
                    notes.append("modify: нет такого объекта")
                    continue
                if "r" in raw:
                    ent.r = r
                if "blocks" in raw:
                    ent.blocks = bool(raw["blocks"])
                if "hazard" in raw:
                    ent.hazard = max(0.0, min(2.0, _num(raw.get("hazard"), ent.hazard)))
                if "minutes" in raw:
                    ent.until = self.t + max(1.0, min(1440.0, _num(raw.get("minutes"), 60.0)))
                self.version += 1
                applied.append({"op": op, "id": ent.id})
            elif op == "remove":
                ident = int(_num(raw.get("id"), -1))
                if self.ents.pop(ident, None) is None:
                    notes.append("remove: нет такого объекта")
                    continue
                self.version += 1
                applied.append({"op": op, "id": ident})
            elif op == "area":
                effect = raw.get("effect")
                amount = max(-1.0, min(1.0, _num(raw.get("amount"), 0.3)))
                hit = 0
                for ped in self.peds.values():
                    if ped.state == "inside" or math.hypot(ped.x - x, ped.y - y) > r:
                        continue
                    hit += 1
                    if effect == "damage":
                        ped.hp = max(0.0, ped.hp - abs(amount))
                        if ped.hp <= 0.25:
                            ped.state, ped.until, ped.route = "down", self.t + 25.0, []
                    elif effect == "mood":
                        ped.mood = "радость" if amount > 0.3 else "бодрость" if amount > 0 else "тревога" if amount > -0.5 else "раздражение"
                if effect == "damage":
                    for car in list(self.cars.values()):
                        lane = LANES[car.lane]
                        cx = lane_u(lane, car.s) if lane["axis"] == "x" else lane["fixed"]
                        cy = lane["fixed"] if lane["axis"] == "x" else lane_u(lane, car.s)
                        if math.hypot(cx - x, cy - y) <= r and car.state != "parked":
                            car.v = 0.0
                            car.stalled += 4.0
                applied.append({"op": op, "effect": effect, "people": hit})
            elif op == "fact":
                text = " ".join(str(raw.get("text") or "").split())[:160]
                if not text:
                    continue
                fact = {"id": self.new_id(), "text": text, "x": x, "y": y, "r": max(r, 4.0), "t": self.t}
                self.facts.append(fact)
                self.facts = self.facts[-20:]
                told = 0
                for ped in self.peds.values():
                    if math.hypot(ped.x - x, ped.y - y) <= fact["r"]:
                        ped.alerts.append(-fact["id"])
                        told += 1
                applied.append({"op": op, "text": text, "heard": told})
            elif op == "place":
                row = self.places.get(str(raw.get("id") or ""))
                if row is None:
                    notes.append("place: нет такого заведения")
                    continue
                row["status"] = "closed" if raw.get("status") == "closed" else "open"
                applied.append({"op": op, "id": row["id"], "status": row["status"]})
            else:
                notes.append(f"неизвестная операция {op}")
        return applied, notes

    # ---------- кадры и снимок ----------

    def frame(self) -> dict:
        peds = []
        for p in self.peds.values():
            if p.state == "inside":
                continue
            peds.append([p.id, round(p.x, 2), round(p.y, 2), _STATE_CODE.get(p.state, 0), p.heading])
        cars = []
        for c in self.cars.values():
            lane = LANES[c.lane]
            u = lane_u(lane, c.s)
            fixed = lane["fixed"]
            if c.slot is not None and c.off:
                fixed = fixed + (SLOT_X - fixed) * c.off
            if c.state == "parked":
                u, fixed = SLOT_Y[c.slot], SLOT_X
            x, y = (u, fixed) if lane["axis"] == "x" else (fixed, u)
            cars.append([c.id, round(x, 2), round(y, 2), c.lane, int(c.brake) + 2 * int(c.state == "parked"), round(c.wheel, 2)])
        ents = [[e.id, e.kind, round(e.x, 2), round(e.y, 2), round(e.r, 2), int(e.blocks), round(e.hazard, 2), e.glyph, e.label]
                for e in self.ents.values()]
        return {"t": round(self.minute, 3), "day": self.day, "p": peds, "c": cars, "e": ents, "v": self.version, "r": self.roster_version}

    def roster(self) -> dict:
        peds = {}
        for p in self.peds.values():
            peds[p.id] = {"n": p.name, "c": p.client_id, "m": p.mood, "g": _goal_text(p), "s": p.state, "t": p.trait,
                          "k": 0 if p.client_id is None else 1, "l": p.look, "h": round(p.hp, 2), "say": p.said}
        cars = {}
        for c in self.cars.values():
            cars[c.id] = {"k": KIND_CODE[c.kind], "col": c.color, "taxi": int(c.taxi), "lane": c.lane, "slot": c.slot, "own": c.owner}
        return {"peds": peds, "cars": cars, "inside": {k: list(v.values()) for k, v in self.inside.items()},
                "slots": [1 if s else 0 for s in self.slots], "facts": self.facts[-5:], "r": self.roster_version}

    def drain_events(self) -> list[dict]:
        out, self.events = self.events, []
        return out

    def drain_log(self) -> list[tuple]:
        out, self.log = self.log, []
        return out

    def drain_alerts(self, limit: int = 8) -> list[dict]:
        """Люди, которые заметили что-то новое: для решения через модель. Рефлексы (обойти, убежать) работают и без неё."""
        out = []
        for ped in self.peds.values():
            if not ped.alerts or ped.state in ("inside", "down"):
                continue
            seen = ped.alerts
            ped.alerts = []
            out.append({"ped": ped, "alerts": seen})
            if len(out) >= limit:
                break
        return out

    def percept(self, ped: Ped, alerts: list[int]) -> dict:
        """Что человек видит вокруг: описание для решения. Названия события тут нет, только свойства объектов и люди рядом."""
        near_ents = []
        for e in self.ents.values():
            d = math.hypot(ped.x - e.x, ped.y - e.y)
            if d <= PERCEPTION + e.r:
                near_ents.append({"id": e.id, "kind": e.kind, "dist": round(d, 1), "r": e.r, "blocks": e.blocks, "hazard": e.hazard, "label": e.label})
        crowd = []
        for q in self.peds.values():
            if q.id != ped.id and q.state != "inside" and math.hypot(ped.x - q.x, ped.y - q.y) <= 4.0:
                crowd.append({"name": q.name, "state": q.state, "mood": q.mood})
        heard = [f["text"] for f in self.facts if -f["id"] in alerts]
        return {
            "name": ped.name, "trait": ped.trait, "mood": ped.mood, "hp": round(ped.hp, 2), "goal": _goal_text(ped),
            "time": f"{int(self.minute // 60):02d}:{int(self.minute % 60):02d}", "near": near_ents[:6], "people": crowd[:6],
            "facts": heard[:3], "light": {"x": signal(self.minute, "x"), "y": signal(self.minute, "y")},
        }

    def intent(self, ped_id: int, data: dict) -> str:
        """Принять решение, которое модель дала человеку. Границы проверяет код, смысл не проверяется."""
        ped = self.peds.get(ped_id)
        if ped is None:
            return ""
        do = str(data.get("do") or "continue")
        said = " ".join(str(data.get("say") or "").split())[:70]
        if said:
            ped.said, ped.said_until = said, self.t + 4.0
        mood = data.get("mood")
        if mood in ("радость", "бодрость", "спокойствие", "усталость", "тревога", "грусть", "раздражение"):
            ped.mood = mood
        if ped.state in ("inside", "down"):
            return do
        hazards = [e for e in self.ents.values() if e.hazard > 0 or e.blocks]
        if do == "flee" and hazards:
            self._flee(ped)
        elif do == "watch" and hazards:
            ped.state, ped.route, ped.until = "linger", [], self.t + max(1.0, min(12.0, _num(data.get("minutes"), 4.0)))
        elif do == "wait":
            ped.state, ped.until = "linger", self.t + max(0.5, min(12.0, _num(data.get("minutes"), 2.0)))
        elif do == "home" and ped.home:
            self._depart(ped)
        return do


_STATE_CODE = {"walk": 0, "wait": 1, "cross": 2, "chat": 3, "linger": 4, "flee": 5, "down": 6}


def _num(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _glyph(raw) -> dict:
    """Как рисовать объект, придуманный ведущим: форма из набора, цвет, размер, подпись. Кода на каждое событие нет."""
    raw = raw if isinstance(raw, dict) else {}
    shape = raw.get("shape") if raw.get("shape") in ("circle", "ring", "square", "cloud", "star") else "circle"
    color = str(raw.get("color") or "")
    if not (len(color) == 7 and color.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in color[1:])):
        color = "#d9604c"
    return {"shape": shape, "color": color, "size": max(0.4, min(3.0, _num(raw.get("size"), 1.0))), "text": str(raw.get("text") or "")[:3]}


def _goal_text(ped: Ped) -> str:
    kind = ped.goal.get("kind")
    if ped.state == "chat":
        return "разговаривает"
    if ped.state == "down":
        return "лежит, пострадал"
    if ped.state == "flee":
        return "уходит от опасности"
    if ped.state == "wait":
        return "ждёт, чтобы перейти дорогу" if ped.route else "ждёт, путь закрыт"
    if kind == "visit":
        return f"идёт в «{ped.goal.get('place')}»"
    if kind == "car":
        return "идёт к машине"
    if kind == "home":
        return "идёт домой"
    if kind == "exit":
        return "уходит из квартала"
    if kind == "stroll":
        return "гуляет"
    return "стоит"
