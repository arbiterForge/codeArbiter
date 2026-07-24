import { createHash } from "node:crypto";
import { isAbsolute } from "node:path";
import { types as utilTypes } from "node:util";
import { callPlanFileBridge } from "./bridge.ts";
import type { BridgePort } from "./contracts.ts";
import type { PolicyMode } from "./policy.ts";

export const PLAN_SESSION_ENTRY_TYPE = "codearbiter.plan-mode.v1";

export const PLAN_TASK_STATUSES = Object.freeze(["PENDING", "IN_PROGRESS", "ACCEPTED"] as const);
export type PlanTaskStatus = (typeof PLAN_TASK_STATUSES)[number];
export type PlanDisposition = "draft" | "approved";

export interface PlanTaskState {
  readonly id: string;
  readonly status: PlanTaskStatus;
}

export interface ActivePlanState {
  readonly slug: string;
  readonly specPath: string;
  readonly planPath: string;
  /** The plan Markdown status column is the ledger; version one creates no parallel task file. */
  readonly ledgerPath: string;
  readonly disposition: PlanDisposition;
  readonly tasks: readonly PlanTaskState[];
}

export interface PlanSessionState {
  readonly version: 1;
  readonly revision: number;
  readonly mode: PolicyMode;
  readonly activePlan: ActivePlanState;
}

const CONTROL = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u061c\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/u;
const SLUG = /^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$/u;
const TASK_ID = /^[A-Za-z0-9](?:[A-Za-z0-9]|[-.](?=[A-Za-z0-9])){0,63}$/u;
const MAX_PLAN_CONTENT_BYTES = 92_160;
const MAX_LEDGER_LINES = 10_000;
const MAX_TASKS = 256;
const MAX_ENTRIES = 4_096;
const MAX_ENTRY_BYTES = 16_384;
const MAX_REVISION = Number.MAX_SAFE_INTEGER;
const TASK_HEADERS = new Set(["#", "id", "task", "task id"]);

interface DataRecord {
  readonly descriptors: Readonly<Record<PropertyKey, PropertyDescriptor>>;
  readonly keys: readonly string[];
}

export type PlanFileOperation =
  | Readonly<{ kind: "read" }>
  | Readonly<{ kind: "replace"; content: string }>
  | Readonly<{ kind: "transition"; taskId: string; status: PlanTaskStatus }>;

export type PlanFileOperationResult =
  | Readonly<{ ok: false }>
  | Readonly<{ ok: false; committed: true; content?: string; state?: PlanSessionState }>
  | Readonly<{ ok: true; content: string; state: PlanSessionState }>;

const OPERATION_FAILED = Object.freeze({ ok: false } as const);

function plainDataRecord(value: unknown): DataRecord | undefined {
  if (value === null || typeof value !== "object" || Array.isArray(value) || utilTypes.isProxy(value)) return undefined;
  if (Object.getPrototypeOf(value) !== Object.prototype) return undefined;
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string" || key === "__proto__" || key === "prototype" || key === "constructor")) return undefined;
  const descriptors = Object.getOwnPropertyDescriptors(value) as Readonly<Record<PropertyKey, PropertyDescriptor>>;
  for (const key of keys as string[]) {
    const descriptor = descriptors[key];
    if (descriptor === undefined || !("value" in descriptor) || descriptor.enumerable !== true) return undefined;
  }
  return Object.freeze({ descriptors, keys: Object.freeze(keys as string[]) });
}

function exactKeys(record: DataRecord, keys: readonly string[]): boolean {
  return record.keys.length === keys.length && keys.every((key) => record.keys.includes(key));
}

function safeArray(value: unknown, limit: number): readonly unknown[] | undefined {
  if (!Array.isArray(value) || utilTypes.isProxy(value)) return undefined;
  const descriptors = Object.getOwnPropertyDescriptors(value) as Record<string, PropertyDescriptor>;
  const lengthDescriptor = descriptors.length;
  if (lengthDescriptor === undefined || !("value" in lengthDescriptor)
    || typeof lengthDescriptor.value !== "number" || !Number.isInteger(lengthDescriptor.value)
    || lengthDescriptor.value < 0 || lengthDescriptor.value > limit) return undefined;
  const length = lengthDescriptor.value;
  if (Reflect.ownKeys(value).length !== length + 1) return undefined;
  const output: unknown[] = [];
  for (let index = 0; index < length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (descriptor === undefined || !("value" in descriptor) || descriptor.enumerable !== true) return undefined;
    output.push(descriptor.value);
  }
  return Object.freeze(output);
}

function frozenTask(id: string, status: PlanTaskStatus): PlanTaskState {
  return Object.freeze({ id, status });
}

function freezeActivePlan(input: Omit<ActivePlanState, "tasks"> & { tasks: readonly PlanTaskState[] }): ActivePlanState {
  return Object.freeze({ ...input, tasks: Object.freeze([...input.tasks]) });
}

function freezeState(input: Omit<PlanSessionState, "activePlan"> & { activePlan: ActivePlanState }): PlanSessionState {
  return Object.freeze({ ...input, activePlan: freezeActivePlan(input.activePlan) });
}

function pathsFor(slug: string): Readonly<{ specPath: string; planPath: string; ledgerPath: string }> {
  const planPath = `.codearbiter/plans/${slug}.md`;
  return Object.freeze({
    specPath: `.codearbiter/specs/${slug}.md`,
    planPath,
    ledgerPath: planPath,
  });
}

interface TableCell {
  readonly value: string;
  readonly start: number;
  readonly end: number;
}

function tableRow(line: string): readonly TableCell[] | undefined {
  const trimmed = line.trim();
  if (!trimmed.startsWith("|") || !trimmed.endsWith("|")) return undefined;
  const outerStart = line.indexOf(trimmed);
  const bodyStart = outerStart + 1;
  const bodyEnd = outerStart + trimmed.length - 1;
  const cells: TableCell[] = [];
  let start = bodyStart;
  for (let index = bodyStart; index < bodyEnd; index += 1) {
    if (line[index] !== "|") continue;
    let slashes = 0;
    for (let cursor = index - 1; cursor >= bodyStart && line[cursor] === "\\"; cursor -= 1) slashes += 1;
    if (slashes % 2 === 1) continue;
    const raw = line.slice(start, index);
    const leading = raw.match(/^\s*/u)?.[0].length ?? 0;
    const trailing = raw.match(/\s*$/u)?.[0].length ?? 0;
    cells.push(Object.freeze({ value: raw.trim(), start: start + leading, end: index - trailing }));
    start = index + 1;
  }
  const raw = line.slice(start, bodyEnd);
  const leading = raw.match(/^\s*/u)?.[0].length ?? 0;
  const trailing = raw.match(/\s*$/u)?.[0].length ?? 0;
  cells.push(Object.freeze({ value: raw.trim(), start: start + leading, end: bodyEnd - trailing }));
  return Object.freeze(cells);
}

function splitTableRow(line: string): readonly string[] | undefined {
  return tableRow(line)?.map((cell) => cell.value);
}

function isSeparator(cells: readonly string[], width: number): boolean {
  return cells.length === width && cells.every((cell) => /^:?-{3,}:?$/u.test(cell));
}

function taskStatus(cell: string): PlanTaskStatus | undefined {
  const normalized = cell.trim();
  if (/^(?:PENDING|QUEUED)$/u.test(normalized)) return "PENDING";
  if (/^IN[-_]PROGRESS$/u.test(normalized)) return "IN_PROGRESS";
  if (/^ACCEPTED(?:\s+(?:—|-)\s+[^\r\n]+)?$/u.test(normalized)) return "ACCEPTED";
  return undefined;
}

/** Parses the single canonical Markdown Status table into stable task identities. */
export function parsePlanLedger(markdown: unknown): readonly PlanTaskState[] | undefined {
  try {
    if (typeof markdown !== "string" || CONTROL.test(markdown) || /\r(?!\n)/u.test(markdown)
      || Buffer.byteLength(markdown, "utf8") > MAX_PLAN_CONTENT_BYTES) return undefined;
    const lines = markdown.replace(/\r\n/gu, "\n").split("\n");
    if (lines.length > MAX_LEDGER_LINES) return undefined;
    let found: readonly PlanTaskState[] | undefined;
    for (let lineIndex = 0; lineIndex < lines.length - 1; lineIndex += 1) {
      const header = splitTableRow(lines[lineIndex]!);
      const separator = splitTableRow(lines[lineIndex + 1]!);
      if (header === undefined || separator === undefined || !isSeparator(separator, header.length)) continue;
      const normalizedHeaders = header.map((cell) => cell.toLowerCase().replace(/\s+/gu, " "));
      const taskColumns = normalizedHeaders.flatMap((cell, index) => TASK_HEADERS.has(cell) ? [index] : []);
      const statusColumns = normalizedHeaders.flatMap((cell, index) => cell === "status" ? [index] : []);
      if (taskColumns.length !== 1 || statusColumns.length !== 1) {
        if (statusColumns.length > 0) return undefined;
        continue;
      }
      if (found !== undefined) return undefined;
      const tasks: PlanTaskState[] = [];
      const ids = new Set<string>();
      for (let rowIndex = lineIndex + 2; rowIndex < lines.length; rowIndex += 1) {
        const cells = splitTableRow(lines[rowIndex]!);
        if (cells === undefined) break;
        if (cells.length !== header.length) return undefined;
        const id = cells[taskColumns[0]!]!;
        const status = taskStatus(cells[statusColumns[0]!]!);
        if (!TASK_ID.test(id) || CONTROL.test(id) || status === undefined || ids.has(id)) return undefined;
        ids.add(id);
        tasks.push(frozenTask(id, status));
        if (tasks.length > MAX_TASKS) return undefined;
      }
      if (tasks.length === 0) return undefined;
      found = Object.freeze(tasks);
    }
    return found;
  } catch {
    return undefined;
  }
}

function normalizeTasks(value: unknown): readonly PlanTaskState[] | undefined {
  const items = safeArray(value, MAX_TASKS);
  if (items === undefined || items.length === 0) return undefined;
  const tasks: PlanTaskState[] = [];
  const ids = new Set<string>();
  for (const item of items) {
    const record = plainDataRecord(item);
    if (record === undefined || !exactKeys(record, ["id", "status"])) return undefined;
    const id = record.descriptors.id!.value as unknown;
    const status = record.descriptors.status!.value as unknown;
    if (typeof id !== "string" || !TASK_ID.test(id) || CONTROL.test(id) || ids.has(id)
      || typeof status !== "string" || !PLAN_TASK_STATUSES.includes(status as PlanTaskStatus)) return undefined;
    ids.add(id);
    tasks.push(frozenTask(id, status as PlanTaskStatus));
  }
  return Object.freeze(tasks);
}

function normalizeActivePlan(value: unknown): ActivePlanState | undefined {
  const record = plainDataRecord(value);
  if (record === undefined || !exactKeys(record, [
    "slug", "specPath", "planPath", "ledgerPath", "disposition", "tasks",
  ])) return undefined;
  const slug = record.descriptors.slug!.value as unknown;
  const disposition = record.descriptors.disposition!.value as unknown;
  if (typeof slug !== "string" || !SLUG.test(slug) || CONTROL.test(slug)
    || disposition !== "draft" && disposition !== "approved") return undefined;
  const canonical = pathsFor(slug);
  if (record.descriptors.specPath!.value !== canonical.specPath
    || record.descriptors.planPath!.value !== canonical.planPath
    || record.descriptors.ledgerPath!.value !== canonical.ledgerPath) return undefined;
  const tasks = normalizeTasks(record.descriptors.tasks!.value);
  if (tasks === undefined) return undefined;
  return freezeActivePlan({ slug, ...canonical, disposition, tasks });
}

function normalizeState(value: unknown): PlanSessionState | undefined {
  const record = plainDataRecord(value);
  if (record === undefined || !exactKeys(record, ["version", "revision", "mode", "activePlan"])) return undefined;
  const version = record.descriptors.version!.value as unknown;
  const revision = record.descriptors.revision!.value as unknown;
  const mode = record.descriptors.mode!.value as unknown;
  if (version !== 1 || typeof revision !== "number" || !Number.isSafeInteger(revision)
    || revision < 1 || revision > MAX_REVISION || mode !== "plan" && mode !== "execute") return undefined;
  const activePlan = normalizeActivePlan(record.descriptors.activePlan!.value);
  if (activePlan === undefined || mode === "plan" && activePlan.disposition !== "draft") return undefined;
  const state = freezeState({ version: 1, revision, mode, activePlan });
  return serializedStateFits(state) ? state : undefined;
}

function serializedStateFits(state: PlanSessionState): boolean {
  try {
    return Buffer.byteLength(JSON.stringify(state), "utf8") <= MAX_ENTRY_BYTES;
  } catch {
    return false;
  }
}

export function enterPlan(slug: unknown, markdown: unknown): PlanSessionState | undefined {
  if (typeof slug !== "string" || !SLUG.test(slug) || CONTROL.test(slug)) return undefined;
  const tasks = parsePlanLedger(markdown);
  if (tasks === undefined) return undefined;
  const state = freezeState({
    version: 1,
    revision: 1,
    mode: "plan",
    activePlan: freezeActivePlan({ slug, ...pathsFor(slug), disposition: "draft", tasks }),
  });
  return serializedStateFits(state) ? state : undefined;
}

const FORWARD: Readonly<Record<PlanTaskStatus, readonly PlanTaskStatus[]>> = Object.freeze({
  PENDING: Object.freeze(["PENDING", "IN_PROGRESS", "ACCEPTED"] as const),
  IN_PROGRESS: Object.freeze(["IN_PROGRESS", "ACCEPTED"] as const),
  ACCEPTED: Object.freeze(["ACCEPTED"] as const),
});

export function transitionPlanTask(
  rawState: PlanSessionState,
  taskId: unknown,
  nextStatus: unknown,
): PlanSessionState | undefined {
  const state = normalizeState(rawState);
  if (state === undefined || state.mode !== "plan" || typeof taskId !== "string" || !TASK_ID.test(taskId)
    || typeof nextStatus !== "string" || !PLAN_TASK_STATUSES.includes(nextStatus as PlanTaskStatus)) return undefined;
  const index = state.activePlan.tasks.findIndex((task) => task.id === taskId);
  if (index < 0) return undefined;
  const current = state.activePlan.tasks[index]!;
  if (!FORWARD[current.status].includes(nextStatus as PlanTaskStatus)) return undefined;
  if (current.status === nextStatus) return state;
  if (state.revision >= MAX_REVISION) return undefined;
  const tasks = state.activePlan.tasks.map((task, taskIndex) => taskIndex === index
    ? frozenTask(task.id, nextStatus as PlanTaskStatus)
    : task);
  const next = freezeState({
    ...state,
    revision: state.revision + 1,
    activePlan: freezeActivePlan({ ...state.activePlan, tasks }),
  });
  return serializedStateFits(next) ? next : undefined;
}

/** Returns Markdown with one forward task transition applied to its canonical Status cell. */
export function updatePlanLedger(
  markdown: unknown,
  taskId: unknown,
  nextStatus: unknown,
): string | undefined {
  const tasks = parsePlanLedger(markdown);
  if (tasks === undefined || typeof markdown !== "string" || typeof taskId !== "string"
    || typeof nextStatus !== "string" || !PLAN_TASK_STATUSES.includes(nextStatus as PlanTaskStatus)) return undefined;
  const task = tasks.find((candidate) => candidate.id === taskId);
  if (task === undefined || !FORWARD[task.status].includes(nextStatus as PlanTaskStatus)
    || task.status === nextStatus) return undefined;
  const lines: Array<Readonly<{ text: string; start: number }>> = [];
  let lineStart = 0;
  for (let index = 0; index <= markdown.length; index += 1) {
    if (index < markdown.length && markdown[index] !== "\n") continue;
    const lineEnd = index > lineStart && markdown[index - 1] === "\r" ? index - 1 : index;
    lines.push(Object.freeze({ text: markdown.slice(lineStart, lineEnd), start: lineStart }));
    lineStart = index + 1;
  }
  for (let lineIndex = 0; lineIndex < lines.length - 1; lineIndex += 1) {
    const header = splitTableRow(lines[lineIndex]!.text);
    const separator = splitTableRow(lines[lineIndex + 1]!.text);
    if (header === undefined || separator === undefined || !isSeparator(separator, header.length)) continue;
    const normalizedHeaders = header.map((cell) => cell.toLowerCase().replace(/\s+/gu, " "));
    const taskColumn = normalizedHeaders.findIndex((cell) => TASK_HEADERS.has(cell));
    const statusColumn = normalizedHeaders.findIndex((cell) => cell === "status");
    if (taskColumn < 0 || statusColumn < 0) continue;
    for (let rowIndex = lineIndex + 2; rowIndex < lines.length; rowIndex += 1) {
      const cells = tableRow(lines[rowIndex]!.text);
      if (cells === undefined) break;
      if (cells[taskColumn]?.value !== taskId) continue;
      const statusCell = cells[statusColumn];
      if (statusCell === undefined) return undefined;
      const replacement = nextStatus === "IN_PROGRESS" ? "IN-PROGRESS" : nextStatus;
      const absoluteStart = lines[rowIndex]!.start + statusCell.start;
      const absoluteEnd = lines[rowIndex]!.start + statusCell.end;
      return `${markdown.slice(0, absoluteStart)}${replacement}${markdown.slice(absoluteEnd)}`;
    }
  }
  return undefined;
}

function leavePlan(rawState: PlanSessionState, disposition: PlanDisposition): PlanSessionState | undefined {
  const state = normalizeState(rawState);
  if (state === undefined || state.mode !== "plan" || state.revision >= MAX_REVISION) return undefined;
  const next = freezeState({
    ...state,
    revision: state.revision + 1,
    mode: "execute",
    activePlan: freezeActivePlan({ ...state.activePlan, disposition }),
  });
  return serializedStateFits(next) ? next : undefined;
}

export function approvePlan(state: PlanSessionState): PlanSessionState | undefined {
  return leavePlan(state, "approved");
}

export function cancelPlan(state: PlanSessionState): PlanSessionState | undefined {
  return leavePlan(state, "draft");
}

/** Replaces session task statuses with the current on-disk status cells; IDs must match exactly. */
export function reconcilePlanState(rawState: PlanSessionState, markdown: unknown): PlanSessionState | undefined {
  const state = normalizeState(rawState);
  const diskTasks = parsePlanLedger(markdown);
  if (state === undefined || diskTasks === undefined || diskTasks.length !== state.activePlan.tasks.length) return undefined;
  if (!diskTasks.every((task, index) => task.id === state.activePlan.tasks[index]!.id)) return undefined;
  const reconciled = freezeState({ ...state, activePlan: freezeActivePlan({ ...state.activePlan, tasks: diskTasks }) });
  return serializedStateFits(reconciled) ? reconciled : undefined;
}

/** Returns bounded plain data suitable for Pi's appendEntry(customType, data) API. */
export function encodePlanSessionState(rawState: PlanSessionState): PlanSessionState | undefined {
  const state = normalizeState(rawState);
  if (state === undefined) return undefined;
  try {
    return serializedStateFits(state) ? state : undefined;
  } catch {
    return undefined;
  }
}

function entryData(value: unknown): Readonly<{ matched: boolean; data?: unknown }> | undefined {
  const record = plainDataRecord(value);
  if (record === undefined || record.keys.length > 32) return undefined;
  const type = record.descriptors.type;
  if (type === undefined || !("value" in type) || typeof type.value !== "string") return Object.freeze({ matched: false });
  if (type.value !== "custom") return Object.freeze({ matched: false });
  const customType = record.descriptors.customType;
  if (customType === undefined || !("value" in customType) || typeof customType.value !== "string") return undefined;
  if (customType.value !== PLAN_SESSION_ENTRY_TYPE) return Object.freeze({ matched: false });
  if (!exactKeys(record, ["type", "id", "parentId", "timestamp", "customType", "data"])) return undefined;
  const data = record.descriptors.data;
  if (data === undefined || !("value" in data)) return undefined;
  return Object.freeze({ matched: true, data: data.value });
}

/** Restores only the latest matching Pi custom entry, then lets disk task statuses win. */
export function restorePlanSessionState(entries: unknown, markdown: unknown): PlanSessionState | undefined {
  const list = safeArray(entries, MAX_ENTRIES);
  if (list === undefined) return undefined;
  for (let index = list.length - 1; index >= 0; index -= 1) {
    const candidate = entryData(list[index]);
    if (candidate === undefined) return undefined;
    if (!candidate.matched) continue;
    const state = normalizeState(candidate.data);
    if (state === undefined) return undefined;
    try {
      if (Buffer.byteLength(JSON.stringify(state), "utf8") > MAX_ENTRY_BYTES) return undefined;
    } catch {
      return undefined;
    }
    return reconcilePlanState(state, markdown);
  }
  return undefined;
}


function normalizeOperation(raw: unknown): PlanFileOperation | undefined {
  const record = plainDataRecord(raw);
  if (record === undefined) return undefined;
  const kind = record.descriptors.kind?.value as unknown;
  if (kind === "read" && exactKeys(record, ["kind"])) return Object.freeze({ kind });
  if (kind === "replace" && exactKeys(record, ["kind", "content"])) {
    const content = record.descriptors.content!.value as unknown;
    if (typeof content !== "string" || CONTROL.test(content) || /\r(?!\n)/u.test(content)
      || Buffer.byteLength(content, "utf8") > MAX_PLAN_CONTENT_BYTES) return undefined;
    return Object.freeze({ kind, content });
  }
  if (kind === "transition" && exactKeys(record, ["kind", "taskId", "status"])) {
    const taskId = record.descriptors.taskId!.value as unknown;
    const status = record.descriptors.status!.value as unknown;
    if (typeof taskId !== "string" || !TASK_ID.test(taskId) || typeof status !== "string"
      || !PLAN_TASK_STATUSES.includes(status as PlanTaskStatus)) return undefined;
    return Object.freeze({ kind, taskId, status: status as PlanTaskStatus });
  }
  return undefined;
}

function contentHash(content: string): string {
  return createHash("sha256").update(content, "utf8").digest("hex");
}

/**
 * Runs one path-free read or CAS through the canonical shared bridge helper.
 * No pathname-only authorization or reusable permission token is returned.
 */
export async function operatePlanFile(
  rawState: PlanSessionState,
  repositoryRoot: unknown,
  targetPath: unknown,
  rawOperation: PlanFileOperation,
  bridge: BridgePort,
  signal: AbortSignal = new AbortController().signal,
): Promise<PlanFileOperationResult> {
  try {
    const state = normalizeState(rawState);
    const operation = normalizeOperation(rawOperation);
    if (state === undefined || state.mode !== "plan" || operation === undefined
      || typeof repositoryRoot !== "string" || !isAbsolute(repositoryRoot)
      || repositoryRoot.length > 4_096 || CONTROL.test(repositoryRoot)
      || typeof targetPath !== "string") return OPERATION_FAILED;
    const kind = targetPath === state.activePlan.specPath
      ? "spec" as const
      : targetPath === state.activePlan.planPath && targetPath === state.activePlan.ledgerPath
        ? "plan" as const
        : undefined;
    if (kind === undefined || operation.kind === "transition" && kind !== "plan") return OPERATION_FAILED;
    const initial = await callPlanFileBridge(
      bridge,
      repositoryRoot,
      { slug: state.activePlan.slug, kind, action: "read" },
      signal,
    );
    if (initial === undefined || initial.status !== "unchanged"
      || initial.hash !== (initial.exists ? contentHash(initial.content) : null)
      || CONTROL.test(initial.content) || /\r(?!\n)/u.test(initial.content)) return OPERATION_FAILED;
    let chosenState = state;
    if (kind === "plan" && initial.exists) {
      const reconciled = reconcilePlanState(state, initial.content);
      if (reconciled === undefined) return OPERATION_FAILED;
      chosenState = reconciled;
    }
    if (operation.kind === "read") {
      return initial.exists
        ? Object.freeze({ ok: true, content: initial.content, state: chosenState })
        : OPERATION_FAILED;
    }
    let wanted = operation.kind === "replace" ? operation.content : initial.content;
    let nextState = chosenState;
    if (operation.kind === "replace" && kind === "plan") {
      const reconciled = reconcilePlanState(chosenState, wanted);
      if (reconciled === undefined) return OPERATION_FAILED;
      nextState = reconciled;
    } else if (operation.kind === "transition") {
      if (!initial.exists) return OPERATION_FAILED;
      const transitioned = transitionPlanTask(chosenState, operation.taskId, operation.status);
      const updated = updatePlanLedger(initial.content, operation.taskId, operation.status);
      if (transitioned === undefined || updated === undefined) return OPERATION_FAILED;
      wanted = updated;
      nextState = transitioned;
    }
    const committed = await callPlanFileBridge(bridge, repositoryRoot, {
      slug: state.activePlan.slug,
      kind,
      action: "replace",
      expectedHash: initial.hash,
      content: wanted,
    }, signal);
    if (committed === undefined || committed.status !== "committed") return OPERATION_FAILED;
    if (!committed.observed) return Object.freeze({ ok: false, committed: true });
    if (!committed.exists || committed.hash !== contentHash(committed.content)) {
      return Object.freeze({ ok: false, committed: true, content: committed.content });
    }
    if (committed.content !== wanted || committed.postCommitDiagnostic === "postcommit_changed") {
      if (kind === "plan") {
        const observedState = reconcilePlanState(nextState, committed.content);
        if (observedState !== undefined) {
          return Object.freeze({ ok: false, committed: true, content: committed.content, state: observedState });
        }
      }
      return Object.freeze({ ok: false, committed: true, content: committed.content });
    }
    if (kind === "plan") {
      const reconciled = reconcilePlanState(nextState, committed.content);
      if (reconciled === undefined) return OPERATION_FAILED;
      nextState = reconciled;
    }
    return Object.freeze({ ok: true, content: committed.content, state: nextState });
  } catch {
    return OPERATION_FAILED;
  }
}
