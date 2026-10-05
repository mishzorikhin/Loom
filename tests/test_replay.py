import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SIM_LOG_STDOUT"] = "0"

import app.db as db  # noqa: E402
from app import cassette  # noqa: E402
from app.llm import LLM, TransportError  # noqa: E402


class CassetteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        db.connect(Path(os.environ["SIM_DB"]))
        db.reset_world()

    def tearDown(self):
        cassette.configure(record="", replay="")

    def test_record_then_replay_in_order(self):
        path = self.tmp / "c.jsonl"
        cassette.configure(record=str(path), replay="")
        cassette.record("client", "client", "sys", "user one", {"say": "Привет"}, 1, "m")
        cassette.record("staff", "staff", "sys", "user two", {"say": "Держите"}, 1, "m")
        cassette.record("client", "client", "sys", "user three", {"say": "Спасибо"}, 2, "m")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["agent"] for row in rows], ["client", "staff", "client"])
        cassette.configure(record="", replay=str(path))
        self.assertTrue(cassette.replaying())
        first, drift = cassette.replay("client", "sys", "user one")
        self.assertEqual((first["say"], drift), ("Привет", False))
        second, drift = cassette.replay("client", "sys", "другой промпт")
        self.assertEqual((second["say"], drift), ("Спасибо", True))
        self.assertIsNone(cassette.replay("client", "sys", "x"))
        self.assertEqual(cassette.replay("staff", "sys", "user two")[0]["say"], "Держите")

    def test_replayed_model_call_skips_the_network(self):
        path = self.tmp / "c.jsonl"
        cassette.configure(record=str(path), replay="")
        cassette.record("client", "client", "s", "u", {"say": "Эспрессо", "item_id": "espresso", "request": "", "willing_to_wait": True})
        cassette.configure(record="", replay=str(path))

        async def go():
            llm = LLM()
            try:
                data = await llm.complete(agent="client", schema_key="client", system="s", user="u", visit_id=1, week_day=None)
                with self.assertRaises(TransportError):
                    await llm.complete(agent="client", schema_key="client", system="s", user="u", visit_id=1, week_day=None)
                return data
            finally:
                await llm.aclose()

        data = asyncio.run(go())
        self.assertEqual(data["item_id"], "espresso")
        calls = db.recent_llm(5)
        self.assertEqual(calls[-1]["model"], "кассета")
        self.assertTrue(any(call["error"] for call in calls))

    def test_broken_lines_are_ignored(self):
        path = self.tmp / "c.jsonl"
        path.write_text('мусор\n{"agent": "staff", "parsed": {"say": "ок"}}\n{"agent": 1}\n', encoding="utf-8")
        cassette.configure(record="", replay=str(path))
        self.assertEqual(cassette.replay("staff", "s", "u")[0]["say"], "ок")


if __name__ == "__main__":
    unittest.main()
