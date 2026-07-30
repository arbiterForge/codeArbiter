import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

const siteRoot = resolve(import.meta.dirname, "../..");
const repoRoot = resolve(siteRoot, "..");
const pluginRoot = join(repoRoot, "plugins", "ca");
const curatedRoot = join(siteRoot, "src", "curated");

function sourceEntities(): string[] {
  const commands = readdirSync(join(pluginRoot, "commands"))
    .filter((name) => name.endsWith(".md"))
    .map((name) => `commands/${name.replace(/\.md$/, "")}`);

  const agents = readdirSync(join(pluginRoot, "agents"))
    .filter((name) => name.endsWith(".md") && name.toLowerCase() !== "index.md")
    .map((name) => `agents/${name.replace(/\.md$/, "")}`);

  const skills = readdirSync(join(pluginRoot, "skills"), { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => `skills/${entry.name}`);

  return [...commands, ...agents, ...skills].sort();
}

function curatedEntities(): string[] {
  const entities: string[] = [];
  for (const collection of ["commands", "agents", "skills"]) {
    for (const name of readdirSync(join(curatedRoot, collection))) {
      if (!name.endsWith(".md")) continue;
      const source = readFileSync(join(curatedRoot, collection, name), "utf8");
      const entity = source.match(/^entity:\s*(\S+)\s*$/m)?.[1];
      if (entity) entities.push(entity);
    }
  }
  return entities.sort();
}

describe("generated reference curated coverage", () => {
  it("has curated reader framing for every published command, agent, and skill", () => {
    const source = sourceEntities();
    const curated = new Set(curatedEntities());
    const missing = source.filter((entity) => !curated.has(entity));

    expect(missing, `Missing curated reference framing: ${missing.join(", ")}`).toEqual([]);
  });
});
