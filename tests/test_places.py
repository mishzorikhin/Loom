"""Заведения квартала: кофейня и ЦОД NeuralDeep работают на одном каркасе, данные не смешиваются."""

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
from app.engine import Engine, menu_block, venue_ids  # noqa: E402
from app.rules import gpu_status, gpu_utilization  # noqa: E402
from app.venues import DC_CAPACITY  # noqa: E402
from app.view import snapshot  # noqa: E402


class RecordingLLM:
    """Модель-заглушка: запоминает промпты и отвечает по ролям. Клиент ЦОДа просит пакет токенов."""

    def __init__(self, item="qwen_pack"):
        self.item = item
        self.seen: list[tuple[str, str, str]] = []

    async def complete(self, *, agent, schema_key, system, user, visit_id, week_day, final_staff=False, echo_of="", target=""):
        self.seen.append((agent, system, user))
        if agent in ("narrator", "director"):
            return {"headline": "", "story": "", "effects": []}
        if agent == "district":
            return {"traffic": 1.0, "newcomers": 0.3, "curve": [1] * 6, "why": "", "buzz": ""}
        if agent == "demographer":
            return {"guests": []}
        if agent == "world":
            return {"say": "", "changes": [], "proposals": []}
        if agent == "critic":
            return {"score": 5, "issues": []}
        if agent == "queue":
            return {"stay": True, "say": "Подожду."}
        if agent == "verdict":
            return {"say": "Всё понятно.", "liked": 5, "return": "yes", "return_in_days": 2, "recommend": True,
                    "review": "Быстро выдали ключ."}
        if agent == "client":
            return {"say": "Мне пакет токенов, пожалуйста", "item_id": self.item, "request": "", "willing_to_wait": True}
        if agent == "staff":
            return {"say": "Оформляю.", "action": "serve", "item_id": self.item, "mood": "бодрость"}
        return {"say": "Ровно", "changes": []}


def fresh(item="qwen_pack"):
    db.connect(Path(os.environ["SIM_DB"]))
    db.reset_world()
    llm = RecordingLLM(item)
    return Engine(llm, lambda payload: None), llm


def run(coro):
    return asyncio.run(coro)


def visit_in_dc(engine):
    """Один клиент приходит в ЦОД и обслуживается."""
    with db.at_place("neuraldeep"):
        arrival = db.next_arrival(1)
        db.execute("UPDATE arrivals SET minute = 100 WHERE id = ?", (arrival["id"],))
        db.set_run(clock_min=130.0, clock_real=0)
        visit_id = engine._admit(db.next_arrival(1))
        run(engine._serve(visit_id))
        return visit_id


class PlacesTest(unittest.TestCase):
    def test_places_are_seeded_and_cafe_data_stays_the_same(self):
        fresh()
        ids = [row["id"] for row in db.places()]
        self.assertEqual(ids[0], "cafe")
        self.assertEqual(set(ids), {"cafe", "neuraldeep"})
        self.assertEqual(len(db.items()), 6)
        self.assertEqual({row["id"] for row in db.staff()}, {"anya", "mark"})
        with db.at_place("neuraldeep"):
            self.assertEqual({row["id"] for row in db.staff()}, {"valera", "pasha"})
            self.assertIn("qwen_unlim", {row["id"] for row in db.items()})
            self.assertNotIn("espresso", {row["id"] for row in db.items()})
        self.assertEqual(venue_ids(), ["cafe", "neuraldeep"])

    def test_datacenter_prices_follow_the_public_price_list(self):
        fresh()
        with db.at_place("neuraldeep"):
            prices = {row["id"]: row["price"] for row in db.items()}
        self.assertEqual(prices["qwen_unlim"], 512)
        self.assertEqual(prices["qwen_unlim_xl"], 1024)

    def test_day_opening_plans_an_arrival_for_each_place(self):
        engine, _ = fresh()
        engine._open_day()
        for place_id in ("cafe", "neuraldeep"):
            with db.at_place(place_id):
                self.assertEqual(len(db.q("SELECT * FROM arrivals WHERE status = 'scheduled' AND place_id = ?", (place_id,))), 1)

    def test_a_place_added_to_an_open_day_gets_its_first_arrival(self):
        engine, _ = fresh()
        engine._open_day()
        db.execute("DELETE FROM arrivals WHERE place_id = 'neuraldeep'")
        db.set_run(clock_min=600.0, clock_real=0, status="paused")
        with db.at_place("neuraldeep"):
            run(engine._tick_place(1, 600.0))
            self.assertEqual(len(db.q("SELECT * FROM arrivals WHERE place_id = 'neuraldeep' AND status = 'scheduled'")), 1)
            run(engine._tick_place(1, 601.0))
            self.assertEqual(len(db.q("SELECT * FROM arrivals WHERE place_id = 'neuraldeep'")), 1)  # второй раз не разыгрывается

    def test_datacenter_visit_is_recorded_in_its_place_only(self):
        engine, llm = fresh()
        engine._open_day()
        visit_id = visit_in_dc(engine)
        visit = db.visit(visit_id)
        self.assertEqual(visit["place_id"], "neuraldeep")
        self.assertEqual(visit["status"], "served")
        self.assertEqual(visit["price"], 180)
        self.assertEqual(visit["stay_min"], 0)  # клиент ЦОДа не засиживается
        self.assertEqual(db.q("SELECT COUNT(*) AS n FROM visits WHERE place_id = 'cafe'")[0]["n"], 0)
        self.assertEqual(snapshot()["summary"]["all"]["visits"], 0)  # кофейня об этом визите не знает
        with db.at_place("neuraldeep"):
            self.assertEqual(db.review_stats()["count"], 1)
            client = db.one("SELECT * FROM clients WHERE id = ?", (visit["client_id"],))
        self.assertEqual(client["place_id"], "neuraldeep")
        self.assertEqual(db.clients(), [])

    def test_datacenter_roles_speak_in_its_own_words(self):
        engine, llm = fresh()
        engine._open_day()
        visit_in_dc(engine)
        by_agent = {agent: (system, user) for agent, system, user in llm.seen}
        self.assertIn("NeuralDeep", by_agent["client"][0])
        self.assertIn("Прайс:", by_agent["client"][1])
        self.assertIn("api.neuraldeep.ru/v1", by_agent["staff"][0])
        self.assertIn("Нагрузка на GPU", by_agent["staff"][1])
        self.assertIn("Инженер", by_agent["verdict"][1])
        self.assertNotIn("бариста", by_agent["client"][1].casefold())
        self.assertIn("10 млн токенов Qwen 3.6", by_agent["client"][1])
        self.assertNotIn("qwen_pack", by_agent["client"][1])  # технические id модель не видит
        self.assertNotIn("qwen_pack", by_agent["staff"][1])
        self.assertNotIn("qwen_pack", menu_block())  # меню по умолчанию — кофейни, прайс ЦОДа в него не попадает

    def test_items_are_found_by_name_not_by_id(self):
        from app.engine import clean_item_id
        fresh()
        items = {row["id"]: row for row in db.items()}
        self.assertEqual(clean_item_id("Латте", items), "latte")
        self.assertEqual(clean_item_id("  латте ", items), "latte")
        self.assertEqual(clean_item_id("Беру капучино, пожалуйста", items), "cappuccino")
        self.assertEqual(clean_item_id("espresso", items), "espresso")
        self.assertEqual(clean_item_id("пицца", items), "")
        self.assertEqual(clean_item_id('{"item', items), "")
        self.assertEqual(clean_item_id("", items), "")

    def test_cafe_prompts_do_not_change(self):
        engine, llm = fresh()
        engine._open_day()
        arrival = db.next_arrival(1)
        db.execute("UPDATE arrivals SET minute = 100 WHERE id = ?", (arrival["id"],))
        db.set_run(clock_min=130.0, clock_real=0)
        run(engine._serve(engine._admit(db.next_arrival(1))))
        user = next(user for agent, _, user in llm.seen if agent == "client")
        self.assertIn("Меню:", user)
        self.assertIn("у стойки", user)

    def test_gpu_load_slows_service_and_blocks_unlimited(self):
        engine, llm = fresh(item="qwen_unlim")
        engine._open_day()
        with db.at_place("neuraldeep"):
            # Парк уже забит: безлимит оформлен много раз за последние дни.
            client = db.insert_client("Тест", "студент, ищет бесплатное или подешевле", 3, 3000, 1)
            for n in range(30):
                db.insert_visit(
                    day=1, seq=n, clock="09:00", client_id=client["id"], staff_id="valera", status="served", is_return=0,
                    requested_item_id="qwen_unlim", requested_text="", served_item_id="qwen_unlim", price=512, rating=5, asks=0,
                    memory_before="", memory_phrase="", outcome_note="", start_min=500.0, end_min=510.0, stay_min=0,
                    mood="спокойствие", wait_min=0,
                )
            self.assertGreaterEqual(engine._utilization(), 1.0)
        visit_id = visit_in_dc(engine)
        visit = db.visit(visit_id)
        self.assertEqual(visit["status"], "refused")
        self.assertIn("ёмкости GPU", visit["outcome_note"])
        self.assertEqual(visit["price"], 0)

    def test_gpu_utilization_counts_only_active_services(self):
        rows = [{"day": 1, "load": 0.5, "days": 3}, {"day": 9, "load": 0.5, "days": 30}]
        self.assertAlmostEqual(gpu_utilization(rows, 10, 1.0), 0.5)
        self.assertEqual(gpu_status(0.5), "штатно")
        self.assertEqual(gpu_status(0.87), "высокая нагрузка")
        self.assertEqual(gpu_status(1.2), "деградация")
        self.assertGreater(DC_CAPACITY, 0)

    def test_manager_gives_datacenter_items_their_own_ids(self):
        engine, llm = fresh()
        engine._open_day()

        original = llm.complete

        async def manager(**kwargs):
            if kwargs["agent"] == "manager":
                return {"say": "Нужен тариф под агентов", "changes": [
                    {"op": "add_item", "item_id": "", "name": "Тариф Coder", "price": 990, "minutes": 3, "available": True}]}
            return await original(**kwargs)

        llm.complete = manager
        db.set_run(day=5, day_closed=0)
        with db.at_place("neuraldeep"):
            self.assertTrue(run(engine._manager()))
            names = {row["name"]: row["id"] for row in db.items()}
        self.assertEqual(names["Тариф Coder"], "ne1")
        self.assertEqual(len(db.items()), 6)  # кофейня не изменилась

    def test_snapshot_lists_places_with_open_flags(self):
        fresh()
        db.set_run(day=1, clock_min=300.0, clock_real=0, status="paused")
        places = {row["id"]: row for row in snapshot()["places"]}
        self.assertFalse(places["cafe"]["open"])
        self.assertTrue(places["neuraldeep"]["open"])


if __name__ == "__main__":
    unittest.main()
