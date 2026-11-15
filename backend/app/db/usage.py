from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    case,
    select,
)
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.models import Base


class UserDailyUsage(Base):
    __tablename__ = "user_daily_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "usage_date", name="uq_user_daily_usage"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[object] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class UserMinuteRateLimit(Base):
    __tablename__ = "user_minute_rate_limits"

    user_id: Mapped[object] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True
    )
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


async def check_rate_limit(user_id):
    from datetime import timedelta
    from app.db.database import AsyncSessionLocal

    now = datetime.now(timezone.utc)
    minute = now.replace(second=0, microsecond=0)
    limit = settings.chat_requests_per_minute

    statement = insert(UserMinuteRateLimit).values(
        user_id=user_id,
        window_start=minute,
        request_count=1,
    )

    same_window = UserMinuteRateLimit.window_start == minute
    next_count = case(
        (same_window, UserMinuteRateLimit.request_count + 1),
        else_=1,
    )

    statement = statement.on_conflict_do_update(
        index_elements=[UserMinuteRateLimit.user_id],
        set_={
            "window_start": minute,
            "request_count": next_count,
        },
        where=case(
            (same_window, UserMinuteRateLimit.request_count < limit),
            else_=True,
        ),
    ).returning(UserMinuteRateLimit.request_count)

    async with AsyncSessionLocal() as db:
        result = await db.execute(statement)
        count = result.scalar_one_or_none()

        if count is not None:
            daily_statement = insert(UserDailyUsage).values(
                user_id=user_id,
                usage_date=now.date(),
                request_count=1,
                estimated_tokens=0,
                updated_at=now,
            )
            daily_statement = daily_statement.on_conflict_do_update(
                index_elements=[
                    UserDailyUsage.user_id,
                    UserDailyUsage.usage_date,
                ],
                set_={
                    "request_count": UserDailyUsage.request_count + 1,
                    "updated_at": now,
                },
            )
            await db.execute(daily_statement)

        await db.commit()

    if count is None:
        retry_seconds = max(
            1, int((minute + timedelta(minutes=1) - now).total_seconds())
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again next minute.",
            headers={"Retry-After": str(retry_seconds)},
        )

    return count


async def reserve_daily_tokens(user_id, estimated_tokens):
    today = datetime.now(timezone.utc).date()
    amount = max(0, estimated_tokens)
    budget = settings.daily_token_budget

    statement = insert(UserDailyUsage).values(
        user_id=user_id,
        usage_date=today,
        request_count=0,
        estimated_tokens=amount,
        updated_at=datetime.now(timezone.utc),
    )

    statement = statement.on_conflict_do_update(
        index_elements=[
            UserDailyUsage.user_id,
            UserDailyUsage.usage_date,
        ],
        set_={
            "estimated_tokens": (
                UserDailyUsage.estimated_tokens + amount
            ),
            "updated_at": datetime.now(timezone.utc),
        },
        where=UserDailyUsage.estimated_tokens + amount <= budget,
    ).returning(UserDailyUsage.estimated_tokens)

    from app.db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(statement)
        total = result.scalar_one_or_none()
        await db.commit()

    if total is None:
        raise HTTPException(
            status_code=429,
            detail="Daily token budget exceeded. Try again tomorrow.",
        )

    return total


async def get_daily_usage(user_id):
    today = datetime.now(timezone.utc).date()

    from app.db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserDailyUsage).where(
                UserDailyUsage.user_id == user_id,
                UserDailyUsage.usage_date == today,
            )
        )
        usage = result.scalar_one_or_none()

        return {
            "request_count": usage.request_count if usage else 0,
            "estimated_tokens": usage.estimated_tokens if usage else 0,
        }


async def release_daily_tokens(user_id, estimated_tokens):
    from sqlalchemy import update
    from app.db.database import AsyncSessionLocal

    today = datetime.now(timezone.utc).date()
    amount = max(0, estimated_tokens)

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(UserDailyUsage)
            .where(
                UserDailyUsage.user_id == user_id,
                UserDailyUsage.usage_date == today,
            )
            .values(
                estimated_tokens=case(
                    (
                        UserDailyUsage.estimated_tokens >= amount,
                        UserDailyUsage.estimated_tokens - amount,
                    ),
                    else_=0,
                ),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
