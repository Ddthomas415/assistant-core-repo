# Real-Use Failure Log

## Session 1 — [date]
Tasks intended: [list what you planned to do]

| # | input (exact) | actual output (brief) | expected | category | impact |
|---|---|---|---|---|---|
| 1 | "what is todays date ?" | "I understood your request, but this minimal engine only supports the core trusted-turn flows." | answer current date | routing-miss | medium |
| 2 | "what is the core truste ?" | "I understood your request, but this minimal engine only supports the core trusted-turn flows." | explain the assistant core / trust model | output-confusing | low |
| 3 | "what files are in my workspace" | "[paste first line of actual output]" | list workspace files | [category] | [impact] |
| 4 | "show me the contents of notes.txt" | "[paste first line of actual output]" | read notes.txt | [category] | [impact] |
| 5 | "can you list everything in the workspace folder" | "[paste first line of actual output]" | list workspace files | [category] | [impact] |
| 6 | "open the config file" | "[paste first line of actual output]" | ask which config file | [category] | [impact] |
| 7 | "make a file called test.py that prints hello" | "[paste first line of actual output]" | write_file action | [category] | [impact] |

## Result
Completed one real-use session.
Record all failed or confusing interactions above.
