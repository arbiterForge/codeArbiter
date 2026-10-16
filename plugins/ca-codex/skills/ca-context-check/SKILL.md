---
name: ca-context-check
description: "Inspect context drift and refresh selected source-backed documents under existing authorization."
argument-hint: "(none)"
---

# context-check

Inspect context drift or refresh selected source-backed documents. This includes
drift from a merge or external edit that commit-gate's Phase 5.5 auto-heal did
not cover, and an explicitly requested full refresh of initialized context.

This skill is NOT in the daily loop. Commit-gate auto-heal (Phase 5.5,
`heal_worklist`) owns the routine maintenance path. Reuse existing selection and
authorization for requested refresh; an audit-only request remains read-only.

<!-- catalog-compatibility-notice:start -->
> Compatibility route. Prefer `$ca-status drift` for new explicit usage. The retained entry
> and natural-language intent use this owner under
> [includes/command-compatibility.md](../../includes/command-compatibility.md).
<!-- catalog-compatibility-notice:end -->

## Entry boundaries

Use this owner for a requested provenance drift audit, `$ca-status drift`, or
the explicit `$ca-context-check` compatibility entry. Explanation-only questions
and ordinary status snapshots remain read-only answers, not repair requests.
Report first for an audit-only request. A direct request to refresh selected
documents or the full project context supplies that selection; reuse the
existing authorization instead of asking again per document. Never change an
unselected derived document. This owner neither stages nor commits. Routine
commit-gate auto-heal is unchanged.

An **initialized refresh** belongs to this existing owner after an explicit
selection. It is separate from initial population: do not call the initialized
`$ca-create-context`/`$ca-init --brownfield` path, rerun the scaffolder,
clear `<!--INITIALIZED-->`, or repeat context finalization. An ordinary status
snapshot and the initial `$ca-status drift` report are read-only. A declined
refresh leaves every file unchanged.

## Pre-flight

Read these before computing drift:

1. `.codearbiter/.provenance/` — the per-doc provenance records. Load all
   records via `load_provenance_dir` from
   [hooks/_provenancelib.py](../../hooks/_provenancelib.py).
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
force: only actual evidence can support a narrower semantic claim;
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
custom section or oversized document is a write refusal for that document, not a reason to erase it or abandon safe
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
any supported bounded update. Missing or legacy v1 provenance may use explicit native `adopt` with current
evidence and selected supported spans, preserving the old provenance preimage.
An unsupported template still needs reconciliation through its actual owner or
a supported writer transition. Its refusal never authorizes raw Write/Edit fallback or a regex rewrite.
Task, question, audit, release and ADR files remain with their existing writers;
do not normalize, recreate or edit their history during context refresh.

### Step 3 — Selected initialized refresh

Use the user's selected documents and affected scope. If only an audit was
requested, offer reinspection, re-baseline and defer choices before writing.
A request for full refresh already selects all five content documents and all
six logical categories; do not repeat that question. Record the selection and
source paths, then inspect only what those claims need. Keep the initialized
marker and prior history. Full inspection accounts for all six categories;
incremental inspection does not claim a new full scan.

**re-scout / reinspect** — use direct bounded inspection or optional scoped
agents for the selected claims. The context-creation evidence and gap rules
apply. When structured reports help, `join_scout_reports` tracks their declared
coverage; a scoped result has `full_coverage: false`. The helper is not a
permission or containment check. A missing report can be replaced by direct
inspection, but failed or uninspected work never becomes evidence of absence.
Recheck changed source snapshots and resolve contradictions before their
claims are written. Unrelated gaps do not hold independent selected work.

If claims still hold, a selected owned-field metadata refresh may keep document
bytes identical when current evidence changes the v2 provenance. Missing
selection and unchanged proposed provenance refuse rather than claim a refresh.
Surface the proposed content and provenance pair, inspect its source bindings,
and apply within the selected authorization. Review consequential or disputed
claims independently when useful; a matching digest does not verify semantics.

**re-baseline** — the legacy v1 provenance choice may acknowledge a verified
cosmetic change through its existing owner, where applicable. For an enrolled
v2 content document, use only a selected owned field and the native bounded
update with new, validated source evidence and changed proposed provenance.
If no field is selected or the proposed pair is a true no-op, retain the stale
pair and defer that selection. Never directly write the v2 provenance or use
the legacy `rebaseline` helper as a fallback for it.

**full refresh** — use bounded inspection across all six categories and
synthesize all five content documents from current evidence. Preserve unknowns
and reconcile material user decisions under context-creation Phase 3–4. Do not
enter its Phase 6 lock for an already initialized repository.

For a selected whole-document refresh, prepare a UTF-8 draft inside the workspace
that retains user-owned content outside the requested change. The installed CLI
collects bounded source hashes and chooses create/adopt/update from the current
pair. Substitute the actual inspected repository-relative source paths; repeat
`--source` for each supporting file. For example:

```text
python "${PLUGIN_ROOT}/hooks/init-codearbiter.py" --root "<project-root>" --context-draft "context-code-map-draft.md" --document code-map --source "src/main.py"
```

This retains an internal preview but does not change the content document or
provenance. Inspect the returned diff, then apply the exact returned reference
and digest:

```text
python "${PLUGIN_ROOT}/hooks/init-codearbiter.py" --root "<project-root>" --context-apply "<preview_ref>" --preview-sha256 "<preview_sha256>"
```

The source list must support the draft; it is not an automatic semantic review.
The convenience path records `semantic_review: unreviewed`. Use typed field
previews below when only specific managed fields are selected.

For each selected document, send the typed preview through
`python "${PLUGIN_ROOT}/hooks/init-codearbiter.py" --root <exact-root> --context-request <request-file>`.
The request uses `operation: preview` and a `preview` object. Native
`context-preview` supports `create` for a genuinely absent document, explicit
`adopt` for supported missing/v1 provenance, and `update` for a managed v2 pair.
Supply the exact expected document/provenance hashes, selected fields, typed
content and source evidence. Keep request files inside the workspace.

Inspect the returned diff and preserved content. Apply with `operation: apply`,
`preview_ref` and `preview_sha256` through the same bridge;
native `context-apply` rechecks the preview and current identities under its
lock and writes the selected document/provenance pair together. No approval
receipt, actor ticket or qualified scout profile is a prerequisite for ordinary
already-authorized refresh. This is compare-and-swap protection, not a second
permission system. A stale preview requires reinspection, never an overwrite.
After a lost response, inspect the transaction and retry its identical request
and operation ID or use native recovery; do not start a duplicate write.

Read back the committed pair and confirm `<!--INITIALIZED-->` remains for
`CONTEXT.md`. Keep unowned spans byte-identical and retain legacy provenance
history. Task, question, audit, release and ADR history stay with their actual
writers. Never hand-write a provenance record or bypass a refused unsupported
shape. A missing safe writer stops that write, not authorized task-time reads.

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
