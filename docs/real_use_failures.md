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

## Session 6 — prompt variant validation

Tasks intended: probe nearby phrasing variants around help, capability, and listing prompts

| # | input (exact) | actual output (brief) | expected | category | impact |
|---|---|---|---|---|---|
| 1 | "what is your name ?" | "That request is outside my current scope..." | brief assistant identity or clear scope statement | output-confusing | low |
| 2 | "what is todays date ?" | "That request is outside my current scope..." | clear out-of-scope answer | output-confusing | low |
| 3 | "list file directory ?" | "That request is outside my current scope..." | workspace-list guidance | output-confusing | medium |
| 4 | "list files?" | "That request is outside my current scope..." | workspace-list guidance | output-confusing | medium |
| 5 | "can can you do ?" | "That request is outside my current scope..." | capability summary | output-confusing | low |
| 6 | "help?" | "That request is outside my current scope..." | capability/help summary | output-confusing | medium |

## Session 6 Conclusion

Pattern:
- exact supported prompts work
- nearby variants still fall back too often

Decision:
- next slice should improve small help/capability/listing phrasing variants only
- do not broaden architecture or routing beyond this UX cluster

## Session 7 — capability and command-phrase validation

Tasks intended: probe nearby natural-language variants around capability, help, and basic file commands

| # | input (exact) | actual output (brief) | expected | category | impact |
|---|---|---|---|---|---|
| 1 | "can you code?" | "That request is outside my current scope..." | clear scope/capability answer | output-confusing | low |
| 2 | "what is with in your current scope?" | "That request is outside my current scope..." | capability summary | output-confusing | medium |
| 3 | "help me with local files" | "That request is outside my current scope..." | local file help guidance | output-confusing | medium |
| 4 | "what workspace tasks can you perform?" | "That request is outside my current scope..." | workspace capability summary | output-confusing | medium |
| 5 | "read file" | "Read failed: file not found: .../workspace/file" | ask which file or give read guidance | unclear-clarification | medium |
| 6 | "write file" | "That request is outside my current scope..." | ask what filename/content or give write guidance | output-confusing | medium |
| 7 | "list files" | "That request is outside my current scope..." | workspace-list guidance | output-confusing | medium |
| 8 | "list all workspace file" | "That request is outside my current scope..." | workspace-list guidance | output-confusing | medium |
| 9 | "clarify your functions?" | "That request is outside my current scope..." | capability/help summary | output-confusing | low |

## Session 7 Conclusion

Pattern:
- exact supported prompts work
- nearby natural-language variants still fall back too often
- "read file" should likely clarify instead of treating "file" as a literal path

Decision:
- next slice should improve capability/help/listing phrasing and ambiguous bare command prompts
- do not broaden architecture or routing beyond this UX cluster

## Session 8 — workspace listing phrasing validation

Tasks intended: probe natural-language variants for workspace listing and task discovery

| # | input (exact) | actual output (brief) | expected | category | impact |
|---|---|---|---|---|---|
| 1 | "list capable workspace tasks" | "That request is outside my current scope..." | capability/help summary or workspace-task guidance | output-confusing | low |
| 2 | "what files are in my workspace?" | "That request is outside my current scope..." | actual workspace listing | routing-miss | high |
| 3 | "'can you list everything in the workspace folder?" | "That request is outside my current scope..." | actual workspace listing | routing-miss | high |
| 4 | "list folders?" | "That request is outside my current scope..." | workspace listing or folder guidance | routing-miss | medium |
| 5 | "task list?" | "That request is outside my current scope..." | clear out-of-scope answer | output-confusing | low |
| 6 | "list all tasks" | "That request is outside my current scope..." | clear out-of-scope answer | output-confusing | low |
| 7 | "directory" | "That request is outside my current scope..." | workspace listing guidance | output-confusing | medium |
| 8 | "folders" | "That request is outside my current scope..." | workspace listing guidance | output-confusing | medium |
| 9 | "list workspace files" | "That request is outside my current scope..." | actual workspace listing | routing-miss | high |

## Session 8 Conclusion

Pattern:
- workspace-listing behavior is still too phrase-sensitive
- exact help/capability prompts work
- next coding slice should improve real workspace-listing variants only

## Session 9 — workspace-task and bare-write validation

Tasks intended: probe remaining nearby variants after folder/directory guidance fixes

| # | input (exact) | actual output (brief) | expected | category | impact |
|---|---|---|---|---|---|
| 1 | "what workspace tasks can you perform?" | "That request is outside my current scope..." | workspace capability summary | output-confusing | medium |
| 2 | "help me with local files" | useful local file guidance | same | — (passed) | — |
| 3 | "list files" | useful workspace listing guidance | same | — (passed) | — |
| 4 | "read file" | "[CLARIFY] Which file do you want me to read?" | same | — (passed) | — |
| 5 | "notes.txt" | "Read failed: file not found: .../workspace/notes.txt" | missing-file failure is acceptable | — (passed) | — |
| 6 | "write file" | "That request is outside my current scope..." | write guidance or clarification | output-confusing | medium |

## Session 9 Conclusion

Pattern:
- recent help/list/read improvements are working
- remaining nearby variants still needing coverage are:
  - "what workspace tasks can you perform?"
  - "write file"
