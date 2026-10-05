import asyncio
import os
import unittest
from pathlib import Path

os.environ["SIM_LOG_STDOUT"] = "0"

import httpx  # noqa: E402

import app.db as db  # noqa: E402
from app.llm import LLM  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
