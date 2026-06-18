import { splitFrontmatter } from "./split-frontmatter";
import { parseFields } from "./parse-fields";
import type { ParsedDoc } from "./types";

/**
 * Parse a raw source file into `{ fields, body }`.
 *
 * Composes {@link splitFrontmatter} and {@link parseFields}. When there is no
 * frontmatter, `fields` is `{}`. Never throws on edge inputs (empty file,
 * body-only file).
 */
export function parseDoc(raw: string): ParsedDoc {
  const { frontmatter, body } = splitFrontmatter(raw);
  return {
    fields: frontmatter === null ? {} : parseFields(frontmatter),
    body,
  };
}
