"""Run backend tests in bounded batches for desktop release workflows."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def discover_tests(tests_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in tests_dir.rglob("test_*.py")
        if "integration" not in path.parts and path.is_file()
    )


def run_batches(
    test_files: list[Path],
    *,
    project_root: Path,
    batch_size: int,
    timeout_seconds: int,
    junit_output_dir: Path,
) -> None:
    if not test_files:
        raise RuntimeError("No non-integration backend test files were found")
    junit_output_dir.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(test_files), batch_size):
        batch = test_files[start : start + batch_size]
        end = start + len(batch)
        print(
            f"Running backend test batch {start + 1}-{end} of {len(test_files)}",
            flush=True,
        )
        try:
            junit_report = junit_output_dir / f"backend-{start + 1:03d}-{end:03d}.xml"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    *map(str, batch),
                    "-q",
                    f"--junitxml={junit_report}",
                ],
                cwd=project_root,
                check=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Backend test batch {start + 1}-{end} exceeded {timeout_seconds}s"
            ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--junit-output-dir",
        type=Path,
        default=Path("test-results/backend"),
        help="Directory for per-batch JUnit reports retained by release CI.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1 or args.timeout_seconds < 1:
        raise ValueError("batch-size and timeout-seconds must be positive")
    project_root = Path(__file__).resolve().parents[2]
    run_batches(
        discover_tests(project_root / "tests"),
        project_root=project_root,
        batch_size=args.batch_size,
        timeout_seconds=args.timeout_seconds,
        junit_output_dir=(project_root / args.junit_output_dir).resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
