/** load-curated.ts — codeArbiter's curated-companion-file loader.
 *
 * Discovers and parses every curated framing file under
 * `site/src/curated/{commands,agents,skills}/<basename>.md`, keyed by the
 * plugin source file's basename (the same filename-stable discipline
 * `forge-status.ts` uses) — the skill "basename" is its containing
 * directory name, matching `deriveName`'s SKILL.md fallback.
 *
 * Enforces the divergence check both directions:
 *   - a curated file whose `entity` has no matching collected source is an
 *     orphan and THROWS (lists every orphan file found, not just the first);
 *   - two curated files declaring the same `entity` THROWS;
 *   - a collected source with no curated file is fine — the caller falls
 *     back to an uncurated (generated-only) page.
 *
 * When the caller supplies reader shapes (see `ReaderShape`), each curated file
 * of a shaped entity must carry its reader fields in top-level frontmatter and,
 * for workflow pages, a non-empty `Example` heading in the body. Every miss
 * across every file is reported in one error that names the file and the field.
 *
 * Whatever its shape, no curated file may keep a `When to reach for it` heading:
 * the `use_when` field replaces that section, so the two never sit side by side.
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { splitFrontmatter } from "./split-frontmatter";
import { parseFields } from "./parse-fields";
import { fencedLines, markdownHeadings } from "./markdown-fences";
import {
  READER_FIELD_SPEC,
  type CuratedDoc,
  type GateSpec,
  type ReaderFields,
  type ReaderShape,
  type SourceType,
} from "./types";

const TYPE_DIR_NAME: Record<SourceType, string> = {
  command: "commands",
  skill: "skills",
  agent: "agents",
};
const TYPES: SourceType[] = ["command", "skill", "agent"];

/** Strip a leading BOM and normalize CRLF to LF, matching generate.ts's read boundary. */
function normalize(raw: string): string {
  const noBom = raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw;
  return noBom.replace(/\r\n/g, "\n");
}

/**
 * Parse a `related:` frontmatter field.
 *
 * Accepted syntax: a single flow-style list on one line —
 * `related: [commit, skills/tdd]`. An empty `related: []` yields `[]`.
 * Absent field yields `undefined`. This is deliberately minimal (no
 * block-list form, no quoting) — refs are bare identifiers.
 */
function parseRelated(frontmatter: string): string[] | undefined {
  const match = frontmatter.match(/^related:\s*\[(.*)\]\s*$/m);
  if (!match) return undefined;
  const inner = match[1].trim();
  if (inner === "") return [];
  return inner
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function finalizeGate(partial: Partial<GateSpec>, filePath: string): GateSpec {
  if (!partial.gate || !partial.when || !partial.effect) {
    throw new Error(
      `Curated file ${filePath}: a "gates:" entry is missing gate/when/effect`,
    );
  }
  return { gate: partial.gate, when: partial.when, effect: partial.effect };
}

/**
 * Parse a `gates:` frontmatter field — a block list of `{gate, when, effect}` maps.
 *
 * Accepted syntax (a deliberately minimal, line-based YAML subset — no
 * external YAML dependency, consistent with the rest of the generator):
 *
 * ```yaml
 * gates:
 *   - gate: commit-gate
 *     when: staged changes exist
 *     effect: blocks commit until tests/lint/secrets scan pass
 *   - gate: another gate
 *     when: ...
 *     effect: ...
 * ```
 *
 * Each entry starts with a `- gate: <value>` line; the following `when:` and
 * `effect:` lines (any indentation, in either order) belong to that entry
 * until the next `- gate:` line or a line that dedents back to column 0
 * (the next top-level frontmatter key). No nested lists, no flow-style
 * `{...}` maps, no multi-line scalars.
 */
function parseGates(frontmatter: string, filePath: string): GateSpec[] | undefined {
  const lines = frontmatter.split("\n");
  const startIdx = lines.findIndex((l) => /^gates:\s*$/.test(l));
  if (startIdx === -1) return undefined;

  const gates: GateSpec[] = [];
  let current: Partial<GateSpec> | null = null;

  for (let i = startIdx + 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === "") continue;
    // A line starting at column 0 is the next top-level frontmatter key.
    if (!/^\s/.test(line)) break;

    const item = line.match(/^\s*-\s*gate:\s*(.+)$/);
    if (item) {
      if (current) gates.push(finalizeGate(current, filePath));
      current = { gate: item[1].trim() };
      continue;
    }
    const kv = line.match(/^\s*(when|effect):\s*(.*)$/);
    if (kv && current) {
      current[kv[1] as "when" | "effect"] = kv[2].trim();
    }
  }
  if (current) gates.push(finalizeGate(current, filePath));
  return gates;
}

const READER_KEYS: ReadonlyArray<keyof ReaderFields> = [
  "use_when",
  "avoid_when",
  "asks",
  "produces",
  "runs_inside",
];

/**
 * Parse the reader fields: top-level `key: value` lines only, one line each.
 *
 * Only column-0 keys count, so an indented `use_when:` inside a `gates:` entry
 * is never read as a field. One pair of matching quotes is stripped. A key
 * written with no value is kept as an empty string so the validator can say
 * "empty" rather than "missing". A YAML block scalar (`|`, `>`) is rejected:
 * this subset reads single lines and would otherwise keep the indicator as text.
 */
function parseReaderFields(frontmatter: string, filePath: string): ReaderFields | undefined {
  const reader: ReaderFields = {};
  for (const key of READER_KEYS) {
    const match = frontmatter.match(new RegExp(`^${key}:[ \t]*(.*?)[ \t]*$`, "m"));
    if (!match) continue;
    let value = match[1];
    if (
      value.length >= 2 &&
      ((value.startsWith("'") && value.endsWith("'")) ||
        (value.startsWith('"') && value.endsWith('"')))
    ) {
      value = value.slice(1, -1).trim();
    }
    if (/^[|>][+-]?$/.test(value)) {
      throw new Error(
        `Curated file ${filePath}: field "${key}" must be a single line, not a YAML block scalar`,
      );
    }
    reader[key] = value;
  }
  return Object.keys(reader).length > 0 ? reader : undefined;
}

/** Whether `body` has a non-empty heading named exactly Example (level 2 or deeper, outside code fences). */
function exampleProblem(body: string, filePath: string): string | undefined {
  const lines = body.split("\n");
  const fenced = fencedLines(lines);
  const headings = markdownHeadings(body);
  const headingLines = new Set(headings.map((heading) => heading.line));
  const examples = headings.filter(
    (heading) => heading.level >= 2 && heading.text.toLowerCase() === "example",
  );
  if (examples.length === 0) {
    return `${filePath}: missing an "Example" heading in the body`;
  }
  const hasContent = examples.some((example) => {
    const next = headings.find((h) => h.line > example.line && h.level <= example.level);
    const end = next ? next.line : lines.length;
    for (let i = example.line + 1; i < end; i++) {
      if (lines[i].trim() === "") continue;
      if (!fenced[i] && headingLines.has(i)) continue;
      return true;
    }
    return false;
  });
  return hasContent
    ? undefined
    : `${filePath}: "Example" heading has no content before the next heading`;
}

/** The heading `use_when` replaced; a curated file keeps the field or the section, never both. */
const RETIRED_SECTION = "when to reach for it";

/** Whether the body still carries the retired section heading (outside code fences, any level). */
function retiredSectionProblem(body: string, filePath: string): string | undefined {
  const retired = markdownHeadings(body).some(
    (heading) => heading.text.toLowerCase() === RETIRED_SECTION,
  );
  return retired
    ? `${filePath}: the "When to reach for it" section is replaced by the "use_when" field; remove the heading and move any remaining substance elsewhere`
    : undefined;
}

/** Every reader-field problem of one curated file, each naming the file and the field. */
function readerProblems(doc: CuratedDoc, shape: ReaderShape, filePath: string): string[] {
  const problems: string[] = [];
  for (const { key } of READER_FIELD_SPEC[shape]) {
    const value = doc.reader?.[key];
    if (value === undefined) {
      problems.push(`${filePath}: missing required field "${key}"`);
    } else if (value === "") {
      problems.push(`${filePath}: field "${key}" is empty`);
    }
  }
  if (shape === "workflow") {
    const example = exampleProblem(doc.body, filePath);
    if (example) problems.push(example);
  }
  return problems;
}

function parseCurated(raw: string, filePath: string): CuratedDoc {
  const { frontmatter, body } = splitFrontmatter(normalize(raw));
  if (frontmatter === null) {
    throw new Error(`Curated file ${filePath} has no frontmatter block`);
  }
  const fields = parseFields(frontmatter);
  const entity = fields.entity;
  if (!entity) {
    throw new Error(`Curated file ${filePath} is missing the required "entity" field`);
  }
  return {
    entity,
    related: parseRelated(frontmatter),
    gates: parseGates(frontmatter, filePath),
    reader: parseReaderFields(frontmatter, filePath),
    body: body.trim(),
  };
}

/**
 * Discover and parse every curated companion file under `curatedDir`.
 *
 * `collectedKeys` is the set of `<type-dir>/<basename>` keys for every
 * collected plugin source (built by `generate.ts` from the same collection
 * pass, so this check reads exactly the sources a given `npm run gen`
 * invocation saw). Returns a Map keyed by `entity` (`<type-dir>/<basename>`).
 * A missing `curatedDir` returns an empty Map (curated content is entirely
 * optional).
 *
 * `readerShapes` maps an entity to the reader fields it must carry; an entity
 * absent from the map (or no map at all) is not validated. `generate.ts` derives
 * the map from the command catalog and the command/skill pairs.
 */
export function loadCurated(
  curatedDir: string,
  collectedKeys: Set<string>,
  readerShapes?: ReadonlyMap<string, ReaderShape>,
): Map<string, CuratedDoc> {
  const result = new Map<string, CuratedDoc>();
  if (!existsSync(curatedDir)) return result;

  const orphans: string[] = [];
  const readerIssues: string[] = [];
  const seenBy = new Map<string, string>();

  for (const type of TYPES) {
    const dirName = TYPE_DIR_NAME[type];
    const dir = join(curatedDir, dirName);
    if (!existsSync(dir)) continue;

    for (const entry of readdirSync(dir)) {
      if (!entry.endsWith(".md")) continue;
      const filePath = join(dir, entry);
      const raw = readFileSync(filePath, "utf-8");
      const doc = parseCurated(raw, filePath);

      const existing = seenBy.get(doc.entity);
      if (existing) {
        throw new Error(
          `Duplicate curated file for entity "${doc.entity}": ${existing} and ${filePath}`,
        );
      }
      seenBy.set(doc.entity, filePath);

      if (!collectedKeys.has(doc.entity)) {
        orphans.push(filePath);
        continue;
      }
      const shape = readerShapes?.get(doc.entity);
      if (shape) readerIssues.push(...readerProblems(doc, shape, filePath));
      const retired = retiredSectionProblem(doc.body, filePath);
      if (retired) readerIssues.push(retired);
      result.set(doc.entity, doc);
    }
  }

  if (orphans.length > 0) {
    throw new Error(
      `Orphan curated file(s) with no matching collected source: ${orphans.join(", ")}`,
    );
  }

  if (readerIssues.length > 0) {
    throw new Error(
      `Curated reader-field validation failed (${readerIssues.length} problem${readerIssues.length === 1 ? "" : "s"}):\n` +
        readerIssues.map((issue) => `  - ${issue}`).join("\n"),
    );
  }

  return result;
}
