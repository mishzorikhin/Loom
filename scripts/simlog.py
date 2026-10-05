#!/usr/bin/env python3
"""Читалка журнала Loom для агента. Только стандартная библиотека.

  simlog.py digest                    сводка: всё ли в порядке и что не так (начинать с неё)
  simlog.py tail [-n 50] [--level warn] [--ev visit,llm] [--since 10m] [--visit 65] [-q текст] [--json]
  simlog.py errors [--since 1h]       то же, что tail --level warn
  simlog.py visit 65                  события визита и сам разговор
  simlog.py call 183                  вызов модели целиком (промпты, сырой ответ)
  simlog.py follow [--level info]     смотреть новые события, Ctrl+C — выход

Адрес: LOOM_URL (http://192.168.0.16:8421). Входа на странице нет, скрипт ходит обычными запросами.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

URL = (os.environ.get("LOOM_URL") or os.environ.get("SIMCHECK_URL") or "http://192.168.0.16:8421").rstrip("/")
OPENER = urllib.request.build_opener()


def get(path: str, **params) -> dict:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    url = f"{URL}{path}" + (f"?{query}" if query else "")
    try:
        return json.loads(OPENER.open(url, timeout=30).read())
    except urllib.error.HTTPError as exc:
        sys.exit(f"{url}: HTTP {exc.code} {exc.read()[:200].decode('utf-8', 'replace')}")
    except urllib.error.URLError as exc:
        sys.exit(f"{url}: нет связи ({exc.reason})")


def line(row: dict) -> str:
    skip = {"t", "lvl", "ev"}
    parts = []
    for key, value in row.items():
        if key in skip:
            continue
        parts.append(f"{key}={json.dumps(value, ensure_ascii=False)}" if isinstance(value, (list, dict)) else f"{key}={value}")
    return f"{str(row.get('t', ''))[11:23]} {str(row.get('lvl', '')).upper():5} {row.get('ev', ''):<14} " + " ".join(parts)


def show(rows: list[dict], raw: bool) -> None:
    for row in rows:
        print(json.dumps(row, ensure_ascii=False) if raw else line(row))


def cmd_digest(args) -> None:
    data = get("/api/digest")
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    run = data["run"]
    print(f"ВЕРДИКТ: {data['verdict']}")
    for flag in data["flags"]:
        print(f"  ! {flag}")
    print(f"прогон: {run['status']} день {run['day']} {run['clock']} темп x{run['speed']} цель {run['goal']} "
          f"визитов {run['day_done']} фаза «{run['phase'] or '—'}»"
          + (f" сообщение: {run['message']}" if run["message"] else ""))
    traffic = data["traffic"]
    print(f"поток: популярность {traffic['popularity']} (вердиктов {traffic['recent_verdicts']}, средняя оценка {traffic['recent_liked_avg']}), "
          f"советов знакомым {traffic['referral_pool']}, следующий приход {traffic['next_arrival'] or '—'}, "
          f"гостей по дням {traffic['visits_per_day']}")
    moods = data.get("moods")
    if moods:
        print(f"настроения: бариста {moods['staff']}, гости пришли {moods['guests_arrived']}, ушли {moods['guests_left']}")
    critic = data.get("critic")
    if critic and critic["reviewed"]:
        print(f"критик: просмотрено {critic['reviewed']}, средняя {critic['avg_score']}, замечания {critic['issues']}, серьёзных {critic['high']}"
              + (f", напоминания ролям: {critic['hints']}" if critic["hints"] else ""))
    voice = data.get("district")
    if voice:
        print(f"район: спрос ×{voice['traffic']}, новых {voice['newcomers']}, кривая {voice['curve']}, в пачке демографа {voice['pool_left']}, "
              f"рейтинг {voice['rating']} по {voice['reviews']} отзывам; «{voice['buzz']}» {voice['why'] or ''}")
    if data.get("events"):
        print("события дня: " + "; ".join(data["events"]))
    health = data["llm"]["health"] or {}
    print(f"модель: {data['llm']['model']} {'на связи' if health.get('ok') else 'НЕДОСТУПНА'} ({health.get('detail')}), таймаут {data['llm']['timeout_s']} с")
    for agent, stat in data["llm"]["agents"].items():
        print(f"  {agent}: вызовов {stat['calls']}, ошибок {stat['errors']}, повторов {stat['retries']}, "
              f"мс p50/p95/max {stat['ms_p50']}/{stat['ms_p95']}/{stat['ms_max']}")
    today = data["today"]
    if today:
        print(f"сегодня: визитов {today['visits']}, обслужено {today['served']}, отказов {today['refused']}, "
              f"обрывов {today['failed']}, выручка {today['revenue']} ₽, оценка {today['avg_rating']}")
    for row in data["failed_visits"]:
        print(f"  оборван визит {row['id']} {row['clock']}: {row['outcome_note']}")
    for title, key in (("проблемы (warn и error)", "problems"), ("ошибки страницы", "client_errors"), ("последние события", "recent")):
        if data[key]:
            print(f"{title}:")
            for text in data[key]:
                print(f"  {text}")
    print(f"сервер: аптайм {data['server']['uptime_s']} с, журнал {data['server']['log_file']}")


def cmd_tail(args) -> None:
    level = "warn" if args.cmd == "errors" else args.level
    data = get("/api/log", n=args.n, level=level, ev=args.ev, since=args.since, visit=args.visit, q=args.q)
    show(data["lines"], args.json)
    if not data["lines"]:
        print("(пусто)", file=sys.stderr)


def cmd_visit(args) -> None:
    data = get("/api/log", n=200, visit=args.id)
    show(data["lines"], args.json)
    visit = get(f"/api/visits/{args.id}")
    print(f"--- визит {visit['id']}: день {visit['day']} {visit['clock']}, {visit['client_name']} ↔ {visit['staff_name']}, "
          f"статус {visit['status']}, чек {visit['price']} ₽, оценка {visit['rating']}"
          + (f", заметка: {visit['outcome_note']}" if visit["outcome_note"] else ""))
    for row in visit["lines"]:
        who = visit["client_name"] if row["role"] == "client" else visit["staff_name"]
        print(f"  {who} [{row['action'] or ''}{' ' + row['item_id'] if row['item_id'] else ''}]: {row['text']}")


def cmd_call(args) -> None:
    call = get(f"/api/llm/{args.id}")
    if args.json:
        print(json.dumps(call, ensure_ascii=False, indent=2))
        return
    print(f"вызов {call['id']} {call['created_at']} {call['agent']} визит {call['visit_id']} попытка {call['attempt']} "
          f"{call['latency_ms']} мс токены {call['prompt_tokens']}/{call['completion_tokens']} ошибка: {call['error'] or '—'}")
    for title, key in (("СИСТЕМА", "system_prompt"), ("ХОД", "user_prompt"), ("СЫРОЙ ОТВЕТ", "raw_content"), ("РАЗБОР", "parsed_json")):
        print(f"--- {title}\n{call[key]}")


def cmd_follow(args) -> None:
    last = ""
    print(f"слежу за {URL}, Ctrl+C — выход", file=sys.stderr)
    while True:
        rows = get("/api/log", n=100, level=args.level, ev=args.ev, since="30s" if not last else None)["lines"]
        fresh = [row for row in rows if row["t"] > last]
        show(fresh, args.json)
        if fresh:
            last = fresh[-1]["t"]
        time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="сырой JSON вместо строк")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("digest")
    for name in ("tail", "errors", "follow"):
        p = sub.add_parser(name)
        p.add_argument("-n", type=int, default=50)
        p.add_argument("--level", default="info" if name != "errors" else "warn")
        p.add_argument("--ev")
        p.add_argument("--since")
        p.add_argument("--visit", type=int)
        p.add_argument("-q")
    for name in ("visit", "call"):
        sub.add_parser(name).add_argument("id", type=int)
    args = parser.parse_args()
    {"digest": cmd_digest, "tail": cmd_tail, "errors": cmd_tail, "visit": cmd_visit, "call": cmd_call, "follow": cmd_follow}[args.cmd](args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
