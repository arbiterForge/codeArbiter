import { execFileSync } from "node:child_process";
import { readFileSync, realpathSync } from "node:fs";
import { isAbsolute, relative, resolve, sep } from "node:path";

const RELEASE = "preview-0.30";
const LESSON_ID = /^(F|P|U)\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$/;

export type AcademyLessonSource = {
  id: string;
  track: "foundations" | "practitioner" | "power-user";
  guide: string;
  actions: unknown;
};

export type AcademySource = {
  release: string;
  commit: string;
  lessons: AcademyLessonSource[];
};

type PublicationManifest = {
  release: unknown;
  available_labs: unknown;
  runnable_labs: unknown;
  guided_labs: unknown;
};

function isApprovedResourceHref(value: unknown): value is string {
  if (typeof value !== "string" || value.length === 0 || /\s/.test(value) || value.startsWith("//")) {
    return false;
  }
  try {
    return new URL(value, "https://academy.invalid/").protocol === "https:";
  } catch {
    return false;
  }
}

function validateActionResources(actions: unknown, lessonId: string): void {
  if (typeof actions !== "object" || actions === null || !Array.isArray((actions as { actions?: unknown }).actions)) {
    throw new Error(`Academy action manifest must contain actions for ${lessonId}`);
  }
  for (const action of (actions as { actions: unknown[] }).actions) {
    if (typeof action !== "object" || action === null) {
      throw new Error(`Academy action manifest contains an invalid action for ${lessonId}`);
    }
    const resources = (action as { resources?: unknown }).resources;
    if (resources === undefined) continue;
    if (!Array.isArray(resources)) {
      throw new Error(`Academy action resources must be an array for ${lessonId}`);
    }
    for (const resource of resources) {
      if (typeof resource !== "object" || resource === null || !isApprovedResourceHref((resource as { href?: unknown }).href)) {
        throw new Error(`Academy action resource URL must be HTTPS or relative for ${lessonId}`);
      }
    }
  }
}

function isWithin(root: string, target: string): boolean {
  const pathFromRoot = relative(root, target);
  return pathFromRoot !== "" && !pathFromRoot.startsWith(`..${sep}`) && pathFromRoot !== ".." && !isAbsolute(pathFromRoot);
}

function sourcePath(sourceRoot: string, ...parts: string[]): string {
  const candidate = resolve(sourceRoot, ...parts);
  const resolved = realpathSync(candidate);
  if (!isWithin(sourceRoot, resolved)) {
    throw new Error(`Academy source path must remain beneath the pinned submodule: ${parts.join("/")}`);
  }
  return resolved;
}

function parseJson(path: string): unknown {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new Error(`Academy source JSON is invalid: ${path}`, { cause: error });
  }
}

function stringArray(value: unknown, field: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`Academy public inventories require a string array for ${field}`);
  }
  return value;
}

function sameIds(expected: string[], actual: string[]): boolean {
  return expected.length === actual.length && expected.every((id, index) => id === actual[index]);
}

function trackFor(id: string): AcademyLessonSource["track"] {
  if (!LESSON_ID.test(id)) {
    throw new Error(`Academy source path rejected an invalid lesson ID: ${id}`);
  }
  if (id.startsWith("F")) return "foundations";
  if (id.startsWith("P")) return "practitioner";
  return "power-user";
}

export function loadAcademySource(root: string): AcademySource {
  const sourceRoot = realpathSync(resolve(root, "academy-source"));
  const manifestPath = sourcePath(sourceRoot, "academy", "publication", `${RELEASE}.json`);
  const manifest = parseJson(manifestPath) as PublicationManifest;
  const availableLabs = stringArray(manifest.available_labs, "available_labs");
  const runnableLabs = stringArray(manifest.runnable_labs, "runnable_labs");
  const guidedLabs = stringArray(manifest.guided_labs, "guided_labs");

  if (!sameIds(availableLabs, runnableLabs) || !sameIds(availableLabs, guidedLabs)) {
    throw new Error("Academy public inventories must contain the same ordered lesson IDs");
  }
  if (manifest.release !== RELEASE) {
    throw new Error(`Academy source manifest must declare ${RELEASE}`);
  }

  const lessons = availableLabs.map((id) => {
    const track = trackFor(id);
    const actions = parseJson(sourcePath(sourceRoot, "academy", "actions", `${id}.json`));
    validateActionResources(actions, id);
    return {
      id,
      track,
      guide: readFileSync(sourcePath(sourceRoot, "academy", "tracks", track, `${id}.md`), "utf8"),
      actions,
    };
  });

  return {
    release: RELEASE,
    commit: execFileSync("git", ["-C", sourceRoot, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    lessons,
  };
}
