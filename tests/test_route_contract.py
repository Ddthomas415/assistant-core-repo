from core.types import RequestedAction, RouteDecision, ToolRequest


def test_route_kind_answer_contract():
    route = RouteDecision(kind="answer", answer_text="Hello")
    assert route.kind == "answer"
    assert route.answer_text == "Hello"
    assert route.tool_request is None
    assert route.requested_action is None


def test_route_kind_clarify_contract():
    route = RouteDecision(
        kind="clarify",
        clarification_prompt="Which file do you mean?",
        clarification_target="filename",
    )
    assert route.kind == "clarify"
    assert route.clarification_prompt == "Which file do you mean?"
    assert route.clarification_target == "filename"


def test_route_kind_confirm_contract():
    action = RequestedAction(
        action_name="write_file",
        arguments={"filename": "demo.py", "content": "print('hi')"},
        user_facing_label="write demo.py",
    )
    route = RouteDecision(
        kind="confirm",
        confirmation_prompt="Do you want me to overwrite demo.py?",
        requested_action=action,
    )
    assert route.kind == "confirm"
    assert route.confirmation_prompt is not None
    assert route.requested_action == action


def test_route_kind_tool_contract():
    req = ToolRequest(
        tool_name="read_file",
        arguments={"filename": "demo.py"},
        user_facing_label="read demo.py",
    )
    route = RouteDecision(kind="tool", tool_request=req)
    assert route.kind == "tool"
    assert route.tool_request == req
