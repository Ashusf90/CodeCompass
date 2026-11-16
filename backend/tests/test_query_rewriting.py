import pytest
from app.services import query_rewriting


@pytest.mark.asyncio
async def test_returns_original_without_groq_key(monkeypatch):
    monkeypatch.setattr(query_rewriting.settings, "groq_api_key", "")
    query = "How does FastAPI register routes?"
    assert await query_rewriting.rewrite_search_query(query) == query


@pytest.mark.asyncio
async def test_returns_rewritten_groq_query(monkeypatch):
    monkeypatch.setattr(query_rewriting.settings, "groq_api_key", "test-key")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "FastAPI route registration"}}]}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(query_rewriting.httpx, "AsyncClient", Client)
    result = await query_rewriting.rewrite_search_query("How does FastAPI register routes?")
    assert result == "FastAPI route registration"


@pytest.mark.asyncio
async def test_falls_back_when_groq_response_is_invalid(monkeypatch):
    monkeypatch.setattr(query_rewriting.settings, "groq_api_key", "test-key")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": []}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(query_rewriting.httpx, "AsyncClient", Client)
    query = "How does Requests create a session?"
    assert await query_rewriting.rewrite_search_query(query) == query


@pytest.mark.asyncio
async def test_expands_architecture_question_without_groq(monkeypatch):
    monkeypatch.setattr(query_rewriting.settings, "groq_api_key", "")

    query = "Explain the overall architecture of this project."
    result = await query_rewriting.rewrite_search_query(query)

    assert query in result
    assert "components" in result
    assert "data flow" in result
    assert "technology stack" in result


@pytest.mark.asyncio
async def test_preserves_architecture_question_with_groq(monkeypatch):
    monkeypatch.setattr(query_rewriting.settings, "groq_api_key", "test-key")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {"message": {"content": "overall architecture of project"}}
                ]
            }

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(query_rewriting.httpx, "AsyncClient", Client)

    query = "Explain the overall architecture of this project."
    result = await query_rewriting.rewrite_search_query(query)

    assert query in result
    assert "overall architecture of project" in result
    assert "components" in result


@pytest.mark.asyncio
async def test_does_not_expand_specific_questions(monkeypatch):
    monkeypatch.setattr(query_rewriting.settings, "groq_api_key", "test-key")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {"message": {"content": "FastAPI route registration"}}
                ]
            }

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(query_rewriting.httpx, "AsyncClient", Client)

    result = await query_rewriting.rewrite_search_query(
        "How does FastAPI register routes?"
    )

    assert result == "FastAPI route registration"
    assert "technology stack" not in result
