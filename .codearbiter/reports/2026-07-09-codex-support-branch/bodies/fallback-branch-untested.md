# CodexHost non-patch-tool defensive fallback branch is untested

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** low  |  **Confidence:** 0.75  |  **Group:** fallback-branch-untested

**Where:**
- `plugins/ca-codex/hooks/_host.py:243-247`
- `.github/scripts/test_codex_adapter.py:252-260`

**Evidence / impact:**
- (coverage-002) CodexHost.iter_file_ops has TWO separate 'defer to super().iter_file_ops()' defensive branches: one inside `if tool in self._PATCH_TOOLS:` (_host.py:240-241, exercised by test_claude_shaped_fallback at test_codex_adapter.py:252-260, which passes tool_name='Write' — a member of _PATCH_TOOLS), and a SECOND, distinct one for tools NOT in _PATCH_TOOLS (_host.py:243-247: 'Non-write tools carry no file 
- (coverage-002 impact) Low likelihood (mcp tools rarely carry file_path) but this is the second of two structurally-similar fallback branches guarding against an unhandled-but-file-shaped payload reaching disk unguarded; only one of the two is verified to actually route to the base guarded-write mapping instead of silentl

**Recommendation:**

Add a fixture for CodexHost.iter_file_ops' non-patch-tool fallback (an mcp__*/OTHER payload carrying file_path).

**Acceptance criteria:**
- A test exercises the _host.py:243-247 branch.

<!-- dedup_key: coverage:plugins/ca-codex/hooks/_host.py:non-patch-tool-fallback-untested · findings: coverage-002 -->
