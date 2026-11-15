from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.security import get_current_user
from app.db.models import User
from app.db.usage import get_daily_usage

router = APIRouter(prefix="/api/usage", tags=["Usage"])


@router.get("/me")
async def my_usage(
    current_user: User = Depends(get_current_user),
):
    usage = await get_daily_usage(current_user.id)

    return {
        **usage,
        "requests_per_minute_limit": settings.chat_requests_per_minute,
        "daily_token_budget": settings.daily_token_budget,
        "remaining_estimated_tokens": max(
            0, settings.daily_token_budget - usage["estimated_tokens"]
        ),
    }
