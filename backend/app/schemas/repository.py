from uuid import UUID

from pydantic import BaseModel, field_validator
from urllib.parse import urlsplit


class RepositoryCreateRequest(BaseModel):
    github_url: str

    @field_validator("github_url")
    @classmethod
    def validate_github_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")

        parsed = urlsplit(value)

        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Only public HTTPS GitHub repository URLs are supported")

        parts = parsed.path.strip("/").split("/")

        if len(parts) != 2:
            raise ValueError("URL must have the format https://github.com/owner/repository")

        owner, repository = parts
        repository = repository.removesuffix(".git")

        if not owner or not repository or owner in {".", ".."} or repository in {".", ".."}:
            raise ValueError("Invalid GitHub repository URL")

        return f"https://github.com/{owner}/{repository}"


class RepositoryCreateResponse(BaseModel):
    id: UUID
    name: str
    github_url: str
    status: str
    job_id: UUID


class RepositoryStatusResponse(BaseModel):
    id: UUID
    name: str
    github_url: str
    status: str
    branch: str | None
    commit_sha: str | None
    error_message: str | None = None
