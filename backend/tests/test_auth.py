import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import (
    SESSION_COOKIE_NAME,
    STATE_COOKIE_NAME,
    create_session_token,
    decode_session_token,
)
from app.main import app

client = TestClient(app)


def test_create_and_decode_session_token():
    user_id = uuid.uuid4()
    token = create_session_token(user_id)

    assert decode_session_token(token) == user_id


def test_invalid_session_token_is_rejected():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        decode_session_token("invalid.token.value")

    assert exc.value.status_code == 401


def test_expired_session_token_is_rejected():
    from fastapi import HTTPException

    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "iat": datetime.now(timezone.utc) - timedelta(days=2),
            "exp": datetime.now(timezone.utc) - timedelta(days=1),
            "type": "access",
        },
        settings.session_secret,
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc:
        decode_session_token(token)

    assert exc.value.status_code == 401


def test_wrong_token_type_is_rejected():
    from fastapi import HTTPException

    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "refresh",
        },
        settings.session_secret,
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc:
        decode_session_token(token)

    assert exc.value.status_code == 401


def test_me_requires_authentication():
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_logout_clears_session_cookie():
    response = client.post(
        "/api/auth/logout",
        cookies={SESSION_COOKIE_NAME: "fake-session"},
    )

    assert response.status_code == 200
    assert SESSION_COOKIE_NAME in response.headers.get(
        "set-cookie", ""
    )


def test_github_login_redirects_and_sets_state_cookie(monkeypatch):
    monkeypatch.setattr(settings, "github_client_id", "test-client-id")
    monkeypatch.setattr(
        settings, "github_client_secret", "test-client-secret"
    )

    response = client.get(
        "/api/auth/github/login",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert "github.com/login/oauth/authorize" in response.headers["location"]
    assert "client_id=test-client-id" in response.headers["location"]
    assert STATE_COOKIE_NAME in response.headers.get("set-cookie", "")


def test_github_callback_rejects_invalid_state():
    response = client.get(
        "/api/auth/github/callback?code=test-code&state=wrong-state",
        cookies={STATE_COOKIE_NAME: "expected-state"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid OAuth state"
