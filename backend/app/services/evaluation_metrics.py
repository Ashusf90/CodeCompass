def normalize_path(path):
    return str(path).replace("\\", "/").lstrip("./").lower()


def calculate_metrics(results):
    total = len(results)

    if not total:
        return {
            "questions": 0,
            "hit_at_1": 0.0,
            "hit_at_5": 0.0,
            "answer_accuracy": None,
            "verified_answers": 0,
        }

    hit_at_1 = 0
    hit_at_5 = 0
    verified = []

    for result in results:
        expected = normalize_path(result["expected_file"])
        returned = [
            normalize_path(hit["file_path"])
            for hit in result["retrieved"]
        ]

        if returned and returned[0] == expected:
            hit_at_1 += 1

        if expected in returned[:5]:
            hit_at_5 += 1

        if isinstance(result.get("answer_correct"), bool):
            verified.append(result["answer_correct"])

    return {
        "questions": total,
        "hit_at_1": round(hit_at_1 / total, 4),
        "hit_at_5": round(hit_at_5 / total, 4),
        "answer_accuracy": (
            round(sum(verified) / len(verified), 4)
            if verified else None
        ),
        "verified_answers": len(verified),
    }
