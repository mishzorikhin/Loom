import contextvars
import json
import sqlite3
import threading
from contextlib import contextmanager

from app.config import (
    CLOSE_MIN,
    OPEN_MIN,
    DAYS_PER_WEEK,
    DB_PATH,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_TIMEOUT,
)

from app.venues import DC_MENU, DC_STAFF  # noqa: E402

LOCK = threading.Lock()
CONN: sqlite3.Connection | None = None

# Заведение, с которым сейчас работает код: меню, персонал, гости, визиты, очередь и записки привязаны к нему.
# По умолчанию кофейня. Движок на время хода заведения входит в `at_place`, поэтому весь прежний код работает и для других.
_PLACE: contextvars.ContextVar[str] = contextvars.ContextVar("place", default="cafe")


def current_place() -> str:
    return _PLACE.get()


@contextmanager
def at_place(place_id: str):
    token = _PLACE.set(place_id)
    try:
        yield place_id
    finally:
        _PLACE.reset(token)

MENU = [
    ("espresso", "Эспрессо", 150, 2),
    ("cappuccino", "Капучино", 220, 4),
    ("latte", "Латте", 240, 4),
    ("filter", "Фильтр", 180, 3),
    ("cocoa", "Какао", 200, 3),
    ("bun", "Булочка", 120, 1),
]

# Заведения квартала: id, тип, название, открытие, закрытие (минуты суток), дверь на карте (клетки), заметка.
# У кофейни и ЦОДа общий каркас: свои меню, персонал, визиты, очередь и часы работы.
PLACES = [
    ("cafe", "cafe", "Кофейня на углу", OPEN_MIN, CLOSE_MIN, -0.7, 5.9, ""),
    ("neuraldeep", "datacenter", "NeuralDeep", 0, 1440, -4.7, 25.4,
     "ЦОД и LLM-шлюз через дорогу от кофейни (отсылка к hub.neuraldeep.ru): OpenAI-совместимый API, свои GPU, тарифы и кошелёк."),
]

STAFF = [
    ("anya", "Аня", 1.2),
    ("mark", "Марк", 0.8),
]


def connect(path=DB_PATH) -> sqlite3.Connection:
    global CONN
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    CONN = conn
    init()
    from app.venue_api import init_tables
    init_tables()
    return conn


def init() -> None:
    with LOCK:
        CONN.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS places (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                open_min INTEGER NOT NULL,
                close_min INTEGER NOT NULL,
                door_x REAL NOT NULL,
                door_y REAL NOT NULL,
                note TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                price INTEGER NOT NULL,
                minutes INTEGER NOT NULL,
                available INTEGER NOT NULL,
                out_until INTEGER
            );
            CREATE TABLE IF NOT EXISTS staff (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                speed REAL NOT NULL,
                on_shift INTEGER NOT NULL,
                mood TEXT
            );
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                trait TEXT NOT NULL,
                patience INTEGER NOT NULL,
                budget INTEGER NOT NULL,
                visits INTEGER NOT NULL,
                last_rating INTEGER,
                memory TEXT NOT NULL,
                preferred_item TEXT,
                created_day INTEGER NOT NULL,
                liked INTEGER,
                intent TEXT,
                come_day INTEGER,
                referrals INTEGER NOT NULL DEFAULT 0,
                source TEXT,
                mood TEXT
            );
            CREATE TABLE IF NOT EXISTS visits (
                id INTEGER PRIMARY KEY,
                day INTEGER NOT NULL,
                seq INTEGER NOT NULL,
                clock TEXT NOT NULL,
                client_id INTEGER NOT NULL,
                staff_id TEXT NOT NULL,
                status TEXT NOT NULL,
                is_return INTEGER NOT NULL,
                requested_item_id TEXT,
                requested_text TEXT,
                served_item_id TEXT,
                price INTEGER NOT NULL DEFAULT 0,
                rating INTEGER,
                asks INTEGER NOT NULL DEFAULT 0,
                memory_before TEXT,
                memory_phrase TEXT,
                outcome_note TEXT,
                start_min REAL,
                end_min REAL,
                stay_min INTEGER,
                verdict TEXT,
                liked INTEGER,
                intent TEXT,
                return_days INTEGER,
                recommend INTEGER,
                mood TEXT,
                mood_after TEXT,
                staff_mood TEXT,
                wait_min REAL,
                critic_json TEXT,
                critic_score INTEGER,
                serve_min REAL,
                next_check REAL,
                review TEXT
            );
            CREATE TABLE IF NOT EXISTS lines (
                id INTEGER PRIMARY KEY,
                visit_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                action TEXT,
                item_id TEXT
            );
            CREATE TABLE IF NOT EXISTS llm_calls (
                id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL,
                agent TEXT NOT NULL,
                visit_id INTEGER,
                week_day INTEGER,
                model TEXT NOT NULL,
                latency_ms INTEGER,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                cached_tokens INTEGER,
                system_prompt TEXT NOT NULL,
                user_prompt TEXT NOT NULL,
                raw_content TEXT,
                parsed_json TEXT,
                error TEXT,
                attempt INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS weeks (
                id INTEGER PRIMARY KEY,
                through_day INTEGER NOT NULL,
                summary_json TEXT NOT NULL,
                say TEXT,
                changes_json TEXT NOT NULL,
                notes_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS run_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                status TEXT NOT NULL,
                goal TEXT NOT NULL,
                day INTEGER NOT NULL,
                day_target INTEGER NOT NULL,
                day_done INTEGER NOT NULL,
                day_closed INTEGER NOT NULL,
                pending_manager INTEGER NOT NULL,
                speed REAL NOT NULL,
                phase TEXT NOT NULL,
                active_agent TEXT NOT NULL,
                active_visit_id INTEGER,
                message TEXT NOT NULL,
                clock TEXT NOT NULL,
                clock_min REAL NOT NULL DEFAULT 480,
                clock_real REAL NOT NULL DEFAULT 0,
                thinking INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS district (
                day INTEGER PRIMARY KEY,
                traffic REAL NOT NULL,
                newcomers REAL NOT NULL,
                curve_json TEXT NOT NULL,
                why TEXT NOT NULL,
                buzz TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pool (
                id INTEGER PRIMARY KEY,
                day INTEGER NOT NULL,
                name TEXT NOT NULL,
                trait TEXT NOT NULL,
                patience INTEGER NOT NULL,
                budget INTEGER NOT NULL,
                story TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                day INTEGER NOT NULL,
                until_day INTEGER NOT NULL,
                source TEXT NOT NULL,
                input TEXT,
                headline TEXT NOT NULL,
                story TEXT NOT NULL,
                effects_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS arrivals (
                id INTEGER PRIMARY KEY,
                day INTEGER NOT NULL,
                minute INTEGER NOT NULL,
                status TEXT NOT NULL,
                visit_id INTEGER
            );
            """
        )
        _ensure_clock_columns()
        _ensure_visit_columns()
        _ensure_place_columns()
        event_columns = {row["name"] for row in CONN.execute("PRAGMA table_info(events)")}
        for column in ("changes_json", "proposals_json"):
            if column not in event_columns:
                CONN.execute(f"ALTER TABLE events ADD COLUMN {column} TEXT NOT NULL DEFAULT '[]'")
        row = CONN.execute("SELECT value FROM settings WHERE key = 'clock_model'").fetchone()
        if row is None or row["value"] != "hour-minute":
            for table in ("lines", "visits", "clients", "llm_calls", "weeks", "arrivals", "events", "district", "pool", "items", "staff", "run_state"):
                CONN.execute(f"DELETE FROM {table}")
            _seed_unlocked()
            CONN.execute(
                """
                INSERT INTO settings(key, value) VALUES('clock_model', 'hour-minute')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            )
        elif CONN.execute("SELECT COUNT(*) AS n FROM run_state").fetchone()["n"] == 0:
            _seed_unlocked()
        CONN.commit()


def _ensure_clock_columns() -> None:
    names = {row["name"] for row in CONN.execute("PRAGMA table_info(run_state)")}
    if not names:
        return
    if "clock_min" not in names:
        CONN.execute("ALTER TABLE run_state ADD COLUMN clock_min REAL NOT NULL DEFAULT 480")
    if "clock_real" not in names:
        CONN.execute("ALTER TABLE run_state ADD COLUMN clock_real REAL NOT NULL DEFAULT 0")
    if "thinking" not in names:
        CONN.execute("ALTER TABLE run_state ADD COLUMN thinking INTEGER NOT NULL DEFAULT 0")
    CONN.execute("UPDATE run_state SET speed = 2 WHERE speed != 2")
    CONN.execute("UPDATE run_state SET goal = 'auto' WHERE goal IN ('step', 'idle')")


def _ensure_visit_columns() -> None:
    names = {row["name"] for row in CONN.execute("PRAGMA table_info(visits)")}
    if not names:
        return
    for column, kind in (
        ("start_min", "REAL"), ("end_min", "REAL"), ("stay_min", "INTEGER"), ("verdict", "TEXT"),
        ("liked", "INTEGER"), ("intent", "TEXT"), ("return_days", "INTEGER"), ("recommend", "INTEGER"),
        ("mood", "TEXT"), ("mood_after", "TEXT"), ("staff_mood", "TEXT"), ("wait_min", "REAL"),
        ("critic_json", "TEXT"), ("critic_score", "INTEGER"), ("serve_min", "REAL"), ("next_check", "REAL"),
        ("review", "TEXT"),
    ):
        if column not in names:
            CONN.execute(f"ALTER TABLE visits ADD COLUMN {column} {kind}")
    people = {row["name"] for row in CONN.execute("PRAGMA table_info(clients)")}
    for column, kind in (
        ("liked", "INTEGER"), ("intent", "TEXT"), ("come_day", "INTEGER"),
        ("referrals", "INTEGER NOT NULL DEFAULT 0"), ("source", "TEXT"), ("mood", "TEXT"),
    ):
        if people and column not in people:
            CONN.execute(f"ALTER TABLE clients ADD COLUMN {column} {kind}")
    stock = {row["name"] for row in CONN.execute("PRAGMA table_info(items)")}
    if stock and "out_until" not in stock:
        CONN.execute("ALTER TABLE items ADD COLUMN out_until INTEGER")
    crew = {row["name"] for row in CONN.execute("PRAGMA table_info(staff)")}
    if crew and "mood" not in crew:
        CONN.execute("ALTER TABLE staff ADD COLUMN mood TEXT")


def _ensure_place_columns() -> None:
    """Всё, что принадлежит заведению (меню, персонал, визиты, записки управляющего), помечено `place_id`.
    Старые строки относятся к кофейне."""
    for table in ("items", "staff", "visits", "weeks", "arrivals", "clients", "pool"):
        names = {row["name"] for row in CONN.execute(f"PRAGMA table_info({table})")}
        if names and "place_id" not in names:
            CONN.execute(f"ALTER TABLE {table} ADD COLUMN place_id TEXT NOT NULL DEFAULT 'cafe'")
    visit_cols = {row["name"] for row in CONN.execute("PRAGMA table_info(visits)")}
    if visit_cols and "side" not in visit_cols:
        CONN.execute("ALTER TABLE visits ADD COLUMN side INTEGER")
    stock = {row["name"] for row in CONN.execute("PRAGMA table_info(items)")}
    if stock:
        if "load" not in stock:
            CONN.execute("ALTER TABLE items ADD COLUMN load REAL NOT NULL DEFAULT 0")
        if "load_days" not in stock:
            CONN.execute("ALTER TABLE items ADD COLUMN load_days INTEGER NOT NULL DEFAULT 1")
    _seed_places()


def _seed_places() -> None:
    for row in PLACES:
        CONN.execute(
            "INSERT INTO places(id, type, name, open_min, close_min, door_x, door_y, note) VALUES(?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO NOTHING",
            row,
        )
    # Прайс и инженеры ЦОДа: добавляются один раз, в том числе в уже работающую базу.
    if CONN.execute("SELECT COUNT(*) AS n FROM items WHERE place_id = 'neuraldeep'").fetchone()["n"] == 0:
        CONN.executemany(
            "INSERT INTO items(id, name, price, minutes, available, place_id, load, load_days) VALUES(?, ?, ?, ?, 1, 'neuraldeep', ?, ?)",
            DC_MENU,
        )
    if CONN.execute("SELECT COUNT(*) AS n FROM staff WHERE place_id = 'neuraldeep'").fetchone()["n"] == 0:
        CONN.executemany("INSERT INTO staff(id, name, speed, on_shift, place_id) VALUES(?, ?, ?, 1, 'neuraldeep')", DC_STAFF)


def _seed_unlocked() -> None:
    defaults = {
        "llm_base_url": LLM_BASE_URL,
        "llm_model": LLM_MODEL,
        "llm_timeout": str(int(LLM_TIMEOUT)),
        "llm_api_key": LLM_API_KEY,
        "venue_name": "Кофейня на углу",
        "days_per_week": str(DAYS_PER_WEEK),
    }
    for key, value in defaults.items():
        CONN.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO NOTHING",
            (key, value),
        )
    _seed_places()
    if CONN.execute("SELECT COUNT(*) AS n FROM items WHERE place_id = 'cafe'").fetchone()["n"] == 0:
        CONN.executemany(
            "INSERT INTO items(id, name, price, minutes, available) VALUES(?, ?, ?, ?, 1)",
            MENU,
        )
    if CONN.execute("SELECT COUNT(*) AS n FROM staff WHERE place_id = 'cafe'").fetchone()["n"] == 0:
        CONN.executemany(
            "INSERT INTO staff(id, name, speed, on_shift) VALUES(?, ?, ?, 1)",
            STAFF,
        )
    CONN.execute(
        """
        INSERT INTO run_state(
            id, status, goal, day, day_target, day_done, day_closed,
            pending_manager, speed, phase, active_agent, active_visit_id, message, clock, clock_min, clock_real
        ) VALUES (1, 'idle', 'idle', 0, 0, 0, 1, 0, 2, '', '', NULL, '', '00:00', 0, 0)
        """
    )


def reset_world() -> None:
    with LOCK:
        for table in ("agent_jobs", "external_venues", "lines", "visits", "clients", "llm_calls", "weeks", "arrivals", "events", "district", "pool", "items", "staff", "run_state", "places"):
            CONN.execute(f"DELETE FROM {table}")
        _seed_unlocked()
        CONN.commit()


@contextmanager
def tx():
    with LOCK:
        try:
            yield CONN
            CONN.commit()
        except Exception:
            CONN.rollback()
            raise


def q(sql: str, args: tuple = ()) -> list[dict]:
    with LOCK:
        return [dict(row) for row in CONN.execute(sql, args).fetchall()]


def one(sql: str, args: tuple = ()) -> dict | None:
    rows = q(sql, args)
    return rows[0] if rows else None


def setting(key: str) -> str:
    row = one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else ""


def save_settings(base_url: str, model: str, timeout: int, critic_url: str = "", critic_model: str = "",
                  api_key: str | None = None) -> None:
    """Адрес, модель, таймаут, критик. Ключ меняется, только если передан непустой: пустое поле «не менять»."""
    with tx() as conn:
        pairs = {
            "llm_base_url": base_url.rstrip("/"),
            "llm_model": model.strip(),
            "llm_timeout": str(timeout),
            "critic_base_url": critic_url.strip().rstrip("/"),
            "critic_model": critic_model.strip(),
        }
        if api_key and api_key.strip():
            pairs["llm_api_key"] = api_key.strip()
        for key, value in pairs.items():
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )


def execute(sql: str, args: tuple = ()) -> None:
    with tx() as conn:
        conn.execute(sql, args)


def run() -> dict:
    return one("SELECT * FROM run_state WHERE id = 1")


def set_run(**fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{key} = ?" for key in fields)
    with tx() as conn:
        conn.execute(f"UPDATE run_state SET {cols} WHERE id = 1", tuple(fields.values()))


def items() -> list[dict]:
    """Меню. `blocked` — позиция временно недоступна из-за события дня (не путать с `available`, которым управляет управляющий)."""
    return q(
        """
        SELECT i.*, CASE WHEN i.out_until IS NOT NULL AND i.out_until >= COALESCE((SELECT day FROM run_state WHERE id = 1), 0)
                         THEN 1 ELSE 0 END AS blocked
        FROM items i WHERE i.place_id = ? ORDER BY price, name
        """,
        (current_place(),),
    )


def save_district(day: int, view: dict) -> None:
    execute(
        "INSERT OR REPLACE INTO district(day, traffic, newcomers, curve_json, why, buzz) VALUES(?, ?, ?, ?, ?, ?)",
        (day, view["traffic"], view["newcomers"], json.dumps(view["curve"]), view["why"], view["buzz"]),
    )


def last_district_traffic(before_day: int) -> float:
    """Спрос района в последний день до `before_day`; без истории 1."""
    row = one("SELECT traffic FROM district WHERE day < ? ORDER BY day DESC LIMIT 1", (before_day,))
    return row["traffic"] if row else 1.0


def district_for(day: int) -> dict | None:
    """Голос района задаёт спрос только кофейни; у остальных заведений поток по формуле."""
    if current_place() != "cafe":
        return None
    row = one("SELECT * FROM district WHERE day = ?", (day,))
    if row:
        row["curve"] = json.loads(row["curve_json"])
    return row


def reset_pool(day: int, guests: list[dict]) -> None:
    """Новая пачка профилей на день: неиспользованные вчерашние пропадают."""
    with tx() as conn:
        conn.execute("DELETE FROM pool WHERE used = 0 AND place_id = ?", (current_place(),))
        conn.executemany(
            "INSERT INTO pool(day, name, trait, patience, budget, story, place_id) VALUES(?, ?, ?, ?, ?, ?, ?)",
            [(day, g["name"], g["trait"], g["patience"], g["budget"], g["story"], current_place()) for g in guests],
        )


def take_newcomer() -> dict | None:
    row = one("SELECT * FROM pool WHERE used = 0 AND place_id = ? ORDER BY id LIMIT 1", (current_place(),))
    if row:
        execute("UPDATE pool SET used = 1 WHERE id = ?", (row["id"],))
    return row


def pool_left() -> int:
    return one("SELECT COUNT(*) AS n FROM pool WHERE used = 0 AND place_id = ?", (current_place(),))["n"]


def review_stats() -> dict:
    row = one("SELECT AVG(liked) AS avg, COUNT(liked) AS n FROM visits WHERE liked IS NOT NULL AND place_id = ?", (current_place(),))
    latest = q(
        """
        SELECT v.id, v.day, v.clock, v.liked, v.review, v.client_id, c.name AS client_name FROM visits v
        JOIN clients c ON c.id = v.client_id
        WHERE v.review IS NOT NULL AND v.review != '' AND v.place_id = ? ORDER BY v.id DESC LIMIT 30
        """,
        (current_place(),),
    )
    return {"avg": round(row["avg"], 2) if row["avg"] is not None else None, "count": row["n"] or 0, "latest": latest}


def block_item(item_id: str, until_day: int) -> None:
    execute("UPDATE items SET out_until = ? WHERE id = ?", (until_day, item_id))


def add_event(day: int, until_day: int, source: str, text: str | None, headline: str, story: str, effects: list[dict], changes: list[dict] | None = None, proposals: list[str] | None = None) -> int:
    with tx() as conn:
        cur = conn.execute(
            """
            INSERT INTO events(day, until_day, source, input, headline, story, effects_json, changes_json, proposals_json, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
            """,
            (day, until_day, source, text, headline, story, json.dumps(effects, ensure_ascii=False), json.dumps(changes or [], ensure_ascii=False), json.dumps(proposals or [], ensure_ascii=False)),
        )
        for change in changes or []:
            if change["op"] == "add_item":
                conn.execute("INSERT INTO items(id,name,price,minutes,available,place_id) VALUES(?,?,?,?,1,'cafe')",
                             (change["item_id"],change["name"],change["price"],change["minutes"]))
            elif change["op"] == "set_price":
                conn.execute("UPDATE items SET price=? WHERE id=?", (change["price_after"],change["item_id"]))
            elif change["op"] == "set_available":
                conn.execute("UPDATE items SET available=? WHERE id=?", (int(change["available_after"]),change["item_id"]))
        return cur.lastrowid


def end_event(event_id: int, day: int) -> bool:
    """Завершить событие сегодня: эффекты перестают действовать, недоступные из-за него позиции возвращаются."""
    row = one("SELECT * FROM events WHERE id = ? AND day <= ? AND until_day >= ?", (event_id, day, day))
    if row is None:
        return False
    execute("UPDATE events SET until_day = ? WHERE id = ?", (day - 1, event_id))
    still = {fx["target"] for ev in active_events(day) for fx in ev["effects"] if fx["type"] == "item_out"}
    for item in q("SELECT id FROM items WHERE out_until IS NOT NULL AND out_until >= ?", (day,)):
        if item["id"] not in still:
            execute("UPDATE items SET out_until = NULL WHERE id = ?", (item["id"],))
    return True


def active_events(day: int) -> list[dict]:
    rows = q("SELECT * FROM events WHERE day <= ? AND until_day >= ? ORDER BY id", (day, day))
    for row in rows:
        row["effects"] = json.loads(row["effects_json"])
        row["changes"] = json.loads(row["changes_json"])
        row["proposals"] = json.loads(row["proposals_json"])
    return rows


def recent_events(limit: int = 5) -> list[dict]:
    rows = q("SELECT day, source, headline, proposals_json FROM events ORDER BY id DESC LIMIT ?", (limit,))
    for row in rows:
        row["proposals"] = json.loads(row.pop("proposals_json"))
    return rows


def places() -> list[dict]:
    return q("SELECT * FROM places ORDER BY CASE id WHEN 'cafe' THEN 0 ELSE 1 END, id")


def place(place_id: str) -> dict | None:
    return one("SELECT * FROM places WHERE id = ?", (place_id,))


def staff() -> list[dict]:
    return q("SELECT * FROM staff WHERE place_id = ? ORDER BY id", (current_place(),))


def clients() -> list[dict]:
    return q("SELECT * FROM clients WHERE place_id = ? ORDER BY visits DESC, id DESC", (current_place(),))


def all_clients() -> list[dict]:
    """Люди всех заведений: для окна разговоров."""
    return q("SELECT * FROM clients ORDER BY visits DESC, id DESC")


def insert_client(name, trait, patience, budget, day, source=None) -> dict:
    with tx() as conn:
        cur = conn.execute(
            """
            INSERT INTO clients(name, trait, patience, budget, visits, last_rating, memory, preferred_item, created_day, source, place_id)
            VALUES(?, ?, ?, ?, 0, NULL, '', NULL, ?, ?, ?)
            """,
            (name, trait, patience, budget, day, source, current_place()),
        )
        client_id = cur.lastrowid
    return one("SELECT * FROM clients WHERE id = ?", (client_id,))


def insert_visit(**fields) -> int:
    fields.setdefault("place_id", current_place())
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    with tx() as conn:
        cur = conn.execute(
            f"INSERT INTO visits({cols}) VALUES({marks})",
            tuple(fields.values()),
        )
        return cur.lastrowid


def update_visit(visit_id: int, **fields) -> None:
    cols = ", ".join(f"{key} = ?" for key in fields)
    with tx() as conn:
        conn.execute(f"UPDATE visits SET {cols} WHERE id = ?", (*fields.values(), visit_id))


def add_line(visit_id: int, role: str, text: str, action: str | None, item_id: str | None) -> None:
    with tx() as conn:
        conn.execute(
            "INSERT INTO lines(visit_id, role, text, action, item_id) VALUES(?, ?, ?, ?, ?)",
            (visit_id, role, text, action, item_id),
        )


def visit_lines(visit_id: int) -> list[dict]:
    return q("SELECT * FROM lines WHERE visit_id = ? ORDER BY id", (visit_id,))


def visit(visit_id: int) -> dict | None:
    row = one(
        """
        SELECT v.*, c.name AS client_name, c.memory AS client_memory, s.name AS staff_name
        FROM visits v
        JOIN clients c ON c.id = v.client_id
        JOIN staff s ON s.id = v.staff_id
        WHERE v.id = ?
        """,
        (visit_id,),
    )
    if row:
        row["lines"] = visit_lines(visit_id)
    return row


def finish_client(client_id: int, rating: int | None, memory: str, preferred: str | None) -> None:
    with tx() as conn:
        conn.execute(
            """
            UPDATE clients
            SET visits = visits + 1,
                last_rating = ?,
                memory = ?,
                preferred_item = COALESCE(?, preferred_item)
            WHERE id = ?
            """,
            (rating, memory, preferred, client_id),
        )


def add_llm(**fields) -> int:
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    with tx() as conn:
        cur = conn.execute(f"INSERT INTO llm_calls({cols}) VALUES({marks})", tuple(fields.values()))
        return cur.lastrowid


def llm_call(call_id: int) -> dict | None:
    return one("SELECT * FROM llm_calls WHERE id = ?", (call_id,))


def recent_llm(limit: int = 40) -> list[dict]:
    return q("SELECT * FROM llm_calls ORDER BY id DESC LIMIT ?", (limit,))


def add_week(**fields) -> None:
    fields.setdefault("place_id", current_place())
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    with tx() as conn:
        conn.execute(f"INSERT INTO weeks({cols}) VALUES({marks})", tuple(fields.values()))


def weeks() -> list[dict]:
    return q("SELECT * FROM weeks WHERE place_id = ? ORDER BY id DESC", (current_place(),))


def add_arrivals(day: int, minutes: list[int]) -> None:
    with tx() as conn:
        conn.executemany(
            "INSERT INTO arrivals(day, minute, status, visit_id, place_id) VALUES(?, ?, 'scheduled', NULL, ?)",
            [(day, minute, current_place()) for minute in minutes],
        )


def due_arrival(day: int, minute: float) -> dict | None:
    return one(
        """
        SELECT * FROM arrivals
        WHERE day = ? AND status = 'scheduled' AND minute <= ? AND place_id = ?
        ORDER BY minute, id LIMIT 1
        """,
        (day, int(minute), current_place()),
    )


def next_arrival(day: int) -> dict | None:
    return one(
        "SELECT * FROM arrivals WHERE day = ? AND status = 'scheduled' AND place_id = ? ORDER BY minute, id LIMIT 1",
        (day, current_place()),
    )


def save_verdict(visit_id: int, client_id: int, verdict: dict, come_day: int) -> None:
    """Вердикт гостя: на визит, на карточку гостя и в разговор отдельной строкой."""
    with tx() as conn:
        conn.execute(
            "UPDATE visits SET verdict = ?, liked = ?, intent = ?, return_days = ?, recommend = ?, mood_after = ?, review = ? WHERE id = ?",
            (verdict["say"], verdict["liked"], verdict["return"], verdict["return_in_days"], int(verdict["recommend"]),
             verdict.get("mood"), verdict.get("review") or None, visit_id),
        )
        conn.execute(
            "UPDATE clients SET liked = ?, intent = ?, come_day = ?, referrals = referrals + ?, mood = COALESCE(?, mood) WHERE id = ?",
            (verdict["liked"], verdict["return"], come_day, 1 if verdict["recommend"] else 0, verdict.get("mood"), client_id),
        )
        if verdict["say"]:
            conn.execute(
                "INSERT INTO lines(visit_id, role, text, action, item_id) VALUES(?, 'client', ?, 'verdict', NULL)",
                (visit_id, verdict["say"]),
            )


def set_staff_mood(staff_id: str, mood: str) -> None:
    execute("UPDATE staff SET mood = ? WHERE id = ?", (mood, staff_id))


def save_critic(visit_id: int, score: int, issues: list[dict]) -> None:
    execute(
        "UPDATE visits SET critic_json = ?, critic_score = ? WHERE id = ?",
        (json.dumps(issues, ensure_ascii=False), score, visit_id),
    )


def recent_critic(limit: int) -> list[list[dict]]:
    out = []
    for row in q("SELECT critic_json FROM visits WHERE critic_json IS NOT NULL AND place_id = ? ORDER BY id DESC LIMIT ?", (current_place(), limit)):
        try:
            out.append(json.loads(row["critic_json"]))
        except (TypeError, ValueError):
            continue
    return out


def recent_likes(limit: int) -> list[int]:
    return [row["liked"] for row in q("SELECT liked FROM visits WHERE liked IS NOT NULL AND place_id = ? ORDER BY id DESC LIMIT ?", (current_place(), limit))]


def referral_pool() -> int:
    return one("SELECT COALESCE(SUM(referrals), 0) AS n FROM clients WHERE place_id = ?", (current_place(),))["n"]


def take_referral() -> str | None:
    """Один совет знакомому расходуется: вернуть имя того, кто посоветовал."""
    row = one("SELECT id, name FROM clients WHERE referrals > 0 AND place_id = ? ORDER BY referrals DESC, id DESC LIMIT 1", (current_place(),))
    if row is None:
        return None
    execute("UPDATE clients SET referrals = referrals - 1 WHERE id = ?", (row["id"],))
    return row["name"]


def waiting(day: int) -> list[dict]:
    """Очередь: гости, которые пришли и ещё не дошли до прилавка, в порядке прихода."""
    return q("SELECT * FROM visits WHERE day = ? AND status = 'waiting' AND place_id = ? ORDER BY start_min, id", (day, current_place()))


def visited_today(day: int) -> set[int]:
    return {row["client_id"] for row in q("SELECT client_id FROM visits WHERE day = ? AND place_id = ?", (day, current_place()))}


def day_counts(limit: int = 14) -> list[dict]:
    rows = q(
        """
        SELECT day, COUNT(*) AS visits, COALESCE(SUM(price), 0) AS revenue FROM visits
        WHERE status NOT IN ('open', 'waiting') AND place_id = ? GROUP BY day ORDER BY day DESC LIMIT ?
        """,
        (current_place(), limit),
    )
    return list(reversed(rows))


def scheduled_left(day: int) -> int:
    return one("SELECT COUNT(*) AS n FROM arrivals WHERE day = ? AND status = 'scheduled' AND place_id = ?", (day, current_place()))["n"]


def set_arrival(arrival_id: int, **fields) -> None:
    cols = ", ".join(f"{key} = ?" for key in fields)
    with tx() as conn:
        conn.execute(f"UPDATE arrivals SET {cols} WHERE id = ?", (*fields.values(), arrival_id))


def client_visits(client_id: int) -> list[dict]:
    return q(
        """
        SELECT v.id, v.day, v.clock, v.status, v.price, v.rating, v.memory_phrase, v.is_return,
               s.name AS staff_name, i.name AS item_name, v.requested_text
        FROM visits v
        JOIN staff s ON s.id = v.staff_id
        LEFT JOIN items i ON i.id = COALESCE(v.served_item_id, v.requested_item_id)
        WHERE v.client_id = ?
        ORDER BY v.id
        """,
        (client_id,),
    )


def insert_item(item_id: str, name: str, price: int, minutes: int) -> None:
    is_dc = place(current_place())["type"] == "datacenter"
    with tx() as conn:
        conn.execute(
            "INSERT INTO items(id, name, price, minutes, available, place_id, load, load_days) VALUES(?, ?, ?, ?, 1, ?, ?, ?)",
            (item_id, name, price, minutes, current_place(), 0.1 if is_dc else 0, 5 if is_dc else 1),
        )


def load_rows(day: int, span: int = 31) -> list[dict]:
    """Оформленные услуги заведения за последний месяц с их нагрузкой на GPU (для ЦОДа)."""
    return q(
        """
        SELECT v.day, i.load AS load, i.load_days AS days FROM visits v
        JOIN items i ON i.id = v.served_item_id
        WHERE v.place_id = ? AND v.status = 'served' AND v.day > ?
        """,
        (current_place(), day - span),
    )


def save_item(item_id: str, price: int, available: int) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE items SET price = ?, available = ? WHERE id = ?",
            (price, available, item_id),
        )
