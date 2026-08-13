"""
Unit tests for the deeper_notebook.graphs module.

This test suite focuses on testing graph structures, tools, and validation
without heavy mocking of the actual processing logic.
"""

import hashlib
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deeper_notebook.domain.notebook import Source
from deeper_notebook.graphs.prompt import PatternChainState, graph
from deeper_notebook.graphs.tools import get_current_timestamp
from deeper_notebook.graphs.transformation import (
    TransformationState,
    run_transformation,
)
from deeper_notebook.graphs.transformation import (
    graph as transformation_graph,
)

# ============================================================================
# TEST SUITE 1: Graph Tools
# ============================================================================


class TestGraphTools:
    """Test suite for graph tool definitions."""

    def test_get_current_timestamp_format(self):
        """Test timestamp tool returns correct format.

        v0.7.190 — Format changed from `YYYYMMDDHHmmss` to ISO 8601
        basic `YYYYMMDDTHHmmssZ` with explicit UTC marker. Cross-
        machine prompt caching previously left ambiguous local-time
        stamps in LLM context windows.
        """
        timestamp = get_current_timestamp.func()

        assert isinstance(timestamp, str)
        assert len(timestamp) == 16  # YYYYMMDDTHHmmssZ format
        assert "T" in timestamp
        assert timestamp.endswith("Z")

    def test_get_current_timestamp_validity(self):
        """Test timestamp represents valid datetime.

        v0.7.190 — parsing format updated for the new ISO 8601 basic
        shape with UTC marker."""
        timestamp = get_current_timestamp.func()

        # New shape: YYYYMMDDTHHmmssZ — strip the trailing Z and
        # split on T to extract components.
        assert timestamp.endswith("Z")
        date_part, time_part = timestamp[:-1].split("T")
        year = int(date_part[0:4])
        month = int(date_part[4:6])
        day = int(date_part[6:8])
        hour = int(time_part[0:2])
        minute = int(time_part[2:4])
        second = int(time_part[4:6])

        # Should be valid date components
        assert 2020 <= year <= 2100
        assert 1 <= month <= 12
        assert 1 <= day <= 31
        assert 0 <= hour <= 23
        assert 0 <= minute <= 59
        assert 0 <= second <= 59

        # Should parse as a datetime via the new format.
        dt = datetime.strptime(timestamp, "%Y%m%dT%H%M%SZ")
        assert isinstance(dt, datetime)

    def test_get_current_timestamp_is_tool(self):
        """Test that function is properly decorated as a tool."""
        # Check it has tool attributes
        assert hasattr(get_current_timestamp, "name")
        assert hasattr(get_current_timestamp, "description")


# ============================================================================
# TEST SUITE 2: Prompt Graph State
# ============================================================================


class TestPromptGraph:
    """Test suite for prompt pattern chain graph."""

    def test_pattern_chain_state_structure(self):
        """Test PatternChainState structure and fields."""
        state = PatternChainState(
            prompt="Test prompt", parser=None, input_text="Test input", output=""
        )

        assert state["prompt"] == "Test prompt"
        assert state["parser"] is None
        assert state["input_text"] == "Test input"
        assert state["output"] == ""

    def test_prompt_graph_compilation(self):
        """Test that prompt graph compiles correctly."""
        assert graph is not None

        # Graph should have the expected structure
        assert hasattr(graph, "invoke")
        assert hasattr(graph, "ainvoke")


# ============================================================================
# TEST SUITE 3: Transformation Graph
# ============================================================================


class TestTransformationGraph:
    """Test suite for transformation graph workflows."""

    def test_transformation_state_structure(self):
        """Test TransformationState structure and fields."""
        from unittest.mock import MagicMock

        from deeper_notebook.domain.notebook import Source
        from deeper_notebook.domain.transformation import Transformation

        mock_source = MagicMock(spec=Source)
        mock_transformation = MagicMock(spec=Transformation)

        state = TransformationState(
            input_text="Test text",
            source=mock_source,
            transformation=mock_transformation,
            output="",
        )

        assert state["input_text"] == "Test text"
        assert state["source"] == mock_source
        assert state["transformation"] == mock_transformation
        assert state["output"] == ""

    @pytest.mark.asyncio
    async def test_run_transformation_assertion_no_content(self):
        """Test transformation raises assertion with no content."""
        from unittest.mock import MagicMock

        from deeper_notebook.domain.transformation import Transformation

        mock_transformation = MagicMock(spec=Transformation)

        state = {
            "input_text": None,
            "transformation": mock_transformation,
            "source": None,
        }

        config = {"configurable": {"model_id": None}}

        with pytest.raises(AssertionError, match="No content to transform"):
            await run_transformation(state, config)

    def test_transformation_graph_compilation(self):
        """Test that transformation graph compiles correctly."""
        assert transformation_graph is not None
        assert hasattr(transformation_graph, "invoke")
        assert hasattr(transformation_graph, "ainvoke")


# ============================================================================
# TEST SUITE 4: Source Graph - Title Preservation
# ============================================================================


class TestSaveSourceTitlePreservation:
    """Test save_source node preserves user-set titles (#670)."""

    @pytest.mark.asyncio
    @patch("deeper_notebook.graphs.source.Source.get")
    async def test_custom_title_preserved(self, mock_get):
        """User-set title is NOT overwritten by content_state.title."""
        from deeper_notebook.graphs.source import save_source

        mock_source = MagicMock(spec=Source)
        mock_source.title = "My Custom Research Title"
        mock_source.save = AsyncMock()
        mock_get.return_value = mock_source

        content_state = MagicMock()
        content_state.title = "video.mp4"
        content_state.url = "https://example.com"
        content_state.file_path = None
        content_state.content = "Some content"

        state = {
            "source_id": "source:123",
            "content_state": content_state,
            "embed": False,
            "apply_transformations": [],
        }

        await save_source(state)

        assert mock_source.title == "My Custom Research Title"
        mock_source.save.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("deeper_notebook.graphs.source.Source.get")
    async def test_placeholder_title_replaced(self, mock_get):
        """Placeholder 'Processing...' title IS replaced by extracted title."""
        from deeper_notebook.graphs.source import save_source

        mock_source = MagicMock(spec=Source)
        mock_source.title = "Processing..."
        mock_source.save = AsyncMock()
        mock_get.return_value = mock_source

        content_state = MagicMock()
        content_state.title = "Extracted Article Title"
        content_state.url = "https://example.com"
        content_state.file_path = None
        content_state.content = "Some content"

        state = {
            "source_id": "source:123",
            "content_state": content_state,
            "embed": False,
            "apply_transformations": [],
        }

        await save_source(state)

        assert mock_source.title == "Extracted Article Title"
        mock_source.save.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("deeper_notebook.graphs.source.Source.get")
    async def test_none_title_replaced(self, mock_get):
        """None title IS replaced by extracted title."""
        from deeper_notebook.graphs.source import save_source

        mock_source = MagicMock(spec=Source)
        mock_source.title = None
        mock_source.save = AsyncMock()
        mock_get.return_value = mock_source

        content_state = MagicMock()
        content_state.title = "Extracted Title"
        content_state.url = None
        content_state.file_path = "/tmp/file.pdf"
        content_state.content = "Content"

        state = {
            "source_id": "source:123",
            "content_state": content_state,
            "embed": False,
            "apply_transformations": [],
        }

        await save_source(state)

        assert mock_source.title == "Extracted Title"
        mock_source.save.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("deeper_notebook.graphs.source.Source.get")
    async def test_empty_title_replaced(self, mock_get):
        """Empty string title IS replaced by extracted title."""
        from deeper_notebook.graphs.source import save_source

        mock_source = MagicMock(spec=Source)
        mock_source.title = ""
        mock_source.save = AsyncMock()
        mock_get.return_value = mock_source

        content_state = MagicMock()
        content_state.title = "Extracted Title"
        content_state.url = None
        content_state.file_path = None
        content_state.content = "Content"

        state = {
            "source_id": "source:123",
            "content_state": content_state,
            "embed": False,
            "apply_transformations": [],
        }

        await save_source(state)

        assert mock_source.title == "Extracted Title"
        mock_source.save.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("deeper_notebook.graphs.source.Source.get")
    async def test_extracted_content_persists_content_fingerprint(self, mock_get):
        """Processed source evidence exposes the hash required by Study readiness."""
        from deeper_notebook.graphs.source import save_source

        mock_source = MagicMock(spec=Source)
        mock_source.title = "Processing..."
        mock_source.provenance = {
            "origin": "upload",
            "content_fingerprint": "client-value",
        }
        mock_source.save = AsyncMock()
        mock_get.return_value = mock_source

        content_state = MagicMock()
        content_state.title = "Extracted Title"
        content_state.url = None
        content_state.file_path = "/tmp/file.pdf"
        content_state.content = "Actual extracted evidence"
        content_state.source_type = "upload"
        content_state.identified_type = "application/pdf"
        content_state.metadata = None

        await save_source(
            {
                "source_id": "source:123",
                "content_state": content_state,
                "embed": False,
                "apply_transformations": [],
            }
        )

        assert (
            mock_source.provenance["content_fingerprint"]
            == hashlib.sha256(content_state.content.encode("utf-8")).hexdigest()
        )
        assert mock_source.provenance["content_fingerprint"] != "client-value"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
