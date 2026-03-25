from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from assistant.engine import Engine
from assistant.models import (
    ClarificationTarget,
    PendingConfirmation,
    RequestedAction,
    RouteKind,
    SessionMetadata,
    SessionState,
    ToolRequest,
    ToolResult,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def expired_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()


def make_state() -> SessionState:
    now = now_iso()
    return SessionState(
        session_id=str(uuid4()),
        metadata=SessionMetadata(created_at=now, updated_at=now),
    )


def fake_read_tool(request: ToolRequest) -> ToolResult:
    return ToolResult(
        ok=True,
        tool_name=request.tool_name,
        execution_id=str(uuid4()),
        summary=f"Read {request.arguments['path']}",
        data={"path": request.arguments["path"]},
        started_at=now_iso(),
        finished_at=now_iso(),
    )


def fake_write_tool(request: ToolRequest) -> ToolResult:
    return ToolResult(
        ok=True,
        tool_name=request.tool_name,
        execution_id=str(uuid4()),
        summary=f"Wrote {request.arguments['path']}",
        data={"path": request.arguments["path"]},
        started_at=now_iso(),
        finished_at=now_iso(),
    )


def test_direct_answer_produces_answer_route_and_no_pending_state() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "What does this assistant do?")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert result.policy_outcome.kind.value == "allow"
    assert state.pending_clarification is None
    assert state.pending_confirmation is None
    assert "terminal-first private assistant" in result.rendered_output.lower()


def test_ambiguous_request_creates_pending_clarification() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "Open the config file.")

    assert result.route_decision.kind == RouteKind.CLARIFY
    assert result.policy_outcome.kind.value == "require_clarification"
    assert state.pending_clarification is not None
    assert state.pending_clarification.target == ClarificationTarget.FILE_PATH
    assert state.pending_confirmation is None


def test_modifying_request_creates_pending_confirmation() -> None:
    engine = Engine(write_tool=fake_write_tool)
    state = make_state()

    result = engine.handle_turn(state, "Overwrite config.yaml with defaults.")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.policy_outcome.kind.value == "require_confirmation"
    assert state.pending_confirmation is not None
    assert state.pending_confirmation.requested_action.tool_name == "write_file"
    assert state.pending_clarification is None


def test_valid_yes_resolves_matching_pending_confirmation_only() -> None:
    engine = Engine(write_tool=fake_write_tool)
    state = make_state()

    engine.handle_turn(state, "Overwrite config.yaml with defaults.")
    pending_id = state.pending_confirmation.action_id
    result = engine.handle_turn(state, "yes")

    assert result.route_decision.kind == RouteKind.CONFIRM
    assert result.policy_outcome.kind.value == "allow"
    assert result.tool_result is not None
    assert result.tool_result.tool_name == "write_file"
    assert state.pending_confirmation is None
    assert state.last_tool_execution is not None
    assert pending_id != ""


def test_stale_confirmation_does_not_execute() -> None:
    engine = Engine(write_tool=fake_write_tool)
    state = make_state()

    requested_action = RequestedAction(
        action_id=str(uuid4()),
        tool_name="write_file",
        arguments={"path": "config.yaml", "content": "defaults"},
        reason="test",
    )
    state.pending_confirmation = PendingConfirmation(
        confirmation_id=str(uuid4()),
        action_id=requested_action.action_id,
        created_at=now_iso(),
        expires_at=expired_iso(),
        prompt="Please confirm.",
        requested_action=requested_action,
    )

    result = engine.handle_turn(state, "confirm")

    assert result.route_decision.kind == RouteKind.CONFIRM
    assert result.policy_outcome.kind.value == "block"
    assert result.tool_result is None
    assert state.pending_confirmation is None
    assert "no valid pending confirmation" in result.rendered_output.lower()


def test_unrelated_input_clears_pending_confirmation() -> None:
    engine = Engine(write_tool=fake_write_tool)
    state = make_state()

    engine.handle_turn(state, "Overwrite config.yaml with defaults.")
    assert state.pending_confirmation is not None

    result = engine.handle_turn(state, "What does this assistant do?")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert state.pending_confirmation is None
    assert "terminal-first private assistant" in result.rendered_output.lower()


def test_resolved_clarification_clears_pending_state() -> None:
    engine = Engine()
    state = make_state()

    engine.handle_turn(state, "Open the config file.")
    assert state.pending_clarification is not None

    result = engine.handle_turn(state, "project-config.yaml")

    assert result.route_decision.kind == RouteKind.CLARIFY
    assert result.policy_outcome.kind.value == "allow"
    assert state.pending_clarification is None
    assert "project-config.yaml" in result.rendered_output


def test_read_tool_path_is_allowed_and_records_last_execution() -> None:
    engine = Engine(read_tool=fake_read_tool)
    state = make_state()

    result = engine.handle_turn(state, "Read pyproject.toml")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.policy_outcome.kind.value == "allow"
    assert result.tool_result is not None
    assert result.tool_result.tool_name == "read_file"
    assert state.last_tool_execution is not None
    assert "read pyproject.toml" in result.rendered_output.lower()


def test_read_tool_uses_real_filesystem_tool_when_no_injected_handler(tmp_path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("alpha beta", encoding="utf-8")

    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, f"Read {file_path}")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.policy_outcome.kind.value == "allow"
    assert result.tool_result is not None
    assert result.tool_result.ok is True
    assert result.tool_result.tool_name == "read_file"
    assert result.tool_result.data["content"] == "alpha beta"
    assert state.last_tool_execution is not None


def test_read_tool_missing_file_returns_structured_failure_when_no_injected_handler(tmp_path) -> None:
    file_path = tmp_path / "missing.txt"

    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, f"Read {file_path}")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is False
    assert result.tool_result.error_code == "file_not_found"
    assert state.last_tool_execution is not None
    assert state.last_tool_execution.ok is False


def test_confirmed_write_uses_real_filesystem_tool_when_no_injected_handler(tmp_path) -> None:
    file_path = tmp_path / "config.yaml"

    engine = Engine()
    state = make_state()

    result1 = engine.handle_turn(state, f"Overwrite {file_path} with defaults.")
    assert result1.policy_outcome.kind.value == "require_confirmation"
    assert state.pending_confirmation is not None

    result2 = engine.handle_turn(state, "yes")

    assert result2.route_decision.kind == RouteKind.CONFIRM
    assert result2.policy_outcome.kind.value == "allow"
    assert result2.tool_result is not None
    assert result2.tool_result.ok is True
    assert file_path.read_text(encoding="utf-8") == "defaults."
    assert state.pending_confirmation is None
    assert state.last_tool_execution is not None
    assert state.last_tool_execution.tool_name == "write_file"


def test_malformed_overwrite_request_requires_clarification() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "Overwrite  with defaults.")

    assert result.route_decision.kind == RouteKind.CLARIFY
    assert result.policy_outcome.kind.value == "require_clarification"
    assert state.pending_clarification is not None
    assert state.pending_confirmation is None
    assert "which file" in result.rendered_output.lower()


def test_engine_read_blocks_path_outside_workspace(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, f"Read {outside}")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is False
    assert result.tool_result.error_code == "path_outside_workspace"


def test_engine_confirmed_write_blocks_path_outside_workspace(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outside = tmp_path / "outside.txt"

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result1 = engine.handle_turn(state, f"Overwrite {outside} with secret")
    assert result1.policy_outcome.kind.value == "require_confirmation"

    result2 = engine.handle_turn(state, "yes")

    assert result2.route_decision.kind == RouteKind.CONFIRM
    assert result2.tool_result is not None
    assert result2.tool_result.ok is False
    assert result2.tool_result.error_code == "path_outside_workspace"


# --- Tests proving the two engine.py correctness fixes ---


def test_overwrite_parser_preserves_path_case(tmp_path) -> None:
    """The overwrite body must be sliced from cleaned_input, not from normalized.
    Slicing normalized would lowercase the file path and content, silently
    writing to the wrong path on case-sensitive filesystems."""
    # Use a path with mixed case to make case-preservation observable
    mixed_case_dir = tmp_path / "MyProject"
    mixed_case_dir.mkdir()
    file_path = mixed_case_dir / "Config.YAML"

    engine = Engine(write_tool=fake_write_tool)
    state = make_state()

    engine.handle_turn(state, f"overwrite {file_path} with updated")

    assert state.pending_confirmation is not None
    parsed_path = state.pending_confirmation.requested_action.arguments["path"]
    # Must preserve original case — NOT be lowercased
    assert parsed_path == str(file_path), (
        f"Path case not preserved. Expected {str(file_path)!r}, got {parsed_path!r}"
    )


def test_overwrite_parser_preserves_content_case(tmp_path) -> None:
    """Content after 'with' must preserve original case — not be lowercased."""
    file_path = tmp_path / "notes.txt"

    engine = Engine(write_tool=fake_write_tool)
    state = make_state()

    engine.handle_turn(state, f"overwrite {file_path} with Hello World")

    assert state.pending_confirmation is not None
    parsed_content = state.pending_confirmation.requested_action.arguments["content"]
    # Content must preserve original casing from cleaned_input, not be lowercased
    assert parsed_content == "Hello World", (
        f"Content case not preserved. Expected 'Hello World', got {parsed_content!r}"
    )


def test_overwrite_uppercase_trigger_parses_body_correctly(tmp_path) -> None:
    """Uppercase OVERWRITE trigger must route to confirmation and parse
    path and content correctly — not produce garbled output."""
    file_path = tmp_path / "output.txt"

    engine = Engine()
    state = make_state()

    engine.handle_turn(state, f"OVERWRITE {file_path} with correct content")

    assert state.pending_confirmation is not None, (
        "OVERWRITE (uppercase) should create pending confirmation"
    )
    args = state.pending_confirmation.requested_action.arguments
    assert args["path"] == str(file_path), (
        f"Path mismatch. Expected {str(file_path)!r}, got {args['path']!r}"
    )
    assert args["content"] == "correct content", (
        f"Content mismatch. Expected 'correct content', got {args['content']!r}"
    )


def test_overwrite_end_to_end_writes_correct_content(tmp_path) -> None:
    """Full round-trip: parse body, confirm, execute, verify file on disk."""
    file_path = tmp_path / "result.txt"

    engine = Engine()
    state = make_state()

    engine.handle_turn(state, f"overwrite {file_path} with exact content")
    assert state.pending_confirmation is not None

    result2 = engine.handle_turn(state, "yes")
    assert result2.route_decision.kind == RouteKind.CONFIRM
    assert result2.policy_outcome.kind.value == "allow"
    assert result2.tool_result is not None
    assert result2.tool_result.ok is True

    on_disk = file_path.read_text(encoding="utf-8")
    assert on_disk == "exact content", (
        f"File content mismatch. Expected 'exact content', got {on_disk!r}"
    )


def test_engine_routes_workspace_listing_phrase() -> None:
    engine = Engine()
    state = make_state()
    result = engine.handle_turn(state, "what files are in my workspace")
    assert result.route_decision.kind == RouteKind.TOOL
    assert result.route_decision.tool_request is not None
    assert result.route_decision.tool_request.tool_name == "list_workspace"
