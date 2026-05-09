import type { FastifyRequest, FastifyReply } from 'fastify'
import { createRemoteJWKSet, jwtVerify } from 'jose'
import { randomUUID } from 'node:crypto'
import { emit } from '../lib/audit/index.js'

declare module 'fastify' {
  interface FastifyRequest {
    actorSub: string
  }
}

// All env reads are inside getJwks()/verifyToken — not at module load time —
// so tests that set env vars in beforeAll see the correct values.
let jwks: ReturnType<typeof createRemoteJWKSet> | null = null
function getJwks(): ReturnType<typeof createRemoteJWKSet> {
  if (!jwks) {
    const uri = process.env.OIDC_JWKS_URI
    if (!uri) throw new Error('OIDC_JWKS_URI not configured')
    jwks = createRemoteJWKSet(new URL(uri))
  }
  return jwks
}

// Public paths that bypass auth entirely — checked by prefix.
const PUBLIC_PREFIXES = ['/health']

export async function verifyToken(request: FastifyRequest, reply: FastifyReply): Promise<void> {
  if (PUBLIC_PREFIXES.some((p) => request.url === p || request.url.startsWith(`${p}/`))) {
    return
  }

  // Read at request time so AUTH_BYPASS can be toggled by tests without needing
  // a module reload.
  if (process.env.AUTH_BYPASS === 'true') {
    request.actorSub = 'bypass-user'
    return
  }

  const authHeader = request.headers.authorization
  if (!authHeader?.startsWith('Bearer ')) {
    void emit({
      ts: new Date().toISOString(),
      event_id: randomUUID(),
      action: 'authn.failure',
      actor: { id: 'anonymous', type: 'user' },
      subject: { type: 'config', id: 'oidc' },
      outcome: 'failure',
      reason: 'missing_token',
      source: { request_id: String(request.id) },
      classification: 'none',
      metadata: { schema_version: '1.0.0', product: 'fusion-core' },
      class_uid: 3001,
    })
    return reply.code(401).send({ error: 'missing_token' })
  }

  const token = authHeader.slice(7)
  try {
    const { payload } = await jwtVerify(token, getJwks(), {
      audience: process.env.OIDC_AUDIENCE ?? 'fusion-api',
      issuer: process.env.OIDC_ISSUER ?? '',
    })
    request.actorSub = typeof payload.sub === 'string' ? payload.sub : 'unknown'
    void emit({
      ts: new Date().toISOString(),
      event_id: randomUUID(),
      action: 'authn.success',
      actor: { id: request.actorSub, type: 'user' },
      subject: { type: 'config', id: 'oidc' },
      outcome: 'success',
      source: { request_id: String(request.id) },
      classification: 'none',
      metadata: { schema_version: '1.0.0', product: 'fusion-core' },
      class_uid: 3001,
    })
  } catch {
    void emit({
      ts: new Date().toISOString(),
      event_id: randomUUID(),
      action: 'authn.failure',
      actor: { id: 'anonymous', type: 'user' },
      subject: { type: 'config', id: 'oidc' },
      outcome: 'failure',
      reason: 'invalid_token',
      source: { request_id: String(request.id) },
      classification: 'none',
      metadata: { schema_version: '1.0.0', product: 'fusion-core' },
      class_uid: 3001,
    })
    return reply.code(401).send({ error: 'invalid_token' })
  }
}
