#!/usr/bin/env python3
"""Original isolated component assertions; never Pages tar or served-site authority."""
from __future__ import annotations
import argparse
import copy
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import zipfile

import major_readiness as owner
import major_qualification_report as reports
import site_playwright_observation as browser
import site_vitest_observation as source

ROOT = Path(__file__).resolve().parents[2]
JOB = browser.JOB
PROFILE = 'site-components-v1'
ROLE = 'docs-original-component-browser'
PAYLOAD = 'major-source-inputs-site-components'
UPLOAD = 'Upload original component source-test inputs'
REPORT_STEP = 'Upload component source-test qualification report'
REPORT_FILE = 'component-qualification.json'
MANIFEST = 'component-source-manifest.json'
FORMAT = 'codearbiter-site-component-source/1'
OBSERVATION = 'codearbiter-site-component-observation/1'
REPORT = 'codearbiter-site-component-qualification/1'
ENVELOPE = 'codearbiter-major-component-source-readiness/1'
CONFIG = 'site/playwright.components.config.ts'
ARGV = ['npm', 'run', 'test:components']
SCRIPT = 'playwright test --config=playwright.components.config.ts'
MAX_JSON = 4 << 20
need = owner.require

CASES = (
    ('lifecycle.spec.ts', 'search recovers query'),
    ('lifecycle.spec.ts', 'search recovers data'),
    ('lifecycle.spec.ts', 'search recovers expansion'),
    ('lifecycle.spec.ts', 'search recovers stale'),
    ('lifecycle.spec.ts', 'drawer reconnect owns exactly one set of opener, close and keyboard listeners'),
    ('search-boundaries.spec.ts', 'module failure retains query and retries a cache-busted import'),
    ('search-boundaries.spec.ts', 'pending query cannot reopen search after clear'),
    ('search-boundaries.spec.ts', 'pending query cannot reopen search after Escape'),
    ('search-boundaries.spec.ts', 'pending query cannot reopen search after outside'),
    ('search-boundaries.spec.ts', 'disconnect cancels pending render and releases shortcut until reconnect'),
    ('search-interactions.spec.ts', 'concurrent focus and submitted queries await one module initialization'),
    ('search-interactions.spec.ts', 'normalized queries debounce for140ms and fetch only the first8 results'),
    ('search-interactions.spec.ts', 'pending expansion disables repeat activation until all data settles'),
    ('search-interactions.spec.ts', 'empty results, arrow wrapping, submit and activation preserve combobox navigation'),
    ('search-interactions.spec.ts', 'late successful queries cannot replace newer results or empty state'),
    ('search-interactions.spec.ts', 'options rejection remains handled and explicit retry initializes a fresh module'),
)
# Empty project segment preserves the actual default unnamed Playwright project.
SELECTORS = tuple('playwright:site/test/components/' + path + '::' + title for path, title in CASES)
COMPLEMENTS = {
    'disposition:transitions:S55:01': (10,),
    'disposition:transitions:S55:02': (10, 15),
    'disposition:transitions:S55:03': (5, 15),
    'disposition:transitions:S55:04': (5, 15),
    'disposition:transitions:S55:05': (11, 13, 14),
    'disposition:transitions:S55:06': (13, 14),
    'disposition:transitions:S55:07': (0, 1, 3),
    'disposition:transitions:S55:08': (12,),
    'disposition:transitions:S55:09': (2, 12),
    'disposition:transitions:S55:10': (13, 9),
    'disposition:transitions:S55:11': (6, 7, 8, 9),
    'disposition:findings:SF11': (0, 1, 2, 3, 5, 12, 14, 15),
}
COMPLEMENTS['disposition:machines:S55'] = tuple(i for i in range(len(CASES)) if i != 4)
RECIPES = {cell: [SELECTORS[i] for i in indices] for cell, indices in COMPLEMENTS.items()}
CELLS = frozenset(RECIPES)


def parse_playwright(document):
    """Same bounded JSONReporter shape, with a distinct fixed component contract."""
    need(type(document) is dict and type(document.get('suites')) is list
         and document.get('errors') == [], 'component Playwright global failure')
    config = document.get('config', {})
    projects = config.get('projects')
    need(type(projects) is list and len(projects) == 1 and type(projects[0]) is dict
         and projects[0].get('id') == projects[0].get('name') == ''
         and type(projects[0].get('retries')) is int and projects[0]['retries'] == 0
         and type(projects[0].get('repeatEach')) is int and projects[0]['repeatEach'] == 1
         and projects[0].get('timeout') == 10000
         and type(config.get('workers')) is int and config['workers'] == 1
         and config.get('forbidOnly') is False, 'component project/config differs')
    found, ids, seen = {}, set(), 0
    def visit(suite, parents, depth):
        nonlocal seen
        seen += 1
        need(type(suite) is dict and depth <= 16 and seen <= reports.MAX_TESTS
             and type(suite.get('title')) is str and type(suite.get('specs')) is list,
             'component suite malformed or unbounded')
        chain = parents + ([suite['title']] if depth else [])
        for spec in suite['specs']:
            need(type(spec) is dict and type(spec.get('title')) is str
                 and 0 < len(spec['title']) <= 2048 and spec.get('ok') is True,
                 'component spec failed or malformed')
            path = spec.get('file')
            need(type(path) is str and path in {p for p, _ in CASES}, 'component case path differs')
            tests = spec.get('tests')
            need(type(tests) is list and len(tests) == 1 and type(tests[0]) is dict,
                 'component spec project population differs')
            test = tests[0]
            need(test.get('projectName') == test.get('projectId') == ''
                 and test.get('expectedStatus') == 'passed' and test.get('status') == 'expected'
                 and type(test.get('annotations')) is list
                 and all(type(a) is dict and a.get('type') not in ('skip', 'fixme', 'fail')
                         for a in test['annotations']), 'component test skipped or unsuccessful')
            rows = test.get('results')
            need(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict,
                 'component result missing or repeated')
            row = rows[0]
            need(row.get('status') == 'passed' and type(row.get('retry')) is int and row['retry'] == 0
                 and row.get('errors') == [] and not row.get('error')
                 and type(row.get('duration')) in (int, float)
                 and browser.math.isfinite(row['duration']) and row['duration'] >= 0,
                 'component result is not one affirmative pass')
            name = 'playwright:site/test/components/' + path + '::' + ' '.join([*chain, spec['title']])
            need(name in SELECTORS and name not in found and type(spec.get('id')) is str
                 and spec['id'] and spec['id'] not in ids, 'component identity unexpected or repeated')
            ids.add(spec['id'])
            found[name] = {'name': name, 'result': 'PASSED'}
        children = suite.get('suites', [])
        need(type(children) is list, 'component child suite malformed')
        for child in children:
            visit(child, chain, depth + 1)
    for suite in document['suites']:
        visit(suite, [], 0)
    stats = document.get('stats', {})
    need(set(found) == set(SELECTORS) and type(stats) is dict
         and all(type(stats.get(k)) is int for k in ('expected', 'unexpected', 'flaky', 'skipped'))
         and stats['expected'] == len(SELECTORS)
         and all(stats[k] == 0 for k in ('unexpected', 'flaky', 'skipped')),
         'component complete once-passing population differs')
    return [found[name] for name in sorted(found)]


def validate_selection_map(document):
    groups = [g for g in reports.validate_selections(document) if g['observation'] == ROLE]
    need(len(groups) == len(CELLS) and {c for g in groups for c in g['cells']} == CELLS,
         'component cell population differs')
    for group in groups:
        need(len(group['cells']) == 1 and group['job'] == JOB and group['payload_name'] == PAYLOAD
             and group['proof_kind'] == 'source-test' and group['selectors'] == RECIPES[group['cells'][0]],
             'component finite source selection differs')


def expected_inputs(repo, commit):
    inputs = source.expected_inputs(repo, commit)
    raw = owner.blob(repo, commit, CONFIG)
    inputs[CONFIG] = {'bytes': len(raw), 'sha256': owner.digest(raw)}
    need(len(raw) <= source.MAX_FILE and sum(v['bytes'] for v in inputs.values()) <= source.MAX_SOURCE,
         'component source closure exceeds bound')
    return inputs


def snapshot(repo):
    result = source.source_snapshot(repo)
    raw = source.read_file(Path(repo) / CONFIG, source.MAX_FILE)
    immutable = owner.blob(repo, result['source_commit'], CONFIG)
    need(raw == immutable, 'component config differs from immutable source')
    result['inputs'][CONFIG] = {'bytes': len(raw), 'sha256': owner.digest(raw)}
    need(sum(v['bytes'] for v in result['inputs'].values()) <= source.MAX_SOURCE,
         'component source closure exceeds bound')
    package = source.decode(source.read_file(Path(repo) / 'site/package.json', source.MAX_MANIFEST))
    need(package.get('scripts', {}).get('test:components') == SCRIPT
         and not any(k in package['scripts'] for k in ('pretest:components', 'posttest:components')),
         'original component npm lifecycle differs')
    return result


def manifest_document(state):
    return {'format': FORMAT, 'profile': PROFILE, 'workflow': browser.WORKFLOW, 'job': JOB,
            **{key: state[key] for key in ('source_commit', 'source_tree', 'inputs', 'python_namespaces')}}


def validate_manifest(document, req, repo=ROOT):
    expected = {'format': FORMAT, 'profile': PROFILE, 'workflow': browser.WORKFLOW, 'job': JOB,
                'source_commit': req['source_commit'], 'source_tree': req['source_tree'],
                'inputs': expected_inputs(repo, req['source_commit']),
                'python_namespaces': source.namespace_members(repo, req['source_commit'])}
    need(document == expected, 'component original source manifest differs')


def prepare_source(repo, output):
    state = snapshot(repo)
    need(state['clean'] is True, 'component source checkout is not clean')
    output = Path(output)
    output.mkdir(mode=0o700)
    for path, identity in state['inputs'].items():
        raw = source.read_file(Path(repo) / path, source.MAX_FILE)
        need(len(raw) == identity['bytes'] and owner.digest(raw) == identity['sha256'], 'component source changed')
        target = output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
    source._write(output / MANIFEST, manifest_document(state), source.MAX_MANIFEST)


def observe(repo, source_payload, output, *, browser_binary):
    repo = Path(repo).resolve(strict=True)
    need(not (os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN') or os.environ.get('COMPONENT_SOURCE_REF')),
         'component observer needs tokenless current source')
    before = snapshot(repo)
    need(before['clean'] is True, 'component source checkout is not clean')
    manifest_raw = source.read_file(Path(source_payload) / MANIFEST, source.MAX_MANIFEST)
    need(source.decode(manifest_raw) == manifest_document(before), 'component prepared source differs')
    node, npm = shutil.which('node'), shutil.which('npm')
    need(node and npm, 'component original toolchain missing')
    tools = {'node': browser.tool_identity(node), 'npm': browser.tool_identity(npm),
             'chrome': browser.tool_identity(browser_binary)}
    with tempfile.TemporaryDirectory(prefix='ca-components-json-') as directory:
        parent = Path(directory).resolve(strict=True)
        parent_before = parent.lstat()
        raw = parent / 'playwright.json'
        completed = subprocess.run([npm, *ARGV[1:]], cwd=repo / 'site',
            env=dict(os.environ, CA_COMPONENT_PLAYWRIGHT_JSON=str(raw)), check=False)
        after_tools = {'node': browser.tool_identity(node), 'npm': browser.tool_identity(npm),
                       'chrome': browser.tool_identity(browser_binary)}
        parent_after = parent.lstat()
        need(completed.returncode == 0 and snapshot(repo) == before and tools == after_tools
             and (parent_before.st_dev, parent_before.st_ino) == (parent_after.st_dev, parent_after.st_ino)
             and stat.S_ISDIR(parent_after.st_mode)
             and not getattr(parent_after, 'st_file_attributes', 0) & 0x400
             and parent.resolve(strict=True) == parent and not parent.is_symlink(),
             'component original command failed or source/tool/reporter identity changed')
        tests = parse_playwright(source.decode(source.read_file(raw, MAX_JSON)))
        record = {'format': OBSERVATION, 'profile': PROFILE, **before,
                  'run_id': int(os.environ['GITHUB_RUN_ID']), 'run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
                  'argv': ARGV, 'cwd': 'site', 'exit_code': 0, 'tools': tools,
                  'source_manifest_sha256': owner.digest(manifest_raw), 'tests': tests}
        source._write(Path(output), record)
    return 0


def validate_observation(record, req, manifest):
    keys = {'format', 'profile', 'source_commit', 'source_tree', 'clean', 'inputs', 'python_namespaces',
            'run_id', 'run_attempt', 'argv', 'cwd', 'exit_code', 'tools', 'source_manifest_sha256', 'tests'}
    need(type(record) is dict and set(record) == keys and record['format'] == OBSERVATION
         and record['profile'] == PROFILE and record['source_commit'] == req['source_commit']
         and record['source_tree'] == req['source_tree'] and record['run_id'] == req['ci_run_id']
         and type(record['run_id']) is int and type(record['run_attempt']) is int and record['run_attempt'] > 0
         and record['clean'] is True and record['inputs'] == manifest['inputs']
         and record['python_namespaces'] == manifest['python_namespaces']
         and record['argv'] == ARGV and record['cwd'] == 'site'
         and type(record['exit_code']) is int and record['exit_code'] == 0,
         'component observation source/run/command differs')
    need(type(record['tools']) is dict and set(record['tools']) == {'node', 'npm', 'chrome'}
         and all(type(v) is dict and set(v) == {'sha256', 'size'} and type(v['size']) is int
                 and 0 < v['size'] <= 512 << 20 and type(v['sha256']) is str
                 and owner.DIGEST.fullmatch(v['sha256']) for v in record['tools'].values()),
         'component launch tool identity differs')
    need(record['tests'] == [{'name': s, 'result': 'PASSED'} for s in sorted(SELECTORS)],
         'component original named population differs')
    return [{'cell': cell, 'result': 'PASSED', 'selectors': RECIPES[cell]} for cell in sorted(CELLS)]


def source_archive(artifact, req, archive, repo=ROOT):
    owner.validate_artifact(artifact, req, owner.digest(archive))
    owner.members(archive)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        need(MANIFEST in zipped.namelist() and zipped.getinfo(MANIFEST).file_size <= source.MAX_MANIFEST,
             'component source manifest missing or oversized')
        raw = zipped.read(MANIFEST)
        manifest = source.decode(raw)
        validate_manifest(manifest, req, repo)
        need(set(zipped.namelist()) == set(manifest['inputs']) | {MANIFEST}, 'component archive population differs')
        for path, identity in manifest['inputs'].items():
            need(zipped.getinfo(path).file_size == identity['bytes']
                 and owner.digest(zipped.read(path)) == identity['sha256'], 'component source archive bytes differ')
    return manifest, owner.digest(raw)


def _report(observed, req, run, job, artifact, archive, repo=ROOT):
    need(artifact.get('name') == PAYLOAD, 'component source payload role differs')
    source._payload_identity(artifact, run)
    manifest, manifest_sha = source_archive(artifact, req, archive, repo)
    results = validate_observation(observed, req, manifest)
    need(observed['run_attempt'] == run['run_attempt'] and observed['source_manifest_sha256'] == manifest_sha,
         'component original manifest or attempt differs')
    return {'schema': REPORT, 'source_commit': req['source_commit'], 'source_tree': req['source_tree'],
            'docs_run_id': run['id'], 'run_attempt': run['run_attempt'], 'job_id': job['id'],
            'source_artifact_id': artifact['id'], 'source_archive_sha256': owner.digest(archive),
            'observation': observed, 'results': results}


def report_from_observation(observed, req, run, job, artifact, archive, repo=ROOT):
    browser._run(run, req['source_commit'], req['ci_run_id'], producing=True)
    need(job.get('run_id') == run['id'] and job.get('run_attempt') == run['run_attempt'] and job.get('name') == JOB
         and job.get('status') == 'in_progress' and job.get('conclusion') is None, 'component producer job differs')
    uploads = [s for s in job.get('steps', []) if s.get('name') == UPLOAD]
    need(len(uploads) == 1 and uploads[0].get('status') == 'completed' and uploads[0].get('conclusion') == 'success',
         'component original source upload incomplete')
    return _report(observed, req, run, job, artifact, archive, repo)


def admit(req, *, run_id=None, repo=ROOT):
    need(required(req), 'component admission has no selected finite cell')
    run = browser._selected_run(req, run_id)
    need(run.get('head_branch') == 'main', 'final component qualification must be main')
    job, artifacts = browser._context(run)
    need(job.get('status') == 'completed' and job.get('conclusion') == 'success', 'component whole original job failed')
    by_name = {a.get('name'): a for a in artifacts}
    payload = by_name.get(PAYLOAD)
    report_artifact = by_name.get('major-docs-component-qualification-' + str(job['id']))
    need(type(payload) is dict and type(report_artifact) is dict, 'component original source/report upload missing')
    docs_req = {'source_commit': req['source_commit'], 'source_tree': req['source_tree'], 'ci_run_id': run['id']}
    source._payload_identity(report_artifact, run)
    archive = owner.artifact_bytes(payload, docs_req)
    log = owner.api('actions/jobs/' + str(job['id']) + '/logs', binary=True)
    owner.validate_upload(job, payload, UPLOAD, job_log=log)
    owner.validate_upload(job, report_artifact, REPORT_STEP, job_log=log)
    report_zip = owner.artifact_bytes(report_artifact, docs_req)
    need(len(report_zip) <= 8 << 20, 'component report archive oversized')
    owner.members(report_zip)
    with zipfile.ZipFile(io.BytesIO(report_zip)) as zipped:
        need(zipped.namelist() == [REPORT_FILE] and zipped.getinfo(REPORT_FILE).file_size <= MAX_JSON,
             'component report archive population differs')
        report = source.decode(zipped.read(REPORT_FILE))
    need(type(report) is dict and 'observation' in report, 'component original report missing')
    expected = _report(report['observation'], docs_req, run, job, payload, archive, repo)
    need(report == expected, 'component report differs from original authenticated evidence')
    return {'run_id': run['id'], 'run_attempt': run['run_attempt'], 'job_id': job['id'],
            'source_artifact_id': payload['id'], 'source_archive_sha256': owner.digest(archive),
            'report_artifact_id': report_artifact['id'], 'report_archive_sha256': report_artifact['digest'][7:],
            'results': [row for row in expected['results'] if row['cell'] in req['cells']]}


def required(req):
    selected = CELLS.intersection(req['cells'])
    need(all(req['cell_jobs'].get(c) == JOB for c in selected), 'component selected owner differs')
    return bool(selected)


def core_requirements(req):
    result = copy.deepcopy(req)
    result['cells'] = [c for c in req['cells'] if c not in CELLS]
    result['cell_jobs'] = {c: j for c, j in req['cell_jobs'].items() if c not in CELLS}
    return result


def produce(req, artifacts, jobs):
    need(required(req), 'component readiness requires its selected finite cells')
    return {'schema': ENVELOPE, 'program_id': owner.PROGRAM, 'state': 'PREPUBLICATION_READY', **req,
            'core': owner.produce(core_requirements(req), artifacts, jobs), 'components': admit(req)}


def verify(*, record, requirements, **kwargs):
    req = requirements
    owner.validate_run(kwargs['run'], req)
    need(required(req) and type(record) is dict
         and set(record) == {'schema', 'program_id', 'state', 'core', 'components', *req}
         and record['schema'] == ENVELOPE and record['program_id'] == owner.PROGRAM
         and record['state'] == 'PREPUBLICATION_READY' and all(record.get(k) == v for k, v in req.items()),
         'component readiness envelope differs')
    need(type(record['components']) is dict, 'component evidence missing')
    expected = admit(req, run_id=record['components'].get('run_id'))
    need(record['components'] == expected, 'component readiness differs from original evidence')
    owner.require(type(record['core']) is dict and record['core'].get('schema') in
        (owner.SCHEMA, 'codearbiter-major-readiness/2', 'codearbiter-major-readiness/4',
         'codearbiter-major-site-source-readiness/1'), 'invalid component envelope Core runtime schema')
    return owner.verify(record=record['core'], requirements=core_requirements(req), **kwargs)


def emit(repo, observed, output):
    reports.validate_emitter_environment()
    identity = snapshot(repo)
    validate_selection_map(reports.load_json(Path(repo) / '.github/major-test-selections.json'))
    run_id = int(os.environ['GITHUB_RUN_ID'])
    need(identity['clean'] and identity['source_commit'] == os.environ['GITHUB_SHA'], 'component emitting source differs')
    run = owner.api('actions/runs/' + str(run_id))
    browser._run(run, identity['source_commit'], run_id, producing=True)
    job, artifacts = browser._context(run)
    payloads = [a for a in artifacts if a.get('name') == PAYLOAD]
    need(len(payloads) == 1, 'component source upload ambiguous or missing')
    req = {**identity, 'ci_run_id': run_id}
    archive = owner.artifact_bytes(payloads[0], req)
    report = report_from_observation(source.decode(source.read_file(Path(observed), MAX_JSON)),
                                    req, run, job, payloads[0], archive, repo)
    source._write(Path(output), report)
    return job['id']


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare-source', 'observe', 'emit'):
        child = sub.add_parser(name)
        child.add_argument('--repo', type=Path, default=ROOT)
        child.add_argument('--output', type=Path, required=True)
        if name == 'observe':
            child.add_argument('--source-payload', type=Path, required=True)
            child.add_argument('--browser-binary', required=True)
        if name == 'emit':
            child.add_argument('--observation', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'prepare-source':
        prepare_source(args.repo, args.output)
    elif args.command == 'observe':
        return observe(args.repo, args.source_payload, args.output, browser_binary=args.browser_binary)
    else:
        job = emit(args.repo, args.observation, args.output)
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.write('job_id=' + str(job) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
