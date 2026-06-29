from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select

from core.config import settings
from database.models import LLMUsageDaily
from database.session import AsyncSessionLocal


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def key_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def key_label(api_key: str) -> str:
    digest = key_hash(api_key)
    suffix = api_key[-4:] if len(api_key) >= 4 else digest[:4]
    return f"key-{digest[:8]}-{suffix}"


async def get_daily_usage(provider: str, model: str, api_keys: Iterable[str]) -> dict[str, LLMUsageDaily]:
    hashes = [key_hash(k) for k in api_keys if k]
    if not hashes:
        return {}

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(LLMUsageDaily).where(
                LLMUsageDaily.usage_date == today_key(),
                LLMUsageDaily.provider == provider,
                LLMUsageDaily.model == model,
                LLMUsageDaily.api_key_hash.in_(hashes),
            )
        )
        return {row.api_key_hash: row for row in result.scalars().all()}


async def record_llm_success(provider: str, model: str, api_key: str, tokens_used: int) -> None:
    await _upsert_usage(
        provider=provider,
        model=model,
        api_key=api_key,
        tokens_delta=max(0, int(tokens_used or 0)),
        request_delta=1,
        error_delta=0,
        rate_limit_delta=0,
        last_status="healthy",
        last_error=None,
        blocked_until=None,
    )


async def record_llm_error(
    provider: str,
    model: str,
    api_key: str,
    error_type: str,
    message: str,
    retry_after_seconds: int | None = None,
) -> None:
    now = utc_now()
    blocked_until = None
    if retry_after_seconds:
        blocked_until = now + timedelta(seconds=max(1, retry_after_seconds))

    await _upsert_usage(
        provider=provider,
        model=model,
        api_key=api_key,
        tokens_delta=0,
        request_delta=0,
        error_delta=1,
        rate_limit_delta=1 if error_type == "rate_limit" else 0,
        last_status=error_type,
        last_error=message[:500],
        blocked_until=blocked_until,
    )


async def _upsert_usage(
    provider: str,
    model: str,
    api_key: str,
    tokens_delta: int,
    request_delta: int,
    error_delta: int,
    rate_limit_delta: int,
    last_status: str,
    last_error: str | None,
    blocked_until: datetime | None,
) -> None:
    usage_date = today_key()
    api_key_hash = key_hash(api_key)
    now = utc_now()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(LLMUsageDaily).where(
                LLMUsageDaily.usage_date == usage_date,
                LLMUsageDaily.provider == provider,
                LLMUsageDaily.model == model,
                LLMUsageDaily.api_key_hash == api_key_hash,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = LLMUsageDaily(
                usage_date=usage_date,
                provider=provider,
                model=model,
                api_key_hash=api_key_hash,
                api_key_label=key_label(api_key),
                tokens_used=0,
                request_count=0,
                error_count=0,
                rate_limit_count=0,
            )
            session.add(row)

        row.tokens_used = int(row.tokens_used or 0) + tokens_delta
        row.request_count = int(row.request_count or 0) + request_delta
        row.error_count = int(row.error_count or 0) + error_delta
        row.rate_limit_count = int(row.rate_limit_count or 0) + rate_limit_delta
        row.last_status = last_status
        row.last_error = last_error
        if blocked_until is not None:
            row.blocked_until = blocked_until
        elif last_status == "healthy":
            row.blocked_until = None
        row.updated_at = now

        await session.commit()


def groq_daily_limit_per_key() -> int:
    return max(1, int(getattr(settings, "GROQ_DAILY_TOKEN_LIMIT_PER_KEY", 500000) or 500000))
