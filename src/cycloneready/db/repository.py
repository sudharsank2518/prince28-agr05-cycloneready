"""Database queries for reading CycloneReady documents."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cycloneready.db.models import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def search(
        self,
        query: str | None = None,
        limit: int = 20,
        offset: int = 0,
        sort: str | None = None,
    ) -> tuple[list[dict], int]:
        statement = select(Document)

        if query:
            statement = statement.where(Document.title.ilike(f"%{query}%"))

        count_statement = select(Document.id)

        if query:
            count_statement = count_statement.where(Document.title.ilike(f"%{query}%"))

        total_result = await self.session.execute(count_statement)
        total = len(total_result.scalars().all())

        # Sorting options
        sort_columns = {
            "title": Document.title,
            "published_on": Document.published_on,
        }

        if sort:
            descending = sort.startswith("-")
            field = sort[1:] if descending else sort

            if field not in sort_columns:
                raise ValueError("Invalid sort field")

            column = sort_columns[field]

            statement = statement.order_by(column.desc() if descending else column.asc())
        else:
            # Preserve the original default ordering
            statement = statement.order_by(Document.id)

        statement = statement.limit(limit).offset(offset)

        result = await self.session.execute(statement)
        documents = result.scalars().all()

        items = [
            {
                "id": document.external_id,
                "title": document.title,
                "source_url": document.source_url,
                "licence": document.licence,
                "doc_type": document.doc_type,
                "published_on": (
                    document.published_on.isoformat() if document.published_on else None
                ),
                **document.metadata_,
            }
            for document in documents
        ]

        return items, total

    async def get(self, external_id: str) -> dict | None:
        statement = select(Document).where(Document.external_id == external_id)

        result = await self.session.execute(statement)
        document = result.scalar_one_or_none()

        if document is None:
            return None

        return {
            "id": document.external_id,
            "title": document.title,
            "source_url": document.source_url,
            "licence": document.licence,
            "doc_type": document.doc_type,
            "published_on": (document.published_on.isoformat() if document.published_on else None),
            **document.metadata_,
        }
