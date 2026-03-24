# Assistant Core Contract v1

This document is the canonical engineering contract for the assistant core.

## 1. Core turn contract

### Function
`handle_turn(state, user_input) -> EngineResult`

### Inputs
`state: SessionState`
- full in-memory session state for the active session

`user_input: str`
- raw user text for the current turn
- may be empty or whitespace; this is handled as a normal input and must not create a special route kind

### Output
`EngineResult`
- `route_decision: RouteDecision`
- `policy_outcome: PolicyOutcome`
- `rendered_output: str`
- `tool_result: ToolResult | None`
- `trace: TurnTrace`

### In-memory mutation during a turn
The turn handler may mutate only:
- `state.messages`
- `state.summary`
- `state.pending_clarification`
- `state.pending_confirmation`
- `state.last_tool_execution`
- `state.metadata.updated_at`

### Persistence after each turn
After each completed turn, the persisted session must include:
- schema version
- session metadata
- messages
- summary
- pending clarification
- pending confirmation
- last tool execution metadata

## 2. Route decision contract

### Allowed kinds only
- `answer`
- `clarify`
- `confirm`
- `tool`

There is no `error` route.

### RouteDecision is pre-policy
RouteDecision may propose one of the four kinds only.
It must not encode policy enforcement.

### Required payload by kind

#### answer
- `kind = answer`
- `answer_text: str`

#### clarify
- `kind = clarify`
- `clarification_prompt: str`
- `clarification_target: ClarificationTarget`

#### confirm
- `kind = confirm`
- `confirmation_prompt: str`
- `requested_action: RequestedAction`

#### tool
- `kind = tool`
- `tool_request: ToolRequest`

### Precedence rules
When multiple interpretations are possible, choose in this order:
1. unresolved pending clarification that the user reply satisfies
2. unresolved pending confirmation that the user reply satisfies
3. clarification for ambiguous modifying request
4. confirmation for explicit modifying request
5. tool for explicit informational/tool-needed request
6. answer for direct-answer request

A lower-priority interpretation must not override a higher-priority valid pending-state resolution.

## 3. Policy outcome contract

### Allowed outcomes
- `allow`
- `block`
- `require_confirmation`
- `require_clarification`

### PolicyOutcome rules
- PolicyOutcome is the only execution gate.
- RouteDecision cannot directly execute tools.
- Unknown tools are blocked unless explicitly allowed by policy.
- Blocking metadata must be separate from advisory metadata.

### Required fields
- `kind: PolicyOutcomeKind`
- `reason: str`
- `blocking_code: str | None`
- `advisory_notes: list[str]`

## 4. Pending-state contract

There is no generic pending bucket.

### Pending clarification
A pending clarification stores:
- `clarification_id`
- `created_at`
- `expires_at`
- `prompt`
- `target`
- `bound_user_request`
- `allowed_reply_kinds`

#### Clarification semantics
- bound to exactly one unresolved ambiguous request
- satisfied only by a reply that narrows the missing field(s)
- expires by time or explicit invalidation
- invalidated by a new unrelated user request unless policy explicitly preserves it
- only one pending clarification may exist at a time

### Pending confirmation
A pending confirmation stores:
- `confirmation_id`
- `action_id`
- `created_at`
- `expires_at`
- `prompt`
- `requested_action`

#### Confirmation semantics
- bound to exactly one action ID
- one-shot only
- satisfied only by a positive confirmation reply
- stale `yes` / `confirm` must not execute anything if:
  - confirmation is expired
  - confirmation is missing
  - action ID is no longer valid
- invalidated by action mutation, expiry, or superseding request according to policy
- only one pending confirmation may exist at a time

### Coexistence rules
- pending clarification and pending confirmation cannot coexist
- if a new state would create one, the other must be cleared first
- clarification takes precedence over confirmation for ambiguous modify requests before an action becomes confirmable

### New unrelated input while pending state exists
- unrelated input cancels pending clarification
- unrelated input cancels pending confirmation
- cancellation must be recorded in trace

## 5. Tool protocol

### ToolRequest
Required fields:
- `tool_name`
- `arguments`
- `user_facing_label`

### ToolResult
Required fields:
- `ok`
- `tool_name`
- `execution_id`
- `summary`
- `data`
- `error_code`
- `error_message`
- `started_at`
- `finished_at`

### Validation boundary
- arguments must be validated before registry execution
- invalid tool request does not execute
- validation failures become `PolicyOutcome(block)` or tool failure depending on where detected

### Failure model
Tool failures are structured:
- validation failure
- unknown tool
- execution failure
- timeout
- denied by policy

### Registry execution contract
`execute(tool_request) -> ToolResult`

Registry responsibilities:
- validate tool existence
- dispatch execution
- return structured result only

## 6. Session persistence contract

### Persisted fields
- `schema_version`
- `session_id`
- `metadata`
- `messages`
- `summary`
- `pending_clarification`
- `pending_confirmation`
- `last_tool_execution`

### Session metadata
- `created_at`
- `updated_at`

### Missing session behavior
- loading a missing session must fail clearly with `SessionNotFoundError`

### Corrupt session behavior
- loading invalid or incomplete persisted state must fail clearly with `SessionCorruptError`
- no silent repair during load

### Resume behavior
`--resume` restores:
- session_id
- messages
- summary
- pending clarification
- pending confirmation
- last tool execution metadata

`--resume` does not restore:
- live in-memory tool handles
- expired pending state as executable
- transient CLI/UI-only state

Expired pending state may be loaded for inspection but must not be executable.

## 7. Audit trace minimum

Each turn must emit structured trace fields:
- `route_kind`
- `policy_outcome`
- `tool_invoked`
- `tool_execution_id`
- `pending_transition`
- `persistence_event`
- `notes`

This is minimum operational trace, not a full observability platform.

## 8. Invariants

- only one pending clarification at a time
- only one pending confirmation at a time
- pending clarification and pending confirmation cannot coexist
- a confirmation applies to exactly one action ID
- expired pending state cannot be executed
- unknown tools cannot execute unless explicitly allowed by policy
- RouteDecision is policy-free
- PolicyOutcome is the only execution gate
- persisted session schema version is required
- corrupt persisted sessions fail load explicitly

## 9. State transition examples

### Example 1: direct answer
Input state:
- no pending clarification
- no pending confirmation

User input:
- "What does this assistant do?"

Route decision:
- `answer`

Policy outcome:
- `allow`

Resulting state:
- append user message
- append assistant answer
- no pending state

Rendered output:
- direct answer text

### Example 2: ambiguous request -> clarification
Input state:
- no pending clarification
- no pending confirmation

User input:
- "Open the config file."

Route decision:
- `clarify`

Policy outcome:
- `require_clarification`

Resulting state:
- set pending clarification bound to the ambiguous request
- no pending confirmation

Rendered output:
- clarification prompt asking which config file

### Example 3: modifying request -> confirmation
Input state:
- no pending clarification
- no pending confirmation

User input:
- "Overwrite config.yaml with defaults."

Route decision:
- `tool` with `write_file`

Policy outcome:
- `require_confirmation`

Resulting state:
- set pending confirmation bound to one action ID
- no pending clarification

Rendered output:
- confirmation prompt naming `config.yaml`

### Example 4: confirmation accepted -> action executed
Input state:
- pending confirmation exists for action ID `a1`
- not expired

User input:
- "yes"

Route decision:
- `confirm`

Policy outcome:
- `allow`

Resulting state:
- execute bound action `a1`
- clear pending confirmation
- store last tool execution metadata

Rendered output:
- tool signal and execution result summary

### Example 5: stale confirmation rejected
Input state:
- pending confirmation exists for action ID `a1`
- expired

User input:
- "confirm"

Route decision:
- `confirm`

Policy outcome:
- `block`

Resulting state:
- clear expired pending confirmation
- do not execute tool

Rendered output:
- message that there is no valid pending confirmation to apply

### Example 6: resumed session with unresolved pending clarification
Input state:
- resumed session
- pending clarification loaded and still valid

User input:
- "the project config"

Route decision:
- `clarify`

Policy outcome:
- `allow`

Resulting state:
- resolve pending clarification
- clear pending clarification
- continue toward follow-up route on next step or same turn, depending on engine implementation

Rendered output:
- acknowledgment or next clarification / action prompt

### Example 7: new unrelated input while confirmation is pending
Input state:
- pending confirmation exists for action ID `a1`
- valid

User input:
- "What did we decide about memory?"

Route decision:
- `answer`

Policy outcome:
- `allow`

Resulting state:
- pending confirmation cleared as superseded by unrelated request
- append normal answer messages

Rendered output:
- direct answer
