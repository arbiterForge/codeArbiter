/** command-matrix.ts - every command, spelled for every host, from the shipped catalogs.
 *
 * Rows come from core/surface/command-routes.json (level and workflow), spellings from each
 * host's command_form in core/hosts.json, availability from each host's shipped COMMANDS.md
 * (host-command-catalog.ts), and each lane's route from the machine model (machine-joins.ts).
 * Nothing here is hand-kept: a command no host ships fails the build instead of printing.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { commandHostAvailability, loadHostCommandCatalogs, type CommandHost } from "../generator/host-command-catalog";
import { lanePartFor, routeStops, type RouteStop } from "../generator/machine-joins";
import { readMachineSources, REPO_ROOT } from "../machine/machine-model";
import { spellCommand } from "../machine/machine-render";

export const HOSTS: { name: CommandHost; label: string }[] = [
  { name: "claude", label: "Claude Code" },
  { name: "codex", label: "Codex CLI" },
  { name: "pi", label: "Pi" },
];

export const LEVEL_LABEL: Record<string, string> = {
  core: "Core",
  advanced: "Advanced",
  alias: "Compatibility alias",
  internal: "Internal",
  deprecated: "Deprecated",
};

export interface RoutesManifest {
  visibilityOrder: string[];
  workflowOrder: string[];
  commands: Record<string, { visibility: string; workflow: string; canonical: string; legacyRoutes?: string[]; replacement?: string }>;
}

export interface MatrixRow {
  name: string;
  visibility: string;
  workflow: string;
  /** The command an alias forwards to; equal to `name` for every other command. */
  canonical: string;
  /** For an alias, the command and arguments that replace it, such as "pr --cleanup". */
  replacement: string | null;
  description: string;
  hosts: Record<CommandHost, { available: boolean; spelled: string }>;
  lane: { name: string; href: string; stops: RouteStop[] } | null;
}

export interface MatrixHostInput {
  forms: Record<CommandHost, string>;
  catalogs: Record<CommandHost, ReadonlySet<string>>;
}

/** Build the rows. `descriptions` maps a command to its one-line description, when known. */
export function buildCommandMatrix(
  routes: RoutesManifest,
  descriptions: Record<string, string>,
  hosts: MatrixHostInput = loadHostInput(),
  lane: (command: string) => MatrixRow["lane"] = laneFor,
): MatrixRow[] {
  const rank = (list: string[], value: string) => {
    const index = list.indexOf(value);
    return index === -1 ? list.length : index;
  };
  return Object.entries(routes.commands)
    .map(([name, entry]) => {
      const availability = commandHostAvailability(name, hosts.catalogs);
      if (!HOSTS.some(({ name: host }) => availability[host])) throw new Error(`command-matrix: ${name} is shipped by no host's COMMANDS.md`);
      return {
        name,
        visibility: entry.visibility,
        workflow: entry.workflow,
        canonical: entry.canonical,
        replacement: entry.replacement ?? null,
        description: descriptions[name] ?? "",
        hosts: Object.fromEntries(HOSTS.map(({ name: host }) => [host, { available: availability[host], spelled: spellCommand(hosts.forms[host], name) }])) as MatrixRow["hosts"],
        lane: entry.visibility === "alias" ? null : lane(name),
      };
    })
    .sort((a, b) =>
      rank(routes.visibilityOrder, a.visibility) - rank(routes.visibilityOrder, b.visibility) ||
      rank(routes.workflowOrder, a.workflow) - rank(routes.workflowOrder, b.workflow) ||
      a.name.localeCompare(b.name),
    );
}

function laneFor(command: string): MatrixRow["lane"] {
  const part = lanePartFor(command);
  if (!part) return null;
  return { name: part.name, href: part.href, stops: routeStops(part.id) };
}

function loadHostInput(repoRoot = REPO_ROOT): MatrixHostInput {
  const sources = readMachineSources(repoRoot);
  const forms = Object.fromEntries(HOSTS.map(({ name }) => {
    const host = sources.hosts.find((candidate) => candidate.name === name);
    if (!host) throw new Error(`command-matrix: core/hosts.json has no host ${name}`);
    return [name, host.commandForm];
  })) as Record<CommandHost, string>;
  const catalogs = loadHostCommandCatalogs(join(repoRoot, "plugins", "ca")) as Record<CommandHost, ReadonlySet<string>>;
  return { forms, catalogs };
}

export function loadCommandMatrix(descriptions: Record<string, string> = {}, repoRoot = REPO_ROOT): MatrixRow[] {
  const routes = JSON.parse(readFileSync(join(repoRoot, "core", "surface", "command-routes.json"), "utf8")) as RoutesManifest;
  return buildCommandMatrix(routes, descriptions, loadHostInput(repoRoot));
}
