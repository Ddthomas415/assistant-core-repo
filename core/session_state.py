from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.types import PendingClarification, PendingConfirmation, RequestedAction, ToolResult

SESSIONS_DIR = Path(".assistant_sessions")
SCHEMA_VERSION = 1


class SessionNotFoundError(FileNotFoundError):
    """Raised when a requested assistant session does not exist."""


@dataclass
class SessionMetadata:
    created_at: str
    updated_at: str


@dataclass
class PersistedSession:
    schema_version: int
    session_id: str
    metadata: SessionMetadata
    messages: list[dict[str, Any]] = field(default_factory=list)
    summary: str | None = None
    pending_clarification: PendingClarification | None = None
    pending_confirmation: PendingConfirmation | None = None
    last_tool_execution: ToolResult | None = None


def _session_path(session_id: str) -> Path:
    """Return the storage path for a persisted assistant session."""
    return SESSIONS_DIR / f"{session_id}.json"


def _serialize_session(session: PersistedSession) -> dict[str, Any]:
    """Convert a session object into a JSON-serializable dict."""
    return asdict(session)


def _deserialize_session(payload: dict[str, Any]) -> PersistedSession:
    """Rebuild a PersistedSession from a JSON payload."""
    metadata = SessionMetadata(**payload["metadata"])

    pending_clarification = None
    if payload.get("pending_clarification") is not None:
        pending_clarification = PendingClarification(**payload["pending_clarification"])

    pending_confirmation = None
    if payload.get("pending_confirmation") is not None:
        pending_confirmation_payload = dict(payload["pending_confirmation"])
        pending_confirmation_payload["requested_action"] = RequestedAction(
            **pending_confirmation_payload["requested_action"]
        )
        pending_confirmation = PendingConfirmation(**pending_confirmation_payload)

    last_tool_execution = None
    if payload.get("last_tool_execution") is not None:
        last_tool_execution = ToolResult(**payload["last_tool_execution"])

    return PersistedSession(
        schema_version=payload["schema_version"],
        session_id=payload["session_id"],
        metadata=metadata,
        messages=payload.get("messages", []),
        summary=payload.get("summary"),
        pending_clarification=pending_clarification,
        pending_confirmation=pending_confirmation,
        last_tool_execution=last_tool_execution,
    )


def create_session(*, session_id: str, created_at: str) -> PersistedSession:
    """Create a new empty persisted session object."""
    metadata = SessionMetadata(created_at=created_at, updated_at=created_at)
    return PersistedSession(
        schema_version=SCHEMA_VERSION,
        session_id=session_id,
        metadata=metadata,
    )


def save_session(session: PersistedSession) -> Path:
    """Persist a session to disk and return the written path."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = _session_path(session.session_id)
    path.write_text(json.dumps(_serialize_session(session), indent=2), encoding="utf-8")
    return path


def load_session(session_id: str) -> PersistedSession:
    """Load a persisted session or raise SessionNotFoundError."""
    path = _session_path(session_id)
    if not path.exists():
        raise SessionNotFoundError(f"Session not found: {session_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _deserialize_session(payload)
