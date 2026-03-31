from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RouteKind = Literal["answer", "clarify", "confirm", "tool"]
PolicyOutcomeKind = Literal["allow", "block", "require_confirmation", "require_clarification"]
ClarificationTarget = Literal["filename", "content", "tool_arguments", "user_intent"]


@dataclass(frozen=True)
class RequestedAction:
    action_name: str
    arguments: dict[str, Any]
    user_facing_label: str


@dataclass(frozen=True)
class ToolRequest:
    tool_name: str
    arguments: dict[str, Any]
    user_facing_label: str


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    tool_name: str
    execution_id: str
    summary: str
    data: Any
    error_code: str | None
    error_message: str | None
    started_at: str
    finished_at: str


@dataclass(frozen=True)
class RouteDecision:
    kind: RouteKind
    answer_text: str | None = None
    clarification_prompt: str | None = None
    clarification_target: ClarificationTarget | None = None
    confirmation_prompt: str | None = None
    requested_action: RequestedAction | None = None
    tool_request: ToolRequest | None = None


@dataclass(frozen=True)
class PolicyOutcome:
    kind: PolicyOutcomeKind
    reason: str
    blocking_code: str | None
    advisory_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PendingClarification:
    clarification_id: str
    created_at: str
    expires_at: str
    prompt: str
    target: ClarificationTarget
    bound_user_request: str
    allowed_reply_kinds: list[str]


@dataclass(frozen=True)
class PendingConfirmation:
    confirmation_id: str
    action_id: str
    created_at: str
    expires_at: str
    prompt: str
    requested_action: RequestedAction


@dataclass(frozen=True)
class TurnTrace:
    route_kind: RouteKind
    policy_kind: PolicyOutcomeKind | None
    canceled_pending_state: str | None = None


@dataclass(frozen=True)
class TurnResult:
    assistant_message: str
    route: RouteDecision
    policy: PolicyOutcome | None
    tool_result: ToolResult | None
    trace: TurnTrace


# planner_mode:
# - "heuristic": default local planner path
# - "model": model-backed planner path
# - "model_fallback": model path was requested but local heuristic fallback was used
PlannerMode = Literal["heuristic", "model", "model_fallback"]
