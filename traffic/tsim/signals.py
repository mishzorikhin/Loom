"""Светофоры: стадии фаз и контроллеры.

Порядок стадий держит код: зелёный → жёлтый (машинам) и мигающий (пешеходам) →
весь красный → новый зелёный. Длительности выбирает контроллер в пределах
bounds перекрёстка (вариант B: опасно малые значения разрешены).
"""

from __future__ import annotations

from .compiler import Junction

CAR_GREEN, CAR_YELLOW, CAR_RED = "G", "Y", "R"
PED_WALK, PED_FLASH, PED_STOP = "W", "F", "D"


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class SignalCtl:
    """Состояние одного светофора."""

    def __init__(self, j: Junction, scale: float = 1.0):
        self.j = j
        self.scale = scale
        self.phase = 0
        self.stage = "green"        # green | change | all_red
        self.t = 0.0                # время в стадии
        self.green_t = 0.0          # время зелёного текущей фазы
        self.target = -1
        self.dur = {"yellow": 0.0, "all_red": 0.0, "ped_flash": 0.0, "change": 0.0}
        self.served = [0.0] * len(j.phases)   # когда фаза последний раз заканчивалась
        self.state: dict[str, str] = {}
        self.calls = 0              # вызовы пешеходов (переход посреди квартала)
        self._apply_green()

    @property
    def groups(self):
        return self.j.groups

    def green_set(self, phase: int) -> set[str]:
        return set(self.j.phases[phase]["green"])

    def _apply_green(self):
        green = self.green_set(self.phase)
        for name, g in self.groups.items():
            if g.kind == "car":
                self.state[name] = CAR_GREEN if name in green else CAR_RED
            else:
                self.state[name] = PED_WALK if name in green else PED_STOP

    def defaults(self) -> dict[str, float]:
        b, s = self.j.bounds, self.j.safe
        return {k: clamp(s.get(k, 0.0) * self.scale, b[k][0], b[k][1]) for k in ("yellow", "all_red", "ped_flash")}

    def min_green(self) -> float:
        return self.j.bounds["green"][0]

    def max_green(self) -> float:
        return self.j.bounds["green"][1]

    def can_switch(self) -> bool:
        return self.stage == "green" and self.green_t >= self.min_green()

    def request(self, phase: int, yellow: float | None = None, all_red: float | None = None,
                ped_flash: float | None = None, force: bool = False) -> bool:
        """Перейти на фазу. Длительности None — по умолчанию (безопасные × запас)."""
        if phase < 0 or phase >= len(self.j.phases) or phase == self.phase:
            return False
        if self.stage != "green" or (not force and self.green_t < self.min_green()):
            return False
        d = self.defaults()
        b = self.j.bounds
        if yellow is not None:
            d["yellow"] = clamp(yellow, *b["yellow"])
        if all_red is not None:
            d["all_red"] = clamp(all_red, *b["all_red"])
        if ped_flash is not None:
            d["ped_flash"] = clamp(ped_flash, *b["ped_flash"])
        now, nxt = self.green_set(self.phase), self.green_set(phase)
        ending = now - nxt
        car_end = any(self.groups[g].kind == "car" for g in ending)
        ped_end = any(self.groups[g].kind == "ped" for g in ending)
        d["change"] = max(d["yellow"] if car_end else 0.0, d["ped_flash"] if ped_end else 0.0)
        self.dur = d
        self.target = phase
        self.stage = "change"
        self.t = 0.0
        for g in ending:
            self.state[g] = CAR_YELLOW if self.groups[g].kind == "car" else PED_FLASH
        self._ending = ending
        if d["change"] <= 0:
            self._to_all_red()
        return True

    def _to_all_red(self):
        for g in self._ending:
            self.state[g] = CAR_RED if self.groups[g].kind == "car" else PED_STOP
        self.stage = "all_red"
        self.t = 0.0
        if self.dur["all_red"] <= 0:
            self._to_green()

    def _to_green(self):
        self.served[self.phase] = 0.0
        self.phase = self.target
        self.target = -1
        self.stage = "green"
        self.t = 0.0
        self.green_t = 0.0
        self._apply_green()

    def tick(self, dt: float):
        self.t += dt
        for i in range(len(self.served)):
            self.served[i] += dt
        if self.stage == "green":
            self.green_t += dt
        elif self.stage == "change":
            # жёлтый у машин кончается раньше мигающего у пешеходов
            for g in self._ending:
                if self.groups[g].kind == "car" and self.t >= self.dur["yellow"] and self.state[g] == CAR_YELLOW:
                    self.state[g] = CAR_RED
            if self.t >= self.dur["change"]:
                self._to_all_red()
        elif self.stage == "all_red":
            if self.t >= self.dur["all_red"]:
                self._to_green()

    def snapshot(self) -> dict:
        return {"phase": self.phase, "stage": self.stage, "t": round(self.t, 1), "green_t": round(self.green_t, 1),
                "target": self.target, "dur": {k: round(v, 1) for k, v in self.dur.items()},
                "state": "".join(self.state[g] for g in self.groups)}


# ---------------------------------------------------------------- контроллеры


def _midblock(ctl: SignalCtl, peds_waiting: int):
    """Переход по вызову: пешеходам после вызова и минимального зелёного машинам."""
    if ctl.phase == 0:
        if peds_waiting and ctl.green_t >= max(20.0, ctl.min_green()):
            ctl.request(1)
    elif ctl.green_t >= max(8.0, ctl.min_green()):
        ctl.request(0)


class Controller:
    name = "base"
    title = ""

    def decide(self, sim, jid: str, ctl: SignalCtl):
        raise NotImplementedError

    def step(self, sim):
        for jid, ctl in sim.signals.items():
            if ctl.j.kind == "midblock":
                _midblock(ctl, sim.peds_waiting(jid))
                continue
            self.decide(sim, jid, ctl)


class FixedTime(Controller):
    """Фиксированный цикл: фазы по кругу, длительность зелёного от состава фазы."""
    name = "fixed"
    title = "Фиксированный цикл"

    def green_for(self, ctl: SignalCtl, phase: int) -> float:
        pid = ctl.j.phases[phase]["id"]
        groups = [ctl.groups[g] for g in ctl.j.phases[phase]["green"]]
        if all(g.kind == "ped" for g in groups):
            g = 10.0
        elif "left" in pid:
            g = 12.0
        else:
            lanes = sum(len(x.links) for x in groups if x.kind == "car")
            g = 16.0 + 2.5 * lanes
        return clamp(g, ctl.min_green(), ctl.max_green())

    def decide(self, sim, jid, ctl):
        if ctl.stage == "green" and ctl.green_t >= self.green_for(ctl, ctl.phase):
            ctl.request((ctl.phase + 1) % len(ctl.j.phases))


class MaxPressure(Controller):
    """Max-pressure: фаза с наибольшим «давлением» (очередь на входе минус загрузка выхода)."""
    name = "max_pressure"
    title = "Max-pressure"

    def __init__(self, min_green: float = 8.0, period: float = 2.0):
        self.min_green = min_green
        self.period = period
        self.last: dict[str, float] = {}

    def decide(self, sim, jid, ctl):
        if ctl.stage != "green" or ctl.green_t < max(self.min_green, ctl.min_green()):
            return
        if sim.t - self.last.get(jid, -1e9) < self.period:
            return
        self.last[jid] = sim.t
        obs = sim.junction_obs(jid)
        score = []
        for i, p in enumerate(obs["phase_pressure"]):
            # голодание: давно не обслуженная фаза получает надбавку
            wait = 0.0 if i == ctl.phase else ctl.served[i]
            score.append(p + 0.06 * max(0.0, wait - 40.0))
        others = [i for i in range(len(score)) if i != ctl.phase]
        if not others:
            return
        best = max(others, key=lambda i: score[i])
        if score[best] > score[ctl.phase] + 1.0 or ctl.green_t >= ctl.max_green():
            ctl.request(best)


class Manual(Controller):
    """Ручное управление: фаза меняется только по команде; переходы посреди квартала — по вызову."""
    name = "manual"
    title = "Вручную"

    def decide(self, sim, jid, ctl):
        pass


class External(Controller):
    """Решения приходят снаружи (среда обучения): контроллер ничего не делает сам."""
    name = "external"
    title = "Внешний агент"

    def decide(self, sim, jid, ctl):
        pass


CONTROLLERS = {c.name: c for c in (FixedTime, MaxPressure, Manual, External)}


def make(name: str) -> Controller:
    return CONTROLLERS.get(name, FixedTime)()
