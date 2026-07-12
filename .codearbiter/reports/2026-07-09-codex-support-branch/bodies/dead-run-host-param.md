# Dead run(host) parameter on all 20 seam entry points

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** med  |  **Confidence:** 0.85  |  **Group:** dead-run-host-param

**Where:**
- `core/pysrc/pre-write.py:153-164`
- `core/pysrc/pre-edit.py:205-216`
- `core/pysrc/_hooklib.py:76-84`
- `core/pysrc/session-start.py:541-556`
- `core/pysrc/pre-bash.py:875-886`
- `core/pysrc/post-write-edit.py:185-196`
- `core/pysrc/security-pass.py:94-105`
- `core/pysrc/migration-pass.py:100-115`
- `core/pysrc/taskwrite.py:125-133`
- `core/pysrc/pre-read.py:62-73`
- `core/pysrc/session-start.py:690-701`
- `core/pysrc/git-enforce.py:293-304`
- `core/pysrc/hostapi.py:176-192`

**Evidence / impact:**
- (architecture-001) Every one of the 20 entry scripts defines `def run(host, argv=None)` per ADR-0011's 'importable run(host) functions' shape, but a mechanical scan of all 20 run() bodies shows NONE references `host` — each delegates to main(), which re-acquires the host through the hidden module-global `_hooklib.get_host()` / a fresh `hostapi.load_host()` (e.g. session-start.py:541 calls `hostapi.load_host()` insid
- (architecture-001 impact) The parameter promises dependency injection it does not deliver: `run(fake_host)` silently runs against the disk-loaded _host.py instead, so contract tests exercising 'same entry, two hosts' through run() would be testing the wrong host without failing. It also masks that the real seam wiring is a g
- (performance-002) Every entry script's __main__ guard does `sys.exit(run(hostapi.load_host()) or 0)` — an eager, explicit call to `hostapi.load_host()`, which does `importlib.util.spec_from_file_location` + `module_from_spec` + `spec.loader.exec_module(mod)` on `_host.py` beside it (hostapi.py:183-189). That loaded `host` is then passed into `run(host, argv=None)`, but every `run()` in the audited scripts (pre-writ
- (performance-002 impact) Every single hook invocation across the whole hook surface (both the ca and ca-codex plugins, ~19 entry scripts) pays the file-load + exec_module cost of `_host.py` twice instead of once. Per-call cost is modest (a small already-cached file, tens to a couple hundred lines of Python to parse/exec), s

**Recommendation:**

Remove the host parameter from run(host, argv=None) on all 20 entries, or wire it so run(host) truly injects. Today every run() ignores it and re-acquires the host via the module global, so _host.py is exec-loaded twice per invocation (performance-002).

**Acceptance criteria:**
- run(host) either injects the passed host or the parameter is gone.
- _host.py is loaded at most once per hook process.

**Folds (same root cause / corroborating findings):** architecture-001, performance-002

<!-- dedup_key: architecture:core/pysrc:run-host-param-dead · findings: architecture-001, performance-002 -->
