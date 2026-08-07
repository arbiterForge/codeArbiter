# Plan — recorded-intent + kernel-slim campaign (rev 2)

**Spec:** `.codearbiter/specs/recorded-intent-kernel-campaign.md` (rev 2) · **Status ledger below is the resume point.**
**Rev 2:** regeneration re-sequenced INSIDE each lane before verification/measurement tasks
(feasibility #2); CI wiring added (feasibility #3); version paths corrected (feasibility #7);
release fan-out enumerated (feasibility #8); T-13 rebuilt on the #609 protocol (blast F-3).

## AC ledger

AC-01..AC-14 — lifted verbatim from the spec rev 2 (single source; not restated per #566).

## Lanes and PR shape

- **Lane 1 (ADRs)** — T-01..T-02. ADR files COMMIT IN THE LANE-2 PR (never sit uncommitted
  across a lane boundary).
- **Lane 2 (S1 recorded-intent)** — T-03..T-09 → one PR, one version advance.
- **Lane 3 (S2+S3 kernel)** — T-10..T-16 → one PR, one version advance, A/B-gated.
- Lane order 1 → 2 → 3; PRs merge in ascending version order. Fetch + compare `origin/main`
  before cutting each branch.

## Task table

| id | task | path(s) | verification | covers | depends | status |
|---|---|---|---|---|---|---|
| T-01 | Author ADR-0025 (Step-0 scope header + exempt list + authority-order "answered" are normative content; via `/ca:adr`, authoring marker armed; STOP for user ratification) | `.codearbiter/decisions/0025-recorded-intent-precedes-autonomous-scoring-and-spec-shaping.md`, `decisions/decision-log.md` | file present, `status: accepted`, user-attributed, `governs:` per AC-01; log line appended | AC-01 | — | PENDING |
| T-02 | Author ADR-0026 destructive-operations BLOCK in routing table (amends ADR-0022; block form, not per-row column; STOP for user ratification) | `.codearbiter/decisions/0026-destructive-set-declared-in-routing-table.md`, `decisions/decision-log.md` | same as T-01, `governs:` per AC-02 | AC-02 | — | PENDING |
| T-03 | smarts Step-0: scope header (applies: /sprint scoring, brainstorming; exempt BY NAME: decision-variance, grader, decision-challenger), authority-order "answered", three outcomes (answered/constrains/silent; /sprint answered-contradiction = hard gate, never mid-sprint reconcile), index-first loading rule, fail-soft sentence | `core/surface/includes/smarts/core.md` | T-07 assertions (post-regen) | AC-03 | T-01 | PENDING |
| T-04 | SPRINT.md: pre-approval intent read (decision-log + ADR index + plans/01–03 headings + open-questions deferred sections; fail-soft); valve wording (trigger-occurred reopen; one-stop-per-record; pre-ruled collisions cite ruling); contradiction in NEVER list; `intent:` field AFTER `confidence:` or body-line; answered→`confidence: high`, citation in verdict slot; diagnostic extension | `core/surface/SPRINT.md` | T-07 assertions; `python .github/scripts/test_taskwriter.py` green incl. NEW fixture heading carrying both `intent:` + `confidence:` proving title extraction unpolluted | AC-04 | T-01 | PENDING |
| T-05 | grader: one informational ADR-index-citation line in assignment format (grader stays Step-0-exempt) | `core/surface/agents/grader.md`, `.github/scripts/test_taskwriter.py` (fixture from T-04 if placed here) | T-07 assertion (core/ca/ca-pi only) | AC-05 | T-01 | PENDING |
| T-06 | brainstorming: pre-flight fail-soft block SEPARATE from the 'Read these, or STOP' contract; Phase 1 resurrection check folded into the CONTEXT.md framing bullet; Phase 2 ADR-index conformance (surface-with-citation, supersession-fork pairing, only-sane-approach-IS-the-fork); Phase 5 bullet | `core/surface/skills/brainstorming/SKILL.md` | T-07 assertions | AC-06 | T-01 | PENDING |
| T-07 | Regenerate (write mode) THEN author the structural test: pins AC-03..06 across core + carrying hosts (grader: core/ca/ca-pi + explicit codex-exemption comment; per-host paths via the HOSTS-tuple pattern, `test_routing_and_cleanup_surface.py:38` — brainstorming is `routines/` on codex/pi); prove every assertion dies to a mutant (delete passage → red, restore); wire into ci.yml as an explicit step | `python tools/build-surface.py` (write), `.github/scripts/test_recorded_intent_surface.py`, `.github/workflows/ci.yml` | test green post-regen; mutant transcript in PR body; ci.yml step present | AC-07 | T-03,T-04,T-05,T-06 | PENDING |
| T-08 | Lane-2 parity + refs sweep | generated `plugins/**` | `python tools/build-surface.py --check`; `python tools/sync-core.py --check`; `python .github/scripts/check-plugin-refs.py`; `python .github/scripts/check_routing_index_parity.py` | AC-08 | T-07 | PENDING |
| T-09 | Lane-2 PR (ADR files ride here): version advance on REAL surfaces — `plugins/ca/.claude-plugin/plugin.json`, `plugins/ca-codex/.codex-plugin/plugin.json`, `plugins/ca-pi/package.json`, root `package.json`, `CHANGELOG.md`, `plugins/ca-codex/CHANGELOG.md`, `plugins/ca-pi/CHANGELOG.md`, README badge — commit-gate (unset NO_COLOR first), push, **read the CI job log to confirm test_recorded_intent_surface.py executed**, `gh pr checks` green before done-claim | version surfaces + `.codearbiter/decisions/0025*,0026*` | `python tools/build-host-packages.py --check`; `python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"`; pi aggregate: `npm --prefix plugins/ca-pi/tools ci --ignore-scripts && npm --prefix plugins/ca-pi/tools test`; `python .github/scripts/test_pi_parity.py`; CI log inspection | AC-14, AC-07(CI) | T-08 | PENDING |
| T-10 | Kernel edit: §6 compression (tier rule once; asking discipline once; phrasing-channel clause in; #598 boundary rule + #609 asking rule SURVIVE as content, reworded allowed) + §7 mechanics removed (override.md already authoritative); redirect.md trimmed of relocated rule; extend `test_routing_and_cleanup_surface.py` with #598/#609 content-survival pins | `core/surface/ORCHESTRATOR.md`, `core/surface/commands/override.md`, `core/surface/includes/redirect.md`, `.github/scripts/test_routing_and_cleanup_surface.py` | `python .github/scripts/test_routing_and_cleanup_surface.py` (post-T-12 regen for host copies; core copy checkable immediately); `python .github/scripts/test_ux_conversion.py` | AC-09, AC-10 | T-02, T-09 | PENDING |
| T-11 | Routing-table `## Destructive operations` block (NOT a column — parity checker reads cells positionally); CI consistency check §6↔block; seeded-mismatch proof captures the FAILING LOG + `check_routing_index_parity.py` green in same run | `core/surface/includes/routing-table.md`, `.github/scripts/test_routing_and_cleanup_surface.py` (or sibling), `.github/workflows/ci.yml` (if new file) | seeded red log + green run transcript in PR body | AC-11 | T-10 | PENDING |
| T-12 | Regenerate (write mode) + lane parity sweep | `python tools/build-surface.py` (write) + generated `plugins/**` | same four checks as T-08 | AC-08 (lane 3) | T-11 | PENDING |
| T-13 | Byte measurement on the REGENERATED `plugins/ca/ORCHESTRATOR.md` vs 10,053 B; report actual, floor ≥ 500 B | `plugins/ca/ORCHESTRATOR.md` (generated) | figure + method in PR body | AC-13 | T-12 | PENDING |
| T-14 | A/B per #609 PROTOCOL: read `gh issue view 609` for format precedent; author NEW pre-registered scenario set (incl. #598 tier-misroute + #609 menu-not-a-briefing seeds + destructive-set confirmations + interrogative-channel + retained-text regression checks) + rubrics BEFORE any output; sealed runners, incumbent vs candidate; red pre-defined per spec; revision = FULL candidate arm re-run, ceiling 3 arms; results + limitation statement in PR; **STOP — user reviews before merge** | scratchpad artifacts; PR body | results table attached; user approval recorded | AC-12 | T-13 | PENDING |
| T-15 | Lane-3 PR: version advance (same real surfaces as T-09), commit-gate, CI log inspection, `gh pr checks` green | same as T-09 minus ADR files | same as T-09 | AC-14 | T-14 | PENDING |
| T-16 | Campaign close: `/ca:release` PER TARGET — ca, then ca-codex (`ca-codex-v*`), then ca-pi (`ca-pi-v*`) as their payloads advanced; each `--dry-run` first, each tag user-gated; harvest per SPRINT.md close rule | CHANGELOGs, tags | three dry-runs green; user rules on each tag | AC-14 | T-15 | PENDING |

## MVP slice

T-01..T-09 (Lane 1 + Lane 2). Independently shippable, carries most of the value. Lane 3 is the
incremental slice behind the A/B gate with the enforceable stopping rule (red → one full
candidate-arm revision; second red → kernel lane closes as a findings note, S1 stands).

## Standing cautions (from memory, binding at execution)

- Unset `NO_COLOR` before every commit-gate test run (fakes 7 red statusline tests).
- gate-events.log / overrides.log merge conflicts resolve as append-only unions.
- Local green ≠ CI green: read `gh pr checks` before any done-claim.
- Verify every new CI check by READING ITS LOG (seeded red + confirmed execution), never by
  status alone.
- Edits can flip LF→CRLF on Windows; normalize before commit.
