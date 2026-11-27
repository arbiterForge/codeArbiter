/** gate-index.ts - the data behind the Hook Gates explorer, derived from the hooks themselves.
 *
 * Every gate, its kind, its call sites and their exact messages come from the `block()` and
 * `remind()` call sites (extract-hook-gates.ts). Where a gate fires comes from each script's
 * registered events in hooks.json. Its machine parts and failure scenarios come from the
 * machine model (machine-joins.ts). The one hand-written field is a single plain sentence per
 * gate (src/data/gate-summaries.json), and this module refuses a gate without one, a sentence
 * without a gate, or a sentence filed under the wrong kind.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { extractHookGates, type HookCallSite } from "../generator/extract-hook-gates";
import { buildEventMap, eventsFor, type HooksJson } from "../generator/render-hooks-reference";
import { gateJoin } from "../generator/machine-joins";
import { REPO_ROOT } from "../machine/machine-model";
import summariesJson from "../../src/data/gate-summaries.json" with { type: "json" };

export type GateKind = "block" | "remind";
export type Surface = "shell" | "files" | "after-write" | "git";

/** Where a gate fires, in the reader's terms, in the order the explorer lists them. */
export const SURFACES: Record<Surface, string> = {
  shell: "Shell commands",
  files: "File writes and edits",
  "after-write": "After a write",
  git: "Git backstop",
};

export interface GateSummaries {
  gates: Record<string, { kind: GateKind; summary: string }>;
}

export interface GateSite {
  kind: GateKind;
  file: string;
  line: number;
  message: string;
}

export interface GateEntry {
  tag: string;
  kind: GateKind;
  summary: string;
  surfaces: Surface[];
  events: string[];
  sites: GateSite[];
  /** Parts that cite a file printing the gate: they refuse, or for a reminder, raise it. */
  enforcers: { id: string; name: string; href: string; zoneId: string }[];
  /** Other parts whose hooks list names the gate: what it protects, reads or keeps in force. */
  actsOn: { id: string; name: string; href: string; zoneId: string }[];
  scenarios: { title: string; href: string }[];
}

/** The surface a registered event belongs to, or null when the explorer has no place for it. */
export function surfaceOf(event: string): Surface | null {
  if (/^PreToolUse \((?:Bash|PowerShell)/.test(event)) return "shell";
  if (/^PreToolUse \((?:Edit|MultiEdit|NotebookEdit|Write)/.test(event)) return "files";
  if (/^PostToolUse \((?:Write|Edit)/.test(event)) return "after-write";
  if (event === "git backstop") return "git";
  return null;
}

/** Natural gate order: H-00 ... H-09, H-09b, H-10, H-10b ... */
export function compareGateTags(a: string, b: string): number {
  const parse = (tag: string) => {
    const match = /^H-(\d+)([a-z]?)$/.exec(tag);
    return match ? { num: Number(match[1]), suffix: match[2] } : { num: Number.MAX_SAFE_INTEGER, suffix: tag };
  };
  const pa = parse(a);
  const pb = parse(b);
  return pa.num !== pb.num ? pa.num - pb.num : pa.suffix.localeCompare(pb.suffix);
}

const SURFACE_ORDER = Object.keys(SURFACES) as Surface[];

export function buildGateIndex(
  callSites: HookCallSite[],
  eventMap: Map<string, string[]>,
  summaries: GateSummaries,
  join_: (tag: string, files: string[]) => Pick<GateEntry, "enforcers" | "actsOn" | "scenarios"> = () => ({ enforcers: [], actsOn: [], scenarios: [] }),
): { gates: GateEntry[]; findings: string[] } {
  const findings: string[] = [];
  const byTag = new Map<string, HookCallSite[]>();
  for (const site of callSites) byTag.set(site.tag, [...(byTag.get(site.tag) ?? []), site]);

  for (const tag of Object.keys(summaries.gates)) {
    if (!byTag.has(tag)) findings.push(`${tag} has a summary but no call site in the hooks`);
  }

  const gates: GateEntry[] = [];
  for (const tag of [...byTag.keys()].sort(compareGateTags)) {
    const sites = byTag.get(tag)!;
    const kinds = new Set(sites.map((site) => site.kind));
    if (kinds.size > 1) {
      findings.push(`${tag} both blocks and reminds; one summary cannot describe it`);
      continue;
    }
    const kind = sites[0].kind;
    const summary = summaries.gates[tag];
    if (!summary) {
      findings.push(`${tag} has no summary in src/data/gate-summaries.json`);
      continue;
    }
    if (summary.kind !== kind) findings.push(`${tag} is summarized as ${summary.kind} but its call sites ${kind}`);

    const events = [...new Set(sites.flatMap((site) => eventsFor(site.file, eventMap)))];
    const surfaces = new Set<Surface>();
    for (const event of events) {
      const surface = surfaceOf(event);
      if (surface) surfaces.add(surface);
      else findings.push(`${tag} fires on ${event}, which the explorer cannot place`);
    }
    if (events.length === 0) findings.push(`${tag} has no registered event`);

    gates.push({
      tag,
      kind,
      summary: summary.summary,
      surfaces: SURFACE_ORDER.filter((surface) => surfaces.has(surface)),
      events,
      sites: sites.map(({ kind: siteKind, file, line, message }) => ({ kind: siteKind, file, line, message })),
      ...join_(tag, [...new Set(sites.map((site) => site.file))]),
    });
  }
  return { gates, findings };
}

/** The explorer's index for the shipped hooks. Throws with every finding when it cannot be trusted. */
export function loadGateIndex(repoRoot = REPO_ROOT): GateEntry[] {
  const hooksDir = join(repoRoot, "plugins", "ca", "hooks");
  const { callSites } = extractHookGates(hooksDir);
  const eventMap = buildEventMap(JSON.parse(readFileSync(join(hooksDir, "hooks.json"), "utf8")) as HooksJson);
  const brief = (part: { id: string; name: string; href: string; zoneId: string }) => ({ id: part.id, name: part.name, href: part.href, zoneId: part.zoneId });
  const { gates, findings } = buildGateIndex(callSites, eventMap, summariesJson as GateSummaries, (tag, files) => {
    const machine = gateJoin(tag, files);
    return {
      enforcers: machine.enforcers.map(brief),
      actsOn: machine.actsOn.map(brief),
      scenarios: machine.scenarios.map((scenario) => ({ title: scenario.title, href: scenario.href })),
    };
  });
  if (findings.length > 0) throw new Error(`Hook Gates explorer index is inconsistent:\n- ${findings.join("\n- ")}`);
  return gates;
}
