from core.session_state import (
    SESSIONS_DIR,
    SessionNotFoundError,
    create_session,
    load_session,
    save_session,
)
from core.types import PendingClarification, PendingConfirmation, RequestedAction, ToolResult


def test_missing_session_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr("core.session_state.SESSIONS_DIR", tmp_path)

    try:
        load_session("missing")
        assert False, "Expected SessionNotFoundError"
    except SessionNotFoundError as exc:
        assert "missing" in str(exc)


def test_create_and_roundtrip_empty_session(tmp_path, monkeypatch):
    monkeypatch.setattr("core.session_state.SESSIONS_DIR", tmp_path)

    session = create_session(session_id="s1", created_at="2026-01-01T00:00:00Z")
    path = save_session(session)
    loaded = load_session("s1")

    assert path == tmp_path / "s1.json"
    assert loaded.schema_version == 1
    assert loaded.session_id == "s1"
    assert loaded.messages == []
    assert loaded.summary is None
    assert loaded.pending_clarification is None
    assert loaded.pending_confirmation is None
    assert loaded.last_tool_execution is None


def test_roundtrip_with_pending_clarification(tmp_path, monkeypatch):
    monkeypatch.setattr("core.session_state.SESSIONS_DIR", tmp_path)

    session = create_session(session_id="s2", created_at="2026-01-01T00:00:00Z")
    session.pending_clarification = PendingClarification(
        clarification_id="c1",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T00:05:00Z",
        prompt="Which file do you mean?",
        target="filename",
        bound_user_request="read my file",
        allowed_reply_kinds=["filename"],
    )

    save_session(session)
    loaded = load_session("s2")

    assert loaded.pending_clarification is not None
    assert loaded.pending_clarification.target == "filename"


def test_roundtrip_with_pending_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr("core.session_state.SESSIONS_DIR", tmp_path)

    session = create_session(session_id="s3", created_at="2026-01-01T00:00:00Z")
    session.pending_confirmation = PendingConfirmation(
        confirmation_id="k1",
        action_id="a1",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T00:05:00Z",
        prompt="Confirm write?",
        requested_action=RequestedAction(
            action_name="write_file",
            arguments={"filename": "demo.py", "content": "print('hi')"},
            user_facing_label="write demo.py",
        ),
    )

    save_session(session)
    loaded = load_session("s3")

    assert loaded.pending_confirmation is not None
    assert loaded.pending_confirmation.action_id == "a1"
    assert loaded.pending_confirmation.requested_action.action_name == "write_file"


def test_roundtrip_with_last_tool_execution(tmp_path, monkeypatch):
    monkeypatch.setattr("core.session_state.SESSIONS_DIR", tmp_path)

    session = create_session(session_id="s4", created_at="2026-01-01T00:00:00Z")
    session.last_tool_execution = ToolResult(
        ok=True,
        tool_name="read_file",
        execution_id="exec-1",
        summary="Read demo.py",
        data={"filename": "demo.py", "content": "print('hi')"},
        error_code=None,
        error_message=None,
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:01Z",
    )

    save_session(session)
    loaded = load_session("s4")

    assert loaded.last_tool_execution is not None
    assert loaded.last_tool_execution.tool_name == "read_file"
    assert loaded.last_tool_execution.ok is True
