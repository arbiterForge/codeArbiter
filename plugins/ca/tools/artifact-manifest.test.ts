import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { parseArtifactReleaseManifest } from './artifact-manifest.ts';

const fixtures = JSON.parse(readFileSync(new URL('../../../.github/fixtures/artifact-release-manifest.json', import.meta.url),'utf8'));
describe('shared native manifest declarations', () => {
  for (const fixture of fixtures.cases) {
    it(fixture.id, () => {
      const read=()=>parseArtifactReleaseManifest(JSON.stringify(fixture.manifest));
      if (fixture.valid) expect(read()).toEqual(fixture.manifest);
      else expect(read).toThrow();
    });
  }
  it('bounds UTF-8 bytes before parsing',()=>{
    expect(()=>parseArtifactReleaseManifest(JSON.stringify('\u00e9'.repeat(33000)))).toThrow('bounded');
  });
  it('rejects duplicate and escaped-duplicate keys',()=>{
    expect(()=>parseArtifactReleaseManifest('{"format":"a","format":"b"}')).toThrow('duplicate');
    expect(()=>parseArtifactReleaseManifest('{"format":"a","for\\u006dat":"b"}')).toThrow('duplicate');
  });
});
