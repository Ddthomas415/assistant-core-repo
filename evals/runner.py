#!/usr/bin/env python3
"""
Conversation-layer eval runner.

Usage:
    python3 -m evals.runner            # run all cases
    python3 -m evals.runner tool_read  # run one case by id prefix

Exit code: 0 = all pass, 1 = any failure.

Designed to run without ANTHROPIC_API_KEY (heuristic mode).
CI-safe: no network calls unless a test case specifically triggers
web_search or fetch_page (which will fail gracefully with ok=False).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

# Ensure repo root is on the path when run as a script.
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Force heuristic mode — evals must be deterministic.
os.environ["PLANNER_MODE"] = "heuristic"

from server.chat_service import process_turn, TurnOutput  # noqa: E402

CASES_PATH = Path(__file__).parent / "cases.json"

_GREEN = "\033[32m"
_RED   = "\033[31m"
_GREY  = "\033[90m"
_RESET = "\033[0m"
_BOLD  = "\033[1m"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    message: str
    turn: TurnOutput
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


@dataclass
class CaseResult:
    case_id: str
    description: str
    steps: list[StepResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(s.passed for s in self.steps)

    @property
    def failures(self) -> list[str]:
        out = []
        for i, s in enumerate(self.steps, 1):
            for f in s.failures:
                prefix = f"step {i}: " if len(self.steps) > 1 else ""
                out.append(f"{prefix}{f}")
        return out


# ---------------------------------------------------------------------------
# Assertion checker
# ---------------------------------------------------------------------------


def _check_step(turn: TurnOutput, expect: dict) -> list[str]:
    failures: list[str] = []

    if "route_kind" in expect:
        if turn.route_kind != expect["route_kind"]:
            failures.append(
                f"route_kind: expected '{expect['route_kind']}', got '{turn.route_kind}'"
            )

    if "tool_name" in expect:
        actual_tool = (
            turn.agent_steps[-1].tool_name if turn.agent_steps else None
        )
        if actual_tool != expect["tool_name"]:
            failures.append(
                f"tool_name: expected {expect['tool_name']!r}, got {actual_tool!r}"
            )

    if "agent_steps_count" in expect:
        count = len(turn.agent_steps)
        if count != expect["agent_steps_count"]:
            failures.append(
                f"agent_steps_count: expected {expect['agent_steps_count']}, got {count}"
            )

    if "tool_ok" in expect and turn.agent_steps:
        actual_ok = turn.agent_steps[-1].tool_result.ok
        if actual_ok != expect["tool_ok"]:
            failures.append(
                f"tool_ok: expected {expect['tool_ok']}, got {actual_ok}"
            )

    if "pending_clarification" in expect:
        has_cl = turn.pending_clarification is not None
        if has_cl != expect["pending_clarification"]:
            failures.append(
                f"pending_clarification: expected {expect['pending_clarification']}, got {has_cl}"
            )

    if "pending_confirmation" in expect:
        has_cn = turn.pending_confirmation is not None
        if has_cn != expect["pending_confirmation"]:
            failures.append(
                f"pending_confirmation: expected {expect['pending_confirmation']}, got {has_cn}"
            )

    return failures


# ---------------------------------------------------------------------------
# Case runner
# ---------------------------------------------------------------------------


def run_case(case: dict) -> CaseResult:
    result = CaseResult(case_id=case["id"], description=case["description"])

    # Single-turn case
    if "message" in case:
        turns = [{"message": case["message"], "expect": case.get("expect", {})}]
    else:
        turns = case.get("chain", [])

    session_id = str(uuid4())

    for turn_spec in turns:
        message = turn_spec["message"]
        expect  = turn_spec.get("expect", {})

        turn = process_turn(session_id=session_id, message=message)
        failures = _check_step(turn, expect)
        result.steps.append(StepResult(message=message, turn=turn, failures=failures))

        # Stop chain early on unexpected failure to avoid cascading errors.
        if failures and len(turns) > 1:
            break

    return result


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------


def _print_result(r: CaseResult) -> None:
    icon = f"{_GREEN}✓{_RESET}" if r.passed else f"{_RED}✗{_RESET}"
    print(f"  {icon}  {r.case_id:<40} {_GREY}{r.description}{_RESET}")
    for f in r.failures:
        print(f"       {_RED}↳ {f}{_RESET}")


def _print_summary(results: list[CaseResult]) -> None:
    passed = sum(1 for r in results if r.passed)
    total  = len(results)
    colour = _GREEN if passed == total else _RED
    print()
    print(f"{_BOLD}{colour}{passed}/{total} cases passed{_RESET}")
    if passed < total:
        failed_ids = [r.case_id for r in results if not r.passed]
        print(f"  failed: {', '.join(failed_ids)}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args    = argv if argv is not None else sys.argv[1:]
    filter_ = args[0].lower() if args else None

    all_cases: list[dict] = json.loads(CASES_PATH.read_text())

    if filter_:
        all_cases = [c for c in all_cases if filter_ in c["id"].lower()]
        if not all_cases:
            print(f"No cases matching '{filter_}'")
            return 1

    print(f"\n{_BOLD}Running {len(all_cases)} eval case(s){_RESET} "
          f"{_GREY}(heuristic mode — no API key required){_RESET}\n")

    results: list[CaseResult] = []
    for case in all_cases:
        r = run_case(case)
        results.append(r)
        _print_result(r)

    _print_summary(results)
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
