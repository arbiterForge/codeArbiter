# 06 — Troubleshooting guide has no Pi-specific failure modes

**Severity:** medium

**Page path:** `site/src/content/docs/guides/troubleshooting.md` (existing
page, 0 mentions of Pi).

**What the user was trying to do:** After installing `ca-pi`, the user hits
one of several plausible Pi-specific failure states and looks in the site's
troubleshooting guide, as they would for a Claude Code/Codex issue.

**What's missing:** Known Pi-specific failure modes documented only in
`plugins/ca-pi/includes/pi-host-notes.md` / `README.md` are absent from the
troubleshooting page:
- Enforcement stays dormant if the repo lacks an enabled
  `.codearbiter/CONTEXT.md`, or if project trust hasn't been granted, or the
  session isn't fresh after granting trust — three distinct silent-inactivity
  causes a new user could easily hit and not distinguish.
- Missing Python 3 on `PATH`: per README's Prerequisites section (asserted by
  `test_public_pi_docs.py::test_missing_python_failure_direction_is_not_documented_as_silent`),
  this "blocks mutating calls" and surfaces an "interpreter breadcrumb" rather
  than failing silently — but a user who hasn't read the root README won't
  know to look for that breadcrumb or what it looks like.
- `/ca-doctor` is the diagnostic entry point on Pi (module-identity,
  supported-version fingerprint, child fingerprint, H-03 wrapper self-test)
  but isn't mentioned as a first troubleshooting step anywhere on the site.
- Command invocation confusion: Pi uses `/ca-<name>` generated aliases with
  `/skill:ca-<name>` as host-native fallback — different from Codex's
  `$ca-<name>` convention. A user coming from Codex docs (if they existed on
  the site) or guessing syntax could easily use the wrong prefix.

**Remediation shape:** Add a "Pi" section to `guides/troubleshooting.md`
covering: dormant-until-trusted/fresh-session states, the Python-on-PATH
breadcrumb, `/ca-doctor` as the first diagnostic step, and the `/ca-<name>` vs
`/skill:ca-<name>` command-invocation syntax.
