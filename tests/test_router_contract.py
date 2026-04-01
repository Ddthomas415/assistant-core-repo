from core.router import route_user_message
from core.types import PendingClarification, PendingConfirmation, RequestedAction


def test_question_routes_to_answer():
    route, policy = route_user_message("what can you do?")
    assert route.kind == "answer"
    assert route.answer_text is not None
    assert policy is None


def test_list_routes_to_tool():
    route, policy = route_user_message("list workspace files")
    assert route.kind == "tool"
    assert route.tool_request is not None
    assert route.tool_request.tool_name == "list_workspace"
    assert policy is not None
    assert policy.kind == "allow"


def test_read_without_filename_routes_to_clarify():
    route, policy = route_user_message("read the file")
    assert route.kind == "clarify"
    assert route.clarification_target == "filename"
    assert policy is not None
    assert policy.kind == "require_clarification"


def test_read_with_filename_routes_to_tool():
    route, policy = route_user_message("read demo.py")
    assert route.kind == "tool"
    assert route.tool_request is not None
    assert route.tool_request.tool_name == "read_file"
    assert route.tool_request.arguments["filename"] == "demo.py"
    assert policy is not None
    assert policy.kind == "allow"


def test_write_routes_to_confirm():
    route, policy = route_user_message("write demo.py")
    assert route.kind == "confirm"
    assert route.requested_action is not None
    assert route.requested_action.action_name == "write_file"
    assert policy is not None
    assert policy.kind == "require_confirmation"


def test_pending_clarification_reissues_prompt():
    pending = PendingClarification(
        clarification_id="c1",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T00:05:00Z",
        prompt="Which file do you mean?",
        target="filename",
        bound_user_request="read the file",
        allowed_reply_kinds=["filename"],
    )
    route, policy = route_user_message("anything", pending_clarification=pending)
    assert route.kind == "clarify"
    assert route.clarification_prompt == "Which file do you mean?"
    assert policy is None


def test_pending_confirmation_yes_routes_to_tool():
    pending = PendingConfirmation(
        confirmation_id="k1",
        action_id="a1",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T00:05:00Z",
        prompt="Do you want me to write demo.py?",
        requested_action=RequestedAction(
            action_name="write_file",
            arguments={"filename": "demo.py", "content": ""},
            user_facing_label="write demo.py",
        ),
    )
    route, policy = route_user_message("yes", pending_confirmation=pending)
    assert route.kind == "tool"
    assert route.tool_request is not None
    assert route.tool_request.tool_name == "write_file"
    assert policy is not None
    assert policy.kind == "require_confirmation"


def test_pending_confirmation_no_routes_to_answer():
    pending = PendingConfirmation(
        confirmation_id="k1",
        action_id="a1",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T00:05:00Z",
        prompt="Do you want me to write demo.py?",
        requested_action=RequestedAction(
            action_name="write_file",
            arguments={"filename": "demo.py", "content": ""},
            user_facing_label="write demo.py",
        ),
    )
    route, policy = route_user_message("no", pending_confirmation=pending)
    assert route.kind == "answer"
    assert "canceled" in route.answer_text.lower()
    assert policy is None
