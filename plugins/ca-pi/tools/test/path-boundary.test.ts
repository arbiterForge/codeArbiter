import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import { realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import {
  canonicalPath,
  canonicallyInside,
  flavorForPlatform,
  lexicallyInside,
} from "../src/path-boundary.ts";
import type { PathFlavor } from "../src/path-boundary.ts";

const temporaryRoots: string[] = [];

async function temporaryRoot(): Promise<string> {
  const created = realpathSync(await mkdtemp(resolve(tmpdir(), "ca-pi-path-boundary-")));
  temporaryRoots.push(created);
  return created;
}

afterEach(async () => {
  while (temporaryRoots.length > 0) {
    await rm(temporaryRoots.pop()!, { recursive: true, force: true });
  }
});

interface LexicalCase {
  readonly name: string;
  readonly flavor: PathFlavor;
  readonly path: string;
  readonly root: string;
  readonly contained: boolean;
}

const LEXICAL_CASES: readonly LexicalCase[] = Object.freeze([
  { name: "posix equal paths are contained", flavor: "posix", path: "/a/b", root: "/a/b", contained: true },
  { name: "posix trailing separator is equal", flavor: "posix", path: "/a/b", root: "/a/b/", contained: true },
  { name: "posix child is contained", flavor: "posix", path: "/a/b/c", root: "/a/b", contained: true },
  { name: "posix deep child is contained", flavor: "posix", path: "/a/b/c/d/e", root: "/a/b", contained: true },
  { name: "posix filesystem root contains everything", flavor: "posix", path: "/a", root: "/", contained: true },
  { name: "posix sibling sharing a name prefix is not contained", flavor: "posix", path: "/a/bc", root: "/a/b", contained: false },
  { name: "posix parent is not contained by its child", flavor: "posix", path: "/a", root: "/a/b", contained: false },
  { name: "posix traversal escape is not contained", flavor: "posix", path: "/a/b/../../c", root: "/a/b", contained: false },
  { name: "posix embedded traversal that returns inside is contained", flavor: "posix", path: "/a/b/c/../d", root: "/a/b", contained: true },
  { name: "posix relative operands are compared relatively", flavor: "posix", path: "b/c", root: "b", contained: true },
  { name: "posix comparison is case sensitive", flavor: "posix", path: "/A/b", root: "/a", contained: false },
  { name: "win32 child is contained", flavor: "win32", path: "C:\\a\\b", root: "C:\\a", contained: true },
  { name: "win32 equal paths are contained", flavor: "win32", path: "C:\\a", root: "C:\\a", contained: true },
  { name: "win32 drive letter case is ignored", flavor: "win32", path: "c:\\a\\b", root: "C:\\a", contained: true },
  { name: "win32 segment case is ignored", flavor: "win32", path: "C:\\A\\B", root: "C:\\a", contained: true },
  { name: "win32 mixed separators are contained", flavor: "win32", path: "C:/a/b", root: "C:\\a", contained: true },
  { name: "win32 other drive is not contained", flavor: "win32", path: "D:\\a\\b", root: "C:\\a", contained: false },
  { name: "win32 sibling sharing a name prefix is not contained", flavor: "win32", path: "C:\\ab", root: "C:\\a", contained: false },
  { name: "win32 traversal escape is not contained", flavor: "win32", path: "C:\\a\\..\\b", root: "C:\\a", contained: false },
  { name: "win32 UNC child is contained", flavor: "win32", path: "\\\\server\\share\\a\\b", root: "\\\\server\\share\\a", contained: true },
  { name: "win32 other UNC share is not contained", flavor: "win32", path: "\\\\server\\other\\a", root: "\\\\server\\share\\a", contained: false },
]);

describe("Pi path boundary", () => {
  test.each(LEXICAL_CASES.map((entry) => [entry.name, entry] as const))(
    "lexical containment: %s",
    (_name, entry) => {
      expect(lexicallyInside(entry.path, entry.root, entry.flavor)).toBe(entry.contained);
    },
  );

  test("flavorForPlatform maps win32 to Windows semantics and every other platform to POSIX", () => {
    expect(flavorForPlatform("win32")).toBe("win32");
    for (const platform of ["linux", "darwin", "freebsd", "aix"] as const) {
      expect(flavorForPlatform(platform)).toBe("posix");
    }
  });

  test("the default flavor follows the host platform", () => {
    const host: PathFlavor = flavorForPlatform(process.platform);
    const cases: readonly (readonly [string, string])[] = Object.freeze([
      [resolve("/a/b/c"), resolve("/a/b")],
      [resolve("/a/bc"), resolve("/a/b")],
      [resolve("/a/b"), resolve("/a/b")],
    ]);
    for (const [path, root] of cases) {
      expect(lexicallyInside(path, root)).toBe(lexicallyInside(path, root, host));
    }
  });

  test("lexical containment never touches the filesystem", async () => {
    const root = await temporaryRoot();
    const missing = resolve(root, "absent", "child");
    expect(lexicallyInside(missing, root)).toBe(true);
    expect(lexicallyInside(resolve(root, "..", "elsewhere"), root)).toBe(false);
  });

  test("canonicalPath resolves real paths through the filesystem", async () => {
    const root = await temporaryRoot();
    const child = resolve(root, "child");
    await mkdir(child);
    expect(canonicalPath(resolve(root, ".", "child"))).toBe(realpathSync(child));
  });

  test("canonicalPath falls back to lexical resolution for absent paths", async () => {
    const root = await temporaryRoot();
    const missing = resolve(root, "absent");
    expect(canonicalPath(missing)).toBe(resolve(missing));
  });

  test("canonical containment normalizes both operands", async () => {
    const root = await temporaryRoot();
    const child = resolve(root, "child");
    await mkdir(child);
    expect(canonicallyInside(resolve(child, "..", "child"), root)).toBe(true);
    expect(canonicallyInside(root, root)).toBe(true);
  });

  test("canonical containment rejects an escaping sibling", async () => {
    const parent = await temporaryRoot();
    const root = resolve(parent, "root");
    const sibling = resolve(parent, "root-sibling");
    await mkdir(root);
    await mkdir(sibling);
    expect(canonicallyInside(sibling, root)).toBe(false);
  });

  test("canonical containment follows a symlink out of the root while lexical containment does not", async () => {
    const parent = await temporaryRoot();
    const root = resolve(parent, "root");
    const outside = resolve(parent, "outside");
    await mkdir(root);
    await mkdir(outside);
    await writeFile(resolve(outside, "target.txt"), "target", { encoding: "utf8" });
    const link = resolve(root, "link.txt");
    try {
      await symlink(resolve(outside, "target.txt"), link, "file");
    } catch {
      return; // Symlink creation is privileged on some Windows hosts.
    }
    expect(lexicallyInside(link, root)).toBe(true);
    expect(canonicallyInside(link, root)).toBe(false);
  });
});
