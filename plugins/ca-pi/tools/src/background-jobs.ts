import { types as utilTypes } from "node:util";
import { posix, win32 } from "node:path";

import type { LifecycleAuthorization } from "./contracts.ts";
import { publishActivity } from "./activity.ts";
import type { ActivityPublisher, ActivityState } from "./activity.ts";
import { openProcessTree } from "./process-tree.ts";
import type {
  ManagedProcessTree,
  ProcessTreeCleanupReason,
  ProcessTreeSpawnInput,
} from "./process-tree.ts";

export const MAX_ACTIVE_JOBS = 4;
export const JOB_OUTPUT_BYTE_LIMIT = 65_536;
export const MIN_JOB_TIMEOUT_MS = 1_000;
export const MAX_JOB_TIMEOUT_MS = 7 * 24 * 60 * 60 * 1_000;
export const MAX_RECENT_TERMINAL_JOBS = 64;
export const JOB_MANAGER_UNHEALTHY_MESSAGE = "Background job cleanup could not be verified; run /ca-doctor.";
export const MAX_JOB_COMMAND_BYTES = 131_072;
export const MAX_JOB_COMMAND_PREFIX_BYTES = 8_192;
export const MAX_JOB_ENV_ENTRIES = 256;
export const MAX_JOB_ENV_BYTES = 262_144;

const UTF8_MAX_PENDING_BYTES = 3;
const BINARY_SUFFIX_BYTE_LIMIT = JOB_OUTPUT_BYTE_LIMIT + UTF8_MAX_PENDING_BYTES;
const STRING_SUFFIX_CODE_UNIT_LIMIT = JOB_OUTPUT_BYTE_LIMIT + 1;
const STRING_SELECTED_CODE_UNIT_LIMIT = STRING_SUFFIX_CODE_UNIT_LIMIT + 1;

export const JOB_STATES = Object.freeze([
  "queued",
  "active",
  "completed",
  "failed",
  "cancelled",
  "timed-out",
] as const);

export type BackgroundJobState = (typeof JOB_STATES)[number];
export type BackgroundJobTerminalState = Extract<
  BackgroundJobState,
  "completed" | "failed" | "cancelled" | "timed-out"
>;

export interface BackgroundJobSnapshot {
  readonly id: number;
  readonly label: string;
  readonly state: BackgroundJobState;
  readonly status: string;
  readonly timeoutMs: number | null;
  readonly outputBytes: number;
}

export interface BackgroundJobManager {
  createJob(input: unknown): Readonly<BackgroundJobSnapshot> | undefined;
  transitionJob(input: unknown): Readonly<BackgroundJobSnapshot> | undefined;
  appendOutput(input: unknown): boolean;
  getJob(id: unknown): Readonly<BackgroundJobSnapshot> | undefined;
  listJobs(): readonly Readonly<BackgroundJobSnapshot>[];
  activeJobIds(): readonly number[];
  tail(id: unknown): string | undefined;
  /** Erases session state only; the composition layer must terminate and verify resources first. */
  dispose(): void;
}

export type BackgroundJobStopReason = "session-switch" | "shutdown" | "unload" | "fatal";

export interface PiShellLaunch {
  readonly command: string;
  readonly args: readonly string[];
  readonly stdin: string | undefined;
}

export interface BackgroundJobLaunchInput {
  readonly authorization: LifecycleAuthorization;
  readonly command: string;
  readonly commandPrefix?: string;
  readonly cwd: string;
  /** T13 converts Pi's OS-owned environment to this bounded entry representation. */
  readonly env: readonly (readonly [string, string | undefined])[];
  readonly label: string;
  readonly shellPath: string;
  readonly timeoutMs?: number;
}

export interface BackgroundJobRuntime {
  launch(input: BackgroundJobLaunchInput): Promise<Readonly<BackgroundJobSnapshot> | undefined>;
  cancel(id: unknown): Promise<boolean>;
  stop(reason: BackgroundJobStopReason): Promise<boolean>;
  settled(id: unknown): Promise<void>;
  health(): Readonly<{ healthy: boolean; diagnostic?: string }>;
  getJob(id: unknown): Readonly<BackgroundJobSnapshot> | undefined;
  listJobs(): readonly Readonly<BackgroundJobSnapshot>[];
  activeJobIds(): readonly number[];
  tail(id: unknown): string | undefined;
  dispose(): Promise<boolean>;
}

export interface BackgroundJobRuntimeDependencies {
  readonly openTree?: (
    command: string,
    args: readonly string[],
    options: ProcessTreeSpawnInput,
  ) => Promise<ManagedProcessTree>;
  readonly activity?: ActivityPublisher;
}

interface DataRecord {
  readonly descriptors: Readonly<Record<PropertyKey, PropertyDescriptor>>;
  readonly keys: readonly string[];
}

interface ManagerOptions {
  readonly idLimit: number;
  readonly recentTerminalLimit: number;
}

interface MutableJob {
  readonly id: number;
  readonly label: string;
  state: BackgroundJobState;
  status: string;
  readonly timeoutMs: number | null;
  output: Buffer;
  pendingUtf8: Buffer;
}

const STATE_SET = new Set<unknown>(JOB_STATES);
const TERMINAL_STATES = new Set<BackgroundJobState>(["completed", "failed", "cancelled", "timed-out"]);
const NON_TERMINAL_STATES = new Set<BackgroundJobState>(["queued", "active"]);
const LABEL_CODE_POINT_LIMIT = 128;
const LABEL_BYTE_LIMIT = 256;
const STATUS_CODE_POINT_LIMIT = 256;
const STATUS_BYTE_LIMIT = 512;
const DEFAULT_RECENT_TERMINAL_JOBS = 32;
const UNSAFE_DISPLAY = /[\u0000-\u001f\u007f-\u009f\u061c\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u206f\ufeff]/u;
const UNSAFE_OUTPUT = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u061c\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u206f\ufeff]/gu;

const DEFAULT_STATUS: Readonly<Record<BackgroundJobState, string>> = Object.freeze({
  queued: "Queued",
  active: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  "timed-out": "Timed out",
});

function fixedDataRecord(value: unknown, required: readonly string[], optional: readonly string[] = []): DataRecord | undefined {
  if (value === null || typeof value !== "object" || Array.isArray(value) || utilTypes.isProxy(value)) return undefined;
  if (Object.getPrototypeOf(value) !== Object.prototype) return undefined;
  const descriptors: Record<string, PropertyDescriptor> = {};
  const keys: string[] = [];
  for (const key of [...required, ...optional]) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (descriptor === undefined) {
      if (required.includes(key)) return undefined;
      continue;
    }
    if (!descriptor.enumerable || !("value" in descriptor)) return undefined;
    keys.push(key);
    descriptors[key] = descriptor;
  }
  return Object.freeze({ descriptors: Object.freeze(descriptors), keys: Object.freeze(keys) });
}

function hasUnpairedSurrogate(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return true;
      index += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      return true;
    }
  }
  return false;
}

function validDisplayText(value: unknown, codePointLimit: number, byteLimit: number): value is string {
  return typeof value === "string"
    && value.length > 0
    && value === value.trim()
    && !UNSAFE_DISPLAY.test(value)
    && !hasUnpairedSurrogate(value)
    && Array.from(value).length <= codePointLimit
    && Buffer.byteLength(value, "utf8") <= byteLimit;
}

function positiveSafeInteger(value: unknown, maximum: number): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 1 && value <= maximum;
}

function parseOptions(raw: unknown): ManagerOptions | undefined {
  if (raw === undefined) {
    return Object.freeze({ idLimit: Number.MAX_SAFE_INTEGER, recentTerminalLimit: DEFAULT_RECENT_TERMINAL_JOBS });
  }
  const record = fixedDataRecord(raw, [], ["idLimit", "recentTerminalLimit"]);
  if (record === undefined) return undefined;
  const hasIdLimit = record.keys.includes("idLimit");
  const hasRecentLimit = record.keys.includes("recentTerminalLimit");
  const rawIdLimit = record.descriptors.idLimit?.value as unknown;
  const rawRecentLimit = record.descriptors.recentTerminalLimit?.value as unknown;
  if ((hasIdLimit && rawIdLimit === undefined) || (hasRecentLimit && rawRecentLimit === undefined)) return undefined;
  const idLimit = rawIdLimit === undefined ? Number.MAX_SAFE_INTEGER : rawIdLimit;
  const recentTerminalLimit = rawRecentLimit === undefined ? DEFAULT_RECENT_TERMINAL_JOBS : rawRecentLimit;
  if (!positiveSafeInteger(idLimit, Number.MAX_SAFE_INTEGER)
    || !positiveSafeInteger(recentTerminalLimit, MAX_RECENT_TERMINAL_JOBS)) return undefined;
  return Object.freeze({ idLimit, recentTerminalLimit });
}

function parseId(value: unknown): number | undefined {
  return positiveSafeInteger(value, Number.MAX_SAFE_INTEGER) ? value : undefined;
}

function sanitizeOutput(value: string): string {
  return value.replace(UNSAFE_OUTPUT, "\ufffd");
}

function boundedBufferSuffix(source: Buffer, limit: number): Buffer {
  if (limit <= 0) return Buffer.alloc(0);
  if (source.length <= limit) return source;
  let start = source.length - limit;
  while (start < source.length && (source[start]! & 0xc0) === 0x80) start += 1;
  return Buffer.from(source.subarray(start));
}

function utf8SequenceLength(lead: number): number {
  if (lead >= 0xc2 && lead <= 0xdf) return 2;
  if (lead >= 0xe0 && lead <= 0xef) return 3;
  if (lead >= 0xf0 && lead <= 0xf4) return 4;
  return 0;
}

function validUtf8SecondByte(lead: number, second: number): boolean {
  if ((second & 0xc0) !== 0x80) return false;
  if (lead === 0xe0) return second >= 0xa0;
  if (lead === 0xed) return second <= 0x9f;
  if (lead === 0xf0) return second >= 0x90;
  if (lead === 0xf4) return second <= 0x8f;
  return true;
}

function incompleteUtf8TailLength(source: Buffer): number {
  if (source.length === 0) return 0;
  let start = source.length - 1;
  const earliest = Math.max(0, source.length - 4);
  while (start >= earliest && (source[start]! & 0xc0) === 0x80) start -= 1;
  if (start < earliest) return 0;
  const lead = source[start]!;
  const expected = utf8SequenceLength(lead);
  if (expected === 0) return 0;
  const actual = source.length - start;
  if (actual >= expected) return 0;
  for (let index = start + 1; index < source.length; index += 1) {
    if ((source[index]! & 0xc0) !== 0x80) return 0;
  }
  if (actual >= 2 && !validUtf8SecondByte(lead, source[start + 1]!)) return 0;
  return actual;
}

function selectStringSuffix(source: string): Readonly<{ value: string; discardedPrefix: boolean }> {
  if (source.length <= STRING_SUFFIX_CODE_UNIT_LIMIT) {
    return Object.freeze({ value: source, discardedPrefix: false });
  }
  let start = source.length - STRING_SUFFIX_CODE_UNIT_LIMIT;
  const first = source.charCodeAt(start);
  const previous = source.charCodeAt(start - 1);
  if (first >= 0xdc00 && first <= 0xdfff && previous >= 0xd800 && previous <= 0xdbff) start -= 1;
  return Object.freeze({ value: source.slice(start), discardedPrefix: true });
}

function selectBinarySuffix(source: Uint8Array): Readonly<{ value: Buffer; discardedPrefix: boolean }> {
  const start = Math.max(0, source.byteLength - BINARY_SUFFIX_BYTE_LIMIT);
  const view = source.subarray(start);
  return Object.freeze({ value: Buffer.from(view), discardedPrefix: start > 0 });
}

function nextOutput(previous: Buffer, decoded: string): Readonly<{
  output: Buffer;
  sanitizedUtf8Bytes: number;
  encodedOutputBytes: number;
}> {
  const sanitized = sanitizeOutput(decoded);
  const sanitizedUtf8Bytes = Buffer.byteLength(sanitized, "utf8");
  if (sanitized.length === 0) {
    return Object.freeze({ output: previous, sanitizedUtf8Bytes, encodedOutputBytes: 0 });
  }
  const encoded = Buffer.from(sanitized, "utf8");
  const addition = boundedBufferSuffix(encoded, JOB_OUTPUT_BYTE_LIMIT);
  const kept = boundedBufferSuffix(previous, JOB_OUTPUT_BYTE_LIMIT - addition.length);
  return Object.freeze({
    output: Buffer.concat([kept, addition], kept.length + addition.length),
    sanitizedUtf8Bytes,
    encodedOutputBytes: encoded.length,
  });
}

function snapshot(job: MutableJob): Readonly<BackgroundJobSnapshot> {
  return Object.freeze({
    id: job.id,
    label: job.label,
    state: job.state,
    status: job.status,
    timeoutMs: job.timeoutMs,
    outputBytes: job.output.length,
  });
}

function parseCreateInput(raw: unknown): Readonly<{ label: string; timeoutMs: number | null }> | undefined {
  const record = fixedDataRecord(raw, ["label"], ["timeoutMs"]);
  if (record === undefined) return undefined;
  const label = record.descriptors.label!.value as unknown;
  const hasTimeout = record.keys.includes("timeoutMs");
  const rawTimeout = record.descriptors.timeoutMs?.value as unknown;
  if (!validDisplayText(label, LABEL_CODE_POINT_LIMIT, LABEL_BYTE_LIMIT)) return undefined;
  if (hasTimeout && rawTimeout === undefined) return undefined;
  if (rawTimeout !== undefined
    && (!positiveSafeInteger(rawTimeout, MAX_JOB_TIMEOUT_MS) || rawTimeout < MIN_JOB_TIMEOUT_MS)) return undefined;
  return Object.freeze({ label, timeoutMs: rawTimeout === undefined ? null : rawTimeout as number });
}

function parseTransitionInput(
  raw: unknown,
): Readonly<{ id: number; state: BackgroundJobState; status: string | undefined }> | undefined {
  const record = fixedDataRecord(raw, ["id", "state"], ["status"]);
  if (record === undefined) return undefined;
  const id = parseId(record.descriptors.id!.value);
  const state = record.descriptors.state!.value as unknown;
  const hasStatus = record.keys.includes("status");
  const status = record.descriptors.status?.value as unknown;
  if (id === undefined || typeof state !== "string" || !STATE_SET.has(state)) return undefined;
  if (hasStatus && status === undefined) return undefined;
  if (status !== undefined && !validDisplayText(status, STATUS_CODE_POINT_LIMIT, STATUS_BYTE_LIMIT)) return undefined;
  return Object.freeze({ id, state: state as BackgroundJobState, status: status as string | undefined });
}

function parseOutputInput(raw: unknown): Readonly<{ id: number; chunk: string | Uint8Array }> | undefined {
  const record = fixedDataRecord(raw, ["id", "chunk"]);
  if (record === undefined) return undefined;
  const id = parseId(record.descriptors.id!.value);
  const chunk = record.descriptors.chunk!.value as unknown;
  if (id === undefined || utilTypes.isProxy(chunk)) return undefined;
  if (typeof chunk !== "string" && !(chunk instanceof Uint8Array)) return undefined;
  return Object.freeze({ id, chunk });
}

class SessionBackgroundJobManager implements BackgroundJobManager {
  readonly #idLimit: number;
  readonly #recentTerminalLimit: number;
  readonly #jobs = new Map<number, MutableJob>();
  readonly #terminalOrder: number[] = [];
  #nextId = 1;
  #nonTerminalCount = 0;
  #disposed = false;

  constructor(options: ManagerOptions) {
    this.#idLimit = options.idLimit;
    this.#recentTerminalLimit = options.recentTerminalLimit;
  }

  createJob(input: unknown): Readonly<BackgroundJobSnapshot> | undefined {
    try {
      const parsed = parseCreateInput(input);
      if (parsed === undefined || this.#disposed || this.#nonTerminalCount >= MAX_ACTIVE_JOBS
        || this.#nextId > this.#idLimit || !Number.isSafeInteger(this.#nextId)) return undefined;
      const id = this.#nextId;
      this.#nextId += 1;
      const job: MutableJob = {
        id,
        label: parsed.label,
        state: "queued",
        status: DEFAULT_STATUS.queued,
        timeoutMs: parsed.timeoutMs,
        output: Buffer.alloc(0),
        pendingUtf8: Buffer.alloc(0),
      };
      this.#jobs.set(id, job);
      this.#nonTerminalCount += 1;
      return snapshot(job);
    } catch {
      return undefined;
    }
  }

  transitionJob(input: unknown): Readonly<BackgroundJobSnapshot> | undefined {
    try {
      const parsed = parseTransitionInput(input);
      if (parsed === undefined || this.#disposed) return undefined;
      const job = this.#jobs.get(parsed.id);
      if (job === undefined) return undefined;

      if (job.state === parsed.state) {
        if (parsed.status !== undefined && parsed.status !== job.status) return undefined;
        return snapshot(job);
      }
      if (!NON_TERMINAL_STATES.has(job.state)) return undefined;
      if (job.state === "active" && parsed.state === "queued") return undefined;
      if (job.state === "queued" && parsed.state !== "active" && !TERMINAL_STATES.has(parsed.state)) return undefined;
      if (job.state === "active" && !TERMINAL_STATES.has(parsed.state)) return undefined;

      if (TERMINAL_STATES.has(parsed.state) && !this.#flushPending(job)) return undefined;
      job.state = parsed.state;
      job.status = parsed.status ?? DEFAULT_STATUS[parsed.state];
      if (TERMINAL_STATES.has(parsed.state)) {
        this.#nonTerminalCount -= 1;
        this.#terminalOrder.push(job.id);
        this.#pruneTerminalJobs();
      }
      return snapshot(job);
    } catch {
      return undefined;
    }
  }

  appendOutput(input: unknown): boolean {
    try {
      const parsed = parseOutputInput(input);
      if (parsed === undefined || this.#disposed) return false;
      const job = this.#jobs.get(parsed.id);
      if (job === undefined || !NON_TERMINAL_STATES.has(job.state)) return false;
      const prepared = typeof parsed.chunk === "string"
        ? this.#prepareStringAppend(job, parsed.chunk)
        : this.#prepareBinaryAppend(job, parsed.chunk);
      if (prepared === undefined) return false;
      const oldOutput = job.output;
      const oldPending = job.pendingUtf8;
      job.output = prepared.output;
      job.pendingUtf8 = prepared.pendingUtf8;
      if (oldOutput !== job.output) oldOutput.fill(0);
      if (oldPending !== job.pendingUtf8) oldPending.fill(0);
      return true;
    } catch {
      return false;
    }
  }

  getJob(id: unknown): Readonly<BackgroundJobSnapshot> | undefined {
    try {
      const parsed = parseId(id);
      if (parsed === undefined || this.#disposed) return undefined;
      const job = this.#jobs.get(parsed);
      return job === undefined ? undefined : snapshot(job);
    } catch {
      return undefined;
    }
  }

  listJobs(): readonly Readonly<BackgroundJobSnapshot>[] {
    if (this.#disposed) return Object.freeze([]);
    return Object.freeze([...this.#jobs.values()]
      .sort((left, right) => left.id - right.id)
      .map((job) => snapshot(job)));
  }

  activeJobIds(): readonly number[] {
    if (this.#disposed) return Object.freeze([]);
    return Object.freeze([...this.#jobs.values()]
      .filter((job) => NON_TERMINAL_STATES.has(job.state))
      .map((job) => job.id)
      .sort((left, right) => left - right));
  }

  tail(id: unknown): string | undefined {
    try {
      const parsed = parseId(id);
      if (parsed === undefined || this.#disposed) return undefined;
      const job = this.#jobs.get(parsed);
      return job?.output.toString("utf8");
    } catch {
      return undefined;
    }
  }

  dispose(): void {
    if (this.#disposed) return;
    this.#disposed = true;
    for (const job of this.#jobs.values()) {
      job.output.fill(0);
      job.pendingUtf8.fill(0);
    }
    this.#jobs.clear();
    this.#terminalOrder.length = 0;
    this.#nonTerminalCount = 0;
  }

  #flushPending(job: MutableJob): boolean {
    if (job.pendingUtf8.length === 0) return true;
    try {
      const decoded = new TextDecoder("utf-8", { fatal: false, ignoreBOM: true }).decode(job.pendingUtf8);
      const prepared = nextOutput(job.output, decoded);
      const oldOutput = job.output;
      const oldPending = job.pendingUtf8;
      job.output = prepared.output;
      job.pendingUtf8 = Buffer.alloc(0);
      if (oldOutput !== job.output) oldOutput.fill(0);
      oldPending.fill(0);
      return true;
    } catch {
      return false;
    }
  }

  #prepareStringAppend(job: MutableJob, source: string): Readonly<{
    output: Buffer;
    pendingUtf8: Buffer;
  }> | undefined {
    const selected = selectStringSuffix(source);
    if (selected.value.length > STRING_SELECTED_CODE_UNIT_LIMIT) return undefined;
    const bytes = Buffer.from(selected.value, "utf8");
    return this.#prepareAppend(job, bytes, selected.discardedPrefix);
  }

  #prepareBinaryAppend(job: MutableJob, source: Uint8Array): Readonly<{
    output: Buffer;
    pendingUtf8: Buffer;
  }> | undefined {
    const selected = selectBinarySuffix(source);
    if (selected.value.length > BINARY_SUFFIX_BYTE_LIMIT) return undefined;
    return this.#prepareAppend(job, selected.value, selected.discardedPrefix);
  }

  #prepareAppend(
    job: MutableJob,
    selectedBytes: Buffer,
    discardedPrefix: boolean,
  ): Readonly<{ output: Buffer; pendingUtf8: Buffer }> | undefined {
    try {
      const carry = discardedPrefix ? Buffer.alloc(0) : job.pendingUtf8;
      if (carry.length > UTF8_MAX_PENDING_BYTES) return undefined;
      const decoderInput = Buffer.concat([carry, selectedBytes], carry.length + selectedBytes.length);
      const pendingLength = incompleteUtf8TailLength(decoderInput);
      if (pendingLength > UTF8_MAX_PENDING_BYTES) return undefined;
      const decodeLength = decoderInput.length - pendingLength;
      const pendingUtf8 = Buffer.from(decoderInput.subarray(decodeLength));
      const decoded = new TextDecoder("utf-8", { fatal: false, ignoreBOM: true })
        .decode(decoderInput.subarray(0, decodeLength));
      const decodedUtf8Bytes = Buffer.byteLength(decoded, "utf8");
      const previous = discardedPrefix ? Buffer.alloc(0) : job.output;
      const prepared = nextOutput(previous, decoded);
      const maximumTransformedBytes = decoderInput.length * 3;
      if (decodedUtf8Bytes > maximumTransformedBytes
        || prepared.sanitizedUtf8Bytes > maximumTransformedBytes
        || prepared.encodedOutputBytes > maximumTransformedBytes) return undefined;
      return Object.freeze({ output: prepared.output, pendingUtf8 });
    } catch {
      return undefined;
    }
  }

  #pruneTerminalJobs(): void {
    while (this.#terminalOrder.length > this.#recentTerminalLimit) {
      const oldest = this.#terminalOrder.shift();
      if (oldest === undefined) return;
      const job = this.#jobs.get(oldest);
      if (job !== undefined && TERMINAL_STATES.has(job.state)) {
        job.output.fill(0);
        this.#jobs.delete(oldest);
      }
    }
  }
}

export function createBackgroundJobManager(options?: unknown): BackgroundJobManager | undefined {
  try {
    const parsed = parseOptions(options);
    return parsed === undefined ? undefined : new SessionBackgroundJobManager(parsed);
  } catch {
    return undefined;
  }
}

function absoluteShellPath(value: string): boolean {
  return posix.isAbsolute(value) || win32.isAbsolute(value);
}

function boundedString(value: unknown, codeUnitLimit: number, byteLimit: number, allowEmpty = false): value is string {
  return typeof value === "string"
    && (allowEmpty || value.length > 0)
    && value.length <= codeUnitLimit
    && !value.includes("\0")
    && Buffer.byteLength(value, "utf8") <= byteLimit;
}

function boundedEnvironment(value: unknown): NodeJS.ProcessEnv | undefined {
  if (!Array.isArray(value) || utilTypes.isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > MAX_JOB_ENV_ENTRIES) return undefined;
  let total = 0;
  const env: NodeJS.ProcessEnv = {};
  const names = new Set<string>();
  for (let index = 0; index < value.length; index += 1) {
    const entryDescriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (entryDescriptor === undefined || !entryDescriptor.enumerable || !("value" in entryDescriptor)) return undefined;
    const entry = entryDescriptor.value as unknown;
    if (!Array.isArray(entry) || utilTypes.isProxy(entry) || Object.getPrototypeOf(entry) !== Array.prototype || entry.length !== 2) return undefined;
    const keyDescriptor = Object.getOwnPropertyDescriptor(entry, "0");
    const valueDescriptor = Object.getOwnPropertyDescriptor(entry, "1");
    if (keyDescriptor === undefined || valueDescriptor === undefined || !keyDescriptor.enumerable || !valueDescriptor.enumerable
      || !("value" in keyDescriptor) || !("value" in valueDescriptor)) return undefined;
    const key = keyDescriptor.value as unknown;
    const item = valueDescriptor.value as unknown;
    if (!boundedString(key, 256, 512) || (item !== undefined && !boundedString(item, 32_768, 65_536, true))) {
      return undefined;
    }
    if (names.has(key)) return undefined;
    names.add(key);
    total += Buffer.byteLength(key, "utf8") + (item === undefined ? 0 : Buffer.byteLength(item, "utf8"));
    if (total > MAX_JOB_ENV_BYTES) return undefined;
    env[key] = item as string | undefined;
  }
  return env;
}

function legacyWindowsBash(shellPath: string): boolean {
  const normalized = shellPath.replaceAll("/", "\\").toLowerCase();
  return /^[a-z]:\\windows\\(?:system32|sysnative)\\bash\.exe$/u.test(normalized);
}

function authorizationCurrent(authorization: LifecycleAuthorization): boolean {
  try { return authorization.isCurrent(authorization.lease) === true; }
  catch { return false; }
}

function parseRuntimeLaunchInput(input: unknown): Readonly<{
  authorization: LifecycleAuthorization;
  cwd: string;
  env: NodeJS.ProcessEnv;
  label: unknown;
  shell: Readonly<PiShellLaunch>;
  timeoutMs?: unknown;
}> | undefined {
  const record = fixedDataRecord(
    input,
    ["authorization", "command", "cwd", "env", "label", "shellPath"],
    ["commandPrefix", "timeoutMs"],
  );
  if (record === undefined) return undefined;
  const command = record.descriptors.command?.value as unknown;
  const commandPrefix = record.descriptors.commandPrefix?.value as unknown;
  const cwd = record.descriptors.cwd?.value as unknown;
  const shellPath = record.descriptors.shellPath?.value as unknown;
  const env = boundedEnvironment(record.descriptors.env?.value);
  if (!boundedString(cwd, 4_096, 8_192) || env === undefined) return undefined;
  const shell = piShellLaunch({
    shellPath: shellPath as string,
    command: command as string,
    ...(commandPrefix === undefined ? {} : { commandPrefix: commandPrefix as string }),
  });
  if (shell === undefined) return undefined;
  return Object.freeze({
    authorization: record.descriptors.authorization?.value as LifecycleAuthorization,
    cwd,
    env,
    label: record.descriptors.label?.value,
    shell,
    ...(record.keys.includes("timeoutMs") ? { timeoutMs: record.descriptors.timeoutMs?.value } : {}),
  });
}

/** Mirrors Pi's configured bash transport, but requires T13 to supply a resolved absolute identity. */
export function piShellLaunch(input: Readonly<{
  shellPath: string;
  command: string;
  commandPrefix?: string;
}>): Readonly<PiShellLaunch> | undefined {
  const record = fixedDataRecord(input, ["shellPath", "command"], ["commandPrefix"]);
  if (record === undefined) return undefined;
  const shellPath = record.descriptors.shellPath?.value as unknown;
  const rawCommand = record.descriptors.command?.value as unknown;
  const prefix = record.descriptors.commandPrefix?.value as unknown;
  if (!boundedString(shellPath, 4_096, 8_192) || !absoluteShellPath(shellPath)) return undefined;
  if (!boundedString(rawCommand, MAX_JOB_COMMAND_BYTES, MAX_JOB_COMMAND_BYTES)) return undefined;
  if (prefix !== undefined && !boundedString(prefix, MAX_JOB_COMMAND_PREFIX_BYTES, MAX_JOB_COMMAND_PREFIX_BYTES, true)) return undefined;
  const combinedBytes = Buffer.byteLength(rawCommand, "utf8")
    + (prefix ? Buffer.byteLength(prefix, "utf8") + 1 : 0);
  if (combinedBytes > MAX_JOB_COMMAND_BYTES + MAX_JOB_COMMAND_PREFIX_BYTES + 1) return undefined;
  const command = prefix ? `${prefix}\n${rawCommand}` : rawCommand;
  if (legacyWindowsBash(shellPath)) {
    return Object.freeze({ command: shellPath, args: Object.freeze(["-s"]), stdin: command });
  }
  return Object.freeze({ command: shellPath, args: Object.freeze(["-c", command]), stdin: undefined });
}

interface RuntimeSlot {
  readonly id: number;
  readonly tree: ManagedProcessTree;
  readonly done: Promise<void>;
  readonly finish: () => void;
  timer?: ReturnType<typeof setTimeout>;
  settling?: Promise<boolean>;
}

const STOP_REASON: Readonly<Record<BackgroundJobStopReason, ProcessTreeCleanupReason>> = Object.freeze({
  "session-switch": "session_switch",
  shutdown: "shutdown",
  unload: "unload",
  fatal: "fatal_error",
});

class SessionBackgroundJobRuntime implements BackgroundJobRuntime {
  readonly #manager: BackgroundJobManager;
  readonly #openTree: NonNullable<BackgroundJobRuntimeDependencies["openTree"]>;
  readonly #activity: ActivityPublisher | undefined;
  readonly #slots = new Map<number, RuntimeSlot>();
  readonly #pendingOwnership = new Set<Promise<void>>();
  #healthy = true;
  #disposed = false;
  #stoppingReason: ProcessTreeCleanupReason | undefined;

  constructor(manager: BackgroundJobManager, dependencies: BackgroundJobRuntimeDependencies) {
    this.#manager = manager;
    this.#openTree = dependencies.openTree ?? openProcessTree;
    this.#activity = dependencies.activity;
  }

  getJob(id: unknown) { return this.#manager.getJob(id); }
  listJobs() { return this.#manager.listJobs(); }
  activeJobIds() { return this.#manager.activeJobIds(); }
  tail(id: unknown) { return this.#manager.tail(id); }

  health(): Readonly<{ healthy: boolean; diagnostic?: string }> {
    return this.#healthy
      ? Object.freeze({ healthy: true })
      : Object.freeze({ healthy: false, diagnostic: JOB_MANAGER_UNHEALTHY_MESSAGE });
  }

  async launch(input: BackgroundJobLaunchInput): Promise<Readonly<BackgroundJobSnapshot> | undefined> {
    if (this.#disposed || this.#stoppingReason !== undefined || !this.#healthy) return undefined;
    const parsed = parseRuntimeLaunchInput(input);
    if (parsed === undefined || !authorizationCurrent(parsed.authorization)) return undefined;
    const launch = parsed.shell;
    const job = this.#manager.createJob({
      label: parsed.label,
      ...(parsed.timeoutMs === undefined ? {} : { timeoutMs: parsed.timeoutMs }),
    });
    if (job === undefined) return undefined;
    this.#publish(job, "active");
    if (!authorizationCurrent(parsed.authorization)) {
      const terminal = this.#manager.transitionJob({ id: job.id, state: "cancelled" });
      if (terminal !== undefined) this.#publish(terminal, "completed");
      return undefined;
    }
    let releaseOwnership!: () => void;
    const ownership = new Promise<void>((resolveOwnership) => { releaseOwnership = resolveOwnership; });
    this.#pendingOwnership.add(ownership);
    let tree: ManagedProcessTree;
    try {
      tree = await this.#openTree(launch.command, launch.args, {
        cwd: parsed.cwd,
        env: parsed.env,
        stdio: ["pipe", "pipe", "pipe", "pipe"],
      });
    } catch {
      releaseOwnership();
      this.#pendingOwnership.delete(ownership);
      const terminal = this.#manager.transitionJob({ id: job.id, state: "failed" });
      if (terminal !== undefined) this.#publish(terminal, "completed");
      return undefined;
    }
    let finish!: () => void;
    const done = new Promise<void>((resolveDone) => { finish = resolveDone; });
    const slot: RuntimeSlot = { id: job.id, tree, done, finish };
    this.#slots.set(job.id, slot);
    releaseOwnership();
    this.#pendingOwnership.delete(ownership);
    tree.child.stdout.on("data", (chunk: unknown) => { this.#manager.appendOutput({ id: job.id, chunk }); });
    tree.child.stderr.on("data", (chunk: unknown) => { this.#manager.appendOutput({ id: job.id, chunk }); });
    tree.child.stdin.once("error", () => { void this.#settle(slot, "fatal_error", "failed"); });
    tree.child.once("error", () => { void this.#settle(slot, "fatal_error", "failed"); });
    tree.child.once("close", (code: number | null) => {
      void this.#settle(slot, "completed", code === 0 ? "completed" : "failed");
    });
    if (this.#stoppingReason !== undefined) {
      await this.#settle(slot, this.#stoppingReason, this.#stoppingReason === "fatal_error" ? "failed" : "cancelled");
      return undefined;
    }
    let ready = false;
    try { ready = await tree.cleanup.ready(); } catch { ready = false; }
    if (slot.settling !== undefined) {
      const clean = await slot.settling;
      if (!clean || this.#stoppingReason !== undefined || !this.#healthy
        || !authorizationCurrent(parsed.authorization)) return undefined;
      return this.#manager.getJob(job.id);
    }
    if (!ready) {
      await this.#settle(slot, "startup_failure", "failed");
      return undefined;
    }
    if (this.#stoppingReason !== undefined) {
      await this.#settle(slot, this.#stoppingReason, this.#stoppingReason === "fatal_error" ? "failed" : "cancelled");
      return undefined;
    }
    if (!this.#healthy || !authorizationCurrent(parsed.authorization)) {
      await this.#settle(slot, "cancelled", "cancelled");
      return undefined;
    }
    try { tree.child.stdin.end(launch.stdin); }
    catch { await this.#settle(slot, "startup_failure", "failed"); return undefined; }
    const active = this.#manager.transitionJob({ id: job.id, state: "active" });
    if (active === undefined) return this.#manager.getJob(job.id);
    if (job.timeoutMs !== null) {
      slot.timer = setTimeout(() => { void this.#settle(slot, "timeout", "timed-out"); }, job.timeoutMs);
      slot.timer.unref?.();
    }
    return active;
  }

  async cancel(id: unknown): Promise<boolean> {
    const parsed = parseId(id);
    if (parsed === undefined) return false;
    const slot = this.#slots.get(parsed);
    return slot !== undefined && await this.#settle(slot, "cancelled", "cancelled");
  }

  async stop(reason: BackgroundJobStopReason): Promise<boolean> {
    if (!Object.hasOwn(STOP_REASON, reason)) return false;
    this.#stoppingReason ??= STOP_REASON[reason];
    await Promise.all([...this.#pendingOwnership]);
    const cleanupReason = this.#stoppingReason;
    const terminal: BackgroundJobTerminalState = cleanupReason === "fatal_error" ? "failed" : "cancelled";
    const results = await Promise.all([...this.#slots.values()].map(async (slot) =>
      await this.#settle(slot, cleanupReason, terminal)));
    return results.every(Boolean);
  }

  async settled(id: unknown): Promise<void> {
    const parsed = parseId(id);
    if (parsed === undefined) return;
    await (this.#slots.get(parsed)?.done ?? Promise.resolve());
  }

  async dispose(): Promise<boolean> {
    if (this.#disposed) return true;
    const clean = await this.stop("unload");
    if (!clean || !this.#healthy) return false;
    this.#disposed = true;
    this.#manager.dispose();
    return true;
  }

  #settle(
    slot: RuntimeSlot,
    reason: ProcessTreeCleanupReason,
    terminal: BackgroundJobTerminalState,
  ): Promise<boolean> {
    if (slot.settling !== undefined) return slot.settling;
    if (slot.timer !== undefined) clearTimeout(slot.timer);
    slot.settling = (async () => {
      let verified = false;
      try { verified = (await slot.tree.cleanup.terminate(reason)).verified === true; }
      catch { verified = false; }
      if (!verified) {
        this.#healthy = false;
        return false;
      }
      const snapshot = this.#manager.transitionJob({ id: slot.id, state: terminal });
      if (snapshot !== undefined) this.#publish(snapshot, "completed");
      this.#slots.delete(slot.id);
      return true;
    })().finally(slot.finish);
    return slot.settling;
  }

  #publish(job: Readonly<BackgroundJobSnapshot>, state: ActivityState): void {
    publishActivity(this.#activity, {
      kind: "job",
      id: String(job.id),
      label: job.label,
      state,
    });
  }
}

export function createBackgroundJobRuntime(
  dependencies: BackgroundJobRuntimeDependencies = {},
): BackgroundJobRuntime | undefined {
  const manager = createBackgroundJobManager();
  return manager === undefined ? undefined : new SessionBackgroundJobRuntime(manager, dependencies);
}
