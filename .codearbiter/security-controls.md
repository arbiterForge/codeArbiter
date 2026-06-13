# Security controls — codeArbiter

This document is the single source of truth for the project's security posture.
The `auth-crypto-reviewer`, `security-reviewer`, and `dependency-reviewer` agents
read this file before every review. The crypto-compliance and secret-handling
skills gate on this file being present.

---

## Cryptographic primitives

**Approved:** SHA-256 and the broader SHA-2 family (SHA-384, SHA-512).

**Forbidden:** MD5, SHA-1, DES, 3DES, RC4, RC2, Blowfish (in new code). These
are never acceptable regardless of context.

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

All other env vars (`FARM_MODEL`, `FARM_BASE_BRANCH`, etc.) are non-sensitive
configuration and may freely use `process.env`.

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

## Approved licenses (devDependencies)

This is a private package (`"private": true`). The following SPDX identifiers
are approved for devDependencies:

- MIT
- ISC
- Apache-2.0
- BSD-2-Clause
- BSD-3-Clause

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

`overrides.log` and `triage.log` are append-only artifacts. They may never be
truncated, rewritten, or deleted. The `pre-bash.py` H-05 guard and the
`pre-write.py` / `pre-edit.py` H-05 guards enforce this at every tool-call
boundary.

---

## Boundary crossings (declared exceptions)

| Boundary | Exception | Rationale |
|----------|-----------|-----------|
| H-03 explicit staging | `farm.ts` stages `worker.filesWritten` explicitly — previously `git add -A`, corrected 2026-06-12 | Farm worktree commits are operator-initiated, reviewed in PR |
| Fail-open on hook input parse | `_hooklib.py:read_input()` | Parse failure must not brick the session |
| Unsigned dispatcher commits | `NOSIGN` constant in `farm.ts` | CI signing servers reject unattended commits; the integration PR is the signed artifact |
| Gate command shell execution | `plan.json` `gate.commands` / `test.command` and `FARM_MUTATION_CMD` run via `cmd.exe /c` / `bash -c` in `farm.ts` | Operator-authored, length-capped (≤1024), PR-reviewed; deterministic gate by design — no untrusted source. See ADR for the trust model |
| Loopback `http://` for API base | `assertSecureBaseUrl` in `farm.ts` allows `http://127.0.0.1`/`localhost` (no userinfo) | Test mocks bind without TLS; same WHATWG parser as `fetch` → connection target is loopback, no cleartext-to-remote path |
