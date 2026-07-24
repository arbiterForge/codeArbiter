import { types as utilTypes } from "node:util";
import type { ToolCategory } from "./contracts.ts";

export const POLICY_MODES = Object.freeze(["plan", "execute"] as const);
export type PolicyMode = (typeof POLICY_MODES)[number];

export const POLICY_DECISIONS = Object.freeze(["allow", "ask", "deny"] as const);
export type PolicyDecision = (typeof POLICY_DECISIONS)[number];

export const POLICY_ACTION_CLASSES = Object.freeze([
  "read",
  "inspection",
  "source-write",
  "source-edit",
  "config-write",
  "config-edit",
  "planning-write",
  "shell-mutation",
  "dependency-change",
  "network-side-effect",
  "external-side-effect",
  "background-launch",
  "push",
  "release",
] as const);
export type PolicyActionClass = (typeof POLICY_ACTION_CLASSES)[number];

type PolicyRow = Readonly<Record<PolicyActionClass, PolicyDecision>>;

export const POLICY_TABLE: Readonly<Record<PolicyMode, PolicyRow>> = Object.freeze({
  plan: Object.freeze({
    read: "allow",
    inspection: "allow",
    "source-write": "deny",
    "source-edit": "deny",
    "config-write": "deny",
    "config-edit": "deny",
    "planning-write": "allow",
    "shell-mutation": "deny",
    "dependency-change": "deny",
    "network-side-effect": "deny",
    "external-side-effect": "deny",
    "background-launch": "deny",
    push: "deny",
    release: "deny",
  }),
  execute: Object.freeze({
    read: "allow",
    inspection: "allow",
    "source-write": "ask",
    "source-edit": "ask",
    "config-write": "ask",
    "config-edit": "ask",
    "planning-write": "ask",
    "shell-mutation": "ask",
    "dependency-change": "ask",
    "network-side-effect": "ask",
    "external-side-effect": "ask",
    "background-launch": "ask",
    push: "ask",
    release: "ask",
  }),
});

export const POLICY_CONSEQUENCES: Readonly<Record<PolicyActionClass, string>> = Object.freeze({
  read: "Read project or session data.",
  inspection: "Inspect operational state without mutation.",
  "source-write": "Write source files.",
  "source-edit": "Edit source files.",
  "config-write": "Write configuration files.",
  "config-edit": "Edit configuration files.",
  "planning-write": "Write the active plan's governed planning files.",
  "shell-mutation": "Run a mutating shell operation.",
  "dependency-change": "Change project dependencies.",
  "network-side-effect": "Perform a network side effect.",
  "external-side-effect": "Perform an external side effect.",
  "background-launch": "Launch a session-scoped background process.",
  push: "Push repository state.",
  release: "Create or publish a release.",
});

declare const COMPILED_PERMISSION_POLICY: unique symbol;

export type CompiledPermissionPolicyDescriptor = Readonly<{
  readonly toolClasses: Readonly<Record<string, ToolCategory>>;
  readonly actionClasses: Readonly<Record<string, PolicyActionClass>>;
  readonly [COMPILED_PERMISSION_POLICY]: true;
}>;

export interface PolicyConfirmation {
  readonly actionClasses: readonly PolicyActionClass[];
  readonly cwd: string;
  readonly consequence: string;
}

export interface PolicyRequest {
  readonly mode: PolicyMode;
  readonly tool: string;
  readonly actions: readonly PolicyActionClass[];
  readonly cwd: string;
}

export type PolicyVerdict =
  | Readonly<{ decision: "allow" | "deny" }>
  | Readonly<{ decision: "ask"; confirmation: Readonly<PolicyConfirmation> }>;

const MODES = new Set<unknown>(POLICY_MODES);
const ACTIONS = new Set<unknown>(POLICY_ACTION_CLASSES);
const CATEGORIES = new Set<unknown>(["EXEC", "WRITE", "EDIT", "READ", "OTHER"]);
const SURFACE_NAME = /^[a-z][a-z0-9_-]{0,127}$/u;
const CONTROL = /[\u0000-\u001f\u007f-\u009f\u061c\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/gu;
const DESCRIPTOR_ENTRY_LIMIT = 128;
const REQUEST_ACTION_LIMIT = 32;
const CWD_CODE_POINT_LIMIT = 256;
const CWD_BYTE_LIMIT = 512;

const actions = (...values: PolicyActionClass[]): readonly PolicyActionClass[] => Object.freeze(values);

const TOOL_ACTIONS: Readonly<Record<ToolCategory, readonly PolicyActionClass[]>> = Object.freeze({
  READ: actions("read"),
  WRITE: actions("source-write", "config-write"),
  EDIT: actions("source-edit", "config-edit"),
  EXEC: actions(
    "inspection",
    "shell-mutation",
    "dependency-change",
    "network-side-effect",
    "external-side-effect",
    "background-launch",
    "push",
    "release",
  ),
  OTHER: actions(),
});

const ALLOW = Object.freeze({ decision: "allow" } as const);
const DENY = Object.freeze({ decision: "deny" } as const);
const COMPILED = new WeakSet<object>();

interface DataRecord {
  readonly descriptors: Readonly<Record<PropertyKey, PropertyDescriptor>>;
  readonly keys: readonly string[];
}

function plainDataRecord(value: unknown): DataRecord | undefined {
  if (value === null || typeof value !== "object" || Array.isArray(value) || utilTypes.isProxy(value)) return undefined;
  if (Object.getPrototypeOf(value) !== Object.prototype) return undefined;
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) return undefined;
  const descriptors = Object.getOwnPropertyDescriptors(value) as Readonly<Record<PropertyKey, PropertyDescriptor>>;
  for (const key of keys as string[]) {
    const descriptor = descriptors[key];
    if (descriptor === undefined || !("value" in descriptor) || descriptor.enumerable !== true) return undefined;
  }
  return Object.freeze({ descriptors, keys: Object.freeze(keys as string[]) });
}

function exactKeys(record: DataRecord, expected: readonly string[]): boolean {
  return record.keys.length === expected.length
    && expected.every((key) => record.keys.includes(key));
}

function compileMapping<T extends string>(
  value: unknown,
  validValue: (candidate: unknown) => candidate is T,
): Readonly<Record<string, T>> | undefined {
  const record = plainDataRecord(value);
  if (record === undefined || record.keys.length > DESCRIPTOR_ENTRY_LIMIT) return undefined;
  const output: Record<string, T> = Object.create(null) as Record<string, T>;
  for (const name of record.keys) {
    const item = record.descriptors[name]!.value as unknown;
    if (!SURFACE_NAME.test(name) || !validValue(item)) return undefined;
    output[name] = item;
  }
  return Object.freeze(output);
}

export function compilePermissionPolicyDescriptor(raw: unknown): CompiledPermissionPolicyDescriptor | undefined {
  try {
    const record = plainDataRecord(raw);
    if (record === undefined || !exactKeys(record, ["toolClasses", "actionClasses"])) return undefined;
    const toolClasses = compileMapping(
      record.descriptors.toolClasses!.value,
      (candidate): candidate is ToolCategory => CATEGORIES.has(candidate),
    );
    const actionClasses = compileMapping(
      record.descriptors.actionClasses!.value,
      (candidate): candidate is PolicyActionClass => ACTIONS.has(candidate),
    );
    if (toolClasses === undefined || actionClasses === undefined) return undefined;
    for (const [tool, exactAction] of Object.entries(actionClasses)) {
      if (!hasOwn(toolClasses, tool)) continue;
      const category = toolClasses[tool];
      if (category === undefined || !TOOL_ACTIONS[category].includes(exactAction)) return undefined;
    }
    const compiled = Object.freeze({ toolClasses, actionClasses }) as CompiledPermissionPolicyDescriptor;
    COMPILED.add(compiled);
    return compiled;
  } catch {
    return undefined;
  }
}

function hasOwn(value: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function boundedCwd(value: string): string {
  const normalized = value.replace(CONTROL, " ").replace(/\s+/gu, " ").trim();
  const source = normalized === "" ? "(unknown working directory)" : normalized;
  const points = Array.from(source);
  if (points.length <= CWD_CODE_POINT_LIMIT && Buffer.byteLength(source, "utf8") <= CWD_BYTE_LIMIT) return source;
  const kept: string[] = [];
  let bytes = 0;
  const ellipsisBytes = Buffer.byteLength("…", "utf8");
  for (const point of points) {
    const pointBytes = Buffer.byteLength(point, "utf8");
    if (kept.length >= CWD_CODE_POINT_LIMIT - 1 || bytes + pointBytes + ellipsisBytes > CWD_BYTE_LIMIT) break;
    kept.push(point);
    bytes += pointBytes;
  }
  return `${kept.join("")}…`;
}

function normalizeActions(value: unknown): readonly PolicyActionClass[] | undefined {
  if (!Array.isArray(value) || utilTypes.isProxy(value)) return undefined;
  const descriptors = Object.getOwnPropertyDescriptors(value) as Record<string, PropertyDescriptor>;
  const lengthDescriptor = descriptors.length;
  const rawLength = lengthDescriptor !== undefined && "value" in lengthDescriptor
    ? lengthDescriptor.value as unknown
    : undefined;
  if (lengthDescriptor === undefined || !("value" in lengthDescriptor)
    || typeof rawLength !== "number" || !Number.isInteger(rawLength) || rawLength < 1
    || rawLength > REQUEST_ACTION_LIMIT) return undefined;
  const length = rawLength;
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key === "symbol") || keys.length !== length + 1) return undefined;
  const present = new Set<PolicyActionClass>();
  for (let index = 0; index < length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (descriptor === undefined || !("value" in descriptor) || descriptor.enumerable !== true
      || typeof descriptor.value !== "string" || !ACTIONS.has(descriptor.value)) return undefined;
    present.add(descriptor.value as PolicyActionClass);
  }
  return Object.freeze(POLICY_ACTION_CLASSES.filter((action) => present.has(action)));
}

function normalizeRequest(raw: unknown): Readonly<PolicyRequest> | undefined {
  const record = plainDataRecord(raw);
  if (record === undefined || !exactKeys(record, ["mode", "tool", "actions", "cwd"])) return undefined;
  const mode = record.descriptors.mode!.value as unknown;
  const tool = record.descriptors.tool!.value as unknown;
  const cwd = record.descriptors.cwd!.value as unknown;
  const actions = normalizeActions(record.descriptors.actions!.value);
  if (typeof mode !== "string" || !MODES.has(mode)
    || typeof tool !== "string" || !SURFACE_NAME.test(tool)
    || typeof cwd !== "string" || actions === undefined) return undefined;
  return Object.freeze({ mode: mode as PolicyMode, tool, actions, cwd: boundedCwd(cwd) });
}

function descriptorAllows(
  descriptor: CompiledPermissionPolicyDescriptor,
  tool: string,
  action: PolicyActionClass,
): boolean {
  const exact = hasOwn(descriptor.actionClasses, tool) ? descriptor.actionClasses[tool] : undefined;
  if (action === "planning-write") return tool === "ca-plan" && exact === "planning-write";
  if (Object.values(descriptor.actionClasses).includes(action)) return exact === action;
  if (exact === action) return true;
  if (!hasOwn(descriptor.toolClasses, tool)) return false;
  const category = descriptor.toolClasses[tool];
  return category !== undefined && TOOL_ACTIONS[category].includes(action);
}

/**
 * Evaluates already classified labels only. T08 owns deriving those labels from
 * canonical frozen arguments and applying shared hard blocks first. T09 owns
 * canonical path authorization after this class-level `ca-plan` admission.
 */
export function evaluatePolicy(
  descriptor: CompiledPermissionPolicyDescriptor,
  rawRequest: PolicyRequest,
): PolicyVerdict {
  try {
    if (descriptor === null || typeof descriptor !== "object"
      || utilTypes.isProxy(descriptor) || !COMPILED.has(descriptor)) return DENY;
    const request = normalizeRequest(rawRequest);
    if (request === undefined) return DENY;
    const ownedAction = hasOwn(descriptor.actionClasses, request.tool)
      ? descriptor.actionClasses[request.tool]
      : undefined;
    if (ownedAction !== undefined && !request.actions.includes(ownedAction)) return DENY;

    let decision: PolicyDecision = "allow";
    let consequenceAction: PolicyActionClass | undefined;
    for (const action of request.actions) {
      if (!descriptorAllows(descriptor, request.tool, action)) return DENY;
      const actionDecision = POLICY_TABLE[request.mode][action];
      if (actionDecision === "deny") return DENY;
      if (actionDecision === "ask") {
        decision = "ask";
        // Canonical action order makes the last asking class deterministic.
        consequenceAction = action;
      }
    }
    if (decision === "allow") return ALLOW;
    if (consequenceAction === undefined) return DENY;
    return Object.freeze({
      decision: "ask" as const,
      confirmation: Object.freeze({
        actionClasses: request.actions,
        cwd: request.cwd,
        consequence: POLICY_CONSEQUENCES[consequenceAction],
      }),
    });
  } catch {
    return DENY;
  }
}
