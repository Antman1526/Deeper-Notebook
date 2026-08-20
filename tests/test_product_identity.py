import hashlib
import importlib
import json
import re
import subprocess
import sys
import tomllib
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

import deeper_notebook
import scripts.rebrand_audit as rebrand_audit
from deeper_notebook.environment import SETTINGS
from deeper_notebook.identity import (
    API_NAMESPACE,
    DATA_DIR_NAME,
    LEGACY_API_NAMESPACE,
    LEGACY_DATA_DIR_NAME,
    PRODUCT_NAME,
    REPOSITORY,
    TAGLINE,
)
from deeper_notebook.logging import default_log_dir
from scripts.rebrand_audit import (
    ALLOWLIST_SCHEMA_VERSION,
    LEGACY_PATTERNS,
    Approval,
    Rationale,
    audit_repository,
    classify_match,
    context_sha256,
    load_allowlist,
    occurrence_digest,
    patterns_for_path,
)

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts" / "rebrand_audit.py"
ALLOWLIST_PATH = ROOT / "scripts" / "rebrand-allowlist.json"


def _materialize_test_contracts(
    entries: list[dict[str, object]],
    contracts: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    materialized: dict[str, dict[str, object]] = {}
    referenced_contracts = {
        entry["rationale"].get("compatibility_contract")
        for entry in entries
        if isinstance(entry.get("rationale"), dict)
    }
    for contract_id, contract in contracts.items():
        if contract_id not in referenced_contracts:
            continue
        owned_entries = [
            entry
            for entry in entries
            if entry["rationale"]["compatibility_contract"] == contract_id
        ]
        complete = dict(contract)
        complete.setdefault(
            "scope",
            {
                "paths": sorted({str(entry["path"]) for entry in owned_entries}),
                "patterns": sorted({str(entry["pattern"]) for entry in owned_entries}),
                "sources": sorted({str(entry["source"]) for entry in owned_entries}),
            },
        )
        complete.setdefault(
            "coverage_sha256",
            _test_coverage_digest(owned_entries, contract_id),
        )
        materialized[contract_id] = complete
    return materialized


def _write_allowlist(path: Path, entries: list[dict[str, object]]) -> Path:
    has_compatibility = any(
        entry.get("category") == "compatibility_alias" for entry in entries
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": ALLOWLIST_SCHEMA_VERSION,
                "persisted_queue_identifiers": [],
                "compatibility_contracts": (
                    _materialize_test_contracts(
                        entries,
                        {
                            "test-compatibility-v1": {
                                "kind": "regression_fixture",
                                "owner": "rebrand-audit-tests",
                                "retention_reason": (
                                    "The focused audit fixture exercises a "
                                    "specific compatibility validation branch."
                                ),
                                "proof": ("static:regression-fixture-contract-v1"),
                            }
                        },
                    )
                    if has_compatibility
                    else {}
                ),
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_contract_allowlist(
    path: Path,
    entries: list[dict[str, object]],
    contracts: dict[str, dict[str, object]],
) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": ALLOWLIST_SCHEMA_VERSION,
                "persisted_queue_identifiers": [],
                "compatibility_contracts": _materialize_test_contracts(
                    entries,
                    contracts,
                ),
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )
    return path


def _approval(
    *,
    path: str,
    pattern: str,
    context: str,
    source: str = "content",
    line: int | None = 1,
    column: int | None = None,
    category: str = "compatibility_alias",
    rationale: str = "Compatibility behavior is intentionally preserved.",
    compatibility_contract: str = "test-compatibility-v1",
):
    actual_column = column or context.index(pattern) + 1
    # The key's digest must fold in the intra-line ordinal, or a fixture
    # approving the SECOND occurrence on a line will not match what the scanner
    # computes for it.
    key = (
        path,
        pattern,
        source,
        line,
        actual_column,
        context_sha256(context)
        if line is None
        else occurrence_digest(pattern=pattern, context=context, column=actual_column),
    )
    return key, Approval(
        category=category,
        rationale=Rationale(
            path=path,
            pattern=pattern,
            source=source,
            line=line,
            column=actual_column,
            context_sha256=key[-1],
            category=category,
            explanation=rationale,
            compatibility_contract=(
                compatibility_contract if category == "compatibility_alias" else None
            ),
        ),
    )


def _rationale(
    *,
    path: str,
    pattern: str,
    source: str,
    line: int | None,
    column: int,
    context: str,
    category: str,
    explanation: str,
    compatibility_contract: str | None = None,
) -> dict[str, object]:
    return {
        "path": path,
        "pattern": pattern,
        "source": source,
        "line": line,
        "column": column,
        # Line-sourced approvals fold the intra-line ordinal into the digest;
        # only path-sourced ones, which have no line to disambiguate, use
        # context_sha256 (which is itself the ordinal-0 digest).
        "context_sha256": (
            context_sha256(context)
            if line is None
            else occurrence_digest(pattern=pattern, context=context, column=column)
        ),
        "category": category,
        "explanation": explanation,
        "compatibility_contract": (
            compatibility_contract
            if compatibility_contract is not None
            else (
                "test-compatibility-v1" if category == "compatibility_alias" else None
            )
        ),
    }


def _init_tracked_repo(path: Path, files: dict[str, bytes | str]) -> Path:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for relative_path, content in files.items():
        target = path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    return path


def test_canonical_product_identity():
    assert PRODUCT_NAME == "Deeper Notebook"
    assert TAGLINE == "Think further with every source"
    assert REPOSITORY == "Antman1526/Deeper-Notebook"
    assert DATA_DIR_NAME == ".deeper-notebook"
    assert API_NAMESPACE == "/api/deeper-notebook"


def test_legacy_identity_is_explicitly_compatibility_only():
    assert LEGACY_DATA_DIR_NAME == ".open-notebook-plus"
    assert LEGACY_API_NAMESPACE == "/api/onp"


def test_audit_distinguishes_compatibility_from_active_branding():
    line = "open_notebook"
    approved_key, approval = _approval(
        path="desktop/build/deeper-notebook.iss",
        pattern=line,
        context=line,
    )
    allowlist = {approved_key: approval}

    assert classify_match(approved_key, allowlist) == "compatibility_alias"
    active_key, _ = _approval(
        path="frontend/src/app/layout.tsx",
        pattern="Open Notebook Plus",
        context="Open Notebook Plus",
    )
    assert classify_match(active_key, allowlist) == "unexpected_active_identity"


def test_distribution_metadata_is_canonical():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "deeper-notebook"
    assert pyproject["project"]["description"] == (
        "Local-first, source-grounded research and personal knowledge workspace"
    )
    assert pyproject["tool"]["setuptools"]["packages"]["find"]["include"] == [
        "deeper_notebook*",
        "open_notebook*",
    ]
    assert deeper_notebook.__version__ == pyproject["project"]["version"]


def test_source_fallback_version_matches_pyproject_when_metadata_is_unavailable():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    try:
        with patch(
            "importlib.metadata.version",
            side_effect=PackageNotFoundError,
        ):
            fallback_module = importlib.reload(deeper_notebook)
            assert fallback_module.__version__ == pyproject["project"]["version"]
    finally:
        importlib.reload(deeper_notebook)


def test_audit_patterns_are_immutable_and_not_extended_by_approvals():
    custom_allowlist = {
        ("README.upstream.md", "lfnovo/open-notebook"): "upstream_reference"
    }

    assert patterns_for_path("README.upstream.md", custom_allowlist) == (
        LEGACY_PATTERNS
    )


def test_allowlist_rejects_broad_custom_pattern_containing_builtins(tmp_path):
    path = "docs/history.md"
    pattern = "compat open_notebook and Open Notebook Plus wrapper"
    custom = _write_allowlist(
        tmp_path / "custom.json",
        [
            {
                "path": path,
                "pattern": pattern,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(pattern),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern=pattern,
                    source="content",
                    line=1,
                    column=1,
                    context=pattern,
                    category="historical_reference",
                    explanation=(
                        "This exact historical wording is retained to preserve "
                        "the accuracy of the recorded release."
                    ),
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="built-in legacy patterns"):
        load_allowlist(custom)


def test_legacy_installer_path_is_unexpected_and_app_id_remains_stable():
    allowlist = load_allowlist(ALLOWLIST_PATH)
    legacy_installer = "desktop/build/open-notebook-plus.iss"
    legacy_key = (
        legacy_installer,
        "open-notebook-plus",
        "path",
        None,
        legacy_installer.index("open-notebook-plus") + 1,
        context_sha256(legacy_installer),
    )

    assert classify_match(legacy_key, allowlist) == "unexpected_active_identity"
    installer = (ROOT / "desktop/build/deeper-notebook.iss").read_text(encoding="utf-8")
    assert "AppId={{572C65B3-D1E8-4EBD-8D64-2BFDF3CA5842}" in installer


def test_allowlist_uses_exact_persisted_context_not_broad_module_pattern():
    allowlist = load_allowlist(ALLOWLIST_PATH)
    command_key = next(
        key
        for key, approval in allowlist.items()
        if key[0] == "commands/embedding_commands.py"
        and key[1] == "open_notebook"
        and approval.category == "compatibility_alias"
    )
    # CHANGED ASSERTION, deliberately — worth reviewing.
    #
    # This used to shift the COLUMN by +1 and assert rejection, i.e. it asserted
    # that absolute column is part of an approval's identity. The re-key removes
    # that on purpose: absolute column shifts whenever a line is reindented,
    # which is why a reformat invalidated every approval and why an edit above a
    # pinned line broke the gate.
    #
    # What column really encoded — WHICH occurrence on a line is approved — is
    # preserved, folded into the digest as an intra-line ordinal. The old
    # assertion is now unreachable rather than merely relaxed: the scanner
    # derives digest and column together from the same (context, column), so a
    # key with a shifted column and an unchanged digest cannot be produced by
    # any code path; only a hand-built tuple can express it.
    #
    # The property is therefore asserted directly. A key naming a genuinely
    # DIFFERENT occurrence must still be rejected, which is what matters and is
    # strictly stronger than checking one integer field.
    _twice = "a = open_notebook; b = open_notebook"
    same_line_other_occurrence = (
        *command_key[:5],
        occurrence_digest(
            pattern="open_notebook",
            context=_twice,
            column=_twice.rindex("open_notebook") + 1,
        ),
    )
    assert (
        classify_match(same_line_other_occurrence, allowlist)
        == "unexpected_active_identity"
    )
    repair_key = next(
        key
        for key, approval in allowlist.items()
        if key[0] == "desktop/db_repair.py"
        and key[1] == "open_notebook"
        and approval.category == "compatibility_alias"
    )
    assert classify_match(command_key, allowlist) == "compatibility_alias"
    assert classify_match(repair_key, allowlist) == "compatibility_alias"


def test_allowlist_rejects_all_wildcard_paths(
    tmp_path,
):
    path = "docs/1-INSTALLATION/**"
    pattern = "Open Notebook"
    wildcard = _write_allowlist(
        tmp_path / "wildcard.json",
        [
            {
                "path": path,
                "pattern": pattern,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(pattern),
                "category": "upstream_reference",
                "rationale": _rationale(
                    path=path,
                    pattern=pattern,
                    source="content",
                    line=1,
                    column=1,
                    context=pattern,
                    category="upstream_reference",
                    explanation=(
                        "This exact upstream product reference is retained to "
                        "preserve the documented project history."
                    ),
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="wildcards are disallowed"):
        load_allowlist(wildcard)


def test_repository_allowlist_entries_have_bound_specific_rationales():
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))

    for entry in payload["entries"]:
        rationale = entry["rationale"]
        for field in (
            "path",
            "pattern",
            "source",
            "line",
            "column",
            "context_sha256",
            "category",
        ):
            assert rationale[field] == entry[field], entry
        assert len(rationale["explanation"]) >= 48, entry
        assert len(rationale["explanation"].split()) >= 8, entry
        assert entry["path"] not in rationale["explanation"], entry
        assert entry["pattern"] not in rationale["explanation"], entry
        assert entry["category"] not in rationale["explanation"], entry
        assert not re.search(
            r"\boccurrence at\b|:[0-9]+:[0-9]+\b|[0-9a-f]{64}",
            rationale["explanation"],
            flags=re.IGNORECASE,
        ), entry


def test_allowlist_requires_occurrence_location_and_context(tmp_path):
    incomplete = _write_allowlist(
        tmp_path / "incomplete.json",
        [
            {
                "path": "docs/history.md",
                "pattern": "Open Notebook Plus",
                "category": "historical_reference",
                "rationale": {},
            }
        ],
    )

    with pytest.raises(ValueError, match="exactly the documented fields"):
        load_allowlist(incomplete)


def test_allowlist_rationale_is_bound_to_its_exact_occurrence(tmp_path):
    line = "Historical release: Open Notebook Plus"
    generic = _write_allowlist(
        tmp_path / "generic.json",
        [
            {
                "path": "docs/history.md",
                "pattern": "Open Notebook Plus",
                "source": "content",
                "line": 1,
                "column": line.index("Open Notebook Plus") + 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path="docs/wrong-history.md",
                    pattern="Open Notebook Plus",
                    source="content",
                    line=1,
                    column=line.index("Open Notebook Plus") + 1,
                    context=line,
                    category="historical_reference",
                    explanation=(
                        "This historical product name is retained to preserve "
                        "the accuracy of the documented release."
                    ),
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="exactly match its occurrence"):
        load_allowlist(generic)


def test_allowlist_rejects_rationale_pattern_mismatch_for_safe_nested_names(
    tmp_path,
):
    path = "docs/history.md"
    line = "Open Notebook Plus"
    mismatched = _write_allowlist(
        tmp_path / "pattern-mismatch.json",
        [
            {
                "path": path,
                "pattern": "Open Notebook Plus",
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern="Open Notebook",
                    source="content",
                    line=1,
                    column=1,
                    context=line,
                    category="historical_reference",
                    explanation=(
                        "The release record preserves the former desktop name "
                        "because that was the identity shipped to users."
                    ),
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="pattern.*exactly match"):
        load_allowlist(mismatched)


def test_allowlist_rejects_rationale_category_mismatch(tmp_path):
    path = "docs/history.md"
    line = "Open Notebook Plus"
    mismatched = _write_allowlist(
        tmp_path / "category-mismatch.json",
        [
            {
                "path": path,
                "pattern": line,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern=line,
                    source="content",
                    line=1,
                    column=1,
                    context=line,
                    category="compatibility_alias",
                    explanation=(
                        "The release record preserves the former desktop name "
                        "because that was the identity shipped to users."
                    ),
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="category.*exactly match"):
        load_allowlist(mismatched)


def test_allowlist_rejects_unknown_entry_fields(tmp_path):
    path = "docs/history.md"
    line = "Historical release: Open Notebook Plus"
    unknown = _write_allowlist(
        tmp_path / "unknown.json",
        [
            {
                "path": path,
                "pattern": "Open Notebook Plus",
                "source": "content",
                "line": 1,
                "column": line.index("Open Notebook Plus") + 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern="Open Notebook Plus",
                    source="content",
                    line=1,
                    column=21,
                    context=line,
                    category="historical_reference",
                    explanation=(
                        "This exact historical release name is retained to "
                        "preserve the accuracy of the release record."
                    ),
                ),
                "unexpected": True,
            }
        ],
    )

    with pytest.raises(ValueError, match="exactly the documented fields"):
        load_allowlist(unknown)


def _contract_entry(
    *,
    path: str = "deeper_notebook/environment.py",
    pattern: str = "ONP_",
    context: str = "legacy_name = 'ONP_SETTING'",
    contract: str | None = "env-alias-v1",
) -> dict[str, object]:
    column = context.index(pattern) + 1
    rationale = _rationale(
        path=path,
        pattern=pattern,
        source="content",
        line=1,
        column=column,
        context=context,
        category="compatibility_alias",
        explanation=(
            "The environment resolver retains the deprecated short-form "
            "setting so existing operator configuration keeps loading."
        ),
    )
    rationale["compatibility_contract"] = contract
    return {
        "path": path,
        "pattern": pattern,
        "source": "content",
        "line": 1,
        "column": column,
        "context_sha256": context_sha256(context),
        "category": "compatibility_alias",
        "rationale": rationale,
    }


def _valid_contract(**overrides: object) -> dict[str, object]:
    contract: dict[str, object] = {
        "kind": "env_alias",
        "owner": "runtime-configuration",
        "retention_reason": (
            "Existing operator environments need a deprecation window while "
            "canonical settings take precedence."
        ),
        "proof": "static:env-alias-contract-fixture-v1",
    }
    contract.update(overrides)
    return contract


def test_allowlist_accepts_proof_backed_structured_compatibility_contract():
    loaded = load_allowlist(ALLOWLIST_PATH)

    assert any(
        approval.rationale.compatibility_contract == "env-alias-v1"
        for approval in loaded.values()
    )


def test_allowlist_rejects_compatibility_without_structured_contract(tmp_path):
    allowlist_path = _write_contract_allowlist(
        tmp_path / "missing-contract.json",
        [_contract_entry(contract=None)],
        {"env-alias-v1": _valid_contract()},
    )

    with pytest.raises(ValueError, match="requires a structured compatibility"):
        load_allowlist(allowlist_path)


def test_allowlist_rejects_unknown_compatibility_contract_kind(tmp_path):
    allowlist_path = _write_contract_allowlist(
        tmp_path / "unknown-contract-kind.json",
        [_contract_entry()],
        {
            "env-alias-v1": _valid_contract(
                kind="freeform-compatibility-assertion",
            )
        },
    )

    with pytest.raises(ValueError, match="closed compatibility contract kind"):
        load_allowlist(allowlist_path)


def test_allowlist_rejects_unvalidated_compatibility_proof(tmp_path):
    allowlist_path = _write_contract_allowlist(
        tmp_path / "missing-proof.json",
        [_contract_entry()],
        {
            "env-alias-v1": _valid_contract(
                proof="tests/missing-proof.py::test_missing_contract",
            )
        },
    )

    with pytest.raises(ValueError, match="tracked proof reference"):
        load_allowlist(allowlist_path)


def _v5_contract_entry(
    *,
    path: str = "fixtures/legacy-name.py",
    pattern: str = "Open Notebook Plus",
    contract_id: str = "legacy-test-fixture-v1",
) -> dict[str, object]:
    context = f"legacy_name = {pattern!r}"
    column = context.index(pattern) + 1
    rationale = _rationale(
        path=path,
        pattern=pattern,
        source="content",
        line=1,
        column=column,
        context=context,
        category="compatibility_alias",
        explanation=(
            "The synthetic regression fixture retains a former identity to "
            "exercise the exact compatibility contract boundary."
        ),
        compatibility_contract=contract_id,
    )
    return {
        "path": path,
        "pattern": pattern,
        "source": "content",
        "line": 1,
        "column": column,
        "context_sha256": context_sha256(context),
        "category": "compatibility_alias",
        "rationale": rationale,
    }


def _test_coverage_digest(
    entries: list[dict[str, object]],
    contract_id: str,
) -> str:
    identities = sorted(
        "|".join(
            str(entry[field])
            for field in (
                "path",
                "pattern",
                "source",
                "line",
                "column",
                "context_sha256",
            )
        )
        for entry in entries
        if entry["rationale"]["compatibility_contract"] == contract_id
    )
    encoded = json.dumps(
        identities,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_v5_contract_allowlist(
    path: Path,
    *,
    entries: list[dict[str, object]],
    kind: str = "regression_fixture",
    proof: str = "static:regression-fixture-contract-v1",
    scope_paths: list[str] | None = None,
    coverage_sha256: str | None = None,
) -> Path:
    contract_id = "legacy-test-fixture-v1"
    payload = {
        "schema_version": ALLOWLIST_SCHEMA_VERSION,
        "persisted_queue_identifiers": [],
        "compatibility_contracts": {
            contract_id: {
                "kind": kind,
                "owner": "rebrand-audit-tests",
                "retention_reason": (
                    "The focused fixture exercises an exact compatibility "
                    "validation branch without broad runtime approval."
                ),
                "proof": proof,
                "scope": {
                    "paths": scope_paths
                    or sorted({str(entry["path"]) for entry in entries}),
                    "patterns": sorted({str(entry["pattern"]) for entry in entries}),
                    "sources": sorted({str(entry["source"]) for entry in entries}),
                },
                "coverage_sha256": (
                    coverage_sha256 or _test_coverage_digest(entries, contract_id)
                ),
            }
        },
        "entries": entries,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_schema_v5_accepts_only_kind_specific_static_proof_ids(tmp_path):
    rebrand_audit._validate_compatibility_proof(
        ROOT,
        "static:regression-fixture-contract-v1",
        "regression_fixture",
    )

    entries = [_v5_contract_entry()]
    invalid = _write_v5_contract_allowlist(
        tmp_path / "generic-static-proof.json",
        entries=entries,
        proof="static:rebrand-audit-schema-v1",
    )
    with pytest.raises(ValueError, match="closed kind-specific static proof"):
        load_allowlist(invalid)


def test_schema_v5_rejects_static_proof_for_the_wrong_contract_kind(tmp_path):
    entries = [_v5_contract_entry()]
    wrong_kind = _write_v5_contract_allowlist(
        tmp_path / "wrong-static-kind.json",
        entries=entries,
        kind="env_alias",
    )

    with pytest.raises(ValueError, match="does not prove contract kind"):
        load_allowlist(wrong_kind)


def test_schema_v5_rejects_contract_coverage_digest_tampering(tmp_path):
    entries = [_v5_contract_entry()]
    tampered = _write_v5_contract_allowlist(
        tmp_path / "tampered-coverage.json",
        entries=entries,
        coverage_sha256="0" * 64,
    )

    with pytest.raises(
        ValueError,
        match="coverage digest|canonical compatibility contract",
    ):
        load_allowlist(tampered)


def test_schema_v5_rejects_entry_outside_exact_contract_scope(tmp_path):
    entries = [_v5_contract_entry()]
    broad = _write_v5_contract_allowlist(
        tmp_path / "out-of-scope.json",
        entries=entries,
        scope_paths=["fixtures/different.py"],
    )

    with pytest.raises(
        ValueError,
        match="exact contract scope|canonical compatibility contract",
    ):
        load_allowlist(broad)


@pytest.mark.parametrize("pattern", rebrand_audit.LEGACY_PATTERNS)
def test_every_legacy_pattern_is_forbidden_on_active_ui(pattern):
    assert rebrand_audit._compatibility_is_forbidden(
        ROOT,
        "frontend/src/components/VisibleBanner.tsx",
        pattern,
        "content",
        1,
    )


@pytest.mark.parametrize("pattern", rebrand_audit.LEGACY_PATTERNS)
def test_every_legacy_pattern_is_forbidden_on_all_production_frontend_paths(
    pattern,
):
    assert rebrand_audit._compatibility_is_forbidden(
        ROOT,
        "frontend/src/lib/VisibleTip.ts",
        pattern,
        "content",
        1,
    )


@pytest.mark.parametrize(
    "path",
    [
        "frontend/src/lib/VisibleTip.ts",
        "api/lib/visible_tip.py",
        "deeper_notebook/visible_tip.py",
        "desktop/visible_tip.py",
    ],
)
def test_regression_fixture_contract_rejects_active_production_paths(
    tmp_path,
    path,
):
    context = "legacy_name = 'Open Notebook Plus'"
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(context + "\n", encoding="utf-8")
    entry = _contract_entry(
        path=path,
        pattern="Open Notebook Plus",
        context=context,
        contract="test-compatibility-v1",
    )
    allowlist_path = _write_contract_allowlist(
        tmp_path / (path.replace("/", "-") + ".json"),
        [entry],
        {
            "test-compatibility-v1": {
                "kind": "regression_fixture",
                "owner": "rebrand-audit-tests",
                "retention_reason": (
                    "The focused fixture proves runtime code cannot be "
                    "smuggled into a regression-only compatibility scope."
                ),
                "proof": "static:regression-fixture-contract-v1",
            }
        },
    )

    with pytest.raises(
        ValueError,
        match=("canonical compatibility contract|kind-specific boundary|active UI"),
    ):
        load_allowlist(allowlist_path)


def test_regression_fixture_scope_accepts_only_true_test_or_fixture_paths():
    accepted = [
        "tests/test_visible_tip.py",
        "desktop/tests/test_visible_tip.py",
        "fixtures/visible_tip.py",
        "frontend/src/lib/VisibleTip.test.ts",
        "frontend/tests/build-contract/app/page.tsx",
    ]
    rejected = [
        "frontend/src/lib/VisibleTip.ts",
        "api/lib/visible_tip.py",
        "deeper_notebook/visible_tip.py",
        "desktop/visible_tip.py",
    ]

    assert all(
        rebrand_audit._scope_path_allowed("regression_fixture", path)
        for path in accepted
    )
    assert not any(
        rebrand_audit._scope_path_allowed("regression_fixture", path)
        for path in rejected
    )


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("frontend/src/lib/features.ts", "ONP_", "frontend-env-alias-v1"),
        (
            "frontend/src/lib/theme-storage.ts",
            "onp-theme",
            "theme-storage-migration-v1",
        ),
        (
            "frontend/src/lib/api/deeper-notebook.ts",
            "onpFetch",
            "legacy-api-route-v1",
        ),
        (
            "frontend/src/lib/api/onp.ts",
            "/api/onp",
            "legacy-api-route-v1",
        ),
    ],
)
def test_canonical_mapper_allows_only_exact_frontend_compatibility_seams(
    path,
    pattern,
    expected,
):
    selectors = rebrand_audit.compatibility_selector_inventory(ROOT)
    key = next(
        key
        for key, contract_id in selectors.items()
        if key[0] == path and key[1] == pattern and contract_id == expected
    )
    occurrence = {
        field: value
        for field, value in zip(
            (
                "path",
                "pattern",
                "source",
                "line",
                "column",
                "context_sha256",
            ),
            key,
            strict=True,
        )
    }
    arbitrary = dict(occurrence, context_sha256="0" * 64)

    assert (
        rebrand_audit.compatibility_contract_for_occurrence(
            occurrence,
            root=ROOT,
            selectors=selectors,
        )
        == expected
    )
    assert (
        rebrand_audit.compatibility_contract_for_occurrence(
            arbitrary,
            root=ROOT,
            selectors=selectors,
        )
        is None
    )


_SAME_FILE_LAUNDERING_PROBES = (
    (
        "frontend/src/lib/features.ts",
        "ONP_",
        "const ONP_REVIEW_PROBE = true",
        "frontend-env-alias-v1",
        "env_alias",
        "tests/test_environment_aliases.py",
    ),
    (
        "api/routers/chat.py",
        "open_notebook",
        'CHAT_REVIEW_PROBE = "open_notebook"',
        "persisted-queue-identifier-v1",
        "persisted_identifier",
        "tests/test_persisted_queue_identifiers.py",
    ),
    (
        "deeper_notebook/domain/notebook.py",
        "open_notebook",
        'NOTEBOOK_REVIEW_PROBE = "open_notebook"',
        "persisted-queue-identifier-v1",
        "persisted_identifier",
        "tests/test_persisted_queue_identifiers.py",
    ),
)


@pytest.mark.parametrize(
    (
        "path",
        "pattern",
        "context",
        "contract_id",
        "kind",
        "proof_path",
    ),
    _SAME_FILE_LAUNDERING_PROBES,
)
def test_same_file_laundering_is_rejected_by_load_and_audit(
    tmp_path,
    path,
    pattern,
    context,
    contract_id,
    kind,
    proof_path,
):
    root = _init_tracked_repo(
        tmp_path / "repo",
        {
            path: context + "\n",
            proof_path: ("def test_exact_compatibility_selector():\n    assert True\n"),
        },
    )
    entry = _contract_entry(
        path=path,
        pattern=pattern,
        context=context,
        contract=contract_id,
    )
    (root / "scripts").mkdir()
    allowlist_path = _write_contract_allowlist(
        root / "scripts/rebrand-allowlist.json",
        [entry],
        {
            contract_id: {
                "kind": kind,
                "owner": "same-file-laundering-regression",
                "retention_reason": (
                    "The probe must not inherit compatibility merely because "
                    "it shares a path and token with an approved construct."
                ),
                "proof": f"{proof_path}::test_exact_compatibility_selector",
            }
        },
    )

    with pytest.raises(
        ValueError,
        match="canonical compatibility contract",
    ):
        load_allowlist(allowlist_path)

    key, approval = _approval(
        path=path,
        pattern=pattern,
        context=context,
        compatibility_contract=contract_id,
    )
    report = audit_repository(root, {key: approval})
    assert report["summary"]["compatibility_alias"] == 0
    assert report["summary"]["unexpected_active_identity"] == 1


@pytest.mark.parametrize(
    ("path", "pattern", "context", "_contract_id", "_kind", "_proof_path"),
    _SAME_FILE_LAUNDERING_PROBES,
)
def test_same_file_laundering_blocks_allowlist_regeneration(
    tmp_path,
    path,
    pattern,
    context,
    _contract_id,
    _kind,
    _proof_path,
):
    root = _init_tracked_repo(
        tmp_path / "repo",
        {path: context + "\n"},
    )
    (root / "scripts").mkdir()
    allowlist_path = root / "scripts/rebrand-allowlist.json"
    allowlist_path.write_text(
        json.dumps(
            {
                "schema_version": ALLOWLIST_SCHEMA_VERSION,
                "persisted_queue_identifiers": [],
                "compatibility_contracts": {},
                "entries": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="unclassified occurrence requires explicit review",
    ):
        rebrand_audit.regenerate_allowlist(root, allowlist_path)


def test_exact_selector_inventory_matches_every_declared_contract_digest():
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    selectors = rebrand_audit.compatibility_selector_inventory(ROOT)
    expected = {
        (
            entry["path"],
            entry["pattern"],
            entry["source"],
            entry["line"],
            entry["column"],
            entry["context_sha256"],
        ): entry["rationale"]["compatibility_contract"]
        for entry in payload["entries"]
        if entry["category"] == "compatibility_alias"
    }

    assert selectors == expected
    for contract_id, contract in payload["compatibility_contracts"].items():
        owned_entries = [
            entry
            for entry in payload["entries"]
            if selectors.get(
                (
                    entry["path"],
                    entry["pattern"],
                    entry["source"],
                    entry["line"],
                    entry["column"],
                    entry["context_sha256"],
                )
            )
            == contract_id
        ]
        assert (
            rebrand_audit.compatibility_coverage_digest(
                owned_entries,
                contract_id,
            )
            == contract["coverage_sha256"]
        )


def test_exact_selectors_reject_extra_literal_in_each_active_production_scope():
    selectors = rebrand_audit.compatibility_selector_inventory(ROOT)
    active_examples: dict[str, tuple[object, ...]] = {}
    for key, contract_id in selectors.items():
        path, pattern, source, _line, _column, _digest = key
        if (
            source == "content"
            and not path.startswith(("tests/", "desktop/tests/", "fixtures/"))
            and "/tests/" not in path
            and ".test." not in Path(path).name
        ):
            active_examples.setdefault(contract_id, key)

    assert active_examples
    for contract_id, key in active_examples.items():
        path, pattern, source, _line, _column, _digest = key
        context = f"selector_review_probe = {pattern!r}"
        probe = {
            "path": path,
            "pattern": pattern,
            "source": source,
            "line": 999_999,
            "column": context.index(pattern) + 1,
            "context_sha256": context_sha256(context),
        }
        assert (
            rebrand_audit.compatibility_contract_for_occurrence(
                probe,
                root=ROOT,
            )
            is None
        ), contract_id


@pytest.mark.parametrize(
    "kind",
    sorted(rebrand_audit.COMPATIBILITY_CONTRACT_KINDS),
)
def test_canonical_mapper_rejects_cross_kind_contract_laundering(
    tmp_path,
    kind,
):
    root = tmp_path / kind
    context = "visible_name = 'Open Notebook Plus'"
    active_path = "deeper_notebook/domain.py"
    proof_path = next(
        path
        for path in sorted(rebrand_audit._KIND_PROOF_PATHS[kind])
        if path.endswith(".py")
    )
    _init_tracked_repo(
        root,
        {
            active_path: context + "\n",
            proof_path: "def test_contract_proof():\n    assert True\n",
        },
    )
    contract_id = f"laundered-{kind}"
    entry = _contract_entry(
        path=active_path,
        pattern="Open Notebook Plus",
        context=context,
        contract=contract_id,
    )
    (root / "scripts").mkdir()
    allowlist_path = _write_contract_allowlist(
        root / "scripts/rebrand-allowlist.json",
        [entry],
        {
            contract_id: {
                "kind": kind,
                "owner": "adversarial-audit-test",
                "retention_reason": (
                    "The fabricated contract has a valid proof and digest but "
                    "must not override the canonical occurrence mapper."
                ),
                "proof": f"{proof_path}::test_contract_proof",
            }
        },
    )

    with pytest.raises(
        ValueError,
        match="canonical compatibility contract",
    ):
        load_allowlist(allowlist_path)


def test_audit_rechecks_canonical_contract_for_preconstructed_allowlist(
    tmp_path,
):
    path = "deeper_notebook/domain.py"
    context = "visible_name = 'Open Notebook Plus'"
    root = _init_tracked_repo(tmp_path / "repo", {path: context + "\n"})
    key, approval = _approval(
        path=path,
        pattern="Open Notebook Plus",
        context=context,
    )

    report = audit_repository(root, {key: approval})

    assert report["summary"]["compatibility_alias"] == 0
    assert report["summary"]["unexpected_active_identity"] == 2


def test_runtime_record_contract_has_exact_behavioral_inventory():
    from deeper_notebook.ai.models import DefaultModels
    from deeper_notebook.domain.content_settings import ContentSettings
    from deeper_notebook.domain.provider_config import ProviderConfig
    from deeper_notebook.domain.transformation import DefaultPrompts

    expected = {
        "deeper_notebook/ai/models.py": {
            "open_notebook:default_models",
        },
        "deeper_notebook/domain/content_settings.py": {
            "open_notebook:content_settings",
        },
        "deeper_notebook/domain/provider_config.py": {
            "open_notebook",
            "open_notebook:provider_configs",
        },
        "deeper_notebook/domain/transformation.py": {
            "open_notebook:default_prompts",
        },
    }
    actual: dict[str, set[str]] = {}
    for path in expected:
        source = (ROOT / path).read_text(encoding="utf-8")
        actual[path] = set(
            re.findall(r"[\"'](open_notebook(?::[a-z_]+)?)[\"']", source)
        )

    assert actual == expected
    assert {
        DefaultModels.record_id,
        ContentSettings.record_id,
        ProviderConfig.record_id,
        DefaultPrompts.record_id,
    } == {
        "open_notebook:default_models",
        "open_notebook:content_settings",
        "open_notebook:provider_configs",
        "open_notebook:default_prompts",
    }


def test_installation_issue_log_command_names_existing_compose_service():
    issue_path = ROOT / ".github/ISSUE_TEMPLATE/installation_issue.yml"
    issue_source = issue_path.read_text(encoding="utf-8")
    issue = yaml.safe_load(issue_source)
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    logs_field = next(item for item in issue["body"] if item.get("id") == "logs")
    description = logs_field["attributes"]["description"]
    command = re.search(
        r"docker compose logs -f ([a-zA-Z0-9_-]+)",
        description,
    )

    assert command is not None
    assert command.group(1) in compose["services"]
    assert command.group(1) == "open_notebook"

    allowlist = json.loads(
        (ROOT / "scripts/rebrand-allowlist.json").read_text(encoding="utf-8")
    )
    command_line = next(
        number
        for number, line in enumerate(issue_source.splitlines(), start=1)
        if "docker compose logs -f open_notebook" in line
    )
    image_line = next(
        number
        for number, line in enumerate(issue_source.splitlines(), start=1)
        if "image: lfnovo/open_notebook" in line
    )
    issue_entries = {
        entry["line"]: entry
        for entry in allowlist["entries"]
        if entry["path"] == ".github/ISSUE_TEMPLATE/installation_issue.yml"
        and entry["pattern"] == "open_notebook"
    }
    assert issue_entries[command_line]["category"] == "compatibility_alias"
    assert (
        issue_entries[command_line]["rationale"]["compatibility_contract"]
        == "compose-service-identifier-v1"
    )
    assert issue_entries[image_line]["category"] == "upstream_reference"
    assert issue_entries[image_line]["rationale"]["compatibility_contract"] is None


@pytest.mark.parametrize(
    ("path", "pattern"),
    [
        ("api/routers/unrelated.py", "ONP_"),
        ("api/routers/unrelated.py", "OPEN_NOTEBOOK_"),
        ("api/routers/unrelated.py", "open_notebook"),
        ("tests/test_unrelated_feature.py", "open_notebook"),
    ],
)
def test_contract_mapping_rejects_broad_env_and_import_groups(path, pattern):
    assert (
        rebrand_audit.compatibility_contract_for_occurrence(
            {
                "path": path,
                "pattern": pattern,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": "0" * 64,
            }
        )
        is None
    )


def test_persisted_database_identifier_contract_has_exact_inventory():
    migration_root = ROOT / "deeper_notebook" / "database" / "migrations"
    inventory: list[tuple[str, int]] = []
    for migration in sorted(migration_root.glob("*.surrealql")):
        for line_number, line in enumerate(
            migration.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            inventory.extend(
                (migration.name, line_number)
                for _match in re.finditer(r"\bopen_notebook\b", line)
            )

    assert inventory == [
        ("1.surrealql", 175),
        ("1.surrealql", 176),
        ("11.surrealql", 8),
        ("11_down.surrealql", 4),
        ("18.surrealql", 5),
        ("18_down.surrealql", 2),
        ("1_down.surrealql", 24),
        ("5.surrealql", 4),
        ("5.surrealql", 159),
    ]


def test_surreal_namespace_contract_has_exact_runtime_scope():
    expected_occurrences = {
        ".github/workflows/test.yml": 2,
        "desktop/db_repair.py": 2,
        "desktop/launcher.py": 5,
        "desktop/memory/_register.py": 2,
        "desktop/memory/client.py": 2,
        "desktop/memory/surreal_store.py": 2,
        "desktop/memory/tests/test_register.py": 2,
        "scripts/repair_desktop_db.sh": 2,
        "tests/integration/conftest.py": 1,
    }

    assert {
        path: len(
            re.findall(
                r"\bopen_notebook\b",
                (ROOT / path).read_text(encoding="utf-8"),
            )
        )
        for path in expected_occurrences
    } == expected_occurrences


@pytest.mark.parametrize(
    ("path", "pattern", "context"),
    [
        (
            "docs/operator-guide.md",
            "ONP_",
            "Default configuration uses ONP_SETTING.",
        ),
        (
            "frontend/src/lib/locales/en-US/index.ts",
            "Open Notebook Plus",
            "appName: 'Open Notebook Plus',",
        ),
        (
            "api/routers/filesystem.py",
            "OpenNotebook",
            "default_exports = home / 'OpenNotebookPlus-Exports'",
        ),
    ],
)
def test_allowlist_rejects_compatibility_for_active_docs_ui_and_defaults(
    tmp_path,
    path,
    pattern,
    context,
):
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(context + "\n", encoding="utf-8")
    allowlist_path = _write_contract_allowlist(
        tmp_path / "forbidden-compatibility.json",
        [
            _contract_entry(
                path=path,
                pattern=pattern,
                context=context,
            )
        ],
        {"env-alias-v1": _valid_contract()},
    )

    with pytest.raises(
        ValueError,
        match=(
            "canonical compatibility contract|active UI, documentation, "
            "or default identifier"
        ),
    ):
        load_allowlist(allowlist_path)


@pytest.mark.parametrize(
    ("path", "pattern", "expected_contract"),
    [
        (
            "deeper_notebook/environment.py",
            "ONP_",
            "env-alias-v1",
        ),
        (
            "open_notebook/_alias.py",
            "open_notebook",
            "python-import-shim-v1",
        ),
        (
            "api/main.py",
            "/api/onp",
            "legacy-api-route-v1",
        ),
        (
            "desktop/app_migration.py",
            "open-notebook-plus",
            "data-root-migration-v1",
        ),
        (
            "tests/test_environment_aliases.py",
            "ONP_",
            "env-alias-v1",
        ),
        (
            "api/routers/chat.py",
            "open_notebook",
            "persisted-queue-identifier-v1",
        ),
        (
            "api/routers/filesystem.py",
            "OpenNotebook",
            "export-directory-fallback-v1",
        ),
    ],
)
def test_compatibility_contract_mapping_uses_only_proof_backed_groups(
    path,
    pattern,
    expected_contract,
):
    selectors = rebrand_audit.compatibility_selector_inventory(ROOT)
    key = next(
        key
        for key, contract_id in selectors.items()
        if key[0] == path and key[1] == pattern and contract_id == expected_contract
    )
    occurrence = {
        field: value
        for field, value in zip(
            (
                "path",
                "pattern",
                "source",
                "line",
                "column",
                "context_sha256",
            ),
            key,
            strict=True,
        )
    }
    assert (
        rebrand_audit.compatibility_contract_for_occurrence(
            occurrence,
            root=ROOT,
            selectors=selectors,
        )
        == expected_contract
    )


@pytest.mark.parametrize(
    ("path", "pattern"),
    [
        ("tests/test_unrelated_feature.py", "Open Notebook Plus"),
        ("docs/operator-guide.md", "ONP_"),
        ("frontend/src/components/VisibleBanner.tsx", "Open Notebook Plus"),
    ],
)
def test_compatibility_contract_mapping_does_not_invent_ungrounded_contracts(
    path,
    pattern,
):
    assert (
        rebrand_audit.compatibility_contract_for_occurrence(
            {
                "path": path,
                "pattern": pattern,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": "0" * 64,
            }
        )
        is None
    )


def test_allowlist_rejects_one_character_rationale(tmp_path):
    path = "docs/history.md"
    line = "Open Notebook Plus"
    trivial = _write_allowlist(
        tmp_path / "trivial.json",
        [
            {
                "path": path,
                "pattern": line,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern=line,
                    source="content",
                    line=1,
                    column=1,
                    context=line,
                    category="historical_reference",
                    explanation="x",
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="meaningful explanation"):
        load_allowlist(trivial)


def test_allowlist_rejects_generic_rationale(tmp_path):
    path = "docs/history.md"
    line = "Open Notebook Plus"
    generic = _write_allowlist(
        tmp_path / "generic-rationale.json",
        [
            {
                "path": path,
                "pattern": line,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern=line,
                    source="content",
                    line=1,
                    column=1,
                    context=line,
                    category="historical_reference",
                    explanation=(
                        "Historical reference retained for accuracy and "
                        "migration compatibility."
                    ),
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="meaningful explanation"):
        load_allowlist(generic)


def test_allowlist_rejects_duplicate_generic_rationales(tmp_path):
    first_path = "docs/history-one.md"
    second_path = "docs/history-two.md"
    line = "Open Notebook Plus"
    generic = (
        "This exact historical product reference remains here to preserve "
        "the accuracy of the documented release record."
    )
    duplicate = _write_allowlist(
        tmp_path / "duplicate.json",
        [
            {
                "path": path,
                "pattern": line,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern=line,
                    source="content",
                    line=1,
                    column=1,
                    context=line,
                    category="historical_reference",
                    explanation=generic,
                ),
            }
            for path in (first_path, second_path)
        ],
    )

    with pytest.raises(ValueError, match="duplicate semantic explanation"):
        load_allowlist(duplicate)


@pytest.mark.parametrize(
    ("first_term", "second_term"),
    [
        ("Open Notebook Plus", "OPEN NOTEBOOK PLUS"),
        ("Open Notebook Plus", "open notebook plus"),
        ("historical_reference", "HISTORICAL_REFERENCE"),
        ("historical_reference", "Historical_Reference"),
    ],
)
def test_allowlist_rejects_semantic_duplicates_across_structural_term_case(
    tmp_path,
    first_term,
    second_term,
):
    line = "open-notebook-plus"
    explanations = [
        (
            f"The release record retains {term} wording because archive "
            "readers need the legacy desktop lineage for attribution."
        )
        for term in (first_term, second_term)
    ]
    duplicate = _write_allowlist(
        tmp_path / "case-duplicate.json",
        [
            {
                "path": path,
                "pattern": line,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(line),
                "category": "upstream_reference",
                "rationale": _rationale(
                    path=path,
                    pattern=line,
                    source="content",
                    line=1,
                    column=1,
                    context=line,
                    category="upstream_reference",
                    explanation=explanation,
                ),
            }
            for path, explanation in zip(
                ("fixtures/history-one.py", "fixtures/history-two.py"),
                explanations,
                strict=True,
            )
        ],
    )

    with pytest.raises(ValueError, match="duplicate semantic explanation"):
        load_allowlist(duplicate)


@pytest.mark.parametrize(
    "structural_term",
    [
        "DOCS/HISTORY.MD",
        "OPEN-NOTEBOOK-PLUS",
        "COMPATIBILITY_ALIAS",
    ],
)
def test_allowlist_rejects_case_variants_of_own_structural_fields(
    tmp_path,
    structural_term,
):
    path = "docs/history.md"
    line = "open-notebook-plus"
    explanation = (
        f"The release record retains {structural_term} wording because "
        "archive readers need the legacy desktop lineage for attribution."
    )
    allowlist_path = _write_allowlist(
        tmp_path / "case-structural.json",
        [
            {
                "path": path,
                "pattern": line,
                "source": "content",
                "line": 1,
                "column": 1,
                "context_sha256": context_sha256(line),
                "category": "compatibility_alias",
                "rationale": _rationale(
                    path=path,
                    pattern=line,
                    source="content",
                    line=1,
                    column=1,
                    context=line,
                    category="compatibility_alias",
                    explanation=explanation,
                ),
            }
        ],
    )

    with pytest.raises(ValueError, match="must not repeat structural"):
        load_allowlist(allowlist_path)


def test_semantic_duplicate_key_ignores_mechanical_locator_suffixes():
    first = (
        "The release record preserves the former desktop name because that "
        "was the identity shipped to users. This occurrence at "
        "docs/history-one.md:12:4 is individually pinned."
    )
    second = (
        "The release record preserves the former desktop name because that "
        "was the identity shipped to users. This occurrence at "
        "docs/history-two.md:48:9 is individually pinned."
    )

    assert rebrand_audit.semantic_explanation_key(first) == (
        rebrand_audit.semantic_explanation_key(second)
    )


def test_semantic_explanation_uses_heading_and_line_purpose_not_locator(
    tmp_path,
):
    path = "docs/history.md"
    line = "Upgrade notes retain Open Notebook Plus for archival accuracy."
    root = tmp_path / "repo"
    root.mkdir()
    target = root / path
    target.parent.mkdir(parents=True)
    target.write_text(
        "# Release History\n\n## Version 1 migration\n\n" + line + "\n",
        encoding="utf-8",
    )

    explanation = rebrand_audit.semantic_explanation_for_occurrence(
        root,
        {
            "path": path,
            "pattern": "Open Notebook Plus",
            "source": "content",
            "line": 5,
            "column": line.index("Open Notebook Plus") + 1,
            "context_sha256": context_sha256(line),
        },
        "historical_reference",
    )

    assert "Version 1 migration" in explanation
    assert "archival accuracy" in explanation
    assert path not in explanation
    assert "Open Notebook Plus" not in explanation
    assert "historical_reference" not in explanation
    assert not re.search(r":[0-9]+:[0-9]+", explanation)


def test_semantic_explanation_does_not_repeat_bare_path_with_different_case(
    tmp_path,
):
    path = "Makefile"
    line = "LEGACY_PACKAGE := open_notebook"
    root = tmp_path / "repo"
    root.mkdir()
    (root / path).write_text(line + "\n", encoding="utf-8")

    explanation = rebrand_audit.semantic_explanation_for_occurrence(
        root,
        {
            "path": path,
            "pattern": "open_notebook",
            "source": "content",
            "line": 1,
            "column": line.index("open_notebook") + 1,
            "context_sha256": context_sha256(line),
        },
        "compatibility_alias",
    )

    assert path.casefold() not in explanation.casefold()


def test_allowlist_regeneration_is_deterministic_and_semantic(tmp_path):
    path = "docs/history.md"
    line = "Upgrade notes retain Open Notebook Plus for archival accuracy."
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {path: (f"# Release History\n\n## Version 1 migration\n\n{line}\n")},
    )
    allowlist_path = _write_allowlist(
        tmp_path / "allowlist.json",
        [
            {
                "path": path,
                "pattern": "Open Notebook Plus",
                "source": "content",
                "line": 5,
                "column": line.index("Open Notebook Plus") + 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path=path,
                    pattern="Open Notebook Plus",
                    source="content",
                    line=5,
                    column=line.index("Open Notebook Plus") + 1,
                    context=line,
                    category="historical_reference",
                    explanation=(
                        "The release history preserves the former desktop "
                        "identity because the migration record depends on it."
                    ),
                ),
            }
        ],
    )

    first = rebrand_audit.regenerate_allowlist(repo, allowlist_path)
    first_bytes = allowlist_path.read_bytes()
    second = rebrand_audit.regenerate_allowlist(repo, allowlist_path)

    assert first == second
    assert allowlist_path.read_bytes() == first_bytes
    entry = first["entries"][0]
    assert entry["rationale"]["pattern"] == entry["pattern"]
    assert entry["rationale"]["category"] == entry["category"]
    assert "Version 1 migration" in entry["rationale"]["explanation"]


def test_allowlist_regeneration_rejects_unselected_same_file_env_alias(
    tmp_path,
):
    path = "deeper_notebook/environment.py"
    line = "legacy_prefix = 'ONP_SETTING'"
    repo = _init_tracked_repo(tmp_path / "repo", {path: line + "\n"})
    allowlist_path = _write_contract_allowlist(
        tmp_path / "allowlist.json",
        [
            _contract_entry(
                path=path,
                pattern="ONP_",
                context=line,
            )
        ],
        {"env-alias-v1": _valid_contract()},
    )

    with pytest.raises(
        ValueError,
        match="uncontracted compatibility groups require review",
    ):
        rebrand_audit.regenerate_allowlist(repo, allowlist_path)


def test_allowlist_regeneration_surfaces_ungrounded_compatibility_groups(
    tmp_path,
):
    path = "tests/test_unrelated_feature.py"
    line = "legacy_label = 'Open Notebook Plus'"
    repo = _init_tracked_repo(tmp_path / "repo", {path: line + "\n"})
    allowlist_path = _write_contract_allowlist(
        tmp_path / "allowlist.json",
        [
            _contract_entry(
                path=path,
                pattern="Open Notebook Plus",
                context=line,
            )
        ],
        {"env-alias-v1": _valid_contract()},
    )

    with pytest.raises(
        ValueError,
        match=r"uncontracted compatibility groups.*tests.*Open Notebook Plus",
    ):
        rebrand_audit.regenerate_allowlist(repo, allowlist_path)


def test_repository_category_examples_match_their_actual_roles():
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    entries = payload["entries"]

    assert any(
        entry["path"] == "deeper_notebook/identity.py"
        and entry["pattern"] == "open_notebook"
        and entry["category"] == "compatibility_alias"
        for entry in entries
    )
    assert any(
        entry["path"] == "desktop/__init__.py"
        and entry["pattern"] == "open-notebook-plus"
        and entry["category"] == "historical_reference"
        for entry in entries
    )
    logging_aliases = [
        entry
        for entry in entries
        if entry["path"] == "deeper_notebook/logging.py"
        and entry["line"] in {18, 19}
        and entry["pattern"] in {"OPEN_NOTEBOOK_", "ONP_"}
    ]
    assert logging_aliases == []
    assert any(
        entry["path"] == "README.upstream.md"
        and entry["category"] == "upstream_reference"
        for entry in entries
    )
    assert any(
        entry["path"] == ".github/workflows/build-desktop.yml"
        and entry["pattern"] == "open-notebook-plus"
        and entry["category"] == "compatibility_alias"
        for entry in entries
    )
    assert any(
        entry["path"] == "CHANGELOG.md" and entry["category"] == "historical_reference"
        for entry in entries
    )
    assert any(
        entry["path"] == "docs/7-DEVELOPMENT/maintainer-guide.md"
        and entry["category"] == "migration_documentation"
        for entry in entries
    )
    assert any(
        entry["path"] == "Makefile" and entry["category"] == "upstream_reference"
        for entry in entries
    )


def test_approved_broad_builtin_suppresses_only_its_safe_nested_pattern(
    tmp_path,
):
    line = "Historical release: Open Notebook Plus"
    repo = _init_tracked_repo(tmp_path / "repo", {"history.md": f"{line}\n"})
    key, approval = _approval(
        path="history.md",
        pattern="Open Notebook Plus",
        context=line,
        category="historical_reference",
        rationale=(
            "This exact product name identifies the software shipped in the "
            "recorded historical release."
        ),
    )

    report = audit_repository(repo, {key: approval})

    assert report["summary"]["historical_reference"] == 1
    assert report["summary"]["unexpected_active_identity"] == 0


def test_logging_contract_prefers_canonical_names_and_container_path(
    monkeypatch,
):
    assert SETTINGS["DEEPER_NOTEBOOK_LOG_DIR"].precedence == (
        "DEEPER_NOTEBOOK_LOG_DIR",
        "DN_LOG_DIR",
        "OPEN_NOTEBOOK_LOG_DIR",
        "ONP_LOG_DIR",
    )
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    for name in SETTINGS["DEEPER_NOTEBOOK_LOG_DIR"].precedence:
        monkeypatch.delenv(name, raising=False)

    assert default_log_dir() == Path("/var/log/deeper-notebook")


def test_active_logging_provision_maintainer_and_wrapper_copy_is_canonical():
    logging_source = (ROOT / "deeper_notebook/logging.py").read_text(encoding="utf-8")
    provision_source = (ROOT / "deeper_notebook/ai/provision.py").read_text(
        encoding="utf-8"
    )
    maintainer_source = (ROOT / "docs/7-DEVELOPMENT/maintainer-guide.md").read_text(
        encoding="utf-8"
    )
    wrapper_source = (ROOT / "desktop/__init__.py").read_text(encoding="utf-8")

    assert "DEEPER_NOTEBOOK_LOG_LEVEL" in logging_source
    assert "DEEPER_NOTEBOOK_LOG_JSON" in logging_source
    assert "deprecated spellings" in logging_source
    assert "DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT" in provision_source
    assert "DEEPER_NOTEBOOK_CLOUD_CHAT_MODEL_ID" in provision_source
    assert "Deprecated aliases accepted during migration" in provision_source
    assert "## Deeper Notebook Hardening Reference" in maintainer_source
    assert "`DN_STUDIO_PAGE_TIMEOUT_SEC`" in maintainer_source
    assert "### Deprecated environment aliases" in maintainer_source
    assert wrapper_source.startswith('"""Deeper Notebook desktop wrapper.')


def test_same_file_legacy_injection_is_not_covered_by_existing_approval(tmp_path):
    line = "Historical release: Open Notebook Plus"
    repo = _init_tracked_repo(tmp_path / "repo", {"history.md": f"{line}\n"})
    allowlist_path = _write_allowlist(
        tmp_path / "allowlist.json",
        [
            {
                "path": "history.md",
                "pattern": "Open Notebook Plus",
                "source": "content",
                "line": 1,
                "column": line.index("Open Notebook Plus") + 1,
                "context_sha256": context_sha256(line),
                "category": "historical_reference",
                "rationale": _rationale(
                    path="history.md",
                    pattern="Open Notebook Plus",
                    source="content",
                    line=1,
                    column=line.index("Open Notebook Plus") + 1,
                    context=line,
                    category="historical_reference",
                    explanation=(
                        "This exact product name identifies the software "
                        "shipped in the recorded historical release."
                    ),
                ),
            }
        ],
    )
    command = [
        sys.executable,
        str(AUDIT_SCRIPT),
        "--root",
        str(repo),
        "--allowlist",
        str(allowlist_path),
        "--check",
    ]

    assert subprocess.run(command, capture_output=True, check=False).returncode == 0

    (repo / "history.md").write_text(
        f"{line}\nActive copy: Open Notebook Plus\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "history.md"], check=True)

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 1, result.stdout + result.stderr


def test_active_user_copy_uses_canonical_paths_and_settings():
    expected = {
        "frontend/src/app/(dashboard)/page.tsx": ("~/.deeper-notebook/",),
        "frontend/src/lib/api/client.ts": ("~/.deeper-notebook/logs/api.log",),
        "docs/4-AI-PROVIDERS/local-models-tool-calling.md": (
            "DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID",
            "~/.deeper-notebook/launcher.env",
        ),
        "docs/3-USER-GUIDE/free-mcp-servers-web-search.md": (
            "DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID",
            "~/.deeper-notebook/logs/launcher.log",
        ),
    }
    forbidden = (
        "~/.open-notebook-plus/",
        "OPEN_NOTEBOOK_LOCAL_CHAT_MODEL_ID",
    )

    for path, snippets in expected.items():
        source = (ROOT / path).read_text(encoding="utf-8")
        for snippet in snippets:
            assert snippet in source, f"{path}: {snippet}"
        for legacy in forbidden:
            assert legacy not in source, f"{path}: {legacy}"


def test_current_runtime_descriptions_use_deeper_notebook_name():
    expected_copy = {
        "api/routers/auth.py": ("Authentication router for Deeper Notebook API."),
        "api/updates_service.py": ("Deeper Notebook is privacy-first"),
        "deeper_notebook/exceptions.py": (
            "Base exception class for Deeper Notebook errors."
        ),
        "deeper_notebook/domain/__init__.py": ("Domain models for Deeper Notebook."),
        "deeper_notebook/utils/__init__.py": ("Utils package for Deeper Notebook."),
        "deeper_notebook/utils/token_utils.py": (
            "Token utilities for Deeper Notebook."
        ),
        "deeper_notebook/utils/context_builder.py": (
            "Generic ContextBuilder for the Deeper Notebook project."
        ),
        "deeper_notebook/utils/embedding.py": (
            "Unified embedding utilities for Deeper Notebook."
        ),
        "deeper_notebook/utils/text_utils.py": ("Text utilities for Deeper Notebook."),
        "deeper_notebook/utils/chunking.py": (
            "Chunking utilities for Deeper Notebook."
        ),
        "deeper_notebook/utils/version_utils.py": (
            "Version utilities for Deeper Notebook."
        ),
        "deeper_notebook/local_models/manifest.py": (
            "Most helpers let Deeper Notebook"
        ),
    }

    for path, expected in expected_copy.items():
        source = (ROOT / path).read_text(encoding="utf-8")
        assert expected in source, path


def test_podcast_default_profile_names_use_deeper_notebook():
    source = (ROOT / "api/routers/podcasts.py").read_text(encoding="utf-8")
    from desktop.auto_register.episode_profile import _PRESETS

    assert "Deeper Notebook Local" in source
    assert "Open Notebook Plus Local" not in source
    assert _PRESETS[0]["name"] == "Deeper Notebook Local"


def test_current_bootstrap_and_connection_test_copy_use_deeper_notebook():
    bootstrap = (ROOT / "desktop/bootstrap.py").read_text(encoding="utf-8")
    connection_tester = (ROOT / "deeper_notebook/ai/connection_tester.py").read_text(
        encoding="utf-8"
    )

    assert "open 'Deeper Notebook.app'" in bootstrap
    assert 'text="Hello from Deeper Notebook"' in connection_tester


def test_current_cli_and_development_banners_use_deeper_notebook():
    expected_copy = {
        "Makefile": (
            "Starting Deeper Notebook",
            "Stopping all Deeper Notebook services",
            "Deeper Notebook Service Status",
        ),
        "run_api.py": (
            "Startup script for Deeper Notebook API server.",
            "Starting Deeper Notebook API server",
        ),
        "dev-init.sh": (
            "Development environment startup for Deeper Notebook",
            "=== Deeper Notebook Dev Startup ===",
        ),
        ".pre-commit-config.yaml": ("Pre-commit hooks for Deeper Notebook",),
        ".env.example": ("default ~/.deeper-notebook/logs",),
    }

    for path, snippets in expected_copy.items():
        source = (ROOT / path).read_text(encoding="utf-8")
        for snippet in snippets:
            assert snippet in source, f"{path}: {snippet}"


def test_current_operator_scripts_use_deeper_notebook_copy_and_compat_paths():
    expected_copy = {
        "commands/__init__.py": ("Surreal-commands integration for Deeper Notebook.",),
        "scripts/upstream_sync_guard.sh": (
            "Safe upstream integration guard for Deeper Notebook.",
            "deeper-notebook-upstream-sync-",
        ),
        "scripts/ralph.sh": ("autonomous AI agent loop for Deeper Notebook",),
        "scripts/backup_restore.py": (
            "Backup + restore for the Deeper Notebook data",
            "DEEPER_NOTEBOOK_DATA_DIR",
        ),
        "scripts/create-signing-identity.sh": ("Deeper Notebook Local",),
        "scripts/live_source_ingestion_smoke.py": (
            "running native Deeper Notebook app",
            "Deeper Notebook live ingestion smoke marker",
        ),
        "scripts/verify-chat-platform.sh": (
            "Deeper Notebook v0.8.0",
            "DEEPER_NOTEBOOK_PASSWORD",
            "DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT",
        ),
    }

    for path, snippets in expected_copy.items():
        source = (ROOT / path).read_text(encoding="utf-8")
        for snippet in snippets:
            assert snippet in source, f"{path}: {snippet}"

    repair = (ROOT / "scripts/repair_desktop_db.sh").read_text(encoding="utf-8")
    assert "/Applications/Deeper Notebook.app/" in repair
    assert "/Applications/Open Notebook Plus.app/" in repair
    assert "${HOME}/.deeper-notebook" in repair
    assert "${HOME}/.open-notebook-plus" in repair


def test_visible_locale_configuration_examples_use_canonical_short_prefix():
    locale_root = ROOT / "frontend" / "src" / "lib" / "locales"
    locale_files = sorted(locale_root.glob("*/index.ts"))
    assert locale_files

    for path in locale_files:
        source = path.read_text(encoding="utf-8")
        assert "ONP_" not in source, path
        assert "OPEN_NOTEBOOK_LOCAL_DRAFT_" not in source, path
        assert "DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH" in source, path
        assert "DEEPER_NOTEBOOK_LOCAL_DRAFT_N_PREDICT" in source, path
        assert "DN_CHAT_LLM_CTX" in source, path
        assert "DN_CHAT_LLM_CTX_MAX" in source, path
        assert "DN_METRICS_AUTH_TOKEN" in source, path


def test_audit_scans_tracked_paths_and_content(tmp_path):
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {"legacy/open-notebook-plus.txt": "Open Notebook Plus\n"},
    )

    report = audit_repository(repo, {})
    unexpected = report["categories"]["unexpected_active_identity"]

    assert any(
        match["source"] == "path" and match["path"] == "legacy/open-notebook-plus.txt"
        for match in unexpected
    )
    assert any(
        match["source"] == "content"
        and match["pattern"] == "Open Notebook Plus"
        and match["line"] == 1
        for match in unexpected
    )


def test_audit_skips_only_its_self_referential_allowlist_metadata(tmp_path):
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {
            "scripts/rebrand-allowlist.json": ('{"pattern": "Open Notebook Plus"}\n'),
            "active.txt": "Deeper Notebook\n",
        },
    )

    report = audit_repository(repo, {})

    assert not any(
        match["path"] == "scripts/rebrand-allowlist.json"
        for matches in report["categories"].values()
        for match in matches
    )


def test_exact_context_does_not_hide_active_imports(tmp_path):
    compatibility_line = '@command("work", app="open_notebook")'
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {
            "commands/example_commands.py": (
                "from open_notebook.domain import Note\n"
                "from surreal_commands import command\n"
                f"{compatibility_line}\n"
                "def work():\n"
                "    return None\n"
            )
        },
    )
    key, approval = _approval(
        path="commands/example_commands.py",
        pattern="open_notebook",
        context=compatibility_line,
        line=3,
        compatibility_contract="persisted-queue-identifier-v1",
    )
    allowlist = {key: approval}

    report = audit_repository(repo, allowlist)

    assert report["categories"]["compatibility_alias"] == [
        {
            "path": "commands/example_commands.py",
            "pattern": "open_notebook",
            "source": "content",
            "line": 3,
            "column": compatibility_line.index("open_notebook") + 1,
            "context_sha256": context_sha256(compatibility_line),
        }
    ]
    assert [
        match["line"]
        for match in report["categories"]["unexpected_active_identity"]
        if match["pattern"] == "open_notebook"
    ] == [1]


def test_exact_context_does_not_hide_distinct_same_line_active_occurrence(tmp_path):
    line = 'legacy_module = open_notebook; submit_command("open_notebook", "work", {})'
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {"commands/example_commands.py": f"{line}\n"},
    )
    key, approval = _approval(
        path="commands/example_commands.py",
        pattern="open_notebook",
        context=line,
        column=line.rindex("open_notebook") + 1,
        compatibility_contract="persisted-queue-identifier-v1",
    )
    allowlist = {key: approval}

    report = audit_repository(repo, allowlist)

    assert len(report["categories"]["compatibility_alias"]) == 1
    assert [
        match
        for match in report["categories"]["unexpected_active_identity"]
        if match["pattern"] == "open_notebook"
    ] == [
        {
            "path": "commands/example_commands.py",
            "pattern": "open_notebook",
            "source": "content",
            "line": 1,
            "column": line.index("open_notebook") + 1,
            "context_sha256": context_sha256(line),
        }
    ]


def test_repository_rebrand_audit_has_no_unexpected_active_identity():
    result = subprocess.run(
        [sys.executable, "scripts/rebrand_audit.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_audit_reports_stale_entries_and_skips_binary_contents(tmp_path):
    repo = _init_tracked_repo(
        tmp_path / "repo",
        {
            "binary.bin": b"\0Open Notebook Plus",
            "invalid.bin": b"\xffOpen Notebook Plus",
            "clean.txt": "Deeper Notebook\n",
        },
    )
    key, approval = _approval(
        path="missing.md",
        pattern="Open Notebook",
        context="Open Notebook",
        category="historical_reference",
        rationale="Historical product name retained for accuracy.",
    )
    allowlist = {key: approval}

    report = audit_repository(repo, allowlist)

    assert report["stale_allowlist"] == [
        {
            "path": "missing.md",
            "pattern": "Open Notebook",
            "source": "content",
            "line": 1,
            "column": 1,
            "context_sha256": context_sha256("Open Notebook"),
            "category": "historical_reference",
            "rationale": approval.rationale.as_dict(),
        }
    ]
    assert not any(
        match["path"] in {"binary.bin", "invalid.bin"}
        for matches in report["categories"].values()
        for match in matches
    )


def test_check_exits_for_unexpected_identity_and_passes_for_clean_repo(tmp_path):
    repo = _init_tracked_repo(tmp_path / "repo", {"product.txt": "Deeper Notebook\n"})
    allowlist_path = _write_allowlist(tmp_path / "allowlist.json", [])
    command = [
        sys.executable,
        str(AUDIT_SCRIPT),
        "--root",
        str(repo),
        "--allowlist",
        str(allowlist_path),
        "--check",
    ]

    assert subprocess.run(command, capture_output=True, check=False).returncode == 0

    (repo / "product.txt").write_text("Open Notebook Plus\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "product.txt"], check=True)

    assert subprocess.run(command, capture_output=True, check=False).returncode == 1


def test_vault_legacy_route_selector_rejects_an_unapproved_new_route(tmp_path):
    legacy_api_namespace = "/" + "api/" + "onp"
    approved_line = f'    assert test_client.get("{legacy_api_namespace}/vaults").status_code == 404'
    unapproved_line = f'    assert test_client.get("{legacy_api_namespace}/unapproved").status_code == 404'
    root = _init_tracked_repo(
        tmp_path / "repo",
        {
            "tests/test_vault_api.py": (
                "def test_vault_routes_are_read_only():\n"
                f"{approved_line}\n"
                f"{unapproved_line}\n"
            )
        },
    )
    selectors = rebrand_audit.compatibility_selector_inventory(root)
    occurrences = rebrand_audit._selector_occurrences_for_path(
        root, "tests/test_vault_api.py"
    )
    approved = next(
        occurrence
        for occurrence in occurrences
        if occurrence["pattern"] == legacy_api_namespace and occurrence["line"] == 2
    )
    unapproved = next(
        occurrence
        for occurrence in occurrences
        if occurrence["pattern"] == legacy_api_namespace and occurrence["line"] == 3
    )

    assert (
        rebrand_audit.compatibility_contract_for_occurrence(
            approved, root=root, selectors=selectors
        )
        == "legacy-api-route-v1"
    )
    assert (
        rebrand_audit.compatibility_contract_for_occurrence(
            unapproved, root=root, selectors=selectors
        )
        is None
    )
    report = audit_repository(root, {})
    assert any(
        occurrence["path"] == "tests/test_vault_api.py"
        and occurrence["pattern"] == legacy_api_namespace
        and occurrence["line"] == 3
        for occurrence in report["categories"]["unexpected_active_identity"]
    )


def test_frontend_alias_contract_survives_additional_canonical_feature_flag():
    selectors = rebrand_audit.compatibility_selector_inventory(ROOT)
    legacy_alias_pattern = next(
        pattern
        for pattern in LEGACY_PATTERNS
        if pattern.endswith("_") and len(pattern) == 4
    )
    feature_aliases = [
        contract_id
        for key, contract_id in selectors.items()
        if key[0] == "frontend/src/lib/features.ts" and key[1] == legacy_alias_pattern
    ]

    assert len(feature_aliases) == 4
    assert set(feature_aliases) == {"frontend-env-alias-v1"}


def test_source_visual_environment_alias_contract_is_closed():
    selectors = rebrand_audit.compatibility_selector_inventory(ROOT)
    source_lines = (
        ROOT / "tests/test_environment_aliases.py"
    ).read_text(encoding="utf-8").splitlines()
    legacy_alias_pattern = next(
        pattern
        for pattern in LEGACY_PATTERNS
        if pattern.endswith("_") and len(pattern) == 4
    )
    expected_lines = {
        '        ("OPEN_NOTEBOOK_SOURCE_VISUALS_ENABLED", "0", True),',
        '        ("ONP_SOURCE_VISUALS_ENABLED", "1", True),',
        '        "OPEN_NOTEBOOK_SOURCE_VISUALS_ENABLED",',
        '        "ONP_SOURCE_VISUALS_ENABLED",',
        '        "OPEN_NOTEBOOK_SOURCE_VISUALS_ENABLED": "0",',
        '        "ONP_SOURCE_VISUALS_ENABLED": "1",',
    }
    source_visual_aliases = [
        rebrand_audit.compatibility_contract_for_occurrence(
            occurrence, root=ROOT, selectors=selectors
        )
        for occurrence in rebrand_audit._selector_occurrences_for_path(
            ROOT, "tests/test_environment_aliases.py"
        )
        if occurrence["pattern"] in {"OPEN_NOTEBOOK_", legacy_alias_pattern}
        and source_lines[int(occurrence["line"]) - 1] in expected_lines
    ]

    assert len(source_visual_aliases) == 6
    assert set(source_visual_aliases) == {"env-alias-v1"}


def test_current_frontend_compatibility_seams_use_existing_contracts():
    selectors = rebrand_audit.compatibility_selector_inventory(ROOT)
    legacy_alias_pattern = next(
        pattern
        for pattern in LEGACY_PATTERNS
        if pattern.endswith("_") and len(pattern) == 4
    )
    theme_alias_pattern = next(
        pattern for pattern in LEGACY_PATTERNS if pattern.endswith("-theme")
    )
    expected = {
        (
            "frontend/src/lib/features.ts",
            legacy_alias_pattern,
            "frontend-env-alias-v1",
        ),
        (
            "frontend/src/lib/features.test.ts",
            legacy_alias_pattern,
            "frontend-env-alias-v1",
        ),
        (
            "frontend/src/lib/features-build-contract.test.ts",
            legacy_alias_pattern,
            "frontend-env-alias-v1",
        ),
        (
            "frontend/src/lib/theme-script.ts",
            theme_alias_pattern,
            "theme-storage-migration-v1",
        ),
        (
            "frontend/src/lib/theme-script.test.ts",
            theme_alias_pattern,
            "theme-storage-migration-v1",
        ),
    }

    for path, pattern, contract_id in expected:
        occurrences = {
            rebrand_audit._selector_key(occurrence)
            for occurrence in rebrand_audit._selector_occurrences_for_path(
                ROOT,
                path,
            )
            if occurrence["pattern"] == pattern
        }
        assert occurrences
        assert all(selectors.get(key) == contract_id for key in occurrences)
