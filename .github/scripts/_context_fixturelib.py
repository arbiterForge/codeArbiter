#!/usr/bin/env python3
"""Test-owned brownfield repositories; never an onboarding or instruction writer.

Load a closed, bounded fixture catalog and materialize one create-only workspace.
Only fixed Git operations execute. Repository commands and evaluator checks remain
inert data. Evaluator records live outside the solver workspace and Git history;
this placement is not proof that a host sandbox denies access to sibling paths.
There are no import-time filesystem, Git, environment or network side effects.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

MAX_CATALOG_BYTES = 256 * 1024
MAX_FILE_BYTES = 32 * 1024
SETUPS = frozenset({'committed', 'unborn', 'detached', 'linked', 'sparse'})
KINDS = frozenset({'feature', 'fix', 'test', 'review'})
TAGS = frozenset({'tiny', 'instructed', 'monorepo', 'infrastructure', 'conflict',
                  'partial', 'dirty', 'linked', 'unborn', 'sparse', 'ignored'})
CASE_KEYS = frozenset({'id', 'tags', 'setup', 'files', 'staged_edits',
                       'working_edits', 'task', 'oracle', 'oracle_sha256',
                       'snapshot_sha256'})


class FixtureError(ValueError):
    """Invalid fixture input or unsafe materialization target; no success implied."""


def canonical_digest(value: object) -> str:
    """Bind fixture data identity, not the correctness or approval of its oracle."""
    raw = json.dumps(value, ensure_ascii=True, allow_nan=False,
                     sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _shape(value: object, keys: set | frozenset, where: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise FixtureError('invalid closed shape: ' + where)
    return value


def _string(value: object, limit: int, where: str) -> str:
    if type(value) is not str or not value:
        raise FixtureError('invalid bounded string: ' + where)
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError as error:
        raise FixtureError('invalid Unicode: ' + where) from error
    if size > limit:
        raise FixtureError('invalid bounded string: ' + where)
    return value


def _path(value: object) -> str:
    path = _string(value, 240, 'path')
    if path.startswith('/') or '\\' in path or ':' in path:
        raise FixtureError('unsafe fixture path')
    for part in path.split('/'):
        if (part in {'', '.', '..'} or part.casefold() == '.git'
                or part.endswith((' ', '.')) or any(ord(c) < 32 or ord(c) == 127 for c in part)
                or any(c in '<>"|?*' for c in part)
                or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?', part)):
            raise FixtureError('unsafe fixture path')
    return path


def _files(values: object, *, initial: bool) -> dict[str, str]:
    if type(values) is not list or len(values) > 64 or (initial and not values):
        raise FixtureError('invalid fixture file count')
    result, folded = {}, set()
    for value in values:
        _shape(value, {'path', 'text', 'sha256'}, 'file')
        path = _path(value['path'])
        if path.casefold() in folded:
            raise FixtureError('duplicate or case-colliding fixture path')
        text = value['text']
        if type(text) is not str:
            raise FixtureError('invalid fixture content')
        try:
            raw = text.encode('utf-8')
        except UnicodeError as error:
            raise FixtureError('invalid Unicode fixture content') from error
        if len(raw) > MAX_FILE_BYTES:
            raise FixtureError('invalid fixture content')
        if hashlib.sha256(raw).hexdigest() != value['sha256']:
            raise FixtureError('fixture content identity mismatch')
        result[path] = text
        folded.add(path.casefold())
    for path in folded:
        if any('/'.join(path.split('/')[:i]) in folded for i in range(1, len(path.split('/')))):
            raise FixtureError('file/directory fixture collision')
    return result


def validate_catalog(value: object) -> dict:
    """Validate every case before any fixture path or process can be created."""
    _shape(value, {'schema_version', 'campaign', 'oracle_state', 'cases'}, 'catalog')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise FixtureError('unsupported fixture schema')
    if value['campaign'] != 'exercise-ready-brownfield' or value['oracle_state'] != 'proposed':
        raise FixtureError('fixture catalog cannot convey campaign approval')
    cases = value['cases']
    if type(cases) is not list or not 1 <= len(cases) <= 32:
        raise FixtureError('invalid fixture case count')
    ids = set()
    for case in cases:
        _shape(case, CASE_KEYS, 'case')
        ident = _string(case['id'], 64, 'id')
        if not re.fullmatch(r'[a-z][a-z0-9-]*', ident) or ident in ids:
            raise FixtureError('invalid or duplicate case id')
        ids.add(ident)
        tags = case['tags']
        if (type(tags) is not list or not tags or any(type(t) is not str for t in tags)
                or len(set(tags)) != len(tags) or not set(tags) <= TAGS):
            raise FixtureError('invalid fixture tags')
        if type(case['setup']) is not str or case['setup'] not in SETUPS:
            raise FixtureError('unknown setup recipe')
        files = _files(case['files'], initial=True)
        if case['setup'] in {'linked', 'unborn', 'sparse'} and case['setup'] not in tags:
            raise FixtureError('setup coverage is mislabeled')
        if case['setup'] == 'sparse' and not (any(p.startswith('app/') for p in files)
                and any('/' in p and not p.startswith('app/') for p in files)):
            raise FixtureError('sparse fixture must include visible and excluded scopes')
        for key in ('staged_edits', 'working_edits'):
            edits = _files(case[key], initial=False)
            # Validate the final union before creating partial on-disk state.
            files.update(edits)
        _files([{'path': p, 'text': t, 'sha256': hashlib.sha256(t.encode()).hexdigest()}
                for p, t in files.items()], initial=True)
        initial = {f['path']: f['sha256'] for f in case['files']}
        if canonical_digest(initial) != case['snapshot_sha256']:
            raise FixtureError('fixture snapshot identity mismatch')
        _shape(case['task'], {'kind', 'prompt'}, 'task')
        if type(case['task']['kind']) is not str or case['task']['kind'] not in KINDS:
            raise FixtureError('unknown task kind')
        _string(case['task']['prompt'], 4096, 'task prompt')
        oracle = _shape(case['oracle'], {'disposition', 'default_new_instruction_files',
                                         'preserve_paths', 'checks'}, 'oracle')
        if oracle['disposition'] not in ('task_possible', 'needs_decision', 'repair_required'):
            raise FixtureError('unknown expected disposition')
        if type(oracle['default_new_instruction_files']) is not int or oracle['default_new_instruction_files'] != 0:
            raise FixtureError('fixture does not authorize native instruction generation')
        if type(oracle['preserve_paths']) is not list or len(oracle['preserve_paths']) > 64:
            raise FixtureError('invalid preservation set')
        if any(type(p) is not str for p in oracle['preserve_paths']):
            raise FixtureError('invalid preservation path')
        if len(set(oracle['preserve_paths'])) != len(oracle['preserve_paths']):
            raise FixtureError('duplicate preservation path')
        for path in oracle['preserve_paths']:
            if _path(path) not in files:
                raise FixtureError('preservation path is not a fixture file')
        if type(oracle['checks']) is not list or not 1 <= len(oracle['checks']) <= 16:
            raise FixtureError('invalid evaluator checks')
        for check in oracle['checks']:
            _string(check, 1024, 'evaluator check')
        if canonical_digest(oracle) != case['oracle_sha256']:
            raise FixtureError('oracle identity mismatch')
    return value


def _pairs(pairs: list) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise FixtureError('duplicate JSON key')
        value[key] = item
    return value


def load_catalog(path: str | Path) -> dict:
    """Read bounded UTF-8 JSON; duplicate keys and nonfinite values are errors."""
    with open(path, 'rb') as source:
        raw = source.read(MAX_CATALOG_BYTES + 1)
    if len(raw) > MAX_CATALOG_BYTES:
        raise FixtureError('fixture catalog too large')
    def bad_constant(_value):
        raise FixtureError('nonfinite fixture value')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                           parse_constant=bad_constant)
        return validate_catalog(value)
    except (UnicodeError, RecursionError, TypeError, KeyError) as error:
        raise FixtureError('malformed fixture catalog') from error


def _linked(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def snapshot(workspace: str | Path) -> dict[str, str]:
    """Record raw regular-file hashes, excluding Git storage and rejecting links."""
    workspace = Path(workspace)
    if _linked(workspace):
        raise FixtureError('linked fixture workspace')
    result = {}
    for directory, dirs, names in os.walk(workspace, followlinks=False):
        dirs[:] = [d for d in dirs if d != '.git']
        for name in dirs + names:
            if name == '.git':
                continue
            path = Path(directory) / name
            if _linked(path):
                raise FixtureError('linked fixture content')
            if path.is_file():
                result[path.relative_to(workspace).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            elif name in names:
                raise FixtureError('nonregular fixture content')
    return dict(sorted(result.items()))


def materialize(catalog: dict, case_id: str, destination: str | Path) -> dict:
    """Build a new test-owned instance; never invoke fixture-declared commands.

    The caller supplies an existing trusted parent. Concurrent hostile filesystem
    mutation and actual host confinement require separate integration tests.
    """
    validate_catalog(catalog)
    selected = [case for case in catalog['cases'] if case['id'] == case_id]
    if len(selected) != 1:
        raise FixtureError('unknown fixture case')
    case = selected[0]
    destination = Path(destination).absolute()
    for path in (destination, *destination.parents):
        if path.exists() or path.is_symlink():
            if _linked(path):
                raise FixtureError('linked fixture destination')
    if destination.exists() or not destination.parent.is_dir():
        raise FixtureError('destination must be new under an existing trusted parent')
    git = shutil.which('git')
    if git is None:
        raise FixtureError('Git is required for fixture creation')
    destination.mkdir()
    control = destination / 'control'; control.mkdir()
    evaluator = destination / 'evaluator'; evaluator.mkdir()
    solver = destination / 'solver'
    initial = destination / 'primary' if case['setup'] == 'linked' else solver
    initial.mkdir()
    empty_config = control / 'gitconfig'; empty_config.write_bytes(b'')
    environment = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=str(empty_config),
                       GIT_TERMINAL_PROMPT='0', GIT_AUTHOR_NAME='Context Fixture',
                       GIT_COMMITTER_NAME='Context Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                       GIT_COMMITTER_EMAIL='fixture@example.invalid',
                       GIT_AUTHOR_DATE='2000-01-01T00:00:00+00:00',
                       GIT_COMMITTER_DATE='2000-01-01T00:00:00+00:00')
    def call(*args, cwd=initial):
        return subprocess.run([git, *args], cwd=cwd, env=environment, check=True,
                              capture_output=True, timeout=20).stdout
    def put(items, where):
        for item in items:
            path = where / item['path']; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(item['text'].encode('utf-8'))
    call('init', '--quiet', '--initial-branch=fixture')
    call('config', 'core.autocrlf', 'false')
    call('config', 'core.filemode', 'false')
    put(case['files'], initial)
    # Files are fixture-owned, not a user's checkout. Ignored inputs remain ignored.
    call('add', '--all')
    if case['setup'] != 'unborn':
        call('commit', '--quiet', '-m', 'Create deterministic context fixture')
    if case['setup'] == 'linked':
        call('worktree', 'add', '--quiet', '--detach', str(solver), 'HEAD')
    elif case['setup'] == 'detached':
        call('checkout', '--quiet', '--detach', 'HEAD')
    elif case['setup'] == 'sparse':
        call('sparse-checkout', 'init', '--cone')
        call('sparse-checkout', 'set', 'app')
    put(case['staged_edits'], solver)
    if case['staged_edits']:
        call('add', '--', *(f['path'] for f in case['staged_edits']), cwd=solver)
    put(case['working_edits'], solver)
    (evaluator / 'oracle.json').write_bytes((json.dumps(case['oracle'], sort_keys=True, indent=2)+'\n').encode())
    (evaluator / 'identity.json').write_bytes((json.dumps({
        'case_id': case_id, 'case_sha256': canonical_digest(case),
        'task_sha256': canonical_digest(case['task']), 'oracle_sha256': case['oracle_sha256'],
        'fixture_snapshot_sha256': case['snapshot_sha256'], 'setup': case['setup'],
        'worktree_files': snapshot(solver), 'evidence_kind': 'fixture-placement-only',
    }, sort_keys=True, indent=2)+'\n').encode())
    return {'solver': solver, 'evaluator': evaluator, 'task': dict(case['task']),
            'setup': case['setup'], 'files': snapshot(solver)}
