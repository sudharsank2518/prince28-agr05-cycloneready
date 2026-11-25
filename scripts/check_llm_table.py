import asyncio

from sqlalchemy import inspect

from cycloneready.config import get_settings
from cycloneready.db.session import make_engine


async def main():
    settings = get_settings()
    engine = make_engine(settings)

    try:
        async with engine.connect() as connection:
            table_exists = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).has_table("llm_calls")
            )

            print("llm_calls table exists:", table_exists)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
