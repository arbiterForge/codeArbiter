/** roles.ts - codeArbiter's validated generated Pi child role catalog. */
import { readFile, realpath } from "node:fs/promises";
import { isAbsolute, relative, resolve } from "node:path";

export type RoleClassification = "author" | "reviewer";

export interface PiRole {
  name: string;
  classification: RoleClassification;
  charterPath: string;
  skillPaths: string[];
  tools: Array<"read" | "bash" | "edit" | "write">;
}

const ROLE_NAME = /^[a-z][a-z0-9-]{0,63}$/u;
const ALLOWED_TOOLS = new Set(["read", "bash", "edit", "write"]);

function inside(path: string, root: string): boolean {
  const suffix = relative(root, path);
  return suffix === "" || (!suffix.startsWith("..") && !isAbsolute(suffix));
}

function validRelativeResource(value: unknown, prefix: string): value is string {
  return typeof value === "string"
    && value.startsWith(prefix)
    && !isAbsolute(value)
    && !value.split(/[\\/]/u).includes("..");
}

function parseRole(value: unknown): PiRole {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("Generated Pi role catalog is invalid; run /ca-doctor.");
  const role = value as Record<string, unknown>;
  const keys = Object.keys(role).sort();
  if (JSON.stringify(keys) !== JSON.stringify(["charterPath", "classification", "name", "skillPaths", "tools"])) {
    throw new Error("Generated Pi role catalog is invalid; run /ca-doctor.");
  }
  if (
    typeof role.name !== "string" || !ROLE_NAME.test(role.name)
    || (role.classification !== "author" && role.classification !== "reviewer")
    || !validRelativeResource(role.charterPath, "agents/")
    || !Array.isArray(role.skillPaths) || role.skillPaths.some((item) => !validRelativeResource(item, "routines/"))
    || !Array.isArray(role.tools) || role.tools.length === 0
    || role.tools.some((item) => typeof item !== "string" || !ALLOWED_TOOLS.has(item))
    || new Set(role.tools).size !== role.tools.length
  ) throw new Error("Generated Pi role catalog is invalid; run /ca-doctor.");
  return Object.freeze({
    name: role.name,
    classification: role.classification,
    charterPath: role.charterPath,
    skillPaths: Object.freeze([...role.skillPaths]) as unknown as string[],
    tools: Object.freeze([...role.tools]) as unknown as PiRole["tools"],
  });
}

export async function loadRoleCatalog(packageRoot: string): Promise<ReadonlyMap<string, PiRole>> {
  const canonicalRoot = await realpath(packageRoot);
  const catalogPath = await realpath(resolve(canonicalRoot, "generated", "roles.json"));
  if (!inside(catalogPath, canonicalRoot)) throw new Error("Generated Pi role catalog escapes the package; run /ca-doctor.");
  const parsed = JSON.parse(await readFile(catalogPath, "utf8")) as unknown;
  if (!Array.isArray(parsed) || parsed.length === 0) throw new Error("Generated Pi role catalog is invalid; run /ca-doctor.");
  const catalog = new Map<string, PiRole>();
  for (const value of parsed) {
    const role = parseRole(value);
    if (catalog.has(role.name)) throw new Error("Generated Pi role catalog contains duplicate roles; run /ca-doctor.");
    catalog.set(role.name, role);
  }
  return catalog;
}
