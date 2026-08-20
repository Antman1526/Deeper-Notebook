"""Run the locked SkillOpt integration suite when the optional wheel is present."""

from __future__ import annotations

import argparse
import ast
import importlib.metadata
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = PROJECT_ROOT / "desktop" / "requirements.lock"
TEST_PATH = PROJECT_ROOT / "tests" / "test_v0_8_68_prompt_optimizer.py"
EXPECTED_TESTS = 19


def locked_skillopt_requirement(lock_path: Path) -> str:
    """Return the one exact SkillOpt pin from the desktop lock."""
    pins = [
        line.strip()
        for line in lock_path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("skillopt==")
    ]
    if pins != ["skillopt==0.1.0"]:
        raise RuntimeError(
            f"desktop lock must contain exactly skillopt==0.1.0; found {pins}"
        )
    return pins[0]


def expected_test_count(test_path: Path = TEST_PATH) -> int:
    """Count the top-level integration tests in the pinned contract module."""
    tree = ast.parse(
        test_path.read_text(encoding="utf-8"),
        filename=str(test_path),
    )
    count = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in tree.body
    )
    if count != EXPECTED_TESTS:
        raise RuntimeError(
            f"SkillOpt integration contract must contain {EXPECTED_TESTS} tests; "
            f"found {count}"
        )
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-installed",
        action="store_true",
        help="fail instead of skipping when the optional SkillOpt wheel is absent",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requirement = locked_skillopt_requirement(LOCK_PATH)
    expected_test_count()
    locked_version = requirement.partition("==")[2]
    try:
        installed_version = importlib.metadata.version("skillopt")
    except importlib.metadata.PackageNotFoundError:
        if args.require_installed:
            print(
                f"{requirement} is required for this integration path",
                file=sys.stderr,
            )
            return 2
        print(f"SKIP: optional {requirement} is not installed")
        return 0
    if installed_version != locked_version:
        print(
            f"installed skillopt=={installed_version}; expected {requirement}",
            file=sys.stderr,
        )
        return 2
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(TEST_PATH),
            "-q",
        ],
        cwd=PROJECT_ROOT,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
