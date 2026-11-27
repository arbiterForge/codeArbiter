/** machine-joins.ts - where a reference entity sits in the 3D machine on /concepts/machine/.
 *
 * Joins are exact, never curated. A page links a machine part only when the machine model
 * cites that page's own plugin file among the part's sources (machine-data/parts.json; the
 * machine validator checks every cited path exists). A command joins the lane part the model
 * keeps for it. A hook gate joins the parts whose hooks list carries its ID and the failure
 * scenarios tagged with it. Links are root-absolute; rehype-base-links adds the site base.
 */
import parts from "../machine/machine-data/parts.json" with { type: "json" };
import key from "../machine/machine-data/key.json" with { type: "json" };
import layout from "../machine/machine-data/layout.json" with { type: "json" };
import faults from "../machine/machine-data/faults.json" with { type: "json" };
import { framePath } from "../machine/machine-render";

interface ModelPart {
  zone: string;
  kind: string;
  name?: string;
  cmd?: string;
  hooks?: string[];
  source?: string[];
  route?: [string, string, string][];
}

export interface JoinedPart {
  id: string;
  /** Machine zone id, such as "guards"; colour follows it. */
  zoneId: string;
  /** Display name; lane parts carry a command, so they read "/ca:<cmd> lane". */
  name: string;
  zone: string;
  shape: string;
  href: string;
  /** The plugin files the model cites for this part. */
  sources: string[];
}

export interface RouteStop {
  part: string;
  name: string;
  shape: string;
  tone: string;
  verdict: string;
}

const MODEL = parts as unknown as Record<string, ModelPart>;
const FRAMES = key.kindFrames as Record<string, string>;
const ZONES = layout.zones as Record<string, { name: string }>;
const SCENARIOS = faults as unknown as { id: string; title: string; tag?: string }[];
const MACHINE = "/concepts/machine/";

/** Colour meanings from the machine key: gold waits on a gate or on you, green passes, red fails or refuses. */
const TONE: Record<string, string> = { run: "steel", gate: "brand", ask: "brand", pass: "positive", fail: "danger", stop: "danger", block: "danger", preview: "preview" };

function joined(id: string): JoinedPart {
  const part = MODEL[id];
  if (!part) throw new Error(`machine-joins: unknown machine part ${id}`);
  return {
    id,
    zoneId: part.zone,
    name: part.name ?? (part.cmd ? `/ca:${part.cmd} lane` : id),
    zone: ZONES[part.zone]?.name ?? part.zone,
    shape: FRAMES[part.kind] ?? "square",
    href: `${MACHINE}#part-${id}`,
    sources: [...(part.source ?? [])],
  };
}

/** One machine part, named and framed the way every join shows it. Throws on an unknown id. */
export function partById(id: string): JoinedPart {
  return joined(id);
}

/** Parts whose cited sources include this plugin file, directly or through its directory. */
export function partsCiting(sourceRelPath: string): JoinedPart[] {
  return Object.entries(MODEL)
    .filter(([, part]) => (part.source ?? []).some((cited) => cited === sourceRelPath || (cited.endsWith("/") && sourceRelPath.startsWith(cited))))
    .map(([id]) => joined(id));
}

/** The lane part the machine keeps for a command, or null. */
export function lanePartFor(command: string): JoinedPart | null {
  const entry = Object.entries(MODEL).find(([, part]) => part.kind === "Lane" && part.cmd === command);
  return entry ? joined(entry[0]) : null;
}

export function routeStops(laneId: string): RouteStop[] {
  return (MODEL[laneId]?.route ?? []).map(([id, verdict]) => {
    const part = joined(id);
    return { part: id, name: part.name, shape: part.shape, tone: TONE[verdict] ?? "steel", verdict };
  });
}

/** A lane's route as decorative machine frames. The surrounding text carries the meaning. */
export function routeLineHtml(stops: RouteStop[]): string {
  const items = stops
    .map((stop, index) =>
      `<span class="ca-route__stop" data-tone="${stop.tone}" title="${stop.name} (${stop.verdict})" style="--i:${index}">` +
      `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">${framePath(stop.shape)}</svg></span>`,
    )
    .join("");
  return `<div class="ca-route" aria-hidden="true" style="--stops:${stops.length}">${items}</div>`;
}

const GATE_ID = /\bH-\d{2}[a-z]?\b/g;

export interface GateJoin {
  /** Parts that cite a hook file which prints the gate: the code that refuses or reminds. */
  enforcers: JoinedPart[];
  /** Other parts whose hooks list names the gate: what it protects, reads or keeps from being
   * skipped, such as the protected branch for H-01 or the git backstop for H-20. */
  actsOn: JoinedPart[];
  scenarios: { id: string; title: string; href: string }[];
}

/**
 * Where a hook gate sits in the machine. `files` are the hook files whose call sites print the
 * gate (extract-hook-gates.ts). A part enforces the gate only when the model cites one of those
 * files itself; a part that cites the whole hooks directory is an umbrella, not the guard.
 */
export function gateJoin(tag: string, files: string[] = []): GateJoin {
  const printing = new Set(files.map((file) => `plugins/ca/hooks/${file}`));
  const enforcers = Object.entries(MODEL)
    .filter(([, part]) => (part.source ?? []).some((cited) => printing.has(cited)))
    .map(([id]) => joined(id));
  const enforcing = new Set(enforcers.map((part) => part.id));
  return {
    enforcers,
    actsOn: Object.entries(MODEL)
      .filter(([id, part]) => !enforcing.has(id) && (part.hooks ?? []).includes(tag))
      .map(([id]) => joined(id)),
    scenarios: SCENARIOS.filter((scenario) => [...(scenario.tag ?? "").matchAll(GATE_ID)].some(([id]) => id === tag)).map((scenario) => ({
      id: scenario.id,
      title: scenario.title,
      href: `${MACHINE}#${scenario.id}`,
    })),
  };
}

/**
 * Machine text made safe for Markdown link text: Markdown punctuation is escaped and command-line
 * flags become inline code, so smart typography cannot print `--no-verify` as a dash.
 */
export function markdownText(text: string): string {
  return text
    .replace(/[\\[\]*_<>`]/g, (character) => `\\${character}`)
    .replace(/(^|\s)(--?[A-Za-z][\w-]*)/g, (_, space: string, flag: string) => `${space}\`${flag}\``);
}

/** Markdown links to joined parts: "[Shell gate (pre-bash)](/concepts/machine/#part-guard-bash) and ...". */
export function partLinks(list: JoinedPart[]): string {
  const links = list.map((part) => `[${markdownText(part.name)}](${part.href})`);
  return links.length > 1 ? `${links.slice(0, -1).join(", ")} and ${links.at(-1)}` : (links[0] ?? "");
}
