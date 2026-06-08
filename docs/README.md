# MyToDo

A ToDo app with simple design and AI integration.

## Quick Start

```sh
# Install dependencies
uv sync --all-extras

# Run the server
uv run uvicorn app.main:app --reload

# Run tests
uv run --all-extras pytest

# Run linter + type checker
uv run ruff check app/ tests/
uv run mypy app/
```

## REST API Endpoints

| Method | Path              | Description              |
|--------|-------------------|--------------------------|
| GET    | /health           | Health check             |
| GET    | /api/todos/       | List todos               |
| POST   | /api/todos/       | Create a todo            |
| GET    | /api/todos/{id}   | Get a todo               |
| PATCH  | /api/todos/{id}   | Update a todo            |
| DELETE | /api/todos/{id}   | Delete a todo            |

Interactive docs are available at `/docs` (Swagger UI) and `/redoc` when the server is running.

## MCP Server

The app exposes a [Model Context Protocol](https://modelcontextprotocol.io) server at `/mcp` over Streamable HTTP. This lets LLM clients (Claude Desktop, MCP Inspector, etc.) read and manage todos directly.

### Tools

| Tool              | Description                                              |
|-------------------|----------------------------------------------------------|
| `list_todos`      | List all todos; optional `completed` bool filter         |
| `get_todo`        | Fetch a single todo by UUID                              |
| `create_todo`     | Create a new todo (`title` required, `description` optional) |
| `update_todo`     | Partial update — only the fields you pass are changed    |
| `delete_todo`     | Delete a todo by UUID                                    |
| `clear_completed` | Delete every completed todo; returns a count summary     |

### Connecting Claude Desktop

Add the following to your `claude_desktop_config.json`:

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

The in-process test client uses `fastmcp.Client` pointed directly at the `FastMCP` instance:

```python
from fastmcp import Client
from app.mcp_server import mcp

async with Client(mcp) as client:
    result = await client.call_tool("create_todo", {"title": "hello"})
    print(result.data)  # {"id": "...", "title": "hello", ...}
```

The test suite covers all 6 tools via `tests/test_mcp/test_mcp_server.py`.

## Project Structure

```
app/
├── main.py           # FastAPI app + MCP mount at /mcp
├── config.py         # pydantic-settings (DATABASE_URL, etc.)
├── database.py       # async engine + session factory
├── dependencies.py   # get_todo_or_404 FastAPI dependency
├── mcp_server.py     # FastMCP server with 6 tools
├── models/todo.py    # SQLModel ORM + Pydantic schemas
├── routers/todos.py  # REST CRUD routes
└── services/todo_service.py  # business logic layer

tests/
├── conftest.py           # session, client, mcp_client fixtures
├── test_routers/         # HTTP endpoint tests
├── test_services/        # service-layer unit tests
└── test_mcp/             # MCP tool tests
```

See [`AGENTS.md`](../AGENTS.md) for the full architecture specification.
