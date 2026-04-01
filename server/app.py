from __future__ import annotations

import json
import os

from collections import defaultdict
import time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

# ---------------------------------------------------------------------------
# Auth + CORS config
#
# ASSISTANT_API_KEY  — set to enable Bearer token auth (skip for local dev)
# ALLOWED_ORIGIN     — CORS origin (default: * for local dev)
# ---------------------------------------------------------------------------
_API_KEY        = os.getenv("ASSISTANT_API_KEY", "")
_ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")
_PUBLIC_PATHS   = {"/health"}


from core.session_state import SESSIONS_DIR, SessionNotFoundError, load_session
from server.chat_service import API_VERSION, TurnOutput, process_turn
from server.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    MemoryFact,
    PendingClarificationOut,
    PendingConfirmationOut,
    SessionMessages,
    SessionSummary,
    ToolResultOut,
)

app = FastAPI(
    title="Assistant Core API",
    version=API_VERSION,
    description="Terminal-first AI assistant — HTTP interface over core/",
)

# ---------------------------------------------------------------------------
# CORS — allow any origin during development.
# Lock this down to your actual frontend origin before deploying.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_ALLOWED_ORIGIN],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Enforce Bearer token auth when ASSISTANT_API_KEY is set."""
    if _API_KEY and request.url.path not in _PUBLIC_PATHS:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer ") or auth_header[7:] != _API_KEY:
            return JSONResponse(
                status_code=401,
                content={"error": "unauthorized", "detail": "Invalid or missing API key"},
            )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Rate limiting
# Simple in-memory per-IP sliding window.
# RATE_LIMIT_RPM=60 (requests per minute, default 60)
# Set RATE_LIMIT_RPM=0 to disable.
# ---------------------------------------------------------------------------
_RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "60"))
_rate_buckets: dict[str, list[float]] = defaultdict(list)
_RATE_EXEMPT_PATHS = {"/health", "/docs", "/openapi.json"}


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if not _RATE_LIMIT_RPM or request.url.path in _RATE_EXEMPT_PATHS:
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now       = time.time()
    window    = 60.0

    hits = _rate_buckets[client_ip]
    _rate_buckets[client_ip] = [t for t in hits if now - t < window]
    _rate_buckets[client_ip].append(now)

    if len(_rate_buckets[client_ip]) > _RATE_LIMIT_RPM:
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limited", "detail": f"Max {_RATE_LIMIT_RPM} requests/minute"},
            headers={"Retry-After": "60"},
        )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Global error handlers
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all — returns a structured JSON error instead of a 500 HTML page."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "detail": str(exc),
            "path": str(request.url.path),
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "detail": str(exc)},
    )


@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": "not_found", "detail": str(exc)},
    )


# ---------------------------------------------------------------------------
# Response assembly
# ---------------------------------------------------------------------------


def _build_response(turn: TurnOutput) -> ChatResponse:
    """Convert a TurnOutput (internal dataclasses) into a ChatResponse (Pydantic)."""

    tool_result_out = None
    if turn.tool_result is not None:
        tool_result_out = ToolResultOut(
            ok=turn.tool_result.ok,
            tool_name=turn.tool_result.tool_name,
            summary=turn.tool_result.summary,
            data=turn.tool_result.data,
            error_code=turn.tool_result.error_code,
            error_message=turn.tool_result.error_message,
        )

    pending_clarification_out = None
    if turn.pending_clarification is not None:
        pending_clarification_out = PendingClarificationOut(
            prompt=turn.pending_clarification.prompt,
            target=turn.pending_clarification.target,
        )

    pending_confirmation_out = None
    if turn.pending_confirmation is not None:
        pending_confirmation_out = PendingConfirmationOut(
            prompt=turn.pending_confirmation.prompt,
            action_name=turn.pending_confirmation.requested_action.action_name,
            user_facing_label=turn.pending_confirmation.requested_action.user_facing_label,
        )

    return ChatResponse(
        session_id=turn.session_id,
        assistant_message=turn.assistant_message,
        route_kind=turn.route_kind,
        policy_kind=turn.policy_kind,
        tool_result=tool_result_out,
        pending_clarification=pending_clarification_out,
        pending_confirmation=pending_confirmation_out,
        planner_mode=turn.planner_mode,
        agent_steps=[
            {
                "step": s.step_number,
                "tool": s.tool_name,
                "label": s.user_facing_label,
                "ok": s.tool_result.ok,
                "summary": s.tool_result.summary,
            }
            for s in turn.agent_steps
        ],
        hit_step_limit=turn.hit_step_limit,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/system", tags=["meta"])
def system_stats() -> dict:
    """Live system metrics for the HUD dashboard."""
    try:
        import psutil  # noqa: PLC0415
        cpu    = psutil.cpu_percent(interval=0.1)
        mem    = psutil.virtual_memory()
        disk   = psutil.disk_usage("/")
        boot   = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
        uptime = int((datetime.now(tz=timezone.utc) - boot).total_seconds())
        return {
            "cpu_percent":    cpu,
            "mem_percent":    mem.percent,
            "mem_used_gb":    round(mem.used / 1e9, 1),
            "mem_total_gb":   round(mem.total / 1e9, 1),
            "disk_percent":   disk.percent,
            "disk_used_gb":   round(disk.used / 1e9, 1),
            "disk_total_gb":  round(disk.total / 1e9, 1),
            "uptime_seconds": uptime,
        }
    except ImportError:
        return {"error": "psutil not installed — run: pip install psutil"}


@app.get("/weather", tags=["meta"])
def current_weather() -> dict:
    """Current weather at the server location — used by the HUD weather widget."""
    from core.tools.weather import get_weather  # noqa: PLC0415
    return get_weather()


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Liveness check. Returns immediately with no side effects."""
    return HealthResponse(status="ok", version=API_VERSION)


@app.get("/sessions", response_model=list[SessionSummary], tags=["sessions"])
def list_sessions() -> list[SessionSummary]:
    """
    Return all persisted sessions, newest first.

    Used by the UI sidebar to populate the session list.
    """
    summaries: list[SessionSummary] = []

    if not SESSIONS_DIR.exists():
        return summaries

    paths = sorted(
        SESSIONS_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            messages: list[dict] = data.get("messages", [])

            preview = next(
                (m["content"][:72] for m in messages if m.get("role") == "user"),
                None,
            )

            summaries.append(
                SessionSummary(
                    session_id=data["session_id"],
                    created_at=data["metadata"]["created_at"],
                    updated_at=data["metadata"]["updated_at"],
                    message_count=len(messages),
                    preview=preview,
                )
            )
        except Exception:
            continue

    return summaries


@app.get("/sessions/{session_id}", response_model=SessionMessages, tags=["sessions"])
def get_session(session_id: str) -> SessionMessages:
    """
    Return the full message history for a session.

    Used by the UI when the user clicks a session in the sidebar.
    """
    try:
        session = load_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionMessages(session_id=session_id, messages=session.messages)


@app.get("/memory", response_model=list[MemoryFact], tags=["memory"])
def list_memory() -> list[MemoryFact]:
    """Return all stored long-term memory facts, newest first."""
    from core.memory.store import get_all  # noqa: PLC0415
    return [
        MemoryFact(
            id=f.id,
            content=f.content,
            source_session_id=f.source_session_id,
            created_at=f.created_at,
        )
        for f in get_all()
    ]


@app.delete("/memory/{fact_id}", tags=["memory"])
def delete_memory(fact_id: str) -> dict:
    """Delete a single memory fact by ID."""
    from core.memory.store import delete_fact  # noqa: PLC0415
    deleted = delete_fact(fact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"deleted": fact_id}


@app.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(request: ChatRequest) -> ChatResponse:
    """
    Process one assistant turn.

    - Omit session_id to start a new session; the response includes the
      assigned session_id for use on subsequent turns.
    - Pending clarification/confirmation state is persisted and replayed
      automatically from session — the client just needs to pass the same
      session_id and the user's reply.
    """
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty")

    try:
        turn = process_turn(session_id=request.session_id, message=request.message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Turn processing failed: {exc}") from exc

    return _build_response(turn)


@app.post("/chat/stream", tags=["chat"])
def chat_stream(request: ChatRequest) -> StreamingResponse:
    """
    Process one assistant turn with Server-Sent Events streaming.

    Emits one SSE event per agent step as it completes, then a final
    `done` event with the full ChatResponse payload.

    Event types:
      data: {"type": "step",   "step": N, "tool": "...", "label": "...", "ok": true, "summary": "..."}
      data: {"type": "done",   ...full ChatResponse fields...}
      data: {"type": "error",  "detail": "..."}
    """
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty")

    def event_stream():
        try:
            from core.agent import AgentStep, run_agent  # noqa: PLC0415
            from core.session_state import (  # noqa: PLC0415
                SessionNotFoundError,
                create_session,
                load_session,
                save_session,
            )
            from core.types import PendingClarification, PendingConfirmation  # noqa: PLC0415
            from datetime import datetime, timedelta, timezone  # noqa: PLC0415
            from uuid import uuid4  # noqa: PLC0415

            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            sid = request.session_id or str(uuid4())

            try:
                session = load_session(sid)
            except SessionNotFoundError:
                session = create_session(session_id=sid, created_at=now)

            # Run agent step by step, yielding each tool event immediately.
            from core.planner import plan_turn  # noqa: PLC0415
            from core.policy import ACTION_POLICY  # noqa: PLC0415
            from core.tool_registry import execute_tool_request  # noqa: PLC0415

            _HISTORY_WINDOW = 20
            history = list(session.messages[-_HISTORY_WINDOW:])
            steps: list[AgentStep] = []
            cur_clarification = session.pending_clarification
            cur_confirmation  = session.pending_confirmation
            planner_mode = "heuristic"
            final_route_kind = "answer"
            final_policy_kind = None
            new_pending_clarification = None
            new_pending_confirmation  = None

            import os  # noqa: PLC0415
            max_steps = int(os.getenv("AGENT_MAX_STEPS", "10"))

            for step_num in range(1, max_steps + 1):
                route, policy, planner_mode = plan_turn(
                    request.message,
                    conversation_history=history,
                    pending_clarification=cur_clarification,
                    pending_confirmation=cur_confirmation,
                )
                had_pending = cur_clarification is not None or cur_confirmation is not None
                cur_clarification = None
                cur_confirmation  = None
                final_policy_kind = policy.kind if policy else None

                if route.kind in ("answer", "clarify", "confirm"):
                    final_route_kind = route.kind
                    if route.kind == "clarify":
                        from core.agent import _make_pending_clarification  # noqa: PLC0415
                        new_pending_clarification = _make_pending_clarification(route, request.message)
                    if route.kind == "confirm":
                        from core.agent import _make_pending_confirmation  # noqa: PLC0415
                        new_pending_confirmation = _make_pending_confirmation(route)
                    break

                if route.kind == "tool" and route.tool_request is not None:
                    tool_req = route.tool_request
                    tool_policy = ACTION_POLICY.get(tool_req.tool_name, "block")
                    had_pending_confirmation = had_pending and cur_confirmation is None

                    if tool_policy == "confirm" and not had_pending_confirmation:
                        from core.agent import _make_pending_confirmation  # noqa: PLC0415
                        final_route_kind = "confirm"
                        new_pending_confirmation = _make_pending_confirmation(route)
                        break

                    tool_result = execute_tool_request(tool_req)
                    step = AgentStep(step_num, tool_req.tool_name, tool_req.user_facing_label, tool_result)
                    steps.append(step)

                    # Yield step event immediately.
                    yield f"data: {json.dumps({'type': 'step', 'step': step_num, 'tool': tool_req.tool_name, 'label': tool_req.user_facing_label, 'ok': tool_result.ok, 'summary': tool_result.summary})}\n\n"

                    if not tool_result.ok:
                        final_route_kind = "answer"
                        break

                    if planner_mode in ("heuristic", "model_fallback"):
                        final_route_kind = "answer"
                        break

                    history = list(history) + [
                        {"role": "user",      "content": request.message},
                        {"role": "assistant",  "content": f"[{tool_req.user_facing_label}]\n{tool_result.summary}"},
                    ]
                    continue

            # Build final message using process_turn (handles persistence + memory).
            # We re-run process_turn here so session saving, memory extraction,
            # and response formatting all happen in one place.
            from server.chat_service import process_turn as _process_turn  # noqa: PLC0415
            turn = _process_turn(session_id=sid, message=request.message)
            response = _build_response(turn)
            yield f"data: {json.dumps({'type': 'done', **response.model_dump()})}\n\n"

        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
