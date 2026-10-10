import unittest

from tsim.compiler import compile_world, load_world
from tsim.signals import SignalCtl
from tsim.sim import Demand, Sim
from tsim.worlds import ROOT

NET = compile_world(load_world(ROOT / "examples" / "cross.json"))


class SignalTest(unittest.TestCase):
    def test_stage_order(self):
        ctl = SignalCtl(NET.junctions["a"])
        self.assertEqual(ctl.stage, "green")
        self.assertFalse(ctl.request(1))  # минимальный зелёный ещё не прошёл
        for _ in range(60):
            ctl.tick(0.1)
        self.assertTrue(ctl.request(1, yellow=3, all_red=2, ped_flash=0))
        self.assertEqual(ctl.stage, "change")
        self.assertEqual(ctl.state["ns_main"], "Y")
        for _ in range(31):
            ctl.tick(0.1)
        self.assertEqual(ctl.stage, "all_red")
        self.assertTrue(all(s in ("R", "D") for s in ctl.state.values()))
        for _ in range(21):
            ctl.tick(0.1)
        self.assertEqual(ctl.phase, 1)
        self.assertEqual(ctl.state["ns_left"], "G")

    def test_bounds_clamp_and_zero_allowed(self):
        ctl = SignalCtl(NET.junctions["a"])
        for _ in range(60):
            ctl.tick(0.1)
        ctl.request(2, yellow=99, all_red=-5, ped_flash=0)
        self.assertEqual(ctl.dur["yellow"], 6)
        self.assertEqual(ctl.dur["all_red"], 0)


class SimTest(unittest.TestCase):
    def test_deterministic(self):
        a = Sim(NET, seed=7)
        b = Sim(NET, seed=7)
        a.run(300)
        b.run(300)
        self.assertEqual(a.metrics(), b.metrics())
        self.assertEqual(a.frame()["cars"], b.frame()["cars"])

    def test_cars_flow_and_stop_on_red(self):
        sim = Sim(NET, seed=2)
        for _ in range(3000):
            sim.step()
            for c in sim.cars.values():
                link = NET.links[c.link]
                if link.kind == "conn" and c.entered.get("a") == "R":
                    self.fail("машина въехала на перекрёсток на красный без проезда на красный")
        self.assertGreater(sim.stats.done, 20)

    def test_safe_timings_no_signal_crashes(self):
        for seed in (1, 2, 3):
            sim = Sim(NET, seed=seed, demand=Demand(scale=1.2))
            sim.run(1200)
            causes = sim.metrics()["causes"]
            self.assertNotIn("signal_timing", causes, f"зерно {seed}: {causes}")
            self.assertNotIn("other", causes, f"зерно {seed}: {causes}")

    def test_variant_b_zero_clearance_causes_crashes(self):
        total = 0
        for seed in (1, 2, 3):
            sim = Sim(NET, seed=seed, controller="max_pressure", demand=Demand(scale=1.4), timing_scale=0.0)
            sim.run(1800)
            total += sim.metrics()["causes"].get("signal_timing", 0)
        self.assertGreater(total, 0)

    def test_frame_shape(self):
        sim = Sim(NET, seed=1)
        sim.run(120)
        f = sim.frame()
        self.assertTrue(f["cars"])
        self.assertEqual(len(f["cars"][0]), 11)
        self.assertEqual(len(f["signals"]["a"]["state"]), len(NET.junctions["a"].groups))


if __name__ == "__main__":
    unittest.main()
