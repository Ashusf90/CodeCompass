import asyncio
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import User
from app.db.usage import (
    check_rate_limit,
    reserve_daily_tokens,
    get_daily_usage,
)


@pytest.mark.parametrize("limit", [3])
def test_concurrent_rate_limit_enforces_exact_limit(limit):
    user_id = uuid.uuid4()
    original_limit = settings.chat_requests_per_minute
    settings.chat_requests_per_minute = limit

    async def run_test():
        async with AsyncSessionLocal() as db:
            db.add(User(
                id=user_id,
                github_id=f"usage-test-{user_id}",
                username="usage_limit_test",
            ))
            await db.commit()

        try:
            results = await asyncio.gather(
                *[check_rate_limit(user_id) for _ in range(8)],
                return_exceptions=True,
            )

            successes = [r for r in results if not isinstance(r, Exception)]
            failures = [r for r in results if isinstance(r, Exception)]

            assert len(successes) == limit
            assert len(failures) == 8 - limit
            assert all(
                isinstance(error, HTTPException) and error.status_code == 429
                for error in failures
            )

            usage = await get_daily_usage(user_id)
            assert usage["request_count"] == limit
        finally:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()

    try:
        asyncio.run(run_test())
    finally:
        settings.chat_requests_per_minute = original_limit


def test_daily_token_budget_rejects_excess_usage():
    user_id = uuid.uuid4()
    original_budget = settings.daily_token_budget
    settings.daily_token_budget = 100

    async def run_test():
        async with AsyncSessionLocal() as db:
            db.add(User(
                id=user_id,
                github_id=f"usage-test-{user_id}",
                username="usage_budget_test",
            ))
            await db.commit()

        try:
            total = await reserve_daily_tokens(user_id, 60)
            assert total == 60

            with pytest.raises(HTTPException) as error:
                await reserve_daily_tokens(user_id, 50)

            assert error.value.status_code == 429

            usage = await get_daily_usage(user_id)
            assert usage["estimated_tokens"] == 60
        finally:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()

    try:
        asyncio.run(run_test())
    finally:
        settings.daily_token_budget = original_budget
