import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.authorization import get_owned_repository
from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_owner_can_access_repository():
    user_id = uuid.uuid4()
    repository = SimpleNamespace(id=uuid.uuid4(), user_id=user_id)
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalar_one_or_none=lambda: repository
            )
        )
    )
    user = SimpleNamespace(id=user_id)

    result = await get_owned_repository(repository.id, db, user)

    assert result is repository
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_owner_cannot_access_repository():
    repository_id = uuid.uuid4()
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalar_one_or_none=lambda: None
            )
        )
    )
    user = SimpleNamespace(id=uuid.uuid4())

    with pytest.raises(HTTPException) as exc:
        await get_owned_repository(repository_id, db, user)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Repository not found"


def test_repository_list_requires_login():
    response = client.get("/api/repositories")
    assert response.status_code == 401


def test_repository_creation_requires_login():
    response = client.post(
        "/api/repositories",
        json={"github_url": "https://github.com/owner/repo"},
    )
    assert response.status_code == 401


def test_repository_status_requires_login():
    response = client.get(
        f"/api/repositories/{uuid.uuid4()}"
    )
    assert response.status_code == 401


def test_repository_search_requires_login():
    response = client.post(
        f"/api/repositories/{uuid.uuid4()}/search",
        json={"query": "How does authentication work?"},
    )
    assert response.status_code == 401


def test_repository_chat_requires_login():
    response = client.post(
        f"/api/repositories/{uuid.uuid4()}/chat/stream",
        json={"query": "How does authentication work?"},
    )
    assert response.status_code == 401


def test_repository_file_requires_login():
    response = client.get(
        f"/api/repositories/{uuid.uuid4()}/files",
        params={"file_path": "src/main.py"},
    )
    assert response.status_code == 401
