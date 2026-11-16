from app.services.abstention import has_relevant_hit


def test_empty_results_should_abstain():
    assert not has_relevant_hit([])


def test_weak_semantic_and_lexical_results_should_abstain():
    hits = [{"similarity": 0.19, "lexical_score": 0.0, "retrieval_score": 0.03}]
    assert not has_relevant_hit(hits)


def test_relevant_semantic_result_should_not_abstain():
    hits = [{"similarity": 0.70, "lexical_score": 0.0, "retrieval_score": 0.02}]
    assert has_relevant_hit(hits)


def test_relevant_lexical_result_should_not_abstain():
    hits = [{"similarity": 0.0, "lexical_score": 0.8, "retrieval_score": 0.02}]
    assert has_relevant_hit(hits)


def test_relevant_result_after_weak_top_result_should_not_abstain():
    hits = [
        {"similarity": 0.3069, "lexical_score": 0.0},
        {"similarity": 0.65, "lexical_score": 0.0},
    ]
    assert has_relevant_hit(hits)


def test_weak_lexical_match_should_abstain():
    hits = [{"similarity": 0.19, "lexical_score": 0.24}]
    assert not has_relevant_hit(hits)


def test_observed_relevant_webcam_result_should_pass():
    hits = [{"similarity": 0.5823, "lexical_score": 0.1}]
    assert has_relevant_hit(hits)


def test_observed_unsupported_payment_results_should_abstain():
    hits = [
        {"similarity": 0.5282, "lexical_score": 0.3},
        {"similarity": 0.5438, "lexical_score": 0.1},
        {"similarity": 0.4628, "lexical_score": 0.5},
    ]
    assert not has_relevant_hit(hits)


def test_observed_unsupported_oauth_results_should_abstain():
    hits = [
        {"similarity": 0.4733, "lexical_score": 0.1},
        {"similarity": 0.4332, "lexical_score": 0.1},
        {"similarity": 0.5183, "lexical_score": 0.0},
    ]
    assert not has_relevant_hit(hits)
