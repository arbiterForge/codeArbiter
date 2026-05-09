# Coding Standards

Decision: ADR-0004 — Python is no longer in the application stack. All application
code (frontend + backend) is TypeScript running on Node.js 22 LTS.

## TypeScript (applies to all src/ in frontend/ and backend/)

- ESLint (`@typescript-eslint/strict`) — same config shared between frontend and backend
- Prettier — `printWidth: 100`, `singleQuote: true`, `trailingComma: 'es5'`
- `tsc --strict` — no implicit `any`, no unchecked index access
- No `any` without `// eslint-disable-next-line @typescript-eslint/no-explicit-any` + mandatory justification comment on the same line
- No `// @ts-ignore` — use `// @ts-expect-error` with an explanation when suppression is genuinely necessary
- All public functions MUST have explicit return types
- All API boundary I/O MUST be validated with Zod at runtime. Rationale: SI-10, SA-11
- `no-console` enforced in src/ — application logging uses the structured logger (backend) or the audit library (frontend); never `console.*`

## Backend-specific (backend/src/)

- All Fastify route handlers MUST declare a Zod schema for both request body and response. Rationale: SI-10, SC-8
- All outbound HTTP calls MUST use the shared client in `backend/src/common/http.ts` (timeouts, retries, TLS, audit hook). Bare `fetch()` and `undici` outside that module are prohibited. Rationale: SC-8, AU-12. Verification: Semgrep rule denies bare `fetch(` and `new Client(` outside `common/http.ts`
- MUST NOT call `child_process.exec()` or `spawn()` with `shell: true`. Rationale: SI-10 (command injection). Verification: Semgrep rule `javascript.lang.security.audit.dangerous-spawn-shell`
- MUST NOT use `eval()`, `Function()` constructor, or `vm.runInNewContext()` on untrusted input. Rationale: SI-10
- Database access MUST use Drizzle ORM typed queries. Raw SQL permitted only in `backend/src/db/migrations/` files. Rationale: SI-10 (SQL injection)

## SQL / Migrations

- Migrations only via Drizzle Kit (`backend/drizzle/`)
- MUST NOT hand-edit the database schema directly
- MUST NOT modify a migration file after it has been applied to any environment (CM-3, SI-7)
- Each migration file MUST include a classification comment: `-- classification: none|cui|secret_ref`

## YAML

- 2-space indent
- `yamllint` config at `.yamllint`
- MUST use `js-yaml` with `safeLoad` equivalent (`yaml.load` with schema option) — never `yaml.load` with untrusted input and no schema

## API Surface Rules

- All Fastify route handlers MUST declare explicit Zod input and output schemas
- The Zod schema for each response MUST match the TypeScript return type — enforced by `zod-to-json-schema` in the OpenAPI generator
- Audit events MUST be emitted via `audit.emit()` exclusively — no direct sink calls. Verification: Semgrep rule `no-audit-events-in-app-logger`

## Commits & PRs

- `main` is protected. No force-push. No direct commits. (CM-3)
- All changes via PR; merge requires: passing CI, ≥1 CODEOWNER review, signed commits. (CM-3, AC-5)
- Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `sec:`. `sec:` triggers extra security review.
- All commits MUST be signed (`gitsign` via Sigstore [S2+] OR GPG). (SR-4, 800-218 PS.2)
- PR description MUST include: what, why, what was tested, classification of any data touched, tradeoff level cited per CLAUDE.md §0.
