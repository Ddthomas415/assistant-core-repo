from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from assistant.engine import Engine
from assistant.models import (
    ClarificationTarget,
    PendingClarification,
    PendingConfirmation,
    PendingTransitionKind,
    RequestedAction,
    RouteKind,
    SessionMetadata,
    SessionState,
)
from assistant.session import SessionStore


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


def test_direct_answer_has_no_pending_transition() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "What does this assistant do?")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert result.trace.pending_transition == PendingTransitionKind.NONE
    assert result.trace.tool_invoked is False


def test_ambiguous_request_creates_pending_clarification_with_created_transition() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "Open the config file.")

    assert result.route_decision.kind == RouteKind.CLARIFY
    assert result.trace.pending_transition == PendingTransitionKind.CREATED
    assert state.pending_clarification is not None


def test_clarification_reply_resolves_pending_clarification_with_resolved_transition() -> None:
    engine = Engine()
    state = make_state()

    engine.handle_turn(state, "Open the config file.")
    result = engine.handle_turn(state, "project-config.yaml")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.trace.pending_transition == PendingTransitionKind.RESOLVED
    assert state.pending_clarification is None


def test_unrelated_input_supersedes_pending_clarification() -> None:
    engine = Engine()
    state = make_state()

    engine.handle_turn(state, "Open the config file.")
    result = engine.handle_turn(state, "What does this assistant do?")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert result.trace.pending_transition == PendingTransitionKind.SUPERSEDED
    assert state.pending_clarification is None


def test_clarified_overwrite_resolves_pending_clarification_and_creates_confirmation() -> None:
    engine = Engine()
    state = make_state()

    engine.handle_turn(state, "Overwrite  with defaults.")
    result = engine.handle_turn(state, "config.yaml")

    assert result.route_decision.kind == RouteKind.CONFIRM
    assert result.trace.pending_transition == PendingTransitionKind.RESOLVED
    assert state.pending_clarification is None
    assert state.pending_confirmation is not None


def test_modifying_request_creates_pending_confirmation_with_created_transition() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "Overwrite config.yaml with defaults.")

    assert result.route_decision.kind == RouteKind.CONFIRM
    assert result.trace.pending_transition == PendingTransitionKind.CREATED
    assert state.pending_confirmation is not None


def test_stale_confirmation_returns_expired_transition_and_blocks_execution() -> None:
    engine = Engine()
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

    result = engine.handle_turn(state, "yes")

    assert result.route_decision.kind == RouteKind.CONFIRM
    assert result.trace.pending_transition == PendingTransitionKind.EXPIRED
    assert result.trace.tool_invoked is False
    assert state.pending_confirmation is None


def test_unrelated_input_supersedes_pending_confirmation() -> None:
    engine = Engine()
    state = make_state()

    engine.handle_turn(state, "Overwrite config.yaml with defaults.")
    result = engine.handle_turn(state, "What does this assistant do?")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert result.trace.pending_transition == PendingTransitionKind.SUPERSEDED
    assert state.pending_confirmation is None


def test_resumed_expired_pending_clarification_is_cleared_before_normal_answer() -> None:
    engine = Engine()
    state = make_state()

    state.pending_clarification = PendingClarification(
        clarification_id=str(uuid4()),
        created_at=now_iso(),
        expires_at=expired_iso(),
        prompt="Which config file?",
        target=ClarificationTarget.FILE_PATH,
        bound_user_request="Open the config file.",
        allowed_reply_kinds=["file_path"],
    )

    result = engine.handle_turn(state, "What does this assistant do?")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert result.trace.pending_transition == PendingTransitionKind.EXPIRED
    assert state.pending_clarification is None

def test_pending_clarification_survives_resume_and_continues(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    engine = Engine(workspace_root="workspace")

    state = store.create()
    result1 = engine.handle_turn(state, "open the config file")
    assert result1.route_decision.kind == RouteKind.CLARIFY
    assert state.pending_clarification is not None

    store.save(state)
    resumed = store.load(state.session_id)

    result2 = engine.handle_turn(resumed, "config.yaml")

    assert result2.route_decision.kind == RouteKind.TOOL
    assert result2.tool_result is not None or result2.route_decision.tool_request is not None
