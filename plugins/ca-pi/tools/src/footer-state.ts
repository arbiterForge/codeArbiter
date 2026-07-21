import type {
  ExtensionContextPort,
  PiFooterApiPort,
  PiFooterDataPort,
  PiUsageSnapshotPortResult,
} from "./contracts.ts";
import type { FooterDailyUsage, FooterInput, FooterUsage } from "./footer.ts";
import type { FooterActivity } from "./footer.ts";
import type { ActivitySnapshotSource } from "./activity.ts";

const MAX_TEXT_POINTS = 512;
const MAX_TOKENS = 1_000_000_000_000_000;
const MAX_COST = 1_000_000_000;
const MAX_AGE_SECONDS = 3650 * 86_400;
const CONTROL_AND_ESCAPE_RE = /(?:\x1b\[[0-?]*[ -/]*[@-~]?|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?|\x1b[@-_]|[\u0000-\u001f\u007f-\u009f])/gu;

export interface PiFooterStateSource {
  readonly pi: PiFooterApiPort;
  readonly context: ExtensionContextPort;
  readonly footerData: PiFooterDataPort;
  /** Optional composition-owned fact; the adapter performs no persistence or I/O. */
  readonly usageSnapshot?: PiUsageSnapshotPortResult;
  readonly now?: Date;
  /** Optional composition-owned fact; stock Pi 0.80.10 does not expose update availability. */
  readonly updateVersion?: unknown;
  /** Current session-only activity; snapshot failure is contained by the adapter. */
  readonly activity?: ActivitySnapshotSource;
}

function finite(value: unknown, maximum: number): number {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.max(0, Math.min(maximum, value))
    : 0;
}

function roundedCost(value: unknown): number {
  return Math.round(finite(value, MAX_COST) * 1_000_000_000) / 1_000_000_000;
}

function sanitize(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const clean = value.replace(CONTROL_AND_ESCAPE_RE, "");
  return clean || undefined;
}

function text(value: unknown, maximum = MAX_TEXT_POINTS): string | undefined {
  const clean = sanitize(value);
  return clean ? Array.from(clean).slice(0, maximum).join("") || undefined : undefined;
}

function object(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null
    ? value as Record<string, unknown>
    : undefined;
}

function callMember(receiver: unknown, key: string): unknown {
  const getter = object(receiver)?.[key];
  if (typeof getter !== "function") return undefined;
  try {
    return getter.call(receiver);
  } catch {
    return undefined;
  }
}

function aggregateSessionUsage(entriesValue: unknown): FooterUsage | undefined {
  if (!Array.isArray(entriesValue)) return undefined;
  let found = false;
  let inputTokens = 0;
  let outputTokens = 0;
  let cacheReadTokens = 0;
  let cacheWriteTokens = 0;
  let costUsd = 0;
  for (const rawEntry of entriesValue) {
    const entry = object(rawEntry);
    const message = object(entry?.message);
    if (entry?.type !== "message" || message?.role !== "assistant") continue;
    const usage = object(message.usage);
    if (!usage) continue;
    found = true;
    inputTokens = finite(inputTokens + finite(usage.input, MAX_TOKENS), MAX_TOKENS);
    outputTokens = finite(outputTokens + finite(usage.output, MAX_TOKENS), MAX_TOKENS);
    cacheReadTokens = finite(cacheReadTokens + finite(usage.cacheRead, MAX_TOKENS), MAX_TOKENS);
    cacheWriteTokens = finite(cacheWriteTokens + finite(usage.cacheWrite, MAX_TOKENS), MAX_TOKENS);
    const cost = object(usage.cost);
    costUsd = roundedCost(costUsd + finite(cost?.total ?? usage.cost, MAX_COST));
  }
  return found ? { inputTokens, outputTokens, cacheReadTokens, cacheWriteTokens, costUsd } : undefined;
}

function normalizeSnapshotSession(value: unknown): FooterUsage | undefined {
  const usage = object(value);
  if (!usage
    || typeof usage.inputTokens !== "number"
    || typeof usage.outputTokens !== "number"
    || typeof usage.costUsd !== "number") return undefined;
  return {
    inputTokens: finite(usage.inputTokens, MAX_TOKENS),
    outputTokens: finite(usage.outputTokens, MAX_TOKENS),
    ...(typeof usage.cacheReadTokens === "number"
      ? { cacheReadTokens: finite(usage.cacheReadTokens, MAX_TOKENS) }
      : {}),
    ...(typeof usage.cacheWriteTokens === "number"
      ? { cacheWriteTokens: finite(usage.cacheWriteTokens, MAX_TOKENS) }
      : {}),
    costUsd: roundedCost(usage.costUsd),
  };
}

function normalizeSnapshotToday(value: unknown): FooterDailyUsage | undefined {
  const usage = object(value);
  if (!usage
    || typeof usage.inputTokens !== "number"
    || typeof usage.outputTokens !== "number"
    || typeof usage.costUsd !== "number") return undefined;
  return {
    inputTokens: finite(usage.inputTokens, MAX_TOKENS),
    outputTokens: finite(usage.outputTokens, MAX_TOKENS),
    costUsd: roundedCost(usage.costUsd),
  };
}

function sessionAge(headerValue: unknown, now: Date): number | undefined {
  const timestamp = object(headerValue)?.timestamp;
  if (typeof timestamp !== "string") return undefined;
  const started = Date.parse(timestamp);
  if (!Number.isFinite(started)) return undefined;
  return finite(Math.floor((now.getTime() - started) / 1000), MAX_AGE_SECONDS);
}

function normalizeActivity(source: ActivitySnapshotSource | undefined): readonly FooterActivity[] | undefined {
  if (source === undefined) return undefined;
  try {
    const raw = source.snapshot();
    if (!Array.isArray(raw)) return undefined;
    const result: FooterActivity[] = [];
    for (const value of raw.slice(0, 16)) {
      const item = object(value);
      const label = text(item?.label, 128);
      if ((item?.kind !== "child" && item?.kind !== "job")
        || (item?.state !== "active" && item?.state !== "completed")
        || label === undefined) continue;
      const ageSeconds = typeof item.ageSeconds === "number" && Number.isFinite(item.ageSeconds)
        ? Math.floor(finite(item.ageSeconds, MAX_AGE_SECONDS))
        : undefined;
      result.push(Object.freeze({
        kind: item.kind,
        label,
        state: item.state,
        ...(ageSeconds === undefined ? {} : { ageSeconds }),
      }));
    }
    return result.length === 0 ? undefined : Object.freeze(result);
  } catch {
    return undefined;
  }
}

export function adaptPiFooterState(source: PiFooterStateSource): FooterInput {
  const manager = source.context.sessionManager;
  const now = source.now ?? new Date();
  const folder = text(source.context.cwd) ?? ".";
  const sessionName = text(callMember(source.pi, "getSessionName"))
    ?? text(callMember(manager, "getSessionName"));
  const branch = text(callMember(source.footerData, "getGitBranch"));
  const modelName = text(source.context.model?.id);
  const provider = text(source.context.model?.provider);
  const thinking = text(callMember(source.pi, "getThinkingLevel"));
  const snapshotSession = normalizeSnapshotSession(source.usageSnapshot?.session);
  const usage = snapshotSession ?? aggregateSessionUsage(callMember(manager, "getEntries"));
  const ageSeconds = sessionAge(callMember(manager, "getHeader"), now);
  const session = usage ? { ...usage, ...(ageSeconds === undefined ? {} : { ageSeconds }) } : undefined;
  const rawContext = object(callMember(source.context, "getContextUsage"));
  const usedTokens = rawContext?.tokens;
  const windowTokens = rawContext?.contextWindow ?? source.context.model?.contextWindow;
  const context = typeof usedTokens === "number" && Number.isFinite(usedTokens)
    && typeof windowTokens === "number" && Number.isFinite(windowTokens) && windowTokens > 0
    ? { usedTokens: finite(usedTokens, MAX_TOKENS), windowTokens: finite(windowTokens, MAX_TOKENS) }
    : undefined;
  const daily = normalizeSnapshotToday(source.usageSnapshot?.today);
  const updateVersion = text(source.updateVersion);
  const activity = normalizeActivity(source.activity);

  return {
    folder,
    ...(sessionName ? { sessionName } : {}),
    ...(branch ? { git: { branch } } : {}),
    ...(modelName ? { model: {
      name: modelName,
      ...(provider ? { provider } : {}),
      ...(thinking ? { thinking } : {}),
    } } : {}),
    ...(session ? { session } : {}),
    ...(context ? { context } : {}),
    ...(daily ? { daily } : {}),
    ...(updateVersion ? { update: { version: updateVersion } } : {}),
    ...(activity ? { activity } : {}),
  };
}
