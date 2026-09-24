---
title: Selected Hardening Notes
description: "Understand the failure patterns behind selected controls while keeping historical fixes, current implementation and verified release behavior distinct."
journey:
  level: Reference
  time: "10 minutes"
  outcome: "Explain why evidence is bound to content and writers are constrained without treating a historical fix as universal current protection."
  prerequisites:
    - Enforcement & Security
    - Auditability
  proof: "You can name the original failure, its intended control, the current source to inspect and the evidence still needed for an installed release."
---

Hardening is the work of turning an observed failure into a bounded control and a regression
that detects its return. This page preserves selected design lessons. **It is not a complete
security history, a claim that every historical weakness is closed in every adapter, or an
independent audit of the current release.**

The earlier account is retained at
[its exact source revision](https://github.com/arbiterForge/codeArbiter/blob/aebee1bb753d29e34030ee22c98c9eb8fabb1752/site/src/content/docs/concepts/hardening-history.md).
Its version-specific examples remain historical. Read [Enforcement & Security](/enforcement/)
for the product boundary, [Auditability](/concepts/auditability/) for the meaning of retained
records, and the [Changelog](/changelog/) for the chronological release record.

## Why the Crypto/Secret Gate Is Digest-Bound (H-09b / H-10b)

Consider a review that approves one sensitive change. Another edit arrives a minute later.
A timestamp-only pass would still look fresh, but it would say nothing about that second edit.
This is the time-of-check/time-of-use problem the digest-bound design addresses: the permission
must apply to the content being evaluated, not just to a recent conversation.

The current source's security commit check combines a fresh marker with coverage of the
sensitive lines in the relevant diff. Its source explicitly considers staged content and the
applicable worktree content for commit forms that include it. The wrapper delegates to the
shared guard implementation; an old location in `pre-bash.py` is not a reason to ignore the
current `_bashguardlib.py` and scan helpers.

The important distinction is **freshness versus coverage**. Freshness limits how long a record
may apply. Coverage binds it to the lines actually considered. Neither a recent pass for unrelated
content nor a nonempty marker file is sufficient. The owning check must also distinguish an empty
diff from a diff it could not read; an unavailable scan cannot establish that nothing sensitive
changed.

That does not make a digest an authenticated human decision or a security proof about the whole
program. It is one part of a specific supported commit path. Classifier coverage, command parsing,
marker production, host events and installed payload identity remain separate assumptions to
verify. [Override guidance](/guides/overriding-a-gate/) explains the sanctioned exception boundary;
hand-editing marker contents is not that process.

To inspect a claim about this control, identify the installed version, the selected diff, the
matching scan result, the marker's actual scope, and the next guarded operation. A test of one
command shape should not be presented as evidence for every shell or every way to invoke Git.
The [hooks reference](/hooks/) links to the current implementation and exact emitted messages.

## Why the Board Has One Writer (ADR-0008)

A task board is useful only when its transitions remain legible. Free-hand edits can leave a task
in an impossible state, lose an identifier or remove a record instead of completing it. The
sanctioned writer validates the transition and preserves the board's schema; callers should use
that boundary rather than inventing their own Markdown edit.

The public task route exposes add, start and done. That is not a complete inventory of every
helper operation. The current task contract also describes the standup-owned archival sweep,
which requests an individual decision before invoking the helper's archive operation. It is not
a new public task-archive command, and it does not justify unattended removal of old records.

Co-locating a relevant board transition with its work commit reduces the risk of a separate,
lagging board-only PR. It does **not** eliminate every cross-session inconsistency. A branch can
contain a done marker before it merges; an interrupted or out-of-band workflow can still leave
records needing reconciliation. The marker describes board state, not independently verified
production delivery.

Treat a reconciliation report as a reason to inspect the work's actual source and PR, not as
permission to blindly flip a task. The correct question is which committed work, transition and
merge establish the intended relationship. Preserve unrelated work and follow the owning command
for any repair. [Return to a project](/guides/return-to-a-project/) teaches that inspection, and
[Review and ship](/guides/review-and-ship/) keeps commit, PR, merge and release distinct.

## Selected Historical Examples

The earlier account associated these themes with **v2.5.2 (2026-06-25)**. This overhaul preserves
that attribution; it did not acquire and rerun that release artifact. The examples explain why
controls were introduced, not which exact current installations are qualified.

**Broader detection.** The historical notes described adding legacy cryptographic identifiers,
TLS-disable forms, compound secret names and recognizable token shapes. The lesson is to bind
detection claims to a reviewed corpus and regression cases. A named pattern is not a guarantee
that every vulnerability or secret can be recognized.

**Atomic, content-bound passes.** The historical notes described gate records becoming atomic
and digest-bound. The lesson is that an interrupted write and a pass for different content must
not become permission to proceed. Verification still needs the actual producer and consumer.

**Shared audit-path classification.** The historical notes described centralizing the protected
path vocabulary. Sharing a catalog reduces inconsistent classifications, but every write surface
still needs its applicable mediation. “One catalog” does not prove that no unsupported route can
modify a file.

**Sandbox restrictions.** The historical notes described container user, filesystem, capability
and network restrictions. Those are boundary-specific settings, not proof that acquisition,
build, execution and export have identical filesystem exposure. Use the current
[sandbox guide](/guides/ca-sandbox/) for those distinct phases rather than applying a historical
“no host mounts” statement to the entire lifecycle.

## How to use a historical fix today

Start with the failure condition: what previously went wrong, on which input and path? Find the
implementation and regression at the version you are actually evaluating. Then run the relevant
supported path against the exact installed candidate, preserving its output and identity.

Keep the conclusions narrow. An accepted design explains intent. A merged fix establishes source
change. A passing test establishes its tested case. A release record establishes publication.
None of them alone establishes all the others. Missing evidence should remain an explicit gap,
not be filled by the age of the fix or a strong sentence in a historical note.

## Related

[Enforcement & Security](/enforcement/) owns the user-facing control boundary.
[ADRs and the Decision Log](/concepts/adrs/) separates accepted choices from implementation and
verification. [Role separation](/concepts/persona-and-context/) explains caller and writer
responsibilities, and [Changelog](/changelog/) remains the release chronology.
