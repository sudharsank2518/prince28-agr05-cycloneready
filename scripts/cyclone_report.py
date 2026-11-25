"""Generate a summary report from cyclone observations."""

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

            unique_storms = await connection.scalar(
                select(func.count(func.distinct(CycloneObservation.storm_id)))
            )

            year_results = await connection.execute(
                select(
                    func.extract("year", CycloneObservation.observed_at).label("year"),
                    func.count().label("observations"),
                )
                .group_by("year")
                .order_by("year")
            )

            basin_results = await connection.execute(
                select(
                    CycloneObservation.basin,
                    func.count().label("observations"),
                )
                .group_by(CycloneObservation.basin)
                .order_by(func.count().desc())
            )

            strongest_results = await connection.execute(
                select(
                    CycloneObservation.storm_id,
                    CycloneObservation.observed_at,
                    CycloneObservation.wind_speed_kt,
                    CycloneObservation.latitude,
                    CycloneObservation.longitude,
                )
                .where(CycloneObservation.wind_speed_kt.is_not(None))
                .order_by(CycloneObservation.wind_speed_kt.desc())
                .limit(10)
            )

            print("\nCYCLONEREADY - CYCLONE SUMMARY REPORT")
            print("=" * 55)

            print(f"\nTotal observations : {total_observations:,}")
            print(f"Unique storms      : {unique_storms:,}")

            print("\nOBSERVATIONS BY YEAR")
            print("-" * 55)

            for year, count in year_results:
                print(f"{int(year)} : {count:,}")

            print("\nOBSERVATIONS BY BASIN")
            print("-" * 55)

            for basin, count in basin_results:
                print(f"{basin or 'Unknown'} : {count:,}")

            print("\nTOP 10 STRONGEST RECORDED WINDS")
            print("-" * 75)
            print(
                f"{'Storm ID':<18} {'Date':<22} "
                f"{'Wind (kt)':<12} {'Latitude':<10} {'Longitude':<10}"
            )

            for storm_id, observed_at, wind, latitude, longitude in strongest_results:
                print(
                    f"{storm_id:<18} "
                    f"{str(observed_at):<22} "
                    f"{wind:<12.1f} "
                    f"{latitude:<10.2f} "
                    f"{longitude:<10.2f}"
                )

            print("\n" + "=" * 55)
            print("REPORT GENERATION COMPLETED")

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
