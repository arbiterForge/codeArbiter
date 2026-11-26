/** machine-model.ts - load the "codeArbiter as a machine" model and refuse drift from the plugin sources.
 *
 * The explanations in machine-data/ are curated. Everything they state about the
 * shipped plugin is resolved from the same sources the reference generator reads:
 * hook gate IDs, kinds and messages from plugins/ca/hooks (extract-hook-gates),
 * command identity, visibility and lane family from core/surface/command-routes.json,
 * host spelling and capabilities from core/hosts.json, and the version from the
 * plugin manifest. validateMachine() returns every disagreement as a sentence;
 * loadMachine() refuses to build while any remain. See site/MACHINE.md.
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { extractHookGates, type HookCallSite } from "../generator/extract-hook-gates";
import { checkClaims, type MachineClaim } from "./machine-claims";
// Imported rather than read from disk, so the bundled page build carries the committed model.
import claims from "./machine-data/claims.json" with { type: "json" };
import faults from "./machine-data/faults.json" with { type: "json" };
import glossary from "./machine-data/glossary.json" with { type: "json" };
import key from "./machine-data/key.json" with { type: "json" };
import labs from "./machine-data/labs.json" with { type: "json" };
import layout from "./machine-data/layout.json" with { type: "json" };
import parts from "./machine-data/parts.json" with { type: "json" };
import provenance from "./machine-data/provenance.json" with { type: "json" };
import tours from "./machine-data/tours.json" with { type: "json" };

/** The checkout root, found from the working directory as the atlas does: bundled build chunks have no stable module path. */
function repositoryRoot(): string {
  let root = process.cwd();
  while (!existsSync(resolve(root, "core/hosts.json")) || !existsSync(resolve(root, "site/package.json"))) {
    const parent = dirname(root);
    if (parent === root) throw new Error("Build the machine model inside the codeArbiter checkout");
    root = parent;
  }
  return root;
}

export const REPO_ROOT = repositoryRoot();

export type HostName = "claude" | "codex" | "pi";
/** One stop on a lane: the part it reaches, the state it shows there, and what happens. */
export type RouteStop = [at: string, state: string, text: string];

export interface MachinePart {
  zone: string;
  kind: string;
  name: string;
  tagline: string;
  what: string;
  simple: string;
  machine?: string;
  how?: string[];
  watch?: string;
  source?: string[];
  related: string[];
  hooks?: string[];
  stops?: string;
  produces?: string;
  /** A Feature Forge preview: shipping, but off until opted in. */
  preview?: boolean;
  cmd?: string;
  family?: string;
  tier?: string;
  args?: string;
  aliases?: string[];
  route?: RouteStop[];
}

export interface TourStep {
  at?: string;
  view?: string;
  title: string;
  text: string;
  fx?: string;
}

export interface MachineTour {
  id: string;
  title: string;
  summary: string;
  steps: TourStep[];
}

export interface MachineFault {
  id: string;
  kind: string;
  title: string;
  catcher?: string;
  tag?: string;
  outcome?: string;
  why?: string;
  steps?: TourStep[];
  /** True when the scenario is an existing tour, listed again under its own id. */
  ref?: boolean;
}

export interface MachineLayout {
  zones: Record<string, { name: string; blurb: string }>;
  families: Record<string, { name: string; blurb: string }>;
  states: Record<string, { label: string; color: string }>;
  laneOrder: [family: string, commands: string[]][];
  hostOmissions: Record<HostName, string[]>;
}

export interface MachineKey {
  frames: { shape: string; name: string; meaning: string }[];
  kindFrames: Record<string, string>;
  motions: { motion: string; name: string; meaning: string }[];
}

export interface GlossaryEntry {
  term: string;
  aliases: string[];
  definition: string;
  part?: string;
  /** Anchor of the same term in the site glossary, which stays the reference for codeArbiter's meaning. */
  siteGlossary?: string;
}

/** `## Term` headings of the site glossary, with the anchor Starlight gives each. */
export function siteGlossaryTerms(markdown: string): { term: string; anchor: string }[] {
  return [...markdown.matchAll(/^## (.+)$/gm)].map(([, heading]) => ({
    term: heading.trim(),
    anchor: heading.trim().toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, "").trim().replace(/\s+/g, "-"),
  }));
}

const termKey = (term: string) => term.replace(/\s*\(.*\)\s*$/, "").trim().toLowerCase();

/** Link every machine glossary term that the site glossary also defines to that entry. */
export function linkSiteGlossary(entries: GlossaryEntry[], site: { term: string; anchor: string }[]): GlossaryEntry[] {
  const anchors = new Map(site.map((entry) => [termKey(entry.term), entry.anchor]));
  return entries.map((entry) => {
    const anchor = [entry.term, ...entry.aliases].map((name) => anchors.get(termKey(name))).find(Boolean);
    return anchor ? { ...entry, siteGlossary: anchor } : entry;
  });
}

export interface MachineProvenance {
  schema: 1;
  model: string;
  authoredAgainst: { release: string; commit: string };
  reviewedAt: { commit: string; date: string };
  checkedOnEveryBuild: string[];
  illustrative: string[];
}

export interface MachineData {
  parts: Record<string, MachinePart>;
  layout: MachineLayout;
  tours: MachineTour[];
  faults: MachineFault[];
  labs: Record<string, { tab: string; title: string; blurb: string }>;
  glossary: GlossaryEntry[];
  key: MachineKey;
  claims: MachineClaim[];
  provenance: MachineProvenance;
}

export interface MachineSources {
  commands: Map<string, { visibility: string; workflow: string }>;
  hosts: { name: HostName; commandForm: string; capabilities: Record<string, boolean> }[];
  gates: HookCallSite[];
  version: string;
  exists(path: string): boolean;
  read(path: string): string;
}

export interface GateSite {
  file: string;
  line: number;
  message: string;
  /** True for the git-level backstop (git-enforce.py), which does not write gate-events.log. */
  backstop: boolean;
}

export interface MachineModel extends Omit<MachineData, "claims"> {
  version: string;
  hosts: { name: HostName; label: string; commandForm: string; omits: string[] }[];
  gates: Record<string, { kind: "block" | "remind"; sites: GateSite[] }>;
  claims: MachineClaim[];
}

const HOST_LABELS: Record<HostName, string> = { claude: "Claude Code", codex: "Codex CLI", pi: "Pi" };
/** Lanes exist for every command a reader can be routed to; aliases and deprecated spellings ride on their canonical lane. */
const LANE_VISIBILITY = new Set(["core", "advanced", "internal"]);
const GATE_TAG = /\bH-\d{2}[a-z]?\b/g;
const PLACEHOLDER = /\{\{([a-z][a-z-]*)((?:\s[^}]*)?)\}\}/g;

const readJson = <T>(path: string): T => JSON.parse(readFileSync(path, "utf8")) as T;

/** The curated model exactly as committed; a fresh copy each call, so callers may change it freely. */
export function readMachineData(): MachineData {
  return structuredClone({ parts, layout, tours, faults, labs, glossary, key, claims, provenance }) as unknown as MachineData;
}

/** The plugin facts the model is checked against, read from the working tree. */
export function readMachineSources(repoRoot = REPO_ROOT): MachineSources {
  const routes = readJson<{ commands: Record<string, { visibility: string; workflow: string }> }>(
    join(repoRoot, "core", "surface", "command-routes.json"),
  );
  const hosts = readJson<{ hosts: { name: HostName; command_form: string; capabilities: Record<string, boolean> }[] }>(
    join(repoRoot, "core", "hosts.json"),
  );
  const manifest = readJson<{ version: string }>(join(repoRoot, "plugins", "ca", ".claude-plugin", "plugin.json"));
  return {
    commands: new Map(Object.entries(routes.commands).map(([name, c]) => [name, { visibility: c.visibility, workflow: c.workflow }])),
    hosts: hosts.hosts.map((h) => ({ name: h.name, commandForm: h.command_form, capabilities: h.capabilities })),
    gates: extractHookGates(join(repoRoot, "plugins", "ca", "hooks")).callSites,
    version: manifest.version,
    exists: (path) => existsSync(join(repoRoot, path)),
    read: (path) => readFileSync(join(repoRoot, path), "utf8"),
  };
}

/** Every reader-facing string of a part, for the tag and command-spelling checks. */
function partTexts(part: MachinePart): string[] {
  return [part.tagline, part.what, part.simple, part.machine, part.watch, part.stops, part.produces,
    ...(part.how ?? []), ...(part.route ?? []).map((stop) => stop[2])].filter((t): t is string => typeof t === "string");
}

const stepTexts = (steps: TourStep[] = []) => steps.flatMap((step) => [step.title, step.text]);

/** Every disagreement between the curated model and the plugin sources, as one sentence each. */
export function validateMachine(data: MachineData, sources: MachineSources): string[] {
  const findings: string[] = [];
  const { parts, layout, key } = data;
  const partIds = new Set(Object.keys(parts));
  const tourIds = new Set(data.tours.map((tour) => tour.id));
  const gateKinds = new Map<string, Set<string>>();
  for (const site of sources.gates) {
    const kinds = gateKinds.get(site.tag) ?? new Set<string>();
    kinds.add(site.kind);
    gateKinds.set(site.tag, kinds);
  }

  const checkText = (owner: string, texts: string[]) => {
    for (const text of texts) {
      for (const tag of text.match(GATE_TAG) ?? []) {
        if (!gateKinds.has(tag)) findings.push(`${owner} names gate ${tag}, which no hook in plugins/ca/hooks defines`);
      }
      for (const [spelled, name] of text.matchAll(PLACEHOLDER)) {
        if (!sources.commands.has(name)) findings.push(`${owner} spells ${spelled}, but ${name} is not a command in core/surface/command-routes.json`);
      }
    }
  };
  const checkSteps = (owner: string, steps: TourStep[] = []) => {
    for (const step of steps) {
      if (step.at && !partIds.has(step.at)) findings.push(`${owner} stops at unknown part ${step.at}`);
      const call = step.fx?.startsWith("call:") ? step.fx.slice(5).split(";") : undefined;
      if (call && call[2]) {
        const [, verdict, tag] = call;
        const kinds = gateKinds.get(tag);
        if (!kinds) findings.push(`${owner} shows gate ${tag}, which no hook in plugins/ca/hooks defines`);
        else if (verdict === "block" && !kinds.has("block")) findings.push(`${owner} shows ${tag} as a block, but every ${tag} call site only reminds`);
        else if (verdict === "remind" && !kinds.has("remind")) findings.push(`${owner} shows ${tag} as a reminder, but every ${tag} call site blocks`);
      }
    }
    checkText(owner, stepTexts(steps));
  };

  for (const [id, part] of Object.entries(parts)) {
    if (!(part.kind in key.kindFrames)) findings.push(`${id} has kind ${part.kind}, which the key does not draw`);
    if (!(part.zone in layout.zones)) findings.push(`${id} sits in zone ${part.zone}, which the layout does not define`);
    for (const other of part.related) if (!partIds.has(other)) findings.push(`${id} relates to unknown part ${other}`);
    for (const [at, state] of part.route ?? []) {
      if (!partIds.has(at)) findings.push(`${id} routes through unknown part ${at}`);
      if (!(state in layout.states)) findings.push(`${id} shows unknown state ${state} at ${at}`);
    }
    for (const tag of part.hooks ?? []) if (!gateKinds.has(tag)) findings.push(`${id} names gate ${tag}, which no hook in plugins/ca/hooks defines`);
    for (const cited of part.source ?? []) {
      const path = cited.replace(/\s+\(.*\)$/, "");
      // Paths under .codearbiter/ name a governed project's own state, not this repository's files.
      if (!path.startsWith(".codearbiter/") && !sources.exists(path)) findings.push(`${id} cites ${path}, which does not exist`);
    }
    checkText(id, partTexts(part));
  }

  // Lanes: one per routable command, filed exactly as command-routes.json files it.
  const lanes = Object.entries(parts).filter(([, part]) => part.kind === "Lane");
  const laneCommands = new Set<string>();
  for (const [id, part] of lanes) {
    const name = part.cmd ?? "";
    laneCommands.add(name);
    const route = sources.commands.get(name);
    if (!route) {
      findings.push(`lane ${id} names command ${name}, which core/surface/command-routes.json does not define`);
      continue;
    }
    if (id !== `ca-${name}`) findings.push(`lane ${id} should be named ca-${name}`);
    if (part.family !== route.workflow) findings.push(`lane ${id} is filed under ${part.family}, but ${name} belongs to ${route.workflow}`);
    if (part.tier !== route.visibility) findings.push(`lane ${id} is marked ${part.tier}, but ${name} is ${route.visibility}`);
  }
  for (const [name, route] of sources.commands) {
    if (LANE_VISIBILITY.has(route.visibility) && !laneCommands.has(name)) {
      findings.push(`command ${name} (${route.visibility}, ${route.workflow}) has no lane`);
    }
  }
  const ordered = layout.laneOrder.flatMap(([family, names]) => names.map((name) => ({ family, name })));
  for (const { family, name } of ordered) {
    if (!laneCommands.has(name)) findings.push(`laneOrder lists ${name}, which has no lane part`);
    else if (parts[`ca-${name}`]?.family !== family) findings.push(`laneOrder files ${name} under ${family}`);
  }
  for (const name of laneCommands) if (!ordered.some((entry) => entry.name === name)) findings.push(`laneOrder leaves out lane ${name}`);

  // Hosts: spellings come from hosts.json; a host omits exactly the commands its capabilities turn off.
  for (const host of sources.hosts) {
    const expected = Object.entries(host.capabilities).filter(([cap, on]) => !on && sources.commands.has(cap)).map(([cap]) => cap).sort();
    const shown = [...(layout.hostOmissions[host.name] ?? [])].sort();
    if (expected.join() !== shown.join()) {
      findings.push(`${host.name} omits ${shown.join(", ") || "nothing"}, but core/hosts.json leaves out ${expected.join(", ") || "nothing"}`);
    }
  }

  for (const tour of data.tours) checkSteps(`tour ${tour.id}`, tour.steps);
  for (const fault of data.faults) {
    if (fault.catcher && !partIds.has(fault.catcher)) findings.push(`scenario ${fault.id} is caught by unknown part ${fault.catcher}`);
    if (fault.ref && !tourIds.has(fault.id)) findings.push(`scenario ${fault.id} reuses a tour, but no tour has that id`);
    checkSteps(`scenario ${fault.id}`, fault.steps);
    checkText(`scenario ${fault.id}`, [fault.title, fault.why, fault.outcome, fault.tag].filter((t): t is string => !!t));
  }
  for (const entry of data.glossary) {
    if (entry.part && !partIds.has(entry.part)) findings.push(`glossary term ${entry.term} points at unknown part ${entry.part}`);
    checkText(`glossary term ${entry.term}`, [entry.definition]);
  }

  findings.push(...checkClaims(data.claims, sources.read));
  return findings;
}

/** The validated model with source-derived gates, hosts and version. Throws on any drift. */
export function loadMachine(repoRoot = REPO_ROOT): MachineModel {
  const data = readMachineData();
  const sources = readMachineSources(repoRoot);
  const findings = validateMachine(data, sources);
  if (findings.length) {
    throw new Error(`The machine model (site/scripts/machine/machine-data) disagrees with the plugin sources. Review each finding, then update the model (see site/MACHINE.md):\n- ${findings.join("\n- ")}`);
  }
  const gates: MachineModel["gates"] = {};
  for (const site of sources.gates) {
    const gate = (gates[site.tag] ??= { kind: "remind", sites: [] });
    if (site.kind === "block") gate.kind = "block";
    gate.sites.push({ file: site.file, line: site.line, message: site.message, backstop: site.file === "git-enforce.py" });
  }
  return {
    ...data,
    glossary: linkSiteGlossary(data.glossary, siteGlossaryTerms(sources.read("site/src/content/docs/glossary.md"))),
    version: sources.version,
    hosts: sources.hosts.map((host) => ({ name: host.name, label: HOST_LABELS[host.name], commandForm: host.commandForm, omits: data.layout.hostOmissions[host.name] ?? [] })),
    gates,
  };
}
