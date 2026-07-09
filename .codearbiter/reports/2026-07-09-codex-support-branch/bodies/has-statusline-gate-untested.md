# session-start has_statusline gate is not exercised end-to-end under a Codex host

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** med  |  **Confidence:** 0.8  |  **Group:** has-statusline-gate-untested

**Where:**
- `core/pysrc/session-start.py:539-557`
- `plugins/ca/hooks/tests/test_session_start.py:187-260`
- `.github/scripts/test_codex_adapter.py:118-125`

**Evidence / impact:**
- (coverage-004) session-start.py:556-557 gates `heal_statusline_wiring(plugin)` on `if host.has_statusline:` inside main() (host = hostapi.load_host() at line 541) — this is the only call site of that capability flag. Two test units touch the pieces but neither exercises the gate itself: (1) test_codex_adapter.py:118-125 (test_name_and_capabilities) only asserts `self.assertFalse(self.host.has_statusline)` on the
- (coverage-004 impact) The one production call site that actually depends on has_statusline being correct (skipping a statusline self-heal that would be a no-op-at-best, or write globally to ~/.claude/settings.json for a host with no statusline surface, at worst) is unverified; a refactor that drops or inverts the `if hos

**Recommendation:**

Add an end-to-end main() test asserting session-start skips the statusline heal when host.has_statusline is False.

**Acceptance criteria:**
- A test drives session-start.main() under a has_statusline=False host and asserts the statusline path is skipped.

<!-- dedup_key: coverage:core/pysrc/session-start.py:has-statusline-gate-untested · findings: coverage-004 -->
