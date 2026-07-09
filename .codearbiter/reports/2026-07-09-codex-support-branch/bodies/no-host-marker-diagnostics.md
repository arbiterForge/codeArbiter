# Startup banner and doctor never surface the resolved host name

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** med  |  **Confidence:** 0.8  |  **Group:** no-host-marker-diagnostics

**Where:**
- `core/pysrc/session-start.py:539-649`
- `core/pysrc/doctor.py:176-195`

**Evidence / impact:**
- (observability-004) session-start.py's main() does `host = hostapi.load_host()` (line 541) and only ever reads two capability flags off it (`host.has_statusline` at line 556, `host.plugin_root()` at line 543) — `host.name` is read nowhere in the function. The printed '=== codeArbiter startup state ===' block (line 589 onward: stage, open questions, task board, provenance drift, update notice, briefing) contains no li
- (observability-004 impact) This branch's own commit history (e19778c, cited in inventory.md as evidence the silent-un-enforcement failure mode already happened once) was a hooks.json registration gap on Codex that went unnoticed until fixed post-hoc. Neither of the two places a maintainer is most likely to check 'is codeArbit

**Recommendation:**

Surface the resolved host.name in both session-start.py's startup banner and doctor.py's report, so a dormant Codex install is distinguishable from a healthy one at the place a maintainer looks.

**Acceptance criteria:**
- session-start and doctor output name the resolved host (claude/codex).

<!-- dedup_key: observability:core/pysrc/session-start.py:no-host-marker-in-startup-output · findings: observability-004 -->
