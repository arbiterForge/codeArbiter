# ADR-0004 — Adopt Node.js/TypeScript for the Backend (Z-API + Z-WORKER)

**Status**: Accepted  
**Date**: 2026-05-04  
**Deciders**: Brennon Huff  
**Supersedes**: The implicit Python assumption in `docs/stack.md` and `CLAUDE.md §4`  
**Tradeoff level**: Level 3 — Maintainability & reviewability (CLAUDE.md §0)

---

## Context

FUSION's backend (Z-API gateway + Z-WORKER job runner) has not been built yet.
`docs/stack.md` listed FastAPI/Python as the backend choice. Before any backend
code is written — the lowest-cost point to make this decision — we re-evaluated
whether Python or Node.js/TypeScript is the better fit given FUSION's specific
constraints.

Three constraints drove the re-evaluation:

1. **Classified/air-gapped registry posture**: FUSION targets environments where
   third-party package registries may be unavailable or require internal mirrors.
   The frontend already commits to npm. Maintaining a separate PyPI mirror doubles
   the supply-chain surface for a codebase that may only reliably maintain one.

2. **AI-agent coherence**: FUSION is developed primarily by AI subagents. A
   single-language stack gives every agent a unified mental model — one lint
   config, one test runner, one type system. Cross-language agent handoffs require
   prose descriptions of API contracts that are lossy and drift-prone.

3. **Type fidelity across the stack**: The JSON Schema source of truth
   (`schemas/audit-event.schema.json`) must propagate to both frontend and backend
   types. In a dual-language stack this requires two separate code-generators,
   two CI gates, and two drift surfaces. In a full-TypeScript stack a single
   `zod` schema definition is importable by both the API route handler and the
   frontend — zero translation.

---

## Decision

**Adopt Node.js 22 LTS + Fastify + Zod + Drizzle ORM for the Z-API backend.**

Z-WORKER (Ansible/OpenTofu job execution) is implemented as a Node.js service
that invokes external tools via `child_process.spawn` with `shell: false`.

---

## Stack

| Component | Choice | Rationale |
|---|---|---|
| Runtime | Node.js 22 LTS | OpenSSL 3.x with FIPS 140-3 module; 4-year LTS window |
| HTTP framework | Fastify 5.x | Per-route JSON Schema validation built-in; explicit security defaults; 3× faster than Express |
| Input validation + types | Zod 3.x | Schema → TypeScript type in one step; importable by frontend test suites |
| ORM | Drizzle ORM | SQL-first; TypeScript-native; typed migrations; no hidden query builder magic |
| Auth token verification | `jose` | JOSE/JWK spec implementation; FIPS-compatible via system OpenSSL |
| Test runner | Vitest | Same runner, same coverage tooling, same mocking patterns as frontend |
| Linter | ESLint (`@typescript-eslint/strict`) | Same config as frontend; single `.eslintrc`-equivalent at repo root |
| Process execution | `child_process.spawn` (`shell: false`) | Identical safety posture to the prohibited `subprocess(shell=True)` rule |
| SAST | Semgrep (Node.js ruleset) | Already in stack; covers `child_process.exec()` shell injection |

---

## Consequences

### Positive

- One package registry (npm), one lockfile format, one SBOM tool run.
- Shared Zod schemas eliminate the JSON Schema → two-type-system translation
  problem that would have required two code-generators in CI.
- `schemas/audit-event.schema.json` can be consumed directly by both the backend
  route validator and the frontend audit library via a shared `packages/` workspace.
- `vitest` runs the same coverage instrumentation across frontend and backend;
  `make ci` has one unified test command.
- AI subagents do not switch language context at the API boundary.

### Negative / Mitigated

- **Python operational SDKs unavailable**: `ansible-runner`, `boto3`, `hvac` are
  Python-native. Mitigated: all three are convenience wrappers over CLI/HTTP
  interfaces. Ansible is invoked via `child_process.spawn('ansible-playbook', ...)`;
  AWS via OpenTofu subprocess; Vault via its REST API over `fetch`. No functional
  capability is lost.
- **FIPS Node.js base image required**: The FIPS 140-3 posture (SC-13) requires
  Node.js to be built against a validated OpenSSL FIPS module. Use Red Hat UBI9
  Node.js 22 image or build from source with `--openssl-fips`. This is a
  deployment configuration step, not a language capability gap.
- **Bandit B602 linting removed**: The `subprocess(shell=True)` Bandit rule is
  replaced by a Semgrep rule targeting `child_process.exec()` and `spawn` with
  `shell: true`. The hard rule in CLAUDE.md §3 is updated accordingly.
- **`validate-definitions` Makefile target**: Currently uses inline Python +
  `jsonschema` + `yaml`. Migration to a Node.js script (`scripts/validate-definitions.ts`
  + `ajv` + `js-yaml`) is tracked as a follow-up task; the Python inline is
  retained temporarily until that script exists.

---

## Rejected Alternatives

**Keep Python (FastAPI + Pydantic)**  
Rejected because: (a) doubles the registry/mirror surface for classified
environments; (b) creates a permanent type-translation layer between Python
Pydantic models and TypeScript interfaces; (c) requires AI agents to maintain
two language contexts and two code-generation pipelines for every schema change.

**Dual-language with shared JSON Schema codegen**  
Rejected because: the "two generators in CI" approach has two drift surfaces,
two failure modes, and ongoing maintenance cost on every schema change. The
structural problem persists; the solution only papers over it.

---

## References

- `docs/stack.md` (updated by this decision)
- `docs/coding-standards.md` (updated by this decision)
- `CLAUDE.md §3, §4` (updated by this decision)
- `[CONFIRM-05]` — audit sink transport (language-neutral; unaffected)
- `[CONFIRM-01]` — OIDC provider (language-neutral; unaffected)
