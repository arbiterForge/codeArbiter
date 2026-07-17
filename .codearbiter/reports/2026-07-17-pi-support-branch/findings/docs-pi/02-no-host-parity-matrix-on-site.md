# 02 — No host-parity matrix (statusline/farm/sandbox/subagent dispatch) on the site

**Severity:** high

**Page path:** missing page. Repo root `docs/parity.md` contains the canonical
`<!-- PI-EXCEPTIONS:START -->...END -->` ledger (SUPPORTED/DEGRADED/
HOST-IMPOSSIBLE/PREVIEW rows, enforced by
`.github/scripts/test_public_pi_docs.py::test_every_pi_exception_has_status_and_evidence`),
but nothing under `site/src/content/docs/` republishes or links to it. The
site's `getting-started/compatibility.md` page (in the nav, "Compatibility")
has zero Pi mentions.

**What the user was trying to do:** Before committing to Pi as a host, or
while debugging a missing feature, the user wants to know what differs on Pi
vs. Claude Code/Codex — e.g. does the statusline work, does `/ca:sprint
--farm` work, how does subagent dispatch differ.

**What's missing:** The site's "Compatibility" page is the obvious place for
this and currently says nothing about Pi. Known deltas that a site user needs
and currently only exist in `plugins/ca-pi/includes/pi-host-notes.md` /
`docs/parity.md` / `README.md`:
- Pi has no statusline replacement — `README.md` line 241 says "Pi omits only
  `statusline`"; `pi-host-notes.md` says Pi status uses
  `ctx.ui.setStatus` and "does not replace Pi's complete footer."
- `--farm` stays at `preview` level on Pi, calling the same checked-in
  `plugins/ca/tools/farm.js`; no Pi-native farm worker ships
  (`pi-host-notes.md`, `README.md` lines 434–436).
- Subagent/child dispatch model differs: fresh child Pi processes via
  `codearbiter_dispatch` (parent-only EXEC tool), with single/chain/parallel
  modes sharing bounded depth, concurrency, timeout, cancellation, and
  process-tree cleanup (`pi-host-notes.md`).
- `/ca:prune` on Pi uses native compaction instead of rewriting session JSONL.

None of this appears on `site/src/content/docs/getting-started/compatibility.md`
or anywhere else on the site.

**Remediation shape:** Add a Pi row/section to the site's Compatibility page
(and/or a "Host differences" table) sourced from `docs/parity.md`'s exception
ledger and `plugins/ca-pi/includes/pi-host-notes.md`, covering statusline,
farm/preview, subagent dispatch, and prune/compaction at minimum.
