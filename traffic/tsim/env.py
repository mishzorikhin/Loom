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
"""

from __future__ import annotations

import numpy as np

from .compiler import compile_world
from .signals import External
from .sim import Demand, Sim
from .worlds import world as load_named

LANE_FEATURES = 4      # очередь, машин в 100 м, средняя скорость, ожидание первой
STAGES = ("green", "change", "all_red")


class TrafficEnv:
    def __init__(self, world: str | dict = "cross", seed: int = 1, decision: float = 5.0, episode: float = 3600.0,
                 demand: float = 1.0, peds: float = 1.0, timing_scale: float = 1.0, start_hour: float = 7.5,
                 weights: dict | None = None):
        self.world = load_named(world) if isinstance(world, str) else world
        self.net = compile_world(self.world)
        self.seed = seed
        self.decision = decision
        self.episode = episode
        self.demand = demand
        self.peds = peds
        self.timing_scale = timing_scale
        self.start_hour = start_hour
        self.w = {"queue": 0.1, "wait": 0.0, "near": 2.0, "crash": 50.0, "ped_wait": 0.05}
        if weights:
            self.w.update(weights)
        self.agents = [jid for jid, j in self.net.junctions.items() if j.kind == "signal"]
        self.max_lanes = max(len(self.net.junctions[j].approaches) for j in self.agents)
        self.max_phases = max(len(self.net.junctions[j].phases) for j in self.agents)
        self.max_ped = max(sum(1 for g in self.net.junctions[j].groups.values() if g.kind == "ped") for j in self.agents)
        self.sim: Sim | None = None

    # -- описание пространств

    def n_actions(self, jid: str) -> int:
        return len(self.net.junctions[jid].phases)

    @property
    def obs_size(self) -> int:
        return self.max_lanes * LANE_FEATURES + self.max_phases + len(STAGES) + 1 + self.max_ped

    def graph(self) -> dict:
        """Граф перекрёстков для графовой сети: рёбра по дорогам между ними."""
        idx = {j: i for i, j in enumerate(self.agents)}
        edges = set()
        for l in self.net.links:
            if l.kind == "lane" and l.from_node in idx and l.to_node in idx:
                edges.add((idx[l.from_node], idx[l.to_node]))
        return {"nodes": list(self.agents), "edges": sorted(edges)}

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
        for jid, a in actions.items():
            ctl = sim.signals[jid]
            if isinstance(a, dict):
                ctl.request(int(a.get("phase", ctl.phase)), a.get("yellow"), a.get("all_red"), a.get("ped_flash"))
            else:
                ctl.request(int(a))
        near = {j: 0 for j in self.agents}
        crash = {j: 0 for j in self.agents}
        q_acc = {j: 0.0 for j in self.agents}
        steps = int(round(self.decision / 0.1))
        for i in range(steps):
            sim.step()
            if i % 10 == 9:
                for jid in self.agents:
                    q_acc[jid] += sum(l["queue"] for l in sim.junction_obs(jid)["lanes"])
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
        for jid in self.agents:
            o = sim.junction_obs(jid)
            ped_wait = o["peds_waiting"]
            rewards[jid] = -(self.w["queue"] * q_acc[jid] / max(1, steps // 10) + self.w["near"] * near[jid]
                             + self.w["crash"] * crash[jid] + self.w["ped_wait"] * ped_wait)
        done = sim.t >= self.episode
        info = {"t": sim.t, "clock": sim.clock(), "metrics": sim.metrics(), "near": near, "crash": crash}
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
