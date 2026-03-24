from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import (
    ClarificationTarget,
    LastToolExecution,
    Message,
    PendingClarification,
    PendingConfirmation,
    RequestedAction,
    Role,
    SCHEMA_VERSION,
    SessionMetadata,
    SessionState,
)


class SessionError(Exception):
    pass


class SessionNotFoundError(SessionError):
    pass


class SessionCorruptError(SessionError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create(self) -> SessionState:
        now = utc_now_iso()
        return SessionState(
            session_id=str(uuid4()),
            schema_version=SCHEMA_VERSION,
            metadata=SessionMetadata(created_at=now, updated_at=now),
        )

    def path_for(self, session_id: str) -> Path:
        return self.base_dir / f"{session_id}.json"

    def save(self, state: SessionState) -> None:
        self._validate_state(state)

        if state.metadata is None:
            now = utc_now_iso()
            state.metadata = SessionMetadata(created_at=now, updated_at=now)

        state.metadata.updated_at = utc_now_iso()

        payload = {
            "schema_version": state.schema_version,
            "session_id": state.session_id,
            "metadata": asdict(state.metadata),
            "messages": [asdict(message) for message in state.messages],
            "summary": state.summary,
            "pending_clarification": (
                asdict(state.pending_clarification) if state.pending_clarification else None
            ),
            "pending_confirmation": (
                asdict(state.pending_confirmation) if state.pending_confirmation else None
            ),
            "last_tool_execution": (
                asdict(state.last_tool_execution) if state.last_tool_execution else None
            ),
        }

        path = self.path_for(state.session_id)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2))
        tmp_path.replace(path)

    def load(self, session_id: str) -> SessionState:
        path = self.path_for(session_id)
        if not path.exists():
            raise SessionNotFoundError(f"Session '{session_id}' not found.")

        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: invalid JSON."
            ) from exc

        return self._state_from_payload(session_id, payload)

    def _state_from_payload(self, session_id: str, payload: dict) -> SessionState:
        required_root = {
            "schema_version",
            "session_id",
            "metadata",
            "messages",
            "summary",
            "pending_clarification",
            "pending_confirmation",
            "last_tool_execution",
        }
        missing = required_root - set(payload.keys())
        if missing:
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: missing fields {sorted(missing)}."
            )

        schema_version = payload["schema_version"]
        if not isinstance(schema_version, int):
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: schema_version must be an integer."
            )

        if schema_version != SCHEMA_VERSION:
            raise SessionCorruptError(
                f"Session '{session_id}' schema version {schema_version} is unsupported."
            )

        if payload["session_id"] != session_id:
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: session_id mismatch."
            )

        metadata_raw = payload["metadata"]
        if not isinstance(metadata_raw, dict):
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: metadata must be an object."
            )

        created_at = metadata_raw.get("created_at")
        updated_at = metadata_raw.get("updated_at")
        if not isinstance(created_at, str) or not isinstance(updated_at, str):
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: metadata timestamps are invalid."
            )

        messages_raw = payload["messages"]
        if not isinstance(messages_raw, list):
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: messages must be a list."
            )

        messages: list[Message] = []
        for item in messages_raw:
            if not isinstance(item, dict):
                raise SessionCorruptError(
                    f"Session '{session_id}' is corrupt: message entry must be an object."
                )
            role = item.get("role")
            content = item.get("content")
            if not isinstance(role, str) or not isinstance(content, str):
                raise SessionCorruptError(
                    f"Session '{session_id}' is corrupt: message fields are invalid."
                )
            try:
                messages.append(Message(role=Role(role), content=content))
            except ValueError as exc:
                raise SessionCorruptError(
                    f"Session '{session_id}' is corrupt: unknown role '{role}'."
                ) from exc

        pending_clarification = self._parse_pending_clarification(
            session_id, payload["pending_clarification"]
        )
        pending_confirmation = self._parse_pending_confirmation(
            session_id, payload["pending_confirmation"]
        )

        if pending_clarification and pending_confirmation:
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: both pending clarification and pending confirmation are set."
            )

        last_tool_execution = self._parse_last_tool_execution(
            session_id, payload["last_tool_execution"]
        )

        state = SessionState(
            session_id=session_id,
            schema_version=schema_version,
            metadata=SessionMetadata(created_at=created_at, updated_at=updated_at),
            messages=messages,
            summary=payload["summary"],
            pending_clarification=pending_clarification,
            pending_confirmation=pending_confirmation,
            last_tool_execution=last_tool_execution,
        )
        self._validate_state(state)
        return state

    def _parse_pending_clarification(
        self, session_id: str, value: object
    ) -> PendingClarification | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: pending_clarification must be an object."
            )

        try:
            target = ClarificationTarget(value["target"])
        except Exception as exc:
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: invalid clarification target."
            ) from exc

        allowed_reply_kinds = value.get("allowed_reply_kinds", [])
        if not isinstance(allowed_reply_kinds, list) or not all(
            isinstance(item, str) for item in allowed_reply_kinds
        ):
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: allowed_reply_kinds is invalid."
            )

        required = [
            "clarification_id",
            "created_at",
            "prompt",
            "target",
            "bound_user_request",
        ]
        for field_name in required:
            if field_name not in value:
                raise SessionCorruptError(
                    f"Session '{session_id}' is corrupt: pending_clarification missing '{field_name}'."
                )

        return PendingClarification(
            clarification_id=self._require_str(session_id, value, "clarification_id"),
            created_at=self._require_str(session_id, value, "created_at"),
            expires_at=self._optional_str(session_id, value, "expires_at"),
            prompt=self._require_str(session_id, value, "prompt"),
            target=target,
            bound_user_request=self._require_str(session_id, value, "bound_user_request"),
            allowed_reply_kinds=allowed_reply_kinds,
        )

    def _parse_pending_confirmation(
        self, session_id: str, value: object
    ) -> PendingConfirmation | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: pending_confirmation must be an object."
            )

        requested_action_raw = value.get("requested_action")
        if not isinstance(requested_action_raw, dict):
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: requested_action is invalid."
            )

        required_action_fields = ["action_id", "tool_name", "arguments", "reason"]
        for field_name in required_action_fields:
            if field_name not in requested_action_raw:
                raise SessionCorruptError(
                    f"Session '{session_id}' is corrupt: requested_action missing '{field_name}'."
                )

        arguments = requested_action_raw["arguments"]
        if not isinstance(arguments, dict):
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: requested_action.arguments must be an object."
            )

        requested_action = RequestedAction(
            action_id=self._require_str(session_id, requested_action_raw, "action_id"),
            tool_name=self._require_str(session_id, requested_action_raw, "tool_name"),
            arguments=arguments,
            reason=self._require_str(session_id, requested_action_raw, "reason"),
        )

        required = [
            "confirmation_id",
            "action_id",
            "created_at",
            "prompt",
            "requested_action",
        ]
        for field_name in required:
            if field_name not in value:
                raise SessionCorruptError(
                    f"Session '{session_id}' is corrupt: pending_confirmation missing '{field_name}'."
                )

        action_id = self._require_str(session_id, value, "action_id")
        if action_id != requested_action.action_id:
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: pending_confirmation action_id mismatch."
            )

        return PendingConfirmation(
            confirmation_id=self._require_str(session_id, value, "confirmation_id"),
            action_id=action_id,
            created_at=self._require_str(session_id, value, "created_at"),
            expires_at=self._optional_str(session_id, value, "expires_at"),
            prompt=self._require_str(session_id, value, "prompt"),
            requested_action=requested_action,
        )

    def _parse_last_tool_execution(
        self, session_id: str, value: object
    ) -> LastToolExecution | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: last_tool_execution must be an object."
            )

        required = ["execution_id", "tool_name", "ok", "summary"]
        for field_name in required:
            if field_name not in value:
                raise SessionCorruptError(
                    f"Session '{session_id}' is corrupt: last_tool_execution missing '{field_name}'."
                )

        ok = value["ok"]
        if not isinstance(ok, bool):
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: last_tool_execution.ok must be boolean."
            )

        return LastToolExecution(
            execution_id=self._require_str(session_id, value, "execution_id"),
            tool_name=self._require_str(session_id, value, "tool_name"),
            ok=ok,
            summary=self._require_str(session_id, value, "summary"),
            finished_at=self._optional_str(session_id, value, "finished_at"),
        )

    def _validate_state(self, state: SessionState) -> None:
        if state.schema_version != SCHEMA_VERSION:
            raise SessionCorruptError(
                f"Unsupported schema version: {state.schema_version}."
            )
        if state.metadata is None:
            raise SessionCorruptError("Session metadata is required.")
        if state.pending_clarification and state.pending_confirmation:
            raise SessionCorruptError(
                "Session state is invalid: pending clarification and pending confirmation cannot coexist."
            )

    def _require_str(self, session_id: str, obj: dict, field_name: str) -> str:
        value = obj.get(field_name)
        if not isinstance(value, str):
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: field '{field_name}' must be a string."
            )
        return value

    def _optional_str(self, session_id: str, obj: dict, field_name: str) -> str | None:
        value = obj.get(field_name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise SessionCorruptError(
                f"Session '{session_id}' is corrupt: field '{field_name}' must be a string or null."
            )
        return value
