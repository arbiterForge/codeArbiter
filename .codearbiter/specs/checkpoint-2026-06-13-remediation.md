# Sprint spec: checkpoint-2026-06-13-remediation

**Status:** APPROVED — 2026-06-13 (Phase 1 gate cleared; autonomy begun)
**Goal:** Close the five actionable decisions from the 2026-06-13 checkpoint sweep. One sprint, one PR.
**Source:** `.codearbiter/checkpoints/2026-06-13.md`
**Branch:** `sprint/checkpoint-2026-06-13-remediation` (new branch off current `checkpoint-remediation-2026-06-12` HEAD)
**SMARTS pre-scoring (this session):** A strong/fix-now · B moderate/securable · C moderate/document · D moderate/hybrid · E moderate/securable

---

## Hard-gate map (read first)

This sprint is hard-gate-dense by nature. Of five items, three are true stops the framework will
NOT auto-decide — they halt and surface for explicit user action even mid-sprint:

| Item | Hard gate | Why it stops |
|------|-----------|--------------|
| B | `security-controls` (TLS / secret-handling) | Touches the documented TLS guarantee + `FARM_API_KEY` exposure path |
| C | Trust-boundary change | Edits `security-controls.md`'s boundary-crossings table |
| D | ADR authoring | MUST be user-attributed via `/ca:adr`; cannot be autonomous |

A (tests) and E (CI audit line) are the only cleanly autonomous items. Structure approved:
**one sprint, planned stops** — A+B+E execute autonomously; C and D halt for interactive user action.

---

## Pre-flight — checkpoint-artifact hygiene

Before any sprint code: land the outstanding checkpoint artifacts already in the working tree and
discard the CRLF-only noise, so the sprint branch starts from a clean, audited base.

- Commit `.codearbiter/checkpoints/2026-06-13.md`, `.codearbiter/last-checkpoint` (=1), and the
  `.codearbiter/overrides.log` force-push audit line (already written; legitimate).
- Revert `plugins/ca/tools/farm.js` — diff is a line-ending (LF→CRLF) artifact, zero content change.

---

## Workstream A — `pre-edit.py` negative-path tests  (HIGH · autonomous)

The lone would-block finding. `pre-edit.py` enforces H-05 (append-only audit logs: an Edit to
`overrides.log`/`triage.log` must `startswith` `old_string`) and H-11 (ADR files editable only via
`/adr`, gated on a fresh `adr-authoring-active` marker). Neither BLOCK path has a behavioral test —
only a benign cold-install allow noop. A regression inverting the `startswith` check, mis-compiling
the regex, or dropping the marker-freshness check would block nothing and pass CI green.

New file `plugins/ca/hooks/tests/test_pre_edit.py` (mirror the `_helpers.py` subprocess pattern used
by `test_governs`/`test_write`), covering:

| Case | Expectation |
|------|-------------|
| H-05 BLOCK — non-appending edit to `overrides.log`/`triage.log` | exit 2, `H-05` tag |
| H-05 ALLOW — pure-append edit | exit 0 |
| H-11 BLOCK — edit `.codearbiter/decisions/NNN-*.md`, no marker | exit 2 |
| H-11 BLOCK — stale (>30 min) marker | exit 2 |
| H-11 ALLOW — fresh marker | exit 0 |
| ALLOW — arbiter disabled / unrelated path | exit 0 |
| Windows path variants (`norm_path` backslash) | guard branch fires |

## Workstream B — `farm.ts` resolved-apiBaseUrl TLS validation  (MEDIUM · HARD GATE)

The TLS-scheme check in `validate()` only covers `plan.meta.apiBaseUrl`. The effective URL is
resolved `ENV.apiBaseUrl ?? plan.meta.apiBaseUrl ?? ENV.defaultApiBaseUrl`, so a `FARM_API_BASE_URL`
env override bypasses the HTTPS check entirely — `FARM_API_KEY` (Bearer header) could ride cleartext
`http://`. Validate the **resolved** `apiBaseUrl` against the same HTTPS-or-loopback rule
immediately before the first `fetch()`; reject a non-HTTPS non-loopback base URL regardless of source.

- Source: `plugins/ca/tools/farm.ts` (resolution at `:808-825`/`:835`; reuse the `validate()`
  `:761-766` rule). Rebuild shipped `farm.js`.
- Test-first (vitest): `FARM_API_BASE_URL=http://evil` → rejected before any fetch; `https://…` and
  `http://127.0.0.1`/`localhost` → accepted.
- **Stop point:** surface the security-relevant change to the user before landing (security-controls gate).

## Workstream C — declare the shell-exec trust boundary  (MEDIUM · HARD GATE)

`plan.json` gate.commands and `FARM_MUTATION_CMD` execute verbatim via `cmd.exe /c` / `bash -c`. This
is intended (deterministic operator-authored gate, length-bounded ≤1024) but the trust boundary is
absent from `security-controls.md`'s boundary-crossings table. **Document, do not allowlist** (SMARTS:
allowlist over-engineers a trusted-operator input and risks breaking valid gates).

- Add one row to the boundary-crossings table (`security-controls.md:100-104`): boundary = plan.json
  gate.commands + `FARM_MUTATION_CMD` shell execution; exception = trusted operator-authored input,
  PR-reviewed; rationale = deterministic gate by design, length-capped, no untrusted source.
- **Stop point:** editing `security-controls.md` is a trust-boundary change — halt for approval.

## Workstream D — governance ADRs + hybrid model  (USER-ATTRIBUTED · HARD GATE)

Author numbered ADRs via `/ca:adr` (user-attributed), adopting the hybrid ADR + living-docs model:
`tech-stack.md`/`security-controls.md` remain the living reference; load-bearing decisions are pinned
as immutable, attributed ADRs. Matches the standing commercialization promotability constraint.

ADRs to author (all four, user-attributed):

1. **Hybrid governance model** — the meta-decision: ADRs pin decisions; living docs stay reference.
2. **plan.json shell-exec boundary** — the trusted-operator execution boundary (pairs with C).
3. **TLS / secret-handling posture** — outbound-HTTPS-only + `FARM_API_KEY`-via-env (relates to B).
4. **Database-free / stdlib-only architecture** — no datastore, Python-stdlib-only hooks.

- Initializes `.codearbiter/decisions/` (currently absent) and the decision log.
- **Stop point:** each ADR halts for user authorship/attribution — cannot be auto-decided.

## Workstream E — CVE audit CI step  (LOW · autonomous)

No CVE audit step exists; the CVE gate `security-controls.md` references is unsatisfiable. Add
`npm audit --omit=dev --audit-level=critical` to the `plugins/ca/tools` CI job and reference it as the
audit command in `tech-stack.md`.

- `.github/workflows/ci.yml` — add the audit step to the tools job.
- `.codearbiter/tech-stack.md:57-58` — replace "no scanner configured" with the enumerated command.

---

## Acceptance criteria

1. `tests/test_pre_edit.py` exists; all seven cases green; full Python suite (225+) no regressions.
2. `farm.ts` rejects a non-HTTPS non-loopback **resolved** apiBaseUrl before first fetch; new vitest
   cases green; `farm.js` rebuilt and in sync; TS suite (56+) green.
3. `security-controls.md` boundary-crossings table has the shell-exec row (user-approved).
4. Four ADRs authored under `.codearbiter/decisions/`, user-attributed, decision log initialized.
5. `ci.yml` runs `npm audit --omit=dev --audit-level=critical`; `tech-stack.md` references it.
6. Pre-flight checkpoint artifacts committed; `farm.js` CRLF noise reverted.
7. Full test suite green (Python + TypeScript); `commit-gate` clean.
8. Every non-hard-gate auto-decision logged to `sprint-log.md` with a confidence flag.

## Out of scope / NEEDS-TRIAGE deferred

- `tools/statusline-screenshot.py` test-floor exclusion (maintenance tool, not shipped) — recorded,
  no action this sprint.
- The LOW defense-in-depth items (strip `FARM_API_KEY` from child env `farm.ts:118`;
  `wire-statusline.py` tmp cleanup; `security-pass.py` branch coverage) — not in this sprint's
  approved scope; carry to the next checkpoint unless the user adds them.
