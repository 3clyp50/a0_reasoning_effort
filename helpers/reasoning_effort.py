import re
from functools import lru_cache
from time import monotonic
from typing import Any

import httpx
import litellm

from helpers.providers import get_provider_config
from plugins._model_config.helpers.model_config import get_chat_model_config


CONTEXT_KEY = "a0_reasoning_effort_override"
CUSTOM_EFFORT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
CANONICAL_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
PROVIDER_CACHE_SECONDS = 15 * 60
PROVIDER_TIMEOUT_SECONDS = 5.0
PROVIDER_METADATA_IDS = frozenset({"a0_venice", "venice", "openrouter"})
_provider_models_cache: dict[tuple[str, str], tuple[float, Any]] = {}


def normalize_effort(value: Any) -> str:
    effort = str(value or "").strip().lower()
    return effort if not effort or CUSTOM_EFFORT_PATTERN.fullmatch(effort) else ""


def _normalize_efforts(values: Any) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    efforts: list[str] = []
    for value in values:
        effort = normalize_effort(value)
        if effort and effort not in efforts:
            efforts.append(effort)
    return tuple(value for value in CANONICAL_EFFORTS if value in efforts) + tuple(
        value for value in efforts if value not in CANONICAL_EFFORTS
    )


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
    }.get(effort, effort.replace("_", " ").replace("-", " ").title())


def _provider_discovery(provider: str, model: str, data: Any) -> tuple[str, tuple[str, ...]]:
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return "unknown", ()
    item = next(
        (
            candidate
            for candidate in data["data"]
            if isinstance(candidate, dict) and str(candidate.get("id") or "") == model
        ),
        None,
    )
    if not item:
        return "unknown", ()

    if provider in {"a0_venice", "venice"}:
        model_spec = item.get("model_spec") if isinstance(item.get("model_spec"), dict) else {}
        capabilities = (
            model_spec.get("capabilities")
            if isinstance(model_spec.get("capabilities"), dict)
            else {}
        )
        if capabilities.get("supportsReasoningEffort") is False:
            return "unsupported", ()
        efforts = _normalize_efforts(capabilities.get("reasoningEffortOptions"))
        return ("supported", efforts) if efforts else ("unknown", ())

    if provider == "openrouter":
        reasoning = item.get("reasoning")
        if not isinstance(reasoning, dict) or "supported_efforts" not in reasoning:
            return "unknown", ()
        raw_efforts = reasoning.get("supported_efforts")
        efforts = CANONICAL_EFFORTS if raw_efforts is None else _normalize_efforts(raw_efforts)
        if reasoning.get("mandatory") is True:
            efforts = tuple(effort for effort in efforts if effort != "none")
        return ("supported", efforts) if efforts else ("unknown", ())

    return "unknown", ()


async def _provider_models(provider: str) -> Any:
    if provider not in PROVIDER_METADATA_IDS:
        return None
    provider_config = get_provider_config("chat", provider) or {}
    endpoint = str((provider_config.get("models_list") or {}).get("endpoint_url") or "")
    if not endpoint.startswith("https://"):
        return None

    cache_key = (provider, endpoint)
    cached = _provider_models_cache.get(cache_key)
    now = monotonic()
    if cached and cached[0] > now:
        return cached[1]

    data = None
    try:
        import models

        headers: dict[str, str] = {}
        api_key = models.get_api_key(provider)
        if api_key and api_key != "None":
            headers["Authorization"] = f"Bearer {api_key}"
        extra_headers = (provider_config.get("kwargs") or {}).get("extra_headers") or {}
        if isinstance(extra_headers, dict):
            headers.update(
                {str(key): value for key, value in extra_headers.items() if isinstance(value, str)}
            )
        params = (provider_config.get("models_list") or {}).get("params") or {}
        async with httpx.AsyncClient(timeout=PROVIDER_TIMEOUT_SECONDS) as client:
            response = await client.get(endpoint, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception:
        pass

    _provider_models_cache[cache_key] = (now + PROVIDER_CACHE_SECONDS, data)
    return data


def _with_options(
    state: dict[str, Any], efforts: tuple[str, ...], support: str, option_source: str
) -> dict[str, Any]:
    provider = str(state["model"]["provider"])
    model = str(state["model"]["name"])
    provider_config = get_provider_config("chat", provider) or {}
    litellm_provider = str(provider_config.get("litellm_provider") or provider).strip().lower()
    updated = dict(state)
    updated.update(
        {
            "available": bool(efforts),
            "support": support,
            "option_source": option_source,
            "options": [
                {
                    "value": effort,
                    "label": _effort_label(effort, litellm_provider, model),
                }
                for effort in efforts
            ],
        }
    )
    return updated


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

    state = {
        "available": bool(efforts),
        "support": "supported" if efforts else "unknown",
        "option_source": "litellm" if efforts else "none",
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
    return state


async def get_discovered_state(agent) -> dict[str, Any]:
    state = get_state(agent)
    if state["available"]:
        return state
    provider = str(state["model"]["provider"])
    model = str(state["model"]["name"])
    support, efforts = _provider_discovery(provider, model, await _provider_models(provider))
    return _with_options(state, efforts, support, "provider" if support != "unknown" else "none")


def get_override(agent) -> str:
    return str(get_state(agent).get("selected") or "")


if __name__ == "__main__":
    import asyncio
    import sys
    from unittest.mock import AsyncMock, patch

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
    assert _normalize_efforts(["high", "low", "extra", "low"]) == ("low", "high", "extra")
    venice = {
        "data": [
            {
                "id": "claude-fable-5",
                "model_spec": {
                    "capabilities": {
                        "supportsReasoningEffort": True,
                        "reasoningEffortOptions": ["low", "medium", "high", "xhigh", "max"],
                    }
                },
            },
            {
                "id": "llama",
                "model_spec": {"capabilities": {"supportsReasoningEffort": False}},
            },
        ]
    }
    assert _provider_discovery("a0_venice", "claude-fable-5", venice) == (
        "supported",
        ("low", "medium", "high", "xhigh", "max"),
    )
    assert _provider_discovery("venice", "llama", venice) == ("unsupported", ())
    openrouter = {
        "data": [
            {
                "id": "anthropic/claude",
                "reasoning": {
                    "supported_efforts": None,
                    "mandatory": True,
                },
            }
        ]
    }
    assert _provider_discovery("openrouter", "anthropic/claude", openrouter) == (
        "supported",
        ("minimal", "low", "medium", "high", "xhigh", "max"),
    )
    assert _provider_discovery("openrouter", "missing", openrouter) == ("unknown", ())
    assert _provider_discovery("other", "model", {}) == ("unknown", ())
    litellm_state = {"available": True}
    with (
        patch.object(sys.modules[__name__], "get_state", return_value=litellm_state),
        patch.object(sys.modules[__name__], "_provider_models", new_callable=AsyncMock) as fetch,
    ):
        assert asyncio.run(get_discovered_state(None)) is litellm_state
        fetch.assert_not_awaited()
    print("reasoning-effort capability mapping: ok")
