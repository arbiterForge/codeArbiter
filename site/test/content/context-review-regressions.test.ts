import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

/** These checks reproduce the two final review findings without changing helper authority. */
describe('context capture and shared-exhibit review regressions', () => {
  it('retains exact observed hashes when unspecified text writes use CRLF', () => {
    // Emulate only Path.write_text's platform default, not a Windows runtime.
    // The actual helpers, Git hashes, fixture writes and stored observations still run.
    const script = String.raw`
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

path = Path('scripts/capture-context-examples.py').resolve()
spec = importlib.util.spec_from_file_location('capture_review_check', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original_write = Path.write_text
writes = []

def platform_write(self, data, encoding=None, errors=None, newline=None):
    """Use CRLF only where the caller leaves newline policy to the platform."""
    writes.append((self.name, newline))
    return original_write(self, data, encoding=encoding, errors=errors,
                          newline='\r\n' if newline is None else newline)

with patch.object(Path, 'write_text', platform_write):
    actual = module.capture()
expected = json.loads(Path('src/data/context-examples.json').read_text(encoding='utf-8'))
assert actual == expected, (actual['changed_source_hashes'], expected['changed_source_hashes'])
assert [newline for name, newline in writes if name == 'package.json'] == ['\n', '\n'], writes
print('Explicit LF survives the CRLF-default simulation; complete observations match.')
`;
    expect(execFileSync('python3', ['-c', script], { encoding: 'utf8', timeout: 20000 }))
      .toContain('complete observations match');
  });

  it('links both embeddings to the actual typed-advice section, not an assumed section below', () => {
    const component = readFileSync('src/components/ContextExplorer.astro', 'utf8');
    expect(component).toContain('href={`${base}/concepts/jit-context-injection/#when-html-advice-reports-a-problem`}');
    expect(component).toContain('HTML advice diagnostics</a>');
    expect(component).not.toContain('is explained below');
    const jit = readFileSync('src/content/docs/concepts/jit-context-injection.mdx', 'utf8');
    expect(jit).toContain('## When HTML advice reports a problem');
    for (const slug of ['jit-context-injection', 'provenance-drift']) {
      expect(readFileSync(`src/content/docs/concepts/${slug}.mdx`, 'utf8')).toContain('<ContextExplorer');
    }
  });
});
