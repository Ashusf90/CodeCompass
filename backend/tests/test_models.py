from sqlalchemy import UniqueConstraint

from app.db.models import (
    Base,
    CodeChunk,
    IngestionJob,
    Repository,
    RepositoryFile,
    User,
)


def test_all_tables_registered():
    expected = {
        "users",
        "repositories",
        "repository_files",
        "code_chunks",
        "ingestion_jobs",
    }
    assert expected.issubset(set(Base.metadata.tables.keys()))


def test_code_chunk_has_vector_embedding():
    column = CodeChunk.__table__.columns["embedding"]
    assert column.type.dim == 384


def test_code_chunk_has_line_numbers():
    columns = CodeChunk.__table__.columns
    assert "start_line" in columns
    assert "end_line" in columns


def test_repository_has_status():
    assert "status" in Repository.__table__.columns


def test_repository_file_has_content_hash():
    assert "content_hash" in RepositoryFile.__table__.columns


def test_ingestion_job_tracks_errors():
    assert "error_message" in IngestionJob.__table__.columns


def test_user_has_github_id():
    assert "github_id" in User.__table__.columns
