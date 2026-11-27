/** changelog-index.ts - the releases on the changelog page, for its navigator.
 *
 * Parses the page exactly as the site renders it (renderChangelog over the root CHANGELOG.md)
 * and gives each release the heading id Starlight gives it, by slugging every heading on the
 * page in order with the same slugger. Entry counts are the page's own bullets per section.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import GithubSlugger from "github-slugger";
import { renderChangelog } from "../generator/render-changelog";
import { REPO_ROOT } from "../machine/machine-model";

export interface Release {
  /** The bracketed label: a version, or a date for releases grouped by date before 2.0.0. */
  label: string;
  version: string | null;
  date: string | null;
  title: string | null;
  /** The heading id on the built changelog page. */
  id: string;
  counts: Record<string, number>;
  total: number;
}

const SEMVER = /^\d+\.\d+\.\d+(?:[-+][\w.]+)?$/;
const DATE = /\b(\d{4}-\d{2}-\d{2})\b/;

/** Heading text as it reaches the slugger: links and code spans reduced to their text. */
function headingText(markdown: string): string {
  return markdown
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/[*_]{1,3}([^*_]+)[*_]{1,3}/g, "$1")
    .trim();
}

export function parseChangelogPage(markdown: string): Release[] {
  const slugger = new GithubSlugger();
  const releases: Release[] = [];
  let current: Release | null = null;
  let section = "Other";
  let fence: string | null = null;
  for (const line of markdown.split(/\r?\n/)) {
    const fenceMatch = /^\s*(```+|~~~+)/.exec(line);
    if (fenceMatch) {
      if (fence === null) fence = fenceMatch[1][0];
      else if (fenceMatch[1][0] === fence) fence = null;
      continue;
    }
    if (fence !== null) continue;
    const heading = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const id = slugger.slug(headingText(heading[2]));
      if (level === 2) {
        const release = /^\[([^\]]+)\](.*)$/.exec(heading[2]);
        current = null;
        if (release && release[1] !== "Unreleased") {
          const label = release[1].trim();
          const rest = release[2];
          const version = SEMVER.test(label) ? label : null;
          const date = DATE.exec(version ? rest : label)?.[1] ?? null;
          if (version || date) {
            const title = (version ? rest.replace(DATE, "") : rest).replace(/^[\s\-–—]+|[\s\-–—]+$/g, "").trim();
            current = { label, version, date, title: title || null, id, counts: {}, total: 0 };
            releases.push(current);
          }
        }
        section = "Other";
      } else if (level === 3 && current) {
        section = headingText(heading[2]);
      }
      continue;
    }
    if (current && /^[-*] /.test(line)) {
      current.counts[section] = (current.counts[section] ?? 0) + 1;
      current.total += 1;
    }
  }
  return releases;
}

export function loadChangelogIndex(repoRoot = REPO_ROOT): Release[] {
  const page = renderChangelog(readFileSync(join(repoRoot, "CHANGELOG.md"), "utf8"));
  return parseChangelogPage(page.replace(/^---\n[\s\S]*?\n---\n/, ""));
}
