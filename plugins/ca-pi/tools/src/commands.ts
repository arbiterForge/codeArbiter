import { lstatSync, readFileSync, realpathSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import type {
  Collision,
  CommandCatalogEntry,
  ExtensionContextPort,
  ParentPiPort,
  SlashCommand,
} from "./contracts.ts";

const COMMAND_DIAGNOSIS = "codeArbiter could not validate the Pi command surface; run /ca-doctor.";
const NAME = /^[a-z][a-z0-9-]*$/u;
const ENVELOPE_UNSAFE = /[\n\r"<>]/u;

function inside(path: string, root: string): boolean {
  const suffix = relative(root, path);
  return suffix === "" || (!suffix.startsWith("..") && !isAbsolute(suffix));
}

function pluginRootFromModule(): string {
  let cursor = dirname(fileURLToPath(import.meta.url));
  while (true) {
    try {
      const manifest = JSON.parse(readFileSync(resolve(cursor, "package.json"), "utf8")) as { name?: unknown };
      if (manifest.name === "ca-pi") return realpathSync(cursor);
    } catch {
      // Continue toward the filesystem root; ca-pi-tools is intentionally skipped.
    }
    const parent = dirname(cursor);
    if (parent === cursor) throw new Error(COMMAND_DIAGNOSIS);
    cursor = parent;
  }
}

function validatedEntry(entry: CommandCatalogEntry): void {
  if (!NAME.test(entry.name) || ENVELOPE_UNSAFE.test(entry.name)) throw new Error(COMMAND_DIAGNOSIS);
  if (entry.skillPath !== `skills/ca-${entry.name}/SKILL.md` || isAbsolute(entry.skillPath)) {
    throw new Error(COMMAND_DIAGNOSIS);
  }
  if (entry.skillPath.split("/").some((part) => part === "" || part === "." || part === "..")) {
    throw new Error(COMMAND_DIAGNOSIS);
  }
}

function strictUtf8(path: string): string {
  const bytes = readFileSync(path);
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

function hasSymlinkComponent(root: string, path: string): boolean {
  const lexicalRoot = resolve(root);
  const lexicalPath = resolve(path);
  if (!inside(lexicalPath, lexicalRoot) || lstatSync(lexicalRoot).isSymbolicLink()) return true;
  const suffix = relative(lexicalRoot, lexicalPath);
  let cursor = lexicalRoot;
  for (const part of suffix.split(/[\\/]/u).filter(Boolean)) {
    cursor = resolve(cursor, part);
    if (lstatSync(cursor).isSymbolicLink()) return true;
  }
  return false;
}

function stripStartingFrontmatter(content: string): string {
  const normalized = content.replaceAll("\r\n", "\n").replaceAll("\r", "\n");
  if (!normalized.startsWith("---\n")) return normalized.trim();
  let end = normalized.indexOf("\n---\n", 4);
  if (end < 0 && normalized.endsWith("\n---")) end = normalized.length - 4;
  if (end < 0) return normalized.trim();
  return normalized.slice(end + 4).trim();
}

export function nativeSkillExpansion(
  name: string,
  path: string,
  body: string,
  args: string,
): string {
  const baseDir = dirname(path);
  const block = `<skill name="ca-${name}" location="${path}">\n`
    + `References are relative to ${baseDir}.\n\n${body}\n</skill>`;
  return args.length > 0 ? `${block}\n\n${args}` : block;
}

function declaredPackageOwner(command: SlashCommand, expectedPath: string): boolean {
  try {
    if (command.sourceInfo.origin !== "package" || command.sourceInfo.baseDir === undefined) return false;
    if (hasSymlinkComponent(command.sourceInfo.baseDir, command.sourceInfo.path)) return false;
    const canonicalPath = realpathSync(command.sourceInfo.path);
    const canonicalExpected = realpathSync(expectedPath);
    const canonicalBase = realpathSync(command.sourceInfo.baseDir);
    if (canonicalPath !== canonicalExpected || !inside(canonicalPath, canonicalBase)) return false;
    const manifest = JSON.parse(strictUtf8(resolve(canonicalBase, "package.json"))) as {
      name?: unknown;
      pi?: { extensions?: unknown; skills?: unknown };
    };
    if (manifest.name !== "ca-pi" || manifest.pi === undefined) return false;
    const declared = command.source === "extension" ? manifest.pi.extensions : manifest.pi.skills;
    if (!Array.isArray(declared) || !declared.every((item) => typeof item === "string")) return false;
    return declared.some((item) => {
      const target = resolve(canonicalBase, item as string);
      return command.source === "extension"
        ? realpathSync(target) === canonicalPath
        : inside(canonicalPath, realpathSync(target));
    });
  } catch {
    return false;
  }
}

function fallbackCommand(
  pi: ParentPiPort,
  packageRoot: string,
  entry: CommandCatalogEntry,
): SlashCommand | undefined {
  const expected = resolve(packageRoot, ...entry.skillPath.split("/"));
  const matches = pi.getCommands().filter((command) => command.name === `skill:ca-${entry.name}`);
  if (matches.length !== 1 || matches[0].source !== "skill") return undefined;
  return declaredPackageOwner(matches[0], expected) ? matches[0] : undefined;
}

export function registerAliases(
  pi: ParentPiPort,
  catalog: readonly CommandCatalogEntry[],
  packageRoot = pluginRootFromModule(),
  onDegraded?: (status: string) => void,
  appendGeneratedContent?: (
    entry: CommandCatalogEntry,
    args: string,
    context: ExtensionContextPort,
  ) => Promise<string | undefined>,
): void {
  const canonicalRoot = realpathSync(packageRoot);
  for (const entry of catalog) {
    validatedEntry(entry);
    pi.registerCommand(`ca-${entry.name}`, {
      description: entry.description,
      handler: async (args, context) => {
        try {
          if (assertCommandOwnership(pi, canonicalRoot, [entry]).length > 0) {
            throw new Error(COMMAND_DIAGNOSIS);
          }
          const fallback = fallbackCommand(pi, canonicalRoot, entry);
          if (fallback === undefined) throw new Error(COMMAND_DIAGNOSIS);
          const expectedPath = resolve(canonicalRoot, ...entry.skillPath.split("/"));
          if (fallback.sourceInfo.baseDir === undefined ||
              hasSymlinkComponent(fallback.sourceInfo.baseDir, fallback.sourceInfo.path)) {
            throw new Error(COMMAND_DIAGNOSIS);
          }
          const path = realpathSync(fallback.sourceInfo.path);
          if (path !== realpathSync(expectedPath) ||
              !inside(path, canonicalRoot) ||
              ENVELOPE_UNSAFE.test(path)) throw new Error(COMMAND_DIAGNOSIS);
          if (!lstatSync(path).isFile()) throw new Error(COMMAND_DIAGNOSIS);
          const body = stripStartingFrontmatter(strictUtf8(path));
          if (body.includes("</skill>")) throw new Error(COMMAND_DIAGNOSIS);
          if (ENVELOPE_UNSAFE.test(dirname(path))) throw new Error(COMMAND_DIAGNOSIS);
          const expanded = nativeSkillExpansion(entry.name, path, body, args);
          const generated = await appendGeneratedContent?.(entry, args, context);
          const content = generated === undefined ? expanded : `${expanded}\n\n${generated}`;
          pi.sendUserMessage(content, { deliverAs: "followUp" });
        } catch {
          const status = "codeArbiter host: pi degraded - command surface; run /ca-doctor";
          onDegraded?.(status);
          context.ui.setStatus("codearbiter", status);
          context.ui.notify(COMMAND_DIAGNOSIS, "error");
        }
      },
    });
  }
}

export function assertCommandOwnership(
  pi: ParentPiPort,
  packageRoot: string,
  catalog: readonly CommandCatalogEntry[],
): Collision[] {
  const collisions: Collision[] = [];
  const canonicalRoot = realpathSync(packageRoot);
  const commands = pi.getCommands();
  for (const entry of catalog) {
    validatedEntry(entry);
    const alias = `ca-${entry.name}`;
    const expectedExtension = resolve(canonicalRoot, "extensions", "codearbiter.js");
    const exact = commands.filter((command) => command.name === alias);
    const suffixed = commands.filter((command) => command.name.startsWith(`${alias}:`));
    const validExact = exact.filter((command) =>
      command.source === "extension" && declaredPackageOwner(command, expectedExtension));
    if (validExact.length === 0) collisions.push({ command: alias, reason: "missing-alias" });
    if (exact.length > 1 || validExact.length > 1) collisions.push({ command: alias, reason: "duplicate-alias" });
    for (const command of [...exact, ...suffixed]) {
      if (command.source !== "extension" || !declaredPackageOwner(command, expectedExtension)) {
        collisions.push({ command: command.name, reason: "foreign-owner", owner: command.sourceInfo.path });
      }
    }
    for (const command of suffixed) {
      collisions.push({ command: command.name, reason: "suffixed-alias", owner: command.sourceInfo.path });
    }
    const fallbackName = `skill:ca-${entry.name}`;
    const fallbacks = commands.filter((command) => command.name === fallbackName);
    const expectedSkill = resolve(canonicalRoot, ...entry.skillPath.split("/"));
    const validFallbacks = fallbacks.filter((command) =>
      command.source === "skill" && declaredPackageOwner(command, expectedSkill));
    if (validFallbacks.length === 0) collisions.push({ command: fallbackName, reason: "missing-fallback" });
    if (fallbacks.length > 1) collisions.push({ command: fallbackName, reason: "duplicate-alias" });
    for (const command of fallbacks) {
      if (command.source !== "skill" || !declaredPackageOwner(command, expectedSkill)) {
        collisions.push({ command: fallbackName, reason: "foreign-owner", owner: command.sourceInfo.path });
      }
    }
    if (validExact.length === 1 && validFallbacks.length === 1 &&
        validExact[0].sourceInfo.source !== validFallbacks[0].sourceInfo.source) {
      collisions.push({
        command: fallbackName,
        reason: "foreign-owner",
        owner: validFallbacks[0].sourceInfo.path,
      });
    }
  }
  return collisions;
}
