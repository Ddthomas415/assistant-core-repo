from __future__ import annotations

from assistant.models import ClarificationTarget, PendingClarification, SessionState


CONFIRMATION_REPLIES = {"yes", "y", "confirm"}


def is_confirmation_reply(user_input: str) -> bool:
    return user_input.strip().lower() in CONFIRMATION_REPLIES


def looks_like_file_path(user_input: str) -> bool:
    cleaned = user_input.strip()

    if not cleaned:
        return False

    if cleaned.endswith("?"):
        return False

    path_markers = ["/", "\\", ".", "_", "-"]
    known_extensions = {
        ".py", ".txt", ".md", ".json", ".yaml", ".yml",
        ".toml", ".ini", ".cfg", ".conf", ".xml",
    }

    lowered = cleaned.lower()

    if any(ext in lowered for ext in known_extensions):
        return True

    if any(marker in cleaned for marker in path_markers):
        return True

    return False


def satisfies_clarification(
    pending: PendingClarification,
    user_input: str,
) -> bool:
    cleaned = user_input.strip()
    if not cleaned:
        return False
    if is_confirmation_reply(cleaned):
        return False

    if pending.target == ClarificationTarget.FILE_PATH:
        return looks_like_file_path(cleaned)

    return False


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
