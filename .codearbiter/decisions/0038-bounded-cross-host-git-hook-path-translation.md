---
status: accepted
date: 2026-09-20
title: Bounded 3-way path-form translation lets WSL and Git-for-Windows share one git-hook registry
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0014-githook-shim-dropin-fail-closed
governs: core/pysrc/_githooks.py, plugins/ca/hooks/_githooks.py, plugins/ca-codex/hooks/_githooks.py, plugins/ca-pi/hooks/_githooks.py, core/pysrc/doctor.py
---

# ADR-0038 — Bounded 3-way path-form translation lets WSL and Git-for-Windows share one git-hook registry

## Status
Accepted — accepted 2026-09-20 by SUaDtL@users.noreply.github.com, in the same session that chose
this option. Accepted/Planned: this records the governance decision; it does not itself claim the
translator is implemented or verified (see `/ca:fix` work on branch `fix/hooks-wsl-path-races`).

## Context

`/ca:debug` investigated GitHub issues #684, #686, #683: when the same physical
repository (or a same-runtime linked worktree of it) is used from both a
WSL-hosted process and Git for Windows, the shared drop-in registry
(`.git/codearbiter-hooksd/*.path`, ADR-0014) and the generated shim's embedded
`D=` drop-in-dir string end up written in whichever host's own path spelling
(Windows-native `C:/...`, Git-Bash/MSYS `/c/...`, or WSL drvfs `/mnt/c/...`)
wrote them last. `_shell_path()` (`core/pysrc/_githooks.py`) only normalizes
backslashes; it performs no translation between these spellings.

Verified directly (Opus adversarial review of the debug spec, then confirmed
against Git-Bash and WSL bash behavior): Git-Bash's `test`/`[ -f ]` resolves
BOTH `/c/...` and `C:/...`, but not `/mnt/c/...`; WSL bash resolves only
`/mnt/c/...`. **No single spelling is resolvable by both shells** — so any fix
that lets both hosts share one registry entry requires trying more than one
candidate spelling somewhere in the resolution path.

ADR-0014's own "Alternatives considered" already rejected this shape of fix —
"Multiple-candidate path embedding / runtime cache glob" — for a different,
narrower problem (deriving a *sibling plugin's* enforcer path), on the grounds
that "an unverified, host-layout-guessing filesystem search on every commit
under Windows Git-Bash — a fragile git-level backstop is worse than the
accepted trade." That rejection did not have, and could not have anticipated,
three independently-filed issues showing the *cross-host path-form* version of
this problem blocking real commits, pushes, and a release attempt (#683: "The
current release attempt will use a one-time logged override... and rely on
exact-head hosted CI before merge").

The full investigation, evidence, and the two dispositions this cluster split
into is recorded at `.codearbiter/specs/hooks-cross-host-path-races.md`
(branch `fix/hooks-wsl-path-races`). This ADR covers only the disposition that
needed a user decision — the path-form translator. The installer
partial-write race, the silent `trusted-executables.identity` lockout, and the
cross-host install/doctor churn are unambiguous code bugs and do not need this
ADR; they route to `/ca:fix` directly.

## Decision

Accept a **bounded, finite** 3-way path-form translator for the one grammar
this repo actually needs — Windows-native, Git-Bash/MSYS, and WSL-drvfs
spellings of an absolute path on a Windows drive letter — applied at the two
places a foreign spelling currently breaks resolution:

1. The drop-in registry write path (`.path` entries and
   `trusted-executables.identity`) may record, or the reader may derive, the
   candidate spellings a POSIX shell consumer would need, so a value written
   by one host's Python remains resolvable by the other host's shell.
2. The generated shim's resolution loop (and/or `doctor.py`'s equivalent
   Python-side checks) may test more than one candidate spelling for the same
   registered entry before concluding it doesn't resolve.

This explicitly **revisits, and narrows, ADR-0014's rejection of
multi-candidate resolution** — but only for this one closed, well-understood
grammar (three known spellings of a Windows-drive absolute path), never as a
general "guess the layout" search. It does **not** touch ADR-0014's fail-closed
contract: if none of the finite candidate spellings resolves, the shim still
fails closed exactly as ADR-0014 specifies. This is a **partial supersession**
— only the "Multiple-candidate path embedding" alternative in ADR-0014's
"Alternatives considered" section is revisited, for the cross-host path-form
problem specifically; ADR-0014's actual decision (shared drop-in dir,
fail-closed when nothing resolves, each host owns only its own entry) stands
unchanged and is not reopened.

## Alternatives considered

- **Keep WSL + Git-for-Windows mixed use formally unsupported (Exit-(b)'s
  other option).** Ship only the B1/B2/B3 robustness/observability fixes from
  the debug spec — the failure becomes fast, stable, and loudly diagnosed
  instead of flapping or silent, but WSL and Windows still cannot both operate
  on the same physical repo. Not chosen: the user weighed the now-demonstrated
  real blast radius (three filed issues, a blocked release, a "safe" false
  block that still stops work) against the bounded, finite grammar this
  translator actually needs, and chose to close the gap rather than merely
  make it clearer.
- **Store a single canonical spelling and require the consuming shell to
  translate it itself.** Rejected: there is no canonical spelling both shells
  already understand (see verified asymmetry above) — this would just move
  the untranslatable string from the registry to the shim body.
- **Full general host-layout discovery (glob/guess at runtime).** This is the
  shape ADR-0014 rejected and remains rejected here too — the translator is
  scoped to a closed, finite, statically-known grammar (three specific
  spellings of one path), never an open-ended filesystem search.

## Consequences

- `core/pysrc/_githooks.py` (and its materialized copies in `plugins/ca/`,
  `plugins/ca-codex/`, `plugins/ca-pi/` via `tools/sync-core.py`) gains a small,
  pure, no-I/O path-form converter and a resolution loop that tries each
  candidate — implemented test-first under `/ca:fix`, per the debug spec's
  regression-test obligations.
- `.codearbiter/tech-stack.md`'s "WSL is not a separately verified named cell...
  unsupported" paragraph becomes stale once the fix is proven and must be
  updated to record the new, measured support boundary — a docs follow-up
  landing with the fix, not a precondition for it.
- The git-level backstop's shim gains one more finite branch of logic to
  maintain (three candidate spellings instead of one path per registered
  entry); this is a one-time, bounded complexity cost, not an open-ended one.

## Risks

- **The translator itself could be a source of new bugs** in a security-critical
  fail-closed backstop — every candidate-spelling branch must still fail
  closed, never fail open, if none resolves. `/ca:fix`'s TDD obligations must
  cover the "nothing resolves" path as rigorously as the "one candidate
  resolves" path.
- **Scope creep.** If a future host introduces a fourth path grammar (e.g. a
  container bind-mount spelling), this ADR does not pre-authorize extending
  the translator to it — that would be a new decision, not an automatic
  widening of this one.
- This decision is proven wrong if the translator's candidate-resolution loop
  measurably slows down every commit/push (it runs on the hot path ADR-0014
  already cares about), or if it is later found to admit a spelling that
  resolves to the wrong file on some host/filesystem combination the test
  matrix did not anticipate — either would call for revisiting this decision
  specifically, not ADR-0014's original fail-closed contract.
