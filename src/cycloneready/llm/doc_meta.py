"""Validated metadata contract for CycloneReady documents."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocKind = Literal[
    "guideline",
    "handbook",
    "guide",
    "plan",
    "manual",
    "bulletin",
    "notice",
    "circular",
    "checklist",
    "other",
]

Hazard = Literal[
    "cyclone",
    "flood",
    "storm_surge",
    "heavy_rain",
    "coastal_flooding",
    "other",
]

Phase = Literal[
    "mitigation",
    "preparedness",
    "response",
    "recovery",
    "monitoring",
]


class DocMeta(BaseModel):
    """Structured metadata extracted from a CycloneReady source document."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    doc_kind: DocKind
    year: int | None = Field(default=None, ge=1900, le=2100)
    language: str = Field(min_length=2, max_length=50)
    summary: str = Field(min_length=1, max_length=500)

    topics: list[str] = Field(default_factory=list)
    hazard: list[Hazard] = Field(default_factory=list)
    phase: list[Phase] = Field(default_factory=list)
    action: list[str] = Field(default_factory=list)
    responsible: list[str] = Field(default_factory=list)
    warning_stage: list[str] = Field(default_factory=list)
