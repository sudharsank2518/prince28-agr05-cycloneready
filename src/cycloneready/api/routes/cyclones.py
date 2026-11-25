"""Cyclone routes: retrieve historical storm tracks."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from cycloneready.api.deps import DbSessionDep
from cycloneready.db.models import CycloneObservation

router = APIRouter(prefix="/cyclones", tags=["cyclones"])


@router.get("/{storm_id}/track")
async def get_cyclone_track(
    storm_id: str,
    session: DbSessionDep,
    limit: Annotated[int, Query(ge=1, le=10000)] = 5000,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Return chronological observations for one cyclone."""

    total = await session.scalar(
        select(func.count())
        .select_from(CycloneObservation)
        .where(CycloneObservation.storm_id == storm_id)
    )

    if not total:
        raise HTTPException(
            status_code=404,
            detail=f"No cyclone observations found for storm '{storm_id}'.",
        )

    statement = (
        select(CycloneObservation)
        .where(CycloneObservation.storm_id == storm_id)
        .order_by(CycloneObservation.observed_at.asc())
        .limit(limit)
        .offset(offset)
    )

    observations = (await session.scalars(statement)).all()

    return {
        "storm_id": storm_id,
        "total_observations": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "observed_at": item.observed_at,
                "latitude": item.latitude,
                "longitude": item.longitude,
                "wind_speed_kt": item.wind_speed_kt,
                "pressure_mb": item.pressure_mb,
                "basin": item.basin,
                "subbasin": item.subbasin,
                "nature": item.nature,
                "storm_number": item.storm_number,
            }
            for item in observations
        ],
    }
