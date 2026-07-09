# ca-codex ships ~15 unreachable entry scripts and a broken /ca-init first-run pointer

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** med  |  **Confidence:** 0.8  |  **Group:** dead-vendored-entries

**Where:**
- `plugins/ca-codex/hooks/hooks.json:1-70`
- `plugins/ca-codex/.codex-plugin/plugin.json:5`
- `tools/sync-core.py:41-50`

**Evidence / impact:**
- (architecture-005) hooks.json registers exactly 5 entries (session-start, pre-bash, pre-write, post-write-edit, prune-transcript). The plugin ships no commands/, skills/, or agents/ (`ls plugins/ca-codex/` = hooks + ORCHESTRATOR.md + manifest). Yet sync-core.py vendors ALL 42 core .py files, so statusline.py, wire-statusline.py, pre-read.py, pre-edit.py, git-enforce.py, doctor.py, preview.py, metrics.py, taskwrite.p
- (architecture-005 impact) Dead code masquerading as live: two-thirds of the shipped Codex payload is unreachable, inflating the trust-review surface users must approve and blurring which files are enforcement-bearing. The /ca-init pointer is a broken first-run path for the shipped beta: an installing user cannot follow the m

**Recommendation:**

Capability-gate or trim the vendored payload so ca-codex does not ship ~15 non-registered enforcement scripts as trust-surface bloat, and fix the manifest first-run pointer (it names a /ca-init that ca-codex does not ship).

**Acceptance criteria:**
- ca-codex's shipped payload contains only files reachable on that host, or unreachable ones are clearly marked.
- The manifest's documented first-run command exists in the shipped plugin.

<!-- dedup_key: architecture:plugins/ca-codex:dead-vendored-entries · findings: architecture-005 -->
