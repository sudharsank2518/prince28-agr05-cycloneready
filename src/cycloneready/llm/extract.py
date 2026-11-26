"""Extract and validate structured metadata from CycloneReady documents."""

import json

from pydantic import ValidationError

from cycloneready.llm.doc_meta import DocMeta
from cycloneready.llm.gateway import LLMGateway, LLMResult


class ExtractionError(ValueError):
    """Raised when an LLM response cannot be parsed or validated."""


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
        response_format={"type": "json_object"},
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
