import uuid

from fastapi.testclient import TestClient

from app.db.models import Base, ChatMessage, ChatSession
from app.main import app

client = TestClient(app)


def test_chat_tables_registered():
    assert "chat_sessions" in Base.metadata.tables
    assert "chat_messages" in Base.metadata.tables


def test_chat_session_has_user_and_repository_ownership():
    columns = ChatSession.__table__.columns
    assert "user_id" in columns
    assert "repository_id" in columns


def test_chat_message_has_citations():
    columns = ChatMessage.__table__.columns
    assert "session_id" in columns
    assert "role" in columns
    assert "content" in columns
    assert "citations" in columns


def test_create_chat_session_requires_login():
    response = client.post(
        f"/api/repositories/{uuid.uuid4()}/chat/sessions",
        json={"title": "Test conversation"},
    )
    assert response.status_code == 401


def test_list_chat_sessions_requires_login():
    response = client.get(
        f"/api/repositories/{uuid.uuid4()}/chat/sessions"
    )
    assert response.status_code == 401


def test_get_chat_messages_requires_login():
    response = client.get(
        f"/api/repositories/{uuid.uuid4()}/chat/sessions/{uuid.uuid4()}/messages"
    )
    assert response.status_code == 401


def test_delete_chat_session_requires_login():
    response = client.delete(
        f"/api/repositories/{uuid.uuid4()}/chat/sessions/{uuid.uuid4()}"
    )
    assert response.status_code == 401
