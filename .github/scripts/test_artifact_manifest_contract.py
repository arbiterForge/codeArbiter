"""Cross-consumer native manifest declarations; no receipt authentication claim."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'core/pysrc'))
from _artifactmanifestlib import parse_release_manifest


class ManifestContract(unittest.TestCase):
    def test_shared_declarations_and_negative_cases(self):
        fixtures=json.loads((ROOT/'.github/fixtures/artifact-release-manifest.json').read_text())['cases']
        for case in fixtures:
            with self.subTest(case=case['id']):
                raw=json.dumps(case['manifest'])
                if case['valid']:
                    self.assertEqual(parse_release_manifest(raw),case['manifest'])
                else:
                    with self.assertRaises(ValueError):parse_release_manifest(raw)

    def test_parser_bounds_utf8_bytes_before_parsing(self):
        raw = '"' + '\u00e9' * 33000 + '"'
        for data in (raw, raw.encode('utf-8')):
            with self.assertRaisesRegex(ValueError, 'bounded'): parse_release_manifest(data)

    def test_duplicate_keys_are_not_lost_before_shape_validation(self):
        raw='{"format":"first","format":"second"}'
        with self.assertRaisesRegex(ValueError,'duplicate'):parse_release_manifest(raw)

    def test_installed_contract_is_derived_from_canonical_source(self):
        subprocess.run([sys.executable,str(ROOT/'tools/build-artifact-manifest-contract.py'),'--check'],check=True)


if __name__=='__main__':unittest.main()
