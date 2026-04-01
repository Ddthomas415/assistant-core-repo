from pathlib import Path

from core.tool_registry import WORKSPACE_ROOT, execute_tool_request
from core.types import ToolRequest


def test_read_file_tool_result_shape(tmp_path, monkeypatch):
    monkeypatch.setattr("core.tool_registry.WORKSPACE_ROOT", tmp_path.resolve())

    target = tmp_path / "demo.py"
    target.write_text("print('hi')", encoding="utf-8")

    result = execute_tool_request(
        ToolRequest(
            tool_name="read_file",
            arguments={"filename": "demo.py"},
            user_facing_label="read demo.py",
        )
    )
    assert result.ok is True
    assert result.tool_name == "read_file"
    assert result.error_code is None
    assert result.data["filename"] == "demo.py"
    assert result.data["content"] == "print('hi')"


def test_list_workspace_tool_result_shape(tmp_path, monkeypatch):
    monkeypatch.setattr("core.tool_registry.WORKSPACE_ROOT", tmp_path.resolve())

    (tmp_path / "a.py").write_text("print('a')", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "b.py").write_text("print('b')", encoding="utf-8")

    result = execute_tool_request(
        ToolRequest(
            tool_name="list_workspace",
            arguments={},
            user_facing_label="list workspace",
        )
    )
    assert result.ok is True
    assert result.tool_name == "list_workspace"
    assert result.error_code is None
    assert "a.py" in result.data["files"]
    assert "nested/b.py" in result.data["files"]


def test_write_file_tool_result_shape(tmp_path, monkeypatch):
    monkeypatch.setattr("core.tool_registry.WORKSPACE_ROOT", tmp_path.resolve())

    result = execute_tool_request(
        ToolRequest(
            tool_name="write_file",
            arguments={"filename": "demo.py", "content": "print('hi')"},
            user_facing_label="write demo.py",
        )
    )
    assert result.ok is True
    assert result.tool_name == "write_file"
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == "print('hi')"


def test_edit_file_tool_result_shape(tmp_path, monkeypatch):
    monkeypatch.setattr("core.tool_registry.WORKSPACE_ROOT", tmp_path.resolve())

    target = tmp_path / "demo.py"
    target.write_text("print('old')", encoding="utf-8")

    result = execute_tool_request(
        ToolRequest(
            tool_name="edit_file",
            arguments={"filename": "demo.py", "content": "print('new')"},
            user_facing_label="edit demo.py",
        )
    )
    assert result.ok is True
    assert result.tool_name == "edit_file"
    assert target.read_text(encoding="utf-8") == "print('new')"


def test_unknown_tool_returns_structured_error():
    result = execute_tool_request(
        ToolRequest(
            tool_name="delete_everything",
            arguments={},
            user_facing_label="delete everything",
        )
    )
    assert result.ok is False
    assert result.error_code == "UNSUPPORTED_TOOL"
    assert result.error_message is not None


def test_path_traversal_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr("core.tool_registry.WORKSPACE_ROOT", tmp_path.resolve())

    result = execute_tool_request(
        ToolRequest(
            tool_name="read_file",
            arguments={"filename": "../secret.txt"},
            user_facing_label="read secret",
        )
    )
    assert result.ok is False
    assert result.error_code == "PATH_NOT_ALLOWED"
