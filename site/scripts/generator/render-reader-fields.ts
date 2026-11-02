/** render-reader-fields.ts — the fixed reader panel above a reference page's body. */
import { escapeHtml } from "./render-reference-lead";
import { READER_FIELD_SPEC, type ReaderFields, type ReaderShape } from "./types";

/**
 * One inline token, tried left to right: a code span (any run of backticks,
 * closed by an equal run) or a `[label](url)` link. Text between tokens is
 * plain text with optional emphasis.
 */
const INLINE_TOKEN =
  /(?<!`)(`+)(?!`)([\s\S]*?[^`])\1(?!`)|\[([^\]]+)\]\(([^)\s]+)\)/g;

/** A link target is kept only when it has no scheme or the scheme is benign. */
function isSafeHref(href: string): boolean {
  const scheme = /^([a-z][a-z0-9+.-]*):/i.exec(href);
  return scheme === null || /^(https?|mailto)$/i.test(scheme[1]);
}

/** Escape plain text, then apply `**strong**`, `*emphasis*` and `_emphasis_`. */
function renderEmphasis(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*(?=\S)(.+?)(?<=\S)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])/g, "<em>$1</em>")
    .replace(/(?<![_\w])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![_\w])/g, "<em>$1</em>");
}

/**
 * Convert the inline markdown a curated value may carry (code spans, links,
 * strong, emphasis) to escaped HTML. The panel is a raw HTML block, so the
 * markdown processor never sees these values; every character that is not
 * part of a token below is escaped, code contents included.
 */
export function renderInlineMarkdown(value: string): string {
  let html = "";
  let last = 0;
  for (const match of value.matchAll(INLINE_TOKEN)) {
    html += renderEmphasis(value.slice(last, match.index));
    last = match.index + match[0].length;
    const [token, , code, label, href] = match;
    if (code !== undefined) {
      const trimmed = /^ .*[^ ].* $/s.test(code) ? code.slice(1, -1) : code;
      html += `<code>${escapeHtml(trimmed)}</code>`;
    } else if (isSafeHref(href)) {
      html += `<a href="${escapeHtml(href)}">${renderInlineMarkdown(label)}</a>`;
    } else {
      html += renderEmphasis(token);
    }
  }
  return html + renderEmphasis(value.slice(last));
}

/**
 * Render a page's reader fields as one `## At a glance` panel: a definition
 * list with one label/value pair per field, in the order
 * {@link READER_FIELD_SPEC} fixes for the page's shape:
 *
 * - `workflow`: Use it when, Don't use it for, What it asks you, What it produces.
 * - `internal-skill`: Runs inside, What it produces.
 *
 * The list is a raw HTML block, so it holds no blank line (one would end the
 * block) and the values arrive as escaped HTML from {@link renderInlineMarkdown}.
 *
 * Returns an empty string when the page has no shape (alias commands, uncurated
 * pages) or no fields. Presence is the loader's job (see `load-curated.ts`);
 * this renders what the curated file declared and skips empty values.
 */
export function renderReaderFields(
  reader: ReaderFields | undefined,
  shape: ReaderShape | undefined,
): string {
  if (shape === undefined || reader === undefined) return "";
  const pairs = READER_FIELD_SPEC[shape].flatMap(({ key, label }) => {
    const value = reader[key]?.replace(/\s+/g, " ").trim();
    return value
      ? [`<dt>${escapeHtml(label)}</dt>\n<dd>${renderInlineMarkdown(value)}</dd>`]
      : [];
  });
  if (pairs.length === 0) return "";
  return `## At a glance\n\n<dl class="ca-reader-fields">\n${pairs.join("\n")}\n</dl>`;
}
