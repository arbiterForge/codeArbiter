# Assistive state-engine upgrade: source-candidate runbook

**Status:** implementation/verification guidance for draft [PR #983](https://github.com/arbiterForge/codeArbiter/pull/983). This is **not** a released compatibility guarantee. Follow the actual installed package/tag until new binaries and adapters are published and read back.

**Owning decisions:** [ADR-0043](../../.codearbiter/decisions/0043-assistive-state-engine.md); [native artifact protocol](PROTOCOL.md). Applies only to personal `arbiterForge/codeArbiter`, including public `ca-pi`.

## Before upgrading a consumer repository

1. Identify the **actual installed** Claude/Codex/Pi adapter and pinned `release.json` binary identity. The repository's candidate manifests do not establish installed behavior. Avoid running an older and newer engine against the same canonical HTML pair at the same time.
2. Inspect current spec/plan, unfinished tasks, explicit user stops, outstanding host tool runs, and any **uncertain** native operation ID. Never assume a restart means work was not executed or that `BLOCKED` means permission was later granted.
3. Preserve a verified backup of **only the affected canonical HTML pair and its journal/receipt history**, with paths and hashes. Do not erase `.codearbiter`, historical receipts, or an in-flight journal. Keep source files and exact tasks under version control independently.
4. Only then install a coherent engine + Python bridge + generated host resources cohort through its documented release process. This draft PR does not grant a release exemption.

## Compatibility matrix (tested with two source-built development binaries)

| State | Older schema 0.3.1 engine | Newer schema 0.3.2 engine |
|---|---|---|
| Unchanged 0.3.1 pair | Read/write per the older protocol; old approval semantics still apply | Read unchanged bytes; no implicit reapproval or format rewrite |
| New 0.3.2 command observation or task field | **Fails closed** with `UNSUPPORTED_VERSION`, including during repository catalog scans | Journaled mutation; preserve IDs, task progress, explicit stops, and prior evidence |
| Retried same operation ID and request | Never invent a second action | Original committed result is replayed; no duplicate edit |
| Restore a previous binary after new edits | **Not a downgrade method.** Do not overwrite the modern plan | Forward recovery/export is the safe default |

The tested older client may refuse **the whole repository's canonical pair** after one modern artifact appears. Do not interpret this as a missing spec or delete/recreate it.

## When an old approval question is still pending

The new default workflow does **not** require artifact-specific user reply codes. Keep three separate cases:

- **Unanswered, properly bound legacy reconciliation question, no durable attempt:** after inspecting active work, use the existing helper's `--supersede --reason` command. It clears only that question/route and records a non-authorizing disposition; it never clears an actual task stop.
- **An answered prerequisite, submitted paired approval, or durable reconciliation mutation:** **do not discard the marker**. Use the owning historical recovery/replay method. A newly failing requirement or explicit user denial remains meaningful even when the old UI prompt is obsolete.
- **Unknown, malformed or conflicting legacy/current markers, uncertain host execution:** preserve the bytes and investigate. Do not bulk-delete marker directories, generate new approval events, or start the task under a fresh operation ID.

For a supported host whose plugin helpers include `artifact-reconcile.py`, an *unanswered* reconciliation repair looks like:

```sh
python "<PLUGIN_ROOT>/hooks/artifact-reconcile.py" \
  --root "<PROJECT_DIR>" --artifact-id PLAN-EXAMPLE \
  --supersede --reason "Confirmed no pending worker or mutation; old artifact prompt no longer applies"
```

If an attempt exists, this command refuses it. Use the helper's `--recover` to replay the **exact stored** operation; recoveries distinguish committed or proven-uncommitted outcomes. Inspect the result before dispatching any new work.

For older *ARMED* single-approval or prerequisite prompts, the existing owner-specific `cancel` methods remain available, but they are **not** universal cleanup commands. A confirmed/captured answer, submitted pair, or uncertain operation is not disposable.

## Recovering source state or returning to an older package

For a failed or ambiguous write, use the native `recover` transaction mechanism with the **original** operation ID and matching request, then reread `identity`. The engine's before-image must remain intact; a broken journal is not a reason to overwrite a changed document with an old file.

- **No new edits since the exact backup:** an explicitly reviewed restore may be possible after confirming file hashes, the installed cohort, and absence of running/uncertain mutations. Never infer this from timestamps alone.
- **Modern edits or check history exist:** continue with a compatible current binary and, when useful, create a **standalone** `export` under `.codearbiter/exports/`. It cannot replace or downgrade the canonical plan. Preserve edits, notes, receipts and evidence history.
- **Markdown-to-HTML migration:** native `migration-rollback` applies only to the original completed, reviewed Markdown pair cutover and refuses any subsequent edits. It does **not** implement a general 0.3.2-to-0.3.1 downgrade.

## Reproducible compatibility check

In a clean source candidate checkout with both trusted exact binaries:

```sh
python tools/test-artifact-mixed-schema.py \
  --old "<source-built-schema-0.3.1-engine>" \
  --candidate "<source-built-schema-0.3.2-engine>"
```

The probe creates a disposable temporary repository, writes no consumer files, and checks: unchanged old reads, first modern write, preserved user `BLOCKED` task, journal replay, older-client closed refusal, current plan identity, ordinary check **not** promoted to verified acceptance, and standalone export not altering the canonical pair.

**What is not proved:** model-backed host behavior, actual deployed artifact hashes, all possible older package states, full imported-build dependency closure, or that every historical prompt category has been migrated. Those need the final T09 installed-canary and packaging release gates.

## Acceptance receipts

Record the tested commit, exact two binary hashes/versions/platforms, test outcomes, checked repository kind (temporary or real), before/after canonical digests, legacy pending-state disposition, and whether the installed host was exercised. Distinguish **implemented**, **candidate tested**, **published**, and **installed verified**. No draft code or green source test alone is a shipping claim.
