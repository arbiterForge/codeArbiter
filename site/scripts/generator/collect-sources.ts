import { readdirSync, readFileSync, existsSync, statSync } from "node:fs";
import { join } from "node:path";
import { classifySource } from "./classify-source";
import type { SourceFile } from "./types";

export function collectSources(rootDir: string): SourceFile[] {
  if (!existsSync(rootDir)) {
    return [];
  }

  const result: SourceFile[] = [];

  // commands
  const commandsDir = join(rootDir, "commands");
  if (existsSync(commandsDir)) {
    const entries = readdirSync(commandsDir);
    for (const entry of entries) {
      if (entry.endsWith(".md")) {
        const raw = readFileSync(join(commandsDir, entry), "utf-8");
        const path = `commands/${entry}`;
        result.push({ path, raw, type: classifySource(path) });
      }
    }
  }

  // agents
  const agentsDir = join(rootDir, "agents");
  if (existsSync(agentsDir)) {
    const entries = readdirSync(agentsDir);
    for (const entry of entries) {
      if (entry.endsWith(".md")) {
        const raw = readFileSync(join(agentsDir, entry), "utf-8");
        const path = `agents/${entry}`;
        result.push({ path, raw, type: classifySource(path) });
      }
    }
  }

  // skills
  const skillsDir = join(rootDir, "skills");
  if (existsSync(skillsDir)) {
    const entries = readdirSync(skillsDir);
    for (const entry of entries) {
      const skillSubdir = join(skillsDir, entry);
      if (statSync(skillSubdir).isDirectory()) {
        const skillMd = join(skillSubdir, "SKILL.md");
        if (existsSync(skillMd)) {
          const raw = readFileSync(skillMd, "utf-8");
          const path = `skills/${entry}/SKILL.md`;
          result.push({ path, raw, type: classifySource(path) });
        }
      }
    }
  }

  // stable sort by path
  result.sort((a, b) => a.path.localeCompare(b.path));
  return result;
}
