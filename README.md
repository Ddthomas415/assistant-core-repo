# assistant-core-repo

## Project Overview

This repo is a terminal-first private assistant core focused on trust-first behavior.

It is intentionally small and deterministic:
- a thin CLI accepts user input
- an engine handles routing and state transitions
- policy helpers enforce simple deterministic behavior
- filesystem helpers provide controlled read/write operations
- session persistence stores state as JSON

This is not a general assistant platform. It is a focused assistant core for controlled local workflows.

## Current Implemented Behavior

- direct answers when no tool is needed
- clarification for ambiguous requests
- clarification follow-through for the current supported ambiguous read/write flows
- confirmation before modifying actions
- filesystem read/write flows
- workspace boundary enforcement
- session persistence and resume
- thin CLI entrypoint
- regression test suite

Verified locally:
- `83 passed` via `pytest -q`

## What Is Not Implemented

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

    assistant-core \
      --session-dir .assistant_sessions \
      --workspace-root "$PWD/workspace"

Resume a prior session:

    assistant-core \
      --session-dir .assistant_sessions \
      --resume <session-id>

Session storage:
- sessions are stored in the directory passed to `--session-dir`
- each session is persisted as a JSON file
- `--resume` expects the printed session identifier, not a file path

## Test

Run the full test suite:

    python3 -m pytest tests -q

Run the checkpoint script:

    bash scripts/checkpoint_core_contract.sh

One-shot bootstrap:

    bash scripts/dev.sh

## Repo map

Small core modules only:
- `docs/spec-v1.md` - frozen assistant core contract
- `docs/real_use_failures.md` - real-use evidence log
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

## Known Issues / TODOs

- routing remains heuristic and phrase-based
- large file reads should be bounded
- large workspace listings should be bounded
- session/schema hardening can continue if new formats are introduced
- CI currently runs `pytest` but does not yet run `bash scripts/checkpoint_core_contract.sh`
- local reviewed changes are present and should be committed explicitly before final archival or handoff packaging

## Handoff Note

Recommended recovery order:
1. read `README.md`
2. read `docs/spec-v1.md`
3. read `docs/real_use_failures.md`
4. run tests
5. inspect `git status` and recent commits
6. review any local diffs before packaging or handoff

## Platform note

`scripts/dev.sh` is intended for macOS/Linux POSIX shells.
