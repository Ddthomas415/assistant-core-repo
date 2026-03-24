from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from .models import (
    ClarificationTarget,
    EngineResult,
    LastToolExecution,
    Message,
    PendingClarification,
    PendingConfirmation,
    PendingTransitionKind,
    PolicyOutcome,
    PolicyOutcomeKind,
    RequestedAction,
    Role,
    RouteDecision,
    RouteKind,
    SessionState,
    ToolRequest,
    ToolResult,
    TurnTrace,
)
from .policy import (
    is_clarification_expired,
    is_confirmation_expired,
    is_confirmation_reply,
    satisfies_clarification,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Engine:
    """
    Minimal v1 engine.

    This is intentionally narrow:
    - direct answers
    - clarification for ambiguous file/action requests
    - confirmation for modifying actions
    - one fake read tool
    - one fake write tool
    """

    read_tool: Callable[[ToolRequest], ToolResult] | None = None
    write_tool: Callable[[ToolRequest], ToolResult] | None = None

    def handle_turn(self, state: SessionState, user_input: str) -> EngineResult:
        now = utc_now_iso()
        cleaned_input = user_input.strip()

        if state.metadata is not None:
            state.metadata.updated_at = now

        pending_transition = PendingTransitionKind.NONE
        notes: list[str] = []
        tool_result: ToolResult | None = None

        # 1. Expire stale pending state first.
        if is_confirmation_expired(state, now):
            state.pending_confirmation = None
            pending_transition = PendingTransitionKind.EXPIRED
            notes.append("expired_pending_confirmation_cleared")

        if is_clarification_expired(state, now):
            state.pending_clarification = None
            pending_transition = PendingTransitionKind.EXPIRED
            notes.append("expired_pending_clarification_cleared")

        # 2. Resolve valid pending clarification if the user reply satisfies it.
        if state.pending_clarification is not None:
            if satisfies_clarification(state.pending_clarification, cleaned_input):
                resolved = state.pending_clarification
                state.pending_clarification = None
                pending_transition = PendingTransitionKind.RESOLVED
                notes.append("pending_clarification_resolved")

                rendered_output = (
                    f"Thanks. I’ll use '{cleaned_input}' as the {resolved.target.value.replace('_', ' ')}."
                )
                route_decision = RouteDecision(
                    kind=RouteKind.CLARIFY,
                    clarification_prompt=resolved.prompt,
                    clarification_target=resolved.target,
                )
                policy_outcome = PolicyOutcome(
                    kind=PolicyOutcomeKind.ALLOW,
                    reason="Clarification reply satisfied pending clarification.",
                )
                self._append_turn_messages(state, cleaned_input, rendered_output)
                return EngineResult(
                    route_decision=route_decision,
                    policy_outcome=policy_outcome,
                    rendered_output=rendered_output,
                    tool_result=None,
                    trace=TurnTrace(
                        route_kind=route_decision.kind,
                        policy_outcome=policy_outcome.kind,
                        tool_invoked=False,
                        tool_execution_id=None,
                        pending_transition=pending_transition,
                        persistence_event="save_required",
                        notes=notes,
                    ),
                )

            # Unrelated input cancels clarification.
            if cleaned_input:
                state.pending_clarification = None
                pending_transition = PendingTransitionKind.SUPERSEDED
                notes.append("pending_clarification_superseded")

        # 3. Resolve valid pending confirmation if the user reply is a confirmation.
        if state.pending_confirmation is not None:
            if is_confirmation_reply(cleaned_input):
                pending = state.pending_confirmation
                state.pending_confirmation = None
                pending_transition = PendingTransitionKind.RESOLVED
                notes.append("pending_confirmation_resolved")

                route_decision = RouteDecision(
                    kind=RouteKind.CONFIRM,
                    confirmation_prompt=pending.prompt,
                    requested_action=pending.requested_action,
                )
                policy_outcome = PolicyOutcome(
                    kind=PolicyOutcomeKind.ALLOW,
                    reason="Confirmation reply matched pending action.",
                )

                tool_request = ToolRequest(
                    tool_name=pending.requested_action.tool_name,
                    arguments=pending.requested_action.arguments,
                    user_facing_label=self._tool_label(
                        pending.requested_action.tool_name,
                        pending.requested_action.arguments,
                    ),
                )

                tool_result = self._execute_tool(tool_request)
                if tool_result is not None:
                    state.last_tool_execution = LastToolExecution(
                        execution_id=tool_result.execution_id,
                        tool_name=tool_result.tool_name,
                        ok=tool_result.ok,
                        summary=tool_result.summary,
                        finished_at=tool_result.finished_at,
                    )
                    rendered_output = f"[{tool_request.user_facing_label}...]\n{tool_result.summary}"
                else:
                    rendered_output = "Confirmed, but no tool handler is configured."

                self._append_turn_messages(state, cleaned_input, rendered_output)
                return EngineResult(
                    route_decision=route_decision,
                    policy_outcome=policy_outcome,
                    rendered_output=rendered_output,
                    tool_result=tool_result,
                    trace=TurnTrace(
                        route_kind=route_decision.kind,
                        policy_outcome=policy_outcome.kind,
                        tool_invoked=tool_result is not None,
                        tool_execution_id=tool_result.execution_id if tool_result else None,
                        pending_transition=pending_transition,
                        persistence_event="save_required",
                        notes=notes,
                    ),
                )

            # Unrelated input cancels confirmation.
            if cleaned_input:
                state.pending_confirmation = None
                pending_transition = PendingTransitionKind.SUPERSEDED
                notes.append("pending_confirmation_superseded")

        # 4. Stale yes/confirm with no valid pending confirmation.
        if is_confirmation_reply(cleaned_input):
            route_decision = RouteDecision(
                kind=RouteKind.CONFIRM,
                confirmation_prompt="No valid pending confirmation.",
                requested_action=None,
            )
            policy_outcome = PolicyOutcome(
                kind=PolicyOutcomeKind.BLOCK,
                reason="No valid pending confirmation exists.",
                blocking_code="no_pending_confirmation",
            )
            rendered_output = "There is no valid pending confirmation to apply."
            self._append_turn_messages(state, cleaned_input, rendered_output)
            return EngineResult(
                route_decision=route_decision,
                policy_outcome=policy_outcome,
                rendered_output=rendered_output,
                tool_result=None,
                trace=TurnTrace(
                    route_kind=route_decision.kind,
                    policy_outcome=policy_outcome.kind,
                    tool_invoked=False,
                    tool_execution_id=None,
                    pending_transition=pending_transition,
                    persistence_event="save_required",
                    notes=notes,
                ),
            )

        normalized = cleaned_input.lower()

        # 5. Ambiguous requests -> clarification.
        if normalized in {"open the config file.", "open the config file"}:
            pending = PendingClarification(
                clarification_id=str(uuid4()),
                created_at=now,
                expires_at=None,
                prompt="Which config file do you want me to use?",
                target=ClarificationTarget.FILE_PATH,
                bound_user_request=cleaned_input,
                allowed_reply_kinds=["file_path"],
            )
            state.pending_clarification = pending
            route_decision = RouteDecision(
                kind=RouteKind.CLARIFY,
                clarification_prompt=pending.prompt,
                clarification_target=pending.target,
            )
            policy_outcome = PolicyOutcome(
                kind=PolicyOutcomeKind.REQUIRE_CLARIFICATION,
                reason="The target file is ambiguous.",
            )
            pending_transition = PendingTransitionKind.CREATED
            rendered_output = pending.prompt
            self._append_turn_messages(state, cleaned_input, rendered_output)
            return EngineResult(
                route_decision=route_decision,
                policy_outcome=policy_outcome,
                rendered_output=rendered_output,
                tool_result=None,
                trace=TurnTrace(
                    route_kind=route_decision.kind,
                    policy_outcome=policy_outcome.kind,
                    tool_invoked=False,
                    tool_execution_id=None,
                    pending_transition=pending_transition,
                    persistence_event="save_required",
                    notes=notes,
                ),
            )

        # 6. Explicit modifying requests -> confirmation.
        if normalized.startswith("overwrite "):
            path = cleaned_input[len("overwrite ") :].strip()
            if " with " in path:
                file_path, content = path.split(" with ", 1)
            else:
                file_path, content = path, "updated content"

            requested_action = RequestedAction(
                action_id=str(uuid4()),
                tool_name="write_file",
                arguments={"path": file_path.strip(), "content": content.strip()},
                reason="User requested a modifying file write.",
            )
            pending = PendingConfirmation(
                confirmation_id=str(uuid4()),
                action_id=requested_action.action_id,
                created_at=now,
                expires_at=None,
                prompt=f"Please confirm overwriting {file_path.strip()}.",
                requested_action=requested_action,
            )
            state.pending_confirmation = pending
            route_decision = RouteDecision(
                kind=RouteKind.TOOL,
                tool_request=ToolRequest(
                    tool_name="write_file",
                    arguments=requested_action.arguments,
                    user_facing_label=f"writing {file_path.strip()}",
                ),
            )
            policy_outcome = PolicyOutcome(
                kind=PolicyOutcomeKind.REQUIRE_CONFIRMATION,
                reason="Modifying actions require confirmation.",
            )
            pending_transition = PendingTransitionKind.CREATED
            rendered_output = pending.prompt
            self._append_turn_messages(state, cleaned_input, rendered_output)
            return EngineResult(
                route_decision=route_decision,
                policy_outcome=policy_outcome,
                rendered_output=rendered_output,
                tool_result=None,
                trace=TurnTrace(
                    route_kind=route_decision.kind,
                    policy_outcome=policy_outcome.kind,
                    tool_invoked=False,
                    tool_execution_id=None,
                    pending_transition=pending_transition,
                    persistence_event="save_required",
                    notes=notes,
                ),
            )

        # 7. Read-only tool path.
        if normalized.startswith("read "):
            file_path = cleaned_input[len("read ") :].strip()
            route_decision = RouteDecision(
                kind=RouteKind.TOOL,
                tool_request=ToolRequest(
                    tool_name="read_file",
                    arguments={"path": file_path},
                    user_facing_label=f"reading {file_path}",
                ),
            )
            policy_outcome = PolicyOutcome(
                kind=PolicyOutcomeKind.ALLOW,
                reason="Read-only tool use is allowed.",
            )
            tool_result = self._execute_tool(route_decision.tool_request)
            if tool_result is not None:
                state.last_tool_execution = LastToolExecution(
                    execution_id=tool_result.execution_id,
                    tool_name=tool_result.tool_name,
                    ok=tool_result.ok,
                    summary=tool_result.summary,
                    finished_at=tool_result.finished_at,
                )
                rendered_output = f"[{route_decision.tool_request.user_facing_label}...]\n{tool_result.summary}"
            else:
                rendered_output = "Read requested, but no read tool handler is configured."

            self._append_turn_messages(state, cleaned_input, rendered_output)
            return EngineResult(
                route_decision=route_decision,
                policy_outcome=policy_outcome,
                rendered_output=rendered_output,
                tool_result=tool_result,
                trace=TurnTrace(
                    route_kind=route_decision.kind,
                    policy_outcome=policy_outcome.kind,
                    tool_invoked=tool_result is not None,
                    tool_execution_id=tool_result.execution_id if tool_result else None,
                    pending_transition=pending_transition,
                    persistence_event="save_required",
                    notes=notes,
                ),
            )

        # 8. Default direct answer.
        route_decision = RouteDecision(
            kind=RouteKind.ANSWER,
            answer_text=self._default_answer(cleaned_input),
        )
        policy_outcome = PolicyOutcome(
            kind=PolicyOutcomeKind.ALLOW,
            reason="Direct answer does not require tool use.",
        )
        rendered_output = route_decision.answer_text or "I can help with that."
        self._append_turn_messages(state, cleaned_input, rendered_output)
        return EngineResult(
            route_decision=route_decision,
            policy_outcome=policy_outcome,
            rendered_output=rendered_output,
            tool_result=None,
            trace=TurnTrace(
                route_kind=route_decision.kind,
                policy_outcome=policy_outcome.kind,
                tool_invoked=False,
                tool_execution_id=None,
                pending_transition=pending_transition,
                persistence_event="save_required",
                notes=notes,
            ),
        )

    def _append_turn_messages(self, state: SessionState, user_input: str, output: str) -> None:
        state.messages.append(Message(role=Role.USER, content=user_input))
        state.messages.append(Message(role=Role.ASSISTANT, content=output))

    def _default_answer(self, user_input: str) -> str:
        if "what does this assistant do" in user_input.lower():
            return (
                "This is a terminal-first private assistant that can answer directly, "
                "use workspace tools when needed, clarify ambiguity, and confirm modifying actions."
            )
        return "I understood your request, but this minimal engine only supports the core trusted-turn flows."

    def _tool_label(self, tool_name: str, arguments: dict[str, str]) -> str:
        path = arguments.get("path", "")
        if tool_name == "read_file":
            return f"reading {path}"
        if tool_name == "write_file":
            return f"writing {path}"
        return f"running {tool_name}"

    def _execute_tool(self, tool_request: ToolRequest) -> ToolResult | None:
        if tool_request.tool_name == "read_file" and self.read_tool is not None:
            return self.read_tool(tool_request)
        if tool_request.tool_name == "write_file" and self.write_tool is not None:
            return self.write_tool(tool_request)
        return None
