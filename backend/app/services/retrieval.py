import asyncio
from uuid import UUID

from sqlalchemy import func, or_, select

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import CodeChunk, Repository, RepositoryFile
from app.services.indexing import generate_embeddings
from app.services.query_rewriting import rewrite_search_query


RRF_K = 60
CANDIDATE_LIMIT = 40

_reranker = None


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    k: int = RRF_K,
) -> dict[str, float]:
    """Combine ranked result lists using Reciprocal Rank Fusion."""
    scores: dict[str, float] = {}

    for ranked_list in ranked_lists:
        seen = set()
        for rank, item_id in enumerate(ranked_list, start=1):
            if item_id in seen:
                continue
            seen.add(item_id)
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)

    return scores


def _rerank_hits(query: str, hits: list[dict]) -> list[dict]:
    global _reranker

    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            _reranker = CrossEncoder(settings.reranker_model)
        except ImportError:
            return hits

    pairs = [
        (query, f"{hit['file_path']}\n{hit['content']}")
        for hit in hits
    ]
    scores = _reranker.predict(pairs)

    reranked = []
    for hit, score in zip(hits, scores):
        updated = dict(hit)
        updated["rerank_score"] = float(score)
        reranked.append(updated)

    return sorted(
        reranked,
        key=lambda item: item["rerank_score"],
        reverse=True,
    )


async def search_repository(
    repository_id: UUID,
    query: str,
    limit: int = 5,
    language: str | None = None,
    file_type: str | None = None,
    rerank: bool = False,
    retrieval_mode: str = "hybrid",
    exclude_tests: bool = False,
):
    if retrieval_mode not in {"vector", "hybrid"}:
        raise ValueError("retrieval_mode must be 'vector' or 'hybrid'")

    search_query = await rewrite_search_query(query)
    query_vectors = await asyncio.to_thread(
        generate_embeddings,
        [search_query],
    )
    query_vector = query_vectors[0]
    candidate_limit = min(max(limit * 8, CANDIDATE_LIMIT), 100)

    async with AsyncSessionLocal() as session:
        repository = await session.get(Repository, repository_id)

        if repository is None:
            raise LookupError("Repository not found")

        if repository.status != "ready":
            raise RuntimeError("Repository is not ready for searching")

        filters = [
            RepositoryFile.repository_id == repository_id,
            CodeChunk.embedding.is_not(None),
        ]

        if language:
            filters.append(RepositoryFile.language == language.lower())

        if file_type:
            filters.append(RepositoryFile.file_type == file_type.lower())

        if exclude_tests:
            test_file_conditions = [
                RepositoryFile.path.ilike("tests/%"),
                RepositoryFile.path.ilike("%/tests/%"),
                RepositoryFile.path.ilike("testing/%"),
                RepositoryFile.path.ilike("%/testing/%"),
                RepositoryFile.path.ilike("test\\_%", escape="\\"),
                RepositoryFile.path.ilike("%/test\\_%", escape="\\"),
                RepositoryFile.path.ilike("%\\_test.py", escape="\\"),
                RepositoryFile.path.ilike("conftest.py"),
                RepositoryFile.path.ilike("%/conftest.py"),
            ]
            filters.append(~or_(*test_file_conditions))

        # Semantic retrieval using pgvector cosine distance.
        distance = CodeChunk.embedding.cosine_distance(query_vector).label("distance")

        vector_statement = (
            select(CodeChunk, RepositoryFile, distance)
            .join(RepositoryFile, CodeChunk.file_id == RepositoryFile.id)
            .where(*filters)
            .order_by(distance)
            .limit(candidate_limit)
        )

        vector_result = await session.execute(vector_statement)
        vector_rows = vector_result.all()

        lexical_rows = []
        if retrieval_mode == "hybrid":
            # Lexical retrieval using PostgreSQL full-text search.
            search_document = func.to_tsvector(
                "simple",
                func.concat(RepositoryFile.path, " ", CodeChunk.content),
            )
            # Convert natural-language questions into an OR-based lexical query.
            # This avoids requiring every question word to exist in one code chunk.
            import re

            stop_words = {
                "how", "does", "do", "the", "a", "an", "is", "are",
                "what", "where", "when", "why", "which", "who",
                "and", "or", "to", "of", "in", "on", "for", "with",
                "this", "that", "these", "those", "it", "its",
                "be", "been", "being", "from", "by", "as",
            }

            terms = [
                term.lower()
                for term in re.findall(r"[A-Za-z0-9_]+", search_query)
                if len(term) > 1 and term.lower() not in stop_words
            ]

            lexical_query = " OR ".join(dict.fromkeys(terms))
            ts_query = func.websearch_to_tsquery("simple", lexical_query)
            lexical_rank = func.ts_rank_cd(search_document, ts_query).label("rank")

            lexical_statement = (
                select(CodeChunk, RepositoryFile, lexical_rank)
                .join(RepositoryFile, CodeChunk.file_id == RepositoryFile.id)
                .where(
                    *filters,
                    search_document.op("@@")(ts_query),
                )
                .order_by(lexical_rank.desc())
                .limit(candidate_limit)
            )

            lexical_result = await session.execute(lexical_statement)
            lexical_rows = lexical_result.all()

        hits_by_id: dict[str, dict] = {}
        vector_ids: list[str] = []
        lexical_ids: list[str] = []

        def make_hit(chunk, file, similarity: float = 0.0, lexical_score: float = 0.0):
            branch = repository.branch or "main"
            github_url = (
                f"{repository.github_url}/blob/{branch}/{file.path}"
                f"#L{chunk.start_line}-L{chunk.end_line}"
            )
            return {
                "file_path": file.path,
                "symbol_name": chunk.symbol_name,
                "content": chunk.content,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "similarity": round(similarity, 4),
                "lexical_score": round(lexical_score, 6),
                "retrieval_score": 0.0,
                "github_url": github_url,
            }

        for chunk, file, distance_value in vector_rows:
            chunk_id = str(chunk.id)
            similarity = max(0.0, min(1.0, 1.0 - float(distance_value)))
            vector_ids.append(chunk_id)
            hits_by_id[chunk_id] = make_hit(chunk, file, similarity)

        for chunk, file, rank in lexical_rows:
            chunk_id = str(chunk.id)
            lexical_ids.append(chunk_id)
            lexical_score = float(rank or 0.0)

            if chunk_id not in hits_by_id:
                hits_by_id[chunk_id] = make_hit(
                    chunk, file, lexical_score=lexical_score
                )
            else:
                hits_by_id[chunk_id]["lexical_score"] = round(
                    lexical_score, 6
                )

        ranked_lists = (
            [vector_ids, lexical_ids]
            if retrieval_mode == "hybrid"
            else [vector_ids]
        )
        fused_scores = reciprocal_rank_fusion(ranked_lists)

        ordered_ids = sorted(
            fused_scores,
            key=lambda item_id: fused_scores[item_id],
            reverse=True,
        )

        hits = []
        for chunk_id in ordered_ids:
            hit = hits_by_id[chunk_id]
            hit["retrieval_score"] = round(fused_scores[chunk_id], 6)
            hits.append(hit)

        if rerank and settings.enable_reranker and hits:
            hits = await asyncio.to_thread(
                _rerank_hits,
                search_query,
                hits[:candidate_limit],
            )

        return hits[:limit]
