import json
import unittest

from fastapi.testclient import TestClient

from tsim.env import TrafficEnv
from tsim.server import create_app


class EnvTest(unittest.TestCase):
    def test_reset_step(self):
        env = TrafficEnv("grid2", seed=1, decision=5, episode=60)
        obs = env.reset()
        self.assertEqual(set(obs), set(env.agents))
        self.assertEqual(next(iter(obs.values())).shape, (env.obs_size,))
        done = False
        steps = 0
        while not done:
            obs, rewards, done, info = env.step({j: {"phase": 1, "yellow": 3, "all_red": 2} for j in env.agents})
            steps += 1
            self.assertTrue(all(r <= 0 for r in rewards.values()))
        self.assertEqual(steps, 12)
        self.assertEqual(len(env.graph()["edges"]), 8)


    def test_mask_layout_and_ignored(self):
        env = TrafficEnv("grid2", seed=1, decision=5, episode=60)
        env.reset()
        self.assertEqual(len(env.obs_layout()), env.obs_size)
        jid = env.agents[0]
        mask = env.action_mask(jid)
        self.assertEqual(mask.shape, (env.max_actions,))
        # в начале минимальный зелёный не прошёл: разрешено только держать текущую фазу
        self.assertEqual(int(mask.sum()), 1)
        _, _, _, info = env.step({j: (env.sim.signals[j].phase + 1) % env.n_actions(j) for j in env.agents})
        self.assertTrue(all(info["ignored"].values()))
        for _ in range(8):
            env.step({})
        self.assertGreater(int(env.action_mask(jid).sum()), 1)


class ServerTest(unittest.TestCase):
    def test_ws_hello_net_frame_and_commands(self):
        app = create_app("cross", 1)
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                hello = json.loads(ws.receive_text())
                self.assertEqual(hello["type"], "hello")
                net = json.loads(ws.receive_text())
                self.assertEqual(net["type"], "net")
                self.assertIn("buildings", net["scenery"])
                frame = json.loads(ws.receive_text())
                self.assertEqual(frame["type"], "frame")
                self.assertTrue(frame["full"])
                ws.send_text(json.dumps({"cmd": "timing", "value": 0.5}))
                for _ in range(20):
                    msg = json.loads(ws.receive_text())
                    if msg["type"] == "hello":
                        self.assertEqual(msg["settings"]["timing"], 0.5)
                        break
                else:
                    self.fail("нет подтверждения настроек")
            state = client.get("/api/state").json()
            self.assertEqual(state["settings"]["timing"], 0.5)


if __name__ == "__main__":
    unittest.main()
