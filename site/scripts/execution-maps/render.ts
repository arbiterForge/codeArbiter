import type { ExecutionMap, MapChapter, Role } from './model';
import { validateExecutionMap } from './model';

const W = 900;
const H = 456;
const FONT = 'Manrope Variable, Segoe UI, Arial, sans-serif';
const MONO = 'JetBrains Mono Variable, Consolas, Cascadia Mono, monospace';
const rows: Record<Role, { y: number; title: string; color: string }> = {
  command: { y: 120, title: 'Commands', color: '#f0b92f' },
  skill: { y: 252, title: 'Skills', color: '#7ab7ff' },
  agent: { y: 384, title: 'Agents', color: '#58d68d' },
};

/** All authored strings are text, never an HTML/SVG fragment. */
const xml = (value: string) => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;').replaceAll('"', '&quot;');

/** Bound every label for the site's existing conservative font-metric audit. */
function text(x: number, y: number, value: string, width: number, size = 18,
  color = '#f6f7f9', mono = false, anchor = 'start'): string {
  return `<text x="${x}" y="${y}" font-family="${mono ? MONO : FONT}" font-size="${size}" font-weight="${mono ? 600 : 650}" fill="${color}" text-anchor="${anchor}" data-max-width="${width}"${size < 14 ? ' data-label-kind="annotation"' : ''}>${xml(value)}</text>`;
}

/** Render a chapter with left-to-right order crossing the three role rows. */
export function renderChapterSvg(chapter: MapChapter, namespace: string, offset = 0): string {
  if (!/^[a-zA-Z][a-zA-Z0-9-]*$/.test(namespace)) throw new Error('Invalid SVG namespace');
  const nodes = chapter.nodes.map((node, index) => ({ node, x: 130 + index * (chapter.nodes.length > 1 ? 567 / (chapter.nodes.length - 1) : 0), y: rows[node.role].y }));
  const content: string[] = [];
  for (const { y, title, color } of Object.values(rows)) {
    content.push(`<rect x="12" y="${y - 54}" width="876" height="108" rx="10" fill="#0e141c"/>`);
    content.push(`<path d="M118 ${y}H874" fill="none" stroke="#273647" stroke-dasharray="3 6"/>`);
    content.push(text(24, y + 5, title, 91, 14, color));
  }
  for (const edge of chapter.edges) {
    const start = nodes.find(node => node.node.id === edge.from)!;
    const end = nodes.find(node => node.node.id === edge.to)!;
    // A 9-unit head needs a straight approach longer than the head itself.
    // Stroke-scaled markers previously overlaid the vertical elbow like a flag.
    const x1 = start.x + 169; const x2 = end.x - 2; const mid = x2 - 13;
    content.push(`<path data-map-edge="${xml(edge.from)}:${xml(edge.to)}" data-relation="${edge.kind}" d="M${x1} ${start.y}H${mid}V${end.y}H${x2}" fill="none" stroke="#f0b92f" stroke-width="2.5" stroke-linejoin="round"${edge.kind === 'reuse' ? ' stroke-dasharray="5 4"' : ''} marker-end="url(#${namespace}-arrow)"><title>${xml(edge.label + ': ' + edge.detail)}</title></path>`);
  }
  nodes.forEach(({ node, x, y }, index) => {
    const lines = node.label;
    const firstY = y + 8 - (lines.length - 1) * 11;
    content.push(`<g data-map-node="${xml(node.id)}" data-role="${node.role}"><title>${xml(node.title + '. ' + node.detail)}</title>`);
    content.push(`<rect x="${x}" y="${y - 44}" width="169" height="88" rx="10" fill="#121a24" stroke="${rows[node.role].color}" stroke-width="1.7"${node.conditional ? ' stroke-dasharray="5 4"' : ''}/>`);
    content.push(text(x + 13, y - 24, String(offset + index + 1).padStart(2, '0') + (node.conditional ? ' · if applicable' : ''), 147, 12, rows[node.role].color, true));
    lines.forEach((line, lineIndex) => content.push(text(x + 84.5, firstY + lineIndex * 22, line, 153, 18, '#f6f7f9', false, 'middle')));
    content.push('</g>');
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" role="img" data-diagram-system="ca-v2" data-execution-chapter="${xml(chapter.id)}">
<title>${xml(chapter.title)}</title><desc>${xml(chapter.nodes.map(node => `${node.role}: ${node.title}`).join(' → ') + '. ' + chapter.output)}</desc>
<defs><marker id="${namespace}-arrow" markerUnits="userSpaceOnUse" viewBox="0 0 9 8" markerWidth="9" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0 0L9 4L0 8Z" fill="#f0b92f"/></marker></defs>
<rect x="1" y="1" width="898" height="454" rx="14" fill="#090d12" stroke="#3a4c60"/>
${text(24, 35, chapter.title, 760, 20)}
${content.join('\n')}
${text(24, 443, 'Order → across rows. Full step names, results and conditions are in the reading view.', 852, 12, '#91a0b2', true)}
</svg>`;
}

/** Labels for a whole-map asset, separate from its authoritative editorial content. */
export interface MapPresentation { kicker: string; summary: string; endpoint: string }

/** Shared numbering also works when a chapter has fewer than four stages. */
export function chapterOffset(map: ExecutionMap, index: number): number {
  return map.chapters.slice(0, index).reduce((count, chapter) => count + chapter.nodes.length, 0);
}

/** Keep public image URLs; the static image and ordered reading use the same model. */
export function renderExecutionSvg(map: ExecutionMap, presentation?: MapPresentation): string {
  const failures = validateExecutionMap(map);
  if (failures.length) throw new Error(failures.join('; '));
  const height = 104 + map.chapters.length * (H + 70);
  const chapters = map.chapters.map((chapter, index) => {
    const y = 94 + index * (H + 70);
    const plot = renderChapterSvg(chapter, `asset-${map.id}-${chapter.id}`, chapterOffset(map, index))
      .replace('<svg ', `<svg x="0" y="${y}" width="900" height="456" `);
    const next = map.chapters[index + 1];
    const bridge = next ? `Continue ↓ ${next.title}` : presentation?.endpoint ?? 'Outcome: open PR. Merge and release require their own decisions.';
    return plot + '\n' + text(24, y + H + 36, bridge, 852, 18, '#ffd568');
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${height}" role="img" data-diagram-system="ca-v2" data-execution-map="${xml(map.id)}">
<title>${xml(map.title)}</title><desc>${xml(map.boundary + ' Actual endpoint: ' + map.outcome)} Conditions and return paths remain in the companion reading view.</desc>
<rect width="900" height="${height}" fill="#090d12"/>
${text(24, 35, presentation?.kicker ?? 'FEATURE • COMMANDS / SKILLS / AGENTS', 852, 14, '#f0b92f', true)}
${text(24, 70, presentation?.summary ?? 'Definition → task loop → scope acceptance → PR handoff', 852, 20)}
${chapters.join('\n')}
</svg>\n`;
}

/** Two initialization alternatives, deliberately without a connector between them. */
export function renderAlternativeMaps(entries: Array<{ map: ExecutionMap; presentation: MapPresentation }>): string {
  if (entries.length !== 2) throw new Error('Initialization requires two independent alternatives');
  let y = 112;
  const parts = entries.map(({ map, presentation }, index) => {
    const height = 104 + map.chapters.length * (H + 70);
    const diagram = renderExecutionSvg(map, presentation)
      .replace('<svg ', `<svg x="0" y="${y + 42}" width="900" height="${height}" `);
    const label = text(24, y + 20, `Alternative ${index + 1}: ${map.title}`, 852, 20, '#ffd568');
    y += height + 82;
    return label + '\n' + diagram;
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 ${y}" role="img" data-diagram-system="ca-v2" data-workflow-alternatives="initialization">
<title>Initialize one repository: choose the matching route</title>
<desc>Greenfield and brownfield are alternatives, not consecutive phases. Each has its own entry, scope and terminal result. Read the companion guide for conditions and all output details.</desc>
<rect width="900" height="${y}" fill="#090d12"/>
${text(24, 38, 'INITIALIZATION • TWO ALTERNATIVES, NOT ONE SEQUENCE', 852, 14, '#f0b92f', true)}
${text(24, 74, 'New project: interview. Existing source: isolated evidence collection.', 852, 20)}
${parts.join('\n')}
</svg>\n`;
}
