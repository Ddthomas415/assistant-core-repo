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
