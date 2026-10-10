"""Генераторы описаний мира: решётка и магистраль. Выдают тот же JSON, что пишут руками."""

from __future__ import annotations

import math

COMPASS = {"n": (0, 1), "e": (1, 0), "s": (0, -1), "w": (-1, 0)}
OPP = {"n": "s", "s": "n", "e": "w", "w": "e"}
LEFT_OF = {"n": "w", "w": "s", "s": "e", "e": "n"}   # налево от направления движения


def _moves(arm: str, arms: set[str]) -> dict[str, bool]:
    """Какие движения есть у подхода с луча arm: машина едет к центру, то есть в сторону OPP[arm]."""
    heading = OPP[arm]
    return {
        "straight": OPP[arm] in arms,
        "left": LEFT_OF[heading] in arms,
        "right": OPP[LEFT_OF[heading]] in arms,
    }


def _approach(kind: str, mv: dict[str, bool]) -> list[dict]:
    """Полосы подхода от бордюра к центру."""
    have = [m for m in ("left", "straight", "right") if mv[m]]
    if kind == "avenue":
        lanes = []
        curb = [m for m in ("straight", "right") if mv[m]] or have
        lanes.append({"width": 3.5, "turns": curb})
        if mv["straight"]:
            lanes.append({"width": 3.5, "turns": ["straight"]})
        if mv["left"]:
            lanes.append({"width": 3.25, "turns": ["left"], "length": 45})
        return lanes
    return [{"width": 3.25, "turns": have}]


def _exit(kind: str) -> list[dict]:
    return [{"width": 3.5}, {"width": 3.5}] if kind == "avenue" else [{"width": 3.25}]


def _road(a: str, b: str, kind: str, nodes: dict, arms: dict, dir_ab: str, shape=None) -> dict:
    """Дорога a → b; dir_ab — сторона света от a к b."""
    def lanes_to(node, from_dir):
        if nodes[node]["kind"] == "boundary":
            return _exit(kind)
        return _approach(kind, _moves(from_dir, arms[node]))

    r = {
        "from": a, "to": b,
        "speed": 16.7 if kind == "avenue" else 11.1,
        # forward едет к b и подходит к нему с луча OPP[dir_ab]
        "forward": lanes_to(b, OPP[dir_ab]) if nodes[b]["kind"] == "signal" else _exit(kind),
        "backward": lanes_to(a, dir_ab) if nodes[a]["kind"] == "signal" else _exit(kind),
        "sidewalk": {"left": 3.5 if kind == "avenue" else 3.0, "right": 3.5 if kind == "avenue" else 3.0},
    }
    if kind == "avenue":
        r["median"] = {"width": 1.0}
    if shape:
        r["shape"] = shape
    return r


def grid(nx: int = 3, ny: int = 3, spacing: float = 170.0, tail: float = 150.0, avenues_vertical: bool = True,
         name: str | None = None) -> dict:
    """Решётка nx × ny перекрёстков. Вертикальные улицы — проспекты с карманами, горизонтальные — однополосные."""
    nodes: dict[str, dict] = {}
    arms: dict[str, set[str]] = {}

    def nid(i, j):
        return f"j{i}{j}"

    for i in range(nx):
        for j in range(ny):
            nodes[nid(i, j)] = {"pos": [i * spacing, j * spacing], "kind": "signal"}
            arms[nid(i, j)] = {"n", "e", "s", "w"}
    edges = []
    for i in range(nx):
        for j in range(ny):
            if i + 1 < nx:
                edges.append((nid(i, j), nid(i + 1, j), "e"))
            if j + 1 < ny:
                edges.append((nid(i, j), nid(i, j + 1), "n"))
    for i in range(nx):
        bs, bn = f"bs{i}", f"bn{i}"
        nodes[bs] = {"pos": [i * spacing, -tail], "kind": "boundary"}
        nodes[bn] = {"pos": [i * spacing, (ny - 1) * spacing + tail], "kind": "boundary"}
        edges.append((nid(i, 0), bs, "s"))
        edges.append((nid(i, ny - 1), bn, "n"))
    for j in range(ny):
        bw, be = f"bw{j}", f"be{j}"
        nodes[bw] = {"pos": [-tail, j * spacing], "kind": "boundary"}
        nodes[be] = {"pos": [(nx - 1) * spacing + tail, j * spacing], "kind": "boundary"}
        edges.append((nid(0, j), bw, "w"))
        edges.append((nid(nx - 1, j), be, "e"))
    roads = {}
    for a, b, d in edges:
        vertical = d in ("n", "s")
        kind = "avenue" if vertical == avenues_vertical else "street"
        roads[f"r_{a}_{b}"] = _road(a, b, kind, nodes, arms, d)
    junctions = {k: {"crosswalks": "auto", "signal": "auto"} for k, v in nodes.items() if v["kind"] == "signal"}
    return {"format": "loom-traffic/world", "version": 1, "name": name or f"Решётка {nx} × {ny}",
            "nodes": nodes, "roads": roads, "junctions": junctions}


def corridor(n: int = 4, spacing: float = 190.0, tail: float = 160.0, side: float = 140.0) -> dict:
    """Магистраль запад — восток, n перекрёстков; боковые улицы чередуются: крест, Т на север, крест, Т на юг."""
    nodes: dict[str, dict] = {}
    arms: dict[str, set[str]] = {}
    edges = []
    nodes["bw"] = {"pos": [-tail, 0], "kind": "boundary"}
    nodes["be"] = {"pos": [(n - 1) * spacing + tail, 0], "kind": "boundary"}
    pattern = ["ns", "n", "ns", "s"]
    for i in range(n):
        j = f"c{i}"
        nodes[j] = {"pos": [i * spacing, 0], "kind": "signal"}
        sides = pattern[i % len(pattern)]
        arms[j] = {"e", "w"} | set(sides)
        for sd in sides:
            b = f"b{sd}{i}"
            bend = 30 if sd == "n" else -24
            nodes[b] = {"pos": [i * spacing + bend, side if sd == "n" else -side], "kind": "boundary"}
            edges.append((j, b, sd, "street", [[i * spacing + bend * 0.15, (side if sd == "n" else -side) * 0.55]]))
    edges.append(("c0", "bw", "w", "avenue", None))
    for i in range(n - 1):
        edges.append((f"c{i}", f"c{i + 1}", "e", "avenue", None))
    edges.append((f"c{n - 1}", "be", "e", "avenue", None))
    roads = {}
    for a, b, d, kind, shape in edges:
        roads[f"r_{a}_{b}"] = _road(a, b, kind, nodes, arms, d, shape)
    junctions = {k: {"crosswalks": "auto", "signal": "auto"} for k, v in nodes.items() if v["kind"] == "signal"}
    world = {"format": "loom-traffic/world", "version": 1, "name": f"Магистраль, {n} перекрёстка",
             "nodes": nodes, "roads": roads, "junctions": junctions}
    world["midblock_crosswalks"] = [{"id": "park", "road": "r_c1_c2", "at": spacing / 2, "width": 4, "signal": "button"}]
    return world


# -- произвольный граф: дороги под любыми углами

def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def _movements(heading: float, outs: list[float]) -> dict[str, bool]:
    """Движения подхода по углам лучей выезда. Правило то же, что в компиляторе (`classify`):
    прямо — ближайший луч в пределах 40° от продолжения, остальные делятся на левые и правые."""
    mv = {"left": False, "straight": False, "right": False}
    cand = [_wrap(o - heading) for o in outs]
    near = [c for c in cand if abs(c) < math.radians(40)]
    if near:
        mv["straight"] = True
        cand.remove(min(near, key=abs))
    mv["left"] = any(c > 0 for c in cand)
    mv["right"] = any(c < 0 for c in cand)
    return mv


def from_graph(nodes: dict[str, dict], edges: list[tuple], name: str, midblock: list[dict] | None = None) -> dict:
    """Мир из графа: узлы (`pos`, `kind`) и дороги `(от, до, "avenue" | "street", shape | None)`.
    Полосы и стрелки выводятся по углам лучей, поэтому дороги могут идти под любым углом."""
    out_angle: dict[str, list[float]] = {k: [] for k in nodes}
    for a, b, _kind, shape in edges:
        pa, pb = nodes[a]["pos"], nodes[b]["pos"]
        first = shape[0] if shape else pb
        last = shape[-1] if shape else pa
        out_angle[a].append(math.atan2(first[1] - pa[1], first[0] - pa[0]))
        out_angle[b].append(math.atan2(last[1] - pb[1], last[0] - pb[0]))

    def lanes_into(node: str, kind: str, out: float) -> list[dict]:
        if nodes[node]["kind"] != "signal":
            return _exit(kind)
        heading = out + math.pi
        others = [o for o in out_angle[node] if abs(_wrap(o - out)) > 1e-6]
        return _approach(kind, _movements(heading, others))

    roads = {}
    for a, b, kind, shape in edges:
        pa, pb = nodes[a]["pos"], nodes[b]["pos"]
        first = shape[0] if shape else pb
        last = shape[-1] if shape else pa
        r = {
            "from": a, "to": b, "speed": 16.7 if kind == "avenue" else 11.1,
            "forward": lanes_into(b, kind, math.atan2(last[1] - pb[1], last[0] - pb[0])),
            "backward": lanes_into(a, kind, math.atan2(first[1] - pa[1], first[0] - pa[0])),
            "sidewalk": {"left": 3.5 if kind == "avenue" else 3.0, "right": 3.5 if kind == "avenue" else 3.0},
        }
        if kind == "avenue":
            r["median"] = {"width": 1.0}
        if shape:
            r["shape"] = shape
        roads[f"r_{a}_{b}"] = r
    junctions = {k: {"crosswalks": "auto", "signal": "auto"} for k, v in nodes.items() if v["kind"] == "signal"}
    world = {"format": "loom-traffic/world", "version": 1, "name": name, "nodes": nodes, "roads": roads, "junctions": junctions}
    if midblock:
        world["midblock_crosswalks"] = midblock
    return world


def district() -> dict:
    """Городской район: проспект по диагонали, шоссе под острым углом, косые перекрёстки, Т-образные, кривая улица."""
    def at(p, deg, d):
        a = math.radians(deg)
        return [round(p[0] + d * math.cos(a), 1), round(p[1] + d * math.sin(a), 1)]

    m0 = [0.0, 0.0]
    m1 = at(m0, 25, 230)
    m2 = at(m1, 25, 210)
    m3 = at(m2, 25, 220)
    p = at(m1, 100, 160)
    nodes = {
        "m0": {"pos": m0, "kind": "signal"}, "m1": {"pos": m1, "kind": "signal"},
        "m2": {"pos": m2, "kind": "signal"}, "m3": {"pos": m3, "kind": "signal"},
        "p": {"pos": p, "kind": "signal"},
        "b_sw": {"pos": at(m0, 205, 170), "kind": "boundary"},
        "b_ne": {"pos": at(m3, 25, 170), "kind": "boundary"},
        "b_hw": {"pos": [-250.0, 330.0], "kind": "boundary"},
        "b_n1": {"pos": at(p, 100, 150), "kind": "boundary"},
        "b_s1": {"pos": at(m1, 280, 180), "kind": "boundary"},
        "b_w": {"pos": at(p, 190, 190), "kind": "boundary"},
        "b_e": {"pos": at(p, 8, 200), "kind": "boundary"},
        "b_s2": {"pos": at(m2, 295, 150), "kind": "boundary"},
        "b_n3": {"pos": at(m3, 80, 190), "kind": "boundary"},
        "b_s3": {"pos": at(m3, 262, 210), "kind": "boundary"},
    }
    s2 = at(m2, 295, 70)
    s2 = [s2[0] + 18, s2[1]]
    s3 = at(m3, 262, 100)
    s3 = [s3[0] - 35, s3[1]]
    edges = [
        ("m0", "b_sw", "avenue", None),
        ("m0", "m1", "avenue", None), ("m1", "m2", "avenue", None), ("m2", "m3", "avenue", None),
        ("m3", "b_ne", "avenue", None),
        ("m0", "b_hw", "avenue", None),
        ("m1", "p", "street", None), ("p", "b_n1", "street", None), ("m1", "b_s1", "street", None),
        ("p", "b_w", "street", None), ("p", "b_e", "street", None),
        ("m2", "b_s2", "street", [s2]),
        ("m3", "b_n3", "street", None), ("m3", "b_s3", "street", [s3]),
    ]
    return from_graph(nodes, edges, "Район с диагональным проспектом")


def irregular() -> dict:
    """Небольшой мир с разным числом фаз: звезда из пяти лучей (6 фаз) и Т-перекрёсток (3 фазы). Нужен проверкам раскладки среды."""
    def at(p, deg, d):
        a = math.radians(deg)
        return [round(p[0] + d * math.cos(a), 1), round(p[1] + d * math.sin(a), 1)]

    star, tee = [0.0, 0.0], [260.0, 0.0]
    nodes = {"star": {"pos": star, "kind": "signal"}, "tee": {"pos": tee, "kind": "signal"}}
    edges = [("star", "tee", "street", None)]
    for i, deg in enumerate((72, 144, 216, 288)):
        nodes[f"s{i}"] = {"pos": at(star, deg, 200), "kind": "boundary"}
        edges.append(("star", f"s{i}", "street", None))
    for i, deg in enumerate((60, -60)):
        nodes[f"t{i}"] = {"pos": at(tee, deg, 200), "kind": "boundary"}
        edges.append(("tee", f"t{i}", "street", None))
    return from_graph(nodes, edges, "Звезда и Т-перекрёсток")
