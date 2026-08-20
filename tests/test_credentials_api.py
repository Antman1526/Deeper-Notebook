"""Tests for the credentials API endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client after environment variables have been cleared by conftest."""
    from api.main import app

    return TestClient(app)


class TestCredentialCascadeDelete:
    """Tests for #651 - deleting credential cascade-deletes linked models."""

    @pytest.mark.asyncio
    @patch("api.routers.credentials.Credential.get")
    async def test_cascade_delete_linked_models(self, mock_get, client):
        """Deleting credential without options cascade-deletes linked models."""
        mock_model1 = AsyncMock()
        mock_model1.id = "model:1"
        mock_model1.provider = "openai"
        mock_model1.name = "gpt-4"

        mock_model2 = AsyncMock()
        mock_model2.id = "model:2"
        mock_model2.provider = "openai"
        mock_model2.name = "gpt-3.5-turbo"

        mock_cred = AsyncMock()
        mock_cred.get_linked_models = AsyncMock(return_value=[mock_model1, mock_model2])
        mock_cred.delete = AsyncMock()
        mock_get.return_value = mock_cred

        response = client.delete("/api/credentials/cred:123")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_models"] == 2
        assert data["message"] == "Credential deleted successfully"

        mock_model1.delete.assert_awaited_once()
        mock_model2.delete.assert_awaited_once()
        mock_cred.delete.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("api.routers.credentials.Credential.get")
    async def test_delete_credential_no_linked_models(self, mock_get, client):
        """Deleting credential with no linked models works cleanly."""
        mock_cred = AsyncMock()
        mock_cred.get_linked_models = AsyncMock(return_value=[])
        mock_cred.delete = AsyncMock()
        mock_get.return_value = mock_cred

        response = client.delete("/api/credentials/cred:123")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_models"] == 0
        mock_cred.delete.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("api.routers.credentials.Credential.get")
    async def test_migrate_models_instead_of_delete(self, mock_get, client):
        """Passing migrate_to reassigns models instead of deleting them."""
        mock_model = AsyncMock()
        mock_model.id = "model:1"
        mock_model.credential = "cred:123"
        mock_model.save = AsyncMock()

        mock_cred = AsyncMock()
        mock_cred.get_linked_models = AsyncMock(return_value=[mock_model])
        mock_cred.delete = AsyncMock()

        mock_target_cred = AsyncMock()
        mock_target_cred.id = "cred:456"

        # First call returns cred to delete, second returns target
        mock_get.side_effect = [mock_cred, mock_target_cred]

        response = client.delete("/api/credentials/cred:123?migrate_to=cred:456")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_models"] == 0  # Models were migrated, not deleted
        mock_model.save.assert_awaited_once()
        assert mock_model.credential == "cred:456"
        mock_cred.delete.assert_awaited_once()


class TestV0822MigrationSanitization:
    """v0.8.22 — migration endpoints must NOT echo raw exception strings
    into the response payload. Same family as the v0.7.177 podcast
    sanitization sweep, which missed credentials_service.py.
    """

    @pytest.mark.asyncio
    @patch("api.credentials_service.create_credential_from_env")
    @patch("api.credentials_service.check_env_configured")
    @patch("api.credentials_service.Credential.get_by_provider")
    @patch("api.credentials_service.require_encryption_key")
    async def test_migrate_from_env_sanitizes_exception_in_response(
        self,
        mock_require,
        mock_get_by_provider,
        mock_check_env,
        mock_create_cred,
        client,
    ):
        """Force migrate_from_env into the except branch and assert the
        response's `errors[]` carries only the exception TYPE NAME — not
        the raw message. Real exception messages here can carry SurrealDB
        WS frames, Fernet base64 fragments, or api_key prefixes."""
        # All providers report no existing credential — proceed to create.
        mock_get_by_provider.return_value = []
        # All providers detected as configured — forces the migration path.
        mock_check_env.return_value = True
        # The "sensitive" exception message we will assert does NOT leak.
        secret_in_exception = (
            "INTERNAL: api_key=sk-VERYSECRET345; "
            "SurrealDB pool WS frame=0x4F2C; "
            "encrypted=gAAAAABnoEOFw"
        )
        mock_create_cred.side_effect = RuntimeError(secret_in_exception)

        response = client.post("/api/credentials/migrate-from-env")

        assert response.status_code == 200, response.text
        body = response.json()
        # At least one provider's migration hit the except branch.
        assert len(body["errors"]) > 0, (
            "Expected at least one error entry; "
            "got migrated/skipped only — the mock injection didn't fire."
        )
        # The CRITICAL assertion: no error entry contains the raw message.
        for err in body["errors"]:
            assert "sk-VERYSECRET345" not in err, (
                f"api_key leaked into response error string: {err!r}. "
                f"v0.8.22 fix: emit type(e).__name__, not str(e)."
            )
            assert "WS frame" not in err, (
                f"SurrealDB internal leaked into response: {err!r}."
            )
            assert "gAAAAABnoEOFw" not in err, (
                f"Fernet ciphertext fragment leaked: {err!r}."
            )
            # And the type name MUST be present so operators can triage.
            assert "RuntimeError" in err, (
                f"Expected the exception type name in {err!r} so the "
                f"operator can correlate the response with the log line."
            )

    @pytest.mark.asyncio
    @patch("api.credentials_service.Credential.get_by_provider")
    # NOTE: ProviderConfig is imported lazily INSIDE the migration
    # function (`from deeper_notebook.domain.provider_config import
    # ProviderConfig`). Patching `api.credentials_service.ProviderConfig`
    # does not intercept that local import — we must patch the source
    # module path instead. This is the same shape as v0.7.96's lazy-
    # import patch fix in test_provider_config.py.
    @patch("deeper_notebook.domain.provider_config.ProviderConfig")
    @patch("api.credentials_service.require_encryption_key")
    async def test_migrate_from_provider_config_sanitizes_exception(
        self,
        mock_require,
        mock_provider_config,
        mock_get_by_provider,
        client,
    ):
        """Same contract as the env migration: exception messages from
        the inner Credential() constructor / save() must not leak into
        the response. Tests the OTHER except branch."""
        # Construct a fake ProviderConfig with one credentials entry whose
        # api_key attribute access raises with sensitive content. We
        # intercept at the get_by_provider call (executes inside the for
        # loop's try block) so the except handler fires.
        from unittest.mock import MagicMock

        old_cred = MagicMock()
        old_cred.name = "test-cred"
        old_cred.api_key = "sk-LEAKME-123"
        old_cred.base_url = None
        old_cred.endpoint = None
        old_cred.api_version = None
        old_cred.endpoint_llm = None
        old_cred.endpoint_embedding = None
        old_cred.endpoint_stt = None
        old_cred.endpoint_tts = None
        old_cred.project = None
        old_cred.location = None
        old_cred.credentials_path = None

        fake_config = MagicMock()
        fake_config.credentials = {"openai": [old_cred]}
        mock_provider_config.get_instance = AsyncMock(return_value=fake_config)

        # Force the except branch via Credential.get_by_provider raising.
        mock_get_by_provider.side_effect = RuntimeError(
            "SurrealDB query failed: SELECT * FROM credential api_key=sk-LEAKME-123"
        )

        response = client.post("/api/credentials/migrate-from-provider-config")

        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["errors"]) > 0, (
            "Expected the mocked exception to land in errors[]."
        )
        for err in body["errors"]:
            assert "sk-LEAKME-123" not in err, (
                f"api_key prefix leaked into migration response: {err!r}. "
                f"v0.8.22 fix: emit type(e).__name__, not str(e)."
            )
            assert "SELECT * FROM credential" not in err, (
                f"SurrealQL query fragment leaked: {err!r}."
            )
            assert "RuntimeError" in err, (
                f"Type name missing from {err!r} — operators can't "
                f"correlate response with log line without it."
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
