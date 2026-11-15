import uuid

from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.db.models import User
from app.db.usage import get_daily_usage
from app.main import app


def test_usage_endpoint_requires_authentication():
    with TestClient(app) as client:
        response = client.get("/api/usage/me")
        assert response.status_code == 401


def test_usage_endpoint_returns_authenticated_user_usage():
    user_id = uuid.uuid4()

    async def setup():
        async with AsyncSessionLocal() as db:
            user = User(
                id=user_id,
                github_id=f"usage-api-{user_id}",
                username="usage_api_test",
            )
            db.add(user)
            await db.commit()

    async def cleanup():
        from sqlalchemy import delete
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()

    import asyncio
    asyncio.run(setup())

    async def fake_current_user():
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(User).where(User.id == user_id)
            )
            return result.scalar_one()

    app.dependency_overrides[get_current_user] = fake_current_user

    try:
        with TestClient(app) as client:
            response = client.get("/api/usage/me")

        assert response.status_code == 200
        data = response.json()

        assert data["request_count"] == 0
        assert data["estimated_tokens"] == 0
        assert data["requests_per_minute_limit"] > 0
        assert data["daily_token_budget"] > 0
        assert data["remaining_estimated_tokens"] == data["daily_token_budget"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        asyncio.run(cleanup())
