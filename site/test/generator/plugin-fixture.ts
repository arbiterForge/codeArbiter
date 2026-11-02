/** Synthetic plugin trees for generator tests that need pairs, catalog visibility and curated files. */
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

const roots: string[] = [];

/** A fresh temp directory, removed by {@link cleanupFixtures}. */
export function tempDir(prefix: string): string {
  const dir = mkdtempSync(join(tmpdir(), prefix));
  roots.push(dir);
  return dir;
}

/** Remove every directory made by {@link tempDir}; call from `afterEach`. */
export function cleanupFixtures(): void {
  roots.splice(0).forEach((root) => rmSync(root, { recursive: true, force: true }));
}

export function write(path: string, content: string): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
}

export interface FixtureCommand {
  name: string;
  /** The command source's first heading: `release-flow` claims a skill, `/ca:x — y` claims none. */
  heading: string;
  visibility?: "core" | "advanced" | "alias" | "internal";
  canonical?: string;
  replacement?: string;
  legacyRoutes?: string[];
}

/**
 * Build a plugin tree: one command source per entry, one skill source per skill
 * name, and (unless `withCatalog` is false) the generated command catalog that
 * supplies each command's visibility.
 */
export function buildPlugin(
  commands: readonly FixtureCommand[],
  skills: readonly string[],
  withCatalog = true,
): string {
  const dir = tempDir("ca-fixture-plugin-");
  for (const command of commands) {
    write(
      join(dir, "commands", `${command.name}.md`),
      `---\ndescription: "Fixture ${command.name}."\n---\n\n# ${command.heading}\n\nBody of ${command.name}.\n`,
    );
  }
  for (const skill of skills) {
    write(
      join(dir, "skills", skill, "SKILL.md"),
      `---\nname: ${skill}\ndescription: "Fixture skill ${skill}."\n---\n\n# ${skill}\n\nBody of ${skill}.\n`,
    );
  }
  if (withCatalog) {
    write(
      join(dir, "generated", "command-catalog.json"),
      JSON.stringify({
        schemaVersion: 1,
        visibilityOrder: ["core", "advanced", "alias", "internal", "deprecated"],
        workflowOrder: ["evaluate", "initialize", "change", "review", "decide", "ship", "operate", "extend", "help"],
        compatibility: {},
        commands: Object.fromEntries(
          commands.map((command) => [
            command.name,
            {
              description: `Fixture ${command.name}.`,
              commandPath: `commands/${command.name}.md`,
              visibility: command.visibility ?? "core",
              workflow: "change",
              canonical: command.canonical ?? command.name,
              ...(command.replacement ? { replacement: command.replacement } : {}),
              ...(command.legacyRoutes ? { legacyRoutes: command.legacyRoutes } : {}),
            },
          ]),
        ),
      }),
    );
  }
  return dir;
}

/** Write one curated companion file (`commands/ship.md`, `skills/release-flow.md`) under `curatedDir`. */
export function writeCurated(curatedDir: string, relPath: string, content: string): void {
  write(join(curatedDir, relPath), content);
}
