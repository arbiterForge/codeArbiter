#!/usr/bin/env python3
"""Regenerate unapproved documentation fixtures with an explicitly supplied native engine.

This authoring tool operates only in disposable temporary repositories. It is not
an installed-product engine selector or a public codeArbiter command. No approval
operation, provider call, tag, publication, or real project mutation is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SITE = Path(__file__).resolve().parents[1]
SOURCE = SITE / 'examples' / 'saved-searches'
OUTPUT = SITE / 'public' / 'examples' / 'saved-searches'
PROTOCOL = 'codearbiter.artifact-api/0.1.0'
EXPECTED_ENGINE_SHA256 = '77c8671c8bfc34f09edadea3a81182698ebcfa97997bbc9e93bb391ef7f8dd1d'
SOURCE_COMMIT = 'b41d9803eacb3acf4b93c8bec81e1aa2f086aec7'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def generate(engine):
    if not engine.is_file():
        raise ValueError('Supply an existing native engine built from the declared source.')
    if digest(engine) != EXPECTED_ENGINE_SHA256:
        raise ValueError('Engine differs from the reviewed hosted build; review and update its provenance before recapture.')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ca-doc-example-') as temporary:
        work = Path(temporary)
        subprocess.run(['git', 'init', '-q', str(work)], check=True)

        def call(operation, request, expect_ok=True):
            result = subprocess.run([str(engine), operation, '--root', str(work), '--request', '-'],
                                    input=json.dumps({'protocol': PROTOCOL, **request}), text=True,
                                    capture_output=True, timeout=30)
            envelope = json.loads(result.stdout)
            if expect_ok and (result.returncode != 0 or not envelope.get('ok')):
                raise RuntimeError(f'{operation}: {envelope}')
            return envelope

        capabilities = call('capabilities', {})
        spec = json.loads((SOURCE / 'spec.request.json').read_text())
        call('create', spec)
        identity = call('identity', {'artifact_id': spec['artifact_id']})
        plan = json.loads((SOURCE / 'plan.request.json').read_text())
        plan['normative']['spec_ref'] = {'artifact_id': spec['artifact_id'],
            'normative_sha256': identity['result']['normative_sha256'], 'binding_mode': 'draft_preview'}
        call('create', plan)
        receipts = {}
        for request, kind in [(spec, 'specs'), (plan, 'plans')]:
            for gate in ['structural', 'ready']:
                result = call('validate', {'artifact_id': request['artifact_id'], 'gate': gate})
                if not result['result'].get('valid'):
                    raise RuntimeError(f'{kind} {gate}: {result}')
                receipts[f'{kind}_{gate}'] = result
            approved = call('validate', {'artifact_id': request['artifact_id'], 'gate': 'approved'}, expect_ok=False)
            if approved['result'].get('valid'):
                raise RuntimeError('Documentation fixtures must remain unapproved')
            receipts[f'{kind}_approved'] = approved
            target = OUTPUT / kind / 'saved-searches.html'
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(work / '.codearbiter' / kind / 'saved-searches.html', target)
        eligibility = call('eligible', {'artifact_id': plan['artifact_id']}, expect_ok=False)
        if eligibility.get('ok'):
            raise RuntimeError('Unapproved plan must not be executable')
        receipts['draft_eligibility'] = eligibility
        write_json(OUTPUT / 'native-validation.json', receipts)

    runs = {}
    for phase, filename in [('red', 'baseline.py'), ('green', 'completed.py')]:
        with tempfile.TemporaryDirectory(prefix='ca-doc-test-') as temporary:
            work = Path(temporary)
            shutil.copyfile(SOURCE / filename, work / 'export_csv.py')
            shutil.copyfile(SOURCE / 'test_export_csv.py', work / 'test_export_csv.py')
            result = subprocess.run([sys.executable, '-m', 'unittest', '-v', 'test_export_csv'],
                                    cwd=work, capture_output=True, text=True, timeout=30)
            output = result.stderr.replace(str(work), '<fixture-root>')
            expected = 1 if phase == 'red' else 0
            if result.returncode != expected or 'Ran 3 tests' not in output or 'ERROR' in output:
                raise RuntimeError(f'Unexpected {phase} result: {output}')
            runs[phase] = {'argv': ['python', '-m', 'unittest', '-v', 'test_export_csv'],
                           'exit_code': result.returncode, 'output': output,
                           'implementation_sha256': digest(SOURCE / filename),
                           'test_sha256': digest(SOURCE / 'test_export_csv.py')}
    write_json(OUTPUT / 'test-runs.json', runs)
    for filename in ['baseline.py', 'completed.py', 'test_export_csv.py', 'spec.request.json', 'plan.request.json']:
        shutil.copyfile(SOURCE / filename, OUTPUT / filename)
    files = {str(path.relative_to(OUTPUT)): digest(path) for path in sorted(OUTPUT.rglob('*'))
             if path.is_file() and path.name != 'provenance.json'}
    write_json(OUTPUT / 'provenance.json', {
        'schema_version': 1, 'authority': 'unapproved documentation fixture',
        'source': f'arbiterForge/codeArbiter@{SOURCE_COMMIT}:core/artifacts',
        'source_commit': SOURCE_COMMIT, 'engine_sha256': digest(engine),
        'engine_build': {'workflow_run_id': 35814529881, 'commit': '8f6d39f181be6a55e10c4caa4b329d73d31b9de2', 'artifact_tree': 'a53ea9fcd574f219c184f39e0e66f9e4e2890242', 'toolchain': 'go1.27.1 linux/amd64', 'note': 'The compiled core/artifacts tree equals the source_commit tree; preparation workflow only differs.'},
        'capabilities': capabilities['result'], 'files': files,
        'evidence_boundary': 'Native create/validate and actual local Python tests only. No host dispatch, human approval, authenticated actor, workflow task acceptance, commit gate, or published release is demonstrated.',
        'runtime': {'python': sys.version.split()[0]},
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', required=True, type=Path)
    args = parser.parse_args()
    generate(args.engine.resolve())
