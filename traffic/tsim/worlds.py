"""Готовые миры и загрузка мира по имени или пути к JSON."""

from __future__ import annotations

from pathlib import Path

from .compiler import load_world
from .generators import corridor, district, grid

ROOT = Path(__file__).resolve().parent.parent

PRESETS = {
    "cross": ("Перекрёсток", lambda: load_world(ROOT / "examples" / "cross.json")),
    "corridor": ("Магистраль", lambda: corridor(4)),
    "grid": ("Решётка 3 × 3", lambda: grid(3, 3)),
    "district": ("Район (диагональ)", lambda: district()),
    "perm": ("Пермь, ул. Мира", lambda: load_world(ROOT / "examples" / "perm_mira.json")),
    "grid2": ("Решётка 2 × 2", lambda: grid(2, 2)),
}


def world(name: str) -> dict:
    """Мир по имени из PRESETS или по пути к файлу описания."""
    if name in PRESETS:
        return PRESETS[name][1]()
    path = Path(name)
    if path.suffix == ".json" and path.exists():
        return load_world(path)
    raise ValueError(f"нет мира «{name}»: ни готового, ни файла")
