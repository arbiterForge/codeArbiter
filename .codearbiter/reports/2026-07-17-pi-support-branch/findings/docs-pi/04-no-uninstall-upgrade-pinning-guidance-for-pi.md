# 04 — No uninstall/upgrade/version-pinning guidance for ca-pi on the site

**Severity:** medium

**Page path:** `site/src/content/docs/guides/uninstalling.md` (existing page,
0 mentions of Pi).

**What the user was trying to do:** After installing `ca-pi` via
`pi install git:arbiterForge/codeArbiter@ca-pi-v<version>`, the user wants to
upgrade to a newer `ca-pi` tag, pin to a specific version, or uninstall it
later — mirroring what the Claude Code/Codex sections of this same guide
presumably cover.

**What's missing:** The existing `guides/uninstalling.md` page covers
uninstall/disable but has zero Pi content. Facts that exist only in
`README.md` (lines 113–130, 469–470) and are absent from the site:
- `ca-pi` is distributed Git-only and versioned independently as
  `ca-pi-v<version>` tags (not tied to the `ca`/`ca-codex` release cadence).
- Upgrade = re-running `pi install git:...@ca-pi-v<new-version>` with a new
  pinned tag (no auto-update / no npm registry).
- Uninstall = `pi remove` with the pinned Git source; `.codearbiter/` state
  survives so another governance host can pick it up.
- `README.md` explicitly states "no npm release" for ca-pi (per
  `test_public_pi_docs.py::test_release_docs_keep_preview_and_future_work_explicit`) —
  a user who assumes `npm install` or an app-store-style auto-update will be
  stuck.

**Remediation shape:** Add a Pi subsection to `guides/uninstalling.md`
covering pin/upgrade via re-running `pi install ...@ca-pi-vX.Y.Z`, `pi
remove` for uninstall, and an explicit "no npm packaging yet" callout.
