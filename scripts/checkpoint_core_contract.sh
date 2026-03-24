#!/usr/bin/env bash
set -euo pipefail

echo "== Core contract checkpoint verification =="

required_files=(
  "docs/spec-v1.md"
  "src/assistant/models.py"
  "src/assistant/session.py"
)

for f in "${required_files[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing required file: $f" >&2
    exit 1
  fi
done

python3 -m py_compile src/assistant/models.py src/assistant/session.py

python3 - <<'PY'
from pathlib import Path

spec = Path("docs/spec-v1.md").read_text()
models = Path("src/assistant/models.py").read_text()
session = Path("src/assistant/session.py").read_text()

required_spec_terms = [
    "handle_turn(state, user_input) -> EngineResult",
    "RouteDecision",
    "PolicyOutcome",
    "pending clarification",
    "pending confirmation",
    "ToolRequest",
    "ToolResult",
    "schema version",
    "Audit trace minimum",
    "Invariants",
]

required_model_terms = [
    "class RouteKind",
    "class PolicyOutcomeKind",
    "class PendingClarification",
    "class PendingConfirmation",
    "class EngineResult",
    "class SessionState",
    "SCHEMA_VERSION = 1",
]

required_session_terms = [
    "class SessionNotFoundError",
    "class SessionCorruptError",
    "schema_version",
    "pending_clarification",
    "pending_confirmation",
    "last_tool_execution",
]

for term in required_spec_terms:
    if term not in spec:
        raise SystemExit(f"spec-v1.md missing term: {term}")

for term in required_model_terms:
    if term not in models:
        raise SystemExit(f"models.py missing term: {term}")

for term in required_session_terms:
    if term not in session:
        raise SystemExit(f"session.py missing term: {term}")

print("Checkpoint content verification: OK")
PY

echo "Python compile verification: OK"
echo "Checkpoint verification complete."
