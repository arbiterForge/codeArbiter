export type AuditOutcome = 'success' | 'failure' | 'denied'
export type AuditActorType = 'user' | 'service' | 'agent'
export type AuditSubjectType =
  | 'solution'
  | 'node'
  | 'adapter'
  | 'secret_ref'
  | 'role'
  | 'schema'
  | 'key'
  | 'config'
export type AuditClassification = 'none' | 'cui' | 'secret_ref'
export type AuditEnvironment =
  | 'prototype'
  | 'internal-mvp'
  | 'hardened-pilot'
  | 'production'

// Derived from schemas/audit-event.schema.json v1.0.0
// Source of truth is the JSON Schema — do not add fields here that are not in the schema.
export interface AuditEvent {
  ts: string
  event_id: string
  action: string
  class_uid?: number
  severity_id?: number
  actor: {
    id: string
    type: AuditActorType
    session_id?: string
  }
  subject: {
    type: AuditSubjectType
    id: string
    name?: string
  }
  outcome: AuditOutcome
  reason?: string
  source: {
    request_id: string
    ip?: string
    user_agent?: string
  }
  classification: AuditClassification
  git_sha?: string
  environment?: AuditEnvironment
  metadata: {
    schema_version: string
    product: string
    emit_version?: string
  }
}
