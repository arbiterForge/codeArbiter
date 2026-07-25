import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, test } from "vitest";

const sourceDirectory = resolve(import.meta.dirname, "..", "src");

/** The exact private containment predicate that used to be cloned across the Pi trust boundary. */
const CONTAINMENT_CLONE = /===\s*""\s*\|\|\s*\(!\s*[A-Za-z_$][\w$]*\.startsWith\("\.\."\)/u;

/** The command-surface cluster split out of the former 1,033-line commands.ts god module. */
const COMMAND_SURFACE_CLUSTER = Object.freeze([
  "commands.ts",
  "command-ownership.ts",
  "native-background.ts",
  "native-plan.ts",
  "session-identity.ts",
  "path-boundary.ts",
]);

/** The governance log a Pi producer may only reach through the shared hardened primitive. */
const AUDIT_SINK_TARGET = /gate-events\.log/u;

/** A filesystem append: a second, unhardened audit-sink implementation if it is not the owner. */
const DIRECT_APPEND = /\bappendFile\b/u;

const COMMAND_SURFACE_CEILING = 350;
const CLUSTER_CEILING = 450;

function sourceFiles(): readonly string[] {
  return readdirSync(sourceDirectory)
    .filter((name) => name.endsWith(".ts") && !name.endsWith(".d.ts"))
    .sort();
}

function sourceOf(name: string): string {
  return readFileSync(resolve(sourceDirectory, name), "utf8");
}

function lineCount(name: string): number {
  return sourceOf(name).replaceAll("\r\n", "\n").split("\n").length;
}

function importGraph(): ReadonlyMap<string, readonly string[]> {
  const graph = new Map<string, readonly string[]>();
  for (const name of sourceFiles()) {
    const edges = new Set<string>();
    for (const match of sourceOf(name).matchAll(/from\s+"\.\/([A-Za-z0-9._-]+\.ts)"/gu)) {
      edges.add(match[1]!);
    }
    graph.set(name, [...edges]);
  }
  return graph;
}

function importCycles(): readonly string[] {
  const graph = importGraph();
  const state = new Map<string, "open" | "done">();
  const cycles: string[] = [];
  const walk = (node: string, stack: readonly string[]): void => {
    if (state.get(node) === "done") return;
    if (state.get(node) === "open") {
      cycles.push([...stack.slice(stack.indexOf(node)), node].join(" -> "));
      return;
    }
    state.set(node, "open");
    for (const next of graph.get(node) ?? []) walk(next, [...stack, next]);
    state.set(node, "done");
  };
  for (const name of graph.keys()) walk(name, [name]);
  return cycles;
}

describe("Pi module structure", () => {
  test("path containment semantics have exactly one owner", () => {
    const owners = sourceFiles().filter((name) => CONTAINMENT_CLONE.test(sourceOf(name)));
    expect(owners).toEqual(["path-boundary.ts"]);
  });

  test("the path boundary module exports named lexical and canonical operations", async () => {
    const boundary = await import("../src/path-boundary.ts");
    for (const name of ["lexicallyInside", "canonicallyInside", "canonicalPath", "flavorForPlatform"]) {
      expect(typeof (boundary as Record<string, unknown>)[name]).toBe("function");
    }
  });

  test("gate-events audit appends have exactly one owner", () => {
    const owners = sourceFiles().filter((name) => AUDIT_SINK_TARGET.test(sourceOf(name)));
    expect(owners).toEqual(["audit-sink.ts"]);
  });

  test("no production module appends to the filesystem outside the audit sink", () => {
    const direct = sourceFiles()
      .filter((name) => name !== "audit-sink.ts" && DIRECT_APPEND.test(sourceOf(name)));
    expect(direct).toEqual([]);
  });

  test("the audit sink module exports the hardened primitive and its injectable seam", async () => {
    const sink = await import("../src/audit-sink.ts");
    for (const name of ["appendAuditLine", "appendAuditLineWithIo"]) {
      expect(typeof (sink as Record<string, unknown>)[name]).toBe("function");
    }
  });

  test("the command surface, ownership, jobs, and plan subsystems are separate modules", async () => {
    const ownership = await import("../src/command-ownership.ts");
    const background = await import("../src/native-background.ts");
    const plan = await import("../src/native-plan.ts");
    const commands = await import("../src/commands.ts");
    expect(typeof ownership.assertCommandOwnership).toBe("function");
    expect(typeof ownership.assertNativeJobsCommandOwnership).toBe("function");
    expect(typeof ownership.assertNativePlanCommandOwnership).toBe("function");
    expect(typeof background.createNativeBackgroundController).toBe("function");
    expect(typeof plan.createNativePlanController).toBe("function");
    expect(typeof commands.registerAliases).toBe("function");
  });

  test("the background and plan controllers are not implemented inside the command surface", () => {
    const commands = sourceOf("commands.ts");
    expect(commands).not.toContain("export function createNativeBackgroundController");
    expect(commands).not.toContain("export function createNativePlanController");
  });

  test("the command surface module is below the oversized-module threshold", () => {
    expect(lineCount("commands.ts")).toBeLessThanOrEqual(COMMAND_SURFACE_CEILING);
  });

  test("every command-surface cluster module stays below the cluster ceiling", () => {
    const oversized = COMMAND_SURFACE_CLUSTER
      .filter((name) => lineCount(name) > CLUSTER_CEILING);
    expect(oversized).toEqual([]);
  });

  test("the Pi source module graph has no import cycles", () => {
    expect(importCycles()).toEqual([]);
  });
});
