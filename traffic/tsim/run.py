"""Прогон без картинки: сравнение контроллеров на нескольких зёрнах.

    python3 -m tsim.run --world grid --controllers fixed,max_pressure --minutes 30 --seeds 3
    python3 -m tsim.run --world examples/cross.json --timing 0 --demand 1.6 --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import time

from .compiler import compile_world
from .sim import Demand, Sim
from .worlds import world as load_named

KEYS = ("done", "delay", "stops", "crashes", "near_total", "red_runs", "jaywalks", "ped_wait", "stuck")


def run_one(net, controller: str, seed: int, minutes: float, demand: float, timing: float, start_hour: float) -> dict:
    sim = Sim(net, seed=seed, controller=controller, demand=Demand(scale=demand), start_hour=start_hour, timing_scale=timing)
    sim.run(minutes * 60)
    m = sim.metrics()
    m["near_total"] = sum(m["near"].values())
    return m


def main():
    ap = argparse.ArgumentParser(description="Сравнение контроллеров светофоров")
    ap.add_argument("--world", default="cross", help="имя готового мира или путь к JSON")
    ap.add_argument("--controllers", default="fixed,max_pressure")
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--demand", type=float, default=1.0)
    ap.add_argument("--timing", type=float, default=1.0, help="запас переходных стадий: 1 — безопасно, 0 — без жёлтого и всего красного")
    ap.add_argument("--start-hour", type=float, default=7.5)
    ap.add_argument("--json", action="store_true", help="сырые результаты одной строкой JSON")
    a = ap.parse_args()
    net = compile_world(load_named(a.world))
    out = {}
    for ctl in a.controllers.split(","):
        rows = []
        t0 = time.time()
        for seed in range(1, a.seeds + 1):
            rows.append(run_one(net, ctl, seed, a.minutes, a.demand, a.timing, a.start_hour))
        out[ctl] = {"runs": rows, "seconds": round(time.time() - t0, 1)}
    if a.json:
        print(json.dumps(out, ensure_ascii=False))
        return
    print(f"мир {a.world}, {a.minutes:g} мин, зёрна 1..{a.seeds}, спрос ×{a.demand:g}, запас переходов ×{a.timing:g}")
    print(f"{'контроллер':<14}" + "".join(f"{k:>14}" for k in KEYS))
    for ctl, r in out.items():
        cells = []
        for k in KEYS:
            vals = [float(x[k]) for x in r["runs"]]
            mean = statistics.mean(vals)
            sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
            cells.append(f"{mean:>8.1f} ±{sd:<4.1f}")
        print(f"{ctl:<14}" + "".join(f"{c:>14}" for c in cells) + f"   ({r['seconds']} с)")


if __name__ == "__main__":
    main()
