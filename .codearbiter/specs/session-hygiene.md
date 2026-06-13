# Sprint spec: session-hygiene

**Status:** APPROVED — 2026-06-13 (user: brennonhuff@gmail.com); executing
**Backend:** premium (no `--farm`)
**Build order:** Feature 1 (standup-hygiene) → Feature 2 (pr-babysitter)

## Sprint goal

Buckle up day-to-day workflow hygiene ahead of the Anthropic marketplace
submission: give arbiter a read-only morning briefing + a gated cleanup command,
and a token-efficient PR babysitter that watches CI, diagnoses red, and offers
(never takes) the merge.

## Work units (the approved feature specs are authoritative)

1. `specs/standup-hygiene.md` — SessionStart read-only briefing + background fetch +
   gated `/ca:standup`. APPROVED 2026-06-13.
2. `specs/pr-babysitter.md` — `/ca:watch <PR>` on `gh pr checks --watch`, on-red
   diagnose (depth `propose`|`branch`), on-green notify + offer, global flag.
   Approved into this sprint 2026-06-13.

Acceptance criteria are NOT restated here — the two feature specs hold them (10
each). This sprint spec governs intent, priorities, and the autonomy steers.

## Priorities & risk tolerance (governs "deciding as the user")

- **Tie-break posture: BALANCED.** Meet every acceptance criterion plus obvious,
  cheap hardening (error paths, Windows/macOS/Linux edge cases). Skip speculative
  config surface and gold-plating. Break SMARTS ties toward this posture; failing
  that, toward the ORCHESTRATOR §2 conflict hierarchy.
- **Scope is locked** to the two specs as written. No additions mid-sprint without
  a stop.
- **Marketplace-readiness is the why:** prefer the smallest mergeable, well-tested
  slice over breadth.

## Explicit "decide it this way" steers

- **Hook discipline:** the SessionStart briefing MUST stay read-only and MUST NOT
  block on the network — mirror the existing `session-start.py` dormancy/gating and
  the documented plain-stdout injection pattern; never convert it to a mutating
  hook.
- **Flag pattern:** the global babysitter on/off flag mirrors `CODEARBITER_PRUNE`
  exactly — an env var, default **off**, read once in a lib function, two-layer
  gated against `arbiter_active(root)`, and NEVER auto-enabled by any command.
- **No auto-merge, ever** — green → notify + offer; merge-to-default remains a §3
  hard-gate stop even behind the flag.
- **Reuse, don't reinvent:** the briefing reuses the overrides-since-checkpoint /
  task / question computations already in `statusline.py` (`arbiter_state`) and the
  git-state reads (`head_branch`, `git_dirty`); factor shared pure logic into a
  testable helper rather than duplicating.
- **Test idiom:** stdlib `unittest` under `plugins/ca/hooks/tests/`, env injected
  via `env=` dicts (never mutate `os.environ`), hyphenated scripts loaded via
  `importlib` per the existing test convention.

## Release invariants (carried to Phase 3 landing)

- Changes under `plugins/ca/**` require a version bump (CI-enforced). Target
  `2.1.0-beta.3` → `2.1.0-beta.4`, synced across `plugin.json`, README badge, and a
  dated `CHANGELOG.md` section.
- All CI parity checks green before landing: hook-guard matrix, cold-install
  matrix, `check-plugin-refs.py`, JSON manifest parse, `py_compile` on touched
  hooks. (No `plugins/ca/tools/**` change is planned, so the vitest/typecheck leg
  is not triggered — confirm at landing.)

## Anticipated hard gates

None expected during execution — no crypto/secrets/auth/security-controls surface,
no irreversible op (ff-only pull on a clean tree; deletion limited to
already-merged branches/worktrees). The single hard gate is Phase 3
**merge-to-default**, which is auto-deferred to an open PR for the user to merge.
If hard gates trip repeatedly, that is a spec-thinness signal to surface, not grind
past.

## Open questions

None blocking. No `[CONFIRM-NN]` carried into autonomy.
