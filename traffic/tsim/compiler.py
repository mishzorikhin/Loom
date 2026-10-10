"""Компилятор: описание мира (JSON) → скомпилированная сеть.

Сеть — единственный источник и для симуляции, и для отрисовки. Правила
вывода описаны в docs/world-format.md.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .geom import Polyline, Pt, add, angle, bezier, hull, left, line_meet, mul, quad, sub, unit, wrap

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "world.schema.json"

KERB_RADIUS = 4.0      # радиус скругления бордюра на углу перекрёстка, м
STOP_GAP = 1.0         # от перехода до стоп-линии, м
TURN_LAT_ACC = 2.2     # боковое ускорение на повороте, м/с²
DEFAULT_BOUNDS = {"green": [5, 90], "yellow": [0, 6], "all_red": [0, 4], "ped_flash": [0, 20]}


class CompileError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass
class Conflict:
    other: str            # 'link' или 'cw'
    other_idx: int
    s_self: float         # положение точки на своём пути
    s_other: float        # положение точки на другом пути
    kind: str             # 'cross', 'merge', 'ped'
    rule: str = "protected"   # 'protected' или 'yield'


@dataclass
class Stop:
    s: float
    junction: str
    group: str
    cw: int


@dataclass
class Link:
    idx: int
    id: str
    kind: str             # 'lane' или 'conn'
    poly: Polyline
    speed: float
    width: float
    road: str = ""
    side: str = ""
    index: int = 0
    turns: list[str] = field(default_factory=list)
    from_node: str = ""
    to_node: str = ""
    pocket: float = 0.0   # длина кармана, 0 — полоса на всю длину
    next: list[int] = field(default_factory=list)
    prev: list[int] = field(default_factory=list)
    movement: str = ""
    junction: str = ""
    group: str = ""
    from_lane: int = -1
    to_lane: int = -1
    left: int = -1        # соседняя попутная полоса слева
    right: int = -1
    change_zone: dict[int, tuple[float, float]] = field(default_factory=dict)  # сосед → (d_min, d_max) до конца
    conflicts: list[Conflict] = field(default_factory=list)
    stops: list[Stop] = field(default_factory=list)
    entry: str = ""       # узел boundary, с которого полоса начинается
    exit: str = ""        # узел boundary, в который полоса уходит

    @property
    def length(self) -> float:
        return self.poly.length


@dataclass
class Crosswalk:
    idx: int
    id: str
    junction: str
    road: str
    axis: Polyline
    width: float
    group: str = ""
    edge: int = -1
    conflicts: list[Conflict] = field(default_factory=list)


@dataclass
class SwNode:
    idx: int
    id: str
    pos: Pt
    boundary: bool = False
    edges: list[int] = field(default_factory=list)


@dataclass
class SwEdge:
    idx: int
    a: int
    b: int
    poly: Polyline
    kind: str             # 'walk', 'corner', 'cross'
    cw: int = -1
    width: float = 3.0


@dataclass
class Group:
    name: str
    kind: str             # 'car' или 'ped'
    links: list[int] = field(default_factory=list)
    crosswalks: list[int] = field(default_factory=list)


@dataclass
class Junction:
    id: str
    kind: str             # 'signal' или 'midblock'
    pos: Pt
    groups: dict[str, Group] = field(default_factory=dict)
    phases: list[dict] = field(default_factory=list)
    bounds: dict[str, list[float]] = field(default_factory=dict)
    arms: list[dict] = field(default_factory=list)
    polygon: list[Pt] = field(default_factory=list)
    links: list[int] = field(default_factory=list)       # коннекторы перекрёстка
    approaches: list[int] = field(default_factory=list)  # полосы подхода
    crosswalks: list[int] = field(default_factory=list)
    safe: dict[str, float] = field(default_factory=dict)  # безопасные длительности по геометрии


@dataclass
class Net:
    world: dict
    hash: str
    links: list[Link]
    crosswalks: list[Crosswalk]
    sw_nodes: list[SwNode]
    sw_edges: list[SwEdge]
    junctions: dict[str, Junction]
    boundaries: dict[str, dict]
    render: dict

    def link(self, lid: str) -> Link:
        for l in self.links:
            if l.id == lid:
                return l
        raise KeyError(lid)


# ---------------------------------------------------------------- загрузка


def load_world(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_schema(world: dict) -> list[str]:
    try:
        import jsonschema
    except ImportError:  # схема — дополнительная проверка, компилятор проверяет смысл сам
        return []
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    v = jsonschema.Draft202012Validator(schema)
    out = []
    for e in sorted(v.iter_errors(world), key=lambda e: list(e.path)):
        path = "/".join(str(p) for p in e.path) or "(корень)"
        out.append(f"{path}: {e.message}")
    return out


# ---------------------------------------------------------------- компилятор


class _Builder:
    def __init__(self, world: dict):
        self.w = world
        self.errors: list[str] = []
        self.links: list[Link] = []
        self.crosswalks: list[Crosswalk] = []
        self.sw_nodes: list[SwNode] = []
        self.sw_edges: list[SwEdge] = []
        self.junctions: dict[str, Junction] = {}
        self.render: dict = {"roads": [], "junctions": [], "sidewalks": [], "medians": [], "lines": [],
                             "arrows": [], "stops": [], "zebras": [], "hatches": [], "heads": []}
        self.nodes = {k: (tuple(v["pos"]), v["kind"]) for k, v in world["nodes"].items()}
        self.roads = world["roads"]
        self.jspec = world.get("junctions", {})
        self.road_geo: dict[str, dict] = {}
        self.arms: dict[str, list[dict]] = {}
        self.lane_of: dict[tuple[str, str, int], int] = {}
        self.sw_key: dict[str, int] = {}

    def err(self, msg: str):
        self.errors.append(msg)

    # -- дороги и лучи

    def build_roads(self):
        for rid, r in self.roads.items():
            for end in ("from", "to"):
                if r[end] not in self.nodes:
                    self.err(f"roads/{rid}/{end}: нет узла «{r[end]}»")
            if r["from"] == r["to"]:
                self.err(f"roads/{rid}: дорога начинается и кончается в одном узле")
        if self.errors:
            return
        for rid, r in self.roads.items():
            pts = [self.nodes[r["from"]][0], *[tuple(p) for p in r.get("shape", [])], self.nodes[r["to"]][0]]
            axis = Polyline(pts)
            med = r.get("median", {}).get("width", 0.0)
            fw = [l.get("width", 3.5) for l in r["forward"]]
            bw = [l.get("width", 3.5) for l in r["backward"]]
            sw = r.get("sidewalk", {})
            self.road_geo[rid] = {
                "axis": axis,
                "med": med,
                "hw_right": med / 2 + sum(fw),
                "hw_left": med / 2 + sum(bw),
                "sw_left": sw.get("left", 3.0),
                "sw_right": sw.get("right", 3.0),
                "speed": r.get("speed", 13.9),
                "solid": r.get("solid_before_stop", 30.0),
            }
            if not r["forward"] and not r["backward"]:
                self.err(f"roads/{rid}: у дороги нет полос")

        for nid, (pos, kind) in self.nodes.items():
            arms = []
            for rid, r in self.roads.items():
                g = self.road_geo[rid]
                if r["from"] == nid:
                    out = g["axis"].dir(0)
                    arms.append({"road": rid, "at": "from", "out": out,
                                 "hw_out": g["hw_right"], "hw_in": g["hw_left"],
                                 "sw_R": g["sw_right"], "sw_L": g["sw_left"],
                                 "out_side": "forward", "in_side": "backward"})
                if r["to"] == nid:
                    d = g["axis"].dir(g["axis"].length)
                    out = (-d[0], -d[1])
                    arms.append({"road": rid, "at": "to", "out": out,
                                 "hw_out": g["hw_left"], "hw_in": g["hw_right"],
                                 "sw_R": g["sw_left"], "sw_L": g["sw_right"],
                                 "out_side": "backward", "in_side": "forward"})
            arms.sort(key=lambda a: angle(a["out"]))
            self.arms[nid] = arms
            if kind == "boundary" and len(arms) != 1:
                self.err(f"nodes/{nid}: у края сети должна быть ровно одна дорога, а их {len(arms)}")
            if kind == "signal":
                if len(arms) < 3:
                    self.err(f"nodes/{nid}: у перекрёстка со светофором меньше трёх лучей")
                if not isinstance(self.jspec.get(nid, {}).get("signal"), (dict, str)):
                    self.err(f"junctions/{nid}/signal: нет светофора для узла signal")
        for jid in self.jspec:
            if jid not in self.nodes or self.nodes[jid][1] != "signal":
                self.err(f"junctions/{jid}: узел не существует или не signal")

    def trim(self):
        """Расстояния от центра узла: ядро, переход, стоп-линия."""
        for nid, arms in self.arms.items():
            kind = self.nodes[nid][1]
            spec = self.jspec.get(nid, {})
            cws = spec.get("crosswalks", "auto")
            listed = {}
            if isinstance(cws, list):
                for c in cws:
                    listed[c["arm"]] = c
                    if c["arm"] not in [a["road"] for a in arms]:
                        self.err(f"junctions/{nid}/crosswalks: луч «{c['arm']}» не входит в перекрёсток")
            for a in arms:
                if kind == "boundary":
                    a.update(core=0.0, cw=None, stop=0.0, walk=0.0)
                    continue
                core = 0.0
                for b in arms:
                    if b is a:
                        continue
                    s = abs(math.sin(angle(b["out"]) - angle(a["out"])))
                    if s < 0.26:
                        continue
                    core = max(core, max(b["hw_in"], b["hw_out"]) / max(s, 0.45))
                core += KERB_RADIUS
                has_sw = a["sw_L"] > 0 and a["sw_R"] > 0
                cw = None
                if cws == "auto" and has_sw:
                    cw = {"width": 4.0, "offset": 1.0}
                elif isinstance(cws, list) and a["road"] in listed:
                    c = listed[a["road"]]
                    cw = {"width": c.get("width", 4.0), "offset": c.get("offset", 1.0)}
                if cw:
                    a.update(core=core, cw=cw, walk=core + cw["offset"] + cw["width"] / 2,
                             stop=core + cw["offset"] + cw["width"] + STOP_GAP)
                else:
                    a.update(core=core, cw=None, walk=core, stop=core + 0.5)

    def arm_of(self, nid: str, rid: str, at: str | None = None) -> dict:
        for a in self.arms[nid]:
            if a["road"] == rid and (at is None or a["at"] == at):
                return a
        raise KeyError((nid, rid))

    def build_lanes(self):
        for rid, r in self.roads.items():
            g = self.road_geo[rid]
            a_from = self.arm_of(r["from"], rid, "from")
            a_to = self.arm_of(r["to"], rid, "to")
            s0, s1 = a_from["stop"], g["axis"].length - a_to["stop"]
            if s1 - s0 < 10:
                self.err(f"roads/{rid}: дорога слишком коротка для своих перекрёстков ({s1 - s0:.1f} м между стоп-линиями)")
                continue
            g["s0"], g["s1"] = s0, s1
            sub_axis = g["axis"].slice(s0, s1)
            g["sub"] = sub_axis
            for side in ("forward", "backward"):
                specs = r[side]
                to_node = r["to"] if side == "forward" else r["from"]
                from_node = r["from"] if side == "forward" else r["to"]
                to_kind = self.nodes[to_node][1]
                offs = []
                for k, l in enumerate(specs):
                    off = g["med"] / 2 + sum(x.get("width", 3.5) for x in specs[k + 1:]) + l.get("width", 3.5) / 2
                    offs.append(off)
                for k, l in enumerate(specs):
                    if side == "forward":
                        poly = sub_axis.offset(-offs[k])
                    else:
                        poly = sub_axis.offset(offs[k]).reversed()
                    pocket = float(l.get("length", 0.0))
                    if pocket:
                        if pocket >= poly.length - 5:
                            self.err(f"roads/{rid}/{side}/{k}: карман длиннее дороги")
                            pocket = 0.0
                        else:
                            poly = poly.slice(poly.length - pocket, poly.length)
                    turns = l.get("turns", [])
                    if to_kind == "signal" and not turns:
                        self.err(f"roads/{rid}/{side}/{k}: у полосы к перекрёстку нет стрелок")
                    if to_kind == "boundary" and turns:
                        self.err(f"roads/{rid}/{side}/{k}: у полосы к краю сети стрелки не задаются")
                    link = Link(idx=len(self.links), id=f"{rid}.{side}.{k}", kind="lane", poly=poly,
                                speed=l.get("speed", g["speed"]), width=l.get("width", 3.5), road=rid,
                                side=side, index=k, turns=list(turns), from_node=from_node, to_node=to_node,
                                pocket=pocket)
                    if to_kind == "boundary":
                        link.exit = to_node
                    if self.nodes[from_node][1] == "boundary" and not pocket:
                        link.entry = from_node
                    self.lane_of[(rid, side, k)] = link.idx
                    self.links.append(link)
                # соседние полосы и зоны перестроения
                solid = g["solid"] if to_kind == "signal" else 0.0
                for k in range(len(specs) - 1):
                    a = self.links[self.lane_of[(rid, side, k)]]
                    b = self.links[self.lane_of[(rid, side, k + 1)]]
                    a.left, b.right = b.idx, a.idx
                    reach = min(a.length, b.length)
                    sol = min(solid, reach * 0.5) if (a.pocket or b.pocket) else solid
                    zone = (sol, reach - 2.0)
                    if zone[1] > zone[0]:
                        a.change_zone[b.idx] = zone
                        b.change_zone[a.idx] = zone

    # -- коннекторы

    def classify(self, nid: str, arm_in: dict) -> dict[str, dict]:
        """Движение → луч выезда."""
        inward = angle(arm_in["out"]) + math.pi
        res: dict[str, dict] = {"uturn": arm_in}
        cand = []
        for b in self.arms[nid]:
            if b is arm_in:
                continue
            cand.append((wrap(angle(b["out"]) - inward), b))
        straight = [c for c in cand if abs(c[0]) < math.radians(40)]
        if straight:
            st = min(straight, key=lambda c: abs(c[0]))
            res["straight"] = st[1]
            cand = [c for c in cand if c[1] is not st[1]]
        lefts = [c for c in cand if c[0] > 0]
        rights = [c for c in cand if c[0] < 0]
        if lefts:
            res["left"] = min(lefts, key=lambda c: c[0])[1]
        if rights:
            res["right"] = max(rights, key=lambda c: c[0])[1]
        return res

    def in_lanes(self, nid: str, arm: dict) -> list[int]:
        r = self.roads[arm["road"]]
        side = arm["in_side"]
        return [self.lane_of[(arm["road"], side, k)] for k in range(len(r[side])) if (arm["road"], side, k) in self.lane_of]

    def out_lanes(self, nid: str, arm: dict) -> list[int]:
        r = self.roads[arm["road"]]
        side = arm["out_side"]
        res = []
        for k in range(len(r[side])):
            li = self.lane_of.get((arm["road"], side, k))
            if li is not None and not self.links[li].pocket:
                res.append(li)
        return res

    def add_conn(self, nid: str, a: int, b: int, movement: str):
        la, lb = self.links[a], self.links[b]
        p0, d0 = la.poly.at(la.length)
        p3, d3 = lb.poly.at(0)
        poly = bezier(p0, d0, p3, d3, 18)
        turn = abs(wrap(angle(d3) - angle(d0)))
        speed = min(la.speed, lb.speed)
        if turn > 0.3:
            radius = poly.length / turn
            speed = min(speed, math.sqrt(TURN_LAT_ACC * radius))
        c = Link(idx=len(self.links), id=f"{nid}:{la.id}>{lb.id}", kind="conn", poly=poly, speed=max(speed, 3.0),
                 width=min(la.width, lb.width), movement=movement, junction=nid, from_lane=a, to_lane=b,
                 from_node=nid, to_node=nid, road=la.road)
        la.next.append(c.idx)
        c.next.append(b)
        c.prev.append(a)
        lb.prev.append(c.idx)
        self.links.append(c)
        self.junctions[nid].links.append(c.idx)
        return c

    def build_connectors(self):
        for nid, (pos, kind) in self.nodes.items():
            if kind != "signal":
                continue
            self.junctions[nid] = Junction(id=nid, kind="signal", pos=pos, arms=self.arms[nid])
            spec = self.jspec.get(nid, {})
            explicit = spec.get("connections", "auto")
            override: dict[int, list[int]] = {}
            if isinstance(explicit, list):
                for i, c in enumerate(explicit):
                    fa = (c["from"]["road"], c["from"]["side"], c["from"]["lane"])
                    ta = (c["to"]["road"], c["to"]["side"], c["to"]["lane"])
                    if fa not in self.lane_of or ta not in self.lane_of:
                        self.err(f"junctions/{nid}/connections/{i}: нет такой полосы")
                        continue
                    la, lb = self.lane_of[fa], self.lane_of[ta]
                    if self.links[la].to_node != nid or self.links[lb].from_node != nid:
                        self.err(f"junctions/{nid}/connections/{i}: полосы не примыкают к узлу")
                        continue
                    override.setdefault(la, []).append(lb)
            for arm in self.arms[nid]:
                ins = self.in_lanes(nid, arm)
                self.junctions[nid].approaches.extend(ins)
                exits = self.classify(nid, arm)
                for mv in ("right", "straight", "left", "uturn"):
                    users = [li for li in ins if mv in self.links[li].turns]
                    if not users:
                        continue
                    if mv not in exits:
                        for li in users:
                            self.err(f"roads/{self.links[li].id}: стрелка {mv}, но у узла {nid} нет выезда в эту сторону")
                        continue
                    outs = self.out_lanes(nid, exits[mv])
                    if not outs:
                        self.err(f"узел {nid}: на луче {exits[mv]['road']} нет полос выезда для движения {mv}")
                        continue
                    pairs = []
                    if mv == "right":
                        for i, li in enumerate(users):
                            pairs.append((li, outs[min(i, len(outs) - 1)]))
                    elif mv in ("left", "uturn"):
                        ru, ro = list(reversed(users)), list(reversed(outs))
                        for i, li in enumerate(ru):
                            pairs.append((li, ro[min(i, len(ro) - 1)]))
                    else:
                        for i, li in enumerate(users):
                            pairs.append((li, outs[min(i, len(outs) - 1)]))
                    for li, lo in pairs:
                        if li in override:
                            continue
                        self.add_conn(nid, li, lo, mv)
                for li in ins:
                    for lo in override.get(li, []):
                        mv = None
                        for m, b in exits.items():
                            if b["road"] == self.links[lo].road:
                                mv = m
                        if mv is None or mv not in self.links[li].turns:
                            self.err(f"junctions/{nid}/connections: соединение {self.links[li].id} → {self.links[lo].id} не совпадает со стрелками полосы")
                            continue
                        self.add_conn(nid, li, lo, mv)

    # -- переходы и тротуары

    def sw_node(self, key: str, pos: Pt, boundary=False) -> int:
        if key in self.sw_key:
            return self.sw_key[key]
        n = SwNode(idx=len(self.sw_nodes), id=key, pos=pos, boundary=boundary)
        self.sw_nodes.append(n)
        self.sw_key[key] = n.idx
        return n.idx

    def sw_edge(self, a: int, b: int, poly: Polyline, kind: str, cw: int = -1, width: float = 3.0) -> int:
        e = SwEdge(idx=len(self.sw_edges), a=a, b=b, poly=poly, kind=kind, cw=cw, width=width)
        self.sw_edges.append(e)
        self.sw_nodes[a].edges.append(e.idx)
        self.sw_nodes[b].edges.append(e.idx)
        return e.idx

    def arm_point(self, nid: str, arm: dict, dist: float, lateral: float) -> Pt:
        """Точка луча: dist от центра вдоль луча, lateral влево от направления наружу."""
        g = self.road_geo[arm["road"]]
        axis = g["axis"]
        s = dist if arm["at"] == "from" else axis.length - dist
        p, d = axis.at(s)
        out = d if arm["at"] == "from" else (-d[0], -d[1])
        return add(p, mul(left(out), lateral))

    def build_walks(self):
        midblocks = self.w.get("midblock_crosswalks", [])
        mb_by_road: dict[str, list[dict]] = {}
        for i, m in enumerate(midblocks):
            if m["road"] not in self.roads:
                self.err(f"midblock_crosswalks/{i}: нет дороги «{m['road']}»")
                continue
            mb_by_road.setdefault(m["road"], []).append(m)

        # узлы тротуаров у перекрёстков и краёв
        for nid, arms in self.arms.items():
            for a in arms:
                for side in ("L", "R"):
                    sw = a[f"sw_{side}"]
                    if sw <= 0:
                        continue
                    hw = a["hw_in"] if side == "L" else a["hw_out"]
                    lat = (hw + sw / 2) * (1 if side == "L" else -1)
                    pos = self.arm_point(nid, a, a["walk"], lat)
                    self.sw_node(f"{nid}.{a['road']}.{a['at']}.{side}", pos, boundary=self.nodes[nid][1] == "boundary")

        # тротуары вдоль дорог (с разрывами на переходах посреди квартала)
        for rid, r in self.roads.items():
            g = self.road_geo[rid]
            if "sub" not in g:
                continue
            a_from = self.arm_of(r["from"], rid, "from")
            a_to = self.arm_of(r["to"], rid, "to")
            for road_side, lat_sign, hw, sw in (("left", 1, g["hw_left"], g["sw_left"]), ("right", -1, g["hw_right"], g["sw_right"])):
                if sw <= 0:
                    continue
                # сторона дороги → сторона луча: у from влево = left дороги, у to наоборот
                k_from = f"{r['from']}.{rid}.from.{'L' if road_side == 'left' else 'R'}"
                k_to = f"{r['to']}.{rid}.to.{'R' if road_side == 'left' else 'L'}"
                stops = [(a_from["walk"], self.sw_key[k_from])]
                for m in sorted(mb_by_road.get(rid, []), key=lambda m: m["at"]):
                    pos = add(g["axis"].point(m["at"]), mul(left(g["axis"].dir(m["at"])), lat_sign * (hw + sw / 2)))
                    stops.append((m["at"], self.sw_node(f"mb.{m['id']}.{road_side}", pos)))
                stops.append((g["axis"].length - a_to["walk"], self.sw_key[k_to]))
                for (sa, na), (sb, nb) in zip(stops, stops[1:]):
                    if sb - sa < 1:
                        continue
                    poly = g["axis"].slice(sa, sb).offset(lat_sign * (hw + sw / 2))
                    self.sw_edge(na, nb, poly, "walk", width=sw)

        # углы и переходы у перекрёстков
        for nid, arms in self.arms.items():
            if self.nodes[nid][1] != "signal":
                continue
            j = self.junctions[nid]
            n = len(arms)
            for i, a in enumerate(arms):
                b = arms[(i + 1) % n]
                ka, kb = f"{nid}.{a['road']}.{a['at']}.L", f"{nid}.{b['road']}.{b['at']}.R"
                if ka in self.sw_key and kb in self.sw_key:
                    pa, pb = self.sw_nodes[self.sw_key[ka]].pos, self.sw_nodes[self.sw_key[kb]].pos
                    ctrl = line_meet(pa, a["out"], pb, b["out"])
                    if ctrl is None or math.dist(ctrl, pa) > 60:
                        ctrl = mul(add(pa, pb), 0.5)
                    self.sw_edge(self.sw_key[ka], self.sw_key[kb], quad(pa, ctrl, pb, 12), "corner",
                                 width=min(a["sw_L"], b["sw_R"]))
                if a["cw"]:
                    kr, kl = f"{nid}.{a['road']}.{a['at']}.R", f"{nid}.{a['road']}.{a['at']}.L"
                    if kr not in self.sw_key or kl not in self.sw_key:
                        continue
                    pr, pl = self.sw_nodes[self.sw_key[kr]].pos, self.sw_nodes[self.sw_key[kl]].pos
                    axis = Polyline([pr, pl])
                    cw = Crosswalk(idx=len(self.crosswalks), id=f"{nid}.cw.{a['road']}", junction=nid,
                                   road=a["road"], axis=axis, width=a["cw"]["width"])
                    self.crosswalks.append(cw)
                    cw.edge = self.sw_edge(self.sw_key[kr], self.sw_key[kl], axis, "cross", cw.idx, a["cw"]["width"])
                    j.crosswalks.append(cw.idx)
                    a["cw_idx"] = cw.idx

        # переходы посреди квартала
        for m in midblocks:
            rid = m["road"]
            if rid not in self.road_geo or "sub" not in self.road_geo[rid]:
                continue
            g = self.road_geo[rid]
            if not (g["s0"] + 8 < m["at"] < g["s1"] - 8):
                self.err(f"midblock_crosswalks/{m['id']}: переход вне дороги или слишком близко к перекрёстку")
                continue
            kl, kr = f"mb.{m['id']}.left", f"mb.{m['id']}.right"
            if kl not in self.sw_key or kr not in self.sw_key:
                self.err(f"midblock_crosswalks/{m['id']}: у дороги нет тротуаров с обеих сторон")
                continue
            pr, pl = self.sw_nodes[self.sw_key[kr]].pos, self.sw_nodes[self.sw_key[kl]].pos
            axis = Polyline([pr, pl])
            jid = f"mb_{m['id']}"
            width = m.get("width", 4.0)
            cw = Crosswalk(idx=len(self.crosswalks), id=f"{jid}.cw", junction=jid, road=rid, axis=axis, width=width,
                           group="ped")
            self.crosswalks.append(cw)
            cw.edge = self.sw_edge(self.sw_key[kr], self.sw_key[kl], axis, "cross", cw.idx, width)
            j = Junction(id=jid, kind="midblock", pos=g["axis"].point(m["at"]),
                         bounds=m.get("bounds", DEFAULT_BOUNDS), crosswalks=[cw.idx])
            j.groups = {"veh": Group("veh", "car"), "ped": Group("ped", "ped", crosswalks=[cw.idx])}
            j.phases = [{"id": "cars", "green": ["veh"]}, {"id": "walk", "green": ["ped"]}]
            r = self.roads[rid]
            for side in ("forward", "backward"):
                for k in range(len(r[side])):
                    li = self.lane_of.get((rid, side, k))
                    if li is None:
                        continue
                    lane = self.links[li]
                    s_cross, _ = lane.poly.project(g["axis"].point(m["at"]))
                    if lane.pocket and (s_cross <= 0.5 or s_cross >= lane.length - 0.5):
                        continue
                    hits = lane.poly.intersections(axis)
                    if not hits:
                        continue
                    s_l, s_c, _ = hits[0]
                    lane.stops.append(Stop(s=max(0.0, s_l - width / 2 - 1.5), junction=jid, group="veh", cw=cw.idx))
                    lane.conflicts.append(Conflict("cw", cw.idx, s_l, s_c, "ped"))
                    cw.conflicts.append(Conflict("link", li, s_c, s_l, "ped"))
                    j.groups["veh"].links.append(li)
                    j.approaches.append(li)
            self.junctions[jid] = j

    # -- светофоры

    def auto_signal(self, nid: str) -> dict:
        """Фазы по умолчанию: по одной на луч (все движения луча) и пешеходы на луче выезда направо."""
        arms = self.arms[nid]
        groups, phases = {}, []
        names = ["e", "ne", "n", "nw", "w", "sw", "s", "se"]
        label: dict[str, str] = {}
        for a in arms:
            base = names[round(angle(a["out"]) / (math.pi / 4)) % 8]
            lab, k = base, 2
            while lab in label.values():
                lab, k = f"{base}{k}", k + 1
            label[a["road"]] = lab
        # пары встречных лучей с отдельными полосами налево получают общие фазы
        def dedicated_left(a):
            ins = self.in_lanes(nid, a)
            lanes = [self.links[i] for i in ins]
            return any(l.turns == ["left"] for l in lanes) and all("left" not in l.turns or l.turns == ["left"] for l in lanes)

        paired = set()
        for i, a in enumerate(arms):
            for b in arms[i + 1:]:
                if abs(abs(wrap(angle(a["out"]) - angle(b["out"]))) - math.pi) < 0.35 and dedicated_left(a) and dedicated_left(b):
                    if a["road"] in paired or b["road"] in paired:
                        continue
                    paired.update([a["road"], b["road"]])
                    tag = "".join(sorted([label[a["road"]], label[b["road"]]], key=lambda x: "nsew".find(x[0])))
                    mv_main, mv_left = [], []
                    for x in (a, b):
                        turns = set()
                        for li in self.in_lanes(nid, x):
                            turns.update(self.links[li].turns)
                        mv_main += [f"{x['road']}:{m}" for m in ("straight", "right") if m in turns]
                        mv_left += [f"{x['road']}:{m}" for m in ("left", "uturn") if m in turns]
                    peds = []
                    for x in (a, b):
                        ex = self.classify(nid, x)
                        if "right" in ex and ex["right"].get("cw"):
                            peds.append(ex["right"]["road"])
                    green = []
                    if mv_main:
                        groups[f"{tag}_main"] = {"movements": mv_main}
                        green.append(f"{tag}_main")
                    if peds:
                        groups[f"ped_{tag}"] = {"crosswalks": sorted(set(peds))}
                        green.append(f"ped_{tag}")
                    if green:
                        phases.append({"id": f"p_{tag}", "green": green})
                    if mv_left:
                        groups[f"{tag}_left"] = {"movements": mv_left}
                        phases.append({"id": f"p_{tag}_left", "green": [f"{tag}_left"]})
        used_cw: set[str] = set()
        for g in groups.values():
            used_cw.update(g.get("crosswalks", []))
        for a in arms:
            if a["road"] in paired:
                continue
            turns = set()
            for li in self.in_lanes(nid, a):
                turns.update(self.links[li].turns)
            if not turns:
                continue
            gname = label[a["road"]]
            groups[gname] = {"movements": [f"{a['road']}:{m}" for m in ("left", "straight", "right", "uturn") if m in turns]}
            green = [gname]
            ex = self.classify(nid, a)
            if "right" in ex and ex["right"].get("cw") and "right" in turns:
                pname = f"ped_{label[ex['right']['road']]}"
                if ex["right"]["road"] not in used_cw:
                    groups[pname] = {"crosswalks": [ex["right"]["road"]]}
                    used_cw.add(ex["right"]["road"])
                if pname in groups:
                    green.append(pname)
            phases.append({"id": f"p_{label[a['road']]}", "green": green})
        # переходы, не попавшие ни в одну фазу, получают отдельную пешеходную фазу
        rest = [a["road"] for a in arms if a.get("cw") and a["road"] not in used_cw]
        if rest:
            groups["ped"] = {"crosswalks": rest}
            phases.append({"id": "p_ped", "green": ["ped"]})
        return {"groups": groups, "phases": phases, "bounds": DEFAULT_BOUNDS}

    def build_signals(self):
        for nid, j in self.junctions.items():
            if j.kind != "signal":
                continue
            spec = self.jspec.get(nid, {}).get("signal", "auto")
            if spec == "auto":
                spec = self.auto_signal(nid)
                j.auto = True
            j.bounds = {k: list(v) for k, v in spec["bounds"].items()}
            for k, (lo, hi) in j.bounds.items():
                if lo > hi:
                    self.err(f"junctions/{nid}/signal/bounds/{k}: нижний предел больше верхнего")
            arm_roads = {a["road"]: a for a in self.arms[nid]}
            owner: dict[int, str] = {}
            cw_owner: dict[int, str] = {}
            for gname, g in spec["groups"].items():
                if "movements" in g:
                    grp = Group(gname, "car")
                    for mvref in g["movements"]:
                        road, mv = mvref.split(":")
                        if road not in arm_roads:
                            self.err(f"junctions/{nid}/signal/groups/{gname}: дорога «{road}» не входит в перекрёсток")
                            continue
                        found = False
                        for ci in j.links:
                            c = self.links[ci]
                            if self.links[c.from_lane].road == road and c.movement == mv:
                                found = True
                                if ci in owner and owner[ci] != gname:
                                    self.err(f"junctions/{nid}/signal: движение {mvref} входит в группы {owner[ci]} и {gname}")
                                owner[ci] = gname
                                c.group = gname
                                if ci not in grp.links:
                                    grp.links.append(ci)
                        if not found:
                            self.err(f"junctions/{nid}/signal/groups/{gname}: у луча {road} нет движения {mv}")
                else:
                    grp = Group(gname, "ped")
                    for road in g["crosswalks"]:
                        a = arm_roads.get(road)
                        if not a or "cw_idx" not in a:
                            self.err(f"junctions/{nid}/signal/groups/{gname}: на луче «{road}» нет перехода")
                            continue
                        ci = a["cw_idx"]
                        if ci in cw_owner:
                            self.err(f"junctions/{nid}/signal: переход {road} входит в группы {cw_owner[ci]} и {gname}")
                        cw_owner[ci] = gname
                        self.crosswalks[ci].group = gname
                        grp.crosswalks.append(ci)
                j.groups[gname] = grp
            for ci in j.links:
                if ci not in owner:
                    c = self.links[ci]
                    self.err(f"junctions/{nid}/signal: движение {self.links[c.from_lane].road}:{c.movement} не входит ни в одну группу")
            for ci in j.crosswalks:
                if ci not in cw_owner:
                    self.err(f"junctions/{nid}/signal: переход {self.crosswalks[ci].road} не входит ни в одну группу")
            ids = set()
            for p in spec["phases"]:
                if p["id"] in ids:
                    self.err(f"junctions/{nid}/signal/phases: повтор фазы {p['id']}")
                ids.add(p["id"])
                for gname in p["green"]:
                    if gname not in j.groups:
                        self.err(f"junctions/{nid}/signal/phases/{p['id']}: нет группы {gname}")
            j.phases = [{"id": p["id"], "green": list(p["green"])} for p in spec["phases"]]

    # -- конфликты

    def build_conflicts(self):
        for nid, j in self.junctions.items():
            if j.kind != "signal":
                continue
            conns = [self.links[i] for i in j.links]
            for i, a in enumerate(conns):
                for b in conns[i + 1:]:
                    if a.from_lane == b.from_lane:
                        continue
                    if a.to_lane == b.to_lane:
                        a.conflicts.append(Conflict("link", b.idx, a.length, b.length, "merge"))
                        b.conflicts.append(Conflict("link", a.idx, b.length, a.length, "merge"))
                        continue
                    for sa, sb, _ in a.poly.intersections(b.poly):
                        a.conflicts.append(Conflict("link", b.idx, sa, sb, "cross"))
                        b.conflicts.append(Conflict("link", a.idx, sb, sa, "cross"))
            for c in conns:
                for ci in j.crosswalks:
                    cw = self.crosswalks[ci]
                    for s_l, s_c, _ in c.poly.intersections(cw.axis):
                        c.conflicts.append(Conflict("cw", ci, s_l, s_c, "ped"))
                        cw.conflicts.append(Conflict("link", c.idx, s_c, s_l, "ped"))
            # правило: конфликт машины с пешеходом в одной фазе — уступить
            for p in j.phases:
                green = set(p["green"])
                for c in conns:
                    if c.group not in green:
                        continue
                    for cf in c.conflicts:
                        if cf.kind == "ped" and self.crosswalks[cf.other_idx].group in green:
                            cf.rule = "yield"
                            for back in self.crosswalks[cf.other_idx].conflicts:
                                if back.other_idx == c.idx:
                                    back.rule = "yield"
                # безопасность фазы: пересечения машин запрещены
                bad = set()
                for c in conns:
                    if c.group not in green:
                        continue
                    for cf in c.conflicts:
                        if cf.kind != "cross":
                            continue
                        o = self.links[cf.other_idx]
                        if o.group in green:
                            key = tuple(sorted([f"{self.links[c.from_lane].road}:{c.movement}", f"{self.links[o.from_lane].road}:{o.movement}"]))
                            bad.add(key)
                for x, y in sorted(bad):
                    self.err(f"junctions/{nid}/signal/phases/{p['id']}: движения {x} и {y} пересекаются в одной фазе")

    def safe_timings(self):
        """Безопасные длительности по геометрии (формула ITE и скорость пешехода)."""
        for nid, j in self.junctions.items():
            v = max((self.links[i].speed for i in j.approaches), default=13.9)
            yellow = 1.0 + v / (2 * 3.0)
            width = 0.0
            for i in j.links:
                width = max(width, self.links[i].length)
            if j.kind == "midblock":
                width = max((self.crosswalks[c].width for c in j.crosswalks), default=4.0)
            all_red = (width + 5.0) / max(v, 5.0)
            flash = max((self.crosswalks[c].axis.length for c in j.crosswalks), default=0.0) / 1.0
            j.safe = {"yellow": round(yellow, 1), "all_red": round(all_red, 1), "ped_flash": round(flash, 1)}

    # -- примитивы отрисовки

    def build_render(self):
        R = self.render
        for rid, r in self.roads.items():
            g = self.road_geo[rid]
            if "sub" not in g:
                continue
            road_axis = g["sub"]
            R["roads"].append({"id": rid, "left": road_axis.offset(g["hw_left"]).to_list(), "right": road_axis.offset(-g["hw_right"]).to_list(),
                               "boundary": [self.nodes[r["from"]][1] == "boundary", self.nodes[r["to"]][1] == "boundary"]})
            if g["med"] > 0:
                R["medians"].append({"pts": road_axis.to_list(), "width": g["med"]})
            else:
                for d in (0.12, -0.12):
                    R["lines"].append({"pts": road_axis.offset(d).to_list(), "style": "solid", "w": 0.12})
            for side in ("forward", "backward"):
                specs = r[side]
                to_node = r["to"] if side == "forward" else r["from"]
                solid = g["solid"] if self.nodes[to_node][1] == "signal" else 0.0
                for k in range(len(specs) - 1):
                    a = self.links[self.lane_of[(rid, side, k)]]
                    b = self.links[self.lane_of[(rid, side, k + 1)]]
                    full = a if not a.pocket else b
                    # граница между полосами: по полосе на всю длину смещением влево на полширины
                    base = self.links[self.lane_of[(rid, side, 0)]]
                    lane_full = full.poly
                    border = lane_full.offset(full.width / 2) if full is a else lane_full.offset(-full.width / 2)
                    L = border.length
                    pocket = max(a.pocket, b.pocket)
                    start_dash = L - pocket if pocket else 0.0
                    sol = min(solid, (L - start_dash) * 0.5) if pocket else solid
                    if start_dash > 0.5:
                        R["lines"].append({"pts": border.slice(0, start_dash).to_list(), "style": "solid", "w": 0.15})
                    if L - sol - start_dash > 1:
                        R["lines"].append({"pts": border.slice(start_dash, L - sol).to_list(), "style": "dashed", "w": 0.15})
                    if sol > 0.5:
                        R["lines"].append({"pts": border.slice(L - sol, L).to_list(), "style": "solid", "w": 0.15})
                    del base
                # штриховка перед карманом
                for k in range(len(specs)):
                    l = self.links[self.lane_of[(rid, side, k)]]
                    if not l.pocket:
                        continue
                    lat = g["med"] / 2 + sum(x.get("width", 3.5) for x in specs[k + 1:]) + l.width / 2
                    full = road_axis.offset(-lat) if side == "forward" else road_axis.offset(lat).reversed()
                    if full.length - l.pocket > 3:
                        R["hatches"].append({"pts": full.slice(0, full.length - l.pocket).to_list(), "width": l.width})
                # стрелки
                for k in range(len(specs)):
                    l = self.links[self.lane_of[(rid, side, k)]]
                    if not l.turns:
                        continue
                    for back in (7.0, 32.0):
                        if back < l.length - 4:
                            p, d = l.poly.at(l.length - back)
                            R["arrows"].append({"pos": [round(p[0], 2), round(p[1], 2)], "dir": round(angle(d), 4), "turns": l.turns})
        for nid, j in self.junctions.items():
            if j.kind != "signal":
                continue
            arms = self.arms[nid]
            pts: list[Pt] = []
            for i, a in enumerate(arms):
                b = arms[(i + 1) % len(arms)]
                pts.append(self.arm_point(nid, a, a["stop"], -a["hw_out"]))
                pts.append(self.arm_point(nid, a, a["stop"], a["hw_in"]))
                pa = self.arm_point(nid, a, a["core"], a["hw_in"])
                pb = self.arm_point(nid, b, b["core"], -b["hw_out"])
                ctrl = line_meet(pa, a["out"], pb, b["out"])
                if ctrl is not None and math.dist(ctrl, pa) < 40 and len(arms) > 2:
                    pts.extend(quad(pa, ctrl, pb, 8).pts)
                else:
                    pts.extend([pa, pb])
            j.polygon = pts
            R["junctions"].append({"id": nid, "pts": [[round(x, 2), round(y, 2)] for x, y in pts]})
            # стоп-линии и светофоры
            for a in arms:
                ins = self.in_lanes(nid, a)
                if not ins:
                    continue
                g = self.road_geo[a["road"]]
                p0 = self.arm_point(nid, a, a["stop"], g["med"] / 2)
                p1 = self.arm_point(nid, a, a["stop"], a["hw_in"])
                R["stops"].append({"pts": [[round(p0[0], 2), round(p0[1], 2)], [round(p1[0], 2), round(p1[1], 2)]], "w": 0.45})
                by_group: dict[str, list[float]] = {}
                for li in ins:
                    lane = self.links[li]
                    lat = (lane.poly.point(lane.length)[0] - self.arm_point(nid, a, a["stop"], 0)[0], lane.poly.point(lane.length)[1] - self.arm_point(nid, a, a["stop"], 0)[1])
                    lat_v = lat[0] * left(a["out"])[0] + lat[1] * left(a["out"])[1]
                    for ci in lane.next:
                        grp = self.links[ci].group
                        if grp:
                            by_group.setdefault(grp, []).append(lat_v)
                pole = self.arm_point(nid, a, a["stop"] - 0.6, a["hw_in"] + 0.8)
                facing = angle(a["out"])
                for grp, lats in sorted(by_group.items(), key=lambda kv: sum(kv[1]) / len(kv[1])):
                    lat = sum(lats) / len(lats)
                    head = self.arm_point(nid, a, a["stop"] - 0.6, lat)
                    movs = sorted({self.links[ci].movement for ci in j.groups[grp].links if self.links[self.links[ci].from_lane].road == a["road"]})
                    R["heads"].append({"junction": nid, "group": grp, "kind": "car", "pos": [round(head[0], 2), round(head[1], 2)],
                                       "pole": [round(pole[0], 2), round(pole[1], 2)], "facing": round(facing, 4), "movements": movs})
        for cw in self.crosswalks:
            R["zebras"].append({"id": cw.id, "pts": cw.axis.to_list(), "width": cw.width})
            for end, other in ((0, 1), (1, 0)):
                p = cw.axis.pts[end]
                q = cw.axis.pts[other]
                d = unit(sub(q, p))
                side = left(d)
                pos = add(p, mul(side, cw.width / 2 + 0.4))
                R["heads"].append({"junction": cw.junction, "group": cw.group, "kind": "ped", "pos": [round(pos[0], 2), round(pos[1], 2)],
                                   "pole": [round(pos[0], 2), round(pos[1], 2)], "facing": round(angle(sub(p, q)), 4)})
        for nid, j in self.junctions.items():
            if j.kind == "midblock":
                cw = self.crosswalks[j.crosswalks[0]]
                for li in j.groups["veh"].links:
                    lane = self.links[li]
                    stop = next(s for s in lane.stops if s.junction == nid)
                    p, d = lane.poly.at(stop.s)
                    a = add(p, mul(left(d), lane.width / 2))
                    b = add(p, mul(left(d), -lane.width / 2))
                    R["stops"].append({"pts": [[round(a[0], 2), round(a[1], 2)], [round(b[0], 2), round(b[1], 2)]], "w": 0.45})
                    pole = add(p, mul(left(d), -(lane.width / 2 + 1.2)))
                    R["heads"].append({"junction": nid, "group": "veh", "kind": "car", "pos": [round(pole[0], 2), round(pole[1], 2)],
                                       "pole": [round(pole[0], 2), round(pole[1], 2)], "facing": round(angle((-d[0], -d[1])), 4), "movements": ["straight"]})
        for e in self.sw_edges:
            if e.kind in ("walk", "corner"):
                R["sidewalks"].append({"pts": e.poly.to_list(), "width": e.width, "kind": e.kind})

    def compile(self) -> Net:
        self.build_roads()
        if self.errors:
            raise CompileError(self.errors)
        self.trim()
        self.build_lanes()
        if self.errors:
            raise CompileError(self.errors)
        self.build_connectors()
        self.build_walks()
        if self.errors:
            raise CompileError(self.errors)
        self.build_signals()
        if self.errors:
            raise CompileError(self.errors)
        self.build_conflicts()
        if self.errors:
            raise CompileError(self.errors)
        self.safe_timings()
        self.build_render()
        boundaries = {}
        for nid, (pos, kind) in self.nodes.items():
            if kind != "boundary":
                continue
            entry = [l.idx for l in self.links if l.kind == "lane" and l.entry == nid]
            exits = [l.idx for l in self.links if l.kind == "lane" and l.exit == nid]
            walk = [n.idx for n in self.sw_nodes if n.boundary and n.id.startswith(f"{nid}.")]
            boundaries[nid] = {"pos": pos, "entry": entry, "exit": exits, "walk": walk}
        digest = hashlib.sha256(json.dumps(self.w, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        xs = [p[0] for p, _ in self.nodes.values()]
        ys = [p[1] for p, _ in self.nodes.values()]
        self.render["bbox"] = [min(xs), min(ys), max(xs), max(ys)]
        return Net(world=self.w, hash=digest, links=self.links, crosswalks=self.crosswalks, sw_nodes=self.sw_nodes,
                   sw_edges=self.sw_edges, junctions=self.junctions, boundaries=boundaries, render=self.render)


def compile_world(world: dict, check_schema: bool = True) -> Net:
    if check_schema:
        errs = validate_schema(world)
        if errs:
            raise CompileError(errs)
    return _Builder(world).compile()


def net_json(net: Net) -> dict:
    """Сеть для страницы: геометрия путей, переходов, тротуаров, перекрёстков и разметки."""
    def r(x):
        return round(x, 3)

    return {
        "hash": net.hash,
        "name": net.world.get("name", ""),
        "links": [{"id": l.id, "kind": l.kind, "pts": l.poly.to_list(), "len": r(l.length), "w": l.width,
                   "speed": r(l.speed), "junction": l.junction, "group": l.group, "movement": l.movement,
                   "turns": l.turns, "from": l.from_lane, "to": l.to_lane, "next": l.next, "conflicts": [[c.other, c.other_idx, r(c.s_self), c.kind, c.rule] for c in l.conflicts]}
                  for l in net.links],
        "crosswalks": [{"id": c.id, "junction": c.junction, "pts": c.axis.to_list(), "width": c.width, "group": c.group,
                        "edge": c.edge} for c in net.crosswalks],
        "sw_edges": [{"pts": e.poly.to_list(), "kind": e.kind, "cw": e.cw} for e in net.sw_edges],
        "junctions": [{"id": j.id, "kind": j.kind, "pos": [r(j.pos[0]), r(j.pos[1])],
                       "groups": [{"name": g.name, "kind": g.kind, "links": g.links, "crosswalks": g.crosswalks} for g in j.groups.values()],
                       "phases": j.phases, "bounds": j.bounds, "safe": j.safe, "approaches": j.approaches}
                      for j in net.junctions.values()],
        "boundaries": {k: {"pos": list(v["pos"])} for k, v in net.boundaries.items()},
        "render": net.render,
    }
