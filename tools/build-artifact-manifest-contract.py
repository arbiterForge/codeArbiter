"""Embed the canonical manifest contract in installed Python helpers."""
import ast
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from owned_output import assert_complete, publish_files

ROOT = Path(__file__).resolve().parents[1]
def main():
    assert_complete(ROOT, "artifact-manifest-contract")
    source = json.loads((ROOT/'core/artifact-release-manifest.json').read_text(encoding='utf-8'))
    if source.get('contract') != 'codearbiter.native-manifest-contract/1':
        raise ValueError('unsupported manifest contract')
    path = ROOT/'core/pysrc/_artifactmanifestlib.py'
    text = path.read_text(encoding='utf-8')
    before, tail = text.split('# BEGIN GENERATED MANIFEST CONTRACT\n',1)
    _, after = tail.split('# END GENERATED MANIFEST CONTRACT',1)
    generated = before + '# BEGIN GENERATED MANIFEST CONTRACT\n_CONTRACT_JSON = ' + repr(json.dumps(source,sort_keys=True,separators=(',',':'))) + '\n# END GENERATED MANIFEST CONTRACT' + after
    if '--check' in sys.argv:
        if text != generated:
            raise ValueError('native manifest contract embedding is stale')
    elif text != generated:
        ast.parse(generated)
        publish_files(ROOT, "artifact-manifest-contract", {path: generated.encode('utf-8')})
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
