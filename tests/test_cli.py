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


def test_cli_confirmed_write_inside_workspace_succeeds(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    target = workspace_root / "notes.txt"

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
        input=f"Overwrite {target} with hello world\nyes\nexit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    assert "please confirm overwriting" in result.stdout.lower()
    assert "wrote" in result.stdout.lower()
    assert target.read_text(encoding="utf-8") == "hello world"


def test_cli_confirmed_write_outside_workspace_fails_cleanly(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    outside = tmp_path / "outside.txt"

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
        input=f"Overwrite {outside} with secret\nyes\nexit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    assert "please confirm overwriting" in result.stdout.lower()
    assert "outside workspace" in result.stdout.lower()
    assert not outside.exists()


def test_cli_keyboard_interrupt_exits_cleanly(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistant.cli",
            "--session-dir",
            str(session_dir),
        ],
        input="\x03",
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "KeyboardInterrupt" not in result.stderr


def test_cli_help_includes_core_description() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistant.cli",
            "--help",
        ],
        text=True,
        capture_output=True,
        check=True,
    )

    assert "terminal-first private assistant core" in result.stdout.lower()


def test_cli_startup_text_is_friendly(tmp_path: Path) -> None:
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

    assert "assistant ready." in result.stdout.lower()


def test_cli_read_emits_visible_tool_signal(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    target = workspace_root / "notes.txt"
    target.write_text("hello signal", encoding="utf-8")

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
        input=f"Read {target}\nexit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    assert "[reading " in result.stdout.lower()


def test_cli_confirmed_write_emits_visible_tool_signal(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    target = workspace_root / "write-signal.txt"

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
        input=f"Overwrite {target} with hello\nyes\nexit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    assert "please confirm overwriting" in result.stdout.lower()
    assert "[writing " in result.stdout.lower()


def test_cli_direct_answer_does_not_emit_tool_signal(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistant.cli",
            "--session-dir",
            str(session_dir),
        ],
        input="What does this assistant do?\nexit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    stdout = result.stdout.lower()
    assert "[reading " not in stdout
    assert "[writing " not in stdout
