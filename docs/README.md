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
| `CHAT_MODEL` | `claude-sonnet-4-6` | LiteLLM model string (see [Chatbot](#chatbot)) |
| `ANTHROPIC_API_KEY` | — | Required for Claude models |
| `OPENAI_API_KEY` | — | Required for GPT models |
| `OLLAMA_API_KEY` | — | Required for Ollama Cloud |
| `CHAT_API_BASE` | — | Override base URL for local LLMs |

## REST API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/todos/` | List todos (`?completed=true/false`, `?order_by=position/priority/due_date`) |
| POST | `/api/todos/` | Create a todo (`title` required, `priority` and `due_date` optional) |
| GET | `/api/todos/{id}` | Get a todo |
| PATCH | `/api/todos/{id}` | Partial update (supports `priority`, `due_date`, `is_completed`, `title`, `description`) |
| DELETE | `/api/todos/{id}` | Delete a todo |
| PATCH | `/api/todos/reorder` | Batch reorder (`{items: [{id, position}, …]}`) |
| POST | `/api/chat/` | Send a message to the AI chatbot (non-streaming) |
| POST | `/api/chat/stream` | Send a message and stream the reply via SSE |
| GET | `/api/chat/info` | Active provider, model, capability flags |
| GET | `/api/chat/models` | Models exposed by the configured OpenAI-compatible server |
| GET | `/api/chat/sessions` | List persisted chat sessions |
| POST | `/api/chat/sessions` | Create a new chat session |
| GET | `/api/chat/sessions/{id}` | Fetch a single chat session |
| GET | `/api/chat/sessions/{id}/messages` | List messages for a session |
| DELETE | `/api/chat/sessions/{id}` | Delete a session and its messages |

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
| `list_todos` | List all todos; optional `completed` bool filter and `order_by` sort (`position`, `priority`, `due_date`) |
| `get_todo` | Fetch a single todo by UUID |
| `create_todo` | Create a new todo (`title` required, `priority` and `due_date` optional) |
| `update_todo` | Partial update — only the fields you pass are changed; set `due_date` to `"clear"` to remove it |
| `delete_todo` | Delete a todo by UUID |
| `clear_completed` | Delete every completed todo; returns a count summary |
| `reorder_todos` | Batch reorder by position (`items: [{id, position}, …]`) |

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

The app serves a single-page app at `/` built with **Preact + htm** (no build step).

### Features

- **List view** — Filter pills (All / Active / Completed), drag-and-drop reorder, priority badges (P1/P2/P3), due dates with overdue highlighting
- **Calendar view** — Weekly grid with prev/next week navigation, "Today" button, priority-sorted cards (P1 first), unscheduled section
- **Add-todo form** — Priority dropdown (None / P3 / P2 / P1) and date picker
- **AI chat widget** — Streaming responses, session persistence, provider detection
- **Theme toggle** — Light / Auto / Dark, persisted in localStorage

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
├── main.py                   # FastAPI app + MCP mount at /mcp
├── config.py                 # pydantic-settings (DATABASE_URL, CHAT_MODEL, etc.)
├── database.py               # async engine + session factory
├── dependencies.py           # get_todo_or_404 FastAPI dependency
├── mcp_server.py             # FastMCP server with 7 tools
├── models/
│   ├── todo.py               # SQLModel ORM + Pydantic schemas
│   └── chat.py               # ChatSession + ChatMessage ORM & schemas
├── routers/
│   ├── todos.py               # REST CRUD routes (/api/todos/)
│   ├── chat.py                # Chat streaming/non-streaming + info + models
│   └── chat_sessions.py       # Chat session CRUD (/api/chat/sessions)
└── services/
    ├── todo_service.py        # business logic layer
    ├── chat_service.py        # LLM agentic loop via LiteLLM (tools → MCP)
    └── chat_history.py        # chat session + message persistence

tests/
├── conftest.py                # session, client, mcp_client fixtures
├── test_routers/
│   ├── test_todos.py          # HTTP endpoint tests
│   ├── test_chat.py           # Non-streaming chat tests
│   └── test_chat_endpoints.py  # SSE, sessions, models tests
├── test_services/
│   ├── test_todo_service.py    # Service-layer unit tests
│   ├── test_chat_service.py    # Chat service + MCP tool tests
│   └── test_chat_history.py   # Chat persistence tests
└── test_mcp/
    └── test_mcp_server.py      # MCP tool tests (in-process fastmcp.Client)
```

See [`AGENTS.md`](../AGENTS.md) for the full architecture specification.