from __future__ import annotations

import httpx
import pytest

import deeper_notebook.research.safe_fetch as safe_fetch_mod
from deeper_notebook.research.safe_fetch import (
    MAX_BODY_BYTES,
    SafeFetcher,
    SafeFetchError,
)
from deeper_notebook.security.outbound_url import (
    OutboundURLPolicyError,
    ValidatedOutboundURL,
)


def _checked(url: str) -> ValidatedOutboundURL:
    return ValidatedOutboundURL(
        url=url, hostname="public.example", addresses=("8.8.8.8",)
    )


@pytest.mark.asyncio
async def test_safe_fetch_uses_canonical_product_user_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def validator(url: str) -> ValidatedOutboundURL:
        return _checked(url)

    observed: dict[str, object] = {}
    real_async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        observed["request_user_agent"] = request.headers["user-agent"]
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"ok",
        )

    def client_factory(**kwargs):
        observed["configured_headers"] = kwargs["headers"]
        return real_async_client(
            **kwargs,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(safe_fetch_mod.httpx, "AsyncClient", client_factory)

    await SafeFetcher(validator=validator).fetch("https://public.example/guide")

    expected = "DeeperNotebook/0.8 safe-research-fetch"
    assert observed["configured_headers"] == {"User-Agent": expected}
    assert observed["request_user_agent"] == expected


@pytest.mark.asyncio
async def test_safe_fetch_revalidates_each_redirect_hop() -> None:
    validated: list[str] = []

    async def validator(url: str) -> ValidatedOutboundURL:
        validated.append(url)
        if url.endswith("/private"):
            raise OutboundURLPolicyError("private destination")
        return _checked(url)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/private"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SafeFetchError, match="could not be fetched safely"):
            await SafeFetcher(validator=validator).fetch(
                "https://public.example/start", client=client
            )

    assert validated == [
        "https://public.example/start",
        "https://public.example/private",
    ]


@pytest.mark.asyncio
async def test_safe_fetch_rejects_oversized_streamed_response() -> None:
    async def validator(url: str) -> ValidatedOutboundURL:
        return _checked(url)

    class OversizedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * (MAX_BODY_BYTES + 1)

        async def aclose(self) -> None:
            return None

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, stream=OversizedStream()
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SafeFetchError, match="25 MB"):
            await SafeFetcher(validator=validator).fetch(
                "https://public.example/large", client=client
            )


@pytest.mark.asyncio
async def test_safe_fetch_rejects_unsupported_mime_type() -> None:
    async def validator(url: str) -> ValidatedOutboundURL:
        return _checked(url)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "image/png"}, content=b"png"
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SafeFetchError, match="MIME"):
            await SafeFetcher(validator=validator).fetch(
                "https://public.example/image", client=client
            )


@pytest.mark.asyncio
async def test_safe_fetch_accepts_a_valid_public_text_response() -> None:
    async def validator(url: str) -> ValidatedOutboundURL:
        return _checked(url)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain; charset=utf-8"},
            content=b"Public source text",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await SafeFetcher(validator=validator).fetch(
            "https://public.example/guide", client=client
        )

    assert response.text == "Public source text"
    assert response.url == "https://public.example/guide"
