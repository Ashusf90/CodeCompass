import asyncio
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from app.db.database import AsyncSessionLocal
from app.db.models import IngestionJob, Repository
from app.services.indexing import index_repository


REPOSITORY_STORAGE = Path(__file__).resolve().parents[2] / "data" / "repos"


async def update_status(
    repository_id: UUID,
    job_id: UUID,
    status: str,
    error_message: str | None = None,
):
    async with AsyncSessionLocal() as session:
        repository = await session.get(Repository, repository_id)
        job = await session.get(IngestionJob, job_id)

        if repository is None or job is None:
            return

        repository.status = status
        job.status = status
        job.error_message = error_message

        if status in {"ready", "failed"}:
            job.completed_at = datetime.now(timezone.utc)

        await session.commit()


def clone_repository(github_url: str, destination: Path) -> tuple[str, str]:
    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--", github_url, str(destination)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Git clone failed")

    commit_result = subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )

    branch_result = subprocess.run(
        ["git", "-C", str(destination), "branch", "--show-current"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )

    return commit_result.stdout.strip(), branch_result.stdout.strip()


async def process_repository(repository_id: UUID, job_id: UUID):
    temporary_path = REPOSITORY_STORAGE / f".tmp-{repository_id}"
    final_path = REPOSITORY_STORAGE / str(repository_id)

    try:
        await update_status(repository_id, job_id, "indexing")

        async with AsyncSessionLocal() as session:
            repository = await session.get(Repository, repository_id)

            if repository is None:
                raise RuntimeError("Repository record not found")

            github_url = repository.github_url

        REPOSITORY_STORAGE.mkdir(parents=True, exist_ok=True)

        if temporary_path.exists():
            shutil.rmtree(temporary_path)

        if final_path.exists():
            shutil.rmtree(final_path)

        commit_sha, branch = await asyncio.to_thread(
            clone_repository,
            github_url,
            temporary_path,
        )

        temporary_path.rename(final_path)

        async with AsyncSessionLocal() as session:
            repository = await session.get(Repository, repository_id)

            if repository is None:
                raise RuntimeError("Repository record disappeared")

            repository.local_path = str(final_path)
            repository.commit_sha = commit_sha
            repository.branch = branch or "main"

            await session.commit()

        indexing_result = await index_repository(repository_id)

        print(
            f"Indexed repository {repository_id}: "
            f"{indexing_result}"
        )

        await update_status(repository_id, job_id, "ready")

    except Exception as exc:
        if temporary_path.exists():
            shutil.rmtree(temporary_path, ignore_errors=True)

        await update_status(
            repository_id,
            job_id,
            "failed",
            str(exc)[:5000],
        )
