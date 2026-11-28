"""Extract and validate structured metadata from CycloneReady documents."""

import json

from pydantic import ValidationError

from cycloneready.llm.doc_meta import DocMeta
from cycloneready.llm.gateway import LLMGateway, LLMResult


class ExtractionError(ValueError):
    """Raised when an LLM response cannot be parsed or validated."""


def metadata_response_format() -> dict:
    """Build a provider-enforced strict JSON Schema from DocMeta."""
    schema = DocMeta.model_json_schema()
    schema.pop("title", None)
    schema.pop("description", None)

    properties = schema["properties"]
    schema["required"] = list(properties)

    def clean_schema(value):
        if isinstance(value, dict):
            for key in (
                "title",
                "description",
                "default",
                "minimum",
                "maximum",
                "minLength",
                "maxLength",
            ):
                value.pop(key, None)

            for child in value.values():
                clean_schema(child)

        elif isinstance(value, list):
            for child in value:
                clean_schema(child)

    clean_schema(schema)

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "cycloneready_document_metadata",
            "strict": True,
            "schema": schema,
        },
    }


def build_messages(prompt: str, document_text: str) -> list[dict[str, str]]:
    """Keep document content separate from extraction instructions."""
    return [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": f"<document>\n{document_text.strip()}\n</document>",
        },
    ]


async def extract_metadata(
    gateway: LLMGateway,
    prompt: str,
    version: str,
    document_text: str,
) -> tuple[DocMeta, LLMResult]:
    """Extract JSON metadata and validate it against the DocMeta contract."""
    if not document_text.strip():
        raise ExtractionError("Cannot extract metadata from an empty document.")

    result = await gateway.generate(
        build_messages(prompt, document_text),
        purpose="extract",
        prompt_version=version,
        temperature=0,
        max_tokens=2000,
        response_format=metadata_response_format(),
    )

    try:
        data = json.loads(result.text)
    except json.JSONDecodeError as exc:
        raise ExtractionError("LLM returned invalid JSON.") from exc

    try:
        metadata = DocMeta.model_validate(data)
    except ValidationError as exc:
        raise ExtractionError("LLM metadata failed DocMeta validation.") from exc

    return metadata, result


def chunk_pages(
    page_texts: list[str],
    max_chars: int = 4000,
) -> list[str]:
    """Group page text into manageable chunks without losing words."""
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")

    chunks = []
    current_parts = []
    current_length = 0

    for page in page_texts:
        if not page or not page.strip():
            continue

        words = page.split()

        for word in words:
            if len(word) > max_chars:
                raise ExtractionError("A single word exceeds the maximum chunk size.")

            separator_length = 1 if current_parts else 0

            if current_length + separator_length + len(word) > max_chars:
                chunks.append(" ".join(current_parts))
                current_parts = []
                current_length = 0
                separator_length = 0

            current_parts.append(word)
            current_length += separator_length + len(word)

    if current_parts:
        chunks.append(" ".join(current_parts))

    return chunks


def merge_metadata(results: list[DocMeta]) -> DocMeta:
    """Merge metadata extracted from document chunks."""
    if not results:
        raise ExtractionError("No chunk metadata was provided.")

    years = [item.year for item in results]

    year = years[0] if years[0] is not None and all(item == years[0] for item in years) else None

    def unique_values(field: str) -> list[str]:
        values = []
        seen = set()

        for item in results:
            for value in getattr(item, field):
                normalized = value.strip()

                if normalized and normalized.casefold() not in seen:
                    seen.add(normalized.casefold())
                    values.append(normalized)

        return values

    return DocMeta(
        doc_kind=results[0].doc_kind,
        year=year,
        language=results[0].language,
        summary=results[0].summary,
        topics=unique_values("topics"),
        hazard=unique_values("hazard"),
        phase=unique_values("phase"),
        action=unique_values("action"),
        responsible=unique_values("responsible"),
        warning_stage=unique_values("warning_stage"),
    )
