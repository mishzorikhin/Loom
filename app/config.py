import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROMPTS = ROOT / "prompts"
STATIC = ROOT / "static"

DB_PATH = Path(os.environ.get("SIM_DB", str(ROOT.parent / "data" / "sim.db")))
LOG_PATH = Path(os.environ.get("SIM_LOG", str(DB_PATH.parent / "simcheck.log")))
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://192.168.0.16:8080/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.5-9b")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "60"))
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")  # только для первого запуска; дальше ключ хранится в настройках

PRICE_MIN = 50
PRICE_MAX = 900
MAX_EDITS = 3
MAX_ITEMS = 10
ITEM_MINUTES_MIN = 1
ITEM_MINUTES_MAX = 8
ITEM_NAME_MAX = 24
DAYS_PER_WEEK = 5
# Поток гостей: приходы идут случайным потоком, а не расписанием на день.
BASE_PER_HOUR = 0.9        # гостей в час при популярности 1 и среднем часе
MAX_VISITS_DAY = 30
MIN_GAP = 2.0              # минут между приходами не меньше
LIKES_WINDOW = 25          # сколько последних вердиктов определяют популярность
REFERRAL_CHANCE = 0.5      # шанс, что новый гость пришёл по совету
OPEN_MIN = 8 * 60
CLOSE_MIN = 20 * 60
SPEEDS = (1, 2, 4, 8)
IDLE_PAUSE_S = float(os.environ.get("SIM_IDLE_PAUSE", "10"))  # без зрителей столько секунд, затем пауза; 0 — выключено
