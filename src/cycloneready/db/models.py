"""Tables, written as Python classes. Alembic turns changes here into migrations."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Predictable constraint names, so migrations can drop them later.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(Text)

    document: Mapped[str | None] = mapped_column(Text, index=True)

    source_url: Mapped[str | None] = mapped_column(Text)
    licence: Mapped[str | None] = mapped_column(String(200))
    doc_type: Mapped[str] = mapped_column(String(50), server_default="record")
    published_on: Mapped[date | None]
    sha256: Mapped[str] = mapped_column(String(64), index=True)

    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        server_default=text("'{}'"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    pages: Mapped[list["Page"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    cyclone_observations: Mapped[list["CycloneObservation"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_documents_doc_type", "doc_type"),
        Index(
            "ix_documents_metadata_gin",
            "metadata",
            postgresql_using="gin",
            postgresql_ops={"metadata": "jsonb_path_ops"},
        ),
    )


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    page_no: Mapped[int]
    text: Mapped[str] = mapped_column(Text)

    headings: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")

    document: Mapped[Document] = relationship(back_populates="pages")

    __table_args__ = (
        UniqueConstraint("document_id", "page_no", name="uq_pages_document_page"),
        CheckConstraint("page_no >= 1", name="page_no_positive"),
    )


class ParseFailure(Base):
    """One row per raw file that could not be parsed."""

    __tablename__ = "parse_failures"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(40), index=True)
    detail: Mapped[str] = mapped_column(Text, server_default="")
    attempts: Mapped[int] = mapped_column(server_default="1")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CycloneObservation(Base):
    """One position/intensity observation for a tropical cyclone."""

    __tablename__ = "cyclone_observations"

    id: Mapped[int] = mapped_column(primary_key=True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )

    storm_id: Mapped[str] = mapped_column(String(40), index=True)
    storm_number: Mapped[int | None]

    basin: Mapped[str | None] = mapped_column(String(80))
    subbasin: Mapped[str | None] = mapped_column(String(80))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    nature: Mapped[str | None] = mapped_column(String(80))

    latitude: Mapped[float]
    longitude: Mapped[float]
    wind_speed_kt: Mapped[float | None]
    pressure_mb: Mapped[float | None]

    document: Mapped[Document] = relationship(back_populates="cyclone_observations")

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "storm_id",
            "observed_at",
            name="uq_cyclone_observations_document_storm_time",
        ),
        CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="latitude_range",
        ),
        CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="longitude_range",
        ),
        Index(
            "ix_cyclone_observations_storm_time",
            "storm_id",
            "observed_at",
        ),
        # Additional indexes for analysis and reporting.
        Index(
            "ix_cyclone_observations_basin_year",
            "basin",
            "observed_at",
        ),
        Index(
            "ix_cyclone_observations_wind_speed",
            "wind_speed_kt",
        ),
    )
