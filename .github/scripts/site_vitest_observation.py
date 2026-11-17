#!/usr/bin/env python3
"""Original Docs coverage observations; separate from Core CI and browser authority.

The original npm coverage lifecycle executes once. Primary named results cannot
stand in for its builds/followups, and a producer-time report cannot stand in for
whole successful main Docs/Core runs at final admission.
"""
from __future__ import annotations
import argparse
import copy
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import zipfile
import major_readiness as owner
import major_qualification_report as reports
import site_playwright_observation as browser
from _boundedproc import start, terminate_tree

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = '.github/workflows/docs.yml'
JOB = 'Site | [Test] - Generator'
PROFILE = 'site-vitest-findings-v1'
PAYLOAD = 'major-source-inputs-site-vitest-findings'
UPLOAD = 'Upload original Docs source-test inputs'
REPORT_STEP = 'Upload Docs source-test qualification report'
MANIFEST = 'docs-source-manifest.json'
MANIFEST_FORMAT = 'codearbiter-docs-site-source-manifest/1'
OBSERVATION = 'codearbiter-docs-site-test-observation/1'
REPORT = 'codearbiter-docs-site-test-qualification/1'
ENVELOPE = 'codearbiter-major-site-source-readiness/1'
REPORT_FILE = 'docs-site-test-qualification.json'
ARGV = ['npm', 'run', 'coverage']
COVERAGE_SCRIPT = 'vitest run --coverage && npm run test:academy-base && npm run test:release-applicability-rendered'
SCRIPTS = {'coverage': COVERAGE_SCRIPT, 'precoverage': 'npm run build', 'build': 'astro build',
    'prebuild': 'npm run gen', 'test:academy-base': 'node scripts/test-academy-non-root-base.mjs',
    'test:release-applicability-rendered': 'astro build && tsx test/release-applicability/rendered.ts'}
SOURCE_ROOTS = ('site/scripts', 'site/test', 'site/src', 'plugins/ca/hooks')
NAMESPACES = ('core/pysrc', '.github/scripts')
EXTRAS = ('.github/workflows/docs.yml', '.github/major-qualification-policy.json',
    '.github/major-test-selections.json', '.github/scripts/site_vitest_observation.py',
    '.github/scripts/test_site_vitest_observation.py', '.github/scripts/site_playwright_observation.py',
    '.github/scripts/major_qualification_report.py', '.github/scripts/major_readiness.py',
    '.github/scripts/pages_readiness.py', '.github/scripts/_boundedproc.py',
    '.github/scripts/_immutable_git_blobs.py', '.github/scripts/_contextverificationlib.py',
    'core/pysrc/_gitexec.py', 'core/pysrc/_prunelib.py', 'site/package.json', 'site/package-lock.json',
    'site/vitest.config.ts', 'site/astro.config.mjs', 'site/tsconfig.json',
    '.github/published-tags.json', '.codearbiter/release-targets.md', '.github/workflows/ci.yml',
    'plugins/ca-pi/tools/src/compatibility.ts', 'plugins/ca-pi/package.json',
    'plugins/ca-codex/.codex-plugin/plugin.json', 'plugins/ca/.claude-plugin/plugin.json',
    'core/artifacts/internal/authority/receipt.go',
    'docs/state-contracts-major/contracts/finding-dispositions.json')
RENDERED = ('site/src/generated/release-applicability.json', 'site/dist/release-applicability.json',
    'site/dist/index.html', 'site/dist/getting-started/compatibility/index.html')
MAX_FILE = 64 << 20
MAX_SOURCE = 64 << 20
MAX_MANIFEST = 1 << 20
MAX_REPORT = 4 << 20
MAX_ROWS = reports.MAX_TESTS
need = owner.require

RECIPES = {'disposition:findings:GEN-B01': ['vitest:site/test/generator/assign-slugs.test.ts:assignSlugs slugifies names with no '
                                  'collisions',
                                  'vitest:site/test/generator/assign-slugs.test.ts:assignSlugs suffixes colliding '
                                  'slugs in order of appearance',
                                  'vitest:site/test/generator/assign-slugs.test.ts:assignSlugs suffixes triple '
                                  'collisions deterministically',
                                  'vitest:site/test/generator/assign-slugs.test.ts:assignSlugs preserves input length '
                                  'and order',
                                  'vitest:site/test/generator/assign-slugs.test.ts:assignSlugs reserves every emitted '
                                  'slug, including suffixed forms (HW-24)',
                                  'vitest:site/test/generator/assign-slugs.test.ts:assignSlugs never emits a duplicate '
                                  'for names already ending in numeric suffixes'],
 'disposition:findings:GEN-F01': ['vitest:site/test/generator/configuration-reference.test.ts:configuration reference '
                                  'describes the prune nudge threshold with the runtime predicate and default (HW-22)',
                                  'vitest:site/test/generator/configuration-reference.test.ts:configuration reference '
                                  'is deterministic'],
 'disposition:findings:GEN-F02': ['vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — fixture '
                                  'extracts a multi-line adjacent f-string call, concatenating placeholder text '
                                  'verbatim',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — fixture '
                                  'handles nested parens inside a plain string literal without truncating the call',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — fixture '
                                  'handles `+` concatenation, ignoring the non-literal trailing call but tracking its '
                                  'parens',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — fixture '
                                  'finds two distinct tags in the same file',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — fixture '
                                  'resolves a bare-assignment variable tag to its single literal tag',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — fixture '
                                  'resolves a conditional-assignment variable tag to BOTH tags with the same message '
                                  'and line pin',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — fixture '
                                  'counts an unresolvable variable-tag call (loop unpack) into `skipped`, not silently '
                                  'dropped',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — fixture '
                                  'excludes the block()/remind() definition sites themselves',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — fixture '
                                  'records 1-based line numbers and the source file basename',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — real '
                                  'plugin hooks (count-floor snapshot) finds at least 60 attributed call sites in the '
                                  'real hooks',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — real '
                                  'plugin hooks (count-floor snapshot) attributes at least one H-10b entry (the '
                                  'conditional-assignment split) with its real message',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — real '
                                  'plugin hooks (count-floor snapshot) keeps the genuinely unresolvable loop-unpack '
                                  'call site in `skipped`',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — real '
                                  "plugin hooks (count-floor snapshot) extracts H-01's protected-branch commit message "
                                  'from _bashguardlib.py verbatim',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — real '
                                  'plugin hooks (count-floor snapshot) keeps the same real-hook structural assertions '
                                  'after unrelated _bashguardlib.py line insertions',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — real '
                                  'plugin hooks (count-floor snapshot) extracts an H-09b message from _bashguardlib.py '
                                  'verbatim',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — bounded, '
                                  'masked, honest about dynamic text (HW-23) excludes quoted, commented and docstring '
                                  'fake block calls',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — bounded, '
                                  'masked, honest about dynamic text (HW-23) marks a dynamic recovery suffix instead '
                                  'of presenting a partial message as complete',
                                  'vitest:site/test/generator/extract-hook-gates.test.ts:extractHookGates — bounded, '
                                  'masked, honest about dynamic text (HW-23) leaves an assignment beyond the 30-line '
                                  'window as an explicit skipped gap',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:buildEventMap / eventsFor '
                                  'maps a script to its EventName (matcher) label',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:buildEventMap / eventsFor '
                                  'maps a script with no matcher to a bare EventName label',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:buildEventMap / eventsFor '
                                  'hand-maps git-enforce.py to the git backstop label, bypassing hooks.json',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:buildEventMap / eventsFor '
                                  'attributes extracted shared-library gates to their registered entry hook',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:buildEventMap / eventsFor '
                                  'returns an empty list for a script registered nowhere',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:renderHooksReference '
                                  'renders frontmatter with title Hook Gates',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:renderHooksReference '
                                  'orders sections in natural gate-ID order: H-09 before H-09b before H-10',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:renderHooksReference '
                                  'shows the Blocking badge for a block-only tag',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:renderHooksReference '
                                  'shows both badges when a tag has both a block and a remind call site',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:renderHooksReference '
                                  'renders a line-pinned permalink in the expected format',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:renderHooksReference '
                                  'wraps f-string placeholders in backticks',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:renderHooksReference — '
                                  'honest coverage (HW-23) never claims runtime equivalence',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:renderHooksReference — '
                                  'honest coverage (HW-23) names a dynamic recovery fragment instead of presenting a '
                                  'partial message as complete',
                                  'vitest:site/test/generator/render-hooks-reference.test.ts:renderHooksReference — '
                                  'honest coverage (HW-23) lists skipped call sites with source links'],
 'disposition:findings:SX-F01': ['vitest:site/test/release-applicability/endpoint.test.ts:release applicability '
                                 'endpoint statically serves the canonical generated record as JSON',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation loads the exact supported direct-hook replay claim while allowing fixture '
                                 'detail (O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects missing schema before proof metadata enters the generated record '
                                 '(O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects unsupported schema before proof metadata enters the generated '
                                 'record (O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects relabeled evidence kind before proof metadata enters the '
                                 'generated record (O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects host discovery promoted to true before proof metadata enters the '
                                 'generated record (O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects missing proof evidence before generation (O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects invalid JSON proof evidence before generation (O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects a non-canonical or unconfined hook evidence path ../outside.py '
                                 '(O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects a non-canonical or unconfined hook evidence path '
                                 'plugins/ca/hooks/../pre-bash.py (O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects a non-canonical or unconfined hook evidence path '
                                 'plugins\\ca\\hooks\\pre-bash.py (O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects a non-canonical or unconfined hook evidence path '
                                 '/plugins/ca/hooks/pre-bash.py (O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects a non-canonical or unconfined hook evidence path '
                                 'C:/plugins/ca/hooks/pre-bash.py (O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects a non-canonical or unconfined hook evidence path '
                                 './plugins/ca/hooks/pre-bash.py (O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects a canonical hook path whose parent symlink escapes the repository '
                                 '(O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation rejects a canonical hook path that resolves to a directory (O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 "generation writes the strict deterministic record from the repository's real "
                                 'evidence (O-10)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 "generation reports each host's highest stable release tag, not the lagging receipt "
                                 'ledger (R-01)',
                                 'vitest:site/test/release-applicability/generation.test.ts:release applicability '
                                 'generation fails closed without writing output when build identity evidence is '
                                 'inconsistent (O-10)',
                                 'vitest:site/test/release-applicability/presentation.test.ts:release applicability '
                                 'presentation generates and builds fresh fixtures before top-level test and coverage '
                                 'runners',
                                 'vitest:site/test/release-applicability/presentation.test.ts:release applicability '
                                 'presentation distinguishes a published-artifact mismatch from a current-source '
                                 'mismatch (O-13)',
                                 'vitest:site/test/release-applicability/presentation.test.ts:release applicability '
                                 'presentation presents the exact successful applicability claim (O-13)',
                                 'vitest:site/test/release-applicability/presentation.test.ts:release applicability '
                                 'presentation rejects an internally inconsistent applicability claim (O-13)',
                                 'vitest:site/test/release-applicability/publication.test.ts:observed publication is '
                                 'distinct from source applicability never calls an offline local tag or historical '
                                 'receipt published',
                                 'vitest:site/test/release-applicability/publication.test.ts:observed publication is '
                                 'distinct from source applicability retains exact observed published state',
                                 'vitest:site/test/release-applicability/publication.test.ts:observed publication is '
                                 'distinct from source applicability retains exact observed draft state',
                                 'vitest:site/test/release-applicability/publication.test.ts:observed publication is '
                                 'distinct from source applicability retains exact observed tag-only state',
                                 'vitest:site/test/release-applicability/publication.test.ts:observed publication is '
                                 'distinct from source applicability refuses wrong tag/source/payload identity, '
                                 'duplicate rows and malformed observations',
                                 'vitest:site/test/release-applicability/publication.test.ts:observed publication is '
                                 'distinct from source applicability keeps public-hidden/missing and unavailable '
                                 'observations unknown',
                                 'vitest:site/test/release-applicability/publication.test.ts:observed publication is '
                                 'distinct from source applicability retains source matches while explicitly exposing '
                                 'unknown, draft or published state']}
CELLS = frozenset(RECIPES)


def _regular(info):
    return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and not getattr(info, 'st_file_attributes', 0) & 0x400)


def _version(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink


def read_file(path, limit):
    """Bound acquired regular bytes; diagnostics never include a path/value."""
    path = Path(path)
    before = path.lstat()
    need(_regular(before) and 0 <= before.st_size <= limit, 'source file is not bounded regular bytes')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0)
                 | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        opened = os.fstat(fd)
        need(_regular(opened) and _version(opened) == _version(before), 'source identity changed at acquisition')
        data = bytearray()
        while len(data) <= limit:
            part = os.read(fd, min(1 << 20, limit + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        final, current = os.fstat(fd), path.lstat()
        need(len(data) <= limit and len(data) == before.st_size
             and _regular(final) and _regular(current)
             and _version(final) == _version(current) == _version(before), 'source identity changed during read')
        return bytes(data)
    finally:
        os.close(fd)


def decode(raw):
    def invalid(_value):
        raise ValueError('non-JSON number')
    try:
        return json.loads(raw, object_pairs_hook=reports.unique, parse_constant=invalid)
    except RecursionError:
        raise ValueError('JSON nesting exceeds decoder capacity') from None


def _path(value):
    need(type(value) is str and 0 < len(value.encode('utf8')) <= 4096
         and not any(ord(c) < 32 or ord(c) == 127 for c in value)
         and '\\' not in value and ':' not in value and not value.startswith('/')
         and all(p not in ('', '.', '..') for p in value.split('/'))
         and PurePosixPath(value).as_posix() == value, 'noncanonical source path')
    return value


def namespace_members(repo, source):
    result = {}
    for root in NAMESPACES:
        rows = owner._tree_entries(repo, source, root, recursive=True)
        names = []
        for name, (mode, kind, size) in rows.items():
            if not name.endswith('.py'):
                continue
            _path(name)
            need(mode in ('100644', '100755') and kind == 'blob' and type(size) is int,
                 'Python namespace has an unsupported member')
            names.append(name)
        need(0 < len(names) <= 1024 and not any(n.casefold() == '_host.py' for n in names),
             'Python namespace is incomplete or has a host shadow')
        result[root] = sorted(names)
    return result


def expected_inputs(repo, source, load=None):
    load = load or (lambda commit, path: owner.blob(repo, commit, path))
    paths = set(EXTRAS)
    for root, names in namespace_members(repo, source).items():
        paths.update(root + '/' + name for name in names)
    for root in SOURCE_ROOTS:
        rows = owner._tree_entries(repo, source, root, recursive=True)
        for name, (mode, kind, size) in rows.items():
            _path(name)
            need(mode in ('100644', '100755') and kind == 'blob' and type(size) is int
                 and 0 <= size <= MAX_FILE, 'Docs source namespace has an unsupported member')
            paths.add(root + '/' + name)
    need(0 < len(paths) <= 4096, 'Docs source population exceeds bound')
    result, total = {}, 0
    for path in sorted(paths):
        _path(path)
        raw = load(source, path)
        need(type(raw) is bytes and len(raw) <= MAX_FILE, 'immutable Docs source exceeds bound')
        total += len(raw)
        need(total <= MAX_SOURCE, 'immutable Docs source total exceeds bound')
        result[path] = {'bytes': len(raw), 'sha256': owner.digest(raw)}
    return result


def _package_contract(raw):
    document = decode(raw)
    need(type(document) is dict and type(document.get('scripts')) is dict
         and all(document['scripts'].get(k) == v for k, v in SCRIPTS.items()),
         'original Docs npm lifecycle differs')


def _physical_names(root, *, python_only=False):
    names = []
    for path in root.rglob('*'):
        if '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        info = path.lstat()
        need(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
             'Docs source namespace has a linked member')
        if stat.S_ISDIR(info.st_mode):
            continue
        if python_only and path.suffix != '.py':
            continue
        need(_regular(info), 'Docs source namespace has a nonregular member')
        names.append(path.relative_to(root).as_posix())
        need(len(names) <= 4096, 'Docs source namespace exceeds bound')
    return sorted(names)


def source_snapshot(repo):
    repo = Path(repo).resolve(strict=True)
    source = reports.git(repo, 'rev-parse', 'HEAD')
    tree = reports.git(repo, 'rev-parse', source + '^{tree}')
    need(owner.SHA.fullmatch(source) and owner.SHA.fullmatch(tree), 'Docs source identity unavailable')
    inputs = expected_inputs(repo, source)
    namespaces = namespace_members(repo, source)
    # These are executable/source fixture namespaces. Generated site content is
    # derived output, not an invitation to silently add another executable here.
    for root in ('site/scripts', 'site/test', 'plugins/ca/hooks'):
        expected = sorted(p[len(root)+1:] for p in inputs if p.startswith(root + '/'))
        need(_physical_names(repo / root) == expected, 'Docs working source namespace differs')
    for root, names in namespaces.items():
        need(_physical_names(repo / root, python_only=True) == names, 'Docs Python namespace differs')
    for path, identity in inputs.items():
        raw = read_file(repo / path, MAX_FILE)
        need(len(raw) == identity['bytes'] and owner.digest(raw) == identity['sha256'],
             'Docs working source differs from immutable Git bytes')
    _package_contract(read_file(repo / 'site/package.json', MAX_MANIFEST))
    status = reports._source_git(repo, 'status', '--porcelain=v1', '--untracked-files=all', '-z')
    allowed = status == b'' or (status == b'?? .codearbiter/.artifacts/store.lock\0'
                               and reports.ordinary_native_read_lock(repo))
    return {'source_commit': source, 'source_tree': tree, 'clean': allowed,
            'inputs': inputs, 'python_namespaces': namespaces}


def manifest_document(snapshot):
    return {'format': MANIFEST_FORMAT, 'profile': PROFILE, 'workflow': WORKFLOW, 'job': JOB,
            'source_commit': snapshot['source_commit'], 'source_tree': snapshot['source_tree'],
            'inputs': snapshot['inputs'], 'python_namespaces': snapshot['python_namespaces']}


def validate_manifest(document, req, repo=ROOT):
    need(type(document) is dict and set(document) == {'format', 'profile', 'workflow', 'job',
        'source_commit', 'source_tree', 'inputs', 'python_namespaces'}
         and document['format'] == MANIFEST_FORMAT and document['profile'] == PROFILE
         and document['workflow'] == WORKFLOW and document['job'] == JOB
         and document['source_commit'] == req['source_commit'] and document['source_tree'] == req['source_tree'],
         'Docs source manifest identity differs')
    need(document['inputs'] == expected_inputs(repo, req['source_commit'])
         and document['python_namespaces'] == namespace_members(repo, req['source_commit']),
         'Docs source manifest closure differs')


def prepare_source(repo, output, snapshot=None):
    repo, output = Path(repo).resolve(strict=True), Path(output)
    before = snapshot or source_snapshot(repo)
    need(before['clean'] is True, 'Docs original checkout is not clean')
    output.mkdir(mode=0o700)
    for path, identity in before['inputs'].items():
        raw = read_file(repo / path, MAX_FILE)
        need(len(raw) == identity['bytes'] and owner.digest(raw) == identity['sha256'], 'Docs source changed while retained')
        target = output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
    document = manifest_document(before)
    encoded = json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode() + b'\n'
    need(len(encoded) <= MAX_MANIFEST, 'Docs source manifest exceeds bound')
    with (output / MANIFEST).open('xb') as stream:
        stream.write(encoded)
    return document, owner.digest(encoded)


def parse_named(document, repo, source_inputs):
    need(type(document) is dict and type(document.get('testResults')) is list
         and 0 < len(document['testResults']) <= MAX_ROWS, 'Docs primary named results unavailable')
    parsed = reports.admit_vitest(document, repo=repo, before={'clean': True}, after={'clean': True},
        argv=ARGV, exit_code=0, run_id=0)
    rows = parsed['tests']
    counts = {key: 0 for key in ('numPassedTests', 'numFailedTests', 'numPendingTests', 'numTodoTests')}
    for suite in document['testResults']:
        for case in suite['assertionResults']:
            key = {'passed': 'numPassedTests', 'failed': 'numFailedTests', 'pending': 'numPendingTests',
                   'skipped': 'numPendingTests', 'disabled': 'numPendingTests', 'todo': 'numTodoTests'}[case['status']]
            counts[key] += 1
    need(type(document.get('numTotalTests')) is int and document['numTotalTests'] == len(rows)
         and all(type(document.get(k)) is int and document[k] == v for k, v in counts.items())
         and type(document.get('success')) is bool, 'Docs primary named summary differs')
    need(not document['success'] or document.get('numFailedTestSuites') == 0,
         'Docs primary suite failure contradicts success')
    for row in rows:
        path = row['id'].split(':', 2)[1]
        need(path in source_inputs and path.endswith('.test.ts')
             and path.startswith(('site/test/', 'site/scripts/')), 'Docs named case is outside captured source')
    # Preserve pending/todo rows; only selected complete cases can qualify.
    return rows, {'total': len(rows), **counts, 'success': document['success']}


def named_results(observed):
    rows = observed['tests']
    need(type(rows) is list and 0 < len(rows) <= MAX_ROWS
         and all(type(row) is dict and set(row) == {'id', 'result'} and type(row['id']) is str
                 and 0 < len(row['id'].encode('utf8')) <= reports.MAX_TEST_ID_BYTES
                 and row['result'] in ('passed', 'failed', 'skipped') for row in rows), 'Docs named projection is malformed')
    index = {}
    for row in rows:
        index.setdefault(row['id'], []).append(row['result'])
    need(all(len(values) == 1 for values in index.values()), 'Docs named projection repeats a case')
    return [{'cell': cell, 'result': 'PASSED' if all(index.get(s) == ['passed'] for s in selectors)
             else 'NOT_QUALIFIED', 'selectors': selectors} for cell, selectors in sorted(RECIPES.items())]


def _number_summary(document):
    need(type(document) is dict, 'Docs numeric coverage is unavailable')
    result = {}
    for metric in ('lines', 'branches'):
        row = document.get('total', {}).get(metric)
        need(type(row) is dict and type(row.get('total')) is int and row['total'] > 0
             and type(row.get('covered')) is int and 0 <= row['covered'] <= row['total']
             and type(row.get('pct')) in (int, float) and math.isfinite(row['pct'])
             and 0 <= row['pct'] <= 100, 'Docs numeric coverage is incomplete')
        result[metric] = {key: row[key] for key in ('total', 'covered', 'pct')}
    return result  # Preserve the existing numeric policy; do not invent a new floor.


def rendered_outputs(repo, source):
    raw = {path: read_file(Path(repo) / path, reports.MAX_JSON) for path in RENDERED}
    generated, endpoint = decode(raw[RENDERED[0]]), decode(raw[RENDERED[1]])
    need(type(generated) is dict and generated == endpoint
         and generated.get('build', {}).get('commit') == source, 'Docs rendered data differs from its actual build')
    return {path: {'bytes': len(content), 'sha256': owner.digest(content)} for path, content in raw.items()}


def _write(path, document, maximum=MAX_REPORT):
    raw = json.dumps(document, ensure_ascii=True, separators=(',', ':'), sort_keys=True).encode() + b'\n'
    need(len(raw) <= maximum, 'Docs record exceeds bound')
    with Path(path).open('xb') as stream:
        stream.write(raw)


def observe(repo, source_payload, raw_results, output):
    """Run the unchanged compound lifecycle once, keeping the workflow deadline."""
    repo = Path(repo).resolve(strict=True)
    raw_results, raw_parent = reports._vitest_new_path(raw_results)
    output, output_parent = reports._vitest_new_path(output)
    need(raw_results.name == 'primary-vitest.json' and raw_results != output, 'Docs reporter output role differs')
    before = source_snapshot(repo)
    need(before['clean'], 'Docs original checkout is not clean')
    manifest_raw = read_file(Path(source_payload) / MANIFEST, MAX_MANIFEST)
    manifest = decode(manifest_raw)
    need(manifest == manifest_document(before), 'Docs prepared source differs before original execution')
    launch, runtime = reports._vitest_launch(ARGV)
    fd = os.open(raw_results, os.O_RDWR | os.O_CREAT | os.O_EXCL
                 | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        original = os.fstat(fd)
        with tempfile.TemporaryDirectory(prefix='ca-docs-site-runtime-') as temporary:
            environment = reports._vitest_environment(Path(temporary))
            for key in ('GITHUB_SHA', 'GITHUB_REPOSITORY', 'GITHUB_REF', 'GITHUB_EVENT_NAME', 'RUNNER_OS'):
                if key in os.environ:
                    environment[key] = os.environ[key]
            environment['CODEARBITER_DOCS_NAMED_RESULTS'] = str(raw_results)
            process = start(launch, cwd=repo / 'site', env=environment)
            try:
                code = process.wait()  # Original workflow/job timeout remains the owner.
            except BaseException:
                terminate_tree(process)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
                raise
            need(type(code) is int and -(1 << 31) <= code < (1 << 32), 'Docs command status is invalid')
            try:
                after = source_snapshot(repo)
                stable = before == after and [_ for _ in runtime] == [reports._vitest_runtime_file(r['path']) for r in runtime]
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
                stable = False
            need(all((p.parent.stat().st_dev, p.parent.stat().st_ino) == identity
                     for p, identity in ((raw_results, raw_parent), (output, output_parent))), 'Docs output parent changed')
            try:
                primary, raw_sha = reports._vitest_owned_json(raw_results, fd, original)
                tests, summary = parse_named(primary, repo, before['inputs'])
            except (OSError, ValueError, KeyError, TypeError):
                if code != 0:
                    _write(output, {'format': 'codearbiter-docs-site-refusal/1', 'code': 'PRIMARY_RESULTS_UNAVAILABLE',
                                    'exit_code': code})
                    return code
                raise
            run_id, attempt = os.environ.get('GITHUB_RUN_ID', ''), os.environ.get('GITHUB_RUN_ATTEMPT', '')
            need(run_id.isdigit() and int(run_id) > 0 and attempt.isdigit() and int(attempt) > 0,
                 'Docs original run identity is unavailable')
            document = {'format': OBSERVATION, 'profile': PROFILE, 'workflow': WORKFLOW, 'job': JOB,
                'source_commit': before['source_commit'], 'source_tree': before['source_tree'],
                'docs_run_id': int(run_id), 'run_attempt': int(attempt), 'argv': ARGV,
                'exit_code': code, 'source_stable': stable, 'source_manifest_sha256': owner.digest(manifest_raw),
                'primary_raw_sha256': raw_sha, 'primary_summary': summary, 'tests': tests,
                'launch_inputs': runtime, 'runtime_scope': 'Selected launch inputs only; not an installed host or full third-party graph.',
                'rendered_outputs': {}, 'numeric_summary_sha256': None, 'numeric_totals': {}}
            if code == 0:
                numeric = read_file(repo / 'site/coverage/coverage-summary.json', reports.MAX_JSON)
                document.update(rendered_outputs=rendered_outputs(repo, before['source_commit']),
                    numeric_summary_sha256=owner.digest(numeric), numeric_totals=_number_summary(decode(numeric)))
            _write(output, document)
            return code if code != 0 or stable else 1
    finally:
        os.close(fd)


def validate_observation(record, req, manifest):
    fields = {'format', 'profile', 'workflow', 'job', 'source_commit', 'source_tree', 'docs_run_id',
        'run_attempt', 'argv', 'exit_code', 'source_stable', 'source_manifest_sha256', 'primary_raw_sha256',
        'primary_summary', 'tests', 'launch_inputs', 'runtime_scope', 'rendered_outputs',
        'numeric_summary_sha256', 'numeric_totals'}
    need(type(record) is dict and set(record) == fields and record['format'] == OBSERVATION
         and record['profile'] == PROFILE and record['workflow'] == WORKFLOW and record['job'] == JOB
         and record['source_commit'] == req['source_commit'] and record['source_tree'] == req['source_tree']
         and type(record['docs_run_id']) is int and record['docs_run_id'] == req['ci_run_id']
         and type(record['run_attempt']) is int and record['run_attempt'] > 0
         and record['argv'] == ARGV and type(record['exit_code']) is int and record['exit_code'] == 0
         and record['source_stable'] is True, 'Docs original complete command identity or success differs')
    for field in ('source_manifest_sha256', 'primary_raw_sha256', 'numeric_summary_sha256'):
        need(type(record[field]) is str and owner.DIGEST.fullmatch(record[field]), 'Docs digest is invalid')
    results = named_results(record)
    summary = record['primary_summary']
    need(type(summary) is dict and set(summary) == {'total', 'numPassedTests', 'numFailedTests',
        'numPendingTests', 'numTodoTests', 'success'} and summary['success'] is True
         and all(type(summary[k]) is int and 0 <= summary[k] <= MAX_ROWS
                 for k in summary if k != 'success')
         and summary['total'] == len(record['tests'])
         and summary['numFailedTests'] == 0
         and summary['numPassedTests'] == sum(r['result'] == 'passed' for r in record['tests'])
         and summary['numPendingTests'] + summary['numTodoTests'] == sum(r['result'] == 'skipped' for r in record['tests'])
         and sum(summary[k] for k in ('numPassedTests','numFailedTests','numPendingTests','numTodoTests')) == summary['total'],
         'Docs primary result summary is incomplete')
    for row in record['tests']:
        need(row['id'].startswith('vitest:') and row['id'].split(':', 2)[1] in manifest['inputs'],
             'Docs named test is outside original source closure')
    runtime = record['launch_inputs']
    need(type(runtime) is list and 0 < len(runtime) <= 32
         and record['runtime_scope'] == 'Selected launch inputs only; not an installed host or full third-party graph.',
         'Docs launch scope differs')
    for item in runtime:
        need(type(item) is dict and set(item) == {'path','resolved_path','bytes','sha256','filesystem_id'}
             and all(type(item[k]) is str and 0 < len(item[k].encode('utf8')) <= 4096
                     for k in ('path','resolved_path','filesystem_id'))
             and type(item['bytes']) is int and 0 <= item['bytes'] <= 128 << 20
             and type(item['sha256']) is str and owner.DIGEST.fullmatch(item['sha256']), 'Docs launch identity is invalid')
    need(type(record['rendered_outputs']) is dict and set(record['rendered_outputs']) == set(RENDERED),
         'Docs rendered/data/endpoint complement is incomplete')
    for row in record['rendered_outputs'].values():
        need(type(row) is dict and set(row) == {'bytes','sha256'} and type(row['bytes']) is int
             and 0 < row['bytes'] <= reports.MAX_JSON and type(row['sha256']) is str
             and owner.DIGEST.fullmatch(row['sha256']), 'Docs rendered output identity is invalid')
    need(_number_summary({'total': record['numeric_totals']}) == record['numeric_totals'], 'Docs numeric identity differs')
    return results


def validate_selection_map(document):
    groups = [g for g in reports.validate_selections(document) if g['job'] == JOB]
    need(len(groups) == len(CELLS) and {c for g in groups for c in g['cells']} == CELLS,
         'Docs source selection must declare its exact four findings')
    for group in groups:
        need(len(group['cells']) == 1 and group['payload_name'] == PAYLOAD
             and group['observation'] == 'docs-original-site-coverage' and group['proof_kind'] == 'source-test'
             and group['selectors'] == RECIPES[group['cells'][0]], 'Docs source finding composition differs')


def docs_required(req):
    selected = CELLS.intersection(req['cells'])
    need(all(req['cell_jobs'].get(cell) == JOB for cell in selected)
         and all(name != JOB or cell in CELLS for cell, name in req['cell_jobs'].items()),
         'Docs source job cannot qualify another scope')
    return bool(selected)


def core_requirements(req):
    result = copy.deepcopy(req)
    result['cells'] = [c for c in req['cells'] if c not in CELLS]
    result['cell_jobs'] = {c: job for c, job in req['cell_jobs'].items() if c not in CELLS}
    return result


def _context(run):
    identity = run['id']
    jobs = browser._population(owner.api(f'actions/runs/{identity}/jobs?filter=latest&per_page=100'), 'jobs', 100)
    matches = [job for job in jobs if job.get('name') == JOB]
    need(len(matches) == 1, 'Docs original site-check job missing or ambiguous')
    job = matches[0]
    need(job.get('run_id') == identity and job.get('run_attempt') == run['run_attempt'],
         'Docs site-check job belongs to another run/attempt')
    artifacts = browser._population(owner.api(f'actions/runs/{identity}/artifacts?per_page=100'), 'artifacts', 100)
    need(len({a.get('name') for a in artifacts}) == len(artifacts), 'Docs artifact names ambiguous')
    return job, artifacts


def source_archive(artifact, req, archive, *, repo=ROOT):
    owner.validate_artifact(artifact, req, owner.digest(archive))
    owner.members(archive)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        need(MANIFEST in zipped.namelist() and zipped.getinfo(MANIFEST).file_size <= MAX_MANIFEST,
             'Docs original source manifest missing or too large')
        raw = zipped.read(MANIFEST)
        manifest = decode(raw)
        validate_manifest(manifest, req, repo=repo)
        need(set(zipped.namelist()) == set(manifest['inputs']) | {MANIFEST},
             'Docs source archive population differs')
        for path, identity in manifest['inputs'].items():
            info = zipped.getinfo(path)
            need(info.file_size == identity['bytes'], 'Docs source member size differs')
            need(owner.digest(zipped.read(path)) == identity['sha256'], 'Docs source member bytes differ')
        _package_contract(zipped.read('site/package.json'))
    return manifest, owner.digest(raw)


def _payload_identity(artifact, run):
    need(artifact.get('workflow_run', {}).get('head_branch') == run['head_branch']
         and artifact['workflow_run'].get('repository_id') == run['repository']['id']
         and artifact['workflow_run'].get('head_repository_id') == run['repository']['id'],
         'Docs source artifact repository differs')


def _report(observed, req, run, job, artifact, archive, *, repo=ROOT):
    need(artifact.get('name') == PAYLOAD, 'Docs original source payload role differs')
    _payload_identity(artifact, run)
    manifest, manifest_sha = source_archive(artifact, req, archive, repo=repo)
    results = validate_observation(observed, req, manifest)
    need(observed['run_attempt'] == run['run_attempt'] and observed['source_manifest_sha256'] == manifest_sha,
         'Docs observation source manifest or attempt differs')
    return {'schema': REPORT, 'source_commit': req['source_commit'], 'source_tree': req['source_tree'],
        'docs_run_id': run['id'], 'run_attempt': run['run_attempt'], 'job_id': job['id'],
        'source_artifact_id': artifact['id'], 'source_archive_sha256': owner.digest(archive),
        'observation': observed, 'results': results}


def report_from_observation(observed, req, run, job, artifact, archive, *, repo=ROOT):
    browser._run(run, req['source_commit'], req['ci_run_id'], producing=True)
    need(job.get('run_id') == run['id'] and job.get('run_attempt') == run['run_attempt']
         and job.get('name') == JOB and job.get('status') == 'in_progress' and job.get('conclusion') is None,
         'Docs producer is not its original active site-check job')
    uploads = [step for step in job.get('steps', []) if step.get('name') == UPLOAD]
    need(len(uploads) == 1 and uploads[0].get('status') == 'completed'
         and uploads[0].get('conclusion') == 'success', 'Docs original source upload has not completed')
    return _report(observed, req, run, job, artifact, archive, repo=repo)


def _report_document(artifact, req):
    archive = owner.artifact_bytes(artifact, req)
    need(len(archive) <= 8 << 20, 'Docs source-test report archive exceeds bound')
    owner.members(archive)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        need(zipped.namelist() == [REPORT_FILE] and zipped.getinfo(REPORT_FILE).file_size <= MAX_REPORT,
             'Docs source-test report archive population differs')
        return decode(zipped.read(REPORT_FILE))


def admit(req, *, run_id=None, repo=ROOT):
    run = browser._selected_run(req, run_id)
    need(run.get('head_branch') == 'main', 'final Docs source-test qualification must be main')
    job, artifacts = _context(run)
    need(job.get('status') == 'completed' and job.get('conclusion') == 'success',
         'Docs whole original site-check job did not succeed')
    by_name = {a.get('name'): a for a in artifacts}
    payload = by_name.get(PAYLOAD)
    report_artifact = by_name.get('major-docs-site-test-qualification-' + str(job['id']))
    need(type(payload) is dict and type(report_artifact) is dict, 'Docs original source/report artifacts missing')
    docs_req = {'source_commit': req['source_commit'], 'source_tree': req['source_tree'], 'ci_run_id': run['id']}
    _payload_identity(payload, run)
    _payload_identity(report_artifact, run)
    archive = owner.artifact_bytes(payload, docs_req)
    log = owner.api('actions/jobs/' + str(job['id']) + '/logs', binary=True)
    owner.validate_upload(job, payload, UPLOAD, job_log=log)
    owner.validate_upload(job, report_artifact, REPORT_STEP, job_log=log)
    report = _report_document(report_artifact, docs_req)
    need(type(report) is dict and 'observation' in report, 'Docs source-test report missing')
    expected = _report(report['observation'], docs_req, run, job, payload, archive, repo=repo)
    need(report == expected, 'Docs source-test report differs from original authenticated evidence')
    selected = set(req['cells']) & CELLS
    need(selected and all(row['result'] == 'PASSED' for row in expected['results'] if row['cell'] in selected),
         'Docs selected finding complement is missing, skipped or unsuccessful')
    return {'run_id': run['id'], 'run_attempt': run['run_attempt'], 'job_id': job['id'],
        'source_artifact_id': payload['id'], 'source_archive_sha256': owner.digest(archive),
        'report_artifact_id': report_artifact['id'], 'report_archive_sha256': report_artifact['digest'][7:],
        'results': [row for row in expected['results'] if row['cell'] in selected]}


def produce(req, artifacts, jobs):
    need(docs_required(req), 'Docs source envelope requires its finite population')
    core = owner.produce(core_requirements(req), artifacts, jobs)
    return {'schema': ENVELOPE, 'program_id': owner.PROGRAM, 'state': 'PREPUBLICATION_READY',
        **req, 'core': core, 'docs_source': admit(req)}


def verify(*, record, requirements, **kwargs):
    req = requirements
    owner.validate_run(kwargs['run'], req)
    need(docs_required(req) and type(record) is dict
         and set(record) == {'schema','program_id','state','core','docs_source', *req}
         and record['schema'] == ENVELOPE and record['program_id'] == owner.PROGRAM
         and record['state'] == 'PREPUBLICATION_READY' and all(record.get(k) == v for k,v in req.items()),
         'Docs source readiness envelope differs from selected source/population')
    need(type(record['docs_source']) is dict, 'Docs source authority missing')
    expected = admit(req, run_id=record['docs_source'].get('run_id'))
    need(record['docs_source'] == expected, 'Docs source envelope differs from original evidence')
    owner.verify(record=record['core'], requirements=core_requirements(req), **kwargs)
    return {'state':'PREPUBLICATION_READY','source':req['source_commit'],
        'ci_run_id':req['ci_run_id'],'docs_source_run_id':expected['run_id']}


def emit(repo, observed, output):
    reports.validate_emitter_environment()
    identity = source_snapshot(repo)
    validate_selection_map(reports.load_json(Path(repo) / '.github/major-test-selections.json'))
    source, run_id = os.environ['GITHUB_SHA'], int(os.environ['GITHUB_RUN_ID'])
    need(identity['clean'] and identity['source_commit'] == source, 'Docs emitting source differs')
    run = owner.api('actions/runs/' + str(run_id))
    browser._run(run, source, run_id, producing=True)
    job, artifacts = _context(run)
    payloads = [a for a in artifacts if a.get('name') == PAYLOAD]
    need(len(payloads) == 1, 'Docs exact original source payload missing')
    req = {**identity, 'ci_run_id':run_id}
    payload = payloads[0]
    archive = owner.artifact_bytes(payload, req)
    record = report_from_observation(decode(read_file(Path(observed), MAX_REPORT)), req, run, job, payload, archive, repo=repo)
    _write(Path(output), record)
    return job['id']


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('prepare-source','observe','emit'):
        child = sub.add_parser(command)
        child.add_argument('--repo', type=Path, default=ROOT)
        child.add_argument('--output', type=Path, required=True)
        if command == 'observe':
            child.add_argument('--source-payload', type=Path, required=True)
            child.add_argument('--raw-results', type=Path, required=True)
        if command == 'emit':
            child.add_argument('--observation', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare-source':
            prepare_source(args.repo, args.output)
        elif args.command == 'observe':
            return observe(args.repo, args.source_payload, args.raw_results, args.output)
        else:
            identity = emit(args.repo, args.observation, args.output)
            # Only the positive public job identity crosses the step boundary.
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf8') as handle:
                handle.write('job_id=' + str(identity) + '\n')
        return 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, subprocess.SubprocessError):
        print('Docs original source-test observation refused.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
