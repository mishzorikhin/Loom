"""Журнал для разбора агентом: одна строка JSON на событие.

Ключи стабильны: `t` время с поясом, `lvl` (debug, info, warn, error), `ev` событие вида `visit.end`,
дальше поля события. Файл лежит рядом с базой (`SIM_LOG`), те же строки идут в stdout контейнера.
Промпты и ответы модели сюда не пишутся, они лежат в таблице `llm_calls`.
"""

import json
import logging
import logging.handlers
import os
import re
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from app.config import LOG_PATH

LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}
MAX_TEXT = 300
MAX_BYTES = 5_000_000
KEEP_FILES = 3

_logger = logging.getLogger("loom.journal")
_logger.propagate = False
_path: Path = LOG_PATH


def configure(path: Path | None = None) -> Path:
    """Направить журнал в файл (по умолчанию `LOG_PATH`). Старые обработчики снимаются."""
    global _path
    _path = Path(path) if path else LOG_PATH
    for handler in list(_logger.handlers):
        _logger.removeHandler(handler)
        handler.close()
    _logger.setLevel(logging.DEBUG)
    if os.environ.get("SIM_LOG_STDOUT", "1") != "0":
        out = logging.StreamHandler(sys.stdout)
        out.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(out)
    try:
        _path.parent.mkdir(parents=True, exist_ok=True)
        disk = logging.handlers.RotatingFileHandler(_path, maxBytes=MAX_BYTES, backupCount=KEEP_FILES, encoding="utf-8")
        disk.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(disk)
    except OSError as exc:
        _logger.warning(json.dumps({"t": _now(), "lvl": "error", "ev": "log.file", "msg": str(exc)[:MAX_TEXT]}, ensure_ascii=False))
    return _path


def path() -> Path:
    return _path


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def trim(value):
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[: MAX_TEXT - 1] + "…"
    if isinstance(value, (list, tuple)):
        return [trim(item) for item in list(value)[:20]]
    if isinstance(value, dict):
        return {str(key): trim(item) for key, item in list(value.items())[:20]}
    if isinstance(value, float):
        return round(value, 3)
    return value


def event(ev: str, level: str = "info", **fields) -> dict:
    record = {"t": _now(), "lvl": level, "ev": ev}
    record.update({key: trim(value) for key, value in fields.items() if value is not None})
    if not _logger.handlers:
        configure()
    _logger.log(logging.DEBUG, json.dumps(record, ensure_ascii=False, default=str))
    return record


def exc_fields(exc: BaseException) -> dict:
    """Тип, сообщение и последние кадры стека: достаточно, чтобы найти строку, не раздувая журнал."""
    frames = traceback.extract_tb(exc.__traceback__)[-4:]
    where = " < ".join(f"{Path(frame.filename).name}:{frame.lineno} {frame.name}" for frame in reversed(frames))
    return {"exc": exc.__class__.__name__, "msg": str(exc)[:MAX_TEXT], "where": where}


def parse_since(value: str | None) -> datetime | None:
    """`90s`, `10m`, `2h`, `1d` или ISO-время."""
    if not value:
        return None
    match = re.fullmatch(r"(\d+)\s*([smhd])", value.strip())
    if match:
        unit = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}[match.group(2)]
        return datetime.now().astimezone() - timedelta(**{unit: int(match.group(1))})
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def _lines(limit: int) -> list[str]:
    files = [_path] + [Path(f"{_path}.{i}") for i in range(1, KEEP_FILES + 1)]
    out: list[str] = []
    for file in files:
        try:
            rows = file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        out = rows + out
        if len(out) >= limit:
            break
    return out


def read(n: int = 200, level: str | None = None, ev: str | None = None, since: str | None = None,
         visit: int | None = None, q: str | None = None, scan: int = 20000) -> list[dict]:
    """Последние `n` событий (старые сверху) по фильтрам. `ev` — префиксы через запятую, `q` — подстрока строки."""
    floor = LEVELS.get(level or "debug", 10)
    prefixes = [p.strip() for p in (ev or "").split(",") if p.strip()]
    after = parse_since(since)
    out: list[dict] = []
    for line in _lines(scan)[-scan:]:
        if q and q not in line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or LEVELS.get(row.get("lvl"), 20) < floor:
            continue
        if prefixes and not any(str(row.get("ev", "")).startswith(p) for p in prefixes):
            continue
        if visit is not None and row.get("visit_id") != visit:
            continue
        if after is not None:
            try:
                if datetime.fromisoformat(row["t"]) < after:
                    continue
            except (KeyError, ValueError):
                continue
        out.append(row)
    return out[-max(1, min(n, 2000)):]


configure()
