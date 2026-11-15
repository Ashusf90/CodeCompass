from pathlib import Path

from app.services.indexing import (
    extract_chunks,
    fallback_chunks,
    should_index_file,
)


def test_skip_node_modules():
    assert not should_index_file(
        Path("project/node_modules/example/index.js")
    )


def test_skip_lock_files():
    assert not should_index_file(Path("package-lock.json"))


def test_accept_python_file():
    assert should_index_file(Path("app/main.py"))


def test_extract_python_function():
    source = """def calculate_total(a, b):
    return a + b
"""
    chunks = extract_chunks(Path("example.py"), source)

    assert len(chunks) >= 1
    assert any("calculate_total" in chunk["content"] for chunk in chunks)
    assert chunks[0]["start_line"] == 1


def test_markdown_fallback():
    source = "# Project\n\nThis is a README file."
    chunks = extract_chunks(Path("README.md"), source)

    assert len(chunks) == 1
    assert "README file" in chunks[0]["content"]


def test_fallback_line_numbers():
    chunks = fallback_chunks("first line\nsecond line")

    assert chunks[0]["start_line"] == 1
    assert chunks[0]["end_line"] == 2
