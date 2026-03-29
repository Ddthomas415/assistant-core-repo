# Real-Use Failure Log

## Purpose

This file tracks actual observed user-facing failures or friction.

Rules:
- keep only evidence that still matters to the current repo state
- mark historical issues as resolved once tests and code make them obsolete
- do not use this file for speculative architecture ideas

## Current Status — 2026-03-29

Current verified baseline:
- `python3 -m pytest -q` passes
- `bash scripts/checkpoint_core_contract.sh` passes

Current behavior already covered by code and tests:
- clarification follow-through works for the current supported ambiguous read/write flows
- bounded file reads reject oversized files and truncate preview text in summaries
- workspace listing is bounded and marks truncated output deterministically
- capability/help prompts such as `what can you do?`, `help with reading`, `files?`, and `writing?` are handled directly instead of falling back to the older generic out-of-scope wording

## Historical Issues Resolved

These issues were real in earlier sessions but should no longer drive current roadmap decisions:
- alternate read/list phrases that previously missed routing
- clarification flows that acknowledged the reply but did not continue the original action
- workspace-root handling regressions in supported read/write flows
- older generic fallback wording for handled capability/help prompts

## Current Open Evidence

No new manual real-workflow session was run in this remediation pass.

The remaining known product limitation from current repo evidence is:

| area | current state | impact | next action |
|---|---|---|---|
| routing | routing remains deterministic and phrase-based; nearby unhandled phrasings may still miss | medium | collect fresh real usage before changing routing |
| scope boundary | general assistant questions outside local file/workspace scope are answered with a scoped limitation message rather than a broad assistant answer | low | accepted unless product scope changes |
| session schema | current validation is stronger, but future persisted fields would need explicit schema handling | low | only revisit if the session format changes |

## Known v1 Limitations

These are accepted architectural constraints, not open bugs.

| area | behavior | impact | decision |
|---|---|---|---|
| `write_file_tool` | `path.write_text()` is not atomic, so a crash mid-write can corrupt the target file | low for single-user local use | accepted for v1; use tmp-then-replace only if stronger reliability is required |
| session persistence | session save happens after engine return, so a crash between response and save can lose the last persisted turn | low | accepted for v1; the user still saw the output even if persistence lags one turn |

## Next Real-Use Session Template

When running a real usage pass, append entries in this format:

| # | input (exact) | actual output (brief) | expected | category | impact |
|---|---|---|---|---|---|
| 1 | "..." | "..." | "..." | routing-miss / unclear-clarification / confirmation-friction / missing-tool / output-confusing | low / medium / high |

After the table, add:
- grouped repeated failures
- one evidence-backed recommendation for the next coding slice
