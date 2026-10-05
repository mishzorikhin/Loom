import asyncio
import json
import os
import time
import tempfile
import unittest
from pathlib import Path

_TMP = Path(tempfile.mkdtemp())
os.environ["SIM_DB"] = str(_TMP / "sim.db")
os.environ["SIM_LOG"] = str(_TMP / "simcheck.log")
os.environ["SIM_LOG_STDOUT"] = "0"

import app.db as db  # noqa: E402
import app.engine as engine_mod  # noqa: E402
from app import log  # noqa: E402
from app.engine import Engine, menu_block  # noqa: E402
from app.llm import SchemaError, TransportError  # noqa: E402
from app.rules import mood_value, shift_mood, stay_minutes  # noqa: E402
from app.view import current_popularity, popularity_hint, snapshot  # noqa: E402


class FakeLLM:
    """Подменяет модель: гость просит эспрессо, бариста отдаёт. Сбои задаются сценарием."""

    def __init__(self):
        self.calls = []
        self.fail = None
        self.script = {}

    async def complete(self, *, agent, schema_key, system, user, visit_id, week_day, final_staff=False, echo_of="", target=""):
        self.calls.append(agent)
        if self.fail == agent:
            raise self.fail_with
        if agent in self.script:
            return self.script[agent]
        if agent in ("narrator", "director"):
            return {"headline": "", "story": "", "effects": []}
        if agent == "district":
            return {"traffic": 1.0, "newcomers": 0.3, "curve": [1, 1, 1, 1, 1, 1], "why": "", "buzz": ""}
        if agent == "demographer":
            return {"guests": []}
        if agent == "queue":
            return {"stay": True, "say": "Подожду."}
        if agent == "critic":
            return {"score": 5, "issues": []}
        if agent == "verdict":
            return {"say": "Было приятно.", "liked": 5, "return": "yes", "return_in_days": 2, "recommend": True,
                    "review": "Быстро и вкусно."}
        if agent == "client":
            return {"say": "Эспрессо, пожалуйста", "item_id": "espresso", "request": "", "willing_to_wait": True}
        if agent == "staff":
            return {"say": "Держите", "action": "serve", "item_id": "espresso"}
        return {"say": "Спрос ровный", "changes": []}


def fresh() -> tuple[Engine, FakeLLM]:
    db.connect(Path(os.environ["SIM_DB"]))
    db.reset_world()
    llm = FakeLLM()
    return Engine(llm, lambda payload: None), llm


def run_async(coro):
    return asyncio.run(coro)


class EngineTest(unittest.TestCase):
    def test_visit_serves_and_writes_check(self):
        engine, _ = fresh()
        engine._open_day()
        arrival = db.next_arrival(1)
        self.assertEqual(run_async(engine._visit(arrival)), "ok")
        visit = db.q("SELECT * FROM visits")[0]
        self.assertEqual(visit["status"], "served")
        self.assertEqual(visit["price"], 150)
        self.assertEqual(visit["rating"], 5)
        self.assertGreaterEqual(visit["start_min"], 480)
        self.assertGreaterEqual(visit["end_min"], visit["start_min"])
        self.assertEqual(visit["stay_min"], stay_minutes(visit["id"], "served", mood_value(visit["mood"])))

    def test_journal_has_visit_and_day_events(self):
        engine, _ = fresh()
        engine._open_day()
        run_async(engine._visit(db.next_arrival(1)))
        events = log.read(n=50)
        names = [row["ev"] for row in events]
        self.assertIn("day.open", names)
        start = [row for row in events if row["ev"] == "visit.start"][-1]
        end = [row for row in events if row["ev"] == "visit.end"][-1]
        self.assertEqual(start["visit_id"], end["visit_id"])
        self.assertEqual((end["status"], end["price"], end["day"]), ("served", 150, 1))
        self.assertEqual(log.read(n=10, visit=start["visit_id"], ev="visit.end")[0]["ev"], "visit.end")

    def test_journal_marks_failure_as_error(self):
        engine, llm = fresh()
        llm.fail, llm.fail_with = "client", TransportError("нет связи")
        engine._open_day()
        run_async(engine._visit(db.next_arrival(1)))
        failed = log.read(n=20, level="error", ev="visit.fail")
        self.assertEqual(len(failed), 1)
        self.assertIn("нет связи", failed[0]["reason"])

    def test_verdict_decides_return_and_recommendation(self):
        engine, llm = fresh()
        engine._open_day()
        run_async(engine._visit(db.next_arrival(1)))
        visit = db.q("SELECT * FROM visits")[0]
        self.assertEqual((visit["liked"], visit["intent"], visit["recommend"]), (5, "yes", 1))
        self.assertEqual(visit["verdict"], "Было приятно.")
        client = db.clients()[0]
        self.assertEqual((client["liked"], client["intent"], client["come_day"], client["referrals"]), (5, "yes", 3, 1))
        last = db.visit_lines(visit["id"])[-1]
        self.assertEqual((last["role"], last["action"]), ("client", "verdict"))
        self.assertEqual(llm.calls[-2:], ["verdict", "critic"])
        self.assertEqual(db.run()["phase"], "")
        said = log.read(5, ev="visit.verdict")[-1]
        self.assertEqual((said["visit_id"], said["liked"], said["returns"]), (visit["id"], 5, "yes"))

    def test_moods_flow_into_prompts_and_back(self):
        engine, llm = fresh()
        prompts = []

        async def watching(**kwargs):
            prompts.append((kwargs["agent"], kwargs["user"]))
            agent = kwargs["agent"]
            if agent == "client":
                return {"say": "Эспрессо, пожалуйста", "item_id": "espresso", "request": "", "willing_to_wait": True}
            if agent == "staff":
                return {"say": "Держите.", "action": "serve", "item_id": "espresso", "mood": "раздражение"}
            return {"say": "Нормально.", "liked": 4, "return": "yes", "return_in_days": 2, "recommend": False, "mood": "радость"}

        llm.complete = watching
        engine._open_day()
        self.assertTrue(all(person["mood"] for person in db.staff()))
        for person in db.staff():
            db.set_staff_mood(person["id"], "спокойствие")
        run_async(engine._visit(db.next_arrival(1)))
        visit = db.q("SELECT * FROM visits")[0]
        guest_prompt = next(text for agent, text in prompts if agent == "client")
        self.assertIn(f"Настроение сейчас: {visit['mood']}", guest_prompt)
        staff_prompt = next(text for agent, text in prompts if agent == "staff")
        self.assertIn("Твоё настроение:", staff_prompt)
        verdict_prompt = next(text for agent, text in prompts if agent == "verdict")
        self.assertIn("Ты пришёл в настроении", verdict_prompt)
        self.assertIn("Очереди не было", verdict_prompt)
        self.assertEqual(visit["mood_after"], "радость")
        self.assertEqual(db.clients()[0]["mood"], "радость")
        crew = {row["id"]: row["mood"] for row in db.staff()}
        self.assertEqual(crew[visit["staff_id"]], "усталость")
        said = log.read(10, ev="mood.staff")
        self.assertEqual({row["by"] for row in said[-2:]}, {"model", "outcome"})

    def test_waiting_makes_guest_worse_and_is_told_to_the_verdict(self):
        engine, llm = fresh()
        seen = []

        async def watching(**kwargs):
            seen.append(kwargs["user"])
            return await original(**kwargs)

        original = llm.complete
        llm.complete = watching
        engine._open_day()
        arrival = db.next_arrival(1)
        db.execute("UPDATE arrivals SET minute = ? WHERE id = ?", (400, arrival["id"]))
        db.set_run(clock_min=480, clock_real=0)
        visit_id = engine._admit(db.next_arrival(1) or db.q("SELECT * FROM arrivals")[0])
        provisional = db.visit(visit_id)["mood"]
        run_async(engine._serve(visit_id))
        visit = db.q("SELECT * FROM visits")[0]
        self.assertGreater(visit["wait_min"], 30)
        self.assertEqual(visit["mood"], shift_mood(provisional, -2))
        self.assertTrue(any("ждал своей очереди" in text for text in seen))
        self.assertEqual(visit["stay_min"], stay_minutes(visit["id"], visit["status"], mood_value(visit["mood"])))

    def test_critic_reviews_visit_and_stores_issues(self):
        engine, llm = fresh()
        llm.script["critic"] = {"score": 3, "issues": [
            {"code": "price_named", "line": 2, "quote": "Держите", "severity": "high", "note": "назвала цену"},
            {"code": "что-то", "line": 1, "quote": "Эспрессо", "severity": "low", "note": "мусор"},
            {"code": "echo", "line": 99, "quote": "", "severity": "weird", "note": "x" * 300},
            {"code": "nonsense", "line": 1, "quote": "этого нет в реплике", "severity": "low", "note": "выдумка"},
        ]}
        engine._open_day()
        run_async(engine._visit(db.next_arrival(1)))
        visit = db.q("SELECT * FROM visits")[0]
        stored = json.loads(visit["critic_json"])
        self.assertEqual(visit["critic_score"], 3)
        self.assertEqual([row["code"] for row in stored], ["price_named", "echo"])
        self.assertEqual(stored[1]["line"], 0)
        self.assertEqual(stored[1]["severity"], "low")
        self.assertLessEqual(len(stored[1]["note"]), 160)
        self.assertEqual(llm.calls[-1], "critic")
        said = log.read(5, ev="critic.review")[-1]
        self.assertEqual(said["lvl"], "warn")
        self.assertEqual(db.run()["phase"], "")

    def test_critic_failure_does_not_stop_the_run(self):
        engine, llm = fresh()
        llm.fail, llm.fail_with = "critic", TransportError("нет связи")
        engine._open_day()
        self.assertEqual(run_async(engine._visit(db.next_arrival(1))), "ok")
        self.assertEqual(db.run()["status"], "idle")
        self.assertIsNone(db.q("SELECT critic_json FROM visits")[0]["critic_json"])
        self.assertTrue(log.read(5, ev="critic.fail"))

    def test_frequent_critic_issues_become_prompt_hints(self):
        engine, llm = fresh()
        prompts = []
        original = llm.complete

        async def watching(**kwargs):
            prompts.append((kwargs["agent"], kwargs["user"]))
            return await original(**kwargs)

        llm.complete = watching
        engine._open_day()
        for visit_id in range(3):
            run_async(engine._visit(db.next_arrival(1)))
            db.save_critic(visit_id + 1, 3, [{"code": "price_named", "line": 2, "severity": "high", "note": ""}])
        prompts.clear()
        run_async(engine._visit(db.next_arrival(1)))
        staff = next(text for agent, text in prompts if agent == "staff")
        client = next(text for agent, text in prompts if agent == "client")
        self.assertIn("цену не называй, пока гость не спросил", staff)
        self.assertNotIn("цену не называй, пока", client)

    def _crowd(self, engine, minutes=(482, 483)):
        engine._open_day()
        engine._plan_next = lambda *args, **kwargs: None  # без случайных добавочных гостей: тест задаёт приходы сам
        db.execute("DELETE FROM arrivals")
        db.add_arrivals(1, list(minutes))
        db.set_run(clock_min=500.0, clock_real=0, status="running", goal="auto")

    def test_clock_is_slow_only_while_the_model_thinks(self):
        engine, llm = fresh()
        engine._open_day()
        db.set_run(status="running", speed=8.0, clock_min=480.0, clock_real=time.time() - 10)
        self.assertAlmostEqual(engine._live_minutes(), 480 + 80, delta=1)

        async def inside():
            async with engine._thinking():
                self.assertEqual(db.run()["thinking"], 1)
                db.set_run(clock_real=time.time() - 10)
                return engine._live_minutes()

        slow = run_async(inside())
        self.assertAlmostEqual(slow, 560 + 10, delta=1)
        self.assertEqual(db.run()["thinking"], 0)

    def test_event_item_out_blocks_the_item_and_expires(self):
        engine, llm = fresh()
        engine._open_day()
        engine._apply_event(1, {"headline": "Кончилось молоко", "story": "Поставка завтра.", "effects": [
            {"type": "item_out", "target": "latte", "amount": 0, "days": 1}]}, "narrator", None)
        latte = next(item for item in db.items() if item["id"] == "latte")
        self.assertEqual((latte["available"], latte["blocked"]), (1, 1))
        self.assertIn("latte: Латте, 240 ₽, 4 мин, нет", menu_block())
        self.assertEqual(next(m for m in snapshot()["menu"] if m["id"] == "latte")["available"], False)
        db.set_run(day=2)
        self.assertEqual(next(item for item in db.items() if item["id"] == "latte")["blocked"], 0)
        self.assertEqual(snapshot()["events"], [])

    def test_blocked_item_is_refused(self):
        engine, llm = fresh()
        llm.script["client"] = {"say": "Латте, пожалуйста", "item_id": "latte", "request": "", "willing_to_wait": True}
        llm.script["staff"] = {"say": "Держите", "action": "serve", "item_id": "latte"}
        engine._open_day()
        engine._apply_event(1, {"headline": "Нет молока", "story": "", "effects": [
            {"type": "item_out", "target": "Латте", "amount": 0, "days": 1}]}, "director", "нет молока")
        run_async(engine._visit(db.next_arrival(1)))
        visit = db.q("SELECT * FROM visits")[0]
        self.assertEqual((visit["status"], visit["price"]), ("refused", 0))

    def test_event_demand_scales_popularity_and_ends(self):
        engine, llm = fresh()
        engine._open_day()
        base = current_popularity()
        engine._apply_event(1, {"headline": "Жара", "story": "", "effects": [
            {"type": "demand", "target": "", "amount": 1.4, "days": 2}]}, "narrator", None)
        self.assertAlmostEqual(current_popularity(), base * 1.4, places=2)
        db.set_run(day=2)
        self.assertAlmostEqual(current_popularity(), base * 1.4, places=2)
        db.set_run(day=3)
        self.assertAlmostEqual(current_popularity(), base, places=2)

    def test_stacked_demand_events_are_clamped_and_district_prompt_has_no_events(self):
        engine, llm = fresh()
        prompts = []
        original = llm.complete

        async def watching(**kwargs):
            prompts.append((kwargs["agent"], kwargs["user"]))
            return await original(**kwargs)

        llm.complete = watching
        engine._open_day()
        base = current_popularity()
        for amount in (1.5, 1.5, 1.5):
            engine._apply_event(1, {"headline": "Ажиотаж", "story": "", "effects": [
                {"type": "demand", "target": "", "amount": amount, "days": 1}]}, "narrator", None)
        self.assertAlmostEqual(current_popularity(), base * 1.8, places=2)
        run_async(engine._district())
        text = next(user for agent, user in prompts if agent == "district")
        self.assertNotIn("Ажиотаж", text)
        self.assertIn("код применяет отдельно", text)

    def test_ending_an_event_returns_its_items_unless_another_blocks_them(self):
        engine, llm = fresh()
        engine._open_day()
        first = engine._apply_event(1, {"headline": "Нет молока", "story": "", "effects": [
            {"type": "item_out", "target": "latte", "amount": 0, "days": 2}, {"type": "demand", "target": "", "amount": 0.6, "days": 2}]}, "narrator", None)
        engine._apply_event(1, {"headline": "Нет сиропа", "story": "", "effects": [
            {"type": "item_out", "target": "latte", "amount": 0, "days": 1}]}, "director", "нет сиропа")
        ids = [row["id"] for row in db.active_events(1)]
        self.assertTrue(engine.end_event(ids[0]))
        latte = next(item for item in db.items() if item["id"] == "latte")
        self.assertEqual(latte["blocked"], 1)
        self.assertEqual([row["headline"] for row in db.active_events(1)], ["Нет сиропа"])
        self.assertAlmostEqual(current_popularity(), popularity_hint(), places=2)
        self.assertTrue(engine.end_event(ids[1]))
        self.assertEqual(next(item for item in db.items() if item["id"] == "latte")["blocked"], 0)
        self.assertFalse(engine.end_event(ids[1]))
        self.assertFalse(engine.end_event(9999))
        self.assertEqual(db.active_events(2), [])

    def test_director_event_ends_with_the_day(self):
        engine, llm = fresh()
        llm.script["director"] = {"headline": "Акция", "story": "", "effects": [{"type": "demand", "target": "", "amount": 1.3, "days": 3}]}
        engine._open_day()
        run_async(engine.direct("акция на всё"))
        self.assertEqual(db.active_events(1)[0]["until_day"], 1)
        self.assertEqual(db.active_events(2), [])

    def test_event_moods_and_prompts(self):
        engine, llm = fresh()
        prompts = []
        original = llm.complete

        async def watching(**kwargs):
            prompts.append((kwargs["agent"], kwargs["user"]))
            return await original(**kwargs)

        llm.complete = watching
        engine._open_day()
        for person in db.staff():
            db.set_staff_mood(person["id"], "спокойствие")
        engine._apply_event(1, {"headline": "Дождь", "story": "Все промокли.", "effects": [
            {"type": "staff_mood", "target": "anya", "amount": -1, "days": 1},
            {"type": "guest_mood", "target": "", "amount": -1, "days": 1}]}, "narrator", None)
        crew = {row["id"]: row["mood"] for row in db.staff()}
        self.assertEqual((crew["anya"], crew["mark"]), ("усталость", "спокойствие"))
        saved = engine_mod.arrival_mood
        engine_mod.arrival_mood = lambda *args, **kwargs: "спокойствие"
        try:
            visit_id = engine._admit(db.next_arrival(1))
        finally:
            engine_mod.arrival_mood = saved
        self.assertEqual(db.visit(visit_id)["mood"], "усталость")
        run_async(engine._serve(visit_id))
        client_prompt = next(text for agent, text in prompts if agent == "client")
        self.assertIn("Сегодня: Дождь. Все промокли.", client_prompt)
        self.assertTrue(log.read(10, ev="event.new"))

    def test_slow_prep_keeps_the_barista_busy(self):
        engine, llm = fresh()
        engine._open_day()
        engine._apply_event(1, {"headline": "Машина барахлит", "story": "", "effects": [
            {"type": "slower_prep", "target": "", "amount": 2.0, "days": 1}]}, "narrator", None)
        db.set_run(status="running", speed=8.0)
        run_async(engine._visit(db.next_arrival(1)))
        visit = db.q("SELECT * FROM visits")[0]
        self.assertGreater(visit["end_min"] - visit["serve_min"], 1.5)
        self.assertTrue(log.read(10, ev="event.slow"))
        self.assertGreaterEqual(engine._live_minutes(), visit["end_min"] - 0.01)

    def test_director_turns_words_into_an_event(self):
        engine, llm = fresh()
        llm.script["director"] = {"headline": "Санинспекция", "story": "Пришла проверка.", "effects": [
            {"type": "guest_mood", "target": "", "amount": -1, "days": 1}]}
        engine._open_day()
        event = run_async(engine.direct("приехала санинспекция"))
        self.assertEqual(event["headline"], "Санинспекция")
        stored = db.active_events(1)[0]
        self.assertEqual((stored["source"], stored["input"]), ("director", "приехала санинспекция"))
        self.assertEqual(llm.calls[-1], "director")
        self.assertEqual(db.run()["phase"], "")

    def test_director_without_model_still_records_the_words(self):
        engine, llm = fresh()
        llm.fail, llm.fail_with = "director", TransportError("нет связи")
        engine._open_day()
        event = run_async(engine.direct("скидка двадцать процентов"))
        self.assertEqual((event["headline"], event["effects"]), ("скидка двадцать процентов", []))
        self.assertEqual(db.run()["status"], "idle")

    def test_director_needs_an_open_day(self):
        engine, llm = fresh()
        with self.assertRaises(ValueError):
            run_async(engine.direct("что-нибудь"))

    def test_day_opening_asks_the_narrator_and_survives_its_failure(self):
        engine, llm = fresh()
        llm.script["narrator"] = {"headline": "Праздник", "story": "В районе ярмарка.", "effects": [
            {"type": "demand", "target": "", "amount": 1.3, "days": 1}]}
        db.set_run(status="running", goal="auto")
        run_async(engine._tick())
        self.assertIn("narrator", llm.calls)
        self.assertEqual(db.active_events(1)[0]["headline"], "Праздник")
        engine2, llm2 = fresh()
        llm2.fail, llm2.fail_with = "narrator", TransportError("нет связи")
        db.set_run(status="running", goal="auto")
        run_async(engine2._tick())
        self.assertEqual(db.run()["status"], "running")
        self.assertEqual(db.active_events(1), [])
        self.assertTrue(log.read(5, ev="event.fail"))

    def test_day_opening_runs_district_and_demographer_before_the_first_arrival(self):
        engine, llm = fresh()
        llm.script["district"] = {"traffic": 1.3, "newcomers": 0.5, "curve": [1, 1, 2, 1, 1, 1], "why": "Праздник.", "buzz": "Хвалят эспрессо."}
        llm.script["demographer"] = {"guests": [
            {"name": "Ася", "trait": "спокоен и не торопит", "patience": 4, "budget": 320, "story": "Ты зашла после работы."},
            {"name": "Борис", "trait": "говорит коротко и спешит", "patience": 2, "budget": 180, "story": "Ты идёшь на поезд."},
        ]}
        db.set_run(status="running", goal="auto")
        run_async(engine._tick())
        self.assertEqual(llm.calls[:3], ["narrator", "district", "demographer"])
        voice = db.district_for(1)
        self.assertEqual((voice["traffic"], voice["newcomers"]), (1.3, 0.5))
        self.assertAlmostEqual(current_popularity(), 1.3, places=2)
        self.assertEqual(db.pool_left(), 2)
        self.assertEqual(len(db.q("SELECT * FROM arrivals WHERE status = 'scheduled'")), 1)
        view = snapshot()
        self.assertEqual(view["district"]["buzz"], "Хвалят эспрессо.")
        self.assertTrue(log.read(5, ev="district.new"))
        self.assertTrue(log.read(5, ev="demographer.new"))

    def test_new_guest_comes_from_the_demographer_pool(self):
        engine, llm = fresh()
        engine._open_day()
        db.reset_pool(1, [{"name": "Ася", "trait": "спокоен и не торопит", "patience": 4, "budget": 320, "story": "Ты зашла после работы."}])
        client = engine._spawn(1)
        self.assertEqual((client["name"], client["trait"], client["budget"]), ("Ася", "спокоен и не торопит", 320))
        self.assertEqual(client["source"], "Ты зашла после работы.")
        self.assertEqual(db.pool_left(), 0)
        fallback = engine._spawn(1)
        self.assertTrue(fallback["name"])

    def test_district_and_demographer_failures_fall_back_to_the_formula(self):
        engine, llm = fresh()
        llm.fail, llm.fail_with = "district", TransportError("нет связи")
        db.set_run(status="running", goal="auto")
        run_async(engine._tick())
        self.assertIsNone(db.district_for(1))
        self.assertAlmostEqual(current_popularity(), popularity_hint(), places=2)
        self.assertEqual(db.run()["status"], "running")
        self.assertTrue(log.read(5, ev="district.fail"))
        self.assertEqual(len(db.q("SELECT * FROM arrivals WHERE status = 'scheduled'")), 1)

    def test_review_is_stored_and_rated(self):
        engine, llm = fresh()
        engine._open_day()
        run_async(engine._visit(db.next_arrival(1)))
        visit = db.q("SELECT * FROM visits")[0]
        self.assertEqual(visit["review"], "Быстро и вкусно.")
        stats = snapshot()["reviews"]
        self.assertEqual((stats["avg"], stats["count"]), (5.0, 1))
        self.assertEqual(stats["latest"][0]["review"], "Быстро и вкусно.")

    def test_guests_queue_and_the_first_is_served(self):
        engine, llm = fresh()
        self._crowd(engine, (482, 483, 484))
        self.assertEqual(run_async(engine._tick()), "ok")
        rows = db.q("SELECT id, status, start_min FROM visits ORDER BY id")
        self.assertEqual([row["status"] for row in rows], ["served", "waiting", "waiting"])
        self.assertEqual([row["start_min"] for row in rows], [482.0, 483.0, 484.0])
        self.assertEqual(len(db.waiting(1)), 2)
        self.assertEqual(db.q("SELECT status FROM arrivals WHERE minute = 482")[0]["status"], "done")
        served = db.visit(rows[0]["id"])
        self.assertGreater(served["wait_min"], 15)
        self.assertEqual(served["serve_min"], served["serve_min"])
        self.assertGreaterEqual(served["serve_min"], 500.0)

    def test_waiting_guest_leaves_when_the_model_says_so(self):
        engine, llm = fresh()
        llm.script["queue"] = {"stay": False, "say": "Пойду в другое место."}
        self._crowd(engine, (482, 483))
        run_async(engine._tick())
        rows = db.q("SELECT * FROM visits ORDER BY id")
        self.assertEqual([row["status"] for row in rows], ["served", "left"])
        gone = db.visit(rows[1]["id"])
        self.assertEqual((gone["rating"], gone["stay_min"], gone["outcome_note"]), (1, 0, "Не дождался очереди"))
        self.assertGreater(gone["end_min"], 0)
        actions = [row["action"] for row in gone["lines"]]
        self.assertEqual(actions[0], "left")
        self.assertIn("verdict", actions)
        self.assertEqual(db.q("SELECT memory FROM clients WHERE id = ?", (gone["client_id"],))[0]["memory"],
                         "В прошлый раз не дождался очереди и ушёл, оценка 1.")
        self.assertEqual(db.run()["day_done"], 2)
        self.assertTrue(log.read(10, ev="visit.left"))

    def test_waiting_guest_who_stays_is_asked_again_later(self):
        engine, llm = fresh()
        self._crowd(engine, (482, 483))
        run_async(engine._tick())
        waiting_row = db.q("SELECT * FROM visits ORDER BY id")[1]
        self.assertEqual(waiting_row["status"], "waiting")
        self.assertGreater(waiting_row["next_check"], 500.0 - 1)
        self.assertEqual([row["action"] for row in db.visit_lines(waiting_row["id"])], ["queue"])
        self.assertEqual(llm.calls.count("queue"), 1)

    def test_queue_lines_do_not_leak_into_the_dialog_prompt(self):
        engine, llm = fresh()
        prompts = []
        original = llm.complete

        async def watching(**kwargs):
            prompts.append((kwargs["agent"], kwargs["visit_id"], kwargs["user"]))
            return await original(**kwargs)

        llm.complete = watching
        self._crowd(engine, (482, 483))
        run_async(engine._tick())
        run_async(engine._tick())
        second = db.q("SELECT id FROM visits ORDER BY id")[1]["id"]
        client_prompt = next(text for agent, vid, text in prompts if agent == "client" and vid == second)
        self.assertNotIn("Подожду", client_prompt)
        self.assertIn("Скажи бариста, что берёшь сегодня", client_prompt)

    def test_day_does_not_close_while_someone_waits(self):
        engine, llm = fresh()
        self._crowd(engine, (1190,))
        db.set_run(clock_min=1205.0, clock_real=0)
        self.assertNotEqual(run_async(engine._tick()), "day_complete")
        self.assertEqual(db.waiting(1), [])
        self.assertEqual(run_async(engine._tick()), "day_complete")

    def test_queue_transport_error_pauses(self):
        engine, llm = fresh()
        llm.fail, llm.fail_with = "queue", TransportError("нет связи")
        self._crowd(engine, (482, 483))
        self.assertEqual(run_async(engine._tick()), "transport")
        self.assertEqual(db.run()["status"], "error")
        self.assertEqual(db.q("SELECT status FROM visits ORDER BY id")[1]["status"], "waiting")

    def test_verdict_that_repeats_the_guest_is_blanked(self):
        engine, llm = fresh()
        llm.script["verdict"] = {"say": "Эспрессо, пожалуйста", "liked": 4, "return": "yes", "return_in_days": 2, "recommend": False}
        engine._open_day()
        run_async(engine._visit(db.next_arrival(1)))
        visit = db.q("SELECT * FROM visits")[0]
        self.assertEqual(visit["verdict"], "")
        self.assertEqual(visit["liked"], 4)
        self.assertNotIn("verdict", [row["action"] for row in db.visit_lines(visit["id"])])
        self.assertTrue(log.read(10, ev="verdict.echo"))

    def test_bad_verdict_falls_back_to_rating(self):
        engine, llm = fresh()
        llm.script["verdict"] = {"say": "?", "liked": 4}
        engine._open_day()

        async def broken(**kwargs):
            llm.calls.append(kwargs["agent"])
            if kwargs["agent"] == "verdict":
                raise SchemaError("Нет полей", "")
            return {"say": "Эспрессо", "item_id": "espresso", "request": "", "willing_to_wait": True} if kwargs["agent"] == "client" \
                else {"say": "Держи", "action": "serve", "item_id": "espresso"}

        llm.complete = broken
        self.assertEqual(run_async(engine._visit(db.next_arrival(1))), "ok")
        visit = db.q("SELECT * FROM visits")[0]
        self.assertEqual((visit["liked"], visit["intent"]), (5, "yes"))
        self.assertTrue(log.read(10, ev="visit.verdict")[-1]["fallback"])

    def test_verdict_transport_error_pauses_but_keeps_visit(self):
        engine, llm = fresh()
        llm.fail, llm.fail_with = "verdict", TransportError("нет связи")
        engine._open_day()
        self.assertEqual(run_async(engine._visit(db.next_arrival(1))), "transport")
        self.assertEqual(db.q("SELECT status FROM visits")[0]["status"], "served")
        self.assertEqual(db.run()["status"], "error")

    def test_arrivals_are_a_stream_not_a_schedule(self):
        engine, _ = fresh()
        engine._open_day()
        self.assertEqual(len(db.q("SELECT * FROM arrivals WHERE status = 'scheduled'")), 1)
        run_async(engine._visit(db.next_arrival(1)))
        run_async(engine._visit(db.next_arrival(1)))
        pending = db.q("SELECT * FROM arrivals WHERE status = 'scheduled'")
        self.assertEqual(len(pending), 1)
        self.assertEqual(db.run()["day_target"], 0)
        self.assertGreater(len(log.read(30, ev="arrival.plan")), 2)

    def test_friend_referral_is_spent_on_a_new_guest(self):
        engine, _ = fresh()
        engine._open_day()
        run_async(engine._visit(db.next_arrival(1)))
        self.assertEqual(db.referral_pool(), 1)
        engine.rng.random = lambda: 0.0
        newcomer = engine._spawn(1)
        self.assertIn("знакомый", newcomer["source"])
        self.assertEqual(db.referral_pool(), 0)

    def test_closing_question_is_replaced_by_statement(self):
        engine, llm = fresh()
        llm.script["client"] = {"say": "Не знаю, булочку или эспрессо?", "item_id": "", "request": "", "willing_to_wait": True}
        llm.script["staff"] = {"say": "Что выберешь: булочку или эспрессо?", "action": "ask", "item_id": ""}
        engine._open_day()
        seq = iter([
            {"say": "Не знаю, булочку или эспрессо?", "item_id": "", "request": "", "willing_to_wait": True},
            {"say": "Что выберешь: булочку или эспрессо?", "action": "ask", "item_id": ""},
            {"say": "Что выберешь: булочку или эспрессо?", "item_id": "bun", "request": "", "willing_to_wait": True},
            {"say": "Берёшь булочку или эспрессо?", "action": "serve", "item_id": "bun"},
            {"say": "Булочка вышла неплохо.", "liked": 4, "return": "maybe", "return_in_days": 3, "recommend": False},
            {"score": 5, "issues": []},
        ])

        async def scripted(**kwargs):
            llm.calls.append(kwargs["agent"])
            return next(seq)

        llm.complete = scripted
        self.assertEqual(run_async(engine._visit(db.next_arrival(1))), "ok")
        lines = db.q("SELECT role, text FROM lines ORDER BY id")
        self.assertEqual(lines[2]["text"], "Решил. Беру: Булочка.")
        self.assertEqual(lines[3]["text"], "Хорошо, сейчас будет: Булочка.")
        self.assertNotIn("?", lines[3]["text"])

    def test_unavailable_item_is_refused_without_check(self):
        engine, _ = fresh()
        db.save_item("espresso", 150, 0)
        engine._open_day()
        run_async(engine._visit(db.next_arrival(1)))
        visit = db.q("SELECT * FROM visits")[0]
        self.assertEqual(visit["status"], "refused")
        self.assertEqual(visit["price"], 0)

    def test_ask_costs_a_point(self):
        engine, llm = fresh()
        replies = iter([
            {"say": "Что именно?", "action": "ask", "item_id": ""},
            {"say": "Держите", "action": "serve", "item_id": "espresso"},
        ])

        original = llm.complete

        async def staged(**kw):
            if kw["agent"] == "staff":
                llm.calls.append("staff")
                return next(replies)
            return await original(**kw)

        llm.complete = staged
        engine._spawn = lambda day: db.insert_client("Тест", "спокоен", 4, 250, day)
        engine._open_day()
        run_async(engine._visit(db.next_arrival(1)))
        visit = db.q("SELECT * FROM visits")[0]
        self.assertEqual(visit["rating"], 4)
        self.assertEqual(visit["asks"], 1)

    def test_bad_item_id_is_dropped_before_staff(self):
        engine, llm = fresh()
        prompts = []

        async def staged(**kw):
            prompts.append(kw["user"])
            if kw["agent"] == "client":
                return {
                    "say": "Хочу капучино",
                    "item_id": 'willing_to_wait": true',
                    "request": "",
                    "willing_to_wait": True,
                }
            return {"say": "Капучино, четыре минуты", "action": "serve", "item_id": "cappuccino"}

        llm.complete = staged
        engine._open_day()
        self.assertEqual(run_async(engine._visit(db.next_arrival(1))), "ok")
        self.assertNotIn("willing_to_wait", prompts[1])
        self.assertIn("В поле заказа позиции нет.", prompts[1])
        self.assertIn("Хочу капучино", prompts[1])
        visit = db.q("SELECT * FROM visits")[0]
        self.assertIsNone(visit["requested_item_id"])
        self.assertEqual(visit["served_item_id"], "cappuccino")
        memory = db.clients()[0]["memory"]
        self.assertNotIn("«", memory)
        self.assertNotIn("Хочу капучино", memory)
        self.assertIn("Капучино", memory)

    def test_followup_keeps_this_visit_only(self):
        engine, llm = fresh()
        prompts = []
        staff = iter([
            {"say": "Капучино четыре минуты, успеете?", "action": "ask", "item_id": "cappuccino"},
            {"say": "Тогда капучино, 220 рублей", "action": "serve", "item_id": "cappuccino"},
        ])

        async def staged(**kw):
            prompts.append((kw["agent"], kw["user"]))
            if kw["agent"] == "staff":
                return next(staff)
            if not any(agent == "client" for agent, _ in prompts[:-1]):
                return {"say": "Хочу капучино", "item_id": "cappuccino", "request": "", "willing_to_wait": False}
            return {"say": "Да, подожду", "item_id": "cappuccino", "request": "", "willing_to_wait": True}

        llm.complete = staged
        engine._open_day()
        run_async(engine._visit(db.next_arrival(1)))
        follow = next(text for agent, text in prompts if agent == "client" and "Этот же разговор" in text)
        final = next(text for agent, text in prompts if "Уточнение уже было" in text)
        self.assertNotIn("Скажи бариста", follow)
        self.assertIn("Капучино четыре минуты", follow)
        self.assertIn("Хочу капучино", final)
        self.assertIn("Капучино четыре минуты", final)
        self.assertIn("Да, подожду", final)
        self.assertNotIn("Память прошлого визита", final)

    def test_old_quote_is_stripped_from_prompt(self):
        from app.engine import menu_block, plain_memory

        old = "Капучино, обслужен, оценка 4. «Привет, покажите оба, если получится.»"
        self.assertEqual(plain_memory(old), "В прошлый раз брал Капучино, обслужили, оценка 4.")
        engine, _ = fresh()
        engine._open_day()
        client = db.insert_client("Катя", "сомневается между двумя позициями", 5, 180, 1)
        db.execute("UPDATE clients SET memory = ? WHERE id = ?", (old, client["id"]))
        client = db.one("SELECT * FROM clients WHERE id = ?", (client["id"],))
        vid = db.insert_visit(
            day=1, seq=0, clock="08:10", client_id=client["id"], staff_id="anya", status="open",
            is_return=1, requested_item_id=None, requested_text="", served_item_id=None, price=0,
            rating=None, asks=0, memory_before=old, memory_phrase="", outcome_note="",
        )
        text = engine._client_prompt(client, menu_block(), vid)
        self.assertNotIn("«", text)
        self.assertNotIn("покажите оба", text)
        self.assertIn("Назови две позиции", text)
        self.assertIn("вслух не называй", text)
        person = next(row for row in db.staff() if row["id"] == "anya")
        guest = {"say": "фильтр или капучино?", "item_id": "", "request": "что взять", "willing_to_wait": True}
        staff = engine._staff_prompt(person, client, menu_block(), guest, False, vid)
        self.assertNotIn("«", staff)
        self.assertIn("один вопрос, ask", staff)
        self.assertNotIn("бюджет", staff)
        self.assertIn("без цены", staff)
        other = engine._spawn(1)
        db.execute("UPDATE clients SET memory = ? WHERE id = ?", (old, other["id"]))
        engine.recover()
        self.assertEqual(db.one("SELECT memory FROM clients WHERE id = ?", (other["id"],))["memory"], plain_memory(old))
        self.assertEqual(db.visit(vid)["status"], "failed")

    def test_return_prompt_has_fact_not_old_line(self):
        import app.engine as engine_mod

        engine, _ = fresh()
        prompts = []
        original = engine.llm.complete

        async def staged(**kw):
            prompts.append(kw["user"])
            return await original(**kw)

        engine.llm.complete = staged
        engine._open_day()
        run_async(engine._visit(db.next_arrival(1)))
        saved = engine_mod.choose_arrival
        engine_mod.choose_arrival = lambda *args, **kwargs: db.clients()[0]
        try:
            run_async(engine._visit(db.next_arrival(1)))
        finally:
            engine_mod.choose_arrival = saved
        opening = next(text for text in prompts if text.startswith("Меню:") and "Это уже было" in text)
        self.assertIn("В прошлый раз брал Эспрессо", opening)
        self.assertNotIn("Эспрессо, пожалуйста", opening)

    def test_transport_error_fails_visit_and_stops(self):
        engine, llm = fresh()
        llm.fail, llm.fail_with = "client", TransportError("нет связи")
        engine._open_day()
        self.assertEqual(run_async(engine._visit(db.next_arrival(1))), "transport")
        failed = db.q("SELECT status, end_min, stay_min FROM visits")[0]
        self.assertEqual(failed["status"], "failed")
        self.assertIsNotNone(failed["end_min"])
        self.assertEqual(failed["stay_min"], 0)
        self.assertEqual(db.run()["status"], "error")

    def test_schema_error_closes_visit_and_day_goes_on(self):
        engine, llm = fresh()
        llm.fail, llm.fail_with = "staff", SchemaError("Ответ не JSON", "")
        engine._open_day()
        self.assertEqual(run_async(engine._visit(db.next_arrival(1))), "schema")
        self.assertEqual(db.run()["status"], "idle")
        self.assertEqual(db.run()["day_done"], 1)

    def test_step_with_no_arrivals_jumps_to_close(self):
        engine, _ = fresh()
        engine._open_day()
        db.execute("UPDATE arrivals SET status = 'done'")
        db.set_run(goal="step", status="running")
        self.assertEqual(run_async(engine._tick()), "day_complete")
        self.assertEqual(db.run()["day_closed"], 1)

    def test_manager_after_day_five(self):
        engine, llm = fresh()
        llm.script["manager"] = {
            "say": "Дорого",
            "changes": [{"op": "set_price", "item_id": "latte", "price": 230, "available": True}] * 3,
        }
        db.set_run(day=5, day_closed=0)
        self.assertEqual(run_async(engine._close_day()), "day_complete")
        week = db.weeks()[0]
        self.assertEqual(week["through_day"], 5)
        latte = next(i for i in db.items() if i["id"] == "latte")
        self.assertEqual(latte["price"], 230)

    def test_manager_adds_item_and_menu_shows_it(self):
        engine, llm = fresh()
        llm.script["manager"] = {
            "say": "Просят раф",
            "changes": [
                {"op": "add_item", "item_id": "", "name": "Раф", "price": 260, "minutes": 5, "available": True},
                {"op": "set_available", "item_id": "cocoa", "name": "", "price": 0, "minutes": 0, "available": False},
            ],
        }
        db.set_run(day=5, day_closed=0)
        self.assertEqual(run_async(engine._close_day()), "day_complete")
        added = next(i for i in db.items() if i["name"] == "Раф")
        self.assertEqual((added["price"], added["minutes"], added["available"]), (260, 5, 1))
        self.assertIn("Раф, 260 ₽, 5 мин, есть", menu_block())
        self.assertEqual(next(i for i in db.items() if i["id"] == "cocoa")["available"], 0)
        ops = [change["op"] for change in json.loads(db.weeks()[0]["changes_json"])]
        self.assertEqual(ops, ["add_item", "set_available"])
        self.assertIn("wishes", json.loads(db.weeks()[0]["summary_json"]))

    def test_recover_closes_orphan_visit(self):
        engine, _ = fresh()
        engine._open_day()
        arrival = db.next_arrival(1)
        client = engine._spawn(1)
        vid = db.insert_visit(
            day=1, seq=0, clock="08:10", client_id=client["id"], staff_id="anya", status="open",
            is_return=0, requested_item_id=None, requested_text="", served_item_id=None, price=0,
            rating=None, asks=0, memory_before="", memory_phrase="", outcome_note="",
        )
        db.set_arrival(arrival["id"], status="serving", visit_id=vid)
        engine.recover()
        self.assertEqual(db.visit(vid)["status"], "failed")
        self.assertEqual(db.q("SELECT status FROM arrivals WHERE id = ?", (arrival["id"],))[0]["status"], "done")

    def test_snapshot_shape(self):
        engine, _ = fresh()
        engine._open_day()
        run_async(engine._visit(db.next_arrival(1)))
        data = snapshot()
        self.assertEqual(data["summary"]["all"]["served"], 1)
        self.assertEqual(len(data["journal"]), 1)
        today = data["day_visits"][0]
        self.assertIn("client_id", today)
        self.assertLessEqual(today["start_min"], today["end_min"])
        self.assertTrue(data["llm_calls"] == [] or isinstance(data["llm_calls"], list))


class StaleConnectionTest(unittest.TestCase):
    def test_post_retries_once_on_dropped_keepalive(self):
        import httpx

        from app.llm import LLM

        async def go():
            llm = LLM()
            attempts = []

            async def flaky(url, json=None, timeout=None, **kwargs):
                attempts.append(1)
                if len(attempts) == 1:
                    raise httpx.RemoteProtocolError("Server disconnected")
                return "ok"

            llm.client.post = flaky
            result = await llm._post("http://x", {}, 5)
            await llm.aclose()
            return result, len(attempts)

        self.assertEqual(run_async(go()), ("ok", 2))


if __name__ == "__main__":
    unittest.main()
