from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.repositories import router as repositories_router
from app.api.routes.chat import router as chat_router
from app.api.routes.auth import router as auth_router
from app.api.routes.chat_history import router as chat_history_router
from app.api.routes.usage import router as usage_router
from app.db.database import close_database
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_database()


app = FastAPI(
    title="CodeCompass API",
    description="AI-powered GitHub repository Q&A",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repositories_router)
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(chat_history_router)
app.include_router(usage_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "project": "CodeCompass"}
