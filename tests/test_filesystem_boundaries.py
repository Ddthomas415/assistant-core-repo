from __future__ import annotations

from pathlib import Path

from assistant.filesystem import read_file_tool, write_file_tool
from assistant.models import ToolRequest


def test_read_file_tool_blocks_path_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside = outside_dir / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    request = ToolRequest(
        tool_name="read_file",
        arguments={
            "path": str(outside),
            "workspace_root": str(workspace),
        },
        user_facing_label=f"reading {outside}",
    )

    result = read_file_tool(request)

    assert result.ok is False
    assert result.error_code == "path_outside_workspace"


def test_write_file_tool_blocks_path_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside = outside_dir / "outside.txt"

    request = ToolRequest(
        tool_name="write_file",
        arguments={
            "path": str(outside),
            "content": "secret",
            "workspace_root": str(workspace),
        },
        user_facing_label=f"writing {outside}",
    )

    result = write_file_tool(request)

    assert result.ok is False
    assert result.error_code == "path_outside_workspace"


def test_read_file_tool_allows_path_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    inside = workspace / "inside.txt"
    inside.write_text("hello", encoding="utf-8")

    request = ToolRequest(
        tool_name="read_file",
        arguments={
            "path": str(inside),
            "workspace_root": str(workspace),
        },
        user_facing_label=f"reading {inside}",
    )

    result = read_file_tool(request)

    assert result.ok is True
    assert result.data["content"] == "hello"


def test_write_file_tool_allows_path_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    inside = workspace / "inside.txt"

    request = ToolRequest(
        tool_name="write_file",
        arguments={
            "path": str(inside),
            "content": "hello",
            "workspace_root": str(workspace),
        },
        user_facing_label=f"writing {inside}",
    )

    result = write_file_tool(request)

    assert result.ok is True
    assert inside.read_text(encoding="utf-8") == "hello"
