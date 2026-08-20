"""Task 6 contracts for active Deeper Notebook product surfaces."""

from __future__ import annotations

import inspect
import json
import re
import zipfile
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.main import app
from api.routers.studio import artifacts as artifact_router
from deeper_notebook.domain.notebook import StudioArtifact
from deeper_notebook.studio.exporters.research_bundle import (
    build_research_bundle,
    verify_research_bundle,
)
from deeper_notebook.studio.generation import persistence
from desktop.splash import build_splash_html
from desktop.window import open_window

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_NAME = "Deeper Notebook"
DESCRIPTION = "Local-first research and knowledge workspace"


def test_api_metadata_root_version_and_health_use_active_identity() -> None:
    client = TestClient(app)

    assert app.title == PRODUCT_NAME
    assert app.description == DESCRIPTION
    assert client.get("/").json() == {
        "message": "Deeper Notebook API is running",
        "name": PRODUCT_NAME,
        "description": DESCRIPTION,
    }
    version = client.get("/api/version").json()
    assert version["name"] == PRODUCT_NAME
    assert version["description"] == DESCRIPTION
    assert client.get("/health").json()["name"] == PRODUCT_NAME
    assert client.get("/livez").json()["name"] == PRODUCT_NAME


def test_canonical_namespace_is_documented_and_legacy_alias_is_hidden(
    monkeypatch,
) -> None:
    from api.routers import deeper_notebook as theme_router

    monkeypatch.setattr(
        theme_router,
        "_load_config",
        lambda: (Path("/tmp/config.toml"), SimpleNamespace(theme="dark")),
    )
    client = TestClient(app)
    schema_paths = set(app.openapi()["paths"])

    assert client.get("/api/deeper-notebook/theme").status_code == 200
    assert client.get("/api/onp/theme").status_code == 200
    assert "/api/deeper-notebook/theme" in schema_paths
    assert "/api/deeper-notebook/gmail/status" in schema_paths
    assert "/api/onp/theme" not in schema_paths
    assert "/api/onp/gmail/status" not in schema_paths


def test_active_router_and_frontend_helper_have_canonical_paths() -> None:
    canonical_router = ROOT / "api/routers/deeper_notebook.py"
    legacy_router = ROOT / "api/routers/onp.py"
    canonical_helper = ROOT / "frontend/src/lib/api/deeper-notebook.ts"
    legacy_helper = ROOT / "frontend/src/lib/api/onp.ts"

    assert canonical_router.is_file()
    assert '@router.get("/theme"' in canonical_router.read_text(encoding="utf-8")
    assert legacy_router.is_file()
    assert "from .deeper_notebook import" in legacy_router.read_text(encoding="utf-8")
    assert canonical_helper.is_file()
    assert "deeperNotebookFetch" in canonical_helper.read_text(encoding="utf-8")
    assert legacy_helper.is_file()
    assert "deeperNotebookFetch as onpFetch" in legacy_helper.read_text(
        encoding="utf-8"
    )


def test_desktop_active_chrome_uses_deeper_notebook_identity() -> None:
    splash = build_splash_html("http://127.0.0.1:54321/")
    assert "<title>Deeper Notebook</title>" in splash
    assert "<h1>Deeper Notebook</h1>" in splash
    assert "Think further with every source" in splash
    assert inspect.signature(open_window).parameters["title"].default == PRODUCT_NAME

    active_files = [
        "desktop/app.py",
        "desktop/tray.py",
        "desktop/first_run/server.py",
        "desktop/first_run/static/index.html",
        "desktop/model_manager/static/index.html",
        "desktop/memory_dashboard/static/index.html",
    ]
    for relative_path in active_files:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert PRODUCT_NAME in source, relative_path
        assert "Open Notebook Plus" not in source, relative_path
        assert "Open notebook+" not in source, relative_path


def test_generated_course_pack_provenance_uses_canonical_urn() -> None:
    artifact = StudioArtifact(
        id="studio_artifact:course-pack",
        notebook_id="notebook:research",
        artifact_type="course_pack",
        title="Grounded course",
        status="completed",
    )

    for module in (persistence, artifact_router):
        xml = module._course_pack_tincan_xml(artifact)
        statements = module._course_pack_xapi_statements(artifact, [])
        assert "urn:deeper-notebook:studio_artifact:course-pack" in xml
        assert statements["activity"]["id"] == (
            "urn:deeper-notebook:studio_artifact:course-pack"
        )


def test_research_bundle_writes_canonical_format_and_reads_legacy_format(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "canonical.zip"
    build_research_bundle(
        canonical,
        artifact={"id": "studio_artifact:canonical"},
        markdown="# Canonical\n",
        citations=[],
        source_metadata=[],
        evaluation_report={},
    )

    assert verify_research_bundle(canonical)["format"] == (
        "deeper-notebook-research-bundle"
    )

    legacy = tmp_path / "legacy.zip"
    with zipfile.ZipFile(canonical) as source:
        entries = {name: source.read(name) for name in source.namelist()}
    manifest = json.loads(entries["manifest.json"])
    manifest["format"] = "open-notebook-plus-research-bundle"
    entries["manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    with zipfile.ZipFile(legacy, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, data in entries.items():
            output.writestr(name, data)

    verified = verify_research_bundle(legacy)
    assert verified["format"] == "open-notebook-plus-research-bundle"


def test_active_product_code_has_no_stale_visible_brand_labels() -> None:
    """Keep compatibility IDs while rejecting stale active display identity."""
    roots = [
        ROOT / "api",
        ROOT / "deeper_notebook",
        ROOT / "frontend/src",
        ROOT / "desktop/first_run",
        ROOT / "desktop/model_manager",
        ROOT / "desktop/memory_dashboard",
    ]
    explicit_files = [
        ROOT / "desktop/app.py",
        ROOT / "desktop/singleton.py",
        ROOT / "desktop/splash.py",
        ROOT / "desktop/tray.py",
        ROOT / "desktop/window.py",
    ]
    stale = re.compile(r"Open Notebook Plus|Open notebook\+|Open Notebook\+")
    unexpected: list[str] = []
    candidates = [
        path
        for root in roots
        for path in root.rglob("*")
        if path.suffix in {".py", ".ts", ".tsx", ".html"}
    ]
    for path in [*candidates, *explicit_files]:
        relative = path.relative_to(ROOT)
        if (
            "__pycache__" in path.parts
            or ".next" in path.parts
            or "node_modules" in path.parts
            or ".test." in path.name
            or relative.parts[:3]
            == (
                "deeper_notebook",
                "database",
                "migrations",
            )
        ):
            continue
        source = path.read_text(encoding="utf-8")
        # This is a persisted episode-profile identity. It remains readable and
        # selectable until a dedicated record migration exists.
        source = source.replace("Open Notebook Plus Local", "")
        # The replacement prompt must name the legacy .app bundle precisely so
        # users know which installed application will be moved to Trash.
        source = source.replace("Open Notebook Plus.app", "")
        for line_number, line in enumerate(source.splitlines(), start=1):
            if stale.search(line):
                unexpected.append(f"{relative}:{line_number}")

    assert unexpected == [], "Stale active product labels remain:\n" + "\n".join(
        unexpected
    )
