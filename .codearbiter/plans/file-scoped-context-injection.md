# Plan — file-scoped just-in-time context injection on Read

**Spec:** `.codearbiter/specs/file-scoped-context-injection.md` (approved 2026-06-26, Lane: full)
**Task:** `v2.feature.0001` (in-progress) · **Precondition:** `v2.chore.*` spike-residue cleanup (on board)

Execution: `executing-plans` (checkpointed, via `/feature`), each task through `tdd`. The plan
never hands to `tdd` directly. Status column is the resume ledger.

---

## AC ledger (lifted verbatim from the spec; AC-01 resolved = spike GO, NOT an impl task)

- **AC-02** — wired as a plugin `hooks.json` `PreToolUse` matcher `Read` → `pre-read.py`, `python3 || python` fallback.
- **AC-03** — emits exactly `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","additionalContext":"…"}}`, ALWAYS allows, including when `additionalContext` is empty.
- **AC-04** — tier 1: `governing_docs` returns the security-controls.md pointer for any path where `classify_source(path)` is True, with NO provenance present; nothing for a non-security path.
- **AC-05** — tier 2: an ADR with `governs:` glob + `status: accepted` returns its id+title on a matching Read; unmatched → nothing; `status: superseded` never returned even on a glob match.
- **AC-06** — tier 3: a spec carrying `**Governs:** <glob>` is returned for a Read of that path; a spec with no `Governs:` line matches nothing.
- **AC-07** — tier 4 (enrichment): with a populated `.provenance/`, a Read whose stored `hash` EQUALS the file's current `git hash-object` returns doc+claim; a diverged hash is SUPPRESSED (nothing).
- **AC-08** — assembled `additionalContext` ≤150 tokens (`ceil(chars/4)`); over budget → priority order (security-controls > decisions > specs > standards), truncated at cap with trailing ellipsis.
- **AC-09** — at most one injection per `(session, file)` via a per-session `.codearbiter/.markers/` entry; a different file in the same session still injects.
- **AC-10** — a Read under `.codearbiter/` itself, and a Read of any path with no governing match, produce allow with empty `additionalContext`.
- **AC-11** — a non-matching Read does zero git subprocess calls and parses no provenance hashes (assert via an injected runner: call count = 0).
- **AC-12** — every failure mode (missing/corrupt index, malformed ADR frontmatter, git unavailable, any exception) degrades to allow-with-empty; no input makes the hook raise or deny.
- **AC-13** — the spec header format documents an optional `**Governs:** <comma-separated globs>` line, and the matcher (AC-06) parses it; adding the line is sufficient to enroll a spec with no other change.

---

## Task table

All lib tasks land pure functions in `plugins/ca/hooks/_readinjectlib.py` (stdlib only, zero
import-time side effects, never raises — mirrors `_provenancelib.py`), tested by a new
`.github/scripts/test_readinjectlib.py` (plain-`python` self-asserting script, the repo pattern).
Verification "→ exit 0" means the script's assertions pass.

| id | path(s) | verification | maps-to (tdd obligation) | covers | depends-on |
|----|---------|--------------|--------------------------|--------|------------|
| **T-01** | `_readinjectlib.py`, `test_readinjectlib.py` | header + `allow_output(ctx)` builds the exact `hookSpecificOutput` dict incl. `additionalContext=""`; `python .github/scripts/test_readinjectlib.py` → exit 0 | output-shape obligation (exact JSON, empty-safe) | AC-03 | — |
| **T-02** | `_readinjectlib.py`, `test_readinjectlib.py` | `token_estimate(s)==ceil(len/4)`; `assemble_context(pointers, budget=150)` ≤150-token cap, priority order preserved, over-budget truncates with trailing ellipsis marker → exit 0 | budget-assembler obligation | AC-08 | — |
| **T-03** | `_readinjectlib.py`, `test_readinjectlib.py` | tier 1 `security_pointer(path)` reuses `_provenancelib.classify_source`: `src/auth/jwt.ts`→security-controls pointer (no provenance), `src/ui/Button.tsx`→None → exit 0 | tier-1 map obligation | AC-04 | — |
| **T-04** | `_readinjectlib.py`, `test_readinjectlib.py` | tier 2 `accepted_adr_index(root)` (filesystem reader, accepted-only) + `adr_pointers(rel, index)`: accepted ADR with `governs:` glob→id+title, unmatched→[], `status: superseded`→[] even on glob match → exit 0 | tier-2 map obligation | AC-05 | — |
| **T-05** | `_readinjectlib.py`, `test_readinjectlib.py` | tier 3 `parse_spec_governs(text)` (the `**Governs:**` header line) + `spec_pointers(rel, specs_index)` approved-only: spec with `**Governs:** <glob>`→pointer, spec w/o line→[] → exit 0 | tier-3 map + `**Governs:**` parse obligation | AC-06 | — |
| **T-06** | `_readinjectlib.py`, `test_readinjectlib.py` | tier 4 `provenance_pointer(rel, provenance, current_hashes)` reuses `_provenancelib.batch_hash`: synthetic provenance, stored hash==current→doc+claim, diverged→[] (suppressed) → exit 0 | tier-4 enrichment obligation | AC-07 | — |
| **T-07** | `_readinjectlib.py`, `test_readinjectlib.py` | `governing_docs(path, index)` orders tiers security-controls > decisions > specs > standards(prov); returns ordered pointer list; tier-4 absent (empty `.provenance/`) degrades to tiers 1–3 → exit 0 | tier-orchestration + priority obligation | AC-04, AC-05, AC-06, AC-08 | T-03, T-04, T-05, T-06 |
| **T-08** | `_readinjectlib.py`, `test_readinjectlib.py` | dedup `marker_path/already_injected/record_injection` under `.codearbiter/.markers/` keyed `(session,file)`: 2nd Read of same file suppressed, a different file in the same session injects → exit 0 | dedup-marker obligation | AC-09 | — |
| **T-09** | `_readinjectlib.py`, `test_readinjectlib.py` | `build_index(root)` reader + miss fast-path: a non-matching Read makes the injected runner record **0** git calls and parses no provenance hashes → exit 0 | zero-cost-on-miss obligation | AC-11 | T-03, T-04, T-05 |
| **T-10** | `_readinjectlib.py`, `test_readinjectlib.py` | robustness: corrupt index, malformed ADR frontmatter, git-unavailable runner, exception in any pure fn → allow-with-empty; fuzz of `None`/garbage never raises/denies → exit 0 | fail-open obligation | AC-12 | T-07, T-09 |
| **T-11** | `plugins/ca/hooks/pre-read.py`, `.github/scripts/test_pre_read.py` | thin hook: reads stdin (`session_id`,`file_path`), `arbiter_active` gate, calls lib, emits `allow_output`; driven by subprocess with synthetic stdin → JSON allow + `additionalContext`; a Read under `.codearbiter/` → empty `additionalContext` → exit 0 | hook entry-point + self-read obligation | AC-03, AC-10 | T-01, T-02, T-07, T-08, T-09 |
| **T-12** | `plugins/ca/hooks/hooks.json`, `.codearbiter/tech-stack.md`, `.github/workflows/ci.yml` | add `PreToolUse` matcher `Read`→`pre-read.py` with `python3 \| python` fallback; register `test_readinjectlib.py`+`test_pre_read.py` in tech-stack Test list + CI; `python .github/scripts/check-plugin-refs.py` green, `hooks.json` parses | wiring obligation (matcher resolves, dual-interpreter, CI runs suites) | AC-02 | T-11, **`v2.chore.*` spike cleanup** |
| **T-13** | `plugins/ca/skills/brainstorming/SKILL.md` | document the optional `**Governs:** <comma-separated globs>` header line in Phase 3 spec format; enrollment proven by T-05's parse test (adding the line is sufficient, no other change) | spec-format-doc obligation | AC-13 | T-05 |

---

## Order & MVP slice

Dependency order (topological): T-01, T-02, T-03, T-04, T-05, T-08 (all independent) →
T-06 → T-07 → T-09 → T-10 → T-11 → T-13 → T-12.

**MVP slice (tiers 1–3, shippable on its own):** T-01, T-02, T-03, T-04, T-05, T-07, T-08,
T-09, T-10, T-11, T-13, T-12. This delivers the spec's core "done looks like" — a governed-file
Read gets a budgeted, deduped, fail-open note from security-controls / accepted ADRs / approved
specs; a non-governed Read costs nothing. `governing_docs` (T-07) degrades cleanly when
`.provenance/` is empty, which is the real state of this repo today.

**Incremental (past MVP):** **T-06** (AC-07 tier-4 provenance enrichment). Lights up only once a
re-scout backfills `.codearbiter/.provenance/` (empty in this pre-#145-data repo). Tested against
a synthetic provenance fixture, so it does not block on a live backfill — but it adds no
user-visible value until the store is populated, so it ships after the MVP slice.

> Sequencing note for executing-plans: T-12 (hooks.json wiring) MUST NOT run until the
> `v2.chore.*` spike-residue cleanup is done — the spike left a live `PreToolUse:Read` matcher in
> the plugin **cache** `hooks.json` that would collide with the real one. Verify the cleanup task
> is `[x]` before the T-12 batch.

---

## Coverage proof

Every AC has ≥1 task; every task covers ≥1 AC.

- AC-02 → T-12 · AC-03 → T-01, T-11 · AC-04 → T-03, T-07 · AC-05 → T-04, T-07 · AC-06 → T-05, T-07
- AC-07 → T-06 · AC-08 → T-02, T-07 · AC-09 → T-08 · AC-10 → T-11 · AC-11 → T-09 · AC-12 → T-10 · AC-13 → T-13

No uncovered criterion; no task without a criterion. Bijective.

---

## Status ledger

| task | status |
|------|--------|
| T-01 | ACCEPTED |
| T-02 | ACCEPTED |
| T-03 | ACCEPTED |
| T-04 | ACCEPTED |
| T-05 | ACCEPTED |
| T-06 | ACCEPTED |
| T-07 | ACCEPTED |
| T-08 | ACCEPTED |
| T-09 | ACCEPTED |
| T-10 | ACCEPTED |
| T-11 | ACCEPTED |
| T-12 | ACCEPTED |
| T-13 | ACCEPTED |

---

## Reuse / notes (no `[NEEDS-TRIAGE]` items raised)

- T-03 reuses `_provenancelib.classify_source()`; T-06 reuses `_provenancelib.batch_hash()` — verbatim, no re-implementation.
- T-04's `governs:` parsing mirrors `post-write-edit.py:governs_index()` but uses an **accepted-only** predicate (that hook filters `not in (superseded, rejected)` — looser; tier 2 is stricter). New lib reader, not a verbatim lift.
- Markers live under the existing `.codearbiter/.markers/` (already used by `governs-cache.json`); confirm it is git-ignored as a transient dir during T-08.
