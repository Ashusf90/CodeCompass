import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db
from app.db.models import User

SESSION_COOKIE_NAME = "codecompass_session"
STATE_COOKIE_NAME = "codecompass_oauth_state"


def create_session_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(
            minutes=settings.auth_token_expire_minutes
        ),
        "type": "access",
    }
    return jwt.encode(
        payload, settings.session_secret, algorithm="HS256"
    )


def decode_session_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(
            token,
            settings.session_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "iat", "exp"]},
        )
        if payload.get("type") != "access":
            raise ValueError("Invalid token type")
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
        )


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME)

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    user_id = decode_session_token(token)

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User session no longer exists",
        )

    return user
