import json
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import get_owned_repository
from app.core.config import settings
from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal, get_db
from app.db.models import User, ChatSession, ChatMessage
from app.db.usage import (
    check_rate_limit,
    reserve_daily_tokens,
    release_daily_tokens,
)
from app.schemas.chat import (
    SearchRequest,
    SearchResponse,
    SearchHit,
    ChatStreamRequest,
)
from app.services.retrieval import search_repository
from app.services.abstention import has_relevant_hit


router = APIRouter(prefix="/api/repositories", tags=["Repository Chat"])


def sse_event(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


async def persist_assistant_message(
    session_id: UUID,
    content: str,
    citations: list | None = None,
):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if session is None:
            return

        db.add(ChatMessage(
            session_id=session_id,
            role="assistant",
            content=content,
            citations=citations,
        ))
        session.updated_at = datetime.now(timezone.utc)
        await db.commit()


@router.post("/{repository_id}/search", response_model=SearchResponse)
async def search_code(
    repository_id: UUID,
    payload: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await get_owned_repository(repository_id, db, current_user)

    try:
        hits = await search_repository(
            repository_id,
            payload.query,
            payload.limit,
            language=payload.language,
            file_type=payload.file_type,
            rerank=payload.rerank,
            exclude_tests=payload.exclude_tests,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Repository not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return SearchResponse(
        repository_id=repository_id,
        query=payload.query,
        results=[SearchHit(**hit) for hit in hits],
    )


@router.post("/{repository_id}/chat/stream")
async def stream_chat(
    repository_id: UUID,
    payload: ChatStreamRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await get_owned_repository(repository_id, db, current_user)
    await check_rate_limit(current_user.id)

    if payload.session_id:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == payload.session_id,
                ChatSession.repository_id == repository_id,
                ChatSession.user_id == current_user.id,
            )
        )
        chat_session = result.scalar_one_or_none()

        if chat_session is None:
            raise HTTPException(status_code=404, detail="Chat session not found")
    else:
        chat_session = ChatSession(
            user_id=current_user.id,
            repository_id=repository_id,
            title=payload.query[:80],
        )
        db.add(chat_session)
        await db.flush()

    try:
        hits = await search_repository(
            repository_id,
            payload.query,
            payload.limit,
            language=payload.language,
            file_type=payload.file_type,
            rerank=payload.rerank,
            exclude_tests=payload.exclude_tests,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Repository not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_session.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
    )
    conversation_history = list(reversed(history_result.scalars().all()))

    reserved_tokens = 0
    if hits and has_relevant_hit(hits) and settings.groq_api_key:
        prompt_characters = (
            len(payload.query)
            + sum(len(message.content) for message in conversation_history)
            + sum(len(hit["content"]) for hit in hits)
            + 2000
        )
        reserved_tokens = (prompt_characters + 3) // 4 + 1024
        await reserve_daily_tokens(current_user.id, reserved_tokens)

    db.add(ChatMessage(
        session_id=chat_session.id,
        role="user",
        content=payload.query,
    ))
    chat_session.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(chat_session)

    session_id = chat_session.id

    citations = [
        {
            "id": index + 1,
            "file_path": hit["file_path"],
            "start_line": hit["start_line"],
            "end_line": hit["end_line"],
            "github_url": hit["github_url"],
            "similarity": hit["similarity"],
        }
        for index, hit in enumerate(hits)
    ]

    async def event_stream():
        if not has_relevant_hit(hits):
            answer = "I couldn't find relevant information in this repository."
            await persist_assistant_message(session_id, answer, [])
            yield sse_event("answer", {"content": answer})
            yield sse_event("done", {
                "status": "completed",
                "session_id": str(session_id),
            })
            return

        yield sse_event("citations", {"sources": citations})

        if not settings.groq_api_key:
            message = "AI response unavailable: GROQ_API_KEY is not configured."
            await persist_assistant_message(session_id, message, citations)
            yield sse_event("error", {"message": message})
            yield sse_event("done", {
                "status": "error",
                "session_id": str(session_id),
            })
            return

        context = "\n\n".join(
            f"[{index + 1}] File: {hit['file_path']} "
            f"(lines {hit['start_line']}-{hit['end_line']})\n"
            f"{hit['content']}"
            for index, hit in enumerate(hits)
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are CodeCompass, an assistant that answers questions "
                    "about a specific source-code repository. Use only the "
                    "provided repository context for repository facts. Never "
                    "invent files, functions, or behavior. Cite supporting "
                    "claims using source numbers such as [1] or [2]. Previous "
                    "messages provide conversational context, but do not treat "
                    "old answers as evidence when the current repository context "
                    "does not support a claim. If the context does not contain "
                    "the answer, say: I couldn't find that information in this repository."
                ),
            },
        ]

        for previous_message in conversation_history:
            if previous_message.role in ("user", "assistant"):
                messages.append({
                    "role": previous_message.role,
                    "content": previous_message.content,
                })

        messages.append({
            "role": "user",
            "content": (
                f"Question:\n{payload.query}\n\n"
                f"Repository context:\n{context}"
            ),
        })

        request_body = {
            "model": "openai/gpt-oss-120b",
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1024,
            "stream": True,
        }

        answer_parts = []

        try:
            async with httpx.AsyncClient(timeout=90) as client:
                async with client.stream(
                    "POST",
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        message = (
                            f"Groq API error ({response.status_code}): "
                            f"{body.decode('utf-8', errors='replace')[:500]}"
                        )
                        await release_daily_tokens(
                            current_user.id, reserved_tokens
                        )
                        await persist_assistant_message(
                            session_id, message, citations
                        )
                        yield sse_event("error", {"message": message})
                        yield sse_event("done", {
                            "status": "error",
                            "session_id": str(session_id),
                        })
                        return

                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue

                        data = line[6:]
                        if data == "[DONE]":
                            break

                        try:
                            parsed = json.loads(data)
                            content = (
                                parsed.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content")
                            )
                            if content:
                                answer_parts.append(content)
                                yield sse_event("token", {"content": content})
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue

            answer = "".join(answer_parts)

            if answer:
                await persist_assistant_message(
                    session_id, answer, citations
                )
            elif reserved_tokens:
                await release_daily_tokens(
                    current_user.id, reserved_tokens
                )

            yield sse_event("done", {
                "status": "completed",
                "session_id": str(session_id),
            })

        except httpx.HTTPError as exc:
            message = f"AI provider connection failed: {exc}"
            if not answer_parts and reserved_tokens:
                await release_daily_tokens(
                    current_user.id, reserved_tokens
                )
            await persist_assistant_message(session_id, message, citations)
            yield sse_event("error", {"message": message})
            yield sse_event("done", {
                "status": "error",
                "session_id": str(session_id),
            })

        except Exception as exc:
            message = f"Unexpected AI streaming error: {type(exc).__name__}"
            if not answer_parts and reserved_tokens:
                await release_daily_tokens(
                    current_user.id, reserved_tokens
                )
            await persist_assistant_message(session_id, message, citations)
            yield sse_event("error", {"message": message})
            yield sse_event("done", {
                "status": "error",
                "session_id": str(session_id),
            })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
