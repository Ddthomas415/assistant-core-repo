from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from core.agent import AgentStep, run_agent
from core.session_state import (
    SessionNotFoundError,
    create_session,
    load_session,
    save_session,
)
from core.types import (
    PendingClarification,
    PendingConfirmation,
    PlannerMode,
    ToolResult,
)

API_VERSION    = "0.1.0"
_HISTORY_WINDOW = 20


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_steps(steps: list[AgentStep]) -> str:
    """Build a compact step-by-step header shown above the final answer."""
    if not steps:
        return ""
    lines = []
    for s in steps:
        status = "✓" if s.tool_result.ok else "✗"
        lines.append(f"[{status} {s.user_facing_label}]")
    return "\n".join(lines)


@dataclass
class TurnOutput:
    session_id: str
    assistant_message: str
    route_kind: str
    policy_kind: str | None
    tool_result: ToolResult | None          # last tool result (single-step compat)
    pending_clarification: PendingClarification | None
    pending_confirmation: PendingConfirmation | None
    planner_mode: PlannerMode = field(default="heuristic")
    agent_steps: list[AgentStep] = field(default_factory=list)
    hit_step_limit: bool = False


def process_turn(*, session_id: str | None, message: str) -> TurnOutput:
    now = _utc_now()
    sid = session_id or str(uuid4())

    try:
        session = load_session(sid)
    except SessionNotFoundError:
        session = create_session(session_id=sid, created_at=now)

    result = run_agent(
        message,
        conversation_history=session.messages[-_HISTORY_WINDOW:],
        pending_clarification=session.pending_clarification,
        pending_confirmation=session.pending_confirmation,
    )

    # Build the full assistant message — step trail + final answer.
    step_header = _format_steps(result.steps)
    if step_header:
        assistant_message = f"{step_header}\n\n{result.final_message}"
    else:
        assistant_message = result.final_message

    # Last tool result for API compatibility.
    last_tool_result = result.steps[-1].tool_result if result.steps else None

    # Persist session.
    session.messages.append({"role": "user",      "content": message})
    session.messages.append({"role": "assistant",  "content": assistant_message})
    session.metadata.updated_at = _utc_now()
    session.pending_clarification = result.pending_clarification
    session.pending_confirmation  = result.pending_confirmation
    if last_tool_result is not None:
        session.last_tool_execution = last_tool_result

    save_session(session)

    # Extract long-term memories (fire-and-forget).
    try:
        from core.memory.extractor import extract_facts  # noqa: PLC0415
        from core.memory.store import save_facts  # noqa: PLC0415
        new_facts = extract_facts(session.messages[-_HISTORY_WINDOW:], source_session_id=sid)
        if new_facts:
            save_facts(new_facts, source_session_id=sid)
    except Exception:
        pass

    return TurnOutput(
        session_id=sid,
        assistant_message=assistant_message,
        route_kind=result.route_kind,
        policy_kind=result.policy_kind,
        tool_result=last_tool_result,
        pending_clarification=result.pending_clarification,
        pending_confirmation=result.pending_confirmation,
        planner_mode=result.planner_mode,
        agent_steps=result.steps,
        hit_step_limit=result.hit_step_limit,
    )
