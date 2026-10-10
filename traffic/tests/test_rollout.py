"""Воспроизводимость сравнения и полный отчёт о качестве политики."""

import contextlib
import io
import json
import random
import unittest
from unittest.mock import patch

from tsim.env import TrafficEnv
from tsim.rollout import automatic_max_pressure_policy, episode, fixed_policy, main, random_policy
from tsim.sim import Sim


class RolloutTest(unittest.TestCase):
    def test_seeded_episode_repeats(self):
        env = TrafficEnv("cross", episode=30)
        first = episode(env, random_policy, 11, random.Random(11))
        again = episode(env, random_policy, 11, random.Random(11))
        self.assertEqual(first, again)
        self.assertGreaterEqual(first["queue_mean"], 0)
        self.assertGreaterEqual(first["ped_waiting_mean"], 0)
        self.assertIn("blocked_spawn", first)
        self.assertIn("cars", first)

    def test_automatic_policies_match_builtin_controllers(self):
        for controller, policy in (("fixed", fixed_policy), ("max_pressure", automatic_max_pressure_policy)):
            env = TrafficEnv("cross", episode=60)
            result = episode(env, policy, 7, random.Random(7))
            reference = Sim(env.net, seed=7, controller=controller)
            # Одинаковое число шагов ядра исключает погрешность границы эпизода.
            while reference.t < env.sim.t:
                reference.step()
            for key, value in reference.metrics().items():
                self.assertEqual(result[key], value)
            for jid in env.agents:
                self.assertEqual(env.sim.signals[jid].snapshot(), reference.signals[jid].snapshot())

    def test_json_reports_each_seed_with_shared_layout(self):
        args = ["rollout", "--world", "cross", "--layout-worlds", "cross,irregular",
                "--policy", "fixed,max_pressure", "--episodes", "2", "--seed", "101",
                "--minutes", "0.1", "--json"]
        out = io.StringIO()
        with patch("sys.argv", args), contextlib.redirect_stdout(out):
            main()
        report = json.loads(out.getvalue())
        self.assertEqual(report["settings"]["seeds"], [101, 102])
        self.assertIn("world_hash", report["settings"])
        self.assertEqual(report["settings"]["obs_spec"]["max_phases"], 6)
        for result in report["policies"].values():
            self.assertEqual([r["seed"] for r in result["runs"]], [101, 102])
            self.assertEqual(result["summary"]["return"]["mean"],
                             sum(r["return"] for r in result["runs"]) / 2)


if __name__ == "__main__":
    unittest.main()
