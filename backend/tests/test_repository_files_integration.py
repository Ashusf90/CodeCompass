import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.security import get_current_user
from app.db.database import AsyncSessionLocal
from app.db.models import User, Repository, RepositoryFile
from app.main import app


async def create_test_data():
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()

    async with AsyncSessionLocal() as db:
        owner = User(
            id=owner_id,
            github_id=f"file-owner-{owner_id}",
            username="file_owner_test",
        )
        other = User(
            id=other_id,
            github_id=f"file-other-{other_id}",
            username="file_other_test",
        )
        db.add_all([owner, other])
        await db.flush()

        repository = Repository(
            user_id=owner_id,
            github_url=f"https://github.com/test/{owner_id}",
            name="file-test-repo",
            status="ready",
        )
        db.add(repository)
        await db.flush()

        source = RepositoryFile(
            repository_id=repository.id,
            path="src/main.py",
            language="python",
            file_type="source",
            content_hash="a" * 64,
            content="def hello():\n    return 'CodeCompass'\n",
        )
        db.add(source)
        await db.commit()

        return {
            "owner_id": owner_id,
            "other_id": other_id,
            "repository_id": repository.id,
        }


async def cleanup_test_data(data):
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(RepositoryFile).where(
                RepositoryFile.repository_id == data["repository_id"]
            )
        )
        await db.execute(
            delete(Repository).where(
                Repository.id == data["repository_id"]
            )
        )
        await db.execute(
            delete(User).where(
                User.id.in_([data["owner_id"], data["other_id"]])
            )
        )
        await db.commit()


@pytest.fixture
def file_test_environment():
    data = asyncio.run(create_test_data())

    app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=data["owner_id"])
    )

    with TestClient(app) as client:
        yield client, data

    app.dependency_overrides.clear()
    asyncio.run(cleanup_test_data(data))


def test_owner_can_retrieve_indexed_file(file_test_environment):
    client, data = file_test_environment

    response = client.get(
        f"/api/repositories/{data['repository_id']}/files",
        params={"file_path": "src/main.py"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["file_path"] == "src/main.py"
    assert result["language"] == "python"
    assert result["file_type"] == "source"
    assert result["content"] == "def hello():\n    return 'CodeCompass'\n"


def test_other_user_cannot_retrieve_repository_file(file_test_environment):
    client, data = file_test_environment

    app.dependency_overrides[get_current_user] = lambda: (
        SimpleNamespace(id=data["other_id"])
    )

    response = client.get(
        f"/api/repositories/{data['repository_id']}/files",
        params={"file_path": "src/main.py"},
    )

    assert response.status_code == 404


def test_invalid_repository_file_path_is_rejected(file_test_environment):
    client, data = file_test_environment

    response = client.get(
        f"/api/repositories/{data['repository_id']}/files",
        params={"file_path": "src//main.py"},
    )

    assert response.status_code == 400


def test_missing_repository_file_returns_404(file_test_environment):
    client, data = file_test_environment

    response = client.get(
        f"/api/repositories/{data['repository_id']}/files",
        params={"file_path": "src/missing.py"},
    )

    assert response.status_code == 404
