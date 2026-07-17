---
status: accepted
date: 2026-07-13
title: The git-hook shim resolves either host's enforcer from a shared drop-in dir and fails closed
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/pysrc/_githooks.py, core/pysrc/session-start.py
---

# ADR-0014 — The git-hook shim resolves either host's enforcer from a shared drop-in dir and fails closed

## Status
Accepted — ratified 2026-07-13 by SUaDtL@users.noreply.github.com during the `pre-release-hardening`
sprint (`/ca:sprint`), resolving issue #265.

## Context
The `#161` git-level backstop installs a `pre-commit` / `pre-push` shim (`core/pysrc/_githooks.py`)
that execs the plugin's `git-enforce.py`. The shim embeds the enforcer by **absolute path**, resolved
from the installing plugin's own location, and is deliberately **fail-open**: `[ -f "$E" ] || exit 0`.

That fail-open was an accepted trade for a single plugin: `install()` re-runs every SessionStart, so a
version-bump path drift heals on the next session, and the brief window where the enforcer path is
stale should never brick a user's commits.

ADR-0011 added a second host. With both `ca` and `ca-codex` installed against one repo, each
SessionStart rewrites the shim to point at **whichever host ran last**. The two hosts keep separate,
independently versioned plugin caches, so neither can derive the other's absolute enforcer path. Issue
#265 (tribunal `reliability-009`) showed the consequence: **uninstall one plugin and the git-level
backstop is silently unwired for BOTH hosts** until the surviving host's next SessionStart — and if the
uninstalled plugin was the one the shim last pointed at, every commit in that window passes with no
git-level enforcement at all.

The `_githooks.py` header recorded this as accepted risk and **explicitly rejected** the two obvious
fixes: embedding multiple candidate paths ("requires knowing a path this file cannot derive") and a
runtime cache-glob from inside the POSIX `sh` shim ("an unverified, host-layout-guessing filesystem
search on every commit under Windows Git-Bash — a fragile git-level backstop is worse than the accepted
trade"). Crucially, that same header named its own exit condition: *revisit only if a host-neutral,
version-independent enforcer location becomes available (e.g. a shared non-versioned shim target).*

That target now exists. This decision does not override the header's rejection — it satisfies the
condition the header itself set for revisiting.

## Decision
Each host's `install()` registers its own current enforcer path into a shared, non-versioned drop-in
directory inside the repo's own `.git/`:

```
.git/codearbiter-hooksd/<plugin>.path      # e.g. ca.path, ca-codex.path
```

The shim iterates that directory and execs the **first** enforcer path that resolves:

```sh
for c in "$D"/*.path; do
    E=$(cat "$c" 2>/dev/null) || continue
    [ -f "$E" ] && exec "$PY" "$E" <phase>
done
# nothing resolved:
```

...and when nothing resolves, the shim **fails closed** — non-zero exit with a diagnostic message,
rather than `exit 0`.

This is a read of a directory **codeArbiter itself owns**, inside `.git/` (where `_githooks.py` already
writes its hooks-dir cache), populated by each host writing its own path. It is not the rejected
host-layout guess: no plugin has to derive a sibling's path, and there is no glob of an unknown cache
root. Each host refreshes its own `<plugin>.path` on every SessionStart, so a live host self-heals a
stale entry; `uninstall()` removes only its own `.path` file.

## Alternatives considered
- **Keep fail-open, ship the drop-in dir only.** Fixes the cross-plugin discovery symptom (both
  enforcers become resolvable) while preserving "never brick a commit over our own path drift."
  Rejected: a genuinely broken or fully-uninstalled install would still enforce nothing, silently, and
  a release should not ship a security backstop whose failure mode is invisible. The whole point of the
  #161 backstop is to catch the case where the higher layers are absent; a backstop that fails open in
  exactly that case is not a backstop.
- **Keep the accepted risk, close #265 won't-fix.** Rejected: the exit condition the original header
  set has been met, so the trade that justified the risk no longer holds.
- **Multiple-candidate path embedding / runtime cache glob.** Already rejected by the prior header and
  not revived — the drop-in dir is strictly better than both.

## Consequences
- Removing one of two installed plugins leaves the git-level backstop wired to the survivor; removing
  all of them makes the next commit **block** with a clear message rather than pass silently.
- The `_githooks.py` header block (the ADR-of-record for the fail-open behavior) is rewritten to point
  at this ADR and describe the drop-in dir and the fail-closed contract.
- The behavior change has a real blast radius: a state where **no** enforcer resolves now blocks
  commits where it previously allowed them. This is the intended direction — a security backstop should
  fail safe — and the drop-in dir bounds it, since any one live host keeps its own entry fresh.

## Risks
- **Stale entry from an uninstalled plugin.** A removed plugin leaves its `<plugin>.path` behind; the
  shim's `[ -f "$E" ]` test on that dead path simply fails and the loop moves on, so a stale entry is
  inert, not a hazard. `uninstall()` drops its own entry when it runs, but plugin removal does not
  reliably invoke it — hence the `-f` guard is the real safety, not the reaper.
- **A repo with the drop-in dir but no live SessionStart** (e.g. a bare CI checkout that never runs the
  hook) would find no `.path` entries and block. This is the fail-closed contract working as designed;
  environments that must not run the backstop should not install the shim.
- Relates to ADR-0011 (multi-host shared core) and the fail-closed posture of the `#161` backstop.
  This decision is proven wrong if the fail-closed shim blocks legitimate commits in a common,
  non-broken configuration that the test matrix did not anticipate.
