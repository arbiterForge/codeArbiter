import { describe, expect, it } from 'vitest';
import { rehypeTableShell } from '../scripts/rehype-table-shell';

type Node = { type?: string; tagName?: string; value?: string; properties?: Record<string, unknown>; children?: Node[] };
const text = (value: string): Node => ({ type: 'text', value });
const el = (tagName: string, children: Node[] = [], properties: Record<string, unknown> = {}): Node => ({ type: 'element', tagName, properties, children });
const guidePath = '/repo/site/src/content/docs/guides/review-and-ship.mdx';
const simple = (): Node => el('table', [el('thead', [el('tr', [el('th', [text('Intent')]), el('th', [text('Host entry')])])]), el('tbody', [el('tr', [el('td', [text('Read a PR')]), el('td', [el('code', [text('/ca:review #123')]), text(' then '), el('a', [text('inspect')], { href: '/reference/commands/review/' })])])])]);
const flatten = (node: Node): string => node.value ?? (node.children ?? []).map(flatten).join('');
function apply(table: Node, path = guidePath): Node {
  const tree = { type: 'root', children: [table] };
  (rehypeTableShell()() as (tree: Node, file: { path: string }) => void)(tree, { path });
  return tree;
}

describe('simple guide-table reflow', () => {
  it('adds labelled rows while preserving one native table and every original cell child', () => {
    const table = simple();
    const cell = table.children![1].children![0].children![1];
    const original = cell.children!;
    const tree = apply(table);
    expect(tree.children![0].properties?.className).toContain('ca-table-shell--stackable');
    expect(table.properties?.role).toBe('table');
    expect(table.properties?.dataCaTable).toBe('stacked');
    expect(cell.properties?.role).toBe('cell');
    expect(cell.children![0]).toMatchObject({ tagName: 'span', properties: { ariaHidden: 'true', dataPagefindIgnore: 'all' } });
    expect(flatten(cell.children![0])).toBe('Host entry');
    expect(cell.children![1].children).toEqual(original);
    expect(cell.children![1].children![2]).toBe(original[2]);
    const header = table.children![0].children![0].children![0];
    expect(header.properties).toMatchObject({ role: 'columnheader', scope: 'col' });
  });
  it('is idempotent, including labels and original content', () => {
    const tree = apply(simple()); const before = JSON.stringify(tree);
    (rehypeTableShell()() as (tree: Node, file: { path: string }) => void)(tree, { path: guidePath });
    expect(JSON.stringify(tree)).toBe(before);
  });
  it('handles normalized Windows paths without matching unrelated guide-like paths', () => {
    expect(apply(simple(), 'C:\\repo\\site\\src\\content\\docs\\guides\\example.md').children![0].properties?.className)
      .toContain('ca-table-shell--stackable');
    for (const path of ['/repo/site/src/content/docs/academy/example.md', '/repo/site/src/content/docs/reference/commands/review.md', '/repo/site/src/content/docs/guides-other/example.md']) {
      expect(apply(simple(), path).children![0].properties?.className).toEqual(['ca-table-shell']);
    }
  });
  it.each(['colSpan', 'rowSpan'])('keeps a %s table on its existing scroll path without guessing associations', property => {
    const table = simple(); table.children![1].children![0].children![0].properties = { [property]: 2 };
    expect(apply(table).children![0].properties?.className).toEqual(['ca-table-shell']);
    expect(table.properties?.role).toBeUndefined();
  });
  it('leaves incomplete, empty-header and multi-header structures unchanged', () => {
    for (const mode of ['missing', 'blank', 'multi']) {
      const table = simple();
      if (mode === 'missing') table.children![1].children![0].children!.pop();
      if (mode === 'blank') table.children![0].children![0].children![0].children = [text(' ')];
      if (mode === 'multi') table.children![0].children!.push(el('tr', [el('th', [text('More')])]));
      expect(apply(table).children![0].properties?.className).toEqual(['ca-table-shell']);
    }
  });
  it('does not overwrite authored header relationships or transform nested tables', () => {
    for (const mode of ['headers', 'scope', 'nested']) {
      const table = simple(); const cell = table.children![1].children![0].children![0];
      if (mode === 'nested') cell.children!.push(simple());
      else cell.properties = { [mode]: mode === 'scope' ? 'row' : 'custom-heading' };
      expect(apply(table).children![0].properties?.className).toEqual(['ca-table-shell']);
    }
  });
});
