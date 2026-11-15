from app.services.evaluation_metrics import calculate_metrics


def test_calculate_hit_at_one_and_five():
    results = [
        {
            "expected_file": "src/main.py",
            "retrieved": [
                {"file_path": "src/main.py"},
                {"file_path": "src/utils.py"},
            ],
            "answer_correct": True,
        },
        {
            "expected_file": "src/auth.py",
            "retrieved": [
                {"file_path": "README.md"},
                {"file_path": "src/auth.py"},
            ],
            "answer_correct": False,
        },
    ]

    metrics = calculate_metrics(results)

    assert metrics["hit_at_1"] == 0.5
    assert metrics["hit_at_5"] == 1.0
    assert metrics["answer_accuracy"] == 0.5
    assert metrics["verified_answers"] == 2


def test_unverified_answers_are_not_counted():
    results = [
        {
            "expected_file": "README",
            "retrieved": [{"file_path": "README"}],
            "answer_correct": None,
        }
    ]

    metrics = calculate_metrics(results)

    assert metrics["hit_at_1"] == 1.0
    assert metrics["answer_accuracy"] is None
    assert metrics["verified_answers"] == 0


def test_empty_results():
    metrics = calculate_metrics([])

    assert metrics["questions"] == 0
    assert metrics["answer_accuracy"] is None
