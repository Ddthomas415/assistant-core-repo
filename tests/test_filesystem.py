from __future__ import annotations

from pathlib import Path

from assistant.filesystem import read_file_tool
from assistant.models import ToolRequest


def test_read_file_tool_success(tmp_path: Path) -> None:
    file_path = tmp_path / "example.txt"
    file_path.write_text("hello world", encoding="utf-8")

    request = ToolRequest(
        tool_name="read_file",
        arguments={"path": str(file_path)},
        user_facing_label=f"reading {file_path}",
    )

    result = read_file_tool(request)

    assert result.ok is True
    assert result.error_code is None
    assert result.data["content"] == "hello world"
    assert str(file_path) in result.summary


def test_read_file_tool_missing_file_failure(tmp_path: Path) -> None:
    file_path = tmp_path / "missing.txt"

    request = ToolRequest(
        tool_name="read_file",
        arguments={"path": str(file_path)},
        user_facing_label=f"reading {file_path}",
    )

    result = read_file_tool(request)

    assert result.ok is False
    assert result.error_code == "file_not_found"
    assert "file not found" in result.summary.lower()


def test_read_file_tool_directory_failure(tmp_path: Path) -> None:
    request = ToolRequest(
        tool_name="read_file",
        arguments={"path": str(tmp_path)},
        user_facing_label=f"reading {tmp_path}",
    )

    result = read_file_tool(request)

    assert result.ok is False
    assert result.error_code == "not_a_file"
    assert "not a file" in result.summary.lower()
