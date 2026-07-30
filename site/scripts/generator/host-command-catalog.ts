import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";

export type CommandHost = "claude" | "codex" | "pi";

export type CommandHostAvailability = Readonly<Record<CommandHost, boolean>>;

const HOST_CATALOGS: Readonly<Record<CommandHost, string>> = {
  claude: "ca/COMMANDS.md",
  codex: "ca-codex/COMMANDS.md",
  pi: "ca-pi/COMMANDS.md",
};

const COMMAND_PATTERNS: Readonly<Record<CommandHost, RegExp>> = {
  claude: /`\/ca:([a-z0-9-]+)`/g,
  codex: /`\$ca-([a-z0-9-]+)`/g,
  pi: /`\/ca-([a-z0-9-]+)`/g,
};

export function parseHostCommandCatalog(
  host: CommandHost,
  markdown: string,
): ReadonlySet<string> {
  return new Set(
    Array.from(markdown.matchAll(COMMAND_PATTERNS[host]), (match) => match[1]),
  );
}

/**
 * Load the three shipped command catalogs adjacent to `plugins/ca`. Synthetic
 * generator fixtures do not carry sibling adapters, so they fall back to the
 * collected Claude command names and mark the other hosts unavailable.
 */
export function loadHostCommandCatalogs(
  claudePluginDir: string,
  fallbackClaudeCommands: readonly string[] = [],
): Readonly<Record<CommandHost, ReadonlySet<string>>> {
  const pluginsDir = dirname(claudePluginDir);
  const fallback = {
    claude: new Set(fallbackClaudeCommands),
    codex: new Set<string>(),
    pi: new Set<string>(),
  };

  return Object.fromEntries(
    (Object.keys(HOST_CATALOGS) as CommandHost[]).map((host) => {
      const path = join(pluginsDir, HOST_CATALOGS[host]);
      if (!existsSync(path)) return [host, fallback[host]];
      return [
        host,
        parseHostCommandCatalog(host, readFileSync(path, "utf8")),
      ];
    }),
  ) as Record<CommandHost, ReadonlySet<string>>;
}

export function commandHostAvailability(
  command: string,
  catalogs: Readonly<Record<CommandHost, ReadonlySet<string>>>,
): CommandHostAvailability {
  return {
    claude: catalogs.claude.has(command),
    codex: catalogs.codex.has(command),
    pi: catalogs.pi.has(command),
  };
}
