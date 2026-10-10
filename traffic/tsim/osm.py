"""Импорт района из OpenStreetMap в описание мира.

    python3 -m tsim.osm fetch --bbox 57.9655,56.1480,57.9760,56.1700 --out raw.json
    python3 -m tsim.osm convert raw.json --center 57.9707,56.1601 --window -620,-400,620,520 --out examples/perm_mira.json

Данные © участники OpenStreetMap, лицензия ODbL (https://www.openstreetmap.org/copyright).

Что делает конвертер:
- берёт крупные дороги (primary, secondary, tertiary и съезды), переводит координаты в метры и обрезает по окну;
- перекрёстки, лежащие ближе `CLUSTER` метров друг к другу, склеивает в один узел;
- две односторонние проезжие части между одними и теми же узлами сливает в одну дорогу с разделительной полосой;
- узлы с тремя и больше дорогами становятся светофорными, тупики и места обрыва окна — краями сети;
- полосы по числу `lanes` и стрелки по углам лучей (как в `generators.from_graph`).

Нерегулируемых перекрёстков в формате версии 1 нет, поэтому каждый перекрёсток получает светофор,
а мелкие улицы и дворовые проезды отброшены.
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.parse
import urllib.request
from collections import defaultdict

from .generators import _wrap

MAIN = {"primary", "secondary", "tertiary", "primary_link", "secondary_link", "tertiary_link"}
SPEED = {"primary": 16.7, "secondary": 13.9, "tertiary": 11.1}
CLUSTER = 38.0        # перекрёстки ближе этого склеиваются
MIN_ROAD = 45.0       # дорога между узлами короче — слияние узлов
LANE_W = 3.5
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def fetch(bbox: str, out: str) -> None:
    """Скачивает дороги, светофоры и переходы из Overpass."""
    q = ('[out:json][timeout:60];(way["highway"~"^(primary|secondary|tertiary)(_link)?$"](%s);'
         'node["highway"="traffic_signals"](%s););out body;>;out body qt;' % (bbox, bbox))
    last = None
    for url in OVERPASS * 2:
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": "loom-traffic-dev"})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.load(r)
            json.dump(data, open(out, "w"), ensure_ascii=False)
            return
        except Exception as e:  # сервер перегружен — пробуем следующий
            last = e
    raise RuntimeError(f"Overpass не ответил: {last}")


class _UF:
    def __init__(self):
        self.p: dict = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _length(pts) -> float:
    return sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _sample(pts, t: float):
    """Точка на ломаной на доле t её длины."""
    total = _length(pts)
    target = t * total
    acc = 0.0
    for i in range(len(pts) - 1):
        seg = _dist(pts[i], pts[i + 1])
        if acc + seg >= target and seg > 0:
            u = (target - acc) / seg
            return (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * u, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * u)
        acc += seg
    return pts[-1]


def _simplify(pts, tol=3.0):
    """Дуглас — Пёкер: выкидывает точки, лежащие ближе tol метров от прямой."""
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-9
    best, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        d = abs(dy * (pts[i][0] - x1) - dx * (pts[i][1] - y1)) / norm
        if d > best:
            best, idx = d, i
    if best <= tol:
        return [pts[0], pts[-1]]
    return _simplify(pts[: idx + 1], tol)[:-1] + _simplify(pts[idx:], tol)


def _classify(heading: float, arms: list[tuple[float, object]]) -> dict[str, object]:
    """Движение → луч выезда, по тому же правилу, что `Builder.classify` в компиляторе (учитывает все лучи)."""
    cand = [(_wrap(a - heading), k) for a, k in arms]
    res = {}
    near = [c for c in cand if abs(c[0]) < math.radians(40)]
    if near:
        st = min(near, key=lambda c: abs(c[0]))
        res["straight"] = st[1]
        cand = [c for c in cand if c[1] != st[1]]
    lefts = [c for c in cand if c[0] > 0]
    rights = [c for c in cand if c[0] < 0]
    if lefts:
        res["left"] = min(lefts, key=lambda c: c[0])[1]
    if rights:
        res["right"] = max(rights, key=lambda c: c[0])[1]
    return res


def _cross(nodes: dict, out_id, in_id, window) -> int:
    """Точка, где отрезок от внешнего узла к внутреннему пересекает границу окна; кладёт её в nodes с новым id."""
    x0, y0, x1, y1 = window
    (ax, ay), (bx, by) = nodes[out_id], nodes[in_id]
    t = 1.0
    for lo, hi, a, b in ((x0, x1, ax, bx), (y0, y1, ay, by)):
        for edge in (lo, hi):
            if (a - edge) * (b - edge) < 0:
                t = min(t, (edge - a) / (b - a))
    p = (round(ax + (bx - ax) * t, 2), round(ay + (by - ay) * t, 2))
    nid = min(min(nodes), 0) - 1
    nodes[nid] = p
    return nid


def convert(osm: dict, center: tuple[float, float], window: tuple[float, float, float, float], name: str) -> dict:
    lat0, lon0 = center
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110574.0
    nodes = {e["id"]: (round((e["lon"] - lon0) * kx, 2), round((e["lat"] - lat0) * ky, 2))
             for e in osm["elements"] if e["type"] == "node"}
    signals = {e["id"] for e in osm["elements"] if e["type"] == "node" and e.get("tags", {}).get("highway") == "traffic_signals"}
    x0, y0, x1, y1 = window

    def inside(n):
        p = nodes[n]
        return x0 <= p[0] <= x1 and y0 <= p[1] <= y1

    # 1. дороги → отрезки внутри окна
    runs = []   # {"nodes": [...], "tags": {...}, "oneway": bool}
    for w in osm["elements"]:
        if w["type"] != "way" or w.get("tags", {}).get("highway") not in MAIN:
            continue
        t = w["tags"]
        ids = [n for n in w["nodes"] if n in nodes]
        oneway = t.get("oneway") in ("yes", "true", "1", "-1") or t.get("junction") == "roundabout"
        if t.get("oneway") == "-1":
            ids.reverse()
        cur = []
        for i, n in enumerate(ids):
            if inside(n):
                if not cur and i > 0:
                    cur.append(_cross(nodes, ids[i - 1], n, window))     # вошли в окно: точка на границе
                cur.append(n)
            else:
                if cur:
                    cur.append(_cross(nodes, n, cur[-1], window))        # вышли из окна: точка на границе
                    runs.append({"nodes": cur, "tags": t, "oneway": oneway})
                cur = []
        if len(cur) >= 2:
            runs.append({"nodes": cur, "tags": t, "oneway": oneway})
    runs = [r for r in runs if len(r["nodes"]) >= 2 and r["nodes"][0] != r["nodes"][-1]]

    # 2. вершины: перекрёстки, концы, светофоры
    uses = defaultdict(int)
    for r in runs:
        for n in r["nodes"]:
            uses[n] += 1
        uses[r["nodes"][0]] += 1
        uses[r["nodes"][-1]] += 1
    vertex = {n for n, c in uses.items() if c >= 2}

    # 3. склейка близких вершин в кластеры
    uf = _UF()
    vs = sorted(vertex)
    for i, a in enumerate(vs):
        uf.find(a)
        for b in vs[i + 1:]:
            if _dist(nodes[a], nodes[b]) < CLUSTER:
                uf.union(a, b)
    members = defaultdict(list)
    for v in vs:
        members[uf.find(v)].append(v)
    cpos = {c: (sum(nodes[v][0] for v in m) / len(m), sum(nodes[v][1] for v in m) / len(m)) for c, m in members.items()}
    cof = {v: uf.find(v) for v in vs}

    # 4. отрезки между кластерами
    edges = []  # a, b, pts (внутренние), highway, lanes, oneway, speed
    for r in runs:
        ids = r["nodes"]
        last = 0
        for i in range(1, len(ids)):
            if ids[i] in vertex:
                a, b = cof[ids[last]] if ids[last] in cof else None, cof[ids[i]]
                if a is not None and a != b:
                    inner = [nodes[n] for n in ids[last + 1: i]]
                    t = r["tags"]
                    lanes = int(t["lanes"]) if str(t.get("lanes", "")).isdigit() else None
                    edges.append({"a": a, "b": b, "pts": inner, "hw": t["highway"].replace("_link", ""), "lanes": lanes,
                                  "oneway": r["oneway"], "link": t["highway"].endswith("_link")})
                last = i

    # 5. слияние: пара узлов → одна дорога, два направления
    # roads[(a, b)], a < b: fwd/bwd — число полос a→b и b→a, gf/gb — путь по направлению движения (с концами)
    ORDER = ("primary", "secondary", "tertiary")
    groups = defaultdict(list)
    for e in edges:
        groups[frozenset((e["a"], e["b"]))].append(e)
    roads: dict = {}
    for key, es in groups.items():
        a, b = sorted(key)
        best = {"f": None, "b": None}
        for e in es:
            pts = [cpos[e["a"]], *e["pts"], cpos[e["b"]]]   # в порядке e.a → e.b
            fwd = e["a"] == a
            n_dir = e["lanes"] or (1 if e["hw"] == "tertiary" else 2)
            for d in (["f" if fwd else "b"] if e["oneway"] else ["f", "b"]):
                n = n_dir if e["oneway"] else max(1, n_dir // 2)
                # путь по ходу движения в направлении d
                path = pts if (d == "f") == fwd else pts[::-1]
                cur = best[d]
                if cur is None or n > cur[0] or (n == cur[0] and ORDER.index(e["hw"]) < ORDER.index(cur[2])):
                    best[d] = (n, path, e["hw"])
        f, bk = best["f"], best["b"]
        roads[(a, b)] = {"fwd": f[0] if f else 0, "bwd": bk[0] if bk else 0,
                         "gf": f[1] if f else None, "gb": bk[1] if bk else None,
                         "hw": min((x[2] for x in (f, bk) if x), key=ORDER.index)}

    # 6. сжатие узлов степени 2
    def adj():
        m = defaultdict(list)
        for k in roads:
            m[k[0]].append(k)
            m[k[1]].append(k)
        return m

    def orient(k, start):
        """Дорога k глядя от узла start: полосы туда и обратно и пути по ходу движения."""
        d = roads[k]
        if k[0] == start:
            return d["fwd"], d["bwd"], d["gf"], d["gb"]
        return d["bwd"], d["fwd"], d["gb"], d["gf"]

    changed = True
    while changed:
        changed = False
        for c, ks in adj().items():
            if len(ks) != 2 or ks[0] == ks[1]:
                continue
            r1, r2 = ks
            o1 = r1[0] if r1[1] == c else r1[1]
            o2 = r2[0] if r2[1] == c else r2[1]
            if o1 == o2:
                continue
            f1, b1, g1f, g1b = orient(r1, o1)       # o1 → c и c → o1
            f2, b2, g2f, g2b = orient(r2, c)        # c → o2 и o2 → c
            f = min(f1, f2) if f1 and f2 else 0
            b = min(b1, b2) if b1 and b2 else 0
            if not f and not b:
                continue
            gf = g1f + g2f[1:] if f else None       # o1 → o2
            gb = g2b + g1b[1:] if b else None       # o2 → o1
            hw = min(roads[r1]["hw"], roads[r2]["hw"], key=ORDER.index)
            del roads[r1], roads[r2]
            a_, b_ = (o1, o2) if o1 < o2 else (o2, o1)
            if o1 < o2:
                new = {"fwd": f, "bwd": b, "gf": gf, "gb": gb, "hw": hw}
            else:
                new = {"fwd": b, "bwd": f, "gf": gb, "gb": gf, "hw": hw}
            old = roads.get((a_, b_))
            if old is None:
                roads[(a_, b_)] = new
            else:
                # вторая проезжая часть уже есть: добираем недостающее направление
                for lanes, g in (("fwd", "gf"), ("bwd", "gb")):
                    if not old[lanes] and new[lanes]:
                        old[lanes], old[g] = new[lanes], new[g]
            changed = True
            break

    # 7. самая большая связная часть
    m = adj()
    seen, comps = set(), []
    for c in m:
        if c in seen:
            continue
        stack, comp = [c], set()
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            stack.extend(k[0] if k[1] == x else k[1] for k in m[x])
        seen |= comp
        comps.append(comp)
    def road_len(k):
        return _length(roads[k]["gf"] or roads[k]["gb"])

    keep = max(comps, key=lambda s: sum(road_len(k) for k in roads if k[0] in s))
    roads = {k: v for k, v in roads.items() if k[0] in keep}
    m = adj()

    # 8. сборка описания мира
    # ось и разделительная полоса: среднее двух проезжих частей
    for k, d in roads.items():
        a, b = k
        gf, gb = d["gf"], d["gb"]
        if gf and gb:
            rb = gb[::-1]                                   # путь b → a развёрнут в a → b
            samples = [(_sample(gf, i / 8), _sample(rb, i / 8)) for i in range(9)]
            sep = sum(_dist(p, q) for p, q in samples[1:-1]) / 7
            d["median"] = max(0.0, min(30.0, sep - (d["fwd"] + d["bwd"]) * LANE_W / 2))
            axis = [tuple((x + y) / 2 for x, y in zip(p, q)) for p, q in samples]
            axis[0], axis[-1] = cpos[a], cpos[b]
        else:
            d["median"] = 0.0
            axis = gf or gb[::-1]
        d["shape"] = _simplify(axis)[1:-1]

    def arm_angle(c, k):
        d = roads[k]
        pts = [cpos[k[0]], *d["shape"], cpos[k[1]]]
        if k[1] == c:
            pts = pts[::-1]
        return math.atan2(pts[1][1] - cpos[c][1], pts[1][0] - cpos[c][0])

    def moves_at(c, k):
        """Какие движения возможны у подхода по дороге k в узле c (с учётом полос выезда)."""
        mv = {x: False for x in ("left", "straight", "right")}
        for x, target in _classify(arm_angle(c, k) + math.pi, [(arm_angle(c, kk), kk) for kk in m[c] if kk != k]).items():
            mv[x] = bool(roads[target]["fwd"] if target[0] == c else roads[target]["bwd"])
        return mv

    def inbound(c, k):
        d = roads[k]
        return d["bwd"] if k[0] == c else d["fwd"]

    def set_inbound(c, k, n):
        d = roads[k]
        d["bwd" if k[0] == c else "fwd"] = n

    # подход, из которого некуда ехать, убираем вместе с его полосами; повторяем, пока что-то меняется
    settled = False
    while not settled:
        settled = True
        for c in [c for c in m if len(m[c]) >= 3]:
            for k in m[c]:
                if inbound(c, k) and not any(moves_at(c, k).values()):
                    set_inbound(c, k, 0)
                    settled = False
    for k in [k for k, d in roads.items() if not d["fwd"] and not d["bwd"]]:
        del roads[k]
    m = adj()

    def lanes_in(c, k, n):
        """Полосы, входящие в узел c по дороге k."""
        if n == 0:
            return []
        if len(m[c]) < 3:
            return [{"width": LANE_W} for _ in range(n)]
        mv = moves_at(c, k)
        M = [x for x in ("right", "straight", "left") if mv[x]]
        if n >= len(M):
            lanes = [[x] for x in M]
            idx = M.index("straight") if "straight" in M else len(M) // 2
            for _ in range(n - len(M)):
                lanes.insert(idx, [M[idx]])
        elif n == 1:
            lanes = [M]
        else:
            lanes = [[x for x in ("right", "straight") if x in M] or ["right"],
                     [x for x in ("left", "straight") if x in M] or ["left"]]
        return [{"width": LANE_W, "turns": t} for t in lanes]

    ids = {}
    wn = {}
    for c in sorted(m):
        deg = len(m[c])
        kind = "signal" if deg >= 3 else "boundary"
        ids[c] = ("j" if kind == "signal" else "b") + str(len(ids) + 1)
        wn[ids[c]] = {"pos": [round(cpos[c][0], 1), round(cpos[c][1], 1)], "kind": kind}

    wroads = {}
    for k, d in roads.items():
        a, b = k
        r = {"from": ids[a], "to": ids[b], "speed": SPEED[d["hw"]],
             "forward": lanes_in(b, k, d["fwd"]), "backward": lanes_in(a, k, d["bwd"]),
             "sidewalk": {"left": 3.0, "right": 3.0}}
        if d["median"] > 0.4:
            r["median"] = {"width": round(d["median"], 1)}
        if d["shape"]:
            r["shape"] = [[round(p[0], 1), round(p[1], 1)] for p in d["shape"]]
        wroads[f"r_{ids[a]}_{ids[b]}"] = r
    junctions = {i: {"crosswalks": "auto", "signal": "auto"} for i, n in wn.items() if n["kind"] == "signal"}
    return {"format": "loom-traffic/world", "version": 1, "name": name,
            "nodes": wn, "roads": wroads, "junctions": junctions}


def main():
    ap = argparse.ArgumentParser(description="Район из OpenStreetMap")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--bbox", required=True, help="юг,запад,север,восток")
    f.add_argument("--out", required=True)
    c = sub.add_parser("convert")
    c.add_argument("src")
    c.add_argument("--center", required=True, help="широта,долгота — начало координат")
    c.add_argument("--window", required=True, help="x0,y0,x1,y1 в метрах от центра")
    c.add_argument("--name", default="Район из OpenStreetMap")
    c.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "fetch":
        fetch(a.bbox, a.out)
        return
    world = convert(json.load(open(a.src)), tuple(map(float, a.center.split(","))), tuple(map(float, a.window.split(","))), a.name)
    json.dump(world, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"узлов {len(world['nodes'])}, дорог {len(world['roads'])}")


if __name__ == "__main__":
    main()
