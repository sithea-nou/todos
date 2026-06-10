# Contributing to MyToDo

Thanks for your interest in contributing! This guide covers everything you need to get started.

## Prerequisites

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** — Python package manager (replaces pip/poetry)
- **Git**
- **Docker** (optional, for containerized testing)

## Setup

```sh
# Clone the repository
git clone https://github.com/your-org/todos.git
cd todos

# Install dependencies (includes dev tools)
uv sync --all-extras

# Copy environment template and configure
cp .env.example .env
# Edit .env with your API keys (see docs/README.md for provider options)

# Run the dev server
uv run uvicorn app.main:app --reload
```

The app is available at `http://localhost:8000`. Interactive API docs at `/docs` (Swagger) and `/redoc`.

## Project Structure

```
root/
├── AGENTS.md               # Architecture & conventions for AI agents
├── CONTRIBUTING.md         # This file
├── pyproject.toml           # Dependencies, metadata, tool config
├── uv.lock                  # Locked deps (committed)
├── Dockerfile               # Multi-stage build (builder + runtime)
├── docker-compose.yml       # Single-service compose with persistent volume
├── index.html               # Minimal HTML shell (theme script + links)
├── static/                  # Frontend assets (no build step)
│   ├── css/
│   │   ├── variables.css    # CSS custom properties + reset + theme variants
│   │   ├── base.css         # Body, container, header, progress, toast
│   │   ├── components.css   # All component styles
│   │   └── responsive.css   # Mobile media queries
│   └── js/
│       ├── preact.js         # Re-exports Preact + htm from CDN
│       ├── main.js           # Entry point: renders <App />
│       ├── app.js            # App component (state, API calls)
│       ├── api.js            # API helper functions
│       ├── utils.js          # formatDate, priorityBadge, etc.
│       └── components/
│           ├── InputRow.js
│           ├── Toolbar.js
│           ├── TodoList.js
│           ├── TodoItem.js
│           ├── CalendarView.js
│           ├── ChatBubble.js
│           ├── ChatPanel.js
│           ├── ThemeToggle.js
│           └── Toast.js
├── app/                     # Python backend
│   ├── main.py              # FastAPI app + static file mount
│   ├── config.py            # pydantic-settings
│   ├── database.py          # Async engine + session factory
│   ├── dependencies.py      # FastAPI dependencies
│   ├── mcp_server.py        # FastMCP server (7 tools)
│   ├── models/              # SQLModel ORM + Pydantic schemas
│   ├── routers/             # REST API route handlers
│   └── services/            # Business logic layer
├── tests/                   # pytest + pytest-asyncio + httpx
├── scripts/                 # Utility scripts (seed.py)
└── docs/
    └── README.md            # User-facing documentation
```

## Development Commands

```sh
# Start dev server (with hot reload)
uv run uvicorn app.main:app --reload

# Run all tests
uv run --all-extras pytest

# Run tests with coverage
uv run --all-extras pytest --cov=app --cov-report=term-missing

# Lint
uv run ruff check app/ tests/

# Auto-fix lint issues
uv run ruff check app/ tests/ --fix

# Type check
uv run mypy app/

# Build and run Docker container
docker compose up --build
```

## Code Style

### Python

- **Ruff** enforces formatting and linting (configured in `pyproject.toml`)
- **mypy** in strict mode for type checking
- Target Python 3.13+ (use modern syntax: `X | None`, `list[str]`, etc.)
- **No comments** unless explicitly requested — code should be self-documenting
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` decorator needed

### Frontend (JS/CSS)

- **No build step** — uses native ES modules with Preact + htm from CDN
- Each component lives in its own file under `static/js/components/`
- Shared utilities go in `static/js/utils.js`
- API helpers go in `static/js/api.js`
- Preact imports come from `static/js/preact.js` (single CDN source)
- CSS is split by concern: `variables.css`, `base.css`, `components.css`, `responsive.css`
- Use CSS custom properties (variables) for theming — never hardcode colors

## Making Changes

### Branch naming

- `feat/short-description` — new features
- `fix/short-description` — bug fixes
- `docs/short-description` — documentation changes
- `refactor/short-description` — code restructuring

### Commit messages

Use clear, concise commit messages:

```
feat: add calendar view to frontend
fix: resolve dark mode calendar icon color mismatch
docs: update CONTRIBUTING.md with frontend structure
refactor: extract ChatPanel into separate component
```

### Pull requests

1. Create a branch from `main`
2. Make your changes
3. Ensure all checks pass:
   - `uv run ruff check app/ tests/`
   - `uv run mypy app/`
   - `uv run --all-extras pytest`
4. Push and open a PR against `main`
5. CI must pass (lint, type check, tests, Docker build)

### Adding a new REST endpoint

1. Define the route in `app/routers/` (use existing routers or create a new one)
2. Add the Pydantic schema in `app/models/`
3. Implement business logic in `app/services/`
4. Add tests in `tests/test_routers/`
5. Register the router in `app/main.py` if it's a new router file

### Adding a new MCP tool

1. Add the tool in `app/mcp_server.py` with `@mcp.tool` decorator
2. The chat service automatically picks up new tools — no changes needed there
3. Add tests in `tests/test_mcp/test_mcp_server.py`
4. Update `AGENTS.md` Feature Reference table

### Adding a new frontend component

1. Create `static/js/components/MyComponent.js`
2. Import Preact hooks from `../preact.js`: `import { html, useState } from '../preact.js'`
3. Export the component: `export function MyComponent({ ... }) { ... }`
4. Import and use it in `static/js/app.js`
5. Add styles in `static/css/components.css`
6. No build step required — browser handles ES modules natively

### Changing the database schema

1. Update the SQLModel class in `app/models/`
2. Delete `todos.db` (development will auto-recreate via `init_db`)
3. Update related service functions in `app/services/`
4. Update test fixtures if needed
5. **Note**: There is no migration system — schema changes recreate the DB

## Testing

### Running tests

```sh
# All tests
uv run --all-extras pytest

# Specific test file
uv run --all-extras pytest tests/test_routers/test_todos.py

# With verbose output
uv run --all-extras pytest -v

# With coverage
uv run --all-extras pytest --cov=app --cov-report=html
```

### Test structure

- `tests/conftest.py` — shared fixtures (async session, HTTP client, MCP client)
- `tests/test_routers/` — HTTP endpoint integration tests
- `tests/test_services/` — Service-layer unit tests
- `tests/test_mcp/` — MCP tool tests using in-process `fastmcp.Client`

### Writing tests

- Use `httpx.AsyncClient` for endpoint tests (see `conftest.py` for the fixture)
- Use `fastmcp.Client(mcp)` for MCP tool tests
- The `session` fixture cleans tables before and after each test
- All async tests run automatically (`asyncio_mode = "auto"`)

## Debugging

Enable debug logging in `.env`:

```bash
DEBUG_LOGGING=true
```

This shows LiteLLM API requests/responses, SQL queries, and chat service iterations in the server logs.

## Architecture Notes

### Key conventions

- **MCP is the single source of truth** for tool definitions. `app/mcp_server.py` defines all tools; `chat_service.py` derives OpenAI-format schemas at runtime.
- **Frontend has no build step** — Preact + htm are loaded from CDN, components use native ES module imports.
- **Session management**: FastAPI routes use request-scoped sessions; MCP tools use `async_session_factory()` independently.
- **Static files** are served from `/static` by FastAPI's `StaticFiles` mount. `index.html` is served at `/` by a route handler.

### Adding dependencies

1. Add to `pyproject.toml` under `[project.dependencies]` or `[project.optional-dependencies]`
2. Run `uv sync` to update the lockfile
3. Commit both `pyproject.toml` and `uv.lock`