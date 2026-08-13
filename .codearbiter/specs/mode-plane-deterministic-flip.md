# Spec — Mode plane with deterministic flip and composed persona injection

**Governs:** core/pysrc/session-start.py, core/pysrc/_modelib.py, core/pysrc/_hooklib.py, core/pysrc/_arbiterstatelib.py, core/pysrc/statusline.py, core/pysrc/_prunepolicy.py, core/pysrc/_metricslib.py, core/surface/arbiter.md, core/surface/includes/safety-core.md, core/surface/includes/dangerous-mode.md, core/surface/includes/ops-mode.md, core/surface/includes/redirect.md, plugins/ca/hooks/hooks.json, plugins/ca-codex/hooks/hooks.json, plugins/ca-pi/hooks/pi-bridge.py, plugins/ca-pi/tools/src/extension.ts, README.md

Issue: #437 · Slug: `mode-plane-deterministic-flip` · Stage: 2

## Problem

codeArbiter has no channel for reversible local runtime work: `/btw` is correctly read-only, `/dev` is
correctly maintainer-reserved, and the only remaining route is a logged `/override` — a governance
bypass for a routine act. Separately the two behavior-modifying commands are a manually-driven pair
with no mechanical backing (`CODEARBITER_DEV` has **zero code readers**; the `dev-active` marker is
written by command *prose*), and every session pays the full 10,053-byte `ORCHESTRATOR.md` at turn 0 —
including dev sessions, which ignore every rule in it by definition.

**Caller:** any developer in a governed repo who wants to run their app, or work without gates, without
staging a governance bypass to do it. **Done:** one deliberate token switches posture, the injected
persona matches the posture, and the command surface got *smaller*.

**Explicitly NOT doing:** process supervision for `ops` (owned PIDs, readiness probes, scoped stop,
cross-session recovery) — deferred by user ruling so it gets a dedicated scoping pass, **not** because
ADR-0007 forbids it; a committed project-level `profile:` default (#247); prototype mode.

## Approach

**`ORCHESTRATOR.md` is not an always-on kernel — it is the arbiter mode's *body*.** The persona becomes
`safety-core + <current mode body>`, composed at injection time; the mode is flipped by a bare control
token intercepted at each host's prompt seam with no model inference on the flip turn.

Injection moves **off `SessionStart` to the per-turn seam**, deduped per (session, mode, compaction
generation). Forced, not stylistic: `SessionStart` fires once per session boundary, so a mid-session
flip could not change the injected body. Composition rather than three standalone bodies avoids
triplicating safety text into files with no gate comparing them.

**`ops` is advisory (user ruling).** No enforcement hook becomes mode-aware, so every gate fires
identically in all three modes. `ops` narrows *persona* prose only; the spec says so plainly rather
than implying mechanical enforcement.

**Design assumption, recorded not asserted:** on Claude, a hook block yields no model turn
(`shouldQuery:false`, read from the installed 2.1.228 binary). This is a *host* invariant that can
change without notice, so it is **not** an acceptance criterion — the criteria assert our exit code and
stderr contract. Codex confirms blocking via its embedded `user-prompt-submit.command.output` schema;
Pi via `input` → `{action:"handled"}` (present in both supported versions).

**ADR conflict, surfaced:** the deterministic flip removes the tier-2 confirmation ADR-0022:46-49
requires for dev entry (*"There the confirmation is the gate, not friction"* — a token is friction).
This ships only with a narrow supersession of that clause, and its compensating control is the audit
row — made load-bearing by AC-11 (the injector refuses a mode the ledger does not back). ADR-0026 is
not the target: it superseded only the placement clause.

## Scope

**In:** the three-value mode plane; deterministic token flip on Claude, Codex, Pi; composed per-turn
injection with dedup and compaction re-injection; startup-block decomposition into per-mode emitters;
deletion of `/ca:dev` and `/ca:arbiter` (catalog 40 → 38); `dev` expanded to a general `dangerous`
posture with `CODEARBITER_DEV` removed; `ops` as an advisory persona carve-out plus a redirect and
routing-table entry; the `ORCHESTRATOR.md` → `arbiter.md` rename; the ADR-0022 supersession; docs, site
and release surfaces; `CONTEXT.md` vocabulary.

**Out:** everything in the Problem section's NOT-doing list.

## Decided parameters

- **Modes:** `arbiter`, `dangerous`, `ops`. `dev` retired.
- **Token:** `mode --arbiter|--dangerous|--ops`, matched **whole-prompt, never substring**, case- and
  surrounding-whitespace-insensitive. Bare `mode` reports current mode and legal values on stderr, exits
  2, writes nothing.
- **State:** `.codearbiter/.markers/mode.d/<sha256(session_id)>`, **one file per session**, under
  **`marker_root`** — *correcting an earlier error: `marker_root` exists precisely because
  `project_root` splits marker state across linked worktrees (#604), and this repo runs worktree agents
  routinely.* Absent, empty, unreadable, or unknown value ⇒ `arbiter` **with a diagnostic that
  distinguishes unreadable from absent** (house rule `never-fold-unreadable-into-absent`).
  *Amended (#681): this shipped as a single `.markers/mode` file holding a `{session_id: mode}` map.
  Keying by session inside one file still made every flip a read-modify-write over state other
  sessions own, so a session holding a map it read moments earlier could reinstate a `dangerous`
  entry another session had explicitly left — authorized, because `ledger_backs` still matched that
  session's original `enter` row. Verifying the write did not close it: each writer confirmed only
  its OWN key. The map is now read-only for migration; nothing writes it.*
- **Lifetime:** cleared at `SessionStart`, matching today's `dev-active` contract. Gates-off must not
  survive a session boundary.
- **Single source of truth:** every reader migrates to the mode file; `dev-active` is not dual-written.
- **Bodies:** `core/surface/arbiter.md`, `includes/{safety-core,dangerous-mode,ops-mode}.md`.
- **Audit verb:** writers emit `MODE: <name> enter|exit`; readers accept those **and** legacy `DEV:`
  rows, since existing `overrides.log` rows are append-only.
- **Ledger reuse is scoped to close/exit rows only** — `_settle_dev_close`'s `marker_mtime` is a
  close-tombstone and its dedupe is not safe for freshly-minted `enter` rows in the same second.
- **Dedup marker:** `modeinject-`, keyed on (session, mode, compaction generation).
- **Injection channel:** plain stdout on Claude (plugin-scoped `additionalContext` is unreliable —
  claude-code #16538); the camelCase envelope on Codex, whose schema is `additionalProperties:false`
  with seven valid keys, so `permissionDecision` must be absent; `before_agent_start` on Pi for
  injection and the newly-registered `input` handler for the flip.
- **Rename scope:** live surface only; `arbiter.md`'s header carries `(formerly ORCHESTRATOR.md)`.
  Historical surfaces (`gate-events.log`, `decisions/`, `sprint-log.md`, published CHANGELOGs,
  `site/.../changelog.md`) are **byte-unchanged**.

## Acceptance criteria

### Mode state and flip
1. `_modelib.write_mode` routes through `write_text_atomic`; an interrupted write leaves no partial file.
2. An absent, empty, unreadable, or unrecognized mode file resolves to `arbiter` and emits a diagnostic
   that distinguishes unreadable from absent.
3. The mode is session-keyed: a flip in one session does not change the mode resolved by a concurrently
   live session in the same repo.
4. The mode file is cleared at `SessionStart`; a session that begins after a `dangerous` flip resolves
   `arbiter`.
5. The mode file resolves through `marker_root`, so a linked worktree and its main checkout agree.
6. A flip to the already-active mode is a no-op and writes no audit row.
7. On Claude, a whole-prompt token match flips the state, exits 2, and emits a named stderr line; the
   flip is idempotent under the two-entry `hooks.json` fallback pair.
8. A prompt containing a token as a substring exits 0, reaches the model unmodified, and leaves the mode
   file byte-unchanged; the same test flips on the exact-match control.
9. Bare `mode` emits the current mode and all three legal values on stderr, exits 2, and writes nothing.
10. A flip whose state write fails does not report success; the return-to-`arbiter` path is proven
    against an unwritable marker directory and does not wedge the session.
11. The injector refuses to compose a non-arbiter body when the audit trail holds no matching
    `MODE: <name> enter` row **for that session**: it resolves `arbiter` and emits a diagnostic.
    The row is an AUTHORIZATION, not merely a record, so it carries `SESSION: <id>` and is matched
    per session — a repo-wide match would let one session's row authorize another session's
    gates-off marker, defeating the isolation AC-3 requires everywhere else in the plane. A row
    written before the field existed authorizes no session and resolves to `arbiter`; the single
    session-blind exception is a legacy `DEV: enter` row backing `dangerous` only, which predates
    session attribution and is what the dev-to-dangerous migration runs on.
12. **Both halves** of a transition route through `_settle_dev_close` — the `enter` row as well as
    the exit/close row (ADR-0030 position 4: never a bare append). An interruption between stage
    and append leaves the row owed and the next run appends it exactly once; a flip whose row
    cannot be confirmed reports `FLIP_FAILED` rather than a success the injector will then refuse.

### Cross-host interception
13. On Codex, a token flips the state using the camelCase envelope; the emitted object's key set equals
    the seven schema-permitted names and `permissionDecision` is absent.
14. On Pi, a registered `input` handler returns `handled` and flips the state; the bridge payload's key
    set matches an allowlist (asserted as a set, not by grepping for absent text).
15. `pi-bridge.py`'s `ALLOWED_KEYS`/`EVENT_KEYS` are widened deliberately for the new event.
16. The interceptor is registered on `UserPromptSubmit` in both `hooks.json` files with the py2 fallback
    pair; a test covers both slot occupants wanting to exit 2 on the same turn.
17. `doctor.py`'s `HOOK_SCRIPTS` and `test_hooks_cold_install.py`'s expected-script sets include the new
    script, and the cold-install matrix reports it.

### Composed injection
18. The injected persona equals `safety-core` followed by the current mode's body, and the previous
    mode's body does not appear.
19. `safety-core` contains, asserted by named anchor: the §2 conflict ladder; §7's diagnose-don't-bypass
    paragraph; the secrets prohibition (`ORCHESTRATOR.md:27`); the irreversible-action set **excluding
    the superseded dev-entry item**; "state is read, not remembered"; the decision-authority rule
    (reversible + one sensible answer + recorded); and the duty to surface rather than silently
    reconcile a conflict.
20. `safety-core` enumerates the residual invariant set it binds over **before** stating the
    anti-circumvention rule, so that rule is not vacuous in a mode with no gates.
21. `safety-core` declares its own precedence over every mode body, and no mode body weakens a
    safety-core clause; a test asserts no mode body contradicts a safety-core anchor.
22. Each mode body is non-empty and mode-distinct; the dangerous body contains no maintainer-only
    framing and no `CODEARBITER_DEV` reference.
23. The persona injects once per (session, mode, compaction generation); a second turn in the same
    session and mode injects nothing, and a new session injects again.
24. After a flip, the next turn injects the new mode's body.
25. After a compaction, the next turn re-injects the current mode's persona.
26. `_prunepolicy` protects the injected persona entry from folding, condensing, and eviction at every
    tier including aggressive.
27. `SessionStart` injects no persona and still emits the startup-state block.
28. The composed persona for each mode fits Codex's per-hook `additionalContextLimit`, or the chosen
    behavior when it does not is specified and tested.
29. Every hook message's `§` citation resolves to a section present in the injected persona.

### Startup emitters
30. Each startup emitter is individually selectable and its output depends only on its own inputs.
31. Against a committed input fixture, the `arbiter` emitter set produces the same line set as the
    pre-change monolith; regenerating the fixture requires an explicit flag, never a bare overwrite.
32. A non-arbiter startup omits the await-a-command trailer, the catalog reference, and the standup
    reference, and still emits host, stage, and the active mode; the same fixture in `arbiter` emits all
    three omitted lines.

### Surface removal, rename, and readers
33. `/ca:dev` and `/ca:arbiter` are absent from all three generated host surfaces, and no surface
    references `{{CMD:dev}}`/`{{CMD:arbiter}}` or their rendered forms.
34. `check_badge_consistency.py` passes: command-count badge reads 38, every prose count echo matches,
    `COMMANDS.md` enumerates exactly the surviving command files, and the README catalog table drops both
    rows.
35. Running `clear_dev_marker` against a live-marker fixture emits an `overrides.log` line containing no
    deleted command name — asserted on the emitted line, not by source grep.
36. `_STALE_FLOWS` warns for a stale non-arbiter mode and never warns for `arbiter`.
37. `arbiter.md` is the injected arbiter body and its header records the former filename.
38. `_arbiterstatelib`, the statusline, and the Pi footer read the mode file; each of the three modes has
    a distinct tested rendering, `arbiter` unchanged from today and `dangerous` keeping the red-shift.
39. `test_pi_security.py`'s PI-SEC-FOOTER-TRUST contract is repointed to the mode reader and still fails
    on a seeded removal.
40. `override_rate` and the statusline override counter exclude `MODE:` and legacy `DEV:` rows.
41. A pre-existing `dev-active` marker converts to `dangerous` exactly once and is removed; a second run
    does not resurrect it after a flip to `arbiter`.
42. Downgrading to a pre-mode build leaves no un-closed audit pair and no orphaned state; the mode file
    is inert to that build.

### ops
43. `ops-mode.md` enumerates its permitted and refused sets, and a test binds those literal strings to
    the persona the injector emits.
44. The ops carve-out explicitly refuses irreversible action against anything outside this repo —
    infrastructure teardown, cluster or namespace deletion, package publication, live-database migration,
    volume destruction — and names the ambiguous cases (`npm test`, `npm ci`, `docker compose up`) with a
    verdict for each.
45. `includes/redirect.md` and `includes/routing-table.md` gain a runtime-operations entry naming the ops
    token, and a test binds the documented string to the interceptor's matched string across the catalog,
    redirect, and routing surfaces.

### Repo mechanics, docs, and record
46. `tools/sync-core.py --check`, `tools/build-surface.py --check`, `tools/build-host-packages.py
    --check`, `check-plugin-refs.py ca`, `check_docs_contract.py`, and
    `test_routing_and_cleanup_surface.py` all pass; `test_build_surface.py`'s fixture path is repointed.
47. `plugins/ca/.claude-plugin/plugin.json` advances with a matching README version badge and a dated
    `CHANGELOG.md` section; the `version-bump` gate passes.
48. `plugins/ca-pi/package.json`, the generated root `package.json`, and `plugins/ca-pi/CHANGELOG.md`
    advance together; the `version-bump-pi` gate passes.
49. `site/src/curated/commands/{dev,arbiter}.md` and their generated reference pages are removed, inbound
    `related:` refs are repaired, and the site generator, `npm test`, and the link audit pass.
50. No live `docs/`, `CONTRIBUTING.md`, or site surface states that `ORCHESTRATOR.md` is the always-on
    kernel, or names `/ca:dev`, `/ca:arbiter`, or `CODEARBITER_DEV` as current; a grep assertion fails on
    reintroduction.
51. Historical surfaces (`gate-events.log`, `decisions/`, `sprint-log.md`, published CHANGELOGs, the
    site changelog) are byte-unchanged.
52. `CONTEXT.md` names `mode` and its three values, string-equal to `_modelib`'s legal-value tuple.
53. An accepted ADR records: the arbiter-body reframe; the injection move off `SessionStart`; the narrow
    ADR-0022 supersession scoped to dangerous-mode entry with a resolving supersession chain; the
    unaudited-flip posture and its residual; the router fail-direction (ADR-0020 rebutted, not
    inherited); #247's precedence rule and frontmatter key, including that a committed profile may never
    default to a gates-off posture; and the ops deferral as *sequencing*, not ADR-0007 deference. The ADR
    is accepted before the flip ships.
54. A comment on #437 itemizes which of its eight acceptance criteria this change closes and which are
    deferred.
55. Every enforcement gate produces an identical `(returncode, tag)` for the whole existing
    `test_hook_guards.py` corpus in all three modes.

### End-to-end and cost
*(AC-56/57 added post-approval by `writing-plans` Phase 1's negative-judgment question — the ledger was
unit-level throughout and bounded no per-turn cost.)*

56. A live end-to-end run on each host proves the full path: typing the token flips the mode, the next
    turn's context carries the new mode's composed persona, and a subsequent turn does not re-inject.
    Verified against observed session behavior, not a self-report.
57. The interceptor's added per-turn cost is bounded and measured, including the AC-11 ledger read,
    against `UserPromptSubmit`'s 30-second timeout — with the audit log at its current size and an
    order-of-magnitude larger.

## Open questions

None blocking. `[CONFIRM-05]` is unrelated and untouched.

Rulings on record: `ops` is advisory-only, enforced by persona rather than hooks; the injector refuses a
mode the ledger does not back; the mode plane is session-scoped and session-cleared, with #247's
project-level plane documented but unimplemented; #437's supervision criteria are deferred as sequencing.
