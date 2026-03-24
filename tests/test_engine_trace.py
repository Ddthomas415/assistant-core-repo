from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from assistant.engine import Engine
from assistant.models import (
    LastToolExecution,
    PendingConfirmation,
    RequestedAction,
    RouteKind,
    SessionMetadata,
    SessionState,
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


def test_expired_confirmation_adds_expired_trace_note_and_does_not_mutate_last_tool_execution() -> None:
    engine = Engine()
    state = make_state()

    state.last_tool_execution = LastToolExecution(
        execution_id="prev-exec",
        tool_name="read_file",
        ok=True,
        summary="previous read",
        finished_at=now_iso(),
    )

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

    result = engine.handle_turn(state, "yes")

    assert result.route_decision.kind == RouteKind.CONFIRM
    assert result.policy_outcome.kind.value == "block"
    assert result.trace.tool_invoked is False
    assert result.trace.tool_execution_id is None
    assert "expired_pending_confirmation_cleared" in result.trace.notes
    assert state.last_tool_execution is not None
    assert state.last_tool_execution.execution_id == "prev-exec"


def test_superseded_pending_confirmation_adds_superseded_trace_note() -> None:
    engine = Engine()
    state = make_state()

    engine.handle_turn(state, "Overwrite config.yaml with defaults.")
    result = engine.handle_turn(state, "What does this assistant do?")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert result.trace.tool_invoked is False
    assert result.trace.tool_execution_id is None
    assert "pending_confirmation_superseded" in result.trace.notes


def test_superseded_pending_clarification_adds_superseded_trace_note() -> None:
    engine = Engine()
    state = make_state()

    engine.handle_turn(state, "Open the config file.")
    result = engine.handle_turn(state, "What does this assistant do?")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert result.trace.tool_invoked is False
    assert result.trace.tool_execution_id is None
    assert "pending_clarification_superseded" in result.trace.notes


def test_real_read_tool_success_sets_trace_execution_fields() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "Read pyproject.toml")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.policy_outcome.kind.value == "allow"
    assert result.trace.tool_invoked is True
    assert result.trace.tool_execution_id is not None
    assert result.tool_result is not None
    assert result.trace.tool_execution_id == result.tool_result.execution_id


def test_real_read_tool_failure_sets_trace_execution_fields() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "Read /definitely/not/a/real/file.txt")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.policy_outcome.kind.value == "allow"
    assert result.tool_result is not None
    assert result.tool_result.ok is False
    assert result.trace.tool_invoked is True
    assert result.trace.tool_execution_id == result.tool_result.execution_id
