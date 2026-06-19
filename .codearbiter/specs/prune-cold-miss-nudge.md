# Spec: prune cold-miss nudge

**Source:** GitHub issue #69 (`enhancement,prune`). Brainstormed 2026-06-18; all six
issue open-questions resolved (see Decisions). Feature Forge: ships under the
`preview` gate, same as live pruning.

## Problem

When the prompt cache TTL (~5 min, refreshed on each cached read) lapses, the next
submit pays an unavoidable full re-cache **write** (~1.25×) on the entire **in-memory**
context. A running session streams in-memory history to the API, not the on-disk
transcript — so prune savings banked in the file only materialize when context is
rebuilt from disk (`--resume` or compaction). Today the user gets no signal at the one
moment where acting changes the bill: they can let the re-cache land on **bloated**
context, or `/compact` / exit+`--resume` to land that same write on **pruned** context.

**Caller:** a user running `CODEARBITER_PRUNE=on` who has opted into the nudge, returning
mid-session after an idle stretch with a large banked prune delta. "Done" = they are told,
**once**, before the cold submit, and can act or override by resubmitting.

## Scope

**In:**
- A new arming check in `plugins/ca/hooks/_prunelib.py`'s `hook_run` (the `UserPromptSubmit`
  path) that, when all conditions hold, **blocks the submit once** with an advisory.
- A pure, injectable decision helper (`nudge_decision(...)`) that hook_run calls — the
  unit-testable surface, stdlib-only, consistent with the existing pure-function + thin-hook
  structure.
- The block is the **first non-zero exit path** in a hook that otherwise always returns 0.
  It MUST be the rare, well-gated exception: any error or uncertainty fails open (returns 0).
- New env gate + thresholds (all default-safe, see Decisions).
- Docs: `/ca:prune` doc + the preview / Feature-Forge note describe the nudge and its env gate.

**Out of scope (NOT this feature):**
- Auto-restarting the CLI / re-attaching the TTY — a hook cannot relaunch the host. The
  action stays the user's (`/compact`, exit + `--resume`).
- Predicting cache hit/miss exactly — no API cache-state query exists; we approximate from
  local signals (banked delta + idle time).
- Touching the live transcript beyond the existing prune; intercepting a warm cache *hit*
  (a warm read is the cheap state — never interrupt it).
- Any nudge in `dry`/`off` mode or on a non-aggressive/non-armed submit.
- `[NEEDS-TRIAGE]` **dry-mode "you'd save X if on" informational nudge** — deferred. In dry
  mode nothing is banked (disk isn't pruned), so a resume reloads the same size; that message
  is a different (marketing) nudge, not this one.
- `[NEEDS-TRIAGE]` **statusline tie-in** — a passive delta+staleness statusline hint is
  independently shippable from the submit-time block; deferred to a follow-up.

## Decisions (issue open-questions, resolved)

1. **Gate = dedicated flag, default off.** `CODEARBITER_PRUNE_NUDGE=on`, independent of
   `CODEARBITER_PRUNE_TIER`. The block is a distinct UX behavior from pruning depth; a
   separate opt-in keeps it rare, well-gated, and off by default (preview).
2. **Hard block once, override on resubmit.** Armed → `hook_run` returns `2` with the advisory
   on **stderr**; a per-session `cold_nudged` marker in `prune-state.json` makes the immediate
   resubmit proceed (returns 0). Chosen over a non-blocking injected advisory because it owns
   the one decision moment; safety is preserved by the strict arming gate + fail-open.
3. **Cadence = once per cold window.** The `cold_nudged` marker is set when the nudge fires
   and **cleared on any warm submit** (idle < idle-floor), so the next genuine cold window
   re-arms. No arbitrary turn counter.
4. **Banked-delta proxy = last run's `freed_bytes`** from `prune-state.json` (the issue's
   "projected freed_bytes/pct from the last run"). Approximate by design.
5. **Idle signal = now − last assistant-turn `timestamp`** from the transcript tail. Optional
   corroboration from the last turn's `message.usage.cache_*` fields is a non-required nicety.
6. **Thresholds (env-overridable defaults):**
   - `CODEARBITER_PRUNE_NUDGE_MIN_TOKENS` = `80000` — floor on est-tokens freed
     (`est_tokens(freed_bytes)`), below which the nudge is noise.
   - `CODEARBITER_PRUNE_NUDGE_IDLE_SECS` = `240` — idle floor (~approaching the ~5 min TTL);
     a submit after this gap is treated as probably-cold. Heuristic; TTL is not queryable.

## Behavior

Advisory (sizes/tokens/percent/time only — never transcript content):

> Cold cache miss imminent on ~140k tokens. `/compact` or exit + `--resume` lands that
> re-cache on pruned context (~40% smaller). Submit again to proceed.

Arming (ALL must hold): mode is `on` · `CODEARBITER_PRUNE_NUDGE=on` · est-tokens(freed_bytes)
≥ MIN_TOKENS · idle ≥ IDLE_SECS · `cold_nudged` not already set for this cold window. The
nudge is evaluated even when this turn's prune would short-circuit on insufficient growth
(an idle user adds no bytes but is exactly who should be nudged); the `cold_nudged` flag
change is persisted regardless. When armed, hook_run blocks **before** pruning this turn —
the bank is already on disk from a prior run; the override resubmit proceeds to the normal path.

## Acceptance criteria

Each is verifiable by a single test (one `tdd` Phase 1 obligation each). Idle/state-driven
tests use synthetic transcript tails (timestamps) + synthetic `prune-state` records, with an
injectable `now`. New fixtures carry top-level `timestamp` (the live synthetic fixture omits it).

1. **Flag off → silent.** `nudge_decision` returns not-armed when `CODEARBITER_PRUNE_NUDGE`
   is unset or ≠ `on`, even if every other condition holds.
2. **Wrong mode → silent.** `hook_run` reaches the nudge only in `on` mode; in `off`/`dry`
   it returns 0 and never blocks.
3. **Small delta → silent.** Not-armed when `est_tokens(freed_bytes)` < `MIN_TOKENS`
   (default 80000).
4. **Warm session → silent.** Not-armed when idle (now − last-assistant `timestamp`) <
   `IDLE_SECS` (default 240).
5. **All conditions hold → armed.** Returns a block decision carrying the advisory string.
6. **Blocked exactly once.** A second evaluation with `cold_nudged` already set returns
   not-armed — the override resubmit proceeds.
7. **Once per cold window.** A warm evaluation (idle < floor) clears `cold_nudged`, so a
   subsequent cold window arms again.
8. **Fail-open always.** Any internal error (malformed transcript, missing timestamp, bad
   state) yields not-armed; `hook_run` returns 0 — never 2 on a pruner fault.
9. **Privacy.** The advisory contains only sizes / est-tokens / percent / time — asserted to
   be derived from state numbers, with no transcript text (consistent with the dry-metrics
   privacy stance).
10. **hook_run integration.** Armed → `hook_run` returns `2` with the advisory on stderr and
    skips this turn's prune; non-armed → returns 0 and the existing prune behavior is
    unchanged (verified: flag-off run is byte-identical to today).
11. **Docs updated.** The `/ca:prune` doc and the preview / Feature-Forge note describe the
    nudge and name its env gate (`CODEARBITER_PRUNE_NUDGE` + the two threshold vars) —
    verifiable by asserting the doc text references `CODEARBITER_PRUNE_NUDGE`.

## Open questions

None blocking. The two deferred items (dry-mode marketing nudge, statusline tie-in) are marked
`[NEEDS-TRIAGE]` in Scope above — future scope, not routed to a ticket.

## Implementation notes

- Entry: `plugins/ca/hooks/_prunelib.py` → `hook_run` (already wired to `UserPromptSubmit`
  via `prune-transcript.py:123`, which `sys.exit()`s the return). Block = return `2` +
  advisory on stderr; allow = return `0`.
- New state fields in `prune-state.json` per session: `cold_nudged` (bool). Reuses existing
  `freed_bytes`, `pct`, `last_pruned_size`, `last_run_ts`.
- New env: `CODEARBITER_PRUNE_NUDGE`, `CODEARBITER_PRUNE_NUDGE_MIN_TOKENS`,
  `CODEARBITER_PRUNE_NUDGE_IDLE_SECS` (wire through `Config.from_env` or read in the helper).
- Tests under `plugins/ca/hooks/tests/` (mirror `test_prune_cli.py` / `test_hook.py` style);
  register any new test entry in `tech-stack.md`'s test list if it must run in the commit gate.
- Release: any `plugins/ca/**` change on a tagged version bumps `plugin.json` version (CI
  `version-bump`), and the version rides in plugin.json + README badge + CHANGELOG.
