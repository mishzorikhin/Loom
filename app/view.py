import json
import time
from datetime import datetime

import app.db as db
from app.config import CLOSE_MIN, LIKES_WINDOW, OPEN_MIN
from app.rules import advance_minutes, effect_label, format_clock, popularity


def _stats(day: int | None) -> dict:
    where = ""
    args: tuple = ()
    if day is not None:
        where = "WHERE day = ?"
        args = (day,)
    row = db.one(
        f"""
        SELECT
            COUNT(*) AS visits,
            SUM(CASE WHEN status = 'served' THEN 1 ELSE 0 END) AS served,
            SUM(CASE WHEN status = 'refused' THEN 1 ELSE 0 END) AS refused,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
            SUM(CASE WHEN status = 'left' THEN 1 ELSE 0 END) AS left_queue,
            SUM(CASE WHEN is_return = 1 THEN 1 ELSE 0 END) AS returned,
            COUNT(DISTINCT client_id) AS unique_clients,
            COALESCE(SUM(price), 0) AS revenue,
            AVG(rating) AS avg_rating
        FROM visits
        {where}
        """,
        args,
    )
    served = row["served"] or 0
    revenue = row["revenue"] or 0
    return {
        "visits": row["visits"] or 0,
        "served": served,
        "refused": row["refused"] or 0,
        "failed": row["failed"] or 0,
        "left": row["left_queue"] or 0,
        "returned": row["returned"] or 0,
        "unique_clients": row["unique_clients"] or 0,
        "revenue": revenue,
        "avg_check": int(revenue / served) if served else 0,
        "avg_rating": round(row["avg_rating"], 2) if row["avg_rating"] is not None else None,
    }


def event_effects(kind: str) -> list[dict]:
    """Эффекты заданного вида из событий, которые действуют сегодня."""
    day = (db.run() or {}).get("day") or 0
    return [fx for event in (db.active_events(day) if day else []) for fx in event["effects"] if fx["type"] == kind]


def popularity_hint() -> float:
    """Популярность по формуле из вердиктов: опора для районного голоса и запасной вариант, если он промолчал."""
    return popularity(db.recent_likes(LIKES_WINDOW), db.referral_pool())


def current_popularity() -> float:
    """Множитель потока гостей: ответ районного голоса на сегодня (иначе формула из вердиктов) и спрос от событий дня."""
    day = (db.run() or {}).get("day") or 0
    voice = db.district_for(day) if day else None
    base = voice["traffic"] if voice else popularity_hint()
    shock = 1.0
    for fx in event_effects("demand"):
        shock *= fx["amount"]
    return max(0.3, min(2.6, base * max(0.5, min(1.8, shock))))


def _item_stats() -> list[dict]:
    stats = []
    for item in db.items():
        requested = db.one(
            "SELECT COUNT(*) AS n FROM visits WHERE requested_item_id = ?",
            (item["id"],),
        )["n"]
        sold = db.one(
            "SELECT COUNT(*) AS n FROM visits WHERE status = 'served' AND served_item_id = ?",
            (item["id"],),
        )["n"]
        refused = db.one(
            "SELECT COUNT(*) AS n FROM visits WHERE status = 'refused' AND requested_item_id = ?",
            (item["id"],),
        )["n"]
        stats.append({
            **item, "enabled": bool(item["available"]), "available": bool(item["available"]) and not item["blocked"],
            "requested": requested, "sold": sold, "refused": refused,
        })
    return stats


def _guest_mood(start: int, through_day: int) -> dict:
    row = db.one(
        """
        SELECT AVG(liked) AS liked,
               SUM(CASE WHEN intent = 'yes' THEN 1 ELSE 0 END) AS yes,
               SUM(CASE WHEN intent = 'maybe' THEN 1 ELSE 0 END) AS maybe,
               SUM(CASE WHEN intent = 'no' THEN 1 ELSE 0 END) AS no,
               SUM(COALESCE(recommend, 0)) AS recommend,
               SUM(CASE WHEN is_return = 1 THEN 1 ELSE 0 END) AS repeat_visits
        FROM visits WHERE day BETWEEN ? AND ? AND liked IS NOT NULL
        """,
        (start, through_day),
    )
    fresh = db.one("SELECT COUNT(*) AS n FROM clients WHERE created_day BETWEEN ? AND ?", (start, through_day))["n"]
    return {
        "avg_liked": round(row["liked"], 2) if row["liked"] is not None else None,
        "will_return": row["yes"] or 0,
        "maybe_return": row["maybe"] or 0,
        "wont_return": row["no"] or 0,
        "recommend": row["recommend"] or 0,
        "returning_visits": row["repeat_visits"] or 0,
        "new_guests": fresh,
    }


def week_summary(through_day: int) -> dict:
    start = through_day - 4
    rows = db.q(
        """
        SELECT
            COUNT(*) AS visits,
            SUM(CASE WHEN status = 'served' THEN 1 ELSE 0 END) AS served,
            SUM(CASE WHEN status = 'refused' THEN 1 ELSE 0 END) AS refused,
            SUM(CASE WHEN status = 'left' THEN 1 ELSE 0 END) AS left_queue,
            COALESCE(SUM(price), 0) AS revenue,
            AVG(rating) AS avg_rating
        FROM visits
        WHERE day BETWEEN ? AND ? AND status NOT IN ('open', 'waiting')
        """,
        (start, through_day),
    )[0]
    items = []
    for item in db.items():
        requested = db.one(
            "SELECT COUNT(*) AS n FROM visits WHERE day BETWEEN ? AND ? AND requested_item_id = ?",
            (start, through_day, item["id"]),
        )["n"]
        sold = db.one(
            """
            SELECT COUNT(*) AS n FROM visits
            WHERE day BETWEEN ? AND ? AND status = 'served' AND served_item_id = ?
            """,
            (start, through_day, item["id"]),
        )["n"]
        refused = db.one(
            """
            SELECT COUNT(*) AS n FROM visits
            WHERE day BETWEEN ? AND ? AND status = 'refused' AND requested_item_id = ?
            """,
            (start, through_day, item["id"]),
        )["n"]
        items.append(
            {
                "id": item["id"],
                "name": item["name"],
                "price": item["price"],
                "minutes": item["minutes"],
                "available": bool(item["available"]),
                "requested": requested,
                "sold": sold,
                "refused": refused,
            }
        )
    wishes = []
    for row in db.q(
        """
        SELECT requested_text FROM visits
        WHERE day BETWEEN ? AND ? AND status = 'refused' AND TRIM(COALESCE(requested_text, '')) != ''
        ORDER BY id DESC LIMIT 8
        """,
        (start, through_day),
    ):
        text = " ".join(str(row["requested_text"]).split())[:60]
        if text and text not in wishes:
            wishes.append(text)
    return {
        "days": list(range(start, through_day + 1)),
        "visits": rows["visits"] or 0,
        "served": rows["served"] or 0,
        "refused": rows["refused"] or 0,
        "left_queue": rows["left_queue"] or 0,
        "revenue": rows["revenue"] or 0,
        "avg_rating": round(rows["avg_rating"], 2) if rows["avg_rating"] is not None else None,
        "items": items,
        "menu_size": len(items),
        "wishes": wishes,
        "guests": _guest_mood(start, through_day),
        "visits_per_day": [row["visits"] for row in db.day_counts(10)][-5:],
    }


def _district_view(day: int) -> dict | None:
    row = db.district_for(day) if day else None
    if row is None:
        return None
    return {"traffic": row["traffic"], "newcomers": row["newcomers"], "why": row["why"], "buzz": row["buzz"], "curve": row["curve"]}


def _events_view(day: int) -> list[dict]:
    """События, которые действуют сегодня, с подписями эффектов для страницы."""
    if not day:
        return []
    items = {item["id"]: item for item in db.items()}
    names = {row["id"]: row["name"] for row in db.staff()}
    return [
        {
            "id": event["id"], "day": event["day"], "until_day": event["until_day"], "source": event["source"],
            "headline": event["headline"], "story": event["story"], "input": event["input"],
            "effects": [effect_label(fx, items, names) for fx in event["effects"]],
        }
        for event in db.active_events(day)
    ]


def snapshot() -> dict:
    state = dict(db.run())
    live = advance_minutes(
        state.get("clock_min") or OPEN_MIN,
        state.get("clock_real") or time.time(),
        time.time(),
        state.get("speed") or 1,
        state["status"] == "running",
        bool(state.get("thinking")),
    )
    state["clock_min"] = live
    state["clock"] = format_clock(live)
    state["open_min"] = OPEN_MIN
    state["close_min"] = CLOSE_MIN
    people = []
    for client in db.clients():
        people.append(
            {
                **client,
                "history": db.client_visits(client["id"]),
            }
        )
    roster = []
    for person in db.staff():
        served = db.one(
            """
            SELECT COUNT(*) AS n FROM visits
            WHERE staff_id = ? AND status = 'served' AND day = ?
            """,
            (person["id"], state["day"] or -1),
        )["n"]
        roster.append({**person, "served_today": served, "role": "бариста"})
    current = None
    if state["active_visit_id"]:
        current = db.visit(state["active_visit_id"])
    day_visits = []
    if state["day"]:
        day_visits = db.q(
            """
            SELECT v.id, v.day, v.seq, v.clock, v.status, v.price, v.is_return, v.rating,
                   v.client_id, v.staff_id, v.start_min, v.end_min, v.stay_min, v.serve_min, v.mood, v.mood_after, v.staff_mood,
                   v.requested_text, c.name AS client_name, i.name AS item_name
            FROM visits v
            JOIN clients c ON c.id = v.client_id
            LEFT JOIN items i ON i.id = COALESCE(v.served_item_id, v.requested_item_id)
            WHERE v.day = ?
            ORDER BY v.seq
            """,
            (state["day"],),
        )
    journal = db.q(
        """
        SELECT v.id, v.day, v.clock, v.status, v.price, v.rating, v.is_return, v.memory_phrase,
               v.requested_text, c.name AS client_name, s.name AS staff_name, i.name AS item_name
        FROM visits v
        JOIN clients c ON c.id = v.client_id
        JOIN staff s ON s.id = v.staff_id
        LEFT JOIN items i ON i.id = COALESCE(v.served_item_id, v.requested_item_id)
        ORDER BY v.id DESC
        LIMIT 80
        """
    )
    calls = []
    for call in db.recent_llm(40):
        calls.append(
            {
                "id": call["id"],
                "created_at": call["created_at"],
                "agent": call["agent"],
                "visit_id": call["visit_id"],
                "week_day": call["week_day"],
                "model": call["model"],
                "latency_ms": call["latency_ms"],
                "prompt_tokens": call["prompt_tokens"],
                "completion_tokens": call["completion_tokens"],
                "cached_tokens": call["cached_tokens"],
                "error": call["error"],
                "attempt": call["attempt"],
                "parsed": bool(call["parsed_json"]),
            }
        )
    weeks = []
    for week in db.weeks():
        weeks.append(
            {
                "id": week["id"],
                "through_day": week["through_day"],
                "say": week["say"],
                "summary": json.loads(week["summary_json"]),
                "changes": json.loads(week["changes_json"]),
                "notes": json.loads(week["notes_json"]),
                "created_at": week["created_at"],
            }
        )
    repeat_people = db.one("SELECT COUNT(*) AS n FROM clients WHERE visits >= 2")["n"]
    return {
        "run": state,
        "venue": {
            "name": db.setting("venue_name"),
            "days_per_week": int(db.setting("days_per_week")),
            "repeat_people": repeat_people,
        },
        "llm": {
            "base_url": db.setting("llm_base_url"),
            "model": db.setting("llm_model"),
            "timeout": int(float(db.setting("llm_timeout") or 60)),
            "has_key": bool(db.setting("llm_api_key")),
            "critic_base_url": db.setting("critic_base_url"),
            "critic_model": db.setting("critic_model"),
        },
        "staff": roster,
        "days": db.day_counts(14),
        "events": _events_view(state["day"]),
        "district": _district_view(state["day"]),
        "reviews": db.review_stats(),
        "menu": _item_stats(),
        "clients": people,
        "current_visit": current,
        "day_visits": day_visits,
        "summary": {"today": _stats(state["day"] or None) if state["day"] else _stats(-1), "all": _stats(None)},
        "journal": journal,
        "llm_calls": calls,
        "weeks": weeks,
        "server_time": datetime.now().isoformat(timespec="seconds"),
    }
