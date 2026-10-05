import math
import re

from app.config import (
    BASE_PER_HOUR, ITEM_MINUTES_MAX, ITEM_MINUTES_MIN, ITEM_NAME_MAX, MAX_EDITS, MAX_ITEMS, MIN_GAP, PRICE_MAX, PRICE_MIN,
)


def format_clock(minutes: float) -> str:
    total = max(0, int(minutes))
    hours, mins = divmod(total, 60)
    return f"{hours:02d}:{mins:02d}"


THINK_SPEED = 1.0  # пока модель отвечает, часы идут не быстрее, чем час за минуту


def advance_minutes(anchor_min: float, anchor_real: float, now: float, speed: float, running: bool, thinking: bool = False) -> float:
    if not running:
        return anchor_min
    if thinking:
        speed = min(speed, THINK_SPEED)
    return anchor_min + max(0.0, now - anchor_real) * speed


def stay_minutes(visit_id: int, status: str, valence: int = 0) -> int:
    """Сколько минут гость сидит с напитком. 0 — берёт с собой или уходит сразу.
    Раздражённый не остаётся, радостный сидит дольше."""
    if status != "served" or visit_id % 4 == 0 or valence <= -2:
        return 0
    return min(45, 12 + (visit_id * 37) % 29 + (8 if valence >= 2 else 0))


def rating_for(status: str, asks: int, patience: int = 3) -> int | None:
    if status == "served":
        impatient = 1 if asks and patience <= 2 else 0
        return max(1, min(5, 5 - asks - impatient))
    if status == "refused":
        return 2
    return None


# ---------- настроения ----------

# Настроение и его знак. Слова нейтральны по роду: «Настроение: усталость».
MOODS = {"радость": 2, "бодрость": 1, "спокойствие": 0, "усталость": -1, "тревога": -1, "грусть": -1, "раздражение": -2}
DEFAULT_MOOD = "спокойствие"
MOOD_WEIGHTS = (("радость", 0.10), ("бодрость", 0.17), ("спокойствие", 0.33), ("усталость", 0.15),
                ("тревога", 0.09), ("грусть", 0.08), ("раздражение", 0.08))
# Лестница для сдвигов: тревога и грусть считаются ступенью «усталость».
LADDER = ("раздражение", "усталость", "спокойствие", "бодрость", "радость")
FATIGUE_FROM = 17 * 60


def mood_value(mood: str | None) -> int:
    return MOODS.get(mood or "", 0)


def pick_mood(roll: float) -> str:
    acc = 0.0
    for mood, weight in MOOD_WEIGHTS:
        acc += weight
        if roll < acc:
            return mood
    return DEFAULT_MOOD


def shift_mood(mood: str | None, shift: int) -> str:
    """Сдвинуть настроение вверх или вниз по лестнице. Без сдвига оно не меняется."""
    current = mood if mood in MOODS else DEFAULT_MOOD
    if not shift:
        return current
    index = LADDER.index(current) if current in LADDER else 1
    return LADDER[max(0, min(len(LADDER) - 1, index + shift))]


QUEUE_CHECK_EVERY = 10  # через сколько минут ожидания гостя в очереди снова спрашивают, ждать ли


def wait_shift(wait: float) -> int:
    """Насколько ожидание в очереди портит настроение: больше 15 минут на ступень, больше 30 на две."""
    return -2 if wait > 30 else -1 if wait > 15 else 0


def arrival_mood(roll: float, keep_roll: float, carry: str | None, liked: int | None, wait: float) -> str:
    """Настроение гостя, когда он вошёл: случайное или оставшееся с прошлого визита; хороший прошлый визит
    поднимает, плохой опускает, долгое ожидание опускает."""
    shift = 0
    if liked:
        shift += 1 if liked >= 4 else -1 if liked <= 2 else 0
    shift += wait_shift(wait)
    base = carry if carry in MOODS and keep_roll < 0.5 else pick_mood(roll)
    return shift_mood(base, max(-2, min(2, shift))) if shift else base


def after_visit_mood(mood: str | None, status: str, liked: int | None, minute: float, roll: float) -> str:
    """Настроение бариста после визита: отказ и оборванный разговор опускают, довольный гость поднимает,
    недовольный опускает, к вечеру растёт усталость."""
    shift = -1 if status in ("refused", "failed", "left") else 0
    if liked:
        shift += 1 if liked >= 4 else -1 if liked <= 2 else 0
    if minute >= FATIGUE_FROM and roll < 0.3:
        shift -= 1
    return shift_mood(mood, max(-2, min(2, shift)))


def effective_patience(patience: int, mood: str | None) -> int:
    """Терпение гостя с поправкой на настроение: в радости терпит больше, в раздражении меньше."""
    value = mood_value(mood)
    return max(1, min(5, patience + (1 if value >= 2 else -1 if value <= -2 else 0)))


# ---------- поток гостей и возврат ----------

# Вес часа в потоке: с этого часа и до следующей строки. Утренний и обеденный пики, вечерний спад.
DAY_CURVE = ((8, 1.35), (10, 0.8), (12, 1.45), (14, 0.8), (17, 1.25), (19, 0.6))
INTENT_WEIGHT = {"yes": 1.0, "maybe": 0.45, "no": 0.05}
INTENTS = ("yes", "maybe", "no")


def day_curve(minute: float) -> float:
    weight = DAY_CURVE[0][1]
    for start, value in DAY_CURVE:
        if minute / 60 >= start:
            weight = value
    return weight


# Части дня, на которые районный голос раскладывает поток: границы по часам.
DAYPARTS = ((8, 10), (10, 12), (12, 14), (14, 17), (17, 19), (19, 20))


def part_curve(minute: float, curve: list[float]) -> float:
    """Вес часа по кривой из шести частей дня, которую задал районный голос."""
    hour = minute / 60
    for (start, end), weight in zip(DAYPARTS, curve):
        if start <= hour < end:
            return weight
    return curve[-1] if hour >= DAYPARTS[-1][0] else curve[0]


def arrival_gap(minute: float, popularity: float, roll: float, curve: list[float] | None = None) -> float:
    """Через сколько минут после `minute` придёт следующий гость. `roll` — случайное число от 0 до 1.
    Без кривой от районного голоса берётся обычная суточная."""
    rate = BASE_PER_HOUR / 60 * max(0.05, popularity) * (part_curve(minute, curve) if curve else day_curve(minute))
    return max(MIN_GAP, -math.log(max(1e-9, 1 - min(roll, 0.999999))) / rate)


def popularity(likes: list[int], referral_pool: int = 0) -> float:
    """Множитель потока гостей от того, как гостям понравилось. Без вердиктов — 1."""
    if not likes:
        return 1.0
    average = sum(likes) / len(likes)
    return max(0.5, min(2.2, 1.0 + 0.30 * (average - 3.5) + 0.04 * min(referral_pool, 6)))


def new_share(pop: float) -> float:
    """Доля новых гостей среди приходов: чем популярнее заведение, тем больше новых лиц."""
    return max(0.1, min(0.6, 0.25 + 0.25 * (pop - 1)))


def return_weight(client: dict, day: int) -> float:
    """Насколько гость готов прийти сегодня: из его вердикта. 0 — ещё рано."""
    come = client.get("come_day")
    if come and day < come:
        return 0.0
    base = INTENT_WEIGHT.get(client.get("intent"), 0.5)
    liked = client.get("liked") or client.get("last_rating") or 3
    return base * (0.4 + 0.12 * liked)


def choose_arrival(clients: list[dict], day: int, seen_today: set[int], pop: float, roll: float, pick: float,
                   share: float | None = None) -> dict | None:
    """Карточка знакомого гостя или None, если заходит новый. `share` — доля новых от районного голоса."""
    eligible = []
    for client in clients:
        if client["id"] in seen_today:
            continue
        weight = return_weight(client, day)
        if weight > 0:
            eligible.append((client, weight))
    if not eligible or roll < (share if share is not None else new_share(pop)):
        return None
    cursor = pick * sum(weight for _, weight in eligible)
    acc = 0.0
    for client, weight in eligible:
        acc += weight
        if cursor <= acc:
            return client
    return eligible[-1][0]


def come_day_for(intent: str, days: int, day: int) -> int:
    if intent == "no":
        return day + 30
    return day + max(1, min(14, int(days)))


def clean_verdict(data: dict) -> dict:
    """Вердикт гостя приводится к границам: оценка 1–5, намерение из списка, дни 0–14."""
    try:
        liked = int(data.get("liked"))
    except (TypeError, ValueError):
        liked = 3
    try:
        days = int(data.get("return_in_days"))
    except (TypeError, ValueError):
        days = 3
    intent = data.get("return") if data.get("return") in INTENTS else "maybe"
    return {
        "say": " ".join(str(data.get("say") or "").split())[:200],
        "liked": max(1, min(5, liked)),
        "return": intent,
        "return_in_days": max(0, min(14, days)),
        "recommend": bool(data.get("recommend")),
        "mood": data.get("mood") if data.get("mood") in MOODS else None,
        "review": " ".join(str(data.get("review") or "").split())[:140],
    }


def fallback_verdict(status: str, rating: int | None) -> dict:
    """Запасной вердикт от кода, если модель не смогла: по оценке визита."""
    liked = rating or (2 if status == "refused" else 3)
    return {
        "say": "",
        "liked": liked,
        "return": "yes" if liked >= 4 else "maybe",
        "return_in_days": 2 if liked >= 4 else 5,
        "recommend": False,
        "mood": None,
        "review": "",
    }


_NAME = re.compile(r"^[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9 \-]*$")


def _new_item(items: dict[str, dict], change: dict, already: bool) -> tuple[dict | None, str]:
    """Проверить новую позицию. Вернёт запись правки или причину отказа."""
    name = " ".join(str(change.get("name") or "").split())
    if already:
        return None, f"{name or 'Позиция'}: за неделю добавляется одна новая позиция, остальные пропущены."
    if len(items) >= MAX_ITEMS:
        return None, f"{name or 'Позиция'}: в меню уже {MAX_ITEMS} позиций, новая не добавлена."
    if len(name) < 2 or len(name) > ITEM_NAME_MAX or not _NAME.match(name):
        return None, f"Новая позиция «{name[:30]}»: название должно быть от 2 до {ITEM_NAME_MAX} знаков, буквы и цифры."
    if any(str(item["name"]).casefold() == name.casefold() for item in items.values()):
        return None, f"{name}: такая позиция уже есть."
    try:
        price = int(change.get("price"))
        minutes = int(change.get("minutes"))
    except (TypeError, ValueError):
        return None, f"{name}: цена или минуты не числа, позиция не добавлена."
    if price < PRICE_MIN or price > PRICE_MAX:
        return None, f"{name}: цена {price} вне {PRICE_MIN}–{PRICE_MAX}, позиция не добавлена."
    if minutes < ITEM_MINUTES_MIN or minutes > ITEM_MINUTES_MAX:
        return None, f"{name}: {minutes} мин вне {ITEM_MINUTES_MIN}–{ITEM_MINUTES_MAX}, позиция не добавлена."
    number = 1
    while f"new{number}" in items:
        number += 1
    item_id = f"new{number}"
    return {"op": "add_item", "item_id": item_id, "name": name, "price": price, "minutes": minutes}, ""


def apply_changes(items: dict[str, dict], changes: list[dict]) -> tuple[list[dict], list[str]]:
    applied: list[dict] = []
    notes: list[str] = []
    if len(changes) > MAX_EDITS:
        notes.append(f"Лишние правки отброшены, оставлены {MAX_EDITS} первых.")
    added = False
    for change in changes[:MAX_EDITS]:
        op = change.get("op")
        if op == "add_item":
            entry, note = _new_item(items, change, added)
            if entry is None:
                notes.append(note)
                continue
            items[entry["item_id"]] = {
                "id": entry["item_id"], "name": entry["name"], "price": entry["price"],
                "minutes": entry["minutes"], "available": 1,
            }
            applied.append(entry)
            added = True
            continue
        item_id = str(change.get("item_id") or "")
        item = items.get(item_id)
        if item is None or op not in ("set_price", "set_available"):
            notes.append(f"Правка не применена: неизвестная позиция или действие ({item_id or 'пусто'}).")
            continue
        if op == "set_price":
            try:
                price = int(change.get("price"))
            except (TypeError, ValueError):
                notes.append(f"{item['name']}: цена не число, правка пропущена.")
                continue
            if price < PRICE_MIN or price > PRICE_MAX:
                notes.append(f"{item['name']}: цена {price} вне {PRICE_MIN}–{PRICE_MAX}, правка пропущена.")
                continue
            previous = item["price"]
            item["price"] = price
            applied.append(
                {
                    "op": op,
                    "item_id": item_id,
                    "name": item["name"],
                    "price_before": previous,
                    "price_after": price,
                }
            )
        else:
            available = bool(change.get("available"))
            before = bool(item["available"])
            item["available"] = 1 if available else 0
            applied.append(
                {
                    "op": op,
                    "item_id": item_id,
                    "name": item["name"],
                    "available_before": before,
                    "available_after": available,
                }
            )
    return applied, notes


def _tokens(text: str) -> set[str]:
    return {word for word in re.findall(r"[а-яёa-z0-9]+", str(text).casefold()) if len(word) > 2}


def echo_ratio(reply: str, said: str) -> float:
    """Какая доля слов реплики `said` повторена в `reply`. 1 — пересказ целиком."""
    wanted = _tokens(said)
    if not wanted:
        return 0.0
    return len(wanted & _tokens(reply)) / len(wanted)


ECHO_LIMIT = 0.55


def style_problem(agent: str, data: dict, echo_of: str = "") -> str:
    """Очевидная ерунда, которую стоит переспросить: гость пересказывает вопрос бариста,
    бариста отдаёт или отказывает вопросом."""
    say = str(data.get("say") or "")
    if agent == "client" and echo_of and echo_ratio(say, echo_of) >= ECHO_LIMIT:
        return "Ты повторил слова бариста. Ответь на его вопрос выбором, своими словами, без пересказа."
    if agent == "staff" and data.get("action") in ("serve", "refuse") and "?" in say:
        return "Реплика закрывает заказ, вопрос в ней лишний. Скажи утверждением, что делаешь."
    if agent == "verdict" and echo_of and echo_ratio(say, echo_of) >= ECHO_LIMIT:
        return "Ты пересказал свою же реплику. Скажи, что ты думаешь про сам визит: что запомнилось и как тебе."
    return ""


def fallback_choice(item_name: str) -> str:
    return f"Решил. Беру: {item_name}."


def fallback_close(item_name: str) -> str:
    return f"Хорошо, сейчас будет: {item_name}."


# ---------- критик диалогов ----------

CRITIC_CODES = ("echo", "price_named", "second_item", "mood_named", "contradiction", "nonsense", "off_menu", "wrong_name")

# Какое напоминание добавлять в промпт роли, если критик часто видит такую ошибку.
CRITIC_HINTS = {
    "price_named": {"staff": "Напоминание: цену не называй, пока гость не спросил."},
    "second_item": {"staff": "Напоминание: в реплике только одна позиция, вторую не обещай."},
    "mood_named": {
        "client": "Напоминание: настроение не называй словом, оно слышно в тоне.",
        "staff": "Напоминание: настроение не называй словом, оно слышно в тоне.",
        "verdict": "Напоминание: настроение называть словом не нужно.",
    },
    "echo": {"client": "Напоминание: чужие слова и свои прошлые не повторяй.", "verdict": "Напоминание: не пересказывай реплики."},
    "contradiction": {"staff": "Напоминание: реплика должна совпадать с твоим действием."},
    "nonsense": {"client": "Напоминание: говори ясно и по делу.", "staff": "Напоминание: говори ясно и по делу."},
    "wrong_name": {"staff": "Напоминание: гостя зовут так, как в строке «Гость». Другое имя не называй."},
    "off_menu": {"staff": "Напоминание: предлагай только позиции из меню.", "client": "Напоминание: проси только то, что есть в меню."},
}
HINT_AFTER = 3


def clean_critic(data: dict, texts: list[str]) -> dict:
    """Ответ критика приводится к границам: не больше шести замечаний, код из списка, номер реплики в диапазоне.
    Замечание принимается, только если цитата из него действительно есть в названной реплике: так отсекается выдумка."""
    lines = len(texts)
    try:
        score = int(data.get("score"))
    except (TypeError, ValueError):
        score = 3
    issues = []
    for row in (data.get("issues") or [])[:6]:
        if not isinstance(row, dict) or row.get("code") not in CRITIC_CODES:
            continue
        try:
            line = int(row.get("line"))
        except (TypeError, ValueError):
            line = 0
        quote = " ".join(str(row.get("quote") or "").split()).casefold().strip(" «»\"'")
        if 1 <= line <= lines:
            if len(quote) < 3 or quote not in " ".join(texts[line - 1].split()).casefold():
                continue
        issues.append({
            "code": row["code"],
            "line": line if 1 <= line <= lines else 0,
            "severity": "high" if row.get("severity") == "high" else "low",
            "note": " ".join(str(row.get("note") or "").split())[:160],
        })
    return {"score": max(1, min(5, score)), "issues": issues}


def active_hints(recent: list[list[dict]], role: str) -> list[str]:
    """Напоминания для роли: коды уверенных замечаний (`high`), которые критик видел не меньше трёх раз за последние
    визиты. Слабые замечания только показываются, на промпты они не влияют."""
    counts: dict[str, int] = {}
    for issues in recent:
        for code in {row["code"] for row in issues if row.get("severity") == "high"}:
            counts[code] = counts.get(code, 0) + 1
    out = []
    for code in CRITIC_CODES:
        if counts.get(code, 0) >= HINT_AFTER and role in CRITIC_HINTS.get(code, {}):
            out.append(CRITIC_HINTS[code][role])
    return out[:2]


# ---------- события дня ----------

EFFECT_TYPES = ("slower_prep", "item_out", "demand", "staff_mood", "guest_mood")
WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
SEASONS = ("осень", "зима", "весна", "лето")


def calendar(day: int) -> tuple[str, str]:
    """День недели и сезон по номеру дня: день 1 — понедельник, сезон меняется каждые 30 дней."""
    return WEEKDAYS[(max(1, day) - 1) % 7], SEASONS[((max(1, day) - 1) // 30) % 4]


def cut_text(text, limit: int) -> str:
    """Текст до `limit` знаков, обрезанный по слову, с многоточием."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    head = text[: limit - 1]
    if text[limit - 1] != " " and " " in head:  # обрезали посреди слова: слово не оставляем
        head = head.rsplit(" ", 1)[0]
    return head.rstrip(" ,;:—-") + "…"


def clean_event(data: dict, items: dict[str, dict], staff_ids: list[str], max_days: int = 3) -> dict | None:
    """Событие дня, придуманное моделью, приводится к границам каталога эффектов. Всё, что за пределами, отбрасывается.
    Возвращает None, если события нет (обычный день без заголовка)."""
    headline = " ".join(str(data.get("headline") or "").split())[:60]
    story = " ".join(str(data.get("story") or "").split())[:240]
    names = {str(item["name"]).casefold(): item_id for item_id, item in items.items()}
    effects: list[dict] = []
    for row in (data.get("effects") or [])[:2]:
        if not isinstance(row, dict) or row.get("type") not in EFFECT_TYPES:
            continue
        kind = row["type"]
        try:
            amount = float(row.get("amount"))
        except (TypeError, ValueError):
            continue
        try:
            days = int(row.get("days"))
        except (TypeError, ValueError):
            days = 1
        target = " ".join(str(row.get("target") or "").split())
        days = min(days, max_days)
        effect = {"type": kind, "target": "", "amount": 0.0, "days": 1}
        if kind == "slower_prep":
            effect.update(amount=round(max(1.2, min(2.0, amount)), 2), days=max(1, min(2, days)))
        elif kind == "item_out":
            item_id = target if target in items else names.get(target.casefold())
            if item_id is None:
                continue
            effect.update(target=item_id, days=max(1, min(2, days)))
        elif kind == "demand":
            effect.update(amount=round(max(0.6, min(1.5, amount)), 2), days=max(1, min(3, days)))
        elif kind == "staff_mood":
            shift = int(max(-2, min(2, round(amount))))
            if not shift:
                continue
            who = target if target in staff_ids else "all"
            effect.update(target=who, amount=float(shift))
        elif kind == "guest_mood":
            shift = int(max(-1, min(1, round(amount))))
            if not shift:
                continue
            effect.update(amount=float(shift), days=max(1, min(2, days)))
        effects.append(effect)
    if not headline and not effects:
        return None
    return {"headline": headline or "Необычный день", "story": story, "effects": effects}


def effect_label(effect: dict, items: dict[str, dict], staff_names: dict[str, str]) -> str:
    """Короткая подпись эффекта для страницы."""
    kind, amount, target = effect["type"], effect["amount"], effect["target"]
    if kind == "slower_prep":
        return f"готовка ×{amount:g}"
    if kind == "item_out":
        return f"нет: {items.get(target, {}).get('name', target)}"
    if kind == "demand":
        return f"спрос ×{amount:g}"
    if kind == "guest_mood":
        return f"настроение гостей {int(amount):+d}"
    who = "бариста" if target == "all" else staff_names.get(target, target)
    return f"настроение: {who} {int(amount):+d}"


# ---------- районный голос и демограф ----------

TRAITS = (
    "говорит коротко и спешит",
    "любит уточнить и поболтать",
    "бережёт деньги и просит проще",
    "приходит за одним и тем же",
    "сомневается между двумя позициями",
    "спокоен и не торопит",
)
BUDGETS = (180, 250, 320, 450)


DISTRICT_SWING = 0.35  # за день спрос района меняется не больше чем на столько долей от вчерашнего


def clean_district(data: dict, previous: float = 1.0) -> dict:
    """Ответ районного голоса: поток 0.5–1.8 и не дальше ±35% от вчерашнего, доля новых 0.1–0.6,
    шесть весов частей дня 0.3–2.0 со средним 1."""
    def number(value, low, high, default):
        try:
            return max(low, min(high, float(value)))
        except (TypeError, ValueError):
            return default

    weights = []
    for raw in list(data.get("curve") or [])[:6]:
        weights.append(number(raw, 0.3, 2.0, 1.0))
    weights += [1.0] * (6 - len(weights))
    hours = [end - start for start, end in DAYPARTS]
    mean = sum(w * h for w, h in zip(weights, hours)) / sum(hours)
    return {
        "traffic": round(number(number(data.get("traffic"), 0.5, 1.8, 1.0),
                                previous * (1 - DISTRICT_SWING), previous * (1 + DISTRICT_SWING), 1.0), 2),
        "newcomers": round(number(data.get("newcomers"), 0.1, 0.6, 0.3), 2),
        "curve": [round(w / mean, 2) for w in weights],
        "why": cut_text(data.get("why"), 220),
        "buzz": cut_text(data.get("buzz"), 140),
    }


def clean_newcomers(data: dict, taken: set[str], limit: int = 8) -> list[dict]:
    """Профили новых гостей от демографа приводятся к границам: имя без повтора, характер и бюджет из списков."""
    out: list[dict] = []
    used = {name.casefold() for name in taken}
    for row in list(data.get("guests") or [])[:limit]:
        if not isinstance(row, dict):
            continue
        name = " ".join(str(row.get("name") or "").split())
        if not 2 <= len(name) <= 16 or not re.match(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё \-]*$", name):
            continue
        base, number = name, 2
        while name.casefold() in used:
            name = f"{base} {number}"
            number += 1
        used.add(name.casefold())
        trait = row.get("trait") if row.get("trait") in TRAITS else TRAITS[len(out) % len(TRAITS)]
        try:
            patience = max(1, min(5, int(row.get("patience"))))
        except (TypeError, ValueError):
            patience = 3
        try:
            wanted = int(row.get("budget"))
        except (TypeError, ValueError):
            wanted = 250
        out.append({
            "name": name, "trait": trait, "patience": patience,
            "budget": min(BUDGETS, key=lambda value: abs(value - wanted)),
            "story": " ".join(str(row.get("story") or "").split())[:160],
        })
    return out


def clean_review(text) -> str:
    return " ".join(str(text or "").split())[:140]
