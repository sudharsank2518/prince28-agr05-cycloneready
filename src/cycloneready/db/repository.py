"""Database queries for reading CycloneReady documents."""

from __future__ import annotations

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from cycloneready.db.models import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(
        self,
        q: str | None = None,
        filters: dict[str, str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[int, list[dict]]:
        """List documents with typed-column and JSONB metadata filters."""

        statement = select(Document)
        count_statement = select(func.count(Document.id))

        if q:
            condition = Document.title.ilike(f"%{q}%")
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)

        if filters:
            for key, value in filters.items():
                if key == "document":
                    condition = Document.document == value

                elif key == "tags":
                    condition = cast(Document.metadata_, JSONB).contains({"tags": [value]})

                elif key == "year":
                    year_value = int(value) if value.isdigit() else value
                    condition = cast(Document.metadata_, JSONB).contains({"year": year_value})

                else:
                    condition = cast(Document.metadata_, JSONB).contains({key: value})

                statement = statement.where(condition)
                count_statement = count_statement.where(condition)

        total_result = await self.session.execute(count_statement)
        total = total_result.scalar_one()

        statement = statement.order_by(Document.id).limit(limit).offset(offset)

        result = await self.session.execute(statement)
        documents = result.scalars().all()

        items = [
            {
                "id": document.external_id,
                "title": document.title,
                **document.metadata_,
                "document": document.document,
            }
            for document in documents
        ]

        return total, items

    async def search(
        self,
        query: str | None = None,
        limit: int = 20,
        offset: int = 0,
        sort: str | None = None,
        document: str | None = None,
    ) -> tuple[list[dict], int]:
        """Search documents by title with optional document filtering."""

        statement = select(Document)
        count_statement = select(func.count(Document.id))

        if query:
            condition = Document.title.ilike(f"%{query}%")
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)

        # Filter using the indexed typed document column.
        if document:
            condition = Document.document == document
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)

        total_result = await self.session.execute(count_statement)
        total = total_result.scalar_one()

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
                "document": document.document,
            }
            for document in documents
        ]

        return items, total

    async def get(self, external_id: str) -> dict | None:
        """Get a document by its external ID."""

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
            "document": document.document,
        }
