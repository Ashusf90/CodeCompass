import re

import httpx

from app.core.config import settings


ARCHITECTURE_TERMS = (
    "components modules architecture system design "
    "workflow data flow application pipeline "
    "technology stack dependencies frontend backend"
)


def _is_architecture_question(query: str) -> bool:
    return bool(
        re.search(
            r"\b(architecture|architectural|system design|"
            r"overall design|high.level design|data flow)\b",
            query,
            re.IGNORECASE,
        )
    )


def _build_search_query(original: str, rewritten: str) -> str:
    if not _is_architecture_question(original):
        return rewritten

    return f"{original} {rewritten} {ARCHITECTURE_TERMS}"


async def rewrite_search_query(query: str) -> str:
    """
    Rewrite repository questions into search-friendly queries.
    Preserve and expand broad architecture questions.
    Fall back safely when Groq is unavailable.
    """
    if not settings.groq_api_key:
        return _build_search_query(query, query)

    request_body = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Rewrite the user's question as a concise code-search query. "
                    "Preserve important technical terms, identifiers, and filenames. "
                    "For architecture questions, include relevant components, "
                    "modules, technologies, workflow, and data flow. "
                    "Return only the rewritten query, with no explanation."
                ),
            },
            {"role": "user", "content": query},
        ],
        "temperature": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )
            response.raise_for_status()
            rewritten = response.json()["choices"][0]["message"]["content"].strip()

            if rewritten and len(rewritten) <= 2000:
                return _build_search_query(query, rewritten)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        pass

    return _build_search_query(query, query)
