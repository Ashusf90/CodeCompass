import asyncio

from sqlalchemy import text

from app.db.database import engine
from app.db.models import Base
from app.db.usage import UserDailyUsage, UserMinuteRateLimit


async def init_db():
    async with engine.begin() as connection:
        await connection.execute(
            text("CREATE EXTENSION IF NOT EXISTS vector")
        )
        await connection.run_sync(Base.metadata.create_all)

    print("Database initialized successfully!")


if __name__ == "__main__":
    asyncio.run(init_db())
