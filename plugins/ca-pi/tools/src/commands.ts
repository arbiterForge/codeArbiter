/**
 * commands.ts - codeArbiter's generated Pi command surface.
 *
 * This module owns exactly one thing: registering the generated `/ca-*` aliases and expanding the
 * package-declared skill file behind each one into an owned envelope. Ownership predicates live in
 * command-ownership.ts, and the two lifecycle-bearing native surfaces live in native-background.ts
 * and native-plan.ts; they are re-exported below so the Pi command surface stays one import
 * boundary for consumers.
 */
import { lstatSync, realpathSync } from "node:fs";
import { dirname, resolve } from "node:path";

import type {
  CommandCatalogEntry,
  ExtensionContextPort,
  ParentPiPort,
  SlashCommand,
} from "./contracts.ts";
import {
  COMMAND_DIAGNOSIS,
  ENVELOPE_UNSAFE,
  assertCommandOwnership,
  declaredPackageOwner,
  hasSymlinkComponent,
  pluginRootFromModule,
  strictUtf8,
  validatedEntry,
} from "./command-ownership.ts";
import { lexicallyInside } from "./path-boundary.ts";

export {
  assertCommandOwnership,
  assertNativeJobsCommandOwnership,
  assertNativePlanCommandOwnership,
} from "./command-ownership.ts";
export { createNativeBackgroundController } from "./native-background.ts";
export type {
  BackgroundJobLaunchConfiguration,
  NativeBackgroundController,
  NativeBackgroundControllerOptions,
} from "./native-background.ts";
export { createNativePlanController } from "./native-plan.ts";
export type {
  NativePlanController,
  NativePlanControllerOptions,
} from "./native-plan.ts";

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
              !lexicallyInside(path, canonicalRoot) ||
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
