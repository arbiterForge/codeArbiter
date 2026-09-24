# C03: repository knowledge and role separation

## Scope and source identity

The owner requested C03 on the existing PR #859 together with CI and arrow correction on
2026-09-24. This continuation follows `site/CONCEPTS-OVERHAUL.md`; it does not complete C04.
Source baseline: `aebee1bb753d29e34030ee22c98c9eb8fabb1752`, containing the already-published
arrow/deadline correction. The base repository CI and site runs passed before C03 began.

Current source is not an exact installed-release claim. Academy remains the separately pinned
Preview 0.32 source. No runtime, host capability, authority, package, curriculum or policy change
is made by C03. Existing C02 contradictions remain open at their owning record.

## Claim-specific owners

All references below use `arbiterForge/codeArbiter@aebee1bb753d29e34030ee22c98c9eb8fabb1752:`.

| Path | What was actually inspected |
|---|---|
| `core/pysrc/_provenancelib.py` | Record shape, exact drift-trigger selection, changed/missing results, rebaseline behavior, skipped invalid records and startup hash failure handling |
| `core/pysrc/_readinjectlib.py` | All-tier pointer accumulation, lazy provenance hashing, 150-token character proxy, legacy dedup, final HTML-aware overrides, same-snapshot epoch and diagnostics |
| `core/pysrc/pre-read.py` | Enabled-repository gate, normalized read path, additional-context output and fail-open exception posture |
| `core/pysrc/session-start.py` | Passive drift briefing; persona injection removed from startup in favor of per-turn composition |
| `core/pysrc/prompt-submit.py` | Per-prompt routing/composition entry, distinct from read-pointer advice |
| `core/surface/skills/context-check/SKILL.md` | Per-document re-scout/rebaseline/defer; no staging or commit; missing evidence remains separately interpreted |
| `core/surface/commands/context-check.md` | Compatibility routing and optional manual maintenance boundary |
| `core/surface/skills/commit-gate/SKILL.md` | Phase 5.5 incremental heal before commit, unchanged versus changed claims, scoped staging/review |
| `core/surface/skills/context-creation/SKILL.md` | Brownfield discovery and project-owned derived knowledge |
| `core/surface/skills/subagent-driven-development/SKILL.md` | Fresh task authors, caller-owned verification/acceptance and typed context handoff |
| `core/surface/skills/dispatching-parallel-agents/SKILL.md` | Role routing, no conflicting writes in one directory, complete unit accounting and read-only funnel |
| `core/surface/agents/checkpoint-aggregator.md` | Explicit report writer despite a reviewer classification; not a read-only verdict role |
| `core/surface/agents/{backend-author,frontend-author,infra-author,finding-triage,verdict-aggregator}.md` | Distinct worker tools, responsibilities and output obligations |
| `core/surface/commands/task.md` | Public add/start/done versus standup-owned archival helper use |
| `core/pysrc/_bashguardlib.py` | Current security-diff and marker consumer rather than obsolete monolithic entry-file wording |
| `site/src/content/docs/concepts/{persona-research-basis,hardening-history}.md` | Historical claims, attribution, existing public anchors and provenance to preserve |

## Corrections made in derivative teaching

**C03-DOC-01: first-match context narrative.** The old concept and static diagram described a
highest-priority winner. The implementation accumulates all matching tiers before bounded assembly.
The new page, actual fixture and static map teach that order; no runtime was changed.

**C03-DOC-02: freshness scope and timing.** Recorded hashes are not comprehensive semantic proof.
Only actual records and applicable drift-trigger flags define the alarm scope. Commit auto-heal is
before the work commit, not a post-merge repair promise. The curated example no longer invents a
number of commits since a mismatch or a glob as a concrete hashed source.

**C03-DOC-03: all reviewers read-only / only authors write.** The explicit checkpoint writer is a
counterexample. The role page distinguishes the writer from triage/verdict roles and explains the
host boundary rather than treating a charter or classification label as enforced isolation.

**C03-DOC-04: historical efficacy and absolute hardening.** Original research attribution is retained
without promoting historical percentages or a single project experiment to current efficacy. The
hardening page removes the universal no-drift assertion, describes the archival writer exception and
keeps v2.5.2 examples explicitly historical. Exact original pages remain linked. No research result
was rerun or replaced with a new benchmark claim.

## Actual helper capture

`site/scripts/capture-context-examples.py` invokes the current `_readinjectlib` and
`_provenancelib` over a temporary Git repository. It records exact fixture files, provenance
records, helper-source SHA-256 values, hashes, candidate pointers, bounded output, repeated-read
output, changed-source drift and the character-proxy budget. `--check` reproduces those results
and compares them with `site/src/data/context-examples.json`.

The four cases are all-tier overlap, fresh package mapping, changed package source, and an
unmapped file. They demonstrate actual helper behavior, not a host event, approval ceremony,
production context completeness, typed-authority qualification or isolation. Counts identify
provenance hash calls, not all work performed by every host path. The fixture's accepted Markdown
ADR/spec fields are inputs, not authenticated acceptance records. They exist only in the disposable
repository.

The UI is a read-only explorer of this existing capture. It does not run a helper, store a reading
choice or submit a request. No production token budget, gate, dedup marker or artifact was modified.

## Verification and continuation

Run the capture check, source/content tests, generation and diagram audit, unit/type/voice checks,
non-root build and link audit, followed by the actual hosted browser suite. The latter must inspect
all observations at 320/390/768/1024/1440px, same-content enlarged text, no JavaScript, print,
normal/forced colors, keyboard access, navigation/back and zero selector side effects. Keep the
existing corrected arrow and guide tests. Record final commit/tree, CI runs and actual captures in
the PR rather than claiming this source note is a completed execution receipt.

C04 broader workflow propagation remains open. Roll back C03 presentation and tests as a coherent
unit while preserving public addresses, C01/C02, the earlier mobile corrections and the validated
CI/arrow fix. Do not alter actual project records or historical authority to roll back documentation.
