"""Database seeding helper."""

import asyncio

from app.database import async_session_factory
from app.models.todo import Todo


async def seed() -> None:
    """Insert sample todos into the database."""
    async with async_session_factory() as session:
        sample = [
            Todo(title="Buy groceries", description="Milk, eggs, bread"),
            Todo(title="Read documentation", is_completed=True),
            Todo(title="Build the app"),
        ]
        for todo in sample:
            session.add(todo)
        await session.commit()
        print(f"Seeded {len(sample)} todos.")


if __name__ == "__main__":
    asyncio.run(seed())
