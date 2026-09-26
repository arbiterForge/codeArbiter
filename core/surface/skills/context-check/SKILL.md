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
> Compatibility route. Prefer `{{CMD:status}} drift` for new explicit usage. The retained entry
> and natural-language intent use this owner under
> {{PLUGIN_ROOT}}/includes/command-compatibility.md.
<!-- catalog-compatibility-notice:end -->

## Entry boundaries

Use this owner for a requested provenance drift audit, `{{CMD:status}} drift`, or
the explicit `{{CMD:context-check}}` compatibility entry. Explanation-only questions
and ordinary status snapshots remain read-only answers, not repair requests.
Report first. Write only after the user selects re-scout or re-baseline for that
document; never change an unselected derived document. This owner neither stages
nor commits. Routine commit-gate auto-heal is unchanged.

## Pre-flight

Read these before computing drift:

1. `.codearbiter/.provenance/` — the per-doc provenance records. Load all
   records via `load_provenance_dir` from
   `{{PLUGIN_ROOT}}/hooks/_provenancelib.py`.
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

If the drift report is empty: report "no stale docs — provenance is fresh"
and exit. No further action required.

### Step 2 — Report stale docs

For each doc in the drift report, call `changed_scope(doc_provenance, drift)`
to list its drifted paths. Present a concise report before offering actions:

```
Stale docs (N):
  <doc>: <path1>, <path2>  (changed | missing)
  ...
```

### Step 3 — Per-doc action loop

For each stale doc, present three choices and wait for the user to select one:

**re-scout** — dispatch an incremental re-scout of the drifted paths for this
doc, scoped to those paths only (like commit-gate Phase 5.5 heal but manually
invoked). The scout re-reads the changed paths and reports whether claims still
hold. If claims still hold: silently re-baseline the hashes via `rebaseline`.
If claims changed: surface the proposed doc edits for the user to accept before
re-baselining.

**re-baseline** — acknowledge the drift without re-scouting: call
`rebaseline(provenance, current_hashes)` to update the stored hashes silently.
Use this when the source change is cosmetic (formatting, comments, whitespace)
and the derived doc claims are still accurate.

**defer** — do nothing for this doc now. The drift line will reappear at the
next SessionStart. Use when the change is in-progress and the doc update should
wait for a later commit.

After processing all stale docs, summarize which docs were re-scouted,
re-baselined, or deferred.

## Hard rule

This skill MUST NOT commit. If re-scout or re-baseline produces updated
`.codearbiter/.provenance/` records, those file changes ride the next
user-initiated commit through commit-gate normally. No staging, no commits here.
