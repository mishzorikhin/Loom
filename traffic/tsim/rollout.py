"""Прогон политик через среду обучения: образец цикла и эталоны для сравнения.

    python3 -m tsim.rollout --world grid2 --policy random,hold,max_pressure --episodes 3 --minutes 20
    python3 -m tsim.rollout --world irregular --policy mypkg.mymodule:policy      # своя политика

Политика — функция `policy(env, obs, rng) -> {id перекрёстка: действие}`; `obs` — результат `env.reset()` или
`env.step()`, действие — номер фазы или словарь `{"phase", "yellow", "all_red", "ped_flash"}`.
Нейросеть подключается так же: берёт `obs[jid]` и `env.action_mask(jid)`, возвращает номер фазы.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import random
import statistics
from dataclasses import asdict

import numpy as np

from .env import ObservationSpec, TrafficEnv
from .signals import FixedTime, MaxPressure
from .sim import DT

KEYS = ("done", "delay", "queue_mean", "cars", "blocked_spawn", "crashes", "near_total", "ped_wait", "ped_waiting_mean", "stuck")


def fixed_policy(env: TrafficEnv, obs, rng: random.Random) -> dict:
    """Тот же фиксированный контроллер, что на странице: работает каждый шаг ядра."""
    if not isinstance(env.sim.controller, FixedTime):
        env.sim.controller = FixedTime()
    return {}


def automatic_max_pressure_policy(env: TrafficEnv, obs, rng: random.Random) -> dict:
    """Тот же max-pressure, что на странице (включая защиту от голодания фаз)."""
    if not isinstance(env.sim.controller, MaxPressure):
        env.sim.controller = MaxPressure()
    return {}


def random_policy(env: TrafficEnv, obs, rng: random.Random) -> dict:
    """Случайная допустимая фаза (по маске)."""
    out = {}
    for jid in env.agents:
        legal = np.flatnonzero(env.action_mask(jid))
        out[jid] = int(rng.choice(list(legal)))
    return out


def hold_policy(env: TrafficEnv, obs, rng: random.Random) -> dict:
    """Никогда не переключает: остаётся на первой фазе (нижняя граница качества)."""
    return {jid: env.sim.signals[jid].phase for jid in env.agents}


def max_pressure_policy(env: TrafficEnv, obs, rng: random.Random) -> dict:
    """Фаза с наибольшим давлением из `junction_obs` (упрощённый max-pressure, решение раз в `decision`)."""
    out = {}
    for jid in env.agents:
        o = env.sim.junction_obs(jid)
        mask = env.action_mask(jid)
        cur = env.sim.signals[jid].phase
        best = max((k for k in range(env.n_actions(jid)) if mask[k]), key=lambda k: o["phase_pressure"][k] + (1.0 if k == cur else 0.0))
        out[jid] = best
    return out


POLICIES = {"fixed": fixed_policy, "automatic_max_pressure": automatic_max_pressure_policy,
            "random": random_policy, "hold": hold_policy, "max_pressure": max_pressure_policy}


def load_policy(spec: str):
    if spec in POLICIES:
        return POLICIES[spec]
    mod, _, fn = spec.partition(":")
    return getattr(importlib.import_module(mod), fn)


def episode(env: TrafficEnv, policy, seed: int, rng: random.Random) -> dict:
    obs = env.reset(seed=seed)
    done, ret, ignored, steps = False, 0.0, 0, 0
    queue_sum = ped_sum = 0.0
    info = {}
    while not done:
        obs, rewards, done, info = env.step(policy(env, obs, rng))
        ret += sum(rewards.values())
        ignored += sum(info["ignored"].values())
        queue_sum += sum(info["queue"].values())
        ped_sum += sum(info["ped_waiting"].values())
        steps += 1
    m = dict(info["metrics"])
    m["near_total"] = sum(m["near"].values())
    m["return"] = ret
    m["ignored_share"] = ignored / max(1, steps * len(env.agents))
    m["queue_mean"] = queue_sum / steps
    m["ped_waiting_mean"] = ped_sum / steps
    return m


def main():
    ap = argparse.ArgumentParser(description="Прогон политик через среду обучения")
    ap.add_argument("--world", default="grid2")
    ap.add_argument("--policy", default="random,hold,max_pressure", help="fixed, automatic_max_pressure, random, hold, max_pressure или модуль:функция")
    ap.add_argument("--episodes", type=int, default=3)
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--decision", type=float, default=5.0)
    ap.add_argument("--demand", type=float, default=1.0)
    ap.add_argument("--peds", type=float, default=1.0)
    ap.add_argument("--timing", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=1, help="первое зерно; последующие идут подряд")
    ap.add_argument("--layout-worlds", help="миры через запятую для общей раскладки модели, например cross,grid2,irregular")
    ap.add_argument("--json", action="store_true", help="результаты каждого зерна и средние со стандартным отклонением")
    ap.add_argument("--start-hour", type=float, default=7.5)
    a = ap.parse_args()
    if a.episodes < 1 or not math.isfinite(a.minutes) or a.minutes <= 0 or not math.isfinite(a.decision) or a.decision < DT:
        ap.error(f"нужны episodes >= 1, minutes > 0 и decision >= {DT} с")
    obs_spec = ObservationSpec.from_worlds(a.layout_worlds.split(",")) if a.layout_worlds else None
    env = TrafficEnv(a.world, decision=a.decision, episode=a.minutes * 60, demand=a.demand,
                     peds=a.peds, timing_scale=a.timing, start_hour=a.start_hour, obs_spec=obs_spec)
    cols = ("return",) + KEYS + ("ignored_share",)
    report = {"settings": {"world": a.world, "world_hash": env.net.hash, "minutes": a.minutes, "decision": a.decision,
                           "demand": a.demand, "peds": a.peds, "timing": a.timing,
                           "start_hour": a.start_hour, "seeds": list(range(a.seed, a.seed + a.episodes)),
                           "obs_spec": asdict(env.obs_spec)}, "policies": {}}
    for spec in a.policy.split(","):
        spec = spec.strip()
        pol = load_policy(spec)
        rows = [{"seed": seed, **episode(env, pol, seed, random.Random(seed))}
                for seed in report["settings"]["seeds"]]
        summary = {k: {"mean": statistics.mean(float(r[k]) for r in rows),
                       "std": statistics.pstdev(float(r[k]) for r in rows)} for k in cols}
        report["policies"][spec] = {"runs": rows, "summary": summary}
    if a.json:
        print(json.dumps(report, ensure_ascii=False))
        return
    print(f"мир {a.world}: {len(env.agents)} перекрёстков, наблюдение {env.obs_size}, действий до {env.max_actions}, {a.minutes:g} мин, решение раз в {a.decision:g} с, зёрна {a.seed}..{a.seed + a.episodes - 1}")
    print(f"{'политика':<14}" + "".join(f"{k:>20}" for k in cols))
    for spec, result in report["policies"].items():
        cells = [f"{result['summary'][k]['mean']:.2f} ±{result['summary'][k]['std']:.2f}" for k in cols]
        print(f"{spec:<14}" + "".join(f"{c:>20}" for c in cells))


if __name__ == "__main__":
    main()
