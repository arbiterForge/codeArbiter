/** workflow-pairs.ts — pair each command with the skill that owns its procedure.
 *
 * A shipped command source names its owning skill as its first heading:
 * `plugins/ca/commands/adr.md` opens with `# decision-lifecycle`, every other
 * command opens with `# /ca:<name> — <summary>`. Pairs are read from that
 * convention and the command catalog, not from a hand-kept list, so a new
 * pairing (or a broken one) shows up on the next build.
 *
 * A first heading that is a bare identifier is a CLAIM on a skill. A claim on a
 * skill that is not shipped, or two commands claiming the same skill, makes
 * generation fail, naming every offender. A `/ca:` heading is not a claim.
 */
import { splitFrontmatter } from "./split-frontmatter";
import { markdownHeadings } from "./markdown-fences";
import type { CommandCatalog, WorkflowPair } from "./types";

/** A skill directory name: lowercase words joined by single hyphens. */
const SKILL_NAME = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;

/** A command source, normalized to LF, with its filename-derived name. */
export interface WorkflowCommandSource {
  name: string;
  raw: string;
}

/** The first level-1 heading of a markdown source (frontmatter and code fences skipped). */
export function firstHeading(raw: string): string | undefined {
  const { body } = splitFrontmatter(raw);
  return markdownHeadings(body).find((heading) => heading.level === 1)?.text;
}

/**
 * The skill a command source claims as its owner, or undefined when its first
 * heading is not a bare identifier (the `/ca:<name> — summary` form).
 */
export function claimedSkill(raw: string): string | undefined {
  const heading = firstHeading(raw);
  return heading !== undefined && SKILL_NAME.test(heading) ? heading : undefined;
}

/**
 * Derive the command/skill pairs from the shipped sources and the catalog.
 *
 * `skills` is every shipped skill directory name. A command whose catalog
 * visibility is `alias` pairs in `alias` mode, every other visibility in
 * `merge` mode. Throws one error listing every unknown or duplicated owner;
 * the catalog is required only when some command makes a claim.
 */
export function deriveWorkflowPairs(
  commands: readonly WorkflowCommandSource[],
  skills: readonly string[],
  catalog: CommandCatalog | undefined,
): WorkflowPair[] {
  const shipped = new Set(skills);
  const problems: string[] = [];
  const claims: Array<{ command: string; skill: string }> = [];

  for (const { name, raw } of [...commands].sort((a, b) => a.name.localeCompare(b.name))) {
    const skill = claimedSkill(raw);
    if (skill === undefined) continue;
    if (!shipped.has(skill)) {
      problems.push(
        `commands/${name}.md names owning skill "${skill}" in its first heading, but no skills/${skill}/ is shipped`,
      );
      continue;
    }
    claims.push({ command: name, skill });
  }

  const owners = new Map<string, string[]>();
  for (const { command, skill } of claims) {
    owners.set(skill, [...(owners.get(skill) ?? []), command]);
  }
  for (const [skill, claimants] of owners) {
    if (claimants.length > 1) {
      problems.push(
        `skill "${skill}" is named as owner by ${claimants.length} commands: ${claimants
          .map((command) => `commands/${command}.md`)
          .join(", ")}`,
      );
    }
  }

  if (problems.length > 0) {
    throw new Error(`Cannot pair commands with skills: ${problems.join("; ")}`);
  }
  if (claims.length === 0) return [];
  if (catalog === undefined) {
    throw new Error(
      `Cannot pair commands with skills: ${claims
        .map((claim) => `commands/${claim.command}.md`)
        .join(", ")} name an owning skill but no generated command catalog supplies their visibility`,
    );
  }

  return claims.map(({ command, skill }): WorkflowPair => {
    const entry = catalog.commands[command];
    if (entry === undefined) {
      throw new Error(
        `Cannot pair commands with skills: commands/${command}.md names owning skill "${skill}" but the command catalog has no entry for it`,
      );
    }
    if (entry.visibility === "alias") {
      return {
        command,
        skill,
        mode: "alias",
        visibility: entry.visibility,
        canonical: entry.canonical,
        replacement: entry.replacement,
      };
    }
    return { command, skill, mode: "merge", visibility: entry.visibility };
  });
}

/** How a skill's reader page is produced, derived from the pairs. */
export type SkillRole = "merged" | "alias-owner" | "internal-only";

/**
 * Classify every shipped skill. `merged` skills have no page (their command
 * page is the workflow page); `alias-owner` skills are the workflow page for an
 * alias command; `internal-only` skills have no command at all.
 */
export function classifySkills(
  skills: readonly string[],
  pairs: readonly WorkflowPair[],
): Map<string, SkillRole> {
  const roles = new Map<string, SkillRole>();
  for (const skill of skills) roles.set(skill, "internal-only");
  for (const pair of pairs) {
    roles.set(pair.skill, pair.mode === "merge" ? "merged" : "alias-owner");
  }
  return roles;
}

/**
 * The skills whose pages once received a `-2` slug. Each shared its name with a
 * same-named command, and the old combined slug pass pushed the skill page to
 * `<name>-2`. Per-collection slugs ended that, but the old URLs were published,
 * so they stay redirected. This is a closed historical set, not a rule: a skill
 * added later never had a `-2` URL.
 */
export const LEGACY_SECOND_SLUG_SKILLS = [
  "context-check",
  "debug",
  "decompose",
  "refactor",
  "release",
  "tribunal",
] as const;

/**
 * Redirects for the skills that have no page of their own: each merged skill's
 * old `/reference/skills/<skill>` URL goes to its command page.
 *
 * Keys are base-relative, because Astro matches redirect keys through `base`
 * itself. Destinations are emitted verbatim as the Location target, so they
 * carry the base explicitly. Alias pairs are left out: their skill page is the
 * workflow page and still exists.
 */
export function mergedSkillRedirects(
  pairs: readonly WorkflowPair[],
  base: string,
): Record<string, string> {
  return Object.fromEntries(
    pairs
      .filter((pair) => pair.mode === "merge")
      .map((pair) => [`/reference/skills/${pair.skill}`, `${base}/reference/commands/${pair.command}`]),
  );
}

/**
 * Redirects for the old `-2` skill URLs, resolved to the final page in one hop:
 * the command page when the skill was merged into one, the skill page otherwise.
 */
export function legacySecondSlugRedirects(
  skills: readonly string[],
  pairs: readonly WorkflowPair[],
  base: string,
): Record<string, string> {
  const commandOf = new Map(
    pairs.filter((pair) => pair.mode === "merge").map((pair) => [pair.skill, pair.command]),
  );
  return Object.fromEntries(
    skills.map((skill) => {
      const command = commandOf.get(skill);
      const destination =
        command === undefined ? `/reference/skills/${skill}` : `/reference/commands/${command}`;
      return [`/reference/skills/${skill}-2`, `${base}${destination}`];
    }),
  );
}
