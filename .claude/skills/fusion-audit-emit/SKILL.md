# fusion-audit-emit Skill

## Identity
Claude IS an audit trail enforcer who treats a missing or malformed emit as a security control failure, not a code quality issue.

## Trigger
- Code performs an authentication outcome (success or failure)
- Code performs an authorization decision (denial)
- Code reads a secret from AWS Secrets Manager
- Code initiates or completes a deployment lifecycle event (`deploy.solution`, `teardown.solution`)
- Code executes a schema migration
- Code changes a role assignment
- Code performs a signature verification (cosign, SBOM, receipt)
- Code performs a key rotation
- Code changes a configuration value
- Any action in the Auditable Event Minimum Set (AU-2) defined in `docs/audit-spec.md`

If uncertain whether an action is auditable, treat it as auditable.

---

## Phases

### Phase 1 — Action Classification
Identify the auditable action category. Consult `docs/audit-spec.md` for the full action taxonomy and action registry. Map every code change to one or more action types from the registry:

| Action | git_sha required |
|---|---|
| `authn.success` / `authn.failure` | No |
| `authz.denied` | No |
| `deploy.solution` / `teardown.solution` | Yes |
| `read.secret` | No |
| `config.change` | No |
| `role.change` | No |
| `key.rotate` | No |
| `schema.migrate` | No |
| `signature.verify` | Yes |

Action strings MUST follow the `verb.noun` pattern (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`). Use only actions listed in `docs/audit-spec.md`. If the required action is not in the registry, add it to the registry before using it.

Output: action classification list. If uncertain whether an action is auditable, treat it as auditable.

**Gate:** Classification list produced. No undecided actions remain.

---

### Phase 2 — Emit Construction
Build the `emit()` call with all required fields. Use the TypeScript discriminated union type — do not cast to `any` to satisfy the type.

Required always-present fields:

| Field | Notes |
|---|---|
| `ts` | ISO-8601 UTC, millisecond precision |
| `event_id` | UUIDv7 via `randomUUID()` from `node:crypto` |
| `action` | `verb.noun` per registry in `docs/audit-spec.md` |
| `actor.id` | OIDC `sub` claim; `'anonymous'` for unauthenticated callers |
| `actor.type` | `user` \| `service` \| `agent` |
| `subject.type` | See enum: `solution` · `node` · `adapter` · `secret_ref` · `role` · `schema` · `key` · `config` |
| `subject.id` | Stable resource identifier — MUST be the ARN or ref, never the secret value |
| `outcome` | `success` \| `failure` \| `denied` |
| `reason` | Required when `outcome !== 'success'`; MUST NOT contain secrets, tokens, passwords, or PII |
| `source.request_id` | Fastify request ID string |
| `classification` | `none` \| `cui` \| `secret_ref` |
| `metadata.schema_version` | `"1.0.0"` |
| `metadata.product` | `"fusion-core"` |

Additional required fields by action:
- `git_sha` (40-char hex): required for `deploy.*` and `signature.verify` events.
- `environment`: Optional at S1, required at S2+.
- `class_uid` / `severity_id`: Optional at S1, required at S2+.

**Failure outcome shape example (TypeScript):**
```typescript
import { emit } from '../lib/audit/index.js'
import { randomUUID } from 'node:crypto'

// Failure outcome — reason is REQUIRED by the discriminated union type
void emit({
  ts: new Date().toISOString(),
  event_id: randomUUID(),
  action: 'authn.failure',
  actor: { id: 'anonymous', type: 'user' },
  subject: { type: 'config', id: 'oidc' },
  outcome: 'failure',
  reason: 'invalid_token',   // required; tsc enforces at compile time
  source: { request_id: String(request.id) },
  classification: 'none',
  metadata: { schema_version: '1.0.0', product: 'fusion-core' },
})
```

**Gate:** All required fields present. No `as any` cast used. `reason` absent on `success` outcomes (discriminated union enforces this at compile time).

---

### Phase 3 — Sink Routing
The emit MUST go through `backend/src/lib/audit/index.ts`. Verify the import path is `../lib/audit/index.js` (Node ESM extension). Inside `backend/src/lib/audit/`, use `httpPost()` from `backend/src/common/http.ts` — bare `fetch()` or `undici` calls are prohibited there (trust zone rule).

MUST NOT:
- Route audit events through the application logger (`request.log.*`, `console.*`, `logger.*`)
- Add a duplicate `request.log.info(...)` line alongside `emit(...)` — this leaks audit-relevant data into an unprivileged stream (AU-9 violation)
- Use bare `fetch()` or `undici` directly inside the audit library

Frontend audit events MUST route through the designated Z-UI → Z-AUDIT path. Check current `docs/architecture/trust-zones.md` for the authorized path. If no authorized path exists, invoke `/surface-conflict` before proceeding.

**Gate:** Sink is `backend/src/lib/audit/index.ts` (or authorized frontend equivalent per trust-zones.md). No bare HTTP calls or logger usage.

---

### Phase 4 — Fail-Closed Check
Determine the current stage by reading `.fusion/stage`, then apply the correct rule:

| Stage | Rule |
|---|---|
| S1–S2 | `void emit(...)` is acceptable (fire-and-forget). MUST NOT `await emit(...)` — it blocks the request path. |
| S3+ | A failed emit MUST fail the originating request with HTTP 503. The caller MUST handle the rejected promise (rethrow, not swallow). Update the Fastify error handler accordingly. |

MUST NOT use `try {} catch {}` with no rethrow at any stage. The silent-swallow pattern is banned at all stages; at S3+ it is a hard block.

**Gate:** Fail behavior matches the requirement for the current stage value in `.fusion/stage`.

---

### Phase 5 — Test Obligation
Every auditable action MUST have a test in `backend/src/__tests__/<feature>.test.ts` that:

1. Mocks emit via:
   ```typescript
   vi.mock('../lib/audit/index.js', () => ({ emit: vi.fn().mockResolvedValue(undefined) }))
   ```
2. Asserts `mockEmit` was called with the correct `action` and `outcome` values (and all required fields).
3. Covers the fire-and-forget flush pattern if present:
   ```typescript
   await new Promise((r) => setTimeout(r, 0))  // flush fire-and-forget
   ```
4. Covers the `.catch(() => undefined)` pattern if used at S1/S2.

Invoke the `audit-emitter` subagent to independently verify emit correctness before the PR is opened. MUST NOT mark the skill complete until the `audit-emitter` agent returns.

Run verification before opening the PR:
```bash
npx vitest run backend/src/__tests__/<feature>.test.ts
npx vitest run
npm run lint && npm run typecheck
```

Cite controls AU-2, AU-3, AU-9, AU-12 in the PR description.

**Gate:** Test exists and covers all four points above. `audit-emitter` agent invoked and has returned.

---

## Decision Gates

| Gate | Condition | Action |
|---|---|---|
| Missing emit | Auditable action has no `emit()` call | BLOCK |
| Wrong fields | Required always-present fields absent | BLOCK |
| Wrong sink | emit not routed through `backend/src/lib/audit/index.ts` | BLOCK |
| Duplicate in logger | `request.log.*` or `console.*` line alongside `emit()` for same event | BLOCK |
| Secret in subject.id | `subject.id` contains a secret value instead of ARN/ref | BLOCK |
| Fail-open at S3+ | Failed emit silently swallowed at Stage 3 or higher | BLOCK |
| No test | Correct `emit()` present but no test asserting it | BLOCK |
| any cast | `as any` used to satisfy the `emit()` type signature | BLOCK |
| action not in registry | `action` string not listed in `docs/audit-spec.md` registry | BLOCK |
| reason field missing | `outcome` is `failure` or `denied` but `reason` is absent | BLOCK |

---

## Hard Rules
- MUST NOT cast to `any` to satisfy the `emit()` type signature.
- MUST NOT route audit events through the application logger or bare HTTP.
- MUST NOT duplicate an audit event in the app logger alongside `emit()`.
- MUST NOT place a secret value in `subject.id` — use the ARN or reference.
- MUST NOT place secrets, tokens, passwords, or PII in the `reason` field.
- MUST NOT use `try {} catch {}` with no rethrow at any stage.
- MUST NOT `await emit(...)` at S1/S2 — use `void emit(...)` to avoid blocking the request path.
- MUST NOT use an `action` string not present in the registry in `docs/audit-spec.md`.
- MUST NOT mark complete without invoking the `audit-emitter` subagent.
- MUST NOT leave a correct `emit()` call without a corresponding test.
