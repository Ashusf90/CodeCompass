# CodeCompass

AI-powered GitHub repository Q&A using hybrid code retrieval.
## Retrieval Evaluation

Two datasets were evaluated: FastAPI (50 questions) and Requests (50 questions).

| Repository | Retrieval mode | Hit@1 | Hit@5 |
|---|---|---:|---:|
| FastAPI | Vector | 32% | 56% |
| FastAPI | Hybrid | 32% | 62% |
| FastAPI | Hybrid + reranker | **52%** | **86%** |
| Requests | Vector | 68% | 94% |
| Requests | Hybrid | 58% | 84% |
| Requests | Hybrid + reranker | **66%** | **88%** |
| Combined (100 questions) | Vector | 50% | 75% |
| Combined (100 questions) | Hybrid | 45% | 73% |
| Combined (100 questions) | Hybrid + reranker | **59%** | **87%** |

Test files were excluded for these results. Hit@1 and Hit@5 measure expected source-file retrieval, not generated-answer correctness. Answer accuracy has not yet been measured because answer labels remain unverified. These results are provisional.

## Local Setup

1. Start PostgreSQL using `docker compose up -d` from the project root.
2. Enter `backend/` and activate your virtual environment.
3. Install dependencies using `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` and configure local settings.
5. Initialize the database using `python -m app.db.init_db`.
6. Start the API using `uvicorn app.main:app --reload`.

API documentation: `http://127.0.0.1:8000/docs`.

## Tests

Run `pytest -q` from the backend directory with the virtual environment activated.

## Project Status

Backend ingestion, indexing, retrieval, reranking, abstention, and retrieval evaluation are implemented and tested. Authentication, persistent chat history, frontend, usage limits, production monitoring, CI/CD, and deployment remain planned.
