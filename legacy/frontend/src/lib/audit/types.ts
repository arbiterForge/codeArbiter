// Handwritten from schemas/audit-event.schema.json at S1.
// SHORTCUT [S1]: Not tooling-derived. Payback trigger: M-007 — wire
// json-schema-to-typescript in CI so this file is generated, never hand-edited.

export type ActorType = 'user' | 'service' | 'agent'
export type SubjectType =
  | 'solution'
  | 'node'
  | 'adapter'
  | 'secret_ref'
  | 'role'
  | 'schema'
  | 'key'
  | 'config'
export type Outcome = 'success' | 'failure' | 'denied'
export type Classification = 'none' | 'cui' | 'secret_ref'
export type Environment = 'prototype' | 'internal-mvp' | 'hardened-pilot' | 'production'
export type ClassUid = 3001 | 3002 | 6001 | 6002 | 6003 | 6004
export type SeverityId = 1 | 2 | 3 | 4 | 5

export interface AuditActor {
  id: string
  type: ActorType
  session_id?: string
}

export interface AuditSubject {
  type: SubjectType
  id: string
  name?: string
}

export interface AuditSource {
  request_id: string
  ip?: string
  user_agent?: string
}

export interface AuditMetadata {
  schema_version: '1.0.0'
  product: 'fusion-core'
  emit_version?: string
}

interface AuditEventBase {
  ts: string
  event_id: string
  action: string
  actor: AuditActor
  subject: AuditSubject
  source: AuditSource
  classification: Classification
  metadata: AuditMetadata
  class_uid?: ClassUid
  severity_id?: SeverityId
  git_sha?: string
  environment?: Environment
}

// Discriminated union enforces reason requirement when outcome is failure/denied.
export type AuditEvent =
  | (AuditEventBase & { outcome: 'success'; reason?: never })
  | (AuditEventBase & { outcome: 'failure' | 'denied'; reason: string })
