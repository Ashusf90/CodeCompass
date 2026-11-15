from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import get_owned_repository
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import ChatMessage, ChatSession, User
from app.schemas.chat import (
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionResponse,
)

router = APIRouter(prefix="/api/repositories", tags=["Chat History"])


@router.post(
    "/{repository_id}/chat/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_session(
    repository_id: UUID,
    payload: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await get_owned_repository(repository_id, db, current_user)

    session = ChatSession(
        user_id=current_user.id,
        repository_id=repository_id,
        title=payload.title or "New conversation",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get(
    "/{repository_id}/chat/sessions",
    response_model=list[ChatSessionResponse],
)
async def list_chat_sessions(
    repository_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await get_owned_repository(repository_id, db, current_user)

    result = await db.execute(
        select(ChatSession)
        .where(
            ChatSession.repository_id == repository_id,
            ChatSession.user_id == current_user.id,
        )
        .order_by(ChatSession.updated_at.desc())
    )
    return result.scalars().all()


@router.get(
    "/{repository_id}/chat/sessions/{session_id}/messages",
    response_model=list[ChatMessageResponse],
)
async def get_chat_messages(
    repository_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await get_owned_repository(repository_id, db, current_user)

    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.repository_id == repository_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    messages = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    return messages.scalars().all()


@router.delete(
    "/{repository_id}/chat/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chat_session(
    repository_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await get_owned_repository(repository_id, db, current_user)

    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.repository_id == repository_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    await db.delete(session)
    await db.commit()
