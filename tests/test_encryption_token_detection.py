"""ONP v0.6.15 — Tests for looks_like_fernet_token.

The pre-v0.6.15 implementation classified any 100+ char base64-decodable
string with the right block alignment as a "Fernet token". This caused two
problems:
  1. Plaintext that happened to look right triggered decrypt_value's
     "appears to be encrypted but key is incorrect" error path — a confusing
     UX for users with legacy plaintext API keys.
  2. Defense-in-depth: in edge cases a buggy caller could pass binary data
     that fooled the detector.

The fix adds a check for Fernet's mandatory version byte (0x80). These
tests prove that:
  - Real Fernet tokens still get classified as such.
  - Random base64 strings (no version byte) do NOT.
  - The 1/256 random-collision case is the worst case (random byte == 0x80
    is needed for a false positive).
"""

from __future__ import annotations

import base64

from deeper_notebook.utils.encryption import (
    _ensure_fernet_key,
    encrypt_value,
    looks_like_fernet_token,
)


def _set_key(monkeypatch, key="test-key"):
    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KEY", key)
    # Reset the lazy-init cache between tests
    from deeper_notebook.utils import encryption

    encryption._ENCRYPTION_KEY = None


def test_real_fernet_token_is_recognized(monkeypatch):
    _set_key(monkeypatch)
    token = encrypt_value("hello world")
    assert looks_like_fernet_token(token) is True


def test_real_fernet_token_of_long_value(monkeypatch):
    """Long plaintext (multiple AES blocks) still parses as a token."""
    _set_key(monkeypatch)
    token = encrypt_value("x" * 500)
    assert looks_like_fernet_token(token) is True


def test_random_base64_without_version_byte_is_rejected():
    """The pre-fix bug: 73+ byte base64-decodable blob with the right block
    structure used to be FALSELY classified as Fernet. Now caught by the
    version-byte check."""
    # 73 bytes, first byte 0x00 (NOT the Fernet version 0x80).
    # Structure: 1 version + 8 ts + 16 IV + 16 ciphertext + 32 HMAC = 73
    fake = bytes([0x00] + [0x00] * 8 + [0x00] * 16 + [0x00] * 16 + [0x00] * 32)
    encoded = base64.urlsafe_b64encode(fake).decode()
    assert len(encoded) >= 100  # would have passed the length check
    assert looks_like_fernet_token(encoded) is False  # now caught


def test_random_base64_with_version_byte_but_wrong_block_size_is_rejected():
    """Even random bytes that happen to start with 0x80 still get rejected
    if the ciphertext length isn't a multiple of 16."""
    # 73 + 1 = 74 bytes → ciphertext_len = 74 - 1 - 8 - 16 - 32 = 17 (not /16)
    fake = bytes([0x80] + [0x00] * 73)
    encoded = base64.urlsafe_b64encode(fake).decode()
    assert looks_like_fernet_token(encoded) is False


def test_too_short_string_rejected():
    assert looks_like_fernet_token("short") is False
    assert looks_like_fernet_token("") is False


def test_non_base64_input_returns_false_without_raising():
    """Garbage in shouldn't crash — the function is defensive."""
    assert looks_like_fernet_token("!!! not base64 at all !!!") is False
    assert looks_like_fernet_token("x" * 200) is False  # not valid base64 alphabet


def test_plaintext_openai_key_pattern_is_not_misclassified():
    """A common legacy-data pattern: a long OpenAI-style API key. Should NOT
    be mistaken for a Fernet token — the user's existing plaintext stays
    intact, and decrypt_value's fallback returns it as-is."""
    # OpenAI keys can look like: sk-proj-<long base64ish chars>
    fake_openai = "sk-proj-" + "x" * 100
    assert looks_like_fernet_token(fake_openai) is False
