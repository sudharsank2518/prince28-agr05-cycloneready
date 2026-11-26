"""Extract and validate structured metadata from CycloneReady documents."""

import json
import re

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

    if metadata.year is not None:
        year_pattern = rf"(?<!\\d){metadata.year}(?!\\d)"
        if re.search(year_pattern, document_text) is None:
            raise ExtractionError(
                f"Extracted year {metadata.year} does not appear in the source document."
            )

    return metadata, result
