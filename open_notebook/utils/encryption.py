"""
Field-level encryption for sensitive data using API keys.

This module provides encryption/decryption for API keys stored in the database.
Fernet uses AES-128-CBC with HMAC-SHA256 for authenticated encryption.

OPEN_NOTEBOOK_ENCRYPTION_KEY accepts **any string**. A Fernet key is derived
from it via SHA-256, so users can set a simple passphrase like
``OPEN_NOTEBOOK_ENCRYPTION_KEY=my-secret`` and it will work.

Usage:
    # Encrypt before storing
    encrypted = encrypt_value(api_key)

    # Decrypt when reading
    decrypted = decrypt_value(encrypted)
"""

import base64
import hashlib
import os
from pathlib import Path
from typing import List, Optional

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from loguru import logger


def get_secret_from_env(var_name: str) -> Optional[str]:
    """
    Get a secret from environment, supporting Docker secrets pattern.

    Checks for VAR_FILE first (Docker secrets), then falls back to VAR.

    Args:
        var_name: Base name of the environment variable (e.g., "OPEN_NOTEBOOK_ENCRYPTION_KEY")

    Returns:
        The secret value, or None if not configured.
    """
    # Check for _FILE variant first (Docker secrets)
    file_path = os.environ.get(f"{var_name}_FILE")
    if file_path:
        try:
            path = Path(file_path)
            if path.exists() and path.is_file():
                secret = path.read_text().strip()
                if secret:
                    logger.debug(f"Loaded {var_name} from file: {file_path}")
                    return secret
                else:
                    logger.warning(f"{var_name}_FILE points to empty file: {file_path}")
            else:
                logger.warning(f"{var_name}_FILE path does not exist: {file_path}")
        except Exception as e:
            logger.error(f"Failed to read {var_name} from file {file_path}: {e}")

    # Fall back to direct environment variable
    return os.environ.get(var_name)


def _get_encryption_keys_from_env() -> list[str]:
    """
    Return all configured encryption-key strings, primary first.

    v0.7.17 — added rotation support. Priority order:

    1. ``OPEN_NOTEBOOK_ENCRYPTION_KEYS`` (plural) — comma-separated list.
       First entry is the *primary* (used for all new encryption);
       remaining entries are accepted for decryption only. Use this
       during a rotation: add the new key first, leave the old one
       second, run a re-encrypt sweep, then drop the old key.
    2. ``OPEN_NOTEBOOK_ENCRYPTION_KEY`` (singular) — single key, the
       pre-rotation default. Still honored for backward compatibility.
    3. Both Docker-secrets ``_FILE`` variants are honored at each step.

    Returns:
        List of non-empty key strings; primary is index 0.

    Raises:
        ValueError: If no key is configured at all.
    """
    # Plural takes precedence — comma-separated list.
    multi = get_secret_from_env("OPEN_NOTEBOOK_ENCRYPTION_KEYS")
    if multi:
        keys = [k.strip() for k in multi.split(",")]
        keys = [k for k in keys if k]
        if keys:
            return keys

    single = get_secret_from_env("OPEN_NOTEBOOK_ENCRYPTION_KEY")
    if single:
        return [single]

    raise ValueError(
        "Neither OPEN_NOTEBOOK_ENCRYPTION_KEYS (plural) nor "
        "OPEN_NOTEBOOK_ENCRYPTION_KEY (singular) is set. "
        "Set OPEN_NOTEBOOK_ENCRYPTION_KEY=<secret-string> to enable "
        "encrypted storage, or OPEN_NOTEBOOK_ENCRYPTION_KEYS=<new>,<old> "
        "to rotate without losing existing credentials."
    )


# Back-compat shim: older code paths might still import this.
def _get_or_create_encryption_key() -> str:
    """Return the *primary* encryption key (first entry).

    Kept as a thin compatibility wrapper around the new
    `_get_encryption_keys_from_env()`. Returns just the primary so any
    pre-v0.7.17 caller that only needs one key sees the new key.
    """
    return _get_encryption_keys_from_env()[0]


# Lazy-loaded key list: initialized on first use, not at import time.
# Avoids crashing other modules at import if the key isn't yet set.
_ENCRYPTION_KEYS: Optional[list[str]] = None


def _get_encryption_keys() -> list[str]:
    """Get the list of encryption keys (primary first).

    v0.7.24 — no caching. Previously this was a process-lifetime
    singleton, which masked a real rotation bug: under uvicorn
    --reload (or any in-place env refresh), updating
    OPEN_NOTEBOOK_ENCRYPTION_KEYS appeared to take effect but the
    module retained the stale cached list, so every encrypt_value
    call used the old key. Plus across the API + worker processes
    the caches could diverge during a rolling rotation, producing
    ciphertexts neither process could later decrypt.

    Fernet construction is microseconds — caching saves nothing
    meaningful. Reading env vars per call is the correct behavior
    so rotation is always visible to live processes.
    """
    return _get_encryption_keys_from_env()


def _reset_encryption_cache() -> None:
    """Clear the cached key list. Test-only — production code never
    needs this; the keys are read once per process at first use."""
    global _ENCRYPTION_KEYS
    _ENCRYPTION_KEYS = None


def _get_encryption_key() -> str:
    """Back-compat: return primary key only. Most call sites should use
    `_get_encryption_keys()` to benefit from rotation."""
    return _get_encryption_keys()[0]


def _ensure_fernet_key(key: str) -> str:
    """
    Derive a valid Fernet key from an arbitrary string via SHA-256.

    Any string is accepted as input. The key is derived by hashing it with
    SHA-256 and encoding the result as URL-safe base64.
    """
    derived = hashlib.sha256(key.encode()).digest()
    return base64.urlsafe_b64encode(derived).decode()


def get_fernet() -> Fernet:
    """
    Get Fernet instance with the *primary* encryption key.

    Used for new encryption only; for decryption use `get_multi_fernet()`
    so rotation works.

    Raises:
        ValueError: If encryption key is not configured.
    """
    return Fernet(_ensure_fernet_key(_get_encryption_key()).encode())


def get_multi_fernet() -> MultiFernet:
    """
    Get a MultiFernet wrapping ALL configured keys (primary first).

    cryptography's MultiFernet:
      - encrypts with the FIRST key only (the active key)
      - decrypts by trying each key in order until one works

    This is the right primitive for rotation: declare the new key first,
    the old key second, and existing data remains decryptable until you
    sweep + drop the old key.

    Raises:
        ValueError: If no encryption key is configured.
    """
    keys = _get_encryption_keys()
    fernets = [Fernet(_ensure_fernet_key(k).encode()) for k in keys]
    return MultiFernet(fernets)


def encrypt_value(value: str) -> str:
    """
    Encrypt a string value using the primary encryption key.

    When multiple keys are configured (rotation in progress), new
    encryptions always use the first key. Old data encrypted with the
    secondary keys remains decryptable via `decrypt_value`.

    Args:
        value: The plain text string to encrypt.

    Returns:
        Base64-encoded encrypted string.

    Raises:
        ValueError: If encryption is not configured.
    """
    return get_multi_fernet().encrypt(value.encode()).decode()


def re_encrypt_value(value: str) -> str:
    """
    Decrypt with any configured key, then re-encrypt with the primary key.

    Used during rotation: walk the credentials table, call
    `re_encrypt_value` on each stored ciphertext, save it back. Once
    everything is re-encrypted with the new primary key, drop the old
    key from `OPEN_NOTEBOOK_ENCRYPTION_KEYS`.

    Args:
        value: The encrypted string to rotate.

    Returns:
        Ciphertext encrypted with the primary key. If the input was a
        legacy plaintext value (failed the `looks_like_fernet_token`
        sniff), it is encrypted as-is rather than re-encrypted.

    Raises:
        ValueError: If decryption fails under every configured key.
    """
    mf = get_multi_fernet()
    try:
        plaintext = mf.decrypt(value.encode())
    except InvalidToken:
        if looks_like_fernet_token(value):
            raise ValueError(
                "Re-encrypt failed: value looks like a Fernet token but no "
                "configured key can decrypt it. Are all old keys still "
                "listed in OPEN_NOTEBOOK_ENCRYPTION_KEYS?"
            )
        # Legacy plaintext — just encrypt it under the primary key.
        return mf.encrypt(value.encode()).decode()
    return mf.encrypt(plaintext).decode()


def looks_like_fernet_token(s: str) -> bool:
    """
    Check if string looks like a Fernet encrypted token.

    Fernet tokens (per spec) are:
      version(1=0x80) + timestamp(8) + IV(16) + ciphertext(>=16, multiple of
      16 with PKCS7 padding) + HMAC(32)
    Minimum decoded size is 73 bytes (1+8+16+16+32) for the smallest payload.

    v0.6.15 — also check the version byte (0x80). Without this guard, any
    random 100+ char base64-decodable string with the right block alignment
    passed the test, which:
      - made decrypt_value raise "data appears to be encrypted but key is
        incorrect" for what was actually plaintext that happened to look
        right — confusing error message
      - in edge cases could mask a legitimate decryption failure
    Random data has a 1/256 chance of starting with 0x80, so this cuts the
    false-positive rate to <1% even before the other structural checks.
    """
    if len(s) < 100:  # Base64 of 73 bytes = ~100 chars minimum
        return False
    try:
        decoded = base64.urlsafe_b64decode(s)
        if len(decoded) < 73:
            return False
        # Fernet's first byte is always the version marker 0x80.
        if decoded[0] != 0x80:
            return False
        ciphertext_len = len(decoded) - 1 - 8 - 16 - 32
        return ciphertext_len > 0 and ciphertext_len % 16 == 0
    except Exception:
        return False


def decrypt_value(value: str) -> str:
    """
    Decrypt a Fernet-encrypted string value.

    Handles graceful fallback for legacy unencrypted data.

    Args:
        value: The encrypted string (or plain text for legacy data).

    Returns:
        Decrypted plain text string, or original value if not encrypted.

    Raises:
        ValueError: If encryption is not configured or if decryption fails
            for what appears to be encrypted data (wrong key).
    """
    # v0.7.17 — use MultiFernet so rotation works. MultiFernet tries each
    # configured key in order until one succeeds, then raises InvalidToken
    # only if none did.
    mf = get_multi_fernet()

    try:
        return mf.decrypt(value.encode()).decode()
    except InvalidToken:
        if looks_like_fernet_token(value):
            # Looks like encrypted data but no configured key can decrypt
            # it — either wrong key, key rotated without re-encrypt, or
            # the old key was dropped from OPEN_NOTEBOOK_ENCRYPTION_KEYS
            # before the data was re-encrypted.
            raise ValueError(
                "Decryption failed: data appears to be encrypted but no "
                "configured key can decrypt it. If you recently rotated "
                "keys, ensure the OLD key is still in "
                "OPEN_NOTEBOOK_ENCRYPTION_KEYS until you've run the "
                "re-encrypt sweep."
            )
        # Not a valid token - treat as legacy plaintext
        return value
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise ValueError(f"Decryption failed: {str(e)}")
