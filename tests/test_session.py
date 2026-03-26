from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from assistant.models import (
    ClarificationTarget,
    PendingClarification,
    PendingConfirmation,
    RequestedAction,
    SessionMetadata,
    SessionState,
)
from assistant.session import SessionCorruptError, SessionNotFoundError, SessionStore, utc_now_iso


def make_store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions")


def make_state() -> SessionState:
    now = utc_now_iso()
    return SessionState(
        session_id=str(uuid4()),
        metadata=SessionMetadata(created_at=now, updated_at=now),
    )


def test_create_save_load_round_trip(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    state = make_state()
    state.summary = "session summary"

    clarification = PendingClarification(
        clarification_id=str(uuid4()),
        created_at=utc_now_iso(),
        expires_at=None,
        prompt="Which config file do you want?",
        target=ClarificationTarget.FILE_PATH,
        bound_user_request="Open the config file.",
        allowed_reply_kinds=["file_path"],
    )
    state.pending_clarification = clarification

    store.save(state)
    loaded = store.load(state.session_id)

    assert loaded.session_id == state.session_id
    assert loaded.schema_version == state.schema_version
    assert loaded.summary == "session summary"
    assert loaded.pending_clarification is not None
    assert loaded.pending_clarification.prompt == clarification.prompt
    assert loaded.pending_confirmation is None


def test_missing_session_raises_not_found(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    with pytest.raises(SessionNotFoundError):
        store.load("missing-session-id")


def test_corrupt_json_raises_corrupt_error(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    session_id = str(uuid4())
    path = store.path_for(session_id)
    path.write_text("{not valid json")

    with pytest.raises(SessionCorruptError):
        store.load(session_id)


def test_missing_required_field_raises_corrupt_error(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    session_id = str(uuid4())
    path = store.path_for(session_id)

    payload = {
        "schema_version": 1,
        "session_id": session_id,
        "metadata": {
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        },
        "messages": [],
        "summary": None,
        "pending_clarification": None,
        "pending_confirmation": None,
        # intentionally omit last_tool_execution
    }
    path.write_text(json.dumps(payload, indent=2))

    with pytest.raises(SessionCorruptError):
        store.load(session_id)


def test_non_object_root_payload_raises_corrupt_error(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    session_id = str(uuid4())
    path = store.path_for(session_id)
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(SessionCorruptError):
        store.load(session_id)


def test_invalid_summary_type_raises_corrupt_error(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    session_id = str(uuid4())
    path = store.path_for(session_id)

    payload = {
        "schema_version": 1,
        "session_id": session_id,
        "metadata": {
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        },
        "messages": [],
        "summary": 123,
        "pending_clarification": None,
        "pending_confirmation": None,
        "last_tool_execution": None,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with pytest.raises(SessionCorruptError):
        store.load(session_id)


def test_dual_pending_state_raises_corrupt_error(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    session_id = str(uuid4())
    path = store.path_for(session_id)

    requested_action = RequestedAction(
        action_id=str(uuid4()),
        tool_name="write_file",
        arguments={"path": "config.yaml", "content": "defaults"},
        reason="test action",
    )

    payload = {
        "schema_version": 1,
        "session_id": session_id,
        "metadata": {
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        },
        "messages": [],
        "summary": None,
        "pending_clarification": {
            "clarification_id": str(uuid4()),
            "created_at": utc_now_iso(),
            "expires_at": None,
            "prompt": "Which config file?",
            "target": "file_path",
            "bound_user_request": "Open the config file.",
            "allowed_reply_kinds": ["file_path"],
        },
        "pending_confirmation": {
            "confirmation_id": str(uuid4()),
            "action_id": requested_action.action_id,
            "created_at": utc_now_iso(),
            "expires_at": None,
            "prompt": "Please confirm overwrite.",
            "requested_action": {
                "action_id": requested_action.action_id,
                "tool_name": requested_action.tool_name,
                "arguments": requested_action.arguments,
                "reason": requested_action.reason,
            },
        },
        "last_tool_execution": None,
    }
    path.write_text(json.dumps(payload, indent=2))

    with pytest.raises(SessionCorruptError):
        store.load(session_id)
