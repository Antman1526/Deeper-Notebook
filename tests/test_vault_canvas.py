"""Strict read-only Canvas document contract."""

from __future__ import annotations

import pytest

from deeper_notebook.vault.canvas import CanvasDocumentError, parse_canvas_document


def test_parse_canvas_document_keeps_safe_nodes_and_edges() -> None:
    result = parse_canvas_document(
        b'{"nodes":[{"id":"idea","type":"text","x":0,"y":0,"width":240,"height":120,"text":"Idea"},{"id":"note","type":"file","x":320,"y":0,"width":240,"height":120,"file":"notes/Plan.md"}],"edges":[{"id":"edge","fromNode":"idea","toNode":"note","label":"supports"}]}',
        relative_path="maps/plan.canvas",
    )

    assert result.nodes[1].file_path == "notes/Plan.md"
    assert result.edges[0].from_node == "idea"
    assert result.edges[0].to_node == "note"


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b'{"nodes":[{"id":"file","type":"file","x":0,"y":0,"width":1,"height":1,"file":"../secret.md"}],"edges":[]}',
        b'{"nodes":[{"id":"node","type":"text","x":0,"y":0,"width":1,"height":1}],"edges":[{"id":"edge","fromNode":"node","toNode":"missing"}]}',
    ],
)
def test_parse_canvas_document_fails_closed_for_unsafe_input(payload: bytes) -> None:
    with pytest.raises(CanvasDocumentError):
        parse_canvas_document(payload, relative_path="maps/plan.canvas")
