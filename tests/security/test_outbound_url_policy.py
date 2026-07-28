from __future__ import annotations

import pytest

from deeper_notebook.security import outbound_url
from deeper_notebook.security.outbound_url import (
    OutboundURLPolicyError,
    normalize_outbound_url,
    validate_outbound_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:password@example.com/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://0x7f000001/",
        "http://2130706433/",
        "http://localhost/",
        "https://example.com%2f.evil.test/",
    ],
)
def test_outbound_policy_rejects_noncanonical_or_embedded_credentials(url: str) -> None:
    with pytest.raises(OutboundURLPolicyError):
        normalize_outbound_url(url)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "192.168.1.10",
        "::1",
        "fe80::1",
        "ff02::1",
    ],
)
def test_outbound_policy_rejects_private_and_special_addresses(address: str) -> None:
    assert not outbound_url.is_public_address(address)


@pytest.mark.asyncio
async def test_outbound_policy_rejects_dns_answer_with_private_address(
    monkeypatch,
) -> None:
    async def private_answer(*_args, **_kwargs):
        return ("93.184.216.34", "10.0.0.7")

    monkeypatch.setattr(outbound_url, "resolve_public_addresses", private_answer)
    with pytest.raises(OutboundURLPolicyError, match="non-public"):
        await validate_outbound_url("https://example.com/guide")


@pytest.mark.asyncio
async def test_outbound_policy_normalizes_and_resolves_a_public_url(
    monkeypatch,
) -> None:
    async def public_answer(*_args, **_kwargs):
        return ("8.8.8.8", "2001:4860:4860::8888")

    monkeypatch.setattr(outbound_url, "resolve_public_addresses", public_answer)
    checked = await validate_outbound_url("HTTPS://Example.COM:443/guide#local")

    assert checked.url == "https://example.com/guide"
    assert checked.addresses == ("8.8.8.8", "2001:4860:4860::8888")
