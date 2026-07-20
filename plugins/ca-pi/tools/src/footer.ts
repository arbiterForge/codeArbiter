export interface FooterGit {
  readonly repository?: string;
  readonly branch?: string;
  readonly dirty?: boolean;
}

export interface FooterModel {
  readonly name: string;
  readonly provider?: string;
  readonly thinking?: string;
}

export interface FooterUsage {
  readonly inputTokens: number;
  readonly outputTokens: number;
  readonly cacheReadTokens?: number;
  readonly cacheWriteTokens?: number;
  readonly costUsd: number;
  readonly ageSeconds?: number;
}

export interface FooterDailyUsage {
  readonly inputTokens: number;
  readonly outputTokens: number;
  readonly costUsd: number;
}

export interface FooterContext {
  readonly usedTokens: number;
  readonly windowTokens: number;
}

export interface FooterGovernance {
  readonly stage: string;
  readonly tasks: number;
  readonly questions: number;
  readonly overrides: number;
  readonly sprint?: boolean;
  readonly dev?: boolean;
  readonly prune?: string;
}

export interface FooterActivity {
  readonly kind: "job" | "child";
  readonly label: string;
  readonly state: "active" | "completed";
  readonly ageSeconds?: number;
}

/**
 * Bounded display facts prepared by the Pi-owned adapter. Provider rate-window
 * telemetry is deliberately not representable because Pi does not expose it.
 */
export interface FooterInput {
  readonly folder: string;
  readonly sessionName?: string;
  readonly git?: FooterGit;
  readonly model?: FooterModel;
  readonly session?: FooterUsage;
  readonly context?: FooterContext;
  readonly daily?: FooterDailyUsage;
  readonly update?: { readonly version: string };
  readonly governance?: FooterGovernance;
  readonly activity?: readonly FooterActivity[];
}

export interface FooterRenderOptions {
  /** Terminal columns. Finite positive requests are honored without a minimum and capped at 160. */
  readonly width?: number;
  /** Set from the host's NO_COLOR presence; the pure renderer never reads the environment. */
  readonly noColor?: boolean;
  readonly compact?: boolean;
}

/** Pi-compatible terminal text operations supplied by the host UI layer. */
export interface FooterTextMetrics {
  readonly visibleWidth: (text: string) => number;
  readonly truncateToWidth: (text: string, width: number, suffix: string) => string;
}

const ESC = "\x1b";
const RESET = `${ESC}[0m`;
const BOLD = `${ESC}[1m`;
const COLORS = {
  deep: `${ESC}[38;2;108;70;180m`,
  primary: `${ESC}[38;2;178;102;255m`,
  bright: `${ESC}[38;2;208;140;255m`,
  muted: `${ESC}[38;2;150;150;162m`,
  normal: `${ESC}[38;2;232;232;240m`,
  onAccent: `${ESC}[38;2;18;14;26m`,
  ok: `${ESC}[38;2;120;220;150m`,
  warn: `${ESC}[38;2;255;184;76m`,
  danger: `${ESC}[38;2;255;86;110m`,
} as const;

const ANSI_RE = /\x1b\[[0-9;]*m/gu;
const OSC_RE = /\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?/gu;
const CSI_RE = /\x1b\[[0-?]*[ -/]*[@-~]?/gu;
const ESCAPE_RE = /\x1b[@-_]/gu;
const CONTROL_RE = /[\u0000-\u001f\u007f-\u009f]/gu;
const MAX_TEXT_POINTS = 512;
const MAX_TOKENS = 1_000_000_000_000_000;
const MAX_COST = 1_000_000_000;
const MAX_AGE_SECONDS = 3650 * 86_400;
const SEGMENTER = new Intl.Segmenter(undefined, { granularity: "grapheme" });

function guard<T>(render: () => T, fallback: T): T {
  try {
    return render();
  } catch {
    return fallback;
  }
}

function boundedNumber(value: unknown, minimum: number, maximum: number, fallback = minimum): number {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.max(minimum, Math.min(maximum, value))
    : fallback;
}

function normalizeWidth(value: unknown): number {
  if (value === undefined) return 100;
  if (typeof value !== "number" || Number.isNaN(value) || value <= 0) return 0;
  if (value === Number.POSITIVE_INFINITY) return 160;
  if (!Number.isFinite(value)) return 0;
  return Math.min(160, Math.floor(value));
}

function boundedCount(value: unknown): number {
  return Math.round(boundedNumber(value, 0, 9_999));
}

function sanitize(value: unknown, fallback = "?"): string {
  if (typeof value !== "string") return fallback;
  const clean = value
    .replace(OSC_RE, "")
    .replace(CSI_RE, "")
    .replace(ESCAPE_RE, "")
    .replace(CONTROL_RE, "");
  return Array.from(clean).slice(0, MAX_TEXT_POINTS).join("") || fallback;
}

function stripAnsi(value: string): string {
  return value.replace(ANSI_RE, "");
}

function clip(value: string, width: number, metrics: FooterTextMetrics): string {
  if (width <= 0) return "";
  return metrics.visibleWidth(value) <= width
    ? value
    : metrics.truncateToWidth(value, width, "…");
}

function pad(value: string, width: number, metrics: FooterTextMetrics): string {
  const clipped = clip(value, width, metrics);
  return clipped + " ".repeat(Math.max(0, width - metrics.visibleWidth(clipped)));
}

function colored(color: string, value: string): string {
  return `${color}${value}${RESET}`;
}

function gradient(value: string, from: readonly [number, number, number], to: readonly [number, number, number], background = false): string {
  const graphemes = [...SEGMENTER.segment(value)].map(({ segment }) => segment);
  const denominator = Math.max(1, graphemes.length - 1);
  return graphemes.map((grapheme, index) => {
    const ratio = index / denominator;
    const rgb = from.map((start, channel) => Math.floor(start + (to[channel]! - start) * ratio));
    return `${ESC}[${background ? 48 : 38};2;${rgb[0]};${rgb[1]};${rgb[2]}m${grapheme}`;
  }).join("") + RESET;
}

function formatTokens(value: unknown): string {
  const count = boundedNumber(value, 0, MAX_TOKENS);
  if (count >= 999_500) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`;
  return String(Math.trunc(count));
}

function formatUsd(value: unknown): string {
  const cost = boundedNumber(value, 0, MAX_COST);
  if (cost >= 100) return `$${cost.toFixed(0)}`;
  if (cost >= 10) return `$${cost.toFixed(1)}`;
  if (cost > 0 && cost < 0.01) return "<$.01";
  return `$${cost.toFixed(2)}`;
}

function formatDuration(value: unknown): string {
  const seconds = Math.trunc(boundedNumber(value, 0, MAX_AGE_SECONDS));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.trunc(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.trunc(minutes / 60);
  const remainderMinutes = minutes % 60;
  if (hours < 24) return remainderMinutes ? `${hours}h${String(remainderMinutes).padStart(2, "0")}m` : `${hours}h`;
  const days = Math.trunc(hours / 24);
  const remainderHours = hours % 24;
  return remainderHours ? `${days}d${remainderHours}h` : `${days}d`;
}

function joinLeftRight(left: string, right: string, width: number, metrics: FooterTextMetrics): string {
  if (!left) return pad(right, width, metrics);
  if (!right) return pad(left, width, metrics);
  const boundedRight = clip(right, width, metrics);
  if (metrics.visibleWidth(boundedRight) >= width) return pad(boundedRight, width, metrics);
  const boundedLeft = clip(left, Math.max(0, width - metrics.visibleWidth(boundedRight) - 1), metrics);
  if (!boundedLeft) return pad(boundedRight, width, metrics);
  const gap = Math.max(1, width - metrics.visibleWidth(boundedLeft) - metrics.visibleWidth(boundedRight));
  return `${boundedLeft}${" ".repeat(gap)}${boundedRight}`;
}

function modelPill(model: FooterModel, includeProvider: boolean): string {
  const name = sanitize(model.name);
  const provider = includeProvider && model.provider ? `${sanitize(model.provider, "")}/` : "";
  const rawThinking = model.thinking ? sanitize(model.thinking, "") : "";
  const effortNames: Readonly<Record<string, string>> = {
    low: "Low", medium: "Medium", high: "High", xhigh: "XHigh", max: "Max", ultracode: "Ultracode",
  };
  const thinking = rawThinking ? effortNames[rawThinking.toLowerCase()]
    ?? rawThinking.charAt(0).toUpperCase() + rawThinking.slice(1) : "";
  const body = `${provider}${name}${thinking ? ` │ ${thinking}` : ""}`;
  const lower = name.toLowerCase();
  const target: [number, number, number] = lower.includes("opus") ? [188, 120, 255]
    : lower.includes("sonnet") ? [96, 174, 235]
      : lower.includes("haiku") ? [120, 220, 150]
        : [150, 150, 162];
  const start = target.map((channel) => Math.floor(channel * 0.5)) as [number, number, number];
  return `${COLORS.onAccent}${BOLD}${gradient(body, start, target, true)}${RESET}`;
}

function gitSegment(git: FooterGit | undefined, compact: boolean): string {
  if (!git) return colored(COLORS.muted, "no git");
  const repository = git.repository ? sanitize(git.repository, "") : "";
  const branch = git.branch ? sanitize(git.branch, "") : "";
  if (!repository && !branch) return colored(COLORS.muted, "no git");
  const lead = compact ? "git" : (repository ? `git ${repository}` : "git");
  if (!branch) return colored(COLORS.normal, lead);
  const divider = !compact && repository ? colored(COLORS.deep, " │ ") : " ";
  const branchColor = git.dirty ? COLORS.warn : COLORS.ok;
  return `${colored(COLORS.normal, lead)}${divider}${colored(branchColor, `${branch}${git.dirty ? "*" : ""}`)}`;
}

function governanceSegment(governance: FooterGovernance): string {
  const badge = governance.dev ? " [DEV]" : governance.sprint ? " [SPRINT]" : "";
  const prune = governance.prune ? sanitize(governance.prune, "") : "";
  return `${colored(COLORS.ok, "●")} ${colored(COLORS.normal, `stage:${sanitize(governance.stage)}`)}`
    + ` ${colored(COLORS.deep, "·")} ${colored(COLORS.normal, `tasks:${boundedCount(governance.tasks)}`)}`
    + ` ${colored(COLORS.deep, "·")} ${colored(governance.questions > 0 ? COLORS.danger : COLORS.muted, `q:${boundedCount(governance.questions)}`)}`
    + ` ${colored(COLORS.deep, "·")} ${colored(governance.overrides > 0 ? COLORS.danger : COLORS.muted, `over:${boundedCount(governance.overrides)}`)}`
    + (prune ? ` ${colored(COLORS.deep, "·")} ${colored(COLORS.muted, `prune:${prune}`)}` : "")
    + (badge ? colored(governance.dev ? COLORS.danger : COLORS.bright, badge) : "");
}

function usageRow(label: string, usage: FooterUsage | FooterDailyUsage): string {
  return `${colored(COLORS.muted, label.padEnd(7))} ${colored(COLORS.deep, "│")}`
    + ` ${colored(COLORS.primary, "↓")} ${colored(COLORS.normal, formatTokens(usage.inputTokens).padStart(6))}`
    + ` ${colored(COLORS.primary, "↑")} ${colored(COLORS.normal, formatTokens(usage.outputTokens).padStart(6))}`
    + ` ${colored(COLORS.deep, "│")} ${colored(COLORS.ok, formatUsd(usage.costUsd))}`;
}

function contextPercentage(context: FooterContext): number | undefined {
  const windowTokens = boundedNumber(context.windowTokens, 0, MAX_TOKENS);
  if (windowTokens <= 0) return undefined;
  const usedTokens = boundedNumber(context.usedTokens, 0, MAX_TOKENS);
  return Math.max(0, Math.min(100, usedTokens / windowTokens * 100));
}

function contextColor(percentage: number): string {
  return percentage < 75 ? COLORS.primary : percentage < 90 ? COLORS.warn : COLORS.danger;
}

function contextWide(context: FooterContext, width: number): string {
  const percentage = contextPercentage(context);
  if (percentage === undefined) return "";
  const color = contextColor(percentage);
  const barWidth = Math.max(10, Math.min(28, width - 10));
  const filled = Math.max(0, Math.min(barWidth, Math.round(percentage / 100 * barWidth)));
  const fill = percentage < 75
    ? gradient("█".repeat(filled), [120, 80, 200], [205, 140, 255])
    : colored(color, "█".repeat(filled));
  const bar = `${fill}${colored(COLORS.deep, "░".repeat(barWidth - filled))}`;
  return `${colored(COLORS.muted, "ctx")} ${bar} ${colored(color, `${Math.round(percentage)}%`)}`;
}

function cacheAndAge(session: FooterUsage): string {
  const hasCache = session.cacheReadTokens !== undefined || session.cacheWriteTokens !== undefined;
  const read = boundedNumber(session.cacheReadTokens, 0, MAX_TOKENS);
  const write = boundedNumber(session.cacheWriteTokens, 0, MAX_TOKENS);
  const total = read + write;
  const hit = total > 0 ? Math.round(read / total * 100) : 0;
  const bits: string[] = [];
  if (hasCache) bits.push(`cache r ${formatTokens(read)} w ${formatTokens(write)} hit ${hit}%`);
  if (session.ageSeconds !== undefined) bits.push(`age ${formatDuration(session.ageSeconds)}`);
  return bits.map((bit) => colored(COLORS.muted, bit)).join(` ${colored(COLORS.deep, "·")} `);
}

function activitySegment(activity: readonly FooterActivity[]): string {
  const rendered = activity.slice(0, 3).map((item) => {
    const glyph = item.state === "active" ? colored(COLORS.ok, "●") : colored(COLORS.muted, "✓");
    const age = item.ageSeconds === undefined ? "" : ` ${formatDuration(item.ageSeconds)}`;
    return `${glyph} ${sanitize(item.kind, "job")}:${sanitize(item.label)}${age}`;
  });
  return rendered.length ? `${colored(COLORS.bright, "activity")} ${rendered.join(` ${colored(COLORS.deep, "·")} `)}` : "";
}

class Box {
  readonly lines: string[] = [];
  readonly inner: number;

  constructor(readonly width: number, readonly metrics: FooterTextMetrics) {
    this.inner = width - 4;
  }

  top(title: string): void {
    const clean = clip(title, Math.max(1, this.width - 8), this.metrics);
    const fill = "─".repeat(Math.max(1, this.width - this.metrics.visibleWidth(clean) - 6));
    this.lines.push(`${colored(COLORS.deep, "╭──")} ${gradient(stripAnsi(clean), [120, 80, 200], [205, 140, 255])} ${colored(COLORS.deep, `${fill}╮`)}`);
  }

  row(content: string): void {
    this.lines.push(`${colored(COLORS.deep, "│")} ${pad(content, this.inner, this.metrics)} ${colored(COLORS.deep, "│")}`);
  }

  separator(): void {
    this.lines.push(colored(COLORS.deep, `├${"┄".repeat(this.width - 2)}┤`));
  }

  bottom(): void {
    this.lines.push(colored(COLORS.deep, `╰${"─".repeat(this.width - 2)}╯`));
  }
}

function renderCompact(input: FooterInput, box: Box): void {
  const git = guard(() => gitSegment(input.git, true), "");
  const model = guard(() => input.model ? modelPill(input.model, false) : "", "");
  if (git || model) box.row(joinLeftRight(git, model, box.inner, box.metrics));

  const session = guard(() => {
    const usage = input.session;
    return usage
      ? `sess ↓${formatTokens(usage.inputTokens)} ↑${formatTokens(usage.outputTokens)} ${formatUsd(usage.costUsd)}`
      : "";
  }, "");
  const context = guard(() => {
    if (!input.context) return "";
    const percentage = contextPercentage(input.context);
    return percentage === undefined ? ""
      : `${colored(COLORS.muted, "ctx")} ${colored(contextColor(percentage), `${Math.round(percentage)}%`)}`;
  }, "");
  if (session || context) {
    box.separator();
    box.row([session, context].filter(Boolean).join(" · "));
  }
  const sessionTail = guard(() => {
    const usage = input.session;
    if (!usage) return "";
    const bits: string[] = [];
    const readValue = usage.cacheReadTokens;
    const writeValue = usage.cacheWriteTokens;
    const read = boundedNumber(readValue, 0, MAX_TOKENS);
    const write = boundedNumber(writeValue, 0, MAX_TOKENS);
    if (readValue !== undefined || writeValue !== undefined) {
      bits.push(`cache ${read + write > 0 ? Math.round(read / (read + write) * 100) : 0}%`);
    }
    const age = usage.ageSeconds;
    if (age !== undefined) bits.push(`age ${formatDuration(age)}`);
    return bits.join(" · ");
  }, "");
  const daily = guard(() => {
    const usage = input.daily;
    return usage
      ? `today ${formatTokens(boundedNumber(usage.inputTokens, 0, MAX_TOKENS) + boundedNumber(usage.outputTokens, 0, MAX_TOKENS))} ${formatUsd(usage.costUsd)}`
      : "";
  }, "");
  const tail = [sessionTail, daily].filter(Boolean);
  if (tail.length) box.row(tail.join(" · "));
}

function renderWide(input: FooterInput, box: Box): void {
  const git = guard(() => gitSegment(input.git, false), "");
  const update = guard(() => input.update ? `${colored(COLORS.bright, "update")} ${colored(COLORS.normal, sanitize(input.update.version))}` : "", "");
  const model = guard(() => input.model ? modelPill(input.model, true) : "", "");
  const right = [update, model].filter(Boolean).join("  ");
  if (git || right) box.row(joinLeftRight(git, right, box.inner, box.metrics));

  const governance = guard(() => input.governance ? governanceSegment(input.governance) : "", "");
  if (governance) {
    box.separator();
    box.row(governance);
  }

  const session = guard(() => input.session, undefined);
  const daily = guard(() => input.daily, undefined);
  const context = guard(() => input.context, undefined);
  const leftWidth = Math.max(34, Math.min(48, Math.floor(box.inner / 2)));
  const rightWidth = Math.max(1, box.inner - leftWidth - 3);
  const sessionRow = guard(() => session ? usageRow("Session", session) : "", "");
  const contextRow = guard(() => context ? contextWide(context, rightWidth) : "", "");
  const dailyRow = guard(() => daily ? usageRow("Today", daily) : "", "");
  const cacheRow = guard(() => session ? cacheAndAge(session) : "", "");
  if (sessionRow || contextRow || dailyRow || cacheRow) {
    box.separator();
    if (sessionRow || contextRow) box.row(`${pad(sessionRow, leftWidth, box.metrics)} ${colored(COLORS.deep, "│")} ${contextRow}`);
    if (dailyRow || cacheRow) box.row(`${pad(dailyRow, leftWidth, box.metrics)} ${colored(COLORS.deep, "│")} ${cacheRow}`);
  }

  const activity = guard(() => input.activity ? activitySegment(input.activity) : "", "");
  if (activity) {
    box.separator();
    box.row(activity);
  }
}

function minimalSafeLine(metrics: FooterTextMetrics, width: number): string {
  return guard(() => width <= 0 ? "" : stripAnsi(clip("codeArbiter footer unavailable", width, metrics)), "");
}

export function renderFooter(
  input: FooterInput,
  options: FooterRenderOptions,
  metrics: FooterTextMetrics,
): string {
  let safeWidth = 30;
  try {
    const width = normalizeWidth(options.width);
    safeWidth = width;
    if (width <= 0) return "";
    if (width < 8) return minimalSafeLine(metrics, width);
    const compact = Boolean(options.compact) || width < 72;
    const noColor = Boolean(options.noColor);
    const box = new Box(width, metrics);
    const title = guard(() => {
      const folder = sanitize(input.folder);
      const session = input.sessionName ? sanitize(input.sessionName, "") : "";
      return session ? `${folder} • ${session}` : folder;
    }, "?");
    box.top(title);
    if (compact) renderCompact(input, box);
    else renderWide(input, box);
    box.bottom();
    const rendered = box.lines.join("\n");
    return noColor ? stripAnsi(rendered) : rendered;
  } catch {
    return minimalSafeLine(metrics, safeWidth);
  }
}
