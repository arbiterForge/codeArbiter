#!/usr/bin/env python3
# codeArbiter -- inert, bounded source digest acquisition for scout snapshots.
#
# Public API: digest_file(root, relative_path, *, scope_paths, max_bytes,
#                         denied_paths) -> dict with path, digest_method, digest.
# DigestError(code) reports a bounded, code-owned failure without source bytes.
# Read only approved regular files beneath the actual worktree. Never invoke Git,
# filters, repository helpers, or network. Identity checks are cooperative drift
# checks, not protection against a hostile same-user ABA replacement.
# context_snapshot(start, *, source_paths, source_scopes, membership,
#                  target_paths, allowed_effect_paths) -> dict
# compare_context_snapshot(saved, start, *, boundary) -> dict

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import threading

import _contextreportlib as _report
from _gitexec import git_executable, root_bound_git_env

DIGEST_METHOD = 'sha256-raw'
DEFAULT_MAX_BYTES = 1024 * 1024
HARD_MAX_BYTES = 16 * 1024 * 1024
_CHUNK_BYTES = 64 * 1024
_SENSITIVE_NAMES = frozenset({'.env', '.ssh', '.aws', '.gnupg', '.npmrc', '.pypirc', 'credentials',
                              'credentials.json', 'id_rsa', 'id_ed25519',
                              'known_hosts', 'secrets.json'})
_SENSITIVE_SUFFIXES = ('.pem', '.key', '.p12', '.pfx')


class DigestError(ValueError):
    """No usable identity was acquired; diagnostics never include file content."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


class MembershipError(ValueError):
    """No safe, bounded membership identity could be acquired."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


# Closed acquisition vocabulary, deliberately narrower than report transport.
MEMBERSHIP_PREDICATES = frozenset({'manifests', 'instructions', 'configuration',
                                   'tests', 'infrastructure', 'security', 'data'})
MEMBERSHIP_METHOD = 'sha256-membership-v1'
HARD_MAX_FILES = 4096
HARD_MAX_DIRECTORIES = 512
SOURCE_SNAPSHOT_METHOD = 'sha256-source-snapshot-v1'
_MAX_SNAPSHOT_PATHS = 64
_MAX_GIT_OUTPUT = 4 * 1024 * 1024
_GIT_TIMEOUT = 8
_MANIFESTS = frozenset({'package.json', 'pyproject.toml', 'cargo.toml', 'go.mod',
                        'pom.xml', 'build.gradle', 'build.gradle.kts', 'requirements.txt',
                        'pipfile', 'gemfile', 'composer.json'})
_INSTRUCTIONS = frozenset({'agents.md', 'claude.md', 'gemini.md', 'copilot-instructions.md'})
_CONFIGURATION = frozenset({'.editorconfig', '.gitattributes', 'tsconfig.json',
                            'pytest.ini', 'tox.ini', 'setup.cfg', 'mypy.ini'})
_INFRASTRUCTURE = frozenset({'dockerfile', 'compose.yaml', 'compose.yml'})
_SECURITY = frozenset({'security.md', 'codeowners', 'dependabot.yml', 'dependabot.yaml'})
_DATA = frozenset({'schema.sql', 'schema.prisma'})
_BOUNDARY_DIRECTORIES = {'tests': frozenset({'tests', 'test', '__tests__'}),
                         'infrastructure': frozenset({'infra', 'infrastructure', 'workflows'}),
                         'security': frozenset({'security'}),
                         'data': frozenset({'migrations', 'schemas'})}
_VENDOR_DIRECTORIES = frozenset({'vendor', 'node_modules', 'third_party'})
_GENERATED_DIRECTORIES = frozenset({'generated', 'dist', 'build', '__pycache__', 'target'})


def _membership_path(value, *, root=False):
    try:
        return _report._path(value, 'path', root=root)
    except _report.ReportError:
        raise MembershipError('UNSAFE_PATH') from None


def _membership_match(predicate, path, directory):
    name = path.rsplit('/', 1)[-1].casefold()
    if directory:
        return name in _BOUNDARY_DIRECTORIES.get(predicate, ())
    if predicate == 'manifests':
        return name in _MANIFESTS or name.endswith(('.csproj', '.fsproj', '.vbproj'))
    if predicate == 'instructions':
        return name in _INSTRUCTIONS
    if predicate == 'configuration':
        return name in _CONFIGURATION
    if predicate == 'tests':
        return ((name.startswith('test_') and name.endswith('.py')) or
                name.endswith(('.test.ts', '.test.tsx', '.test.js', '.test.jsx',
                               '.spec.ts', '.spec.js')))
    if predicate == 'infrastructure':
        return name in _INFRASTRUCTURE or name.endswith(('.tf', '.tfvars'))
    if predicate == 'security':
        return name in _SECURITY
    if predicate == 'data':
        return name in _DATA or name.endswith(('.sql', '.prisma'))
    return False


def _membership_info(path):
    try:
        info = path.lstat()
    except OSError:
        return None
    if (stat.S_ISLNK(info.st_mode) or
            getattr(info, 'st_file_attributes', 0) &
            getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)):
        return None
    return info


def _repository_boundary(directory):
    """A nested .git marker is a boundary; its contents are never read."""
    try:
        marker = (directory / '.git').lstat()
    except FileNotFoundError:
        return None
    except OSError:
        return 'unreadable'
    if (stat.S_ISLNK(marker.st_mode) or
            getattr(marker, 'st_file_attributes', 0) &
            getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)):
        return 'unreadable'
    if stat.S_ISDIR(marker.st_mode):
        return 'nested_repository'
    if stat.S_ISREG(marker.st_mode):
        return 'submodule'
    return 'unreadable'


def _scope_boundary(actual_root, relative):
    """Classify every ancestor before constructing a scoped traversal root."""
    if relative == '.':
        return None
    current = actual_root
    for part in relative.split('/'):
        current = current / part
        info = _membership_info(current)
        if info is None or not stat.S_ISDIR(info.st_mode):
            return 'unreadable'
        folded = part.casefold()
        if folded in _VENDOR_DIRECTORIES:
            return 'vendor'
        if folded in _GENERATED_DIRECTORIES:
            return 'generated'
        marker = _repository_boundary(current)
        if marker:
            return marker
    return None


def _validated_path(value, *, root=False):
    try:
        return _report._path(value, 'path', root=root)
    except _report.ReportError:
        raise DigestError('UNSAFE_PATH') from None


def _identity(info, *, content):
    core = (info.st_dev, info.st_ino, info.st_mode)
    if content:
        return core + (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    return core


def _components(root, parts):
    """Collect path identities without following an in-worktree link or reparse point."""
    result = []
    for index in range(len(parts) + 1):
        path = root.joinpath(*parts[:index])
        try:
            info = path.lstat()
        except OSError:
            raise DigestError('UNREADABLE') from None
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, 'st_file_attributes', 0) &
            getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
        ):
            raise DigestError('UNSAFE_LINK')
        final = index == len(parts)
        if final:
            if not stat.S_ISREG(info.st_mode):
                raise DigestError('NOT_REGULAR')
        elif not stat.S_ISDIR(info.st_mode):
            raise DigestError('NOT_REGULAR')
        result.append(_identity(info, content=final))
    return result


def digest_file(root, relative_path, *, scope_paths=('.',),
                max_bytes=DEFAULT_MAX_BYTES, denied_paths=()):
    """Return an explicit SHA-256 identity of bounded raw bytes, or raise.

    `root` is a caller-trusted worktree, resolved before path construction.
    `relative_path`, scope and deny paths use the report envelope's lexical
    grammar. Missing, short, oversized, changing or nonregular files never
    yield a digest. No Git normalization or filter is consulted.
    """
    path = _validated_path(relative_path)
    if type(max_bytes) is not int or not 0 <= max_bytes <= HARD_MAX_BYTES:
        raise DigestError('BYTE_LIMIT')
    if type(scope_paths) not in (tuple, list) or not scope_paths:
        raise DigestError('OUT_OF_SCOPE')
    scopes = tuple(_validated_path(value, root=True) for value in scope_paths)
    if not any(_report._within(path, scope) for scope in scopes):
        raise DigestError('OUT_OF_SCOPE')
    if type(denied_paths) not in (tuple, list):
        raise DigestError('UNSAFE_PATH')
    denied = tuple(_validated_path(value, root=True) for value in denied_paths)
    parts = path.split('/')
    if (any(part.casefold() in _SENSITIVE_NAMES or
            part.casefold().startswith('.env.') or
            part.casefold().endswith(_SENSITIVE_SUFFIXES) for part in parts)
            or any(_report._within(path, value) for value in denied)):
        raise DigestError('SENSITIVE_PATH')
    try:
        actual_root = Path(root).resolve(strict=True)
        if not actual_root.is_dir():
            raise DigestError('UNREADABLE')
    except (OSError, RuntimeError, TypeError, ValueError):
        raise DigestError('UNREADABLE') from None
    candidate = actual_root.joinpath(*parts)
    before = _components(actual_root, parts)
    try:
        candidate.resolve(strict=True).relative_to(actual_root)
    except (OSError, RuntimeError, ValueError):
        raise DigestError('UNSAFE_LINK') from None
    if before[-1][3] > max_bytes:
        raise DigestError('BYTE_LIMIT')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError:
        raise DigestError('UNREADABLE') from None
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise DigestError('NOT_REGULAR')
        # Windows descriptor ctime can differ from path ctime for the same file.
        # Compare it path-to-path below; descriptor identity still binds the open.
        if _identity(opened, content=True)[:5] != before[-1][:5]:
            raise DigestError('SOURCE_CHANGED')
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, min(_CHUNK_BYTES, max_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise DigestError('BYTE_LIMIT')
            digest.update(chunk)
        if total != opened.st_size:
            raise DigestError('PARTIAL_READ')
        # Stable timestamps can conceal a same-size rewrite during the read.
        # Re-read the bound descriptor before accepting its first byte digest.
        os.lseek(descriptor, 0, os.SEEK_SET)
        confirmation = hashlib.sha256()
        confirmed = 0
        while True:
            chunk = os.read(descriptor, min(_CHUNK_BYTES, max_bytes - confirmed + 1))
            if not chunk:
                break
            confirmed += len(chunk)
            if confirmed > max_bytes:
                raise DigestError('BYTE_LIMIT')
            confirmation.update(chunk)
        if confirmed != total or confirmation.digest() != digest.digest():
            raise DigestError('SOURCE_CHANGED')
        if _identity(os.fstat(descriptor), content=True)[:5] != before[-1][:5]:
            raise DigestError('SOURCE_CHANGED')
        if _components(actual_root, parts) != before:
            raise DigestError('SOURCE_CHANGED')
        try:
            candidate.resolve(strict=True).relative_to(actual_root)
        except (OSError, RuntimeError, ValueError):
            raise DigestError('SOURCE_CHANGED') from None
        return {'path': path, 'digest_method': DIGEST_METHOD, 'digest': digest.hexdigest()}
    except OSError:
        raise DigestError('UNREADABLE') from None
    finally:
        os.close(descriptor)


def membership_snapshot(root, predicate, *, scope_paths=('.',), excluded=(),
                        max_files=1024, max_directories=128):
    """Inventory code-owned path membership in caller-authorized directory scopes.

    Exclusions are caller declarations, not verified ignore rules. Root .git
    metadata is omitted. No file content, Git, helper, shell or network is used.
    A digest identifies only a complete searched subset; any gap prevents a
    broad negative claim. This does not bind T-008 worktree/HEAD identity.
    """
    if type(predicate) is not str or predicate not in MEMBERSHIP_PREDICATES:
        raise MembershipError('UNKNOWN_PREDICATE')
    if (type(max_files) is not int or not 1 <= max_files <= HARD_MAX_FILES or
            type(max_directories) is not int or not 1 <= max_directories <= HARD_MAX_DIRECTORIES):
        raise MembershipError('INVALID_BOUND')
    if type(scope_paths) not in (tuple, list) or not 1 <= len(scope_paths) <= _report.MAX_PATHS:
        raise MembershipError('INVALID_SCOPE')
    scopes = sorted(_membership_path(p, root=True) for p in scope_paths)
    if len({p.casefold() for p in scopes}) != len(scopes) or any(
            _report._within(a, b) or _report._within(b, a)
            for index, a in enumerate(scopes) for b in scopes[index + 1:]):
        raise MembershipError('OVERLAPPING_SCOPE')
    if type(excluded) not in (tuple, list) or len(excluded) > _report.MAX_PATHS:
        raise MembershipError('INVALID_EXCLUSION')
    declared = {}
    for entry in excluded:
        if type(entry) is not dict or set(entry) != {'path', 'reason'}:
            raise MembershipError('INVALID_EXCLUSION')
        path = _membership_path(entry['path'], root=True)
        if type(entry['reason']) is not str or entry['reason'] not in _report.EXCLUSIONS:
            raise MembershipError('UNKNOWN_EXCLUSION')
        if not any(_report._within(path, scope) for scope in scopes):
            raise MembershipError('OUT_OF_SCOPE')
        if path.casefold() in {p.casefold() for p in declared}:
            raise MembershipError('DUPLICATE_EXCLUSION')
        declared[path] = entry['reason']
    paths = list(declared)
    if any(_report._within(a, b) or _report._within(b, a)
           for index, a in enumerate(paths) for b in paths[index + 1:]):
        raise MembershipError('OVERLAPPING_EXCLUSION')
    try:
        actual_root = Path(root).resolve(strict=True)
        if not actual_root.is_dir():
            raise MembershipError('UNREADABLE_ROOT')
    except (OSError, RuntimeError, TypeError, ValueError):
        raise MembershipError('UNREADABLE_ROOT') from None

    matches, dispositions = set(), dict(declared)
    files = directories = 0
    stack = list(reversed(scopes))
    while stack:
        relative = stack.pop()
        if any(_report._within(relative, boundary) for boundary in dispositions):
            continue
        boundary = _scope_boundary(actual_root, relative)
        if boundary:
            dispositions[relative] = boundary
            continue
        path = actual_root if relative == '.' else actual_root.joinpath(*relative.split('/'))
        info = _membership_info(path)
        if info is None or not stat.S_ISDIR(info.st_mode):
            dispositions[relative] = 'unreadable'
            continue
        directories += 1
        if directories > max_directories:
            raise MembershipError('BOUND_EXCEEDED')
        try:
            with os.scandir(path) as stream:
                names = []
                for entry in stream:
                    if relative == '.' and entry.name == '.git':
                        continue
                    names.append(entry.name)
                    if len(names) > max_files + max_directories:
                        raise MembershipError('BOUND_EXCEEDED')
        except OSError:
            dispositions[relative] = 'unreadable'
            continue
        if len({name.casefold() for name in names}) != len(names):
            dispositions[relative] = 'unreadable'
            continue
        children = []
        for name in sorted(names, key=lambda value: (value.casefold(), value)):
            child = name if relative == '.' else relative + '/' + name
            try:
                _membership_path(child)
            except MembershipError:
                dispositions[relative] = 'unreadable'
                break
            if any(_report._within(child, boundary) for boundary in dispositions):
                continue
            child_info = _membership_info(path / name)
            if child_info is None:
                files += 1
                dispositions[child] = 'unreadable'
            elif stat.S_ISDIR(child_info.st_mode):
                folded = name.casefold()
                if folded in _VENDOR_DIRECTORIES:
                    dispositions[child] = 'vendor'
                elif folded in _GENERATED_DIRECTORIES:
                    dispositions[child] = 'generated'
                else:
                    if _membership_match(predicate, child, True):
                        matches.add(child)
                    children.append(child)
            elif stat.S_ISREG(child_info.st_mode):
                files += 1
                if _membership_match(predicate, child, False):
                    matches.add(child)
            else:
                files += 1
                dispositions[child] = 'unreadable'
            if files > max_files:
                raise MembershipError('BOUND_EXCEEDED')
        else:
            stack.extend(reversed(children))
            after = _membership_info(path)
            if after is None or _identity(after, content=True) != _identity(info, content=True):
                dispositions[relative] = 'unreadable'
            continue
        # An unsafe spelling means no membership claim for this directory.
        matches.difference_update({p for p in matches if _report._within(p, relative)})

    ordered = sorted(matches, key=lambda value: (value.casefold(), value))
    gaps = [{'path': path, 'reason': reason} for path, reason in sorted(
        dispositions.items(), key=lambda item: (item[0].casefold(), item[0]))]
    complete = not any(e['reason'] in ('sparse', 'unreadable', 'outside_authorized_scope')
                       for e in gaps)
    identity = None
    if complete:
        payload = json.dumps({'method': MEMBERSHIP_METHOD, 'predicate': predicate,
                              'scope_paths': scopes, 'matches': ordered, 'excluded': gaps},
                             sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')
        identity = hashlib.sha256(payload).hexdigest()
    return {'status': 'complete' if complete else 'not_inspected',
            'predicate': predicate, 'scope_paths': scopes, 'matches': ordered,
            'excluded': gaps, 'digest_method': MEMBERSHIP_METHOD, 'digest': identity,
            'negative_proof': complete and not gaps and not ordered}


class SnapshotError(ValueError):
    """No complete source/target snapshot was acquired; code contains no source bytes."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _snapshot_paths(values, *, root=False):
    if type(values) not in (list, tuple) or len(values) > _MAX_SNAPSHOT_PATHS:
        raise SnapshotError('INVALID_PATHS')
    try:
        paths = [_report._path(value, 'path', root=root) for value in values]
    except _report.ReportError:
        raise SnapshotError('INVALID_PATHS') from None
    if len({value.casefold() for value in paths}) != len(paths):
        raise SnapshotError('DUPLICATE_PATH')
    return sorted(paths)


def _snapshot_membership(values):
    if type(values) not in (list, tuple) or len(values) > 16:
        raise SnapshotError('INVALID_MEMBERSHIP')
    result = []
    for item in values:
        if type(item) not in (list, tuple) or len(item) != 2 or item[0] not in MEMBERSHIP_PREDICATES:
            raise SnapshotError('INVALID_MEMBERSHIP')
        scopes = _snapshot_paths(item[1], root=True)
        if not scopes:
            raise SnapshotError('INVALID_MEMBERSHIP')
        result.append([item[0], scopes])
    if len({json.dumps(item) for item in result}) != len(result):
        raise SnapshotError('INVALID_MEMBERSHIP')
    return sorted(result, key=lambda item: (item[0], item[1]))


def _git_read(root, args, *, limit=_MAX_GIT_OUTPUT, optional=False):
    """Fixed inert Git read with no shell, filters, hooks, fsmonitor or auto writes."""
    env = root_bound_git_env()
    for name in tuple(env):
        if name.startswith('GIT_CONFIG_') or name in ('GIT_CONFIG', 'GIT_EXTERNAL_DIFF',
                                                       'GIT_DIFF_OPTS', 'GIT_ASKPASS',
                                                       'GIT_TRACE', 'GIT_NAMESPACE',
                                                       'GIT_EXEC_PATH'):
            env.pop(name, None)
    env.update({'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_REPLACE_OBJECTS': '1',
                'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                'GIT_TERMINAL_PROMPT': '0', 'GIT_NO_LAZY_FETCH': '1',
                'GIT_PROTOCOL_FROM_USER': '0'})
    argv = [git_executable(), '-C', str(root), '--literal-pathspecs',
            '-c', 'core.fsmonitor=false', *args]
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    except (OSError, RuntimeError):
        raise SnapshotError('GIT_UNAVAILABLE') from None
    output = []
    def read_bounded():
        output.append(process.stdout.read(limit + 1))
    worker = threading.Thread(target=read_bounded, daemon=True)
    worker.start()
    worker.join(_GIT_TIMEOUT)
    if worker.is_alive():
        process.kill()
        worker.join(_GIT_TIMEOUT)
        process.wait()
        process.stdout.close()
        raise SnapshotError('GIT_UNAVAILABLE')
    if not output or len(output[0]) > limit:
        process.kill()
        process.wait()
        process.stdout.close()
        raise SnapshotError('GIT_BOUND_EXCEEDED')
    try:
        code = process.wait(timeout=_GIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        process.stdout.close()
        raise SnapshotError('GIT_UNAVAILABLE') from None
    process.stdout.close()
    if code and not optional:
        raise SnapshotError('GIT_UNAVAILABLE')
    return code, output[0]


def _git_text(root, args, *, optional=False):
    code, output = _git_read(root, args, optional=optional)
    try:
        return code, output.decode('utf-8', 'strict').strip()
    except UnicodeDecodeError:
        raise SnapshotError('GIT_UNAVAILABLE') from None


def _worktree_identity(start):
    try:
        start = Path(start).resolve(strict=True)
        if not start.is_dir():
            raise SnapshotError('UNREADABLE_ROOT')
    except (OSError, RuntimeError, TypeError, ValueError):
        raise SnapshotError('UNREADABLE_ROOT') from None
    _, locations = _git_text(start, ['rev-parse', '--path-format=absolute',
                                     '--show-toplevel', '--absolute-git-dir', '--git-common-dir'])
    lines = locations.splitlines()
    if len(lines) != 3:
        raise SnapshotError('GIT_UNAVAILABLE')
    try:
        root, git_dir, common_dir = (str(Path(value).resolve(strict=True)) for value in lines)
        if not start.is_relative_to(Path(root)):
            raise SnapshotError('UNREADABLE_ROOT')
        if not Path(git_dir).is_dir() or not Path(common_dir).is_dir():
            raise SnapshotError('GIT_UNAVAILABLE')
    except (OSError, RuntimeError, ValueError):
        raise SnapshotError('GIT_UNAVAILABLE') from None
    head_code, head = _git_text(root, ['rev-parse', '--verify', 'HEAD'], optional=True)
    branch_code, branch = _git_text(root, ['symbolic-ref', '-q', '--short', 'HEAD'], optional=True)
    head = head if head_code == 0 else None
    branch = branch if branch_code == 0 else None
    if head is not None and (len(head) not in (40, 64) or
                             any(ch not in '0123456789abcdef' for ch in head)):
        raise SnapshotError('GIT_UNAVAILABLE')
    upstream = {'status': 'none', 'ref': None, 'relation': 'unknown',
                'freshness': 'local_only'}
    if branch:
        upstream['status'] = 'unknown'
        code, ref = _git_text(root, ['rev-parse', '--symbolic-full-name',
                                     '@{upstream}'], optional=True)
        if code == 0:
            if not ref.startswith('refs/') or any(ch not in
                    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/._-'
                    for ch in ref):
                raise SnapshotError('GIT_UNAVAILABLE')
            _, oid = _git_text(root, ['rev-parse', '--verify', ref])
            relation = 'unknown'
            if head:
                _, counts = _git_text(root, ['rev-list', '--left-right', '--count',
                                             head + '...' + oid])
                parts = counts.split()
                if len(parts) != 2 or not all(part.isdecimal() for part in parts):
                    raise SnapshotError('GIT_UNAVAILABLE')
                ahead, behind = map(int, parts)
                relation = ('same' if not ahead and not behind else
                            'ahead' if ahead and not behind else
                            'behind' if behind and not ahead else 'diverged')
            upstream = {'status': 'known_local', 'ref': ref, 'relation': relation,
                        'freshness': 'local_only'}
    return {'root': root, 'git_dir': git_dir, 'common_dir': common_dir,
            'head': head, 'branch': branch, 'detached': branch is None and head is not None,
            'upstream': upstream,
            'fork': {'status': 'unknown', 'basis': 'local_refs_only'}}


def _git_entries(root, args, *, tree=False):
    _, data = _git_read(root, args)
    result = {}
    for raw in data.split(b'\0'):
        if not raw:
            continue
        try:
            prefix, path = raw.split(b'\t', 1)
            path = _report._path(path.decode('utf-8', 'strict'), 'path')
            fields = prefix.decode('ascii').split()
        except (ValueError, UnicodeDecodeError, _report.ReportError):
            raise SnapshotError('GIT_UNAVAILABLE') from None
        if (len(fields) != 3 or fields[1] != 'blob') if tree else (len(fields) != 3 or fields[2] != '0'):
            raise SnapshotError('GIT_UNAVAILABLE')
        oid = fields[2] if tree else fields[1]
        if path in result or len(oid) not in (40, 64) or any(
                ch not in '0123456789abcdef' for ch in oid):
            raise SnapshotError('GIT_UNAVAILABLE')
        result[path] = {'mode': fields[0], 'oid': oid}
    return result


def _preimage(root, path):
    candidate = Path(root)
    for part in path.split('/'):
        candidate = candidate / part
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            return {'status': 'absent', 'digest_method': None, 'digest': None}
        except OSError:
            raise SnapshotError('UNREADABLE_TARGET') from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & getattr(
                stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
            raise SnapshotError('UNSAFE_TARGET')
    try:
        result = digest_file(root, path)
    except DigestError:
        raise SnapshotError('UNREADABLE_TARGET') from None
    return {'status': 'file', 'digest_method': result['digest_method'],
            'digest': result['digest']}


def _member_info(root, path):
    """Recheck a T-007 match without following a changed ancestor or leaf."""
    candidate = Path(root)
    root_info = _membership_info(candidate)
    if root_info is None or not stat.S_ISDIR(root_info.st_mode):
        raise SnapshotError('MEMBERSHIP_UNKNOWN')
    parts = path.split('/')
    for index, part in enumerate(parts):
        candidate = candidate / part
        info = _membership_info(candidate)
        if info is None:
            raise SnapshotError('MEMBERSHIP_UNKNOWN')
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise SnapshotError('MEMBERSHIP_UNKNOWN')
    try:
        candidate.resolve(strict=True).relative_to(Path(root))
    except (OSError, RuntimeError, ValueError):
        raise SnapshotError('MEMBERSHIP_UNKNOWN') from None
    after = _membership_info(candidate)
    if after is None or _identity(after, content=True) != _identity(info, content=True):
        raise SnapshotError('SOURCE_CHANGED')
    return info


def _capture_context(start, selectors):
    worktree = _worktree_identity(start)
    root = worktree['root']
    source_paths = set(selectors['source_paths'])
    target_paths = selectors['target_paths']
    effects = selectors['allowed_effect_paths']
    membership = []
    directory_checks = {}
    for predicate, scopes in selectors['membership']:
        try:
            unexcluded = membership_snapshot(root, predicate, scope_paths=scopes)
        except MembershipError:
            raise SnapshotError('MEMBERSHIP_UNKNOWN') from None
        if unexcluded['status'] != 'complete' or unexcluded['digest'] is None:
            raise SnapshotError('MEMBERSHIP_UNKNOWN')
        if any(_report._within(path, role) or _report._within(role, path)
               for path in unexcluded['matches'] for role in target_paths + effects):
            raise SnapshotError('OVERLAPPING_ROLE')
        excluded = [{'path': path, 'reason': 'generated'} for path in target_paths + effects
                    if any(_report._within(path, scope) for scope in scopes)]
        try:
            result = membership_snapshot(root, predicate, scope_paths=scopes, excluded=excluded)
        except MembershipError:
            raise SnapshotError('MEMBERSHIP_UNKNOWN') from None
        if result['status'] != 'complete' or result['digest'] is None:
            raise SnapshotError('MEMBERSHIP_UNKNOWN')
        for path in result['matches']:
            if any(_report._within(path, role) or _report._within(role, path)
                   for role in target_paths + effects):
                raise SnapshotError('OVERLAPPING_ROLE')
            info = _member_info(root, path)
            if stat.S_ISREG(info.st_mode):
                source_paths.add(path)
            elif stat.S_ISDIR(info.st_mode):
                directory_checks[path] = _identity(info, content=True)
            else:
                raise SnapshotError('MEMBERSHIP_UNKNOWN')
        membership.append(result)
    if len(source_paths) > _MAX_SNAPSHOT_PATHS:
        raise SnapshotError('BOUND_EXCEEDED')
    for path in source_paths:
        if any(_report._within(path, role) or _report._within(role, path)
               for role in target_paths + effects):
            raise SnapshotError('OVERLAPPING_ROLE')
    files = {}
    for path in sorted(source_paths):
        try:
            files[path] = digest_file(root, path, scope_paths=selectors['source_scopes'])
        except DigestError:
            raise SnapshotError('SOURCE_UNKNOWN') from None
    wanted = sorted(files)
    if wanted:
        index = _git_entries(root, ['ls-files', '--stage', '-z', '--', *wanted])
        tree = (_git_entries(root, ['ls-tree', '-r', '-z', 'HEAD', '--', *wanted], tree=True)
                if worktree['head'] else {})
    else:
        index, tree = {}, {}
    staged, untracked, raw_dirty = [], [], []
    for path in wanted:
        entry = index.get(path)
        if entry is None:
            untracked.append(path)
        else:
            if entry != tree.get(path):
                staged.append(path)
            _, blob = _git_read(root, ['cat-file', 'blob', entry['oid']],
                                limit=HARD_MAX_BYTES + 1)
            if hashlib.sha256(blob).hexdigest() != files[path]['digest']:
                raw_dirty.append(path)
    for path, identity in directory_checks.items():
        info = _member_info(root, path)
        if not stat.S_ISDIR(info.st_mode) or _identity(info, content=True) != identity:
            raise SnapshotError('SOURCE_CHANGED')
    git_state = {'staged': staged, 'untracked': untracked, 'raw_dirty': raw_dirty,
                 'index': index, 'head_tree': tree}
    source = {'digest_method': SOURCE_SNAPSHOT_METHOD, 'files': files,
              'membership': membership, 'git_state': git_state}
    payload = {'worktree': worktree, 'selectors': selectors, 'source': source}
    source['digest'] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                                  ensure_ascii=True).encode('utf-8')).hexdigest()
    targets = {path: _preimage(root, path) for path in target_paths}
    return {'method': SOURCE_SNAPSHOT_METHOD, 'selectors': selectors,
            'worktree': worktree, 'source': source, 'targets': targets,
            'allowed_effects': effects}


def context_snapshot(start, *, source_paths=(), source_scopes=('.',), membership=(),
                     target_paths=(), allowed_effect_paths=()):
    """Bind declared external inputs separately from target and allowed output paths."""
    selectors = {'source_paths': _snapshot_paths(source_paths),
                 'source_scopes': _snapshot_paths(source_scopes, root=True),
                 'membership': _snapshot_membership(membership),
                 'target_paths': _snapshot_paths(target_paths),
                 'allowed_effect_paths': _snapshot_paths(allowed_effect_paths)}
    if not selectors['source_scopes']:
        raise SnapshotError('INVALID_SCOPE')
    if not selectors['source_paths'] and not selectors['membership']:
        raise SnapshotError('EMPTY_SOURCE')
    roles = selectors['source_paths'] + selectors['target_paths'] + selectors['allowed_effect_paths']
    if any(_report._within(a, b) or _report._within(b, a)
           for index, a in enumerate(roles) for b in roles[index + 1:]):
        raise SnapshotError('OVERLAPPING_ROLE')
    if any(not any(_report._within(path, scope) for scope in selectors['source_scopes'])
           for path in selectors['source_paths']):
        raise SnapshotError('OUT_OF_SCOPE')
    first = _capture_context(start, selectors)
    second = _capture_context(start, selectors)
    if first != second:
        raise SnapshotError('SOURCE_CHANGED')
    return first


def compare_context_snapshot(saved, start=None, *, boundary='join'):
    """Reacquire a complete snapshot; action additionally requires target preimages."""
    if boundary not in ('join', 'action'):
        raise SnapshotError('INVALID_BOUNDARY')
    if type(saved) is not dict or set(saved) != {
            'method', 'selectors', 'worktree', 'source', 'targets', 'allowed_effects'} or (
            saved['method'] != SOURCE_SNAPSHOT_METHOD or type(saved['source']) is not dict or
            saved['source'].get('digest_method') != SOURCE_SNAPSHOT_METHOD):
        raise SnapshotError('INVALID_SNAPSHOT')
    selectors = saved['selectors']
    if type(selectors) is not dict or set(selectors) != {
            'source_paths', 'source_scopes', 'membership', 'target_paths',
            'allowed_effect_paths'}:
        raise SnapshotError('INVALID_SNAPSHOT')
    if (type(saved['worktree']) is not dict or set(saved['worktree']) != {
            'root', 'git_dir', 'common_dir', 'head', 'branch', 'detached',
            'upstream', 'fork'} or
            type(saved['source']) is not dict or set(saved['source']) != {
                'digest_method', 'digest', 'files', 'membership', 'git_state'} or
            type(saved['targets']) is not dict or
            type(saved['allowed_effects']) is not list or
            saved['allowed_effects'] != selectors['allowed_effect_paths'] or
            not _sha256_hex(saved['source']['digest'])):
        raise SnapshotError('INVALID_SNAPSHOT')
    if (set(saved['targets']) != set(selectors['target_paths']) or
            any(type(value) is not dict or set(value) != {
                'status', 'digest_method', 'digest'} or
                (value['status'] == 'absent' and (
                    value['digest_method'] is not None or value['digest'] is not None)) or
                (value['status'] == 'file' and (
                    value['digest_method'] != DIGEST_METHOD or
                    not _sha256_hex(value['digest']))) or
                value['status'] not in ('absent', 'file')
                for value in saved['targets'].values())):
        raise SnapshotError('INVALID_SNAPSHOT')
    if (type(saved['source']['files']) is not dict or
            any(type(value) is not dict or set(value) != {'path', 'digest_method', 'digest'} or
                value['path'] != path or value['digest_method'] != DIGEST_METHOD or
                not _sha256_hex(value['digest'])
                for path, value in saved['source']['files'].items()) or
            type(saved['source']['membership']) is not list or
            any(type(value) is not dict or value.get('digest_method') != MEMBERSHIP_METHOD or
                value.get('status') != 'complete' or not _sha256_hex(value.get('digest'))
                for value in saved['source']['membership']) or
            type(saved['source']['git_state']) is not dict or
            set(saved['source']['git_state']) != {
                'staged', 'untracked', 'raw_dirty', 'index', 'head_tree'}):
        raise SnapshotError('INVALID_SNAPSHOT')
    if (type(saved['worktree']['upstream']) is not dict or
            set(saved['worktree']['upstream']) != {
                'status', 'ref', 'relation', 'freshness'} or
            saved['worktree']['upstream']['freshness'] != 'local_only' or
            saved['worktree']['fork'] != {
                'status': 'unknown', 'basis': 'local_refs_only'}):
        raise SnapshotError('INVALID_SNAPSHOT')
    try:
        saved_root = saved['worktree']['root']
        if type(saved_root) is not str:
            raise SnapshotError('INVALID_SNAPSHOT')
    except (KeyError, TypeError):
        raise SnapshotError('INVALID_SNAPSHOT') from None
    current = context_snapshot(start if start is not None else saved['worktree']['root'],
                               source_paths=selectors['source_paths'],
                               source_scopes=selectors['source_scopes'],
                               membership=selectors['membership'],
                               target_paths=selectors['target_paths'],
                               allowed_effect_paths=selectors['allowed_effect_paths'])
    source_current = (saved['selectors'] == current['selectors'] and
                      saved['worktree'] == current['worktree'] and
                      saved['source'] == current['source'] and
                      saved['allowed_effects'] == current['allowed_effects'])
    targets_current = saved['targets'] == current['targets']
    return {'boundary': boundary, 'admitted': source_current and (
            boundary == 'join' or targets_current), 'source_current': source_current,
            'targets_current': targets_current}


def compare_context_dependencies(saved, *, source_paths=(), membership=(),
                                 target_paths=(), start=None):
    """Recheck only declared input and target identities for a context claim.

    This is for incremental context assessment. It never substitutes for the
    strict whole-snapshot action/join admission above. The physical worktree
    and Git directory remain bound, while unrelated HEAD and source changes
    cannot make a separate claim stale.
    """
    if type(saved) is not dict or saved.get('method') != SOURCE_SNAPSHOT_METHOD:
        raise SnapshotError('INVALID_SNAPSHOT')
    try:
        selectors = saved['selectors']
        original = saved['source']
        worktree = saved['worktree']
        targets = saved['targets']
        files = original['files']
        members = original['membership']
        scopes = selectors['source_scopes']
        effects = selectors['allowed_effect_paths']
        paths = _snapshot_paths(source_paths)
        selected_members = _snapshot_membership(membership)
        selected_targets = _snapshot_paths(target_paths)
        signed_source = dict(original)
        signed_source.pop('digest', None)
        payload = {'worktree': worktree, 'selectors': selectors, 'source': signed_source}
        expected_digest = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(',', ':'),
            ensure_ascii=True).encode('utf-8')).hexdigest()
        if (original['digest_method'] != SOURCE_SNAPSHOT_METHOD or
                original['digest'] != expected_digest or
                not set(paths) <= set(files) or
                not set(selected_targets) <= set(targets) or
                not {(item[0], tuple(item[1])) for item in selected_members} <=
                {(item['predicate'], tuple(item['scope_paths'])) for item in members}):
            raise SnapshotError('INVALID_SNAPSHOT')
        root = start if start is not None else worktree['root']
        actual = _worktree_identity(root)
        if any(actual[key] != worktree[key]
               for key in ('root', 'git_dir', 'common_dir')):
            raise SnapshotError('WORKTREE_CHANGED')
        current = context_snapshot(root, source_paths=paths, source_scopes=scopes,
                                   membership=selected_members,
                                   target_paths=selected_targets,
                                   allowed_effect_paths=effects)
        original_members = {(item['predicate'], tuple(item['scope_paths'])): item
                            for item in members}
        current_members = {(item['predicate'], tuple(item['scope_paths'])): item
                           for item in current['source']['membership']}
        source_current = (all(files[path] == current['source']['files'].get(path)
                              for path in paths) and
                          all(original_members[(item[0], tuple(item[1]))] ==
                              current_members.get((item[0], tuple(item[1])))
                              for item in selected_members))
        targets_current = all(targets[path] == current['targets'].get(path)
                              for path in selected_targets)
        return {'source_current': source_current, 'targets_current': targets_current,
                'admitted': source_current and targets_current}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise SnapshotError('INVALID_SNAPSHOT') from None


def _sha256_hex(value):
    return type(value) is str and len(value) == 64 and all(
        character in '0123456789abcdef' for character in value)


def capture_context_effects(saved):
    """Read declared output preimages and mtimes for a bounded no-op check.

    This is an observation of files at one instant, not a writer or a proof
    that no transient write occurred between observations.
    """
    try:
        if type(saved) is not dict or saved.get('method') != SOURCE_SNAPSHOT_METHOD:
            raise SnapshotError('INVALID_SNAPSHOT')
        selectors = saved['selectors']
        worktree = saved['worktree']
        paths = _snapshot_paths(selectors['target_paths'] +
                                selectors['allowed_effect_paths'])
        if (type(worktree) is not dict or type(worktree.get('root')) is not str or
                not paths):
            raise SnapshotError('INVALID_SNAPSHOT')
        actual = _worktree_identity(worktree['root'])
        if any(actual[key] != worktree[key] for key in
               ('root', 'git_dir', 'common_dir')):
            raise SnapshotError('WORKTREE_CHANGED')
        root = Path(worktree['root'])
        files = {}
        for path in paths:
            candidate = root.joinpath(*path.split('/'))
            try:
                before = candidate.lstat()
            except FileNotFoundError:
                before = None
            except OSError:
                raise SnapshotError('UNREADABLE_TARGET') from None
            preimage = _preimage(root, path)
            try:
                after = candidate.lstat()
            except FileNotFoundError:
                after = None
            except OSError:
                raise SnapshotError('UNREADABLE_TARGET') from None
            if (before is None) != (after is None) or (before is not None and
                    _identity(before, content=True) != _identity(after, content=True)):
                raise SnapshotError('TARGET_CHANGED')
            if preimage['status'] == 'absent':
                if after is not None:
                    raise SnapshotError('TARGET_CHANGED')
                files[path] = {'status': 'absent', 'digest': None,
                               'size': None, 'mtime_ns': None}
            else:
                if after is None or not stat.S_ISREG(after.st_mode):
                    raise SnapshotError('TARGET_CHANGED')
                files[path] = {'status': 'file', 'digest': preimage['digest'],
                               'size': after.st_size, 'mtime_ns': after.st_mtime_ns}
        return {'root': str(root), 'files': files}
    except SnapshotError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError):
        raise SnapshotError('INVALID_SNAPSHOT') from None


def compare_context_effects(before, after):
    """Classify final byte and timestamp differences without inferring writes."""
    if (type(before) is not dict or type(after) is not dict or
            set(before) != {'root', 'files'} or set(after) != {'root', 'files'} or
            before['root'] != after['root'] or type(before['files']) is not dict or
            type(after['files']) is not dict or
            set(before['files']) != set(after['files'])):
        raise SnapshotError('EFFECT_CONTEXT_MISMATCH')
    bytes_changed, timestamp_only = [], []
    for path in sorted(before['files']):
        _snapshot_paths((path,))
        old, new = before['files'][path], after['files'][path]
        if (type(old) is not dict or type(new) is not dict or
                set(old) != {'status', 'digest', 'size', 'mtime_ns'} or
                set(new) != {'status', 'digest', 'size', 'mtime_ns'}):
            raise SnapshotError('INVALID_EFFECTS')
        for item in (old, new):
            if item['status'] == 'absent':
                if any(item[key] is not None for key in ('digest','size','mtime_ns')):
                    raise SnapshotError('INVALID_EFFECTS')
            elif item['status'] == 'file':
                if (not _sha256_hex(item['digest']) or
                        type(item['size']) is not int or item['size'] < 0 or
                        type(item['mtime_ns']) is not int or item['mtime_ns'] < 0):
                    raise SnapshotError('INVALID_EFFECTS')
            else:
                raise SnapshotError('INVALID_EFFECTS')
        if any(old[key] != new[key] for key in ('status', 'digest', 'size')):
            bytes_changed.append(path)
        elif old['mtime_ns'] != new['mtime_ns']:
            timestamp_only.append(path)
    return {'no_op': not bytes_changed and not timestamp_only,
            'byte_changes': bytes_changed,
            'timestamp_only_changes': timestamp_only}
