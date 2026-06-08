# 🤖 Agent Development Guidelines (`agent.md`)

> **Purpose**: Enforce strict consistency, reproducibility, and workflow alignment across all development sessions. Every AI agent MUST follow these rules.

---

## 📋 Project Context
- **Project Name**: MyToDo
- **Description**: This is ToDo app with simple design and can integrate with AI
- **Primary Goal**: [e.g., REST API, microservice, CLI tool, etc.]
- **Target Environment**: Linux/macOS/Win, Python 3.13, uv

---

## 📦 Tech Stack & Versions
| Component       | Version / Tool          | Notes                                  |
|-----------------|-------------------------|----------------------------------------|
| Runtime         | Python 3.13             | Strict typing, modern syntax           |
| Framework       | FastAPI                 | Async-first, RESTful, OpenAPI          |
| Package Manager | `uv`                    | `pyproject.toml` source of truth       |
| Validation      | Pydantic v2             | `model_config`, `Field()`, `validate_call` |
| ORM/Database    | SQLAlchemy 2.0 + SQLModel | Async session, type-safe models      |
| Config          | pydantic-settings       | `.env` driven, zero hardcoded secrets  |
| Testing         | pytest + pytest-asyncio + httpx | Async client, coverage ≥80% |
| Linting/Types   | ruff + mypy             | Pre-commit recommended                 |
| Server          | uvicorn                 | Run via `uv run`                       |

---

## 📁 Project Structure
```text
root/
├── agent.md              # ← You are here
├── pyproject.toml        # Dependencies & metadata
├── uv.lock               # Locked deps (committed)
├── .env                  # Local secrets (gitignored)
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI app, lifespan, middleware
│   ├── config.py         # pydantic-settings config
│   ├── database.py       # engine, session, deps
│   ├── models/           # SQLModel/SQLAlchemy ORM classes
│   ├── schemas/          # Pydantic request/response models
│   ├── routers/          # API route handlers
│   ├── services/         # Business logic & repositories
│   └── dependencies.py   # Reusable FastAPI dependencies
├── tests/
│   ├── conftest.py
│   ├── test_routers/
│   └── test_services/
├── scripts/              # DB migration, seeding, dev helpers
└── docs/                 # Architecture, API specs, runbooks
