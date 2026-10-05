import os
import tempfile
import unittest
from pathlib import Path

os.environ["SIM_LOG_STDOUT"] = "0"

from app import digest, log  # noqa: E402


class LogTest(unittest.TestCase):
    def setUp(self):
        self.original = log.path()
        self.tmp = Path(tempfile.mkdtemp()) / "j.log"
        log.configure(self.tmp)

    def tearDown(self):
        log.configure(self.original)

    def test_line_is_json_with_stable_keys(self):
        row = log.event("visit.end", visit_id=3, status="served", skipped=None)
        self.assertEqual(set(row), {"t", "lvl", "ev", "visit_id", "status"})
        self.assertEqual(log.read(5)[-1]["visit_id"], 3)

    def test_long_text_is_trimmed(self):
        row = log.event("x", text="я" * 1000)
        self.assertLessEqual(len(row["text"]), log.MAX_TEXT)

    def test_filters(self):
        log.event("visit.start", visit_id=1)
        log.event("llm.call", "warn", visit_id=1, err="Таймаут")
        log.event("visit.end", visit_id=1)
        log.event("visit.start", visit_id=2)
        self.assertEqual(len(log.read(50, level="warn")), 1)
        self.assertEqual([r["ev"] for r in log.read(50, ev="visit")], ["visit.start", "visit.end", "visit.start"])
        self.assertEqual(len(log.read(50, ev="llm,visit.end")), 2)
        self.assertEqual(len(log.read(50, visit=2)), 1)
        self.assertEqual(len(log.read(50, q="Таймаут")), 1)
        self.assertEqual(len(log.read(2)), 2)
        self.assertEqual(len(log.read(50, since="1h")), 4)
        self.assertEqual(len(log.read(50, since="2099-01-01T00:00:00")), 0)

    def test_broken_lines_are_skipped(self):
        log.event("a")
        with self.tmp.open("a", encoding="utf-8") as handle:
            handle.write("не json\n")
        log.event("b")
        self.assertEqual([r["ev"] for r in log.read(10)], ["a", "b"])

    def test_exc_fields_point_to_code(self):
        try:
            int("x")
        except ValueError as exc:
            fields = log.exc_fields(exc)
        self.assertEqual(fields["exc"], "ValueError")
        self.assertIn("test_log.py", fields["where"])

    def test_parse_since(self):
        self.assertIsNone(log.parse_since(None))
        self.assertIsNone(log.parse_since("давно"))
        self.assertIsNotNone(log.parse_since("90s"))

    def test_compact_line_is_readable(self):
        text = digest.compact({"t": "2026-10-05T10:20:49.123+05:00", "lvl": "warn", "ev": "visit.fail", "visit_id": 9})
        self.assertEqual(text, "10:20:49.123 WARN  visit.fail visit_id=9")


if __name__ == "__main__":
    unittest.main()
