"""Ведущий мира и решения людей через модель.

Физика города (`app/city.py`) и рефлексы работают без модели. Модель нужна там, где нужен смысл:
1. Ведущий (`adjudicate`) читает событие и отвечает, что на карте физически изменилось. Он описывает не сценарий,
   а патч из общих примитивов: объект с радиусом, проходимостью и опасностью, разовый урон, факт, закрытое заведение.
   Реакцию людей ведущий не решает: они сами смотрят на то, что видят.
2. Толпа (`_decide`) решает за людей, которые заметили что-то новое: идти мимо, смотреть, бежать, ждать. Вызовы
   пакетируются и ограничены по частоте, а похожие решения запоминаются на несколько минут.
Если модель недоступна, люди действуют рефлексами: обходят препятствия и убегают от опасности.
"""

import asyncio
import json
import time

import app.db as db
from app import log
from app.llm import SchemaError, TransportError, load_system

MAP_NOTE = """Карта квартала в клетках: x растёт вправо-вниз по экрану, y влево-вниз, границы −34…40.
- Кофейня: зал x 0–8, y 0–8, вход по тротуару x = −3.6.
- NeuralDeep (ЦОД и LLM-шлюз): зал x −4…4, y 19.5–27.5, вход по тротуару x = −7.6.
- Главная улица вдоль оси x: y от 11.5 до 15.5. Поперечная улица вдоль оси y: x от 11.5 до 15.5. Перекрёсток в точке (13.5, 13.5), там светофоры и четыре перехода.
- Тротуары: x = −3.6, x = 10.4, x = 16.6, x = −7.6 и y = −3.5, y = 10.4, y = 16.6.
- Парковка на пять мест: x 8–10, y 19–31. Жилые дома: восточнее x = 17 и северо-западнее кофейни."""

CACHE_MIN = 6.0      # столько минут симуляции живёт решение, найденное для похожей ситуации
CALL_EVERY = 8.0     # реальных секунд между вызовами модели про людей


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def patch_ops(raw_ops: list) -> list[dict]:
    """Плоские поля ответа модели превращаются в операции патча города."""
    ops = []
    for row in raw_ops:
        if not isinstance(row, dict):
            continue
        op = {key: row.get(key) for key in ("op", "kind", "x", "y", "r", "blocks", "hazard", "minutes", "effect", "amount",
                                           "text", "status", "label")}
        ident = str(row.get("id") or "")
        if row.get("op") in ("modify", "remove"):
            op["id"] = int(_num(ident, -1))
        elif row.get("op") == "place":
            op["id"] = ident
        op["glyph"] = {"shape": row.get("shape"), "color": row.get("color"), "size": row.get("size"), "text": row.get("text") if row.get("op") == "spawn" else ""}
        ops.append(op)
    return ops


class Mind:
    def __init__(self, engine):
        self.engine = engine
        self.busy = False
        self.last = 0.0
        self.cache: dict[tuple, tuple[float, dict]] = {}
        self.watch: list[dict] = []
        self.tasks: set[asyncio.Task] = set()

    async def reset(self) -> None:
        """Старые ответы не должны менять новый мир после сброса."""
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        self.cache.clear()
        self.watch.clear()
        self.busy = False
        self.last = 0.0

    @property
    def city(self):
        return self.engine.city

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def poll(self) -> None:
        """Вызывается из цикла города: когда пора, запускает решения людей и продолжение событий."""
        if self.busy or self.city is None:
            return
        city = self.city
        for item in self.watch:
            if item["left"] > 0 and city.t >= item["next"]:
                self.busy = True
                self._spawn(self._follow(item))
                return
        self.cache = {key: value for key, value in self.cache.items() if city.t < value[0]}
        now = time.time()
        if now - self.last < CALL_EVERY:
            return
        batch = city.drain_alerts(8)
        if batch:
            self.busy = True
            self.last = now
            self._spawn(self._decide(batch))

    # ---------- решения людей ----------

    async def _decide(self, batch: list[dict]) -> None:
        city = self.city
        try:
            asked = []
            for row in batch:
                ped = row["ped"]
                if ped.id not in city.peds:
                    continue
                percept = city.percept(ped, row["alerts"])
                key = (ped.id, json.dumps({k: v for k, v in percept.items() if k != "time"},
                                          ensure_ascii=False, sort_keys=True))
                cached = self.cache.get(key)
                if cached and city.t < cached[0]:
                    city.intent(ped.id, cached[1])
                    continue
                asked.append((ped.id, key, {"id": ped.id, **percept}))
            if not asked:
                return
            user = f"Сейчас {asked[0][2]['time']}.\n" + json.dumps({"people": [row[2] for row in asked]}, ensure_ascii=False)
            began = time.perf_counter()
            async with self.engine._thinking():
                data = await self.engine.llm.complete(
                    agent="crowd", schema_key="crowd", system=load_system("crowd"), user=user, visit_id=None, week_day=None)
            by_id = {row[0]: row for row in asked}
            done = 0
            for item in data.get("people", []):
                ident = int(_num(item.get("id"), -1))
                if ident not in by_id:
                    continue
                do = city.intent(ident, item)
                self.cache[by_id[ident][1]] = (city.t + CACHE_MIN, item)
                done += 1
                log.event("crowd.choice", ped=ident, name=city.peds[ident].name if ident in city.peds else None,
                          do=do, say=item.get("say") or None, mood=item.get("mood"))
            log.event("crowd.decide", asked=len(asked), answered=done, ms=int((time.perf_counter() - began) * 1000))
            self.engine.notify({"type": "city"})
        except (TransportError, SchemaError) as exc:
            log.event("crowd.fail", "warn", reason=str(exc))
        except Exception as exc:  # решение людей не должно ронять город
            log.event("crowd.fail", "error", **log.exc_fields(exc))
        finally:
            self.busy = False

    # ---------- ведущий ----------

    def _objects_note(self) -> str:
        city = self.city
        rows = []
        for e in city.ents.values():
            left = int(max(0, (e.until or city.t) - city.t))
            rows.append(f"- id {e.id}: {e.kind}, центр ({e.x:.1f}, {e.y:.1f}), радиус {e.r:.1f}, "
                        f"{'непроходим' if e.blocks else 'проходим'}, вред {e.hazard:.1f}, ещё {left} мин")
        return "На карте сейчас:\n" + ("\n".join(rows) if rows else "ничего необычного.")

    def _places_note(self) -> str:
        city = self.city
        return "Заведения мира (id, название, дверь): " + json.dumps([
            {"id": row["id"], "name": row.get("name", row["id"]),
             "door": list(city.doors.get(row["id"], (0, 0)))}
            for row in city.places.values()
        ], ensure_ascii=False)

    async def adjudicate(self, text: str, headline: str = "", story: str = "") -> list[dict]:
        """Событие → патч мира. Возвращает применённые операции; сбой модели оставляет мир как был."""
        city = self.city
        if city is None:
            return []
        state = db.run()
        places_note = self._places_note()
        brief = (f"{MAP_NOTE}\n{places_note}\nСейчас {state['clock']}, день {state['day']}.\n{self._objects_note()}\n"
                 f"Событие: {headline}. {story}\nВброс владельца: {text or 'нет'}")
        try:
            data = await self.engine._speak("Ведущий мира размечает карту", "adjudicator", "adjudicator", brief, None, False)
        except (TransportError, SchemaError) as exc:
            self.engine._ev("world.fail", "warn", reason=str(exc))
            db.set_run(phase="", active_agent="")
            return []
        db.set_run(phase="", active_agent="")
        applied, notes = city.apply_patch(patch_ops(data.get("ops") or []), source=(headline or text or "событие")[:40])
        log.event("world.patch", applied=applied or None, notes=notes or None, say=data.get("say") or None, event=headline or text)
        if applied and any(row["op"] == "spawn" for row in applied):
            self.watch.append({"src": (headline or text or "событие")[:40], "text": text or headline, "next": city.t + 25.0, "left": 4})
        self.engine.notify({"type": "city"})
        return applied

    async def _follow(self, item: dict) -> None:
        """Событие продолжается: ведущий смотрит, что стало с местом через четверть часа."""
        city = self.city
        try:
            item["left"] -= 1
            item["next"] = city.t + 25.0
            if not any(e.src == item["src"] for e in city.ents.values()):
                item["left"] = 0
                return
            places_note = self._places_note()
            brief = (f"{MAP_NOTE}\n{places_note}\nСейчас {db.run()['clock']}. Прошло около 25 минут после события «{item['text']}».\n"
                     f"{self._objects_note()}\nЧто изменилось? Верни только изменения (modify, remove, новые spawn, fact).")
            data = await self.engine._speak("Ведущий мира смотрит, что стало", "adjudicator", "adjudicator", brief, None, False)
            applied, notes = city.apply_patch(patch_ops(data.get("ops") or []), source=item["src"])
            log.event("world.patch", applied=applied or None, notes=notes or None, say=data.get("say") or None, event=item["text"], follow=True)
            self.engine.notify({"type": "city"})
        except (TransportError, SchemaError) as exc:
            log.event("world.fail", "warn", reason=str(exc), follow=True)
        except Exception as exc:
            log.event("world.fail", "error", **log.exc_fields(exc))
        finally:
            db.set_run(phase="", active_agent="")
            self.busy = False
