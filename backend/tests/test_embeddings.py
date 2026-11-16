import math

import pytest

from app.core.config import settings
from app.services import indexing


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, responses, calls):
        self.responses = iter(responses)
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers, json):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return next(self.responses)


def vector_payload(count, dimension=384):
    return {
        "success": True,
        "result": {"data": [[1.0] * dimension for _ in range(count)]},
    }


def configure_cloudflare(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "cloudflare")
    monkeypatch.setattr(settings, "cloudflare_account_id", "test-account")
    monkeypatch.setattr(settings, "cloudflare_api_token", "test-token")


def test_cloudflare_embeddings_are_normalized(monkeypatch):
    configure_cloudflare(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "httpx.Client",
        lambda timeout: FakeClient([FakeResponse(payload=vector_payload(2))], calls),
    )

    vectors = indexing.generate_embeddings(["first", "second"])

    assert len(vectors) == 2
    assert all(len(vector) == 384 for vector in vectors)
    assert math.isclose(sum(x * x for x in vectors[0]), 1.0)
    assert calls[0]["json"] == {"text": ["first", "second"]}


def test_cloudflare_batches_more_than_16_texts(monkeypatch):
    configure_cloudflare(monkeypatch)
    calls = []
    responses = [
        FakeResponse(payload=vector_payload(16)),
        FakeResponse(payload=vector_payload(1)),
    ]
    monkeypatch.setattr(
        "httpx.Client",
        lambda timeout: FakeClient(responses, calls),
    )

    vectors = indexing.generate_embeddings([f"text {i}" for i in range(17)])

    assert len(vectors) == 17
    assert [len(call["json"]["text"]) for call in calls] == [16, 1]


def test_cloudflare_requires_credentials(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "cloudflare")
    monkeypatch.setattr(settings, "cloudflare_account_id", "")
    monkeypatch.setattr(settings, "cloudflare_api_token", "")

    with pytest.raises(RuntimeError, match="CLOUDFLARE_ACCOUNT_ID"):
        indexing.generate_embeddings(["test"])


def test_cloudflare_quota_error_has_no_paid_fallback(monkeypatch):
    configure_cloudflare(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "httpx.Client",
        lambda timeout: FakeClient([FakeResponse(status_code=429)], calls),
    )

    with pytest.raises(RuntimeError, match="No paid fallback"):
        indexing.generate_embeddings(["test"])


def test_cloudflare_rejects_wrong_dimension(monkeypatch):
    configure_cloudflare(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "httpx.Client",
        lambda timeout: FakeClient(
            [FakeResponse(payload=vector_payload(1, 10))], calls
        ),
    )

    with pytest.raises(RuntimeError, match="dimension"):
        indexing.generate_embeddings(["test"])


def test_cloudflare_rejects_invalid_response(monkeypatch):
    configure_cloudflare(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "httpx.Client",
        lambda timeout: FakeClient(
            [FakeResponse(payload={"success": False})], calls
        ),
    )

    with pytest.raises(RuntimeError, match="invalid embedding response"):
        indexing.generate_embeddings(["test"])
