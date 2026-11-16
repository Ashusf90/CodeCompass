from app.services.retrieval import reciprocal_rank_fusion


def test_rrf_rewards_results_found_by_both_retrievers():
    scores = reciprocal_rank_fusion([
        ["shared", "vector-only"],
        ["shared", "lexical-only"],
    ])

    assert scores["shared"] > scores["vector-only"]
    assert scores["shared"] > scores["lexical-only"]


def test_rrf_rewards_higher_ranked_results():
    scores = reciprocal_rank_fusion([
        ["first", "second", "third"],
    ])

    assert scores["first"] > scores["second"] > scores["third"]


def test_rrf_handles_empty_lists():
    assert reciprocal_rank_fusion([[], []]) == {}


def test_rrf_does_not_double_count_duplicate_ids_in_one_list():
    scores = reciprocal_rank_fusion([
        ["same", "same", "other"],
    ])

    assert scores["same"] == 1 / 61
    assert scores["other"] == 1 / 63



def test_reranker_sorts_by_cross_encoder_score(monkeypatch):
    from app.services import retrieval

    class FakeReranker:
        def __init__(self):
            self.pairs = None

        def predict(self, pairs):
            self.pairs = pairs
            return [0.1, 0.9]

    fake = FakeReranker()
    monkeypatch.setattr(retrieval, "_reranker", fake)

    hits = [
        {"file_path": "first.py", "content": "irrelevant", "similarity": 0.8},
        {"file_path": "second.py", "content": "relevant", "similarity": 0.5},
    ]

    results = retrieval._rerank_hits("test query", hits)

    assert results[0]["file_path"] == "second.py"
    assert results[1]["file_path"] == "first.py"
    assert results[0]["rerank_score"] == 0.9
    assert results[1]["rerank_score"] == 0.1
    assert fake.pairs[1][1] == "second.py\nrelevant"
    assert results[0]["similarity"] == 0.5


def test_reranker_falls_back_when_optional_dependency_missing(monkeypatch):
    import sys
    from app.services import retrieval

    monkeypatch.setattr(retrieval, "_reranker", None)
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)

    hits = [
        {"file_path": "main.py", "content": "example", "similarity": 0.8}
    ]

    results = retrieval._rerank_hits("test query", hits)

    assert results == hits
