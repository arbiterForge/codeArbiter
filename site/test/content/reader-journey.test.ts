import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const routes = ['opt-in-a-repo', 'feature-lane', 'autonomous-sprints'];
const component = readFileSync(join(process.cwd(), 'src/components/ReaderJourney.astro'), 'utf8');

describe('reader-first workflow contract', () => {
  for (const route of routes) {
    const source = readFileSync(join(process.cwd(), `src/content/docs/guides/${route}.mdx`), 'utf8');
    const match = source.match(/steps=\{(\[[\s\S]*?\])\}/);
    const steps = match ? JSON.parse(match[1]) : [];
    it(`${route} retains its route, diagram and four actionable reading steps`, () => {
      expect(existsSync(join(process.cwd(), `src/content/docs/guides/${route}.md`))).toBe(false);
      expect(steps).toHaveLength(4);
      for (const step of steps) {
        for (const field of ['actor', 'title', 'artifact', 'review', 'href', 'linkLabel']) {
          expect(step[field], `${route}: ${field}`).toBeTruthy();
        }
        const path = step.href.split('#')[0].replace(/^\//, '').replace(/\/$/, '');
        expect(['.md', '.mdx'].some(extension => existsSync(join(process.cwd(), `src/content/docs/${path}${extension}`))), step.href).toBe(true);
      }
      expect(source.indexOf('<ReaderJourney')).toBeLessThan(source.indexOf('<details class="ca-implementation-view">'));
      expect(source).toMatch(/<details class="ca-implementation-view">[\s\S]*<figure class="ca-diagram">[\s\S]*<\/figure>\s*<\/details>/);
    });
  }
  it('does not represent numbered steps as proof or progress', () => {
    expect(component).toContain('Reading map, not a captured run or live status');
    expect(component).not.toMatch(/localStorage|fetch\(|aria-valuenow|role="progressbar"|<script/);
    expect(component).toContain('import.meta.env.BASE_URL');
  });
  it('pairs shared reader-map tokens in forced colors without disabling user colors', () => {
    const forced = component.split('@media (forced-colors: active)')[1].split('@media print')[0];
    for (const token of ['--ca-brand-bright', '--ca-ink', '--ca-ink-soft', '--ca-ink-muted', '--ca-line-strong']) {
      expect(forced).toContain(`${token}: CanvasText;`);
    }
    expect(forced).toContain('--ca-bg-panel: Canvas;');
    expect(forced).toContain('.ca-reader-journey h2, .ca-reader-journey h3 { color: CanvasText; }');
    expect(forced).toContain('.ca-reader-journey__step > a { color: LinkText; }');
    expect(component).not.toContain('forced-color-adjust: none');
  });
  it('uses one direct-child spacing contract without globally resetting prose', () => {
    const css = readFileSync(join(process.cwd(), 'src/styles/design-system.css'), 'utf8');
    expect(css).toMatch(/\[data-ca-layout="peers"\] > \*\s*\{\s*margin-block: 0;\s*min-inline-size: 0;/);
    for (const file of ['TrustRow', 'AcademyOverview', 'AcademyLesson', 'ArtifactWorkbench', 'DeliveryStory', 'ProjectBlueprint', 'ExampleChoices']) {
      expect(readFileSync(join(process.cwd(), `src/components/${file}.astro`), 'utf8')).toContain('data-ca-layout="peers"');
    }
  });
});
