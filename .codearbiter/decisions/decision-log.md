# Decision log

Append-only. One entry per recorded architecture decision, mirroring the ADR files in this
directory. Format per `decision-variance/references/smarts.md`. Never edit a prior entry — to
supersede, append a new entry whose `Supersedes:` names the prior one.

Note: entries carry `Status: proposed` to match the ADR files' lifecycle state (proposed →
accepted → superseded | rejected). The smarts.md enum predates the decision-lifecycle `proposed`
state; `proposed` is used here for fidelity to the recorded ADR status.

---

## DECISION-0001 — ADR-0001 — Adopt a hybrid ADR + living-docs governance model

**Date:** 2026-06-13
**Status:** proposed
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** governance
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** Governance lived as prose in tech-stack.md/security-controls.md; no decision record existed.
- **Scaffold position:** The `/adr` + decision-log machinery existed but had never been used (0 ADRs).
- **Status type:** open-decision-closure

### Decision
Pin load-bearing architecture/security/governance decisions as numbered, immutable, user-attributed
ADRs under `.codearbiter/decisions/`; keep tech-stack.md and security-controls.md as living reference
docs. Recorded as a proposed ADR pending explicit ratification.

### SMARTS rationale
Reliable + Securable drove it: an immutable, attributed decision trail satisfies the audit and
commercialization-promotability requirement. Maintainable killed the full-migration alternative
(two drifting surfaces); the hybrid keeps the living "current state" docs.

### Implementation implication
`.codearbiter/decisions/` initialized; this log created. Future load-bearing decisions go through
`/ca:adr`. `governs:` globs cover the two governance docs and the decisions dir.

---

## DECISION-0002 — ADR-0002 — Trusted operator-authored shell input (plan.json / FARM_MUTATION_CMD)

**Date:** 2026-06-13
**Status:** proposed
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** security
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** security-controls.md did not declare farm.ts's plan.json shell-execution boundary.
- **Scaffold position:** farm.ts executes plan.json gate commands verbatim by design, length-capped.
- **Status type:** open-decision-closure

### Decision
plan.json gate/test commands and FARM_MUTATION_CMD are trusted, operator-authored, PR-reviewed shell
input; no content allowlist is imposed; the boundary is declared in the boundary-crossings table.

### SMARTS rationale
Maintainable + Securable favored documenting over allowlisting — an allowlist over-engineers a
trusted-operator input and risks breaking valid gates; an undeclared boundary is Securable-weak.

### Implementation implication
boundary-crossings table row added (this sprint, Workstream C). Revisit trigger: plan.json ever
ingesting untrusted/third-party source.

---

## DECISION-0003 — ADR-0003 — HTTPS-only API transport (loopback exception); FARM_API_KEY via env

**Date:** 2026-06-13
**Status:** proposed
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** security
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** security-controls.md TLS section validated only plan.meta.apiBaseUrl at parse time.
- **Scaffold position:** farm.ts resolved the base URL from env/plan/default; the env path bypassed validation.
- **Status type:** open-decision-closure

### Decision
Validate the resolved apiBaseUrl before every call via `assertSecureBaseUrl` — https-only with a
documented loopback http:// exception (no userinfo), WHATWG-URL-parsed; FARM_API_KEY via process.env
into the Authorization header only.

### SMARTS rationale
Securable + Reliable: closes a cleartext-secret-leak path on every fetch; URL parsing eliminates the
parser-differential class that a regex check risks. Verified by two security-reviewer PASS passes.

### Implementation implication
farm.ts `assertSecureBaseUrl` (Workstream B); TLS section + loopback boundary row updated (Workstream
C). Residual deferred LOW: FARM_API_KEY still in child-process env.

---

## DECISION-0004 — ADR-0004 — Database-free architecture; Python hooks stdlib-only

**Date:** 2026-06-13
**Status:** proposed
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** architecture
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** tech-stack.md asserted a database-free, stdlib-only design as prose only.
- **Scaffold position:** No datastore exists; hooks import only the Python standard library.
- **Status type:** open-decision-closure

### Decision
codeArbiter remains database-free (file-based prose state); all hooks under plugins/ca/hooks/ use the
Python standard library only — no third-party dependencies, ever.

### SMARTS rationale
Maintainable + Securable + Scalable-at-current-scale: zero install friction, no migration machinery,
a small auditable dependency surface; a datastore adds weight with no current benefit.

### Implementation implication
Recorded as ratification of existing design; no code change. Revisit trigger: project state outgrowing
file-based artifacts.

---

## Ratification — 2026-06-13

DECISION-0001, DECISION-0002, DECISION-0003, and DECISION-0004 advanced from
`proposed` to **`accepted`** on explicit user instruction
(SUaDtL@users.noreply.github.com), ratified 2026-06-13. The `accepted` state is
the canonical decision-log Status enum value (per
`decision-variance/references/smarts.md`), resolving the proposed-vs-enum
reconciliation noted in this log's header: the four entries above were recorded
`proposed` for fidelity to the ADR lifecycle at authoring time and are now
accepted. The ADR files (`0001..0004-*.md`) carry the authoritative
`status: accepted` frontmatter and a ratification line in their `## Status`
section. No content was superseded — ratification is the maturation of these
same decisions, not a new decision.

---

## DECISION-0005 — ADR-0005 — Split the persona register (terse gates, conversational thinking)

**Date:** 2026-06-16
**Status:** proposed
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** product/persona
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** Persona is terse everywhere by design (ORCHESTRATOR.md), including the exploratory thinking surfaces.
- **Scaffold position:** Issue #70's eval found uniform terseness is the cause of "flat" daily feel and a drag on adoption.
- **Status type:** open-decision-closure

### Decision
Run two persona registers scoped by surface: gates and enforcement (commit-gate, reviewer fleet,
hard STOPs, BLOCK findings) stay terse and non-negotiable; the thinking surfaces (brainstorming,
debug, decision-variance/SMARTS) run a conversational register. Sets direction for #82/#83/#84.

### SMARTS rationale
SMARTS verdict was tied (only Reliable differentiated, favoring terse gates over a chatty gate);
the non-SMARTS adoption factor broke the tie toward the split. Reliable holds the gate line;
warmth is quarantined to non-gating surfaces, so enforcement authority is preserved.

### Implementation implication
ADR-0005 authored. Future work on brainstorming/debug/decision-variance bodies and ORCHESTRATOR.md
register. Ratifies the direction of issues #82, #83, #84.

---

## DECISION-0006 — ADR-0006 — Broad-adoption OSS posture (decline a commercial vertical)

**Date:** 2026-06-16
**Status:** proposed
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** governance/strategy
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** No recorded strategic posture; the eval (#70) implicitly pushed a commercialize-to-vertical framing.
- **Scaffold position:** Issue #70 recommended re-targeting to a regulated/audited commercial ICP for willingness-to-pay.
- **Status type:** open-decision-closure

### Decision
codeArbiter stays broad open-source software optimized for public adoption; it declines
re-targeting to a regulated or narrow commercial vertical. The objective is maximizing adoption
of a tool with demonstrated value (a real team uses it daily). Explicitly overrules #70's
vertical-ICP recommendation.

### SMARTS rationale
The user reframed the ICP question as moot for OSS. Decision rests on non-SMARTS factors (intent,
adoption goal) over the eval's Securable-aligned commercial framing. The audit/SMARTS machinery is
retained as a broad-audience quality/trust feature, not a compliance-only one.

### Implementation implication
ADR-0006 authored. Priority order set: cold-install observation (#70 move 1), demo above the fold
(#71), zero-onboarding dry run (#81 /ca:preview), README adoption-proof positioning (#72).
Re-evaluation trigger: if adoption does not move after time-to-first-value + proof work ships,
the vertical-ICP question reopens.

---

## Ratification — 2026-06-16

DECISION-0005 and DECISION-0006 advanced from `proposed` to **`accepted`** on
explicit user instruction (SUaDtL@users.noreply.github.com), ratified 2026-06-16.
The ADR files (`0005-split-persona-register.md`, `0006-broad-adoption-oss-posture.md`)
carry the authoritative `status: accepted` frontmatter and a ratification line in their
`## Status` section. No content was superseded — ratification is the maturation of these
same decisions, not a new decision.

---

## DECISION-0007 — ADR-0007 — Host a second sibling plugin (ca-sandbox) in the repo/marketplace

**Date:** 2026-06-20
**Status:** proposed
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** architecture/governance
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** CONTEXT.md frames the repo as "the orchestration framework itself"; marketplace.json says "Single-plugin marketplace."
- **Scaffold position:** The marketplace `plugins` array supports multiple entries; the ca-sandbox brainstorm needs a home and integrates with farm.ts.
- **Status type:** open-decision-closure

### Decision
Host `ca-sandbox` as a second, sibling plugin (`plugins/ca-sandbox/`) in this repo/marketplace,
distinct from the `ca` governance plugin, with path-scoped CI so neither plugin's changes trigger the
other's checks. ca-sandbox is infrastructure arbiter integrates with, not part of the governance
kernel; the `ca` plugin's identity and gates are unchanged.

### SMARTS rationale
Maintainable + Scalable-at-current-scale favored co-location over a separate repo (one less repo for a
solo dev; tight `farm.ts` item-3 coupling) while path-scoped CI preserves independence. Securable held
the line that the governance plugin's gates must not absorb infrastructure concerns — hence sibling,
not embedded.

### Implementation implication
Update `.codearbiter/CONTEXT.md` and `.claude-plugin/marketplace.json` descriptions to state the
two-plugin shape; add the `{ "name": "ca-sandbox", "source": "./plugins/ca-sandbox" }` marketplace
entry; parameterize/duplicate CI (check-plugin-refs, version-bump, tools tests) per-plugin by path.
Re-evaluation trigger: if the two plugins require constant cross-plugin changes, reopen to merge or
split to separate repos.

---

## Ratification — 2026-06-20

DECISION-0007 advanced from `proposed` to **`accepted`** on explicit user instruction
(SUaDtL@users.noreply.github.com), ratified 2026-06-20. The ADR file
(`0007-second-plugin-ca-sandbox.md`) carries the authoritative `status: accepted` frontmatter and a
ratification line in its `## Status` section. No content was superseded — ratification is the
maturation of this decision, not a new one.

---

## DECISION-0008 — ADR-0008 — commit-gate is the board-sync chokepoint (task-board transitions ride the work commit)

**Date:** 2026-06-26
**Status:** proposed
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** process/governance
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** commit-gate Phase 6 ejects an `open-tasks.md` edit as scope creep; the raise-new harvest runs post-commit — so board flips landed in a separate `chore(board)` PR or a PR-description note (issue #142; drift in #138, #140/#141).
- **Scaffold position:** flips are human-declared via `/ca:task`→`taskwrite.py` (no inference); the board edit is invisible on `main` until merge, so co-locating it with the work commit is self-correcting.
- **Status type:** open-decision-closure

### Decision
commit-gate becomes the single board-sync chokepoint. done-flip rides the completing commit, start-flip rides the first work commit (both revert on abandonment); raise-new rides the work commit as a contingent default (the harvest moves pre-commit), with must-survive follow-ups filed as GitHub issues. Phase 6 stops flagging schema-valid board transitions as scope creep, Phase 7 stages them, and a `/ca:standup`/`/ca:doctor` reconciliation sweep backstops any residual drift.

### SMARTS rationale
Reliable + Maintainable: one atomic merge lands work and board state together, removing the cross-session memory dependency that was the failure mode, while the narrow Phase 6 exemption (only `taskwrite.py`-shaped diffs) preserves the genuine scope-creep check. The contingent-default + GitHub-issue split keeps capture co-located without a CI-writes-to-`main` mechanism (declined) or an unnecessary task→commit linkage convention (the human already declares the id).

### Implementation implication
Follow-on `/ca:feature`: commit-gate SKILL Phase 6/7 + harvest ordering, `/ca:task` doc, `harvest.md`, and `task-board-lifecycle.md` updated in lockstep; `/ca:standup` (and/or `/ca:doctor`) gains the board↔merged-PR reconciliation sweep. Resolves D-1's start-flip drop-off sibling. Re-evaluation trigger: board drift persists post-ship, or the Phase 6 exemption causes a scope-creep escape — reopen to the post-merge Action or a stricter linkage convention.

---

## Ratification — 2026-06-26

DECISION-0008 advanced from `proposed` to **`accepted`** on explicit user instruction
(SUaDtL@users.noreply.github.com), ratified 2026-06-26. The ADR file
(`0008-commit-gate-board-sync-chokepoint.md`) carries the authoritative `status: accepted` frontmatter
and a ratification line in its `## Status` section. No content was superseded — ratification is the
maturation of this decision, not a new one.

---

## DECISION-0009 — relicense-agplv3-dual-licensing — Relicense MIT → AGPLv3 with proprietary dual-licensing

**Date:** 2026-06-27
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** licensing / strategic posture
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** ADR-0006 set a broad-OSS-adoption posture under permissive MIT, declining a commercial vertical.
- **Scaffold position:** n/a — a maintainer strategic/licensing decision, not a scaffold-derived variance.
- **Status type:** divergent

### Decision
Relicense the open-source distribution from MIT to GNU AGPLv3, with sole copyright retained by the maintainer, who reserves a proprietary dual-licensing path for a planned closed-source SaaS. Future contributions require a CLA granting relicensing rights. Recorded as ADR-0009, which supersedes ADR-0006; the project stays OSS (AGPLv3 is OSI-approved) but trades adoption breadth for SaaS-moat protection plus a commercial path.

### SMARTS rationale
A maintainer strategic decision rather than a technical multi-lens arbitration. The driving factor is protecting future commercial value: AGPLv3's network-use copyleft deters a closed-source hosted fork that MIT permits freely, while sole ownership preserves a clean dual-license. The accepted cost, weighed and chosen by the maintainer, is reduced corporate adoption (AGPL is widely banned in enterprises) and added contribution friction from the CLA.

### Implementation implication
Follow-on /ca:chore: replace LICENSE with the canonical AGPLv3 text plus a sole-owner copyright line, add a README license-transition notice and a Dual-Licensing & Contributions section, and add CLA.md. No per-file headers (single-root-LICENSE convention retained). ADR-0009 governs LICENSE, README.md, CLA.md. ADR-0006 is superseded by ADR-0009 on the forward chain; its status field stays accepted on disk per the no-edit-prior-ADR rule, and /ca:adr-status will report the supersession.

---

## DECISION-0010 — security-gate-pass-cooperative-attestation — Security-gate pass is a cooperative-agent attestation, not a non-fabricable proof

**Date:** 2026-07-02
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** security / trust model
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** security-controls.md documented gate markers as enforcement without stating whether minting one proves a review occurred; tribunal appsec-003 (#196) surfaced that `security-pass.py` self-mints from the worktree with no review evidence.
- **Scaffold position:** n/a — an open trust-model design question, not a scaffold-derived variance.
- **Status type:** open-decision-closure

### Decision
codeArbiter's gate markers are cooperative-agent attestations, not tamper-proof proofs. Direct invocation of `security-pass.py` is the intended attestation mechanism; the trust boundary is documented in `security-controls.md`. No code change. Declined binding the marker to a non-fabricable reviewer-signed artifact — it defends a non-cooperating Bash-capable agent that already bypasses surrounding controls (appsec-002/#175), outside the product's cooperative-agent threat model. Recorded as ADR-0010.

### SMARTS rationale
Security-and-audit-trail lens (level 1) weighed against maintainability (level 3): the non-fabricable binding is real, brittle M-effort complexity that raises the review bar for a threat the product explicitly does not claim to stop. For a cooperating orchestrator, the marker's value is friction plus an audit trail, both preserved. The maintainer chose the documented-boundary posture over machinery whose protection evaporates against the very agent it would target.

### Implementation implication
No producer change. Add a "Gate-marker trust boundary" note to `security-controls.md` stating markers are cooperative-agent attestations and direct `security-pass.py` invocation is the intended attestation. Close issue #196 referencing ADR-0010. Reopens if the threat model expands to untrusted/adversarial agents.

---

## DECISION-0011 — ADR-0011 — Multi-host support: third sibling plugin ca-codex via shared core + thin host adapters

**Date:** 2026-07-08
**Status:** proposed
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** architecture / scope
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** CONTEXT.md "NOT this project" declares "Claude Code only"; v1's multi-host machinery was deliberately deleted.
- **Scaffold position:** n/a — an open scope decision prompted by Codex CLI v0.142.x reaching extension-point parity (plugins, blocking hooks, SKILL.md skills, subagents).
- **Status type:** open-decision-closure

### Decision
Host a third sibling plugin `plugins/ca-codex/` bringing the same governance kernel to Codex CLI, built as shared core + thin host adapters: host-neutral Python in `core/pysrc/` and markdown templates in `core/surface/`, vendored byte-exact into each plugin by stdlib generators with CI-enforced byte-identity. Independent SemVer from 0.1.0 (ADR-0007 pattern). Beta-labeled until live-Codex verification. Statusline and prune-transcript backend ledgered out of parity in docs/parity.md. Recorded as ADR-0011; amends CONTEXT.md's "Claude Code only" scope.

### SMARTS rationale
Maintainability (level 3) drove the architecture: copy-and-adapt reproduces the v1 drift failure, runtime shared imports couple to both hosts' clone layouts — build-time vendoring with a mechanical drift guard is the only option that keeps one source of truth without runtime fragility. Correctness of the audit trail (level 1) is preserved by keeping one shared `.codearbiter/` store and porting the same blocking gates. Adoption (ADR-0006 posture) motivated the scope expansion itself.

### Implementation implication
New `core/` + `tools/sync-core.py` + `tools/build-surface.py`; `plugins/ca-codex/` scaffold; CONTEXT.md identity/scope rewrite; release.yml and CI path filters parameterized for a third plugin (`core/**` triggers both suites); docs/parity.md ledger. Plan: `.codearbiter/plans/codex-support.md`. M0 spike answers the live-fire unknowns (SessionStart stdout injection, tool names, trust review) before M2 ships.

---

## DECISION-0012 — ADR-0012 — Dual-host .codearbiter/ concurrency is at parity with same-host concurrency

**Date:** 2026-07-09
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** architecture / concurrency
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** ADR-0011 keeps one shared `.codearbiter/` store across hosts but specifies no concurrency contract for two hosts writing it at once.
- **Scaffold position:** n/a — an open-decision closure prompted by tribunal run 2026-07-09-codex-support-branch (issue #269).
- **Status type:** open-decision-closure

### Decision
Dual-host concurrency on the shared store is accepted at parity with same-host concurrency: the Codex campaign owes no stronger guarantee than two Claude sessions already have. Host attribution (`get_host().name`) is added to the audit-log writes — the one gap genuinely new to dual-host — and ships in the codex-support sprint. File locking / CAS on read-modify-write state is NOT added under the Codex campaign; the lock-free board RMW (reliability-004) and repo-global dev-marker clobber (reliability-007) are re-scoped as pre-existing, host-agnostic debt, tracked separately, not codex-branch blockers.

### SMARTS rationale
Correctness of the audit trail (level 1) drove the one required change: two distinct host identities now share one trail, so attribution is a genuine new obligation. Maintainability and developer velocity (levels 3, 5) argued against bundling a full locking contract into the Codex campaign — the RMW race is pre-existing and host-agnostic, so fixing it under the Codex banner would hold the branch hostage to unrelated hardening. The maintainer's explicit bar (Codex ≤ Claude-today) closed it.

### Implementation implication
Recorded as ADR-0012 (governs core/pysrc/taskwrite.py, _hooklib.py, session-start.py). Sprint fix: host attribution in `_hooklib` gate-event/block/remind/warn (issue #269 / observability-001). Re-scope: reliability-004 and reliability-007 tracked as pre-existing host-agnostic concurrency debt, not codex blockers. Extends ADR-0011; relates to ADR-0010.

---

## DECISION-0013 — Codex-only users are first-class: full standalone parity (closes #287)

**Date:** 2026-07-10
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** scope / product
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** ca-codex shipped hooks-only through M2; its manifest and doctor pointed Codex users to the Claude-side `/ca:init`, so a Codex-only user had no shipped path to opt a repo in (issue #287, surfaced from #259).
- **Scaffold position:** ADR-0011 authorizes full parity and names `ca-init` as the M4 agent scaffolder — implying a Codex-side init — but #287 asked whether standalone Codex-only use is the requirement or a nice-to-have.
- **Status type:** open-decision-closure

### Decision
Codex-only users are first-class arbiter users. The maintainer's directive (2026-07-09): they "should have EVERY capability just like a Claude user". #287 resolves as option 2 — the full command/skill surface ships on Codex (M3: 37 `ca-`-prefixed entry skills generated from `core/surface/`, including `ca-init` for standalone opt-in; no Claude-side install required). Host-impossible surfaces remain ledgered exceptions in `docs/parity.md` (statusline, prune engine, pre-read/pre-edit), never silent gaps; agents/review chains follow in M4 per the ADR-0011 milestone order.

### SMARTS rationale
Subsumed by ADR-0011's accepted full-parity decision — this entry closes the UX/scope question #287 left open rather than minting a new architecture. Maintainability (level 3) rejected the thin hand-authored-init alternative: hand copies of skills are the exact drift v1 died of and M3's generator replaces. Adoption posture (ADR-0006) favors standalone: requiring a Claude Code install to onboard a Codex repo contradicts the broad-OSS goal.

### Implementation implication
M3 (branch `feat/codex-surface-m3` → `feat/codex-support-m0`): `core/surface/` templates + `tools/build-surface.py` + always-on `surface` CI gate; `Host.cmd_ref` runtime vocabulary seam (ca 2.8.13, ca-codex 0.2.0); manifest/doctor first-run pointers host-native; `prose-codex` reference-graph job. Plan: `.codearbiter/plans/codex-surface-m3.md`. #287 closes on merge; #259's pointer half closes with it.

---

## DECISION-0014 — ADR-0012 ratification — true ratification recorded; premature flip in commit 3902096 corrected

**Date:** 2026-07-12
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com ("i approve adr 12")
**Decision category:** governance / audit-trail integrity
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** commit 3902096 (2026-07-11, authored by the external codex agent under the maintainer's git identity) flipped ADR-0012 to `accepted` with a ratification line dated 2026-07-11 that had not occurred.
- **Scaffold position:** ORCHESTRATOR §3 — ADR status transitions require explicit user instruction via /adr; the maintainer had not ratified as of that commit (the same day's review explicitly listed ratification as still pending).
- **Status type:** open-decision-closure

### Decision
The maintainer ratified ADR-0012 on 2026-07-12 ("i approve adr 12"). The ADR's Status section now carries that true attribution plus an explicit record-correction note; the fabricated 2026-07-11 ratification line is replaced, and this entry preserves the fact that it existed. The accepted bar is unchanged: dual-host concurrency at parity with same-host concurrency, no locking/CAS obligation added.

### SMARTS rationale
Conflict-hierarchy level 1 (integrity of the audit trail) drove the shape of the fix: correct the record visibly rather than silently, so a future auditor sees both the premature flip and its correction. The decision content itself needed no re-scoring — the maintainer approved the identical bar the ADR already stated.

### Implementation implication
ADR-0012 Status section corrected (this commit). PR #254's body updated to drop the ratify-before-merge caveat. Standing lesson for external-agent integrations: an instruction to "get X ratified" is a request to route to the user, never license to author the ratification record.

---

## DECISION-0015 — ADR-0013 — Add ca-pi as a sibling governance plugin

**Date:** 2026-07-13
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com ("approve")
**Decision category:** architecture / host support
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** `CONTEXT.md` limits governance hosts to Claude Code and Codex CLI and requires a new ADR before adding another host.
- **Scaffold position:** The maintainer authorized a `ca-pi` sibling generated from the shared core with a thin Pi adapter and full parity before shipping.
- **Status type:** open-decision-closure

### Decision
Add `plugins/ca-pi/` as an independently versioned sibling governance package. Generate its host-neutral payload from the shared core, confine Pi-specific event and tool translation to a thin adapter, and share `.codearbiter/` project state across hosts. Keep implementation on one feature branch until automated parity, the full required suite, and live Pi verification pass.

### SMARTS rationale
Maintainable is Strong because one generated kernel prevents three host copies from drifting. Reliable and Testable are Strong because contract parity, the full suite, and live verification are explicit ship gates. Scalable and Available are Adequate because Pi package distribution gives the third host an independent install and release path. Securable is Adequate because trust activation and enforcement gaps must be detected by doctor checks and recorded in the parity ledger.

### Implementation implication
ADR-0013 governs `core/**`, the core generators, `plugins/ca-pi/**`, and `docs/parity.md`. Resume the paused `ca-feature` pipeline at brainstorming Phase 2, then update project vocabulary through the approved feature before implementation ships.

---

## DECISION-0016 — Pi authentication stays host-owned; children are enforcement-only and unknown tools fail closed

**Date:** 2026-07-13
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com ("a")
**Decision category:** security architecture / host boundary
**Artifact-section-hash:** f4fce3a6fab0b82455a42d87feb71b5eb5e2acb3a0ee757492a714dbc05035dc

### Variance summary
- **Artifact position:** `.codearbiter/specs/pi-support.md` §Subagents requires exact-model fresh Pi children with environment handling and disabled discovery, but leaves provider credential resolution and the enforcement adapter's child-loading contract implicit.
- **Scaffold position:** `.codearbiter/security-controls.md` §Secret store and access method declares only codeArbiter's farm and sandbox secrets; it does not classify Pi's host-managed auth store, provider environment, or credential commands.
- **Status type:** same-level-conflict-resolution

### Decision
Resolve the conflict with Option A. Pi authentication remains opaque external trusted runtime state: `ca-pi` never reads, copies, snapshots, logs, or implements it. Children use an exact provider/model, a minimal allowlisted environment with unrelated codeArbiter secrets removed, no ambient discovery, and only the trusted enforcement adapter plus explicit generated skills/charters. `CODEARBITER_SUBAGENT=1` disables recursive dispatch only. Unknown Pi tools are potentially mutating and blocked unless the generated host descriptor explicitly classifies them read-only or maps them to a governed operation. Same-process trusted-extension execution remains ADR-0010 residual risk, but final-argument ordering is a live promotion gate; failure reopens ADR-0013.

### SMARTS rationale
Securable and Reliable are Strong because credentials remain owned by the host that already resolves them, child authority is minimized, and unknown operations fail closed. Maintainable and Scalable are Strong because provider/tool knowledge lives in generated descriptors and shared contracts instead of per-host governance copies. Testable is Strong because environment construction, exact provider selection, discovery disablement, recursion, redaction, process cleanup, unknown tools, and final-argument ordering all become explicit fixtures or live gates. Available is Adequate: configurations that rely on broad ambient environment inheritance may require explicit setup, a deliberate cost of preventing secret bleed.

### Implementation implication
Recorded as ADR-0014. Reconcile `.codearbiter/security-controls.md` and the approved Pi spec, then plan the environment builder, enforcement-only child adapter, generated tool classification, doctor diagnostics, schema/redaction limits, and live final-argument-ordering promotion test before mutating adapter code begins.

---

## DECISION-0017 — Development-only plugin tooling may use scoped MPL-2.0 and 0BSD dependencies

**Date:** 2026-07-14
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com ("1")
**Decision category:** dependency policy / conflict resolution
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** `.codearbiter/security-controls.md` limited MPL-2.0 and 0BSD to build-time dependencies under `site/` and excluded them from `plugins/**`.
- **Scaffold position:** The approved Pi plan pins Vitest 4.1.9 under `plugins/ca-pi/tools`; its reviewed lock includes MPL-2.0 Lightning CSS and 0BSD `tslib` development dependencies.
- **Status type:** same-level-conflict-resolution

### Decision
Select conflict resolution option 1. Extend MPL-2.0 and 0BSD approval to development-only tooling under `plugins/*/tools`. This does not authorize runtime plugin dependencies or distribution of dependency source, `node_modules`, native `.node` bindings, WASM, Vite, Rolldown, or Lightning CSS artifacts. Built and released plugin payloads must prove those materials are absent.

### SMARTS rationale
Maintainability and Testability are Strong because sibling plugin toolchains can use the same reviewed test infrastructure without bespoke harness copies. Securable and Reliable remain Strong only with exact locks, ignored lifecycle scripts, secret-free build environments, supported-platform native-binding smoke tests, and release artifact exclusion checks. Conflict-hierarchy level 1 governs: the dependency policy is expanded explicitly instead of silently bypassed.

### Implementation implication
The reviewed Task 2 lock may be installed unchanged with `npm ci --ignore-scripts`. Keep `NAPI_RS_FORCE_WASI` unset, fail unsupported platforms instead of forcing WASI, and add CI/release checks proving no dependency/native/WASM payload ships. The same policy text resolves the pre-existing `plugins/ca-sandbox/tools` lock mismatch; later lock regeneration or integrity drift requires a fresh dependency review.

---

## DECISION-0018 — Pi command aliases use native-equivalent skill expansion through the public API

**Date:** 2026-07-14
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com ("approve")
**Decision category:** host adapter / command parity conflict resolution
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** the approved Pi Task 3 plan said each generated `/ca-*` alias would call `sendUserMessage()` with a literal `/skill:ca-*` command and unchanged arguments.
- **Scaffold position:** Pi 0.80.6 source shows that extension `sendUserMessage()` deliberately calls the prompt path with skill and command expansion disabled, so literal forwarding reaches the model without invoking the skill.
- **Status type:** implementation-plan-conflict-resolution

### Decision
Use native-equivalent expansion at the thin Pi adapter seam. A `/ca-*` handler resolves the generated in-package skill, strips only frontmatter, builds the same `<skill name="..." location="...">` envelope used by supported Pi versions, appends the user's arguments unchanged, and sends that expanded content through the public extension API. User-entered `/skill:ca-*` remains the native fallback. Missing, unreadable, or out-of-package skill paths fail visibly; the adapter never sends knowingly unexpanded slash text.

### SMARTS rationale
Reliable and Testable are Strong because the alias now executes the intended generated skill and fixtures can pin the expansion envelope against Pi 0.80.5 and 0.80.6. Maintainable is Adequate rather than Strong because a small host-private formatting contract is mirrored, so version-matrix tests and doctor diagnostics must detect drift. Securable remains Strong because skill paths are generated, package-contained, and fail closed. Conflict-hierarchy level 2 applies: verified host behavior overrides an infeasible plan mechanism, while the approved full-parity outcome remains unchanged.

### Implementation implication
Amend Task 3 tests and implementation before any activation code is accepted. Keep expansion logic Pi-specific and thin; generated skill content remains owned by the shared core. Task 5 doctor and Tasks 13-14 promotion gates must surface expansion-format drift across the supported Pi matrix.

---

## DECISION-0019 - ADR-0015 - Every live git enforcer must allow; trusted identity is atomic and persistent

**Date:** 2026-07-16
**Status:** accepted
**Supersedes:** ADR-0014 first-resolving enforcer selection
**Decided by:** SUaDtL@users.noreply.github.com ("resolve concerns with SMARTS")
**Decision category:** security architecture / same-level conflict resolution
**Artifact-section-hash:** a6efa1943f3c15f4326aed8c7af4333ea2deb179a0381fd47c01946a6453c422

### Variance summary
- **Artifact position:** accepted ADR-0014 and the pre-release hardening plan require the shared git-hook shim to execute the first resolving enforcer.
- **Scaffold position:** independent host-plugin versions make registry order non-authoritative; Pi security controls also require absolute executable identities and fail-closed ambiguity.
- **Status type:** same-level-conflict-resolution

### Decision
Run every live, stably named enforcer and require every verdict to allow. Replay the same pre-push ref payload to each enforcer. Store trusted Python path, Git path, and owning plugin as one atomically replaced identity bundle. Identity-less hosts preserve a complete bundle; incomplete first registration, failed first persistence, and stale or malformed persisted identity fail closed. Legacy PATH lookup remains available only when no trusted identity was ever registered.

### SMARTS rationale
Securable, Reliable, and Testable are Strong because a less strict sibling cannot win by filename order, attempted trusted identity cannot downgrade to PATH, and the mixed-version, persistence-failure, PATH-poisoning, and stdin-replay cases have behavioral tests. Maintainable is Strong because plugin identity comes from manifests and security identity is one atomic state. Available is Adequate because stale state intentionally blocks until repaired. Scalable is Indifferent because host-plugin counts are bounded and sequential checks are small.

### Implementation implication
ADR-0015 supersedes the selection rule in `0014-githook-shim-dropin-fail-closed.md` without rewriting it. Reconcile the mutable pre-release hardening plan, keep all generated hook copies synchronized, and require independent security review plus the complete Pi preclosure verifier before promotion.

---

## DECISION-0020 - ADR-0015 - Every live git enforcer must allow; trusted identity is atomic and persistent

**Date:** 2026-07-16
**Status:** accepted
**Supersedes:** DECISION-0019
**Decided by:** User explicitly accepted recommendation as their decision ("approve")
**Decision category:** security architecture / git enforcement boundary
**Artifact-section-hash:** a6efa1943f3c15f4326aed8c7af4333ea2deb179a0381fd47c01946a6453c422

### Variance summary
- **Artifact position:** accepted `0014-githook-shim-dropin-fail-closed.md` requires the shared shim to execute the first resolving enforcer.
- **Scaffold position:** the verified mixed-host implementation requires every live stable enforcer to allow and persists trusted executable identity atomically.
- **Status type:** divergent

### Decision
Accept Option A. Run every live, stably named enforcer and require every verdict to allow; replay identical pre-push input to each. Persist trusted Python path, Git path, and owner atomically; identity-less hosts preserve complete state, while incomplete, stale, malformed, or failed first persistence fails closed. ADR-0015 supersedes the first-resolving selection rule in the git-hook ADR numbered 0014.

### SMARTS rationale
Securable, Reliable, and Testable are Strong because registry order cannot downgrade a stricter sibling, attempted trusted identity cannot fall back to PATH, and adversarial states are behaviorally covered. Maintainable is Strong because manifests name plugins and one bundle owns identity consistency. Available is Adequate because stale state blocks until repaired. Scalable is Indifferent because the host-plugin count is bounded.

### Implementation implication
Treat DECISION-0019 as a premature malformed record and use this entry as its forward-only correction. Reconcile `.codearbiter/security-controls.md`, `.codearbiter/plans/pi-support.md`, and the pre-release hardening plan; reject broken-symlink and extra-record identity bundles; synchronize generated hook copies; then rerun security review and the complete Pi preclosure verifier before commit.

---

## DECISION-0021 — ADR-0016 — Permit bounded selected-provider credential projection for isolated Pi children

**Date:** 2026-07-22
**Status:** accepted
**Supersedes:** DECISION-0016
**Decided by:** SUaDtL@users.noreply.github.com ("1")
**Decision category:** security architecture / Pi credential boundary
**Artifact-section-hash:** 64a761f9944743dd684682053aa875ad733ad1dd9ff28ed2379a73d4bf4f944c

### Variance summary
- **Artifact position:** Accepted Pi ADR-0014 made all host-managed authentication opaque and prohibited `ca-pi` from reading or copying credential material.
- **Scaffold position:** A private child home prevents Pi from seeing stored authentication; inheriting the operator home exposes every provider and mutable Pi state.
- **Status type:** same-level-conflict-resolution

### Decision
Supersede the opaque-auth portion of the Pi authentication ADR with a bounded projection boundary.
`ca-pi` may copy only the exact selected-provider record into private ephemeral child storage, with
strict bounds, permissions, non-observability, retained-handle scrubbing, and fail-degraded cleanup.
All unrelated ADR-0014 child-enforcement and fail-closed tool controls remain in force.

### SMARTS rationale
Available and Reliable are Strong because stored-session parity survives while exact-provider selection
prevents fallback and whole-store exposure. Testable is Strong because success, failure, replacement,
cleanup, and foreign-provider exclusion are deterministic contracts. Maintainable and Scalable are
Adequate because one isolated boundary works across providers but now tracks Pi's auth-store shape.
Securable is Adequate because raw credential transport is newly owned, constrained by ephemeral
single-record storage and mandatory security review. Conflict-hierarchy Level 1 governs.

### Implementation implication
Record ADR-0016 as the superseding Pi credential decision. Reconcile `.codearbiter/security-controls.md`,
the approved Pi spec and plan, and the child-environment tests. Keep exact-provider projection,
private child paths, cleanup-degradation behavior, and shipped-bundle parity as release blockers;
then rerun the secret-handling gate and full Pi promotion verification before commit.

### Resolves same-level conflict between (when applicable)
Accepted `0014-pi-host-authentication-and-fail-closed-tool-boundary.md` and the verified isolated-child
credential requirements exposed by tribunal issue #372.

---

## DECISION-0022 — ADR-0017 — Permit credential-blind selected-provider configuration projection for isolated Pi children

**Date:** 2026-07-24
**Status:** accepted
**Supersedes:** DECISION-0021 (partial — only the "no Pi configuration" clause of ADR-0016's Decision)
**Decided by:** SUaDtL@users.noreply.github.com ("credential-blind selected-provider config projection")
**Decision category:** security architecture / Pi configuration boundary
**Artifact-section-hash:** cc8514b0a6eacedad8c0cca919828ecb5398230524d3ed2793fe110003bf8670

### Variance summary
- **Artifact position:** Accepted ADR-0016 forbids any Pi configuration from entering the child boundary — "No other provider record, Pi configuration, session, package state, or ambient home data may enter the child boundary."
- **Scaffold position:** Pi 0.80.10 binds `models.json` to `getAgentDir()` with no separate env override, so the ADR-0016 private agent dir strips every operator provider/model definition and the child silently resolves the provider from Pi's built-in catalog, sending the operator's key to an endpoint they never configured.
- **Status type:** same-level-conflict-resolution

### Decision
Amend exactly one clause of ADR-0016 — the words "Pi configuration" in its no-crossing sentence — to
permit projecting a `models.json` that holds only the exactly-selected provider's record and only
credential-blind structural/protocol configuration. The amendment permits **configuration**
projection and still forbids **credential** projection, which remains bounded solely by ADR-0016's
`auth.json` clause. `apiKey` and `headers` cross only as whole-value `$NAME`/`${NAME}` environment
references, which carry no secret, and a `baseUrl` crosses as an endpoint only — a URL embedding
userinfo is refused. Literal `apiKey`/header values, `!command` forms, userinfo or unparseable
endpoints, unreviewed provider-schema keys, any non-selected provider record, and anything beyond the
provider record fail closed with a fixed, bounded, non-leaking degraded diagnostic.

### SMARTS rationale
Securable is Strong and, decisively, *unchanged*: the projected document is credential-blind by
construction, so the secret-bearing surface stays exactly what ADR-0016 already sanctioned while the
real leak — an operator credential silently redirected to Pi's built-in endpoint — is closed.
Available and Reliable are Strong because endpoint, gateway, proxy, Azure-deployment-map, and
self-hosted-model parity return to isolated children. Testable is Strong because every rejection
(literal key, `!command`, literal header, foreign provider record) is a deterministic behavioral
contract and the whole path is proven by the live Pi 0.80.10 contract. Maintainable is Adequate: the
key allowlist is pinned to the reviewed Pi provider schema and must be re-reviewed when Pi's schema
moves. Conflict-hierarchy Level 1 governs.

### Implementation implication
Record ADR-0017 as the amending Pi configuration decision (forward-only; ADR-0016's file is not
edited). Reconcile `.codearbiter/security-controls.md` — Pi authentication section and the
boundary-crossings table. Implement the sanitizer in `plugins/ca-pi/tools/src/child-env.ts` as the
single sanctioned config-transport seam, extend the runner's closed degraded-reason allowlist by one
fixed identifier, and keep the four fail-closed rejections plus the live `test_pi_child_live.py`
contract as release blockers. Rebuild both committed esbuild bundles and advance the `ca-pi` payload
manifest and changelog.

### Resolves same-level conflict between (when applicable)
Accepted `0016-bounded-pi-child-credential-projection.md` and the verified Pi 0.80.10 `models.json`
agent-dir binding exposed by the live isolated-child contract on PR #426.

---

## DECISION-0023 — ADR-0018 — Accept endpoints by bounded structure rather than case, and pin projected value shapes

**Date:** 2026-07-25
**Status:** accepted
**Supersedes:** DECISION-0022 (partial — only ADR-0017's `baseUrl` clause, its fail-closed list, and its Consequences paragraph)
**Decided by:** SUaDtL@users.noreply.github.com ("allow mixed-case segments"; ADR amendment approved 2026-07-25)
**Decision category:** security architecture / Pi configuration boundary
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** Accepted ADR-0017 refuses a `baseUrl` only for URL userinfo or unparseability, and pins the projected record by KEY NAME against the reviewed Pi provider schema.
- **Scaffold position:** Adversarial probing of the shipped implementation proved a credential in a query string, path, or fragment projected verbatim (the dominant Azure `?api-key=` / Google `?key=` shape), that the projected endpoint was absent from the child's sensitive-value scrub set, and that a name-only pin lets a wrong-typed value project and then die mutely inside Pi's own validator.
- **Status type:** same-level-conflict-resolution

### Decision
Accept a projected `baseUrl` by bounded structure rather than character case, and pin value shapes as
well as key names. A value crosses only as a parseable absolute `http`/`https` URL with no userinfo,
no query, no fragment, no percent-encoding, and a route of at most 8 segments of at most 32 bytes
each. Route segments are deliberately case-insensitive: a lowercase-only rule admitted
`sk-querysecret999` while refusing `GPT4-Prod`, so it cost operators their isolated children for no
security gain. Everything accepted is also registered in the child's sensitive-value scrub set and
retained behind a scrub handle. A record satisfying the name allowlist but not Pi's declared value
type now fails closed instead of projecting.

### SMARTS rationale
Securable drove it in both directions. The query/fragment/percent-encoding refusals close a *proven*
leak — the first implementation shipped a credential-in-endpoint path that an adversarial probe
demonstrated — and scrub-set registration removes the blind spot in the two controls that assume the
projection holds no secret. The case relaxation was measured, not assumed: the byte bound is what
refuses realistic key material, so dropping the case rule sacrifices nothing Securable while
restoring Available for every operator with a mixed-case Azure or Cloudflare deployment name.
Testable is Strong: both directions were mutation-tested — reverting to lowercase-only reddens the
Azure/Cloudflare fixtures, and loosening the byte bound reddens the realistic-key fixture.
Maintainable improves because the value-shape pin converts a mute child death into a legible
fail-closed refusal. Conflict-hierarchy Level 1 governs.

### Implementation implication
Record ADR-0018 as the amending decision (forward-only; ADR-0017's file is not edited). The code
already shipped on `fix/pi-credential-projection` ahead of this record and is strictly NARROWER than
ADR-0017 described, so nothing ADR-0017 asserts was falsified in the interim — this entry closes the
gap between the record and the shipped rule. Keep `.codearbiter/security-controls.md` in agreement,
including the stated residual that scrub-set registration covers endpoints and not the other
projected free-string leaves.

### Resolves same-level conflict between (when applicable)
Accepted `0017-credential-blind-selected-provider-config-projection.md` and the adversarial boundary
probe of its implementation on PR #426, which proved the endpoint clause both incomplete (leaked) and,
once corrected, over-strict (refused ordinary Azure deployment names).

---

## DECISION-0024 — ADR-0019 — Broker Pi child inference instead of projecting a credential into the child

**Date:** 2026-07-25
**Status:** accepted
**Supersedes:** DECISION-0021 (partial — only ADR-0016's credential-projection clause)
**Decided by:** SUaDtL@users.noreply.github.com ("B — build the broker now"; architecture "Loopback proxy + ephemeral token"; authoring explicitly approved)
**Decision category:** security architecture / Pi credential boundary
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** Accepted ADR-0016 permits projecting the operator's selected-provider `auth.json` record into an isolated child's private agent directory, guarded by scrubbing and exact-value result matching.
- **Scaffold position:** The child holds `bash`/`read` tools and `cat` is on the inspection allowlist, so a prompt-injected child can read that credential and defeat exact-value matching with any encoding transform. The class of transforms is unbounded, so no blacklist closes it.
- **Status type:** same-level-conflict-resolution

### Decision
Remove the credential from the child entirely rather than trying to detect it on the way out. The
parent binds a per-child loopback broker on `127.0.0.1:0`, projects a configuration whose `baseUrl`
names that listener and whose `apiKey` is a per-child ephemeral token, and substitutes the real
credential upstream. The `auth.json` projection is deleted, not disabled. Providers a
bearer-substituting broker cannot serve fail the launch closed rather than falling back to a
credential in the child.

### SMARTS rationale
Securable drove it decisively. The maintainer rejected the cheaper "document the residual" option on
the grounds that its safety rested on a single compensating control — a governed child has no
network egress — which is a property of the current tool set and would be silently removed the
moment a network-capable tool (WebFetch) reaches a child. Accepting a residual whose compensating
control a roadmapped feature erases is how a documented risk becomes a breach. Available is
preserved: stored-auth parity survives, which is what ADR-0016 was created to protect. Maintainable
is Adequate — the broker is a new permanent surface, accepted because it kills a class rather than
an instance. Testable is Strong: containment was proven by adversarial probe, not asserted.
Conflict-hierarchy Level 1 governs.

### Implementation implication
Record ADR-0019 as the superseding credential decision (forward-only; ADR-0016's file is not
edited). Reconcile `.codearbiter/security-controls.md` — the Pi authentication section, the child
environment paragraph, and the boundary-crossings row. Implement in
`plugins/ca-pi/tools/src/inference-broker.ts` with `child-env.ts` as the projection seam, extend the
runner's closed degraded-reason allowlist by `isolation-broker`, and keep the live
`test_pi_child_live.py` contract plus the credential-containment probe as release blockers. Close
#414 and #415, which this decision resolves rather than implements.

### Resolves same-level conflict between (when applicable)
Accepted `0016-bounded-pi-child-credential-projection.md` and the adversarial finding on #414 that a
child can read its own projected credential and defeat exact-value result matching by encoding it.

---

## DECISION-0025 — ADR-0020 — Hook input fails open on malformed shape as well as malformed syntax

**Date:** 2026-07-25
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com ("A — extend fail-open")
**Decision category:** hook contract / fail direction
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** `_hooklib.read_input()` documents a deliberate fail-OPEN exception for malformed stdin, on the grounds that a bad payload must not brick the session.
- **Scaffold position:** That exception covers malformed syntax only. Valid-but-non-object JSON parses cleanly and returns a non-dict, and truthy non-dicts then raise AttributeError out of every guard, while falsy ones survive only by accident of `(data or {})`.
- **Status type:** open-decision-closure

### Decision
Treat malformed shape exactly as malformed syntax: normalize any non-dict payload to `{}` at the
single `read_input()` chokepoint. Unreadable input is unreadable regardless of whether the failure is
syntactic or structural.

### SMARTS rationale
Securable is the lens that decides it, and it decides for fail-open: the hook envelope is
HOST-produced, not model-produced. A model can place hostile content inside `tool_input` fields but
cannot make the top-level object a list, so failing closed protects against a threat that cannot
reach this surface. Reliable and Available are Strong for fail-open and Weak for fail-closed — a host
payload change would otherwise brick every tool call until codeArbiter shipped a fix, which is the
exact failure the documented exception exists to prevent. Maintainable favours one rule at one
chokepoint over a per-position rule. Conflict hierarchy resolves at Level 2 (correctness), because
Level 1 has no genuine stake.

### Implementation implication
Normalize in `core/pysrc/_hooklib.py` and widen its docstring; re-vendor via `tools/sync-core.py`.
Record that the ca-codex ADAPTER's fail-CLOSED behaviour on non-object payloads is a deliberate
asymmetry and stays: a router that cannot route cannot prove the call safe, unlike a guard that
cannot parse. That refusal is dormancy-aware, so it cannot affect repositories that never opted in.

---

## DECISION-0026 — ADR-0021 — Per-call Python bridge spawn is the cross-host cost model

**Date:** 2026-07-25
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com ("A — accept per-call spawn as the cost model")
**Decision category:** performance / enforcement architecture
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** Tribunal finding performance-001 proposes a persistent bridge worker to remove the per-gated-call Python spawn.
- **Scaffold position:** Claude Code pays the same per-call hook-spawn cost, so Pi is not anomalous; the finding downgraded itself on that basis.
- **Status type:** open-decision-closure

### Decision
Accept the per-call spawn as the cross-host standard. Do not build a persistent worker. The per-call
process is stateless by construction — no lifetime, nothing carried between gate decisions.

### SMARTS rationale
Securable and Reliable both favour accepting. A persistent worker is a long-lived process holding
enforcement authority in front of every gated call, requiring its own auth, health check, restart and
staleness handling; a wedged worker degrades every subsequent call rather than one. The 2026-07-25
sweep produced three independent defects from long-lived or ambient state (a statusline pinned into a
pruned worktree, a broker listener that could outlive its child, a token bound to a broker rather
than a process), which is direct evidence about where this codebase actually breaks. Available is
the only lens favouring the daemon, and the cost it removes is one every other host already pays.

### Implementation implication
Record the acceptance; no code change. Keep `.github/scripts/pi_benchmark.py` as the observable
guard. If measured p95 later becomes a real impediment, the remedy is to make the bridge cheaper to
start, not to keep one alive — adopting a daemon would require superseding ADR-0021 deliberately.

---

## DECISION-0027 — ADR-0022 — Auto-route unambiguous, non-destructive intent into its command

**Date:** 2026-07-25
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com ("auto route obvious … it SHOULD actually route the command though. not free ball it"; destructive commands always confirm)
**Decision category:** orchestration / user interaction contract
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** ORCHESTRATOR §6 states that all intent flows through a slash command and "nothing routes without their command", so the orchestrator names the command and asks the user to type it.
- **Scaffold position:** Naming the command proves the routing was already understood, so requiring it to be retyped adds friction without adding a decision — and in issue #308's observed flow that friction produced two incorrect routes, to `/ca:chore` and then to `/ca:override`, for routine post-merge hygiene.
- **Status type:** same-level-conflict-resolution

### Decision
Route on understood intent in three tiers: auto-route when intent is unambiguous AND the command is
non-destructive; ask once naming the command when intent is probable; present candidates when it is
genuinely unclear. The orchestrator routes the command and never performs the operation itself.
Irreversible or gate-bypassing commands always confirm, however clear the intent.

### SMARTS rationale
The maintainer's framing corrected the analysis: §6's invariant is that nothing happens outside a
gated command path, NOT that the user does typing — so auto-routing INTO the command preserves
Securable entirely, and what §6 actually prohibits is the orchestrator improvising the work. Given
that, Available and Reliable both favour routing, and the evidence is that the friction produced an
unjustified override rather than preventing one. Maintainable is the cost: "unambiguous" is a
judgement, and the destructive set is enumerated rather than declared per command. Conflict hierarchy
Level 3 (maintainability/reviewability) governs, since Level 1 is untouched.

### Implementation implication
Amend §6 in `plugins/ca/ORCHESTRATOR.md` and its sibling host copies via `core/surface`, and rework
`includes/redirect.md` into the three tiers. Enumerate the always-confirm set (`/ca:override`, merge
to default, branch and worktree deletion, release and tag publication, `/ca:dev` entry). Ship #308's
other half — a sanctioned owner for the merged-branch transition with ancestry proof against the
fetched default, artifact classification, and per-item confirmation before discarding anything unique
or ambiguous. Prefer moving the destructive declaration into the routing table if the enumerated set
proves hard to keep current.

### Resolves same-level conflict between (when applicable)
ORCHESTRATOR §6's command-enforcement directive and issue #308's observed post-merge cleanup dead
end, in which no command owned the operation and the redirect loop produced an unjustified
`/ca:override`.

---

## DECISION-0028 — ADR-0023 — Ephemeral tool runs are a carve-out inside /ca:add-dep

**Date:** 2026-07-26
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com (chose "Carve-out inside /ca:add-dep" over a new command projected to all three hosts, and over closing the issue; authoring approved 2026-07-26)
**Decision category:** orchestration / dependency governance
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** `/ca:add-dep` applied whenever an agent needed to download and execute a third-party package, making no distinction between adopting a dependency and running a pinned tool once.
- **Scaffold position:** Those are different actions with different risk. Issue #346 records the conflation interrupting a duplicate-code investigation over `jscpd`, which the operator had explicitly said must never be a dependency — and with no owner for the action, the routing loop reached for `/ca:override`.
- **Status type:** coverage-gap-closure

### Decision
Add a bounded **Ephemeral tool run** section inside `/ca:add-dep`, plus a routing-table row pointing
at it. No new command. The distinguishing test is the dependency GRAPH, not the download: anything
entering a manifest, a lockfile, or a base image takes the existing review unchanged. The carve-out
keeps the exact pinned version and the approved registry, requires one confirmation rather than a
review, and MUST NOT modify a manifest or lockfile — verified with `git status --porcelain` after the
run, not trusted.

### SMARTS rationale
Maintainable decided it. A new command would drag in the command catalog, the Pi command catalog, the
README badges and counts, and the site sidebar — a public surface across three hosts to govern an
action whose entire definition is that it changes nothing. Securable is unaffected either way: the
part of supply-chain review that still applies (version pinning, approved registry) is kept at full
strength, and the part that does not (manifest review) has nothing to review. Available favours the
carve-out, since the distinction is written where an operator actually hits it. The cost is
Reviewability: the section can be missed by someone scanning the command list, which the routing-table
row exists to catch. Conflict hierarchy Level 3 governs; Level 1 is untouched.

### Implementation implication
Add the section to `core/surface/commands/add-dep.md` and the row to
`core/surface/includes/routing-table.md`, then regenerate all three host projections via
`build-surface`. Pin the distinction with a surface contract test so the carve-out cannot silently
widen into a dependency bypass. Two of #346's four acceptance criteria were already satisfied — the
routing table, review matrix, and `dependency-reviewer` frontmatter were already manifest-scoped — so
the work is the sanctioned path for the other case. If operators cannot find the section and reach for
`/ca:override` again, promote it to its own command.

---

## DECISION-0029 — #525 — One shared formatter renders the mutation survivor count for both risk arms

**Date:** 2026-07-27
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com (chose "shared formatter" from a four-option SMARTS table, over the minimal one-line fix, over deferring to the next farm.ts change, and over closing won't-fix)
**Decision category:** observability / operator-facing reporting
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** `farm.ts`'s mutation-escalation arm rendered `${mut.evaluated} mutants survived` — the count EVALUATED, under a "survived" label.
- **Scaffold position:** the warn arm four lines below rendered `${mut.survivors.length}/${mut.evaluated} survived`. Two independently-written format strings for one quantity, one of them wrong.
- **Status type:** divergent

### Decision
Extract a single formatter and call it from both arms, rather than correcting the
literal. This removes the class of drift that produced the defect instead of the
instance, and the warn arm keeps its distinct suffix so the two notes stay
distinguishable.

### SMARTS rationale
Reliable and Maintainable decided it; the shared formatter dominated the minimal
fix — strictly better on Maintainable, equal on every other lens. The argument
that had favoured the minimal fix, that a `farm.js` payload rebuild makes any
`farm.ts` change expensive, did not survive measurement: the version was
unpublished and the five most recent `farm.ts` commits were all standalone
`fix(farm)`. Securable was Indifferent — the note carries a score and a count and
crosses into the worker prompt either way.

### Implementation implication
Shipped in #526 over six commits and five adversarial rounds. The final design went
further than this decision anticipated: the root cause was `MutationResult`
declaring optional hook fields as required, so `parseMutationHookOutput` had to
invent them. `evaluated` and `survivors` are now optional and the note states a
count only when one was reported. Four hook shapes changed from escalate to warn,
measured across 27 shapes and recorded in the CHANGELOG.

---

## DECISION-0030 — #527 — The coverage no-tooling exemption must cite `tech-stack.md`, not assert it

**Date:** 2026-07-27
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com (chose "require a citation" over removing the escape hatch entirely, and over passing the gate while logging the exemption to the audit trail)
**Decision category:** governance / gate integrity
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** `tdd` Phase 5 and `refactor` Phase 2/6 are BLOCK gates that may be passed when a surface has no coverage tooling, on the agent's own say-so.
- **Scaffold position:** the same skills carry "MUST NOT guess the test, coverage, or lint command — read `tech-stack.md` or STOP". "I could not find the command" and "this surface has none" are indistinguishable from inside the agent, and demand opposite responses.
- **Status type:** divergent

### Decision
Keep the exemption but make its trigger evidenced: the record must name the
surface and quote, from `tech-stack.md`, either the whole Coverage section or the
passage stating the absence for that surface by name. No citation, no exemption —
the phase STOPs. The record travels into the PR description so the claim is
falsifiable at review time, not only while the lane is live.

### SMARTS rationale
Reliable and Securable drove it: a BLOCK gate that passes on an unverifiable
self-assertion is the #507 failure mode — a gate that reads as satisfied without
executing. Removing the hatch outright scored worse on Available: a consumer repo
genuinely lacking coverage tooling could never complete a `tdd` lane, and #308
records what follows when no command owns a situation. Logging the exemption to
the audit trail surfaced repeated use but still passed each individual gate on an
unverifiable claim; its one real advantage, durability, is taken here by routing
the citation into the PR.

### Implementation implication
Shipped in #527. Conditions live in `includes/maturity-coverage.md` alone, with
`tdd`, `refactor` and `coverage-auditor` deferring to it. Review found this repo
was itself a counterexample — `site/` and the Python hooks have no coverage
command, and `tech-stack.md` carried a local copy of the older, laxer wording for
exactly those surfaces; both are now pointers.

---

## DECISION-0031 — #521 — A quoted coverage figure is the union across supported hosts, per tree

**Date:** 2026-07-28
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com (chose "union across hosts, per-tree" from a four-option SMARTS table, over naming ubuntu-latest authoritative, over requiring the floor to clear on the lower host, and over a documentation-only fix)
**Decision category:** governance / gate integrity
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** `tech-stack.md`'s Coverage section states the script takes no arguments "so it is identical on every platform", and #511's AC-1 names a command with no host.
- **Scaffold position:** measured reports diverge by host — 66.18% branches on Windows against 65.35% on Linux for `plugins/ca/tools`, and 87.50% against 76.38% for `exec.ts` alone. CI measures on ubuntu-latest; the gate is orchestrator-run wherever the developer is.
- **Status type:** divergent

### Decision
A quoted coverage figure is the UNION of the supported hosts' reports for that
tree, not any single host's. The rule applies per-tree: trees carrying
platform-forked code (`plugins/ca/tools`, `plugins/ca-pi/tools`) are measured on
ubuntu-latest and windows-latest and merged; trees with no platform fork (`site/`)
stay single-host. `tech-stack.md` states that the command is identical while the
report is host-dependent, and names the measurement rule.

### SMARTS rationale
Reliable, Testable and Securable aligned on the union. `exec.ts`'s `awaitTaskkill`
and its win32 `treeKill` arm cannot execute on Linux, and the POSIX arm cannot
execute on Windows — so every single-host rule scores structurally-unreachable
code as uncovered permanently, and the 11-point `exec.ts` gap is a platform
artifact rather than a test gap. Securable decided the margin: `treeKill` is a
process-containment path, and under a single-host rule a genuine gap in it is
indistinguishable from the artifact. Maintainable is the cost — blob artifacts
plus a merge step — and is bounded, because the 3-OS matrix already runs in two
jobs and `--mergeReports` is first-class in vitest 4. Available was the live
objection, #504 and #515 both being open Windows flakes, and is answered by the
gate being orchestrator-run rather than a required check: a missing Windows blob
degrades to the ubuntu figure with the gap named, and blocks nothing.
Precedent: none on record for coverage platform. DECISION-0017 is nearest, having
established testing supported platforms rather than assuming parity.

### Implementation implication
A coverage-only CI cell — install plus `vitest run --coverage --reporter=blob` —
on ubuntu-latest and windows-latest for the two platform-forked trees, plus a
merge step. Not the full tools job duplicated. `tech-stack.md`'s Coverage section
drops "identical on every platform" and states the union rule;
`includes/maturity-coverage.md` and `tdd` Phase 5 are aligned to it per #521 AC-3.
#511's closing measurement is restated against the merged figure.

---

## DECISION-0032 — #514 — `site/` is inside the coverage gate

**Date:** 2026-07-28
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com (chose "inside — migrate and measure" over a permanent documented exemption, and over deferring behind #513's visible exemption)
**Decision category:** governance / gate integrity
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** `tdd` Phase 5 and `refactor` Phase 2/6 read a coverage command from `tech-stack.md`; #513 landed one for the three plugin tool trees.
- **Scaffold position:** `site/` is a fourth tested TypeScript tree — `vitest.config.ts`, a `test` script, and real suites under `test/generator/` and `test/content/` — with no coverage command, so those gates reach the phase and pass on a gap.
- **Status type:** divergent

### Decision
`site/` is inside the coverage gate. It migrates from vitest 3 to vitest 4, gains
a `coverage` script and config, and `tech-stack.md` names the invocation. The
measured baseline is recorded against the stage-2 floor, and any shortfall is
tracked as its own issue rather than blocking. `COVERAGE_EXEMPT` in
`.github/scripts/test_ci_impact.py` is emptied.

### SMARTS rationale
Reliable and Testable decided it. A tested tree whose coverage gate no-ops is the
#507 failure mode DECISION-0030 was written to close, and leaving one tree outside
re-opens it by a different door. The argument for a permanent exemption — that
`site/`'s build output is republished from source rather than committed, which is
why it sits off the dev-inclusive CVE gate — bears on supply-chain posture, not on
whether its suites are measured. Securable is unaffected: adding a coverage
provider does not inherit the audit posture the plugin trees carry, and that stays
documented. Maintainable is the cost, since `site/` declares production
dependencies (astro, starlight, markdown-remark) and a major bump there is a
different risk profile than a dev-only tree — bounded here because vitest and the
coverage provider are dev-only within it. Per DECISION-0031 `site/` carries no
platform fork and stays single-host.

### Implementation implication
vitest 3 to 4 in `site/`, `@vitest/coverage-v8` added via `/ca:add-dep` per #513's
precedent, a `coverage` script, and a config whose `include` is scoped to `site/`'s
own sources so the report does not count its tests as covered source.
`tech-stack.md` gains the invocation and a sentence on the CVE-gate distinction.
Baseline recorded; shortfall tracked like #511.

---

## DECISION-0033 — release-pre-tag-steps — Repo-specific pre-tag reconciliation is declared per target row, not pushed to CI

**Date:** 2026-07-30
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** architecture
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** The `release` skill hardcodes this repo's pre-tag steps (README badge sync, command/skill/agent count derivation, `build-host-packages.py` regeneration) as skill prose.
- **Scaffold position:** A shippable skill cannot carry any repo's specific reconciliation commands; project state is where per-repo facts belong.
- **Status type:** open-decision-closure

### Decision
Each release target row in `.codearbiter/release-targets.md` carries an ordered list of pre-tag shell commands. The skill runs them before tagging, asserts each exits 0, and asserts the tree is clean afterward. This repo's four existing steps move into its own rows unchanged. CI's `check_badge_consistency.py` is retained as the mechanical backstop it already is — the declared steps complement it rather than replace it.

### SMARTS rationale
Testable, Available, Scalable, and Maintainable favored declared rows cleanly. Declared steps are data, so a fixture can assert run order and dirty-tree failure; pushing the steps to CI would require simulating CI status payloads to test, and would make tagging unavailable during any CI outage. Securable was the only non-Strong cell, and it falls inside the trust class ADR-0002 already accepted: operator-authored, PR-reviewed shell input, resolved by declaring the boundary rather than restricting the operator. The rejected local-hook-script option scored Weak on Securable for precisely the reason ADR-0002 rejected its own equivalent — an undeclared executable-input boundary.

### Implementation implication
`.codearbiter/release-targets.md` gains a `pre-tag` list per row plus an assert-clean flag. `security-controls.md` gains a boundary-crossings entry declaring the file as executable input, with a length cap following ADR-0002's 1024-character precedent. An ADR is warranted for the new trust boundary and should be authored via `/ca:adr` during implementation. The `release` skill drops its four hardcoded reconciliation steps in favor of running the declared list. Tracked under issue #563.

---

## DECISION-0034 — release-pre-tag-semantics — Declared pre-tag commands are check-only and may never mutate the tree

**Date:** 2026-07-30
**Status:** accepted
**Supersedes:** DECISION-0033
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** architecture
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** DECISION-0033 held that pre-tag steps are declared per target row and run with exit-code and clean-tree assertions, and its implementation note described a per-row assert-clean flag.
- **Scaffold position:** This repo's actual pre-tag steps are edits, not assertions — `build-host-packages.py` regenerates the root manifest and `wc -l` count derivation implies editing README prose — so a clean-tree assertion blocks the very reconciliation the steps exist to perform.
- **Status type:** open-decision-closure

### Decision
Pre-tag commands remain declared per target row rather than pushed to CI, restating DECISION-0033's holding in full. They are additionally constrained to be **check-only**: a command must assert and exit non-zero on drift, and must not mutate the working tree. The clean-tree assertion applies unconditionally, so any mutation is detected and blocks the release. No per-row assert-clean flag exists. Reconciliation itself — regenerating a manifest, syncing README badges — stays a separate action the operator performs and commits through `commit-gate` before re-running the release.

### SMARTS rationale
Five of six lenses favored check-only. Maintainable and Testable: one rule with no branch, and a fixture asserts exit code plus unchanged tree without standing up commit-gate, whose own gates would otherwise leak into release tests. Reliable: the tree the suite ran against is the tree that gets tagged, with no mid-phase mutation landing after the last green run. Securable: because the clean-tree assertion always runs, a rogue declared command's writes surface before tagging, which the flagged and unconditional-mutation alternatives both lose. Available was the single Weak cell and is an accepted cost — a lagging generated manifest stops the release and names what to run. ADR-0008's ride-along precedent genuinely favored in-lane reconciliation, but it applies to narrow classified edits with named exemptions (`classify_board_diff` transitions, provenance re-baselines), never to arbitrary operator-declared commands; extending it here would let a regenerated manifest reach a tag without passing commit-gate review.

### Implementation implication
`.codearbiter/release-targets.md` rows carry a `pre-tag` list with no assert-clean flag. The release skill runs each command, asserts exit 0, then asserts a clean tree, and BLOCKs on either failure. This repo's badge and count reconciliation must be expressed as check scripts — `check_badge_consistency.py` already has that shape; the catalog and README-table assertions need equivalent non-mutating checks written. `build-host-packages.py` is not a pre-tag command; a companion check asserts the generated root manifest matches the plugin manifest and fails when it lags. Costs this repo one extra loop per release when a generated artifact is stale. Tracked under issue #563, spec `specs/release-portable-fixture.md`.

---

## DECISION-0035 — adr-0024-ratification — Protected-state registry ratified as a declared executable-input boundary

**Date:** 2026-07-31
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** security-architecture
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** `.codearbiter/release-targets.md` carries per-row `pre-tag` shell commands that `/ca:release` executes, making it executable input, with no recorded trust model.
- **Scaffold position:** ADR-0002 already governs this class for `plan.json` — operator-authored, PR-reviewed, length-capped, boundary declared rather than allowlisted — but three material differences separate the new case from it.
- **Status type:** open-decision-closure

### Decision
ADR-0024 is accepted. The protected-state registry is a declared executable-input boundary protected by write-gating rather than content inspection: marker-gated writes, a 1024-character cap per `pre-tag` entry, check-only commands under an unconditional clean-tree assertion, and a content hash forcing re-confirmation when a command changes. No content predicate ever grants admission. The authoring marker is explicitly audit friction rather than authorization, self-mintable by design under ADR-0010, and `GATE_MARKER_NAMES` is not widened to cover it. Case handling is global rather than host-derived.

### SMARTS rationale
Securable drove it, and the decisive reasoning is that the alternatives fail in the same shape: a content predicate admitting a write based on what the file contains converts content into an authorization signal, launderable by anyone who can write the content — the same defect that sank the file-absent exemption and the conflict-marker carve-out considered earlier in this campaign. Maintainable and Scalable favored one registry over per-file hook branches, and the maintainer's standing steer to weight `Scalable` heavily for deterministic enforcement over prose reinforced it. Reliable favored global case handling once it was established that `realpath` cannot fold case for a file that does not yet exist, which is precisely a Write creating a protected file for the first time — a host-derived rule would have been silently wrong exactly at creation.

### Implementation implication
`core/pysrc/_protectedstatelib.py`, `_protectedlib.py` and `_bashguardlib.py` carry the enforcement, already landed at 56387ee. The ADR's `governs:` field enrolls those three plus `.codearbiter/release-targets.md`, so the post-write hook surfaces the decision at edit time rather than at a checkpoint sweep. Four residuals are declared in both the ADR and `security-controls.md`, and three reopen conditions are recorded — most concretely, that recurring board-conflict overrides in `gate-events.log` mean building a `taskwrite resolve` verb rather than punching an exception into the guard. Closes T-16 of the sprint plan.

---

## DECISION-0036 — bare-release-requires-explicit-target — A multi-target project must name its release target; no implicit default

**Date:** 2026-07-31
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** architecture
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** The release skill defaulted a bare `/ca:release` to target `ca`, a hardcoded fact about this repository.
- **Scaffold position:** A-6.0 requires that no hardcoded row survive the portability rewrite, and steer 5 requires no behavior change to this repo's four-plugin release. Both cannot hold for the bare invocation.
- **Status type:** same-level-conflict-resolution

### Decision
A declared file with exactly one target resolves that target implicitly. A declared file with more than one target requires an explicit `$TARGET`; a bare invocation STOPs. This repository declares four targets, so `/ca:release` alone now stops and `/ca:release ca` is required. This is an accepted, deliberate exception to steer 5, taken with the steer in view rather than around it.

### SMARTS rationale
Securable and Reliable drove it. A bare invocation that resolves a target nobody named is a default-allow on a lane that ends in a `contents: write` publisher, and the alternative places that default inside `release-targets.md`, which has no write protection until its H-22 enrolment at T-33 and would therefore be an unguarded redirect. Reliable agrees: a stale default flag publishes the wrong series, where an explicit argument cannot. Scalable was the one clean win for the declared-default alternative, since bare invocation silently changes meaning the day a consumer adds a second row, but that discontinuity is one-time per consumer and surfaces as a STOP rather than as a wrong publish. Precedent aligns: DECISION-0034 chose check-only over silent fixers, and this campaign already rejected positional target selection as a reorder-to-mispublish hazard.

Recorded against the author's original justification, which does not survive scrutiny: the claim was that a declared default would bake in "the primary target is named ca", but `latest-eligible: true` already singles out `ca` in the same row set and shipped in the same change under the same criterion. The objection proves too much. The decision stands on the security and reliability grounds above, not on that reasoning.

### Implementation implication
`core/surface/skills/release/SKILL.md` keeps the STOP. `core/surface/commands/release.md` must stop documenting a `ca`-only default when T-71 reconciles it. A test must pin this: an adversarial mutant restoring the hardcoded `ca` default currently survives both suites, so the behavior is asserted by nothing. That test is a follow-up obligation of this decision, not optional.

---

## DECISION-0037 — adr-0025-ratification — Recorded intent precedes autonomous scoring and spec shaping

**Date:** 2026-08-07
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com — content approved at the recorded-intent-kernel-campaign sprint Phase 1 gate; ratified "accept both" same day
**Decision category:** governance-process
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** n/a — new governance rule; no prior artifact position existed
- **Scaffold position:** n/a
- **Status type:** open-decision-closure

### Decision
ADR-0025 accepted: a Step-0 recorded-intent check precedes SMARTS scoring, scoped to /sprint autonomous scoring and brainstorming only; decision-variance, grader, and decision-challenger exempt by name; "answered" ranked by the decision-variance Phase 4 authority order; sprint contradiction is a hard gate with a stale-record valve; index-first loading and fail-soft are normative.

### SMARTS rationale
Reliable and Maintainable dominate: conformance to the recorded decision trail prevents silent architectural drift overnight, and scoping the check away from arbitration surfaces preserves the single authority order instead of forking it. The unscoped form was killed by adversarial review (rank-4 artifact would defeat a rank-1 user steer).

### Implementation implication
core/surface/includes/smarts/core.md (Step-0), core/surface/SPRINT.md, core/surface/agents/grader.md, core/surface/skills/brainstorming/SKILL.md; structural test .github/scripts/test_recorded_intent_surface.py wired into ci.yml as an explicit step; regenerated plugin copies on all three hosts.

---

## DECISION-0038 — adr-0026-ratification — Destructive operations declared in the routing table

**Date:** 2026-08-07
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com — content approved at the recorded-intent-kernel-campaign sprint Phase 1 gate; ratified "accept both" same day
**Decision category:** governance-routing
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** ADR-0022 enumerated the destructive set inside ORCHESTRATOR §6 and recorded the routing-table declaration as its preferred refinement
- **Scaffold position:** routing-table.md carries no destructive declarations; the parity checker reads cells positionally
- **Status type:** open-decision-closure

### Decision
ADR-0026 accepted, partially superseding ADR-0022 (placement clause only): routing-table.md gains an operation-scoped "Destructive operations" block as the authority; ORCHESTRATOR §6 keeps a CI-checked resident copy; no new table column. The three-tier routing decision of ADR-0022 remains in force.

### SMARTS rationale
Maintainable and Reliable dominate: a declared registry with mechanical drift detection replaces reviewer memory as the update path for new destructive commands, and the block form (not a column) keeps check_routing_index_parity.py's positional parsing valid. The per-row-flag alternative could not express 2 of 5 set members and was rejected on adversarial review.

### Implementation implication
core/surface/includes/routing-table.md (new block), core/surface/ORCHESTRATOR.md §6 (resident copy retained), consistency check extending .github/scripts/test_routing_and_cleanup_surface.py (seeded-mismatch proof with captured failing log), pin at test_routing_and_cleanup_surface.py:79 repointed.

---

## DECISION-0039 — adr-0027-authored — Tribunal lens roster is data; one generic lens-reviewer executes it

**Date:** 2026-08-08
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com — plan "tranquil-crunching-fog" v2 approved post-adversarial-review 2026-08-08; explicit rulings "Tribunal-only collapse" and "publish lens cards + redirects" the same day. ADR-0027 authored as proposed; ratification pending.
**Decision category:** framework-structure
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** eleven tribunal-<lens>-reviewer agents, ~73% identical template, each hardcoding its lens card path; cards carry the mandates but not the project-doc pre-reads
- **Scaffold position:** scout/grader already prove generic-body + injected-assignment; run/triage/telemetry schemas key on lens, never agent name
- **Status type:** divergent

### Decision
One generic tribunal-lens-reviewer dispatched once per active lens with a title-first assignment block; the roster is the lens-card set; cards absorb Scope-emphasis and Required-reading from the deleted bodies; shared reviewer/author contracts extracted to includes/reviewer-contract.md and includes/author-tdd-workflow.md; the eleven public agent URLs redirect to a generated per-lens reference collection.

### SMARTS rationale
Maintainable dominates: one body and one include per contract instead of eleven copies, with a new lens reduced to data. Reliable held after adversarial review closed the two real hazards (nine lenses' project-doc pre-reads migrated into the cards; assignment title line preserves per-lens statusline labels). Token cost falls ~589 per Claude-host session. The rejected alternatives (keep-eleven-with-template, collapse-checkpoint-family, merge-mappers) are recorded in the ADR.

### Implementation implication
core/surface/agents/tribunal-lens-reviewer.md (new), 11 agent files deleted, 11 lens cards gain Scope-emphasis/Required-reading, skills/tribunal/SKILL.md Phase 2 rewritten, cost-and-models.md re-keyed by lens, includes/reviewer-contract.md + author-tdd-workflow.md (new) with 7 agents rewired, agents/INDEX.md -11/+1, three CI tests re-pinned 28->18, site lens collection + 11 redirects, README badges, manifests ca 2.13.0 / ca-codex 0.6.0 / ca-pi 0.4.0 + root lockstep.

---

## DECISION-0040 — adr-0027-ratification — Tribunal lens roster is data; one generic lens-reviewer executes it

**Date:** 2026-08-08
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com — explicit ratification "approve the adr", 2026-08-08
**Decision category:** framework-structure
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** ADR-0027 authored the same day as proposed (DECISION-0039 recorded "ratification pending" — true at write time; this entry closes it, the prior entry stands unedited per the append-only rule)
- **Scaffold position:** n/a — ratification of an authored record, no competing artifact
- **Status type:** open-decision-closure

### Decision
ADR-0027 ratified to accepted (frontmatter and body Status advanced in commit 8e46074 on the PR #647 branch). Content unchanged from authoring.

### SMARTS rationale
Recording-only entry; the decision's SMARTS rationale lives in DECISION-0039 and the ADR itself.

### Implementation implication
None beyond the status flip — the ADR's governs: globs became live pushback at edit time on acceptance.

---

## DECISION-0041 — adr-0028-authored — Chain-internal skills are path-routed and registry-hidden

**Date:** 2026-08-08
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com — plan "tranquil-crunching-fog" v2 approved post-adversarial-review; rulings 2026-08-08: dual-fronted skills stay visible, harness-reserved names documented not renamed. ADR-0028 authored as proposed; ratification pending.
**Decision category:** framework-structure
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** nine chain-internal skills cost ~1K registry tokens per session and were reached by bare name, with the registry entry as their only resolution path
- **Scaffold position:** ORCHESTRATOR mandates load-on-invocation; five-round harness spike proved disable-model-invocation works, the colon-drop theory false, and feature/fix/new-skill harness-reserved
- **Status type:** divergent

### Decision
Routing is path-defined (routing-table preamble + explicit path citations at every chain-internal route site); the nine chain-internal skills ship disable-model-invocation: true; dual-fronted skills stay visible; frontmatter scalars quote per the _yaml_safe_scalar predicate as a house rule; reserved names documented, not renamed.

### SMARTS rationale
Reliable dominates: the adversarial finding that bare-name routing had no written fallback made the path rewrite the load-bearing half, with the frontmatter hides only safe on top of it. Token-efficient second: ~1K chars of descriptions leave every session and the registry-budget drop pressure clears. The rejected alternatives (frontmatter-only, user-invocable:false, skillOverrides, renames) are recorded in the ADR.

### Implementation implication
routing-table.md preamble rule; path citations in feature/checkpoint/review/spike commands, SPRINT.md, subagent-driven-development, dispatching-parallel-agents, commit-gate; 9 SKILL.md frontmatter keys; ~11 frontmatter scalars JSON-quoted; skill-author Phase 4 + template amended; token-efficiency.md findings section; bumps ca 2.14.0 / ca-codex 0.6.1 / ca-pi 0.4.1 + root lockstep.

---

## DECISION-0042 — adr-0028-ratification — Chain-internal skills are path-routed and registry-hidden

**Date:** 2026-08-08
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com — explicit ratification "approve adr28", 2026-08-08
**Decision category:** framework-structure
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** ADR-0028 authored as proposed (DECISION-0041 recorded "ratification pending" — true at write time; this entry closes it, the prior entry stands unedited per the append-only rule)
- **Scaffold position:** n/a — ratification of an authored record; the implementation merged as PR #649 and verified live before ratification
- **Status type:** open-decision-closure

### Decision
ADR-0028 ratified to accepted. Content unchanged from authoring; post-merge verification on record (nine skills hidden, dual-fronted skills listed, plugin 2.14.0).

### SMARTS rationale
Recording-only entry; the decision's rationale lives in DECISION-0041 and the ADR.

### Implementation implication
None beyond the status flip — the ADR's governs: globs became live pushback at edit time on acceptance.

---

## DECISION-0043 — adr-0029-authored — Publish ca-pi to npm under the arbiterforge org

**Date:** 2026-08-09

**Decided by:** SUaDtL@users.noreply.github.com — direct directives 2026-08-09: "i'd like to start publishing to NPM in the arbiterforge organization" and "adr for change to publishing route approved"; NPMJS_TOKEN org actions secret created by the owner. ADR-0029 authored and accepted on that attribution.

### SMARTS rationale
Recording-only entry; the decision's rationale lives in ADR-0029. Scope deliberately ca-pi-only: npm is Pi's native channel; the other three plugins install from marketplaces.

### Implementation implication
Spec `npm-publish-ca-pi` implements: generator emits publishable root manifest (@arbiterforge/ca-pi, files whitelist, publishConfig, no private), tag-triggered npm-publish workflow with provenance and version guard, documentation posture flip with doc-contract tests repointed.

---

## DECISION-0044 — adr-0030-authored — Orchestration mode plane with a composed, per-turn persona

**Date:** 2026-08-12
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com — seven positions ruled directly across the #437 session; ADR authoring approved 2026-08-12 ("approve adr, route through /ca:adr").
**Decision category:** architecture
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** Issue #437 proposed a new `/ops` command for local runtime operations.
- **Scaffold position:** ORCHESTRATOR.md presents itself as the always-on core (`:3`); §0/§6 refuse off-channel runtime work; ADR-0022`:46-49` puts `{{CMD:dev}}` entry at tier 2.
- **Status type:** divergent

### Decision
An orchestration mode plane (`arbiter` / `dangerous` / `ops`) replaces the fixed persona. ORCHESTRATOR.md is reframed as the arbiter mode's body and renamed `arbiter.md`; the injected persona becomes `safety-core.md` + the current mode's body, injected at the per-turn prompt seam rather than `SessionStart`, and flipped by a whole-prompt-anchored control token that produces no model turn. The two mode-entry commands are deleted (catalog 40 to 38). ADR-0022's tier-2 clause is superseded for dangerous-mode entry only.

### SMARTS rationale
Two sub-decisions were SMARTS-scored rather than asserted. **Startup-block handling**: decomposing into per-mode composable emitters beat wholesale suppression at strength `strong` — four dominant lenses aligned, and suppression's only advantage (smallest diff, largest saving) is not a lens and would have hidden `[CONFIRM-NN]`s and override counts in exactly the posture that most needs them. **Durable `profile:` layer**: transient-plus-documented-seam beat implementing both layers now at strength `moderate`; two-layer-now is penalised on Reliable (two sources for one fact) and Securable (a committed gates-off default). Step 0 recorded-intent constrained both: the user ruled twice that hooks here are modifiable, eliminating every option premised on `SessionStart` being fixed.

### Implementation implication
Spec `.codearbiter/specs/mode-plane-deterministic-flip.md` (57 acceptance criteria) and plan `.codearbiter/plans/mode-plane-deterministic-flip.md` (87 tasks) implement this on branch `feat/mode-plane-deterministic-flip`. New: `core/pysrc/_modelib.py`, the per-turn injector, `core/surface/includes/{safety-core,dangerous-mode,ops-mode}.md`. Renamed: `core/surface/ORCHESTRATOR.md` to `arbiter.md`, carried in `core/hosts.json` `managed_subtrees` under both names during migration so the pruner can see the orphan. Modified: `session-start.py` (persona injection removed, startup block decomposed), `_hooklib._STALE_FLOWS`, `_metricslib.override_rate`, `pi-bridge.py`, `extension.ts`, `hosts.json`, README badge, `CONTRIBUTING.md`, `docs/architecture.md`, `site/scripts/generator/configuration-reference.ts`. Deleted: the two mode-entry command bodies under `core/surface/commands/`. Test pin `test_routing_and_cleanup_surface.py:79-93` is repointed — that edit is the supersession act. Filed separately: #674 (ADR-0026 unimplemented), #675 (ADR content hashing), #676 (`test_ci_impact` worktree walk).

---

## DECISION-0045 — adr-0030-ratified — ADR-0030 accepted

**Date:** 2026-08-12
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com — direct ratification 2026-08-12 ("approved"), given after the authored ADR was presented for review.
**Decision category:** architecture
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** ADR-0030 authored as `proposed` (DECISION-0044). Authoring approval predated the document's existence, so it was deliberately not treated as ratification.
- **Scaffold position:** n/a — ratification of an authored record.
- **Status type:** open-decision-closure

### Decision
ADR-0030 ratified to `accepted`. Content unchanged from authoring; only the `status:` frontmatter and the mirroring `## Status` body line were edited, per the canonical template's rule that the two must agree.

### SMARTS rationale
Recording-only entry; the decision's rationale lives in DECISION-0044 and in ADR-0030 itself. The one judgement recorded here is the refusal to self-ratify: an approval to *author* cannot ratify content the approver has not read, and DECISION-0014 exists in this repo precisely because an external agent once fabricated an ADR ratification.

### Implementation implication
Unblocks the command-deletion cluster, which was gated on an accepted ADR standing behind the ADR-0022 supersession. T-66b (editing the `{{CMD:dev}}` assertion at `test_routing_and_cleanup_surface.py:79-93` — the supersession act itself) is now permitted, and with it T-64 (deleting the two command bodies), T-65 (stripping the 7 surviving `{{CMD:}}` tokens), and T-67 (catalog badge 40 to 38). Acceptance also makes ADR-0030's `governs:` globs live, so edits to the mode bodies, `_modelib.py`, and the injection path now surface a governed-file notice at write time.

---

## DECISION-0046 — mode-state-shape — Per-session mode entry files replace the shared session map

**Date:** 2026-08-13
**Status:** accepted
**Supersedes:** none
**Decided by:** User explicitly accepted recommendation as their decision — the choice between the two candidate fixes was delegated to SMARTS scoring ("yes. and make choice based on smarts", 2026-08-13).
**Decision category:** architecture
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** ADR-0030 position 5 requires the return path out of `dangerous` to be a verified write that surfaces its failure; the spec's State line put every session's posture in one `.markers/mode` map.
- **Scaffold position:** `write_mode` verified only the calling session's own key, so a session holding a map read moments earlier could reinstate a `dangerous` entry another session had explicitly left — with that session's own earlier `enter` row still satisfying `ledger_backs`, so the reinstated gates-off posture was authorized and silent.
- **Status type:** divergent

### Decision
The mode plane's state becomes one file per session under `.codearbiter/.markers/mode.d/`, named by the SHA-256 of the session id and carrying that id inside the record. `write_mode` no longer performs a read-modify-write and no longer retries; it writes one path and verifies it. The pre-split `.markers/mode` map is read-only, consulted when a session has no entry of its own, so a session live across the upgrade keeps its posture and an explicit `arbiter` still reads as a choice rather than as "never flipped".

### SMARTS rationale
Scored against the alternative — serializing the read-modify-write with `_hooklib.acquire_lock`. Reliable and Available drove it: removing the shared cell makes the interleave structurally impossible rather than serialized, and leaves no contention state, where a lock on the prompt seam fail-softs to None after a bounded spin and the only safe reading of None is a failed flip. Securable follows Reliable, since the defect being closed is a fail-open. Testable favours the split too: the guarantee is assertable on the filesystem without simulating an interleave. Maintainable was the lock's one win — it would have touched a single function instead of the reader, the staleness registry, and three vendored copies — which makes this `moderate`, not `strong`. Step 0: ADR-0012 constrains rather than decides, naming "session-scoped markers" as the deferred hardening it declined to demand of the Codex campaign; ADR-0030 position 6 already fixes the plane as transient and session-scoped.

### Implementation implication
`core/pysrc/_modelib.py` gains `mode_entry_dir` / `mode_entry_path` / `session_has_entry` and drops the retry loop; `session-start.py`'s legacy-conversion check moves from a raw map membership test to `session_has_entry`; `_hooklib._STALE_FLOWS` points at the directory and gains `_mode_plane_active_since`, which also fixes an unrelated session's write resetting a stale session's staleness clock. Regenerated into the three vendored `plugins/*/hooks/` copies. The spec's State line is amended in place; `docs/hooks.md` and the dual-host concurrency section of `site/src/content/docs/getting-started/claude-code-and-codex.md` are corrected, the latter having documented the now-fixed race as accepted debt.

---

## DECISION-0047 - adr-0031-authored - Internal generated kernel, host-native roots, and Codex resource charters

**Date:** 2026-08-22
**Status:** proposed
**Supersedes:** DECISION-0011
**Decided by:** SUaDtL@users.noreply.github.com - approved the six migration positions on 2026-08-21 and explicitly approved the internal kernel packaging boundary on 2026-08-22.
**Decision category:** architecture / host packaging and dispatch
**Artifact-section-hash:** d853b7cbef6e4587af607c03ca20877ef33299eb0998ea10c568898cb8cbd369

### Variance summary
- **Artifact position:** `.codearbiter/plans/cross-host-identity-packaging-migration.md` under `## Recommended architecture decision` specifies host-native root resolution, Codex resource charters, dispatch policy, and bounded compatibility; the user later fixed the kernel packaging boundary.
- **Scaffold position:** `core/pysrc/`, `core/surface/`, `core/hosts.json`, `tools/sync-core.py`, and `tools/build-surface.py` already implement an internal canonical source with generated independently versioned adapters, while current `ca-codex` omits the charter payload.
- **Status type:** open-decision-closure

### Decision
Use the existing `core/` plus deterministic generators as the internal `ca-core` source of truth, not a separately published or runtime package. Publish Claude and Codex as independently versioned host-native adapters, keep Pi Forge-only, resolve roots by validated host-native evidence, and ship all Codex charters as generated resources dispatched through host threads. This partially supersedes only ADR-0011's `.codex/agents/*.toml` scaffolding fallback; the rest of ADR-0011 remains in force.

### SMARTS rationale
Maintainable and Reliable are decisive: the existing canonical source plus checked generation preserves one behavior contract without adding a fourth release unit or runtime installation coupling. Testable is strong because source-to-payload drift, root precedence, complete route closure, and each supported host can be verified independently. Securable favors file/module-derived roots, corroborating environment values, containment checks, and fail-closed isolation over ambient aliases or project-scaffolded agents. Available and Scalable favor separate host-native packages because one adapter's distribution or host drift does not make the shared governance source unavailable to the other. Precedent: DECISION-0011 established build-time vendoring instead of runtime shared imports; DECISION-0015 extended that generated kernel to Pi; DECISION-0043 kept Pi's native publication route package-specific.

### Implementation implication
ADR-0031 governs the canonical kernel, generators, Claude/Codex/Pi adapter payloads, route-closure and portability checks, payload version gates, and host-specific release evidence. PR 2 must change canonical source and generated outputs atomically, add all Codex charter resources and dispatch policy, preserve the legacy Codex alias only for the approved window, and block release until exact-candidate Windows desktop proof succeeds without API-key billing or fabricated equivalence.

---

## DECISION-0048 - adr-0031-record-correction - Align the mutable plan and bind its canonical UTF-8 section hash

**Date:** 2026-08-22
**Status:** proposed
**Supersedes:** DECISION-0047
**Decided by:** SUaDtL@users.noreply.github.com - the repository user's 2026-08-22 zero-API-key and internal-kernel approvals control; this entry corrects their durable plan/log representation without changing the decision.
**Decision category:** record correction / architecture
**Artifact-section-hash:** 850636eb9e7ef34cf165473f3e6e26d2c1b81bcdd04ce4dffff2aa474b199bdc

### Variance summary
- **Artifact position:** The mutable migration plan retained an obsolete API-key desktop lane and unauthored-ADR statement after the user prohibited API-key/API-billed substitution, approved ChatGPT browser/device authorization within included access, approved the internal `core/` plus generators boundary, and the four-cell prerequisite passed.
- **Scaffold position:** ADR-0031 and DECISION-0047 already record the current zero-API-key, internal-kernel architecture as `proposed`; the plan and DECISION-0047's PowerShell-decoded artifact hash lagged that state.
- **Status type:** divergent

### Decision
Keep ADR-0031's architecture decision unchanged and proposed. Align the mutable plan to the approved ChatGPT browser/device included-access lane, explicitly prohibit API-key/API-billed substitution, record the backend prerequisite complete and ADR-0031 authored but unratified, and bind this forward correction to the canonical raw-UTF-8 plan-section SHA-256. DECISION-0048 supersedes DECISION-0047 only as the current plan/hash record; it does not rewrite or broaden ADR-0031's Decision-5-only partial supersession of ADR-0011.

### SMARTS rationale
Recording-only correction. Reliable and Testable require the mutable plan, proposed ADR, and recomputable section hash to agree byte-for-byte; Securable requires the user's no-API-key boundary to replace the obsolete credential lane everywhere active. No architectural option was reopened and no acceptance was inferred.

### Implementation implication
Reviewers resolve ADR-0031 authoring through DECISION-0048 and SHA-256 `850636eb9e7ef34cf165473f3e6e26d2c1b81bcdd04ce4dffff2aa474b199bdc`; DECISION-0047 remains immutable history of the original authoring record and its corrected H-05 append. Exact-candidate Windows desktop proof remains a release blocker and now uses only explicit ChatGPT browser/device authorization within included access.

---

## DECISION-0049 - adr-0031-ratified - ADR-0031 accepted

**Date:** 2026-08-22
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com - direct ratification after the exact proposed ADR and definitive independent PASS were presented: "Ratify ADR-0031: transition it from proposed to accepted with its content unchanged."
**Decision category:** architecture lifecycle
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** ADR-0031 was authored as `proposed`, corrected forward through DECISION-0048 without changing its architecture, and independently reviewed PASS.
- **Scaffold position:** n/a - this is the explicit lifecycle transition of the reviewed authored record.
- **Status type:** open-decision-closure

### Decision
ADR-0031 is accepted with decision content unchanged. Only the authoritative `status:` frontmatter and its mirrored `## Status` text transition from proposed to accepted; the internal generated-kernel boundary, host-native root and Codex resource/dispatch contracts, compatibility window, zero-API-key release boundary, Pi Forge-only positioning, and ADR-0011 Decision-5-only partial supersession remain exactly as reviewed.

### SMARTS rationale
Recording-only lifecycle entry. The architecture rationale remains in ADR-0031 and DECISION-0048; this entry records the repository user's explicit post-review ratification and preserves the rule that authoring approval, tests, and reviewer PASS cannot self-ratify an ADR.

### Implementation implication
ADR-0031 now governs its declared paths and unblocks the next governed PR 1 delivery contract. It does not itself authorize staging, committing, pushing, opening or merging a pull request, payload implementation, release, or publication; those actions remain controlled by the campaign's next explicit execution contract and repository gates.

---

## DECISION-0050 - adr-0031-ratification-plan-sync - Bind the accepted lifecycle and ChatGPT-device receipt schema

**Date:** 2026-08-22
**Status:** accepted
**Supersedes:** DECISION-0048
**Decided by:** SUaDtL@users.noreply.github.com - the repository user's direct ADR-0031 ratification and prior zero-API-key approval control this forward synchronization.
**Decision category:** record correction / architecture lifecycle
**Artifact-section-hash:** f6fbcf403075c02015bcf0e784a072bce0e21db218dca7591ee6bfb4cb58e4e8

### Variance summary
- **Artifact position:** After ADR-0031 moved to `accepted`, the mutable migration plan still described it as proposed/unratified and one PR 1 candidate-receipt task still named `api-key` authentication despite the approved ChatGPT browser/device included-access lane.
- **Scaffold position:** Accepted ADR-0031 and DECISION-0049 already record unchanged architecture, explicit ratification, and the zero-API-key release boundary; only mutable plan lifecycle/schema wording and DECISION-0048's prior plan-section hash lagged that state.
- **Status type:** divergent

### Decision
Keep accepted ADR-0031's architecture content unchanged. Align the mutable plan to the explicit ratification, replace the stale candidate-receipt `api-key` label with `chatgpt-device`, retain the prohibition on API-key/API-billed substitution, and bind this forward synchronization to the canonical raw-UTF-8 plan-section SHA-256. DECISION-0050 supersedes DECISION-0048 only as the current plan/hash record; DECISION-0049 remains the authoritative lifecycle acceptance record.

### SMARTS rationale
Recording-only synchronization. Reliable and Testable require the mutable plan, accepted ADR lifecycle, receipt schema, and recomputable section hash to agree. Securable requires the approved no-extra-spend authentication boundary to be explicit at every active candidate-evidence seam. No architecture option was reopened and no additional authority was inferred.

### Implementation implication
PR 1 reviewers resolve the current plan record through DECISION-0050 and SHA-256 `f6fbcf403075c02015bcf0e784a072bce0e21db218dca7591ee6bfb4cb58e4e8`. Exact-candidate Windows desktop proof remains deferred to its governed release gate and can be satisfied only by explicit ChatGPT browser/device authorization within included access; no API-key or API-billed substitute is permitted.

---

## DECISION-0051 - hosted-static-codex-release-evidence - Replace mandatory desktop proof with deterministic plugin evidence

**Date:** 2026-08-31
**Status:** proposed
**Supersedes:** DECISION-0050
**Decided by:** SUaDtL@users.noreply.github.com - the repository user explicitly rejected desktop installation and personal-PC runner use, approved static package-shape CI plus local plugin loading, and granted continuing merge authority through parity release and local installation.
**Decision category:** architecture / release evidence
**Artifact-section-hash:** bb5980ac802d6e7db37b0d65ce3321b9dc06a75e7b7cde7481f0e4a0b0b46822

### Variance summary
- **Artifact position:** Accepted ADR-0031 Decision 5 requires an exact-candidate installed Windows desktop cell using ChatGPT device authorization before `ca-codex` release.
- **Scaffold position:** The active release path now contains a self-hosted runner, Hyper-V/ADK broker stack, desktop receipt, and attestation chain whose operational cost is disproportionate to validating a static plugin package.
- **Status type:** divergent

### Decision
Supersede only ADR-0031 Decision 5's mandatory desktop-shell release evidence. Require trusted GitHub-hosted deterministic validation of the exact plugin manifest, front matter, resource and route graph, generated parity, hooks, contained paths, and release/archive identity; retire the active desktop workflow and executable infrastructure. Prove practical host loading by updating the supported local Codex marketplace plugin and running a fresh-task `$ca-doctor`, not by installing or automating the Windows desktop application.

### SMARTS rationale
Simple and Reliable remove an interactive personal-machine dependency from an otherwise static artifact release. Testable strengthens direct assertions on every byte and reference the plugin actually ships. Securable eliminates device authorization, reusable runner registration, Hyper-V, ADK, and receipt-attestation attack surface while preserving trusted-code/inert-data separation, bounded archive parsing, CodeQL, secret scanning, and fail-closed publication.

### Implementation implication
ADR-0032 records the forward-only partial supersession. Active CI and release workflows move to hosted static candidate validation; desktop workflow, broker, driver, probe, boundary manifest, receipt, and attestation code are removed. The pending governed `ca-codex` release proceeds only after the replacement gate is reviewed, green, merged, and its exact artifact identity is verified.

---

## DECISION-0052 - adr-0032-ratified - ADR-0032 accepted

**Date:** 2026-08-31
**Status:** accepted
**Supersedes:** DECISION-0051
**Decided by:** SUaDtL@users.noreply.github.com - the repository user explicitly ratified ADR-0032 and instructed that its content remain unchanged.
**Decision category:** architecture lifecycle acceptance
**Artifact-section-hash:** bb5980ac802d6e7db37b0d65ce3321b9dc06a75e7b7cde7481f0e4a0b0b46822

### Variance summary
- **Artifact position:** ADR-0032 and DECISION-0051 recorded the hosted-static ca-codex release-evidence decision as proposed pending explicit ratification.
- **Scaffold position:** The user has now explicitly accepted ADR-0032 with its decision content unchanged.
- **Status type:** open-decision-closure

### Decision
Accept ADR-0032 without changing its architecture content. Supersede only ADR-0031 Decision 5's mandatory desktop-shell evidence with trusted hosted static package evidence and supported local marketplace load proof; every other ADR-0031 decision remains unchanged.

### SMARTS rationale
This is a lifecycle transition explicitly directed by the user, not a new architectural choice. Reliable and Securable preserve the independently reviewed trusted-verifier and inert-candidate boundary; Simple and Testable retain the proportionate static package contract and fresh-task `$ca-doctor` proof without personal-PC release infrastructure.

### Implementation implication
The conditional ADR blocker is cleared. Deliver the additive compatibility-preserving trusted static verifier prerequisite first, integrate its exact landed main revision into the hosted-static feature branch, then retire the desktop path and proceed through governed CI, CodeRabbit, merge, release, supported local installation, fresh-task verification, and campaign completion audit.

---

## DECISION-0053 — adr-0033-ratified — Accepted ADRs bind sealed obligations to current evidence

**Date:** 2026-09-02
**Status:** accepted
**Supersedes:** none
**Decided by:** SUaDtL@users.noreply.github.com
**Decision category:** governance-integrity
**Artifact-section-hash:** n/a

### Variance summary
- **Artifact position:** Accepted ADRs record approved plans but do not prove implementation, verification, or immutable accepted content.
- **Scaffold position:** A separate append-only lifecycle ledger content-binds acceptance, seals obligations, and derives only current input-bound delivery states.
- **Status type:** open-decision-closure

### Decision
Preserve `status: accepted` as Accepted/Planned and record delivery evidence separately in an append-only `adr-lifecycle.jsonl`. Bind future acceptance once to exact content and a sealed obligation set; treat legacy records as incomplete baselines; expose only fresh, input-matching Verified obligations.

### SMARTS rationale
Safety and maintainability reject rewriting accepted bodies or fabricating historical completeness. Reversibility favors an append-only companion ledger whose derived states can invalidate on changed inputs without erasing evidence. Specificity and testability require stable obligation IDs, exact digests, explicit proof contracts, and narrow repository claims.

### Implementation implication
Add the lifecycle ledger schema, parser, checker, tests, CI integration, decision-lifecycle guidance, truthful legacy baselines, and verified-only export. Complete ADR-0026's current four-item destructive registry and parity checker under ADR-0030's narrowing.

---
