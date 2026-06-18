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
  throw new Error("not implemented");
}
