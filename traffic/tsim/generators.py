"""Генераторы описаний мира: решётка и магистраль. Выдают тот же JSON, что пишут руками."""

from __future__ import annotations

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
