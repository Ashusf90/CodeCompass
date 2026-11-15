from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import get_owned_repository
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import IngestionJob, Repository, RepositoryFile, User
from app.schemas.repository import (
    RepositoryCreateRequest,
    RepositoryCreateResponse,
    RepositoryStatusResponse,
)
from app.services.ingestion import process_repository

router = APIRouter(prefix="/api/repositories", tags=["Repositories"])


@router.post(
    "",
    response_model=RepositoryCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_repository(
    payload: RepositoryCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = await db.execute(
        select(Repository).where(
            Repository.github_url == payload.github_url,
            Repository.user_id == current_user.id,
        )
    )

    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="You have already registered this repository",
        )

    repository_name = payload.github_url.rstrip("/").split("/")[-1]

    repository = Repository(
        user_id=current_user.id,
        github_url=payload.github_url,
        name=repository_name,
        status="queued",
    )

    db.add(repository)
    await db.flush()

    job = IngestionJob(
        repository_id=repository.id,
        status="queued",
    )

    db.add(job)
    await db.commit()
    await db.refresh(repository)
    await db.refresh(job)

    background_tasks.add_task(
        process_repository,
        repository.id,
        job.id,
    )

    return RepositoryCreateResponse(
        id=repository.id,
        name=repository.name,
        github_url=repository.github_url,
        status=repository.status,
        job_id=job.id,
    )


@router.get("", response_model=list[RepositoryStatusResponse])
async def list_repositories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Repository)
        .where(Repository.user_id == current_user.id)
        .order_by(Repository.created_at.desc())
    )

    repositories = result.scalars().all()
    responses = []

    for repository in repositories:
        job_result = await db.execute(
            select(IngestionJob)
            .where(IngestionJob.repository_id == repository.id)
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )
        job = job_result.scalar_one_or_none()

        responses.append(
            RepositoryStatusResponse(
                id=repository.id,
                name=repository.name,
                github_url=repository.github_url,
                status=repository.status,
                branch=repository.branch,
                commit_sha=repository.commit_sha,
                error_message=job.error_message if job else None,
            )
        )

    return responses


@router.get("/{repository_id}/files")
async def get_repository_file(
    repository_id: UUID,
    file_path: str = Query(..., min_length=1, max_length=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await get_owned_repository(repository_id, db, current_user)

    if (
        file_path.startswith("/")
        or "\\" in file_path
        or "\x00" in file_path
        or any(part in ("", ".", "..") for part in file_path.split("/"))
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid repository file path",
        )

    result = await db.execute(
        select(RepositoryFile).where(
            RepositoryFile.repository_id == repository_id,
            RepositoryFile.path == file_path,
        )
    )
    file_record = result.scalar_one_or_none()

    if file_record is None:
        raise HTTPException(status_code=404, detail="File not found")

    return {
        "repository_id": str(repository_id),
        "file_path": file_record.path,
        "language": file_record.language,
        "file_type": file_record.file_type,
        "content": file_record.content or "",
    }


@router.get("/{repository_id}", response_model=RepositoryStatusResponse)
async def get_repository(
    repository_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repository = await get_owned_repository(
        repository_id, db, current_user
    )

    job_result = await db.execute(
        select(IngestionJob)
        .where(IngestionJob.repository_id == repository_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    )

    job = job_result.scalar_one_or_none()

    return RepositoryStatusResponse(
        id=repository.id,
        name=repository.name,
        github_url=repository.github_url,
        status=repository.status,
        branch=repository.branch,
        commit_sha=repository.commit_sha,
        error_message=job.error_message if job else None,
    )
