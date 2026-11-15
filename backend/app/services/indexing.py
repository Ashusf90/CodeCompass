import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import CodeChunk, Repository, RepositoryFile


MAX_FILE_SIZE = 1_000_000
MAX_CHUNK_CHARS = 8_000
FALLBACK_LINES = 80

SKIP_DIRS = {
    ".git", ".github", ".next", ".venv", "venv",
    "node_modules", "__pycache__", ".pytest_cache",
    "dist", "build", "coverage", "vendor",
}

SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "Cargo.lock",
    "composer.lock", "Gemfile.lock",
}

LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "c_sharp",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "bash",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}

SYMBOL_TYPES = {
    "function_definition",
    "function_declaration",
    "function_item",
    "class_definition",
    "class_declaration",
    "class_specifier",
    "method_definition",
    "method_declaration",
    "impl_item",
    "struct_item",
    "interface_declaration",
    "trait_item",
}


def should_index_file(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False

    if path.name in SKIP_FILES:
        return False

    if path.name.startswith(".") and path.name not in {
        ".gitignore", ".dockerignore", ".env.example"
    }:
        return False

    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return False
    except OSError:
        return False

    return path.is_file()


def split_large_chunk(
    content: str,
    start_line: int,
    symbol_name: str | None,
    chunk_type: str,
) -> list[dict]:
    lines = content.splitlines()
    chunks = []

    for offset in range(0, len(lines), FALLBACK_LINES):
        part = lines[offset:offset + FALLBACK_LINES]
        if not any(line.strip() for line in part):
            continue

        chunks.append({
            "symbol_name": symbol_name,
            "chunk_type": chunk_type,
            "content": "\n".join(part),
            "start_line": start_line + offset,
            "end_line": start_line + offset + len(part) - 1,
        })

    return chunks


def fallback_chunks(content: str) -> list[dict]:
    return split_large_chunk(content, 1, None, "block")


def extract_chunks(path: Path, content: str) -> list[dict]:
    language = LANGUAGES.get(path.suffix.lower())

    if not language:
        return fallback_chunks(content)

    try:
        from tree_sitter_language_pack import get_parser

        parser = get_parser(language)
        source = content.encode("utf-8")
        tree = parser.parse(source)
        found = []

        container_types = {
            "class_definition", "class_declaration", "class_specifier",
            "impl_item", "struct_item", "interface_declaration", "trait_item",
        }

        function_types = {
            "function_definition", "function_declaration", "function_item",
            "method_definition", "method_declaration",
        }

        def contains_nested_symbol(node):
            for child in node.children:
                if child.type in SYMBOL_TYPES:
                    return True
                if contains_nested_symbol(child):
                    return True
            return False

        def add_chunk(node):
            text = source[node.start_byte:node.end_byte].decode(
                "utf-8", errors="replace"
            )
            name = None

            for child in node.children:
                if child.type in {
                    "identifier", "type_identifier",
                    "field_identifier", "operator_name",
                }:
                    name = source[
                        child.start_byte:child.end_byte
                    ].decode("utf-8", errors="replace")
                    break

            found.append({
                "symbol_name": name,
                "chunk_type": node.type,
                "content": text,
                "start_line": node.start_point.row + 1,
                "end_line": node.end_point.row + 1,
            })

        def visit(node):
            if node.type in function_types:
                add_chunk(node)
                return

            if node.type in container_types:
                if not contains_nested_symbol(node):
                    add_chunk(node)
                    return

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        if not found:
            return fallback_chunks(content)

        result = []
        for chunk in found:
            if len(chunk["content"]) <= MAX_CHUNK_CHARS:
                result.append(chunk)
            else:
                result.extend(
                    split_large_chunk(
                        chunk["content"],
                        chunk["start_line"],
                        chunk["symbol_name"],
                        chunk["chunk_type"],
                    )
                )

        return result

    except Exception:
        return fallback_chunks(content)


_embedding_model = None


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    global _embedding_model

    if not texts:
        return []

    from sentence_transformers import SentenceTransformer

    if _embedding_model is None:
        _embedding_model = SentenceTransformer(settings.embedding_model)

    vectors = _embedding_model.encode(
        texts,
        batch_size=16,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    return vectors.tolist()


async def index_repository(repository_id, force_paths=None):
    async with AsyncSessionLocal() as session:
        repository = await session.get(Repository, repository_id)

        if repository is None or not repository.local_path:
            raise RuntimeError("Repository clone path is missing")

        root = Path(repository.local_path)

        if not root.is_dir():
            raise RuntimeError("Cloned repository directory does not exist")

        existing_result = await session.execute(
            select(RepositoryFile).where(
                RepositoryFile.repository_id == repository_id
            )
        )
        existing_files = {
            item.path: item for item in existing_result.scalars().all()
        }

        discovered_paths = set()
        indexed_count = 0
        skipped_count = 0

        for path in root.rglob("*"):
            if not should_index_file(path):
                continue

            relative_path = path.relative_to(root).as_posix()
            discovered_paths.add(relative_path)

            try:
                raw = path.read_bytes()

                if b"\x00" in raw:
                    skipped_count += 1
                    continue

                content = raw.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                skipped_count += 1
                continue

            content_hash = hashlib.sha256(raw).hexdigest()
            old_file = existing_files.get(relative_path)

            if (
                old_file
                and old_file.content_hash == content_hash
                and relative_path not in (force_paths or set())
            ):
                continue

            chunks = extract_chunks(path, content)
            vectors = await asyncio.to_thread(
                generate_embeddings,
                [chunk["content"] for chunk in chunks],
            )

            if old_file:
                await session.execute(
                    delete(CodeChunk).where(CodeChunk.file_id == old_file.id)
                )
                file_record = old_file
            else:
                file_record = RepositoryFile(
                    repository_id=repository_id,
                    path=relative_path,
                    content_hash=content_hash,
                )
                session.add(file_record)

            file_record.language = LANGUAGES.get(path.suffix.lower())
            file_record.file_type = (
                "source" if file_record.language else "document"
            )
            file_record.content_hash = content_hash
            file_record.content = content
            file_record.indexed_at = datetime.now(timezone.utc)

            await session.flush()

            for chunk, vector in zip(chunks, vectors):
                session.add(
                    CodeChunk(
                        file_id=file_record.id,
                        symbol_name=chunk["symbol_name"],
                        chunk_type=chunk["chunk_type"],
                        content=chunk["content"],
                        start_line=chunk["start_line"],
                        end_line=chunk["end_line"],
                        embedding=vector,
                    )
                )

            indexed_count += 1

        for old_path, old_file in existing_files.items():
            if old_path not in discovered_paths:
                await session.delete(old_file)

        await session.commit()

        return {
            "indexed_files": indexed_count,
            "skipped_files": skipped_count,
            "total_files": len(discovered_paths),
        }
