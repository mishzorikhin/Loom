"""Среда обучения: один агент на перекрёсток со светофором.

Интерфейс похож на PettingZoo (parallel API), но без зависимостей:

    env = TrafficEnv("grid", seed=1)
    obs = env.reset()
    while True:
        actions = {jid: policy(o) for jid, o in obs.items()}
        obs, rewards, done, info = env.step(actions)
        if done:
            break

Действие — номер фазы (тот же номер — держать текущую) или словарь
{"phase": k, "yellow": с, "all_red": с, "ped_flash": с}. Длительности
обрезаются по bounds перекрёстка; опасно малые разрешены (вариант B).
Переходы посреди квартала управляются кодом по вызову пешехода.

Подробно — `docs/training.md`: раскладка наблюдения, награда, маска действий, отказы.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .compiler import compile_world
from .signals import External
from .sim import DT, Demand, Sim
from .worlds import world as load_named

LANE_FEATURES = 4      # очередь, машин в 100 м, средняя скорость, ожидание первой
STAGES = ("green", "change", "all_red")
EDGE_FEATURES = ("distance/100", "length/100", "travel_time/10", "lanes/4", "direction.x", "direction.y")
LANE_ATTRS = ("direction.x", "direction.y", "length/100", "speed/15", "width/4", "pocket/100")
MOVEMENTS = ("right", "straight", "left", "uturn")


@dataclass(frozen=True)
class ObservationSpec:
    """Общая ёмкость наблюдений и действий для набора миров, без усечения."""

    max_lanes: int
    max_phases: int
    max_ped: int

    def __post_init__(self):
        for name in ("max_lanes", "max_phases", "max_ped"):
            value = getattr(self, name)
            minimum = 0 if name == "max_ped" else 1
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name}: нужно целое число >= {minimum}")

    @classmethod
    def from_worlds(cls, worlds) -> ObservationSpec:
        """Минимальные общие размеры для списка имён, путей или описаний миров."""
        if isinstance(worlds, (str, dict)):
            raise ValueError("передайте список миров")
        sizes = []
        for world in worlds:
            net = compile_world(load_named(world) if isinstance(world, str) else world)
            sizes.append(cls.from_net(net))
        if not sizes:
            raise ValueError("нужен хотя бы один мир")
        return cls(*(max(getattr(s, k) for s in sizes) for k in ("max_lanes", "max_phases", "max_ped")))

    @classmethod
    def from_net(cls, net) -> ObservationSpec:
        junctions = [j for j in net.junctions.values() if j.kind == "signal"]
        if not junctions:
            raise ValueError("в мире нет перекрёстков со светофором")
        return cls(max(len(j.approaches) for j in junctions), max(len(j.phases) for j in junctions),
                   max(sum(g.kind == "ped" for g in j.groups.values()) for j in junctions))


class TrafficEnv:
    def __init__(self, world: str | dict = "cross", seed: int = 1, decision: float = 5.0, episode: float = 3600.0,
                 demand: float = 1.0, peds: float = 1.0, timing_scale: float = 1.0, start_hour: float = 7.5,
                 weights: dict | None = None, obs_spec: ObservationSpec | None = None):
        self.world = load_named(world) if isinstance(world, str) else world
        self.net = compile_world(self.world)
        self.seed = seed
        self.decision = decision
        self.episode = episode
        self.demand = demand
        self.peds = peds
        self.timing_scale = timing_scale
        self.start_hour = start_hour
        self.w = {"queue": 0.1, "near": 2.0, "crash": 50.0, "ped_wait": 0.05}
        if weights:
            self.w.update(weights)
        self.agents = [jid for jid, j in self.net.junctions.items() if j.kind == "signal"]
        needed = ObservationSpec.from_net(self.net)
        self.obs_spec = obs_spec if obs_spec is not None else needed
        for name in ("max_lanes", "max_phases", "max_ped"):
            if getattr(self.obs_spec, name) < getattr(needed, name):
                raise ValueError(f"obs_spec.{name}={getattr(self.obs_spec, name)}: миру нужно {getattr(needed, name)}")
        self.max_lanes = self.obs_spec.max_lanes
        self.max_phases = self.obs_spec.max_phases
        self.max_ped = self.obs_spec.max_ped
        self.sim: Sim | None = None

    # -- описание пространств

    def n_actions(self, jid: str) -> int:
        return len(self.net.junctions[jid].phases)

    @property
    def max_actions(self) -> int:
        """Ёмкость выхода фаз и маски действий, заданная раскладкой obs_spec."""
        return self.max_phases

    def action_mask(self, jid: str) -> np.ndarray:
        """Какие номера фаз сейчас имеют смысл: текущая (держать) всегда; другие только на зелёной
        стадии после минимального зелёного — иначе запрос перехода игнорируется. Номера за пределами
        числа фаз перекрёстка запрещены."""
        ctl = self.sim.signals[jid]
        mask = np.zeros(self.max_phases, dtype=bool)
        can_switch = ctl.stage == "green" and ctl.green_t >= ctl.min_green()
        for k in range(self.n_actions(jid)):
            mask[k] = k == ctl.phase or can_switch
        return mask

    def obs_layout(self) -> list[str]:
        """Имя каждого элемента вектора наблюдения (длина `obs_size`)."""
        names = []
        for i in range(self.max_lanes):
            names += [f"lane{i}.queue/20", f"lane{i}.count/30", f"lane{i}.speed/15", f"lane{i}.wait/120"]
        names += [f"phase{i}" for i in range(self.max_phases)]
        names += [f"stage.{s}" for s in STAGES]
        names += ["green_t/60"]
        names += [f"ped_group{i}.waiting/10" for i in range(self.max_ped)]
        return names

    @property
    def obs_size(self) -> int:
        return self.max_lanes * LANE_FEATURES + self.max_phases + len(STAGES) + 1 + self.max_ped

    def graph(self) -> dict:
        """Направленный граф светофоров; признаки рёбер в порядке `edges`.

        Параллельные сквозные полосы объединяются по паре узлов. Карманы
        не увеличивают число сквозных полос. Граф не зависит от reset().
        """
        idx = {j: i for i, j in enumerate(self.agents)}
        lanes = {}
        for l in self.net.links:
            if l.kind == "lane" and not l.pocket and l.from_node in idx and l.to_node in idx:
                lanes.setdefault((idx[l.from_node], idx[l.to_node]), []).append(l)
        edges = sorted(lanes)
        features = []
        for i, j in edges:
            a = self.net.junctions[self.agents[i]].pos
            b = self.net.junctions[self.agents[j]].pos
            dx, dy = b[0] - a[0], b[1] - a[1]
            distance = float(np.hypot(dx, dy))
            links = lanes[i, j]
            length = sum(l.length for l in links) / len(links)
            travel = sum(l.length / l.speed for l in links) / len(links)
            features.append([distance / 100, length / 100, travel / 10, len(links) / 4,
                             dx / distance if distance else 0.0, dy / distance if distance else 0.0])
        return {"nodes": list(self.agents), "edges": edges, "edge_features": features,
                "edge_feature_names": list(EDGE_FEATURES)}

    def graph_observation(self) -> dict:
        """Текущее состояние всей сети для графового трансформера (numpy).

        Все строки узлов имеют порядок `nodes == agents`. В attention_mask
        True разрешает внимание: себе и соседям в обоих направлениях.
        feature_mask отличает реальные признаки от дополнения нулями.
        Старые reset()/step() по-прежнему возвращают словари наблюдений.
        """
        if self.sim is None:
            raise RuntimeError("сначала reset()")
        graph = self.graph()
        n = len(self.agents)
        edge_index = np.asarray(graph["edges"], dtype=np.int64).reshape(-1, 2).T.copy()
        attention = np.eye(n, dtype=bool)
        for i, j in graph["edges"]:
            attention[i, j] = attention[j, i] = True
        feature_mask = np.zeros((n, self.obs_size), dtype=bool)
        lane_attr = np.zeros((n, self.max_lanes, len(LANE_ATTRS)), dtype=np.float32)
        phase_lane = np.zeros((n, self.max_phases, self.max_lanes), dtype=bool)
        phase_movement = np.zeros((n, self.max_phases, self.max_lanes, len(MOVEMENTS)), dtype=bool)
        phase_ped = np.zeros((n, self.max_phases, self.max_ped), dtype=bool)
        phase_start = self.max_lanes * LANE_FEATURES
        stage_start = phase_start + self.max_phases
        ped_start = stage_start + len(STAGES) + 1
        for i, jid in enumerate(self.agents):
            junction = self.net.junctions[jid]
            feature_mask[i, :len(junction.approaches) * LANE_FEATURES] = True
            feature_mask[i, phase_start:phase_start + self.n_actions(jid)] = True
            feature_mask[i, stage_start:ped_start] = True
            n_ped = sum(g.kind == "ped" for g in junction.groups.values())
            feature_mask[i, ped_start:ped_start + n_ped] = True
            lane_slots = {li: k for k, li in enumerate(junction.approaches)}
            for li, k in lane_slots.items():
                lane = self.net.links[li]
                dx, dy = lane.poly.at(lane.length)[1]
                lane_attr[i, k] = (dx, dy, lane.length / 100, lane.speed / 15, lane.width / 4, lane.pocket / 100)
            ped_slots = {name: k for k, name in enumerate(
                name for name, group in junction.groups.items() if group.kind == "ped")}
            for p, phase in enumerate(junction.phases):
                for group_name in phase["green"]:
                    group = junction.groups[group_name]
                    if group.kind == "ped":
                        phase_ped[i, p, ped_slots[group_name]] = True
                    else:
                        for li in group.links:
                            link = self.net.links[li]
                            k = lane_slots[link.from_lane]
                            phase_lane[i, p, k] = True
                            phase_movement[i, p, k, MOVEMENTS.index(link.movement)] = True
        return {"nodes": graph["nodes"],
                "x": np.stack([self._obs(jid) for jid in self.agents]),
                "feature_mask": feature_mask,
                "lane_attr": lane_attr,
                "lane_feature_names": list(LANE_ATTRS),
                "lane_mask": feature_mask[:, :phase_start:LANE_FEATURES].copy(),
                "phase_mask": feature_mask[:, phase_start:stage_start].copy(),
                "ped_mask": feature_mask[:, ped_start:].copy(),
                "phase_lane_mask": phase_lane,
                "phase_movement_mask": phase_movement,
                "movement_names": list(MOVEMENTS),
                "phase_ped_mask": phase_ped,
                "edge_index": edge_index,
                "edge_attr": np.asarray(graph["edge_features"], dtype=np.float32).reshape(-1, len(EDGE_FEATURES)),
                "edge_feature_names": graph["edge_feature_names"],
                "attention_mask": attention,
                "action_mask": np.stack([self.action_mask(jid) for jid in self.agents])}

    # -- цикл

    def reset(self, seed: int | None = None) -> dict[str, np.ndarray]:
        if seed is not None:
            self.seed = seed
        self.sim = Sim(self.net, seed=self.seed, controller=External(), demand=Demand(scale=self.demand, peds_scale=self.peds),
                       start_hour=self.start_hour, timing_scale=self.timing_scale)
        self._seen_event = 0
        return {jid: self._obs(jid) for jid in self.agents}

    def step(self, actions: dict[str, int | dict]):
        sim = self.sim
        assert sim is not None, "сначала reset()"
        ignored = {}
        for jid, a in actions.items():
            ctl = sim.signals[jid]
            phase = int(a.get("phase", ctl.phase)) if isinstance(a, dict) else int(a)
            if isinstance(a, dict):
                ok = ctl.request(phase, a.get("yellow"), a.get("all_red"), a.get("ped_flash"))
            else:
                ok = ctl.request(phase)
            ignored[jid] = phase != ctl.phase and not ok and ctl.target != phase
        near = {j: 0 for j in self.agents}
        crash = {j: 0 for j in self.agents}
        q_acc = {j: 0.0 for j in self.agents}
        ped_acc = {j: 0.0 for j in self.agents}
        steps = int(round(self.decision / DT))
        per_second = int(round(1 / DT))
        for i in range(steps):
            sim.step()
            if i % per_second == per_second - 1:
                for jid in self.agents:
                    o = sim.junction_obs(jid)
                    q_acc[jid] += sum(l["queue"] for l in o["lanes"])
                    ped_acc[jid] += o["peds_waiting"]
        for ev in sim.events:
            if ev["id"] <= self._seen_event:
                continue
            jid = ev.get("junction") or self._nearest(ev["pos"])
            if jid in near:
                if ev["kind"] == "near_miss":
                    near[jid] += 1
                elif ev["kind"] == "crash":
                    crash[jid] += 1
        if sim.events:
            self._seen_event = sim.events[-1]["id"]
        obs = {jid: self._obs(jid) for jid in self.agents}
        rewards = {}
        n = max(1, steps // per_second)
        queue = {j: q_acc[j] / n for j in self.agents}
        ped_waiting = {j: ped_acc[j] / n for j in self.agents}
        for jid in self.agents:
            rewards[jid] = -(self.w["queue"] * q_acc[jid] / n + self.w["near"] * near[jid]
                             + self.w["crash"] * crash[jid] + self.w["ped_wait"] * ped_acc[jid] / n)
        done = sim.t >= self.episode
        info = {"t": sim.t, "clock": sim.clock(), "metrics": sim.metrics(), "near": near, "crash": crash,
                "ignored": ignored, "queue": queue, "ped_waiting": ped_waiting}
        return obs, rewards, done, info

    # -- наблюдение

    def _nearest(self, pos) -> str | None:
        best, bd = None, 60.0
        for jid in self.agents:
            p = self.net.junctions[jid].pos
            d = ((p[0] - pos[0]) ** 2 + (p[1] - pos[1]) ** 2) ** 0.5
            if d < bd:
                best, bd = jid, d
        return best

    def _obs(self, jid: str) -> np.ndarray:
        sim = self.sim
        o = sim.junction_obs(jid)
        ctl = sim.signals[jid]
        v = np.zeros(self.obs_size, dtype=np.float32)
        for i, l in enumerate(o["lanes"][: self.max_lanes]):
            k = i * LANE_FEATURES
            v[k: k + LANE_FEATURES] = (l["queue"] / 20.0, l["count"] / 30.0, l["speed"] / 15.0, min(l["wait"], 300) / 120.0)
        k = self.max_lanes * LANE_FEATURES
        v[k + ctl.phase] = 1.0
        k += self.max_phases
        v[k + STAGES.index(ctl.stage)] = 1.0
        k += len(STAGES)
        v[k] = min(ctl.green_t, 180.0) / 60.0
        k += 1
        peds = [g for g in self.net.junctions[jid].groups.values() if g.kind == "ped"]
        for i, g in enumerate(peds[: self.max_ped]):
            v[k + i] = o["ped_groups"].get(g.name, 0) / 10.0
        return v
