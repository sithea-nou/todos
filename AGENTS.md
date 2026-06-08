# Agent Development Guidelines

> **Purpose**: Enforce strict consistency, reproducibility, and workflow alignment across all development sessions. Every AI agent MUST follow these rules.

---

## Project Context
- **Project Name**: MyToDo
- **Description**: A ToDo app with a simple UI, a REST API, and an MCP server for LLM integration
- **Primary Goal**: REST API + MCP server for AI clients, served by a single FastAPI app
- **Target Environment**: Linux/macOS/Win, Python 3.13, uv

---

## Tech Stack & Versions
| Component       | Version / Tool                  | Notes                                      |
|-----------------|---------------------------------|--------------------------------------------|
| Runtime         | Python 3.13                     | Strict typing, modern syntax               |
| Framework       | FastAPI                         | Async-first, RESTful, OpenAPI              |
| MCP             | fastmcp ≥ 2.0                   | Mounted at `/mcp` via Streamable HTTP      |
| Package Manager | `uv`                            | `pyproject.toml` source of truth           |
| Validation      | Pydantic v2                     | `model_config`, `Field()`, `validate_call` |
| ORM/Database    | SQLAlchemy 2.0 + SQLModel       | Async session, type-safe models            |
| Config          | pydantic-settings               | `.env` driven, zero hardcoded secrets      |
| Testing         | pytest + pytest-asyncio + httpx | Async client, `asyncio_mode = "auto"`      |
| Linting/Types   | ruff + mypy                     | Pre-commit recommended                     |
| Server          | uvicorn                         | Run via `uv run`                           |
| Container       | Docker + docker-compose         | Multi-stage build, non-root user           |

---

## Project Structure
```text
root/
├── AGENTS.md             # ← You are here
├── pyproject.toml        # Dependencies, metadata, pytest/ruff/mypy config
├── uv.lock               # Locked deps (committed)
├── Dockerfile            # Multi-stage build (builder + runtime)
├── docker-compose.yml    # Single-service compose with persistent volume
├── index.html            # Frontend SPA (vanilla JS, served at /)
├── .env                  # Local secrets (gitignored)
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI app, lifespan, MCP mount at /mcp
│   ├── config.py         # pydantic-settings (DATABASE_URL, SECRET_KEY, …)
│   ├── database.py       # async engine, async_session_factory, init_db
│   ├── dependencies.py   # get_todo_or_404 FastAPI dependency
│   ├── mcp_server.py     # FastMCP server — 6 tools wrapping todo_service
│   ├── models/
│   │   └── todo.py       # Todo ORM + TodoCreate/Update/Read schemas
│   ├── routers/
│   │   └── todos.py      # REST CRUD routes (/api/todos/)
│   └── services/
│       └── todo_service.py  # Business logic & DB queries
├── tests/
│   ├── conftest.py          # session, client, mcp_client fixtures
│   ├── test_routers/
│   │   └── test_todos.py    # HTTP endpoint tests
│   ├── test_services/
│   │   └── test_todo_service.py  # Service-layer unit tests
│   └── test_mcp/
│       └── test_mcp_server.py    # MCP tool tests (in-process fastmcp.Client)
└── docs/
    └── README.md         # Quick-start, API reference, MCP connection guide
```

---

## Key Conventions

### Session management
- FastAPI routes use the `get_session()` dependency (request-scoped).
- MCP tools open their own sessions via `async_session_factory()` inside `_session_do()` — they do **not** depend on a FastAPI request context.
- Tests monkeypatch `app.mcp_server.async_session_factory` (not `app.database.async_session_factory`) to route MCP tool sessions through the per-test session fixture.

### Testing
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` decorator needed.
- `pythonpath = ["."]` in `pyproject.toml` — run tests from the project root.
- The `session` fixture cleans the `todos` table **before and after** each test to survive interrupted runs.
- Run with: `uv run --all-extras pytest`

### Commands
```sh
uv run uvicorn app.main:app --reload   # dev server
uv run --all-extras pytest             # tests
uv run ruff check app/ tests/          # lint
uv run mypy app/                       # type check
docker compose up --build              # containerised run
```
