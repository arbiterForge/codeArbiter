/**
 * command-ownership.ts - who owns a Pi command, and does its backing file belong to this package?
 *
 * The ownership predicates here are the trust boundary for every codeArbiter command Pi exposes:
 * they decide whether a registered command really came from the installed `ca-pi` package, whether
 * its declared file is inside that package with no symlink component, and which collisions a
 * degraded surface must report. The command surface, the background-job controller, and the plan
 * controller all ask this module rather than each re-deriving ownership.
 */
import { lstatSync, readFileSync, realpathSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import type {
  Collision,
  CommandCatalogEntry,
  ParentPiPort,
  SlashCommand,
} from "./contracts.ts";
import { lexicallyInside } from "./path-boundary.ts";

export const COMMAND_DIAGNOSIS = "codeArbiter could not validate the Pi command surface; run /ca-doctor.";
const NAME = /^[a-z][a-z0-9-]*$/u;
export const ENVELOPE_UNSAFE = /[\n\r"<>]/u;

/** Walk up from this module to the installed `ca-pi` package root, failing closed at the top. */
export function pluginRootFromModule(): string {
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

/** A catalog entry may only name a lowercase alias and its own package-relative skill file. */
export function validatedEntry(entry: CommandCatalogEntry): void {
  if (!NAME.test(entry.name) || ENVELOPE_UNSAFE.test(entry.name)) throw new Error(COMMAND_DIAGNOSIS);
  if (entry.skillPath !== `skills/ca-${entry.name}/SKILL.md` || isAbsolute(entry.skillPath)) {
    throw new Error(COMMAND_DIAGNOSIS);
  }
  if (entry.skillPath.split("/").some((part) => part === "" || part === "." || part === "..")) {
    throw new Error(COMMAND_DIAGNOSIS);
  }
}

/** Read a file as strict UTF-8 so invalid bytes fail closed rather than becoming replacements. */
export function strictUtf8(path: string): string {
  const bytes = readFileSync(path);
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

/** True when `root`, or any component between it and `path`, is a symlink. */
export function hasSymlinkComponent(root: string, path: string): boolean {
  const lexicalRoot = resolve(root);
  const lexicalPath = resolve(path);
  if (!lexicallyInside(lexicalPath, lexicalRoot) || lstatSync(lexicalRoot).isSymbolicLink()) return true;
  const suffix = relative(lexicalRoot, lexicalPath);
  let cursor = lexicalRoot;
  for (const part of suffix.split(/[\\/]/u).filter(Boolean)) {
    cursor = resolve(cursor, part);
    if (lstatSync(cursor).isSymbolicLink()) return true;
  }
  return false;
}

/** True when the command's own source file is the expected package-declared file. */
export function declaredPackageOwner(command: SlashCommand, expectedPath: string): boolean {
  try {
    if (command.sourceInfo.origin !== "package" || command.sourceInfo.baseDir === undefined) return false;
    if (hasSymlinkComponent(command.sourceInfo.baseDir, command.sourceInfo.path)) return false;
    const canonicalPath = realpathSync(command.sourceInfo.path);
    const canonicalExpected = realpathSync(expectedPath);
    const canonicalBase = realpathSync(command.sourceInfo.baseDir);
    if (canonicalPath !== canonicalExpected || !lexicallyInside(canonicalPath, canonicalBase)) return false;
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
        : lexicallyInside(canonicalPath, realpathSync(target));
    });
  } catch {
    return false;
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

export function assertNativePlanCommandOwnership(
  pi: ParentPiPort,
  packageRoot: string,
): Collision[] {
  const canonicalRoot = realpathSync(packageRoot);
  const expectedExtension = resolve(canonicalRoot, "extensions", "codearbiter.js");
  const commands = pi.getCommands();
  const exact = commands.filter((command) => command.name === "ca-plan");
  const suffixed = commands.filter((command) => command.name.startsWith("ca-plan:"));
  const fallbacks = commands.filter((command) => command.name === "skill:ca-plan");
  const valid = exact.filter((command) => command.source === "extension"
    && declaredPackageOwner(command, expectedExtension));
  const collisions: Collision[] = [];
  if (valid.length === 0) collisions.push({ command: "ca-plan", reason: "missing-alias" });
  if (exact.length > 1 || valid.length > 1) collisions.push({ command: "ca-plan", reason: "duplicate-alias" });
  for (const command of [...exact, ...suffixed, ...fallbacks]) {
    const owned = command.name === "ca-plan" && command.source === "extension"
      && declaredPackageOwner(command, expectedExtension);
    if (!owned) collisions.push({ command: command.name, reason: "foreign-owner", owner: command.sourceInfo.path });
  }
  for (const command of suffixed) {
    collisions.push({ command: command.name, reason: "suffixed-alias", owner: command.sourceInfo.path });
  }
  return collisions;
}

export function assertNativeJobsCommandOwnership(
  pi: ParentPiPort,
  packageRoot: string,
): Collision[] {
  const canonicalRoot = realpathSync(packageRoot);
  const expectedExtension = resolve(canonicalRoot, "extensions", "codearbiter.js");
  const commands = pi.getCommands();
  const exact = commands.filter((command) => command.name === "ca-jobs");
  const related = commands.filter((command) => command.name.startsWith("ca-jobs:")
    || command.name === "skill:ca-jobs");
  const valid = exact.filter((command) => command.source === "extension"
    && declaredPackageOwner(command, expectedExtension));
  const collisions: Collision[] = [];
  if (valid.length === 0) collisions.push({ command: "ca-jobs", reason: "missing-alias" });
  if (exact.length > 1 || valid.length > 1) collisions.push({ command: "ca-jobs", reason: "duplicate-alias" });
  for (const command of [...exact, ...related]) {
    if (command.name !== "ca-jobs" || command.source !== "extension"
      || !declaredPackageOwner(command, expectedExtension)) {
      collisions.push({ command: command.name, reason: "foreign-owner", owner: command.sourceInfo.path });
    }
  }
  for (const command of related.filter((command) => command.name.startsWith("ca-jobs:"))) {
    collisions.push({ command: command.name, reason: "suffixed-alias", owner: command.sourceInfo.path });
  }
  return collisions;
}
