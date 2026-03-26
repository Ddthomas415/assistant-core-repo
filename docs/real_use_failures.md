# Real-Use Failure Log

## Session 1 — [date]
Tasks intended: [list what you planned to do]

| # | input (exact) | actual output (brief) | expected | category | impact |
|---|---|---|---|---|---|
| 1 | "what is todays date ?" | "I understood your request, but this minimal engine only supports the core trusted-turn flows." | answer current date | routing-miss | medium |
| 2 | "what is the core truste ?" | "I understood your request, but this minimal engine only supports the core trusted-turn flows." | explain the assistant core / trust model | output-confusing | low |
| 3 | "what files are in my workspace" | "I understood your request, but this minimal engine only supports the core trusted-turn flows." | list workspace files | routing-miss | high |
| 4 | "show me the contents of notes.txt" | "I understood your request, but this minimal engine only supports the core trusted-turn flows." | read notes.txt | routing-miss | high |
| 5 | "can you list everything in the workspace folder" | "I understood your request, but this minimal engine only supports the core trusted-turn flows." | list workspace files | routing-miss | high |
| 6 | "open the config file" | "Which config file do you want me to use?" | ask which config file | — (passed) | — |
| 7 | "make a file called test.py that prints hello" | "I understood your request, but this minimal engine only supports the core trusted-turn flows." | write_file action | routing-miss | high |

## Result
Completed one real-use session.
Record all failed or confusing interactions above.


### Post-session status
Resolved on `feature/tool-list-workspace`:
- #3 what files are in my workspace
- #4 show me the contents of notes.txt
- #5 can you list everything in the workspace folder
- #7 make a file called test.py that prints hello

Still review separately:
- #1 what is todays date ?
- #2 what is the core truste ?

## Step 4 Conclusion

High-impact failures from Session 1 are resolved on `feature/tool-list-workspace`:
- #3 what files are in my workspace
- #4 show me the contents of notes.txt
- #5 can you list everything in the workspace folder
- #7 make a file called test.py that prints hello

Remaining items:
- #1 "what is todays date ?" is outside the current repo scope and will not be added to the engine
- #2 "what is the core truste ?" is low-impact wording noise and not worth feature work

Decision:
- Heuristic routing is sufficient for the current workflow
- No LLM-router work is justified from this session

## Session 2 — 2026-03-26
Tasks intended: validate clarification follow-through and workspace-bound behavior after the latest main-branch changes

| # | input (exact) | actual output (brief) | expected | category | impact |
|---|---|---|---|---|---|
| 1 | "open the config file" → "config.yaml" | "Operation failed: path is outside workspace: /Users/baitus/assistant-core-repo/config.yaml" | clarified read should resolve inside configured workspace | routing-miss | high |
| 2 | "write the spec file" → "spec.md" → "yes" | "Please confirm overwriting spec.md with." then attempts to write path "spec.md with" outside workspace | clarified write should preserve filename and enter correct confirmation/write flow | wrong-confirmation | high |
| 3 | "show me the contents of notes.txt" | "Operation failed: path is outside workspace: /Users/baitus/assistant-core-repo/notes.txt" | read should resolve notes.txt relative to configured workspace | routing-miss | high |
| 4 | "make a file called test.py that prints hello" → "yes" | "Operation failed: path is outside workspace: /Users/baitus/assistant-core-repo/test.py" | write should resolve target inside configured workspace | routing-miss | high |
| 5 | "open the config file" (after failed sequence) | "I understood your request, but this minimal engine only supports the core trusted-turn flows." | should clarify consistently | routing-miss | medium |


## Session 2 — update after fix validation

Resolved:
- clarified write flow now preserves filename and writes inside workspace
- workspace listing works
- make-file flow works

Not a regression:
- reading config.yaml failed because the file does not exist in ./workspace
- reading notes.txt failed because the file does not exist in ./workspace

Still open:
- repeating "open the config file" after the prior sequence falls back to the default answer instead of clarifying again

## Session 3 — CLI visibility validation

Result:
- highlighted CLI output improves visibility for clarify/confirm/read/write/list states
- clarification flow worked
- workspace-root resolution worked
- write confirmation worked
- workspace listing worked
- reading config.yaml failed only because the file does not exist in ./workspace

Conclusion:
- CLI visibility change is successful
- no new routing or workspace-boundary regression observed in this session

## Session 4 — 2026-03-26
Tasks intended: probe general conversational behavior after bounded I/O hardening

| # | input (exact) | actual output (brief) | expected | category | impact |
|---|---|---|---|---|---|
| 1 | "whats todays date?" | "I understood your request, but this minimal engine only supports the core trusted-turn flows." | answer current date or clearly state out of scope | output-confusing | medium |
| 2 | "what is your name?" | "I understood your request, but this minimal engine only supports the core trusted-turn flows." | state assistant identity or clearly state out of scope | output-confusing | low |
| 3 | "what can you do?" | "I understood your request, but this minimal engine only supports the core trusted-turn flows." | brief capability summary | routing-miss | medium |
| 4 | "search for downloads path ?" | "I understood your request, but this minimal engine only supports the core trusted-turn flows." | clearly state unsupported or ask a narrower file/workspace question | output-confusing | low |


## Session 4 — capability/help phrasing validation

Tasks intended: probe natural-language variants around capabilities and local file help

| # | input (exact) | actual output (brief) | expected | category | impact |
|---|---|---|---|---|---|
| 1 | "can can you do?" | "That request is outside my current scope..." | brief capability summary | output-confusing | low |
| 2 | "can you code?" | "That request is outside my current scope..." | clearly state code help is out of scope or supported scope | output-confusing | low |
| 3 | "list local file directory?" | "That request is outside my current scope..." | clearly guide toward workspace listing phrasing | output-confusing | medium |
| 4 | "local file help?" | "That request is outside my current scope..." | brief capability/help summary | output-confusing | low |
| 5 | "help with reading" | "That request is outside my current scope..." | brief read-file capability guidance | output-confusing | medium |
| 6 | "files?" | "That request is outside my current scope..." | brief workspace/listing guidance | output-confusing | low |
| 7 | "writing?" | "That request is outside my current scope..." | brief write/confirmation guidance | output-confusing | low |

## Session 4 Conclusion

Pattern:
- exact handled prompts improved
- nearby natural-language variants still fall back to the generic out-of-scope response

Decision:
- next slice should improve capability/help phrasing only
- do not broaden architecture or routing beyond this small UX cluster
