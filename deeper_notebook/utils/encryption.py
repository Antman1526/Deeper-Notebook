"""
Field-level encryption for sensitive data using API keys.

This module provides encryption/decryption for API keys stored in the database.
Fernet uses AES-128-CBC with HMAC-SHA256 for authenticated encryption.

DEEPER_NOTEBOOK_ENCRYPTION_KEY accepts **any string**. A Fernet key is derived
from it via SHA-256, so users can set a simple passphrase like
``DEEPER_NOTEBOOK_ENCRYPTION_KEY=my-secret`` and it will work.

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

from deeper_notebook.environment import resolve_env


def get_secret_from_env(var_name: str) -> Optional[str]:
    """
    Get a secret from environment, supporting Docker secrets pattern.

    Checks for VAR_FILE first (Docker secrets), then falls back to VAR.

    Args:
        var_name: Base name of the environment variable (e.g., "DEEPER_NOTEBOOK_ENCRYPTION_KEY")

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

    1. ``DEEPER_NOTEBOOK_ENCRYPTION_KEYS`` (plural) — comma-separated list.
       First entry is the *primary* (used for all new encryption);
       remaining entries are accepted for decryption only. Use this
       during a rotation: add the new key first, leave the old one
       second, run a re-encrypt sweep, then drop the old key.
    2. ``DEEPER_NOTEBOOK_ENCRYPTION_KEY`` (singular) — single key, the
       pre-rotation default. Still honored for backward compatibility.
    3. Both Docker-secrets ``_FILE`` variants are honored at each step.

    Returns:
        List of non-empty key strings; primary is index 0.

    Raises:
        ValueError: If no key is configured at all.
    """
    # Plural takes precedence — comma-separated list.
    multi = resolve_env("DEEPER_NOTEBOOK_ENCRYPTION_KEYS", getter=get_secret_from_env)
    if multi:
        keys = [k.strip() for k in multi.split(",")]
        keys = [k for k in keys if k]
        if keys:
            return keys

    single = resolve_env("DEEPER_NOTEBOOK_ENCRYPTION_KEY", getter=get_secret_from_env)
    if single:
        return [single]

    raise ValueError(
        "Neither DEEPER_NOTEBOOK_ENCRYPTION_KEYS (plural) nor "
        "DEEPER_NOTEBOOK_ENCRYPTION_KEY (singular) is set. "
        "Set DEEPER_NOTEBOOK_ENCRYPTION_KEY=<secret-string> to enable "
        "encrypted storage, or DEEPER_NOTEBOOK_ENCRYPTION_KEYS=<new>,<old> "
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
    DEEPER_NOTEBOOK_ENCRYPTION_KEYS appeared to take effect but the
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


# v0.7.123 — Key Derivation Function selection.
#
# Original (v0.7.0): SHA-256(passphrase) — instant to compute, instant
# to brute-force if the encrypted data leaks. Acceptable threat model
# for a self-hosted desktop app where the user IS the attacker (they
# already have the data) but not great if the database file ever
# leaves the machine.
#
# v0.7.123 adds PBKDF2-HMAC-SHA256 (stdlib, no new dep) as an opt-in
# upgrade via `DEEPER_NOTEBOOK_ENCRYPTION_KDF=pbkdf2`. 600,000 iterations gives
# ~250ms cost per guess on a modern CPU — slows offline brute-force
# of a stolen database from "instant" to "~one year per million
# guesses". Backward compatible: decryption tries BOTH KDFs in order,
# so existing sha256-encrypted data keeps working when the user
# migrates. New encryptions use whichever KDF the env knob selects.

_KDF_PBKDF2_ITERATIONS = 600_000  # OWASP 2024 recommendation
_KDF_SALT_VERSION = "onp-kdf-salt-v1"


def _derive_kdf_salt(key: str) -> bytes:
    """Derive a deterministic 16-byte salt from the passphrase + a
    version-tagged constant. Same passphrase → same salt → same key.
    Required for decryption to work without storing a per-key salt
    blob. The version tag (`onp-kdf-salt-v1`) means we can rotate
    the salting scheme in the future without breaking existing data
    (decrypt path would try both salts).
    """
    seed = (key + "\0" + _KDF_SALT_VERSION).encode()
    return hashlib.sha256(seed).digest()[:16]


def _derive_fernet_key_sha256(key: str) -> bytes:
    """v0.7.0 derivation. Kept for backward compatibility — existing
    encrypted data was produced by this path."""
    derived = hashlib.sha256(key.encode()).digest()
    return base64.urlsafe_b64encode(derived)


def _derive_fernet_key_pbkdf2(
    key: str,
    iterations: int = _KDF_PBKDF2_ITERATIONS,
) -> bytes:
    """v0.7.123 — PBKDF2-HMAC-SHA256 with 600k iterations.
    ~250ms per guess on modern hardware. Deterministic salt derived
    from the passphrase keeps the derivation reproducible without
    needing a separate salt-storage mechanism."""
    salt = _derive_kdf_salt(key)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        key.encode(),
        salt,
        iterations,
        dklen=32,
    )
    return base64.urlsafe_b64encode(derived)


def _selected_kdf() -> str:
    """Read the configured KDF from env. Defaults to 'sha256' for
    backward compatibility — existing deployments see no change."""
    return (
        resolve_env("DEEPER_NOTEBOOK_ENCRYPTION_KDF", "sha256").strip().lower()
        or "sha256"
    )


# Order in which to try KDFs during decryption. Listed in PREFERENCE
# order — newest/strongest first so encryption uses the right one.
# MultiFernet's first match wins; failed decryption attempts cost
# only a fast hash + base64, not a full PBKDF2 round.
_KDF_DECRYPT_ORDER = ("pbkdf2", "sha256")


def _ensure_fernet_key(key: str, kdf: str | None = None) -> str:
    """Derive a 32-byte Fernet key from an arbitrary passphrase.

    `kdf` selects the derivation function:
      * "sha256" (default, v0.7.0): fast hash, no work factor
      * "pbkdf2" (v0.7.123):        slow KDF, 600k iterations

    When `kdf` is None, the env-configured value is used.
    """
    kdf = (kdf or _selected_kdf()).lower()
    if kdf == "pbkdf2":
        return _derive_fernet_key_pbkdf2(key).decode()
    if kdf == "sha256":
        return _derive_fernet_key_sha256(key).decode()
    raise ValueError(
        f"Unknown DEEPER_NOTEBOOK_ENCRYPTION_KDF: {kdf!r}. "
        "Valid values: 'sha256' (default, fast) or 'pbkdf2' (recommended, slow)."
    )


def get_fernet() -> Fernet:
    """
    Get Fernet instance with the *primary* encryption key.

    Used for new encryption only; for decryption use `get_multi_fernet()`
    so rotation + cross-KDF compatibility works.

    v0.7.123 — uses the env-configured KDF (`DEEPER_NOTEBOOK_ENCRYPTION_KDF`).

    Raises:
        ValueError: If encryption key is not configured.
    """
    return Fernet(_ensure_fernet_key(_get_encryption_key()).encode())


def get_multi_fernet() -> MultiFernet:
    """
    Get a MultiFernet wrapping all configured keys × all known KDFs.

    cryptography's MultiFernet:
      - encrypts with the FIRST Fernet instance only (the active key)
      - decrypts by trying each Fernet in order until one succeeds

    v0.7.123 — Order:
      [primary_key × selected_kdf,
       primary_key × other_kdfs,
       secondary_key × selected_kdf,
       secondary_key × other_kdfs,
       ...]

    This means:
      * New encryption uses the env-selected KDF on the primary key.
      * Decryption tries the active path first (fast), then falls
        back to each older KDF (slightly slower per failure but still
        well under 1 second for a single decrypt). Existing
        sha256-encrypted data is decryptable after migration to
        pbkdf2; existing pbkdf2 data decrypts after downgrade to
        sha256 (rare but supported).
      * The familiar v0.7.17 ENCRYPTION_KEYS rotation still works —
        each key gets its full set of KDFs tried.

    Raises:
        ValueError: If no encryption key is configured.
    """
    keys = _get_encryption_keys()
    selected = _selected_kdf()
    # Build the KDF iteration order: selected first, then the others.
    kdf_order = (selected,) + tuple(k for k in _KDF_DECRYPT_ORDER if k != selected)
    fernets = []
    for k in keys:
        for kdf in kdf_order:
            fernets.append(Fernet(_ensure_fernet_key(k, kdf).encode()))
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
    key from `DEEPER_NOTEBOOK_ENCRYPTION_KEYS`.

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
                "listed in DEEPER_NOTEBOOK_ENCRYPTION_KEYS?"
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
            # the old key was dropped from DEEPER_NOTEBOOK_ENCRYPTION_KEYS
            # before the data was re-encrypted.
            raise ValueError(
                "Decryption failed: data appears to be encrypted but no "
                "configured key can decrypt it. If you recently rotated "
                "keys, ensure the OLD key is still in "
                "DEEPER_NOTEBOOK_ENCRYPTION_KEYS until you've run the "
                "re-encrypt sweep."
            )
        # Not a valid token - treat as legacy plaintext
        return value
    except Exception as e:
        # v0.8.66 (audit S-5) — log the detail for the operator, but do NOT
        # embed `str(e)` in the raised ValueError: it propagates into API
        # responses (credentials read paths) and can leak Fernet/cryptography
        # internals or input fragments. Mirrors the v0.7.201 /readyz sanitization.
        logger.error(f"Decryption failed: {e}")
        raise ValueError("Decryption failed due to an internal error. See server logs.")
