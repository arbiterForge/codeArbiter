"""Closed opt-in identities for the existing actual Python/npm binding test.

No commands are added: the callback is the original _bind_commands invocation.
This is raw identity evidence, never a task verdict or publication authority.
"""
from __future__ import annotations
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import sysconfig
import tempfile

FORMAT = 'codearbiter.native-npm-binding-observation/1'
TASKS = ('HW-04', 'NT-04')
COUNTS = (0, 30, 31, 32)
UPLOAD = 'Upload original npm binding identities'
ARTIFACT = 'native-npm-binding-identities-'
PROFILE = 'actual-python-npm-binding/1'
OBSERVER = '.github/scripts/npm_binding_observation.py'
HEX = re.compile(r'[0-9a-f]{64}\Z')
SOURCE_FILE_LIMIT = 64 << 20
IDENTITY_FILE_LIMIT = 512 << 20  # existing bounded tool-identity owner ceiling
RUNTIME_FILE_LIMIT = 32768
RUNTIME_DIRECTORY_LIMIT = 2048
RUNTIME_ENTRY_LIMIT = 65536
RUNTIME_BYTE_LIMIT = 512 << 20
SIDECAR_JSON_LIMIT = 16 << 20
LINK_TARGET_LIMIT = 4096
LINUX_CONFIG_IMPORTS = {
    'linux/amd64': '_sysconfigdata__linux_x86_64-linux-gnu',
    'linux/arm64': '_sysconfigdata__linux_aarch64-linux-gnu',
}
EVIDENCE_PARENTS = ('TestCompletionAdmitsActualProducerLaunchBindingCounts',
                    'TestCompletionLaunchFileBoundMatchesContract',
                    'TestCompletionWorkspaceRejectsIdentityAndCommandSubstitution')
ROLE_PARENTS = ('TestQualifiedRunnerContractAcceptsDirectAndNativeNPM',
                'TestCompletionRunnerContractKeepsProfilesSeparate',
                'TestQualifiedRunnerContractRejectsBindingMutations',
                'TestRunnerProfilesCannotBeRelabelled',
                'TestQualifiedRunnerContractAcceptsWorkspaceManifestClosure',
                'TestQualifiedRunnerContractRejectsInvalidWorkspaceManifestClosure',
                'TestQualifiedRunnerContractRejectsExitOnlyWorkspaceManifestClosure',
                'TestQualifiedRunnerContractRejectsPrefixHelperWithoutNativeNPM',
                'TestQualifiedRunnerContractSharesLaunchFileBound')


def require(value, message):
    if not value:
        raise ValueError(message)


def _consume_identity(path, limit, consume):
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not path.is_symlink()
            and not getattr(before, 'st_file_attributes', 0) & 0x400
            and 0 <= before.st_size <= limit, 'unavailable bounded identity file')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    try:
        opened = os.fstat(fd)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns), 'identity changed at open')
        size = 0
        while True:
            part = os.read(fd, min(1 << 20, limit + 1 - size))
            if not part:
                break
            size += len(part)
            require(size <= limit, 'identity file grew beyond bound')
            consume(part)
        after = os.fstat(fd); final = path.lstat()
        identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns)
        require(identity(opened) == identity(after) == identity(final), 'identity changed during read')
        return size
    finally:
        os.close(fd)


def read(path, limit=SOURCE_FILE_LIMIT):
    chunks = []
    _consume_identity(path, limit, chunks.append)
    return b''.join(chunks)


def file_identity(path, limit=IDENTITY_FILE_LIMIT):
    # Hash in bounded chunks without retaining executable/runtime bytes in RAM.
    digest = hashlib.sha256()
    size = _consume_identity(path, limit, digest.update)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def source_snapshot(repo):
    repo = Path(repo).resolve(strict=True)
    core = repo / 'core/pysrc'
    names = sorted(p.name for p in core.iterdir() if p.name.endswith('.py'))
    require(0 < len(names) <= 128 and all(n.isascii() for n in names)
            and not any(p.name.casefold() == '_host.py' for p in core.iterdir()),
            'unsupported core Python import namespace')
    result = {'core/pysrc/' + name: file_identity(core / name, SOURCE_FILE_LIMIT) for name in names}
    result[OBSERVER] = file_identity(repo / OBSERVER, SOURCE_FILE_LIMIT)
    require(sum(x['bytes'] for x in result.values()) <= 16 << 20, 'source inventory exceeds bound')
    return result


def link_identity(path):
    """Inert link text/identity only: never open or traverse its target."""
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISLNK(before.st_mode), 'runtime link changed kind')
    target = os.readlink(path)
    require(isinstance(target, str) and 0 < len(target.encode('utf8')) <= LINK_TARGET_LIMIT
            and '\x00' not in target, 'runtime link target exceeds bound')
    after = path.lstat()
    identity = lambda row: (row.st_dev, row.st_ino, row.st_mode, row.st_size, row.st_mtime_ns)
    require(identity(before) == identity(after) and target == os.readlink(path)
            and identity(before) == identity(path.lstat()), 'runtime link changed during read')
    return {'target': target, 'identity': {'device': before.st_dev, 'inode': before.st_ino,
            'mode': before.st_mode, 'bytes': before.st_size, 'mtime_ns': before.st_mtime_ns}}


def runtime_snapshot():
    # Bound the actual interpreter, standard-library and extension lookup roots.
    # -I/-S and the private empty pycache prefix exclude user/site bytecode.
    roots = {'stdlib': Path(sysconfig.get_path('stdlib')).resolve(strict=True)}
    dlls = Path(sys.base_prefix) / 'DLLs'
    if dlls.is_dir():
        roots['extensions'] = dlls.resolve(strict=True)
    paths = {'interpreter': Path(sys.executable).resolve(strict=True)}
    for name in ('python3.dll', f'python{sys.version_info.major}{sys.version_info.minor}.dll'):
        path = Path(sys.base_prefix) / name
        if path.is_file():
            paths[name] = path.resolve(strict=True)
    library, directory = sysconfig.get_config_var('LDLIBRARY'), sysconfig.get_config_var('LIBDIR')
    if library and directory:
        path = Path(directory) / library
        if path.is_file():
            paths['python-library'] = path.resolve(strict=True)
    directories, links, population = {}, {}, 0
    for label, root in roots.items():
        pending = [root]
        while pending:
            directory = pending.pop()
            require(len(directories) < RUNTIME_DIRECTORY_LIMIT,
                    f'runtime directory bound exceeded: observed={len(directories)+1} limit={RUNTIME_DIRECTORY_LIMIT}')
            entries = sorted(directory.iterdir(), key=lambda p: p.name)
            key = label + '/' + directory.relative_to(root).as_posix()
            directories[key] = [p.name for p in entries]
            population += len(entries)
            require(population <= RUNTIME_ENTRY_LIMIT,
                    f'runtime directory population exceeds bound: observed={population} limit={RUNTIME_ENTRY_LIMIT}')
            for path in entries:
                if path.name == 'site-packages':
                    continue  # -S; never admitted as an imported runtime module.
                entry = path.lstat()
                coordinate = label + '/' + path.relative_to(root).as_posix()
                if stat.S_ISLNK(entry.st_mode):
                    links[coordinate] = link_identity(path)
                elif getattr(entry, 'st_file_attributes', 0) & 0x400:
                    raise ValueError('unsupported runtime reparse entry: coordinate_sha256=' +
                                     hashlib.sha256(coordinate.encode('utf8')).hexdigest())
                elif stat.S_ISDIR(entry.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(entry.st_mode):
                    paths[coordinate] = path
                else:
                    raise ValueError('nonregular runtime inventory entry: coordinate_sha256=' +
                                     hashlib.sha256(coordinate.encode('utf8')).hexdigest())
                observed = len(paths) + len(links)
                require(observed <= RUNTIME_FILE_LIMIT,
                        f'runtime file bound exceeded: observed={observed} limit={RUNTIME_FILE_LIMIT}')
    files, total = {}, 0
    for label, path in sorted(paths.items()):
        expected = path.lstat().st_size
        require(0 <= expected and total + expected <= RUNTIME_BYTE_LIMIT,
                f'runtime byte bound exceeded: observed={total+expected} limit={RUNTIME_BYTE_LIMIT}')
        identity = file_identity(path, min(IDENTITY_FILE_LIMIT, RUNTIME_BYTE_LIMIT-total))
        total += identity['bytes']
        files[label] = identity
    return {'version': list(sys.version_info[:3]), 'implementation': sys.implementation.name,
            'sys_platform': sys.platform, 'isolated': sys.flags.isolated,
            'no_site': sys.flags.no_site, 'no_user_site': sys.flags.no_user_site,
            'dont_write_bytecode': bool(sys.dont_write_bytecode), 'files': files,
            'directories': directories, 'links': links}, paths


def consumed_imports(repo, source_inputs, runtime_paths):
    imports = []
    by_runtime = {path: label for label, path in runtime_paths.items()}
    for name, module in sorted(sys.modules.copy().items()):
        spec = getattr(module, '__spec__', None)
        origin = getattr(spec, 'origin', None)
        if origin in ('built-in', 'frozen'):
            imports.append({'name': name, 'kind': origin, 'path': None})
            continue
        path = getattr(module, '__file__', None)
        if not path:
            continue
        path = Path(path).resolve(strict=True)
        if path.is_relative_to(repo):
            relative = path.relative_to(repo).as_posix()
            require(relative in source_inputs, 'import outside declared source profile')
            imports.append({'name': name, 'kind': 'source', 'path': relative})
        else:
            require(path in by_runtime, 'import outside captured Python runtime')
            imports.append({'name': name, 'kind': 'runtime', 'path': by_runtime[path]})
    require(len(imports) <= 512, 'import population exceeds bound')
    return imports


def observe(repo, root, count, platform, output):
    require(count in COUNTS and platform.split('/')[0] ==
            {'win32': 'windows', 'linux': 'linux', 'darwin': 'darwin'}.get(sys.platform), 'wrong producer platform/count')
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.no_user_site
            and sys.dont_write_bytecode, 'binding profile requires isolated no-site/no-bytecode Python')
    repo = Path(repo).resolve(strict=True)
    output = Path(output)
    require(output.is_absolute() and output.resolve(strict=True) == output and output.is_dir()
            and not output.is_relative_to(repo), 'sidecar output must be an external owned directory')
    output_identity = output.stat()
    fields = {key: os.environ.get(key, '') for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB')}
    require(os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('GITHUB_REPOSITORY') == 'arbiterForge/codeArbiter'
            and re.fullmatch(r'[0-9a-f]{40}', fields['GITHUB_SHA'])
            and all(re.fullmatch(r'[1-9][0-9]*', fields[k]) for k in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'))
            and fields['GITHUB_JOB'] == 'artifact-native-build', 'missing original builder identity')
    require('_artifactauthoritylib' not in sys.modules, 'producer imported before identity observation')
    before = source_snapshot(repo)
    runtime_before, runtime_paths = runtime_snapshot()
    with tempfile.TemporaryDirectory(prefix='hw04-empty-bytecode-') as cache:
        previous = sys.pycache_prefix
        sys.pycache_prefix = cache
        try:
            authority = importlib.import_module('_artifactauthoritylib')
            definition = {'argv': ['npm','test'], 'cwd': '.', 'required_tests': ['example test']}
            bindings = authority._bind_commands(Path(root).resolve(strict=True),
                {'commands': [{'definition': definition, 'definition_sha256': 'a'*64}]}, {})
        finally:
            sys.pycache_prefix = previous
    imports = consumed_imports(repo, before, runtime_paths)
    launch = []
    require(isinstance(bindings, list) and len(bindings) == 1, 'one original binding required')
    for row in bindings[0]['launch_files']:
        path = Path(row['path'])
        identity = file_identity(path)
        require(identity['sha256'] == row['sha256'], 'produced launch identity changed')
        launch.append({'role': row['role'], **identity})
    after = source_snapshot(repo); runtime_after, _ = runtime_snapshot()
    require(before == after and runtime_before == runtime_after, 'consumed source/runtime changed')
    record = {'format': FORMAT, 'profile': PROFILE, 'source_commit': fields['GITHUB_SHA'],
              'ci_run_id': int(fields['GITHUB_RUN_ID']), 'run_attempt': int(fields['GITHUB_RUN_ATTEMPT']),
              'producer_job': fields['GITHUB_JOB'], 'platform': platform, 'workspace_count': count,
              'source_before': before, 'source_after': after, 'imports': imports,
              'runtime_before': runtime_before, 'runtime_after': runtime_after,
              'bindings_sha256': hashlib.sha256(json.dumps(bindings, sort_keys=True, separators=(',',':')).encode()).hexdigest(),
              'launch_files': launch}
    encoded = encode_record(record)
    require((output.stat().st_dev, output.stat().st_ino) == (output_identity.st_dev, output_identity.st_ino)
            and output.resolve(strict=True) == output, 'owned sidecar directory changed')
    path = output / f'workspaces-{count}.json'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os,'O_BINARY',0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(encoded)
    return bindings


def encode_record(record):
    encoded = (json.dumps(record, sort_keys=True, separators=(',',':')) + '\n').encode()
    require(len(encoded) <= SIDECAR_JSON_LIMIT,
            f'binding sidecar exceeds bound: observed={len(encoded)} limit={SIDECAR_JSON_LIMIT}')
    return encoded


def selectors(platform=None):
    prefix = 'go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/'
    result = [prefix + 'evidence:' + name for name in EVIDENCE_PARENTS]
    result += [prefix + 'observation:' + name for name in ROLE_PARENTS]
    result += [prefix + 'evidence:' + EVIDENCE_PARENTS[0] + '/workspaces-' + str(n) for n in COUNTS]
    result += [prefix + 'evidence:' + EVIDENCE_PARENTS[1] + '/' + str(n) for n in (33,34,37,38)]
    children = {
        'TestCompletionRunnerContractKeepsProfilesSeparate': ('valid','missing-closure','relabel-old','wrong-root','raw-drift'),
        'TestQualifiedRunnerContractRejectsBindingMutations': (
            'missing_collector','invented_collector','exit-only_named_results','missing_provenance',
            'missing_wrapper','duplicate_role','unknown_role','relative_path','runtime_hash','runtime_path',
            'cli_path','wrapper_path','missing_manifest','wrong_manifest','unexpected_npm_prefix',
            'mutated_argument','extra_argument','unknown_field','unknown_provenance_field'),
        'TestQualifiedRunnerContractRejectsInvalidWorkspaceManifestClosure': (
            'duplicate_workspace','missing_root','root_as_workspace','outside_root','unclean_workspace',
            'not_a_package_manifest','relative_workspace','duplicate_executable_role','missing_npm_prefix','wrong_npm_prefix'),
        'TestQualifiedRunnerContractAcceptsWorkspaceManifestClosure': tuple(
            f'native-{native}-manifests-{count}' for native in ('false','true') for count in (1,2,32)),
    }
    result += [prefix + 'observation:' + parent + '/' + child
               for parent, names in children.items() for child in names]
    result += [prefix + 'evidence:' + EVIDENCE_PARENTS[2] + '/' + child for child in (
        'root-id','cwd-id','common-id','common-path','foreign-worktree','executable',
        'launch-id','launch-bytes','relative-root','empty-bindings')]
    if platform is not None and platform.startswith('windows/'):
        result.append(prefix + 'evidence:TestCompletionWorkspaceLegacyWindowsIdentity')
    return sorted(result)


def tasks(value):
    require(isinstance(value, list) and value and all(type(x) is str and x in TASKS for x in value)
            and value == sorted(set(value)), 'invalid npm binding task selection')
    return value


def expected_inputs(repo, source, load):
    """Immutable Git owner supplies the expected consumed Python namespace."""
    import major_readiness as owner
    rows = owner._tree_entries(repo, source, 'core/pysrc')
    names = sorted(name for name in rows if name.endswith('.py'))
    require(0 < len(names) <= 128 and all(name.isascii() and '/' not in name for name in names)
            and not any(name.casefold() == '_host.py' for name in rows), 'unsupported immutable Python namespace')
    paths = ['core/pysrc/' + name for name in names] + [OBSERVER]
    result = {}
    for path in paths:
        if path != OBSERVER:
            mode, kind, size = rows[path.rsplit('/', 1)[1]]
            require(mode in ('100644','100755') and kind == 'blob' and size is not None,
                    'unsupported immutable Python source')
        raw = load(source, path)
        require(len(raw) <= 64 << 20, 'immutable Python source exceeds bound')
        result[path] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    require(sum(x['bytes'] for x in result.values()) <= 16 << 20, 'immutable Python inventory exceeds bound')
    return result


def validate(record, req, platform, count):
    fields = {'format','profile','source_commit','ci_run_id','run_attempt','producer_job','platform',
              'workspace_count','source_before','source_after','imports','runtime_before','runtime_after',
              'bindings_sha256','launch_files'}
    require(isinstance(record, dict) and set(record) == fields and record['format'] == FORMAT
            and record['profile'] == PROFILE and record['source_commit'] == req['source_commit']
            and type(record['ci_run_id']) is int and record['ci_run_id'] == req['ci_run_id']
            and type(record['run_attempt']) is int and record['run_attempt'] == req['run_attempt']
            and record['producer_job'] == 'artifact-native-build' and record['platform'] == platform
            and type(record['workspace_count']) is int and record['workspace_count'] == count,
            'npm binding source/run/platform/count differs')
    require(record['source_before'] == record['source_after'] == req['launch_binding_inputs'],
            'npm binding consumed Python source differs')
    runtime = record['runtime_before']
    require(isinstance(runtime, dict) and set(runtime) == {'version','implementation','sys_platform','isolated',
            'no_site','no_user_site','dont_write_bytecode','files','directories','links'}
            and runtime == record['runtime_after'] and isinstance(runtime['version'], list)
            and len(runtime['version']) == 3 and all(type(n) is int and n >= 0 for n in runtime['version'])
            and runtime['version'][:2] == [3,14] and runtime['implementation'] == 'cpython'
            and runtime['sys_platform'] == {'windows':'win32','linux':'linux','darwin':'darwin'}[platform.split('/')[0]]
            and all(type(runtime[k]) is int and runtime[k] == 1 for k in ('isolated','no_site','no_user_site'))
            and runtime['dont_write_bytecode'] is True, 'npm binding Python runtime differs')
    files = runtime['files']
    require(isinstance(files, dict) and 'interpreter' in files and 0 < len(files) <= RUNTIME_FILE_LIMIT
            and isinstance(runtime['directories'], dict) and len(runtime['directories']) <= RUNTIME_DIRECTORY_LIMIT,
            'npm binding runtime inventory unavailable')
    for label, row in files.items():
        require(isinstance(label, str) and 0 < len(label.encode('utf8')) <= 4096
                and not any(x in ('', '..') for x in label.split('/')), 'invalid runtime identity label')
        require(isinstance(row, dict) and set(row) == {'bytes','sha256'} and type(row['bytes']) is int
                and 0 <= row['bytes'] <= IDENTITY_FILE_LIMIT and isinstance(row['sha256'],str) and HEX.fullmatch(row['sha256']),
                'invalid runtime file identity')
    require(sum(x['bytes'] for x in files.values()) <= RUNTIME_BYTE_LIMIT, 'runtime identity bytes exceed bound')
    population = 0
    for label, names in runtime['directories'].items():
        require(isinstance(label,str) and 0 < len(label.encode('utf8')) <= 4096
                and isinstance(names,list) and all(isinstance(n,str) and 0 < len(n.encode('utf8')) <= 1024
                    and n not in ('.','..') and '/' not in n and '\\' not in n for n in names)
                and names == sorted(set(names)), 'invalid runtime directory population')
        population += len(names)
    require(population <= RUNTIME_ENTRY_LIMIT, 'runtime directory population exceeds bound')
    links = runtime['links']
    require(isinstance(links,dict) and len(files) + len(links) <= RUNTIME_FILE_LIMIT
            and not set(links).intersection(files), 'invalid runtime link population')
    for label, row in links.items():
        require(isinstance(label,str) and label.startswith(('stdlib/','extensions/'))
                and len(label.encode('utf8')) <= 4096 and not any(p in ('','..') for p in label.split('/'))
                and isinstance(row,dict) and set(row)=={'target','identity'}
                and isinstance(row['target'],str) and 0 < len(row['target'].encode('utf8')) <= LINK_TARGET_LIMIT
                and '\x00' not in row['target'], 'invalid inert runtime link')
        identity = row['identity']
        require(isinstance(identity,dict) and set(identity)=={'device','inode','mode','bytes','mtime_ns'}
                and all(type(v) is int and abs(v) < (1 << 128) for v in identity.values())
                and all(identity[k] >= 0 for k in ('device','inode','mode','bytes'))
                and stat.S_ISLNK(identity['mode']), 'invalid inert runtime link identity')
    require(isinstance(record['imports'], list) and 0 < len(record['imports']) <= 512, 'missing consumed imports')
    names = set(); source_imports = set()
    linux_config = LINUX_CONFIG_IMPORTS.get(platform)
    for row in record['imports']:
        require(isinstance(row,dict) and set(row) == {'name','kind','path'}
                and isinstance(row['name'],str), 'invalid or repeated consumed import')
        name = row['name']
        # CPython imports its architecture-specific Linux configuration from the stdlib.
        is_linux_config = (name == linux_config and row['kind'] == 'runtime'
                           and row['path'] == f'stdlib/{linux_config}.py')
        require((re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.]*', name) or is_linux_config)
                and name not in names, 'invalid or repeated consumed import')
        names.add(name)
        if row['kind'] == 'source':
            require(row['path'] in req['launch_binding_inputs'], 'unbound consumed Python import')
            source_imports.add(row['path'])
        elif row['kind'] == 'runtime':
            require(row['path'] in files, 'unbound runtime import')
        else:
            require(row['kind'] in ('built-in','frozen') and row['path'] is None, 'unsupported import kind')
    require({'core/pysrc/_artifactauthoritylib.py', 'core/pysrc/_artifactlib.py',
             'core/pysrc/_artifactpromptlib.py', 'core/pysrc/_gitexec.py'} <= source_imports,
            'actual producer import closure missing')
    launch = record['launch_files']
    base = 4 if platform.startswith('windows/') else 2
    if count and platform.startswith('windows/'):
        base += 1
    require(isinstance(launch,list) and len(launch) == count + base and len(launch) <= 37
            and isinstance(record['bindings_sha256'],str) and HEX.fullmatch(record['bindings_sha256']),
            'original npm launch shape differs')
    roles = [row.get('role') for row in launch if isinstance(row,dict)]
    expected = ['declared-executable','npm-manifest'] + ['npm-workspace-manifest'] * count
    if platform.startswith('windows/'):
        expected += ['node-runtime','npm-cli'] + (['npm-prefix'] if count else [])
    require(sorted(roles) == sorted(expected), 'npm launch role population differs')
    for row in launch:
        require(set(row) == {'role','bytes','sha256'} and type(row['bytes']) is int and 0 <= row['bytes'] <= IDENTITY_FILE_LIMIT
                and isinstance(row['sha256'],str) and HEX.fullmatch(row['sha256']), 'invalid npm launch identity')
    return record
