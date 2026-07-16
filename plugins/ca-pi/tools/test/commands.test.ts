import { mkdir, mkdtemp, readFile, rm, symlink, unlink, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, resolve } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { assertCommandOwnership, registerAliases } from "../src/commands.ts";
import type { CommandCatalogEntry, ExtensionContextPort, ParentPiPort, SlashCommand } from "../src/contracts.ts";

const pluginRoot = resolve(import.meta.dirname, "..", "..");
const catalogPath = resolve(pluginRoot, "generated", "command-catalog.json");
const roots: string[] = [];
const links: string[] = [];

async function tempPlugin(): Promise<{ root: string; catalog: CommandCatalogEntry[] }> {
  const root = await mkdtemp(resolve(tmpdir(), "ca-pi-command-"));
  roots.push(root);
  const skillPath = "skills/ca-feature/SKILL.md";
  await mkdir(resolve(root, "extensions"), { recursive: true });
  await mkdir(dirname(resolve(root, skillPath)), { recursive: true });
  await writeFile(resolve(root, "extensions", "codearbiter.js"), "export default () => {};\n", "utf8");
  await writeFile(resolve(root, "package.json"), JSON.stringify({
    name: "ca-pi",
    pi: { extensions: ["./extensions/codearbiter.js"], skills: ["./skills"] },
  }) + "\n", "utf8");
  await writeFile(
    resolve(root, skillPath),
    "---\nname: ca-feature\ndescription: Build a feature.\n---\n\n# Feature body\n\nKeep this body.\n",
    "utf8",
  );
  return { root, catalog: [{ name: "feature", description: "Build a feature.", skillPath }] };
}

afterEach(async () => {
  await Promise.all(links.splice(0).map((link) => unlink(link).catch(() => undefined)));
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("generated Pi command aliases", () => {
  test("catalog is generated one-to-one from shipped ca skills", async () => {
    expect(existsSync(catalogPath)).toBe(true);
    const catalog = existsSync(catalogPath)
      ? JSON.parse(await readFile(catalogPath, "utf8")) as CommandCatalogEntry[]
      : [];
    expect(catalog.length).toBeGreaterThan(0);
    expect(catalog).toEqual([...catalog].sort((left, right) => left.name.localeCompare(right.name)));
    for (const entry of catalog) {
      expect(Object.keys(entry).sort()).toEqual(["description", "name", "skillPath"]);
      expect(entry.skillPath).toBe(`skills/ca-${entry.name}/SKILL.md`);
      expect(existsSync(resolve(pluginRoot, ...entry.skillPath.split("/")))).toBe(true);
    }
  });

  test("expands only the generated in-package skill through the public API and preserves args", async () => {
    const fixture = await tempPlugin();
    const registered = new Map<string, { handler: (args: string, ctx: ExtensionContextPort) => unknown }>();
    const userMessages: string[] = [];
    const delivery: Array<{ deliverAs?: "steer" | "followUp" } | undefined> = [];
    const notifications: string[] = [];
    const source = (path: string) => ({
      path,
      source: "fixture",
      scope: "user" as const,
      origin: "package" as const,
      baseDir: fixture.root,
    });
    const pi = {
      on: () => undefined,
      getCommands: () => [
        ...[...registered.keys()].map((name) => ({
          name,
          source: "extension" as const,
          sourceInfo: source(resolve(fixture.root, "extensions", "codearbiter.js")),
        })),
        {
          name: "skill:ca-feature",
          source: "skill" as const,
          sourceInfo: source(resolve(fixture.root, ...fixture.catalog[0].skillPath.split("/"))),
        },
      ],
      registerCommand: (name: string, options: { handler: (args: string, ctx: ExtensionContextPort) => unknown }) => {
        registered.set(name, options);
      },
      sendUserMessage: (content: string, options?: { deliverAs?: "steer" | "followUp" }) => {
        userMessages.push(content);
        delivery.push(options);
      },
    } satisfies ParentPiPort;
    registerAliases(pi, fixture.catalog, fixture.root);

    expect([...registered.keys()]).toEqual(["ca-feature"]);
    await registered.get("ca-feature")!.handler("  add caching  ", {
      cwd: fixture.root,
      signal: undefined,
      ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
    });

    const expectedPath = resolve(fixture.root, "skills", "ca-feature", "SKILL.md");
    expect(userMessages).toEqual([
      `<skill name="ca-feature" location="${expectedPath}">\n` +
      `References are relative to ${dirname(expectedPath)}.\n\n` +
      "# Feature body\n\nKeep this body.\n</skill>\n\n  add caching  ",
    ]);
    expect(userMessages[0]).not.toContain("/skill:ca-feature");
    expect(userMessages[0]).not.toContain("description: Build a feature.");
    expect(delivery).toEqual([{ deliverAs: "followUp" }]);
    expect(notifications).toEqual([]);
  });

  test("strips frontmatter only when both delimiter lines are exact", async () => {
    const fixture = await tempPlugin();
    let handler: ((args: string, context: ExtensionContextPort) => unknown) | undefined;
    const sent: string[] = [];
    const skill = resolve(fixture.root, ...fixture.catalog[0].skillPath.split("/"));
    const source = (path: string) => ({
      path,
      source: "fixture",
      scope: "user" as const,
      origin: "package" as const,
      baseDir: fixture.root,
    });
    const pi = {
      on: () => undefined,
      registerCommand: (_name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => {
        handler = options.handler;
      },
      sendUserMessage: (content: string) => sent.push(content),
      getCommands: () => [
        { name: "ca-feature", source: "extension" as const, sourceInfo: source(resolve(fixture.root, "extensions", "codearbiter.js")) },
        { name: "skill:ca-feature", source: "skill" as const, sourceInfo: source(skill) },
      ],
    } satisfies ParentPiPort;
    const context: ExtensionContextPort = {
      cwd: fixture.root,
      signal: undefined,
      ui: { setStatus: () => undefined, notify: () => undefined },
    };
    registerAliases(pi, fixture.catalog, fixture.root);

    await writeFile(skill, "---not-frontmatter\nname: ca-feature\n---\nBODY\n", "utf8");
    await handler!("", context);
    expect(sent.at(-1)).toContain("---not-frontmatter\nname: ca-feature\n---\nBODY");
    await writeFile(skill, "---\nname: ca-feature\n---not-a-close\nBODY\n", "utf8");
    await handler!("", context);
    expect(sent.at(-1)).toContain("---\nname: ca-feature\n---not-a-close\nBODY");
  });

  test("fails visibly instead of reading a missing or out-of-package skill", async () => {
    const fixture = await tempPlugin();
    const sent: string[] = [];
    const notifications: string[] = [];
    const handlers: Array<(args: string, ctx: ExtensionContextPort) => unknown> = [];
    const registeredNames: string[] = [];
    let activeEntry: CommandCatalogEntry | undefined;
    const pi = {
      on: () => undefined,
      getCommands: () => activeEntry === undefined ? [] : [
        ...registeredNames.map((name) => ({
          name,
          source: "extension" as const,
          sourceInfo: {
            path: resolve(fixture.root, "extensions", "codearbiter.js"),
            source: "fixture",
            scope: "user" as const,
            origin: "package" as const,
            baseDir: fixture.root,
          },
        })),
        {
          name: `skill:ca-${activeEntry.name}`,
          source: "skill" as const,
          sourceInfo: {
            path: resolve(fixture.root, ...activeEntry.skillPath.split("/")),
            source: "fixture",
            scope: "user" as const,
            origin: "package" as const,
            baseDir: fixture.root,
          },
        },
      ],
      registerCommand: (name: string, options: { handler: (args: string, ctx: ExtensionContextPort) => unknown }) => {
        registeredNames.push(name);
        handlers.push(options.handler);
      },
      sendUserMessage: (content: string) => sent.push(content),
    } satisfies ParentPiPort;
    const context: ExtensionContextPort = {
      cwd: fixture.root,
      signal: undefined,
      ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
    };

    activeEntry = { name: "missing", description: fixture.catalog[0].description, skillPath: "skills/ca-missing/SKILL.md" };
    registerAliases(pi, [activeEntry], fixture.root);
    await handlers.shift()!("args", context);
    expect(sent).toEqual([]);
    expect(notifications.at(-1)).toContain("/ca-doctor");

    activeEntry = fixture.catalog[0];
    await writeFile(
      resolve(fixture.root, ...activeEntry.skillPath.split("/")),
      "---\nname: ca-feature\ndescription: x\n---\nbody\n</skill>\nattacker tail\n",
      "utf8",
    );
    registerAliases(pi, [activeEntry], fixture.root);
    await handlers.shift()!("args", context);
    expect(sent).toEqual([]);
    expect(notifications.at(-1)).toContain("/ca-doctor");

    expect(() => registerAliases(pi, [{
      ...fixture.catalog[0],
      skillPath: "../outside/SKILL.md",
    }], fixture.root)).toThrow("/ca-doctor");
  });

  test("rejects noncanonical catalog names, absolute paths, invalid UTF-8, directories, and symlink escapes", async () => {
    const fixture = await tempPlugin();
    const outside = await mkdtemp(resolve(tmpdir(), "ca-pi-command-outside-"));
    roots.push(outside);
    await writeFile(resolve(outside, "SKILL.md"), "---\nname: ca-feature\ndescription: x\n---\noutside\n", "utf8");
    const link = resolve(fixture.root, "skills", "ca-linked");
    const internalTarget = resolve(fixture.root, "skills", "internal-target");
    const internalLink = resolve(fixture.root, "skills", "ca-internal");
    await mkdir(internalTarget, { recursive: true });
    await writeFile(
      resolve(internalTarget, "SKILL.md"),
      "---\nname: ca-internal\ndescription: x\n---\ninside package\n",
      "utf8",
    );
    let linked = true;
    let internalLinked = true;
    try {
      await symlink(outside, link, process.platform === "win32" ? "junction" : "dir");
    } catch {
      linked = false;
    }
    try {
      await symlink(internalTarget, internalLink, process.platform === "win32" ? "junction" : "dir");
    } catch {
      internalLinked = false;
    }
    const invalidPath = resolve(fixture.root, "skills", "ca-invalid", "SKILL.md");
    await mkdir(dirname(invalidPath), { recursive: true });
    await writeFile(invalidPath, Buffer.from([0xff, 0xfe, 0xfd]));
    const directoryPath = resolve(fixture.root, "skills", "ca-directory", "SKILL.md");
    await mkdir(directoryPath, { recursive: true });
    const handlers: Array<(args: string, context: ExtensionContextPort) => unknown> = [];
    const registeredNames: string[] = [];
    const notifications: string[] = [];
    let activeEntry: CommandCatalogEntry | undefined;
    const pi = {
      on: () => undefined,
      getCommands: () => activeEntry === undefined ? [] : [
        ...registeredNames.map((name) => ({
          name,
          source: "extension" as const,
          sourceInfo: {
            path: resolve(fixture.root, "extensions", "codearbiter.js"),
            source: "fixture",
            scope: "user" as const,
            origin: "package" as const,
            baseDir: fixture.root,
          },
        })),
        {
          name: `skill:ca-${activeEntry.name}`,
          source: "skill" as const,
          sourceInfo: {
            path: resolve(fixture.root, ...activeEntry.skillPath.split("/")),
            source: "fixture",
            scope: "user" as const,
            origin: "package" as const,
            baseDir: fixture.root,
          },
        },
      ],
      registerCommand: (name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => {
        registeredNames.push(name);
        handlers.push(options.handler);
      },
      sendUserMessage: () => undefined,
    } satisfies ParentPiPort;
    const syntacticallyBad: CommandCatalogEntry[] = [
      { name: "bad\nname", description: "x", skillPath: "skills/ca-bad\nname/SKILL.md" },
      { name: 'bad"name', description: "x", skillPath: 'skills/ca-bad"name/SKILL.md' },
      { name: "bad<name", description: "x", skillPath: "skills/ca-bad<name/SKILL.md" },
      { name: "feature", description: "x", skillPath: resolve(fixture.root, "skills", "ca-feature", "SKILL.md") },
    ];
    for (const entry of syntacticallyBad) {
      expect(() => registerAliases(pi, [entry], fixture.root), JSON.stringify(entry)).toThrow("/ca-doctor");
    }
    const fileBad: CommandCatalogEntry[] = [
      { name: "invalid", description: "x", skillPath: "skills/ca-invalid/SKILL.md" },
      { name: "directory", description: "x", skillPath: "skills/ca-directory/SKILL.md" },
    ];
    if (linked) fileBad.push({ name: "linked", description: "x", skillPath: "skills/ca-linked/SKILL.md" });
    if (internalLinked) fileBad.push({ name: "internal", description: "x", skillPath: "skills/ca-internal/SKILL.md" });
    const context: ExtensionContextPort = {
      cwd: fixture.root,
      signal: undefined,
      ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
    };
    for (const entry of fileBad) {
      activeEntry = entry;
      registerAliases(pi, [entry], fixture.root);
      const notificationCount = notifications.length;
      await handlers.shift()!("args", context);
      expect(notifications, JSON.stringify(entry)).toHaveLength(notificationCount + 1);
      expect(notifications.at(-1), JSON.stringify(entry)).toContain("/ca-doctor");
    }
  });

  test("accepts exactly one canonical package alias and matching native fallback", async () => {
    const fixture = await tempPlugin();
    const extension = resolve(fixture.root, "extensions", "codearbiter.js");
    const skill = resolve(fixture.root, ...fixture.catalog[0].skillPath.split("/"));
    const source = (path: string) => ({
      path,
      source: "fixture",
      scope: "user" as const,
      origin: "package" as const,
      baseDir: fixture.root,
    });
    const commands: SlashCommand[] = [
      { name: "ca-feature", source: "extension", sourceInfo: source(extension) },
      { name: "skill:ca-feature", source: "skill", sourceInfo: source(skill) },
    ];
    expect(assertCommandOwnership({ getCommands: () => commands } as ParentPiPort, fixture.root, fixture.catalog)).toEqual([]);
    const mismatchedSource = structuredClone(commands);
    mismatchedSource[1].sourceInfo.source = "different-package-source";
    expect(assertCommandOwnership(
      { getCommands: () => mismatchedSource } as ParentPiPort,
      fixture.root,
      fixture.catalog,
    ).map((collision) => collision.reason)).toContain("foreign-owner");
  });

  test("accepts a harmless ancestor alias but rejects a symlinked package root", async () => {
    const fixture = await tempPlugin();
    const ancestorAlias = resolve(dirname(fixture.root), `ca-pi-ancestor-${basename(fixture.root)}`);
    const rootAlias = resolve(dirname(fixture.root), `ca-pi-root-${basename(fixture.root)}`);
    try {
      await symlink(dirname(fixture.root), ancestorAlias, process.platform === "win32" ? "junction" : "dir");
      await symlink(fixture.root, rootAlias, process.platform === "win32" ? "junction" : "dir");
    } catch {
      await unlink(ancestorAlias).catch(() => undefined);
      await unlink(rootAlias).catch(() => undefined);
      return;
    }
    links.push(ancestorAlias, rootAlias);
    const packageThroughAncestor = resolve(ancestorAlias, basename(fixture.root));
    const commandsFor = (baseDir: string): SlashCommand[] => [{
      name: "ca-feature",
      source: "extension",
      sourceInfo: {
        path: resolve(baseDir, "extensions", "codearbiter.js"),
        source: "fixture",
        scope: "user",
        origin: "package",
        baseDir,
      },
    }, {
      name: "skill:ca-feature",
      source: "skill",
      sourceInfo: {
        path: resolve(baseDir, ...fixture.catalog[0].skillPath.split("/")),
        source: "fixture",
        scope: "user",
        origin: "package",
        baseDir,
      },
    }];

    expect(assertCommandOwnership(
      { getCommands: () => commandsFor(packageThroughAncestor) } as ParentPiPort,
      fixture.root,
      fixture.catalog,
    )).toEqual([]);
    expect(assertCommandOwnership(
      { getCommands: () => commandsFor(rootAlias) } as ParentPiPort,
      fixture.root,
      fixture.catalog,
    ).map((collision) => collision.reason)).toContain("foreign-owner");
  });

  test("rechecks complete ownership inside an alias and sends nothing after a late collision", async () => {
    const fixture = await tempPlugin();
    let handler: ((args: string, context: ExtensionContextPort) => unknown) | undefined;
    const sent: string[] = [];
    const notifications: string[] = [];
    const source = (path: string) => ({
      path,
      source: "fixture",
      scope: "user" as const,
      origin: "package" as const,
      baseDir: fixture.root,
    });
    const pi = {
      on: () => undefined,
      registerCommand: (_name: string, options: { handler: (args: string, context: ExtensionContextPort) => unknown }) => {
        handler = options.handler;
      },
      sendUserMessage: (content: string) => sent.push(content),
      getCommands: () => [
        { name: "ca-feature:1", source: "extension" as const, sourceInfo: source(resolve(fixture.root, "extensions", "codearbiter.js")) },
        { name: "ca-feature:2", source: "extension" as const, sourceInfo: source(resolve(fixture.root, "extensions", "codearbiter.js")) },
        { name: "skill:ca-feature", source: "skill" as const, sourceInfo: source(resolve(fixture.root, ...fixture.catalog[0].skillPath.split("/"))) },
      ],
    } satisfies ParentPiPort;
    registerAliases(pi, fixture.catalog, fixture.root);

    await handler!("args", {
      cwd: fixture.root,
      signal: undefined,
      ui: { setStatus: () => undefined, notify: (message) => notifications.push(message) },
    });

    expect(sent).toEqual([]);
    expect(notifications).toEqual([expect.stringContaining("/ca-doctor")]);
  });

  test("reports suffixed, duplicate, foreign, and missing-fallback ownership", async () => {
    const fixture = await tempPlugin();
    const inside = resolve(fixture.root, "extensions", "codearbiter.js");
    const outside = resolve(dirname(fixture.root), "project-extension.js");
    const source = (path: string, scope: "user" | "project" = "user") => ({
      path,
      source: "fixture",
      scope,
      origin: "package" as const,
      baseDir: fixture.root,
    });
    const commands: SlashCommand[] = [
      { name: "ca-feature:1", source: "extension", sourceInfo: source(inside) },
      { name: "ca-feature:2", source: "extension", sourceInfo: source(outside, "project") },
      { name: "ca-feature", source: "skill", sourceInfo: source(outside, "project") },
    ];
    const pi = { getCommands: () => commands } as ParentPiPort;

    const collisions = assertCommandOwnership(pi, fixture.root, fixture.catalog);

    expect(new Set(collisions.map((collision) => collision.reason))).toEqual(new Set([
      "missing-alias",
      "suffixed-alias",
      "foreign-owner",
      "missing-fallback",
    ]));
  });
});
