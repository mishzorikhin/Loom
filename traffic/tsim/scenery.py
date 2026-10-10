"""Окружение для отрисовки: дома, деревья, фонари. На физику не влияет, зерно — хеш мира."""

from __future__ import annotations

import math
import random

from .compiler import Net
from .geom import Polyline, angle, left


def _road_strips(net: Net) -> list[tuple[Polyline, float]]:
    """Полосы, занятые дорогой и тротуаром: ось и полуширина с тротуаром."""
    out = []
    for rid, r in net.world["roads"].items():
        pts = [net.world["nodes"][r["from"]]["pos"], *r.get("shape", []), net.world["nodes"][r["to"]]["pos"]]
        axis = Polyline([tuple(p) for p in pts])
        med = r.get("median", {}).get("width", 0.0)
        hw = med / 2 + max(sum(l.get("width", 3.5) for l in r["forward"]), sum(l.get("width", 3.5) for l in r["backward"]))
        sw = max(r.get("sidewalk", {}).get("left", 3.0), r.get("sidewalk", {}).get("right", 3.0))
        out.append((axis, hw + sw))
    return out


def build(net: Net) -> dict:
    rng = random.Random(int(net.hash, 16))
    strips = _road_strips(net)
    x0, y0, x1, y1 = net.render["bbox"]
    pad = 6.0
    gx0, gy0, gx1, gy1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    span = max(x1 - x0, y1 - y0) / 2
    junctions = [j.pos for j in net.junctions.values() if j.kind == "signal"]

    def nearest(p):
        best = (1e9, None, 0.0)
        for axis, half in strips:
            s, d = axis.project(p)
            if d - half < best[0]:
                best = (d - half, axis, s)
        return best

    buildings, trees, lamps = [], [], []
    cell = 14.0
    taken: list[tuple[float, float, float]] = []
    y = gy0 + cell / 2
    while y < gy1 - cell / 2:
        x = gx0 + cell / 2
        while x < gx1 - cell / 2:
            p = (x + rng.uniform(-1.2, 1.2), y + rng.uniform(-1.2, 1.2))
            free, axis, s = nearest(p)
            edge = min(p[0] - gx0, gx1 - p[0], p[1] - gy0, gy1 - p[1])
            if axis is not None and free > 6.0 and edge > 7:
                d = axis.dir(s)
                ang = angle(d)
                size = min(cell - 2.5, (free - 4.0) * 2)
                near_j = min((math.hypot(p[0] - j[0], p[1] - j[1]) for j in junctions), default=1e9)
                # кварталы: у дороги дома, в глубине — дворы и скверы
                if size >= 7 and (free < 34 or rng.random() < 0.25) and rng.random() < 0.78:
                    w = rng.uniform(0.7, 1.0) * size
                    dd = rng.uniform(0.7, 1.0) * size
                    centre = 1 - min(1.0, near_j / (span * 0.9))
                    tall = rng.random() < 0.06 + 0.22 * centre
                    h = rng.uniform(16, 30) if tall else rng.choice([4.5, 7.5, 7.5, 10.5, 10.5, 13.5])
                    buildings.append({"pos": [round(p[0], 2), round(p[1], 2)], "w": round(w, 2), "d": round(dd, 2),
                                      "h": round(h, 1), "a": round(ang, 4), "style": rng.randrange(8),
                                      "roof": rng.randrange(3)})
                    taken.append((p[0], p[1], size / 2))
                elif rng.random() < 0.85:
                    for _ in range(rng.randint(1, 3)):
                        q = (p[0] + rng.uniform(-5, 5), p[1] + rng.uniform(-5, 5))
                        trees.append({"pos": [round(q[0], 2), round(q[1], 2)], "r": round(rng.uniform(1.8, 3.4), 2), "kind": rng.randrange(3)})
            x += cell
        y += cell

    # деревья вдоль тротуаров и фонари у бордюра
    for rid, r in net.world["roads"].items():
        pts = [net.world["nodes"][r["from"]]["pos"], *r.get("shape", []), net.world["nodes"][r["to"]]["pos"]]
        axis = Polyline([tuple(p) for p in pts])
        med = r.get("median", {}).get("width", 0.0)
        for side, sign in (("left", 1), ("right", -1)):
            lanes = r["backward"] if side == "left" else r["forward"]
            hw = med / 2 + sum(l.get("width", 3.5) for l in lanes)
            sw = r.get("sidewalk", {}).get(side, 3.0)
            if sw <= 0:
                continue
            s = 28.0 + rng.uniform(0, 6)
            while s < axis.length - 28:
                p, d = axis.at(s)
                n = left(d)
                q = (p[0] + n[0] * sign * (hw + sw + 1.4), p[1] + n[1] * sign * (hw + sw + 1.4))
                inside = gx0 + 2 < q[0] < gx1 - 2 and gy0 + 2 < q[1] < gy1 - 2
                if inside and not any(math.hypot(q[0] - bx, q[1] - by) < br + 1.5 for bx, by, br in taken):
                    trees.append({"pos": [round(q[0], 2), round(q[1], 2)], "r": round(rng.uniform(1.6, 2.4), 2), "kind": rng.randrange(2)})
                s += rng.uniform(9, 13)
            s = 30.0 if sign > 0 else 46.0
            while s < axis.length - 30:
                p, d = axis.at(s)
                n = left(d)
                q = (p[0] + n[0] * sign * (hw + 0.6), p[1] + n[1] * sign * (hw + 0.6))
                lamps.append({"pos": [round(q[0], 2), round(q[1], 2)], "a": round(angle((-n[0] * sign, -n[1] * sign)), 4)})
                s += 32.0
    return {"buildings": buildings, "trees": trees, "lamps": lamps, "ground": [gx0, gy0, gx1, gy1]}
