/**
 * Derive a display name for a source document.
 *
 * - When `fields.name` is present and non-empty, return it.
 * - Otherwise derive from the file path: the basename without its `.md`
 *   extension, except a `SKILL.md` file uses its parent directory name.
 *
 * Backslash separators are normalized to forward slashes first.
 */
export function deriveName(path: string, fields: Record<string, string>): string {
  throw new Error("not implemented");
}
