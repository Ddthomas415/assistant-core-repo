from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from assistant.session import utc_now_iso


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


def test_cli_resume_corrupt_session_fails_cleanly_without_traceback(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    session_id = "broken-session"
    (session_dir / f"{session_id}.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "session_id": session_id,
                "metadata": {
                    "created_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                },
                "messages": [],
                "summary": None,
                "pending_clarification": {"bad": "shape"},
                "pending_confirmation": None,
                "last_tool_execution": None,
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistant.cli",
            "--session-dir",
            str(session_dir),
            "--resume",
            session_id,
        ],
        text=True,
        capture_output=True,
    )

    combined_output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "resume failed:" in combined_output.lower()
    assert "traceback" not in combined_output.lower()


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


def test_cli_show_me_contents_outside_workspace_fails_cleanly(tmp_path: Path) -> None:
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
        input=f"show me the contents of {outside}\nexit\n",
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

def test_cli_workspace_listing_phrase_succeeds(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "a.txt").write_text("a", encoding="utf-8")
    sub = workspace_root / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("b", encoding="utf-8")

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
        input="what files are in my workspace\nexit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    stdout = result.stdout.lower()
    assert "[listing workspace...]" in stdout
    assert "a.txt" in stdout
    assert "sub/b.txt" in stdout

def test_cli_resume_preserves_pending_clarification(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    target = workspace_root / "config.yaml"
    target.write_text("name: demo\n", encoding="utf-8")

    first = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistant.cli",
            "--session-dir",
            str(session_dir),
            "--workspace-root",
            str(workspace_root),
        ],
        input="open the config file\nexit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    lines = [line.strip() for line in first.stdout.splitlines() if line.strip()]
    session_line = next(line for line in lines if line.startswith("Session: "))
    session_id = session_line.split("Session: ", 1)[1]

    resumed = subprocess.run(
        [
            sys.executable,
            "-m",
            "assistant.cli",
            "--session-dir",
            str(session_dir),
            "--workspace-root",
            str(workspace_root),
            "--resume",
            session_id,
        ],
        input="config.yaml\nexit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    stdout = resumed.stdout.lower()
    assert "[reading]" in stdout or "[reading " in stdout
    assert "config.yaml" in stdout
    assert "name: demo" in stdout


def test_cli_help_text_is_clear() -> None:
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

    stdout = result.stdout.lower()
    assert "terminal-first assistant" in stdout
    assert "session state" in stdout
    assert "workspace root" in stdout


def test_cli_startup_prints_examples(tmp_path: Path) -> None:
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

    stdout = result.stdout.lower()
    assert "examples:" in stdout
    assert "read spec.md" in stdout


def test_cli_read_outside_workspace_gives_clearer_guidance(tmp_path: Path) -> None:
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

    stdout = result.stdout.lower()
    assert "outside the allowed workspace root" in stdout
    assert "--workspace-root" in stdout


def test_cli_malformed_overwrite_requests_clearer_prompt(tmp_path: Path) -> None:
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
        input="Overwrite  with hello\nexit\n",
        text=True,
        capture_output=True,
        check=True,
    )

    stdout = result.stdout.lower()
    assert "which file do you want me to overwrite?" in stdout
    assert "target file path" in stdout
