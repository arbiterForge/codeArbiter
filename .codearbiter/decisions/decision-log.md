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
