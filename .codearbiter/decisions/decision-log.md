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
