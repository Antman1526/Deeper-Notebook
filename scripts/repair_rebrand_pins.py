#!/usr/bin/env python3
"""Repair the rebrand allowlist after an ordinary edit shifts pinned lines.

WHY THIS EXISTS

`scripts/rebrand-allowlist.json` pins each approval to
`(path, pattern, source, line, column, sha256(raw line))`. Any edit that adds or
removes a line ABOVE a pinned occurrence invalidates that pin, and the failure
cascades through three separate gates that each report something different:

  1. `--check` reports stale entries.
  2. `_PINNED_SELECTOR_INVENTORY_SHA256` (hard-coded in rebrand_audit.py) is a
     digest over every compatibility entry's key. Stale keys make it mismatch,
     the pinned inventory then loads EMPTY, and `--regenerate` refuses with
     "uncontracted compatibility groups require review".
  3. Each contract's `coverage_sha256` is computed the same way and goes stale
     for the same reason.

Hitting this is not rare. It fired three times in a single working session —
once relocating 416 pins for a one-line workflow edit. Re-keying the allowlist
so it stops happening is ROADMAP §2.1; until then, this is the repair, and it
exists as an executable rather than prose so nobody has to rediscover the order.

THE ORDER MATTERS. Relocate pins, THEN recompute the inventory digest, THEN the
coverage digests, THEN regenerate. Doing the digest first bakes in the stale
keys; regenerating first refuses outright.

USAGE

    uv run python scripts/repair_rebrand_pins.py          # repair
    uv run python scripts/repair_rebrand_pins.py --check  # report, change nothing

A pin is only moved when the file still contains a line whose digest matches the
one recorded — that is proof the approval still describes the same content.
Anything that fails that proof is reported and left alone, because it means the
content genuinely changed and a human should look at it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "scripts" / "rebrand-allowlist.json"
AUDIT = ROOT / "scripts" / "rebrand_audit.py"

sys.path.insert(0, str(ROOT / "scripts"))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relocate(payload: dict, *, dry_run: bool) -> tuple[int, list[str]]:
    """Move pins whose content still exists at a different line."""
    cache: dict[str, list[str]] = {}

    def lines_of(rel: str) -> list[str]:
        if rel not in cache:
            target = ROOT / rel
            cache[rel] = (
                target.read_text(encoding="utf-8").splitlines()
                if target.exists()
                else []
            )
        return cache[rel]

    moved = 0
    unresolved: list[str] = []
    for entry in payload["entries"]:
        if entry.get("source") != "content" or entry.get("line") is None:
            continue
        rel, line, digest = entry["path"], entry["line"], entry["context_sha256"]
        lines = lines_of(rel)
        if lines and line <= len(lines) and _sha(lines[line - 1]) == digest:
            continue  # still accurate
        found = next(
            (i for i, text in enumerate(lines, 1) if _sha(text) == digest), None
        )
        if found is None:
            # Content changed, not merely moved. That is a real review item.
            unresolved.append(f"{rel}:{line}")
            continue
        moved += 1
        if not dry_run:
            entry["line"] = found
            rationale = entry.get("rationale") or {}
            if "line" in rationale:
                rationale["line"] = found
    return moved, unresolved


def _inventory_digest(payload: dict) -> str:
    """Recompute the pinned-selector digest using the audit's own encoding.

    Imported rather than reimplemented on purpose: a hand-rolled copy is exactly
    how this gets mis-repaired, and an empty pinned inventory looks like success
    right up until nothing is classified.
    """
    import rebrand_audit as ra

    encoded: list[list[object]] = []
    for entry in payload["entries"]:
        if entry.get("category") != "compatibility_alias":
            continue
        rationale = entry.get("rationale")
        contract = (
            rationale.get("compatibility_contract")
            if isinstance(rationale, dict)
            else None
        )
        key = ra._selector_key(entry)
        if not isinstance(contract, str) or key is None:
            raise SystemExit(f"unencodable compatibility entry: {entry.get('path')}")
        if key[0] in ra._SEMANTIC_SELECTOR_PATHS:
            continue
        if contract == "persisted-queue-identifier-v1" and not key[0].startswith(
            "tests/"
        ):
            continue
        encoded.append([*key, contract])

    encoded.sort(key=lambda i: tuple("" if v is None else str(v) for v in i))
    return hashlib.sha256(
        json.dumps(encoded, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="report what would change; write nothing"
    )
    args = parser.parse_args()

    payload = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    moved, unresolved = _relocate(payload, dry_run=args.check)

    print(f"pins relocated: {moved}")
    if unresolved:
        print(f"content changed (needs review): {len(unresolved)}")
        for item in unresolved[:10]:
            print(f"    {item}")

    if args.check:
        print("--check: nothing written")
        return 1 if unresolved else 0

    ALLOWLIST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    # Inventory digest — must follow relocation, must precede regeneration.
    digest = _inventory_digest(payload)
    audit_source = AUDIT.read_text(encoding="utf-8")
    import re

    current = re.search(r'"([0-9a-f]{64})"', audit_source)
    if current and current.group(1) != digest:
        AUDIT.write_text(audit_source.replace(current.group(1), digest, 1))
        print(f"inventory digest updated -> {digest[:16]}…")

    import rebrand_audit as ra

    importlib_reload = __import__("importlib").reload
    ra = importlib_reload(ra)
    loaded = len(ra._pinned_selector_inventory(ROOT))
    print(f"pinned selectors loaded: {loaded}")
    if loaded == 0:
        print("  ERROR: empty inventory means the digest is still wrong")
        return 1

    # Per-contract coverage digests.
    payload = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    updated = 0
    for contract_id, contract in payload["compatibility_contracts"].items():
        actual = ra.compatibility_coverage_digest(payload["entries"], contract_id)
        if contract.get("coverage_sha256") != actual:
            contract["coverage_sha256"] = actual
            updated += 1
    if updated:
        ALLOWLIST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"coverage digests updated: {updated}")

    subprocess.run(
        [sys.executable, str(AUDIT), "--regenerate"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    result = subprocess.run(
        [sys.executable, str(AUDIT), "--check"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    ok = result.returncode == 0
    print(f"identity audit: {'PASS' if ok else 'FAIL'}")
    if not ok:
        sys.stderr.write(result.stderr.decode()[-800:])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
