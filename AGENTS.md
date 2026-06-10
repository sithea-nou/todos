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
├── pyproject.toml        # Dependencies, metadata, pytest/ruff/mypy config
├── uv.lock               # Locked deps (committed)
├── Dockerfile            # Multi-stage build (builder + runtime)
├── docker-compose.yml    # Single-service compose with persistent volume
├── index.html            # Frontend SPA (Preact + htm, served at /)
├── .env                  # Local secrets (gitignored)
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI app, lifespan, MCP mount at /mcp
│   ├── config.py         # pydantic-settings (DATABASE_URL, SECRET_KEY, …)
│   ├── database.py       # async engine, async_session_factory, init_db
│   ├── dependencies.py   # get_todo_or_404 FastAPI dependency
│   ├── mcp_server.py     # FastMCP server — 7 tools wrapping todo_service
│   ├── models/
│   │   ├── todo.py       # Todo ORM + TodoCreate/Update/Read schemas
│   │   └── chat.py       # ChatSession + ChatMessage ORM & schemas
│   ├── routers/
│   │   ├── todos.py       # REST CRUD routes (/api/todos/)
│   │   ├── chat.py        # Chat streaming/non-streaming + info + models
│   │   └── chat_sessions.py  # Chat session CRUD (/api/chat/sessions)
│   └── services/
│       ├── todo_service.py  # Business logic & DB queries
│       ├── chat_service.py  # LLM agentic loop via LiteLLM (tools → MCP)
│       └── chat_history.py  # Chat session + message persistence
├── tests/
│   ├── conftest.py          # session, client, mcp_client fixtures
│   ├── test_routers/
│   │   ├── test_todos.py         # HTTP endpoint tests
│   │   ├── test_chat.py          # Non-streaming chat tests
│   │   └── test_chat_endpoints.py  # SSE, sessions, models tests
│   ├── test_services/
│   │   ├── test_todo_service.py  # Service-layer unit tests
│   │   ├── test_chat_service.py   # Chat service + MCP tool tests
│   │   └── test_chat_history.py  # Chat persistence tests
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
uv run uvicorn app.main:app --reload   # dev server
uv run --all-extras pytest             # tests
uv run ruff check app/ tests/          # lint
uv run mypy app/                       # type check
docker compose up --build              # containerised run
```

---

## Feature Reference

### REST API (`/api/todos/`)
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/todos/` | List todos (`?completed=true/false`, `?order_by=position/priority/due_date`) |
| POST | `/api/todos/` | Create a todo (`title` required, `priority`, `due_date` optional) |
| GET | `/api/todos/{id}` | Get a todo |
| PATCH | `/api/todos/{id}` | Partial update (supports `priority`, `due_date`, `is_completed`, `title`, `description`) |
| DELETE | `/api/todos/{id}` | Delete a todo |
| PATCH | `/api/todos/reorder` | Batch reorder (`{items: [{id, position}, …]}`) |

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
| `list_todos` | List all todos; optional `completed` filter and `order_by` sort |
| `get_todo` | Fetch a single todo by UUID |
| `create_todo` | Create a new todo (`title` required, `priority` and `due_date` optional) |
| `update_todo` | Partial update; supports `priority`, `due_date` (use `"clear"` to remove) |
| `delete_todo` | Delete a todo by UUID |
| `clear_completed` | Delete all completed todos |
| `reorder_todos` | Batch reorder by position |

### Frontend (index.html)
- **Preact + htm** single-page app served at `/`
- **List view** with filter pills (All/Active/Completed), drag-and-drop reorder, priority badges, due dates with overdue highlighting
- **Calendar view** (weekly grid) with prev/next week navigation, priority-sorted cards, unscheduled section, "Today" button
- **Add-todo form** with priority dropdown (None/P3/P2/P1) and date picker
- **AI chat widget** with streaming, session persistence, provider detection
- **Theme toggle** (Light/Auto/Dark) persisted in localStorage