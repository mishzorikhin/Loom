import asyncio
import contextlib
import json
import os
import random
import re
import time
from datetime import datetime

import app.db as db
from app import log
from app.config import DAY_END, DAY_START, REFERRAL_CHANCE
from app.llm import LLM, SchemaError, TransportError, load_system
from app.rules import (
    DEFAULT_MOOD, ECHO_LIMIT, MOODS, active_hints, clean_critic, advance_minutes, after_visit_mood, apply_changes, arrival_gap, arrival_mood,
    choose_arrival, clean_verdict, come_day_for, echo_ratio, effective_patience, fallback_choice, fallback_close,
    fallback_verdict, format_clock, mood_value, pick_mood, rating_for, shift_mood, stay_minutes, wait_shift,
    QUEUE_CHECK_EVERY, TRAITS, calendar, clean_district, clean_event, clean_newcomers, effect_label,
    GPU_BUSY, GPU_FULL, GPU_SLOW, gpu_status, gpu_utilization,
)
from app.view import _stats as day_stats
from app.view import current_popularity, event_effects, popularity_hint, week_summary
from app.venues import DC_CAPACITY, Venue, venue_of
from app.city import HOMES

HOME_IDS = sorted(HOMES)
CITY_FOLK = 14  # постоянные жители города без записи гостя

def venue_now() -> Venue:
    """Тип заведения, с которым сейчас работает код (см. `db.at_place`)."""
    row = db.place(db.current_place())
    return venue_of(row["type"] if row else None)


def venue_ids() -> list[str]:
    """Заведения с визитами и разговорами: те, для которых есть тип в `venues`."""
    from app.venues import VENUES
    return [row["id"] for row in db.places() if row["type"] in VENUES]


_OLD_TRACE = re.compile(r"^(?P<label>.*), (?P<outcome>обслужен|отказ), оценка (?P<rating>\d+)$")


def usable(item: dict) -> bool:
    """Позиция доступна гостям: включена управляющим и не выбыла из-за события дня."""
    return bool(item["available"]) and not item.get("blocked")


def menu_block() -> str:
    lines = []
    for item in db.items():
        state = "есть" if usable(item) else "нет"
        lines.append(f"- {item['name']}: {item['price']} ₽, {item['minutes']} мин, {state}")
    return "\n".join(lines)


def catalog() -> dict:
    return {item["id"]: item for item in db.items()}


def clean_item_id(item_id: str | None, items: dict | None = None) -> str:
    """Позиция из ответа модели. Модель видит в меню только названия и пишет в поле название; код находит позицию
    по названию (точно или по вхождению) и отдаёт её id. Свой id тоже принимается. Всё остальное, в том числе
    обрывок JSON, — пустая строка."""
    found = items if items is not None else catalog()
    token = " ".join(str(item_id or "").split())
    if token in found:
        return token
    wanted = token.casefold().strip(" «»\".")
    if len(wanted) < 3:
        return ""
    for item in found.values():
        if str(item["name"]).casefold() == wanted:
            return item["id"]
    for item in found.values():
        name = str(item["name"]).casefold()
        if name in wanted or (len(wanted) >= 4 and wanted in name):
            return item["id"]
    return ""


def plain_memory(text: str) -> str:
    """Старый след хранил цитату реплики. В ход идёт только факт."""
    raw = (text or "").strip()
    if "«" in raw:
        raw = raw[: raw.index("«")].strip().rstrip(".")
    match = _OLD_TRACE.match(raw)
    if not match:
        return raw
    label = match.group("label").strip()
    rating = match.group("rating")
    if match.group("outcome") == "обслужен":
        return f"В прошлый раз брал {label}, обслужили, оценка {rating}."
    return f"В прошлый раз {label}: отказ, оценка {rating}."


def visit_trace(label: str, status: str, rating: int) -> str:
    """Факт для следующего визита, без цитаты реплики."""
    name = (label or "без позиции").strip()
    if len(name) > 80:
        name = name[:80].rstrip()
    if status == "served":
        return f"В прошлый раз брал {name}, обслужили, оценка {rating}."
    if status == "left":
        return f"В прошлый раз не дождался очереди и ушёл, оценка {rating}."
    return f"В прошлый раз {name}: отказ, оценка {rating}."


def _closed(reply: dict) -> dict:
    reply = dict(reply)
    reply["say"] = str(reply.get("say") or "").strip()
    reply["item_id"] = clean_item_id(reply.get("item_id"))
    return reply


def _heard(guest: dict) -> dict:
    guest = dict(guest)
    guest["say"] = str(guest.get("say") or "").strip()
    guest["item_id"] = clean_item_id(guest.get("item_id"))
    guest["request"] = str(guest.get("request") or "").strip()
    guest["willing_to_wait"] = bool(guest.get("willing_to_wait"))
    return guest


def _habit(client: dict, items: dict) -> str:
    if client.get("trait") != "приходит за одним и тем же":
        return ""
    item = items.get(client.get("preferred_item") or "")
    if not item:
        return ""
    return f"Обычно берёшь {item['name']}. Сегодня снова её, если она есть и по бюджету."


def talk_lines(visit_id: int) -> str:
    chunks = []
    for row in db.visit_lines(visit_id):
        if row["action"] in ("queue", "left", "verdict"):
            continue
        who = "Гость" if row["role"] == "client" else "Бариста"
        chunks.append(f"{who}: {row['text']}")
    return "\n".join(chunks)


class Engine:
    def __init__(self, llm: LLM, notify, city=None):
        self.llm = llm
        self.notify = notify
        self.task: asyncio.Task | None = None
        self._pause = asyncio.Event()
        self.gen = 0
        seed = os.environ.get("SIM_SEED")
        self.rng = random.Random(int(seed)) if seed else random.Random()
        self._think_depth = 0
        self._turn = 0
        self.city = city
        self.mind = None
        self._trips: dict[int, dict] = {}
        self._leaving: list[dict] = []

    def _ev(self, ev: str, level: str = "info", **fields) -> None:
        """Событие журнала с днём и часами симуляции. Сбой журнала ход не ломает."""
        try:
            state = db.run() or {}
            fields = {"day": state.get("day"), "clock": state.get("clock"), **fields}
            if db.current_place() != "cafe":
                fields.setdefault("place", db.current_place())
            log.event(ev, level, **fields)
        except Exception:
            pass

    def _live_minutes(self) -> float:
        state = db.run()
        return advance_minutes(
            state["clock_min"],
            state["clock_real"] or time.time(),
            time.time(),
            state["speed"] or 1,
            state["status"] == "running",
            bool(state.get("thinking")),
        )

    @contextlib.asynccontextmanager
    async def _thinking(self):
        """Пока модель отвечает, часы идут не быстрее часа за минуту: длительность визита не зависит от темпа."""
        if self._think_depth == 0:
            self._commit()
            db.set_run(thinking=1)
        self._think_depth += 1
        try:
            yield
        finally:
            self._think_depth -= 1
            if self._think_depth == 0:
                self._commit()
                db.set_run(thinking=0)

    def _commit(self, running: bool | None = None) -> float:
        state = db.run()
        moving = state["status"] == "running" if running is None else running
        minutes = advance_minutes(
            state["clock_min"],
            state["clock_real"] or time.time(),
            time.time(),
            state["speed"] or 1,
            moving,
            bool(state.get("thinking")),
        )
        db.set_run(clock_min=minutes, clock_real=time.time(), clock=format_clock(minutes))
        return minutes

    def recover(self) -> None:
        """После перезапуска закрыть визиты, которые оборвались на середине."""
        db.set_run(thinking=0)
        orphans = db.q("SELECT id, client_id FROM visits WHERE status = 'open'")
        if orphans:
            self._ev("run.recover", "warn", closed=[row["id"] for row in orphans])
        for row in orphans:
            db.update_visit(
                row["id"], status="failed", outcome_note="Прерван перезапуском сервера",
                memory_phrase="сбой, без оценки", rating=None,
            )
            db.finish_client(row["client_id"], None, "сбой, без оценки", None)
            db.execute("UPDATE arrivals SET status = 'done' WHERE visit_id = ? AND status = 'serving'", (row["id"],))
            db.execute("UPDATE run_state SET day_done = day_done + 1 WHERE id = 1")
        for row in db.clients():
            cleaned = plain_memory(row["memory"])
            if cleaned != (row["memory"] or ""):
                db.execute("UPDATE clients SET memory = ? WHERE id = ?", (cleaned, row["id"]))

    def kick(self, goal: str) -> None:
        self._ev("run.kick", goal=goal, speed=db.run().get("speed"))
        self._commit()
        db.set_run(goal=goal, status="running", message="", clock_real=time.time())
        self._pause.set()
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._loop())
        self.notify({"type": "status"})

    def pause(self) -> None:
        self._ev("run.pause", phase=db.run().get("phase") or None)
        minutes = self._live_minutes()
        db.set_run(clock_min=minutes, clock_real=time.time(), clock=format_clock(minutes), status="paused", phase="")
        self._pause.clear()
        self.notify({"type": "status"})

    async def reset(self) -> None:
        self._ev("run.reset", "warn")
        self.gen += 1
        self._pause.set()
        task = self.task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.task = None
        db.reset_world()
        self._trips.clear()
        self._leaving.clear()
        if self.city is not None:
            self.city.clear()
            self.city.populate(CITY_FOLK)
            self.city.set_places(db.places())
        self._pause.clear()
        self.notify({"type": "reset"})

    async def _loop(self) -> None:
        gen = self.gen
        try:
            while gen == self.gen:
                if not self._pause.is_set():
                    if db.run()["status"] == "running":
                        db.set_run(status="paused", phase="")
                        self.notify({"type": "status"})
                    await self._pause.wait()
                if gen != self.gen:
                    return
                db.set_run(status="running")
                result = await self._tick()
                if gen != self.gen:
                    return
                goal = db.run()["goal"]
                stop = result == "transport" or (result == "day_complete" and goal != "auto")
                if stop or not self._pause.is_set():
                    self._pause.clear()
                    continue
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._ev("engine.crash", "error", **log.exc_fields(exc))
            db.set_run(status="error", message=str(exc), phase="Сбой прогона")
            self.notify({"type": "error"})

    async def _tick(self) -> str:
        state = db.run()
        if state["pending_manager"]:
            return await self._close_day()
        if state["day"] == 0 or state["day_closed"]:
            self._open_day(plan=False)
            await self._story()
            await self._district()
            for place_id in venue_ids():
                with db.at_place(place_id):
                    await self._demographer()
            day = db.run()["day"]
            for place_id in venue_ids():
                with db.at_place(place_id):
                    self._plan_next(day, db.place(place_id)["open_min"])
            state = db.run()
        else:
            self._commit()
            state = db.run()
        clock = state["clock_min"]
        day = state["day"]
        ids = venue_ids()
        self._turn += 1
        for offset in range(len(ids)):
            place_id = ids[(self._turn + offset) % len(ids)]
            with db.at_place(place_id):
                result = await self._tick_place(day, clock)
            if result != "idle":
                return result
        if clock >= DAY_END:
            left = 0
            for place_id in ids:
                with db.at_place(place_id):
                    left += db.scheduled_left(day)
            if left == 0:
                return await self._close_day()
        await asyncio.sleep(0.4)
        return "wait"

    async def _tick_place(self, day: int, clock: float) -> str:
        """Один ход заведения: пришедшие встают в очередь, ждущие решают, ждать ли, следующий идёт к стойке.
        Вернёт `idle`, если заведению сейчас делать нечего."""
        if not db.one("SELECT id FROM arrivals WHERE day = ? AND place_id = ? LIMIT 1", (day, db.current_place())):
            # День открыт без потока для этого заведения (например, заведение добавили посреди дня): разыграть первый приход
            self._plan_next(day, max(clock, db.place(db.current_place())["open_min"]))
        self._arrivals_due(day, clock)
        queue = db.waiting(day)
        if not queue:
            return "idle"
        stopped = await self._patience_round(queue)
        if stopped:
            return stopped
        queue = db.waiting(day)
        if queue:
            return await self._serve(queue[0]["id"])
        return "ok"

    async def _close_day(self) -> str:
        state = db.run()
        week_len = int(db.setting("days_per_week") or 5)
        if state["day"] % week_len == 0 or state["pending_manager"]:
            db.set_run(pending_manager=1)
            for place_id in venue_ids():
                with db.at_place(place_id):
                    if db.one("SELECT id FROM weeks WHERE through_day = ? AND place_id = ?", (state["day"], place_id)):
                        continue
                    if not await self._manager():
                        return "transport"
            db.set_run(pending_manager=0)
        db.set_run(day_closed=1, phase="", active_agent="")
        stats = day_stats(state["day"])
        self._ev("day.close", visits=stats["visits"], served=stats["served"], refused=stats["refused"],
                 failed=stats["failed"], revenue=stats["revenue"], returned=stats["returned"],
                 avg_rating=round(stats["avg_rating"], 2) if stats["avg_rating"] is not None else None)
        self.notify({"type": "day"})
        return "day_complete"

    def _open_day(self, plan: bool = True) -> None:
        state = db.run()
        day = (state["day"] or 0) + 1
        now = time.time()
        db.set_run(
            day=day,
            day_target=0,
            day_done=0,
            day_closed=0,
            pending_manager=0,
            clock=format_clock(DAY_START),
            clock_min=DAY_START,
            clock_real=now,
            active_visit_id=None,
            phase="",
            active_agent="",
            message="",
        )
        for place_id in venue_ids():
            with db.at_place(place_id):
                for person in db.staff():
                    db.set_staff_mood(person["id"], pick_mood(self.rng.random()))
        self._ev("day.open", day=day, popularity=round(current_popularity(), 2),
                 moods={person["id"]: person["mood"] for person in db.staff()})
        if plan:
            for place_id in venue_ids():
                with db.at_place(place_id):
                    self._plan_next(day, db.place(place_id)["open_min"])
        self.notify({"type": "day"})

    def _plan_next(self, day: int, after: float) -> None:
        """Разыграть минуту следующего прихода. Расписания на день нет: в базе всегда не больше одного будущего прихода."""
        venue = venue_now()
        place = db.place(db.current_place())
        done = db.one("SELECT COUNT(*) AS n FROM visits WHERE day = ? AND place_id = ?", (day, place["id"]))["n"]
        if done + 1 >= venue.max_visits:
            self._ev("arrival.none", reason="потолок гостей за день", visits=done)
            return
        pop = current_popularity()
        voice = db.district_for(day)
        gap = arrival_gap(after, pop, self.rng.random(), voice["curve"] if voice else None,
                          base=venue.base_per_hour, table=venue.day_curve)
        minute = int(round(after + gap))
        if minute > place["close_min"] - 10:
            self._ev("arrival.none", reason="следующий гость пришёл бы после закрытия", gap=round(gap, 1))
            return
        db.add_arrivals(day, [minute])
        self._ev("arrival.plan", at=format_clock(minute), gap=round(gap, 1), popularity=round(pop, 2))

    def _spawn(self, day: int) -> dict:
        newcomer = db.take_newcomer()
        if newcomer:
            source = newcomer["story"] or None
            if db.referral_pool() > 0 and self.rng.random() < REFERRAL_CHANCE:
                friend = db.take_referral()
                if friend:
                    source = f"Тебя позвал знакомый, {friend}: сказал, что {venue_now().this_place} хорошо."
            return db.insert_client(newcomer["name"], newcomer["trait"], newcomer["patience"], newcomer["budget"], day, source)
        venue = venue_now()
        used = {client["name"] for client in db.clients()}
        name = self.rng.choice(venue.names)
        if name in used:
            name = f"{name} {self.rng.randint(2, 9)}"
        source = None
        if db.referral_pool() > 0 and self.rng.random() < REFERRAL_CHANCE:
            friend = db.take_referral()
            if friend:
                source = f"Тебя позвал знакомый, {friend}: сказал, что {venue_now().this_place} хорошо."
        return db.insert_client(
            name,
            self.rng.choice(venue.traits),
            self.rng.randint(1, 5),
            self.rng.choice(venue.budgets),
            day,
            source,
        )

    def _arrivals_due(self, day: int, clock: float) -> None:
        while True:
            due = db.due_arrival(day, clock)
            if not due:
                break
            self._come(due)

    def _travel(self, client: dict) -> tuple[str, str | None]:
        """Как человек добирается: на машине на парковку, пешком из дома или пешком с края квартала."""
        n = client["id"] % 5
        if n < 2:
            return "car", None
        if n < 4:
            return "walk", HOME_IDS[client["id"] % len(HOME_IDS)]
        return "walk", None

    def _come(self, arrival: dict) -> None:
        """Разыгранный приход: без города человек сразу у двери, с городом он выходит из дома или приезжает и идёт по улицам."""
        if self.city is None:
            self._admit(arrival)
            return
        client, known = self._pick(arrival)
        place_id = db.current_place()
        if not self.city.place_open(place_id, arrival["minute"]):
            self._ev("visit.closed", "warn", client=client["name"], place=place_id, why="заведение закрыто")
            return
        mode, home = self._travel(client)
        result = self.city.dispatch(client["id"], client["name"], place_id, mode, home)
        if not result["ok"] and mode == "car":
            self._ev("city.no_parking", "warn", client=client["name"], why=result["why"])
            result = self.city.dispatch(client["id"], client["name"], place_id, "walk", None)
        if not result["ok"]:
            self._ev("city.dispatch_fail", "warn", client=client["name"], why=result["why"])
            self._enter(client, known, float(arrival["minute"]), arrival["id"])
            return
        self._trips[client["id"]] = {"known": known, "arrival": arrival["id"], "place": place_id, "minute": arrival["minute"]}
        self._ev("city.dispatch", client=client["name"], client_id=client["id"], mode=mode, home=home, place=place_id,
                 planned=format_clock(arrival["minute"]))

    def _schedule_release(self, client_id: int, end_min: float | None, stay: int | None) -> None:
        """Когда гость выйдет из заведения и пойдёт дальше по городу: после визита, сидения и выхода к двери."""
        if self.city is None:
            return
        walk_out = 1.6 if venue_now().kind == "cafe" else 0.6
        day = db.run()["day"]
        at = day * 1440 + (end_min if end_min is not None else self._live_minutes()) + (stay or 0) + walk_out
        self._leaving.append({"client": client_id, "at": at})

    def pump_city(self) -> None:
        """Прибытия людей к дверям, выходы из заведений, записи города в журнал."""
        city = self.city
        for ev in city.drain_events():
            trip = self._trips.pop(ev["client_id"], None)
            place_id = ev.get("place") or "cafe"
            if ev["kind"] == "gave_up":
                self._ev("visit.gave_up", "warn", client_id=ev["client_id"], place=place_id, why=ev.get("why"))
                continue
            with db.at_place(place_id):
                client = db.one("SELECT * FROM clients WHERE id = ?", (ev["client_id"],))
                place = db.place(place_id)
                if trip is None or client is None or place is None:
                    city.release(ev["client_id"])
                    continue
                if ev["minute"] >= place["close_min"] or not city.place_open(place_id, ev["minute"]):
                    self._ev("visit.closed", "warn", client=client["name"], place=place_id, why="пришёл к закрытой двери")
                    city.release(ev["client_id"])
                    continue
                self._enter(client, trip["known"], float(ev["minute"]), trip["arrival"], side=ev.get("side"))
        for item in [row for row in self._leaving if row["at"] <= city.t]:
            self._leaving.remove(item)
            city.release(item["client"])
        for level, name, fields in city.drain_log():
            log.event(name, level, **fields)

    async def city_loop(self, broadcast) -> None:
        """Город идёт по часам симуляции, пока прогон работает; кадры уходят зрителям."""
        seen = -1
        while True:
            await asyncio.sleep(0.12)
            try:
                state = db.run()
                if self.city is None or state["status"] != "running" or not state["day"]:
                    continue
                self.city.advance(state["day"], self._live_minutes())
                self.pump_city()
                if self.mind is not None:
                    self.mind.poll()
                if self.city.roster_version != seen:
                    seen = self.city.roster_version
                    self.notify({"type": "city"})
                await broadcast(self.city.frame())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._ev("engine.crash", "error", where="city", **log.exc_fields(exc))
                await asyncio.sleep(1.0)

    def _pick(self, arrival: dict) -> tuple[dict, bool]:
        """Кто придёт по этому разыгранному приходу: знакомый или новый человек. Следующий приход разыгрывается здесь."""
        state = db.run()
        day = state["day"]
        db.set_arrival(arrival["id"], status="done")
        self._plan_next(day, arrival["minute"])
        voice = db.district_for(day)
        away = set(self._trips)  # кто уже в пути или у двери, второй раз не выберется
        if self.city is not None:
            away |= {ped.client_id for ped in self.city.peds.values() if ped.client_id}
        known = choose_arrival(
            db.clients(), day, db.visited_today(day) | away, current_popularity(), self.rng.random(), self.rng.random(),
            share=voice["newcomers"] if voice else None,
        )
        client = known or self._spawn(day)
        return client, bool(known)

    def _admit(self, arrival: dict) -> int:
        """Гость пришёл: появляется у двери и встаёт в очередь. Кто он и в каком настроении, решается здесь,
        бариста берёт его, когда освободится. Без города гость приходит в разыгранную минуту."""
        client, known = self._pick(arrival)
        return self._enter(client, known, float(arrival["minute"]), arrival["id"])

    def _enter(self, client: dict, known: bool, minute: float, arrival_id: int | None = None, side: int | None = None) -> int:
        """Человек у двери заведения: визит открыт, он стоит в очереди."""
        state = db.run()
        day = state["day"]
        mood = arrival_mood(self.rng.random(), self.rng.random(), client.get("mood"), client.get("liked"), 0)
        event_shift = int(sum(fx["amount"] for fx in event_effects("guest_mood")))
        if event_shift:
            mood = shift_mood(mood, max(-2, min(2, event_shift)))
        first = db.staff()[0]
        visit_id = db.insert_visit(
            day=day,
            seq=state["day_done"],
            clock=format_clock(minute),
            client_id=client["id"],
            staff_id=first["id"],
            status="waiting",
            is_return=1 if known else 0,
            requested_item_id=None,
            requested_text="",
            served_item_id=None,
            price=0,
            rating=None,
            asks=0,
            memory_before=client["memory"] or "",
            memory_phrase="",
            outcome_note="",
            start_min=float(minute),
            mood=mood,
            wait_min=0,
            next_check=float(minute + QUEUE_CHECK_EVERY),
            side=side,
        )
        if arrival_id is not None:
            db.set_arrival(arrival_id, visit_id=visit_id)
        self._ev("visit.arrive", visit_id=visit_id, client=client["name"], client_id=client["id"], trait=client["trait"],
                 returning=known, planned=format_clock(minute), mood=mood,
                 queue=len(db.waiting(day)), source=client.get("source") or None)
        self.notify({"type": "visit"})
        return visit_id

    async def _visit(self, arrival: dict) -> str:
        """Пришёл и сразу обслужен (без очереди). Движок ходит через `_admit` и `_serve`, это удобная связка для тестов:
        часы подтягиваются до минуты прихода, как при «Позвать гостя»."""
        if self._live_minutes() < arrival["minute"]:
            db.set_run(clock_min=float(arrival["minute"]), clock_real=time.time(), clock=format_clock(arrival["minute"]))
        return await self._serve(self._admit(arrival))

    async def _serve(self, visit_id: int) -> str:
        """Бариста берёт первого из очереди и ведёт разговор до чека или отказа."""
        state = db.run()
        first = db.visit(visit_id)
        client = db.one("SELECT * FROM clients WHERE id = ?", (first["client_id"],))
        staff_rows = db.staff()
        person = staff_rows[state["day_done"] % len(staff_rows)]
        now = self._live_minutes()
        wait = max(0.0, now - first["start_min"])
        guest_mood = shift_mood(first.get("mood"), wait_shift(wait))
        staff_mood = person.get("mood") or DEFAULT_MOOD
        db.update_visit(
            visit_id, status="open", serve_min=now, staff_id=person["id"], mood=guest_mood,
            staff_mood=staff_mood, wait_min=round(wait, 1),
        )
        db.set_run(active_visit_id=visit_id, message="")
        began = time.perf_counter()
        self._ev("visit.start", visit_id=visit_id, client=client["name"], client_id=client["id"], staff=person["id"],
                 trait=client["trait"], returning=bool(first["is_return"]), planned=first["clock"],
                 late_min=round(wait, 1), mood=guest_mood, staff_mood=staff_mood)
        self.notify({"type": "visit"})
        menu = menu_block()
        try:
            guest = await self._speak(
                "Гость выбирает слова",
                "client",
                "client",
                self._client_prompt(client, menu, visit_id),
                visit_id,
                final_staff=False,
            )
        except TransportError as exc:
            self._fail(visit_id, client["id"], str(exc), pause=True)
            return "transport"
        except SchemaError as exc:
            self._fail(visit_id, client["id"], str(exc), pause=False)
            return "schema"

        guest = _heard(guest)
        db.add_line(visit_id, "client", guest["say"].strip(), None, guest["item_id"])
        db.update_visit(
            visit_id,
            requested_item_id=guest["item_id"] or None,
            requested_text=guest["request"],
            memory_phrase=guest["say"].strip()[:140],
        )
        self.notify({"type": "line"})
        try:
            reply = await self._speak(
                "Бариста отвечает",
                "staff",
                "staff",
                self._staff_prompt(person, client, menu, guest, final=False, visit_id=visit_id),
                visit_id,
                final_staff=False,
            )
        except TransportError as exc:
            self._fail(visit_id, client["id"], str(exc), pause=True)
            return "transport"
        except SchemaError as exc:
            self._fail(visit_id, client["id"], str(exc), pause=False)
            return "schema"

        reply = _closed(reply)
        self._staff_feels(person, reply.get("mood"), visit_id)
        db.add_line(visit_id, "staff", reply["say"], reply["action"], reply["item_id"])
        self.notify({"type": "line"})
        asks = 0
        if reply["action"] == "ask":
            asks = 1
            try:
                guest = await self._speak(
                    "Гость отвечает на вопрос",
                    "client",
                    "client",
                    self._client_prompt(client, menu, visit_id),
                    visit_id,
                    final_staff=False,
                    echo_of=reply["say"],
                )
                guest = _heard(guest)
                chosen = catalog().get(guest["item_id"])
                if chosen and echo_ratio(guest["say"], reply["say"]) >= ECHO_LIMIT:
                    guest["say"] = fallback_choice(chosen["name"])
                    self._ev("dialog.fallback", "warn", visit_id=visit_id, who="client")
                db.add_line(visit_id, "client", guest["say"].strip(), None, guest["item_id"])
                if guest["item_id"]:
                    db.update_visit(visit_id, requested_item_id=guest["item_id"], requested_text=guest["request"])
                reply = await self._speak(
                    "Бариста закрывает заказ",
                    "staff",
                    "staff_final",
                    self._staff_prompt(person, client, menu, guest, final=True, visit_id=visit_id),
                    visit_id,
                    final_staff=True,
                )
            except TransportError as exc:
                self._fail(visit_id, client["id"], str(exc), pause=True)
                return "transport"
            except SchemaError as exc:
                self._fail(visit_id, client["id"], str(exc), pause=False)
                return "schema"
            reply = _closed(reply)
            self._staff_feels(person, reply.get("mood"), visit_id)
            shown = catalog().get(reply["item_id"] or guest["item_id"])
            if reply["action"] == "serve" and "?" in reply["say"] and shown:
                reply["say"] = fallback_close(shown["name"])
                self._ev("dialog.fallback", "warn", visit_id=visit_id, who="staff")
            db.add_line(visit_id, "staff", reply["say"], reply["action"], reply["item_id"])
            self.notify({"type": "line"})

        self._settle(visit_id, client, reply, asks)
        done = db.visit(visit_id)
        slow = 1.0
        for fx in event_effects("slower_prep"):
            slow *= fx["amount"]
        util = self._utilization()
        if util is not None and util >= GPU_SLOW:
            slow *= 1.5
        if slow > 1.0 and done["status"] == "served":
            item = catalog().get(done["served_item_id"] or "")
            extra = (item["minutes"] if item else 2) * (slow - 1.0)
            until = (done.get("end_min") or self._live_minutes()) + extra
            db.update_visit(visit_id, end_min=until)
            done = db.visit(visit_id)
            self._ev("event.slow", visit_id=visit_id, factor=round(slow, 2), extra_min=round(extra, 1))
            stopped = await self._hold(state["day"], until)
            if stopped:
                return stopped
        self._ev("visit.end", visit_id=visit_id, status=done["status"], item=done["served_item_id"] or done["requested_item_id"],
                 price=done["price"], rating=done["rating"], asks=asks, sim_min=round((done["end_min"] or 0) - (done["start_min"] or 0), 1),
                 real_s=round(time.perf_counter() - began, 1), lines=len(done["lines"]), note=done["outcome_note"] or None)
        result = await self._verdict(visit_id, client, done)
        if result == "ok":
            await self._critic(visit_id)
        return result

    def _day_brief(self, day: int) -> str:
        """Контекст для рассказчика и режиссёра: день, популярность, настроение гостей, недавние события, меню."""
        weekday, season = calendar(day)
        likes = db.recent_likes(25)
        mood = f"{sum(likes) / len(likes):.1f} из 5" if likes else "пока нет данных"
        recent = "; ".join(f"день {row['day']}: {'невыполненное предложение: ' if row.get('proposals') else ''}{row['headline']}" for row in db.recent_events(4)) or "ничего особенного"
        menu = ", ".join(f"{item['id']} ({item['name']})" for item in db.items() if usable(item))
        crew = ", ".join(f"{row['id']} ({row['name']}, настроение {row.get('mood') or DEFAULT_MOOD})" for row in db.staff())
        return (
            f"День {day}, {weekday}, {season}.\n"
            f"Популярность заведения: {current_popularity():.2f} (1 — обычная). Оценка гостей в последних визитах: {mood}.\n"
            f"Меню сейчас: {menu}.\nБариста: {crew}.\nНедавние события: {recent}."
        )

    def _apply_event(self, day: int, data: dict, source: str, text: str | None) -> dict | None:
        """Применить проверенные действия и временные эффекты; сохранить невыполненные предложения."""
        items = {item["id"]: item for item in db.items()}
        crew = [row["id"] for row in db.staff()]
        event = clean_event(data, items, crew, max_days=1 if source == "director" else 3)
        if event is None and source == "director" and text:
            event = {"headline": text[:60], "story": "", "effects": []}
        if event is None:
            self._ev("event.calm", source=source)
            return None
        until = day + max([fx["days"] for fx in event["effects"]] + [1]) - 1
        changes, notes = apply_changes({key: dict(value) for key, value in items.items()}, data.get("changes", []), world=True)
        proposals = list(data.get("proposals", [])) + notes
        event["changes"], event["proposals"] = changes, proposals
        if proposals:
            event["story"] = "Предложение события: " + event["story"]
        db.add_event(day, until, source, text, event["headline"], event["story"], event["effects"], changes, proposals)
        self._ev("event.actions", changes=changes or None, proposals=proposals or None)
        names = {row["id"]: row["name"] for row in db.staff()}
        for fx in event["effects"]:
            if fx["type"] == "item_out":
                db.block_item(fx["target"], day + fx["days"] - 1)
            elif fx["type"] == "staff_mood":
                for row in db.staff():
                    if fx["target"] in ("all", row["id"]):
                        now = shift_mood(row.get("mood"), int(fx["amount"]))
                        db.set_staff_mood(row["id"], now)
                        self._ev("mood.staff", staff=row["id"], was=row.get("mood"), now=now, by="event")
        self._ev("event.new", source=source, headline=event["headline"], until=until,
                 effects=[effect_label(fx, items, names) for fx in event["effects"]] or None, text=text)
        self.notify({"type": "event"})
        return event

    def _reviews_brief(self) -> str:
        stats = db.review_stats()
        rating = f"{stats['avg']:.1f} из 5 по {stats['count']} визитам" if stats["avg"] is not None else "отзывов пока нет"
        latest = "; ".join(f"{row['liked']}/5 «{row['review']}»" for row in stats["latest"][:8]) or "нет"
        per_day = ", ".join(f"день {row['day']}: {row['visits']}" for row in db.day_counts(7)) or "нет данных"
        return f"Оценка заведения: {rating}.\nСвежие отзывы: {latest}.\nГостей по дням: {per_day}."

    async def _district(self) -> None:
        """Районный голос: сколько людей и когда придёт сегодня. Без ответа остаётся прежняя формула."""
        day = db.run()["day"]
        weekday, season = calendar(day)
        prompt = (
            f"День {day}, {weekday}, {season}.\n{self._reviews_brief()}\n"
            f"Спрос от событий дня (пожар, праздник, акция) код применяет отдельно, в traffic его не учитывай: "
            f"оценивай только репутацию, день недели и сезон.\n"
            f"Для сравнения: по обычной формуле популярность была бы {popularity_hint():.2f}."
        )
        try:
            data = await self._speak("Районный голос оценивает день", "district", "district", prompt, None, False)
        except (TransportError, SchemaError) as exc:
            self._ev("district.fail", "warn", reason=str(exc))
            db.set_run(phase="", active_agent="")
            return
        db.set_run(phase="", active_agent="")
        view = clean_district(data, db.last_district_traffic(day))
        db.save_district(day, view)
        self._ev("district.new", traffic=view["traffic"], newcomers=view["newcomers"], curve=view["curve"], why=view["why"])
        self.notify({"type": "event"})

    async def _demographer(self) -> None:
        """Демограф создаёт пачку новых людей под сегодняшнюю репутацию. Без ответа новых гостей создаёт код."""
        day = db.run()["day"]
        voice = db.district_for(day)
        share = voice["newcomers"] if voice else 0.3
        expected = venue_now().base_per_hour * 12 * current_popularity()
        count = max(2, min(8, round(expected * share) + 1))
        weekday, season = calendar(day)
        events = "; ".join(f"{e['headline']} ({e['story']})" for e in db.active_events(day) if not e.get("proposals")) or "ничего особенного"
        known = ", ".join(row["name"] for row in db.clients()[:30]) or "пока никого"
        buzz = (voice or {}).get("buzz") or "ничего особенного"
        why = (voice or {}).get("why") or ""
        prompt = (
            f"День {day}, {weekday}, {season}.\n{self._reviews_brief()}\nСобытия сегодня: {events}.\n"
            f"Что говорят в районе: {buzz}. {why}\n"
            f"Уже известные имена (не повторяй): {known}.\nПридумай {count} новых людей."
        )
        try:
            venue = venue_now()
            key = "demographer" if venue.kind == "cafe" else f"demographer_{venue.kind}"
            data = await self._speak("Демограф придумывает людей", "demographer", key, prompt, None, False)
        except (TransportError, SchemaError) as exc:
            self._ev("demographer.fail", "warn", reason=str(exc))
            db.set_run(phase="", active_agent="")
            return
        db.set_run(phase="", active_agent="")
        taken = {row["name"] for row in db.clients()} | {row["name"] for row in db.q("SELECT name FROM pool")}
        guests = clean_newcomers(data, taken, limit=count + 2, traits=venue_now().traits, budgets=venue_now().budgets)
        db.reset_pool(day, guests)
        self._ev("demographer.new", asked=count, made=len(guests), names=[g["name"] for g in guests] or None)

    async def _realize_event(self, data: dict, text: str | None = None) -> dict:
        if not data.get("headline") and not data.get("story") and not text:
            return data
        prompt = self._day_brief(db.run()["day"]) + "\nПолное меню: " + json.dumps(db.items(), ensure_ascii=False)
        prompt += "\nСобытие: " + json.dumps(data, ensure_ascii=False) + "\nВброс владельца: " + (text or "нет")
        try:
            plan = await self._speak("Мир воплощает событие", "world", "world", prompt, None, False)
            return {**data, "changes": plan["changes"], "proposals": plan["proposals"]}
        except (TransportError, SchemaError) as exc:
            self._ev("event.fail", "warn", source="world", reason=str(exc))
            return {**data, "changes": [], "proposals": ["Действия события пока не проверены: " + str(exc)]}
        finally:
            db.set_run(phase="", active_agent="")

    async def _story(self) -> None:
        """Утром рассказчик придумывает день. Сбой модели не мешает дню: он остаётся обычным."""
        day = db.run()["day"]
        try:
            data = await self._speak("Рассказчик придумывает день", "narrator", "event", self._day_brief(day), None, False)
        except TransportError as exc:
            self._ev("event.fail", "warn", source="narrator", reason=str(exc))
            db.set_run(phase="", active_agent="")
            return
        except SchemaError as exc:
            self._ev("event.fail", "warn", source="narrator", reason=str(exc), schema=True)
            db.set_run(phase="", active_agent="")
            return
        db.set_run(phase="", active_agent="")
        data = await self._realize_event(data)
        event = self._apply_event(day, data, "narrator", None)
        if event and self.mind is not None and self.city is not None:
            await self.mind.adjudicate("", event["headline"], event["story"])

    async def direct(self, text: str) -> dict | None:
        """Режиссёр: владелец пишет событие словами, модель переводит его в эффекты из каталога."""
        state = db.run()
        if not state["day"] or state["day_closed"]:
            raise ValueError("Сначала откройте день")
        brief = self._day_brief(state["day"]) + f"\n\nВладелец вбросил событие: «{text.strip()[:200]}»"
        try:
            data = await self._speak("Режиссёр разбирает вброс", "director", "event", brief, None, False)
        except (TransportError, SchemaError) as exc:
            self._ev("event.fail", "warn", source="director", reason=str(exc))
            data = {"headline": "", "story": "", "effects": []}
        finally:
            db.set_run(phase="", active_agent="")
        data = await self._realize_event(data, text.strip()[:200])
        event = self._apply_event(state["day"], data, "director", text.strip()[:200])
        if self.mind is not None and self.city is not None:
            await self.mind.adjudicate(text.strip()[:200], (event or {}).get("headline", ""), (event or {}).get("story", ""))
        return event

    def end_event(self, event_id: int) -> bool:
        """Зритель завершил событие досрочно."""
        day = db.run()["day"]
        ended = bool(day) and db.end_event(event_id, day)
        self._ev("event.end", event_id=event_id, ended=ended)
        if ended:
            self.notify({"type": "event"})
        return ended

    async def _queue_work(self, day: int) -> str | None:
        """Пока бариста занят: приходят новые гости, ждущие по отметкам решают, ждать ли (включая первого в очереди)."""
        for place_id in venue_ids():
            with db.at_place(place_id):
                self._arrivals_due(day, self._live_minutes())
        return await self._patience_round(db.waiting(day), include_head=True)

    async def _hold(self, day: int, until: float) -> str | None:
        """Бариста занят до `until` (например, кофемашина барахлит). Очередь за это время живёт."""
        while self._live_minutes() < until:
            stopped = await self._queue_work(day)
            if stopped:
                return stopped
            await asyncio.sleep(0.2)
        return None

    async def _patience_round(self, queue: list[dict], include_head: bool = False) -> str | None:
        """Ждущие, кроме первого (его сейчас возьмут), по отметкам спрашиваются, ждать ли дальше."""
        for position, visit in enumerate(queue if include_head else queue[1:], start=0 if include_head else 1):
            now = self._live_minutes()
            if now < (visit.get("next_check") or visit["start_min"] + QUEUE_CHECK_EVERY):
                continue
            stopped = await self._patience_check(visit, now - visit["start_min"], position)
            if stopped:
                return stopped
        return None

    async def _patience_check(self, visit: dict, wait: float, ahead: int) -> str | None:
        client = db.one("SELECT * FROM clients WHERE id = ?", (visit["client_id"],))
        mood = shift_mood(visit.get("mood"), wait_shift(wait))
        prompt = (
            f"Ты {client['name']}. Характер: {client['trait']}. Терпение {client['patience']} из 5.\n"
            f"Настроение сейчас: {mood}.\n"
            f"{self._event_note()}"
            f"Ты стоишь в очереди {venue_now().where} уже {int(round(wait))} мин, перед тобой {ahead} чел. {venue_now().queue_phrase}\n"
            "Остаёшься ждать или уходишь?"
        )
        db.set_run(active_visit_id=visit["id"])
        self.notify({"type": "visit"})
        try:
            data = await self._speak("Гость решает, ждать ли", "queue", "queue", prompt, visit["id"], final_staff=False)
        except TransportError as exc:
            db.set_run(status="error", message=str(exc), phase="Ошибка модели", active_agent="")
            self.notify({"type": "error"})
            self._ev("queue.fail", "error", visit_id=visit["id"], reason=str(exc))
            return "transport"
        except SchemaError as exc:
            self._ev("queue.fail", "warn", visit_id=visit["id"], reason=str(exc), schema=True)
            data = {"stay": True, "say": ""}
        db.set_run(phase="", active_agent="")
        say = " ".join(str(data.get("say") or "").split())[:160]
        if data["stay"]:
            db.update_visit(visit["id"], next_check=visit["start_min"] + wait + QUEUE_CHECK_EVERY, mood=mood)
            if say:
                db.add_line(visit["id"], "client", say, "queue", None)
            self._ev("queue.stay", visit_id=visit["id"], waited=round(wait, 1), ahead=ahead, mood=mood)
            self.notify({"type": "line"})
            return None
        return await self._leave(visit, client, wait, mood, say)

    async def _leave(self, visit: dict, client: dict, wait: float, mood: str, say: str) -> str | None:
        """Гость не дождался: уходит, визит закрывается, вердикт он всё равно выносит."""
        now = self._live_minutes()
        memory = visit_trace("", "left", 1)
        db.add_line(visit["id"], "client", say or "Не буду ждать, пойду.", "left", None)
        db.update_visit(
            visit["id"], status="left", end_min=now, stay_min=0, wait_min=round(wait, 1), mood=mood, rating=1,
            memory_phrase=memory, outcome_note="Не дождался очереди",
        )
        db.finish_client(client["id"], 1, memory, None)
        self._schedule_release(client["id"], now, 0)
        db.set_run(day_done=db.run()["day_done"] + 1)
        self._ev("visit.left", "warn", visit_id=visit["id"], waited=round(wait, 1), mood=mood)
        self.notify({"type": "visit"})
        done = db.visit(visit["id"])
        result = await self._verdict(visit["id"], client, done)
        return "transport" if result == "transport" else None

    def _event_note(self) -> str:
        """Строка о сегодняшних событиях: роли учитывают её в тоне и словах. События касаются кофейни."""
        if db.current_place() != "cafe":
            return ""
        day = (db.run() or {}).get("day") or 0
        events = db.active_events(day) if day else []
        if not events:
            return ""
        return "".join(f"Сегодня: {e['headline']}. {e['story']}\n".replace(". .", ".") for e in events[-2:] if not e.get("proposals"))

    def _utilization(self) -> float | None:
        """Нагрузка на GPU, если заведение — ЦОД; для остальных None."""
        if venue_now().kind != "datacenter":
            return None
        day = (db.run() or {}).get("day") or 0
        return gpu_utilization(db.load_rows(day), day, DC_CAPACITY)

    def _dc_load_line(self, venue: Venue) -> str:
        util = self._utilization()
        if util is None:
            return ""
        return f"Нагрузка на GPU сейчас {int(round(util * 100))}% ({gpu_status(util)}).\n"

    def _dc_note(self, venue: Venue) -> str:
        util = self._utilization()
        return "В этот день GPU были перегружены, ответы шли медленно.\n" if util is not None and util >= GPU_SLOW else ""

    def _hints(self, role: str) -> str:
        """Напоминания роли по тому, что критик часто видел в последних диалогах."""
        found = active_hints(db.recent_critic(20), role)
        return ("\n".join(found) + "\n") if found else ""

    def _critic_prompt(self, visit: dict) -> str:
        venue = venue_now()
        names = {"client": visit["client_name"], "staff": visit["staff_name"]}
        rows = []
        for number, row in enumerate(visit["lines"], 1):
            if row["role"] == "client":
                who = f"{names['client']} про себя" if row["action"] == "verdict" else f"Гость {names['client']}"
                tag = ""
            else:
                who = f"{venue.staff_word.capitalize()} {names['staff']}"
                tag = f" [{row['action']}{' ' + row['item_id'] if row['item_id'] else ''}]"
            rows.append(f"{number}. {who}{tag}: {row['text']}")
        outcome = {
            "served": f"Итог: гостю подали, чек {visit['price']} ₽.",
            "refused": "Итог: гостю отказали.",
            "left": "Итог: гость не дождался и ушёл.",
        }.get(visit["status"], "Итог: разговор оборвался.")
        return (
            f"{venue.item_word}:\n{menu_block()}\n\n"
            f"Настроения: гость {visit.get('mood') or DEFAULT_MOOD}, {venue.staff_word} {visit.get('staff_mood') or DEFAULT_MOOD}.\n"
            f"Диалог:\n" + "\n".join(rows) + f"\n{outcome}"
        )

    async def _critic(self, visit_id: int) -> None:
        """Второй взгляд на диалог. Критик ничего не меняет в визите: замечания идут в журнал, на страницу и в напоминания ролям."""
        visit = db.visit(visit_id)
        if not visit or not visit["lines"]:
            return
        try:
            data = await self._speak(
                "Критик читает диалог", "critic", "critic", self._critic_prompt(visit), visit_id, final_staff=False,
                target="critic",
            )
        except TransportError as exc:
            self._ev("critic.fail", "warn", visit_id=visit_id, reason=str(exc))
            db.set_run(phase="", active_agent="")
            return
        except SchemaError as exc:
            self._ev("critic.fail", "warn", visit_id=visit_id, reason=str(exc), schema=True)
            db.set_run(phase="", active_agent="")
            return
        checked = clean_critic(data, [row["text"] for row in visit["lines"]])
        db.save_critic(visit_id, checked["score"], checked["issues"])
        db.set_run(phase="", active_agent="")
        high = [row for row in checked["issues"] if row["severity"] == "high"]
        self._ev("critic.review", "warn" if high else "info", visit_id=visit_id, score=checked["score"],
                 issues=[f"{row['code']}@{row['line']}" for row in checked["issues"]] or None)
        self.notify({"type": "line"})

    def _staff_after(self, visit: dict, liked: int | None) -> None:
        """Настроение бариста после визита: исход и вердикт гостя двигают его, к вечеру растёт усталость."""
        person = next((row for row in db.staff() if row["id"] == visit["staff_id"]), None)
        if person is None:
            return
        was = person.get("mood") or DEFAULT_MOOD
        now = after_visit_mood(was, visit["status"], liked, visit.get("end_min") or 0, self.rng.random())
        if now != was:
            db.set_staff_mood(person["id"], now)
            self._ev("mood.staff", staff=person["id"], was=was, now=now, by="outcome", visit_id=visit["id"])

    def _staff_feels(self, person: dict, mood: str | None, visit_id: int) -> None:
        """Бариста сам называет настроение после реплики. Неизвестное слово игнорируется."""
        if mood not in MOODS:
            return
        was = next((row.get("mood") for row in db.staff() if row["id"] == person["id"]), None)
        if mood != was:
            db.set_staff_mood(person["id"], mood)
            self._ev("mood.staff", staff=person["id"], was=was, now=mood, by="model", visit_id=visit_id)

    def _verdict_prompt(self, client: dict, visit: dict, item_name: str) -> str:
        venue = venue_now()
        if visit["status"] == "served":
            outcome = f"{venue.served_phrase}: {item_name}, заплатил {visit['price']} ₽."
        elif visit["status"] == "left":
            outcome = "Ты не дождался своей очереди и ушёл, тебя так и не обслужили."
        else:
            outcome = "Тебе отказали, ты ушёл без заказа."
        before = plain_memory(client.get("memory") or "")
        history = f"Раньше здесь: {before}\n" if before else "Ты был здесь впервые.\n"
        load = self._dc_note(venue)
        wait = visit.get("wait_min") or 0
        waited = f"Ты ждал своей очереди {int(round(wait))} мин.\n" if wait >= 5 else "Очереди не было.\n"
        return (
            f"Ты {client['name']}. Характер: {client['trait']}. Терпение {client['patience']} из 5.\n"
            f"{history}"
            f"Ты пришёл в настроении: {visit.get('mood') or DEFAULT_MOOD}. {venue.staff_look.format(name=visit['staff_name'], mood=visit.get('staff_mood') or DEFAULT_MOOD)}\n"
            f"{waited}{load}"
            f"{self._hints('verdict')}"
            f"{self._event_note()}"
            f"Сегодняшний разговор {venue.spot}:\n{talk_lines(visit['id'])}\n"
            f"{outcome}\n"
            f"{venue.leave_phrase} Скажи про себя, как прошёл визит, оцени его, реши, вернёшься ли и когда, посоветуешь ли знакомым."
        )

    async def _verdict(self, visit_id: int, client: dict, visit: dict) -> str:
        """Гость сам решает, понравилось ли и вернётся ли. Это входит в популярность и в шанс прихода."""
        item = catalog().get(visit["served_item_id"] or "")
        sound = fallback_verdict(visit["status"], visit["rating"])
        used_fallback = True
        result = "ok"
        try:
            said = next((line["text"] for line in visit["lines"] if line["role"] == "client" and line["action"] != "verdict"), "")
            data = await self._speak(
                "Гость делится впечатлением", "verdict", "verdict",
                self._verdict_prompt(client, visit, item["name"] if item else ""), visit_id, final_staff=False,
                echo_of=said,
            )
            sound = clean_verdict(data)
            used_fallback = False
            if said and echo_ratio(sound["say"], said) >= ECHO_LIMIT:
                sound["say"] = ""
                self._ev("verdict.echo", "warn", visit_id=visit_id)
        except TransportError as exc:
            self._ev("verdict.fail", "error", visit_id=visit_id, reason=str(exc))
            db.set_run(status="error", message=str(exc), phase="Ошибка модели")
            self.notify({"type": "error"})
            result = "transport"
        except SchemaError as exc:
            self._ev("verdict.fallback", "warn", visit_id=visit_id, reason=str(exc))
        if used_fallback:
            sound = clean_verdict(sound)
        day = visit["day"]
        liked = sound["liked"]
        if not sound.get("mood"):
            sound["mood"] = shift_mood(visit.get("mood"), 1 if liked >= 4 else -1 if liked <= 2 else 0)
        db.save_verdict(visit_id, client["id"], sound, come_day_for(sound["return"], sound["return_in_days"], day))
        self._staff_after(visit, liked)
        if result == "ok":
            db.set_run(phase="", active_agent="")
        self._ev("visit.verdict", visit_id=visit_id, mood_after=sound["mood"], liked=sound["liked"], returns=sound["return"], in_days=sound["return_in_days"],
                 recommend=sound["recommend"], fallback=used_fallback or None, popularity=round(current_popularity(), 2))
        self.notify({"type": "line"})
        return result

    async def _speak(self, phase, agent, schema_key, user, visit_id, final_staff, echo_of="", target=""):
        db.set_run(phase=phase, active_agent=agent)
        self.notify({"type": "llm"})
        async with self._thinking():
            return await self.llm.complete(
                agent=agent,
                schema_key=schema_key,
                system=load_system(agent, venue_now().prompts),
                user=user,
                visit_id=visit_id,
                week_day=None,
                final_staff=final_staff,
                **({"echo_of": echo_of} if echo_of else {}),
                **({"target": target} if target else {}),
            )

    def _settle(self, visit_id: int, client: dict, reply: dict, asks: int) -> None:
        visit = db.visit(visit_id)
        requested = visit["requested_item_id"] or ""
        chosen_id = reply["item_id"] or requested
        catalog = {item["id"]: item for item in db.items()}
        item = catalog.get(chosen_id)
        note = ""
        util = self._utilization()
        capacity_full = bool(util is not None and util >= GPU_FULL and item and (item.get("load_days") or 1) >= 30)
        if reply["action"] == "serve" and item and usable(item) and not capacity_full:
            status = "served"
            price = item["price"]
            served_id = item["id"]
            label = item["name"]
        else:
            status = "refused"
            price = 0
            served_id = None
            label = item["name"] if item else (visit["requested_text"] or "без позиции")
            if reply["action"] == "serve":
                note = "Нет ёмкости GPU под безлимит, оформление отклонено." if capacity_full else "Позиция недоступна или не из меню, чек не создан."
        rating = rating_for(status, asks, effective_patience(client["patience"], visit.get("mood")))
        if rating and util is not None and util >= GPU_SLOW:
            rating = max(1, rating - 1)
        memory = visit_trace(label, status, rating)
        db.update_visit(
            visit_id,
            status=status,
            served_item_id=served_id,
            price=price,
            rating=rating,
            asks=asks,
            memory_phrase=memory,
            outcome_note=note,
            end_min=self._live_minutes(),
            stay_min=stay_minutes(visit_id, status, mood_value(visit.get("mood"))) if venue_now().stay else 0,
        )
        db.finish_client(client["id"], rating, memory, served_id)
        ended = db.visit(visit_id)
        self._schedule_release(client["id"], ended["end_min"], ended["stay_min"])
        state = db.run()
        db.set_run(day_done=state["day_done"] + 1, phase="", active_agent="")
        self._commit()
        self.notify({"type": "visit"})

    def _fail(self, visit_id: int, client_id: int, message: str, pause: bool) -> None:
        self._ev("visit.fail", "error" if pause else "warn", visit_id=visit_id, reason=message, pause=pause)
        broken = db.visit(visit_id)
        if broken:
            self._staff_after({**broken, "status": "failed"}, None)
        memory = "сбой, без оценки"
        db.update_visit(
            visit_id, status="failed", outcome_note=message, memory_phrase=memory, rating=None,
            end_min=self._live_minutes(), stay_min=0,
        )
        db.finish_client(client_id, None, memory, None)
        self._schedule_release(client_id, None, 0)
        state = db.run()
        fields = {
            "day_done": state["day_done"] + 1,
            "phase": "Ошибка модели",
            "active_agent": "",
            "message": message,
        }
        if pause:
            fields["status"] = "error"
        db.set_run(**fields)
        self.notify({"type": "error" if pause else "visit"})

    async def _manager(self) -> bool:
        state = db.run()
        summary = week_summary(state["day"])
        self._ev("manager.start", items=summary["menu_size"], visits=summary["visits"], wishes=len(summary["wishes"]))
        who = "Управляющий" if db.current_place() == "cafe" else f"Управляющий {db.place(db.current_place())['name']}"
        db.set_run(phase=f"{who} читает неделю", active_agent="управляющий", message="")
        self.notify({"type": "llm"})
        user = "Сводка недели:\n" + json.dumps(summary, ensure_ascii=False, indent=2)
        try:
            async with self._thinking():
                data = await self.llm.complete(
                    agent="manager",
                    schema_key="manager",
                    system=load_system("manager", venue_now().prompts),
                    user=user,
                    visit_id=None,
                    week_day=state["day"],
                )
        except TransportError as exc:
            self._ev("manager.fail", "error", reason=str(exc))
            db.set_run(status="error", message=str(exc), phase="Ошибка модели")
            self.notify({"type": "error"})
            return False
        except SchemaError as exc:
            self._ev("manager.fail", "warn", reason=str(exc), schema=True)
            self._store_week(state["day"], summary, "", [], [str(exc)])
            return True
        catalog = {item["id"]: dict(item) for item in db.items()}
        venue = venue_now()
        applied, notes = apply_changes(catalog, data["changes"], prefix="new" if venue.kind == "cafe" else f"{db.current_place()[:2]}",
                                       price_max=venue.price_max)
        for change in applied:
            if change["op"] == "add_item":
                db.insert_item(change["item_id"], change["name"], change["price"], change["minutes"])
                continue
            item = catalog[change["item_id"]]
            db.save_item(change["item_id"], int(item["price"]), int(item["available"]))
        self._ev("manager.end", applied=[f"{c['op']}:{c.get('name') or c['item_id']}" for c in applied],
                 notes=notes or None, say_len=len(data["say"]))
        self._store_week(state["day"], summary, data["say"], applied, notes)
        return True

    def _store_week(self, day: int, summary: dict, say: str, changes: list, notes: list) -> None:
        db.add_week(
            through_day=day,
            summary_json=json.dumps(summary, ensure_ascii=False),
            say=say,
            changes_json=json.dumps(changes, ensure_ascii=False),
            notes_json=json.dumps(notes, ensure_ascii=False),
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        self.notify({"type": "week"})

    def _client_prompt(self, client: dict, menu: str, visit_id: int) -> str:
        memory = plain_memory(client.get("memory") or "")
        if memory:
            past = memory + " Это уже было. Ту старую фразу не произноси и не пересказывай."
        else:
            past = "Первый визит: ты здесь впервые, прошлого заказа нет." + (f" {client['source']}" if client.get("source") else "")
        venue = venue_now()
        habit = _habit(client, catalog())
        spoken = talk_lines(visit_id)
        tone = "" if spoken else venue.trait_say.get(client.get("trait") or "", "")
        mood = (db.visit(visit_id) or {}).get("mood")
        card = (
            f"{venue.item_word}:\n{menu}\n\n"
            f"{self._hints('client')}"
            f"{self._event_note()}"
            f"Ты {client['name']} {venue.spot}. Характер: {client['trait']}. "
            f"Терпение {client['patience']} из 5. Дороже {client['budget']} ₽ не бери и эту сумму вслух не называй. Цену тоже не называй.\n"
            + (f"Настроение сейчас: {mood}.\n" if mood else "")
            + f"{past}\n"
            + (f"{habit}\n" if habit else "")
            + (f"{tone}\n" if tone else "")
        )
        if not spoken:
            return card + f"Скажи {venue.staff_dat}, что берёшь сегодня. Характер вслух не зачитывай."
        return (
            card
            + "Этот же разговор, не новый заказ:\n"
            + spoken
            + f"\nОтветь на последнюю реплику {venue.staff_of} своими словами: если он спросил, что взять, выбери одну позицию и назови её. Его вопрос не повторяй и свою первую фразу не повторяй. Ты определился."
        )

    def _staff_prompt(self, person: dict, client: dict, menu: str, guest: dict, final: bool, visit_id: int) -> str:
        pace = "Работаешь быстрее обычного." if person["speed"] >= 1 else "Работаешь спокойнее и дольше."
        venue = venue_now()
        voice = venue.voices.get(person["id"], "Говоришь просто.")
        items = catalog()
        item = items.get(guest["item_id"])
        if item:
            picked = (
                f"В поле заказа: {item['name']}, {item['minutes']} мин, "
                f"{'есть' if usable(item) else 'скрыта'}."
            )
        else:
            picked = "В поле заказа позиции нет."
        request = (guest.get("request") or "").strip()
        wish = f"Просьба: {request}" if request else "Отдельной просьбы нет."
        wait = "Ждать готов: да." if guest.get("willing_to_wait") else "Ждать готов: нет."
        memory = plain_memory(client.get("memory") or "") or "Гость впервые, обычный заказ неизвестен."
        if final:
            task = (
                "Уточнение уже было. Закрой визит: serve или refuse.\n"
                "Ответь на последние слова гостя утверждением, без вопроса. В реплике одна позиция — её id в item_id. "
                "Цену не называй, если гость не спросил, сколько стоит. Вторую не добавляй."
            )
        else:
            task = (
                "Если в поле заказа одна позиция и гость может ждать — serve, в реплике только она, без цены.\n"
                "Если гость просит совета между двумя позициями — посоветуй одну и сразу serve, без вопроса.\n"
                "Если позиции в поле нет и непонятно, чего гость хочет, — один вопрос, ask. Не отдавай, пока не ясно, что одно."
            )
        mood = next((row.get("mood") for row in db.staff() if row["id"] == person["id"]), None) or DEFAULT_MOOD
        return (
            f"{venue.item_word}:\n{menu}\n\n"
            f"Ты {person['name']}. {pace} {voice}\n"
            f"Твоё настроение: {mood}.\n"
            f"{self._dc_load_line(venue)}"
            f"{self._hints('staff')}"
            f"{self._event_note()}"
            f"Гость {client['name']}. {memory}\n"
            f"Разговор:\n{talk_lines(visit_id)}\n"
            f"{picked}\n{wish}\n{wait}\n"
            f"{task}"
        )
