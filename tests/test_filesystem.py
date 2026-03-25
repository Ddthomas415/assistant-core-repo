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


def test_write_file_tool_success(tmp_path: Path) -> None:
    file_path = tmp_path / "write-example.txt"

    request = ToolRequest(
        tool_name="write_file",
        arguments={"path": str(file_path), "content": "written content"},
        user_facing_label=f"writing {file_path}",
    )

    from assistant.filesystem import write_file_tool

    result = write_file_tool(request)

    assert result.ok is True
    assert result.error_code is None
    assert file_path.read_text(encoding="utf-8") == "written content"
    assert result.data["content"] == "written content"


def test_write_file_tool_invalid_path_failure() -> None:
    request = ToolRequest(
        tool_name="write_file",
        arguments={"path": "", "content": "written content"},
        user_facing_label="writing invalid path",
    )

    from assistant.filesystem import write_file_tool

    result = write_file_tool(request)

    assert result.ok is False
    assert result.error_code == "invalid_path"


def test_write_file_tool_directory_failure(tmp_path: Path) -> None:
    request = ToolRequest(
        tool_name="write_file",
        arguments={"path": str(tmp_path), "content": "written content"},
        user_facing_label=f"writing {tmp_path}",
    )

    from assistant.filesystem import write_file_tool

    result = write_file_tool(request)

    assert result.ok is False
    assert result.error_code == "not_a_file"

def test_list_workspace_tool_returns_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.txt").write_text("a", encoding="utf-8")
    sub = workspace / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("b", encoding="utf-8")

    from assistant.filesystem import list_workspace_tool

    request = ToolRequest(
        tool_name="list_workspace",
        arguments={"workspace_root": str(workspace)},
        user_facing_label="listing workspace",
    )

    result = list_workspace_tool(request)

    assert result.ok is True
    assert result.error_code is None
    assert result.data["workspace_root"] == str(workspace.resolve())
    assert result.data["files"] == ["a.txt", "sub/b.txt"]


def test_list_workspace_tool_requires_workspace_root(tmp_path: Path) -> None:
    from assistant.filesystem import list_workspace_tool

    request = ToolRequest(
        tool_name="list_workspace",
        arguments={},
        user_facing_label="listing workspace",
    )

    result = list_workspace_tool(request)

    assert result.ok is False
    assert result.error_code == "no_workspace_root"
