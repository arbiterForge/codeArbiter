# Sprint approval and delegated method authority

This private extension adds no registered command, skill or agent. Check that the verified installed
native capability lists `sprint-approval-context`, `sprint-approve` and `smarts-apply`; a schema name
or model-written event is not an implementation. Qualified exact-prompt host observation remains
Claude Code or Codex only. Pi must not arm it without a real pre-model prompt seam. Other existing
host-specific verification/review restrictions are unchanged.

Prepare the complete ready same-slug spec and plan as unapproved drafts. The private planner
preflight accepts `draft_for_pair: true` only for a full-lane initial sprint, never `/feature`, an
existing approved pair, or an execution shortcut. Keep its `draft_preview` binding until the paired
transaction. Run scope/criterion coverage, recorded-intent and adversarial review on both drafts.
Present the optional plan-method delegation in the review packet before arming:

```sh
python "${PLUGIN_ROOT}/hooks/_approvallib.py" arm-sprint --root "<project-root>" --spec-id <spec-id> --plan-id <plan-id> --delegate-methods
```

Omit `--delegate-methods` for approval without delegated plan-method changes. Show the returned
`short_reply`, which restates the mode: `approve-sprint delegate <code>` or
`approve-sprint approve-only <code>`. The full `reply` naming both IDs, `delegate-methods` or
`approve-only`, and the nonce is also accepted, with the same tolerance as single approval.
An ordinary yes, wrong code/nonce/mode or changed member does not approve either. `sprint-approve`
recomputes both model/revision identities and the projected binding, verifies both observations
from the same actual reply, and commits the two approvals through the existing native journal.
It produces separate bound receipts and an optional `grant_receipt`. No partial approval is visible
while recovery is required. Generic `capture-observation` and single-artifact `approve` cannot reuse
these pair events to approve one half. Confirm both current `approved` gates before dispatch.

An interrupted observed submission retains its exact source events, operation ID and both CAS
identities. Resume it without asking the user to repeat the same decision:

```sh
python "${PLUGIN_ROOT}/hooks/_approvallib.py" resume-sprint --root "<project-root>" --plan-id <plan-id>
```

Arming without an observed reply cannot be resumed as authority. Recovery completes only this
exact observed transaction, not an unrelated pending operation. A committed replay is success;
a closed-set `REVISION_CONFLICT` or `OPERATION_ROLLED_BACK` proves this mutation did not commit and
retires only its stale pending request while preserving source history. Changed content needs a
new genuine approval, not an invented receipt. Other failures retain the request for diagnosis.
Before observation, the existing `cancel --artifact-id <plan-id>` clears an unapproved arm. After
submission, resume/recover first; cancellation cannot erase an uncertain transaction.

With an explicit paired user grant, evaluate an existing task-method choice using SMARTS Step 0,
all six lens verdicts and the actual supporting reasons. Query only the `smarts-apply` request schema.
Provide the exact current plan `artifact_id`, `expected` revision/model hash, unique `operation_id`,
original `grant_receipt`, and `decision` with task ID, options, selected index, strength and rationale.
Each option contains label, steps and the six qualitative verdict/reason cells. There is no new
numeric threshold, mandatory invented alternative or tie-triggered user interview. Persist the
bounded JSON request as inert input and invoke the installation-owned bridge:

```sh
python "${PLUGIN_ROOT}/hooks/_approvallib.py" smarts --root "<project-root>" --request-file <decision-request.json>
```

The native producer validates the original user grant and current bound spec/plan. Only the selected
existing task's method `steps` may change. Every path, criterion, test/verification definition,
prerequisite, dependency, checkpoint, rollback and input policy stays protected. Changes that widen
this scope or need a different authority use their real owner. The producer does not turn step text
into shell permission and never grants commit, network/provider, spending, disclosure, publication,
prerequisite or security authority. Normal execution gates still apply to the chosen method.

An affected `IN_PROGRESS` writer must quiesce before mutation. A successful method change emits an
actual `smarts_workflow` event/receipt and current plan approval together, invalidates affected
checkpoint/dependency proof to `PENDING` while preserving `BLOCKED` members and their reasons,
retains evidence refs as history and requires fresh context,
verification and reviews. It never accepts work. An identical method needs no new approval; retain
current evidence rather than manufacturing another attempt. Log material reasoning and record
citations in the existing sprint audit. Recorded judgments remain model judgments: integrity and
scope checks do not independently prove their truth or create a malicious-same-user sandbox.
