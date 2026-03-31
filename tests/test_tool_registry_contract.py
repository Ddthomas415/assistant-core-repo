from core.tool_registry import execute_tool_request
from core.types import ToolRequest


def test_read_file_tool_result_shape():
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


def test_list_workspace_tool_result_shape():
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
