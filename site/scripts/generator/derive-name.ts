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
  if (fields.name) {
    return fields.name;
  }
  const normalized = path.replace(/\\/g, '/');
  const segments = normalized.split('/');
  let basename = segments[segments.length - 1] || '';
  if (basename.endsWith('.md')) {
    basename = basename.slice(0, -3);
  }
  if (basename === 'SKILL') {
    if (segments.length >= 2) {
      return segments[segments.length - 2];
    }
    return '';
  }
  return basename;
}
