# Agent Development Guidelines

> **Purpose**: Enforce strict consistency, reproducibility, and workflow alignment across all development sessions. Every AI agent MUST follow these rules.

---

## Project Context
- **Project Name**: MyToDo
- **Description**: A ToDo app with a simple UI, REST API, MCP server, and an AI chatbot that can manage todos using any LLM provider
- **Primary Goal**: REST API + MCP server for AI clients, served by a single FastAPI app
- **Target Environment**: Linux/macOS/Win, Python 3.13, uv

---

## Tech Stack & Versions
| Component       | Version / Tool                  | Notes                                      |
|-----------------|---------------------------------|--------------------------------------------|
| Runtime         | Python 3.13                     | Strict typing, modern syntax               |
| Framework       | FastAPI                         | Async-first, RESTful, OpenAPI              |
| MCP             | fastmcp ≥ 2.0                   | Mounted at `/mcp` via Streamable HTTP      |
| LLM Integration | LiteLLM                         | Multi-provider chat with tool use          |
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
├── CONTRIBUTING.md      # Contributing guide
├── pyproject.toml        # Dependencies, metadata, pytest/ruff/mypy config
├── uv.lock               # Locked deps (committed)
├── Dockerfile            # Multi-stage build (builder + runtime)
├── docker-compose.yml    # Single-service compose with persistent volume
├── index.html            # Minimal HTML shell (theme script + CSS/JS links)
├── static/               # Frontend assets (no build step)
│   ├── css/
│   │   ├── variables.css  # CSS custom properties + reset + theme variants
│   │   ├── base.css       # Body, container, header, progress, toast
│   │   ├── components.css # All component styles
│   │   └── responsive.css # Mobile media queries
│   └── js/
│       ├── preact.js       # Re-exports Preact + htm from CDN
│       ├── main.js         # Entry point: renders <App />
│       ├── app.js          # App component (state, API calls)
│       ├── api.js          # API helper functions
│       ├── utils.js        # formatDate, priorityBadge, etc.
│       └── components/
│           ├── InputRow.js
│           ├── Toolbar.js
│           ├── TodoList.js
│           ├── TodoItem.js
│           ├── CalendarView.js
│           ├── TrashView.js
│           ├── ChatBubble.js
│           ├── ChatPanel.js
│           ├── ThemeToggle.js
│           └── Toast.js
├── .env                  # Local secrets (gitignored)
├── .env.example          # Committed template for .env
├── .github/
│   ├── workflows/
│   │   ├── ci.yml        # CI: lint, test, docker build, push to GHCR
│   │   └── release.yml   # Release: on tag push, versioned image + GitHub Release
│   └── dependabot.yml   # Dependency updates (uv + docker + github-actions)
├── scripts/
│   └── seed.py           # DB seeding helper (uv run python scripts/seed.py)
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI app, lifespan, static mount, MCP mount
│   ├── config.py         # pydantic-settings (DATABASE_URL, SECRET_KEY, …)
│   ├── database.py       # async engine, async_session_factory, init_db
│   ├── dependencies.py   # get_todo_or_404 FastAPI dependency
│   ├── mcp_server.py     # FastMCP server — tools wrapping todo_service
│   ├── models/
│   │   ├── todo.py       # Todo ORM + TodoCreate/Update/Read/Stats schemas
│   │   └── chat.py       # ChatSession + ChatMessage ORM & schemas
│   ├── routers/
│   │   ├── todos.py       # REST CRUD routes (/api/todos/)
│   │   ├── chat.py        # Chat streaming/non-streaming + info + models
│   │   └── chat_sessions.py  # Chat session CRUD (/api/chat/sessions)
│   ├── security/          # Optional auth, CORS, rate-limit middleware
│   │   ├── auth.py        # API-key middleware (enabled when API_KEY set)
│   │   ├── cors.py        # CORS from CORS_ORIGINS (off by default)
│   │   └── rate_limit.py  # Per-client /api/chat rate limiting
│   └── services/
│       ├── todo_service.py  # Business logic & DB queries (search/tags/stats/soft-delete)
│       ├── chat_service.py  # LLM agentic loop via LiteLLM (tools → MCP)
│       └── chat_history.py  # Chat session + message persistence
├── tests/
│   ├── conftest.py          # session, client, mcp_client fixtures
│   ├── test_routers/
│   │   ├── test_todos.py         # HTTP endpoint tests
│   │   ├── test_todos_new.py     # Search/filter/pagination/stats/trash/restore tests
│   │   ├── test_chat.py          # Non-streaming chat tests
│   │   ├── test_chat_endpoints.py  # SSE, sessions, models tests
│   │   └── test_security.py      # Auth + rate-limit middleware tests
│   ├── test_services/
│   │   ├── test_todo_service.py  # Service-layer unit tests
│   │   ├── test_todo_service_new.py  # Search/tags/pagination/stats/soft-delete tests
│   │   ├── test_chat_service.py   # Chat service + MCP tool tests
│   │   └── test_chat_history.py  # Chat persistence tests
│   └── test_mcp/
│       ├── test_mcp_server.py     # MCP tool tests (in-process fastmcp.Client)
│       └── test_mcp_server_new.py # Extended list/search/stats/restore tool tests
└── docs/
    └── README.md         # Quick-start, API reference, MCP connection guide
```

---

## Key Conventions

### Session management
- FastAPI routes use the `get_session()` dependency (request-scoped).
- MCP tools open their own sessions via `async_session_factory()` inside `_session_do()` — they do **not** depend on a FastAPI request context.
- Chat service routes tool execution through the MCP server (`_run_tool_via_mcp`) which also uses `_session_do()`.
- Tests monkeypatch `app.mcp_server.async_session_factory` to route all tool sessions (both MCP direct and chat-mediated) through the per-test session fixture.

### Tool definitions: MCP is the single source of truth
- **`app/mcp_server.py`** defines all tools using `@mcp.tool` decorators with full parameter schemas.
- **`app/services/chat_service.py`** derives its OpenAI-format tool schemas from the MCP server at runtime via `_build_openai_tools()` and `_mcp_schema_to_openai()`. It does **not** maintain a separate tool definition list.
- **`_run_tool_via_mcp()`** routes all chat tool execution through `Client(mcp).call_tool()`, eliminating the previous `_run_tool()` duplication.
- When adding a new tool or changing parameters, edit **only** `mcp_server.py`. The chat service picks up changes automatically.

### MCP tool schemas
- The MCP server uses `anyOf` for optional fields (e.g., `priority: int | None = None`). The `_flatten_anyof()` and `_mcp_schema_to_openai()` functions convert these to simple types for OpenAI compatibility (which doesn't support `anyOf`).
- Tool descriptions explicitly instruct LLMs to **only set optional fields when the user mentions them** — this prevents the model from inventing default priority/due_date values.

### Testing
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` decorator needed.
- `pythonpath = ["."]` in `pyproject.toml` — run tests from the project root.
- The `session` fixture cleans the `todos` and `chat_sessions` tables **before and after** each test to survive interrupted runs.
- Run with: `uv run --all-extras pytest`

### Commands
```sh
uv run uvicorn app.main:app --reload                        # dev server
uv run --all-extras pytest                                  # tests (no coverage)
uv run --all-extras pytest --cov=app --cov-report=term-missing  # tests with coverage (CI uses this)
uv run ruff check app/ tests/                                # lint
uv run mypy app/                                             # type check
uv run python scripts/seed.py                                # seed the database with sample todos
docker compose up --build                                    # containerised run
```

### CI
- `.github/workflows/ci.yml` runs on every push/PR to `main`:
  1. **lint** — `ruff check` + `mypy` on `app/`
  2. **test** — `pytest --cov=app --cov-report=term-missing`
  3. **docker-build** — builds the image (cached via GHA cache)
  4. **docker-push** — on push to `main` only, pushes `latest` + `:sha` tags to `ghcr.io/${{ github.repository }}`
- `.github/workflows/release.yml` runs on pushing a `v*.*.*` tag:
  1. **validate** — ruff + mypy + pytest (gates the release)
  2. **release** — builds + pushes a versioned image to GHCR (semver tags: `0.2.0`, `0.2`, `latest`) and creates a GitHub Release with auto-generated notes
  - Cut a release with: `git tag v0.2.0 && git push origin v0.2.0` (bump `version` in `pyproject.toml` first)
- Local pre-commit hooks (see `.pre-commit-config.yaml`) run ruff + mypy before each commit.

---

## Feature Reference

### REST API (`/api/todos/`)
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/todos/` | List todos (`?completed=`, `?order_by=position/priority/due_date`, `?q=`, `?priority=`, `?tag=`, `?limit=`, `?offset=`) |
| POST | `/api/todos/` | Create a todo (`title` required, `priority`, `due_date`, `tags` optional) |
| GET | `/api/todos/{id}` | Get a todo |
| PATCH | `/api/todos/{id}` | Partial update (`priority`, `due_date`, `is_completed`, `title`, `description`, `tags`) |
| DELETE | `/api/todos/{id}` | Soft-delete a todo (movable to trash; restore later) |
| PATCH | `/api/todos/reorder` | Batch reorder (`{items: [{id, position}, …]}`) |
| GET | `/api/todos/stats` | Aggregate counts (total/active/completed/overdue/by_priority) |
| GET | `/api/todos/trash` | List soft-deleted todos |
| DELETE | `/api/todos/trash` | Permanently delete every soft-deleted todo |
| POST | `/api/todos/{id}/restore` | Restore a soft-deleted todo |
| DELETE | `/api/todos/{id}/purge` | Permanently delete a single todo |

### Chat API (`/api/chat/`)
| Method | Path | Description |
|---|---|---|
| POST | `/api/chat/` | Non-streaming chat |
| POST | `/api/chat/stream` | Streaming chat (SSE) |
| GET | `/api/chat/info` | Active provider, model, capability flags |
| GET | `/api/chat/models` | Available models (OpenAI-compatible servers only) |
| GET | `/api/chat/sessions` | List chat sessions |
| POST | `/api/chat/sessions` | Create a new session |
| GET | `/api/chat/sessions/{id}` | Fetch a session |
| GET | `/api/chat/sessions/{id}/messages` | List messages |
| DELETE | `/api/chat/sessions/{id}` | Delete a session |

### MCP Server (`/mcp`)
| Tool | Description |
|---|---|
| `list_todos` | List todos; `completed`/`order_by`/`q`/`priority`/`tag`/`limit`/`offset` |
| `get_todo` | Fetch a single (active) todo by UUID |
| `create_todo` | Create a todo (`title` required; `priority`, `due_date`, `tags` optional) |
| `update_todo` | Partial update; supports `priority`, `due_date`/`tags` (use `"clear"` to remove) |
| `delete_todo` | Soft-delete a todo by UUID |
| `restore_todo` | Restore a soft-deleted todo from the trash |
| `clear_completed` | Soft-delete all completed todos |
| `reorder_todos` | Batch reorder by position |
| `get_todo_stats` | Aggregate counts (total/active/completed/overdue/by_priority) |

### Frontend (static/)
- **Preact + htm** single-page app served at `/`, no build step
- ES modules with CDN imports centralized in `static/js/preact.js`
- CSS split by concern: `variables.css` (theme tokens + reset), `base.css` (layout), `components.css` (all component styles), `responsive.css` (mobile)
- Each Preact component in its own file under `static/js/components/`
- API helpers in `static/js/api.js`, utilities in `static/js/utils.js`
- `app/main.py` serves `index.html` at `/` and mounts `static/` at `/static`
- **List view** with filter pills (All/Active/Completed), drag-and-drop reorder, priority badges, due dates with overdue/due-soon highlighting, **inline edit** (double-click a todo to edit title/description/tags), **tag chips**
- **Calendar view** (weekly grid) with prev/next week navigation, priority-sorted cards, unscheduled section, "Other dates" section for out-of-week todos, "Today" button
- **Add-todo form** with priority dropdown (None/P3/P2/P1), date picker, and comma-separated tags input
- **Search** (title + description substring), **priority filter** dropdown, and a **stats bar** (total/active/completed/overdue) sourced from `/api/todos/stats`
- **Trash view** — soft-deleted todos with restore / purge-permanently / empty-trash actions
- **Browser reminders** for overdue and due-soon todos (requests Notification permission)
- **AI chat widget** with streaming, session persistence, provider detection
- **Theme toggle** (Light/Auto/Dark) persisted in localStorage