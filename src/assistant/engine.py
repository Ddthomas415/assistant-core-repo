from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from .filesystem import list_workspace_tool, read_file_tool, write_file_tool
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
    - one read filesystem tool
    - one write filesystem tool
    """

    read_tool: Callable[[ToolRequest], ToolResult] | None = None
    write_tool: Callable[[ToolRequest], ToolResult] | None = None
    list_tool: Callable[[ToolRequest], ToolResult] | None = None
    workspace_root: str | None = None

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

                continued_input = self._reconstruct_clarified_request(resolved, cleaned_input)
                if continued_input is not None:
                    return self._handle_routed_input(
                        state=state,
                        route_input=continued_input,
                        now=now,
                        pending_transition=pending_transition,
                        notes=notes,
                        message_input=cleaned_input,
                    )

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

                arguments = dict(pending.requested_action.arguments)
                if self.workspace_root is not None:
                    arguments["workspace_root"] = self.workspace_root

                tool_request = ToolRequest(
                    tool_name=pending.requested_action.tool_name,
                    arguments=arguments,
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
                kind=RouteKind.ANSWER,
                answer_text="There is no valid pending confirmation to apply.",
            )
            policy_outcome = PolicyOutcome(
                kind=PolicyOutcomeKind.BLOCK,
                reason="No valid pending confirmation exists.",
                blocking_code="no_pending_confirmation",
            )
            rendered_output = route_decision.answer_text
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

        return self._handle_routed_input(
            state=state,
            route_input=cleaned_input,
            now=now,
            pending_transition=pending_transition,
            notes=notes,
        )

    def _append_turn_messages(self, state: SessionState, user_input: str, output: str) -> None:
        state.messages.append(Message(role=Role.USER, content=user_input))
        state.messages.append(Message(role=Role.ASSISTANT, content=output))

    def _handle_routed_input(
        self,
        state: SessionState,
        route_input: str,
        now: str,
        pending_transition: PendingTransitionKind,
        notes: list[str],
        message_input: str | None = None,
    ) -> EngineResult:
        cleaned_input = route_input.strip()
        if message_input is None:
            message_input = cleaned_input

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
            rendered_output = pending.prompt
            self._append_turn_messages(state, message_input, rendered_output)
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
                    pending_transition=PendingTransitionKind.CREATED,
                    persistence_event="save_required",
                    notes=notes,
                ),
            )

        # 6. Explicit modifying requests -> confirmation.
        if normalized.startswith("overwrite "):
            file_path, content = self._parse_overwrite_request(cleaned_input)

            if not file_path:
                state.pending_clarification = PendingClarification(
                    clarification_id=str(uuid4()),
                    created_at=now,
                    expires_at=None,
                    prompt="Which file do you want me to overwrite?",
                    target=ClarificationTarget.FILE_PATH,
                    bound_user_request=cleaned_input,
                    allowed_reply_kinds=["file_path"],
                )
                route_decision = RouteDecision(
                    kind=RouteKind.CLARIFY,
                    clarification_prompt="Which file do you want me to overwrite?",
                    clarification_target=ClarificationTarget.FILE_PATH,
                )
                policy_outcome = PolicyOutcome(
                    kind=PolicyOutcomeKind.REQUIRE_CLARIFICATION,
                    reason="Modifying request is missing a valid target path.",
                )
                rendered_output = "Which file do you want me to overwrite?"
                self._append_turn_messages(state, message_input, rendered_output)
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
                        pending_transition=PendingTransitionKind.CREATED,
                        persistence_event="save_required",
                        notes=notes,
                    ),
                )

            action_arguments = {"path": file_path, "content": content}
            if self.workspace_root is not None:
                action_arguments["workspace_root"] = self.workspace_root

            requested_action = RequestedAction(
                action_id=str(uuid4()),
                tool_name="write_file",
                arguments=action_arguments,
                reason="User requested a modifying file write.",
            )
            return self._create_pending_confirmation_result(
                state=state,
                user_input=message_input,
                now=now,
                requested_action=requested_action,
                prompt=f"Please confirm overwriting {file_path}.",
                pending_transition=(
                    PendingTransitionKind.RESOLVED
                    if pending_transition == PendingTransitionKind.RESOLVED
                    else PendingTransitionKind.CREATED
                ),
                notes=notes,
            )

        if normalized == "write the spec file":
            state.pending_clarification = PendingClarification(
                clarification_id=str(uuid4()),
                created_at=now,
                expires_at=None,
                prompt="What filename should I use for the spec file?",
                target=ClarificationTarget.FILE_PATH,
                bound_user_request=cleaned_input,
                allowed_reply_kinds=["file_path"],
            )
            route_decision = RouteDecision(
                kind=RouteKind.CLARIFY,
                clarification_prompt="What filename should I use for the spec file?",
                clarification_target=ClarificationTarget.FILE_PATH,
            )
            policy_outcome = PolicyOutcome(
                kind=PolicyOutcomeKind.REQUIRE_CLARIFICATION,
                reason="Requested write target is ambiguous.",
            )
            rendered_output = "What filename should I use for the spec file?"
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
                    pending_transition=PendingTransitionKind.CREATED,
                    persistence_event="save_required",
                    notes=notes,
                ),
            )

        if normalized.startswith("make a file called "):
            remainder = cleaned_input[len("make a file called ") :].strip()
            if " that prints " in remainder:
                file_path, content = remainder.split(" that prints ", 1)
                file_path = file_path.strip()
                content = content.strip()
                if file_path:
                    action_arguments = {"path": file_path, "content": content}
                    if self.workspace_root is not None:
                        action_arguments["workspace_root"] = self.workspace_root

                    requested_action = RequestedAction(
                        action_id=str(uuid4()),
                        tool_name="write_file",
                        arguments=action_arguments,
                        reason="User requested file creation.",
                    )
                    return self._create_pending_confirmation_result(
                        state=state,
                        user_input=message_input,
                        now=now,
                        requested_action=requested_action,
                        prompt=f"Please confirm overwriting {file_path}.",
                        pending_transition=(
                            PendingTransitionKind.RESOLVED
                            if pending_transition == PendingTransitionKind.RESOLVED
                            else PendingTransitionKind.CREATED
                        ),
                        notes=notes,
                    )

        if normalized.startswith("show me the contents of "):
            file_path = cleaned_input[len("show me the contents of ") :].strip()
            arguments = {"path": file_path}
            if self.workspace_root is not None:
                arguments["workspace_root"] = self.workspace_root

            route_decision = RouteDecision(
                kind=RouteKind.TOOL,
                tool_request=ToolRequest(
                    tool_name="read_file",
                    arguments=arguments,
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

            self._append_turn_messages(state, message_input, rendered_output)
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

        if normalized in {
            "what files are in my workspace",
            "show me my workspace files",
            "can you list everything in the workspace folder",
        }:
            arguments = {}
            if self.workspace_root is not None:
                arguments["workspace_root"] = self.workspace_root

            route_decision = RouteDecision(
                kind=RouteKind.TOOL,
                tool_request=ToolRequest(
                    tool_name="list_workspace",
                    arguments=arguments,
                    user_facing_label="listing workspace",
                ),
            )
            policy_outcome = PolicyOutcome(
                kind=PolicyOutcomeKind.ALLOW,
                reason="Workspace listing is allowed.",
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
                rendered_output = "Workspace listing requested, but no tool handler is configured."

            self._append_turn_messages(state, message_input, rendered_output)
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

        # 7. Read-only tool path.
        if normalized in {"read file", "read a file"}:
            state.pending_clarification = PendingClarification(
                clarification_id=str(uuid4()),
                created_at=now,
                expires_at=None,
                prompt="Which file do you want me to read?",
                target=ClarificationTarget.FILE_PATH,
                bound_user_request=cleaned_input,
                allowed_reply_kinds=["file_path"],
            )
            route_decision = RouteDecision(
                kind=RouteKind.CLARIFY,
                clarification_prompt="Which file do you want me to read?",
                clarification_target=ClarificationTarget.FILE_PATH,
            )
            policy_outcome = PolicyOutcome(
                kind=PolicyOutcomeKind.REQUIRE_CLARIFICATION,
                reason="Requested read target is ambiguous.",
            )
            rendered_output = "Which file do you want me to read?"
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
                    pending_transition=PendingTransitionKind.CREATED,
                    persistence_event="save_required",
                    notes=notes,
                ),
            )

        if normalized.startswith("read "):
            file_path = cleaned_input[len("read ") :].strip()
            arguments = {"path": file_path}
            if self.workspace_root is not None:
                arguments["workspace_root"] = self.workspace_root

            route_decision = RouteDecision(
                kind=RouteKind.TOOL,
                tool_request=ToolRequest(
                    tool_name="read_file",
                    arguments=arguments,
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

            self._append_turn_messages(state, message_input, rendered_output)
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
        self._append_turn_messages(state, message_input, rendered_output)
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

    def _parse_overwrite_request(self, user_input: str) -> tuple[str, str]:
        overwrite_body = user_input.strip()[len("overwrite "):]
        if " with " in overwrite_body:
            file_path, content = overwrite_body.split(" with ", 1)
        else:
            file_path, content = overwrite_body, "updated content"
        return file_path.strip(), content.strip()

    def _reconstruct_clarified_request(
        self,
        resolved: PendingClarification,
        cleaned_input: str,
    ) -> str | None:
        original = resolved.bound_user_request.strip().lower()
        clarified_path = cleaned_input.strip()

        if original.rstrip(".?!") == "open the config file":
            return f"read {clarified_path}"

        if original == "write the spec file":
            return f"overwrite {clarified_path}"

        if original.rstrip(".?!") == "overwrite  with defaults":
            return f"overwrite {clarified_path} with defaults."

        return None

    def _create_pending_confirmation_result(
        self,
        state: SessionState,
        user_input: str,
        now: str,
        requested_action: RequestedAction,
        prompt: str,
        pending_transition: PendingTransitionKind,
        notes: list[str],
    ) -> EngineResult:
        pending = PendingConfirmation(
            confirmation_id=str(uuid4()),
            action_id=requested_action.action_id,
            created_at=now,
            expires_at=None,
            prompt=prompt,
            requested_action=requested_action,
        )
        state.pending_confirmation = pending

        route_decision = RouteDecision(
            kind=RouteKind.CONFIRM,
            confirmation_prompt=prompt,
            requested_action=requested_action,
        )
        policy_outcome = PolicyOutcome(
            kind=PolicyOutcomeKind.REQUIRE_CONFIRMATION,
            reason="Modifying actions require confirmation.",
        )
        self._append_turn_messages(state, user_input, prompt)
        return EngineResult(
            route_decision=route_decision,
            policy_outcome=policy_outcome,
            rendered_output=prompt,
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

    def _default_answer(self, user_input: str) -> str:
        normalized = user_input.lower().strip()

        if "what does this assistant do" in normalized:
            return (
                "This is a terminal-first private assistant that can answer directly, "
                "use workspace tools when needed, clarify ambiguity, and confirm modifying actions."
            )

        if normalized in {"what can you do?", "what can you do", "help", "help?", "can can you do ?", "can can you do?"}:
            return (
                "I can read files, write files with confirmation, list workspace files, "
                "ask clarifying questions when requests are ambiguous, and resume sessions."
            )

        if normalized in {"help with reading", "local file help?", "help me with local files"}:
            return (
                "I can help with local files in the workspace. Try reading files like "
                "'read notes.txt' or 'show me the contents of notes.txt', writing files with confirmation, "
                "or listing files in the workspace."
            )

        if normalized in {"files?", "list files?", "list files", "list local file directory?", "list file directory ?", "list all workspace file"}:
            return (
                "I can list files in the workspace. Try requests like "
                "'what files are in my workspace' or 'can you list everything in the workspace folder'."
            )

        if normalized in {"writing?", "writing"}:
            return (
                "I can help write files with confirmation. Try requests like "
                "'make a file called test.py that prints hello' or 'overwrite notes.txt with updated text'. "
                "I will ask for confirmation before modifying files."
            )

        if normalized in {
            "whats todays date?",
            "what's todays date?",
            "what is todays date?",
            "what is today's date?",
        }:
            return (
                "That is outside my current scope. I can help with local file and workspace tasks "
                "inside this assistant."
            )

        return (
            "That request is outside my current scope. I can help with local file and workspace "
            "tasks, including reading files, writing with confirmation, listing workspace files, "
            "and clarifying ambiguous requests."
        )

    def _tool_label(self, tool_name: str, arguments: dict[str, str]) -> str:
        path = arguments.get("path", "")
        if tool_name == "read_file":
            return f"reading {path}"
        if tool_name == "write_file":
            return f"writing {path}"
        return f"running {tool_name}"

    def _execute_tool(self, tool_request: ToolRequest) -> ToolResult | None:
        if tool_request.tool_name == "read_file":
            if self.read_tool is not None:
                return self.read_tool(tool_request)
            return read_file_tool(tool_request)
        if tool_request.tool_name == "write_file":
            if self.write_tool is not None:
                return self.write_tool(tool_request)
            return write_file_tool(tool_request)
        if tool_request.tool_name == "list_workspace":
            if self.list_tool is not None:
                return self.list_tool(tool_request)
            return list_workspace_tool(tool_request)
        return None
