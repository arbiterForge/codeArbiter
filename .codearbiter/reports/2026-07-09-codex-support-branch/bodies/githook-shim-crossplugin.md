# Dual-host git-hook shims fail open when one plugin is uninstalled

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** low  |  **Confidence:** 0.75  |  **Group:** githook-shim-crossplugin

**Where:**
- `core/pysrc/_githooks.py:122-137`
- `core/pysrc/_githooks.py:297-372`
- `core/pysrc/session-start.py:570-576`

**Evidence / impact:**
- (reliability-009) The pre-commit/pre-push shim embeds the ABSOLUTE enforcer path of whichever plugin last ran SessionStart (`E="{enforcer}"` from `_enforcer_path()` = this vendored copy's dir), and the shim is deliberately fail-open when that file is missing: `[ -f "$E" ] || exit 0`. With ca and ca-codex both installed against one repo, every alternation of host rewrites both shims (plus the .git/codearbiter-hooksd
- (reliability-009 impact) A window (potentially long, e.g. Codex-was-last-used then only git CLI is used) where the #161 git-level enforcement backstop is silently unwired for BOTH hosts after removing ONE plugin. The single-plugin fail-open was an accepted 'our OWN staleness' trade; dual-host widens it to a cross-plugin dep

**Recommendation:**

The pre-commit/pre-push shim embeds the last-writing plugin's absolute enforcer path and is fail-open when it is missing. Make the shim resolve either installed plugin's enforcer, or fail closed, so removing the BETA ca-codex does not silently unwire the git-level backstop for both hosts.

**Acceptance criteria:**
- Uninstalling one of two installed plugins leaves the git-level enforcement wired to the survivor, or the commit is blocked, not passed.

<!-- dedup_key: reliability:core/pysrc/_githooks.py:cross-plugin-shim-fail-open · findings: reliability-009 -->
