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
| `CHAT_API_BASE` | — | Override base URL for local LLMs |

## REST API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/todos/` | List todos (`?completed=true/false`) |
| POST | `/api/todos/` | Create a todo |
| GET | `/api/todos/{id}` | Get a todo |
| PATCH | `/api/todos/{id}` | Partial update |
| DELETE | `/api/todos/{id}` | Delete a todo |
| POST | `/api/chat/` | Send a message to the AI chatbot |

Interactive docs at `/docs` (Swagger UI) and `/redoc` when the server is running.

## Chatbot

The app includes an AI chatbot reachable via a floating widget in the UI and the `POST /api/chat/` endpoint. It is a full agent — it can list, create, update, and delete todos on your behalf.

### Endpoint

```
POST /api/chat/
Content-Type: application/json

{
  "message": "Add a todo to buy groceries",
  "history": []          // optional: previous [{"role":"user","content":"..."},...]
}
```

Response:

```json
{ "response": "Done! I've added 'Buy groceries' to your list." }
```

The backend runs an agentic loop: it calls the LLM, executes any tool calls against the database, and loops until the model produces a final text reply.

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

## MCP Server

The app exposes a [Model Context Protocol](https://modelcontextprotocol.io) server at `/mcp` over Streamable HTTP. This lets LLM clients (Claude Desktop, MCP Inspector, etc.) manage todos directly.

### Tools

| Tool | Description |
|---|---|
| `list_todos` | List all todos; optional `completed` bool filter |
| `get_todo` | Fetch a single todo by UUID |
| `create_todo` | Create a new todo (`title` required, `description` optional) |
| `update_todo` | Partial update — only the fields you pass are changed |
| `delete_todo` | Delete a todo by UUID |
| `clear_completed` | Delete every completed todo; returns a count summary |

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
├── mcp_server.py             # FastMCP server with 6 tools
├── models/todo.py            # SQLModel ORM + Pydantic schemas
├── routers/
│   ├── todos.py              # REST CRUD routes
│   └── chat.py               # POST /api/chat/ endpoint
└── services/
    ├── todo_service.py       # business logic layer
    └── chat_service.py       # LLM agentic loop via LiteLLM

tests/
├── conftest.py               # session, client, mcp_client fixtures
├── test_routers/             # HTTP endpoint tests
├── test_services/            # service-layer unit tests
└── test_mcp/                 # MCP tool tests
```

See [`AGENTS.md`](../AGENTS.md) for the full architecture specification.
