"""Verify cyclone observations stored in the database."""

import asyncio

from sqlalchemy import func, select

from cycloneready.config import Settings
from cycloneready.db.models import CycloneObservation
from cycloneready.db.session import make_engine


async def main() -> None:
    settings = Settings()
    engine = make_engine(settings)

    try:
        async with engine.connect() as connection:
            total_observations = await connection.scalar(
                select(func.count()).select_from(CycloneObservation)
            )

            duplicate_groups = await connection.scalar(
                select(func.count()).select_from(
                    select(
                        CycloneObservation.storm_id,
                        CycloneObservation.observed_at,
                    )
                    .group_by(
                        CycloneObservation.storm_id,
                        CycloneObservation.observed_at,
                    )
                    .having(func.count() > 1)
                    .subquery()
                )
            )

            print("\nCycloneReady Duplicate Check")
            print("--------------------------------")
            print(f"Total observations: {total_observations}")
            print(f"Duplicate storm-time groups: {duplicate_groups}")

            if duplicate_groups == 0:
                print("Result: No duplicate observations found.")
            else:
                print("Result: Duplicate observations detected.")

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
