/**
 * delegation-contract.ts - the closed, versioned contract for scoped Pi parent delegation (PI-D01).
 *
 * This is an internal codeArbiter protocol. Pi exposes no upstream delegation, grant or
 * confinement API (see pi-api.d.ts); nothing here claims otherwise.
 *
 * Execution profile `trusted-host-exact-operation-v1` (the only profile):
 * - GUARANTEE: the parent admits each exact child write/edit/bash request after its own final
 *   gate (bridge hard block, descriptor policy, live trust, mode, lifecycle, source ownership,
 *   parent TUI consent), then executes it itself with frozen arguments, records a durable
 *   exclusive claim before the effect and a durable outcome before acknowledging it.
 * - NON-GUARANTEE: no operating-system filesystem or network confinement. An admitted command
 *   runs project code with the operator's host authority; `npm test` may write anywhere and use
 *   the network. A stronger confined profile would need a separately qualified backend and must
 *   never fall back to this one silently.
 *
 * Authority rules this module encodes as data shapes:
 * - The run grant is parent-generated and lives only in parent memory. Nothing in a child
 *   request, task text, role charter, handshake attestation or journal record can mint or
 *   widen one. A restart retires every grant; a durable record never recreates a token.
 * - Admission, execution, containment, observation and recovery are five separate axes. None is
 *   inferred from another; `outcome-unknown` is never folded into failed or not-started.
 * - The child's judgment (`accepted`/`changes_requested`/`blocked`) stays a model result and is
 *   never evidence that an effect happened.
 *
 * Bootstrap: the runner writes a v2 JSON envelope on fd3 in place of the bare 32-byte nonce.
 * The child requires v2 (bounded by MAX_BOOTSTRAP_BYTES), so an old child bundle reading a
 * bare nonce and a new child reading an old runner's bare nonce both refuse before any task.
 * The operation token travels only in this envelope: never in argv, env, prompts or logs.
 */
import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

export const DELEGATION_PROFILE = "trusted-host-exact-operation-v1";
export const BOOTSTRAP_ENVELOPE_VERSION = 2;
export const MAX_BOOTSTRAP_BYTES = 512;
export const OPERATION_PROTOCOL_VERSION = 1;
/** One write's content dominates request size; bounded so a hostile child cannot exhaust memory. */
export const MAX_OPERATION_REQUEST_BYTES = 1_048_576;
export const MAX_OPERATION_RESULT_TEXT_BYTES = 65_536;
export const MAX_OPERATIONS_PER_GRANT = 256;
export const MAX_BASH_COMMAND_BYTES = 131_072;
export const MAX_BASH_TIMEOUT_SECONDS = 600;
export const MAX_EDITS_PER_OPERATION = 64;

export const DELEGATED_TOOLS = Object.freeze(["write", "edit", "bash"] as const);
export type DelegatedTool = (typeof DELEGATED_TOOLS)[number];

export const ADMISSION_STATES = Object.freeze(["admitted", "denied", "cancelled", "expired", "revoked", "unavailable"] as const);
export const EXECUTION_STATES = Object.freeze(["not-started", "executing", "completed", "failed", "outcome-unknown"] as const);
export const CONTAINMENT_STATES = Object.freeze(["not-applicable", "running", "verified-stopped", "unverified"] as const);
export const OBSERVATION_STATES = Object.freeze(["exact", "target-state-only", "unavailable", "stale"] as const);
export const RECOVERY_STATES = Object.freeze(["none", "read-only-reconciliation", "new-operation-required", "dependent-resource-held"] as const);
export type AdmissionState = (typeof ADMISSION_STATES)[number];
export type ExecutionState = (typeof EXECUTION_STATES)[number];
export type ContainmentState = (typeof CONTAINMENT_STATES)[number];
export type ObservationState = (typeof OBSERVATION_STATES)[number];
export type RecoveryState = (typeof RECOVERY_STATES)[number];

/** Fixed, value-free reason codes. A response never carries free text from the gate. */
export const DELEGATION_REASONS = Object.freeze([
  "protocol-invalid",
  "token-invalid",
  "sequence-invalid",
  "digest-mismatch",
  "operation-id-reused",
  "grant-expired",
  "grant-revoked",
  "grant-exhausted",
  "tool-not-delegated",
  "target-invalid",
  "permission-denied",
  "journal-unavailable",
  "executor-failed",
  "executor-unavailable",
  "busy",
] as const);
export type DelegationReason = (typeof DELEGATION_REASONS)[number];

const HEX32 = /^[0-9a-f]{32}$/u;
const HEX64 = /^[0-9a-f]{64}$/u;
const REQUEST_ID = /^[A-Za-z0-9_-]{1,64}$/u;
const ENDPOINT = /^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})\/v1\/operation$/u;

export class DelegationContractError extends Error {
  constructor(readonly reason: DelegationReason) {
    super(`codeArbiter delegation refused (${reason}).`);
    this.name = "DelegationContractError";
  }
}

function refuse(reason: DelegationReason): never {
  throw new DelegationContractError(reason);
}

function plainRecord(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value) || utilTypes.isProxy(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function exactKeys(value: Record<string, unknown>, required: readonly string[], optional: readonly string[] = []): boolean {
  const keys = Object.keys(value);
  return required.every((key) => Object.prototype.hasOwnProperty.call(value, key))
    && keys.every((key) => required.includes(key) || optional.includes(key))
    && Reflect.ownKeys(value).length === keys.length;
}

function boundedText(value: unknown, maxBytes: number): value is string {
  return typeof value === "string" && !value.includes("\0") && Buffer.byteLength(value, "utf8") <= maxBytes;
}

/** Deterministic JSON: sorted keys, finite numbers, plain data only. Throws on anything else. */
export function canonicalJson(value: unknown, depth = 0): string {
  if (depth > 16) refuse("protocol-invalid");
  if (value === null || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") return Number.isFinite(value) ? JSON.stringify(value) : refuse("protocol-invalid");
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value) && !utilTypes.isProxy(value)) {
    return `[${value.map((item) => canonicalJson(item, depth + 1)).join(",")}]`;
  }
  if (!plainRecord(value)) refuse("protocol-invalid");
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key], depth + 1)}`).join(",")}}`;
}

/** The exact-request digest binds tool, frozen parameters and the execution profile. */
export function operationDigest(tool: DelegatedTool, params: Readonly<Record<string, unknown>>): string {
  return createHash("sha256")
    .update(canonicalJson({ profile: DELEGATION_PROFILE, tool, params }), "utf8")
    .digest("hex");
}

// ---------------------------------------------------------------- bootstrap envelope (fd3) ---

export interface DelegationEndpoint {
  readonly endpoint: string;
  readonly token: string;
}

export interface BootstrapEnvelope {
  readonly nonce: string;
  /** Absent for reviewers, compaction and any author whose parent could not establish authority. */
  readonly delegation?: DelegationEndpoint;
}

export function encodeBootstrapEnvelope(envelope: BootstrapEnvelope): string {
  if (!HEX32.test(envelope.nonce)) refuse("protocol-invalid");
  if (envelope.delegation !== undefined
    && (!ENDPOINT.test(envelope.delegation.endpoint) || !HEX64.test(envelope.delegation.token))) refuse("protocol-invalid");
  const text = JSON.stringify({
    v: BOOTSTRAP_ENVELOPE_VERSION,
    nonce: envelope.nonce,
    ...(envelope.delegation === undefined ? {} : {
      delegation: { endpoint: envelope.delegation.endpoint, token: envelope.delegation.token },
    }),
  });
  if (Buffer.byteLength(text, "utf8") > MAX_BOOTSTRAP_BYTES) refuse("protocol-invalid");
  return text;
}

export function decodeBootstrapEnvelope(text: string): BootstrapEnvelope {
  if (typeof text !== "string" || Buffer.byteLength(text, "utf8") > MAX_BOOTSTRAP_BYTES) refuse("protocol-invalid");
  let value: unknown;
  try { value = JSON.parse(text); } catch { refuse("protocol-invalid"); }
  if (!plainRecord(value) || !exactKeys(value, ["v", "nonce"], ["delegation"])
    || value.v !== BOOTSTRAP_ENVELOPE_VERSION || typeof value.nonce !== "string" || !HEX32.test(value.nonce)) {
    refuse("protocol-invalid");
  }
  if (value.delegation === undefined) return Object.freeze({ nonce: value.nonce });
  const delegation = value.delegation;
  if (!plainRecord(delegation) || !exactKeys(delegation, ["endpoint", "token"])
    || typeof delegation.endpoint !== "string" || !ENDPOINT.test(delegation.endpoint)
    || Number(ENDPOINT.exec(delegation.endpoint)![1]) > 65_535
    || typeof delegation.token !== "string" || !HEX64.test(delegation.token)) refuse("protocol-invalid");
  return Object.freeze({
    nonce: value.nonce,
    delegation: Object.freeze({ endpoint: delegation.endpoint, token: delegation.token }),
  });
}

// ------------------------------------------------------------------ operation request ---

export interface OperationRequest {
  readonly v: typeof OPERATION_PROTOCOL_VERSION;
  /** Strictly increasing per grant, starting at 1. A reused or skipped-back value is refused. */
  readonly seq: number;
  /** Child-chosen opaque id. It names an attempt; it never carries authority. */
  readonly requestId: string;
  readonly tool: DelegatedTool;
  readonly params: Readonly<Record<string, unknown>>;
  readonly digest: string;
}

/** Validates the tool's own parameter schema (observed in Pi 1.1.0 dist/core/tools). Only
 * these keys are admitted, because the parent executes the operation itself and must know
 * every field it is asked to honor. */
export function validDelegatedParams(tool: DelegatedTool, params: unknown): params is Record<string, unknown> {
  if (!plainRecord(params)) return false;
  if (tool === "write") {
    return exactKeys(params, ["path", "content"])
      && boundedText(params.path, 4_096) && params.path !== ""
      && boundedText(params.content, MAX_OPERATION_REQUEST_BYTES);
  }
  if (tool === "edit") {
    const edits = params.edits;
    return exactKeys(params, ["path", "edits"])
      && boundedText(params.path, 4_096) && params.path !== ""
      && Array.isArray(edits) && !utilTypes.isProxy(edits)
      && edits.length > 0 && edits.length <= MAX_EDITS_PER_OPERATION
      && edits.every((edit) => plainRecord(edit) && exactKeys(edit, ["oldText", "newText"])
        && boundedText(edit.oldText, MAX_OPERATION_REQUEST_BYTES) && edit.oldText !== ""
        && boundedText(edit.newText, MAX_OPERATION_REQUEST_BYTES));
  }
  return exactKeys(params, ["command"], ["timeout"])
    && boundedText(params.command, MAX_BASH_COMMAND_BYTES) && params.command.trim() !== ""
    && (params.timeout === undefined || (typeof params.timeout === "number" && Number.isFinite(params.timeout)
      && params.timeout > 0 && params.timeout <= MAX_BASH_TIMEOUT_SECONDS));
}

export function encodeOperationRequest(
  input: Readonly<{ seq: number; requestId: string; tool: DelegatedTool; params: Readonly<Record<string, unknown>> }>,
): string {
  if (!Number.isSafeInteger(input.seq) || input.seq < 1 || !REQUEST_ID.test(input.requestId)
    || !DELEGATED_TOOLS.includes(input.tool) || !validDelegatedParams(input.tool, input.params)) refuse("protocol-invalid");
  const text = canonicalJson({
    v: OPERATION_PROTOCOL_VERSION,
    seq: input.seq,
    requestId: input.requestId,
    tool: input.tool,
    params: input.params,
    digest: operationDigest(input.tool, input.params),
  });
  if (Buffer.byteLength(text, "utf8") > MAX_OPERATION_REQUEST_BYTES) refuse("protocol-invalid");
  return text;
}

/** Decodes untrusted request bytes. Any authority-shaped field (grant, run, role, consent,
 * approved, cwd, generation...) is simply an unknown key and refuses the whole request. */
export function decodeOperationRequest(text: string): OperationRequest {
  if (typeof text !== "string" || Buffer.byteLength(text, "utf8") > MAX_OPERATION_REQUEST_BYTES) refuse("protocol-invalid");
  let value: unknown;
  try { value = JSON.parse(text); } catch { refuse("protocol-invalid"); }
  if (!plainRecord(value) || !exactKeys(value, ["v", "seq", "requestId", "tool", "params", "digest"])
    || value.v !== OPERATION_PROTOCOL_VERSION
    || !Number.isSafeInteger(value.seq) || (value.seq as number) < 1
    || typeof value.requestId !== "string" || !REQUEST_ID.test(value.requestId)
    || typeof value.tool !== "string" || !(DELEGATED_TOOLS as readonly string[]).includes(value.tool)
    || typeof value.digest !== "string" || !HEX64.test(value.digest)) refuse("protocol-invalid");
  const tool = value.tool as DelegatedTool;
  if (!validDelegatedParams(tool, value.params)) refuse("protocol-invalid");
  if (operationDigest(tool, value.params) !== value.digest) refuse("digest-mismatch");
  return Object.freeze({
    v: OPERATION_PROTOCOL_VERSION,
    seq: value.seq as number,
    requestId: value.requestId,
    tool,
    params: value.params,
    digest: value.digest,
  });
}

// ----------------------------------------------------------------- operation response ---

export interface OperationResult {
  readonly content: readonly Readonly<{ type: "text"; text: string }>[];
  readonly isError: boolean;
}

export interface OperationResponse {
  readonly v: typeof OPERATION_PROTOCOL_VERSION;
  readonly requestId: string;
  readonly admission: AdmissionState;
  readonly execution: ExecutionState;
  readonly containment: ContainmentState;
  readonly observation: ObservationState;
  readonly recovery: RecoveryState;
  readonly reason?: DelegationReason;
  /** Present only when the parent observed an executor result to return to the child. */
  readonly result?: OperationResult;
}

function validResult(value: unknown): value is OperationResult {
  return plainRecord(value) && exactKeys(value, ["content", "isError"]) && typeof value.isError === "boolean"
    && Array.isArray(value.content) && value.content.length <= 16
    && value.content.every((block) => plainRecord(block) && exactKeys(block, ["type", "text"])
      && block.type === "text" && boundedText(block.text, MAX_OPERATION_RESULT_TEXT_BYTES));
}

/** Cross-axis consistency: refuses combinations that would let one axis imply another falsely. */
function consistentAxes(response: Omit<OperationResponse, "v">): boolean {
  const { admission, execution, result, reason } = response;
  if (admission !== "admitted") {
    // Nothing ran: no effect, no result, and the refusal must say why. `stale` observation is
    // admissible here (a precondition observed to have changed before admission).
    return execution === "not-started" && result === undefined && reason !== undefined
      && response.containment === "not-applicable";
  }
  if (response.observation === "stale" && execution !== "failed") return false;
  // A joined duplicate or bounded wait reports the live claim; no result exists yet.
  if (execution === "executing") return result === undefined && response.recovery !== "none";
  if (response.containment === "running") return false;
  if (execution === "completed") return result !== undefined && reason === undefined;
  if (execution === "outcome-unknown") return result === undefined && response.recovery !== "none";
  if (execution === "failed") return reason !== undefined || result !== undefined;
  // admitted + not-started: claim/journal failed before any effect.
  return result === undefined && reason !== undefined;
}

export function encodeOperationResponse(response: Omit<OperationResponse, "v">): string {
  const full = { v: OPERATION_PROTOCOL_VERSION, ...response } as OperationResponse;
  decodeOperationResponse(JSON.stringify(full));
  return JSON.stringify(full);
}

export function decodeOperationResponse(text: string): OperationResponse {
  if (typeof text !== "string" || Buffer.byteLength(text, "utf8") > 16 * MAX_OPERATION_RESULT_TEXT_BYTES + 4_096) refuse("protocol-invalid");
  let value: unknown;
  try { value = JSON.parse(text); } catch { refuse("protocol-invalid"); }
  if (!plainRecord(value)
    || !exactKeys(value, ["v", "requestId", "admission", "execution", "containment", "observation", "recovery"], ["reason", "result"])
    || value.v !== OPERATION_PROTOCOL_VERSION
    || typeof value.requestId !== "string" || !REQUEST_ID.test(value.requestId)
    || !(ADMISSION_STATES as readonly unknown[]).includes(value.admission)
    || !(EXECUTION_STATES as readonly unknown[]).includes(value.execution)
    || !(CONTAINMENT_STATES as readonly unknown[]).includes(value.containment)
    || !(OBSERVATION_STATES as readonly unknown[]).includes(value.observation)
    || !(RECOVERY_STATES as readonly unknown[]).includes(value.recovery)
    || (value.reason !== undefined && !(DELEGATION_REASONS as readonly unknown[]).includes(value.reason))
    || (value.result !== undefined && !validResult(value.result))) refuse("protocol-invalid");
  const response = value as unknown as OperationResponse;
  if (!consistentAxes(response)) refuse("protocol-invalid");
  return Object.freeze(response);
}

/** A refusal: nothing was admitted, so nothing executed and there is nothing to recover. */
export function refusalResponse(requestId: string, admission: Exclude<AdmissionState, "admitted">, reason: DelegationReason): Omit<OperationResponse, "v"> {
  return Object.freeze({
    requestId: REQUEST_ID.test(requestId) ? requestId : "invalid",
    admission,
    execution: "not-started",
    containment: "not-applicable",
    observation: "unavailable",
    recovery: "new-operation-required",
    reason,
  });
}

// ----------------------------------------------------------------------- run grant ---

/** The parent-only live capability. Never serialized; the journal stores identities only. */
export interface RunGrant {
  readonly runId: string;
  readonly role: string;
  /** SHA-256 of the actual host tool-call id of the parent dispatch call. */
  readonly callerCorrelation: string;
  /** Strictly observed canonical worktree root (realpath, no lexical fallback). */
  readonly worktree: string;
  readonly tools: readonly DelegatedTool[];
  readonly maxOperations: number;
  /** Parent-monotonic expiry (performance.now() milliseconds); wall-clock changes cannot extend it. */
  readonly expiresAtMonotonicMs: number;
}

export function validRunGrant(value: RunGrant): boolean {
  return plainRecord(value as unknown) && HEX32.test(value.runId) && typeof value.role === "string" && value.role !== ""
    && HEX64.test(value.callerCorrelation) && typeof value.worktree === "string" && value.worktree !== ""
    && Array.isArray(value.tools) && value.tools.length > 0
    && value.tools.every((tool) => (DELEGATED_TOOLS as readonly string[]).includes(tool))
    && new Set(value.tools).size === value.tools.length
    && Number.isSafeInteger(value.maxOperations) && value.maxOperations > 0 && value.maxOperations <= MAX_OPERATIONS_PER_GRANT
    && Number.isFinite(value.expiresAtMonotonicMs);
}

// ------------------------------------------------------------------ journal records ---

export const JOURNAL_RECORD_VERSION = 1;
export const JOURNAL_PHASES = Object.freeze(["claimed", "observed"] as const);
export type JournalPhase = (typeof JOURNAL_PHASES)[number];

/** One bounded, secret-free record. Contents and full command text are never stored: only the
 * request digest, target identity and observed outcome. A claim without an observation after
 * restart is `outcome-unknown`, never "not executed". */
export interface JournalRecord {
  readonly v: typeof JOURNAL_RECORD_VERSION;
  readonly phase: JournalPhase;
  readonly operationId: string;
  readonly runId: string;
  readonly callerCorrelation: string;
  readonly role: string;
  readonly tool: DelegatedTool;
  readonly digest: string;
  readonly profile: typeof DELEGATION_PROFILE;
  /** Target path relative to the worktree, for file tools; absent for bash. */
  readonly target?: string;
  /** SHA-256 of target bytes before (claim) or after (observed); "absent" when no file existed. */
  readonly targetHash?: string;
  readonly execution?: Exclude<ExecutionState, "not-started">;
  readonly containment?: ContainmentState;
  readonly recordedAt: string;
}

const OPERATION_ID = /^[0-9a-f]{64}$/u;
const TARGET_HASH = /^(?:[0-9a-f]{64}|absent|unreadable)$/u;

export function decodeJournalRecord(text: string): JournalRecord {
  if (typeof text !== "string" || Buffer.byteLength(text, "utf8") > 8_192) refuse("protocol-invalid");
  let value: unknown;
  try { value = JSON.parse(text); } catch { refuse("protocol-invalid"); }
  if (!plainRecord(value)) refuse("protocol-invalid");
  const observed = value.phase === "observed";
  if (!exactKeys(value,
    ["v", "phase", "operationId", "runId", "callerCorrelation", "role", "tool", "digest", "profile", "recordedAt",
      ...(observed ? ["execution", "containment"] : [])],
    ["target", "targetHash"])
    || value.v !== JOURNAL_RECORD_VERSION
    || !(JOURNAL_PHASES as readonly unknown[]).includes(value.phase)
    || typeof value.operationId !== "string" || !OPERATION_ID.test(value.operationId)
    || typeof value.runId !== "string" || !HEX32.test(value.runId)
    || typeof value.callerCorrelation !== "string" || !HEX64.test(value.callerCorrelation)
    || !boundedText(value.role, 128) || value.role === ""
    || !(DELEGATED_TOOLS as readonly unknown[]).includes(value.tool)
    || typeof value.digest !== "string" || !HEX64.test(value.digest)
    || value.profile !== DELEGATION_PROFILE
    || !boundedText(value.recordedAt, 32) || Number.isNaN(Date.parse(value.recordedAt))
    || (value.target !== undefined && (!boundedText(value.target, 4_096) || value.target === ""))
    || (value.targetHash !== undefined && (typeof value.targetHash !== "string" || !TARGET_HASH.test(value.targetHash)))
    || (observed && (!["completed", "failed", "outcome-unknown"].includes(value.execution as string)
      || !(CONTAINMENT_STATES as readonly unknown[]).includes(value.containment)))) refuse("protocol-invalid");
  return Object.freeze(value as unknown as JournalRecord);
}

/** The durable operation identity: parent-random run id + the child's request id. The digest is
 * deliberately NOT part of it, so a reused request id with different bytes lands on the same
 * record and is detected as `operation-id-reused` instead of silently becoming a new effect.
 * Two runs with identical task text and role still differ because runId is parent-random. */
export function operationId(runId: string, requestId: string): string {
  if (!HEX32.test(runId) || !REQUEST_ID.test(requestId)) refuse("protocol-invalid");
  return createHash("sha256").update(`${runId}\n${requestId}`, "utf8").digest("hex");
}
