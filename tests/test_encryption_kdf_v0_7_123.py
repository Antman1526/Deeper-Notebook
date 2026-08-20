"""v0.7.123 — tests for the PBKDF2 KDF migration.

Verifies:
  * Default behavior (DEEPER_NOTEBOOK_ENCRYPTION_KDF unset) is unchanged from
    v0.7.0 — encrypt+decrypt round-trip works, existing sha256-derived
    keys decrypt correctly.
  * Opt-in pbkdf2 mode encrypts with a different key (more entropy)
    while still decrypting back to the same plaintext.
  * Cross-KDF compatibility via MultiFernet: data encrypted under
    sha256 still decrypts after migrating to pbkdf2, and vice versa.
  * Unknown KDF values raise a clear ValueError naming the valid
    options.
  * PBKDF2 derivation is deterministic for the same passphrase (so
    the key is reproducible across restarts).

No external dependencies, no real database — pure unit tests on the
encryption module.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_encryption_cache(monkeypatch):
    """Each test gets a fresh encryption-key cache. Required because
    the module caches the parsed keys in a module-level variable."""
    from deeper_notebook.utils import encryption as enc

    enc._reset_encryption_cache()
    yield
    enc._reset_encryption_cache()


def test_default_kdf_is_sha256_back_compat(monkeypatch):
    """v0.7.123 — When DEEPER_NOTEBOOK_ENCRYPTION_KDF is unset, the derivation
    path is the original v0.7.0 sha256. No existing user sees any
    change in behavior."""
    from deeper_notebook.utils import encryption as enc

    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KEY", "test-passphrase")
    monkeypatch.delenv("DEEPER_NOTEBOOK_ENCRYPTION_KDF", raising=False)

    assert enc._selected_kdf() == "sha256"
    # Derivation should match the v0.7.0 path
    expected = enc._derive_fernet_key_sha256("test-passphrase").decode()
    actual = enc._ensure_fernet_key("test-passphrase")
    assert actual == expected


def test_pbkdf2_mode_uses_pbkdf2_derivation(monkeypatch):
    """v0.7.123 — Setting DEEPER_NOTEBOOK_ENCRYPTION_KDF=pbkdf2 switches to the
    PBKDF2 path. The resulting Fernet key is different from sha256."""
    from deeper_notebook.utils import encryption as enc

    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KEY", "test-passphrase")
    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KDF", "pbkdf2")

    assert enc._selected_kdf() == "pbkdf2"
    sha_key = enc._derive_fernet_key_sha256("test-passphrase").decode()
    pbk_key = enc._derive_fernet_key_pbkdf2("test-passphrase").decode()
    assert sha_key != pbk_key  # different KDFs → different keys
    actual = enc._ensure_fernet_key("test-passphrase")
    assert actual == pbk_key


def test_pbkdf2_derivation_is_deterministic():
    """v0.7.123 — PBKDF2 with deterministic salt must produce the same
    key for the same passphrase across calls (otherwise the next
    process restart couldn't decrypt anything)."""
    from deeper_notebook.utils import encryption as enc

    k1 = enc._derive_fernet_key_pbkdf2("my-passphrase").decode()
    k2 = enc._derive_fernet_key_pbkdf2("my-passphrase").decode()
    assert k1 == k2

    # Different passphrases produce different keys
    k3 = enc._derive_fernet_key_pbkdf2("different-passphrase").decode()
    assert k1 != k3


def test_unknown_kdf_raises_actionable_error(monkeypatch):
    """v0.7.123 — A typo in DEEPER_NOTEBOOK_ENCRYPTION_KDF should fail fast with a
    clear error message naming the valid options."""
    from deeper_notebook.utils import encryption as enc

    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KEY", "x")
    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KDF", "argon2id-typo")

    with pytest.raises(ValueError) as exc_info:
        enc._ensure_fernet_key("x")
    err = str(exc_info.value)
    assert "sha256" in err
    assert "pbkdf2" in err
    assert "argon2id-typo" in err


def test_round_trip_under_sha256(monkeypatch):
    """v0.7.123 — Sanity: encrypt + decrypt under sha256 still works."""
    from deeper_notebook.utils import encryption as enc

    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KEY", "passphrase-A")
    monkeypatch.delenv("DEEPER_NOTEBOOK_ENCRYPTION_KDF", raising=False)

    encrypted = enc.encrypt_value("hello world")
    assert encrypted != "hello world"
    assert enc.decrypt_value(encrypted) == "hello world"


def test_round_trip_under_pbkdf2(monkeypatch):
    """v0.7.123 — Encrypt + decrypt under pbkdf2 also works."""
    from deeper_notebook.utils import encryption as enc

    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KEY", "passphrase-A")
    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KDF", "pbkdf2")

    encrypted = enc.encrypt_value("hello world")
    assert enc.decrypt_value(encrypted) == "hello world"


def test_migration_sha256_to_pbkdf2_keeps_existing_data_decryptable(
    monkeypatch,
):
    """v0.7.123 — THE migration scenario. User starts on sha256
    (default), encrypts a value, then changes DEEPER_NOTEBOOK_ENCRYPTION_KDF=pbkdf2
    and restarts. The existing sha256-encrypted data must still
    decrypt because MultiFernet tries all KDFs.

    This is the whole point of the migration design: no re-encrypt
    sweep is required for the user's data to remain accessible
    after they change the KDF env var."""
    from deeper_notebook.utils import encryption as enc

    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KEY", "shared-passphrase")

    # Stage 1: encrypt under sha256 (default)
    monkeypatch.delenv("DEEPER_NOTEBOOK_ENCRYPTION_KDF", raising=False)
    enc._reset_encryption_cache()
    old_encrypted = enc.encrypt_value("secret data from v0.7.122 era")

    # Stage 2: user sets DEEPER_NOTEBOOK_ENCRYPTION_KDF=pbkdf2 and restarts
    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KDF", "pbkdf2")
    enc._reset_encryption_cache()

    # Old data still decrypts thanks to cross-KDF MultiFernet
    assert enc.decrypt_value(old_encrypted) == "secret data from v0.7.122 era"

    # New writes go through pbkdf2
    new_encrypted = enc.encrypt_value("secret data from v0.7.123 era")
    assert enc.decrypt_value(new_encrypted) == "secret data from v0.7.123 era"

    # Old and new encrypted strings are different ciphertexts produced
    # by different Fernet keys, but the SAME MultiFernet decrypts both
    assert old_encrypted != new_encrypted


def test_migration_pbkdf2_to_sha256_also_works(monkeypatch):
    """v0.7.123 — The reverse direction (rare but supported). User
    on pbkdf2 downgrades to sha256; pbkdf2-encrypted data must still
    decrypt because the MultiFernet tries both KDFs."""
    from deeper_notebook.utils import encryption as enc

    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KEY", "shared-passphrase")

    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KDF", "pbkdf2")
    enc._reset_encryption_cache()
    pbk_encrypted = enc.encrypt_value("data encrypted under pbkdf2")

    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KDF", "sha256")
    enc._reset_encryption_cache()
    assert enc.decrypt_value(pbk_encrypted) == "data encrypted under pbkdf2"


def test_rotation_works_alongside_kdf_migration(monkeypatch):
    """v0.7.123 — The v0.7.17 rotation feature (ENCRYPTION_KEYS plural)
    still works when KDFs are mixed. User has two keys
    (new + old) AND switches KDF — MultiFernet handles the matrix."""
    from deeper_notebook.utils import encryption as enc

    # Stage 1: encrypt with OLD key + sha256
    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KEY", "old-key")
    monkeypatch.delenv("DEEPER_NOTEBOOK_ENCRYPTION_KEYS", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_ENCRYPTION_KDF", raising=False)
    enc._reset_encryption_cache()
    old_data = enc.encrypt_value("encrypted with old-key + sha256")

    # Stage 2: rotate to NEW key, migrate to pbkdf2 KDF, keep old key in plural
    monkeypatch.delenv("DEEPER_NOTEBOOK_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KEYS", "new-key,old-key")
    monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KDF", "pbkdf2")
    enc._reset_encryption_cache()

    # Old data (encrypted with old-key + sha256) still decrypts —
    # MultiFernet tries (new × pbkdf2, new × sha256, old × pbkdf2,
    # old × sha256) in that order and finds the old × sha256 entry.
    assert enc.decrypt_value(old_data) == "encrypted with old-key + sha256"

    # New encryption uses (new-key × pbkdf2)
    new_data = enc.encrypt_value("encrypted with new-key + pbkdf2")
    assert enc.decrypt_value(new_data) == "encrypted with new-key + pbkdf2"
