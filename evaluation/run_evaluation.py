import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings
from app.services.retrieval import search_repository
from app.services.evaluation_metrics import calculate_metrics


async def evaluate(repository_id, questions, mode, exclude_tests=False):
    results = []

    for index, question in enumerate(questions, start=1):
        print(f"[{mode}] Question {index}/{len(questions)}")

        hits = await search_repository(
            repository_id=repository_id,
            query=question["question"],
            limit=5,
            language=question.get("language"),
            file_type=question.get("file_type"),
            rerank=(mode == "hybrid_rerank"),
            retrieval_mode=(
                "vector" if mode == "vector" else "hybrid"
            ),
            exclude_tests=exclude_tests,
        )

        results.append({
            "id": question["id"],
            "question": question["question"],
            "expected_file": question["expected_file"],
            "answer_correct": question.get("answer_correct"),
            "retrieved": [
                {
                    "file_path": hit["file_path"],
                    "start_line": hit["start_line"],
                    "end_line": hit["end_line"],
                    "similarity": hit["similarity"],
                    "retrieval_score": hit["retrieval_score"],
                    "github_url": hit["github_url"],
                }
                for hit in hits
            ],
        })

    return {
        "metrics": calculate_metrics(results),
        "details": results,
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--exclude-tests", action="store_true", help="Exclude test files from retrieval candidates")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    questions = json.loads(dataset_path.read_text())

    if not isinstance(questions, list) or not questions:
        raise ValueError("Dataset must contain a non-empty JSON array")

    for question in questions:
        for field in ("id", "question", "expected_file"):
            if not question.get(field):
                raise ValueError(f"Every question requires '{field}'")

    if len(questions) < 50:
        print(
            f"WARNING: Dataset contains {len(questions)} questions. "
            "Use at least 50 per repository for the planned evaluation."
        )

    from uuid import UUID
    repository_id = UUID(args.repository_id)

    modes = ["vector", "hybrid"]

    if settings.enable_reranker:
        modes.append("hybrid_rerank")
    else:
        print(
            "Reranker evaluation skipped: "
            "ENABLE_RERANKER is not enabled."
        )

    report = {
        "repository_id": str(repository_id),
        "dataset": str(dataset_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "exclude_tests": args.exclude_tests,
        "results": {},
    }

    for mode in modes:
        print(f"\n========== {mode.upper()} ==========")
        evaluation = await evaluate(
            repository_id, questions, mode,
            exclude_tests=args.exclude_tests,
        )
        report["results"][mode] = evaluation

        print(json.dumps(evaluation["metrics"], indent=2))

    output_dir = PROJECT_ROOT / "evaluation" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / (
        f"evaluation-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )

    output_path.write_text(json.dumps(report, indent=2))
    print(f"\nEvaluation report saved: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
