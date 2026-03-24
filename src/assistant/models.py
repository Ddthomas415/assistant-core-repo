from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


SCHEMA_VERSION = 1


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class RouteKind(str, Enum):
    ANSWER = "answer"
    CLARIFY = "clarify"
    CONFIRM = "confirm"
    TOOL = "tool"


class PolicyOutcomeKind(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE_CONFIRMATION = "require_confirmation"
    REQUIRE_CLARIFICATION = "require_clarification"


class ClarificationTarget(str, Enum):
    FILE_PATH = "file_path"
    ACTION_SCOPE = "action_scope"
    ACTION_CONTENT = "action_content"
    UNKNOWN = "unknown"


class PendingTransitionKind(str, Enum):
    NONE = "none"
    CREATED = "created"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    SUPERSEDED = "superseded"


@dataclass(slots=True)
class Message:
    role: Role
    content: str


@dataclass(slots=True)
class SessionMetadata:
    created_at: str
    updated_at: str


@dataclass(slots=True)
class RequestedAction:
    action_id: str
    tool_name: str
    arguments: dict[str, Any]
    reason: str


@dataclass(slots=True)
class ToolRequest:
    tool_name: str
    arguments: dict[str, Any]
    user_facing_label: str


@dataclass(slots=True)
class ToolResult:
    ok: bool
    tool_name: str
    execution_id: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(slots=True)
class RouteDecision:
    kind: RouteKind
    answer_text: str | None = None
    clarification_prompt: str | None = None
    clarification_target: ClarificationTarget | None = None
    confirmation_prompt: str | None = None
    requested_action: RequestedAction | None = None
    tool_request: ToolRequest | None = None


@dataclass(slots=True)
class PolicyOutcome:
    kind: PolicyOutcomeKind
    reason: str
    blocking_code: str | None = None
    advisory_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PendingClarification:
    clarification_id: str
    created_at: str
    expires_at: str | None
    prompt: str
    target: ClarificationTarget
    bound_user_request: str
    allowed_reply_kinds: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PendingConfirmation:
    confirmation_id: str
    action_id: str
    created_at: str
    expires_at: str | None
    prompt: str
    requested_action: RequestedAction


@dataclass(slots=True)
class LastToolExecution:
    execution_id: str
    tool_name: str
    ok: bool
    summary: str
    finished_at: str | None = None


@dataclass(slots=True)
class TurnTrace:
    route_kind: RouteKind
    policy_outcome: PolicyOutcomeKind
    tool_invoked: bool
    tool_execution_id: str | None
    pending_transition: PendingTransitionKind
    persistence_event: str
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EngineResult:
    route_decision: RouteDecision
    policy_outcome: PolicyOutcome
    rendered_output: str
    tool_result: ToolResult | None
    trace: TurnTrace


@dataclass(slots=True)
class SessionState:
    session_id: str
    schema_version: int = SCHEMA_VERSION
    metadata: SessionMetadata | None = None
    messages: list[Message] = field(default_factory=list)
    summary: str | None = None
    pending_clarification: PendingClarification | None = None
    pending_confirmation: PendingConfirmation | None = None
    last_tool_execution: LastToolExecution | None = None
