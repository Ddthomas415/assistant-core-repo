# Builder Task List

## Purpose

This file is the actual next-work list for the builder.

It is not a packaging checklist and not a handoff checklist.
It answers one question:

What should be built next in this repo, in what order, and why?

Current assumed local state when this file was written:
- current local suite passes via `pytest -q`
- exact branch, commit, and worktree state must be verified before starting a new slice
- clarification follow-through is implemented for the currently supported ambiguous read/write flows
- filesystem read/list guardrails are already implemented and covered by focused tests

## Working Rule

Do one slice at a time.

Each slice must:
- have a narrow objective
- have explicit tests
- preserve the engine contract in `docs/spec-v1.md`
- finish with a passing full suite

Do not mix multiple improvement themes into one slice.

## Priority 0: Verify And Normalize The Local Baseline

### Objective

Before starting new feature work, verify the local repo state and normalize it if needed.

### Why

Counts drift, worktree state drifts, and local artifacts accumulate.

Do not assume:
- the current test count
- the current branch
- the current commit
- whether the worktree is clean
- whether untracked root files are intentional

Starting work on top of an unreviewed local state is how context gets lost.

### Done condition

- `pytest -q` passes
- `bash scripts/checkpoint_core_contract.sh` passes
- `git status --short` is reviewed
- unintended untracked local artifacts are removed or intentionally preserved

## Priority 1: Preserve The Current Passing State If It Has Local Diffs

### Objective

If Task 0 reveals intentional local changes, preserve them in git before starting new feature work.

### Why

Reviewed local changes should not remain as anonymous working-tree state.

### Done condition

- intentional local changes are committed
- `pytest -q` passes
- `bash scripts/checkpoint_core_contract.sh` passes

## Priority 2: Real-Use Failure Collection

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

## Priority 3: Routing Expansion Only If Evidence Demands It

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

## Priority 4: Session Schema Hardening

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

Before changing any `RouteKind`, `PolicyOutcomeKind`, or similarly asserted enum value:
- grep the full `tests/` tree for affected assertions first
- update all matching assertions in the same slice
- do not call the change complete until the old assertion pattern is gone

## Recommended Immediate Next Step

If continuing from the current repo state, do this next:

### Step

Use the assistant for real tasks and update `docs/real_use_failures.md`.

### Why

The repo has already landed:
- clarification follow-through for the current supported ambiguous flows
- bounded filesystem read/list behavior
- CI enforcement of the checkpoint contract

The next useful decision should come from actual usage evidence, not another speculative hardening pass.

### Minimum expected output

- fresh real-use examples in `docs/real_use_failures.md`
- grouped failures by category and impact
- one evidence-backed recommendation for the next coding slice
