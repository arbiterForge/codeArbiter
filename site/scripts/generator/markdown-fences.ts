/** markdown-fences.ts — fenced-code awareness for line-based markdown scans.
 *
 * The generator reads curated and shipped markdown with small line scanners
 * (first heading, `## Example`, heading demotion). A `# comment` or a
 * `## Example` line inside a fenced code block is code, not a heading, so every
 * scanner needs the same answer to "is this line inside a fence?". It lives
 * here once so the scanners cannot disagree.
 */

const FENCE_OPEN = /^ {0,3}(`{3,}|~{3,})/;

/**
 * For each line, whether it belongs to a fenced code block: the opening and
 * closing fence lines themselves count as fenced. A fence closes on a line
 * made of the same character, at least as long as the opener, with nothing
 * after it; an unclosed fence runs to the end of the input (CommonMark).
 */
export function fencedLines(lines: readonly string[]): boolean[] {
  const fenced: boolean[] = [];
  let open: { char: string; length: number } | null = null;
  for (const line of lines) {
    if (open === null) {
      const match = line.match(FENCE_OPEN);
      if (match) {
        open = { char: match[1][0], length: match[1].length };
        fenced.push(true);
      } else {
        fenced.push(false);
      }
      continue;
    }
    fenced.push(true);
    const close = line.match(/^ {0,3}(`{3,}|~{3,})\s*$/);
    if (close && close[1][0] === open.char && close[1].length >= open.length) {
      open = null;
    }
  }
  return fenced;
}

/** One ATX heading found outside a code fence. */
export interface MarkdownHeading {
  /** Zero-based line index. */
  line: number;
  /** 1 for `#` through 6 for `######`. */
  level: number;
  /** Heading text with the trailing closing hashes and spaces removed. */
  text: string;
}

/** Every ATX heading in `body` that is not inside a fenced code block. */
export function markdownHeadings(body: string): MarkdownHeading[] {
  const lines = body.split("\n");
  const fenced = fencedLines(lines);
  const headings: MarkdownHeading[] = [];
  lines.forEach((line, index) => {
    if (fenced[index]) return;
    const match = line.match(/^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$/);
    if (match) headings.push({ line: index, level: match[1].length, text: match[2].trim() });
  });
  return headings;
}

/**
 * Push every heading outside a code fence down one level (`##` becomes `###`)
 * so a body can nest under a heading of the page it is spliced into. A level-6
 * heading cannot go deeper and stays level 6.
 */
export function demoteHeadings(body: string): string {
  const lines = body.split("\n");
  const fenced = fencedLines(lines);
  return lines
    .map((line, index) => {
      if (fenced[index]) return line;
      const match = line.match(/^( {0,3})(#{1,5})([ \t].*)$/);
      return match ? `${match[1]}#${match[2]}${match[3]}` : line;
    })
    .join("\n");
}
