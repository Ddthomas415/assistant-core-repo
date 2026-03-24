from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from assistant.engine import Engine
from assistant.models import (
    ClarificationTarget,
    PendingConfirmation,
    RequestedAction,
    RouteKind,
    SessionMetadata,
    SessionState,
    ToolRequest,
    ToolResult,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def expired_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()


def make_state() -> SessionState:
    now = now_iso()
    return SessionState(
        session_id=str(uuid4()),
        metadata=SessionMetadata(created_at=now, updated_at=now),
    )


def fake_read_tool(request: ToolRequest) -> ToolResult:
    return ToolResult(
        ok=True,
        tool_name=request.tool_name,
        execution_id=str(uuid4()),
        summary=f"Read {request.arguments['path']}",
        data={"path": request.arguments["path"]},
        started_at=now_iso(),
        finished_at=now_iso(),
    )


def fake_write_tool(request: ToolRequest) -> ToolResult:
    return ToolResult(
        ok=True,
        tool_name=request.tool_name,
        execution_id=str(uuid4()),
        summary=f"Wrote {request.arguments['path']}",
        data={"path": request.arguments["path"]},
        started_at=now_iso(),
        finished_at=now_iso(),
    )


def test_direct_answer_produces_answer_route_and_no_pending_state() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "What does this assistant do?")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert result.policy_outcome.kind.value == "allow"
    assert state.pending_clarification is None
    assert state.pending_confirmation is None
    assert "terminal-first private assistant" in result.rendered_output.lower()


def test_ambiguous_request_creates_pending_clarification() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "Open the config file.")

    assert result.route_decision.kind == RouteKind.CLARIFY
    assert result.policy_outcome.kind.value == "require_clarification"
    assert state.pending_clarification is not None
    assert state.pending_clarification.target == ClarificationTarget.FILE_PATH
    assert state.pending_confirmation is None


def test_modifying_request_creates_pending_confirmation() -> None:
    engine = Engine(write_tool=fake_write_tool)
    state = make_state()

    result = engine.handle_turn(state, "Overwrite config.yaml with defaults.")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.policy_outcome.kind.value == "require_confirmation"
    assert state.pending_confirmation is not None
    assert state.pending_confirmation.requested_action.tool_name == "write_file"
    assert state.pending_clarification is None


def test_valid_yes_resolves_matching_pending_confirmation_only() -> None:
    engine = Engine(write_tool=fake_write_tool)
    state = make_state()

    engine.handle_turn(state, "Overwrite config.yaml with defaults.")
    pending_id = state.pending_confirmation.action_id
    result = engine.handle_turn(state, "yes")

    assert result.route_decision.kind == RouteKind.CONFIRM
    assert result.policy_outcome.kind.value == "allow"
    assert result.tool_result is not None
    assert result.tool_result.tool_name == "write_file"
    assert state.pending_confirmation is None
    assert state.last_tool_execution is not None
    assert pending_id != ""


def test_stale_confirmation_does_not_execute() -> None:
    engine = Engine(write_tool=fake_write_tool)
    state = make_state()

    requested_action = RequestedAction(
        action_id=str(uuid4()),
        tool_name="write_file",
        arguments={"path": "config.yaml", "content": "defaults"},
        reason="test",
    )
    state.pending_confirmation = PendingConfirmation(
        confirmation_id=str(uuid4()),
        action_id=requested_action.action_id,
        created_at=now_iso(),
        expires_at=expired_iso(),
        prompt="Please confirm.",
        requested_action=requested_action,
    )

    result = engine.handle_turn(state, "confirm")

    assert result.route_decision.kind == RouteKind.CONFIRM
    assert result.policy_outcome.kind.value == "block"
    assert result.tool_result is None
    assert state.pending_confirmation is None
    assert "no valid pending confirmation" in result.rendered_output.lower()


def test_unrelated_input_clears_pending_confirmation() -> None:
    engine = Engine(write_tool=fake_write_tool)
    state = make_state()

    engine.handle_turn(state, "Overwrite config.yaml with defaults.")
    assert state.pending_confirmation is not None

    result = engine.handle_turn(state, "What does this assistant do?")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert state.pending_confirmation is None
    assert "terminal-first private assistant" in result.rendered_output.lower()


def test_resolved_clarification_clears_pending_state() -> None:
    engine = Engine()
    state = make_state()

    engine.handle_turn(state, "Open the config file.")
    assert state.pending_clarification is not None

    result = engine.handle_turn(state, "project-config.yaml")

    assert result.route_decision.kind == RouteKind.CLARIFY
    assert result.policy_outcome.kind.value == "allow"
    assert state.pending_clarification is None
    assert "project-config.yaml" in result.rendered_output


def test_read_tool_path_is_allowed_and_records_last_execution() -> None:
    engine = Engine(read_tool=fake_read_tool)
    state = make_state()

    result = engine.handle_turn(state, "Read pyproject.toml")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.policy_outcome.kind.value == "allow"
    assert result.tool_result is not None
    assert result.tool_result.tool_name == "read_file"
    assert state.last_tool_execution is not None
    assert "read pyproject.toml" in result.rendered_output.lower()
