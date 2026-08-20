"""Provider-neutral structured generation with a bounded JSON repair path."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Literal, Sequence

from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import ValidationError

from deeper_notebook.studio.schemas import ArtifactDocumentBase
from deeper_notebook.utils.text_utils import (
    clean_thinking_content,
    extract_text_content,
)

_MAX_REPAIR_OUTPUT_CHARS = 4_000
_MAX_ERROR_ITEMS = 12
_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


class StructuredArtifactGenerationError(Exception):
    """Raised after both the original output and one repair fail validation."""

    def __init__(self, *, errors: list[dict[str, Any]], attempts: int = 2):
        super().__init__("Artifact output did not match the required structure")
        self.errors = errors
        self.attempts = attempts


@dataclass(frozen=True)
class StructuredGenerationResult:
    document: ArtifactDocumentBase
    raw_output: str
    attempts: int
    strategy: Literal["native", "json", "json_repair"]


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    content = getattr(response, "content", response)
    return clean_thinking_content(extract_text_content(content)).strip()


def _native_raw_text(response: Any) -> str:
    if isinstance(response, dict) and "raw" in response:
        return _response_text(response["raw"])
    return _response_text(response)


def _parse_json_document(
    raw_output: str,
    schema: type[ArtifactDocumentBase],
) -> ArtifactDocumentBase:
    candidate = raw_output.strip()
    fenced = _FENCED_JSON.search(candidate)
    if fenced:
        candidate = fenced.group(1)
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("structured artifact output must be a JSON object")
    return schema.model_validate(parsed)


def _validation_receipt(exc: Exception) -> list[dict[str, Any]]:
    if isinstance(exc, ValidationError):
        return [
            {
                "type": str(error.get("type", "validation_error"))[:120],
                "location": [str(part)[:120] for part in error.get("loc", ())],
                "message": str(error.get("msg", "Invalid value"))[:240],
            }
            for error in exc.errors(include_url=False)[:_MAX_ERROR_ITEMS]
        ]
    if isinstance(exc, json.JSONDecodeError):
        return [
            {
                "type": "json_invalid",
                "location": [],
                "message": "Response was not valid JSON",
            }
        ]
    return [
        {
            "type": "structure_invalid",
            "location": [],
            "message": "Response did not contain the required JSON object",
        }
    ]


def _schema_prompt(schema: type[ArtifactDocumentBase]) -> str:
    encoded_schema = json.dumps(
        schema.model_json_schema(),
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return (
        "Return exactly one JSON object and no commentary or Markdown fences. "
        "The object must validate against this JSON Schema:\n"
        f"{encoded_schema}"
    )


def _repair_prompt(
    *,
    schema: type[ArtifactDocumentBase],
    raw_output: str,
    error: Exception,
) -> str:
    bounded_output = raw_output[:_MAX_REPAIR_OUTPUT_CHARS]
    receipt = json.dumps(_validation_receipt(error), ensure_ascii=True)
    return (
        "Repair the invalid JSON below. Return exactly one corrected JSON object "
        "with no commentary or Markdown fences.\n\n"
        f"Validation errors:\n{receipt}\n\n"
        f"Invalid output (truncated if necessary):\n{bounded_output}\n\n"
        f"Required JSON Schema:\n{json.dumps(schema.model_json_schema(), ensure_ascii=True)}"
    )


async def _generate_json_with_repair(
    *,
    model: Any,
    schema: type[ArtifactDocumentBase],
    messages: Sequence[BaseMessage],
    timeout_seconds: float,
) -> StructuredGenerationResult:
    first_messages = [*messages, HumanMessage(content=_schema_prompt(schema))]
    response = await asyncio.wait_for(
        model.ainvoke(first_messages), timeout=timeout_seconds
    )
    raw_output = _response_text(response)
    try:
        document = _parse_json_document(raw_output, schema)
    except (
        json.JSONDecodeError,
        TypeError,
        ValueError,
        ValidationError,
    ) as first_error:
        repair_messages = [
            *messages,
            HumanMessage(
                content=_repair_prompt(
                    schema=schema,
                    raw_output=raw_output,
                    error=first_error,
                )
            ),
        ]
        repaired_response = await asyncio.wait_for(
            model.ainvoke(repair_messages), timeout=timeout_seconds
        )
        repaired_output = _response_text(repaired_response)
        try:
            document = _parse_json_document(repaired_output, schema)
        except (
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ValidationError,
        ) as repair_error:
            raise StructuredArtifactGenerationError(
                errors=_validation_receipt(repair_error),
                attempts=2,
            ) from repair_error
        return StructuredGenerationResult(
            document=document,
            raw_output=repaired_output,
            attempts=2,
            strategy="json_repair",
        )

    return StructuredGenerationResult(
        document=document,
        raw_output=raw_output,
        attempts=1,
        strategy="json",
    )


async def generate_structured_document(
    *,
    model: Any,
    schema: type[ArtifactDocumentBase],
    messages: Sequence[BaseMessage],
    timeout_seconds: float,
) -> StructuredGenerationResult:
    """Generate and validate a typed document with at most one repair call."""
    native = getattr(model, "with_structured_output", None)
    if callable(native):
        try:
            structured_model = native(schema, include_raw=True)
            response = await asyncio.wait_for(
                structured_model.ainvoke(messages), timeout=timeout_seconds
            )
            parsed = response.get("parsed") if isinstance(response, dict) else response
            if parsed is not None:
                document = (
                    parsed
                    if isinstance(parsed, schema)
                    else schema.model_validate(parsed)
                )
                return StructuredGenerationResult(
                    document=document,
                    raw_output=_native_raw_text(response),
                    attempts=1,
                    strategy="native",
                )
        except (NotImplementedError, TypeError, ValueError, ValidationError):
            pass

    return await _generate_json_with_repair(
        model=model,
        schema=schema,
        messages=messages,
        timeout_seconds=timeout_seconds,
    )
