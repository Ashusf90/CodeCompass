import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.db.models import User, Repository, ChatSession, ChatMessage
from app.main import app


async def create_test_data():
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()

    async with AsyncSessionLocal() as db:
        owner = User(
            id=owner_id,
            github_id=f"test-{owner_id}",
            username="chat_owner_test",
        )
        other = User(
            id=other_id,
            github_id=f"test-{other_id}",
            username="chat_other_test",
        )
        db.add_all([owner, other])
        await db.flush()

        repository = Repository(
            user_id=owner_id,
            github_url=f"https://github.com/test/{owner_id}",
            name="owner-test-repo",
            status="ready",
        )
        other_repository = Repository(
            user_id=other_id,
            github_url=f"https://github.com/test/{other_id}",
            name="other-test-repo",
            status="ready",
        )
        db.add_all([repository, other_repository])
        await db.commit()

        return {
            "owner_id": owner_id,
            "other_id": other_id,
            "repository_id": repository.id,
            "other_repository_id": other_repository.id,
        }


async def cleanup_test_data(data):
    async with AsyncSessionLocal() as db:
        session_ids = (
            select(ChatSession.id).where(
                ChatSession.user_id.in_(
                    [data["owner_id"], data["other_id"]]
                )
            )
        )

        await db.execute(
            delete(ChatMessage).where(
                ChatMessage.session_id.in_(session_ids)
            )
        )
        await db.execute(
            delete(ChatSession).where(
                ChatSession.user_id.in_(
                    [data["owner_id"], data["other_id"]]
                )
            )
        )
        await db.execute(
            delete(Repository).where(
                Repository.id.in_([
                    data["repository_id"],
                    data["other_repository_id"],
                ])
            )
        )
        await db.execute(
            delete(User).where(
                User.id.in_([data["owner_id"], data["other_id"]])
            )
        )
        await db.commit()


from sqlalchemy import select


@pytest.fixture
def chat_test_environment():
    data = asyncio.run(create_test_data())

    app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=data["owner_id"])
    )

    with TestClient(app) as client:
        yield client, data

    app.dependency_overrides.clear()
    asyncio.run(cleanup_test_data(data))


def test_create_and_list_chat_session(chat_test_environment):
    client, data = chat_test_environment
    url = f"/api/repositories/{data['repository_id']}/chat/sessions"

    response = client.post(url, json={"title": "Authentication discussion"})

    assert response.status_code == 201
    session = response.json()
    assert session["title"] == "Authentication discussion"
    assert session["repository_id"] == str(data["repository_id"])

    listing = client.get(url)
    assert listing.status_code == 200
    assert any(item["id"] == session["id"] for item in listing.json())


def test_chat_message_history_and_delete(chat_test_environment):
    client, data = chat_test_environment
    base_url = f"/api/repositories/{data['repository_id']}/chat/sessions"

    created = client.post(base_url, json={"title": "History test"})
    assert created.status_code == 201
    session_id = created.json()["id"]

    async def insert_message():
        async with AsyncSessionLocal() as db:
            db.add(ChatMessage(
                session_id=uuid.UUID(session_id),
                role="user",
                content="How does authentication work?",
                citations=[],
            ))
            await db.commit()

    asyncio.run(insert_message())

    messages_url = f"{base_url}/{session_id}/messages"
    history = client.get(messages_url)

    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["content"] == "How does authentication work?"

    deleted = client.delete(f"{base_url}/{session_id}")
    assert deleted.status_code == 204

    missing = client.get(messages_url)
    assert missing.status_code == 404


def test_other_user_cannot_access_chat_session(chat_test_environment):
    client, data = chat_test_environment
    owner_url = (
        f"/api/repositories/{data['repository_id']}/chat/sessions"
    )

    created = client.post(owner_url, json={"title": "Private conversation"})
    assert created.status_code == 201
    session_id = created.json()["id"]

    app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=data["other_id"])
    )

    other_url = (
        f"/api/repositories/{data['other_repository_id']}"
        f"/chat/sessions/{session_id}/messages"
    )
    response = client.get(other_url)

    assert response.status_code == 404

    app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=data["owner_id"])
    )


def test_other_user_cannot_list_owner_repository(chat_test_environment):
    client, data = chat_test_environment

    app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=data["other_id"])
    )

    response = client.get(
        f"/api/repositories/{data['repository_id']}/chat/sessions"
    )

    assert response.status_code == 404

    app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=data["owner_id"])
    )


def test_streaming_chat_persists_user_and_assistant_messages(
    chat_test_environment,
    monkeypatch,
):
    client, data = chat_test_environment

    async def fake_search_repository(*args, **kwargs):
        return []

    monkeypatch.setattr(
        "app.api.routes.chat.search_repository",
        fake_search_repository,
    )

    response = client.post(
        f"/api/repositories/{data['repository_id']}/chat/stream",
        json={"query": "Explain authentication"},
    )

    assert response.status_code == 200
    assert "I couldn't find relevant information" in response.text
    assert '"status": "completed"' in response.text

    sessions = client.get(
        f"/api/repositories/{data['repository_id']}/chat/sessions"
    )
    assert sessions.status_code == 200
    assert len(sessions.json()) == 1

    session_id = sessions.json()[0]["id"]

    history = client.get(
        f"/api/repositories/{data['repository_id']}"
        f"/chat/sessions/{session_id}/messages"
    )

    assert history.status_code == 200

    messages = history.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Explain authentication"
    assert messages[1]["role"] == "assistant"
    assert "couldn't find relevant information" in messages[1]["content"]
