"""Прогон политик через среду обучения: образец цикла и эталоны для сравнения.

    python3 -m tsim.rollout --world grid2 --policy random,hold,max_pressure --episodes 3 --minutes 20
    python3 -m tsim.rollout --world perm --policy mypkg.mymodule:policy      # своя политика

Политика — функция `policy(env, obs, rng) -> {id перекрёстка: действие}`; `obs` — результат `env.reset()` или
`env.step()`, действие — номер фазы или словарь `{"phase", "yellow", "all_red", "ped_flash"}`.
Нейросеть подключается так же: берёт `obs[jid]` и `env.action_mask(jid)`, возвращает номер фазы.
"""

from __future__ import annotations

import argparse
import importlib
import random
import statistics

import numpy as np

from .env import TrafficEnv

KEYS = ("done", "delay", "stops", "crashes", "near_total", "red_runs", "jaywalks", "ped_wait", "stuck")


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


POLICIES = {"random": random_policy, "hold": hold_policy, "max_pressure": max_pressure_policy}


def load_policy(spec: str):
    if spec in POLICIES:
        return POLICIES[spec]
    mod, _, fn = spec.partition(":")
    return getattr(importlib.import_module(mod), fn)


def episode(env: TrafficEnv, policy, seed: int, rng: random.Random) -> dict:
    obs = env.reset(seed=seed)
    done, ret, ignored, steps = False, 0.0, 0, 0
    info = {}
    while not done:
        obs, rewards, done, info = env.step(policy(env, obs, rng))
        ret += sum(rewards.values())
        ignored += sum(info["ignored"].values())
        steps += 1
    m = dict(info["metrics"])
    m["near_total"] = sum(m["near"].values())
    m["return"] = ret
    m["ignored_share"] = ignored / max(1, steps * len(env.agents))
    return m


def main():
    ap = argparse.ArgumentParser(description="Прогон политик через среду обучения")
    ap.add_argument("--world", default="grid2")
    ap.add_argument("--policy", default="random,hold,max_pressure", help="random, hold, max_pressure или модуль:функция")
    ap.add_argument("--episodes", type=int, default=3)
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--decision", type=float, default=5.0)
    ap.add_argument("--demand", type=float, default=1.0)
    ap.add_argument("--start-hour", type=float, default=7.5)
    a = ap.parse_args()
    env = TrafficEnv(a.world, decision=a.decision, episode=a.minutes * 60, demand=a.demand, start_hour=a.start_hour)
    print(f"мир {a.world}: {len(env.agents)} перекрёстков, наблюдение {env.obs_size}, действий до {env.max_actions}, {a.minutes:g} мин, решение раз в {a.decision:g} с")
    cols = ("return",) + KEYS + ("ignored_share",)
    print(f"{'политика':<14}" + "".join(f"{k:>14}" for k in cols))
    for spec in a.policy.split(","):
        pol = load_policy(spec)
        rng = random.Random(0)
        rows = [episode(env, pol, seed, rng) for seed in range(1, a.episodes + 1)]
        cells = [f"{statistics.mean(float(r[k]) for r in rows):>14.2f}" for k in cols]
        print(f"{spec:<14}" + "".join(cells))


if __name__ == "__main__":
    main()
