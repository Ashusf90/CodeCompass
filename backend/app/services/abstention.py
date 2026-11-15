SEMANTIC_RELEVANCE_THRESHOLD = 0.20
LEXICAL_RELEVANCE_THRESHOLD = 0.25


def has_relevant_hit(hits: list[dict]) -> bool:
    """Return True when at least one result has meaningful retrieval evidence."""
    return any(
        hit.get("similarity", 0.0) >= SEMANTIC_RELEVANCE_THRESHOLD
        or hit.get("lexical_score", 0.0) >= LEXICAL_RELEVANCE_THRESHOLD
        for hit in hits
    )
