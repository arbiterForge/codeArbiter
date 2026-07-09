# ORCHESTRATOR.md is hand-duplicated across plugins with no sync mechanism

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** med  |  **Confidence:** 0.85  |  **Group:** orchestrator-duplicated

**Where:**
- `plugins/ca-codex/ORCHESTRATOR.md:1-147`
- `tools/sync-core.py:30-38`

**Evidence / impact:**
- (architecture-010) plugins/ca/ORCHESTRATOR.md and plugins/ca-codex/ORCHESTRATOR.md are currently byte-identical (147 lines, `diff` empty), but nothing keeps them so: sync-core.py handles only core/pysrc *.py into hooks/ dirs, and the designed markdown mechanism — core/surface/ templates + tools/build-surface.py (named in ADR-0011's decision and in its own `governs:` line) — does not exist anywhere in the tree (`ls c
- (architecture-010 impact) The governance persona (the plugin's primary behavioral surface) is now in exactly the state ADR-0011's alternatives section rejected: 'two hand-maintained copies ... the exact drift v1 died of, now without even a guard.' Any ca-side ORCHESTRATOR edit that forgets the codex twin ships divergent gove

**Recommendation:**

The two ORCHESTRATOR.md copies are byte-identical today but nothing keeps them so — the core/surface/ + build-surface.py mechanism named in ADR-0011 does not exist. Build the markdown-surface generator or add a CI check that the copies match.

**Acceptance criteria:**
- A ca-side ORCHESTRATOR edit that forgets the codex twin is caught by a gate/CI job, or the twin is generated.

<!-- dedup_key: architecture:plugins/ca-codex/ORCHESTRATOR.md:hand-duplicated-surface · findings: architecture-010 -->
