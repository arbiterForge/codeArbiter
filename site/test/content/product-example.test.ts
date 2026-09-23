import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { afterEach, describe, expect, it } from 'vitest';
import { loadProductExample } from '../../scripts/product-example';
import { loadThemeCaptures, terminalTokens } from '../../scripts/statusline-capture';

const temporary: string[] = [];
afterEach(() => { for (const path of temporary.splice(0)) rmSync(path, { recursive: true, force: true }); });
function copy() {
  const root = mkdtempSync(join(tmpdir(), 'ca-product-fixture-'));
  temporary.push(root);
  cpSync('public/examples/saved-searches', root, { recursive: true });
  return root;
}
function repin(root: string, path: string) {
  const manifest = JSON.parse(readFileSync(join(root, 'provenance.json'), 'utf8'));
  manifest.files[path] = createHash('sha256').update(readFileSync(join(root, path))).digest('hex');
  writeFileSync(join(root, 'provenance.json'), JSON.stringify(manifest));
}
describe('honest product demonstrations', () => {
  it('rejects a changed rendered view even when the embedded model is intact', () => {
    const root = copy(), path = 'specs/saved-searches.html';
    writeFileSync(join(root, path), readFileSync(join(root, path), 'utf8').replace('<title>', '<title>Altered '));
    expect(() => loadProductExample(root)).toThrow('capture digest mismatch');
  });
  it('rejects extra script content even if the capture manifest is updated', () => {
    const root = copy(), path = 'plans/saved-searches.html';
    writeFileSync(join(root, path), readFileSync(join(root, path), 'utf8') + '<script>alert(1)</script>');
    repin(root, path);
    expect(() => loadProductExample(root)).toThrow('unexpected script');
  });
  it('requires the negative authority and eligibility results', () => {
    const root = copy(), path = 'native-validation.json';
    const data = JSON.parse(readFileSync(join(root, path), 'utf8'));
    data.plans_approved.result.valid = true;
    writeFileSync(join(root, path), JSON.stringify(data)); repin(root, path);
    expect(() => loadProductExample(root)).toThrow('approval refusal');
  });
  it('does not accept extra or missing capture paths', () => {
    const root = copy(), manifest = JSON.parse(readFileSync(join(root, 'provenance.json'), 'utf8'));
    manifest.files['../unrelated'] = '0'.repeat(64);
    writeFileSync(join(root, 'provenance.json'), JSON.stringify(manifest));
    expect(() => loadProductExample(root)).toThrow('inventory');
  });
  it.each([['baseline.py', 1, 'FAILED (failures=2)'], ['completed.py', 0, 'OK']] as const)('executes the actual %s example', (source, status, expected) => {
    const root = mkdtempSync(join(tmpdir(), 'ca-example-python-')); temporary.push(root);
    cpSync(`examples/saved-searches/${source}`, join(root, 'export_csv.py'));
    cpSync('examples/saved-searches/test_export_csv.py', join(root, 'test_export_csv.py'));
    const result = spawnSync('python', ['-m', 'unittest', '-v', 'test_export_csv'], { cwd: root, encoding: 'utf8', timeout: 30_000 });
    expect(result.error).toBeUndefined(); expect(result.status).toBe(status);
    expect(result.stderr).toContain('Ran 3 tests'); expect(result.stderr).toContain(expected);
    expect(result.stderr).not.toContain('ERROR');
  });
  it('keeps public source copies identical to the generator inputs', () => {
    for (const file of ['baseline.py', 'completed.py', 'test_export_csv.py', 'spec.request.json', 'plan.request.json']) {
      expect(readFileSync(`public/examples/saved-searches/${file}`, 'utf8')).toBe(readFileSync(`examples/saved-searches/${file}`, 'utf8'));
    }
  });
  it('renders different actual palettes without changing the terminal text', () => {
    const captures = loadThemeCaptures().captures;
    const texts = captures.map((capture) => capture.tokens.map((token) => token.text).join(''));
    expect(new Set(texts).size).toBe(1);
    expect(new Set(captures.map((capture) => capture.ansi)).size).toBe(5);
    expect(texts[0]).toContain('Review export'); expect(texts[0]).toContain('stage:1');
  });
  it('refuses escape sequences and invalid colors outside the capture grammar', () => {
    expect(() => terminalTokens('\u001b]0;bad\u0007')).toThrow();
    expect(() => terminalTokens('\u001b[38;2;999;0;0mtext')).toThrow('Invalid RGB');
    expect(() => terminalTokens('x'.repeat(100_001))).toThrow('bound');
    expect(terminalTokens('<img src=x onerror=alert(1)>')[0].text).toBe('<img src=x onerror=alert(1)>');
  });
});
