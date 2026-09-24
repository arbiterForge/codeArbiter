import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { afterEach, describe, expect, it } from 'vitest';
import { loadProductExample } from '../../scripts/product-example';
import { loadThemeCaptures, terminalTokens } from '../../scripts/statusline-capture';

const temporary: string[] = [];
afterEach(() => { for (const path of temporary.splice(0)) rmSync(path, { recursive: true, force: true }); });
/** Copy the captured example so integrity tests cannot mutate checked-in files. */
function copy() {
  const root = mkdtempSync(join(tmpdir(), 'ca-product-fixture-'));
  temporary.push(root);
  cpSync('public/examples/saved-searches', root, { recursive: true });
  return root;
}
/** Update a scratch manifest to test a changed file beyond its digest check. */
function repin(root: string, path: string) {
  const manifest = JSON.parse(readFileSync(join(root, 'provenance.json'), 'utf8'));
  manifest.files[path] = createHash('sha256').update(readFileSync(join(root, path))).digest('hex');
  writeFileSync(join(root, 'provenance.json'), JSON.stringify(manifest));
}
/** Create an isolated renderer and matching Git source pin for capture tests. */
function rendererFixture() {
  const root = mkdtempSync(join(tmpdir(), 'ca-renderer-pin-')); temporary.push(root);
  const hooks = join(root, 'plugins/ca/hooks'); mkdirSync(hooks, { recursive: true });
  const renderer = join(hooks, 'statusline.py');
  const source = `from __future__ import annotations
from dataclasses import dataclass
import json, re, time
@dataclass
class Segment:
    label: str
ANSI = re.compile(r"\\x1b\\[[0-9;]*m")
def render(payload):
    return "stage:1 Review export"
def persist_sess_start(*args):
    raise AssertionError("unexpected write")
` + ['project_root', 'arbiter_state', 'current_mode', 'head_branch', 'git_dirty',
    'ledger_update', 'session_start', 'burn_spark', 'seg_update', 'seg_pr', 'seg_prune',
    'subagent_dir', 'read_subagents'].map((name) => `def ${name}(*args): return None\n`).join('');
  writeFileSync(renderer, source);
  // The fixture repository has no external remote, hooks, credentials, or network step.
  /** Execute a local Git command without hooks or external credentials. */
  function git(args: string[]) {
    const result = spawnSync('git', ['-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', ...args],
      { cwd: root, encoding: 'utf8', timeout: 10_000,
        env: { PATH: process.env.PATH, HOME: root, GIT_CONFIG_NOSYSTEM: '1',
          GIT_AUTHOR_NAME: 'Documentation fixture', GIT_AUTHOR_EMAIL: 'fixture@example.invalid',
          GIT_COMMITTER_NAME: 'Documentation fixture', GIT_COMMITTER_EMAIL: 'fixture@example.invalid' } });
    expect(result.error).toBeUndefined(); expect(result.status, result.stderr).toBe(0);
    return result.stdout.trim();
  }
  git(['init', '--quiet']); git(['add', '--', 'plugins/ca/hooks/statusline.py']); git(['commit', '--quiet', '-m', 'Pinned renderer fixture']);
  const commit = git(['rev-parse', 'HEAD']);
  const script = join(root, 'site/scripts/capture-statusline-themes.py'); mkdirSync(join(root, 'site/scripts'), { recursive: true });
  writeFileSync(script, readFileSync('scripts/capture-statusline-themes.py', 'utf8')
    .replace(/SOURCE_COMMIT = '[a-f0-9]{40}'/, `SOURCE_COMMIT = '${commit}'`));
  return { root, renderer, script, source, commit };
}

describe('honest product demonstrations', () => {
  it('binds the captured renderer itself to the recorded source pin', () => {
    const capture = JSON.parse(readFileSync('public/examples/statusline-themes.json', 'utf8'));
    const pinned = spawnSync('git', ['show', `${capture.source_commit}:${capture.renderer}`], { encoding: 'utf8', timeout: 10_000 });
    expect(pinned.error).toBeUndefined(); expect(pinned.status).toBe(0);
    const digest = createHash('sha256').update(pinned.stdout).digest('hex');
    expect(capture.renderer_sha256).toBe(digest);
    // Historical capture format stores this digest separately. The producer
    // regression below requires it in source_files for every new capture.
  });
  it('registers and accounts for a valid pinned renderer before capture', () => {
    const fixture = rendererFixture();
    const result = spawnSync('python', [fixture.script], { cwd: fixture.root, encoding: 'utf8', timeout: 30_000 });
    expect(result.error).toBeUndefined(); expect(result.status, result.stderr).toBe(0);
    const capture = JSON.parse(readFileSync(join(fixture.root, 'site/public/examples/statusline-themes.json'), 'utf8'));
    expect(capture.source_commit).toBe(fixture.commit);
    expect(capture.source_files[capture.renderer]).toBe(createHash('sha256').update(fixture.source).digest('hex'));
    expect(capture.captures).toHaveLength(5);
  });
  it('rejects an altered renderer before executing it or publishing a capture', () => {
    const fixture = rendererFixture();
    const marker = join(fixture.root, 'renderer-executed');
    writeFileSync(fixture.renderer, `from pathlib import Path\nPath(${JSON.stringify(marker)}).write_text('executed')\n` +
      fixture.source.replace('from __future__ import annotations\n', ''));
    const result = spawnSync('python', [fixture.script], { cwd: fixture.root, encoding: 'utf8', timeout: 30_000 });
    expect(result.error).toBeUndefined(); expect(result.status).not.toBe(0);
    expect(result.stderr).toContain('Renderer dependency changed: plugins/ca/hooks/statusline.py');
    expect(() => readFileSync(marker)).toThrow();
    expect(() => readFileSync(join(fixture.root, 'site/public/examples/statusline-themes.json'))).toThrow();
  });

  it('binds the secret-scanner exception to one exact public source digest', () => {
    const source = 'plugins/ca/hooks/hostapi.py';
    const digest = 'c6d86b81be1ed7ef2046183b23643d7e1e018e6c41b75ae9205b4077be9b02be';
    const capture = JSON.parse(readFileSync('public/examples/statusline-themes.json', 'utf8'));
    const result = spawnSync('git', ['show', `${capture.source_commit}:${source}`], { encoding: 'utf8', timeout: 10_000 });
    expect(result.error).toBeUndefined();
    expect(result.status).toBe(0);
    expect(createHash('sha256').update(result.stdout).digest('hex')).toBe(digest);
    expect(capture.source_files[source]).toBe(digest);
    const config = readFileSync('../.gitleaks.toml', 'utf8');
    expect(config).toContain(`regexes = ['\\A${digest}\\z']`);
    const exception = config.slice(config.lastIndexOf('[[allowlists]]'));
    expect(exception).not.toMatch(/^(?:paths|commits|stopwords|regexTarget)\s*=/m);
  });
  it('rejects a changed rendered view even when the embedded model is intact', () => {
    const root = copy(), path = 'specs/saved-searches.html';
    writeFileSync(join(root, path), readFileSync(join(root, path), 'utf8').replace('<title>', '<title>Altered '));
    expect(() => loadProductExample(root)).toThrow('capture digest mismatch');
  });
  it.each([
    '<script>alert(1)</script>',
    '<script>alert(1)</script >',
    '<ScRiPt>alert(1)</sCrIpT\t>',
    '<script>alert(1)',
    '<script/src=example.js>',
  ])('rejects extra script tokens even after repinning: %s', (extra) => {
    const root = copy(), path = 'plans/saved-searches.html';
    writeFileSync(join(root, path), readFileSync(join(root, path), 'utf8') + extra);
    repin(root, path);
    expect(() => loadProductExample(root)).toThrow('unexpected script');
  });
  it('requires the exact native-renderer model delimiter', () => {
    const root = copy(), path = 'specs/saved-searches.html';
    writeFileSync(join(root, path), readFileSync(join(root, path), 'utf8').replace('</script>', '</script >'));
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
