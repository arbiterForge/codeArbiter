# Codex project_root: dead payload-cwd leg, wrong subdir root, and a git subprocess every invocation

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** med  |  **Confidence:** 0.8  |  **Group:** project-root-seam

**Where:**
- `core/pysrc/_hooklib.py:341-353`
- `core/pysrc/hostapi.py:66-96`
- `plugins/ca-codex/hooks/_host.py:173-187`
- `plugins/ca-codex/hooks/_host.py:173-198`
- `core/pysrc/pre-write.py:130-134`
- `core/pysrc/session-start.py:539-544`
- `core/pysrc/hostapi.py:173-198`
- `core/pysrc/pre-edit.py:182-186`
- `core/pysrc/pre-bash.py:849-853`
- `core/pysrc/post-write-edit.py:172-176`
- `core/pysrc/security-pass.py:73-77`
- `core/pysrc/migration-pass.py:75-79`
- `core/pysrc/pre-read.py:42-48`
- `core/pysrc/taskwrite.py:73`
- `core/pysrc/_hooklib.py:660-685`
- `core/pysrc/_hooklib.py:696-712`

**Evidence / impact:**
- (architecture-006) CodexHost.project_root documents resolution leg 1 as 'the hook payload's cwd ... the harness's own signal' (_host.py:178-180), and hostapi.Host.project_root(payload=None) carries the same leg 'for hosts with no project-dir env var'. But every production caller goes through _hooklib.project_root(), which takes no arguments and calls get_host().project_root() with no payload (_hooklib.py:353); entry
- (architecture-006 impact) The seam's designed-in signal is dead code with a docstring asserting it works — the tests exercise a path production never takes. If Codex's process cwd ever diverges from the payload cwd (subdirectory sessions, future Codex versions changing hook spawn cwd), the fallback silently resolves a differ
- (reliability-005) CodexHost.project_root docstring: 'the hook payload's cwd … the harness's own signal' is leg 1. But _hooklib.project_root() delegates as `get_host().project_root()` with NO payload, and every entry script (pre-write, pre-bash, pre-edit, post-write-edit, session-start, taskwrite, migration/security-pass) calls the no-arg form — grep confirms zero call sites pass a payload. So on Codex the only harn
- (reliability-005 impact) Today: root resolution on Codex depends entirely on process-cwd + git-toplevel assumptions the seam was explicitly built to avoid; a Codex hook spawned from a different cwd (or a nested-repo session cwd) writes state/logs into the wrong repo's .codearbiter with no signal. Latent: the first refactor 
- (performance-001) CodexHost.project_root(self, payload=None) resolution order is: (1) payload['cwd'] if payload given and a dir, (2) `subprocess.run(['git','rev-parse','--show-toplevel'], ...)`, (3) os.getcwd() — Codex sets NO project-dir env var by design (per the _host.py module docstring: 'Hooks receive PLUGIN_ROOT ... but NO project-dir env var ... CLAUDE_PROJECT_DIR must NOT be consulted here'). Every hot-path
- (performance-001 impact) On Codex CLI, every synchronous hook call (every Bash exec, every apply_patch write/edit, every read-adjacent guard) pays a full process-spawn (git rev-parse --show-toplevel, ~10-50ms depending on platform/repo size) on top of the hook's own interpreter startup, on the user's direct interaction path
- (performance-003) _hooklib.get_host() caches the Host OBJECT (module-level `_HOST`, _hooklib.py:76-84), but not the RESULT of calling `host.project_root()` — `_hooklib.project_root()` (line 341-353) calls `get_host().project_root()` fresh on every call. `main()` in each entry script calls it once to compute `root`, but `_log_gate_event` (line 660-685, the shared sink block()/remind()/warn() funnel through — line 68
- (performance-003 impact) On the Codex host, any hook invocation that logs a gate event (REMIND/WARN, which are common — not just rare BLOCKs) pays an extra git subprocess spawn beyond the one already incurred resolving root at the top of main() (performance-001), compounding latency on the synchronous tool-call path. On Cla

**Recommendation:**

Resolve the seam's root-signal design. The documented payload-cwd leg is unreachable (no caller passes a payload), so every Codex hook spawns `git rev-parse --show-toplevel` (performance-001), and CodexHost leg-1 returns the session cwd verbatim so a subdir session resolves the wrong root (reliability-005). Either thread the payload through and climb to the git toplevel, or delete the dead leg and document the real order. Memoize project_root() at process level so gate-logging does not re-resolve it (performance-003).

**Acceptance criteria:**
- A Codex session started in a repo subdirectory resolves the repo root.
- The tests exercise the same resolution path production uses.
- project_root is resolved at most once per hook process.

**Folds (same root cause / corroborating findings):** architecture-006, reliability-005, performance-001, performance-003

<!-- dedup_key: architecture:core/pysrc/hostapi.py:project-root-payload-leg-dead · findings: architecture-006, reliability-005, performance-001, performance-003 -->
