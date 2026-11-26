from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from cycloneready.api.deps import DbSessionDep
from cycloneready.db.repository import DocumentRepository

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
async def list_documents(
    session: DbSessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    document: Annotated[str | None, Query()] = None,
    doc_kind: Annotated[str | None, Query()] = None,
    year: Annotated[str | None, Query()] = None,
    hazard: Annotated[str | None, Query()] = None,
    phase: Annotated[str | None, Query()] = None,
    language: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Annotated[str | None, Query()] = None,
) -> dict:
    repository = DocumentRepository(session)

    filters = {
        key: value
        for key, value in {
            "document": document,
            "doc_kind": doc_kind,
            "year": year,
            "hazard": hazard,
            "phase": phase,
            "language": language,
        }.items()
        if value is not None
    }

    try:
        total, rows = await repository.list(
            q=q,
            filters=filters or None,
            limit=limit,
            offset=offset,
            sort=sort,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": rows,
    }


@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    session: DbSessionDep,
) -> dict:
    repository = DocumentRepository(session)
    record = await repository.get(doc_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No document with id '{doc_id}'.",
        )

    return record
