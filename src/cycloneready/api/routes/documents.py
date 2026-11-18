from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from cycloneready.api.deps import DbSessionDep
from cycloneready.db.repository import DocumentRepository

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
async def list_documents(
    session: DbSessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    repository = DocumentRepository(session)
    rows, total = await repository.search(q, limit, offset)

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
