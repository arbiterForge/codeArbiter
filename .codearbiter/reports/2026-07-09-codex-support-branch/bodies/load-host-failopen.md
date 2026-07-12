# Codex write gate silently fails open when _host.py fails to load

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** high  |  **Confidence:** 0.8  |  **Group:** load-host-failopen

**Where:**
- `core/pysrc/hostapi.py:176-191`
- `core/pysrc/hostapi.py:168-173`
- `plugins/ca-codex/hooks/_host.py:21-25`
- `core/pysrc/hostapi.py:150-173`
- `core/pysrc/pre-write.py:118-127`
- `core/pysrc/hostapi.py:121-173`
- `plugins/ca-codex/hooks/_host.py:1-32`
- `core/pysrc/_hooklib.py:79-84`
- `.github/scripts/test_codex_adapter.py:1-666`

**Evidence / impact:**
- (architecture-004) hostapi.load_host() catches every exception from executing _host.py and returns a bare Host() (Claude defaults) with no warn()/breadcrumb (`except Exception: return Host()`). Reproduced: feeding a Codex apply_patch payload to the base Host yields `[{'file_path': '', 'kind': 'write', ...}]` — file_path is empty, so classify_protected('') hits nothing and pre-write allows the patch, including one re
- (architecture-004 impact) One syntax error or a partial install of ca-codex converts every enforcement gate to a no-op with zero signal — silent-un-enforcement, the failure class commit e19778c already exhibited once. The base-class-IS-Claude asymmetry means the failure mode is invisible on the host where it is harmless and 
- (reliability-003) `except Exception: return Host()` — on ca-codex, ANY failure loading _host.py (partial install, corrupted file, an import shadowing) yields the CLAUDE host with zero stderr breadcrumb. Downstream on a Codex payload: base Host.iter_file_ops hits the default branch, `fpath = ti.get("file_path", "")` is "" (Codex tool_input is {"command": "<patch>"}), so pre-write._guard_op runs classify_protected(""
- (reliability-003 impact) The documented worst failure shape — silent dormancy — on the enforcement-critical path: the write gate looks installed but admits everything, with no signal. The 'partial install degrades to today's behavior' rationale is only safe for the ca plugin; on ca-codex 'today's behavior' is the WRONG host
- (typesafety-001) hostapi.load_host() (176-191) wraps _host.py's dynamic import in a bare `except Exception` (line 190, `# noqa: BLE001`) and on ANY failure — syntax error, import error, unreadable file, a bad edit to _host.py — returns `Host()` (Claude semantics) with NO signal that the intended CodexHost failed to load; get_host() (_hooklib.py:79-84) caches that value with no warn()/log call anywhere in the path.
- (typesafety-001 impact) Any failure of ca-codex's _host.py to import (a bad edit, a partial install, a stray syntax error, a future refactor typo) degrades Codex-side enforcement from "every apply_patch write is guarded" to "every apply_patch write silently bypasses ALL FOUR pre-write guards, including the CONTEXT.md kill-
- (observability-002) load_host() does: `try: ... spec.loader.exec_module(mod); return mod.HOST\n except Exception: # noqa: BLE001 — no/broken _host.py -> Claude defaults\n    return Host()` (hostapi.py:184-191). This is the ONLY place `_host.py` is loaded, and it is a bare `except Exception` with no call to warn()/_log_gate_event or any stderr/log write before returning the fallback.
- (observability-002 impact) On the Codex install, a syntax error, import failure, or any exception while executing plugins/ca-codex/hooks/_host.py (e.g. a partial/corrupted vendored copy, a Python version incompatibility in the file) causes EVERY entry script to silently run as if it were plain Claude Code: has_statusline reve
- (coverage-003) hostapi.load_host() (core/pysrc/hostapi.py:176-191, vendored byte-identically into both plugins) has a bare `except Exception: return Host()` branch that is the load-bearing fallback for the whole dual-host seam — every one of the ~19 `sys.exit(run(hostapi.load_host()) or 0)` entry points (grep across core/pysrc/*.py) depends on it choosing the RIGHT host or failing loud. Grepped the entire repo f
- (coverage-003 impact) The single riskiest branch in the whole M1/M2 seam (a broken ca-codex install silently degrading every enforcement entry to Claude-host semantics, per architecture-004/reliability-003) can regress or be 'fixed' incorrectly with no test to catch it — CI would stay green through either outcome.

**Recommendation:**

Make hostapi.load_host() distinguish 'no _host.py' from '_host.py present but failed to load'. Present-but-broken must fail CLOSED (or emit a loud stderr breadcrumb and refuse to guard the payload), never silently return the Claude-default Host(). Land the coverage-003 test for the fallback path in the same PR.

**Acceptance criteria:**
- A syntactically-broken ca-codex _host.py causes the write gate to block/refuse a protected apply_patch, not allow it.
- A distinguishing signal (stderr/log breadcrumb) is emitted; a broken load is not observationally identical to a healthy one.
- A test exercises the load_host() except/fallback path (currently zero coverage; typesafety-001 reproduced the bypass: base Host + Codex apply_patch -> file_path='' -> H-18/H-19/H-05/H-11 skipped).

**Folds (same root cause / corroborating findings):** architecture-004, reliability-003, typesafety-001, observability-002, coverage-003

<!-- dedup_key: architecture:core/pysrc/hostapi.py:fallback-wrong-host-fail-open · findings: architecture-004, reliability-003, typesafety-001, observability-002, coverage-003 -->
