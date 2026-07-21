import { types as utilTypes } from "node:util";

import type { FooterActivity } from "./footer.ts";

export const ACTIVITY_POLICY = Object.freeze({
  maxActive: 8,
  maxRecent: 8,
  activeTtlMs: 2 * 60 * 60 * 1_000,
  recentTtlMs: 5 * 60 * 1_000,
  maxLabelCodePoints: 128,
  maxLabelBytes: 256,
  maxIdBytes: 256,
} as const);

export type ActivityKind = "child" | "job";
export type ActivityState = "active" | "completed";

export interface ActivityEvent {
  readonly kind: ActivityKind;
  readonly id: string;
  readonly label: string;
  readonly state: ActivityState;
}

export interface ActivityPublisher {
  publish(event: ActivityEvent): void;
}

export interface ActivitySnapshotSource {
  snapshot(): readonly FooterActivity[];
}

export interface SessionActivityRegistry extends ActivityPublisher, ActivitySnapshotSource {
  dispose(): void;
}

interface ActivityOptions {
  readonly now: () => number;
  readonly maxActive: number;
  readonly maxRecent: number;
  readonly activeTtlMs: number;
  readonly recentTtlMs: number;
  readonly onChange?: () => void;
}

interface StoredActivity {
  readonly key: string;
  readonly kind: ActivityKind;
  readonly label: string;
  readonly state: ActivityState;
  readonly at: number;
  readonly sequence: number;
}

const CONTROL_AND_ESCAPE_RE = /(?:\x1b\[[0-?]*[ -/]*[@-~]?|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?|\x1b[@-_]|[\u0000-\u001f\u007f-\u009f\u061c\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u206f\ufeff])/gu;

function positiveSafeInteger(value: unknown, maximum: number): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0 && value <= maximum;
}

function sanitizeLabel(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const clean = value.replace(CONTROL_AND_ESCAPE_RE, "").trim();
  if (clean.length === 0) return undefined;
  const bounded = Array.from(clean).slice(0, ACTIVITY_POLICY.maxLabelCodePoints).join("");
  if (Buffer.byteLength(bounded, "utf8") <= ACTIVITY_POLICY.maxLabelBytes) return bounded;
  const points = Array.from(bounded);
  while (points.length > 0 && Buffer.byteLength(points.join(""), "utf8") > ACTIVITY_POLICY.maxLabelBytes) {
    points.pop();
  }
  return points.join("") || undefined;
}

function fixedDataRecord(
  value: unknown,
  required: readonly string[],
  optional: readonly string[] = [],
): Readonly<Record<string, PropertyDescriptor>> | undefined {
  if (value === null || typeof value !== "object" || Array.isArray(value) || utilTypes.isProxy(value)) return undefined;
  if (Object.getPrototypeOf(value) !== Object.prototype) return undefined;
  const descriptors: Record<string, PropertyDescriptor> = {};
  for (const key of [...required, ...optional]) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (descriptor === undefined) {
      if (required.includes(key)) return undefined;
      continue;
    }
    if (!descriptor.enumerable || !("value" in descriptor)) return undefined;
    descriptors[key] = descriptor;
  }
  return Object.freeze(descriptors);
}

function parseEvent(value: unknown): ActivityEvent | undefined {
  try {
    const fields = fixedDataRecord(value, ["kind", "id", "label", "state"]);
    if (fields === undefined) return undefined;
    const kind = fields.kind!.value as unknown;
    const state = fields.state!.value as unknown;
    const id = fields.id!.value as unknown;
    if ((kind !== "child" && kind !== "job")
      || (state !== "active" && state !== "completed")
      || typeof id !== "string" || id.length === 0
      || Buffer.byteLength(id, "utf8") > ACTIVITY_POLICY.maxIdBytes) return undefined;
    const label = sanitizeLabel(fields.label!.value);
    return label === undefined ? undefined : Object.freeze({
      kind,
      id,
      label,
      state,
    });
  } catch {
    return undefined;
  }
}

function parseOptions(value: unknown): ActivityOptions | undefined {
  try {
    const fields: Readonly<Record<string, PropertyDescriptor>> | undefined = value === undefined
      ? Object.freeze({} as Record<string, PropertyDescriptor>)
      : fixedDataRecord(value, [], ["now", "maxActive", "maxRecent", "activeTtlMs", "recentTtlMs", "onChange"]);
    if (fields === undefined) return undefined;
    const now = fields.now?.value ?? Date.now;
    const maxActive = fields.maxActive?.value ?? ACTIVITY_POLICY.maxActive;
    const maxRecent = fields.maxRecent?.value ?? ACTIVITY_POLICY.maxRecent;
    const activeTtlMs = fields.activeTtlMs?.value ?? ACTIVITY_POLICY.activeTtlMs;
    const recentTtlMs = fields.recentTtlMs?.value ?? ACTIVITY_POLICY.recentTtlMs;
    const onChange = fields.onChange?.value;
    if (typeof now !== "function"
      || !positiveSafeInteger(maxActive, ACTIVITY_POLICY.maxActive)
      || !positiveSafeInteger(maxRecent, ACTIVITY_POLICY.maxRecent)
      || !positiveSafeInteger(activeTtlMs, ACTIVITY_POLICY.activeTtlMs)
      || !positiveSafeInteger(recentTtlMs, ACTIVITY_POLICY.recentTtlMs)
      || (onChange !== undefined && typeof onChange !== "function")) return undefined;
    return Object.freeze({
      now, maxActive, maxRecent, activeTtlMs, recentTtlMs,
      ...(onChange === undefined ? {} : { onChange }),
    });
  } catch {
    return undefined;
  }
}

class SessionActivity implements SessionActivityRegistry {
  readonly #options: ActivityOptions;
  readonly #active = new Map<string, StoredActivity>();
  readonly #recent = new Map<string, StoredActivity>();
  #sequence = 0;
  #disposed = false;

  constructor(options: ActivityOptions) {
    this.#options = options;
  }

  publish(raw: ActivityEvent): void {
    if (this.#disposed) return;
    try {
      const event = parseEvent(raw);
      const at = this.#now();
      if (event === undefined || at === undefined) return;
      this.#evict(at);
      const key = `${event.kind}\0${event.id}`;
      this.#sequence += 1;
      const stored = Object.freeze({
        key,
        kind: event.kind,
        label: event.label,
        state: event.state,
        at,
        sequence: this.#sequence,
      });
      if (event.state === "active") {
        if (this.#recent.has(key)) return;
        this.#active.delete(key);
        this.#active.set(key, stored);
        this.#bound(this.#active, this.#options.maxActive);
      } else {
        if (this.#recent.has(key)) return;
        this.#active.delete(key);
        this.#recent.set(key, stored);
        this.#bound(this.#recent, this.#options.maxRecent);
      }
      try { this.#options.onChange?.(); } catch { /* Rendering remains fail-soft. */ }
    } catch {
      // Activity is display-only and must never affect its producer.
    }
  }

  snapshot(): readonly FooterActivity[] {
    if (this.#disposed) return Object.freeze([]);
    try {
      const now = this.#now();
      if (now === undefined) return Object.freeze([]);
      this.#evict(now);
      const project = (item: StoredActivity): Readonly<FooterActivity> => Object.freeze({
        kind: item.kind,
        label: item.label,
        state: item.state,
        ageSeconds: Math.max(0, Math.floor((now - item.at) / 1_000)),
      });
      return Object.freeze([
        ...[...this.#active.values()].sort((a, b) => b.sequence - a.sequence).map(project),
        ...[...this.#recent.values()].sort((a, b) => b.sequence - a.sequence).map(project),
      ]);
    } catch {
      return Object.freeze([]);
    }
  }

  dispose(): void {
    this.#disposed = true;
    this.#active.clear();
    this.#recent.clear();
  }

  #now(): number | undefined {
    try {
      const value = this.#options.now();
      return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : undefined;
    } catch {
      return undefined;
    }
  }

  #evict(now: number): void {
    for (const [key, item] of this.#active) {
      if (now - item.at > this.#options.activeTtlMs) this.#active.delete(key);
    }
    for (const [key, item] of this.#recent) {
      if (now - item.at > this.#options.recentTtlMs) this.#recent.delete(key);
    }
  }

  #bound(items: Map<string, StoredActivity>, maximum: number): void {
    while (items.size > maximum) {
      const oldest = items.keys().next().value as string | undefined;
      if (oldest === undefined) return;
      items.delete(oldest);
    }
  }
}

export function createSessionActivityRegistry(options?: unknown): SessionActivityRegistry | undefined {
  const parsed = parseOptions(options);
  return parsed === undefined ? undefined : new SessionActivity(parsed);
}

/** Display reporting is explicitly fail-soft at every producer boundary. */
export function publishActivity(publisher: ActivityPublisher | undefined, event: ActivityEvent): void {
  if (publisher === undefined) return;
  try { publisher.publish(event); } catch { /* Producer behavior is authoritative. */ }
}
