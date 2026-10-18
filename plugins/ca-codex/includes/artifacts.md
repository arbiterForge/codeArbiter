# Structured specifications, plans and task state

Load for new full-lane work or an existing HTML spec/plan pair. The plan tracks
the agreed outcome, implementation and checks; it does **not** create a second
permission system. Follow real user decisions, host security and Git/release
authorization independently.

## Format and installed writer

New full feature and sprint spec/plan pairs default to canonical `.html`.
Check the installation-pinned native capability **before writing**. If it is
missing, invalid or denied, report the failed operation. It must not fall back to Markdown
or claim the artifact was saved. New files are
`.codearbiter/specs/<slug>.html` and `.codearbiter/plans/<slug>.html`.
An existing `.md` pair remains Markdown in its original format; do not
silently convert it or create a shadow ledger. Small-lane features stay inline.
HTML `--farm` dispatch remains disabled.

Use `hooks/_artifactlib.py`, which selects the installation-owned binary by
its verified manifest, never PATH or a project-selected executable. Native
`_select_authoring_route` and `_preflight_plan_authoring` select the same-slug
source/target, check identity and structural validity, then return a draft
target. They do **not** approve work or launch reviewers. This includes the
native Pi writer; it does not establish broader installed-host qualification.

## Author and maintain

Use native `create` and typed `apply`, not manual HTML/JSON editing. Keep stable
spec criterion IDs in the plan; use `record.add`/`record.update` and explicit
retirement reasons. Bind the exact current spec using `plan-bind`.
Incomplete drafts are valid working state. `validate` with `gate: ready`
reports missing coverage or structure, not permission to continue already
authorized work. Do not invent criteria, decisions or test results to pass
validation. A changed outcome goes to the actual decision owner; in-scope
methods and task decomposition can be updated with a reason.

A spec's SMARTS design rationale is stored in its existing `approach` record, bound
`decisions` records and one `SEC-SMARTS` section, as defined once in
[includes/smarts/core.md](smarts/core.md) (Design rationale record); a legacy Markdown spec
uses its one `## SMARTS design rationale` section instead.

Query an operation-specific `schema` only when its request shape is unknown;
reuse known shapes for subsequent calls instead of querying on every read.
Do not preload the entire schema. The packaged bridge invokes the verified native
binary as `ca-artifact <operation> --root <project-root> --request -`
with one JSON request on stdin; never resolve it from PATH. Requests use
protocol `codearbiter.artifact-api/0.1.0`; failed writes remain failures.

From the workspace root, pass this block on Python 3's stdin (`python -B -
'<absolute-installed-plugin-root>' '<plan-id>' '<task-id>'`, using your shell's
multiline stdin syntax and quoting). Use the host's loaded plugin root, not a
guessed project path. No helper script or directory outside the workspace is
needed. The client adds the protocol field; its second argument is the helper
installation, **not** the plugin root. Add `--schema` only when you need the
operation's request schema instead of the task packet.

```python
import json
import sys
from pathlib import Path

plugin = Path(sys.argv[1])
plan_id, task_id = sys.argv[2:4]
sys.path.insert(0, str(plugin / "hooks"))
from _artifactlib import ArtifactClient, helper_installation

client = ArtifactClient(Path.cwd(), helper_installation(str(plugin / "hooks/_artifactlib.py")))
if "--schema" in sys.argv[4:]:
    print(json.dumps(client.call("schema", {"name": "operation", "operation": "task-context"})))
else:
    identity = client.call("identity", {"artifact_id": plan_id})
    packet = client.call("task-context", {
        "artifact_id": plan_id, "task": task_id,
        "model_sha256": identity["model_sha256"],
    })
    print(json.dumps(packet))
```

## Read the smallest useful context

Use `identity` and `eligible` (advisory scheduling), then `task-context` with
the current plan `model_sha256` and task ID. Read the task, its referenced
criteria, dependency states and relevant prerequisite observations. The packet
has `context_complete: false`; expand only necessary exact symbols via
`read`/`read-batch` rather than parsing rendered HTML. Recheck identity after
a changed source or stale cursor. On a packet-size refusal, retrieve complete
individual records within the supported budget; do not accept truncation.
If an installed engine lacks `task-context`, use those existing bounded
symbol reads.

A fact or observable prerequisite is checked with ordinary authorized tools;
record its outcome through the native `prerequisite` **bounded `observation`**
with `kind: fact`, source and relevant `task_refs`. A decision reflects an
actual user choice; ask once if material and unresolved. Keep caller-reported
facts distinct from host-attested proof, and **no certification code** for
ordinary work. An unscoped prerequisite has unknown applicability, not
automatic plan-wide blocking or implicit satisfaction. Continue independent
tasks.

## Implement and report reality

Start an eligible pending task with `task-start`; no artifact approval,
context ticket or reviewer receipt is required. A real check belongs in
`task-check`: observed argv, relative cwd, outcome (pass/fail/skip/unknown),
summary, source and origin (`tool_result` or `agent_report`). Supply exit code
only when actually observed; bind `command_index` only to the exact planned
invocation. Command-level success is not invented named-test proof. A newer
failure/unknown cannot be hidden by an older pass.

`task-context` reports bounded, declared-path and `shared_inputs` source
applicability. `scoped_changed` means recheck affected work;
`scoped_unchanged` is **partial** evidence (`scope_complete: false`), not a
full dependency graph or verified test. Unsafe or unknown file scope is
`unassessed`. A presentation edit or new receipt identity alone does not
require a reviewer rerun.

Use receipt-free `task-review` for implementation ready for review.
Use `accept-scope` with a reason to record a completed implementation batch
as `DONE`; **DONE is not independently verified or accepted**. Report actual
checks, failures and unrun verification separately. Review relevant risks;
do not spawn a reviewer fleet to clear task bookkeeping.

## Resume safely

On interruption, inspect the worktree, running workers and committed state
before changing an `IN_PROGRESS` task. Use `task-reconcile` with the actual
state and reason; never clear a user `BLOCKED` stop without resolution.
Every mutation needs the current revision, model hash and a durable unique
operation ID. After a lost response, **retry the identical request and ID**
or use native `recover`; never start duplicate work or overwrite conflicts.
A rolled-back transaction is not success. Use `repair-preview`/`repair-apply`
only for the native generated-view repair contract, not semantic edits.

If saved state or a separately applicable policy genuinely requires strict
attested proof or older-format recovery, consult only the relevant section of
[includes/artifacts-attestation.md](artifacts-attestation.md). The optional reference
does not authorize ordinary work or replace current host/security rules.
Never open newer saved state with an incompatible old engine; use a matching
installed cohort and preserve the journal. After newer edits, forward
recovery takes precedence over overwriting current work with an old backup.
