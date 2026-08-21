import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_repository_tracks_no_python_bytecode() -> None:
    result = subprocess.run(
        ["git", "ls-files", "*.pyc"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == []
