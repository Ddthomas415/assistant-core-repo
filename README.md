# assistant-core-repo

## What this repo is

This repo is a terminal-first private assistant core focused on trust-first behavior.

Current scope only:
- direct answers when no tool is needed
- clarification for ambiguous requests
- confirmation before modifying actions
- controlled filesystem read/write flows
- workspace boundary enforcement
- session persistence and resume
- a thin CLI over the engine

It is not a general assistant platform. It is a small, tested assistant core.

## What is implemented now

- direct answers
- clarification flow
- confirmation before modifying actions
- controlled filesystem read/write flows
- workspace boundary enforcement
- session persistence and resume
- a thin CLI
- current test status: 56 passing tests

## What is not implemented

- no web UI
- no long-term memory
- no autonomous agents
- no generalized tool platform
- no claims beyond the current repo scope

## Setup

Supported Python:
- Python 3.11+
- currently tested locally with Python 3.12

Create and activate a virtual environment:

    python3 -m venv .venv
    source .venv/bin/activate

Upgrade pip and install dependencies:

    python3 -m pip install --upgrade pip
    python3 -m pip install -e . pytest

## Run

Basic CLI:

    assistant-core --session-dir .assistant_sessions

With workspace boundary enforcement:

    assistant-core       --session-dir .assistant_sessions       --workspace-root /absolute/path/to/workspace

Resume a prior session:

    assistant-core       --session-dir .assistant_sessions       --resume <session-id>

Session storage:
- sessions are stored in the directory passed to `--session-dir`
- each session is persisted as a JSON file
- `--resume` expects the printed session identifier, not a file path

## Test

Run the full test suite:

    python3 -m pytest tests

## Repo map

Small core modules only:
- `docs/spec-v1.md` - frozen assistant core contract
- `src/assistant/models.py` - typed state, decisions, results, trace objects
- `src/assistant/session.py` - versioned session persistence and corruption checks
- `src/assistant/policy.py` - deterministic safety and parsing helpers
- `src/assistant/filesystem.py` - real filesystem read/write helpers with workspace checks
- `src/assistant/engine.py` - core turn handling logic
- `src/assistant/cli.py` - thin terminal shell over the engine
- `tests/` - unit and smoke coverage for the current scope

## Development rule

The engine contract is primary.

New abstractions must be justified by:
- safety
- clarity
- testability

Do not add architecture layers unless the current behavior and tests prove they are needed.

## Platform note

`scripts/dev.sh` is intended for macOS/Linux POSIX shells.
