from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from assistant.models import (
    ClarificationTarget,
    PendingClarification,
    PendingConfirmation,
    RequestedAction,
    SessionMetadata,
    SessionState,
)
from assistant.policy import (
    is_clarification_expired,
    is_confirmation_expired,
    is_confirmation_reply,
    satisfies_clarification,
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


def test_is_confirmation_reply_accepts_expected_values() -> None:
    assert is_confirmation_reply("yes") is True
    assert is_confirmation_reply("Y") is True
    assert is_confirmation_reply(" confirm ") is True
    assert is_confirmation_reply("no") is False


def test_satisfies_clarification_rejects_blank_and_confirmation_reply() -> None:
    pending = PendingClarification(
        clarification_id=str(uuid4()),
        created_at=now_iso(),
        expires_at=None,
        prompt="Which file?",
        target=ClarificationTarget.FILE_PATH,
        bound_user_request="Open the config file.",
        allowed_reply_kinds=["file_path"],
    )

    assert satisfies_clarification(pending, "") is False
    assert satisfies_clarification(pending, "yes") is False
    assert satisfies_clarification(pending, "project-config.yaml") is True


def test_is_confirmation_expired_detects_expired_pending_confirmation() -> None:
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

    assert is_confirmation_expired(state, now_iso()) is True


def test_is_clarification_expired_detects_expired_pending_clarification() -> None:
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

    assert is_clarification_expired(state, now_iso()) is True

def test_satisfies_clarification_rejects_unrelated_question_for_file_path() -> None:
    pending = PendingClarification(
        clarification_id=str(uuid4()),
        created_at=now_iso(),
        expires_at=None,
        prompt="Which config file?",
        target=ClarificationTarget.FILE_PATH,
        bound_user_request="Open the config file.",
        allowed_reply_kinds=["file_path"],
    )

    assert satisfies_clarification(pending, "What does this assistant do?") is False


def test_satisfies_clarification_rejects_reserved_targets() -> None:
    for target in (ClarificationTarget.ACTION_SCOPE, ClarificationTarget.ACTION_CONTENT):
        pending = PendingClarification(
            clarification_id=str(uuid4()),
            created_at=now_iso(),
            expires_at=None,
            prompt="Reserved clarification target.",
            target=target,
            bound_user_request="reserved",
            allowed_reply_kinds=["text"],
        )

        assert satisfies_clarification(pending, "anything") is False
