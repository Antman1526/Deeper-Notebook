import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from deeper_notebook.studio.schemas import FlashcardsDocument
from deeper_notebook.studio.structured_generation import (
    StructuredArtifactGenerationError,
    generate_structured_document,
)

FLASHCARD_DOCUMENT = {
    "schema_version": 1,
    "artifact_type": "flashcards",
    "title": "RAG review",
    "cards": [
        {
            "front": "What is retrieval?",
            "back": "Finding relevant passages.",
            "citations": ["[S1]"],
        }
    ],
}


class NativeStructuredModel:
    def __init__(self, response):
        self.response = response
        self.structured_calls = []
        self.plain_invocations = 0

    def with_structured_output(self, schema, *, include_raw):
        self.structured_calls.append((schema, include_raw))
        parent = self

        class StructuredInvoker:
            async def ainvoke(self, messages):
                return {
                    "parsed": parent.response,
                    "raw": AIMessage(content=json.dumps(FLASHCARD_DOCUMENT)),
                }

        return StructuredInvoker()

    async def ainvoke(self, messages):
        self.plain_invocations += 1
        raise AssertionError("plain generation should not be used")


class PlainJsonModel:
    def __init__(self, responses, *, native_error=NotImplementedError):
        self.responses = list(responses)
        self.native_error = native_error
        self.calls = []

    def with_structured_output(self, schema, *, include_raw):
        raise self.native_error("structured output is unavailable")

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=self.responses.pop(0))


@pytest.mark.asyncio
async def test_native_structured_output_is_preferred():
    model = NativeStructuredModel(FLASHCARD_DOCUMENT)

    result = await generate_structured_document(
        model=model,
        schema=FlashcardsDocument,
        messages=[HumanMessage(content="Build cards")],
        timeout_seconds=5,
    )

    assert result.document.artifact_type == "flashcards"
    assert result.attempts == 1
    assert result.strategy == "native"
    assert model.plain_invocations == 0
    assert model.structured_calls == [(FlashcardsDocument, True)]


@pytest.mark.asyncio
async def test_unsupported_native_output_falls_back_to_json_schema_prompt():
    model = PlainJsonModel([json.dumps(FLASHCARD_DOCUMENT)])

    result = await generate_structured_document(
        model=model,
        schema=FlashcardsDocument,
        messages=[HumanMessage(content="Build cards")],
        timeout_seconds=5,
    )

    assert result.strategy == "json"
    assert result.attempts == 1
    assert len(model.calls) == 1
    fallback_prompt = model.calls[0][-1].content
    assert "Return exactly one JSON object" in fallback_prompt
    assert '"artifact_type"' in fallback_prompt
    assert '"flashcards"' in fallback_prompt


@pytest.mark.asyncio
async def test_fenced_json_is_accepted():
    model = PlainJsonModel([f"```json\n{json.dumps(FLASHCARD_DOCUMENT)}\n```"])

    result = await generate_structured_document(
        model=model,
        schema=FlashcardsDocument,
        messages=[HumanMessage(content="Build cards")],
        timeout_seconds=5,
    )

    assert result.document.title == "RAG review"
    assert result.strategy == "json"


@pytest.mark.asyncio
async def test_invalid_json_gets_exactly_one_repair_attempt():
    model = PlainJsonModel(["not json", json.dumps(FLASHCARD_DOCUMENT)])

    result = await generate_structured_document(
        model=model,
        schema=FlashcardsDocument,
        messages=[HumanMessage(content="Build cards")],
        timeout_seconds=5,
    )

    assert result.strategy == "json_repair"
    assert result.attempts == 2
    assert len(model.calls) == 2
    repair_prompt = model.calls[1][-1].content
    assert "Repair the invalid JSON" in repair_prompt
    assert "not json" in repair_prompt


@pytest.mark.asyncio
async def test_schema_validation_failure_can_be_repaired_once():
    invalid = {**FLASHCARD_DOCUMENT, "cards": [{"front": "Missing back"}]}
    model = PlainJsonModel([json.dumps(invalid), json.dumps(FLASHCARD_DOCUMENT)])

    result = await generate_structured_document(
        model=model,
        schema=FlashcardsDocument,
        messages=[HumanMessage(content="Build cards")],
        timeout_seconds=5,
    )

    assert result.attempts == 2
    assert "cards" in model.calls[1][-1].content
    assert "back" in model.calls[1][-1].content


@pytest.mark.asyncio
async def test_second_invalid_response_raises_bounded_failure_receipt():
    secret_source = "PRIVATE SOURCE " + ("x" * 12_000)
    model = PlainJsonModel([secret_source, "still not json"])

    with pytest.raises(StructuredArtifactGenerationError) as exc_info:
        await generate_structured_document(
            model=model,
            schema=FlashcardsDocument,
            messages=[HumanMessage(content="Build cards")],
            timeout_seconds=5,
        )

    error = exc_info.value
    assert error.attempts == 2
    assert len(model.calls) == 2
    assert error.errors
    assert len(json.dumps(error.errors)) < 2_000
    assert "PRIVATE SOURCE" not in json.dumps(error.errors)


@pytest.mark.asyncio
async def test_native_validation_error_uses_plain_fallback():
    model = NativeStructuredModel({"artifact_type": "flashcards", "title": "Bad"})
    model.responses = [json.dumps(FLASHCARD_DOCUMENT)]

    async def plain_ainvoke(messages):
        model.plain_invocations += 1
        return AIMessage(content=model.responses.pop(0))

    model.ainvoke = plain_ainvoke

    result = await generate_structured_document(
        model=model,
        schema=FlashcardsDocument,
        messages=[HumanMessage(content="Build cards")],
        timeout_seconds=5,
    )

    assert result.strategy == "json"
    assert model.plain_invocations == 1
