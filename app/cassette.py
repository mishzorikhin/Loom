"""Кассета ответов модели: запись и проигрывание.

Запись (`SIM_RECORD=путь`): каждый разобранный ответ модели добавляется строкой JSON. Проигрывание (`SIM_REPLAY=путь`):
вместо запроса к модели берётся следующий записанный ответ той же роли. Порядок ответов у роли сохраняется, поэтому прогон
с тем же зерном (`SIM_SEED`) идёт тем же путём. Совпадение не гарантировано: часы идут по реальному времени, и тексты
промптов с минутами ожидания могут отличаться; такое расхождение пишется в журнал (`cassette.drift`), а ответ всё равно берётся.
"""

import hashlib
import json
import os
import threading
from collections import defaultdict, deque
from pathlib import Path

MAX_BYTES = 30_000_000

_lock = threading.Lock()
_record: Path | None = None
_replay: dict[str, deque] | None = None
_replay_path: Path | None = None


def configure(record: str | None = None, replay: str | None = None) -> None:
    """Задать кассету. Без аргументов берутся `SIM_RECORD` и `SIM_REPLAY` из окружения."""
    global _record, _replay, _replay_path
    record = record if record is not None else os.environ.get("SIM_RECORD") or None
    replay = replay if replay is not None else os.environ.get("SIM_REPLAY") or None
    _record = Path(record) if record else None
    _replay, _replay_path = None, None
    if replay:
        _replay_path = Path(replay)
        queues: dict[str, deque] = defaultdict(deque)
        for line in _replay_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and "agent" in row and "parsed" in row:
                queues[row["agent"]].append(row)
        _replay = queues


def replaying() -> bool:
    return _replay is not None


def recording() -> bool:
    return _record is not None


def fingerprint(system: str, user: str) -> str:
    return hashlib.sha1(f"{system}\n--\n{user}".encode("utf-8")).hexdigest()[:12]


def record(agent: str, schema_key: str, system: str, user: str, parsed: dict, visit_id=None, model: str = "") -> None:
    if _record is None:
        return
    row = {
        "agent": agent, "schema": schema_key, "visit_id": visit_id, "model": model,
        "fp": fingerprint(system, user), "head": user[:100].replace("\n", " "), "parsed": parsed,
    }
    with _lock:
        try:
            _record.parent.mkdir(parents=True, exist_ok=True)
            if _record.exists() and _record.stat().st_size > MAX_BYTES:
                _record.replace(_record.with_suffix(_record.suffix + ".1"))
            with _record.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass


def replay(agent: str, system: str, user: str) -> tuple[dict, bool] | None:
    """Следующий записанный ответ роли и признак «промпт отличается от записанного». None, если записей больше нет."""
    if _replay is None:
        return None
    with _lock:
        queue = _replay.get(agent)
        if not queue:
            return None
        row = queue.popleft()
    return row["parsed"], row.get("fp") != fingerprint(system, user)


configure()
