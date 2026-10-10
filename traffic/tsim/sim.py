"""Ядро симуляции: машины, пешеходы, светофоры, ДТП и опасные сближения.

Шаг фиксированный, вся случайность от одного зерна, время не привязано к
реальному. Машина движется по одной координате s вдоль пути (полоса или
коннектор); координаты на плоскости нужны только для картинки и событий.
"""

from __future__ import annotations

import heapq
import math
import random
from collections import deque
from dataclasses import dataclass, field

from .compiler import Link, Net
from .signals import CAR_GREEN, CAR_RED, CAR_YELLOW, PED_STOP, PED_WALK, Controller, SignalCtl, make

DT = 0.1
B_MAX = 8.0              # предельное торможение, м/с²
CRASH_CLEAR = 150.0      # сколько стоят участники ДТП до уборки, с
STUCK_LIMIT = 300.0      # стоящая столько машина убирается (как в SUMO), с
LANE_CHANGE_COST = 18.0  # штраф маршрута за перестроение, «метры»
OCC_MARGIN = 1.1         # запас занятости точки конфликта, м

# причины торможения машины (номер передаётся в кадре)
WHY = ["free", "car", "red", "yellow", "lane_change", "merge", "yield_ped", "ped", "conflict", "box", "no_room"]
WHY_INDEX = {w: i for i, w in enumerate(WHY)}

# виды машин: длина, ширина, доля
KINDS = [(4.4, 1.8, 0.42), (3.9, 1.75, 0.2), (4.9, 1.95, 0.2), (4.5, 1.8, 0.1), (5.6, 2.0, 0.05), (11.5, 2.5, 0.03)]
# суточная кривая спроса
PROFILE = [(0, 0.08), (5, 0.1), (6.5, 0.45), (8, 1.0), (9.5, 0.7), (12, 0.6), (15, 0.65), (17.5, 1.0),
           (19, 0.7), (21, 0.35), (23, 0.15), (24, 0.08)]


def profile(hour: float) -> float:
    hour %= 24
    for (h0, v0), (h1, v1) in zip(PROFILE, PROFILE[1:]):
        if h0 <= hour <= h1:
            return v0 + (v1 - v0) * (hour - h0) / (h1 - h0)
    return PROFILE[-1][1]


@dataclass
class Demand:
    cars_per_lane_hour: float = 160.0   # на полосу въезда в пик
    peds_per_cw_hour: float = 45.0      # пешеходов на переход в пик
    scale: float = 1.0                  # общий множитель (ползунок на странице)
    peds_scale: float = 1.0


class Car:
    __slots__ = ("id", "link", "s", "v", "a", "length", "width", "kind", "color", "route", "ptr", "dest",
                 "v0f", "T", "s0", "amax", "b", "reaction", "red_p", "distract_until", "lat", "state", "crash_t",
                 "entered", "prev_link", "decision", "seen", "spawn_t", "free_t", "wait_t", "stop_t", "blink",
                 "ttc_cd", "brake_cd", "covered", "red_run", "flags", "stops", "why")

    def __init__(self, cid: int):
        self.id = cid
        self.state = "drive"
        self.lat = 0.0
        self.a = 0.0
        self.crash_t = 0.0
        self.entered: dict[str, str] = {}
        self.prev_link = -1
        self.decision: dict[int, str] = {}
        self.seen: dict[tuple, float] = {}
        self.wait_t = 0.0
        self.stop_t = 0.0
        self.blink = 0
        self.ttc_cd = 0.0
        self.brake_cd = 0.0
        self.covered: set[tuple] = set()
        self.red_run = False
        self.distract_until = -1.0
        self.flags = 0
        self.stops = 0
        self.why = ""


class Ped:
    __slots__ = ("id", "path", "i", "s", "speed", "off", "state", "wait_t", "patience", "color", "kind",
                 "crash_t", "jay", "spawn_t", "entered")

    def __init__(self, pid: int):
        self.id = pid
        self.i = 0
        self.s = 0.0
        self.state = "walk"
        self.wait_t = 0.0
        self.crash_t = 0.0
        self.jay = False
        self.entered = ""


@dataclass
class Stats:
    spawned: int = 0
    done: int = 0
    travel: float = 0.0
    delay: float = 0.0
    stops: int = 0
    peds_done: int = 0
    ped_wait: float = 0.0
    crashes: int = 0
    crash_causes: dict[str, int] = field(default_factory=dict)
    near: dict[str, int] = field(default_factory=dict)
    red_runs: int = 0
    jaywalks: int = 0
    stuck: int = 0
    hard_brakes: int = 0
    blocked_spawn: int = 0


class Sim:
    def __init__(self, net: Net, seed: int = 1, controller: Controller | str = "fixed", demand: Demand | None = None,
                 start_hour: float = 7.5, timing_scale: float = 1.0, block_box: bool = True):
        self.net = net
        self.seed = seed
        self.rng = random.Random(seed)
        self.t = 0.0
        self.start_hour = start_hour
        self.demand = demand or Demand()
        self.block_box = block_box
        self.timing_scale = timing_scale
        self.controller = make(controller) if isinstance(controller, str) else controller
        self.signals = {jid: SignalCtl(j, timing_scale) for jid, j in net.junctions.items()}
        self.cars: dict[int, Car] = {}
        self.peds: dict[int, Ped] = {}
        self.on: list[list[Car]] = [[] for _ in net.links]
        self.peds_on: dict[int, list[Ped]] = {}
        self.next_id = 1
        self.events: deque = deque(maxlen=400)
        self.event_seq = 0
        self.stats = Stats()
        self.series: list[dict] = []
        self._series_acc = {"done": 0, "crashes": 0, "near": 0, "delay": 0.0}
        self.pet: dict[tuple, tuple[float, int]] = {}
        self._crash_pairs: set[tuple] = set()
        self._car_clock: dict[str, float] = {}
        self._ped_clock = 0.0
        self.ped_calls: dict[str, int] = {}
        self._cost_to: dict[str, list[float]] = {}
        self._prepare_routes()
        self._prepare_walks()
        for b in net.boundaries:
            self._car_clock[b] = self._exp(self._car_rate(b))
        self._ped_clock = self._exp(self._ped_rate())

    # ------------------------------------------------------------ время

    @property
    def hour(self) -> float:
        return (self.start_hour + self.t / 3600.0) % 24

    def clock(self) -> str:
        h = self.hour
        return f"{int(h):02d}:{int((h % 1) * 60):02d}"

    def set_timing_scale(self, k: float):
        self.timing_scale = k
        for ctl in self.signals.values():
            ctl.scale = k

    # ------------------------------------------------------------ маршруты

    def _succ(self, li: int) -> list[tuple[int, float]]:
        l = self.net.links[li]
        out = [(n, self.net.links[n].length / max(self.net.links[n].speed, 1.0)) for n in l.next]
        for nb in l.change_zone:
            out.append((nb, LANE_CHANGE_COST / 10.0))
        return out

    def _prepare_routes(self):
        links = self.net.links
        pred: list[list[tuple[int, float]]] = [[] for _ in links]
        for i in range(len(links)):
            for j, c in self._succ(i):
                pred[j].append((i, c))
        for b, info in self.net.boundaries.items():
            dist = [math.inf] * len(links)
            heap = []
            for li in info["exit"]:
                dist[li] = 0.0
                heap.append((0.0, li))
            heapq.heapify(heap)
            while heap:
                d, u = heapq.heappop(heap)
                if d > dist[u]:
                    continue
                for p, c in pred[u]:
                    nd = d + c
                    if nd < dist[p]:
                        dist[p] = nd
                        heapq.heappush(heap, (nd, p))
            self._cost_to[b] = dist

    def _route(self, start: int, dest: str) -> list[int] | None:
        cost = self._cost_to[dest]
        if math.isinf(cost[start]):
            return None
        route = [start]
        cur = start
        for _ in range(400):
            if self.net.links[cur].exit == dest:
                return route
            opts = [(c + cost[n], n) for n, c in self._succ(cur) if not math.isinf(cost[n])]
            if not opts:
                return None
            best = min(o[0] for o in opts)
            near = [n for c, n in opts if c <= best + 0.35]
            nxt = self.rng.choice(near)
            route.append(nxt)
            cur = nxt
        return None

    # ------------------------------------------------------------ пешеходные пути

    def _prepare_walks(self):
        net = self.net
        self.walk_edges = [e for e in net.sw_edges if e.kind == "walk"]
        self.walk_total = sum(e.poly.length for e in self.walk_edges)

    def _walk_point(self) -> tuple[int, float]:
        r = self.rng.uniform(0, self.walk_total)
        for e in self.walk_edges:
            if r <= e.poly.length:
                return e.idx, r
            r -= e.poly.length
        e = self.walk_edges[-1]
        return e.idx, e.poly.length / 2

    def _walk_path(self, origin: tuple[int, float], target: tuple[int, float]) -> list[tuple[int, int, float, float]] | None:
        """Путь пешехода: список (ребро, направление ±1, начало, конец) в координатах прохода."""
        net = self.net
        e0, s0 = origin
        e1, s1 = target
        E0, E1 = net.sw_edges[e0], net.sw_edges[e1]
        if e0 == e1:
            if s1 >= s0:
                return [(e0, 1, s0, s1)]
            return [(e0, -1, E0.poly.length - s0, E0.poly.length - s1)]
        dist: dict[int, float] = {E0.a: s0, E0.b: E0.poly.length - s0}
        back: dict[int, tuple[int, int] | None] = {E0.a: None, E0.b: None}
        heap = [(dist[E0.a], E0.a), (dist[E0.b], E0.b)]
        heapq.heapify(heap)
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist.get(u, math.inf):
                continue
            for ei in net.sw_nodes[u].edges:
                if ei == e0 or ei == e1:
                    continue
                e = net.sw_edges[ei]
                v = e.b if e.a == u else e.a
                nd = d + e.poly.length + (6.0 if e.kind == "cross" else 0.0)
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    back[v] = (u, ei)
                    heapq.heappush(heap, (nd, v))
        ca = dist.get(E1.a, math.inf) + s1
        cb = dist.get(E1.b, math.inf) + E1.poly.length - s1
        if math.isinf(min(ca, cb)):
            return None
        end_node = E1.a if ca <= cb else E1.b
        chain = []
        u = end_node
        while back.get(u) is not None:
            pu, ei = back[u]
            chain.append((pu, ei, u))
            u = pu
        chain.reverse()
        path = []
        L0 = E0.poly.length
        if u == E0.a:
            path.append((e0, -1, L0 - s0, L0))
        else:
            path.append((e0, 1, s0, L0))
        for pu, ei, v in chain:
            e = net.sw_edges[ei]
            path.append((ei, 1 if e.a == pu else -1, 0.0, e.poly.length))
        L1 = E1.poly.length
        if end_node == E1.a:
            path.append((e1, 1, 0.0, s1))
        else:
            path.append((e1, -1, 0.0, L1 - s1))
        return [p for p in path if p[3] - p[2] > 0.01 or net.sw_edges[p[0]].kind == "cross"]

    # ------------------------------------------------------------ появление

    def _exp(self, rate_per_hour: float) -> float:
        if rate_per_hour <= 1e-6:
            return 1e9
        return self.t + self.rng.expovariate(rate_per_hour / 3600.0)

    def _car_rate(self, b: str) -> float:
        n = len(self.net.boundaries[b]["entry"])
        return n * self.demand.cars_per_lane_hour * self.demand.scale * profile(self.hour)

    def _ped_rate(self) -> float:
        return len(self.net.crosswalks) * self.demand.peds_per_cw_hour * self.demand.peds_scale * self.demand.scale * profile(self.hour)

    def reschedule(self):
        for b in self.net.boundaries:
            self._car_clock[b] = self._exp(self._car_rate(b))
        self._ped_clock = self._exp(self._ped_rate())

    def _spawn_car(self, origin: str) -> bool:
        net = self.net
        dests = [b for b in net.boundaries if b != origin and net.boundaries[b]["exit"]]
        if not dests or not net.boundaries[origin]["entry"]:
            return False
        weights = [len(net.boundaries[b]["exit"]) for b in dests]
        dest = self.rng.choices(dests, weights)[0]
        starts = []
        for li in net.boundaries[origin]["entry"]:
            c = self._cost_to[dest][li]
            if not math.isinf(c):
                starts.append((c, li))
        if not starts:
            return False
        best = min(c for c, _ in starts)
        cand = [li for c, li in starts if c <= best + 2.5]
        self.rng.shuffle(cand)
        for li in cand:
            lst = self.on[li]
            if lst and lst[0].s - lst[0].length < 8.0:
                continue
            route = self._route(li, dest)
            if not route:
                continue
            car = Car(self.next_id)
            self.next_id += 1
            r = self.rng.random()
            acc = 0.0
            for k, (length, width, share) in enumerate(KINDS):
                acc += share
                if r <= acc:
                    break
            car.kind = k
            car.length, car.width = KINDS[k][0], KINDS[k][1]
            car.color = self.rng.randrange(12)
            car.link = li
            car.s = 0.0
            car.route = route
            car.ptr = 0
            car.dest = dest
            car.v0f = min(1.2, max(0.85, self.rng.gauss(1.0, 0.08)))
            car.T = self.rng.uniform(1.0, 1.6)
            car.s0 = 2.0
            car.amax = self.rng.uniform(1.3, 2.1) * (0.6 if k == 5 else 1.0)
            car.b = self.rng.uniform(1.9, 2.7)
            car.reaction = self.rng.uniform(0.6, 1.3)
            car.red_p = 0.03 * self.rng.random() ** 2
            lead = lst[0] if lst else None
            car.v = min(net.links[li].speed * car.v0f, lead.v if lead else 99.0)
            car.spawn_t = self.t
            car.free_t = sum(net.links[x].length / net.links[x].speed for x in route)
            self.cars[car.id] = car
            lst.insert(0, car)
            self.stats.spawned += 1
            return True
        self.stats.blocked_spawn += 1
        return False

    def _spawn_ped(self):
        net = self.net
        if not self.walk_edges:
            return
        # половина приходит с краёв сети, половина «из домов» на тротуарах
        def point():
            ends = [n for b in net.boundaries.values() for n in b["walk"]]
            if ends and self.rng.random() < 0.35:
                n = self.rng.choice(ends)
                e = net.sw_edges[net.sw_nodes[n].edges[0]]
                return e.idx, 0.0 if e.a == n else e.poly.length
            return self._walk_point()

        for _ in range(4):
            o, d = point(), point()
            if o[0] == d[0]:
                continue
            path = self._walk_path(o, d)
            if not path or not any(net.sw_edges[p[0]].kind == "cross" for p in path):
                continue
            p = Ped(self.next_id)
            self.next_id += 1
            p.path = path
            p.i = 0
            p.s = path[0][2]
            slow = self.rng.random() < 0.12
            p.speed = self.rng.uniform(0.7, 0.95) if slow else self.rng.uniform(1.1, 1.6)
            p.off = self.rng.uniform(-0.9, 0.9)
            p.patience = self.rng.uniform(60, 180) if self.rng.random() < 0.3 else 1e9
            p.color = self.rng.randrange(10)
            p.kind = 1 if slow else 0
            p.spawn_t = self.t
            self.peds[p.id] = p
            return

    # ------------------------------------------------------------ сигналы

    def car_signal(self, conn: Link) -> str:
        ctl = self.signals.get(conn.junction)
        return ctl.state.get(conn.group, CAR_GREEN) if ctl else CAR_GREEN

    def peds_waiting(self, jid: str) -> int:
        n = 0
        for ci in self.net.junctions[jid].crosswalks:
            for p in self.peds_on.get(self.net.crosswalks[ci].edge, []):
                if p.state == "wait":
                    n += 1
        return n

    def junction_obs(self, jid: str) -> dict:
        """Наблюдение перекрёстка для контроллеров и среды обучения."""
        net = self.net
        j = net.junctions[jid]
        ctl = self.signals[jid]
        lanes = []
        queue_of: dict[int, float] = {}
        for li in j.approaches:
            link = net.links[li]
            stop_s = link.length
            if j.kind == "midblock":
                stop_s = next((s.s for s in link.stops if s.junction == jid), link.length)
            q, n, vs, first = 0, 0, 0.0, 0.0
            for c in self.on[li]:
                d = stop_s - c.s
                if -1 < d < 100:
                    n += 1
                    vs += c.v
                    if c.v < 1.5 and d < 70:
                        q += 1
                        first = max(first, c.wait_t)
            queue_of[li] = q
            lanes.append({"link": li, "queue": q, "count": n, "speed": round(vs / n, 2) if n else 0.0, "wait": round(first, 1)})
        peds_waiting = 0
        ped_by_group: dict[str, int] = {}
        for ci in j.crosswalks:
            cw = net.crosswalks[ci]
            w = 0
            for p in self.peds_on.get(cw.edge, []):
                if p.state == "wait":
                    w += 1
            peds_waiting += w
            ped_by_group[cw.group] = ped_by_group.get(cw.group, 0) + w
        pressure = []
        for ph in j.phases:
            p = 0.0
            for gname in ph["green"]:
                g = j.groups[gname]
                if g.kind == "car":
                    for ci in g.links:
                        c = net.links[ci]
                        src = c.from_lane if c.kind == "conn" else ci
                        out = len(self.on[c.to_lane]) if c.kind == "conn" and c.to_lane >= 0 else 0
                        share = max(1, len(net.links[src].next)) if c.kind == "conn" else 1
                        p += queue_of.get(src, 0) / share - 0.25 * out / max(1, share)
                else:
                    p += 0.6 * ped_by_group.get(gname, 0)
            pressure.append(round(p, 2))
        return {"junction": jid, "phase": ctl.phase, "stage": ctl.stage, "green_t": ctl.green_t, "lanes": lanes,
                "peds_waiting": peds_waiting, "ped_groups": ped_by_group, "phase_pressure": pressure}

    # ------------------------------------------------------------ события

    def _event(self, kind: str, pos, **kw):
        self.event_seq += 1
        ev = {"id": self.event_seq, "t": round(self.t, 1), "clock": self.clock(), "kind": kind,
              "pos": [round(pos[0], 1), round(pos[1], 1)], **kw}
        self.events.append(ev)
        return ev

    def car_xy(self, c: Car):
        return self.net.links[c.link].poly.point(min(max(c.s, 0.0), self.net.links[c.link].length))

    def ped_xy(self, p: Ped):
        e, d, a, b = p.path[p.i]
        poly = self.net.sw_edges[e].poly
        s = p.s if d > 0 else poly.length - p.s
        return poly.point(min(max(s, 0.0), poly.length))

    def _near(self, kind: str, pos, **kw):
        self.stats.near[kind] = self.stats.near.get(kind, 0) + 1
        self._series_acc["near"] += 1
        self._event("near_miss", pos, sub=kind, **kw)

    # ------------------------------------------------------------ занятость

    def _ped_axis(self, p: Ped) -> float:
        """Положение пешехода по оси его перехода (в координатах ребра)."""
        e, d, a, b = p.path[p.i]
        L = self.net.sw_edges[e].poly.length
        return p.s if d > 0 else L - p.s

    def _cw_occupant(self, cw_idx: int, s_axis: float, radius: float) -> Ped | None:
        cw = self.net.crosswalks[cw_idx]
        for p in self.peds_on.get(cw.edge, []):
            if p.state in ("cross", "crash") and abs(self._ped_axis(p) - s_axis) < radius:
                return p
        return None

    def _cw_yield(self, cw_idx: int, s_axis: float) -> bool:
        """Пешеход на переходе идёт к точке конфликта или рядом с ней."""
        cw = self.net.crosswalks[cw_idx]
        for p in self.peds_on.get(cw.edge, []):
            if p.state not in ("cross", "crash"):
                continue
            e, d, a, b = p.path[p.i]
            pos = self._ped_axis(p)
            ahead = (s_axis - pos) * d
            if -2.2 < ahead < 7.5:
                return True
        return False

    def _link_occupant(self, li: int, s: float, exclude: Car) -> Car | None:
        for c in self.on[li]:
            if c is exclude:
                continue
            if c.s - c.length - OCC_MARGIN <= s <= c.s + OCC_MARGIN:
                return c
        return None

    # ------------------------------------------------------------ машины

    def _idm(self, c: Car, v0: float, gap: float, vl: float) -> float:
        v = c.v
        if gap <= 0.05:
            return -B_MAX
        s_star = c.s0 + max(0.0, v * c.T + v * (v - vl) / (2 * math.sqrt(c.amax * c.b)))
        return c.amax * (1 - (v / max(v0, 0.1)) ** 4 - (s_star / gap) ** 2)

    def _accel(self, c: Car, idx: int) -> float:
        net = self.net
        link = net.links[c.link]
        v0 = link.speed * c.v0f
        acc_min = c.amax * (1 - (c.v / max(v0, 0.1)) ** 4)
        look = max(60.0, c.v * c.v / (2 * c.b) + c.v * 3 + 25)
        seen_now: set = set()
        lane_lead: Car | None = None
        lead_gap = 1e9

        why = "free"

        def obstacle(gap: float, vl: float, hazard=None, reason="car"):
            nonlocal acc_min, lane_lead, lead_gap, why
            if hazard is not None:
                seen_now.add(hazard)
                first = c.seen.get(hazard)
                if first is None:
                    c.seen[hazard] = self.t
                    return
                if self.t - first < (c.reaction if c.v > 4.0 else 0.0):
                    return
            a = self._idm(c, v0, gap, vl)
            if a < acc_min:
                acc_min = a
                why = reason

        lst = self.on[c.link]
        if idx + 1 < len(lst):
            l = lst[idx + 1]
            gap = l.s - l.length - c.s
            obstacle(gap, l.v)
            lane_lead, lead_gap = l, gap

        route = c.route
        pending = c.ptr + 1 < len(route) and route[c.ptr + 1] in link.change_zone
        c.blink = 0
        if pending:
            tgt = route[c.ptr + 1]
            zone = link.change_zone[tgt]
            obstacle(link.length - zone[0] - c.s - 1.0, 0.0, reason="lane_change")
            c.blink = -1 if tgt == link.left else 1

        k = c.ptr
        dist = -c.s
        car_found = lane_lead is not None
        while k < len(route) and dist < look:
            li = route[k]
            L = net.links[li]
            if k > c.ptr:
                if pending:
                    break
                # снижение скорости перед поворотом
                vn = L.speed * c.v0f
                if vn < c.v and dist > 0.5:
                    need = (c.v * c.v - vn * vn) / (2 * dist)
                    if need > 0.4 * c.b and -need < acc_min:
                        acc_min = -min(need, c.b * 1.3)
                if not car_found and self.on[li]:
                    l = self.on[li][0]
                    gap = dist + l.s - l.length
                    obstacle(gap, l.v)
                    lane_lead, lead_gap, car_found = l, gap, True
            # стоп-линии переходов посреди квартала
            for st in L.stops:
                pos = dist + st.s
                if pos < -0.3:
                    continue
                state = self.signals[st.junction].state.get("veh", CAR_GREEN)
                if self._should_stop(c, (li, st.junction), state, pos):
                    obstacle(pos - 0.3, 0.0, reason="red")
                elif pos > 0.8 and lane_lead is not None and lane_lead.v < 2.0:
                    room = lead_gap - pos - net.crosswalks[st.cw].width - 2.5
                    if room < c.length + 1.0:
                        obstacle(pos - 0.3, 0.0, reason="no_room")
            # конфликты впереди
            for ci, cf in enumerate(L.conflicts):
                pos = dist + cf.s_self
                if pos < -0.2 or pos > look:
                    continue
                if cf.kind == "merge":
                    if L.kind != "conn":
                        continue
                    mine = dist + L.length
                    for o in self.on[cf.other_idx]:
                        theirs = net.links[cf.other_idx].length - o.s
                        if theirs < mine - 0.01:
                            obstacle(mine - theirs - o.length, o.v, reason="merge")
                    continue
                if cf.kind == "ped":
                    if cf.rule == "yield" and c.v < 12 and self._cw_yield(cf.other_idx, cf.s_other):
                        obstacle(pos - net.crosswalks[cf.other_idx].width / 2 - 1.0, 0.0, reason="yield_ped")
                    elif self._cw_occupant(cf.other_idx, cf.s_other, 4.5):
                        obstacle(pos - net.crosswalks[cf.other_idx].width / 2 - 0.8, 0.0, hazard=("p", li, ci), reason="ped")
                    continue
                occ = self._link_occupant(cf.other_idx, cf.s_other, c)
                if occ is not None and pos > 0.5:
                    obstacle(pos - OCC_MARGIN - 0.5, 0.0, hazard=("c", li, ci, occ.id), reason="conflict")
                elif pos > 0.5:
                    # машина уже на перекрёстке и доедет до общей точки раньше — пропустить
                    mine = pos / max(c.v, 1.0)
                    for o in self.on[cf.other_idx]:
                        d_o = cf.s_other - o.s
                        if d_o < -OCC_MARGIN or d_o > 25 or o.state == "crash":
                            continue
                        theirs = d_o / max(o.v, 1.0)
                        if theirs < mine or (abs(theirs - mine) < 0.05 and o.id < c.id):
                            obstacle(pos - OCC_MARGIN - 0.5, 0.0, hazard=("a", li, ci, o.id), reason="conflict")
                            break
            # хвосты машин, уже свернувших на соседние коннекторы с этой полосы
            if L.kind == "lane" and L.next and not (k == c.ptr and pending):
                nxt_route = route[k + 1] if k + 1 < len(route) else -1
                for ni in L.next:
                    if ni == nxt_route or not self.on[ni]:
                        continue
                    o = self.on[ni][0]
                    rear = o.s - o.length
                    if rear < 1.0:
                        obstacle(dist + L.length + rear, o.v, reason="car")
            # стоп-линия в конце полосы
            if L.kind == "lane" and k + 1 < len(route) and net.links[route[k + 1]].kind == "conn" and not pending:
                conn = net.links[route[k + 1]]
                pos = dist + L.length
                state = self.car_signal(conn)
                c.blink = c.blink or ({"left": -1, "uturn": -1, "right": 1}.get(conn.movement, 0) if pos < 55 else 0)
                if self._should_stop(c, (li, conn.junction), state, pos):
                    obstacle(pos - 0.6, 0.0, reason="red" if state == CAR_RED else "yellow")
                elif self.block_box and pos > 0.8 and conn.to_lane >= 0:
                    out = self.on[conn.to_lane]
                    if out:
                        tail = out[0]
                        if tail.s - tail.length < c.length + 2.5 and tail.v < 2.0:
                            obstacle(pos - 0.6, 0.0, reason="box")
            if L.kind == "conn" and k == c.ptr:
                c.blink = {"left": -1, "uturn": -1, "right": 1}.get(L.movement, 0)
            dist += L.length
            k += 1

        for key in list(c.seen):
            if key not in seen_now:
                del c.seen[key]
        c.why = why

        if lane_lead is not None and lane_lead.state != "crash" and c.v > 3 and c.v > lane_lead.v + 0.5 and lead_gap > 0:
            ttc = lead_gap / (c.v - lane_lead.v)
            if ttc < 1.5 and self.t > c.ttc_cd:
                c.ttc_cd = self.t + 8.0
                self._near("ttc", self.car_xy(c), cars=[c.id, lane_lead.id], value=round(ttc, 2))
        return max(-B_MAX, min(c.amax, acc_min))

    def _should_stop(self, c: Car, key, state: str, pos: float) -> bool:
        if state == CAR_GREEN:
            c.decision.pop(key, None)
            return False
        dec = c.decision.get(key)
        if dec is None:
            if state == CAR_YELLOW:
                need = c.v * c.v / (2 * max(pos, 0.1))
                dec = "stop" if need <= c.b * 1.25 or c.v < 2 else "go"
            else:
                # ранний красный: редкий водитель проскакивает
                dec = "go" if (pos < c.v * 1.6 and c.v > 6 and self.rng.random() < c.red_p) else "stop"
                if dec == "go":
                    c.red_run = True
            c.decision[key] = dec
        elif state == CAR_RED and dec == "go" and not c.red_run:
            # решил проехать на жёлтый, но не успел: на красном пересчитывает, если ещё далеко
            need = c.v * c.v / (2 * max(pos, 0.1))
            if pos > c.v * 1.2 and need < B_MAX * 0.6:
                c.decision[key] = dec = "stop"
        if dec == "stop" and state == CAR_YELLOW and pos > 0 and c.v * c.v / (2 * max(pos, 0.1)) > B_MAX * 0.8:
            return False
        return dec == "stop"

    def _lane_change(self, c: Car, idx: int) -> bool:
        net = self.net
        link = net.links[c.link]
        if c.ptr + 1 >= len(c.route):
            return False
        tgt = c.route[c.ptr + 1]
        if tgt not in link.change_zone:
            return False
        d = link.length - c.s
        zmin, zmax = link.change_zone[tgt]
        if not (zmin <= d <= zmax):
            return False
        T = net.links[tgt]
        s_t = T.length - d
        if s_t < c.length:
            return False
        lead = foll = None
        for o in self.on[tgt]:
            if o.s > s_t:
                lead = o
                break
            foll = o
        if lead:
            gap = lead.s - lead.length - s_t
            if gap < 2.0 or self._idm(c, T.speed * c.v0f, gap, lead.v) < -3.0:
                return False
        if foll:
            gap = s_t - c.length - foll.s
            if gap < 2.5 or self._idm(foll, T.speed * foll.v0f, gap, c.v) < -2.5:
                return False
        self.on[c.link].remove(c)
        lst = self.on[tgt]
        pos = 0
        while pos < len(lst) and lst[pos].s < s_t:
            pos += 1
        lst.insert(pos, c)
        c.lat = -T.width if tgt == link.left else T.width
        c.link = tgt
        c.s = s_t
        c.ptr += 1
        c.prev_link = -1
        return True

    def _enter_link(self, c: Car, li: int):
        """Машина въехала на путь li: запоминает сигнал на въезде в перекрёсток."""
        L = self.net.links[li]
        if L.kind == "lane":
            c.red_run = False
        if L.kind == "conn":
            state = self.car_signal(L)
            c.entered[L.junction] = state
            if state == CAR_RED:
                self.stats.red_runs += 1
                self._event("red_run", self.car_xy(c), cars=[c.id], junction=L.junction)
            c.decision.pop((c.prev_link, L.junction), None)

    def _step_cars(self):
        net = self.net
        dt = DT
        order = []
        for li, lst in enumerate(self.on):
            for i, c in enumerate(lst):
                order.append((c, i))
        acc: dict[int, float] = {}
        for c, i in order:
            if c.state == "crash":
                acc[c.id] = 0.0
                continue
            a = self._accel(c, i)
            if self.t < c.distract_until:
                a = c.a if c.v > 0.2 else min(a, 0.0)
                c.flags |= 16
            else:
                c.flags &= ~16
                if self.rng.random() < dt / 420.0 and c.v > 5:
                    c.distract_until = self.t + self.rng.uniform(1.0, 2.6)
            acc[c.id] = a
        # перестроения
        for c, i in order:
            if c.state != "crash":
                lst = self.on[c.link]
                self._lane_change(c, lst.index(c))
        removed = []
        for c, _ in order:
            if c.state == "crash":
                continue
            a = acc[c.id]
            c.a = a
            v1 = max(0.0, c.v + a * dt)
            c.s += (c.v + v1) / 2 * dt
            if a < -5 and c.v > 3 and self.t > c.brake_cd:
                c.brake_cd = self.t + 6
                self.stats.hard_brakes += 1
            if c.v >= 1.0 and v1 < 1.0:
                c.stops += 1
            c.v = v1
            if c.v < 0.5:
                c.wait_t += dt
                c.stop_t += dt
            else:
                c.stop_t = 0.0
                if c.v > 3:
                    c.wait_t = 0.0
            if c.lat:
                step = 1.3 * dt
                c.lat = 0.0 if abs(c.lat) <= step else c.lat - math.copysign(step, c.lat)
            # переход на следующий путь
            while c.s > net.links[c.link].length:
                L = net.links[c.link]
                nxt = c.ptr + 1
                if nxt >= len(c.route):
                    removed.append(c)
                    break
                n = c.route[nxt]
                if n in L.change_zone:
                    # не успел перестроиться: перестраивается принудительно в конце полосы
                    T = net.links[n]
                    c.s = T.length - 0.1
                    self.on[c.link].remove(c)
                    self.on[n].append(c)
                    self.on[n].sort(key=lambda x: x.s)
                    c.link, c.ptr = n, nxt
                    continue
                c.s -= L.length
                self.on[c.link].remove(c)
                c.prev_link = c.link
                c.link, c.ptr = n, nxt
                self.on[n].insert(0, c)
                self._enter_link(c, n)
            if c.stop_t > STUCK_LIMIT and c not in removed:
                self.stats.stuck += 1
                self._event("stuck", self.car_xy(c), cars=[c.id])
                removed.append(c)
        for c in removed:
            self._remove_car(c, done=c.stop_t <= STUCK_LIMIT)
        for lst in self.on:
            lst.sort(key=lambda x: x.s)
        for c in self.cars.values():
            f = c.flags & 16
            if c.a < -1.0 or (c.v < 0.3 and c.state == "drive"):
                f |= 1
            if c.state == "crash":
                f |= 2
            if c.blink < 0:
                f |= 4
            elif c.blink > 0:
                f |= 8
            if c.red_run:
                f |= 32
            c.flags = f

    def _remove_car(self, c: Car, done: bool):
        if c in self.on[c.link]:
            self.on[c.link].remove(c)
        self.cars.pop(c.id, None)
        if done and c.state != "crash":
            tt = self.t - c.spawn_t
            self.stats.done += 1
            self.stats.travel += tt
            self.stats.delay += max(0.0, tt - c.free_t)
            self.stats.stops += c.stops
            self._series_acc["done"] += 1
            self._series_acc["delay"] += max(0.0, tt - c.free_t)

    # ------------------------------------------------------------ пешеходы

    def _step_peds(self):
        net = self.net
        dt = DT
        removed = []
        for p in list(self.peds.values()):
            if p.state == "crash":
                continue
            e, d, a, b = p.path[p.i]
            edge = net.sw_edges[e]
            if edge.kind == "cross" and p.state != "cross":
                cw = net.crosswalks[edge.cw]
                ctl = self.signals.get(cw.junction)
                state = ctl.state.get(cw.group, PED_WALK) if ctl else PED_WALK
                go = state == PED_WALK
                if not go and p.wait_t > p.patience and self._gap_ok(cw.idx, d):
                    go = True
                    p.jay = True
                    self.stats.jaywalks += 1
                    self._event("jaywalk", self.ped_xy(p), peds=[p.id], junction=cw.junction)
                if go:
                    p.state = "cross"
                    p.entered = state
                    if p.wait_t > 0:
                        self.stats.ped_wait += p.wait_t
                else:
                    p.state = "wait"
                    p.wait_t += dt
                    continue
            p.s += p.speed * dt
            if p.s >= b:
                over = p.s - b
                p.i += 1
                if p.i >= len(p.path):
                    removed.append(p)
                    continue
                p.state = "walk"
                p.jay = False
                p.wait_t = 0.0 if net.sw_edges[p.path[p.i][0]].kind != "cross" else p.wait_t
                p.s = p.path[p.i][2] + (over if net.sw_edges[p.path[p.i][0]].kind != "cross" else 0.0)
        for p in removed:
            self.peds.pop(p.id, None)
            self.stats.peds_done += 1
        self.peds_on = {}
        for p in self.peds.values():
            self.peds_on.setdefault(p.path[p.i][0], []).append(p)

    def _gap_ok(self, cw_idx: int, direction: int) -> bool:
        """Нетерпеливый пешеход оценивает, успеет ли перейти; оценка с ошибкой."""
        net = self.net
        cw = net.crosswalks[cw_idx]
        need = cw.axis.length / 1.3 * self.rng.uniform(0.35, 1.0)
        for cf in cw.conflicts:
            L = net.links[cf.other_idx]
            for c in self.on[cf.other_idx]:
                d = cf.s_other - c.s
                if 0 < d < 80 and d / max(c.v, 0.5) < need:
                    return False
            for pi in L.prev:
                for c in self.on[pi]:
                    d = net.links[pi].length - c.s + cf.s_other
                    if 0 < d < 80 and d / max(c.v, 0.5) < need and c.v > 2:
                        return False
        return True

    # ------------------------------------------------------------ ДТП и сближения

    def _crash(self, cars: list[Car], peds: list[Ped], kind: str, cause: str, pos, junction: str = ""):
        key = tuple(sorted([("c", x.id) for x in cars] + [("p", x.id) for x in peds]))
        if key in self._crash_pairs:
            return
        self._crash_pairs.add(key)
        for x in cars:
            if x.state != "crash":
                x.state = "crash"
                x.crash_t = self.t
                x.v = 0.0
                x.a = 0.0
        for x in peds:
            x.state = "crash"
            x.crash_t = self.t
        self.stats.crashes += 1
        self.stats.crash_causes[cause] = self.stats.crash_causes.get(cause, 0) + 1
        self._series_acc["crashes"] += 1
        self._event("crash", pos, sub=kind, cause=cause, cars=[x.id for x in cars], peds=[x.id for x in peds], junction=junction)

    def _covers(self, c: Car, s: float, margin: float = OCC_MARGIN) -> bool:
        return c.s - c.length - margin <= s <= c.s + margin

    def _detect(self):
        net = self.net
        # удар сзади на пути и на стыке путей
        for li, lst in enumerate(self.on):
            for f, l in zip(lst, lst[1:]):
                if f.s > l.s - l.length + 0.05 and not (f.state == "crash" and l.state == "crash"):
                    cause = "distraction" if self.t < f.distract_until + 0.5 else "following"
                    self._crash([f, l], [], "rear_end", cause, self.car_xy(l))
            if lst:
                head = lst[0]
                if head.prev_link >= 0 and head.s < head.length and self.on[head.prev_link]:
                    f = self.on[head.prev_link][-1]
                    if f is not head and f.s > net.links[head.prev_link].length - (head.length - head.s) + 0.05 \
                            and not (f.state == "crash" and head.state == "crash"):
                        cause = "distraction" if self.t < f.distract_until + 0.5 else "following"
                        self._crash([f, head], [], "rear_end", cause, self.car_xy(head))
        # конфликты на перекрёстках и переходах
        for c in list(self.cars.values()):
            L = net.links[c.link]
            if not L.conflicts:
                continue
            now: set[tuple] = set()
            for ci, cf in enumerate(L.conflicts):
                if cf.kind == "merge":
                    continue
                if cf.kind == "ped":
                    cw = net.crosswalks[cf.other_idx]
                    if not self._covers(c, cf.s_self, cw.width / 2):
                        continue
                    p = self._cw_occupant(cf.other_idx, cf.s_other, c.width / 2 + 0.35)
                    if p is not None and c.v > 1.0 and p.state != "crash" and c.state != "crash":
                        if p.jay:
                            cause = "pedestrian"
                        elif c.entered.get(cw.junction) == CAR_RED or c.red_run:
                            cause = "red_light"
                        elif cf.rule == "yield":
                            cause = "failed_yield"
                        else:
                            cause = "signal_timing"
                        self._crash([c], [p], "pedestrian", cause, self.ped_xy(p), junction=cw.junction)
                    elif c.state == "drive" and self._cw_occupant(cf.other_idx, cf.s_other, 2.6):
                        if ("pc", c.id, cf.other_idx) not in self.pet:
                            self.pet[("pc", c.id, cf.other_idx)] = (self.t, 0)
                            self._near("pedestrian", self.car_xy(c), cars=[c.id], junction=cw.junction)
                    continue
                if not self._covers(c, cf.s_self):
                    continue
                key = (min(c.link, cf.other_idx), max(c.link, cf.other_idx), round(cf.s_self if c.link < cf.other_idx else cf.s_other, 1))
                now.add(key)
                if key not in c.covered:
                    rec = self.pet.get(key)
                    if rec and rec[1] == cf.other_idx and 0 < self.t - rec[0] < 1.0 and c.state == "drive":
                        self._near("pet", self.car_xy(c), cars=[c.id], value=round(self.t - rec[0], 2), junction=L.junction)
                o = self._link_occupant(cf.other_idx, cf.s_other, c)
                if o is not None and self._covers(o, cf.s_other) and max(o.v, c.v) > 1.0 and not (o.state == "crash" and c.state == "crash"):
                    ea, eb = c.entered.get(L.junction, CAR_GREEN), o.entered.get(L.junction, CAR_GREEN)
                    if CAR_RED in (ea, eb) or c.red_run or o.red_run:
                        cause = "red_light"
                    elif CAR_YELLOW in (ea, eb):
                        cause = "signal_timing"
                    else:
                        cause = "other"
                    self._crash([c, o], [], "side", cause, self.car_xy(c), junction=L.junction)
            for key in c.covered - now:
                self.pet[key] = (self.t, c.link)
            c.covered = now
        if len(self.pet) > 5000:
            self.pet = {k: v for k, v in self.pet.items() if self.t - v[0] < 5}

    def _clear(self):
        for c in list(self.cars.values()):
            if c.state == "crash" and self.t - c.crash_t > CRASH_CLEAR:
                self._remove_car(c, done=False)
        for p in list(self.peds.values()):
            if p.state == "crash" and self.t - p.crash_t > CRASH_CLEAR:
                self.peds.pop(p.id, None)

    # ------------------------------------------------------------ шаг

    def step(self):
        self.t += DT
        for ctl in self.signals.values():
            ctl.tick(DT)
        self.controller.step(self)
        for b in self.net.boundaries:
            while self._car_clock[b] <= self.t:
                self._spawn_car(b)
                self._car_clock[b] = self._exp(self._car_rate(b))
        while self._ped_clock <= self.t:
            self._spawn_ped()
            self._ped_clock = self._exp(self._ped_rate())
        self._step_peds()
        self._step_cars()
        self._detect()
        self._clear()
        if int(self.t / 60) != int((self.t - DT) / 60):
            self._close_minute()

    def run(self, seconds: float):
        for _ in range(int(round(seconds / DT))):
            self.step()

    def _close_minute(self):
        a = self._series_acc
        self.series.append({"t": round(self.t), "clock": self.clock(), "done": a["done"], "crashes": a["crashes"],
                            "near": a["near"], "delay": round(a["delay"] / a["done"], 1) if a["done"] else 0.0,
                            "cars": len(self.cars), "peds": len(self.peds)})
        self.series = self.series[-240:]
        self._series_acc = {"done": 0, "crashes": 0, "near": 0, "delay": 0.0}

    # ------------------------------------------------------------ наружу

    def metrics(self) -> dict:
        s = self.stats
        waiting = sum(1 for c in self.cars.values() if c.v < 0.5 and c.state == "drive")
        return {
            "cars": len(self.cars), "peds": len(self.peds), "spawned": s.spawned, "done": s.done,
            "travel": round(s.travel / s.done, 1) if s.done else 0.0,
            "delay": round(s.delay / s.done, 1) if s.done else 0.0,
            "stops": round(s.stops / s.done, 2) if s.done else 0.0,
            "waiting": waiting, "crashes": s.crashes, "causes": dict(s.crash_causes), "near": dict(s.near),
            "red_runs": s.red_runs, "jaywalks": s.jaywalks, "stuck": s.stuck, "hard_brakes": s.hard_brakes,
            "peds_done": s.peds_done, "ped_wait": round(s.ped_wait / max(1, s.peds_done), 1),
            "blocked_spawn": s.blocked_spawn,
        }

    def frame(self) -> dict:
        cars = []
        for c in self.cars.values():
            cars.append([c.id, c.link, round(c.s, 2), round(c.lat, 2), round(c.v, 1), c.flags, c.kind, c.color,
                         WHY_INDEX.get(c.why, 0), round(self.t - c.spawn_t), round(c.wait_t)])
        peds = []
        for p in self.peds.values():
            e, d, a, b = p.path[p.i]
            L = self.net.sw_edges[e].poly.length
            s = p.s if d > 0 else L - p.s
            st = {"walk": 0, "wait": 1, "cross": 2, "crash": 3}[p.state]
            peds.append([p.id, e, round(s, 2), round(p.off * d, 2), st, p.kind, p.color, d])
        return {"t": round(self.t, 2), "clock": self.clock(), "hour": round(self.hour, 4), "cars": cars, "peds": peds,
                "signals": {jid: ctl.snapshot() for jid, ctl in self.signals.items()}}
