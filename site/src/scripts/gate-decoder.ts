/** gate-decoder.ts - match what a hook printed to the gate and call site that printed it.
 *
 * Pure and bounded: literal matching over the shipped call sites, no evaluation, storage or
 * network. A message's `{placeholder}` runs are filled at run time, so they match any text.
 * A paste arrives with curly quotes, other dash spellings and terminal line wraps, so both
 * sides are normalized before they are compared.
 */

export interface DecoderSite {
  tag: string;
  kind: 'block' | 'remind';
  file: string;
  line: number;
  message: string;
}

export interface DecodedMatch {
  tag: string;
  /** exact: the whole message matched; partial: the paste is part of one message;
   * words: most of its words appear in one message; gate: only the printed tag is known;
   * unknown: the printed tag is not one the hooks print. */
  how: 'exact' | 'partial' | 'words' | 'gate' | 'unknown';
  site: DecoderSite | null;
}

const PREFIX = /\b(BLOCKED|REMINDER)\s*\[\s*(H-\d+[a-z]?)\s*\]\s*:?\s*/i;
const PLACEHOLDER = /\{[^{}\n]*\}/g;
const MAX_INPUT = 4000;

export function normalizeTerminalText(text: string): string {
  return text
    .normalize('NFKC')
    .replace(/[‘’‚‛′]/g, "'")
    .replace(/[“”„″]/g, '"')
    .replace(/[‐-―−]/g, '-')
    .replace(/`/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** The literal text of a message with its placeholders removed, normalized. */
function literal(message: string): string {
  return normalizeTerminalText(message.replace(PLACEHOLDER, ' '));
}

/** A pattern for a whole message: literal runs in order, any text where a placeholder was. */
function messagePattern(message: string): RegExp {
  const parts = message.split(PLACEHOLDER).map((part) => normalizeTerminalText(part));
  const body = parts
    .map((part) => escapeRegExp(part).replace(/ /g, '\\s*'))
    .join('[\\s\\S]*?');
  return new RegExp(body, 'i');
}

const words = (text: string) => new Set(text.toLowerCase().match(/[a-z][a-z0-9._-]{3,}/g) ?? []);

/** Best matches first. At most three; an empty list means no gate prints this text. */
export function decodeHookOutput(input: string, sites: DecoderSite[]): DecodedMatch[] {
  const text = normalizeTerminalText(input.slice(0, MAX_INPUT));
  if (text.length === 0) return [];
  const prefix = PREFIX.exec(text);
  const printedTag = prefix ? `H-${prefix[2].slice(2).toLowerCase()}` : null;
  const message = prefix ? text.slice(prefix.index + prefix[0].length) : text;
  const known = new Set(sites.map((site) => site.tag));
  if (printedTag && !known.has(printedTag)) return [{ tag: printedTag, how: 'unknown', site: null }];

  const pool = printedTag ? sites.filter((site) => site.tag === printedTag) : sites;
  const scored: { match: DecodedMatch; score: number }[] = [];
  for (const site of pool) {
    const literalText = literal(site.message);
    // A message that is mostly placeholders would match anything; it can only match by tag.
    if (literalText.replace(/[^a-z0-9]/gi, '').length < 8) continue;
    if (message.length >= 8 && messagePattern(site.message).test(message)) {
      scored.push({ match: { tag: site.tag, how: 'exact', site }, score: 3 + literalText.length / 10000 });
      continue;
    }
    if (message.length >= 12 && literalText.toLowerCase().includes(message.toLowerCase())) {
      scored.push({ match: { tag: site.tag, how: 'partial', site }, score: 2 + message.length / 10000 });
      continue;
    }
    const pasted = words(message);
    if (pasted.size >= 3) {
      const target = words(literalText);
      const shared = [...pasted].filter((word) => target.has(word)).length;
      const ratio = shared / pasted.size;
      if (ratio >= 0.6) scored.push({ match: { tag: site.tag, how: 'words', site }, score: ratio });
    }
  }
  scored.sort((a, b) => b.score - a.score);
  const seen = new Set<string>();
  const best = scored
    .filter(({ match }) => {
      const key = `${match.site?.file}:${match.site?.line}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 3)
    .map(({ match }) => match);
  if (best.length === 0 && printedTag) return [{ tag: printedTag, how: 'gate', site: null }];
  return best;
}
