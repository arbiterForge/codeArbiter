---
name: fusion-audit-emit
description: Use whenever code performs an action that needs to land in the FUSION audit trail — authentication outcomes, authorization decisions, secret reads, deployment lifecycle, schema migrations, role changes, signature verifications, key rotations. Ensures the event is emitted to Z-AUDIT (not the app logger) with all required fields and correct fail-closed semantics.
---

# FUSION Audit Emission

Audit events MUST go to Z-AUDIT via `emit(...)` from
`backend/src/lib/audit/index.ts`. They MUST NOT go through the application
logger. Mixing the two leaks audit-relevant data into unprivileged log streams
(AU-9 violation) and breaks retention guarantees.

## When This Skill Applies

The minimum auditable set, from `docs/audit-spec.md`:

- AuthN success/failure
- AuthZ denial
- Secret read
- Deployment start/end
- Teardown
- Schema migration
- Config change
- Role change
- Signature verification (cosign / SBOM / receipt)
- Key rotation

If your code performs any of these and you're not calling `emit(...)`,
you have a bug. Fix it before the PR.

## Required Fields (every event)

```typescript
import { emit } from '../lib/audit/index.js'
import { randomUUID } from 'node:crypto'

// Success outcome — reason is forbidden by the discriminated union type
void emit({
  ts: new Date().toISOString(),
  event_id: randomUUID(),
  action: 'deploy.solution',        // verb.noun per docs/audit-spec.md
  actor: { id: request.actorSub, type: 'user' },  // type: user | service | agent
  subject: { type: 'solution', id: solution.id },  // see SubjectType in types.ts
  outcome: 'success',
  source: { request_id: String(request.id) },      // Fastify request ID
  classification: 'none',           // none | cui | secret_ref
  metadata: { schema_version: '1.0.0', product: 'fusion-core' },
})

// Failure outcome — reason is REQUIRED by the discriminated union type
void emit({
  ts: new Date().toISOString(),
  event_id: randomUUID(),
  action: 'authn.failure',
  actor: { id: 'anonymous', type: 'user' },
  subject: { type: 'config', id: 'oidc' },
  outcome: 'failure',
  reason: 'invalid_token',          // required; tsc enforces this at compile time
  source: { request_id: String(request.id) },
  classification: 'none',
  metadata: { schema_version: '1.0.0', product: 'fusion-core' },
})
```

If `actor.id`, `subject.id`, or `outcome` is missing, TypeScript will reject
the call at compile time. Fix the call site — do not cast to `any`.

## Event Type Validation

Action strings are NOT registered in a runtime registry. Validity is enforced by:

1. **TypeScript**: `action` is typed as `string` with the `verb.noun` pattern
   documented in `schemas/audit-event.schema.json`. Use only actions listed in
   `docs/audit-spec.md`.
2. **JSON Schema**: `schemas/audit-event.schema.json` defines
   `"pattern": "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"` — the sink validates
   incoming events against this schema at S2+.

Known actions (from `docs/audit-spec.md`):
`authn.success`, `authn.failure`, `authz.denied`, `deploy.solution`,
`teardown.solution`, `secret.read`, `schema.migrate`, `config.change`,
`role.change`, `key.rotate`, `signature.verify`

## Fail-Closed Behavior

The current stage determines what happens when Z-AUDIT is unreachable:

- **Stage 1–2:** `emit` is fire-and-forget (`.catch(() => undefined)`). Loss is
  tolerated. Use `void emit(...)` — do NOT `await`.
- **Stage 3+:** `emit` failure MUST cause the originating request to fail with
  HTTP 503. Replace the `.catch` with rethrow and update the Fastify error handler.
  Verification: `backend/src/__tests__/audit-fail-closed.test.ts` (to be created at S3).

Wrapping `emit` in `try { ... } catch {}` with no rethrow is BANNED at all stages.

## Banned Patterns

```typescript
// BANNED — duplicate event in app logger
request.log.info({ userId: user.id }, 'secret read')
void emit({ action: 'secret.read', ... })
// Remove the log line — it duplicates the audit trail in an unprivileged stream.

// BANNED — secret value in audit event
void emit({ subject: { type: 'secret_ref', id: secretValue } })
// Use the ARN/ref, never the value.
void emit({ subject: { type: 'secret_ref', id: secretArn } })

// BANNED — silent failure
try {
  await emit({ action: 'deploy.solution', ... })
} catch {
  // swallowing errors
}

// BANNED — bare fetch() inside backend/src/lib/audit/
// Use httpPost() from backend/src/common/http.ts (trust zone rule).

// BANNED — await on emit at S1/S2 (blocks request path)
await emit({ ... })   // use void emit(...) instead
```

## How to Add a New Auditable Action

1. Verify the action name follows `verb.noun` and is listed in `docs/audit-spec.md`.
   If not listed, add it to the Auditable Event Minimum Set first.
2. Add `void emit(...)` at the correct call site with all required fields.
3. Write a test in `backend/src/__tests__/<feature>.test.ts` that:
   - Mocks `emit` via `vi.mock('../lib/audit/index.js', () => ({ emit: vi.fn().mockResolvedValue(undefined) }))`
   - Asserts `mockEmit` was called once with the correct `action`, `outcome`, and all required fields
   - Flushes fire-and-forget with `await new Promise((r) => setTimeout(r, 0))` before asserting
4. Invoke the `audit-emitter` subagent to review before opening the PR.

## Verification

Before opening a PR that adds an auditable action:

```bash
# Run the affected test file
npx vitest run backend/src/__tests__/<feature>.test.ts

# Full suite must stay green
npx vitest run

# Lint and typecheck
npm run lint && npm run typecheck
```

Cite controls: AU-2, AU-3, AU-9, AU-12 in the PR description.
