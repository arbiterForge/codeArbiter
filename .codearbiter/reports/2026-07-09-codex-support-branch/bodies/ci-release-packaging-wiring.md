# Wire ca-codex into CI, release, and packaging enforcement gates

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Severity:** high  |  **Confidence:** 0.9  |  **Group:** ci-release-packaging-wiring

**Where:**
- `.github/workflows/ci.yml:22-68`
- `.github/workflows/ci.yml:425-440`
- `tools/sync-core.py:14-17`
- `.github/scripts/test_codex_adapter.py:1-665`
- `.github/workflows/ci.yml:146-252`
- `.github/workflows/release.yml:1-109`
- `.github/scripts/test_hooks_cold_install.py:68-69`
- `plugins/ca-codex/hooks/hooks.json:1-71`
- `plugins/ca/hooks/hooks.json:1-68`
- `.codearbiter/plans/codex-support.md:94`
- `.github/scripts/check_license_consistency.py:37-41`
- `.github/workflows/ci.yml:408-423`
- `plugins/ca-codex/.codex-plugin/plugin.json:7`
- `plugins/ca-codex/hooks/hooks.json:1-70`
- `plugins/ca/hooks/hooks.json:11-40`
- `core/pysrc/_hooklib.py:17-24`

**Evidence / impact:**
- (architecture-002) ADR-0011's stated answer to the v1 drift failure mode is 'CI enforces byte-identity between core/ and every vendored copy' and calls these jobs 'load-bearing and may never be made optional'. But `grep sync-core .github/` returns nothing; ci.yml's path filters (lines 22-29, 51-68) name only plugins/ca/**, plugins/ca-sandbox/**, and .github/** — neither `core/**` nor `plugins/ca-codex/**` appears an
- (architecture-002 impact) The three-copy layout's only anti-drift mechanism is a locally-run script nothing compels anyone to run. A core edit can ship with stale vendored copies (the two hosts silently enforcing different rules — exactly v1's death mode), and ca-codex has no version-bump guard, no hook-suite run, and no pay
- (architecture-003) A repo-wide grep for `test_codex_adapter` finds only two prose mentions (docs/parity.md:11 and the run inventory). Every other .github/scripts/test_*.py suite is an explicit step in ci.yml's `hooks` job (lines 167-252); this one is in no workflow, no CONTRIBUTING command, no unittest-discover path (it lives in .github/scripts/, not plugins/*/hooks/tests/). docs/parity.md claims parity 'is provable
- (architecture-003 impact) The suite guarding the trust-boundary parser (parse_apply_patch) and cross-host verdict parity is dead weight the moment it goes stale: a CodexHost regression merges green while the docs point at this file as the proof of parity. Classic tested-but-never-executed masquerade.
- (infra-001) release.yml's only job (`release`) is hardcoded to ca: it reads `plugins/ca/.claude-plugin/plugin.json` (line 43: `MANIFEST=$(node -p "require('./plugins/ca/.claude-plugin/plugin.json').version")`), tags `v$MANIFEST` (line 50), and extracts release notes from the repo-root `CHANGELOG.md` (line 59, `## [$VER]`). There is no second job, no input to select a plugin, and no ca-codex-namespaced tag sch
- (infra-001 impact) The only way to cut a GitHub Release/tag for ca-codex is by hand outside the sanctioned workflow, or a maintainer runs the ca release with confirm=<ca's version> believing it also republishes ca-codex — it does not. Marketplace consumers pulling `.agents/plugins/marketplace.json` -> `./plugins/ca-co
- (infra-002) test_hooks_cold_install.py hardcodes `PLUGIN_ROOT = os.path.join(REPO, "plugins", "ca")` and `HOOKS_JSON = os.path.join(PLUGIN_ROOT, "hooks", "hooks.json")` (lines 68-69); no code path in the file references plugins/ca-codex. The ca plugin's hooks.json registers each event as TWO hook entries -- a primary `python3 ...` command and a runtime fallback `python3 -c "" || python ...` (e.g. hooks.json:6
- (infra-002 impact) Two independent gaps: (1) the matrix that exists specifically to catch a stock-Windows Store python3 alias (exits 9009 without launching) never runs against ca-codex at all, so a cold-install regression on the new host ships silently; (2) ca-codex's own single-entry commandWindows scheme has no runt
- (infra-003) check_license_consistency.py's `MANIFESTS` list is hardcoded to `plugins/ca/.claude-plugin/plugin.json` and `plugins/ca-sandbox/.claude-plugin/plugin.json` (lines 39-40); ca-codex's manifest lives at a different, un-listed path, `plugins/ca-codex/.codex-plugin/plugin.json`, which currently declares `"license": "AGPL-3.0-only"` matching the canonical value -- but the check does not read that file a
- (infra-003 impact) A future relicense (or an accidental license-field typo/downgrade) on ca-codex's plugin.json passes CI silently, reintroducing the exact stale-declaration failure mode the check was built to prevent, but now on the newest of the three plugin manifests.
- (reliability-008) ca registers every hook TWICE (`python3 <script>` plus `python3 -c "" || python <script>`) precisely because, per _hooklib's header, 'Stock Windows often has no real python3 (the Microsoft Store stub exits 9009), which would make every gate fail OPEN'. ca-codex registers each entry ONCE with `command: python3 …` / `commandWindows: python …`. On Windows, `python` can itself be the Store alias stub 
- (reliability-008 impact) Silent full fail-open of the Codex enforcement surface on stock machines without a working interpreter behind the single registered name — the plugin appears installed but is inert. Confidence tempered: Codex's own hook-failure semantics (fail open vs surfaced error) are not verifiable from this rep

**Recommendation:**

ADR-0011 calls these jobs load-bearing; none exist for ca-codex. Add, in one epic:
1. `sync-core.py --check` job + `core/**` and `plugins/ca-codex/**` path filters + a ca-codex version-bump gate (architecture-002).
2. Wire test_codex_adapter.py into CI (architecture-003) — the trust-boundary parser + parity proof currently has zero callers.
3. A `ca-codex-v*` release job in release.yml mirroring the ca-sandbox pattern (infra-001).
4. Extend test_hooks_cold_install.py to ca-codex, and give ca-codex hooks.json the dual `python3`/`python` STUB-fallback registration ca already uses (infra-002 + reliability-008).
5. Add plugins/ca-codex/.codex-plugin/plugin.json to check_license_consistency.py MANIFESTS (infra-003).

**Acceptance criteria:**
- A core edit with stale vendored copies fails CI (sync-core --check).
- test_codex_adapter.py runs in CI.
- A release produces a ca-codex artifact through the sanctioned path.
- The cold-install matrix exercises ca-codex; a STUB-python3 box does not silently fail its gates open.
- The license-consistency job checks the ca-codex manifest.

**Folds (same root cause / corroborating findings):** architecture-002, architecture-003, infra-001, infra-002, infra-003, reliability-008

<!-- dedup_key: architecture:.github/workflows/ci.yml:sync-contract-unenforced · findings: architecture-002, architecture-003, infra-001, infra-002, infra-003, reliability-008 -->
