import httpx

from app.core.config import settings


async def rewrite_search_query(query: str) -> str:
    """
    Expand a repository question into a search-friendly query.
    If Groq is unavailable, preserve the user's original query.
    """
    if not settings.groq_api_key:
        return query

    request_body = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Rewrite the user's question as a concise code-search query. "
                    "Keep important technical terms, identifiers, and filenames. "
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
                return rewritten
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        pass

    return query
