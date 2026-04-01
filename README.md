# assistant-core-repo

A terminal-first private AI assistant with a web UI, LLM-backed planning,
long-term memory, multi-step agent execution, and full session persistence.

---

## What it does

- Answers questions directly when no tool is needed
- Reads, lists, writes, and edits files in a sandboxed workspace
- Searches the web (DuckDuckGo, no API key required)
- Fetches and extracts content from URLs
- Remembers facts about you across sessions (long-term memory)
- Chains tool calls autonomously for multi-step tasks
- Always asks for confirmation before writing or editing files
- Exposes a FastAPI server consumed by both a web UI and a terminal shell

---

## Requirements

- Python 3.11+
- `ANTHROPIC_API_KEY` for LLM-backed planning and memory extraction
  (falls back to keyword routing silently when not set)

---

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Run

**API server**

```bash
uvicorn server.app:app --reload
```

Server starts at `http://localhost:8000`. Interactive API docs at `/docs`.

**Web UI**

Open `web/index.html` directly in a browser. No build step required.

**Terminal shell**

```bash
python3 -m assistant_shell.chat_loop

# Resume a prior session
python3 -m assistant_shell.chat_loop --resume <session-id>
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(unset)* | Enables LLM planner and memory extraction. Falls back to heuristic router when unset. |
| `ASSISTANT_MODEL` | `claude-haiku-4-5-20251001` | Model used by the planner and memory extractor. |
| `PLANNER_MODE` | *(auto)* | Set to `heuristic` to force keyword routing regardless of API key. |
| `AGENT_MAX_STEPS` | `10` | Maximum tool calls the agent loop will chain per turn. |
| `ASSISTANT_API_KEY` | *(unset)* | Enables Bearer token auth on all API endpoints except `/health`. |
| `ALLOWED_ORIGIN` | `*` | CORS allowed origin. Set to your frontend URL in production. |

Copy `.env.example` to `.env` and fill in values to get started.

---

## Test

**Contract tests**

```bash
python3 -m pytest tests -q
```

**Conversation-layer evals** (deterministic, no API key required)

```bash
python3 -m evals.runner

# Run a single case by id prefix
python3 -m evals.runner confirm_write
```

Exit code `0` = all pass.

---

## Project structure

```
core/                   Contract layer — never import from server/ or above
  types.py              All dataclasses and type aliases
  policy.py             Tool allow / confirm / block rules
  router.py             Heuristic keyword router (fallback)
  planner.py            LLM-backed planner (uses router as fallback)
  agent.py              Multi-step agent loop
  tool_registry.py      Tool execution (read, write, edit, list, search, fetch)
  session_state.py      Session create / save / load
  tools/
    web_search.py       DuckDuckGo search — no API key required
    fetch_page.py       URL fetch and text extraction
  memory/
    store.py            SQLite-backed long-term fact store
    retriever.py        Keyword search over stored facts
    extractor.py        LLM extraction of facts from conversation turns

server/                 API layer
  app.py                FastAPI application, all routes
  chat_service.py       process_turn() — shared by API and terminal shell
  models.py             Pydantic request/response models

assistant_shell/        Terminal shell
  chat_loop.py          Input loop — delegates all logic to chat_service

evals/                  Conversation-layer evals
  cases.json            Test cases (route, tool, confirm, clarify, session flows)
  runner.py             Deterministic pass/fail runner

web/
  index.html            Single-file web UI — open directly in browser

workspace/              Sandboxed file area for read/write tool operations
.assistant_sessions/    Persisted session JSON files
.assistant_memory/      Long-term memory SQLite database
```

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/chat` | Send a message, get a response |
| `GET` | `/sessions` | List all sessions (newest first) |
| `GET` | `/sessions/{id}` | Full message history for a session |
| `GET` | `/memory` | All stored long-term facts |
| `DELETE` | `/memory/{id}` | Delete a single fact |

**POST /chat request**

```json
{ "session_id": "optional-uuid", "message": "your message" }
```

**POST /chat response**

```json
{
  "session_id": "uuid",
  "assistant_message": "...",
  "route_kind": "answer | clarify | confirm | tool",
  "policy_kind": "allow | require_confirmation | ...",
  "tool_result": { "ok": true, "tool_name": "...", "summary": "..." },
  "pending_clarification": null,
  "pending_confirmation": null,
  "planner_mode": "heuristic | model | model_fallback",
  "agent_steps": [{ "step": 1, "tool": "...", "label": "...", "ok": true, "summary": "..." }],
  "hit_step_limit": false
}
```

---

## Auth (production)

```bash
export ASSISTANT_API_KEY=your-secret-key
export ALLOWED_ORIGIN=https://your-frontend.com
uvicorn server.app:app
```

All endpoints except `/health` require:
```
Authorization: Bearer your-secret-key
```

Set `API_KEY` at the top of `web/index.html` to match.
