---
description: Tear down a sandbox box — remove its container and named volume. --keep-volume leaves the volume; with no id, prune reclaims any leaked ca.sandbox=1-labeled object. Cached images are retained.
argument-hint: "[<sandbox id>] [--keep-volume] [--prune]"
---

# /ca-sandbox:sandbox-destroy — tear the box down

A sandbox is ephemeral by contract, and this is how it ends. Destroy removes the container and its
named volume, leaving zero `ca.sandbox=1`-labeled objects behind — the cleanup that makes "explore, then
burn" real. Cached images (`ca-sbx:<repo>-<dephash>`) are intentionally retained so the next `create`
from the same repo is a cache hit.

`--keep-volume` leaves the volume in place for a deliberate re-run. `--prune` (or invoking with no id)
reclaims any leaked labeled object — the safety net for a box whose driver died mid-run.

## Flow

1. **Resolve the target** — the box id to destroy, or `--prune` / no-id to sweep all leaked
   `ca.sandbox=1` objects.
2. **Destroy** — call `destroySandbox` in `${CLAUDE_PLUGIN_ROOT}/tools/destroy.ts`: remove the
   container, then its named volume (unless `--keep-volume`).
3. **Prune leaks** — `prune` in `${CLAUDE_PLUGIN_ROOT}/tools/destroy.ts` finds and removes any
   remaining labeled container/volume via the `ca.sandbox=1` label alone.
4. **Confirm** — report what was removed and what was retained (cached images, a kept volume).

## Routes to

`sandbox-lifecycle` (`${CLAUDE_PLUGIN_ROOT}/skills/sandbox-lifecycle/SKILL.md`) — Phase 5 (teardown),
via `destroySandbox` and `prune` in `${CLAUDE_PLUGIN_ROOT}/tools/destroy.ts`.

## When NOT to use

- Still exploring the box → `/ca-sandbox:sandbox-shell`, `/ca-sandbox:sandbox-exec`.
- Pulling a file out before teardown → `/ca-sandbox:sandbox-cp`.
- Standing a new box up → `/ca-sandbox:sandbox`.

## Hard gate

- MUST leave zero `ca.sandbox=1`-labeled containers or volumes after a destroy (cached images excepted),
  unless `--keep-volume` is set.
- MUST be able to reclaim a leaked labeled object via the `ca.sandbox=1` label alone (`prune`); a leaked
  box MUST NOT be unrecoverable.
- MUST retain cached `ca-sbx:<repo>-<dephash>` images — teardown removes containers and volumes, not the
  build cache.
- MUST NOT touch any object not labeled `ca.sandbox=1`; destroy operates only on this plugin's objects.
