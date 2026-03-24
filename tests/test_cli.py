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


def test_cli_resume_existing_session_loads_same_session_id(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"

    first = subprocess.run(
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

    session_line = next(
        line for line in first.stdout.splitlines() if line.startswith("Session:")
    )
    session_id = session_line.split("Session:", 1)[1].strip()

    second = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistant.cli",
            "--session-dir",
            str(session_dir),
            "--resume",
            session_id,
        ],
        input="exit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    assert f"Session: {session_id}" in second.stdout


def test_cli_prints_workspace_root_when_provided(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistant.cli",
            "--session-dir",
            str(session_dir),
            "--workspace-root",
            str(workspace_root),
        ],
        input="exit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    assert f"Workspace root: {workspace_root}" in result.stdout


def test_cli_read_outside_workspace_fails_cleanly(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistant.cli",
            "--session-dir",
            str(session_dir),
            "--workspace-root",
            str(workspace_root),
        ],
        input=f"Read {outside}\nexit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    assert "outside workspace" in result.stdout.lower()


def test_cli_read_outside_workspace_fails_cleanly(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistant.cli",
            "--session-dir",
            str(session_dir),
            "--workspace-root",
            str(workspace_root),
        ],
        input=f"Read {outside}\nexit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    assert "outside workspace" in result.stdout.lower()
