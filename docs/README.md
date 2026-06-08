# MyToDo

A ToDo app with simple design and AI integration.

## Quick Start

```sh
# Install dependencies
uv sync --all-extras

# Run the server
uv run uvicorn app.main:app --reload

# Run tests
uv run pytest

# Run linter + type checker
uv run ruff check app/ tests/
uv run mypy app/
```

## API Endpoints

| Method | Path              | Description              |
|--------|-------------------|--------------------------|
| GET    | /health           | Health check             |
| GET    | /api/todos/       | List todos               |
| POST   | /api/todos/       | Create a todo            |
| GET    | /api/todos/{id}   | Get a todo               |
| PATCH  | /api/todos/{id}   | Update a todo            |
| DELETE | /api/todos/{id}   | Delete a todo            |

## Project Structure

See [`agent.md`](../agent.md) for the full architecture specification.
