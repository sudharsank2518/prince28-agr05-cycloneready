"""Check the connection to the PostgreSQL database."""

import asyncio

from sqlalchemy import text

from cycloneready.config import Settings
from cycloneready.db.session import make_engine


async def main():
    settings = Settings()
    engine = make_engine(settings)

    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT current_database(), version()"))

            database_name, version = result.fetchone()

            print("Connected to database:", database_name)
            print("PostgreSQL version:", version)

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
