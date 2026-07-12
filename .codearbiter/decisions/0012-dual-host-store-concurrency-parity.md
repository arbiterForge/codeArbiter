---
status: accepted
date: 2026-07-09
title: Dual-host .codearbiter/ concurrency is at parity with same-host concurrency
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/pysrc/taskwrite.py, core/pysrc/_hooklib.py, core/pysrc/session-start.py
---

# ADR-0012 — Dual-host `.codearbiter/` concurrency is at parity with same-host concurrency

## Status
Accepted — ratified 2026-07-12 by SUaDtL@users.noreply.github.com ("i approve adr 12").
The accepted bar remains same-host concurrency parity; this decision does not authorize
a stronger locking or CAS obligation.

**Record correction (2026-07-12, DECISION-0014):** commit 3902096 set this ADR to
accepted carrying a ratification line dated 2026-07-11 that had not occurred; the
maintainer's actual ratification is the 2026-07-12 statement quoted above. Recorded so
the trail shows the premature flip and its correction rather than a silent overwrite.

## Context
ADR-0011 lets Claude Code and Codex CLI share one `.codearbiter/` store per repository, so two
different hosts can now read and write the same governance state concurrently. The tribunal audit of
`feat/codex-support-m0` (run `2026-07-09-codex-support-branch`, issue #269) surfaced three concurrency
concerns on that shared store:

- **Lost board updates (reliability-004):** `taskwrite.py` mutates `open-tasks.md` through a lock-free
  read-modify-write (atomic `os.replace`, but no lock, re-read, or compare-and-swap), so two
  concurrent `/ca:task` sessions can silently drop an update or mint a duplicate dotted ID.
- **Dev-marker clobber (reliability-007):** `SessionStart` unconditionally clears the repo-global
  `.markers/dev-active` marker and appends a synthetic `DEV: exit` to `overrides.log`, so starting one
  session while another is live in `/dev` clobbers the running session's marker and writes a false
  audit close.
- **No host attribution (observability-001):** `gate-events.log` / `overrides.log` record
  `hook=<script>` but not which host wrote the entry, even though `get_host().name` is available at
  every log call site.

The maintainer set the bar for the decision: two agents sharing one repo on Codex must be **no worse
off than two agents on Claude today**. The `taskwrite` read-modify-write race and the repo-global
dev-marker clobber are pre-existing, host-agnostic behaviors — two concurrent Claude sessions race
identically. This branch only vendored that shared-core logic to a second host; it introduced no new
failure mode in either case. The one gap genuinely new to dual-host is audit attribution: two distinct
host identities now share a single trail with no way to tell their entries apart, which never mattered
when both writers were the same host.

## Decision
Dual-host concurrency on the shared `.codearbiter/` store is accepted at **parity with same-host
concurrency** — the Codex campaign owes no concurrency guarantee stronger than what two Claude sessions
already have. Concretely:

1. **Add host attribution** to the audit-log writes (`_hooklib` gate-event / block / remind / warn),
   recording `get_host().name` on each line. This is the only obligation genuinely new to dual-host,
   and it ships as a fix in the codex-support sprint.
2. **Do not add file locking or compare-and-swap** to the read-modify-write state as part of the Codex
   campaign. `reliability-004` (board lost update) and `reliability-007` (dev-marker clobber) are
   re-scoped as pre-existing, host-agnostic concurrency debt, tracked separately, and are **not**
   `feat/codex-support-m0` blockers.

## Alternatives considered
- **Full concurrency contract (locking/CAS on all RMW state + attribution + session-scoped dev
  marker).** Rejected against the maintainer's bar: it would fix a pre-existing, host-agnostic problem
  under the Codex banner and hold the Codex branch hostage to work that has nothing to do with the
  second host. A worthwhile future hardening for all host pairs, but out of scope here.
- **Attribution only, with no acknowledgement of the pre-existing debt.** Rejected: it would leave the
  lock-free RMW and dev-marker clobber unrecorded, inviting a future audit to re-file them as Codex
  regressions when they are neither Codex-specific nor new.

## Consequences
- The shared audit trail becomes host-attributable, restoring forensic value now that two host
  identities write to it.
- Concurrency parity with same-host use is the accepted, documented contract; a reviewer will not block
  the Codex branch on the lock-free RMW or the dev-marker clobber.
- A future hardening effort (lockfile CAS on RMW state, session-scoped markers) can raise the bar for
  every host pair — Claude-Claude included — as its own tracked work, independent of the Codex campaign.

## Risks
- If concurrent use of one repo becomes common (more likely now that a second host is supported), the
  pre-existing lost-update and marker-clobber races will surface more often. The mitigation is the
  separately-tracked hardening, not a Codex-branch blocker. This decision is proven wrong only if
  dual-host use exhibits a concurrency failure mode that same-host use does not — none was found in the
  audit.
- Relates to ADR-0010 (cooperative-agent trust model) and extends ADR-0011 (multi-host shared core).
