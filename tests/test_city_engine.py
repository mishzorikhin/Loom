"""Город и движок вместе: приход гостя по улицам, заведение закрыто, ведущий мира, решения толпы."""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

_TMP = Path(tempfile.mkdtemp())
os.environ["SIM_DB"] = str(_TMP / "sim.db")
os.environ["SIM_LOG"] = str(_TMP / "simcheck.log")
os.environ["SIM_LOG_STDOUT"] = "0"

import app.db as db  # noqa: E402
from app import city as C  # noqa: E402
from app.engine import Engine  # noqa: E402
from app.mind import Mind, patch_ops  # noqa: E402
from app.view import set_city, snapshot  # noqa: E402


class ScriptLLM:
    """Модель-заглушка: гость берёт эспрессо, бариста отдаёт; ведущий и толпа отвечают по сценарию теста."""

    def __init__(self):
        self.script = {}
        self.seen = []

    async def complete(self, *, agent, schema_key, system, user, visit_id, week_day, final_staff=False, echo_of="", target=""):
        self.seen.append((agent, user))
        if agent in self.script:
            return self.script[agent]
        if agent in ("narrator", "director"):
            return {"headline": "Событие", "story": "Что-то случилось.", "effects": []}
        if agent == "world":
            return {"say": "", "changes": [], "proposals": []}
        if agent == "district":
            return {"traffic": 1.0, "newcomers": 0.3, "curve": [1] * 6, "why": "", "buzz": ""}
        if agent == "demographer":
            return {"guests": []}
        if agent == "critic":
            return {"score": 5, "issues": []}
        if agent == "queue":
            return {"stay": True, "say": "Подожду."}
        if agent == "verdict":
            return {"say": "Нормально.", "liked": 4, "return": "yes", "return_in_days": 2, "recommend": False, "review": "Быстро."}
        if agent == "client":
            return {"say": "Эспрессо", "item_id": "espresso", "request": "", "willing_to_wait": True}
        if agent == "staff":
            return {"say": "Держите", "action": "serve", "item_id": "espresso", "mood": "бодрость"}
        if agent == "adjudicator":
            return {"say": "Ничего", "ops": []}
        if agent == "crowd":
            return {"people": []}
        return {"say": "Ровно", "changes": []}


def make():
    db.connect(Path(os.environ["SIM_DB"]))
    db.reset_world()
    llm = ScriptLLM()
    city = C.City(seed=1)
    city.set_places(db.places())
    city.populate(6)
    set_city(city)
    engine = Engine(llm, lambda payload: None, city)
    engine.mind = Mind(engine)
    return engine, llm, city


def run(coro):
    return asyncio.run(coro)


def walk(city, minutes, day=1):
    end = city.t + minutes
    city.advance(day, end - day * 1440)


class CityEngineTest(unittest.TestCase):
    def test_reset_cancels_pending_world_answer(self):
        async def go():
            engine, llm, city = make()
            started = asyncio.Event()
            cancelled = asyncio.Event()
            async def pending():
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            engine.mind._spawn(pending())
            await started.wait()
            engine.mind.watch.append({"old": True})
            engine.mind.cache[(1,)] = (10, {})
            await engine.reset()
            self.assertTrue(cancelled.is_set())
            self.assertFalse(engine.mind.tasks)
            self.assertFalse(engine.mind.watch)
            self.assertFalse(engine.mind.cache)
        run(go())

    def test_crowd_thinking_and_changed_hazard_trigger_new_decision(self):
        async def go():
            engine, llm, city = make()
            ped = next(iter(city.peds.values()))
            hazard = [0]
            city.percept = lambda p, alerts: {"time": "12:00", "trait": p.trait,
                                             "near": [{"kind": "cloud", "hazard": hazard[0]}], "facts": []}
            calls = []
            async def complete(**kwargs):
                calls.append(db.run()["thinking"])
                return {"people": [{"id": ped.id, "do": "continue", "say": "", "mood": "спокойствие", "minutes": 1}]}
            llm.complete = complete
            await engine.mind._decide([{"ped": ped, "alerts": []}])
            await engine.mind._decide([{"ped": ped, "alerts": []}])
            hazard[0] = 1
            await engine.mind._decide([{"ped": ped, "alerts": []}])
            self.assertEqual(calls, [1, 1])
            self.assertEqual(db.run()["thinking"], 0)
        run(go())

    def test_arrival_happens_at_the_door_not_at_the_planned_minute(self):
        engine, llm, city = make()
        engine._open_day()
        city.advance(1, 480.0)
        arrival = db.next_arrival(1)
        db.execute("UPDATE arrivals SET minute = 490 WHERE id = ?", (arrival["id"],))
        db.set_run(clock_min=490.0, clock_real=0)
        engine._come(db.next_arrival(1))
        self.assertEqual(db.q("SELECT COUNT(*) AS n FROM visits")[0]["n"], 0, "визита нет, пока человек идёт")
        self.assertEqual(len(engine._trips), 1)
        walk(city, 60)
        engine.pump_city()
        visits = db.q("SELECT * FROM visits")
        self.assertEqual(len(visits), 1)
        self.assertGreater(visits[0]["start_min"], 490.0)  # дорога заняла время
        self.assertIn(visits[0]["side"], (0, 1))
        self.assertEqual(visits[0]["status"], "waiting")
        self.assertEqual(engine._trips, {})

    def test_served_guest_leaves_the_shop_and_returns_to_the_street(self):
        engine, llm, city = make()
        engine._open_day()
        city.advance(1, 500.0)
        db.set_run(clock_min=500.0, clock_real=0)
        client = db.insert_client("Гость", "спокоен и не торопит", 3, 300, 1)
        city.dispatch(client["id"], "Гость", "cafe", "walk", home="h2")
        engine._trips[client["id"]] = {"known": False, "arrival": None, "place": "cafe", "minute": 500}
        walk(city, 90)
        engine.pump_city()
        visit = db.q("SELECT * FROM visits")[0]
        run(engine._serve(visit["id"]))
        done = db.visit(visit["id"])
        self.assertEqual(done["status"], "served")
        self.assertEqual(len(engine._leaving), 1)
        walk(city, 120)
        engine.pump_city()
        self.assertEqual(engine._leaving, [])
        guest = next((p for p in city.peds.values() if p.client_id == client["id"]), None)
        self.assertTrue(guest is None or guest.state != "inside")

    def test_closed_place_turns_people_away(self):
        engine, llm, city = make()
        engine._open_day()
        city.advance(1, 500.0)
        city.apply_patch([{"op": "place", "id": "cafe", "status": "closed", "x": 0, "y": 0}])
        arrival = db.next_arrival(1)
        db.execute("UPDATE arrivals SET minute = 500 WHERE id = ?", (arrival["id"],))
        db.set_run(clock_min=500.0, clock_real=0)
        engine._come(db.next_arrival(1))
        self.assertEqual(engine._trips, {})
        self.assertFalse([p for p in city.peds.values() if p.client_id])

    def test_two_arrivals_never_pick_the_same_person(self):
        engine, llm, city = make()
        engine._open_day()
        city.advance(1, 500.0)
        db.set_run(clock_min=500.0, clock_real=0)
        for n in range(3):
            db.add_arrivals(1, [500 + n])
        for _ in range(3):
            engine._come(db.due_arrival(1, 600))
        clients = list(engine._trips)
        self.assertEqual(len(clients), 3)
        self.assertEqual(len(clients), len(set(clients)))

    def test_director_event_becomes_a_world_patch_and_people_react_through_the_model(self):
        engine, llm, city = make()
        engine._open_day()
        city.advance(1, 600.0)
        db.set_run(clock_min=600.0, clock_real=0)
        llm.script["adjudicator"] = {"say": "Упало что-то тяжёлое", "ops": [
            {"op": "spawn", "id": "", "kind": "воронка", "x": 16.6, "y": -9.5, "r": 2.0, "blocks": True, "hazard": 0.6, "minutes": 120,
             "effect": "", "amount": 0, "text": "", "status": "", "label": "воронка", "shape": "ring", "color": "#6b4a2f", "size": 1.0}]}
        ped = city._new_ped("Свидетель")
        ped.x, ped.y, ped.prev = 16.6, -6.0, (16.6, -2.5)
        ped.goal = {"kind": "stroll", "to": (16.6, 4.25), "linger": 0.0}
        city._plan_route(ped)
        event = run(engine.direct("Что-то упало с неба у восточного тротуара"))
        self.assertIsNotNone(event)
        self.assertEqual(len(city.ents), 1)
        ent = next(iter(city.ents.values()))
        self.assertEqual((ent.kind, ent.blocks), ("воронка", True))
        self.assertIn("adjudicator", [agent for agent, _ in llm.seen])
        walk(city, 3)
        batch = city.drain_alerts()
        self.assertTrue(batch, "человек заметил новый объект")
        city.advance(1, 604.0)
        self.assertTrue(any(row["alerts"] for row in batch))

        llm.script["crowd"] = {"people": [{"id": ped.id, "do": "watch", "say": "Ого!", "mood": "тревога", "minutes": 3}]}
        for row in batch:
            row["ped"].alerts = row["alerts"]

        async def decide():
            engine.mind.last = 0.0
            engine.mind.poll()
            await asyncio.gather(*list(engine.mind.tasks))

        run(decide())
        self.assertIn("crowd", [agent for agent, _ in llm.seen])
        self.assertEqual(ped.said, "Ого!")
        self.assertEqual(ped.mood, "тревога")

    def test_failed_adjudicator_leaves_the_world_alone(self):
        engine, llm, city = make()
        engine._open_day()

        async def broken(**kwargs):
            if kwargs["agent"] == "adjudicator":
                from app.llm import TransportError
                raise TransportError("нет связи")
            return await ScriptLLM.complete(llm, **kwargs)

        llm.complete = broken
        applied = run(engine.mind.adjudicate("метеорит", "Метеорит", ""))
        self.assertEqual(applied, [])
        self.assertEqual(city.ents, {})
        self.assertEqual(db.run()["phase"], "")

    def test_patch_ops_flattens_the_model_answer(self):
        ops = patch_ops([{"op": "spawn", "id": "", "kind": "x", "x": 1, "y": 2, "r": 1, "blocks": False, "hazard": 0, "minutes": 5,
                          "effect": "", "amount": 0, "text": "!", "status": "", "label": "", "shape": "star", "color": "#112233", "size": 2},
                         {"op": "remove", "id": "7", "kind": "", "x": 0, "y": 0, "r": 0}])
        self.assertEqual(ops[0]["glyph"], {"shape": "star", "color": "#112233", "size": 2, "text": "!"})
        self.assertEqual(ops[1]["id"], 7)

    def test_snapshot_carries_the_city_and_places_follow_its_status(self):
        engine, llm, city = make()
        db.set_run(day=1, clock_min=600.0, clock_real=0, status="paused")
        snap = snapshot()
        self.assertIn("frame", snap["city"])
        self.assertIn("roster", snap["city"])
        self.assertTrue({p["id"]: p for p in snap["places"]}["cafe"]["open"])
        city.apply_patch([{"op": "place", "id": "cafe", "status": "closed", "x": 0, "y": 0}])
        self.assertFalse({p["id"]: p for p in snapshot()["places"]}["cafe"]["open"])

    def test_without_a_city_the_engine_works_as_before(self):
        db.connect(Path(os.environ["SIM_DB"]))
        db.reset_world()
        set_city(None)
        engine = Engine(ScriptLLM(), lambda payload: None)
        engine._open_day()
        arrival = db.next_arrival(1)
        db.execute("UPDATE arrivals SET minute = 500 WHERE id = ?", (arrival["id"],))
        db.set_run(clock_min=500.0, clock_real=0)
        engine._come(db.next_arrival(1))
        self.assertEqual(db.q("SELECT COUNT(*) AS n FROM visits")[0]["n"], 1)
        self.assertIsNone(snapshot()["city"])


if __name__ == "__main__":
    unittest.main()
