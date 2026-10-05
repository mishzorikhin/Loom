import copy
import json
import time
from datetime import datetime

import httpx

import app.db as db
from app import cassette, log
from app.config import PROMPTS
from app.rules import BUDGETS, CRITIC_CODES, EFFECT_TYPES, MOODS, TRAITS, style_problem
from app.venues import DATACENTER


class TransportError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class SchemaError(Exception):
    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.message = message
        self.raw = raw


TEMPERATURE = {"adjudicator": 0.3, "crowd": 0.6, "client": 0.7, "verdict": 0.7, "staff": 0.4, "manager": 0.3, "critic": 0.1, "queue": 0.6, "narrator": 0.9, "director": 0.4, "world": 0.2, "district": 0.5, "demographer": 0.9}
MAX_TOKENS = {"adjudicator": 900, "crowd": 700, "manager": 420, "critic": 560, "queue": 120, "narrator": 520, "director": 520, "world": 1000, "district": 380, "demographer": 900, "verdict": 240}


def load_system(name: str, venue: str = "") -> str:
    """Описание роли. У заведения может быть свой подкаталог: роли без своего файла берутся из общего."""
    if venue and (PROMPTS / venue / f"{name}.md").exists():
        return (PROMPTS / venue / f"{name}.md").read_text(encoding="utf-8").strip()
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()


def parse_content(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise SchemaError("Ответ не JSON", raw)
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise SchemaError("Ответ не JSON", raw) from exc
    if not isinstance(data, dict):
        raise SchemaError("Ответ не объект", raw)
    return data


def _check(data: dict, required: list[str], enums: dict[str, set[str]]) -> None:
    missing = [key for key in required if key not in data]
    if missing:
        raise SchemaError("Нет полей: " + ", ".join(missing), json.dumps(data, ensure_ascii=False))
    for key, allowed in enums.items():
        if data.get(key) not in allowed:
            raise SchemaError(f"Поле {key} вне списка", json.dumps(data, ensure_ascii=False))


def validate(agent: str, data: dict, final_staff: bool = False) -> dict:
    if agent == "client":
        _check(data, ["say", "item_id", "request", "willing_to_wait"], {})
        if not isinstance(data["say"], str) or not data["say"].strip():
            raise SchemaError("Пустая реплика", json.dumps(data, ensure_ascii=False))
        data["item_id"] = str(data.get("item_id") or "")
        data["request"] = str(data.get("request") or "")
        data["willing_to_wait"] = bool(data.get("willing_to_wait"))
        return data
    if agent == "staff":
        allowed = {"serve", "refuse"} if final_staff else {"ask", "serve", "refuse"}
        _check(data, ["say", "action", "item_id"], {"action": allowed})
        if not isinstance(data["say"], str) or not data["say"].strip():
            raise SchemaError("Пустая реплика", json.dumps(data, ensure_ascii=False))
        data["item_id"] = str(data.get("item_id") or "")
        return data
    if agent == "district":
        _check(data, ["traffic", "newcomers", "curve", "why", "buzz"], {})
        if not isinstance(data["curve"], list):
            raise SchemaError("curve не список", json.dumps(data, ensure_ascii=False))
        return data
    if agent == "demographer":
        _check(data, ["guests"], {})
        if not isinstance(data["guests"], list):
            raise SchemaError("guests не список", json.dumps(data, ensure_ascii=False))
        return data
    if agent in ("narrator", "director"):
        _check(data, ["headline", "story", "effects"], {})
        if not isinstance(data["effects"], list):
            raise SchemaError("effects не список", json.dumps(data, ensure_ascii=False))
        return data
    if agent == "world":
        _check(data, ["say", "changes", "proposals"], {})
        if not isinstance(data["changes"], list) or not isinstance(data["proposals"], list) or any(not isinstance(x, str) for x in data["proposals"]):
            raise SchemaError("Действия и предложения должны быть списками", json.dumps(data, ensure_ascii=False))
        return data
    if agent == "adjudicator":
        _check(data, ["say", "ops"], {})
        if not isinstance(data["ops"], list):
            raise SchemaError("ops не список", json.dumps(data, ensure_ascii=False))
        data["say"] = str(data.get("say") or "")
        return data
    if agent == "crowd":
        _check(data, ["people"], {})
        if not isinstance(data["people"], list):
            raise SchemaError("people не список", json.dumps(data, ensure_ascii=False))
        return data
    if agent == "queue":
        _check(data, ["stay", "say"], {})
        data["stay"] = bool(data["stay"])
        data["say"] = str(data.get("say") or "")
        return data
    if agent == "critic":
        _check(data, ["score", "issues"], {})
        if not isinstance(data["issues"], list):
            raise SchemaError("issues не список", json.dumps(data, ensure_ascii=False))
        return data
    if agent == "verdict":
        _check(data, ["say", "liked", "return", "return_in_days", "recommend"], {"return": {"yes", "maybe", "no"}})
        return data
    _check(data, ["say", "changes"], {})
    if not isinstance(data["changes"], list):
        raise SchemaError("changes не список", json.dumps(data, ensure_ascii=False))
    data["say"] = str(data.get("say") or "")
    return data


SCHEMAS = {
    "client": {
        "name": "client_turn",
        "schema": {
            "type": "object",
            "properties": {
                "say": {"type": "string"},
                "item_id": {"type": "string"},
                "request": {"type": "string"},
                "willing_to_wait": {"type": "boolean"},
            },
            "required": ["say", "item_id", "request", "willing_to_wait"],
            "additionalProperties": False,
        },
    },
    "staff": {
        "name": "staff_turn",
        "schema": {
            "type": "object",
            "properties": {
                "say": {"type": "string"},
                "action": {"type": "string", "enum": ["ask", "serve", "refuse"]},
                "item_id": {"type": "string"},
                "mood": {"type": "string", "enum": list(MOODS)},
            },
            "required": ["say", "action", "item_id", "mood"],
            "additionalProperties": False,
        },
    },
    "staff_final": {
        "name": "staff_final",
        "schema": {
            "type": "object",
            "properties": {
                "say": {"type": "string"},
                "action": {"type": "string", "enum": ["serve", "refuse"]},
                "item_id": {"type": "string"},
                "mood": {"type": "string", "enum": list(MOODS)},
            },
            "required": ["say", "action", "item_id", "mood"],
            "additionalProperties": False,
        },
    },
    "district": {
        "name": "district_voice",
        "schema": {
            "type": "object",
            "properties": {
                "traffic": {"type": "number"},
                "newcomers": {"type": "number"},
                "curve": {"type": "array", "items": {"type": "number"}},
                "why": {"type": "string"},
                "buzz": {"type": "string"},
            },
            "required": ["traffic", "newcomers", "curve", "why", "buzz"],
            "additionalProperties": False,
        },
    },
    "demographer": {
        "name": "newcomers",
        "schema": {
            "type": "object",
            "properties": {
                "guests": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "trait": {"type": "string", "enum": list(TRAITS)},
                            "patience": {"type": "integer"},
                            "budget": {"type": "integer", "enum": list(BUDGETS)},
                            "story": {"type": "string"},
                        },
                        "required": ["name", "trait", "patience", "budget", "story"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["guests"],
            "additionalProperties": False,
        },
    },
    "event": {
        "name": "day_event",
        "schema": {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "story": {"type": "string"},
                "effects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": list(EFFECT_TYPES)},
                            "target": {"type": "string"},
                            "amount": {"type": "number"},
                            "days": {"type": "integer"},
                        },
                        "required": ["type", "target", "amount", "days"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["headline", "story", "effects"],
            "additionalProperties": False,
        },
    },
    "queue": {
        "name": "queue_choice",
        "schema": {
            "type": "object",
            "properties": {"stay": {"type": "boolean"}, "say": {"type": "string"}},
            "required": ["stay", "say"],
            "additionalProperties": False,
        },
    },
    "critic": {
        "name": "dialog_review",
        "schema": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "enum": list(CRITIC_CODES)},
                            "line": {"type": "integer"},
                            "quote": {"type": "string"},
                            "severity": {"type": "string", "enum": ["low", "high"]},
                            "note": {"type": "string"},
                        },
                        "required": ["code", "line", "quote", "severity", "note"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["score", "issues"],
            "additionalProperties": False,
        },
    },
    "verdict": {
        "name": "visit_verdict",
        "schema": {
            "type": "object",
            "properties": {
                "say": {"type": "string"},
                "liked": {"type": "integer"},
                "return": {"type": "string", "enum": ["yes", "maybe", "no"]},
                "return_in_days": {"type": "integer"},
                "recommend": {"type": "boolean"},
                "mood": {"type": "string", "enum": list(MOODS)},
                "review": {"type": "string"},
            },
            "required": ["say", "liked", "return", "return_in_days", "recommend", "mood", "review"],
            "additionalProperties": False,
        },
    },
    "manager": {
        "name": "manager_week",
        "schema": {
            "type": "object",
            "properties": {
                "say": {"type": "string"},
                "changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "enum": ["set_price", "set_available", "add_item"]},
                            "item_id": {"type": "string"},
                            "name": {"type": "string"},
                            "price": {"type": "integer"},
                            "minutes": {"type": "integer"},
                            "available": {"type": "boolean"},
                        },
                        "required": ["op", "item_id", "name", "price", "minutes", "available"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["say", "changes"],
            "additionalProperties": False,
        },
    },
}

_PATCH_OP = {
    "type": "object",
    "properties": {
        "op": {"type": "string", "enum": ["spawn", "modify", "remove", "area", "fact", "place"]},
        "id": {"type": "string"},
        "kind": {"type": "string"},
        "x": {"type": "number"}, "y": {"type": "number"}, "r": {"type": "number"},
        "blocks": {"type": "boolean"},
        "hazard": {"type": "number"},
        "minutes": {"type": "number"},
        "effect": {"type": "string", "enum": ["damage", "mood", ""]},
        "amount": {"type": "number"},
        "text": {"type": "string"},
        "status": {"type": "string"},
        "label": {"type": "string"},
        "shape": {"type": "string", "enum": ["circle", "ring", "square", "cloud", "star"]},
        "color": {"type": "string"},
        "size": {"type": "number"},
    },
    "required": ["op", "id", "kind", "x", "y", "r", "blocks", "hazard", "minutes", "effect", "amount", "text", "status", "label",
                 "shape", "color", "size"],
    "additionalProperties": False,
}
SCHEMAS["adjudicator"] = {
    "name": "world_patch",
    "schema": {
        "type": "object",
        "properties": {"say": {"type": "string"}, "ops": {"type": "array", "items": _PATCH_OP}},
        "required": ["say", "ops"],
        "additionalProperties": False,
    },
}
SCHEMAS["crowd"] = {
    "name": "crowd_choices",
    "schema": {
        "type": "object",
        "properties": {
            "people": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "do": {"type": "string", "enum": ["continue", "flee", "watch", "wait", "home"]},
                        "say": {"type": "string"},
                        "mood": {"type": "string", "enum": list(MOODS)},
                        "minutes": {"type": "number"},
                    },
                    "required": ["id", "do", "say", "mood", "minutes"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["people"],
        "additionalProperties": False,
    },
}

SCHEMAS["demographer_datacenter"] = copy.deepcopy(SCHEMAS["demographer"])
_dc_guest = SCHEMAS["demographer_datacenter"]["schema"]["properties"]["guests"]["items"]["properties"]
_dc_guest["trait"]["enum"] = list(DATACENTER.traits)
_dc_guest["budget"]["enum"] = list(DATACENTER.budgets)

SCHEMAS["world"] = {
    "name": "world_actions",
    "schema": {
        "type": "object",
        "properties": {
            "say": {"type": "string"},
            "changes": SCHEMAS["manager"]["schema"]["properties"]["changes"],
            "proposals": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["say", "changes", "proposals"],
        "additionalProperties": False,
    },
}
SCHEMAS["world"] = copy.deepcopy(SCHEMAS["world"])
SCHEMAS["world"]["schema"]["properties"]["changes"]["items"]["properties"]["op"] = {"type": "string"}


class LLM:
    def __init__(self):
        self.client = httpx.AsyncClient(limits=httpx.Limits(keepalive_expiry=3))

    def _headers(self) -> dict:
        """Ключ API из настроек. Без ключа (локальный сервер) заголовка нет."""
        key = db.setting("llm_api_key")
        return {"Authorization": f"Bearer {key}"} if key else {}

    async def _post(self, url: str, body: dict, timeout: float):
        # Сервер модели рвёт простаивающие соединения: протухший keep-alive не считается обрывом.
        try:
            return await self.client.post(url, json=body, timeout=timeout, headers=self._headers())
        except (httpx.RemoteProtocolError, httpx.ConnectError):
            return await self.client.post(url, json=body, timeout=timeout, headers=self._headers())

    async def aclose(self):
        await self.client.aclose()

    def _settings(self, target: str = "main") -> tuple[str, str, float]:
        """Адрес, модель и таймаут. Для критика можно задать отдельную модель, иначе берётся основная."""
        base, model = db.setting("llm_base_url"), db.setting("llm_model")
        if target == "critic":
            base = db.setting("critic_base_url") or base
            model = db.setting("critic_model") or model
        return base, model, float(db.setting("llm_timeout") or 60)

    async def health(self) -> dict:
        base, model, timeout = self._settings()
        root = base[:-3] if base.endswith("/v1") else base
        try:
            headers = self._headers()
            models = await self.client.get(f"{base}/models", timeout=5, headers=headers)
            if models.status_code in (401, 403):
                return {"ok": False, "detail": "Сервер не принял ключ API", "base_url": base, "model": model}
            models.raise_for_status()
            found = next((item for item in models.json().get("data", []) if item.get("id") == model), None)
            if found is None:
                return {"ok": False, "detail": f"В списке нет модели {model}", "base_url": base, "model": model}
            # Свой сервер llama.cpp отдаёт состояние модели и /health. Облачные сервисы обычно нет: тогда достаточно, что модель в списке.
            status = (found.get("status") or {}).get("value")
            if status and status != "loaded":
                return {"ok": False, "detail": f"{model}: {status} (сервер может подгрузить по первому запросу)", "base_url": base, "model": model}
            if status:
                health = await self.client.get(f"{root}/health", timeout=5, headers=headers)
                if health.status_code != 200:
                    return {"ok": False, "detail": f"health {health.status_code}", "base_url": base, "model": model}
            return {"ok": True, "detail": f"{model} доступна" if not status else f"{model} загружена", "base_url": base, "model": model}
        except Exception as exc:
            return {"ok": False, "detail": f"Нет связи: {exc.__class__.__name__}", "base_url": base, "model": model}

    async def complete(
        self,
        *,
        agent: str,
        schema_key: str,
        system: str,
        user: str,
        visit_id: int | None,
        week_day: int | None,
        final_staff: bool = False,
        echo_of: str = "",
        target: str = "main",
    ) -> dict:
        base, model, timeout = self._settings(target)
        schema = SCHEMAS[schema_key]
        if cassette.replaying():
            return self._replayed(agent, schema_key, system, user, visit_id, week_day, final_staff, echo_of, model)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        body = {
            "model": model,
            "temperature": TEMPERATURE.get(agent, 0.3),
            "max_tokens": MAX_TOKENS.get(agent, 180),
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema["name"], "strict": True, "schema": schema["schema"]},
            },
        }
        last_error = "пустой ответ"
        raw = ""
        for attempt in (1, 2):
            log.event("llm.start", agent=agent, visit_id=visit_id, week_day=week_day, attempt=attempt,
                      prompt_chars=len(system) + len(user), model=model)
            prompt_user = user if attempt == 1 else (
                user + f"\n\nПрошлый ответ не разобран: {last_error}. Верни только объект по схеме."
            )
            body["messages"] = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt_user},
            ]
            started = time.perf_counter()
            raw = ""
            error = ""
            parsed = None
            usage = {}
            try:
                response = await self._post(f"{base}/chat/completions", body, timeout)
                latency = int((time.perf_counter() - started) * 1000)
                if response.status_code >= 400:
                    raise TransportError(f"HTTP {response.status_code}: {response.text[:500]}")
                payload = response.json()
                usage = payload.get("usage") or {}
                raw = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                data = parse_content(raw)
                parsed = validate(agent, data, final_staff=final_staff)
                problem = style_problem(agent, parsed, echo_of)
                if problem and attempt == 1:
                    raise SchemaError(problem, raw)
            except TransportError as exc:
                latency = int((time.perf_counter() - started) * 1000)
                self._log(agent, visit_id, week_day, model, latency, usage, system, prompt_user, raw, None, exc.message, attempt)
                raise
            except (SchemaError, KeyError, IndexError, json.JSONDecodeError) as exc:
                latency = int((time.perf_counter() - started) * 1000)
                last_error = getattr(exc, "message", str(exc))
                error = last_error
                self._log(agent, visit_id, week_day, model, latency, usage, system, prompt_user, raw, None, error, attempt)
                if attempt == 2:
                    raise SchemaError(last_error, raw) from exc
                continue
            except httpx.TimeoutException as exc:
                latency = int((time.perf_counter() - started) * 1000)
                self._log(agent, visit_id, week_day, model, latency, {}, system, prompt_user, "", None, "Таймаут", attempt)
                raise TransportError("Таймаут запроса к модели") from exc
            except httpx.HTTPError as exc:
                latency = int((time.perf_counter() - started) * 1000)
                self._log(agent, visit_id, week_day, model, latency, {}, system, prompt_user, "", None, str(exc), attempt)
                raise TransportError(f"Нет связи с моделью: {exc.__class__.__name__}") from exc

            self._log(
                agent, visit_id, week_day, model, latency, usage, system, prompt_user, raw,
                json.dumps(parsed, ensure_ascii=False), "", attempt,
            )
            cassette.record(agent, schema_key, system, user, parsed, visit_id, model)
            return parsed
        raise SchemaError(last_error, raw)

    def _replayed(self, agent, schema_key, system, user, visit_id, week_day, final_staff, echo_of, model) -> dict:
        """Проигрывание кассеты: ответ берётся из записи, запроса к модели нет. Он проходит ту же проверку, что живой."""
        found = cassette.replay(agent, system, user)
        if found is None:
            self._log(agent, visit_id, week_day, "кассета", 0, {}, system, user, "", None, "в кассете нет записи", 1)
            raise TransportError(f"В кассете нет записи для роли {agent}")
        data, drift = found
        if drift:
            log.event("cassette.drift", "warn", agent=agent, visit_id=visit_id)
        parsed = validate(agent, dict(data), final_staff=final_staff)
        self._log(agent, visit_id, week_day, "кассета", 0, {}, system, user, json.dumps(data, ensure_ascii=False),
                  json.dumps(parsed, ensure_ascii=False), "", 1)
        return parsed

    def _log(self, agent, visit_id, week_day, model, latency, usage, system, user, raw, parsed, error, attempt):
        details = usage.get("prompt_tokens_details") or {}
        log.event(
            "llm.call", "warn" if error else "info", agent=agent, visit_id=visit_id, week_day=week_day,
            attempt=attempt, ms=latency, ptok=usage.get("prompt_tokens"), ctok=usage.get("completion_tokens"),
            cached=details.get("cached_tokens"), raw_len=len(raw or ""), ok=not error, err=error or None,
        )
        db.add_llm(
            created_at=datetime.now().isoformat(timespec="seconds"),
            agent=agent,
            visit_id=visit_id,
            week_day=week_day,
            model=model,
            latency_ms=latency,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cached_tokens=details.get("cached_tokens"),
            system_prompt=system,
            user_prompt=user,
            raw_content=raw,
            parsed_json=parsed,
            error=error or "",
            attempt=attempt,
        )
