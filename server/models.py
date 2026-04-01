from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """
    Input to POST /chat.

    session_id is optional — omit it to start a new session.
    The response always includes the session_id so the client
    can pass it back on subsequent turns.
    """

    session_id: str | None = Field(
        default=None,
        description="Existing session ID. Omit to start a new session.",
    )
    message: str = Field(
        description="The user message for this turn.",
    )


class ToolResultOut(BaseModel):
    """Serialisable form of core.types.ToolResult."""

    ok: bool
    tool_name: str
    summary: str
    data: Any = None
    error_code: str | None = None
    error_message: str | None = None


class PendingClarificationOut(BaseModel):
    """
    Tells the client a clarification is expected.

    The client should surface the prompt and echo the user's
    reply back as the next message.
    """

    prompt: str
    target: str


class PendingConfirmationOut(BaseModel):
    """
    Tells the client a confirmation is pending.

    The client should surface the prompt and accept yes/no/cancel.
    """

    prompt: str
    action_name: str
    user_facing_label: str


class ChatResponse(BaseModel):
    """
    Output from POST /chat.

    Exactly one of the following will be present depending on route_kind:
    - answer         → assistant_message only
    - clarify        → assistant_message + pending_clarification
    - confirm        → assistant_message + pending_confirmation
    - tool           → assistant_message + tool_result
    """

    session_id: str
    assistant_message: str
    route_kind: str
    policy_kind: str | None = None
    tool_result: ToolResultOut | None = None
    pending_clarification: PendingClarificationOut | None = None
    pending_confirmation: PendingConfirmationOut | None = None
    planner_mode: str = "heuristic"
    agent_steps: list[dict] = []
    hit_step_limit: bool = False


class SessionSummary(BaseModel):
    """One row in the session list sidebar."""

    session_id: str
    created_at: str
    updated_at: str
    message_count: int
    preview: str | None = None  # First user message, truncated


class SessionMessages(BaseModel):
    """Full message history for a session."""

    session_id: str
    messages: list[dict[str, Any]]


class MemoryFact(BaseModel):
    """One stored long-term memory fact."""

    id: str
    content: str
    source_session_id: str | None = None
    created_at: str


class HealthResponse(BaseModel):
    status: str
    version: str
