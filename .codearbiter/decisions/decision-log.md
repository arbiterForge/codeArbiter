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
