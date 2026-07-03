/** render-hooks-reference.ts — renders the generated `reference/hooks-gates.md`
 * page from the call sites `extract-hook-gates.ts` found, plus each script's
 * registered event(s) from `hooks.json`.
 *
 * See the docs-site-overhaul spec, decision d: hooks are code, not prose — the
 * page's "verbatim layer" is this generated metadata + line-pinned source
 * permalinks, never pasted Python.
 */
import type { HookCallSite } from "./extract-hook-gates";

/** Parsed shape of `plugins/ca/hooks/hooks.json` (only the fields this module reads). */
export interface HooksJson {
  hooks: Record<
    string,
    Array<{
      matcher?: string;
      hooks: Array<{ command: string }>;
    }>
  >;
}

/** `git-enforce.py` is the `.git/hooks` backstop shim — it is installed
 * directly, not registered in `hooks.json`, so it gets a hand-mapped label. */
const GIT_BACKSTOP_FILE = "git-enforce.py";
const GIT_BACKSTOP_LABEL = "git backstop";

/**
 * Build a script-basename -> event-label list map from a parsed `hooks.json`.
 *
 * A label is `EventName` (no matcher registered, or the matcher is absent) or
 * `EventName (matcher)`. A script registered under more than one event/matcher
 * combination gets every one, in the order `hooks.json` lists them, deduplicated.
 */
export function buildEventMap(hooksJson: HooksJson): Map<string, string[]> {
  const map = new Map<string, string[]>();
  const scriptRe = /hooks\/([A-Za-z0-9_.-]+\.py)/;

  for (const [event, entries] of Object.entries(hooksJson.hooks ?? {})) {
    for (const entry of entries) {
      const label = entry.matcher ? `${event} (${entry.matcher})` : event;
      const scripts = new Set<string>();
      for (const h of entry.hooks ?? []) {
        const m = scriptRe.exec(h.command);
        if (m) scripts.add(m[1]);
      }
      for (const script of scripts) {
        const existing = map.get(script) ?? [];
        if (!existing.includes(label)) existing.push(label);
        map.set(script, existing);
      }
    }
  }
  return map;
}

/** Events label list for one hook source file — hand-mapped for the git backstop. */
export function eventsFor(file: string, eventMap: Map<string, string[]>): string[] {
  if (file === GIT_BACKSTOP_FILE) return [GIT_BACKSTOP_LABEL];
  return eventMap.get(file) ?? [];
}

/** Parse a gate tag into (numeric part, letter suffix) for natural sort:
 * H-00, H-01, ..., H-09, H-09b, H-10, H-10b, ..., H-20. */
function parseTag(tag: string): { num: number; suffix: string } {
  const m = /^H-(\d+)([a-z]?)$/.exec(tag);
  if (!m) return { num: Number.MAX_SAFE_INTEGER, suffix: tag };
  return { num: Number(m[1]), suffix: m[2] };
}

function compareTags(a: string, b: string): number {
  const pa = parseTag(a);
  const pb = parseTag(b);
  if (pa.num !== pb.num) return pa.num - pb.num;
  return pa.suffix.localeCompare(pb.suffix);
}

/** Wrap every `{placeholder}` run in an f-string message with backticks, so it
 * renders as inline code rather than looking like missing/broken prose. */
function markPlaceholders(message: string): string {
  return message.replace(/\{[^{}]*\}/g, (m) => `\`${m}\``);
}

/** Escape a string for safe inclusion in a markdown blockquote line. */
function toBlockquote(message: string): string {
  return markPlaceholders(message)
    .split("\n")
    .map((line) => `> ${line}`)
    .join("\n");
}

/**
 * Render the full `reference/hooks-gates.md` page.
 *
 * One `## H-xx` section per tag, sorted in natural gate-ID order. Each section
 * carries a badge line (Blocking / Advisory — both if the tag has call sites of
 * both kinds), the registered event(s) across every file that has a call site
 * for that tag, and one blockquote + line-pinned permalink per call site.
 */
export function renderHooksReference(
  callSites: HookCallSite[],
  eventMap: Map<string, string[]>,
  pluginVersion: string,
): string {
  const tag = `v${pluginVersion}`;
  const byTag = new Map<string, HookCallSite[]>();
  for (const site of callSites) {
    const list = byTag.get(site.tag) ?? [];
    list.push(site);
    byTag.set(site.tag, list);
  }

  const tags = [...byTag.keys()].sort(compareTags);

  const sections = tags.map((gateTag) => {
    const sites = byTag.get(gateTag)!;
    const kinds = new Set(sites.map((s) => s.kind));
    const badges: string[] = [];
    if (kinds.has("block")) badges.push("**Blocking**");
    if (kinds.has("remind")) badges.push("**Advisory**");

    const events = new Set<string>();
    for (const site of sites) {
      for (const label of eventsFor(site.file, eventMap)) events.add(label);
    }

    const entries = sites
      .map((site) => {
        const permalink = `https://github.com/arbiterForge/codeArbiter/blob/${tag}/plugins/ca/hooks/${site.file}#L${site.line}`;
        return `${toBlockquote(site.message)}\n>\n> — [\`${site.file}:${site.line}\`](${permalink})`;
      })
      .join("\n\n");

    return [
      `## ${gateTag}`,
      "",
      badges.join(" / "),
      "",
      `**Event(s):** ${events.size > 0 ? [...events].map((e) => `\`${e}\``).join(", ") : "_(none registered)_"}`,
      "",
      entries,
    ].join("\n");
  });

  const frontmatter = [
    "---",
    "title: Hook Gates",
    'description: "Every gate ID a codeArbiter hook can print — generated from the block()/remind() call sites in plugins/ca/hooks, never hand-transcribed."',
    "---",
  ].join("\n");

  const intro = [
    "These gate IDs appear in terminal output as `BLOCKED [H-xx]: <message>` (a blocking",
    "hook, exit 2) or `REMINDER [H-xx]: <message>` (an advisory hook, exit 0). This page is",
    "generated at build time directly from the `block()`/`remind()` call sites in",
    "`plugins/ca/hooks/*.py`, so it can never drift from what a hook actually prints.",
    "",
    "A `` `{placeholder}` `` shown in a message is an f-string interpolation — the hook fills",
    "it in with a run-time value (a file path, a branch name, a count) when it actually fires.",
  ].join("\n");

  return `${frontmatter}\n\n${intro}\n\n${sections.join("\n\n---\n\n")}\n`;
}
