# Security controls — codeArbiter

This document is the single source of truth for the project's security posture.
The `auth-crypto-reviewer`, `security-reviewer`, and `dependency-reviewer` agents
read this file before every review. The crypto-compliance and secret-handling
skills gate on this file being present.

---

## Cryptographic primitives

**Approved:** SHA-256 and the broader SHA-2 family (SHA-384, SHA-512).

**Forbidden:** MD5, SHA-1, DES, 3DES, RC4, RC2, Blowfish. These are never
acceptable regardless of context; the `CRYPTO_RE` commit gate (H-09b) flags any
added line that uses one, with no new-code-versus-old distinction.

All production crypto in this repo uses `hashlib.sha256` (Python) or
`createHash("sha256")` (Node.js). The two occurrences of `createHash("md5")`
in `.github/scripts/` are intentional adversarial test payloads injected to
verify that the H-09 gate fires on banned algorithms — they are not operational
uses and must never be treated as approved exceptions.

---

## Secret store and access method

This project has no secrets vault. The only secret codeArbiter manages for its
main governance/farm runtime is `FARM_API_KEY`, the API key for the
cost-arbitrage farm dispatcher.

**Approved access method:** `process.env.FARM_API_KEY` in Node.js. This key is
injected by the CI environment (GitHub Actions secret) or by the developer's
shell environment for local runs. It is never stored in a config file, never
committed to the repository, and never written to a log.

`process.env` is the sanctioned access method for `FARM_API_KEY` in this
project. This is an explicit exception to a general "no process.env for secrets"
rule: the project has no vault, the key is short-lived per-session, and the
deployment model is a single-developer CLI tool.

A second secret exists in the `ca-sandbox` plugin (ADR-0007): the
`CLAUDE_CODE_OAUTH_TOKEN` used by `--with-claude` to authenticate Claude Code
*inside* a sandbox box.

**Approved access method:** env-injection only. The token is passed to the
container as `-e CLAUDE_CODE_OAUTH_TOKEN=...` (auth-precedence #5; resolved via
ADR-0007, Spike B). It is never baked into an image layer, never written to a committed
file, never logged (the failure path emits docker's own stderr/stdout, never the
argv), and tests use a clearly-labelled DUMMY value only. Because a token in a box
running untrusted code is stealable, `--with-claude` is hard-defaulted to
offline/Anthropic-only egress and its credential volume is never co-mounted with
an untrusted source volume (`TokenCoMountRejectedError`).

Pi host authentication is a separate opaque external trusted-runtime boundary
(ADR-0014). Pi may resolve provider credentials from its user-owned auth store,
provider environment variables, or credential commands. `ca-pi` never reads,
parses, copies, snapshots, logs, or reimplements that resolution, and it never
stores Pi credentials in `.codearbiter/`. Parent and child requests name an
exact provider and model; silent provider/model fallback is prohibited.

A `ca-pi` child environment is built from a minimal OS/runtime baseline, not a
copy of the parent environment. It explicitly excludes `FARM_API_KEY` and
`CLAUDE_CODE_OAUTH_TOKEN` and admits only necessary runtime variables plus the
selected provider's declared configuration. Task/prompt content is stdin-only,
never argv, environment, or a temporary file. Tests use isolated Pi homes and
dummy credentials and must not inspect or mutate the operator's real auth store.

All other codeArbiter-defined env vars (`FARM_MODEL`, `FARM_BASE_BRANCH`, etc.)
are non-sensitive configuration and may freely use `process.env`. Provider
environment variables remain secret-bearing external Pi inputs and are governed
by ADR-0014's child allowlist and redaction contract, not by that general rule.

---

## Container isolation (ca-sandbox)

`ca-sandbox` (ADR-0007) runs **untrusted** repositories. Its entire value is
isolation, so the following structural controls are load-bearing and enforced by
construction in `plugins/ca-sandbox/tools/`. A regression in any of them is a
security defect, not a style nit.

- **No host filesystem access.** Every mount is built through the single
  chokepoint `buildMountArgs` (`mounts.ts`), which rejects all bind specs (string
  `-v` shorthand, object form, explicit `type=bind`, unknown types) — only
  `type=volume` and `type=tmpfs` are emitted. There is no other path to a `docker`
  mount argv.
- **Reduced privilege.** Sandbox runs (`run.ts`) and the `--with-claude` box
  (`claude-inside.ts`) both emit `--user 1000:1000`, `--cap-drop ALL`,
  `--read-only`, `--security-opt no-new-privileges`, and resource caps. Never
  `--privileged`; the docker socket is never mounted.
- **Egress default-deny.** The default network policy is `offline`
  (`--network none`). The `clone-then-cut` and experimental allowlist policies are
  opt-in; an unknown policy is a hard error, never a silent pass-through.
- **Clone-input trust model.** The repo url is untrusted and validated by
  `validateRepoUrl` (`create.ts`) before it reaches git: only `https://`, `ssh://`,
  and `user@host:path` remotes are allowed; leading-`-` values (git argument
  injection) and transport-helper syntax (`ext::`, `fd::`, `file://`) are rejected,
  and the clone argv emits an end-of-options `--` before the url.
- **No shell interpolation of untrusted input.** Every docker invocation uses an
  argv array (`spawn`/`spawnSync`, no `shell: true`); untrusted urls, ids, and
  paths reach docker as discrete argv elements, never a parsed command line.

---

## TLS

Default Node.js TLS is required on all outbound HTTPS calls.
`rejectUnauthorized: false` is never permitted. No HTTP (non-TLS) endpoint may
be used for API calls, except loopback (`127.0.0.1`/`localhost`) for test mocks
— see the boundary-crossings table.

The **resolved** `apiBaseUrl` — after the `FARM_API_BASE_URL` env override,
`plan.meta.apiBaseUrl`, and the built-in default are applied in that precedence —
is validated before every outbound call by `assertSecureBaseUrl` (`farm.ts`),
which requires the `https://` scheme (or the documented loopback `http://`
exception, no userinfo). Validation uses WHATWG `URL` parsing — the same parser
`fetch` uses for connection targeting — so there is no parser-differential bypass.
This supersedes the prior parse-time check that covered only `plan.meta.apiBaseUrl`.

**Outbound surface — the update-available notifier.** The update-notifier
(`plugins/ca/hooks/_updatelib.py`, run detached by `update-refresh.py`) makes one
outbound call: an **unauthenticated HTTPS GET** to
`https://api.github.com/repos/arbiterForge/codeArbiter/releases/latest`, at most
once per day (cached in the user-global `~/.codearbiter/update-state.json`). It is
the plugin's only routine outbound call outside the farm dispatcher. Posture per
ADR-0003: `https://` is asserted on the initial URL *and* re-asserted on any 3xx
via a custom redirect handler that refuses an `https://`→`http://` downgrade;
stdlib `urllib` only (ADR-0004), default verifying TLS, no `rejectUnauthorized`
equivalent. It **sends no repo content, no PII, and no secret** (User-Agent +
Accept headers only) and is **fail-silent** — any network/parse/cache error
degrades to "no notice" and never raises into the SessionStart or statusline hook.
It adds **no synchronous network call** to the SessionStart hot path (those hooks
only read the cache; the fetch runs in the detached refresh child).

---

## Approved npm registries

`https://registry.npmjs.org` is the only approved registry. No alternative
registries, `git+` URLs, `file:` references, or `http:` (non-TLS) sources are
permitted in `package-lock.json` or any manifest.

---

## Approved licenses (dependencies)

This is a private package (`"private": true`). The following SPDX identifiers
are approved across all manifests (the shipped plugin payload carries no runtime
npm dependencies; the docs site under `site/` is not part of that payload):

- MIT
- ISC
- Apache-2.0
- BSD-2-Clause
- BSD-3-Clause
- BlueOak-1.0.0 — permissive, OSI-approved "better-MIT"; imposes no obligations
- CC0-1.0 — public-domain dedication; imposes no obligations
- MPL-2.0 (development/build-time only): weak, file-level copyleft. The obligation
  attaches only to the MPL-licensed source files themselves and edits made to
  them; it never reaches files that merely consume the library. Approved for
  build-time docs-site dependencies under `site/` and development-only tooling
  under `plugins/*/tools` (introduced by `lightningcss` via `vite@8`). It is not
  approved as a runtime plugin dependency or distributed artifact. `node_modules`,
  native bindings, WASM, Vite, Rolldown, Lightning CSS, and their source files must
  not enter a shipped plugin payload; built outputs must be checked for their absence.
- LGPL-3.0-or-later (build-time, `site/` ONLY): weak, library-level copyleft
  discharged by keeping the component replaceable. Approved solely for the 18
  `@img/sharp-libvips-*` prebuilt binaries pulled by `sharp` as a build-time
  docs-site image optimizer under `site/`. The obligation is low-stakes for a
  replaceable build tool, and its output (optimized images) carries no LGPL
  obligation. NOT approved for the plugin payload (`plugins/**`) or any
  distributed artifact.
- 0BSD (development/build-time only): a public-domain-equivalent BSD variant with
  no attribution requirement — more permissive than MIT. Approved for `tslib`
  pulled transitively under `site/` and development-only `plugins/*/tools` locks.
  It is not approved as a runtime plugin dependency or distributed artifact.

`BlueOak-1.0.0` and `CC0-1.0` were approved 2026-06-22 (user decision via SMARTS
arbitration, checkpoint 2026-06-22) to cover transitive `site/` dependencies
(`common-ancestor-path`, `lru-cache`, `sax`; `mdn-data`). `argparse@2.0.1`
declares a `Python-2.0` SPDX field that is a packaging mislabel — upstream is
MIT — and is accepted on that basis.

`MPL-2.0` was approved 2026-06-27 (user decision, BY SUaDtL@users.noreply.github.com),
scoped to build-time `site/` dependencies only, to cover `lightningcss@1.32.0`
introduced by the Astro 7 / Vite 8 upgrade; the scoped entry above states the
boundary. `satteri@0.9.3` (and its `@bruits/satteri-*` platform variants), Astro
7's markdown processor, omits the SPDX license field in its npm metadata; upstream
(`github.com/bruits/satteri`, published by an Astro core maintainer via OIDC)
ships an MIT license, so it is accepted as MIT on the same packaging-mislabel
basis as `argparse`, build-time `site/` only.

`LGPL-3.0-or-later` and `0BSD` were approved 2026-07-02 (user decision,
BY SUaDtL@users.noreply.github.com, via SMARTS arbitration; resolves
`[CONFIRM-08]`), scoped to build-time `site/` dependencies only, to cover the 18
`@img/sharp-libvips-*` binaries (`sharp` docs-site image optimizer) and `tslib`.
Neither reaches the shipped plugin payload.

`MPL-2.0` and `0BSD` were extended 2026-07-14 (user decision,
BY SUaDtL@users.noreply.github.com, conflict resolution option 1) to
development-only tooling under `plugins/*/tools`. This resolves the `ca-pi`
Vitest 4.1.9 lock gate and the pre-existing `ca-sandbox` lock-policy mismatch.
The extension does not authorize runtime dependencies or distribution of
`node_modules`, native binaries, WASM, or dependency source; release checks must
prove those artifacts are absent from shipped plugin payloads.

Any new dependency with a license outside this list requires an explicit
review and an entry in `overrides.log` before merging.

---

## Hook security (Python)

All hook files under `plugins/ca/hooks/` must use the Python standard library
only — no third-party dependencies, ever. Hooks run on stock Python installs
with nothing additional installed.

Hook input parsing fails open (not closed) on malformed stdin — see
`_hooklib.py:read_input()` for the documented rationale.

**Repo resolution — the guards judge the repo the git op fires in (#190).** The
`.git/hooks` enforcement backstop `git-enforce.py` resolves its target via
`git rev-parse --show-toplevel` inheriting the hook's own cwd (which git sets to
the target repo's work-tree top for `pre-commit`/`pre-push`), **not**
`CLAUDE_PROJECT_DIR` — so a `git -C <other> commit` under a Claude session is
gated against `<other>`, not the session's repo. The PreToolUse `pre-bash.py`
`git_cwd` composes a **repeated** `-C` run the way git itself does (fold-left:
absolute replaces the accumulator, relative joins onto it, seeded with
`project_root`), closing the multi-`-C` fail-open where a crafted
`git -C /abs/main -C . commit` would otherwise be judged against the wrong repo;
a `-C` target that is not a real directory now fails **closed** (H-01 block).
`session-start.py` and `taskwrite.py` resolve via the shared
`_hooklib.project_root` (CLAUDE_PROJECT_DIR-first) rather than divergent local
copies, so audit lines / the task board / installed hooks land in the
harness-authoritative project dir.

The hook payload's `cwd` field is a **trusted-harness input** to repo
resolution, on the same footing as the host's project-dir env var: both are
written by the host harness itself, never by the model. Its precedence is
per-host (`hostapi.Host.project_root`, ADR-0011): under **Claude Code** the
env var `CLAUDE_PROJECT_DIR` is consulted first and the payload-`cwd` leg is
inert (the harness always sets the env var); under **Codex** there is **no
env leg at all** — `CLAUDE_PROJECT_DIR` is deliberately never consulted, so a
value leaked from an adjacent Claude session cannot redirect the guards. The
Codex Host method defines payload `cwd` as its first leg ahead of
`git rev-parse --show-toplevel` and the process cwd, but the entry scripts do
not currently feed the payload into `project_root()` — in the wired path,
Codex resolution is `git rev-parse` from the session cwd, which is equivalent
because the Codex harness runs every hook in the session cwd it also stamps
into the payload. If an entry ever passes the payload, the documented
precedence above is the contract it inherits.

**Hooks-install re-probe fast-path is fail-safe (#194).** To cut SessionStart
latency, `_githooks.install()` may skip the git-spawn hooks-dir probe when a
cheap on-disk cache proves the shims are already current. The skip fires ONLY
when it can positively, spawn-free confirm no hooks redirect: the cached dir is
exactly `<root>/.git/hooks` AND `_confirmed_no_local_hooks_path` finds no
`core.hooksPath` (a **grammar-free** case-insensitive substring scan of
`.git/config`/`.git/config.worktree` for `hookspath` — cannot under-detect any
git-config spelling) AND no `[include]` directive AND the shims still match the
current enforcer path. Any read failure, any `hookspath` occurrence, an
`[include]`, a cached custom hooksPath, or a global-config change (a
`~/.gitconfig` + XDG-config mtime token invalidates the cache) → fall through to
the full probe. The fail direction is **install-when-unsure, never
skip-when-unsure** — the fast path can never leave the #161 git-enforce backstop
unwired. Accepted residual: a `$GIT_CONFIG_GLOBAL`/`$GIT_CONFIG_SYSTEM`
env-repointed config or `/etc/gitconfig` `core.hooksPath` set AFTER a
default-location install (the cold/first install always resolves those via the
full probe).

---

## Pi adapter and child-process security

`ca-pi` is an enforcement adapter inside Pi's cooperative trusted-extension
runtime, not an OS sandbox. It never grants project trust. A parent extension
installed globally may be discovered and loaded before Pi's project-trust
decision; extension loading is discovery, not repository authorization. On each
`session_start`, the adapter invalidates prior lifecycle and cached executable/
bridge identities, enters an activation-check fail-closed generation, and reads
only the canonical `.codearbiter/CONTEXT.md` marker without Python or Git. If the
marker is enabled, `context.isProjectTrusted?.() === true` is required before
Python/Git resolution, bridge/shared-core startup, enforcement installation,
persona loading, hook discovery, repository Git reads, or fetch. Missing, false,
or failing trust performs none of those operations: mutators remain blocked,
native reads use fresh untrusted settings, one fixed redacted trust direction is
shown, and doctor runs without bridge probe or wrapper live fire. Project-local
installs also retain Pi's load-time trust gate and this adapter-level check.

Child launches disable approval, ambient extension/skill/template/theme/context
discovery, and session loading, then explicitly load the trusted enforcement-only
`ca-pi` adapter and generated skill/charter paths. Command or skill collisions
fail visibly rather than shadowing a governance surface.

`CODEARBITER_SUBAGENT=1` disables recursive author/reviewer dispatch only. Every
gate, audit, redaction, and doctor control stays active in the child. An ambient
or user-supplied marker outside the runner's validated child contract is a
fail-closed diagnostic. Tasks use bounded stdin; subprocesses use absolute
executables/bridge paths, argv arrays, `shell: false`, explicit cwd, strict
JSON/JSONL schemas, bounded/redacted stdout and stderr, and cross-platform
process-tree termination on cancellation or timeout.

Unknown Pi tools are potentially mutating and blocked by default. A tool becomes
read-only or governed only through an explicit generated host-descriptor entry
and parity fixtures. The adapter must be the final authority over governed tool
arguments: a live promotion test must prove that no later trusted extension can
rewrite approved arguments before execution. If Pi cannot guarantee that order,
Pi promotion stops and ADR-0013 is revisited. Same-process extensions already
trusted by the operator otherwise retain arbitrary same-user execution under
ADR-0010's cooperative-agent residual-risk boundary.

---

## Audit trail

`overrides.log`, `triage.log`, and `sprint-log.md` are append-only artifacts.
They may never be truncated, rewritten, or deleted. The `pre-bash.py` H-05 guard
and the `pre-write.py` / `pre-edit.py` H-05 guards enforce this at every
tool-call boundary.

**Enforcement scope (accepted residual risk).** These guards are *integrity*
controls, not *completeness* controls — they protect a log once written, they do
not compel a write. The completeness half is resolved by `[CONFIRM-09]`
(2026-07-02, BY SUaDtL@users.noreply.github.com): strategy (a) — a lightweight
staleness check (UserPromptSubmit) warns when an active `/sprint` or `/dev`
flow has not appended its expected log line (`sprint-log.md` / `overrides.log`)
within a bounded window — paired with the durable gate-events sink from
`observability-001` (issue #186). It is a *warn*, not a hard gate: a missed write
is surfaced, not blocked, keeping the integrity guards the sole true STOP.
**Shipped in ca 2.8.11 (#186):** `_hooklib` `block()`/`remind()`/`warn()`
best-effort append a structured line to `.codearbiter/gate-events.log` (fail-open
— a locked/missing/unwritable log never changes a hook's exit code nor suppresses
a BLOCK; the write is wrapped so no exception escapes into any of the 16 entry
hooks), and `_hooklib.staleness_warning` surfaces stale active flows only through
`warn()` (non-blocking by construction). `gate-events.log` is append-only —
added to `AUDIT_LOG_BASENAMES`, the single source that `AUDIT_LOG_NAMES` and all
three H-05 flanks (shell pre-filter + regex, Write, Edit) derive from, so the set
cannot drift. `/override` is deliberately **not** staleness-tracked: it is a
single synchronous announce-then-log action with no in-progress marker to key
off (per CONFIRM-09's "don't invent new state" constraint).
The `pre-bash.py` shell guard is lexical and anchored on the literal log name, so
the following truncation/indirection spellings are out of scope and accepted as
residual risk (the sanctioned bypass for legitimate log management is
`/ca:override`):

- file-descriptor redirects where no filename token is adjacent to the verb —
  `exec 3>.codearbiter/overrides.log`;
- triple-chevron `>>>` (treated as append by some shells);
- process-substitution spellings;
- verb-with-variable targets where the literal name never appears beside the
  verb — `f=.codearbiter/overrides.log; rm "$f"` (bash) or `$f='overrides.log';
  rm $f` (PowerShell).

The `pre-write.py` / `pre-edit.py` guards close the Write/Edit flank (including an
empty-`old_string` Edit, which is not a verifiable append). The append-only path
set is centralized in `_hooklib` (`is_audit_log`, `AUDIT_LOG_NAMES`) so the three
guards never drift on which files are covered.

**H-05 tail-anchor + H-20 `--no-verify` (2026-07-02, #172 / #175).** The H-05
append check (`pre-edit.py`, via `_hooklib.is_tail_append`) now **tail-anchors** —
an audit-log Edit is admitted only as a strict append (`new` = current content +
appended tail, with `old` occurring exactly once), and a `replace_all` Edit on an
audit-log path is **rejected outright** (reliability-003/#172), closing the prior
`new.startswith(old)` hole that let a mid-file insertion or a multi-site suffix
rewrite pass as an "append". The new **H-20** guard (`pre-bash.py`) blocks a
literal `--no-verify`/`-n` on `git commit` — including bundled and attached-value
short-flag spellings (`-nm`, `-nm=x`, `-vnm=y`; the char-walk mirrors git's own
cluster parsing) — and a literal `--no-verify` on `git push` (appsec-002/#175),
because that flag skips the `.git/hooks` git-enforce backstop (voiding
H-01/H-02/H-09b/H-10b/H-14 for that operation). The residual is the same accepted
**shell-indirection** class listed above (`g=git; $g commit --no-verify` defeats
the lexical `COMMIT_RE`/`PUSH_RE` matcher itself) — out of scope per ADR-0010's
cooperative-agent trust model.

**Automated writer of record.** One write to `overrides.log` is performed by the
framework, not a user action: on session start, if a prior session entered
`/ca:dev` and ended without `/ca:arbiter`, `session-start.py` appends a
`BY: session-cleanup | DEV: exit` close line before clearing the live dev marker
(observability-001), so the dev-mode enter/exit trail is never left half-open. It
is append-only and best-effort. This is the only writer of `overrides.log` other
than the three sanctioned mutators (`/override`, `/sprint` auto-decisions,
`/dev` entry/exit).

**Gate-marker trust boundary (ADR-0010).** codeArbiter's gate markers (e.g.
`.codearbiter/.markers/security-gate-passed`) are *cooperative-agent
attestations*, not tamper-proof proofs. `security-pass.py` mints the
security-gate marker by re-deriving the sensitive-line digests from the current
worktree; direct invocation of the sanctioned producer is the *intended*
attestation mechanism. A Bash-capable non-cooperating agent can self-mint a pass
(as it can defeat the `--no-verify` and shell-indirection controls, appsec-002 /
#175) — this is an accepted trust boundary, out of scope for the product's
cooperative-orchestrator threat model, not a defect. The marker's value is the
friction and audit trail it adds on the cooperative path. Reopens (→ non-fabricable
reviewer-signed binding) only if the threat model expands to untrusted agents. See
ADR-0010 (resolves appsec-003 / #196).

**MCP file-write tools out of scope (both hosts).** The write-path guards
(`pre-write.py` / `post-write-edit.py`) are wired to each host's *native* write
tools — Claude's `Write`/`Edit`/`MultiEdit`/`NotebookEdit`, and Codex's
`apply_patch` (plus its `Write`/`Edit` matcher aliases). A file write performed
through an **MCP server tool** (`mcp__<server>__<tool>`) is not covered: on Claude
such tools escape the `Write`/`Edit` matchers, and on Codex `mcp__*` normalizes to
the `OTHER` category (no `TOOL_MAP` entry) and matches neither the
`apply_patch|Write|Edit` write hooks nor the `Bash` exec hook. An agent that adds
an MCP filesystem/write server can therefore write `.codearbiter/CONTEXT.md`, a
`.markers/` token, or an audit log without a guard firing, on either host. This is
**accepted residual risk** under the same cooperative-agent trust model as the
`--no-verify`, shell-indirection, and self-minted-marker gaps above (ADR-0010) — a
cooperating orchestrator does not route protected writes through an out-of-band MCP
tool, and a non-cooperating Bash-capable agent already has stronger bypasses.
Bringing MCP writes under the write gate on both hosts is tracked as **near-term
hardening (issue #270 / tribunal appsec-002)**, not a codex-branch blocker; it
reopens if the threat model expands to untrusted agents.

---

## Boundary crossings (declared exceptions)

| Boundary | Exception | Rationale |
|----------|-----------|-----------|
| H-03 explicit staging | `farm.ts` stages `worker.filesWritten` explicitly — previously `git add -A`, corrected 2026-06-12 | Farm worktree commits are operator-initiated, reviewed in PR |
| Fail-open on hook input parse | `_hooklib.py:read_input()` | Parse failure must not brick the session |
| Unsigned dispatcher commits | `NOSIGN` constant in `farm.ts` | CI signing servers reject unattended commits; the integration PR is the signed artifact |
| Gate command shell execution | `plan.json` `gate.commands` / `test.command` and `FARM_MUTATION_CMD` run via `cmd.exe /c` / `bash -c` in `farm.ts` | Operator-authored, length-capped (≤1024), PR-reviewed; deterministic gate by design — no untrusted source. See ADR for the trust model |
| Loopback `http://` for API base | `assertSecureBaseUrl` in `farm.ts` allows `http://127.0.0.1`/`localhost` (no userinfo) | Test mocks bind without TLS; same WHATWG parser as `fetch` → connection target is loopback, no cleartext-to-remote path |
| Untrusted git clone | `ca-sandbox` clones an attacker-controlled url in a throwaway, `--rm`, networked `alpine/git` container | Input is allowlisted by `validateRepoUrl` + `--` end-of-options; blast radius is the disposable clone container only (no host bind, never co-run with the sandbox) — see ADR-0007 |
| `curl \| bash` nixpacks install | `build.ts` runs `curl -fsSL https://nixpacks.com/install.sh \| bash` when nixpacks is absent | Build-time host convenience; the URL is a hardcoded constant (not attacker-controllable). Tracked: prefer declaring nixpacks a prerequisite or pinning a checksum (NEEDS-TRIAGE in the ca-sandbox plan) |
| Pi host-managed provider authentication | Pi resolves its user-owned auth store, provider environment, or credential command outside codeArbiter | Opaque trusted-runtime boundary under ADR-0014; `ca-pi` never reads/copies/logs credentials and child environments are minimal and provider-specific |
| Pi child process isolation | Fresh Pi processes run with discovery/session loading disabled and only explicit enforcement/skill/charter inputs | Cooperative process isolation for context and recursion control, not an OS sandbox; bounded IPC and process-tree cleanup limit accidental spill |
| Trusted same-process Pi extensions | An operator-approved extension may execute arbitrary same-user code in Pi's process | Accepted ADR-0010 cooperative-agent residual; final governed-argument ordering remains a live promotion STOP under ADR-0014 |
