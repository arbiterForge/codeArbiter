---
name: context-check
description: "Audit stale provenance-tracked docs on request. Report first; re-scout or re-baseline only for selected docs."
argument-hint: "(none)"
---

# context-check

An optional, on-demand drift audit for bypass cases: a merge or an external
edit drifted a tracked source file you are not about to commit, so commit-gate's
Phase 5.5 auto-heal did not fire. This skill reports stale docs and lets you
act on each one individually.

This skill is NOT in the daily loop. Commit-gate auto-heal (Phase 5.5,
`heal_worklist`) owns the routine maintenance path. Invoke this only when drift
was introduced outside a commit (e.g. a direct push, a merge you did not
author, a manual file edit).

<!-- catalog-compatibility-notice:start -->
> Compatibility route. Prefer `/ca-status drift` for new explicit usage. The retained entry
> and natural-language intent use this owner under
> <plugin-root>/includes/command-compatibility.md.
<!-- catalog-compatibility-notice:end -->

## Entry boundaries

Use this owner for a requested provenance drift audit, `/ca-status drift`, or
the explicit `/ca-context-check` compatibility entry. Explanation-only questions
and ordinary status snapshots remain read-only answers, not repair requests.
Report first. Write only after the user selects re-scout or re-baseline for that
document; never change an unselected derived document. This owner neither stages
nor commits. Routine commit-gate auto-heal is unchanged.

An **initialized refresh** belongs to this existing owner after an explicit
selection. It is separate from initial population: do not call the initialized
`/ca-create-context`/`/ca-init --brownfield` path, rerun the scaffolder,
clear `<!--INITIALIZED-->`, or repeat context finalization. An ordinary status
snapshot and the initial `/ca-status drift` report are read-only. A declined
refresh leaves every file unchanged.

## Pre-flight

Read these before computing drift:

1. `.codearbiter/.provenance/` — the per-doc provenance records. Load all
   records via `load_provenance_dir` from
   `<plugin-root>/hooks/_provenancelib.py`.
2. `.codearbiter/code-map.md` — coarse concern map; read to orient on which
   modules the stale docs govern.

## Flow

### Step 1 — Compute drift

Use `_provenancelib` helpers in this order:

1. `load_provenance_dir(root + "/.codearbiter/.provenance/")` — returns the
   provenance map `{doc: record}`.
2. Collect all `drift_trigger: true` paths across all records.
3. `batch_hash(paths, runner)` — hash every existing path in one git call.
4. `compute_drift(provenance_map, current_hashes)` — returns a drift report
   `{doc: [{path, kind}]}` for docs that have stale sources.

Alternatively reuse the same logic as `startup_drift_line` by calling it for
a human-readable summary, then inspecting `compute_drift` directly for detail.

The `entries`/Git-hash comparison above covers legacy v1 records only. For
every enrolled v2 document, call `assess_context_provenance` with the bounded
current source/target snapshot and an action-boundary snapshot probe. Inspect
its per-document states as well as aggregate coverage. A missing, corrupt or
unsupported record, incomplete acquisition, partial hash or unchecked identity
is unknown coverage, even when a neighboring v1 or v2 record is usable. Report
the usable records and the unknowns separately; never turn an empty legacy
drift report into a fresh verdict for v2. `v2_current` acknowledges matching
identities only. `semantic: unverified` and `verified_fresh: false` remain in
force until the owning semantic review and writer receipt establish otherwise;
changing hashes or choosing re-baseline does not perform that review.

Only if the relevant legacy drift report is empty and v2 coverage/identities
have been checked without unknowns may this audit report no stale identities.
That is not a claim that instruction-bearing facts are semantically verified.
Only a separately explicit full initialized refresh selection may proceed
without a stale-document list.

### Step 2 — Report stale docs

For each doc in the drift report, call `changed_scope(doc_provenance, drift)`
to list its drifted paths. Present a concise report before offering actions:

```
Stale docs (N):
  <doc>: <path1>, <path2>  (changed | missing)
  ...
```

Also present every enrolled v2 document's `v2_current`, `v2_stale` or unknown
state from Step 1. For `v2_stale`, derive a proposed affected scope from that
document's bounded evidence references and recheck the exact paths before
selection; the legacy `changed_scope` list cannot discover v2 drift. An
unknown state needs a bounded recovery/inspection, not an inferred fresh or
stale path. Do not offer an automatic write for an unbounded scope.

### Unsupported human content and owner reconciliation

An unsupported human Markdown layout, ambiguous duplicate anchor, unparseable
custom section, oversized document or absent managed ownership record is a
write refusal for that document, not a reason to erase it or abandon safe
task-time reading. An unrelated unknown section in an otherwise supported
document remains unowned and byte-identical during a supported field update.
Preserve exact bytes and report the specific unsupported or unowned span.
Use the existing applicable instructions under their actual precedence for the
current task; referencing those instructions unchanged does not create a new
normative rule or require a new approval. Keep observed upstream conventions
and accepted ADR references source-scoped when they do not already govern this
project. Surface a real conflict without silently displacing either source.

If the requested change would adopt or replace normative instructions, route
the proposal to its actual owner and obtain that owner's actual approval before
any supported bounded update. An unsupported template needs explicit
reconciliation or a qualified per-kind transition through the existing context
writer. Its refusal never authorizes raw Write/Edit fallback or a regex rewrite.
Task, question, audit, release and ADR files remain with their existing writers;
do not normalize, recreate or edit their history during context refresh.

### Step 3 — Selected initialized refresh

For each stale or bounded affected document, present supported re-scout,
re-baseline and defer choices; wait for the user's selection. A user may instead
explicitly select full refresh. Do not interpret
`status drift`, the drift report itself or an ordinary status request as that
selection. Record the selected documents and declared affected source paths
before any scout or write. An incremental refresh re-scouts only the selected
drifted paths and affected logical assignments. A full refresh declares all six
logical assignments and all five content documents. Retain prior coverage as
prior evidence; a scoped `join_scout_reports` result has `full_coverage: false`
and must never be described as a newly completed full scan.

**re-scout** — dispatch an incremental re-scout of the drifted paths for this
doc, scoped to those paths only. Use the context-creation containment profile,
run budget, `admit_scout_attempt` and `join_scout_reports` contract for exactly
the declared affected assignments. A missing/failed report, changed snapshot,
contradiction or unresolved task-dependent decision blocks the selected write.
If the claims still hold, a valid selected owned-field metadata refresh may
keep document bytes identical only when proposed v2 provenance actually
changes. Missing selection and unchanged proposed provenance refuse; retain
the stale pair and do not claim freshness in those cases. Any update still
requires current source evidence, exact preview approval and receipt-only
apply. Surface the proposed content and provenance pair for exact review.

**re-baseline** — the legacy v1 provenance choice may acknowledge a verified
cosmetic change through its existing owner, where applicable. For an enrolled
v2 content document, use only a selected owned field and the native bounded
update with new, validated source evidence and changed proposed provenance.
If no field is selected or the proposed pair is a true no-op, retain the stale
pair and defer that selection. Never directly write the v2 provenance or use
the legacy `rebaseline` helper as a fallback for it.

**full refresh** — only after explicit selection, use the same qualified
containment and bounded join with `mode: full` and six complete logical reports.
Synthesize all five content documents from the new evidence and reconcile gaps
under the context-creation Phase 3–4 rules. Do not enter its Phase 6 lock.

For each selected document, submit its finite typed `update` preview through
`python "<plugin-root>/hooks/init-codearbiter.py" --root <exact-root> --context-request <request-file>`.
The installed qualified context writer checks the existing document/provenance
pair, current source evidence, field ownership and protected target set. Review
the exact proposed pair and obtain its own native `approve-context` reply; apply
only its receipt through the same `--context-request` bridge. Read back the
committed pair and confirm the standalone `<!--INITIALIZED-->` marker remains
for `CONTEXT.md`. The writer's five content targets exclude task, question and
audit history. Never edit those owners as a side effect, hand-write a provenance
record, bypass a refusal, stage or commit here. If the installed writer or
qualified scout profile is unavailable, report that boundary and retain state.

**defer** — do nothing for this doc now. The drift line will reappear at the
next SessionStart. Use when the change is in-progress and the doc update should
wait for a later commit.

After processing selections, summarize changed documents, deferred selections,
the declared coverage, and whether the run was full or incremental. Keep
unselected content, initialized state and prior history intact.

## Hard rule

This skill MUST NOT commit. If re-scout or re-baseline produces updated
`.codearbiter/.provenance/` records, those file changes ride the next
user-initiated commit through commit-gate normally. No staging, no commits here.
