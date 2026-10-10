"""Сервер: один общий прогон, кадры всем зрителям по сокету /ws, команды обратно.

Запуск: python3 -m tsim.server [--port 8500] [--world cross]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import scenery
from .compiler import CompileError, compile_world, net_json
from .signals import CONTROLLERS, External, Manual
from .sim import DT, Demand, Sim
from .worlds import PRESETS
from .worlds import world as load_named

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"
FRAME_HZ = 20
SPEEDS = [0.5, 1, 2, 5, 10, 20, 40]

def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def num(msg: dict, key: str, default: float, lo: float, hi: float) -> float:
    """Число из команды в пределах [lo, hi]; NaN и бесконечность — ошибка."""
    v = float(msg.get(key, default))
    if not math.isfinite(v):
        raise ValueError(f"«{key}» не число")
    return min(max(v, lo), hi)


class Runner:
    def __init__(self, world: str = "cross", seed: int = 1):
        self.clients: set[WebSocket] = set()
        self.settings = {"world": world, "seed": seed, "controller": "fixed", "demand": 1.0, "peds": 1.0,
                         "timing": 1.0, "block_box": True, "start_hour": 7.5}
        self.running = True
        self.speed = 2.0
        self.start_world = world
        self.effective = 0.0
        self.last_event = 0
        self.series_len = 0
        self.load(world)

    # -- мир

    def load(self, world: str):
        self.net = compile_world(load_named(world))
        self.settings["world"] = world
        self.scenery = scenery.build(self.net)
        self.net_msg = dumps({"type": "net", "world": world, "net": net_json(self.net), "scenery": self.scenery})
        self.reset()

    def reset(self, seed: int | None = None):
        if seed is not None:
            self.settings["seed"] = seed
        s = self.settings
        self.sim = Sim(self.net, seed=s["seed"], controller=s["controller"],
                       demand=Demand(scale=s["demand"], peds_scale=s["peds"]), start_hour=s["start_hour"],
                       timing_scale=s["timing"], block_box=s["block_box"])
        self.last_event = 0
        self.series_len = 0
        self.budget = 0.0

    # -- сообщения

    def hello(self) -> str:
        worlds = [{"id": k, "title": v[0]} for k, v in PRESETS.items()]
        if self.settings["world"] not in PRESETS:
            worlds.append({"id": self.settings["world"], "title": self.net.world.get("name") or Path(self.settings["world"]).stem})
        return dumps({"type": "hello", "worlds": worlds,
                      "controllers": [{"id": c.name, "title": c.title} for c in CONTROLLERS.values()],
                      "speeds": SPEEDS, "settings": self.settings})

    def frame_msg(self) -> str:
        sim = self.sim
        f = sim.frame()
        f["type"] = "frame"
        f["events"] = [e for e in sim.events if e["id"] > self.last_event]
        if sim.events:
            self.last_event = sim.events[-1]["id"]
        f["metrics"] = sim.metrics()
        if len(sim.series) != self.series_len:
            f["series"] = sim.series
            self.series_len = len(sim.series)
        f["run"] = {"running": self.running, "speed": self.speed, "effective": round(self.effective, 2),
                    "settings": self.settings}
        return dumps(f)

    def full_frame(self) -> str:
        msg = json.loads(self.frame_msg())
        msg["series"] = self.sim.series
        msg["events"] = list(self.sim.events)[-60:]
        msg["full"] = True
        return dumps(msg)

    # -- команды

    def command(self, msg: dict) -> str | None:
        cmd = msg.get("cmd")
        s = self.settings
        if cmd == "play":
            self.running = True
        elif cmd == "pause":
            self.running = False
        elif cmd == "speed":
            self.speed = num(msg, "value", 1, 0.25, 60)
        elif cmd == "load":
            name = str(msg.get("world"))
            # со страницы — только готовые миры и тот, что задан при запуске
            if name not in PRESETS and name != self.start_world:
                raise ValueError(f"нет мира «{name}»")
            self.load(name)
            return "net"
        elif cmd == "reset":
            self.reset(int(msg["seed"]) if msg.get("seed") is not None else None)
            return "reset"
        elif cmd == "controller":
            name = str(msg.get("value"))
            if name in CONTROLLERS:
                s["controller"] = name
                self.sim.controller = CONTROLLERS[name]()
        elif cmd == "demand":
            s["demand"] = num(msg, "value", 1, 0, 3)
            self.sim.demand.scale = s["demand"]
            self.sim.reschedule()
        elif cmd == "peds":
            s["peds"] = num(msg, "value", 1, 0, 3)
            self.sim.demand.peds_scale = s["peds"]
            self.sim.reschedule()
        elif cmd == "timing":
            s["timing"] = num(msg, "value", 1, 0, 2)
            self.sim.set_timing_scale(s["timing"])
        elif cmd == "block_box":
            s["block_box"] = bool(msg.get("value"))
            self.sim.block_box = s["block_box"]
        elif cmd == "phase":
            jid = str(msg.get("junction"))
            ctl = self.sim.signals.get(jid)
            if ctl is None:
                return None
            if not isinstance(self.sim.controller, (Manual, External)):
                s["controller"] = "manual"
                self.sim.controller = Manual()
            ctl.request(int(msg.get("phase", 0)), msg.get("yellow"), msg.get("all_red"), msg.get("ped_flash"), force=True)
        return None

    async def broadcast(self, text: str):
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def loop(self):
        last = time.perf_counter()
        last_frame = 0.0
        sim_acc, real_acc = 0.0, 0.0
        while True:
            await asyncio.sleep(1 / 120)
            now = time.perf_counter()
            real_dt = min(now - last, 0.25)
            last = now
            if self.running:
                self.budget += real_dt * self.speed
                t0 = time.perf_counter()
                steps = 0
                try:
                    while self.budget >= DT and time.perf_counter() - t0 < 0.03:
                        self.sim.step()
                        self.budget -= DT
                        steps += 1
                except Exception as e:
                    traceback.print_exc(file=sys.stderr)
                    self.running = False
                    self.budget = 0.0
                    await self.broadcast(dumps({"type": "error", "message": f"Сбой симуляции, пауза: {e!r}"}))
                    await self.broadcast(self.hello())
                if self.budget > DT * 4:
                    self.budget = DT * 4   # не успеваем: эффективная скорость ниже заданной
                sim_acc += steps * DT
            real_acc += real_dt
            if real_acc >= 1.0:
                self.effective = sim_acc / real_acc
                sim_acc, real_acc = 0.0, 0.0
            if now - last_frame >= 1 / FRAME_HZ and self.clients:
                last_frame = now
                await self.broadcast(self.frame_msg())


def create_app(world: str = "cross", seed: int = 1) -> FastAPI:
    runner = Runner(world, seed)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(runner.loop())
        yield
        task.cancel()

    app = FastAPI(title="Transport sim", lifespan=lifespan)
    app.state.runner = runner

    @app.get("/api/state")
    def state():
        sim = runner.sim
        return JSONResponse({"settings": runner.settings, "running": runner.running, "speed": runner.speed,
                             "effective": runner.effective, "clock": sim.clock(), "t": sim.t,
                             "metrics": sim.metrics(), "events": list(sim.events)[-30:],
                             "signals": {k: v.snapshot() for k, v in sim.signals.items()}})

    @app.get("/api/net")
    def net():
        return JSONResponse(json.loads(runner.net_msg))

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        runner.clients.add(ws)
        try:
            await ws.send_text(runner.hello())
            await ws.send_text(runner.net_msg)
            await ws.send_text(runner.full_frame())
            while True:
                try:
                    msg = json.loads(await ws.receive_text())
                    if not isinstance(msg, dict):
                        raise ValueError("команда должна быть объектом JSON")
                    before = dict(runner.settings)
                    res = runner.command(msg)
                except (ValueError, KeyError, TypeError, AttributeError, CompileError) as e:
                    await ws.send_text(dumps({"type": "error", "message": str(e)}))
                    continue
                if res == "net":
                    await runner.broadcast(runner.hello())
                    await runner.broadcast(runner.net_msg)
                    await runner.broadcast(runner.full_frame())
                elif res == "reset":
                    if runner.settings != before:
                        await runner.broadcast(runner.hello())
                    await runner.broadcast(runner.full_frame())
                elif runner.settings != before:
                    # скорость и пауза приходят в кадрах, hello нужен только при смене настроек
                    await runner.broadcast(runner.hello())
        except WebSocketDisconnect:
            pass
        finally:
            runner.clients.discard(ws)

    if DIST.exists():
        app.mount("/", StaticFiles(directory=DIST, html=True), name="static")
    else:
        @app.get("/")
        def index():
            return HTMLResponse("<p>Страница не собрана: <code>cd web && npm install && npm run build</code></p>")

    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8500)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--world", default="cross", help="имя готового мира (" + ", ".join(PRESETS) + ") или путь к JSON")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    import uvicorn
    uvicorn.run(create_app(a.world, a.seed), host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
