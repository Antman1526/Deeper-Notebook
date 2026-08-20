from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client after environment variables have been cleared by conftest."""
    from api.main import app

    return TestClient(app)


class TestModelCreation:
    """Test suite for Model Creation endpoint."""

    @pytest.mark.asyncio
    @patch("deeper_notebook.database.repository.repo_query")
    @patch("api.routers.models.Model.save")
    async def test_create_duplicate_model_same_case(
        self, mock_save, mock_repo_query, client
    ):
        """Test that creating a duplicate model with same case returns 400."""
        # Mock repo_query to return a duplicate model
        mock_repo_query.return_value = [
            {
                "id": "model:123",
                "name": "gpt-4",
                "provider": "openai",
                "type": "language",
            }
        ]

        # Attempt to create duplicate
        response = client.post(
            "/api/models",
            json={"name": "gpt-4", "provider": "openai", "type": "language"},
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]
            == "Model 'gpt-4' already exists for provider 'openai' with type 'language'"
        )

    @pytest.mark.asyncio
    @patch("deeper_notebook.database.repository.repo_query")
    @patch("api.routers.models.Model.save")
    async def test_create_duplicate_model_different_case(
        self, mock_save, mock_repo_query, client
    ):
        """Test that creating a duplicate model with different case returns 400."""
        # Mock repo_query to return a duplicate model (case-insensitive match)
        mock_repo_query.return_value = [
            {
                "id": "model:123",
                "name": "gpt-4",
                "provider": "openai",
                "type": "language",
            }
        ]

        # Attempt to create duplicate with different case
        response = client.post(
            "/api/models",
            json={"name": "GPT-4", "provider": "OpenAI", "type": "language"},
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]
            == "Model 'GPT-4' already exists for provider 'OpenAI' with type 'language'"
        )

    @pytest.mark.asyncio
    @patch("deeper_notebook.database.repository.repo_query")
    async def test_create_same_model_name_different_provider(
        self, mock_repo_query, client
    ):
        """Test that creating a model with same name but different provider is allowed."""
        from deeper_notebook.ai.models import Model

        # Mock repo_query to return empty (no duplicate found for different provider)
        mock_repo_query.return_value = []

        # Patch the save method on the Model class
        with patch.object(Model, "save", new_callable=AsyncMock) as mock_save:
            # Attempt to create same model name with different provider (anthropic)
            response = client.post(
                "/api/models",
                json={"name": "gpt-4", "provider": "anthropic", "type": "language"},
            )

            # Should succeed because provider is different
            assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("deeper_notebook.database.repository.repo_query")
    async def test_create_same_model_name_different_type(self, mock_repo_query, client):
        """Test that creating a model with same name but different type is allowed."""
        from deeper_notebook.ai.models import Model

        # Mock repo_query to return empty (no duplicate found for different type)
        mock_repo_query.return_value = []

        # Patch the save method on the Model class
        with patch.object(Model, "save", new_callable=AsyncMock) as mock_save:
            # Attempt to create same model name with different type (embedding instead of language)
            response = client.post(
                "/api/models",
                json={"name": "gpt-4", "provider": "openai", "type": "embedding"},
            )

            # Should succeed because type is different
            assert response.status_code == 200


class TestModelsProviderAvailability:
    """Test suite for Models Provider Availability endpoint."""

    @patch("api.routers.models.os.environ.get")
    @patch("api.routers.models.AIFactory.get_available_providers")
    def test_generic_env_var_enables_all_modes(self, mock_esperanto, mock_env, client):
        """Test that OPENAI_COMPATIBLE_BASE_URL enables all 4 modes."""

        # Mock environment: only generic var is set
        def env_side_effect(key):
            if key == "OPENAI_COMPATIBLE_BASE_URL":
                return "http://localhost:1234/v1"
            return None

        mock_env.side_effect = env_side_effect

        # Mock Esperanto response
        mock_esperanto.return_value = {
            "language": ["openai-compatible"],
            "embedding": ["openai-compatible"],
            "speech_to_text": ["openai-compatible"],
            "text_to_speech": ["openai-compatible"],
        }

        response = client.get("/api/models/providers")

        assert response.status_code == 200
        data = response.json()

        # openai-compatible should be available
        assert "openai_compatible" in data["available"]

        # Should support all 4 types
        assert "openai_compatible" in data["supported_types"]
        supported = data["supported_types"]["openai_compatible"]
        assert "language" in supported
        assert "embedding" in supported
        assert "speech_to_text" in supported
        assert "text_to_speech" in supported
        assert len(supported) == 4

    @patch("api.routers.models.os.environ.get")
    @patch("api.routers.models.AIFactory.get_available_providers")
    def test_mode_specific_env_vars_llm_embedding(
        self, mock_esperanto, mock_env, client
    ):
        """Test mode-specific env vars (LLM + EMBEDDING) enable only those 2 modes."""

        # Mock environment: only LLM and EMBEDDING specific vars are set
        def env_side_effect(key):
            if key == "OPENAI_COMPATIBLE_BASE_URL_LLM":
                return "http://localhost:1234/v1"
            if key == "OPENAI_COMPATIBLE_BASE_URL_EMBEDDING":
                return "http://localhost:8080/v1"
            return None

        mock_env.side_effect = env_side_effect

        # Mock Esperanto response
        mock_esperanto.return_value = {
            "language": ["openai-compatible"],
            "embedding": ["openai-compatible"],
            "speech_to_text": ["openai-compatible"],
            "text_to_speech": ["openai-compatible"],
        }

        response = client.get("/api/models/providers")

        assert response.status_code == 200
        data = response.json()

        # openai-compatible should be available
        assert "openai_compatible" in data["available"]

        # Should support only language and embedding
        assert "openai_compatible" in data["supported_types"]
        supported = data["supported_types"]["openai_compatible"]
        assert "language" in supported
        assert "embedding" in supported
        assert "speech_to_text" not in supported
        assert "text_to_speech" not in supported
        assert len(supported) == 2

    @patch("api.routers.models.os.environ.get")
    @patch("api.routers.models.AIFactory.get_available_providers")
    def test_no_env_vars_set(self, mock_esperanto, mock_env, client):
        """Test that openai-compatible is not available when no env vars are set."""

        # Mock environment: no openai-compatible vars are set
        def env_side_effect(key):
            return None

        mock_env.side_effect = env_side_effect

        # Mock Esperanto response
        mock_esperanto.return_value = {
            "language": ["openai-compatible"],
            "embedding": ["openai-compatible"],
        }

        response = client.get("/api/models/providers")

        assert response.status_code == 200
        data = response.json()

        # openai-compatible should NOT be available
        assert "openai_compatible" not in data["available"]
        assert "openai_compatible" in data["unavailable"]

        # Should not have supported_types entry
        assert "openai_compatible" not in data["supported_types"]

    @patch("api.routers.models.os.environ.get")
    @patch("api.routers.models.AIFactory.get_available_providers")
    def test_mixed_config_generic_and_mode_specific(
        self, mock_esperanto, mock_env, client
    ):
        """Test mixed config: generic + mode-specific (generic should enable all)."""

        # Mock environment: both generic and mode-specific vars are set
        def env_side_effect(key):
            if key == "OPENAI_COMPATIBLE_BASE_URL":
                return "http://localhost:1234/v1"
            if key == "OPENAI_COMPATIBLE_BASE_URL_LLM":
                return "http://localhost:5678/v1"
            return None

        mock_env.side_effect = env_side_effect

        # Mock Esperanto response
        mock_esperanto.return_value = {
            "language": ["openai-compatible"],
            "embedding": ["openai-compatible"],
            "speech_to_text": ["openai-compatible"],
            "text_to_speech": ["openai-compatible"],
        }

        response = client.get("/api/models/providers")

        assert response.status_code == 200
        data = response.json()

        # openai-compatible should be available
        assert "openai_compatible" in data["available"]

        # Generic var enables all, so all 4 should be supported
        assert "openai_compatible" in data["supported_types"]
        supported = data["supported_types"]["openai_compatible"]
        assert "language" in supported
        assert "embedding" in supported
        assert "speech_to_text" in supported
        assert "text_to_speech" in supported
        assert len(supported) == 4

    @patch("api.routers.models.os.environ.get")
    @patch("api.routers.models.AIFactory.get_available_providers")
    def test_individual_mode_llm_only(self, mock_esperanto, mock_env, client):
        """Test individual mode-specific var (LLM only)."""

        # Mock environment: only LLM specific var is set
        def env_side_effect(key):
            if key == "OPENAI_COMPATIBLE_BASE_URL_LLM":
                return "http://localhost:1234/v1"
            return None

        mock_env.side_effect = env_side_effect

        # Mock Esperanto response
        mock_esperanto.return_value = {
            "language": ["openai-compatible"],
            "embedding": ["openai-compatible"],
            "speech_to_text": ["openai-compatible"],
            "text_to_speech": ["openai-compatible"],
        }

        response = client.get("/api/models/providers")

        assert response.status_code == 200
        data = response.json()

        # Should support only language
        supported = data["supported_types"]["openai_compatible"]
        assert supported == ["language"]

    @patch("api.routers.models.os.environ.get")
    @patch("api.routers.models.AIFactory.get_available_providers")
    def test_individual_mode_embedding_only(self, mock_esperanto, mock_env, client):
        """Test individual mode-specific var (EMBEDDING only)."""

        # Mock environment: only EMBEDDING specific var is set
        def env_side_effect(key):
            if key == "OPENAI_COMPATIBLE_BASE_URL_EMBEDDING":
                return "http://localhost:8080/v1"
            return None

        mock_env.side_effect = env_side_effect

        # Mock Esperanto response
        mock_esperanto.return_value = {
            "language": ["openai-compatible"],
            "embedding": ["openai-compatible"],
            "speech_to_text": ["openai-compatible"],
            "text_to_speech": ["openai-compatible"],
        }

        response = client.get("/api/models/providers")

        assert response.status_code == 200
        data = response.json()

        # Should support only embedding
        supported = data["supported_types"]["openai_compatible"]
        assert supported == ["embedding"]

    @patch("api.routers.models.os.environ.get")
    @patch("api.routers.models.AIFactory.get_available_providers")
    def test_individual_mode_stt_only(self, mock_esperanto, mock_env, client):
        """Test individual mode-specific var (STT only)."""

        # Mock environment: only STT specific var is set
        def env_side_effect(key):
            if key == "OPENAI_COMPATIBLE_BASE_URL_STT":
                return "http://localhost:9000/v1"
            return None

        mock_env.side_effect = env_side_effect

        # Mock Esperanto response
        mock_esperanto.return_value = {
            "language": ["openai-compatible"],
            "embedding": ["openai-compatible"],
            "speech_to_text": ["openai-compatible"],
            "text_to_speech": ["openai-compatible"],
        }

        response = client.get("/api/models/providers")

        assert response.status_code == 200
        data = response.json()

        # Should support only speech_to_text
        supported = data["supported_types"]["openai_compatible"]
        assert supported == ["speech_to_text"]

    @patch("api.routers.models.os.environ.get")
    @patch("api.routers.models.AIFactory.get_available_providers")
    def test_individual_mode_tts_only(self, mock_esperanto, mock_env, client):
        """Test individual mode-specific var (TTS only)."""

        # Mock environment: only TTS specific var is set
        def env_side_effect(key):
            if key == "OPENAI_COMPATIBLE_BASE_URL_TTS":
                return "http://localhost:9000/v1"
            return None

        mock_env.side_effect = env_side_effect

        # Mock Esperanto response
        mock_esperanto.return_value = {
            "language": ["openai-compatible"],
            "embedding": ["openai-compatible"],
            "speech_to_text": ["openai-compatible"],
            "text_to_speech": ["openai-compatible"],
        }

        response = client.get("/api/models/providers")

        assert response.status_code == 200
        data = response.json()

        # Should support only text_to_speech
        supported = data["supported_types"]["openai_compatible"]
        assert supported == ["text_to_speech"]


def test_v0829_check_provider_has_credential_logs_debug_on_db_error(monkeypatch):
    """v0.8.29 — `_check_provider_has_credential` had `except Exception:
    pass; return False` with no logging. A DB connection drop, schema
    mismatch, or auth failure would silently report "provider not
    configured" without any trace in launcher.log. Must now log at
    DEBUG so the operator can correlate the UI misreport with the
    cause.
    """
    import asyncio
    from unittest.mock import AsyncMock

    from loguru import logger

    from api.routers import models as models_router

    # Force the DB lookup to raise.
    monkeypatch.setattr(
        models_router.Credential,
        "get_by_provider",
        AsyncMock(side_effect=RuntimeError("simulated DB drop")),
    )

    captured: list[dict] = []
    sink_id = logger.add(
        lambda msg: captured.append(
            {
                "level": msg.record["level"].name,
                "message": msg.record["message"],
            }
        ),
        level="DEBUG",
    )
    try:
        result = asyncio.new_event_loop().run_until_complete(
            models_router._check_provider_has_credential("openai")
        )
    finally:
        logger.remove(sink_id)

    # Function still returns False (correct fallback behaviour) ...
    assert result is False
    # ... but emits a DEBUG line so the operator can see why.
    debug_lines = [c for c in captured if c["level"] == "DEBUG"]
    assert debug_lines, (
        "v0.8.29: a DB error in _check_provider_has_credential must "
        "log at DEBUG. Pre-v0.8.29 was silent; the UI would briefly "
        "show DB-configured providers as unconfigured with no signal."
    )
    # And the log message names the provider so the operator can
    # correlate.
    assert any("openai" in c["message"] for c in debug_lines), (
        f"Expected provider name in DEBUG message; got: {debug_lines}"
    )
