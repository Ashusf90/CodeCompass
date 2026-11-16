import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    SESSION_COOKIE_NAME,
    STATE_COOKIE_NAME,
    create_session_token,
    get_current_user,
)
from app.db.database import get_db
from app.db.models import User

router = APIRouter(prefix="/api/auth", tags=["authentication"])

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"


def cookie_options():
    return {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": "lax",
        "path": "/",
    }


@router.get("/github/login")
async def github_login():
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(503, "GitHub OAuth is not configured")

    state = secrets.token_urlsafe(32)

    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": (
            (
                settings.github_redirect_uri.strip()
                or f"{settings.backend_url.rstrip('/')}/api/auth/github/callback"
            )
        ),
        "scope": "read:user user:email",
        "state": state,
    }

    response = RedirectResponse(
        f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"
    )
    response.set_cookie(
        STATE_COOKIE_NAME,
        state,
        max_age=600,
        **cookie_options(),
    )
    return response


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    expected_state = request.cookies.get(STATE_COOKIE_NAME)

    if not expected_state or not secrets.compare_digest(
        expected_state, state
    ):
        raise HTTPException(400, "Invalid OAuth state")

    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(503, "GitHub OAuth is not configured")

    callback_url = (
        (
            settings.github_redirect_uri.strip()
            or f"{settings.backend_url.rstrip('/')}/api/auth/github/callback"
        )
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_response = await client.post(
                GITHUB_TOKEN_URL,
                headers={"Accept": "application/json"},
                json={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": callback_url,
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")

            if not access_token:
                raise HTTPException(
                    401, "GitHub did not issue an access token"
                )

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            profile_response = await client.get(
                f"{GITHUB_API}/user",
                headers=headers,
            )
            profile_response.raise_for_status()
            profile = profile_response.json()

            email = profile.get("email")

            if not email:
                emails_response = await client.get(
                    f"{GITHUB_API}/user/emails",
                    headers=headers,
                )
                emails_response.raise_for_status()
                emails = emails_response.json()

                email = next(
                    (
                        item["email"]
                        for item in emails
                        if item.get("primary") and item.get("verified")
                    ),
                    None,
                )

                if not email:
                    email = next(
                        (
                            item["email"]
                            for item in emails
                            if item.get("verified")
                        ),
                        None,
                    )

    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise HTTPException(
            502,
            "Could not complete GitHub authentication",
        ) from exc

    github_id = str(profile.get("id", ""))
    username = profile.get("login")

    if not github_id or not username:
        raise HTTPException(502, "Incomplete GitHub user profile")

    result = await db.execute(
        select(User).where(User.github_id == github_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            github_id=github_id,
            username=username,
            email=email,
        )
        db.add(user)
    else:
        user.username = username
        user.email = email

    await db.commit()
    await db.refresh(user)

    response = RedirectResponse(
        f"{settings.frontend_url.rstrip('/')}/dashboard"
    )
    response.delete_cookie(STATE_COOKIE_NAME, path="/")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_token(user.id),
        max_age=settings.auth_token_expire_minutes * 60,
        **cookie_options(),
    )
    return response


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return {
        "id": str(current_user.id),
        "github_id": current_user.github_id,
        "username": current_user.username,
        "email": current_user.email,
    }


@router.post("/logout")
async def logout():
    response = Response(
        content='{"message":"Logged out"}',
        media_type="application/json",
    )
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(STATE_COOKIE_NAME, path="/")
    return response
