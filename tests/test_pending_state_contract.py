from core.types import PendingClarification, PendingConfirmation, RequestedAction


def test_pending_clarification_shape():
    pending = PendingClarification(
        clarification_id="c1",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T00:05:00Z",
        prompt="Which file do you mean?",
        target="filename",
        bound_user_request="read the file",
        allowed_reply_kinds=["filename"],
    )
    assert pending.target == "filename"
    assert pending.allowed_reply_kinds == ["filename"]


def test_pending_confirmation_shape():
    action = RequestedAction(
        action_name="edit_file",
        arguments={"filename": "demo.py", "content": "print('x')"},
        user_facing_label="edit demo.py",
    )
    pending = PendingConfirmation(
        confirmation_id="k1",
        action_id="a1",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T00:05:00Z",
        prompt="Do you want me to edit demo.py?",
        requested_action=action,
    )
    assert pending.action_id == "a1"
    assert pending.requested_action == action


def test_clarification_and_confirmation_are_distinct_types():
    action = RequestedAction(
        action_name="write_file",
        arguments={"filename": "demo.py"},
        user_facing_label="write demo.py",
    )
    clarification = PendingClarification(
        clarification_id="c1",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T00:05:00Z",
        prompt="Which file?",
        target="filename",
        bound_user_request="write file",
        allowed_reply_kinds=["filename"],
    )
    confirmation = PendingConfirmation(
        confirmation_id="k1",
        action_id="a1",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T00:05:00Z",
        prompt="Confirm write?",
        requested_action=action,
    )
    assert type(clarification) is not type(confirmation)
