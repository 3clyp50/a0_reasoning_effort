import re
from functools import lru_cache
from typing import Any

import litellm

from helpers.providers import get_provider_config
from plugins._model_config.helpers.model_config import get_chat_model_config


CONTEXT_KEY = "a0_reasoning_effort_override"
CUSTOM_EFFORT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def normalize_effort(value: Any) -> str:
    effort = str(value or "").strip().lower()
    return effort if not effort or CUSTOM_EFFORT_PATTERN.fullmatch(effort) else ""


def _efforts_from_info(info: dict[str, Any]) -> tuple[str, ...]:
    efforts: list[str] = []
    if info.get("supports_none_reasoning_effort") is True:
        efforts.append("none")
    if info.get("supports_minimal_reasoning_effort") is True:
        efforts.append("minimal")
    if info.get("supports_low_reasoning_effort") is not False:
        efforts.append("low")
    efforts.extend(("medium", "high"))
    if info.get("supports_xhigh_reasoning_effort") is True:
        efforts.append("xhigh")
    if info.get("supports_max_reasoning_effort") is True:
        efforts.append("max")
    return tuple(efforts)


@lru_cache(maxsize=256)
def _supported_efforts(litellm_provider: str, model: str) -> tuple[str, ...]:
    try:
        params = litellm.get_supported_openai_params(
            model=model,
            custom_llm_provider=litellm_provider,
        )
        info = litellm.get_model_info(
            model=model,
            custom_llm_provider=litellm_provider,
        )
    except Exception:
        return ()

    if "reasoning_effort" not in (params or ()) or info.get("supports_reasoning") is not True:
        return ()
    return _efforts_from_info(info)


def _effort_label(effort: str, litellm_provider: str, model: str) -> str:
    if effort == "xhigh":
        is_anthropic = (
            litellm_provider == "anthropic"
            or model.lower().startswith("anthropic/")
            or "claude" in model.lower()
        )
        return "Extra" if is_anthropic else "XHigh"
    return {
        "none": "Off",
        "minimal": "Minimal",
        "low": "Low",
        "medium": "Medium",
        "high": "High",
        "max": "Max",
    }[effort]


def get_state(agent) -> dict[str, Any]:
    config = get_chat_model_config(agent)
    provider = str(config.get("provider") or "").strip().lower()
    model = str(config.get("name") or "").strip()
    provider_config = get_provider_config("chat", provider) or {}
    litellm_provider = str(provider_config.get("litellm_provider") or provider).strip().lower()
    if litellm_provider == "other":
        litellm_provider = "openai"

    efforts = _supported_efforts(litellm_provider, model) if provider and model else ()
    model_key = f"{provider}/{model}"
    stored = agent.context.get_data(CONTEXT_KEY) if getattr(agent, "context", None) else None
    selected = ""
    if isinstance(stored, dict) and stored.get("model") == model_key:
        selected = normalize_effort(stored.get("effort"))

    kwargs = config.get("kwargs") if isinstance(config.get("kwargs"), dict) else {}
    preset_effort = normalize_effort(kwargs.get("reasoning_effort"))

    return {
        "available": bool(efforts),
        "model": {"provider": provider, "name": model, "key": model_key},
        "options": [
            {
                "value": effort,
                "label": _effort_label(effort, litellm_provider, model),
            }
            for effort in efforts
        ],
        "selected": selected,
        "effective": selected or preset_effort,
        "preset_effort": preset_effort,
        "source": "chat" if selected else ("preset" if preset_effort else "provider"),
    }


def get_override(agent) -> str:
    return str(get_state(agent).get("selected") or "")


if __name__ == "__main__":
    assert _efforts_from_info({}) == ("low", "medium", "high")
    assert _efforts_from_info(
        {
            "supports_low_reasoning_effort": False,
            "supports_xhigh_reasoning_effort": True,
        }
    ) == ("medium", "high", "xhigh")
    assert _effort_label("xhigh", "anthropic", "claude-opus") == "Extra"
    assert normalize_effort(" Extra ") == "extra"
    assert normalize_effort("bad value") == ""
    assert normalize_effort("x" * 65) == ""
    print("reasoning-effort capability mapping: ok")
