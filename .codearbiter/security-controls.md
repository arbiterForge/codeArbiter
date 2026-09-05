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

### ca-pi npm publication boundary

ADR-0029 authorizes one release credential, `NPMJS_TOKEN`, sourced only from the
repository or organization Actions secret store. The reusable publisher forwards
that named secret explicitly—never through `secrets: inherit`—to the single
`npm publish` step as `NODE_AUTH_TOKEN`. Its authority is limited to publishing
the public `@arbiterforge/ca-pi` package at the approved npm registry. Candidate
tag content is inert data: its scripts are never executed, packing and publishing
use `--ignore-scripts`, and trusted verifier code is pinned to the protected-main
workflow commit.

The job acquires only exact `npm@11.19.1` from
`https://registry.npmjs.org/npm/-/npm-11.19.1.tgz`, bound before extraction or
execution to
`sha512-ztsxKxt/kkIaAs+2i0GU6I+DRmUdrNasxTZKJe9TCdSjKxlhah/4r/hl5ygMD6XAg1qZ9c2TNomR4qgOydp10g==`.
Acquisition is credential-free and refuses redirects. It uses a fresh runner
temporary root, performs path-containment checks before extraction, rejects
links and special files, and executes only the regular resolved `npm-cli.js`
beneath that root after an exact version check. It does not change a manifest,
lockfile, global npm state, `PATH`, cache, or release artifact. The exact CLI is
passed explicitly to packing, publication, and post-publication verification.

Registry success is not inferred from metadata alone. Every npm network command
pins both the general and `@arbiterforge` scoped registry on the CLI so ambient
user configuration cannot redirect package traffic. The verifier installs the
exact registry version into a disposable directory with scripts disabled and
isolated empty user/global configuration, cache, and log paths; the entire root
is removed afterward. It runs npm's supported `npm audit signatures` Sigstore
verification, and then separately
binds the registry-served SLSA subject digest, repository, main ref, workflow,
protected-main source commit, and GitHub-hosted builder to the expected release.

The publish job also receives GitHub's short-lived OIDC identity solely for npm
OIDC provenance. GitHub's ephemeral `github.token` has read-only repository
permissions and is scoped to checkout and Release evidence lookup; credentials
are not persisted by checkout. Neither token is logged, written to an output, or
retained after the job. Credential rotation or revocation of `NPMJS_TOKEN` occurs in the
organization Actions secret store; no repository change or fallback credential
is permitted.

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

### Hosted static ca-codex release boundary

`ca-codex` release validation uses no authentication secret and no self-hosted
machine. Trusted verifier and packager code is checked out from the exact
release tree on GitHub-hosted runners. Any event-selected candidate tree or ZIP
is inert data: the workflow never executes its scripts, hooks, or verifier code.

Before reading entry content, the trusted candidate reader rejects an archive
larger than 8 MiB, more than 1,024 entries, any regular file larger than 2 MiB
uncompressed, more than 32 MiB total uncompressed content, or any entry whose
declared compression ratio exceeds 100:1. It accepts only safe
`plugins/ca-codex/` regular-file paths, validates the complete ZIP directory
before streaming content, and re-enforces declared and aggregate sizes while
reading. Symbolic/reparse files, encrypted entries, unsafe path normalization,
Windows-reserved names, file/directory collisions, and case or Unicode path
collisions fail closed.

The static contract then validates the plugin manifest, required Markdown front
matter, complete contained resource graph, generated parity, hook declarations
and targets, approved root vocabulary, and deterministic package identity. The
release tag, manifest, changelog, GitHub Release, provenance record, and rebuilt
archive must agree exactly. Missing, malformed, ambiguous, escaping, stale, or
mismatched evidence blocks publication.

Practical host loading is verified after publication through the supported local
Codex marketplace update and a fresh-task `$ca-doctor` check. It does not use a
Store/MSIX desktop install, device authorization, API key, copied session,
self-hosted runner, UAC, Hyper-V, ADK, VM, network mutation, screenshot, or
synthetic receipt. The retired desktop boundary remains only in immutable
historical ADRs, plans, reports, and audit records.

Pi host authentication is an external trusted-runtime boundary. **No provider
credential enters an isolated child in any form** (ADR-0019, superseding the
credential-projection clause of ADR-0016). ADR-0016 permitted projecting the
operator's selected-provider `auth.json` record into the child's private agent
directory; that placed a reusable, exfiltratable credential inside a process
running model-authored code, guarded only by transform-blocking controls over an
unbounded class of encodings.

Instead the parent binds a per-child loopback broker on `127.0.0.1:0`, projects a
provider configuration whose `baseUrl` names that listener and whose `apiKey`
references a per-child ephemeral token, and exchanges that token for the real
credential on the way upstream. The `auth.json` projection is deleted, not
disabled. Providers a bearer-substituting broker cannot serve — `amazon-bedrock`,
`google-vertex`, `github-copilot`, `openai-codex`, any `oauth` record, and any
provider with no resolvable endpoint — fail the launch closed rather than falling
back to a credential in the child. Parent and child requests name an exact
provider and model; silent fallback is prohibited.

ADR-0017 amends one further clause of that boundary for the same isolated child,
and only for **configuration** — credential projection is not widened by it. Pi
binds `models.json` to the agent directory, so a private agent directory would
otherwise strip every operator-defined endpoint, protocol, and model and silently
send the operator's key to Pi's built-in endpoint instead. `ca-pi` may therefore
open the operator-owned Pi `models.json` under the same strict size bound and
project a `models.json` holding only the exactly-selected provider's record,
carrying only credential-blind structural/protocol configuration (`baseUrl`,
`api`, `name`, `oauth`, `authHeader`, `compat`, `models[]`, `modelOverrides`). An
`apiKey` or `headers` value crosses only when the entire value is a pure
`$NAME`/`${NAME}` environment reference: that carries no secret, because it
resolves inside the child from the already-allowlisted child environment. Both
key NAMES and value SHAPES are pinned to the reviewed Pi provider schema, so a
record that satisfies the name allowlist but not the declared type (`oauth` as
anything but `"radius"`, `authHeader` as anything but a boolean) refuses instead
of projecting and then dying mutely inside Pi's own validator.

A `baseUrl` crosses as an endpoint only, and endpoint acceptance is **positive**
rather than a blocklist of credential-bearing parameter names (`api-key`, `key`,
`token`, `sig`, … is an unbounded list). A value crosses only when it is a
parseable absolute `http`/`https` URL with **no userinfo, no query, and no
fragment at all**, and a bounded route of short unencoded segments. A
provider endpoint needs neither query nor fragment — Pi's own Azure provider
takes `api-version` from `AZURE_OPENAI_API_VERSION` — so refusing them outright
closes the common real-world credential-in-endpoint shapes (`?api-key=`,
`?key=`, `#sk-…`, `/keys/sk-…`) that a userinfo-only check admitted. The rule is
deliberately narrower than what Pi accepts: an unusual endpoint fails the launch
closed rather than projecting material that cannot be shown credential-free.

Route segments are **case-insensitive** (maintainer decision, 2026-07-25). An
earlier lowercase-only rule read as a credential control but was not one:
`sk-querysecret999` satisfied it while `GPT4-Prod` — an ordinary Azure
deployment name — did not, costing that operator isolated children entirely for
no security gain. A short path segment cannot be distinguished from a legitimate
route, so the controls that bite are the ones that do not require guessing
intent: no userinfo, no query, no fragment, no percent-encoding, a bounded
segment length (which refuses realistic key material — provider keys run well
past 32 bytes), and a bounded segment count.

The stated residual is that a short route is bounded but not *provably*
credential-free, so every accepted endpoint is also registered in the child's
sensitive-value set (suppressing a child that echoes it into its final message)
and retained behind a scrub handle — the dependent controls are not blind to it.
That registration covers endpoints specifically. Other projected free-string
leaves (`provider.name`, `provider.api`, `models[].id`, `thinkingLevelMap` keys,
and the open-ended `compat` interiors Pi itself leaves untyped) cross verbatim
and are **not** in the scrub set; none carries a real-world credential
convention, and the disk half is covered regardless because the scrub handle
truncates the whole projected document.

Four things fail closed — the child is not launched and a fixed, bounded degraded
failure is returned: a **literal** (non-template) `apiKey` or header value, which
would be credential transport; a **`!command`** value, which Pi executes as a
shell command and which ADR-0016 reserves to the user; and any key or value shape
outside the reviewed Pi provider schema, whose secrecy cannot be established; a
userinfo, query-bearing, fragment-bearing, non-`http(s)`, unbounded-route, or
unparseable endpoint refuses on the same footing. No other
provider record is projected, and nothing beyond the provider record is — no
`settings.json`, no `trust.json`, no sessions, no package state, no other ambient
home data. An absent `models.json`, or one that does not configure the selected
provider, is not a failure: the child proceeds on Pi's built-in catalog exactly as
the operator's own parent would.

A `ca-pi` child environment is built from a minimal OS/runtime baseline, not a
copy of the parent environment. It explicitly excludes `FARM_API_KEY` and
`CLAUDE_CODE_OAUTH_TOKEN` and admits only necessary runtime variables plus the
selected provider's declared configuration. The child receives private home,
agent, and session roots. `PI_PACKAGE_DIR` is deliberately NOT rebound: it names
Pi's own read-only shipped-asset directory — the same installation the parent
already executes — so it carries no operator credential, session, or home data,
and rebinding it to an empty private root breaks Pi's startup before its RPC
loop exists. Under ADR-0019 no stored credential is written into the child at
all; the child's `apiKey` is a per-child ephemeral broker token. The
ADR-0017 projected `models.json` is created restrictively and is
retained by its own scrub handle: it
is credential-BLIND by construction, not provably credential-FREE, so leaving it
intact on the removal-failure path would be an unstated residual. Cleanup of the
private isolation root is idempotent and is additionally guaranteed by a
`try`/`finally` around the whole launch; the same `finally` closes the per-child
broker, so neither a stranded root nor a surviving listener can outlive the
child. Task/prompt content is
stdin-only, never argv, environment, or a temporary file. Tests use disposable
Pi homes and dummy credentials and never inspect or mutate the real auth store.
That clause is enforced by construction rather than per test file: the ca-pi
vitest suite loads `test/setup-disposable-home.ts` before any test, which
repoints every home variable Node consults (`HOME`, `USERPROFILE`, and the
Windows `HOMEDRIVE`/`HOMEPATH` pair) plus `PI_CODING_AGENT_DIR` at a `mkdtemp`
root seeded with an obviously fake record. The request fixtures spread
`process.env`, so before that redirection roughly 25 tests resolved the
operator's real `~/.pi/agent/auth.json` (issue #464). `security.test.ts` asserts
the effect - where `os.homedir()` actually resolves - not that a setup file is
listed somewhere.

All other codeArbiter-defined env vars (`FARM_MODEL`, `FARM_BASE_BRANCH`, etc.)
are non-sensitive configuration and may freely use `process.env`. Provider
environment variables remain secret-bearing external Pi inputs and are governed
by ADR-0016's child allowlist and redaction contract, not by that general rule.

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
`plan.meta.apiBaseUrl`, `FARM_DEFAULT_API_BASE_URL`, and the built-in default are
applied in that precedence — is validated by `assertSecureBaseUrl` (`farm.ts`)
both during configuration resolution and again at each fetch-producing boundary.
The guard requires the `https://` scheme (or the documented loopback `http://`
exception) and rejects userinfo on every scheme. Validation uses WHATWG `URL`
parsing — the same parser `fetch` uses for connection targeting — so there is no
parser-differential bypass. Both farm POSTs refuse automatic redirects, preventing
a validated endpoint from forwarding request bodies to an unvalidated transport.
Provider-controlled response bodies are consumed but never copied into stderr,
retry prompts, or reports; endpoint diagnostics emit only the parsed origin.
This supersedes the prior parse-time check that covered only `plan.meta.apiBaseUrl`.

**Outbound surface — the update-available notifier.** The update-notifier
(`plugins/ca/hooks/_updatelib.py`, run detached by `update-refresh.py`) makes one
outbound operation: bounded **unauthenticated HTTPS GETs** to the GitHub Releases
collection (`/repos/arbiterForge/codeArbiter/releases?per_page=100`), at most once
per day for each independently versioned release target. A refresh follows at
most ten collection pages (up to 1,000 recent releases) so quiet host series can
be found beyond the first page; exhausting that bound produces no new cached
result rather than trusting a partial enumeration. Target-keyed results are cached in the user-global
`~/.codearbiter/update-state.json`; unrelated tag prefixes are ignored. It is the
plugin's only routine outbound operation outside the farm dispatcher. Posture
per ADR-0003: `https://` is asserted on the initial URL *and* re-asserted on any
3xx via a custom redirect handler that refuses an `https://`→`http://` downgrade;
stdlib `urllib` only (ADR-0004), default verifying TLS, no `rejectUnauthorized`
equivalent. It **sends no repo content, no PII, and no secret** (User-Agent +
Accept headers only) and is **fail-silent** — any network/parse/cache error
degrades to the last known target-specific result or "no notice" and never
raises into the SessionStart or statusline hook. It adds **no synchronous network
call** to the SessionStart hot path (those hooks only read the cache; the fetch
runs in the detached refresh child).

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
- Artistic-2.0 (CI-only, exact npm CLI only): approved 2026-09-03 by
  `SUaDtL@users.noreply.github.com` solely for `npm@11.19.1` as the integrity-pinned,
  script-disabled ca-pi publication tool fetched from the approved npm registry.
  It is not approved for another package or npm version, a manifest or lockfile,
  a runtime dependency, or any shipped plugin artifact.
- CC-BY-3.0 (CI-only, one bundled data package): approved 2026-09-03 by
  `SUaDtL@users.noreply.github.com` solely for `spdx-exceptions@2.5.0` bundled
  inside exact `npm@11.19.1` as that same ca-pi publication tool. It is not
  approved generally, for another package or version, for a manifest or
  lockfile, as a runtime dependency, or in any shipped plugin artifact.

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

**Hooks-install re-probe and shared-enforcer identity are fail-safe (#194, ADR-0015).** To cut SessionStart
latency, `_githooks.install()` may skip the git-spawn hooks-dir probe when a
cheap on-disk cache proves the shims are already current. The skip fires ONLY
when it can positively, spawn-free confirm no hooks redirect: the cached dir is
exactly `<root>/.git/hooks` AND `_confirmed_no_local_hooks_path` finds no
`core.hooksPath` (a **grammar-free** case-insensitive substring scan of
`.git/config`/`.git/config.worktree` for `hookspath` — cannot under-detect any
git-config spelling) AND no `[include]` directive AND the host-neutral shims
still match the shared drop-in contract. Any read failure, any `hookspath` occurrence, an
`[include]`, a cached custom hooksPath, or a global-config change (a
`~/.gitconfig` + XDG-config mtime token invalidates the cache) → fall through to
the full probe. The fail direction is **install-when-unsure, never
skip-when-unsure** — the fast path can never leave the #161 git-enforce backstop
unwired. Accepted residual: a `$GIT_CONFIG_GLOBAL`/`$GIT_CONFIG_SYSTEM`
env-repointed config or `/etc/gitconfig` `core.hooksPath` set AFTER a
default-location install (the cold/first install always resolves those via the
full probe). The full probe does not parse `core.hooksPath` itself. It uses the
selected Git binary's `rev-parse --git-path hooks` answer, so Git's own `~`,
`%(prefix)`, absolute, relative, primary-checkout, and linked-worktree semantics
remain authoritative. Doctor resolves the same effective directory, requires
both exact managed shims there, and requires at least one live registered
enforcer. On POSIX it also requires executable shim modes. Only after exact
managed-byte validation does it ask the selected Git binary to run the managed
`pre-push` shim with empty input, exposing Git discovery, trusted-identity,
interpreter, and enforcer failures before it reports the backstop healthy.

Each host refreshes a stable, manifest-named `<plugin>.path` entry under the
repo-owned `.git/codearbiter-hooksd/`; version-directory-shaped legacy entries
are not authorities. The shim runs every live registered enforcer in
deterministic order, returns the first non-zero verdict, and blocks when none
resolve. Pre-push input is captured once and replayed identically to every
enforcer. Registry order therefore cannot let an older host plugin mask a
stricter sibling. Missing or non-regular enforcer targets do not participate in
heartbeat freshness ordering, so a dead newest heartbeat cannot suppress an
older live sibling.

This path contract is same-runtime. Windows with Git for Windows and its bundled
hook shell, native Linux, and native macOS are supported cells. WSL is not a
separately verified named cell, and sharing one physical repository or `.git`
between Windows Git and WSL Git is unsupported. Foreign linked-worktree pointer
dialects are rejected rather than translated or treated as relative marker
roots. The selected Git binary must accept the worktree and return absolute,
distinct admin and common directories before marker-root escalation. Native
absolute and native relative worktree-admin pointers in Git's default
`<main>/.git/worktrees` layout resolve to the shared primary marker root;
both the linked checkout and Git-reported primary must also own real
`CONTEXT.md` files that independently satisfy the canonical `arbiter: enabled`
frontmatter parser. A `--separate-git-dir` storage location without that governed
identity retains the local fail-closed fallback. Git does not retain a
backpointer to the user-supplied primary when the separate directory itself is
named `.git`; a storage location deliberately populated with its own enabled
context is therefore inside the local-filesystem trust boundary and may
be treated as the marker owner. Separate-git-dir remains unsupported.
On Windows, Git's own `safe.directory` decision remains authoritative for UNC
paths; codeArbiter never overrides that trust policy.

Pi's trusted Python path, Git path, and owning plugin are one atomically
replaced three-record identity bundle. Identity-less legacy hosts preserve an
existing complete bundle. An incomplete first registration or failed first
write aborts Pi activation; a refresh failure preserves a prior complete
bundle. Once an identity path exists - including a broken symlink - the shim
requires a regular bundle containing exactly three records, non-empty owner,
and existing executable files. Any malformed or stale state blocks before
enforcer dispatch; it never downgrades to ambient `PATH`. Uninstall removes the
bundle only when the uninstalling plugin owns it.

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
JSON/JSONL schemas, bounded/redacted stdout, count-only stderr, exact credential-value
rejection at the result boundary, and cross-platform
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

`.codearbiter/decisions/adr-lifecycle.jsonl` is the append-only decision-
lifecycle ledger. Its exact repository-relative path is authoritative; hook
classification also compares the path case-folded so equivalent mixed-case
spellings cannot evade protection on supported case-insensitive filesystems.
Tail append is its only permitted write shape. H-05 enforces append-only write
shape by blocking shell and Write/Edit rewrites, truncation, deletion, and
non-tail edits. The lifecycle checker separately validates JSONL syntax, event
completeness, schema, and committed-prefix integrity after bytes are written and
again in CI; H-05 does not inspect or validate appended content.
H-11 separately protects governed decision-document paths and does not replace
the ledger-specific H-05 integrity rule. In CI, the lifecycle checker reads the
base and current ledger as committed Git blobs and requires the base to be an
exact byte prefix of the current blob. A missing, unresolvable, or all-zero base
fails closed rather than weakening append-only validation.

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
(as it can defeat the `--no-verify` and shell-indirection controls,
appsec-002 / #175) — this is an accepted trust boundary, out of scope for the product's
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
**Ratified 2026-07-25 (#270 / tribunal appsec-002).** The acceptance stands: no
default-deny on `mcp__*` ships, and the write matchers are NOT extended. It is
conditioned instead on the gap being VISIBLE to whoever carries it. codeArbiter is
BUILT in this repo but RUN in consumers' repos, so the risk never manifests here
and this file reaches nobody holding it. `/ca:doctor` does: `doctor.check_mcp`
resolves the ACTIVE host's MCP configuration through `Host.mcp_config_sources()`
and WARNs, in the consumer's own repo, that MCP-tool writes are outside the write
gate. It reports a COUNT only — never a server name, command, argument, or
environment value (#449) — and degrades to SILENCE when the configuration cannot
be read, because a diagnostic that errors is worse than one that is quiet.

*Reopen conditions.* Concrete and consumer-side, replacing this clause's former
vague "if the threat model expands to untrusted agents". Any ONE reopens it:

1. A supported host gains a hook matcher (or tool-name normalization) that can
   route `mcp__<server>__<tool>` calls to `pre-write.py`. Closing the gap stops
   requiring a fork, so accepting it stops being the cheaper option.
2. A consumer reports an MCP server writing under `.codearbiter/` — CONTEXT.md, a
   `.markers/` token, `gate-events.log`, or `overrides.log` — in a repo whose
   orchestrator is cooperative. That falsifies the "a cooperating orchestrator
   does not route protected writes out of band" premise this rests on.
3. codeArbiter ships, bundles, or recommends an MCP server in a consumer install
   path. The model above assumes MCP servers are the operator's own choice;
   shipping one makes the bypass ours to own.
4. `doctor.check_mcp` stops reporting the gap on a supported host — the seam
   returns no sources, or the host's configuration location moves. The acceptance
   is conditioned on visibility, so losing visibility voids it.

---

## Protected-state registry (H-22)

`_protectedstatelib.py` (B1/#564) is a generic path->policy registry — `marker-
gated`, `helper-only`, or `append-only` — enforced by a fifth `classify_protected`
class (`"state"`) across all three flanks: `pre-write.py`/`pre-edit.py` (Write/
Edit) and `_bashguardlib.py`'s H-22 check (shell). All THREE planned consumers
are now enrolled, one per policy:

| Path | Policy | Task |
|---|---|---|
| `.codearbiter/release-targets.md` | `marker-gated` | T-33 |
| `.codearbiter/open-tasks.md` | `helper-only` | T-66 |
| `.codearbiter/done-tasks.md` | `append-only` | T-65 |

`release-targets.md` is marker-gated rather than helper-only because it has THREE sanctioned
authors (`context-creation`, the release skill's back-fill lane, and its
row-edit path), so a hard block would leave them no route; the marker is the
route. `git add` on it stays deliberately unblocked, or `commit-gate` could
not commit a sanctioned row edit. The residuals below were declared ahead of
enrolment and remain live.

**Case and canonicalization are deliberately GLOBAL, not host-filesystem-
dependent.** Both flanks — `_protectedstatelib.lookup_policy`'s registry
comparison and `_bashguardlib._state_write_res`'s shell regexes — treat a
registered path case-INSENSITIVELY and tolerate a `./` prefix, a trailing
slash, a doubled slash, and a leading/trailing space. Matching the *host*
filesystem's own case-sensitivity was considered and rejected: it varies by
platform AND by volume on the same platform (Windows/NTFS and default macOS/
APFS are case-preserving-but-insensitive; Linux ext4 and non-default macOS
volumes are case-sensitive), and `os.path.realpath` does not reliably fold
case for a path that does not yet exist on disk — exactly the case of a Write
that creates a protected-state file for the first time. A fixed,
case-insensitive rule that both flanks can apply without inspecting the
filesystem was judged safer: it only WIDENS what H-22 protects (a same-
directory file whose name differs from a registered path only by case is also
treated as protected), never narrows it.

**The bare-basename shell anchor over-matches by design, and the known false
blocks are accepted.** H-22's shell flank matches a registered file's bare
basename with NO directory prefix requirement (unlike `CONTEXT_MD`/`GATE_MARKER`)
— this is forced by spec B1 (`taskwrite add -- "fix open-tasks.md schema"` and a
bare `tee open-tasks.md` run from inside `.codearbiter/` both need to be
distinguishable/catchable with no directory prefix in the command text). The
cost, verified and accepted (the sanctioned bypass for a false block is
`/ca:override`):

- a longer filename that happens to END with a registered basename still
  matches — `> my-open-tasks.md` blocks even though it targets a different
  file. A right-edge lookahead (mirroring `DECISION_LOG_SHELL_RE`, #528) closes
  the mirror-image case (`rm .codearbiter/open-tasks.md.bak` no longer
  matches), but there is no equivalent left-edge anchor: the bare-basename
  design has no directory context available to distinguish a genuine
  no-prefix spelling from a longer name's suffix;
- a same-named file in an UNRELATED directory still matches —
  `rm node_modules/somepkg/open-tasks.md`, `tee tests/fixtures/open-tasks.md`
  — the direct, load-bearing consequence of the bare-basename anchor itself
  (see `_bashguardlib.py`'s `_state_write_res` module comment for the full
  B-07/B-08/T-08b rationale this over-match is forced by);
- a verb that only READS the protected file, then writes elsewhere, still
  matches — `cp .codearbiter/open-tasks.md /tmp/backup` — the same
  "ambiguity resolves CLOSED" stance the H-05 audit-log guard already applies
  to the identical `cp overrides.log backup` shape.

**H-22's write-verb list is wider than the H-05/H-11/H-18 baseline it was
copied from, and the extra verbs are declared, not merely implicit.** Past the
shared baseline (`rm|del|mv|cp|copy|dd|tee|sed|truncate|ni|New-Item|
Remove-Item|Move-Item|Copy-Item|Clear-Content|Set-Content|Out-File|
Add-Content`), H-22 additionally blocks `sponge` (already in H-05's
`LOG_DESTROY_RE`), `ln`, `install`, `patch`, and `shred`. `ln`/`install` are
both real, if less common, English/shell words — `npm install` and `pip
install` are common phrases that could, in principle, sit lexically near a
protected basename in an unrelated command — accepted under the same
"ambiguity resolves CLOSED" stance applied throughout this file. `git
checkout`/`git restore` (a tracked worktree file can be rewritten through git
itself, bypassing every filesystem verb) are covered by a SEPARATE regex leg,
mirroring H-05's `LOG_GIT_RESTORE_RE` (#335) — deliberately not folded into
the general verb list, so it cannot also catch `git add` (commit-gate Phase 7
runs `git add open-tasks.md` on every retained board flip, and must never trip
H-22). An arbitrary interpreter one-liner
(`python -c "open('open-tasks.md','w')..."`) is covered by a third leg
mirroring `GATE_MARKER_INTERP_RE` (#237) — the `helper-only` policy's whole
premise is that the sanctioned helper's own Python file I/O is the only
legitimate route, so an interpreter one-liner reusing that exact route while
naming the file lexically must be caught the same way #237 already catches it.
That leg matches on an INLINE-CODE SWITCH (`-c`, `-e`, `-r`, `deno eval`,
PowerShell's `-Command` and its abbreviations), not on the interpreter token
alone: running a script FILE and passing a protected basename as argv is the
sanctioned helper's own call shape, and matching it blocked every `/ca:task`
invocation whose description named an enrolled file. The interpreter list
covers `py` and `pwsh`/`powershell` — omitting them left the whole leg
bypassable on this repo's primary dev host
for gate markers.

**`touch` is deliberately excluded — two positions are recorded, not one.**
security-reviewer traced every `.codearbiter`-state mtime consumer and found
none feeds an admission decision: `marker_gated_write_admitted` stats the
*marker's* mtime, never the protected file's, so even `touch -t` back-dating a
protected file admits nothing on its own. The adversarial pass counters that
for the `helper-only` policy specifically, *creation itself* is the violation
H-11's own precedent guards against — `touch`ing an absent board would create
an empty one outside the sanctioned helper, and `DECISIONS_WRITE_RE` (H-11's
own shell flank) does include `touch` for exactly that reason. The exclusion
stands: the admission-analysis argument is decisive for what this specific
guard can observe, and including `touch` would false-block a legitimate
description like `taskwrite add -- "touch up open-tasks.md wording"`. Both
positions are recorded here so a future reader sees a considered decision, not
an oversight.

**Scanning the raw `cmd` (not the heredoc-stripped `git_view`) is a known,
consistent residual (LOW-5).** H-22's shell check, like H-05/H-11/H-18, scans
the RAW command rather than plumbing through the `git_view`/
`heredoc_shell_fallback` machinery H-19's gate-marker check uses. A heredoc
body fed to a non-shell consumer that merely QUOTES a protected filename in
prose (e.g. a PR/issue body describing this very control) could, in principle,
false-trip H-22 the same way it could H-05/H-11/H-18 before H-19 grew that
extra plumbing for its own DOTALL-crossing concern. Left as-is for
consistency with the three guards it was modeled on; revisited only if it
proves to cost more false blocks in practice than the extra plumbing is worth.

---

## Published tag immutability

Four installable tag series are published from this repository: `v*` (ca),
`ca-sandbox-v*`, `ca-codex-v*`, and `ca-pi-v*`. The README instructs consumers
to pin an exact tag, so a tag is the identity of a payload that review, CI, and
a published changelog have all vouched for.

**Control: a published tag is immutable. There is no break-glass.** Moving,
retargeting, or deleting a published tag is prohibited outright, in every
namespace, for every actor including a repository administrator. Correction of a
bad release is publication of a NEW version, which is the documented and already
practised path (`core/surface/skills/release/SKILL.md`, "Recovering from a bad
release"). This is the maintainer ruling of 2026-07-25 on issue #386: a standing
bypass credential buys almost nothing, because the recovery it would enable is
one nobody needs, while being exactly the credential an attacker would target.

**Threat.** A git tag is a mutable ref. Anything holding `contents:write` (a
compromised maintainer credential, a leaked token, an over-scoped workflow, or a
mistaken administrative operation) can retarget `v2.8.13` or `ca-pi-v0.1.1` to
arbitrary code. Pinned installs would then execute a payload that the version's
review and verification never covered, while the release notes and prior
verification continue to imply immutability. Deletion is the same weapon aimed at
availability: every pinned install breaks at once.

**Enforcement is two independent layers, because neither covers the other:**

1. *Prevention*: repository rulesets targeting tags, with `deletion` and
   `non_fast_forward` rules over the four namespaces and no bypass actors. This
   is a repository SETTING, which means it can be switched off with no diff, no
   review, and no red check anywhere.
2. *Detection*: `.github/scripts/check_tag_immutability.py`, wired into the merge
   gate as `[CHECK] | [REPO] | Published tag immutability`. It compares every
   live tag ref against the disjoint union of `.github/published-tags.json` and
   `.github/legacy-published-tags.json`, and fails on any disagreement. The first
   ledger contains original-publication receipts only. The second is ADR-0034's
   closed 44-tag epoch observed at `2026-09-04T20:45:43Z`; it is not original-publication proof
   and establishes forward detection only. Layer 2
   notices if layer 1 is removed or was never applied; a ruleset does not act
   retroactively, and GitHub's immutable-releases feature protects only releases
   published after it is enabled.

**Provenance manifest integrity.** The originally-published commit is not
recoverable from the API after a move: a moved tag is indistinguishable from a
tag that was always there, and a Release's `target_commitish` is mutable. So it
is written down. `.github/published-tags.json` records, per tag, the ref's object
sha and the commit it dereferences to; both were verified on 2026-07-25 against
the GitHub API *and* an independent local clone. Its integrity rests on git
history plus branch protection on main: amending a recorded sha requires a
reviewed pull request, whereas moving a tag requires nothing. Editing an entry to
silence a red drift run is a review-visible act and is never the correct fix.

**Legacy epoch integrity.** ADR-0034 pins the legacy ledger's exact canonical
identity-and-grade digest, source-matrix digest, observation time, 44-record
count, and 15/28/1 evidence-grade distribution. It accepts the residual risk
that a historical ref could have moved before observation, while expressly
forbidding any claim that the baseline proves original publication. The closed
set cannot be extended by a publisher or receipt reconciler: changing an
identity, source, or grade requires a new accepted, user-attributed ADR and
architectural review. Any later governed tag must enter the original-publication
ledger from its trusted receipt before another release. Deletion, retargeting,
and movement remain prohibited with no break-glass path; correction is a new
version.

**Accepted residual risk.** The detection layer is read-only and after-the-fact:
it reports a moved tag, it cannot prevent one. Between the move and the next CI
run, a consumer can install the substituted payload. Closing that window is what
layer 1 is for, which is why the ruleset is a maintainer action tracked on #386
and not satisfied by the check alone. The audit also skips loudly rather than
failing when it cannot read the refs (transport failure or rate limit); it needs
only `contents:read`, which `GITHUB_TOKEN` grants, so it runs live in ordinary CI
and a skip is an exception rather than the normal case.

**GitHub immutable Releases (AC-2).** Measured 2026-07-25: every Release on this
repository reports `immutable: false`, and the owning organisation is on the
**free** plan. Where the plan and repository support the setting it should be
enabled, but it is not a substitute for the above and cannot be one: it binds
release assets from the point it is switched on and does nothing for the 26
already-published tags. The manifest-plus-drift-audit control documented here is
the "equivalent audited control" AC-2 permits, and it stands whether or not
immutable Releases are available.

---

## Boundary crossings (declared exceptions)

| Boundary | Exception | Rationale |
|----------|-----------|-----------|
| H-03 explicit staging | `farm.ts` stages `worker.filesWritten` explicitly — previously `git add -A`, corrected 2026-06-12 | Farm worktree commits are operator-initiated, reviewed in PR |
| Fail-open on hook input parse | `_hooklib.py:read_input()` | Parse failure must not brick the session |
| Unsigned dispatcher commits | `NOSIGN` constant in `farm.ts` | CI signing servers reject unattended commits; the integration PR is the signed artifact |
| Gate command shell execution | `plan.json` `gate.commands` / `test.command` and `FARM_MUTATION_CMD` run via `cmd.exe /c` / `bash -c` in `farm.ts` | Operator-authored, length-capped (≤1024), PR-reviewed; deterministic gate by design — no untrusted source. See ADR for the trust model |
| Loopback `http://` for API base | `assertSecureBaseUrl` in `farm.ts` allows `http://127.0.0.1`/`localhost` (no userinfo); farm POSTs use `redirect: "error"` | Test mocks bind without TLS; same WHATWG parser as `fetch` → connection target is loopback, and redirect refusal prevents a mock from forwarding the body to a remote cleartext target |
| Untrusted git clone | `ca-sandbox` clones an attacker-controlled url in a throwaway, `--rm`, networked `alpine/git` container | Input is allowlisted by `validateRepoUrl` + `--` end-of-options; blast radius is the disposable clone container only (no host bind, never co-run with the sandbox) — see ADR-0007 |
| Pi selected-provider child authentication | Pi owns host authentication; `ca-pi` projects one selected stored-provider record only for an isolated child | ADR-0016 bounds the exception: private ephemeral roots, exact-provider selection, restrictive creation, retained-handle scrubbing, no observable sink, and fail-degraded cleanup |
| Pi child inference brokering | `ca-pi` binds a per-child loopback broker and projects a credential-blind `models.json` whose `apiKey` is a per-child ephemeral token; no provider credential enters the child (ADR-0019) | ADR-0017 amends ADR-0016 for **configuration only**, never credentials: exact-provider record, key AND value-shape allowlist pinned to the reviewed Pi provider schema, `apiKey`/`headers` admitted only as whole-value `$NAME`/`${NAME}` references, positively-accepted endpoint-only `baseUrl` (`http(s)`, no userinfo, no query, no fragment, bounded case-insensitive route) that is also registered in the scrub set and retained behind a scrub handle, and fail-closed rejection of literal values, `!command` forms, and unreviewed keys or shapes |
| Pi child process isolation | Fresh Pi processes run with discovery/session loading disabled and only explicit enforcement/skill/charter inputs | Cooperative process isolation for context and recursion control, not an OS sandbox; bounded IPC and process-tree cleanup limit accidental spill |
| Trusted same-process Pi extensions | An operator-approved extension may execute arbitrary same-user code in Pi's process | Accepted ADR-0010 cooperative-agent residual; final governed-argument ordering remains a live promotion STOP under ADR-0016's carried-forward controls |
| Declared release-target commands | `.codearbiter/release-targets.md` rows carry `pre-tag`, `rebuild`, and `generate` shell commands that `/ca:release` executes before composing a tag, on a lane that later holds `contents: write` | Operator-authored executable input, on the `plan.json` `gate.commands` model above and length-capped identically (≤1024 chars, `VALUE_MAX_CHARS`, ADR-0002 precedent). Three controls bound it: commands are **check-only** and a clean-tree assertion runs after each (DECISION-0034), so a mutation blocks the release rather than reaching a tag; the runner (`_releaselib.py run-pre-tag`) enforces order, first-failure stop, and that assertion mechanically rather than by agent compliance; and the declaring file is itself protected under H-22 (ADR-0024), so planting a command requires a fresh authoring marker rather than any write. The residual is the cooperative-agent one ADR-0010 already accepts: a marker-holding session can still declare a command, and this is a governance boundary, not a sandbox |
| Hosted ca-codex candidate data | A final-tree ZIP or directory is parsed by trusted release-tree code on GitHub-hosted runners | Candidate code is never executed; bounded archive limits, regular-file-only extraction semantics, contained paths, static manifest/front-matter/resource/hook validation, and exact deterministic digest binding fail closed before publication |
| CI-only npm CLI acquisition | The ca-pi publisher downloads and executes exact `npm@11.19.1` from the approved npm registry without adding it to repository dependency state | Exact registry URL and SHA-512 SRI are drift-guarded; TLS verification stays enabled and redirects are not followed; acquisition is credential-free; archive path/link/device containment and the resolved executable root are checked before exact-version execution; only the absolute reviewed CLI path reaches pack, publish, and verification; all npm network commands pin the approved general and `@arbiterforge` scoped registry, while verifier config, cache, and logs live only in its cleaned disposable root |

### Closed exceptions

- **Protected Codex desktop proof** - CLOSED 2026-08-31 (ADR-0032). The
  self-hosted runner, Hyper-V/ADK broker, device-auth, desktop receipt, and OIDC
  attestation boundary are retired. `ca-codex` now uses the credential-free
  hosted static package boundary declared above.

- **`curl | bash` nixpacks install** — CLOSED 2026-07-24 (issue #401). `build.ts`
  no longer acquires nixpacks: the pipe-to-shell branch is deleted, nixpacks is a
  documented prerequisite, and a missing prerequisite fails closed to the
  generated-Dockerfile fallback. A structural test in
  `plugins/ca-sandbox/tools/supply-chain.test.ts` keeps remote-fetch-and-execute
  out of ca-sandbox production code.

### Container image inputs

Every external container image ca-sandbox pulls is bound to a reviewed content
digest (`name:tag@sha256:<digest>`) — the clone image (`create.ts`), the
generated-Dockerfile fallback base (`build.ts`), and the `--with-claude` base
image (`claude-inside.ts`, which co-runs with `CLAUDE_CODE_OAUTH_TOKEN`). A
floating tag is a mutable registry input: a retag or registry compromise would
silently change executable code inside a sandbox build. Digest bumps are reviewed
dependency changes, and `supply-chain.test.ts` rejects `:latest` and digest-free
external image references in production code (issue #402).
