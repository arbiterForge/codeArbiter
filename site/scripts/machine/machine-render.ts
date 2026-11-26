/** machine-render.ts - text and frame rendering shared by the static machine page and its viewer.
 *
 * Pure string functions with no Node or DOM dependency, so the build-time page
 * and the browser viewer render identical markup from the same model.
 */

/** Frame shapes: the shape says what kind of thing a part is (see the key in machine-data/key.json). */
const FRAME_PATHS: Record<string, string> = {
  circle: '<circle cx="8" cy="8" r="6"/>',
  square: '<rect x="2.25" y="2.25" width="11.5" height="11.5" rx="2.6"/>',
  shield: '<path d="M8 1.7 13.5 3.7V8c0 3.1-2.3 5.2-5.5 6.3C4.8 13.2 2.5 11.1 2.5 8V3.7Z"/>',
  hex: '<path d="M8 1.6 13.55 4.8v6.4L8 14.4 2.45 11.2V4.8Z"/>',
  chevron: '<path d="M2 3.3h7.7L14 8l-4.3 4.7H2L5.3 8Z"/>',
  doc: '<path d="M3.3 1.8H10l2.7 2.7v9.7H3.3Z"/><path d="M10 1.8v2.7h2.7" fill="none"/>',
  rect: '<rect x="1.8" y="3.6" width="12.4" height="8.8" rx="1.3"/>',
  diamond: '<path d="M8 1.5 14.5 8 8 14.5 1.5 8Z"/>',
  dashed: '<circle cx="8" cy="8" r="6" stroke-dasharray="2.2 2.1"/>',
};

/** A decorative frame icon; the part's name beside it carries the meaning for assistive technology. */
export function frameSvg(shape: string, className = "ca-machine__frame"): string {
  const path = FRAME_PATHS[shape] ?? FRAME_PATHS.square;
  return `<svg class="${className}" viewBox="0 0 16 16" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round">${path}</svg>`;
}

export const FRAME_SHAPES = Object.keys(FRAME_PATHS);

export function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** A command in one host's spelling, from that host's `command_form` in core/hosts.json. */
export function spellCommand(form: string, name: string, args = ""): string {
  const spelled = form.replace("{name}", name);
  return args.trim() ? `${spelled} ${args.trim()}` : spelled;
}

export interface RenderOptions {
  /** The site base path without a trailing slash ("" on the apex domain). */
  base: string;
  /** The host command form used for {{command}} placeholders, such as "/ca:{name}". */
  form: string;
}

const SEGMENT = /(`[^`]+`|\{\{[a-z][a-z-]*(?:\s[^}]*)?\}\})/;

/** Render one model string: escaped text, `code` spans, {{command}} placeholders and linked gate IDs. */
export function renderText(text: string, { base, form }: RenderOptions): string {
  return text.split(SEGMENT).map((segment, index) => {
    if (index % 2 === 0) {
      return escapeHtml(segment).replace(/\bH-\d{2}[a-z]?\b/g, (tag) => `<a href="${base}/reference/hooks-gates/#${tag.toLowerCase()}">${tag}</a>`);
    }
    if (segment.startsWith("`")) return `<code>${escapeHtml(segment.slice(1, -1))}</code>`;
    const [, name, args = ""] = /^\{\{([a-z][a-z-]*)((?:\s[^}]*)?)\}\}$/.exec(segment)!;
    return `<code class="ca-machine__cmd" data-cmd="${name}" data-args="${escapeHtml(args.trim())}">${escapeHtml(spellCommand(form, name, args))}</code>`;
  }).join("");
}
