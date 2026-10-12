---
status: accepted
date: 2026-10-08
title: Bind structured-artifact evidence inputs to the git ship set
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/artifacts/internal/evidence/*, core/artifacts/internal/store/*, docs/artifacts/PROTOCOL.md, core/surface/includes/artifacts.md
---

# ADR-0042 — Bind structured-artifact evidence inputs to the git ship set

## Status
Accepted — decided by SUaDtL@users.noreply.github.com on 2026-10-08: "accept adr 452", confirmed as "42" when asked whether ADR-0042 was meant.

## Context

The structured-artifact engine binds verification receipts, review receipts and scope baselines to an
input identity. Today that identity comes from a filesystem walk of every file under the plan roots,
minus plan excludes and engine outputs. `.gitignore` does not affect it.

Two problems followed on 2026-10-07 during the SMARTS design-quality build (PR #893):

- **Runtime writes staled evidence.** A hook BLOCK appended one line to the tracked
  `.codearbiter/gate-events.log`. That changed the input identity and staled all 20 round-2 receipts.
  The append was not part of the work under review and was never going to change what ships.
- **Snapshots were slow.** One snapshot took 28 s on the SMARTS worktree and 16 s on a clean
  codeArbiter worktree. That exceeded the 30 s UserPromptSubmit hook limit (#931). Profiling showed
  the cost is per-file rooted handle opens in `store/fs_portable.go` (Windows NtCreateFile, scanned by
  Defender), not hashing: reading and hashing the whole SMARTS ship set takes 0.4 s.

The user's requirement: "I don't want a random append by another agent that is part of a file that
isn't getting sent to remote" to stale evidence and stall the effort.

The spec is SPEC-SHIP-SET-EVIDENCE-INPUTS (`.codearbiter/specs/ship-set-evidence-inputs.html`),
approved at revision 2.

## Decision

Evidence input identity is the **git ship set**:

- Membership is the index entries (`git ls-files --stage`) that are present on disk, plus untracked
  files that are not ignored (`git ls-files --others --exclude-standard`).
- Plan roots and plan excludes still apply on top. Engine outputs stay excluded.
- File content is hashed from the working tree, so uncommitted edits to shipped files still count.
- A gitlink (mode 160000) contributes its pointer only, never the submodule's contents.
- `.codearbiter/gate-events.log` is a fixed, engine-declared runtime path that never counts as input.
  It stays tracked as the audit trail (#186). The exemption is not plan-configurable, and the
  existing guard against plans excluding `.codearbiter` stays. Other `.codearbiter` logs, such as
  `overrides.log` and `triage.log`, still count.
- A root that is not a git work tree falls back to the filesystem walk, labelled
  `membership: filesystem`. A failed git probe inside a git work tree fails closed; it never falls
  back silently.
- The manifest format advances to `codearbiter.verification-inputs/0.2.0`. Receipts that carry the
  0.1.0 format read as stale, not as an error.
- Snapshot reads must bound handle opens per file. This is checked through a counting seam, not
  wall-clock time.

## Alternatives considered

- **Commit-bound tree hash** (identity = the git tree of a commit; verification requires a clean
  tree). Rejected: it forces a commit before every verification and adds a new rule that the tree
  must match the commit. The user asked why dirty files count at all; the ship set answers that
  without making commits part of the verification loop.
- **Untrack `gate-events.log`** (make it local-only). Rejected: block history would be lost when merged
  worktrees are cleaned up, which reopens #186.
- **Plan-configurable runtime exemption.** Rejected: letting a plan exclude `.codearbiter` paths
  could hide governance state. One fixed, engine-declared path is narrower.
- **Keep the filesystem walk and only speed it up.** Rejected: runtime appends would still stale
  evidence.

## Consequences

- Ignored local state (`node_modules`, build output, `tmp/` when ignored) no longer stales evidence.
- A runtime append to `gate-events.log` no longer stales receipts.
- Snapshots get faster: fewer files, and fewer handle opens per file.
- Every existing receipt goes stale once, at the format change. An in-flight plan such as SMARTS
  needs a fresh verification round on the new engine.
- Git becomes a dependency of snapshotting in git roots. Probe failures are hard errors.

## Risks

- **Ignored inputs.** A test that depends on ignored local state (a stale `node_modules`, a locally
  built helper) can pass without its evidence going stale. The current rule exists to prevent that.
  The mitigation is exact-head hosted CI before merge.
- **Other appends still stale.** A `/ca:override` or triage append mid-round still stales everything.
  This decision exempts only `gate-events.log`.
- **What would prove it wrong:** shipped behavior that depends on an ignored file the receipts did not
  cover, or a second runtime-written tracked file that keeps staling evidence. The second case would
  argue for a declared runtime-path list rather than a single fixed path.
