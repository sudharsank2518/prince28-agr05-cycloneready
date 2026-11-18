"""Show PostgreSQL's query execution plan for document searches."""

import asyncio
import json

from sqlalchemy import text

from cycloneready.config import get_settings
from cycloneready.db.session import make_engine


async def main() -> None:
    settings = get_settings()
    engine = make_engine(settings)

    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("""
                    SELECT DISTINCT metadata->>'hazard'
                    FROM documents
                    ORDER BY 1
                """)
            )

            hazards = result.scalars().all()
            print("Available hazard values:", hazards)

            query = text("""
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT id, title
                FROM documents
                WHERE metadata ? 'hazard'
            """)

            result = await connection.execute(query)
            plan = result.scalar_one()

            print("\nQuery execution plan:")
            print(json.dumps(plan, indent=2))

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
