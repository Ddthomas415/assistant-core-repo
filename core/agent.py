"""
Agent loop.

Runs plan → execute → feed result back → plan again until the model
produces a final text answer or a safety stop condition is hit.

Safety rules (non-negotiable):
  - write_file and edit_file always break the loop and require confirmation.
  - Hard step limit (default 10, env AGENT_MAX_STEPS).
  - clarify routes always break the loop.
  - If the limit is reached, the partial work so far is returned.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from core.planner import plan_turn
from core.policy import ACTION_POLICY
from core.tool_registry import execute_tool_request
from core.types import (
    PendingClarification,
    PendingConfirmation,
    PlannerMode,
    PolicyOutcome,
    RouteDecision,
    ToolRequest,
    ToolResult,
)

_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class AgentStep:
    """One step in an agent run — a tool call and its result."""
    step_number: int
    tool_name: str
    user_facing_label: str
    tool_result: ToolResult


@dataclass
class AgentResult:
    """
    The complete output of a run_agent call.

    final_message     — what to show the user
    route_kind        — last route kind (answer / confirm / clarify)
    policy_kind       — last policy outcome kind, if any
    steps             — all tool steps executed
    pending_clarification  — set if loop stopped for clarification
    pending_confirmation   — set if loop stopped for confirmation
    planner_mode      — which planner was used
    hit_step_limit    — True if stopped due to step limit
    """
    final_message: str
    route_kind: str
    policy_kind: str | None
    steps: list[AgentStep] = field(default_factory=list)
    pending_clarification: PendingClarification | None = None
    pending_confirmation: PendingConfirmation | None = None
    planner_mode: PlannerMode = "heuristic"
    hit_step_limit: bool = False


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_agent(
    user_message: str,
    *,
    conversation_history: list[dict[str, Any]] | None = None,
    pending_clarification: PendingClarification | None = None,
    pending_confirmation: PendingConfirmation | None = None,
    max_steps: int = _MAX_STEPS,
) -> AgentResult:
    """
    Run the agent loop for one user turn.

    The loop:
      1. Plan (planner decides: answer / clarify / confirm / tool).
      2. If answer → done.
      3. If clarify or confirm → stop, return pending state.
      4. If tool:
           a. write_file / edit_file → stop, return pending confirmation.
           b. read / list / search / fetch → execute, append result to
              history, loop back to step 1.
      5. If step limit reached → return partial answer.
    """
    history: list[dict[str, Any]] = list(conversation_history or [])
    steps:   list[AgentStep]      = []
    planner_mode: PlannerMode     = "heuristic"

    # Current pending state (may be resolved on first plan call)
    cur_clarification = pending_clarification
    cur_confirmation  = pending_confirmation

    for step_num in range(1, max_steps + 1):
        route, policy, planner_mode = plan_turn(
            user_message,
            conversation_history=history,
            pending_clarification=cur_clarification,
            pending_confirmation=cur_confirmation,
        )
        # Clear pending after first use — plan_turn consumed them.
        # Remember whether a confirmation was consumed so we can skip the
        # policy gate below (the user already approved it).
        had_pending_confirmation = cur_confirmation is not None
        cur_clarification = None
        cur_confirmation  = None

        if route.kind == "answer":
            return AgentResult(
                final_message=route.answer_text or "I don't have an answer yet.",
                route_kind="answer",
                policy_kind=policy.kind if policy else None,
                steps=steps,
                planner_mode=planner_mode,
            )

        if route.kind == "clarify":
            return AgentResult(
                final_message=route.clarification_prompt or "Please clarify.",
                route_kind="clarify",
                policy_kind=policy.kind if policy else None,
                steps=steps,
                pending_clarification=_make_pending_clarification(route, user_message),
                planner_mode=planner_mode,
            )

        if route.kind == "confirm":
            return AgentResult(
                final_message=route.confirmation_prompt or "Please confirm.",
                route_kind="confirm",
                policy_kind=policy.kind if policy else None,
                steps=steps,
                pending_confirmation=_make_pending_confirmation(route),
                planner_mode=planner_mode,
            )

        if route.kind == "tool" and route.tool_request is not None:
            tool_req = route.tool_request
            tool_policy = ACTION_POLICY.get(tool_req.tool_name, "block")

            # Modifying tools always break the loop — never autonomous writes.
            # Exception: if the user just confirmed this action, execute it.
            if tool_policy == "confirm" and not had_pending_confirmation:
                return AgentResult(
                    final_message=f"Do you want me to {tool_req.user_facing_label}?",
                    route_kind="confirm",
                    policy_kind="require_confirmation",
                    steps=steps,
                    pending_confirmation=_make_pending_confirmation(route),
                    planner_mode=planner_mode,
                )

            # Execute the tool.
            tool_result = execute_tool_request(tool_req)
            step = AgentStep(
                step_number=step_num,
                tool_name=tool_req.tool_name,
                user_facing_label=tool_req.user_facing_label,
                tool_result=tool_result,
            )
            steps.append(step)

            # If the tool failed, surface the error immediately.
            if not tool_result.ok:
                return AgentResult(
                    final_message=f"Tool failed: {tool_result.error_message or tool_result.summary}",
                    route_kind="answer",
                    policy_kind=policy.kind if policy else None,
                    steps=steps,
                    planner_mode=planner_mode,
                )

            # Heuristic router has no history awareness — it would route
            # the same message identically on the next iteration, creating
            # an infinite loop.  Produce the formatted answer and stop.
            if planner_mode in {"heuristic", "model_fallback"}:
                return AgentResult(
                    final_message=_format_result_message(tool_req, tool_result),
                    route_kind="answer",
                    policy_kind=policy.kind if policy else None,
                    steps=steps,
                    planner_mode=planner_mode,
                )

            # Model mode — feed result into history and let the model decide
            # whether to call another tool or produce a final answer.
            history = _append_tool_result(history, user_message, tool_req, tool_result)
            continue

    # Step limit reached.
    return AgentResult(
        final_message=(
            "I've done as much as I can in one turn. "
            f"Completed {len(steps)} step(s). Ask me to continue if needed."
        ),
        route_kind="answer",
        policy_kind=None,
        steps=steps,
        planner_mode=planner_mode,
        hit_step_limit=True,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_result_message(tool_req: ToolRequest, tool_result: ToolResult) -> str:
    """Format a tool result as a human-readable message (heuristic path)."""
    data  = tool_result.data or {}
    label = tool_req.user_facing_label

    if tool_result.tool_name == "read_file":
        return f"[reading {data.get('filename','')}...]\n\n{data.get('content','')}"
    if tool_result.tool_name == "list_workspace":
        files: list[str] = data.get("files", [])
        if not files:
            return "[listing workspace...]\n\nWorkspace is empty."
        return f"[listing workspace...]\n\n{len(files)} file(s):\n" + "\n".join(f"  {f}" for f in files)
    if tool_result.tool_name == "write_file":
        return f"[writing {data.get('filename','')}...]\n\nWrote {data.get('filename','')} successfully."
    if tool_result.tool_name == "edit_file":
        return f"[editing {data.get('filename','')}...]\n\nEdited {data.get('filename','')} successfully."
    if tool_result.tool_name == "web_search":
        from core.tools.web_search import format_results  # noqa: PLC0415
        return f"[searching for \"{data.get('query','')}\"...]\n\n{format_results(data)}"
    if tool_result.tool_name == "fetch_page":
        from core.tools.fetch_page import format_result  # noqa: PLC0415
        return f"[fetching {data.get('url','')}...]\n\n{format_result(data)}"
    return f"[{label}]\n{tool_result.summary}"


def _append_tool_result(
    history: list[dict[str, Any]],
    user_message: str,
    tool_req: ToolRequest,
    tool_result: ToolResult,
) -> list[dict[str, Any]]:
    """
    Append the tool execution as a synthetic exchange in history so the
    next plan call sees what was done and what came back.
    """
    result_text = (
        f"Tool '{tool_req.tool_name}' result:\n{tool_result.summary}"
        if not tool_result.ok
        else _summarise_tool_data(tool_req.tool_name, tool_result)
    )
    return history + [
        {"role": "user",      "content": user_message},
        {"role": "assistant", "content": f"[{tool_req.user_facing_label}...]\n{result_text}"},
    ]


def _summarise_tool_data(tool_name: str, tool_result: ToolResult) -> str:
    """Produce a compact summary of tool output for history injection."""
    data = tool_result.data or {}

    if tool_name == "read_file":
        content: str = data.get("content", "")
        return content[:2000] + ("…" if len(content) > 2000 else "")

    if tool_name == "list_workspace":
        files: list[str] = data.get("files", [])
        return "Files: " + (", ".join(files) if files else "(empty)")

    if tool_name == "web_search":
        from core.tools.web_search import format_results  # noqa: PLC0415
        return format_results(data)[:1500]

    if tool_name == "fetch_page":
        content = data.get("content", "")
        return content[:2000] + ("…" if len(content) > 2000 else "")

    return tool_result.summary


def _make_pending_clarification(
    route: RouteDecision,
    user_message: str,
) -> PendingClarification:
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=24)
    return PendingClarification(
        clarification_id=str(uuid4()),
        created_at=now.isoformat().replace("+00:00", "Z"),
        expires_at=exp.isoformat().replace("+00:00", "Z"),
        prompt=route.clarification_prompt or "Please clarify.",
        target=route.clarification_target or "user_intent",
        bound_user_request=user_message,
        allowed_reply_kinds=[route.clarification_target or "user_intent"],
    )


def _make_pending_confirmation(route: RouteDecision) -> PendingConfirmation:
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=24)
    return PendingConfirmation(
        confirmation_id=str(uuid4()),
        action_id=str(uuid4()),
        created_at=now.isoformat().replace("+00:00", "Z"),
        expires_at=exp.isoformat().replace("+00:00", "Z"),
        prompt=route.confirmation_prompt or "Please confirm.",
        requested_action=route.requested_action,
    )
