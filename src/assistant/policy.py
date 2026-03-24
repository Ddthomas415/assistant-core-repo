from __future__ import annotations

from assistant.models import PendingClarification, SessionState


CONFIRMATION_REPLIES = {"yes", "y", "confirm"}


def is_confirmation_reply(user_input: str) -> bool:
    return user_input.strip().lower() in CONFIRMATION_REPLIES


def satisfies_clarification(
    pending: PendingClarification,
    user_input: str,
) -> bool:
    cleaned = user_input.strip()
    if not cleaned:
        return False
    if is_confirmation_reply(cleaned):
        return False
    return True


def is_confirmation_expired(state: SessionState, now: str) -> bool:
    pending = state.pending_confirmation
    if pending is None or pending.expires_at is None:
        return False
    return pending.expires_at < now


def is_clarification_expired(state: SessionState, now: str) -> bool:
    pending = state.pending_clarification
    if pending is None or pending.expires_at is None:
        return False
    return pending.expires_at < now
