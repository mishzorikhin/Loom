"""Вещатель: все зрители смотрят одну симуляцию через сокеты.

Сервер один раз собирает снимок на всех и рассылает его, когда что-то изменилось (изменения за 0,12 с склеиваются)
и раз в 15 секунд на всякий случай. Когда зрителей не осталось, через `idle_seconds` вызывается `on_idle`
(прогон ставится на паузу). Короткий обрыв связи, например перезагрузка страницы, паузу не вызывает.
"""

import asyncio
import json
import time

from fastapi import WebSocket

from app import log


class Hub:
    def __init__(self, build, idle_seconds: float, on_idle):
        self.build = build
        self.idle_seconds = idle_seconds
        self.on_idle = on_idle
        self.clients: dict[WebSocket, dict] = {}
        self._dirty = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._idle: asyncio.Task | None = None

    @property
    def count(self) -> int:
        return len(self.clients)

    def start(self) -> None:
        self._dirty = asyncio.Event()
        self._task = asyncio.create_task(self._loop())
        if not self.clients:
            self._arm_idle()

    async def stop(self) -> None:
        for task in (self._task, self._idle):
            if task:
                task.cancel()
        self._task = self._idle = None

    def changed(self) -> None:
        """Что-то изменилось: зрителям уйдёт свежий снимок."""
        self._dirty.set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.clients[websocket] = {"since": time.time(), "ip": websocket.client.host if websocket.client else None}
        if self._idle:
            self._idle.cancel()
            self._idle = None
        log.event("ws.connect", viewers=self.count, ip=self.clients[websocket]["ip"])
        await self._send(websocket, await self._snapshot())
        self.changed()

    def disconnect(self, websocket: WebSocket) -> None:
        if self.clients.pop(websocket, None) is None:
            return
        log.event("ws.disconnect", viewers=self.count)
        self.changed()
        if not self.clients:
            self._arm_idle()

    def _arm_idle(self) -> None:
        if self._idle:
            self._idle.cancel()
            self._idle = None
        if self.idle_seconds > 0:  # 0 — автопауза выключена
            self._idle = asyncio.create_task(self._idle_wait())

    async def _idle_wait(self) -> None:
        try:
            await asyncio.sleep(self.idle_seconds)
        except asyncio.CancelledError:
            return
        if not self.clients:
            self.on_idle()

    async def _snapshot(self) -> str:
        return json.dumps({"type": "snapshot", "data": await self.build()}, ensure_ascii=False, default=str)

    async def _send(self, websocket: WebSocket, raw: str) -> None:
        try:
            await websocket.send_text(raw)
        except Exception:
            self.disconnect(websocket)

    async def broadcast_frame(self, frame: dict) -> None:
        """Кадр города: только позиции людей и машин. Снимок не пересобирается."""
        if not self.clients:
            return
        raw = json.dumps({"type": "city", "d": frame}, ensure_ascii=False, separators=(",", ":"))
        await asyncio.gather(*(self._send(client, raw) for client in list(self.clients)))

    async def reply(self, websocket: WebSocket, ident, ok: bool, **fields) -> None:
        await self._send(websocket, json.dumps({"type": "reply", "id": ident, "ok": ok, **fields}, ensure_ascii=False, default=str))

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._dirty.wait(), timeout=15)
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep(0.12)
            self._dirty.clear()
            if not self.clients:
                continue
            try:
                raw = await self._snapshot()
            except Exception as exc:
                log.event("ws.snapshot_fail", "error", **log.exc_fields(exc))
                continue
            await asyncio.gather(*(self._send(client, raw) for client in list(self.clients)))
