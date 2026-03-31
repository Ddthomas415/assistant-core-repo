from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from assistant.engine import Engine
from assistant.models import (
    ClarificationTarget,
    PendingClarification,
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


def fake_list_tool(request: ToolRequest) -> ToolResult:
    return ToolResult(
        ok=True,
        tool_name=request.tool_name,
        execution_id=str(uuid4()),
        summary="Workspace: injected\nsample.txt",
        data={"workspace_root": request.arguments.get("workspace_root"), "files": ["sample.txt"], "truncated": False},
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

    assert result.route_decision.kind == RouteKind.CONFIRM
    assert result.policy_outcome.kind.value == "require_confirmation"
    assert result.route_decision.requested_action is not None
    assert result.route_decision.requested_action.tool_name == "write_file"
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

    assert result.route_decision.kind == RouteKind.ANSWER
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


def test_resolved_clarification_resumes_read_request() -> None:
    engine = Engine(read_tool=fake_read_tool)
    state = make_state()

    engine.handle_turn(state, "Open the config file.")
    assert state.pending_clarification is not None

    result = engine.handle_turn(state, "project-config.yaml")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.policy_outcome.kind.value == "allow"
    assert result.tool_result is not None
    assert result.tool_result.tool_name == "read_file"
    assert result.tool_result.data["path"] == "project-config.yaml"
    assert state.pending_clarification is None
    assert state.last_tool_execution is not None


def test_resolved_clarification_for_overwrite_creates_pending_confirmation() -> None:
    engine = Engine()
    state = make_state()

    engine.handle_turn(state, "Overwrite  with defaults.")
    assert state.pending_clarification is not None

    result = engine.handle_turn(state, "config.yaml")

    assert result.route_decision.kind == RouteKind.CONFIRM
    assert result.policy_outcome.kind.value == "require_confirmation"
    assert result.route_decision.requested_action is not None
    assert result.route_decision.requested_action.arguments["path"] == "config.yaml"
    assert result.route_decision.requested_action.arguments["content"] == "defaults."
    assert state.pending_clarification is None
    assert state.pending_confirmation is not None
    assert state.pending_confirmation.requested_action.arguments["path"] == "config.yaml"


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


def test_engine_show_me_contents_blocks_path_outside_workspace(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, f"show me the contents of {outside}")

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

def test_engine_list_workspace_uses_injected_handler() -> None:
    engine = Engine(list_tool=fake_list_tool, workspace_root="workspace")
    state = make_state()

    result = engine.handle_turn(state, "what files are in my workspace")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.tool_name == "list_workspace"
    assert result.tool_result.data["files"] == ["sample.txt"]

def test_engine_routes_show_me_contents_phrase() -> None:
    engine = Engine()
    state = make_state()
    result = engine.handle_turn(state, "show me the contents of notes.txt")
    assert result.route_decision.kind == RouteKind.TOOL
    assert result.route_decision.tool_request is not None
    assert result.route_decision.tool_request.tool_name == "read_file"

def test_engine_routes_make_file_phrase() -> None:
    engine = Engine()
    state = make_state()
    result = engine.handle_turn(state, "make a file called test.py that prints hello")
    assert result.route_decision.kind == RouteKind.CONFIRM
    assert result.route_decision.requested_action is not None
    assert result.route_decision.requested_action.tool_name == "write_file"

def test_make_file_called_flow_writes_after_confirmation(tmp_path) -> None:
    engine = Engine(workspace_root=str(tmp_path))
    state = make_state()

    result1 = engine.handle_turn(state, "make a file called test.py that prints hello")
    assert result1.route_decision.kind == RouteKind.CONFIRM
    assert state.pending_confirmation is not None

    result2 = engine.handle_turn(state, "yes")

    assert result2.route_decision.kind == RouteKind.CONFIRM
    assert result2.policy_outcome.kind.value == "allow"
    assert result2.tool_result is not None
    assert result2.tool_result.ok is True
    assert (tmp_path / "test.py").read_text(encoding="utf-8") == "hello"

def test_clarification_reply_resumes_original_read_request() -> None:
    engine = Engine()
    state = make_state()

    result1 = engine.handle_turn(state, "open the config file")
    assert result1.route_decision.kind == RouteKind.CLARIFY
    assert state.pending_clarification is not None

    result2 = engine.handle_turn(state, "config.yaml")

    assert result2.route_decision.kind == RouteKind.TOOL
    assert result2.route_decision.tool_request is not None
    assert result2.route_decision.tool_request.tool_name == "read_file"

def test_clarification_reply_resumes_original_write_request_into_confirmation() -> None:
    engine = Engine()
    state = make_state()

    result1 = engine.handle_turn(state, "write the spec file")
    assert result1.route_decision.kind == RouteKind.CLARIFY
    assert state.pending_clarification is not None

    result2 = engine.handle_turn(state, "spec.md")

    assert result2.route_decision.kind == RouteKind.CONFIRM
    assert result2.route_decision.requested_action is not None
    assert result2.route_decision.requested_action.tool_name == "write_file"
    assert state.pending_confirmation is not None

def test_write_spec_file_flow_executes_after_confirmation(tmp_path) -> None:
    engine = Engine(workspace_root=str(tmp_path))
    state = make_state()

    result1 = engine.handle_turn(state, "write the spec file")
    assert result1.route_decision.kind == RouteKind.CLARIFY

    result2 = engine.handle_turn(state, "spec.md")
    assert result2.route_decision.kind == RouteKind.CONFIRM
    assert state.pending_confirmation is not None

    result3 = engine.handle_turn(state, "yes")

    assert result3.route_decision.kind == RouteKind.CONFIRM
    assert result3.policy_outcome.kind.value == "allow"
    assert result3.tool_result is not None
    assert result3.tool_result.ok is True
    assert (tmp_path / "spec.md").read_text(encoding="utf-8") == "updated content"

def test_clarified_read_uses_workspace_root_for_relative_path(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "config.yaml"
    target.write_text("name: demo", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result1 = engine.handle_turn(state, "open the config file")
    assert result1.route_decision.kind == RouteKind.CLARIFY
    assert state.pending_clarification is not None

    result2 = engine.handle_turn(state, "config.yaml")

    assert result2.route_decision.kind == RouteKind.TOOL
    assert result2.tool_result is not None
    assert result2.tool_result.ok is True
    assert result2.tool_result.data["path"] == str(target.resolve())

def test_clarified_write_preserves_filename_without_with_suffix() -> None:
    engine = Engine()
    state = make_state()

    result1 = engine.handle_turn(state, "write the spec file")
    assert result1.route_decision.kind == RouteKind.CLARIFY
    assert state.pending_clarification is not None

    result2 = engine.handle_turn(state, "spec.md")

    assert result2.route_decision.kind == RouteKind.CONFIRM
    assert state.pending_confirmation is not None
    assert state.pending_confirmation.requested_action.arguments["path"] == "spec.md"
    assert state.pending_confirmation.prompt == "Please confirm overwriting spec.md."

def test_repeated_open_config_file_still_clarifies_after_prior_sequence() -> None:
    engine = Engine(workspace_root="workspace")
    state = make_state()

    result1 = engine.handle_turn(state, "open the config file")
    assert result1.route_decision.kind == RouteKind.CLARIFY

    result2 = engine.handle_turn(state, "config.yaml")
    assert result2.route_decision.kind == RouteKind.TOOL

    result3 = engine.handle_turn(state, "write the spec file")
    assert result3.route_decision.kind == RouteKind.CLARIFY

    result4 = engine.handle_turn(state, "spec.md")
    assert result4.route_decision.kind == RouteKind.CONFIRM

    result5 = engine.handle_turn(state, "yes")
    assert result5.route_decision.kind == RouteKind.CONFIRM

    result6 = engine.handle_turn(state, "open the config file")
    assert result6.route_decision.kind == RouteKind.CLARIFY

def test_unmatched_reconstructed_clarification_acknowledges_without_follow_up_action() -> None:
    engine = Engine()
    state = make_state()

    state.pending_clarification = PendingClarification(
        clarification_id=str(uuid4()),
        created_at=now_iso(),
        expires_at=None,
        prompt="Which file should I use?",
        target=ClarificationTarget.FILE_PATH,
        bound_user_request="Use a file for the report.",
        allowed_reply_kinds=["file_path"],
    )

    result = engine.handle_turn(state, "report.txt")

    assert result.route_decision.kind == RouteKind.CLARIFY
    assert result.policy_outcome.kind.value == "allow"
    assert "i’ll use 'report.txt' as the file path." in result.rendered_output.lower()
    assert state.pending_clarification is None

def test_engine_answers_capability_question_directly() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "what can you do?")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert "read" in result.rendered_output.lower()
    assert "write" in result.rendered_output.lower()
    assert "clarif" in result.rendered_output.lower() or "confirm" in result.rendered_output.lower()


def test_engine_handles_general_out_of_scope_question_cleanly() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "whats todays date?")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert "out of scope" in result.rendered_output.lower() or "i can help" in result.rendered_output.lower()
    assert "trusted-turn flows" not in result.rendered_output.lower()

def test_engine_answers_help_with_reading_cleanly() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "help with reading")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "read" in text
    assert "file" in text or "workspace" in text
    assert "outside my current scope" not in text


def test_engine_answers_files_question_with_workspace_guidance() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "files?")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "workspace" in text or "list" in text
    assert "outside my current scope" not in text

def test_engine_answers_writing_question_with_write_guidance() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "writing?")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "write" in text or "writing" in text
    assert "confirm" in text
    assert "outside my current scope" not in text

def test_engine_answers_help_variant_with_capability_guidance() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "help?")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "read" in text or "write" in text or "workspace" in text
    assert "outside my current scope" not in text


def test_engine_answers_list_files_variant_with_workspace_guidance() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "list files?")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "workspace" in text or "list" in text
    assert "outside my current scope" not in text

def test_engine_answers_help_me_with_local_files_cleanly() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "help me with local files")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "read" in text or "write" in text or "workspace" in text
    assert "outside my current scope" not in text


def test_engine_answers_list_files_variant_with_workspace_guidance() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "list files")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "workspace" in text or "list" in text
    assert "outside my current scope" not in text


def test_engine_clarifies_bare_read_file_prompt() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "read file")

    assert result.route_decision.kind == RouteKind.CLARIFY

def test_bare_read_file_clarification_reply_continues_into_read() -> None:
    workspace = "workspace"
    engine = Engine(workspace_root=workspace)
    state = make_state()

    result1 = engine.handle_turn(state, "read file")
    assert result1.route_decision.kind == RouteKind.CLARIFY
    assert state.pending_clarification is not None

    result2 = engine.handle_turn(state, "notes.txt")

    assert result2.route_decision.kind == RouteKind.TOOL
    assert result2.route_decision.tool_request is not None
    assert result2.route_decision.tool_request.tool_name == "read_file"

def test_engine_routes_workspace_listing_question_variant() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "what files are in my workspace?")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.route_decision.tool_request is not None
    assert result.route_decision.tool_request.tool_name == "list_workspace"

def test_engine_answers_list_folders_variant_with_workspace_guidance() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "list folders?")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "workspace" in text or "list" in text or "folder" in text
    assert "outside my current scope" not in text


def test_engine_answers_directory_variant_with_workspace_guidance() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "directory")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "workspace" in text or "list" in text or "folder" in text
    assert "outside my current scope" not in text

def test_engine_answers_workspace_tasks_question_with_capability_guidance() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "what workspace tasks can you perform?")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "workspace" in text or "read" in text or "write" in text or "list" in text
    assert "outside my current scope" not in text


def test_engine_answers_bare_write_file_prompt_with_write_guidance() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "write file")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "write" in text or "confirmation" in text or "confirm" in text
    assert "outside my current scope" not in text


def test_what_can_you_do_returns_capability_answer() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "What can you do?")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert "answer direct questions" in result.rendered_output.lower()


def test_show_files_returns_honest_direct_answer_until_list_tool_exists() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "show files")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert "workspace root is set" in result.rendered_output.lower()


def test_open_spec_maps_to_read_tool(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    docs = workspace / "docs"
    docs.mkdir()
    spec = docs / "spec-v1.md"
    spec.write_text("contract text", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "open spec")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is True
    assert result.tool_result.tool_name == "read_file"
    assert "contract text" in result.rendered_output.lower()


def test_read_config_requires_clarification() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "read config")

    assert result.route_decision.kind == RouteKind.CLARIFY
    assert result.policy_outcome.kind.value == "require_clarification"
    assert state.pending_clarification is not None


def test_engine_read_missing_file_inside_workspace_suggests_nearby_match(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.yaml").write_text("name: demo", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "Read confi.yaml")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is False
    assert result.tool_result.error_code == "file_not_found"
    assert "config.yaml" in result.rendered_output


def test_open_readme_maps_to_read_tool(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    readme = workspace / "README.md"
    readme.write_text("hello readme", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "open readme")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is True
    assert "hello readme" in result.rendered_output.lower()


def test_read_readme_missing_returns_structured_failure(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "read readme")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is False
    assert result.tool_result.error_code == "file_not_found"
    assert "readme.md" in result.rendered_output.lower()


def test_read_config_reads_single_obvious_config_file(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.yaml").write_text("name: demo", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "read config")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is True
    assert "name: demo" in result.rendered_output.lower()


def test_read_config_with_multiple_candidates_requires_clarification(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.yaml").write_text("a", encoding="utf-8")
    (workspace / "settings.toml").write_text("b", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "read config")

    assert result.route_decision.kind == RouteKind.CLARIFY
    assert result.policy_outcome.kind.value == "require_clarification"
    assert state.pending_clarification is not None
    assert "config.yaml" in result.rendered_output
    assert "settings.toml" in result.rendered_output


def test_read_config_with_no_candidates_keeps_safe_clarification(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("hello", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "read config")

    assert result.route_decision.kind == RouteKind.CLARIFY
    assert result.policy_outcome.kind.value == "require_clarification"
    assert state.pending_clarification is not None
    assert "which config file" in result.rendered_output.lower()


def test_read_config_followup_accepts_extension_reply(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.yaml").write_text("yaml: true", encoding="utf-8")
    (workspace / "settings.toml").write_text("toml = true", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    first = engine.handle_turn(state, "read config")
    assert first.route_decision.kind == RouteKind.CLARIFY

    second = engine.handle_turn(state, "yaml")

    assert second.route_decision.kind == RouteKind.TOOL
    assert second.tool_result is not None
    assert second.tool_result.ok is True
    assert "yaml: true" in second.rendered_output.lower()


def test_read_config_followup_accepts_numeric_choice(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.yaml").write_text("yaml: true", encoding="utf-8")
    (workspace / "settings.toml").write_text("toml = true", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    first = engine.handle_turn(state, "read config")
    assert first.route_decision.kind == RouteKind.CLARIFY

    second = engine.handle_turn(state, "2")

    assert second.route_decision.kind == RouteKind.TOOL
    assert second.tool_result is not None
    assert second.tool_result.ok is True
    assert "toml = true" in second.rendered_output.lower()


def test_read_config_followup_keeps_clarifying_on_invalid_short_reply(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.yaml").write_text("yaml: true", encoding="utf-8")
    (workspace / "settings.toml").write_text("toml = true", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    first = engine.handle_turn(state, "read config")
    assert first.route_decision.kind == RouteKind.CLARIFY

    second = engine.handle_turn(state, "banana")

    assert second.route_decision.kind == RouteKind.CLARIFY
    assert second.policy_outcome.kind.value == "require_clarification"
    assert state.pending_clarification is not None
    assert "config.yaml" in second.rendered_output
    assert "settings.toml" in second.rendered_output


def test_open_settings_reads_single_settings_file(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "settings.toml").write_text("debug = true", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "open settings")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is True
    assert "debug = true" in result.rendered_output.lower()


def test_read_settings_missing_returns_structured_failure(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "read settings")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is False
    assert result.tool_result.error_code == "file_not_found"
    assert "settings" in result.rendered_output.lower()


def test_show_files_with_workspace_root_routes_to_listing_tool(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.txt").write_text("a", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "show files")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is True
    assert "a.txt" in result.rendered_output


def test_list_files_with_workspace_root_routes_to_listing_tool(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.txt").write_text("a", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "list files")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is True
    assert "a.txt" in result.rendered_output




def test_show_me_contents_with_workspace_root_routes_to_listing_tool(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.txt").write_text("a", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "show me contents")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is True
    assert "a.txt" in result.rendered_output


def test_show_me_contents_without_workspace_root_returns_guidance() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "show me contents")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert "workspace root" in result.rendered_output.lower()


def test_open_settings_reads_existing_yaml_settings_file(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "settings.yaml").write_text("debug: true", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "open settings")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is True
    assert "debug: true" in result.rendered_output.lower()


def test_open_settings_prefers_existing_candidate_over_missing_default(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "settings.json").write_text('{"debug": true}', encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "open settings")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is True
    assert '"debug": true' in result.rendered_output.lower()


def test_multiline_input_returns_clear_single_command_message(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "open readme\nread config")

    assert result.route_decision.kind == RouteKind.ANSWER
    assert "one command at a time" in result.rendered_output.lower()


def test_out_of_scope_answer_includes_concrete_examples() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "plan my vacation")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "read readme.md" in text
    assert "show files" in text
    assert "open settings" in text


def test_multiline_guard_still_has_actionable_example() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "open readme\nread config")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "one command at a time" in text
    assert "show files" in text


def test_open_settings_without_settings_files_fails_cleanly(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text("[tool.demo]\n", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "open settings")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is False
    assert result.tool_result.error_code == "file_not_found"
    assert "settings.toml" in result.rendered_output.lower()
    assert "pyproject.toml" not in result.rendered_output.lower()


def test_what_files_can_you_read_returns_capability_guidance() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "what files can you read?")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "workspace" in text
    assert "read readme.md" in text
    assert "show files" in text


def test_settings_routes_like_open_settings(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "settings.yaml").write_text("debug: true", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "settings")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is True
    assert "debug: true" in result.rendered_output.lower()


def test_help_answer_mentions_concrete_commands() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "help")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "show files" in text
    assert "read readme.md" in text
    assert "open settings" in text
    assert "read config" in text


def test_open_settings_without_settings_files_fails_cleanly(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text("[tool.demo]\n", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "open settings")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is False
    assert result.tool_result.error_code == "file_not_found"
    assert "settings.toml" in result.rendered_output.lower()
    assert "pyproject.toml" not in result.rendered_output.lower()


def test_settings_without_settings_files_does_not_suggest_unrelated_files(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text("[tool.demo]\n", encoding="utf-8")

    engine = Engine(workspace_root=str(workspace))
    state = make_state()

    result = engine.handle_turn(state, "settings")

    assert result.route_decision.kind == RouteKind.TOOL
    assert result.tool_result is not None
    assert result.tool_result.ok is False
    assert result.tool_result.error_code == "file_not_found"
    assert "settings.toml" in result.rendered_output.lower()
    assert "pyproject.toml" not in result.rendered_output.lower()


def test_help_mentions_workspace_and_write_confirmation() -> None:
    engine = Engine()
    state = make_state()

    result = engine.handle_turn(state, "help")

    assert result.route_decision.kind == RouteKind.ANSWER
    text = result.rendered_output.lower()
    assert "show files" in text
    assert "read readme.md" in text
    assert "open settings" in text
    assert "read config" in text
    assert "confirmation" in text
