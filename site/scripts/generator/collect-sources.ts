import { classifySource } from "./classify-source";
import type { SourceFile } from "./types";

/**
 * Collect plugin source files under a root directory.
 *
 * Reads `commands/*.md`, `skills/* /SKILL.md`, and `agents/*.md` relative to
 * `rootDir`. Missing subdirectories (or a missing `rootDir`) are skipped and
 * yield no entries — never throws. Results are sorted by path for stable order,
 * and each entry's `type` is set via {@link classifySource}.
 */
export function collectSources(rootDir: string): SourceFile[] {
  throw new Error("not implemented");
}
