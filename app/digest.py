"""Сводка для агента: одним ответом видно, всё ли в порядке и что именно не так."""

import json
import time
from datetime import datetime

import app.db as db
from app import log
from app.rules import active_hints, format_clock
from app.view import _stats, current_popularity

STARTED = time.time()


def _pct(values: list[int], share: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * share))]


def _age(row: dict) -> float | None:
    try:
        return round(datetime.now().astimezone().timestamp() - datetime.fromisoformat(row["t"]).timestamp(), 1)
    except (KeyError, ValueError):
        return None


def compact(row: dict) -> str:
    """Строка события для чтения глазами: время, уровень, событие и поля."""
    skip = {"t", "lvl", "ev"}
    parts = []
    for key, value in row.items():
        if key in skip:
            continue
        parts.append(f"{key}={value!r}" if isinstance(value, (list, dict)) else f"{key}={value}")
    stamp = str(row.get("t", ""))[11:23]
    return f"{stamp} {str(row.get('lvl', '')).upper():5} {row.get('ev', '')} " + " ".join(parts)


def _llm_stats(timeout: float) -> tuple[dict, list[str]]:
    flags: list[str] = []
    out: dict = {}
    for agent in ("client", "staff", "manager"):
        rows = db.q("SELECT latency_ms, error, attempt FROM llm_calls WHERE agent = ? ORDER BY id DESC LIMIT 60", (agent,))
        if not rows:
            continue
        times = [row["latency_ms"] for row in rows if row["latency_ms"] is not None]
        errors = [row for row in rows if row["error"]]
        out[agent] = {
            "calls": len(rows),
            "errors": len(errors),
            "retries": sum(1 for row in rows if row["attempt"] > 1),
            "ms_p50": _pct(times, 0.5),
            "ms_p95": _pct(times, 0.95),
            "ms_max": max(times) if times else None,
        }
        if out[agent]["ms_p95"] and out[agent]["ms_p95"] > timeout * 1000 * 0.8:
            flags.append(f"{agent}: p95 задержки {out[agent]['ms_p95']} мс близко к таймауту {int(timeout)} с")
        recent = rows[:20]
        if len(recent) >= 5 and sum(1 for row in recent if row["error"]) / len(recent) > 0.25:
            flags.append(f"{agent}: больше четверти ответов за последние {len(recent)} с ошибкой")
    return out, flags


def _moods() -> dict:
    """Настроения: у бариста сейчас и у гостей сегодня (при входе и на выходе)."""
    day = (db.run() or {}).get("day") or 0
    arrived: dict[str, int] = {}
    left: dict[str, int] = {}
    for row in db.q("SELECT mood, mood_after FROM visits WHERE day = ? AND status != 'open'", (day,)) if day else []:
        if row["mood"]:
            arrived[row["mood"]] = arrived.get(row["mood"], 0) + 1
        if row["mood_after"]:
            left[row["mood_after"]] = left.get(row["mood_after"], 0) + 1
    return {
        "staff": {row["id"]: row.get("mood") for row in db.staff()},
        "guests_arrived": arrived,
        "guests_left": left,
    }


def _district_line(day: int) -> dict:
    """Что сегодня решил районный голос, сколько новых людей ждёт в пачке и какой рейтинг у заведения."""
    voice = db.district_for(day) if day else None
    stats = db.review_stats()
    return {
        "traffic": voice["traffic"] if voice else None,
        "newcomers": voice["newcomers"] if voice else None,
        "curve": voice["curve"] if voice else None,
        "why": voice["why"] if voice else None,
        "buzz": voice["buzz"] if voice else None,
        "pool_left": db.pool_left(),
        "rating": stats["avg"],
        "reviews": stats["count"],
    }


def _critic_summary() -> dict:
    """Что критик видит в диалогах: средняя оценка, коды замечаний и какие напоминания уже включены ролям."""
    rows = db.q("SELECT critic_json, critic_score FROM visits WHERE critic_score IS NOT NULL ORDER BY id DESC LIMIT 30")
    codes: dict[str, int] = {}
    high = 0
    for row in rows:
        try:
            issues = json.loads(row["critic_json"] or "[]")
        except ValueError:
            continue
        for issue in issues:
            codes[issue["code"]] = codes.get(issue["code"], 0) + 1
            high += 1 if issue.get("severity") == "high" else 0
    recent = db.recent_critic(20)
    return {
        "reviewed": len(rows),
        "avg_score": round(sum(row["critic_score"] for row in rows) / len(rows), 2) if rows else None,
        "issues": codes,
        "high": high,
        "hints": {role: active_hints(recent, role) for role in ("client", "staff", "verdict") if active_hints(recent, role)},
    }


def _traffic() -> dict:
    """Поток гостей: популярность, советы знакомым, следующий приход и посещаемость по дням."""
    likes = db.recent_likes(25)
    state = db.run() or {}
    pending = db.next_arrival(state.get("day") or 0) if state.get("day") else None
    return {
        "popularity": round(current_popularity(), 2),
        "recent_verdicts": len(likes),
        "recent_liked_avg": round(sum(likes) / len(likes), 2) if likes else None,
        "referral_pool": db.referral_pool(),
        "next_arrival": format_clock(pending["minute"]) if pending else None,
        "visits_per_day": {row["day"]: row["visits"] for row in db.day_counts(10)},
    }


def digest(llm_health: dict | None = None) -> dict:
    state = db.run() or {}
    timeout = float(db.setting("llm_timeout") or 60)
    flags: list[str] = []
    events = log.read(n=400)
    problems = [row for row in log.read(n=400, level="warn")][-15:]
    clients = [row for row in events if str(row.get("ev", "")).startswith("client.")]
    last_busy = next((row for row in reversed(events) if str(row.get("ev", "")).startswith(("llm.", "visit.", "day.", "manager."))), None)

    if state.get("status") == "error":
        flags.append(f"прогон в ошибке: {state.get('message') or 'без текста'}")
    if state.get("status") == "running" and state.get("phase") and last_busy is not None:
        age = _age(last_busy)
        if age is not None and age > max(90, timeout * 1.5):
            flags.append(f"ход завис: фаза «{state.get('phase') or '—'}», {int(age)} с без событий")
    open_visits = db.q("SELECT id FROM visits WHERE status = 'open'")
    if open_visits and state.get("status") != "running":
        flags.append(f"открытые визиты при остановленном прогоне: {[row['id'] for row in open_visits]}")
    if llm_health is not None and not llm_health.get("ok"):
        flags.append(f"модель: {llm_health.get('detail')}")

    llm, llm_flags = _llm_stats(timeout)
    flags += llm_flags
    critic = _critic_summary()
    if critic["high"] >= 3:
        flags.append(f"критик нашёл серьёзные ошибки в диалогах: {critic['high']} за последние {critic['reviewed']} визитов ({critic['issues']})")

    day = state.get("day") or 0
    today = _stats(day) if day else {}
    failed = db.q("SELECT id, clock, outcome_note FROM visits WHERE day = ? AND status = 'failed'", (day,)) if day else []
    if failed:
        flags.append(f"сегодня оборвалось визитов: {len(failed)}")
    fallbacks = [row for row in events if row.get("ev") == "dialog.fallback"]
    if fallbacks:
        flags.append(f"запасные реплики кода за журнал: {len(fallbacks)}")
    recent_client = [row for row in clients if (_age(row) or 1e9) < 600]
    if recent_client:
        flags.append(f"ошибки страницы за 10 минут: {len(recent_client)}")

    return {
        "verdict": "attention" if flags else "ok",
        "flags": flags,
        "server": {
            "uptime_s": int(time.time() - STARTED),
            "log_file": str(log.path()),
            "now": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "run": {key: state.get(key) for key in (
            "status", "goal", "day", "clock", "speed", "phase", "day_done", "day_closed", "message",
        )},
        "traffic": _traffic(),
        "moods": _moods(),
        "critic": critic,
        "district": _district_line(state.get("day") or 0),
        "events": [f"{e['headline']} ({e['source']}, до дня {e['until_day']}): {e['effects']}" for e in db.active_events(state.get("day") or 0)] if state.get("day") else [],
        "llm": {"health": llm_health, "model": db.setting("llm_model"), "timeout_s": timeout, "agents": llm},
        "today": today,
        "failed_visits": failed,
        "problems": [compact(row) for row in problems],
        "client_errors": [compact(row) for row in clients[-8:]],
        "recent": [compact(row) for row in events[-20:]],
    }
