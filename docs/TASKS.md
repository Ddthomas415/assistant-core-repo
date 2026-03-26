# Builder Task List

## Purpose

This file is the actual next-work list for the builder.

It is not a packaging checklist and not a handoff checklist.
It answers one question:

What should be built next in this repo, in what order, and why?

Current assumed local state when this file was written:
- current local suite passes at `78 passed`
- recent hardening work exists locally and should be preserved intentionally
- clarification follow-through is implemented for the currently supported ambiguous read/write flows

## Working Rule

Do one slice at a time.

Each slice must:
- have a narrow objective
- have explicit tests
- preserve the engine contract in `docs/spec-v1.md`
- finish with a passing full suite

Do not mix multiple improvement themes into one slice.

## Priority 0: Preserve The Current Passing State

### Objective

Before starting new feature work, preserve the currently reviewed local state in git.

### Why

The repo has meaningful local changes:
- session load hardening
- cleaner CLI resume failure handling
- confirmation route alignment
- clarification follow-through
- updated tests
- updated README

Starting a new slice on top of an uncommitted state is how context gets lost.

### Done condition

- the current local reviewed diff is committed
- `pytest -q` passes
- `bash scripts/checkpoint_core_contract.sh` passes

## Priority 1: Bounded I/O Hardening

### Objective

Add explicit bounds to filesystem reads and workspace listing.

### Why

This is the most important remaining core hardening gap.

Current problems:
- `read_file_tool()` reads the full file into memory
- `list_workspace_tool()` walks and returns the full file list
- very large files or large workspaces can create memory pressure and poor UX

This is a better next slice than routing refactors because it improves safety without changing product scope.

### Scope

In `src/assistant/filesystem.py`:
- add max readable file size
- keep preview truncation explicit
- add max returned file count for workspace listing
- return structured metadata when output is truncated

### Tests to add

In `tests/test_filesystem.py` and/or `tests/test_filesystem_boundaries.py`:
- oversized file read returns structured failure or truncation behavior, depending on chosen contract
- workspace listing returns bounded results when file count exceeds limit
- truncation metadata is present and deterministic

### Done condition

- filesystem functions enforce explicit limits
- tests cover the chosen limit behavior
- full suite passes

## Priority 2: CI Contract Enforcement

### Objective

Make CI prove the engine contract, not just the test suite.

### Why

Current CI in `.github/workflows/tests.yml` runs only:
- package install
- `pytest`

But the repo already has a contract guard:
- `scripts/checkpoint_core_contract.sh`

If that script is not in CI, contract drift can still land.

### Scope

Update `.github/workflows/tests.yml` to also run:

```bash
bash scripts/checkpoint_core_contract.sh
```

### Done condition

- CI runs pytest
- CI runs checkpoint script
- workflow remains green

## Priority 3: Real-Use Failure Collection

### Objective

Use the tool for actual tasks and update `docs/real_use_failures.md` with new evidence.

### Why

The next architecture decision should come from real usage, not speculation.

The current engine is still heuristic and phrase-based. That may or may not be a real problem for the actual workflow. The failure log should decide that.

### Scope

Run real tasks through the assistant and record:
- exact input
- actual output
- expected behavior
- category
- impact

Examples of useful categories:
- routing-miss
- unclear-clarification
- confirmation-friction
- missing-tool
- output-confusing

### Done condition

- `docs/real_use_failures.md` contains fresh real-use evidence
- repeated failures are grouped
- next work can be chosen from evidence instead of guesswork

## Priority 4: Routing Expansion Only If Evidence Demands It

### Objective

Improve routing only after the real-use log shows meaningful misses.

### Why

The repo should not jump straight into a routing refactor or LLM integration without evidence.

Possible outcomes from the failure log:
- mostly phrase misses: expand deterministic routing patterns
- mostly missing tools: add the missing tools instead
- mostly true intent ambiguity: then consider a larger routing redesign

### Scope

Keep this slice small if it becomes necessary:
- add support for the most common real failed phrasings
- add tests for each new supported phrase
- do not redesign the engine in the same slice

### Done condition

- the highest-frequency real routing misses are covered by tests
- full suite passes

## Priority 5: Session Schema Hardening

### Objective

Continue hardening the session layer only if new failure cases justify it.

### Why

Session validation is already stronger than before. More work here should be driven by actual new state-shape risks, not by abstract neatness.

### Good candidates

- tighter validation if new persisted fields are introduced
- explicit migration handling if schema version changes
- additional corruption tests for newly supported state shapes

### Done condition

- changes are tied to a concrete new requirement
- tests prove the new validation behavior

## Not Next

Do not do these next:
- no web UI
- no long-term memory system
- no autonomous agents
- no major `handle_turn()` rewrite for elegance only
- no large routing architecture redesign without fresh evidence
- no product pivot inside this repo

## Definition Of A Good Slice

A good next slice in this repo looks like this:
- one clear objective
- one subsystem touched
- tests added first or alongside code
- no speculative architecture
- full suite green at the end

## Recommended Immediate Next Slice

If starting coding right now, do this next:

### Slice

Bounded I/O hardening in `src/assistant/filesystem.py`

### Files likely touched

- `src/assistant/filesystem.py`
- `tests/test_filesystem.py`
- `tests/test_filesystem_boundaries.py`
- maybe `README.md` if user-facing tool behavior changes materially

### Minimum expected output

- explicit read-size limit
- explicit workspace-list limit
- deterministic structured behavior under truncation/limit conditions
- full suite passing
