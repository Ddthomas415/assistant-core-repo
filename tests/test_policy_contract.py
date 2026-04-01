from core.types import PolicyOutcome


def test_policy_allow_contract():
    result = PolicyOutcome(
        kind="allow",
        reason="safe informational action",
        blocking_code=None,
        advisory_notes=[],
    )
    assert result.kind == "allow"
    assert result.blocking_code is None


def test_policy_block_contract():
    result = PolicyOutcome(
        kind="block",
        reason="unknown tool",
        blocking_code="UNKNOWN_TOOL",
        advisory_notes=["Tool must be registered before execution."],
    )
    assert result.kind == "block"
    assert result.blocking_code == "UNKNOWN_TOOL"
    assert result.advisory_notes


def test_policy_confirmation_contract():
    result = PolicyOutcome(
        kind="require_confirmation",
        reason="write operations require approval",
        blocking_code=None,
        advisory_notes=["Await explicit user confirmation."],
    )
    assert result.kind == "require_confirmation"


def test_policy_clarification_contract():
    result = PolicyOutcome(
        kind="require_clarification",
        reason="filename missing",
        blocking_code=None,
        advisory_notes=["Need filename before proceeding."],
    )
    assert result.kind == "require_clarification"
