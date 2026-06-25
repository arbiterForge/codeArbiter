# Inventory — run 2026-06-24-root

Mapped inline (repo bounded: 397 tracked files, ~150 non-markdown). Below is the
file map plus the orchestrator risk/boundary overlay that the mappers are not
trusted with.

## Structure

- **`plugins/ca/hooks/*.py`** — Python 3, stdlib-only. The enforcement runtime.
  Intercepts Bash/PowerShell, Write, Edit, MultiEdit, SessionStart, UserPromptSubmit,
  PreCompact (see `hooks/hooks.json`). Shared libs: `_hooklib.py` (crypto/secret
  regex + path/frontmatter/marker/digest helpers), `_sloplib.py`, `_taskboardlib.py`,
  `_metricslib.py`, `_prunelib.py`, `_previewlib.py`, `_standuplib.py`, `_babysitlib.py`.
- **`plugins/ca/tools/farm.ts`** (1689 LOC) — TypeScript dispatcher. Reads `plan.json`,
  spawns external "Zen" workers, runs operator-authored gate commands, makes outbound
  HTTPS calls to a configurable API base. Ships built `farm.js`.
- **`plugins/ca-sandbox/tools/*.ts`** — TypeScript driver that clones UNTRUSTED repos
  into ephemeral Docker boxes. Key units: `create.ts` (validateRepoUrl), `mounts.ts`
  (buildMountArgs chokepoint), `run.ts`/`claude-inside.ts` (privilege flags),
  `network.ts` (egress policy), `exec.ts`, `cp.ts`, `build.ts` (nixpacks), `registry.ts`.
  Ships built `sandbox.js`.
- **`site/scripts/**`** — Astro docs-site generator (TS) + vitest tests. Build-time only.
- **`.github/scripts/*.py`** — CI guard scripts (badge consistency, plugin-ref graph,
  hook-guard matrices). Run in CI.
- **Tests** — `plugins/ca/hooks/tests/*.py` (unittest), `.github/scripts/test_*.py`,
  `plugins/ca*/tools/*.test.ts` (vitest), `site/test/**/*.test.ts` (vitest).
- **Prose** — `plugins/ca/{skills,commands,agents}/**.md`, `ORCHESTRATOR.md`, docs.
  Governed by the plugin's own authoring gates. **Out of scope for code lenses.**

## Build / test (from tech-stack.md, CI-authoritative)

- Hooks: stdlib-only; floor = `python -m py_compile`. Test = the `.github/scripts/test_*.py`
  suites + `python -m unittest discover -s plugins/ca/hooks/tests`.
- farm: `cd plugins/ca/tools && npm ci && npm run typecheck && npm test && npm run build`
  (built `farm.js` must be in sync — CI fails on stale artifact).
- ca-sandbox: same shape under `plugins/ca-sandbox/tools`; docker-gated suites self-skip.
- CVE gate: `npm audit --omit=dev --audit-level=critical`.

## Risk ranking (orchestrator overlay — highest first)

1. **`plugins/ca/hooks/pre-bash.py`, `pre-write.py`, `pre-edit.py`, `post-write-edit.py`,
   `security-pass.py`, `_hooklib.py`, `_sloplib.py`** — the enforcement chokepoints.
   They parse UNTRUSTED tool-call payloads from stdin and decide block/allow. A guard
   bypass (regex evadable, normalization gap, fail-open misuse) defeats the product's
   entire value proposition. **appsec + reliability core.**
2. **`plugins/ca-sandbox/tools/`** — runs untrusted code. Isolation IS the product.
   `mounts.ts` (no host bind), `create.ts` (validateRepoUrl — git arg-injection),
   `run.ts`/`claude-inside.ts` (privilege drop), `network.ts` (egress default-deny),
   `exec.ts`/`cp.ts` (argv, no shell). Regression here = isolation escape.
3. **`plugins/ca/tools/farm.ts`** — outbound HTTPS (`assertSecureBaseUrl`), secret
   handling (`FARM_API_KEY` via `process.env`), gate-command execution, git staging.
4. **`migration-pass.py` + `plan.schema.json`** — `.codearbiter` state-format migration
   (not a DB). Destructive-op / immutability concerns adapted to state files.
5. **`.github/scripts/*.py`, `site/scripts/**`** — CI/build-time, lower blast radius.
6. **Markdown prose** — out of code-lens scope.

## Trust boundaries

- **Tool-call payload → hook stdin.** Untrusted (the model's proposed Bash/Write/Edit).
  Crossing guarded by `pre-bash.py` / `pre-write.py` / `pre-edit.py`.
- **Untrusted git URL + repo contents → ca-sandbox Docker box.** Guarded by
  `validateRepoUrl` + `buildMountArgs` + privilege flags + egress policy.
- **Outbound farm HTTPS → external API base.** Guarded by `assertSecureBaseUrl`.
- **Secret env (`FARM_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`) → process / container.**
  env-injection only; never logged, never image-baked, never co-mounted with untrusted src.

## DECLARED EXCEPTIONS — reviewers MUST NOT flag these as findings

From `security-controls.md` (sanctioned, user-attributed, logged):

- `farm.ts` explicit staging of `worker.filesWritten` (not `git add -A`).
- Fail-OPEN on hook stdin parse (`_hooklib.py:read_input()`) — deliberate; parse
  failure must not brick the session.
- Unsigned dispatcher commits (`NOSIGN` in `farm.ts`).
- Gate/test commands run via `cmd.exe /c` / `bash -c` in `farm.ts` — operator-authored,
  ≤1024 chars, PR-reviewed; deterministic gate, no untrusted source.
- Loopback `http://127.0.0.1`/`localhost` allowed by `assertSecureBaseUrl` (test mocks).
- Untrusted git clone in throwaway `--rm` networked `alpine/git` container.
- `curl -fsSL https://nixpacks.com/install.sh | bash` in `build.ts` — hardcoded URL,
  build-time host convenience (already NEEDS-TRIAGE in the ca-sandbox plan).
- The two `createHash("md5")` in `.github/scripts/` are ADVERSARIAL TEST PAYLOADS
  proving the H-09 gate fires — not operational crypto.

A finding that re-flags any of the above is a false positive by construction.
