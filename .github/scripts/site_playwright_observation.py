#!/usr/bin/env python3
"""Finite built-site observations and a distinct, same-source Docs authority.

The producer can inspect its own completed Pages upload while its job runs.
Only the final reader admits a whole successful Docs run and original logs.
Nothing in this module executes a deployment or grants installed qualification.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile

import major_readiness as owner
import major_qualification_report as reports
import pages_readiness as pages

JOB = pages.JOB_NAME
REPORT_STEP = 'Upload Docs qualification report'
REPORT_SCHEMA = 'codearbiter-major-docs-qualification/1'
OBSERVATION = 'codearbiter-major-playwright-observation/1'
ENVELOPE = 'codearbiter-major-readiness/2'
WORKFLOW = '.github/workflows/docs.yml'
PUB = 'site/test/browser/publication.spec.ts'
RECONNECT = 'site/test/browser/concepts-execution.spec.ts'
CASES = (
    (PUB, 'WEB-008 + WEB-030: mobile navigation preserves its accessible reflow contract'),
    (PUB, 'S62: backdrop restores heterogeneous saved background and scroll state'),
    (PUB, 'S62: Tab wraps at both ends of the built drawer'),
    (PUB, 'S62: disconnecting an open drawer releases its document listener'),
    (RECONNECT, 'the same documentation drawer reconnects without duplicate local or Escape listeners'),
)
SELECTORS = tuple('playwright:' + path + ':chrome:' + title for path, title in CASES)
CELL_SELECTORS = {
    'disposition:findings:SF16': (3, 4),
    'disposition:machines:S62': (0, 1, 2, 3, 4),
    'disposition:transitions:S62:01': (0, 1, 2),
    'disposition:transitions:S62:02': (0, 1),
    'disposition:transitions:S62:03': (2,),
    'disposition:transitions:S62:04': (3,),
    'disposition:transitions:S62:05': (4, 3),
}
CELLS = frozenset(CELL_SELECTORS)
need = owner.require


def validate_selection_map(document):
    groups = [group for group in reports.validate_selections(document) if group['job'] == JOB]
    need(len(groups) == len(CELLS) and {cell for group in groups for cell in group['cells']} == CELLS,
         'Docs selection must declare exactly its seven finite cells')
    for group in groups:
        need(len(group['cells']) == 1 and group['payload_name'] == 'github-pages'
             and group['observation'] == 'site-built-drawer' and group['proof_kind'] == 'source-test'
             and group['selectors'] == [SELECTORS[index] for index in CELL_SELECTORS[group['cells'][0]]],
             'Docs selection differs from the complete built assertion mapping')


def docs_required(req):
    selected = CELLS.intersection(req['cells'])
    if selected:
        need(selected == CELLS and all(req['cell_jobs'].get(c) == JOB for c in CELLS),
             'Docs authority requires the exact seven declared site cells')
    need(all(name != JOB or cell in CELLS for cell, name in req['cell_jobs'].items()),
         'Docs job cannot qualify another scope')
    return bool(selected)


def core_requirements(req):
    result = copy.deepcopy(req)
    result['cells'] = [cell for cell in req['cells'] if cell not in CELLS]
    result['cell_jobs'] = {cell: job for cell, job in req['cell_jobs'].items() if cell not in CELLS}
    return result


def _regular(path, limit):
    info = path.lstat()
    need(stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_nlink == 1
         and not getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
         and 0 <= info.st_size <= limit, 'Docs input is not an owned bounded regular file')
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns')
    identity = tuple(getattr(info, field) for field in fields)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0)
                         | getattr(os, 'O_NOFOLLOW', 0))
    try:
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = None
            opened = os.fstat(stream.fileno())
            need(tuple(getattr(opened, field) for field in fields) == identity,
                 'Docs input changed before read')
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        final = path.lstat()
        need(len(raw) <= limit and len(raw) == info.st_size
             and tuple(getattr(after, field) for field in fields) == identity
             and tuple(getattr(final, field) for field in fields) == identity
             and not path.is_symlink()
             and not getattr(final, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
             'Docs input changed while read')
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return raw, info


def served_snapshot(root):
    root = Path(root)
    info = root.lstat()
    need(stat.S_ISDIR(info.st_mode) and not root.is_symlink()
         and not getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
         'served root is linked or unavailable')
    rows, names, total = [], set(), 0
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(directory) / name
            relative, _ = pages._path(path.relative_to(root).as_posix())
            key = relative.casefold()
            need(key not in names and len(names) < pages.MAX_MEMBERS, 'served paths collide or exceed bound')
            names.add(key)
            info = path.lstat()
            need(not path.is_symlink() and not getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                 'served tree contains a link or reparse point')
            if stat.S_ISDIR(info.st_mode):
                continue
            raw, info = _regular(path, pages.MAX_FILE_BYTES)
            total += len(raw)
            need(total <= pages.MAX_TOTAL_BYTES and info.st_mode & 0o7000 == 0,
                 'served bytes or permissions unsupported')
            rows.append({'path': relative, 'mode': stat.S_IMODE(info.st_mode),
                         'size': len(raw), 'sha256': owner.digest(raw)})
    need(rows, 'served tree empty')
    return sorted(rows, key=lambda row: row['path'])


def archive_manifest(archive):
    # Reuse every existing ZIP/tar/path bound before projecting modes. This
    # second pass never extracts, follows links, executes, or accepts new types.
    files, tar_digest = pages._static_files(archive)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        raw = zipped.read('artifact.tar')
    rows = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as tar:
        for member in tar:
            if member.isfile():
                path, _ = pages._path(member.name)
                need(member.mode & ~0o777 == 0, 'Pages member has unsupported permissions')
                rows.append({'path': path, 'mode': member.mode,
                             'size': len(files[path]), 'sha256': owner.digest(files[path])})
    need(len(rows) == len(files), 'Pages mode projection differs')
    return sorted(rows, key=lambda row: row['path']), tar_digest


def _count(value):
    return type(value) is int and 0 <= value <= reports.MAX_TESTS


def parse_playwright(record):
    """Read Playwright's actual suites/specs/tests/results shape, not Vitest."""
    need(type(record) is dict and type(record.get('suites')) is list
         and record.get('errors') == [], 'Playwright report missing or has global errors')
    config = record.get('config', {})
    projects = config.get('projects')
    need(type(projects) is list and len(projects) == 1
         and projects[0].get('name') == projects[0].get('id') == 'chrome'
         and projects[0].get('retries') == 0 and projects[0].get('repeatEach') == 1,
         'Playwright project/retry population differs')
    need(config.get('workers') == 1 and config.get('forbidOnly') is True,
         'Playwright qualification requires the original hosted worker/only guards')
    found, ids, suites_seen = {}, set(), 0

    def visit(suite, parents, depth):
        nonlocal suites_seen
        suites_seen += 1
        need(type(suite) is dict and depth <= 16 and suites_seen <= reports.MAX_TESTS
             and type(suite.get('title')) is str and type(suite.get('specs')) is list,
             'Playwright suite malformed or unbounded')
        # Top-level title is the file-suite label; nested describe titles are
        # actual components of the test title. The file is relative to testDir.
        chain = parents + ([suite['title']] if depth else [])
        for spec in suite['specs']:
            need(type(spec) is dict and type(spec.get('title')) is str
                 and 0 < len(spec['title']) <= 2048 and spec.get('ok') is True,
                 'Playwright spec failed or malformed')
            path = spec.get('file')
            need(type(path) is str and '\\' not in path and not path.startswith('/')
                 and not path.startswith('site/') and '..' not in path.split('/'),
                 'Playwright path differs from its original testDir')
            path, _ = pages._path('site/test/browser/' + path)
            title = ' '.join([*chain, spec['title']])
            tests = spec.get('tests')
            need(type(tests) is list and len(tests) == 1, 'Playwright spec repeated across projects')
            test = tests[0]
            need(type(test) is dict and test.get('projectName') == test.get('projectId') == 'chrome'
                 and test.get('expectedStatus') == 'passed' and test.get('status') == 'expected'
                 and not any(a.get('type') in ('skip', 'fixme', 'fail') for a in test.get('annotations', [])),
                 'Playwright test skipped, failed, flaky, or from another project')
            outcomes = test.get('results')
            need(type(outcomes) is list and len(outcomes) == 1 and type(outcomes[0]) is dict,
                 'Playwright result missing or retried')
            outcome = outcomes[0]
            need(outcome.get('status') == 'passed' and type(outcome.get('retry')) is int and outcome['retry'] == 0
                 and outcome.get('errors') == [] and not outcome.get('error')
                 and type(outcome.get('duration')) in (int, float)
                 and math.isfinite(outcome['duration']) and outcome['duration'] >= 0,
                 'Playwright result is not one affirmative pass')
            identity = 'playwright:' + path + ':chrome:' + title
            need(identity not in found and type(spec.get('id')) is str and spec['id']
                 and spec['id'] not in ids and len(found) < reports.MAX_TESTS,
                 'Playwright case missing identity, duplicated, or unbounded')
            ids.add(spec['id'])
            found[identity] = {'name': identity, 'result': 'PASSED'}
        children = suite.get('suites', [])
        need(type(children) is list, 'Playwright child suites malformed')
        for child in children:
            visit(child, chain, depth + 1)

    for suite in record['suites']:
        visit(suite, [], 0)
    stats = record.get('stats', {})
    need(found and all(_count(stats.get(key)) for key in ('expected', 'unexpected', 'flaky', 'skipped'))
         and stats['expected'] == len(found) and all(stats[key] == 0 for key in ('unexpected', 'flaky', 'skipped')),
         'Playwright summary differs from complete once-passing population')
    need(set(SELECTORS) <= set(found), 'required actual built-browser assertion missing')
    return [found[name] for name in sorted(found)]


def tool_identity(path):
    # Resolve the declared executable, not an arbitrary PATH-supplied report.
    path = Path(path).resolve(strict=True)
    raw, _ = _regular(path, 512 * 1024 * 1024)
    return {'sha256': owner.digest(raw), 'size': len(raw)}


def observe(repo, output, *, browser_binary):
    repo = Path(repo).resolve(strict=True)
    before = reports.source_identity(repo)
    need(before['clean'], 'Docs observation needs the actual clean source checkout')
    need(not (os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')),
         'browser observation must be tokenless')
    served = served_snapshot(repo / 'site/dist')
    node = shutil.which('node')
    npm = shutil.which('npm')
    need(node and npm, 'original browser toolchain unavailable')
    tools = {'node': tool_identity(node), 'chrome': tool_identity(browser_binary),
             'npm': tool_identity(npm)}
    # Output lives outside source/dist. The exclusive private directory remains
    # owned until the reporter has finished; raw report bodies are not uploaded.
    with tempfile.TemporaryDirectory(prefix='ca-docs-json-') as directory:
        parent = Path(directory)
        parent_info = parent.lstat()
        raw = Path(directory) / 'playwright.json'
        env = dict(os.environ, CA_DOCS_PLAYWRIGHT_JSON=str(raw))
        # Keep the original Actions job lifetime and Playwright's unchanged
        # 30-second test / 60-second server deadlines. No retry or extra browser
        # invocation is introduced by this observer.
        completed = subprocess.run([npm, 'run', 'test:browser'], cwd=repo / 'site', env=env, check=False)
        after = reports.source_identity(repo)
        after_served = served_snapshot(repo / 'site/dist')
        after_tools = {'node': tool_identity(node), 'chrome': tool_identity(browser_binary),
                       'npm': tool_identity(npm)}
        need(completed.returncode == 0 and before == after and after['clean']
             and served == after_served and tools == after_tools,
             'browser command failed or source/tool/served bytes changed')
        after_parent = parent.lstat()
        need(not parent.is_symlink() and stat.S_ISDIR(after_parent.st_mode)
             and not getattr(after_parent, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
             and (parent_info.st_dev, parent_info.st_ino) == (after_parent.st_dev, after_parent.st_ino),
             'original reporter directory changed')
        raw_bytes, _ = _regular(raw, reports.MAX_JSON)
        tests = parse_playwright(json.loads(raw_bytes, object_pairs_hook=reports.unique))
        record = {'format': OBSERVATION, **before, 'run_id': int(os.environ['GITHUB_RUN_ID']),
                  'run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
                  'argv': ['npm', 'run', 'test:browser'], 'cwd': 'site', 'exit_code': 0,
                  'tools': tools, 'served_members': served, 'tests': tests}
        reports.new_output(output, record)
    return 0


def validate_observation(observed, req):
    need(type(observed) is dict and set(observed) == {
        'format', 'source_commit', 'source_tree', 'clean', 'run_id', 'run_attempt',
        'argv', 'cwd', 'exit_code', 'tools', 'served_members', 'tests'}
         and observed['format'] == OBSERVATION and observed['source_commit'] == req['source_commit']
         and observed['source_tree'] == req['source_tree'] and observed['clean'] is True
         and observed['run_id'] == req['ci_run_id'] and type(observed['run_attempt']) is int
         and observed['run_attempt'] > 0 and type(observed['exit_code']) is int and observed['exit_code'] == 0
         and observed['argv'] == ['npm', 'run', 'test:browser'] and observed['cwd'] == 'site',
         'Docs observation source/run/command differs')
    need(type(observed['tools']) is dict and set(observed['tools']) == {'node', 'npm', 'chrome'}
         and all(type(value) is dict and set(value) == {'sha256', 'size'}
                 and type(value['size']) is int and value['size'] > 0
                 and type(value['sha256']) is str and owner.DIGEST.fullmatch(value['sha256'])
                 for value in observed['tools'].values()), 'Docs tool identities missing')
    rows = observed['tests']
    need(type(rows) is list and 0 < len(rows) <= reports.MAX_TESTS
         and all(type(row) is dict and set(row) == {'name', 'result'}
                 and type(row['name']) is str and row['name'].startswith('playwright:site/test/browser/')
                 and row['result'] == 'PASSED' for row in rows), 'Docs actual assertion population invalid')
    names = [row['name'] for row in rows]
    need(names == sorted(set(names)) and set(SELECTORS) <= set(names),
         'Docs required assertion missing or repeated')


def _run(run, source, run_id, *, producing=False):
    repository = run.get('repository', {})
    head = run.get('head_repository', {})
    need(type(run_id) is int and run_id > 0 and run.get('id') == run_id
         and run.get('head_sha') == source and run.get('head_branch') in ('main', 'major/state-contracts')
         and run.get('event') == 'push' and run.get('path') == WORKFLOW
         and pages._positive(run.get('run_attempt'))
         and repository.get('full_name') == head.get('full_name') == owner.REPOSITORY
         and pages._positive(repository.get('id')) and repository['id'] == head.get('id'),
         'Docs run is not the exact same-source trusted normal workflow')
    need((run.get('status') == 'completed' and run.get('conclusion') == 'success')
         or producing and run.get('status') == 'in_progress' and run.get('conclusion') is None,
         'Docs whole run did not succeed')


def _population(document, field, maximum):
    values = document.get(field)
    need(type(values) is list and type(document.get('total_count')) is int
         and document['total_count'] == len(values) and len(values) <= maximum
         and all(type(row) is dict and pages._positive(row.get('id')) for row in values)
         and len({row['id'] for row in values}) == len(values), 'Docs API population incomplete or ambiguous')
    return values


def _selected_run(req, run_id=None):
    if run_id is None:
        document = owner.api('actions/workflows/docs.yml/runs?head_sha=' + req['source_commit'] + '&event=push&per_page=100')
        runs = _population(document, 'workflow_runs', 100)
        runs = [run for run in runs if run.get('head_sha') == req['source_commit']
                and run.get('head_branch') == 'main' and run.get('event') == 'push']
        need(len(runs) == 1, 'select exactly one original same-source Docs run; never latest or ambiguous')
        run = runs[0]
    else:
        need(pages._positive(run_id), 'invalid selected Docs run')
        run = owner.api('actions/runs/' + str(run_id))
    _run(run, req['source_commit'], run['id'])
    need(run['id'] != req['ci_run_id'], 'Docs and Core run identities must remain distinct')
    return run


def _context(run):
    identity = run['id']
    jobs = _population(owner.api(f'actions/runs/{identity}/jobs?filter=latest&per_page=100'), 'jobs', 100)
    matches = [job for job in jobs if job.get('name') == JOB]
    need(len(matches) == 1, 'Docs original build job missing or ambiguous')
    job = matches[0]
    need(job.get('run_id') == identity and job.get('run_attempt') == run['run_attempt'],
         'Docs job belongs to another run/attempt')
    artifacts = _population(owner.api(f'actions/runs/{identity}/artifacts?per_page=100'), 'artifacts', 100)
    need(len({artifact.get('name') for artifact in artifacts}) == len(artifacts), 'Docs artifact name ambiguous')
    return job, artifacts


def report_from_observation(observed, req, run, job, artifact, archive):
    """Producing-only: no original job log can exist while this job runs."""
    _run(run, req['source_commit'], req['ci_run_id'], producing=True)
    need(job.get('run_id') == req['ci_run_id'] and job.get('run_attempt') == run['run_attempt']
         and job.get('name') == JOB and job.get('status') == 'in_progress' and job.get('conclusion') is None,
         'Docs producer is not its original active build job')
    uploads = [step for step in job.get('steps', []) if step.get('name') == pages.UPLOAD_STEP]
    need(len(uploads) == 1 and uploads[0].get('status') == 'completed'
         and uploads[0].get('conclusion') == 'success', 'original Pages upload has not completed')
    need(artifact.get('name') == 'github-pages', 'Docs producer payload role differs')
    need(artifact.get('workflow_run', {}).get('head_branch') == run['head_branch']
         and artifact['workflow_run'].get('repository_id') == run['repository']['id']
         and artifact['workflow_run'].get('head_repository_id') == run['repository']['id'],
         'Docs producer payload repository differs')
    owner.validate_artifact(artifact, req, owner.digest(archive))
    validate_observation(observed, req)
    need(observed['run_attempt'] == run['run_attempt'], 'Docs observation attempt differs')
    manifest, tar_sha = archive_manifest(archive)
    need(manifest == observed['served_members'], 'original Pages tar differs from actually served browser bytes')
    return {'schema': REPORT_SCHEMA, 'source_commit': req['source_commit'], 'source_tree': req['source_tree'],
            'docs_run_id': req['ci_run_id'], 'run_attempt': run['run_attempt'], 'job_id': job['id'],
            'pages_artifact_id': artifact['id'], 'archive_sha256': owner.digest(archive),
            'tar_sha256': tar_sha, 'served_members': manifest, 'observation': observed}


def _report_document(artifact, req):
    archive = owner.artifact_bytes(artifact, req)
    need(len(archive) <= 8 * 1024 * 1024, 'Docs report archive exceeds bound')
    owner.members(archive)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        need(zipped.namelist() == ['docs-qualification.json']
             and zipped.getinfo('docs-qualification.json').file_size <= 4 * 1024 * 1024,
             'Docs report archive population differs')
        return json.loads(zipped.read('docs-qualification.json'), object_pairs_hook=reports.unique)


def admit(req, *, run_id=None):
    """Final admission: original completed whole Docs run, both uploader logs."""
    run = _selected_run(req, run_id)
    # Publication records are main-only even if a caller names a major run.
    need(run.get('head_branch') == 'main', 'final Docs publication evidence must be main')
    job, artifacts = _context(run)
    need(job.get('status') == 'completed' and job.get('conclusion') == 'success', 'Docs build job did not succeed')
    by_name = {artifact.get('name'): artifact for artifact in artifacts}
    payload = by_name.get('github-pages')
    report_artifact = by_name.get('major-docs-qualification-' + str(job['id']))
    need(type(payload) is dict and type(report_artifact) is dict, 'original Docs report/Pages payload missing')
    docs_req = {'source_commit': req['source_commit'], 'ci_run_id': run['id']}
    archive = owner.artifact_bytes(payload, docs_req)
    log = owner.api('actions/jobs/' + str(job['id']) + '/logs', binary=True)
    accepted = pages.admit_pages_build(source=req['source_commit'], run_id=run['id'], branch='main',
        job_id=job['id'], artifact_id=payload['id'], run=run, job=job,
        artifact=payload, archive=archive, job_log=log)
    owner.validate_upload(job, report_artifact, REPORT_STEP, job_log=log)
    report = _report_document(report_artifact, docs_req)
    need(type(report) is dict and set(report) == {'schema', 'source_commit', 'source_tree', 'docs_run_id',
        'run_attempt', 'job_id', 'pages_artifact_id', 'archive_sha256', 'tar_sha256', 'served_members', 'observation'}
         and report['schema'] == REPORT_SCHEMA and report['source_commit'] == req['source_commit']
         and all(pages._positive(report[key]) for key in ('docs_run_id', 'run_attempt', 'job_id', 'pages_artifact_id'))
         and report['source_tree'] == req['source_tree'] and report['docs_run_id'] == run['id']
         and report['run_attempt'] == run['run_attempt'] and report['job_id'] == job['id']
         and report['pages_artifact_id'] == payload['id']
         and report['archive_sha256'] == owner.digest(archive), 'Docs original report identity differs')
    manifest, tar_sha = archive_manifest(archive)
    validate_observation(report['observation'], {**docs_req, 'source_tree': req['source_tree']})
    need(report['observation']['run_attempt'] == run['run_attempt']
         and manifest == report['served_members'] == report['observation']['served_members']
         and tar_sha == report['tar_sha256'], 'Docs exact observed/retained served bytes differ')
    return {'run_id': run['id'], 'run_attempt': run['run_attempt'], 'job_id': job['id'],
            'report_artifact_id': report_artifact['id'], 'report_archive_sha256': report_artifact['digest'][7:],
            'pages': accepted['provenance'],
            'results': [{'cell': cell, 'result': 'PASSED', 'selectors': [SELECTORS[i] for i in CELL_SELECTORS[cell]]}
                        for cell in sorted(CELLS)]}


def produce(req, artifacts, jobs):
    need(docs_required(req), 'Docs envelope requires its finite site population')
    core = owner.produce(core_requirements(req), artifacts, jobs)
    docs = admit(req)
    return {'schema': ENVELOPE, 'program_id': owner.PROGRAM, 'state': 'PREPUBLICATION_READY',
            **req, 'core': core, 'docs': docs}


def verify(*, record, requirements, **kwargs):
    req = requirements
    owner.validate_run(kwargs['run'], req)  # Refuse non-main/Core failure before auxiliary I/O.
    need(docs_required(req) and type(record) is dict
         and set(record) == {'schema', 'program_id', 'state', 'core', 'docs', *req}
         and record['schema'] == ENVELOPE and record['program_id'] == owner.PROGRAM
         and record['state'] == 'PREPUBLICATION_READY' and all(record.get(k) == v for k, v in req.items()),
         'closed Docs readiness envelope differs from selected source/population')
    need(type(record.get('docs')) is dict, 'Docs authority missing')
    expected = admit(req, run_id=record['docs'].get('run_id'))
    need(record['docs'] == expected, 'Docs envelope differs from original authenticated evidence')
    owner.verify(record=record['core'], requirements=core_requirements(req), **kwargs)
    return {'state': 'PREPUBLICATION_READY', 'source': req['source_commit'],
            'ci_run_id': req['ci_run_id'], 'docs_run_id': expected['run_id']}


def emit(repo, observed, output):
    reports.validate_emitter_environment()
    identity = reports.source_identity(repo)
    validate_selection_map(reports.load_json(Path(repo) / '.github/major-test-selections.json'))
    source, run_id = os.environ['GITHUB_SHA'], int(os.environ['GITHUB_RUN_ID'])
    need(identity['clean'] and identity['source_commit'] == source, 'Docs emitting source differs')
    run = owner.api('actions/runs/' + str(run_id))
    _run(run, source, run_id, producing=True)
    job, artifacts = _context(run)
    payloads = [artifact for artifact in artifacts if artifact.get('name') == 'github-pages']
    need(len(payloads) == 1, 'exact original Pages payload missing')
    req = {**identity, 'ci_run_id': run_id}
    payload = payloads[0]
    archive = owner.artifact_bytes(payload, req)
    record = report_from_observation(reports.load_json(observed), req, run, job, payload, archive)
    reports.new_output(output, record)
    return job['id']


def prepare_promotion(repo, source, core_run_id, output):
    """Stage only the authenticated original tar for a later current-run upload.

    deploy-pages v5 has no cross-run input. This separate, read-only job stages
    original bytes; its dependent deploy job alone has Pages/OIDC permissions.
    A successful preparation never claims a public deployment/readback.
    """
    need(os.environ.get('GITHUB_ACTIONS') == 'true'
         and os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
         and os.environ.get('GITHUB_REF') == 'refs/heads/main'
         and os.environ.get('GITHUB_REPOSITORY') == owner.REPOSITORY
         and os.environ.get('GITHUB_SHA') == source and pages._positive(core_run_id),
         'qualified Pages promotion requires explicit current main dispatch')
    identity = reports.source_identity(repo)
    need(identity['clean'] and identity['source_commit'] == source, 'promotion checkout differs from main source')
    record, verified = owner.load_verified_receipt(repo, source, core_run_id)
    record = owner.runtime_record(record)
    need(record.get('schema') == ENVELOPE and verified.get('docs_run_id') == record['docs']['run_id']
         and verified.get('state') == 'PREPUBLICATION_READY'
         and record['source_tree'] == identity['source_tree'], 'qualified Docs envelope required before promotion')
    original = record['docs']['pages']
    metadata = owner.api('actions/artifacts/' + str(original['artifact_id']))
    need(metadata.get('id') == original['artifact_id'] and metadata.get('name') == 'github-pages',
         'promotion original artifact identity differs')
    req = {'source_commit': source, 'ci_run_id': record['docs']['run_id']}
    archive = owner.artifact_bytes(metadata, req)
    manifest, tar_sha = archive_manifest(archive)
    need(owner.digest(archive) == original['archive_sha256'] and tar_sha == original['tar_sha256']
         and [{'path': row['path'], 'size': row['size'], 'sha256': row['sha256']} for row in manifest]
             == original['members'], 'promotion original Pages payload differs')
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        tar = zipped.read('artifact.tar')
    need(owner.digest(tar) == original['tar_sha256'], 'promotion must retain the exact qualified tar')
    output = Path(output)
    need(output.is_absolute() and output.parent.resolve(strict=True) == output.parent,
         'promotion stage parent must be an existing canonical directory')
    output.mkdir(mode=0o700)  # Never reuse or merge a previous stage.
    try:
        path = output / 'artifact.tar'
        with path.open('xb') as stream:
            stream.write(tar)
        checked, _ = _regular(path, pages.MAX_TAR_BYTES)
        need(owner.digest(checked) == original['tar_sha256'], 'promotion staged bytes differ')
        lineage = {'format': 'codearbiter-qualified-pages-transfer/1', 'source_commit': source,
                   'source_tree': identity['source_tree'], 'core_run_id': core_run_id,
                   'docs_run_id': record['docs']['run_id'], 'docs_job_id': record['docs']['job_id'],
                   'original_pages_artifact_id': original['artifact_id'],
                   'original_pages_archive_sha256': original['archive_sha256'],
                   'tar_sha256': original['tar_sha256'], 'served_members': manifest,
                   'state': 'QUALIFIED_BYTES_STAGED', 'deployment_observed': False}
        reports.new_output(output.with_name(output.name + '-lineage.json'), lineage)
    except BaseException:
        # Retain uncertain owned output for diagnosis; the job fails before
        # the successful upload/deploy dependency can execute.
        raise
    return lineage


def verify_transfer(repo, lineage_path, output):
    """Read back the current run's upload before the privileged deploy job.

    This is a producing-phase transport check, not a completed-run qualification
    or public readback. The completed preparation job is the deploy dependency.
    """
    lineage = reports.load_json(lineage_path)
    need(type(lineage) is dict and set(lineage) == {'format', 'source_commit', 'source_tree',
        'core_run_id', 'docs_run_id', 'docs_job_id', 'original_pages_artifact_id',
        'original_pages_archive_sha256', 'tar_sha256', 'served_members', 'state', 'deployment_observed'}
         and lineage['format'] == 'codearbiter-qualified-pages-transfer/1'
         and lineage['state'] == 'QUALIFIED_BYTES_STAGED' and lineage['deployment_observed'] is False,
         'original qualified transfer lineage missing')
    source = lineage['source_commit']
    need(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
         and os.environ.get('GITHUB_REF') == 'refs/heads/main' and os.environ.get('GITHUB_SHA') == source
         and os.environ.get('GITHUB_REPOSITORY') == owner.REPOSITORY,
         'qualified tar readback requires its exact main dispatch')
    identity = reports.source_identity(repo)
    need(identity == {'source_commit': source, 'source_tree': lineage['source_tree'], 'clean': True},
         'qualified transfer source changed')
    run_id = int(os.environ['GITHUB_RUN_ID'])
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    run = owner.api('actions/runs/' + str(run_id))
    need(run.get('id') == run_id and run.get('head_sha') == source and run.get('head_branch') == 'main'
         and run.get('event') == 'workflow_dispatch' and run.get('path') == WORKFLOW
         and run.get('status') == 'in_progress' and run.get('conclusion') is None
         and run.get('run_attempt') == attempt and pages._positive(attempt)
         and run.get('repository', {}).get('full_name') == owner.REPOSITORY
         and pages._positive(run.get('repository', {}).get('id'))
         and run.get('head_repository', {}).get('id') == run['repository']['id']
         and run.get('head_repository', {}).get('full_name') == owner.REPOSITORY,
         'qualified transfer run identity differs')
    jobs = _population(owner.api(f'actions/runs/{run_id}/jobs?filter=latest&per_page=100'), 'jobs', 100)
    matches = [job for job in jobs if job.get('name') == 'Site | [Prepare] - Qualified Pages']
    need(len(matches) == 1, 'qualified transfer job missing or ambiguous')
    job = matches[0]
    need(job.get('run_id') == run_id and job.get('run_attempt') == attempt
         and job.get('status') == 'in_progress' and job.get('conclusion') is None,
         'qualified transfer is not its active original job')
    steps = [step for step in job.get('steps', []) if step.get('name') == 'Upload the exact qualified Pages tar']
    need(len(steps) == 1 and steps[0].get('status') == 'completed'
         and steps[0].get('conclusion') == 'success', 'qualified transfer upload did not complete')
    artifacts = _population(owner.api(f'actions/runs/{run_id}/artifacts?per_page=100'), 'artifacts', 100)
    matches = [artifact for artifact in artifacts if artifact.get('name') == 'github-pages']
    need(len(matches) == 1, 'qualified transfer artifact missing or ambiguous')
    artifact = matches[0]
    archive = owner.artifact_bytes(artifact, {'source_commit': source, 'ci_run_id': run_id})
    manifest, tar_sha = archive_manifest(archive)
    need(tar_sha == lineage['tar_sha256'] and manifest == lineage['served_members'],
         'uploaded Pages tar differs from the original qualified bytes')
    result = {'format': 'codearbiter-qualified-pages-readback/1', 'source_commit': source,
              'source_tree': lineage['source_tree'], 'run_id': run_id, 'run_attempt': attempt,
              'job_id': job['id'], 'artifact_id': artifact['id'], 'archive_sha256': owner.digest(archive),
              'tar_sha256': tar_sha, 'original_docs_run_id': lineage['docs_run_id'],
              'original_pages_artifact_id': lineage['original_pages_artifact_id'],
              'state': 'QUALIFIED_BYTES_TRANSFERRED', 'deployment_observed': False}
    reports.new_output(output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('observe', 'emit', 'prepare-promotion', 'verify-transfer'))
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--observation', type=Path)
    parser.add_argument('--browser-binary', type=Path)
    parser.add_argument('--source')
    parser.add_argument('--core-run-id', type=int)
    parser.add_argument('--lineage', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.operation == 'observe':
            need(args.browser_binary is not None, 'original browser binary required')
            return observe(args.repo, args.output, browser_binary=args.browser_binary)
        if args.operation == 'prepare-promotion':
            need(args.source is not None and owner.SHA.fullmatch(args.source), 'exact main source required')
            prepare_promotion(args.repo, args.source, args.core_run_id, args.output)
            return 0
        if args.operation == 'verify-transfer':
            need(args.lineage is not None, 'original qualified transfer lineage required')
            verify_transfer(args.repo, args.lineage, args.output)
            return 0
        need(args.observation is not None, 'original browser observation required')
        job_id = emit(args.repo, args.observation, args.output)
        # This is a numeric API job identity, never the logical GITHUB_JOB key.
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write('job_id=' + str(job_id) + '\n')
        return 0
    except (owner.ReadinessError, ValueError, OSError, KeyError, TypeError,
            zipfile.BadZipFile, tarfile.TarError, RecursionError):
        print('::error::Docs qualification unavailable; original boundary refused', file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
