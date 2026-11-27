/** render-scene.ts - draw one composition of a scene as a decorative SVG.
 *
 * The SVG is aria-hidden: the scene's ordered step list carries the same content for every
 * reader. Each drawn element is tagged with data-el and the step that reveals it, so the
 * player can light it up without knowing the model. Without the player every element is
 * simply drawn, which is the complete picture for print and no-script readers.
 */
import { escapeHtml, framePath } from "../machine/machine-render";
import { METRICS, noteHeight, pathLength, revealStep, type Layout, type Scene } from "./scene";

const num = (value: number) => String(Math.round(value * 100) / 100);

/** Step text as HTML: escaped, with `code` spans. No links, so a hidden step holds nothing focusable. */
export function inlineCode(text: string): string {
  return text
    .split(/(`[^`]+`)/)
    .map((segment) => (segment.startsWith("`") && segment.endsWith("`") && segment.length > 1 ? `<code>${escapeHtml(segment.slice(1, -1))}</code>` : escapeHtml(segment)))
    .join("");
}

export function renderSceneSvg(scene: Scene, layout: Layout): string {
  const { w, h } = scene.size[layout];
  const reveal = revealStep(scene);
  const from = (id: string) => reveal.get(id) ?? 0;
  const gridId = `ca-scene-grid-${scene.id}-${layout}`;
  const out: string[] = [];

  out.push(`<svg class="ca-scene__svg ca-scene__svg--${layout}" viewBox="0 0 ${w} ${h}" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg">`);
  out.push(`<defs><pattern id="${gridId}" width="24" height="24" patternUnits="userSpaceOnUse"><path class="ca-scene__gridline" d="M24 0H0V24" fill="none"/></pattern></defs>`);
  out.push(`<rect class="ca-scene__grid" width="${w}" height="${h}" fill="url(#${gridId})"/>`);

  out.push('<g class="ca-scene__edges">');
  for (const edge of scene.edges) {
    const d = escapeHtml(edge.path[layout]);
    out.push(`<path class="ca-scene__rail" d="${d}"/>`);
    out.push(`<path class="ca-scene__edge" data-el="${escapeHtml(edge.id)}" data-from-step="${from(edge.id)}" d="${d}" style="--len:${num(pathLength(edge.path[layout]))}"/>`);
  }
  out.push("</g>");

  out.push('<g class="ca-scene__nodes">');
  for (const node of scene.nodes) {
    const box = node.at[layout];
    const metric = layout === "wide" ? METRICS.label : METRICS.labelTall;
    const sub = layout === "wide" ? node.sub : undefined;
    const cx = box.x + box.w / 2;
    const cy = box.y + box.h / 2;
    const labelY = sub ? cy - 3 : cy + metric.size * 0.35;
    out.push(`<g class="ca-scene__node" data-el="${escapeHtml(node.id)}" data-from-step="${from(node.id)}" data-tone="${node.tone}">`);
    if (layout === "wide") out.push(`<text class="ca-scene__zone" x="${num(box.x + 2)}" y="${num(box.y - 11)}">${escapeHtml(node.zone)}</text>`);
    out.push(`<rect class="ca-scene__ring" x="${num(box.x)}" y="${num(box.y)}" width="${num(box.w)}" height="${num(box.h)}" rx="14"/>`);
    out.push(`<rect class="ca-scene__box" x="${num(box.x)}" y="${num(box.y)}" width="${num(box.w)}" height="${num(box.h)}" rx="14"/>`);
    out.push(`<svg class="ca-scene__glyph" x="${num(box.x + 16)}" y="${num(cy - METRICS.glyph / 2)}" width="${METRICS.glyph}" height="${METRICS.glyph}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round">${framePath(node.shape)}</svg>`);
    out.push(`<text class="ca-scene__label" x="${num(box.x + METRICS.textInset)}" y="${num(labelY)}" font-size="${metric.size}">${escapeHtml(node.label)}</text>`);
    if (sub) out.push(`<text class="ca-scene__sub" x="${num(box.x + METRICS.textInset)}" y="${num(cy + 15)}">${escapeHtml(sub)}</text>`);
    out.push("</g>");
  }
  out.push("</g>");

  if (layout === "wide" && scene.notes.length) {
    out.push('<g class="ca-scene__notes">');
    for (const note of scene.notes) {
      const annotation = note.kind === "annotation";
      const { padX, padY, size, line } = METRICS.note;
      out.push(`<g class="ca-scene__note${annotation ? " ca-scene__note--annotation" : ""}" data-el="${escapeHtml(note.id)}" data-from-step="${from(note.id)}" data-tone="${note.tone}">`);
      if (annotation) {
        out.push("<text>");
        note.lines.forEach((text, index) => {
          out.push(`<tspan x="${num(note.at.x)}" y="${num(note.at.y + METRICS.annotation.size + index * METRICS.annotation.line)}">${escapeHtml(text)}</tspan>`);
        });
        out.push("</text></g>");
        continue;
      }
      out.push(`<rect x="${num(note.at.x)}" y="${num(note.at.y)}" width="${num(note.at.w)}" height="${num(noteHeight(note.lines.length))}" rx="10"/>`);
      out.push("<text>");
      note.lines.forEach((text, index) => {
        out.push(`<tspan x="${num(note.at.x + padX)}" y="${num(note.at.y + padY + size - 2 + index * line)}">${escapeHtml(text)}</tspan>`);
      });
      out.push("</text></g>");
    }
    out.push("</g>");
  }

  out.push('<g class="ca-scene__token" data-token><circle class="ca-scene__token-halo" r="15"/><circle class="ca-scene__token-core" r="6"/></g>');
  out.push("</svg>");
  return out.join("");
}
