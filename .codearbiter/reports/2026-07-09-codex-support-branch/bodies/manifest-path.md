# Hardcoded .claude-plugin/plugin.json path breaks doctor and the update-notifier on ca-codex

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** med  |  **Confidence:** 0.9  |  **Group:** manifest-path

**Where:**
- `core/pysrc/doctor.py:85-93`
- `plugins/ca-codex/.codex-plugin/plugin.json:1`
- `core/pysrc/_updatelib.py:83-94`
- `core/pysrc/session-start.py:494-505`

**Evidence / impact:**
- (reliability-001) doctor.py check_payload(): `manifest = os.path.join(root, ".claude-plugin", "plugin.json")` then `fail(f"plugin.json unreadable at {manifest}: {e}")` on any open error. The ca-codex plugin ships its manifest at `.codex-plugin/plugin.json` only (verified: `plugins/ca-codex/` contains `.codex-plugin/`, `hooks/`, `ORCHESTRATOR.md` — no `.claude-plugin/`). doctor.py is a byte-identical vendored core f
- (reliability-001 impact) The install-health tool permanently cries wolf on the second host: a correct ca-codex install is reported UNHEALTHY, which (a) misleads users into reinstall loops and (b) trains them to ignore doctor output, masking real dormancy failures — the exact silent-dormancy failure shape doctor exists to ca
- (reliability-002) installed_version(): `open(os.path.join(root, ".claude-plugin", "plugin.json"))` → OSError → None on ca-codex (which ships `.codex-plugin/plugin.json` only). session-start.update_notice_line then computes notice_line(None, latest) → version_gt(latest, None) → parse_version(None) → None → False → no notice, swallowed by the `except Exception: return ""`. Meanwhile spawn_background_update_refresh st
- (reliability-002 impact) AC-1/AC-2 of the update-available notifier are silently dead on the Codex host — a stale ca-codex install runs forever unnoticed, the exact failure the notifier exists to surface. No warn/breadcrumb distinguishes 'up to date' from 'cannot read my own version'. Secondary: even with the path fixed, th
- (observability-003) _updatelib.installed_version(root) opens `os.path.join(root, \".claude-plugin\", \"plugin.json\")` (line 88) and returns None on any OSError/ValueError (lines 91-92, no breadcrumb). The ca-codex plugin ships its manifest at `.codex-plugin/plugin.json` (per inventory.md structure and confirmed on disk: plugins/ca-codex/.codex-plugin/plugin.json is the only plugin.json under plugins/ca-codex/ — ther
- (observability-003 impact) The update-available-notifier (spec: update-available-notifier.md, a purpose-built signal) is silently and permanently non-functional on every Codex install, on every session, forever — not intermittently degraded. Because the failure path and the healthy-and-current path both resolve to the same ob

**Recommendation:**

Introduce a host-aware plugin-manifest path (.claude-plugin/ vs .codex-plugin/), resolved via the Host object. Fixes doctor.py reporting every healthy ca-codex install UNHEALTHY (reliability-001) and the update-notifier silently never firing on Codex (reliability-002 / observability-003).

**Acceptance criteria:**
- doctor.py reports HEALTHY on a correct ca-codex install.
- The update-available notice can fire on a stale ca-codex install.

**Folds (same root cause / corroborating findings):** reliability-001, reliability-002, observability-003

<!-- dedup_key: reliability:core/pysrc/doctor.py:codex-manifest-path-false-fail · findings: reliability-001, reliability-002, observability-003 -->
