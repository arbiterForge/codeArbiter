# Shared-core pre-edit.py branches on Claude-native tool names, bypassing the seam

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** low  |  **Confidence:** 0.75  |  **Group:** pre-edit-native-names

**Where:**
- `core/pysrc/pre-edit.py:53-56`
- `core/pysrc/pre-edit.py:86-92`
- `core/pysrc/pre-edit.py:119-122`
- `core/pysrc/hostapi.py:108-111`

**Evidence / impact:**
- (architecture-008) hostapi.py establishes canonical tool categories ('EXEC|WRITE|EDIT|READ|OTHER') as the seam every shared entry should reason through, and pre-edit.py imports get_host()/normalize_tool_input — yet its guard logic branches on raw native names: `if tool == "MultiEdit"` (lines 53, 119), `if tool == "NotebookEdit"` (line 86). The escape is rationalized in a comment ('Codex does not register this entry 
- (architecture-008 impact) Latent third-host bug and pattern drift: any future host that registers this entry (or a Codex change routing edits through it) gets guard semantics keyed to another host's tool names — MultiEdit-batch and NotebookEdit refusals silently never fire, weakening H-05/H-18 on that host with no signal. It

**Recommendation:**

Route pre-edit.py's `MultiEdit`/`NotebookEdit` branches through normalize_tool categories so a future host that registers this entry cannot silently lose H-05/H-18.

**Acceptance criteria:**
- No shared-core file branches on a raw native tool name; guard decisions flow through the seam's canonical categories.

<!-- dedup_key: architecture:core/pysrc/pre-edit.py:native-tool-name-branches · findings: architecture-008 -->
