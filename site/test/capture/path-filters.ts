/** path-filters.ts - read the docs workflow's path filters and match paths against them.
 *
 * There is no YAML library in this tree and adding one for a single test is not
 * worth a dependency, so this reads exactly the shape docs.yml uses:
 *
 *   on:
 *     push:
 *       paths:
 *         - "site/**"
 *     pull_request:
 *       paths:
 *         - "site/**"
 *
 * It throws when either list is missing or empty, so reformatting the workflow
 * can never make the coverage test pass vacuously.
 */

export interface WorkflowPathFilters {
  push: string[];
  pull_request: string[];
}

function indentOf(line: string): number {
  return line.length - line.trimStart().length;
}

function isContent(line: string): boolean {
  const trimmed = line.trim();
  return trimmed !== "" && !trimmed.startsWith("#");
}

function unquote(value: string): string {
  const withoutComment = value.replace(/\s+#.*$/, "").trim();
  const quoted = /^(["'])(.*)\1$/.exec(withoutComment);
  return quoted ? quoted[2] : withoutComment;
}

/** The `paths:` list under `on.<event>`, in file order. */
function readEventPaths(lines: string[], onIndex: number, event: string): string[] {
  const onIndent = indentOf(lines[onIndex]);
  let eventIndex = -1;
  for (let index = onIndex + 1; index < lines.length; index += 1) {
    if (!isContent(lines[index])) continue;
    if (indentOf(lines[index]) <= onIndent) break;
    if (lines[index].trim() === `${event}:`) {
      eventIndex = index;
      break;
    }
  }
  if (eventIndex < 0) throw new Error(`docs workflow has no on.${event} trigger`);

  const eventIndent = indentOf(lines[eventIndex]);
  let pathsIndex = -1;
  for (let index = eventIndex + 1; index < lines.length; index += 1) {
    if (!isContent(lines[index])) continue;
    if (indentOf(lines[index]) <= eventIndent) break;
    if (lines[index].trim() === "paths:") {
      pathsIndex = index;
      break;
    }
  }
  if (pathsIndex < 0) throw new Error(`docs workflow on.${event} has no paths filter`);

  const pathsIndent = indentOf(lines[pathsIndex]);
  const paths: string[] = [];
  for (let index = pathsIndex + 1; index < lines.length; index += 1) {
    if (!isContent(lines[index])) continue;
    if (indentOf(lines[index]) <= pathsIndent) break;
    const item = /^\s*-\s+(.*)$/.exec(lines[index]);
    if (!item) throw new Error(`docs workflow on.${event}.paths has a line that is not a list item: ${lines[index]}`);
    paths.push(unquote(item[1]));
  }
  if (paths.length === 0) throw new Error(`docs workflow on.${event}.paths is empty`);
  return paths;
}

export function readWorkflowPathFilters(workflowText: string): WorkflowPathFilters {
  const lines = workflowText.replace(/\r\n/g, "\n").split("\n");
  const onIndex = lines.findIndex((line) => /^on:\s*(#.*)?$/.test(line));
  if (onIndex < 0) throw new Error("docs workflow has no top-level `on:` block");
  return {
    push: readEventPaths(lines, onIndex, "push"),
    pull_request: readEventPaths(lines, onIndex, "pull_request"),
  };
}

/** GitHub filter glob: `*` stays inside a path segment, `**` crosses segments, `?` is one non-slash character. */
export function matchesPathFilter(path: string, pattern: string): boolean {
  if (pattern.startsWith("!")) throw new Error(`negated path filters are not supported here: ${pattern}`);
  let source = "";
  for (let index = 0; index < pattern.length; index += 1) {
    const char = pattern[index];
    if (char === "*" && pattern[index + 1] === "*") {
      source += ".*";
      index += 1;
    } else if (char === "*") {
      source += "[^/]*";
    } else if (char === "?") {
      source += "[^/]";
    } else {
      source += char.replace(/[.+^${}()|[\]\\]/g, "\\$&");
    }
  }
  return new RegExp(`^${source}$`).test(path);
}

export function coveredBy(path: string, patterns: readonly string[]): boolean {
  return patterns.some((pattern) => matchesPathFilter(path, pattern));
}

/** Sources that a trigger would not rebuild the site for, by event. Empty means every source is covered. */
export function uncoveredSources(
  sources: readonly string[],
  filters: WorkflowPathFilters,
): Array<{ source: string; event: "push" | "pull_request" }> {
  const missing: Array<{ source: string; event: "push" | "pull_request" }> = [];
  for (const source of sources) {
    for (const event of ["push", "pull_request"] as const) {
      if (!coveredBy(source, filters[event])) missing.push({ source, event });
    }
  }
  return missing;
}
