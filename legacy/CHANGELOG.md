# Changelog

<!-- Changelog format follows Keep a Changelog (https://keepachangelog.com/en/1.1.0/).
     This project uses Semantic Versioning (https://semver.org/).

     Categories per version (use only the ones that apply):
     - Added       — new features
     - Changed     — changes to existing functionality
     - Deprecated  — features that will be removed in a future version
     - Removed     — features removed in this version
     - Fixed       — bug fixes
     - Security    — vulnerability patches

     Always keep an [Unreleased] section at the top for in-progress work.
     When you cut a release, move Unreleased items into a new version heading. -->

## [Unreleased]

### Added
- Gitea Actions runner setup in progress (see docs/deploy-guide.md)
- **Semgrep custom rules** — `.semgrep/bare-fetch.yml` bans direct `fetch()` in `backend/src/**` (except `common/http.ts` and test files); `.semgrep/shell-injection.yml` bans `exec()`, `execSync()`, and `spawn(..., {shell:true})`; `make sast` now loads both rulesets alongside `--config=auto` (F-011)
- **JSON schemas for node and adapter definitions** — `schemas/node.schema.json` and `schemas/adapter.schema.json` derived from `docs/domain.md`; all required fields and enums encoded (F-007)
- **Definitions test infrastructure** — `backend/src/__tests__/definitions.test.ts`; 21 tests covering schema structure and synthetic fixture validation; `globSync`-based discovery with SHORTCUT guard pending `js-yaml` dep (F-007)
- **Step1Configure tests** — `frontend/src/__tests__/Step1Configure.test.tsx`; 26 tests covering `validateStep1` pure function (happy path, missing fields, URL validation, replicaCount bounds) and component rendering/interaction (F-008)
- **auditQuery tests** — `frontend/src/__tests__/auditQuery.test.ts`; 24 tests covering `toggleQueryToken` (add/remove, regex special-char escaping) and `clearFieldFromQuery` (global removal, edge whitespace)
- **`frontend/src/vitest.d.ts`** — triple-slash references to `vitest/globals` and `@testing-library/jest-dom`; resolves pre-existing `tsc --noEmit` failures across all frontend test files
- **Step4Monitor failure-path tests** — injected `stages` prop on `Step4Monitor` exposes a test seam; two new tests assert `outcome: 'failure'` and required `reason` field when a deployment stage fails (F-009)

### Changed
- `auth.ts` authn events now emit full OCSF-aligned audit records (action, actor, subject, outcome, reason, source, classification, metadata, class_uid) for `missing_token`, `invalid_token`, and `success` paths; env vars read lazily inside `getJwks()` to avoid static-import timing bug (F-001)
- `backend/src/lib/audit/index.ts` replaced bare `fetch()` with `httpPost()` from `common/http.ts`; satisfies SC-8/AU-12 trust-zone rule (F-004)
- `.claude/agents/audit-emitter.md` and `.claude/skills/fusion-audit-emit/SKILL.md` rewritten from Python to TypeScript; patterns now reference `void emit(...)`, `randomUUID()`, `vi.mock()`, and Vitest flush idiom (F-006)
- `Step4Monitor` exports `StageDefinition` interface and accepts optional `stages` prop (defaults to production `STAGES`) to enable test seam injection without a mock framework (F-009)
- `FusionNode` and `FusionAdapter` interfaces extend `Record<string, unknown>` to satisfy React Flow v12 `NodeProps<Node<T>>` / `EdgeProps<Edge<T>>` generic constraint

### Fixed
- `backend/src/__tests__/audit.test.ts` schema path corrected (`../../../../schemas/` → `../../../schemas/`) (F-003)
- `backend/src/__tests__/audit.test.ts` full-field assertions added for every emit call; `AbortSignal` propagation through `httpPost` confirmed (F-002)
- `FusionNodeCard.tsx` and `AdapterEdge.tsx` updated to `NodeProps<Node<FusionNode>>` and `EdgeProps<Edge<FusionAdapter>>` — resolves TS2344 errors introduced by React Flow v12 generic tightening
- `AuthProvider.test.tsx` pre-existing ESLint errors resolved (`no-extraneous-class`, `InMemoryWebStorage: Object` cast, `void _opts` in constructor)
- `Step2Compliance.test.ts` base fixture corrected from stale `DeployFormData` shape (`solutionId`/`oidcIssuer`/`replicaCount: number`) to current interface fields

---

## [0.2.0] — 2026-05-05

### Added
- **Backend scaffold** — Fastify 5 + Zod + Drizzle ORM + jose; 21 tests green; ≥84% coverage
  - Routes: `GET /health`, `GET /api/v1/solutions`, `GET /api/v1/solutions/:id`, `POST /api/v1/solutions/:id/deployments`
  - Middleware: JWT bearer token verification via OIDC JWKS; `AUTH_BYPASS` per-request guard
  - Audit: OCSF-aligned `emit()` interface; HTTP POST at Stage 1; fire-and-forget with S3 payback
  - HTTP client: `backend/src/common/http.ts` — AbortController timeout, mandatory for all outbound calls
  - DB: Drizzle ORM with PostgreSQL; schema at `backend/src/db/schema.ts`
- **Frontend auth wiring** — OIDC/PKCE flow, `AuthProvider`, `useAuth` hook, `AuthCallbackPage`
- **Frontend audit wiring** — OCSF-aligned `emit()` matches backend schema; `AuthCallbackPage` and `Step4Monitor` emit events
- **CI pipeline** — `.gitea/workflows/ci-linux.yml`; 10 parallel jobs: lockfile, secrets, lint, test, license, deps, sast, validate, sbom, all-passed sentinel
- **CODEOWNERS** — comprehensive path coverage with NIST 800-53 control citations
- **Pre-commit hooks** — TypeScript-aware: frontend/backend lint + typecheck + test:coverage; gitleaks blocking
- **4 ADRs** — 0001 (CLAUDE.md contract), 0002 (@xyflow/react v12), 0003 (OCSF audit schema), 0004 (Node.js/TypeScript backend)
- **Checkpoint document** — `docs/checkpoints/2026-05-05.md`; 50 findings; 12 BLOCKS_S2

### Changed
- Pre-commit config rewritten: Python hooks removed; TypeScript hooks added; gitleaks updated to v8.18.4 (blocking)
- Root `package.json` restructured as npm workspace root (`frontend/`, `backend/` workspaces)
- `CLAUDE.md §8` scaffold state updated to reflect current codebase reality

### Removed
- **Python stack retired** (ADR-0004): `src/`, `tests/`, `pyproject.toml` deleted; bandit, ruff, mypy, pytest removed from all tooling; `.pre-commit-config.yaml` cleaned

---

## [0.1.0] — 2026-05-04

### Added
- Initial scaffold — folder structure, standard files, CI workflow stubs
- `solution.yaml` with metadata for catalog indexing
- Pre-commit hooks configured
- Four-guide documentation structure (build, deploy, hardening, runbook)
