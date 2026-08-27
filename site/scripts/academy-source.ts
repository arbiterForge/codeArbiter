import { execFileSync } from "node:child_process";
import { readFileSync, realpathSync } from "node:fs";
import { isAbsolute, relative, resolve, sep } from "node:path";

const RELEASE = "preview-0.30";
const LESSON_ID = /^(F|P|U)\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$/;
const HOME_SETUP_ANCHOR = "complete-these-five-setup-steps-before-f01";
const HOME_SETUP_HEADING = "Complete these five setup steps before F01";
const HOME_STEP = /^(\d+)\. \[([^\]]+)\]\(#([a-z0-9]+(?:-[a-z0-9]+)*)\)\.$/;
const NUMBERED_ITEM = /^\d+\.\s/;
const ACTION_ACTORS = ["learner", "academy", "agent"] as const;
const ACTION_SURFACES = ["browser", "native-terminal", "academy-console", "active-harness"] as const;
const VARIANT_SURFACES = ["browser", "native-terminal", "harness", "academy-console"] as const;
const OPERATING_SYSTEMS = ["all", "windows", "macos", "linux"] as const;
const HOSTS = ["none", "claude-code", "codex", "pi"] as const;
const LANGUAGES = ["none", "powershell", "sh", "text", "codearbiter"] as const;

export type AcademyLessonSource = {
  id: string;
  track: "foundations" | "practitioner" | "power-user";
  guide: string;
  actions: unknown;
};

export type AcademyHomeStepSource = {
  title: string;
  anchor: string;
  action: AcademyHomeActionSource;
};

export type AcademyHomeActionSource = {
  id: string;
  sequence: number;
  title: string;
  actor: "learner" | "academy" | "agent";
  surface: "browser" | "native-terminal" | "academy-console" | "active-harness" | null;
  instruction: string;
  rationale: string | null;
  resources: Array<{ label: string; href: string }>;
  variants: AcademyCommandVariantSource[];
  expected_result: string;
  recovery: string;
  evidence: string | null;
};

export type AcademyCommandVariantSource = {
  id: string;
  surface: typeof VARIANT_SURFACES[number];
  operating_system: typeof OPERATING_SYSTEMS[number];
  host: typeof HOSTS[number];
  language: typeof LANGUAGES[number];
  command: string;
  copy: boolean;
};

type AcademyActionManifestSource = {
  schema_version: 1;
  lesson_contract_version: 1;
  document_id: string;
  actions: AcademyHomeActionSource[];
};

export type AcademyHomeSource = {
  title: string;
  anchor: typeof HOME_SETUP_ANCHOR;
  steps: AcademyHomeStepSource[];
};

export type AcademySource = {
  release: string;
  commit: string;
  home: AcademyHomeSource;
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isOneOf<T extends string>(value: unknown, allowed: readonly T[]): value is T {
  return typeof value === "string" && allowed.some((candidate) => candidate === value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function validateActionManifest(actions: unknown, lessonId: string): asserts actions is AcademyActionManifestSource {
  if (!isRecord(actions) || actions.schema_version !== 1 || actions.lesson_contract_version !== 1 ||
      actions.document_id !== lessonId || !Array.isArray(actions.actions)) {
    throw new Error(`Academy action manifest must contain actions for ${lessonId}`);
  }
  for (const action of actions.actions) {
    if (!isRecord(action) || typeof action.id !== "string" || !Number.isInteger(action.sequence) ||
        typeof action.title !== "string" || !isOneOf(action.actor, ACTION_ACTORS) ||
        (action.surface !== null && !isOneOf(action.surface, ACTION_SURFACES)) ||
        typeof action.instruction !== "string" || !isNullableString(action.rationale) ||
        !Array.isArray(action.resources) || !Array.isArray(action.variants) ||
        typeof action.expected_result !== "string" || typeof action.recovery !== "string" ||
        !isNullableString(action.evidence)) {
      throw new Error(`Academy action manifest contains an invalid action for ${lessonId}`);
    }
    for (const resource of action.resources) {
      if (!isRecord(resource) || typeof resource.label !== "string" || !isApprovedResourceHref(resource.href)) {
        throw new Error(`Academy action resource URL must be HTTPS or relative for ${lessonId}`);
      }
    }
    for (const variant of action.variants) {
      if (!isRecord(variant) || typeof variant.id !== "string" ||
          !isOneOf(variant.surface, VARIANT_SURFACES) ||
          !isOneOf(variant.operating_system, OPERATING_SYSTEMS) ||
          !isOneOf(variant.host, HOSTS) || !isOneOf(variant.language, LANGUAGES) ||
          typeof variant.command !== "string" || typeof variant.copy !== "boolean") {
        throw new Error(`Academy action manifest contains an invalid command variant for ${lessonId}`);
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

function loadHomeActions(sourceRoot: string): Map<string, AcademyHomeActionSource> {
  let manifest: unknown;
  try {
    manifest = parseJson(sourcePath(sourceRoot, "academy", "actions", "home.json"));
  } catch (error) {
    throw new Error("Academy Home action manifest is required", { cause: error });
  }
  validateActionManifest(manifest, "home");
  const actions = new Map<string, AcademyHomeActionSource>();
  for (const action of manifest.actions) {
    if (actions.has(action.id)) {
      throw new Error(`Academy Home action manifest repeats ${action.id}`);
    }
    actions.set(action.id, action);
  }
  return actions;
}

function loadHomeGuide(sourceRoot: string): AcademyHomeSource {
  let guide: string;
  try {
    guide = readFileSync(sourcePath(sourceRoot, "academy", "guides", "home.md"), "utf8");
  } catch (error) {
    throw new Error("Academy Home guide is required", { cause: error });
  }

  const lines = guide.split(/\r?\n/);
  const title = lines[0]?.match(/^# (.+)$/)?.[1];
  const setupHeading = lines.findIndex((line) => line === `## ${HOME_SETUP_HEADING}`);
  if (!title || setupHeading === -1) {
    throw new Error("Academy Home guide has an invalid setup contract");
  }

  const setupLinks: Array<{ title: string; anchor: string }> = [];
  const setupLines = lines.slice(setupHeading + 1);
  for (const line of setupLines) {
    if (HOME_STEP.test(line)) break;
    if (NUMBERED_ITEM.test(line)) {
      throw new Error("Academy Home guide setup steps must be valid Markdown links");
    }
  }
  const firstStep = setupLines.findIndex((line) => HOME_STEP.test(line));
  if (firstStep === -1) {
    throw new Error("Academy Home guide must contain five setup steps");
  }
  for (const line of setupLines.slice(firstStep)) {
    const match = line.match(HOME_STEP);
    if (!match) break;
    if (Number(match[1]) !== setupLinks.length + 1) {
      throw new Error("Academy Home guide setup steps must be ordered");
    }
    setupLinks.push({ title: match[2], anchor: match[3] });
  }
  if (setupLinks.length !== 5) {
    throw new Error("Academy Home guide must contain five setup steps");
  }

  const actions = loadHomeActions(sourceRoot);
  const steps = setupLinks.map((step, index) => {
    const heading = lines.findIndex((line, lineIndex) => lineIndex > setupHeading && line === `## ${step.title}`);
    if (heading === -1) {
      throw new Error(`Academy Home guide is missing the ${step.title} section`);
    }
    const nextHeading = lines.findIndex((line, lineIndex) => lineIndex > heading && line.startsWith("## "));
    const section = lines.slice(heading + 1, nextHeading === -1 ? undefined : nextHeading);
    const actionIds = section.flatMap((line) => line.match(/^\{\{action:([A-Za-z0-9-]+)\}\}$/)?.slice(1) ?? []);
    if (actionIds.length !== 1) {
      throw new Error(`Academy Home guide section ${step.title} must contain one action`);
    }
    const action = actions.get(actionIds[0]);
    if (!action || action.sequence !== index + 1) {
      throw new Error(`Academy Home action for ${step.title} is missing or out of order`);
    }
    return { ...step, action };
  });
  if (actions.size !== steps.length) {
    throw new Error("Academy Home action manifest must match the five setup steps");
  }

  return { title, anchor: HOME_SETUP_ANCHOR, steps };
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
  const requiredTracks: Array<[AcademyLessonSource["track"], string]> = [
    ["foundations", "Foundation"],
    ["practitioner", "Practitioner"],
    ["power-user", "Power user"],
  ];
  const publishedTracks = new Set(availableLabs.map(trackFor));
  for (const [track, label] of requiredTracks) {
    if (!publishedTracks.has(track)) {
      throw new Error(`Academy public inventory requires a published ${label} lesson`);
    }
  }
  const home = loadHomeGuide(sourceRoot);

  const lessons = availableLabs.map((id) => {
    const track = trackFor(id);
    const actions = parseJson(sourcePath(sourceRoot, "academy", "actions", `${id}.json`));
    validateActionManifest(actions, id);
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
    home,
    lessons,
  };
}
