# migration — lens mandate

Executed by `tribunal-lens-reviewer` under the `migration` assignment.

## Purpose / failure family
Find schema/data transitions that violate compatibility, integrity, availability
or recovery obligations under the repository's declared deployment model.

## Applicability
Assigned changes migrate persisted data/schema or alter how deployed versions
read and write it.

## Skip conditions
No persisted transition or affected rollout contract. When the deploy model is
unknown, preserve that uncertainty instead of assuming a reversible rollout.

## Scope emphasis
Migration order, schema and query consumers, backfills, deployment windows and
recovery procedures for the affected data.

## Required reading
- Finding record (`${CLAUDE_PLUGIN_ROOT}/skills/tribunal/references/finding-record.md`) and review risk (`${CLAUDE_PLUGIN_ROOT}/skills/tribunal/references/review-risk.md`).
- `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md` — declared migration/deploy model,
  schema tools and version overlap; `${CLAUDE_PROJECT_DIR}/.codearbiter/security-controls.md`
  for relevant data classification and recovery obligations.

## Deterministic probes
Inspect migration history/order, schema diffs, deployed-version compatibility
matrices, query references and available table-size/lock evidence. Read recovery
and rollout checks as evidence; do not apply or roll back migrations.

## Review questions
- Does expand/contract ordering preserve mixed-version readers and writers?
- Can a backfill lose, duplicate or misclassify data, or fail partway irrecoverably?
- Do NOT NULL, renames, drops and index operations respect actual data and locks?
- Is destructive or irreversible work guarded by the required recovery evidence?
- Does editing a previously applied migration create divergent environments?

## False-positive guards / non-findings
A declared forward-only model may use a corrective migration and verified restore
procedure; a down migration is not universally required. A disposable schema or
exclusive downtime window may have different obligations from a rolling deploy.
Do not invent annotation or immutability requirements absent the actual contract.

## Evidence requirements
Cite the deployment model, affected data/version window, operation order and
concrete compatibility, locking or recovery failure. For an absent backfill or
recovery path, state the search universe across migrations, deployment orchestration
and recovery owners. Bound scale claims with available size/lock evidence.

## Exposure metric
Count of persisted transitions checked with their application-version and
recovery windows, not only migration-file count.

## Escalation / cross-lens handoff
Route rollout wiring to infra/change-closure, application authorization to appsec
and secret exposure to secrets-supply. Keep missing recovery proof distinct from
a demonstrated unrecoverable transition.

## Out of scope
Applying migrations, universal rollback policy, and unrelated application-level
data handling outside the assigned transition.
