import type { SourceType } from "./types";

/**
 * Classify a source-file path by its location in the plugin tree.
 *
 * - a path containing `commands/` → `"command"`
 * - a path containing `skills/`   → `"skill"`
 * - a path containing `agents/`   → `"agent"`
 *
 * Backslash separators are normalized to forward slashes first. Throws on a
 * path that matches none of the three.
 */
export function classifySource(path: string): SourceType {
  // Normalize backslashes to forward slashes
  const normalized = path.replace(/\\/g, "/");

  // Check for each known directory pattern in order
  if (normalized.includes("commands/")) {
    return "command";
  }
  if (normalized.includes("skills/")) {
    return "skill";
  }
  if (normalized.includes("agents/")) {
    return "agent";
  }

  // No match – throw an error
  throw new Error(`Could not classify source path: ${path}`);
}
