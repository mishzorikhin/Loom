import asyncio
import os
import json
import tempfile
import unittest
from pathlib import Path

os.environ["SIM_LOG_STDOUT"] = "0"

import httpx  # noqa: E402

import app.db as db  # noqa: E402
from app.llm import LLM, SCHEMAS, SchemaError, check_schema, parse_content  # noqa: E402
from app.view import snapshot  # noqa: E402


def answer(handler):
    llm = LLM()
    llm.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return llm


class KeyAndHealthTest(unittest.TestCase):
    def setUp(self):
        db.connect(Path(os.environ["SIM_DB"]))
        db.reset_world()
        db.save_settings("https://api.example.test/v1", "big-model", 60, "", "", "sk-secret-123")

    def check(self, handler):
        llm = answer(handler)
        try:
            return asyncio.run(llm.health())
        finally:
            asyncio.run(llm.aclose())

    def test_key_goes_into_every_request(self):
        seen = []

        def handler(request):
            seen.append((request.url.path, request.headers.get("authorization")))
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

        async def go():
            llm = answer(handler)
            await llm._post("https://api.example.test/v1/chat/completions", {}, 5)
            await llm.aclose()

        asyncio.run(go())
        self.assertEqual(seen, [("/v1/chat/completions", "Bearer sk-secret-123")])

    def test_no_key_means_no_header(self):
        db.save_settings("http://local/v1", "m", 60)
        db.execute("UPDATE settings SET value = '' WHERE key = 'llm_api_key'")
        self.assertEqual(LLM()._headers(), {})

    def test_empty_key_field_keeps_the_old_key(self):
        db.save_settings("https://api.example.test/v1", "big-model", 60, "", "", "")
        self.assertEqual(db.setting("llm_api_key"), "sk-secret-123")
        db.save_settings("https://api.example.test/v1", "big-model", 60, "", "", "sk-new")
        self.assertEqual(db.setting("llm_api_key"), "sk-new")

    def test_key_never_reaches_the_snapshot(self):
        data = snapshot()
        self.assertTrue(data["llm"]["has_key"])
        self.assertNotIn("sk-secret-123", str(data))

    def test_cloud_service_without_status_and_health_is_fine(self):
        def handler(request):
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "big-model"}, {"id": "other"}]})
            return httpx.Response(401)

        out = self.check(handler)
        self.assertTrue(out["ok"])
        self.assertIn("доступна", out["detail"])

    def test_wrong_key_and_missing_model_are_reported(self):
        self.assertIn("ключ", self.check(lambda request: httpx.Response(401))["detail"])
        out = self.check(lambda request: httpx.Response(200, json={"data": [{"id": "other"}]}))
        self.assertFalse(out["ok"])
        self.assertIn("big-model", out["detail"])

    def test_local_llama_server_still_checks_status_and_health(self):
        def loaded(request):
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "big-model", "status": {"value": "loaded"}}]})
            return httpx.Response(200, json={"status": "ok"})

        self.assertTrue(self.check(loaded)["ok"])

        def sleeping(request):
            return httpx.Response(200, json={"data": [{"id": "big-model", "status": {"value": "unloaded"}}]})

        self.assertFalse(self.check(sleeping)["ok"])

        def sick(request):
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "big-model", "status": {"value": "loaded"}}]})
            return httpx.Response(503)

        self.assertIn("health 503", self.check(sick)["detail"])


class StructuredOutputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.connect(Path(self.tmp.name) / "sim.db")
        db.reset_world()

    def tearDown(self):
        self.tmp.cleanup()

    def complete(self, handler, agent="queue", key="queue"):
        async def go():
            llm = answer(handler)
            try:
                return await llm.complete(agent=agent, schema_key=key, system="s", user="u",
                                          visit_id=None, week_day=None)
            finally:
                await llm.aclose()
        return asyncio.run(go())

    def test_string_false_retries_then_fails_instead_of_waiting(self):
        seen = []
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {
                "content": '{"stay":"false","say":"Ухожу"}'}, "finish_reason": "stop"}]})
        with self.assertRaises(SchemaError):
            self.complete(handler)
        self.assertEqual(len(seen), 2)
        self.assertTrue(seen[0]["response_format"]["json_schema"]["strict"])

    def test_length_retries_with_larger_budget_even_for_valid_json(self):
        budgets = []
        def handler(request):
            budgets.append(json.loads(request.content)["max_tokens"])
            return httpx.Response(200, json={"choices": [{"message": {
                "content": '{"stay":false,"say":"Ухожу"}'},
                "finish_reason": "length" if len(budgets) == 1 else "stop"}]})
        self.assertFalse(self.complete(handler)["stay"])
        self.assertEqual(budgets, [120, 240])
        self.assertIn("лимиту", db.recent_llm(2)[-1]["error"])

    def test_invalid_envelopes_fail_as_schema_errors(self):
        for payload in ([], {"choices": [None]}, {"choices": [{}]},
                        {"choices": [{"message": {"content": ["wrong"]}}]},
                        {"choices": [{"message": {"refusal": "no"}}]}):
            with self.subTest(payload=payload), self.assertRaises(SchemaError):
                self.complete(lambda request: httpx.Response(200, json=payload))

    def test_prose_and_fences_are_not_structured_outputs(self):
        for raw in ('Ответ: {"stay":false,"say":"Пока"}', '```json\n{"stay":false,"say":"Пока"}\n```'):
            with self.subTest(raw=raw), self.assertRaises(SchemaError):
                parse_content(raw)

    def test_nested_types_required_fields_and_nonfinite_numbers(self):
        for data, key in (({"people": [None]}, "crowd"),
                          ({"say": "Да", "action": "serve", "item_id": "espresso"}, "staff"),
                          ({"traffic": float("nan"), "newcomers": .3, "curve": [], "why": "", "buzz": ""}, "district"),
                          ({"stay": False, "say": "Пока", "extra": 1}, "queue"),
                          ({"score": True, "issues": []}, "critic")):
            with self.subTest(key=key), self.assertRaises(SchemaError):
                check_schema(data, SCHEMAS[key]["schema"])


if __name__ == "__main__":
    unittest.main()
