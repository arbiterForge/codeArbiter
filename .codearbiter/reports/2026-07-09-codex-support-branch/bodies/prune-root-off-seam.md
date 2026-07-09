# prune-transcript resolves root off-seam, silently dropping the CONFIRM-09 staleness WARN

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** low  |  **Confidence:** 0.8  |  **Group:** prune-root-off-seam

**Where:**
- `core/pysrc/prune-transcript.py:41-59`

**Evidence / impact:**
- (reliability-006) `root = payload.get("cwd") or os.getcwd()` then `if not _hooklib.arbiter_active(root): return`. This is the one shared-core call site that bypasses the host seam's project_root entirely: no CLAUDE_PROJECT_DIR (Claude), no git-toplevel resolution (either host). A session whose cwd is a subdirectory of the repo reads `<subdir>/.codearbiter/CONTEXT.md`, gets enabled=False, and the audit-staleness WAR
- (reliability-006 impact) WARN-only control lost without signal in exactly the sessions most likely to have drifted state (subdir/nested-cwd sessions); the two hosts and the other 15 entries all resolve root differently from this one, so behavior is inconsistent across hooks in the same session.

**Recommendation:**

Route prune-transcript staleness_check's root resolution through the host seam's project_root instead of raw payload cwd, so a subdir-cwd session does not silently lose the audit-staleness WARN.

**Acceptance criteria:**
- prune-transcript resolves root the same way the other entries do; the WARN fires in a subdir session with stale state.

<!-- dedup_key: reliability:core/pysrc/prune-transcript.py:staleness-root-raw-cwd · findings: reliability-006 -->
