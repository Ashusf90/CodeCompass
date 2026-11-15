import pytest
from pydantic import ValidationError

from app.schemas.repository import RepositoryCreateRequest


def test_valid_github_url():
    request = RepositoryCreateRequest(
        github_url="https://github.com/psf/requests"
    )
    assert request.github_url == "https://github.com/psf/requests"


def test_github_url_with_git_suffix():
    request = RepositoryCreateRequest(
        github_url="https://github.com/psf/requests.git"
    )
    assert request.github_url == "https://github.com/psf/requests"


def test_reject_non_github_url():
    with pytest.raises(ValidationError):
        RepositoryCreateRequest(github_url="https://example.com/user/repo")


def test_reject_extra_path_segments():
    with pytest.raises(ValidationError):
        RepositoryCreateRequest(
            github_url="https://github.com/user/repo/tree/main"
        )


def test_reject_http_url():
    with pytest.raises(ValidationError):
        RepositoryCreateRequest(github_url="http://github.com/user/repo")
