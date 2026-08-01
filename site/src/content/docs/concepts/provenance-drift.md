---
title: Provenance & Context Drift
description: "How codeArbiter tracks source-file hashes to detect when derived documents have drifted from their backing sources, and how the commit-gate auto-heal step keeps them current."
journey:
  level: Power user
  time: 8 min
  outcome: "the ability to trace a stale derived document to changed source and choose re-scout, re-baseline, or defer without hiding drift."
  prerequisites:
    - A repository with provenance-tracked context
  proof: "Context-check reports no unexplained stale documents, or each defer has an explicit reopen condition."
---

Every derived document under `.codearbiter/` traces its claims to source files in the repo. codeArbiter records this mapping as **provenance**: which files back a given doc, and the `git hash-object` hash of each file at the time the doc was authored. When a tracked source changes, the stored hash no longer matches. That mismatch is **context drift**.

## What happens when source changes

Drift is surfaced once, passively, as a single line at SessionStart. It does not interrupt work. `.codearbiter/code-map.md` provides a coarse orientation map: it names the main source files and the docs that depend on them. `/ca:context-check` runs the same detection on demand, as a manual audit.

When a commit lands, the **commit-gate auto-heal** step checks whether any staged source files have drifted their dependent docs. If they have, it re-baselines the provenance in the same commit or proposes a doc update to accompany the work, so a stale claim gets flagged and corrected before it can be read as current. Auto-heal is commit-gate's Phase 5.5, per the [commit-gate skill](/reference/skills/commit-gate/); on an ordinary commit with an empty worklist, it costs nothing.

Per-document provenance records live under `.codearbiter/.provenance/`. [`/ca:context-check`](/reference/commands/context-check/) runs the same drift detection as a manual, on-demand audit, and offers three dispositions per stale doc: re-scout it from the current source, re-baseline the stored hash without re-scouting, or defer.

## Choose the correct disposition

| Choice | Use it when | Result |
|---|---|---|
| Re-scout | The source change may make the document's claims incomplete or false. | Rebuild the document from current evidence, then record new hashes. |
| Re-baseline | You inspected the source change and proved the existing claims remain true. | Keep the document and update only its source hashes. |
| Defer | The document needs work that is out of scope for the current change. | Leave the mismatch visible with an explicit reopen condition. |

Re-baselining is an evidence claim, not a way to silence the warning. If you cannot explain why the
text remains correct, re-scout or defer.

<figure class="ca-diagram">
  <img src="/diagrams/provenance-drift-flow.svg" alt="Context-drift provenance flow: a tracked source change is detected by a git hash-object mismatch, surfaced at SessionStart, and healed by commit-gate which re-baselines or proposes a doc update with the work commit." loading="lazy" />
  <figcaption>Provenance tracks source hashes. A mismatch is detected at SessionStart and healed when the commit lands.</figcaption>
</figure>

Run the host-native context-check command to inspect drift without changing ordinary project files:
Claude Code `/ca:context-check`, Codex `$ca-context-check`, Pi `/ca-context-check`.

Read the report one document at a time. A clean result names no stale provenance records. A stale
result should name the derived document, changed source, old hash, and current hash; if it cannot,
treat the record as untrustworthy and re-scout rather than blindly re-baseline.

After a disposition, run context-check again. Re-scouted and proven re-baselined documents should
leave the stale set. Deferred documents should remain visible with the condition that will reopen
them; defer is tracked debt, not a green result.
