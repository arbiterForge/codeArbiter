/** curated-drift.ts — hand-written reference text cannot name what the source dropped.
 *
 * Curated pages are prose about shipped commands. When a command loses a flag,
 * or a command is renamed or removed, the prose keeps saying the old thing
 * unless something compares the two. This check does, and `generate()` runs it,
 * so a stale page fails the build instead of reaching a reader.
 *
 * Two checks, both over the whole curated file (frontmatter included, because
 * reader fields are printed on the page):
 *   - every `/ca:<name>` must be a command in the catalog;
 *   - every `--flag` attributed to a codeArbiter command must appear in that
 *     command's shipped source.
 *
 * Attribution. A flag belongs to the nearest preceding `/ca:<name>` on its own
 * line; failing that, to the nearest preceding `/ca:<name>` earlier in the same
 * code block; failing that, inside a code block under the page's `Usage`
 * heading, to the page's own command. A flag with no command in reach is left
 * alone, and so is a flag of another program: when the text between the command
 * (or, for a carried command, the start of the line) and the flag names a
 * well-known program such as `git` or `npm`, the flag is that program's. That
 * list identifies tools; it never excuses a codeArbiter flag.
 *
 * "The command's shipped source" is `commands/<name>.md` (its `argument-hint`
 * included) plus, when the command is paired with a skill, that skill's
 * `SKILL.md`. That is the text the command's reference page embeds, so a flag
 * the reader can check against the page's own source is the flag we accept.
 * The compatibility alias is the case that matters: `/ca:cleanup` names its
 * replacement `/ca:pr --cleanup`, and prose on the cleanup page that says so
 * is attributed to `/ca:pr`, the nearest command, and checked against pr's source.
 *
 * Every problem in every file is reported in one error.
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fencedLines, markdownHeadings } from "./markdown-fences";
import { normalizeSource } from "./normalize-source";
import { parseFields } from "./parse-fields";
import { splitFrontmatter } from "./split-frontmatter";

/** One problem: a flag the source lacks, or a command the catalog lacks. */
export interface DriftMiss {
  file: string;
  /** 1-based line in the file as written. */
  line: number;
  kind: "flag" | "command";
  /** The flag (`--amend`) or the command name (`frobnicate`). */
  token: string;
  /** For a flag, the command it was attributed to. */
  command?: string;
}

/** One curated file to check. */
export interface CuratedDriftFile {
  /** Shown in every message. */
  path: string;
  raw: string;
  /** The command this page is about, when it has one (see {@link ownCommandOf}). */
  ownCommand?: string;
}

export interface CuratedDriftInput {
  files: readonly CuratedDriftFile[];
  /** Every command a page may name: the catalog's commands. */
  commands: ReadonlySet<string>;
  /** Shipped source text per command: its command file plus its paired skill. */
  sources: ReadonlyMap<string, string>;
}

/** `--flag`, not preceded by a word character or hyphen, so `a--b` and `---` are not flags. */
const FLAG = /(?<![\w-])--[a-z][a-z0-9]*(?:-[a-z0-9]+)*/g;
/** `/ca:<name>`; a bare `/ca:` or a `/ca:<placeholder>` has no name and matches nothing. */
const COMMAND = /(?<![\w/.-])\/ca:([a-z][a-z0-9]*(?:-[a-z0-9]+)*)(?!\w)/g;
/** Programs whose flags are not ours. A tool list for attribution, never an exception list. */
const FOREIGN_PROGRAM =
  /(?<![\w./-])(?:git|gh|npm|npx|pnpm|yarn|node|python3?|pip3?|cargo|docker|curl|claude|codex)(?![\w-])/;
const FENCE_DELIMITER = /^ {0,3}(`{3,}|~{3,})/;

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Whether `source` names `flag` as a whole flag, so `--since` is not satisfied by `--since-checkpoint`. */
function sourceHasFlag(source: string, flag: string): boolean {
  return new RegExp(`(?<![\\w-])${escapeRegExp(flag)}(?![\\w-])`).test(source);
}

/** Zero-based `[from, to)` line ranges of the sections headed `Usage`, each up to the next heading of its level or higher. */
function usageRanges(text: string): Array<[number, number]> {
  const headings = markdownHeadings(text);
  const ranges: Array<[number, number]> = [];
  headings.forEach((heading, index) => {
    if (heading.text.toLowerCase() !== "usage") return;
    const next = headings.slice(index + 1).find((other) => other.level <= heading.level);
    ranges.push([heading.line + 1, next ? next.line : Number.POSITIVE_INFINITY]);
  });
  return ranges;
}

type Event =
  | { type: "command"; index: number; end: number; name: string }
  | { type: "flag"; index: number; token: string };

/** Every command and flag on one line, in the order they appear. */
function lineEvents(line: string): Event[] {
  const events: Event[] = [];
  for (const match of line.matchAll(COMMAND)) {
    events.push({ type: "command", index: match.index, end: match.index + match[0].length, name: match[1] });
  }
  for (const match of line.matchAll(FLAG)) {
    events.push({ type: "flag", index: match.index, token: match[0] });
  }
  return events.sort((a, b) => a.index - b.index);
}

/** Every problem in `input.files`, in file order and then line order. */
export function findCuratedDrift(input: CuratedDriftInput): DriftMiss[] {
  const misses: DriftMiss[] = [];

  for (const file of input.files) {
    const text = normalizeSource(file.raw);
    const lines = text.split("\n");
    const fenced = fencedLines(lines);
    const usage = usageRanges(text);
    let blockCommand: string | undefined;

    lines.forEach((line, index) => {
      if (!fenced[index] || FENCE_DELIMITER.test(line)) blockCommand = undefined;
      const inUsageBlock = fenced[index] && usage.some(([from, to]) => index >= from && index < to);
      let lineCommand: { name: string; end: number } | undefined;

      for (const event of lineEvents(line)) {
        if (event.type === "command") {
          if (!input.commands.has(event.name)) {
            misses.push({ file: file.path, line: index + 1, kind: "command", token: event.name });
          }
          lineCommand = { name: event.name, end: event.end };
          continue;
        }

        let owner: string | undefined;
        let from = 0;
        if (lineCommand) {
          owner = lineCommand.name;
          from = lineCommand.end;
        } else if (fenced[index] && blockCommand) {
          owner = blockCommand;
        } else if (inUsageBlock) {
          owner = file.ownCommand;
        }
        if (owner === undefined) continue;
        if (FOREIGN_PROGRAM.test(line.slice(from, event.index))) continue;
        const source = input.sources.get(owner);
        if (source === undefined) continue; // an unknown command was already reported
        if (!sourceHasFlag(source, event.token)) {
          misses.push({ file: file.path, line: index + 1, kind: "flag", token: event.token, command: owner });
        }
      }

      if (fenced[index] && lineCommand) blockCommand = lineCommand.name;
    });
  }

  return misses;
}

/** Throw one error naming every problem, or return when there are none. */
export function assertNoCuratedDrift(input: CuratedDriftInput): void {
  const misses = findCuratedDrift(input);
  if (misses.length === 0) return;
  const describe = (miss: DriftMiss): string =>
    miss.kind === "flag"
      ? `${miss.token} is not in the shipped source of /ca:${miss.command}`
      : `/ca:${miss.token} is not a command in the catalog`;
  throw new Error(
    `Curated text names something the shipped source does not have (${misses.length} problem${misses.length === 1 ? "" : "s"}):\n` +
      misses.map((miss) => `  - ${miss.file}:${miss.line}: ${describe(miss)}`).join("\n") +
      `\nCorrect the prose to match the source; the source embed on each page is authoritative.`,
  );
}

/**
 * The command a curated page is about: the command itself for `commands/<name>`,
 * the paired command for a skill that has one, nothing for an internal-only
 * skill or an agent. `skillCommand` maps a skill directory name to its command.
 */
export function ownCommandOf(
  entity: string,
  skillCommand: ReadonlyMap<string, string>,
): string | undefined {
  if (entity.startsWith("commands/")) return entity.slice("commands/".length);
  if (entity.startsWith("skills/")) return skillCommand.get(entity.slice("skills/".length));
  return undefined;
}

/** A curated file as read from disk, with the entity its frontmatter declares. */
export interface CuratedDriftSource {
  path: string;
  raw: string;
  entity: string;
}

/** Every `<type>/<name>.md` under `curatedDir`, in a stable order. A missing directory yields none. */
export function readCuratedDriftSources(curatedDir: string): CuratedDriftSource[] {
  const sources: CuratedDriftSource[] = [];
  for (const dirName of ["commands", "skills", "agents"]) {
    const dir = join(curatedDir, dirName);
    if (!existsSync(dir)) continue;
    for (const entry of readdirSync(dir).filter((name) => name.endsWith(".md")).sort()) {
      const path = join(dir, entry);
      const raw = readFileSync(path, "utf-8");
      const { frontmatter } = splitFrontmatter(normalizeSource(raw));
      sources.push({ path, raw, entity: frontmatter === null ? "" : (parseFields(frontmatter).entity ?? "") });
    }
  }
  return sources;
}
