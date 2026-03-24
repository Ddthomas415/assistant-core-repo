from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_cli_starts_and_exits(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistant.cli",
            "--session-dir",
            str(session_dir),
        ],
        input="exit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Session:" in result.stdout
    assert "Type 'exit' or 'quit' to stop." in result.stdout


def test_cli_resume_missing_session_fails_cleanly(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistant.cli",
            "--session-dir",
            str(session_dir),
            "--resume",
            "missing-session-id",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "missing-session-id" in result.stderr or "missing-session-id" in result.stdout
