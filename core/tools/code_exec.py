"""
Sandboxed Python code execution.

Runs user-approved code in a subprocess with:
  - Hard timeout (default 15s, CODE_EXEC_TIMEOUT env var)
  - Working directory locked to workspace/
  - stdout + stderr captured and returned
  - No network restrictions (enforce at OS level if needed)

Never call this without user confirmation — policy.py enforces confirm.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path("workspace").resolve()
_TIMEOUT = int(os.getenv("CODE_EXEC_TIMEOUT", "15"))


def execute(code: str, *, language: str = "python") -> dict[str, Any]:
    """
    Execute a code snippet and return structured output.

    Returns:
        {
            "stdout":      str,
            "stderr":      str,
            "exit_code":   int,
            "timed_out":   bool,
            "language":    str,
        }
    """
    if language not in ("python",):
        return {
            "stdout": "",
            "stderr": f"Unsupported language: {language}. Only 'python' is supported.",
            "exit_code": 1,
            "timed_out": False,
            "language": language,
        }

    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        dir=str(WORKSPACE_ROOT),
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            cwd=str(WORKSPACE_ROOT),
        )
        return {
            "stdout":    result.stdout,
            "stderr":    result.stderr,
            "exit_code": result.returncode,
            "timed_out": False,
            "language":  language,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout":    "",
            "stderr":    f"Execution timed out after {_TIMEOUT}s.",
            "exit_code": 1,
            "timed_out": True,
            "language":  language,
        }
    except Exception as exc:
        return {
            "stdout":    "",
            "stderr":    str(exc),
            "exit_code": 1,
            "timed_out": False,
            "language":  language,
        }
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass


def format_result(data: dict[str, Any]) -> str:
    """Format execution result for the assistant message."""
    parts: list[str] = []
    lang = data.get("language", "python")

    if data.get("timed_out"):
        parts.append(f"Execution timed out.")
    elif data.get("exit_code", 0) == 0:
        parts.append(f"Ran successfully (exit 0).")
    else:
        parts.append(f"Exited with code {data['exit_code']}.")

    if data.get("stdout", "").strip():
        parts.append(f"\nOutput:\n{data['stdout'].rstrip()}")

    if data.get("stderr", "").strip():
        parts.append(f"\nErrors:\n{data['stderr'].rstrip()}")

    if not data.get("stdout", "").strip() and not data.get("stderr", "").strip():
        parts.append("\n(no output)")

    return "\n".join(parts)
