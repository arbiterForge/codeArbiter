/**
 * Normalize a raw source file at the read boundary: strip a leading BOM and
 * convert CRLF to LF. The frontmatter parser and heading reader are specified
 * against `\n`, so a Windows checkout of the plugin must be normalized before
 * parsing; otherwise the leading `---` line (or a bare-identifier heading such
 * as `# commit-gate`) carries a trailing `\r` and is not recognised.
 */
export function normalizeSource(raw: string): string {
  const noBom = raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw;
  return noBom.replace(/\r\n/g, "\n");
}
