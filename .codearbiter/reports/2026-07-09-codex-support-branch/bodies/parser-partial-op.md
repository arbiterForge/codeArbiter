# Codex apply_patch fail-closed backstop is whole-envelope, not per-directive

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** med  |  **Confidence:** 0.7  |  **Group:** parser-partial-op

**Where:**
- `plugins/ca-codex/hooks/_host.py:116-145`
- `plugins/ca-codex/hooks/_host.py:229-242`
- `.github/scripts/test_codex_adapter.py:237-260`

**Evidence / impact:**
- (appsec-001) parse_apply_patch skips any line inside a recognized envelope that it does not classify as one of the four markers (Add/Delete/Update/Move) — docstring L80-82 and the trailing `# ... skipped` at L143. iter_file_ops only substitutes the fail-closed 'opaque' op when the parse yields ZERO ops (L232-239: `if ops: return ops` else opaque). So a patch that produces >=1 recognized op while silently dropp
- (appsec-001 impact) IF any supported Codex apply-patch version (min rust-v0.134.0; verification was only against 0.143.0) recognizes a `*** `-directive spelling this Python mirror does not, and applies a write to a protected path, pre-write.py's H-18/H-19/H-05/H-11 guards never see that op and the whole-envelope opaque
- (coverage-001) parse_apply_patch's line loop (core logic at plugins/ca-codex/hooks/_host.py:116-145) silently skips any line that doesn't match a recognized marker (`_flush` only ever runs at a recognized _ADD/_DELETE/_UPDATE boundary or at end-of-text) — an unrecognized '*** ' directive INSIDE an otherwise-valid envelope neither aborts parsing nor contributes an op; it is just dropped, and iter_file_ops' fail-c
- (coverage-001 impact) A Codex apply_patch envelope containing one ordinary file op plus one directive shape the adapter doesn't recognize (a parser-grammar drift, a future Codex directive, or an adversarial envelope crafted to exploit the gap) returns a non-empty, seemingly-valid ops list — the fail-closed opaque guard n

**Recommendation:**

In parse_apply_patch/iter_file_ops, trip the fail-closed 'opaque' op on ANY unrecognized '*** ' directive line inside a recognized envelope, not only when the whole parse yields zero ops. Add the missing fixture (coverage-001) for a partially-recognized envelope.

**Acceptance criteria:**
- An envelope mixing a recognized Add/Update op with an unrecognized '*** ' directive (e.g. '*** Copy File:') yields an opaque/blocking op, not a partial allow.
- A fixture covers the mixed recognized+unrecognized envelope case.

**Folds (same root cause / corroborating findings):** appsec-001, coverage-001

<!-- dedup_key: appsec:plugins/ca-codex/hooks/_host.py:opaque-net-whole-envelope · findings: appsec-001, coverage-001 -->
