/** Pure sidebar renderer (spec pi-sidebar-panel AC-1/AC-6).
 *
 * Five panels at pi-sidebar-tui parity — session, agents, workspace, todos,
 * MCP — rendered as width-exact lines. Every panel is independently fail-soft:
 * a throwing data source renders as its header plus an omitted body and never
 * breaks a sibling. The renderer is pure: no environment reads, no host calls;
 * the caller supplies text metrics and the NO_COLOR decision.
 */

import type { FooterTextMetrics } from "./footer.ts";

export type SidebarAgentState = "active" | "completed";
export type SidebarTodoState = "open" | "active" | "done";

export interface SidebarSession {
  readonly model?: string;
  readonly thinkingLevel?: string;
  readonly contextPercent?: number;
  readonly inputTokens?: number;
  readonly outputTokens?: number;
  readonly costUsd?: number;
  /** Per-message burn series, oldest→newest; the panel shows the tail. */
  readonly burn?: readonly number[];
}

export interface SidebarAgentRow {
  readonly kind: "child" | "job";
  readonly label: string;
  readonly state: SidebarAgentState;
  readonly ageSeconds?: number;
}

export interface SidebarWorkspace {
  readonly cwd: string;
  readonly repository?: string;
  readonly dirty?: boolean;
}

export interface SidebarTodoRow {
  readonly text: string;
  readonly state: SidebarTodoState;
}

export interface SidebarMcpRow {
  readonly name: string;
  readonly state: string;
}

export interface SidebarInput {
  readonly session?: SidebarSession;
  readonly subagents?: readonly SidebarAgentRow[];
  readonly workspace?: SidebarWorkspace;
  readonly todos?: readonly SidebarTodoRow[];
  readonly mcp?: readonly SidebarMcpRow[];
}

export interface SidebarRenderOptions {
  /** Set from the host's NO_COLOR presence; the pure renderer never reads the environment. */
  readonly noColor?: boolean;
}

/** Panel row budget mirrored from pi-sidebar-tui's agents panel, raised for ca-pi. */
export const SIDEBAR_MAX_AGENT_ROWS = 16;
const MAX_TODO_ROWS = 12;
const MAX_MCP_ROWS = 8;
const MAX_LIST_ITEMS = 256;
const MAX_TEXT_POINTS = 512;
const SPARK_GLYPHS = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"] as const;

const ESC = "\x1b";
const RESET = `${ESC}[0m`;
const HEADER_COLOR = `${ESC}[38;2;178;102;255m`;
const MUTED = `${ESC}[38;2;150;150;162m`;
const OK = `${ESC}[38;2;120;220;150m`;
const WARN = `${ESC}[38;2;255;184;76m`;

const OSC_RE = /\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?/gu;
const CSI_RE = /\x1b\[[0-?]*[ -/]*[@-~]?/gu;
const ESCAPE_RE = /\x1b[@-_]/gu;
const CONTROL_RE = /[\u0000-\u001f\u007f-\u009f\u061c\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u206f\ufeff]/gu;

function sanitize(value: unknown): string {
  if (typeof value !== "string") return "";
  return value
    .replace(OSC_RE, "")
    .replace(CSI_RE, "")
    .replace(ESCAPE_RE, "")
    .replace(CONTROL_RE, "")
    .slice(0, MAX_TEXT_POINTS);
}

function boundedNumber(value: unknown, maximum: number): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return 0;
  return Math.min(value, maximum);
}

interface Palette {
  readonly header: string;
  readonly muted: string;
  readonly ok: string;
  readonly warn: string;
  readonly reset: string;
}

const COLOR_PALETTE: Palette = { header: HEADER_COLOR, muted: MUTED, ok: OK, warn: WARN, reset: RESET };
const PLAIN_PALETTE: Palette = { header: "", muted: "", ok: "", warn: "", reset: "" };

interface PanelContext {
  readonly width: number;
  readonly metrics: FooterTextMetrics;
  readonly palette: Palette;
}

function fit(text: string, context: PanelContext): string {
  const { width, metrics, palette } = context;
  let value = text;
  let visible: number;
  try {
    visible = metrics.visibleWidth(value);
  } catch {
    value = "";
    visible = 0;
  }
  if (visible > width) {
    try {
      value = metrics.truncateToWidth(value, width, "…");
      visible = metrics.visibleWidth(value);
    } catch {
      value = "";
      visible = 0;
    }
  }
  if (visible > width) {
    // The host truncator disagreed with its own width report; fail to blank
    // rather than overflow the column.
    value = "";
    visible = 0;
  }
  const padded = value + " ".repeat(width - visible);
  return palette.reset === "" ? padded : padded + palette.reset;
}

function header(title: string, context: PanelContext): string {
  const { width, palette } = context;
  const label = ` ${title} `;
  const room = Math.max(0, width - label.length - 2);
  const bar = "─";
  const text = `${bar}${label}${bar.repeat(room)}`.slice(0, width);
  return fit(`${palette.header}${text}`, context);
}

function tokensLabel(input: number, output: number): string {
  const compact = (value: number) => value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(value);
  return `${compact(input)}↑ ${compact(output)}↓`;
}

function sparkline(series: readonly number[]): string {
  const bounded = series.slice(-16).map((value) => boundedNumber(value, Number.MAX_SAFE_INTEGER));
  if (bounded.length === 0) return "";
  const maximum = Math.max(...bounded);
  return bounded.map((value) => {
    const level = maximum > 0 ? Math.min(8, Math.max(1, Math.ceil((value / maximum) * 8))) : 1;
    return SPARK_GLYPHS[level - 1];
  }).join("");
}

function sessionPanel(session: SidebarSession, context: PanelContext): string[] {
  const { palette } = context;
  const lines: string[] = [header("session", context)];
  const model = sanitize(session.model);
  const thinking = sanitize(session.thinkingLevel);
  if (model !== "") lines.push(fit(` ${model}${thinking === "" ? "" : `${palette.muted} · ${thinking}`}`, context));
  const percent = boundedNumber(session.contextPercent, 999);
  if (session.contextPercent !== undefined) {
    const cells = 10;
    const filled = Math.min(cells, Math.round((Math.min(percent, 100) / 100) * cells));
    const bar = "█".repeat(filled) + "░".repeat(cells - filled);
    const tone = percent >= 80 ? palette.warn : palette.ok;
    lines.push(fit(` ctx ${tone}${bar}${palette.reset === "" ? "" : palette.reset} ${Math.round(percent)}%`, context));
  }
  const input = boundedNumber(session.inputTokens, Number.MAX_SAFE_INTEGER);
  const output = boundedNumber(session.outputTokens, Number.MAX_SAFE_INTEGER);
  const cost = boundedNumber(session.costUsd, 1_000_000_000);
  if (session.inputTokens !== undefined || session.outputTokens !== undefined || session.costUsd !== undefined) {
    lines.push(fit(` ${tokensLabel(input, output)}${palette.muted} · $${cost.toFixed(cost >= 100 ? 0 : 2)}`, context));
  }
  if (session.burn !== undefined && session.burn.length > 0) {
    lines.push(fit(` burn ${sparkline(session.burn)}`, context));
  }
  return lines;
}

function agentGlyph(row: SidebarAgentRow, palette: Palette): string {
  if (row.state === "active") return `${palette.ok}●${palette.reset === "" ? "" : palette.reset}`;
  return `${palette.muted}○${palette.reset === "" ? "" : palette.reset}`;
}

function age(seconds: number): string {
  const bounded = boundedNumber(seconds, 3650 * 86_400);
  if (bounded >= 3600) return `${Math.floor(bounded / 3600)}h`;
  if (bounded >= 60) return `${Math.floor(bounded / 60)}m`;
  return `${Math.floor(bounded)}s`;
}

function agentsPanel(rows: readonly SidebarAgentRow[], context: PanelContext): string[] {
  const { palette } = context;
  const lines: string[] = [header("agents", context)];
  const bounded = rows.slice(0, MAX_LIST_ITEMS);
  for (const row of bounded.slice(0, SIDEBAR_MAX_AGENT_ROWS)) {
    const label = sanitize(row.label);
    const kind = row.kind === "job" ? "job" : "child";
    const suffix = row.ageSeconds === undefined ? "" : ` ${age(row.ageSeconds)}`;
    lines.push(fit(` ${agentGlyph(row, palette)} ${label}${palette.muted} · ${kind}${suffix}`, context));
  }
  if (bounded.length > SIDEBAR_MAX_AGENT_ROWS) {
    lines.push(fit(` ${palette.muted}+${bounded.length - SIDEBAR_MAX_AGENT_ROWS} more`, context));
  }
  return lines;
}

function workspacePanel(workspace: SidebarWorkspace, context: PanelContext): string[] {
  const { palette } = context;
  const lines: string[] = [header("workspace", context)];
  const repository = sanitize(workspace.repository);
  if (repository !== "") {
    const dirty = workspace.dirty === true ? `${palette.warn} ●` : "";
    lines.push(fit(` ${repository}${dirty}`, context));
  }
  const cwd = sanitize(workspace.cwd);
  if (cwd !== "") lines.push(fit(` ${palette.muted}${cwd}`, context));
  return lines;
}

const TODO_GLYPHS: Record<SidebarTodoState, string> = {
  done: "✓",
  active: "▸",
  open: "·",
};

function todosPanel(rows: readonly SidebarTodoRow[], context: PanelContext): string[] {
  const { palette } = context;
  const lines: string[] = [header("todos", context)];
  const bounded = rows.slice(0, MAX_LIST_ITEMS);
  for (const row of bounded.slice(0, MAX_TODO_ROWS)) {
    const glyph = TODO_GLYPHS[row.state] ?? TODO_GLYPHS.open;
    const tone = row.state === "done" ? palette.muted : row.state === "active" ? palette.ok : "";
    lines.push(fit(` ${tone}${glyph} ${sanitize(row.text)}`, context));
  }
  if (bounded.length > MAX_TODO_ROWS) {
    lines.push(fit(` ${palette.muted}+${bounded.length - MAX_TODO_ROWS} more`, context));
  }
  return lines;
}

function mcpPanel(rows: readonly SidebarMcpRow[], context: PanelContext): string[] {
  const { palette } = context;
  const lines: string[] = [header("mcp", context)];
  const bounded = rows.slice(0, MAX_LIST_ITEMS);
  for (const row of bounded.slice(0, MAX_MCP_ROWS)) {
    const state = sanitize(row.state);
    const tone = state === "connected" ? palette.ok : palette.muted;
    lines.push(fit(` ${tone}●${palette.reset === "" ? "" : palette.reset} ${sanitize(row.name)}${palette.muted} · ${state}`, context));
  }
  return lines;
}

/** Render the sidebar column as width-exact lines. Panels appear only when
 * their data source is present (and non-empty for list panels); a panel whose
 * source throws renders as its header plus an omitted-body notice. */
export function renderSidebar(
  input: SidebarInput,
  width: number,
  metrics: FooterTextMetrics,
  options?: SidebarRenderOptions,
): readonly string[] {
  const safeWidth = Number.isSafeInteger(width) && width > 0 ? Math.min(width, 160) : 40;
  const palette = options?.noColor === true ? PLAIN_PALETTE : COLOR_PALETTE;
  const context: PanelContext = { width: safeWidth, metrics, palette };
  const lines: string[] = [];
  const panels: ReadonlyArray<readonly [string, () => string[] | undefined]> = [
    ["session", () => {
      const session = input.session;
      return session === undefined ? undefined : sessionPanel(session, context);
    }],
    ["agents", () => {
      const rows = input.subagents;
      return rows === undefined || rows.length === 0 ? undefined : agentsPanel(rows, context);
    }],
    ["workspace", () => {
      const workspace = input.workspace;
      return workspace === undefined ? undefined : workspacePanel(workspace, context);
    }],
    ["todos", () => {
      const rows = input.todos;
      return rows === undefined || rows.length === 0 ? undefined : todosPanel(rows, context);
    }],
    ["mcp", () => {
      const rows = input.mcp;
      return rows === undefined || rows.length === 0 ? undefined : mcpPanel(rows, context);
    }],
  ];
  for (const [title, render] of panels) {
    let rendered: string[] | undefined;
    try {
      rendered = render();
    } catch {
      rendered = [header(title, context), fit(` ${palette.muted}(unavailable)`, context)];
    }
    if (rendered === undefined || rendered.length === 0) continue;
    if (lines.length > 0) lines.push(fit("", context));
    lines.push(...rendered);
  }
  return Object.freeze(lines);
}
