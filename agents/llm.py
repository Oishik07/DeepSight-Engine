from __future__ import annotations

import asyncio
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from core.config import settings
from services.llm_usage import (
    get_daily_usage,
    groq_daily_limit_per_key,
    key_hash,
    record_llm_error,
    record_llm_success,
    utc_now,
)


PROVIDER_API_KEY_ENV_VARS = {
    "openrouter": ("OPENROUTER_API_KEY",),
    "groq": ("GROQ_API_KEYS", "GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_API_KEY_3", "GROQ_API_KEY"),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "claude": ("ANTHROPIC_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


@dataclass
class LLMErrorKind:
    kind: str
    retryable: bool
    user_message: str
    retry_after_seconds: int | None = None


class UserFacingLLMError(Exception):
    """Exception text is safe to show directly to end users."""


_GROQ_LOCK = asyncio.Lock()
_GROQ_MEMORY: dict[str, dict[str, float | int]] = {}
_GROQ_CLIENTS: dict[tuple[str, str], BaseChatModel] = {}


def _env_value(name: str) -> str:
    return (getattr(settings, name, None) or os.environ.get(name, "")).strip()


def _split_keys(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in re.split(r"[\s,;]+", value) if part.strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _resolve_api_keys(provider: str, api_key: str | None) -> list[str]:
    request_keys = _split_keys(api_key or "")
    if request_keys:
        return _dedupe(request_keys)

    env_names = PROVIDER_API_KEY_ENV_VARS.get(provider.lower(), ("OPENAI_API_KEY",))
    keys = []
    for env_name in env_names:
        keys.extend(_split_keys(_env_value(env_name)))

    keys = _dedupe(keys)
    if keys:
        return keys

    expected = " or ".join(env_names)
    raise ValueError(
        f"LLM API key is missing. Set {expected} in your environment/.env file "
        "or provide a key in the Configuration panel."
    )


def _resolve_api_key(provider: str, api_key: str | None) -> str:
    return _resolve_api_keys(provider, api_key)[0]


def _validate_groq_keys(api_keys: list[str]) -> None:
    bad = [key for key in api_keys if not key.startswith("gsk_")]
    if bad:
        raise ValueError("Invalid Groq API Key. Groq keys must start with 'gsk_'.")


def _build_groq_llm(api_key: str, model: str) -> BaseChatModel:
    from langchain_groq import ChatGroq

    is_small = "8b" in model.lower() or "instant" in model.lower()
    max_t = 2048 if is_small else 4096
    return ChatGroq(
        api_key=api_key,
        model=model,
        max_tokens=max_t,
    )


def _make_groq_llm(api_key: str, model: str) -> BaseChatModel:
    cache_key = (key_hash(api_key), model)
    if cache_key in _GROQ_CLIENTS:
        return _GROQ_CLIENTS[cache_key]

    llm = _build_groq_llm(api_key, model)
    _GROQ_CLIENTS[cache_key] = llm
    return llm


def _make_standard_llm(provider: str, model: str, api_key: str) -> BaseChatModel:
    if provider == "openrouter":
        if not api_key.startswith("sk-or-v1-"):
            raise ValueError("Invalid OpenRouter API Key. It must start with 'sk-or-v1-'.")
        return ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model,
            default_headers={
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "DeepSight Engine",
                "Authorization": f"Bearer {api_key}",
            },
        )
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            google_api_key=api_key,
            model=model,
        )
    if provider in {"claude", "anthropic"}:
        if not api_key.startswith("sk-ant-"):
            raise ValueError("Invalid Anthropic API Key. It must start with 'sk-ant-'.")
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            api_key=api_key,
            model_name=model,
        )
    return ChatOpenAI(
        api_key=api_key,
        model=model,
    )


def _retry_after_seconds(error_text: str) -> int | None:
    text = error_text.lower()
    match = re.search(r"try again in\s+(?:(\d+(?:\.\d+)?)m)?\s*(?:(\d+(?:\.\d+)?)s)?", text)
    if match:
        minutes = float(match.group(1) or 0)
        seconds = float(match.group(2) or 0)
        return max(1, min(900, int(minutes * 60 + seconds) + 1))

    match = re.search(r"retry[- ]after[:= ]+(\d+)", text)
    if match:
        return max(1, min(900, int(match.group(1))))

    return None


def classify_llm_error(error: Exception) -> LLMErrorKind:
    raw = str(error)
    text = raw.lower()
    retry_after = _retry_after_seconds(raw)

    if "401" in text or "403" in text or "unauthorized" in text or "invalid api key" in text:
        return LLMErrorKind(
            "auth",
            False,
            "The AI provider rejected the API key. Please update the key and try again.",
        )

    if "429" in text or "rate limit" in text or "tpm" in text or "quota" in text:
        return LLMErrorKind(
            "rate_limit",
            True,
            "Today's AI capacity is temporarily busy. DeepSight tried the available keys automatically; please retry in a short while.",
            retry_after or 75,
        )

    if "timeout" in text or "temporarily" in text or "503" in text or "502" in text or "500" in text:
        return LLMErrorKind(
            "system",
            True,
            "The AI provider is temporarily unavailable. Please retry in a moment.",
            retry_after or 20,
        )

    return LLMErrorKind(
        "system",
        False,
        "The AI provider returned an unexpected error. Please retry, or check the provider configuration.",
    )


def humanize_llm_exception(error: Exception) -> str:
    if isinstance(error, UserFacingLLMError):
        return str(error)
    if isinstance(error, ValueError):
        return str(error)
    return classify_llm_error(error).user_message


def _text_for_tokens(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(f"{k}: {_text_for_tokens(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return " ".join(_text_for_tokens(v) for v in value)
    if hasattr(value, "to_messages"):
        return _text_for_tokens(value.to_messages())
    if hasattr(value, "content"):
        return str(value.content)
    return str(value)


def _estimated_tokens(value: Any) -> int:
    text = _text_for_tokens(value)
    return max(1, len(text) // 4)


def _usage_tokens(input_value: Any, output_value: Any) -> int:
    usage = getattr(output_value, "usage_metadata", None) or {}
    if usage:
        total = usage.get("total_tokens") or usage.get("total")
        if total:
            return int(total)

    metadata = getattr(output_value, "response_metadata", None) or {}
    token_usage = metadata.get("token_usage") or metadata.get("usage") or {}
    total = token_usage.get("total_tokens") or token_usage.get("total")
    if total:
        return int(total)

    return _estimated_tokens(input_value) + _estimated_tokens(output_value)


async def _mark_active(api_key: str, delta: int) -> None:
    digest = key_hash(api_key)
    async with _GROQ_LOCK:
        state = _GROQ_MEMORY.setdefault(digest, {"active": 0, "blocked_until": 0.0})
        state["active"] = max(0, int(state.get("active", 0)) + delta)


async def _block_temporarily(api_key: str, seconds: int) -> None:
    digest = key_hash(api_key)
    async with _GROQ_LOCK:
        state = _GROQ_MEMORY.setdefault(digest, {"active": 0, "blocked_until": 0.0})
        state["blocked_until"] = max(float(state.get("blocked_until", 0.0)), time.time() + seconds)


async def _choose_groq_key(api_keys: list[str], model: str, attempted_hashes: set[str]) -> str | None:
    usage = await get_daily_usage("groq", model, api_keys)
    now_ts = time.time()
    now_dt = utc_now()
    per_key_limit = groq_daily_limit_per_key()
    candidates = []

    async with _GROQ_LOCK:
        for api_key in api_keys:
            digest = key_hash(api_key)
            if digest in attempted_hashes and len(attempted_hashes) < len(api_keys):
                continue

            memory = _GROQ_MEMORY.setdefault(digest, {"active": 0, "blocked_until": 0.0})
            memory_blocked_until = float(memory.get("blocked_until", 0.0))
            active = int(memory.get("active", 0))
            row = usage.get(digest)
            tokens = int(getattr(row, "tokens_used", 0) or 0)
            db_blocked = getattr(row, "blocked_until", None)
            db_blocked_active = bool(db_blocked and db_blocked > now_dt)
            is_blocked = memory_blocked_until > now_ts or db_blocked_active
            over_daily_limit = tokens >= per_key_limit

            if is_blocked or over_daily_limit:
                continue

            score = tokens + (active * 75000)
            candidates.append((score, random.random(), api_key))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _with_standard_error_handling(llm: BaseChatModel) -> BaseChatModel:
    original_ainvoke = llm.ainvoke

    async def ainvoke_with_retry(input_value, *args, **kwargs):
        max_retries = 3
        base_delay = 3.0

        for attempt in range(max_retries):
            try:
                return await original_ainvoke(input_value, *args, **kwargs)
            except Exception as error:
                kind = classify_llm_error(error)
                if kind.retryable and attempt < max_retries - 1:
                    sleep_time = (base_delay * (2 ** attempt)) + random.random()
                    await asyncio.sleep(min(sleep_time, kind.retry_after_seconds or sleep_time))
                    continue
                raise UserFacingLLMError(kind.user_message) from error

    object.__setattr__(llm, "ainvoke", ainvoke_with_retry)
    return llm


def _with_groq_gateway(anchor_llm: BaseChatModel, api_keys: list[str], model: str) -> BaseChatModel:
    async def ainvoke_with_gateway(input_value, *args, **kwargs):
        max_attempts = max(3, len(api_keys) * 2)
        attempted_hashes: set[str] = set()
        last_kind: LLMErrorKind | None = None

        for attempt in range(max_attempts):
            selected_key = await _choose_groq_key(api_keys, model, attempted_hashes)
            if selected_key is None:
                wait_for = min(20, 4 + attempt * 2)
                if attempt < max_attempts - 1:
                    await asyncio.sleep(wait_for)
                    attempted_hashes.clear()
                    continue
                message = "Daily AI capacity is temporarily busy across all configured Groq keys. Please retry shortly."
                if last_kind:
                    message = last_kind.user_message
                raise UserFacingLLMError(message)

            selected_hash = key_hash(selected_key)
            attempted_hashes.add(selected_hash)
            llm = _make_groq_llm(selected_key, model)

            await _mark_active(selected_key, 1)
            try:
                result = await llm.ainvoke(input_value, *args, **kwargs)
                tokens = _usage_tokens(input_value, result)
                await record_llm_success("groq", model, selected_key, tokens)
                return result
            except Exception as error:
                kind = classify_llm_error(error)
                last_kind = kind
                retry_after = kind.retry_after_seconds
                if kind.kind == "auth" and len(api_keys) > 1:
                    retry_after = 3600
                await record_llm_error(
                    "groq",
                    model,
                    selected_key,
                    kind.kind,
                    kind.user_message,
                    retry_after,
                )
                if retry_after:
                    await _block_temporarily(selected_key, retry_after)
                if len(api_keys) > 1 and kind.kind in {"auth", "rate_limit", "system"}:
                    continue
                if kind.retryable and attempt < max_attempts - 1:
                    await asyncio.sleep(min(15, kind.retry_after_seconds or 5))
                    continue
                raise UserFacingLLMError(kind.user_message) from error
            finally:
                await _mark_active(selected_key, -1)

        raise UserFacingLLMError("DeepSight could not reach the AI provider after several automatic retries.")

    object.__setattr__(anchor_llm, "ainvoke", ainvoke_with_gateway)
    return anchor_llm


def get_llm(provider: str, model: str, api_key: str | None) -> BaseChatModel:
    """
    Returns the appropriate LLM based on provider.
    Groq uses a small gateway that can route across multiple configured keys.
    """
    provider = (provider or "").lower()

    if provider == "groq":
        api_keys = _resolve_api_keys(provider, api_key)
        _validate_groq_keys(api_keys)
        anchor = _build_groq_llm(api_keys[0], model)
        return _with_groq_gateway(anchor, api_keys, model)

    resolved_api_key = _resolve_api_key(provider, api_key)
    llm = _make_standard_llm(provider, model, resolved_api_key)
    return _with_standard_error_handling(llm)
