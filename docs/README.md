# MyToDo

A ToDo app with simple design, REST API, MCP server, and an AI chatbot that can manage todos using any LLM provider.

## Quick Start

```sh
# Install dependencies
uv sync --all-extras

# Copy and configure environment
cp .env.example .env   # then fill in your API key(s)

# Run the server
uv run uvicorn app.main:app --reload

# Run tests
uv run --all-extras pytest

# Run linter + type checker
uv run ruff check app/ tests/
uv run mypy app/
```

## Environment Variables

Create a `.env` file at the project root (or set these in your shell):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./todos.db` | Async SQLite connection string |
| `DEBUG_LOGGING` | `false` | Enable debug logs for LLM calls and database operations |
| `API_KEY` | — (empty) | Optional API key. When set, non-browser requests must send `Authorization: Bearer <key>` or `X-API-Key: <key>`. The SPA at `/` and `/health` are always allowed. Empty = open access (default). |
| `CORS_ORIGINS` | — (empty) | Optional CORS allow-list. Set to `*` or a comma-separated list to permit a separate SPA / external client. Empty = same-origin only. |
| `CHAT_RATE_LIMIT` | `0` | Per-client chat request limit per minute on `/api/chat/*`. `0` disables rate limiting (default). |
| `CHAT_MODEL` | `claude-sonnet-4-6` | LiteLLM model string (see [Chatbot](#chatbot)) |
| `ANTHROPIC_API_KEY` | — | Required for Claude models |
| `OPENAI_API_KEY` | — | Required for GPT models |
| `OLLAMA_API_KEY` | — | Required for Ollama Cloud |
| `CHAT_API_BASE` | — | Override base URL for local LLMs |

All security features are **off by default** (empty / `0`) for frictionless local development. The bundled `docker-compose.yml` passes `API_KEY`, `CORS_ORIGINS`, `CHAT_RATE_LIMIT`, and `OLLAMA_API_KEY` through from the host environment.

## REST API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/todos/` | List todos (`?completed=true/false`, `?order_by=position/priority/due_date`, `?q=`, `?priority=`, `?tag=`, `?limit=`, `?offset=`) |
| POST | `/api/todos/` | Create a todo (`title` required; `priority`, `due_date`, `tags` optional) |
| GET | `/api/todos/{id}` | Get a todo |
| PATCH | `/api/todos/{id}` | Partial update (supports `priority`, `due_date`, `is_completed`, `title`, `description`, `tags`; set `tags`/`due_date` to `null` to clear) |
| DELETE | `/api/todos/{id}` | Soft-delete a todo (movable to trash; restore later) |
| PATCH | `/api/todos/reorder` | Batch reorder (`{items: [{id, position}, …]}`) |
| GET | `/api/todos/stats` | Aggregate counts (total/active/completed/overdue/by_priority) |
| GET | `/api/todos/trash` | List soft-deleted todos (newest-deleted first) |
| DELETE | `/api/todos/trash` | Permanently delete every soft-deleted todo |
| POST | `/api/todos/{id}/restore` | Restore a soft-deleted todo |
| DELETE | `/api/todos/{id}/purge` | Permanently delete a single todo |
| POST | `/api/chat/` | Send a message to the AI chatbot (non-streaming) |
| POST | `/api/chat/stream` | Send a message and stream the reply via SSE |
| GET | `/api/chat/info` | Active provider, model, capability flags |
| GET | `/api/chat/models` | Models exposed by the configured OpenAI-compatible server |
| GET | `/api/chat/sessions` | List persisted chat sessions |
| POST | `/api/chat/sessions` | Create a new chat session |
| GET | `/api/chat/sessions/{id}` | Fetch a single chat session |
| GET | `/api/chat/sessions/{id}/messages` | List messages for a session |
| DELETE | `/api/chat/sessions/{id}` | Delete a session and its messages |

Query parameters for `GET /api/todos/`:
- `completed` — `true`/`false` filter on completion status
- `order_by` — `position` (default), `priority`, or `due_date`
- `q` — case-insensitive substring search over title + description
- `priority` — filter by exact priority (`0`=none, `1`=low, `2`=med, `3`=high)
- `tag` — filter by a single tag token (tags are stored comma-separated)
- `limit` / `offset` — pagination (`limit` 1–500, `offset` >= 0)

All todo queries exclude soft-deleted rows by default (i.e. items in the trash don't appear in the main list, stats, or reorder results).

Interactive docs at `/docs` (Swagger UI) and `/redoc` when the server is running.

## Chatbot

The app includes an AI chatbot reachable via a floating widget in the UI and the `/api/chat/*` endpoints. It is a full agent — it can list, create, update, and delete todos on your behalf.

### How it works

The chat service uses **LiteLLM** to call any LLM provider. Tool definitions are derived at runtime from the MCP server (the single source of truth) via `_build_openai_tools()` and `_mcp_schema_to_openai()`. Tool execution is routed through the MCP server via `_run_tool_via_mcp()` — there is no duplicate tool logic in the chat service.

The system prompt instructs the LLM to **only set optional fields like `priority` and `due_date` when the user explicitly mentions them**, preventing the model from inventing default values.

### Endpoints

#### `POST /api/chat/` (non-streaming)

```
POST /api/chat/
Content-Type: application/json

{
  "message": "Add a todo to buy groceries",
  "history": [],          // optional: previous [{"role":"user","content":"..."},...]
  "session_id": "uuid"     // optional: persist the turn + reuse prior history
}
```

Response:

```json
{ "response": "Done! I've added 'Buy groceries' to your list.", "session_id": "uuid" }
```

#### `POST /api/chat/stream` (SSE)

Same request body. The response is a `text/event-stream` with frames:

| Event | Payload | Notes |
|---|---|---|
| `start` | `{session_id, model, provider}` | First event |
| `token` | `{delta}` | Incremental text from the model |
| `tool` | `{name, arguments, result}` | A tool call the agent made |
| `done` | `{response, session_id}` | Stream finished; the assistant reply is complete |
| `error` | `{message}` | Stream aborted |

#### `GET /api/chat/info`

```json
{
  "provider": "lm-studio",
  "model": "openai/qwen2.5-7b-instruct",
  "api_base": "http://localhost:1234/v1",
  "streaming": true,
  "tool_use_supported": true
}
```

#### `GET /api/chat/models`

Proxies `{CHAT_API_BASE}/models` for OpenAI-compatible servers (LM Studio, vLLM, Ollama OpenAI shim, etc). Returns `available: false` with an `error` message for providers that don't expose a models endpoint (e.g. Anthropic).

#### Chat sessions

Create a session with `POST /api/chat/sessions` (body `{"title": "..."}`), then pass the returned `id` as `session_id` on chat calls. The backend will load prior messages on every turn and persist the new turn afterwards. The first user message auto-titles the session.

The frontend widget manages sessions automatically — `session_id` is stored in `localStorage` and reused across messages, with a "+" button to start a new session.

### Switching providers

Set `CHAT_MODEL` to any [LiteLLM model string](https://docs.litellm.ai/docs/providers). **Note: Tool use (the chatbot's ability to manage todos) requires reliable function-calling support.**

#### Recommended (tool use works ✅)

```bash
# Anthropic Claude (default, recommended)
CHAT_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI GPT (also excellent)
CHAT_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

#### Limited Support (tool use unreliable ⚠️)

Local models via Ollama have unreliable tool use — see below.

#### Local / Alternative Providers (no tool support ❌)

Ollama models theoretically support function calling via LiteLLM's JSON mode fallback, but in practice this is **unreliable or crashes**:

- **llama2** — Only "completion" capability; crashes when processing function definitions
- **mistral 7b, neural-chat** — Return tool definitions as text instead of executing them
- **gemma** — Returns tool definitions as text

LiteLLM attempts to work around this by sending function definitions in JSON format, but models lack the instruction-tuning to follow the protocol reliably.

**To use local LLMs effectively:**
- Avoid function calling; use simple conversation queries instead
- Or deploy a larger, more capable model (13B+ with chat/instruct tuning)
- Or use cloud providers (Claude, GPT-4o) for production workloads

```bash
# Ollama (conversation only, no tool use)
CHAT_MODEL=ollama/llama2
CHAT_API_BASE=http://localhost:11434
```

### Running with local LLMs (Ollama, LM Studio, etc.)

#### Option 1: Ollama on host, app in Docker (Mac/Windows)

If Ollama is running on your host machine, set:

```bash
CHAT_MODEL=ollama/llama3.1
CHAT_API_BASE=http://host.docker.internal:11434
```

(On Docker Desktop for Mac/Windows, `host.docker.internal` reaches the host. On Linux, use your host IP instead, e.g., `http://192.168.1.100:11434`.)

#### Option 2: Ollama in Docker alongside the app (recommended)

Use this `docker-compose.yml`:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ollama-data:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0:11434

  app:
    build: .
    container_name: mytodo-app
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite+aiosqlite:////app/data/todos.db
      - CHAT_MODEL=ollama/llama3.1
      - CHAT_API_BASE=http://ollama:11434
      # Security (all optional — empty = feature off)
      - API_KEY=
      - CORS_ORIGINS=
      - CHAT_RATE_LIMIT=0
    depends_on:
      - ollama
    volumes:
      - todos-data:/app/data

volumes:
  todos-data:
  ollama-data:
```

Start both services:

```bash
docker compose up
```

Then pull a model (one-time):

```bash
docker exec ollama ollama pull llama3.1
```

#### Option 3: LM Studio or other OpenAI-compatible servers

For any OpenAI-compatible server (LM Studio, vLLM, text-generation-webui, etc.):

```bash
CHAT_MODEL=openai/my-model
CHAT_API_BASE=http://localhost:1234/v1  # or your server's API endpoint
```

**No API key is required for local servers.** The chat service detects when
`CHAT_API_BASE` points at a local host (localhost, 127.0.0.1,
`host.docker.internal`, `0.0.0.0`) or when `CHAT_MODEL` uses the
`openai/` prefix, and automatically injects a dummy `OPENAI_API_KEY` so
LiteLLM can dispatch the request. Local servers (LM Studio in particular)
ignore the key, but LiteLLM refuses to send a request without one.

If you need a real key, set `OPENAI_API_KEY=anything` in your `.env` —
LM Studio will accept it as long as the value is non-empty.

**LM Studio setup checklist:**
1. Open LM Studio → *Developer* tab → start the local server
   (default: `http://localhost:1234/v1`).
2. Load a model that supports function/tool calling (e.g. Qwen 2.5, Llama 3.1
   Instruct, Mistral Nemo, GLM-4). Smaller/older models won't follow the tool
   protocol.
3. In your `.env`:
   ```bash
   CHAT_MODEL=openai/<model-id-from-LM-Studio>
   CHAT_API_BASE=http://localhost:1234/v1
   ```
   Use the model identifier LM Studio shows for the loaded model
   (e.g. `openai/zai-org/glm-4.7-flash` or `openai/qwen2.5-7b-instruct`).

If tool use is unreliable on your chosen model, the chat service falls back
to parsing JSON tool calls from the model's text output (the same workaround
used for Ollama).

## MCP Server

The app exposes a [Model Context Protocol](https://modelcontextprotocol.io) server at `/mcp` over Streamable HTTP. This lets LLM clients (Claude Desktop, MCP Inspector, etc.) manage todos directly.

### Tools

| Tool | Description |
|---|---|
| `list_todos` | List todos; optional `completed`, `order_by` (`position`/`priority`/`due_date`), `q` (substring search), `priority`, `tag`, `limit`, `offset` |
| `get_todo` | Fetch a single (active) todo by UUID |
| `create_todo` | Create a todo (`title` required; `description`, `priority`, `due_date`, `tags` optional) |
| `update_todo` | Partial update — only the fields you pass are changed; set `due_date` to `"clear"` or `tags` to `"clear"` to remove them |
| `delete_todo` | Soft-delete a todo by UUID (movable to trash; restore later) |
| `restore_todo` | Restore a previously soft-deleted todo from the trash |
| `clear_completed` | Soft-delete every completed todo; returns a count summary |
| `reorder_todos` | Batch reorder by position (`items: [{id, position}, …]`) |
| `get_todo_stats` | Aggregate counts (total/active/completed/overdue/by_priority) |

Tags are stored as a comma-separated string. Use `"clear"` (not `null`) to remove `due_date` or `tags` via the MCP tools, since `null` means "leave unchanged". Tool descriptions instruct the LLM to only set optional fields when the user mentions them.

### Connecting Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mytodo": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Connecting MCP Inspector

```sh
npx @modelcontextprotocol/inspector http://localhost:8000/mcp
```

### Testing the MCP server

```python
from fastmcp import Client
from app.mcp_server import mcp

async with Client(mcp) as client:
    result = await client.call_tool("create_todo", {"title": "hello"})
    print(result.data)  # {"id": "...", "title": "hello", ...}
```

## Frontend

The app serves a single-page app at `/` built with **Preact + htm** (no build step). The frontend is organized as modular ES modules under `static/`.

### File structure

```
static/
├── css/
│   ├── variables.css    # CSS custom properties, reset, light/dark/auto themes
│   ├── base.css         # Body, container, header, progress, toast, stats
│   ├── components.css   # All component styles (input, toolbar, todo, calendar, chat)
│   └── responsive.css   # Mobile media queries
└── js/
    ├── preact.js         # Re-exports Preact + htm from CDN (single import point)
    ├── main.js           # Entry point: renders <App /> into #app
    ├── app.js            # App component (state management, API orchestration)
    ├── api.js            # All REST API and chat API helper functions
    ├── utils.js           # formatDate, priorityBadge, getWeekDates, etc.
    └── components/
        ├── InputRow.js
        ├── Toolbar.js
        ├── TodoList.js
        ├── TodoItem.js
        ├── CalendarView.js
        ├── TrashView.js
        ├── ChatBubble.js
        ├── ChatPanel.js
        ├── ThemeToggle.js
        └── Toast.js
```

`index.html` is a minimal shell that loads the CSS files and the JS entry point. FastAPI serves `index.html` at `/` and mounts `static/` at `/static`.

### Features

- **List view** — Filter pills (All / Active / Completed), drag-and-drop reorder, priority badges (P1/P2/P3), due dates with overdue / due-soon highlighting, **inline edit** (double-click a todo — or click its title / pencil icon — to edit title, description, and tags inline; Enter saves, Esc cancels), **tag chips**
- **Calendar view** — Weekly grid with prev/next week navigation, "Today" button, priority-sorted cards, unscheduled section, "Other dates" section for out-of-week todos
- **Add-todo form** — Priority dropdown (None / P3 / P2 / P1), date picker, and comma-separated tags input
- **Search** — Substring search over title + description (top-right search box)
- **Priority filter** — Dropdown to filter by a single priority value
- **Stats bar** — Total / active / completed / overdue counts sourced from `/api/todos/stats`
- **Trash view** — Soft-deleted todos with restore / purge-permanently / empty-trash actions (toggle via the trash icon in the toolbar)
- **Browser reminders** — Notifications for overdue and due-soon todos (requests Notification permission)
- **AI chat widget** — Streaming responses, session persistence, provider detection
- **Theme toggle** — Light / Auto / Dark, persisted in localStorage

### Adding a new frontend component

1. Create `static/js/components/MyComponent.js`
2. Import from `preact.js`: `import { html, useState } from '../preact.js'`
3. Export the component: `export function MyComponent({ ... }) { return html\`...\`; }`
4. Import and use it in `app.js`
5. Add styles to `static/css/components.css`
6. No build step required — browsers handle ES modules natively

## Debugging

### Enable debug logging

To see detailed logs from LLM calls, database operations, and HTTP requests:

```bash
# In .env or shell environment
DEBUG_LOGGING=true

# Then restart the server
uv run uvicorn app.main:app --reload
```

This will output debug-level logs showing:
- LiteLLM API requests and responses
- SQL queries and results
- Chat service iterations and tool execution

Debug mode is useful for:
- Troubleshooting chatbot tool use issues
- Understanding why a model isn't responding correctly
- Inspecting database queries

## Project Structure

```
app/
├── main.py                   # FastAPI app + static mount + MCP mount at /mcp
├── config.py                 # pydantic-settings (DATABASE_URL, CHAT_MODEL, API_KEY, etc.)
├── database.py               # async engine + session factory
├── dependencies.py           # get_todo_or_404 FastAPI dependency
├── mcp_server.py             # FastMCP server with 9 tools
├── models/
│   ├── todo.py               # SQLModel ORM + Pydantic schemas (incl. TodoStats)
│   └── chat.py               # ChatSession + ChatMessage ORM & schemas
├── routers/
│   ├── todos.py               # REST CRUD routes (/api/todos/)
│   ├── chat.py                # Chat streaming/non-streaming + info + models
│   └── chat_sessions.py       # Chat session CRUD (/api/chat/sessions)
├── security/                  # Optional auth, CORS, rate-limit middleware (all off by default)
│   ├── auth.py                # API-key middleware (enabled when API_KEY set)
│   ├── cors.py                # CORS from CORS_ORIGINS
│   └── rate_limit.py          # Per-client /api/chat rate limiting
└── services/
    ├── todo_service.py        # business logic (search/tags/stats/soft-delete)
    ├── chat_service.py        # LLM agentic loop via LiteLLM (tools → MCP)
    └── chat_history.py        # chat session + message persistence

static/                        # Frontend assets (no build step)
├── css/
│   ├── variables.css          # CSS custom properties + theme variants
│   ├── base.css               # Body, container, header, progress, toast
│   ├── components.css         # All component styles
│   └── responsive.css         # Mobile media queries
└── js/
    ├── preact.js               # Re-exports Preact + htm from CDN
    ├── main.js                 # Entry point: renders <App />
    ├── app.js                  # App component (state, API calls)
    ├── api.js                  # API helper functions
    ├── utils.js                # formatDate, priorityBadge, parseTags, isDueSoon, etc.
    └── components/
        ├── InputRow.js
        ├── Toolbar.js
        ├── TodoList.js
        ├── TodoItem.js
        ├── CalendarView.js
        ├── TrashView.js
        ├── ChatBubble.js
        ├── ChatPanel.js
        ├── ThemeToggle.js
        └── Toast.js

tests/
├── conftest.py                # session, client, mcp_client fixtures
├── test_routers/
│   ├── test_todos.py          # HTTP endpoint tests
│   ├── test_todos_new.py      # Search/filter/pagination/stats/trash/restore tests
│   ├── test_chat.py           # Non-streaming chat tests
│   ├── test_chat_endpoints.py  # SSE, sessions, models tests
│   └── test_security.py       # Auth + rate-limit middleware tests
├── test_services/
│   ├── test_todo_service.py    # Service-layer unit tests
│   ├── test_todo_service_new.py  # Search/tags/pagination/stats/soft-delete tests
│   ├── test_chat_service.py    # Chat service + MCP tool tests
│   └── test_chat_history.py   # Chat persistence tests
└── test_mcp/
    ├── test_mcp_server.py      # MCP tool tests (in-process fastmcp.Client)
    └── test_mcp_server_new.py  # Extended list/search/stats/restore tool tests
```

See [`AGENTS.md`](../AGENTS.md) for the full architecture specification and [`CONTRIBUTING.md`](../CONTRIBUTING.md) for development guidelines.