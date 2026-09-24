/** Keep native table markup; simple authored-guide tables can also reflow by row.
 * The default scroll shell remains for reference, Academy and complex tables.
 * This build-time transform changes presentation, not content or host behavior.
 */
interface HastNode {
  type?: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

function classNames(node: HastNode): string[] {
  const value = node.properties?.className;
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === 'string');
  return typeof value === 'string' ? value.split(/\s+/) : [];
}

function elements(node: HastNode): HastNode[] {
  return (node.children ?? []).filter(child => child.type === 'element');
}

function plainText(node: HastNode): string {
  return node.type === 'text' ? node.value ?? '' : (node.children ?? []).map(plainText).join('');
}

/** Require unambiguous single-row column headers; do not guess complex associations. */
function simpleRows(table: HastNode): { headings: HastNode[]; bodies: HastNode[] } | undefined {
  const parts = elements(table);
  if (parts.length !== 2 || parts[0].tagName !== 'thead' || parts[1].tagName !== 'tbody') return;
  const headerRows = elements(parts[0]);
  if (headerRows.length !== 1 || headerRows[0].tagName !== 'tr') return;
  const headings = elements(headerRows[0]);
  if (headings.length < 2 || headings.some(cell => cell.tagName !== 'th' || !plainText(cell).trim())) return;
  const bodies = elements(parts[1]);
  if (!bodies.length || bodies.some(row => row.tagName !== 'tr' || elements(row).length !== headings.length ||
      elements(row).some(cell => cell.tagName !== 'td'))) return;
  const ambiguous = (node: HastNode): boolean => {
    const props = node.properties ?? {};
    return ['colSpan', 'rowSpan', 'headers', 'scope', 'role'].some(key => props[key] !== undefined) ||
      elements(node).some(child => child.tagName === 'table' || ambiguous(child));
  };
  if (ambiguous(table)) return;
  return { headings, bodies };
}

/** One content tree serves both views; visible mobile labels are not duplicate AT/search text. */
function addRowLabels(table: HastNode): boolean {
  const shape = simpleRows(table);
  if (!shape) return false;
  table.properties = { ...table.properties, role: 'table', dataCaTable: 'stacked' };
  for (const section of elements(table)) {
    section.properties = { ...section.properties, role: 'rowgroup' };
    for (const row of elements(section)) row.properties = { ...row.properties, role: 'row' };
  }
  shape.headings.forEach(heading => {
    heading.properties = { ...heading.properties, role: 'columnheader', scope: 'col' };
  });
  for (const row of shape.bodies) {
    elements(row).forEach((cell, column) => {
      cell.properties = { ...cell.properties, role: 'cell' };
      const original = cell.children ?? [];
      cell.children = [
        { type: 'element', tagName: 'span', properties: {
          className: ['ca-table-cell-label'], ariaHidden: 'true', dataPagefindIgnore: 'all',
        }, children: [{ type: 'text', value: plainText(shape.headings[column]).trim() }] },
        { type: 'element', tagName: 'div', properties: { className: ['ca-table-cell-value'] }, children: original },
      ];
    });
  }
  return true;
}

function wrapTables(node: HastNode, guide: boolean): void {
  if (!Array.isArray(node.children)) return;
  for (let index = 0; index < node.children.length; index++) {
    const child = node.children[index];
    const alreadyWrapped = classNames(node).includes('ca-table-shell');
    if (child.type === 'element' && child.tagName === 'table' && !alreadyWrapped) {
      const stackable = guide && addRowLabels(child);
      node.children[index] = {
        type: 'element', tagName: 'div',
        properties: { className: ['ca-table-shell', ...(stackable ? ['ca-table-shell--stackable'] : [])] },
        children: [child],
      };
      continue;
    }
    wrapTables(child, guide);
  }
}

/** Astro supplies the source VFile for both Markdown and MDX, including subpath builds. */
export function rehypeTableShell() {
  return () => (tree: HastNode, file?: { path?: string }) => {
    const path = file?.path?.replaceAll('\\', '/') ?? '';
    const guide = /(?:^|\/)src\/content\/docs\/guides\/[^/]+\.mdx?$/.test(path);
    wrapTables(tree, guide);
  };
}
