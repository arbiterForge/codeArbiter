/**
 * Format a comma-separated tools string as an inline backticked markdown list.
 *
 * - `"Read, Grep, Glob"` → `` "`Read`, `Grep`, `Glob`" ``
 * - Each entry is trimmed; entries with no space after the comma still split.
 * - Missing or empty → `"—"`.
 */
export function formatToolsList(tools?: string): string {
  if (!tools || tools.trim() === '') {
    return '—'; // em dash U+2014
  }

  return tools
    .split(',')
    .map(entry => entry.trim())
    .filter(entry => entry !== '')
    .map(entry => `\`${entry}\``)
    .join(', ');
}
