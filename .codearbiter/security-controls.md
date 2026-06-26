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

This project has no secrets vault. The only secret in the system is
`FARM_API_KEY`, the API key for the cost-arbitrage farm dispatcher.

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

All other env vars (`FARM_MODEL`, `FARM_BASE_BRANCH`, etc.) are non-sensitive
configuration and may freely use `process.env`.

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

`BlueOak-1.0.0` and `CC0-1.0` were approved 2026-06-22 (user decision via SMARTS
arbitration, checkpoint 2026-06-22) to cover transitive `site/` dependencies
(`common-ancestor-path`, `lru-cache`, `sax`; `mdn-data`). `argparse@2.0.1`
declares a `Python-2.0` SPDX field that is a packaging mislabel — upstream is
MIT — and is accepted on that basis.

Any new dependency with a license outside this list requires an explicit
review and an entry in `overrides.log` before merging.

---

## Hook security (Python)

All hook files under `plugins/ca/hooks/` must use the Python standard library
only — no third-party dependencies, ever. Hooks run on stock Python installs
with nothing additional installed.

Hook input parsing fails open (not closed) on malformed stdin — see
`_hooklib.py:read_input()` for the documented rationale.

---

## Audit trail

`overrides.log`, `triage.log`, and `sprint-log.md` are append-only artifacts.
They may never be truncated, rewritten, or deleted. The `pre-bash.py` H-05 guard
and the `pre-write.py` / `pre-edit.py` H-05 guards enforce this at every
tool-call boundary.

**Enforcement scope (accepted residual risk).** These guards are *integrity*
controls, not *completeness* controls — they protect a log once written, they do
not compel a write (see `observability-002` / the "compel a log write" CONFIRM).
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

**Automated writer of record.** One write to `overrides.log` is performed by the
framework, not a user action: on session start, if a prior session entered
`/ca:dev` and ended without `/ca:arbiter`, `session-start.py` appends a
`BY: session-cleanup | DEV: exit` close line before clearing the live dev marker
(observability-001), so the dev-mode enter/exit trail is never left half-open. It
is append-only and best-effort. This is the only writer of `overrides.log` other
than the three sanctioned mutators (`/override`, `/sprint` auto-decisions,
`/dev` entry/exit).

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
