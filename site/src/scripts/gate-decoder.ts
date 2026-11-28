/** gate-decoder.ts - match what a hook printed to the gate and call site that printed it.
 *
 * Pure and bounded: plain substring search over the shipped call sites. No pattern is built
 * from a message, so no paste can make matching backtrack; each message costs time linear in
 * the paste, which is capped at MAX_INPUT characters. Nothing is evaluated, stored or sent.
 *
 * A message's `{placeholder}` runs are filled at run time, so they match any text. A paste
 * arrives with curly quotes, other dash spellings and terminal line wraps, and a wrap can fall
 * in the middle of a word, so both sides are compared with quotes and dashes in one spelling
 * and with no white space at all.
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
   * words: most of its distinctive words appear in one message; gate: only the printed tag is
   * known; unknown: the printed tag is not one the hooks print. */
  how: 'exact' | 'partial' | 'words' | 'gate' | 'unknown';
  site: DecoderSite | null;
}

const PREFIX = /\b(BLOCKED|REMINDER) ?\[ ?(H-\d+[a-z]?) ?\] ?:? ?/i;
const PLACEHOLDER = /\{[^{}\n]*\}/g;
const WORD = /[a-z][a-z0-9._-]{3,}/g;
export const MAX_INPUT = 4000;
const MAX_MATCHES = 6;

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

/** Quotes and dashes in one spelling, lower case, and no white space at all. */
function compact(text: string): string {
  return normalizeTerminalText(text).replace(/ /g, '').toLowerCase();
}

const wordsOf = (text: string) => new Set(normalizeTerminalText(text).toLowerCase().match(WORD) ?? []);

interface Prepared {
  site: DecoderSite;
  /** The message's literal runs between placeholders, compacted; empty runs dropped. */
  runs: string[];
  /** The literal runs joined, which identifies messages that print the same text. */
  text: string;
  words: Set<string>;
}

interface PreparedSites {
  sites: Prepared[];
  /** How much a word says about which message was pasted: rare words weigh more, and a word
   * no message uses weighs most, because it is evidence against every message. */
  weight: (word: string) => number;
}

const cache = new WeakMap<DecoderSite[], PreparedSites>();

function prepare(sites: DecoderSite[]): PreparedSites {
  const hit = cache.get(sites);
  if (hit) return hit;
  const prepared = sites.map((site) => {
    const runs = site.message.split(PLACEHOLDER).map(compact).filter((run) => run.length > 0);
    return { site, runs, text: runs.join(' '), words: wordsOf(site.message.replace(PLACEHOLDER, ' ')) };
  });
  const seen = new Map<string, number>();
  for (const { words } of prepared) for (const word of words) seen.set(word, (seen.get(word) ?? 0) + 1);
  const total = Math.max(prepared.length, 1);
  const result = { sites: prepared, weight: (word: string) => Math.log(total / (1 + (seen.get(word) ?? 0))) + 1 };
  cache.set(sites, result);
  return result;
}

/** True when every run occurs in `text`, in order and without overlapping. Taking each run's
 * earliest occurrence after the previous one is optimal, so one pass decides it. */
function embedsInOrder(text: string, runs: string[]): boolean {
  let from = 0;
  for (const run of runs) {
    const at = text.indexOf(run, from);
    if (at < 0) return false;
    from = at + run.length;
  }
  return true;
}

/** The length of the longest suffix of `left` that is also a prefix of `right` (linear, KMP). */
export function overlap(left: string, right: string): number {
  const pattern = right.slice(0, left.length);
  if (pattern.length === 0) return 0;
  const fail = new Int32Array(pattern.length);
  for (let i = 1, k = 0; i < pattern.length; i += 1) {
    while (k > 0 && pattern[i] !== pattern[k]) k = fail[k - 1];
    if (pattern[i] === pattern[k]) k += 1;
    fail[i] = k;
  }
  let k = 0;
  for (let i = 0; i < left.length; i += 1) {
    while (k > 0 && (k === pattern.length || left[i] !== pattern[k])) k = fail[k - 1];
    if (left[i] === pattern[k]) k += 1;
  }
  return k;
}

/**
 * How much of `text` a stretch of one message accounts for, when `text` was copied from the
 * middle of it: it may start partway through one run, cross any placeholders (whose printed
 * values match anything) and end partway through a later run. Returns the literal characters
 * matched; the rest of `text` is placeholder values.
 */
function fragmentCover(text: string, runs: string[]): number {
  let best = 0;
  // `first` is the first run copied whole; the copy may begin with the end of the run before it.
  for (let first = 0; first <= runs.length; first += 1) {
    const head = first > 0 ? overlap(runs[first - 1], text) : 0;
    let covered = head;
    let from = head;
    let next = first;
    for (; next < runs.length; next += 1) {
      const at = text.indexOf(runs[next], from);
      if (at < 0) break;
      covered += runs[next].length;
      from = at + runs[next].length;
    }
    if (next < runs.length) covered += overlap(text.slice(from), runs[next]);
    best = Math.max(best, covered);
  }
  return best;
}

/** Best matches first, at most MAX_MATCHES. An empty list means no gate prints this text. */
export function decodeHookOutput(input: string, sites: DecoderSite[]): DecodedMatch[] {
  const text = normalizeTerminalText(input.slice(0, MAX_INPUT));
  if (text.length === 0) return [];
  const prefix = PREFIX.exec(text);
  const printedTag = prefix ? `H-${prefix[2].slice(2).toLowerCase()}` : null;
  const message = prefix ? text.slice(prefix.index + prefix[0].length) : text;
  const { sites: prepared, weight } = prepare(sites);
  const known = new Set(sites.map((site) => site.tag));
  if (printedTag && !known.has(printedTag)) return [{ tag: printedTag, how: 'unknown', site: null }];

  const pasted = compact(message);
  const pastedWords = [...wordsOf(message)];
  const pastedWeight = pastedWords.reduce((sum, word) => sum + weight(word), 0);
  const scored: { match: DecodedMatch; score: number }[] = [];
  for (const entry of prepared) {
    const { site, runs } = entry;
    if (printedTag && site.tag !== printedTag) continue;
    const literalLength = runs.reduce((sum, run) => sum + run.length, 0);
    // A message that is mostly placeholders would match anything; it can only match by tag.
    if (entry.text.replace(/[^a-z0-9]/g, '').length < 8) continue;
    if (pasted.length >= 8 && embedsInOrder(pasted, runs)) {
      scored.push({ match: { tag: site.tag, how: 'exact', site }, score: 3 + literalLength / 100000 });
      continue;
    }
    if (pasted.length >= 10) {
      const within = runs.find((run) => run.includes(pasted));
      // Copied from inside one stretch of text, or across placeholders the hook filled in.
      const covered = within ? pasted.length : fragmentCover(pasted, runs);
      if (covered >= 10 && covered / pasted.length >= 0.6) {
        scored.push({ match: { tag: site.tag, how: 'partial', site }, score: 2 + covered / pasted.length });
        continue;
      }
    }
    if (pastedWords.length >= 3) {
      const shared = pastedWords.filter((word) => entry.words.has(word));
      const ratio = shared.reduce((sum, word) => sum + weight(word), 0) / pastedWeight;
      if (shared.length >= 3 && ratio >= 0.6) scored.push({ match: { tag: site.tag, how: 'words', site }, score: ratio });
    }
  }
  scored.sort((a, b) => b.score - a.score);
  const seen = new Set<string>();
  const best = scored
    .filter(({ match }) => {
      const key = `${match.tag}|${match.site?.file}:${match.site?.line}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, MAX_MATCHES)
    .map(({ match }) => match);
  if (best.length === 0 && printedTag) return [{ tag: printedTag, how: 'gate', site: null }];
  return best;
}

/** The leading matches that are exactly as good as the first: the same kind of match on the
 * same printed text. Two gates or two call sites can print one message word for word, and then
 * only the gate ID at the start of the line tells them apart, so none of them is preferred. */
export function bestTier(matches: DecodedMatch[]): DecodedMatch[] {
  const [first] = matches;
  if (!first?.site) return first ? [first] : [];
  const key = (match: DecodedMatch) => (match.site ? match.site.message.split(PLACEHOLDER).map(compact).join('\u0000') : '');
  const firstKey = key(first);
  return matches.filter((match) => match.how === first.how && match.site !== null && key(match) === firstKey);
}
