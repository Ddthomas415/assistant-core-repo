from __future__ import annotations

from pathlib import Path

from assistant.filesystem import list_workspace_tool, read_file_tool, write_file_tool
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


def test_read_file_tool_missing_file_suggests_nearby_match(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.yaml").write_text("name: demo", encoding="utf-8")

    request = ToolRequest(
        tool_name="read_file",
        arguments={
            "path": "confi.yaml",
            "workspace_root": str(workspace),
        },
        user_facing_label="reading confi.yaml",
    )

    result = read_file_tool(request)

    assert result.ok is False
    assert result.error_code == "file_not_found"
    assert "did you mean" in result.summary.lower()
    assert "config.yaml" in result.summary
    assert result.data["suggestions"] == ["config.yaml"]


def test_read_file_tool_missing_file_without_workspace_has_no_suggestions(tmp_path: Path) -> None:
    missing = tmp_path / "confi.yaml"

    request = ToolRequest(
        tool_name="read_file",
        arguments={
            "path": str(missing),
        },
        user_facing_label="reading missing file",
    )

    result = read_file_tool(request)

    assert result.ok is False
    assert result.error_code == "file_not_found"
    assert "did you mean" not in result.summary.lower()
    assert result.data["suggestions"] == []


def test_list_workspace_tool_returns_recursive_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.txt").write_text("a", encoding="utf-8")
    sub = workspace / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("b", encoding="utf-8")

    request = ToolRequest(
        tool_name="list_workspace",
        arguments={"workspace_root": str(workspace)},
        user_facing_label="listing workspace",
    )

    result = list_workspace_tool(request)

    assert result.ok is True
    assert result.data["files"] == ["a.txt", "sub/b.txt"]
    assert result.data["truncated"] is False
    assert "Workspace files:" in result.summary


def test_list_workspace_tool_reports_recursive_file_count_via_data(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.txt").write_text("a", encoding="utf-8")
    (workspace / "b.txt").write_text("b", encoding="utf-8")

    request = ToolRequest(
        tool_name="list_workspace",
        arguments={"workspace_root": str(workspace)},
        user_facing_label="listing workspace",
    )

    result = list_workspace_tool(request)

    assert result.ok is True
    assert len(result.data["files"]) == 2
    assert result.data["truncated"] is False
