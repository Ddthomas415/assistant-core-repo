from core.policy import ACTION_POLICY, evaluate_requested_action, evaluate_tool_request
from core.types import RequestedAction, ToolRequest


def test_read_file_is_auto_allowed():
    result = evaluate_tool_request(
        ToolRequest(
            tool_name="read_file",
            arguments={"filename": "demo.py"},
            user_facing_label="read demo.py",
        )
    )
    assert ACTION_POLICY["read_file"] == "auto"
    assert result.kind == "allow"
    assert result.blocking_code is None


def test_list_workspace_is_auto_allowed():
    result = evaluate_tool_request(
        ToolRequest(
            tool_name="list_workspace",
            arguments={},
            user_facing_label="list workspace",
        )
    )
    assert result.kind == "allow"


def test_write_file_requires_confirmation():
    result = evaluate_tool_request(
        ToolRequest(
            tool_name="write_file",
            arguments={"filename": "demo.py", "content": "print('hi')"},
            user_facing_label="write demo.py",
        )
    )
    assert ACTION_POLICY["write_file"] == "confirm"
    assert result.kind == "require_confirmation"


def test_edit_file_requires_confirmation():
    result = evaluate_requested_action(
        RequestedAction(
            action_name="edit_file",
            arguments={"filename": "demo.py", "content": "print('x')"},
            user_facing_label="edit demo.py",
        )
    )
    assert result.kind == "require_confirmation"


def test_unknown_tool_is_blocked():
    result = evaluate_tool_request(
        ToolRequest(
            tool_name="delete_everything",
            arguments={},
            user_facing_label="delete everything",
        )
    )
    assert result.kind == "block"
    assert result.blocking_code == "UNKNOWN_TOOL"
