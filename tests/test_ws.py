import os
import time
import unittest

os.environ["SIM_LOG_STDOUT"] = "0"

from starlette.testclient import TestClient  # noqa: E402

import app.db as db  # noqa: E402
import app.main as main  # noqa: E402


async def fake_health():
    return {"ok": True, "detail": "тест"}


class SocketTest(unittest.TestCase):
    def setUp(self):
        self.saved = main.llm_health
        main.llm_health = fake_health
        main.hub.idle_seconds = 0.3

    def tearDown(self):
        main.llm_health = self.saved

    def test_no_login_and_old_link_redirects(self):
        with TestClient(main.app) as client:
            self.assertEqual(client.get("/api/snapshot").status_code, 200)
            self.assertEqual(client.get("/").status_code, 200)
            moved = client.get("/login", follow_redirects=False)
            self.assertEqual((moved.status_code, moved.headers["location"]), (303, "/"))
            self.assertEqual(client.post("/api/logout").status_code, 404)
            self.assertEqual(client.get("/api/events").status_code, 404)

    def test_snapshot_arrives_on_connect_and_viewers_are_counted(self):
        with TestClient(main.app) as client:
            with client.websocket_connect("/ws") as first:
                hello = first.receive_json()
                self.assertEqual(hello["type"], "snapshot")
                self.assertEqual(hello["data"]["viewers"], 1)
                self.assertIn("run", hello["data"])
                with client.websocket_connect("/ws") as second:
                    self.assertEqual(second.receive_json()["data"]["viewers"], 2)
                    seen = first.receive_json()
                    while seen["data"]["viewers"] != 2:
                        seen = first.receive_json()
                    self.assertEqual(main.hub.count, 2)
                for _ in range(5):
                    if main.hub.count == 1:
                        break
                    time.sleep(0.05)
                self.assertEqual(main.hub.count, 1)

    def test_commands_go_through_the_socket_and_everyone_sees_the_result(self):
        with TestClient(main.app) as client:
            with client.websocket_connect("/ws") as one, client.websocket_connect("/ws") as two:
                one.receive_json()
                two.receive_json()
                one.send_json({"id": 7, "cmd": "control", "action": "pause"})
                reply = one.receive_json()
                while reply["type"] != "reply":
                    reply = one.receive_json()
                self.assertEqual((reply["id"], reply["ok"]), (7, True))
                got = two.receive_json()
                for _ in range(10):
                    if got["type"] == "snapshot" and got["data"]["run"]["status"] == "paused":
                        break
                    got = two.receive_json()
                self.assertEqual(got["data"]["run"]["status"], "paused")
                self.assertEqual(got["data"]["run"]["speed"], 2)
                one.send_json({"id": 8, "cmd": "control", "action": "speed"})
                bad = one.receive_json()
                while bad["type"] != "reply":
                    bad = one.receive_json()
                self.assertEqual((bad["ok"], bad["status"]), (False, 400))
                one.send_json({"id": 9, "cmd": "что-то"})
                unknown = one.receive_json()
                while unknown["type"] != "reply":
                    unknown = one.receive_json()
                self.assertFalse(unknown["ok"])
                one.send_json({"id": 10, "cmd": "director", "text": "а"})
                short = one.receive_json()
                while short["type"] != "reply":
                    short = one.receive_json()
                self.assertEqual((short["ok"], short["status"]), (False, 422))
                one.send_json({"id": 11, "cmd": "director", "text": "сломалась кофемашина"})
                closed = one.receive_json()
                while closed["type"] != "reply":
                    closed = one.receive_json()
                self.assertEqual((closed["ok"], closed["status"]), (False, 409))

    def test_end_event_command(self):
        with TestClient(main.app) as client:
            db.reset_world()
            main.app.state.engine._open_day()
            main.app.state.engine._apply_event(1, {"headline": "Жара", "story": "", "effects": [
                {"type": "demand", "target": "", "amount": 1.3, "days": 1}]}, "director", "жара")
            event_id = db.active_events(1)[0]["id"]
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"id": 1, "cmd": "end_event", "event_id": event_id})
                reply = ws.receive_json()
                while reply["type"] != "reply":
                    reply = ws.receive_json()
                self.assertTrue(reply["ok"])
                ws.send_json({"id": 2, "cmd": "end_event", "event_id": event_id})
                again = ws.receive_json()
                while again["type"] != "reply":
                    again = ws.receive_json()
                self.assertEqual((again["ok"], again["status"]), (False, 404))
                ws.send_json({"id": 3, "cmd": "end_event", "event_id": "x"})
                bad = ws.receive_json()
                while bad["type"] != "reply":
                    bad = ws.receive_json()
                self.assertEqual(bad["status"], 422)
            self.assertEqual(db.active_events(1), [])

    def test_run_is_paused_when_the_last_viewer_leaves(self):
        with TestClient(main.app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                db.set_run(status="running", message="")
            time.sleep(0.8)
            run = db.run()
            self.assertEqual(run["status"], "paused")
            self.assertIn("Нет зрителей", run["message"])

    def test_short_reconnect_does_not_pause(self):
        with TestClient(main.app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                db.set_run(status="running", message="")
            time.sleep(0.1)
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                time.sleep(0.6)
                self.assertEqual(db.run()["status"], "running")
            db.set_run(status="idle")

    def test_idle_pause_leaves_a_stopped_run_alone(self):
        with TestClient(main.app) as client:
            db.set_run(status="idle", message="")
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
            time.sleep(0.8)
            self.assertEqual(db.run()["status"], "idle")
            self.assertEqual(db.run()["message"], "")


if __name__ == "__main__":
    unittest.main()
