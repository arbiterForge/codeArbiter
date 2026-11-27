"""One original mapped-work conformance child, bound to source and CI20 input.

This profile reports software fixture behavior only. It never attests GitHub
provider effects, installed hosts, user authority, or native module semantics.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import importlib
import json
import shutil
import tempfile
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import unittest
from unittest import mock
import zipfile
import io

PROFILE = 'mapped-work-native-consumer-v1'
PRODUCER = 'python-mapped-native-consumer-observer-v1'
FORMAT = 'codearbiter.mapped-work-consumer/1'
MANIFEST = 'major-mapped-work-inputs.json'
SOURCE_PAYLOAD = 'major-source-inputs-mapped-work-windows'
NATIVE_PAYLOAD = 'ci20-native-tested-windows-2025'
JOB = '[CHECK] | [CORE] | Native adapters and conformance <windows/amd64>'
UPLOAD = 'Upload mapped-work source-test inputs'
CELL = 'disposition:transitions:S38:04'
SCRIPT = '.github/scripts/test_work_github.py'
ROOTS = ('core/pysrc', 'core/artifacts', 'core/surface', 'plugins/ca-codex', '.github/scripts')
EXTRA = frozenset(('core/hosts.json', 'core/artifact-release-manifest.json',
 '.github/requirements/artifact-conformance-py314.lock', '.github/workflows/ci.yml',
 '.github/major-qualification-policy.json', '.github/major-test-selections.json', '.gitattributes'))
NAMES = (
 'test_mapped_preclaim_transport_failure_keeps_pending_and_continues_independent_target',
 'test_mapped_preclaim_timeout_keeps_pending_and_continues_independent_target',
 'test_mapped_target_local_native_claim_conflict_keeps_pending_and_continues_independent_target',
 'test_mapped_target_local_remote_identity_failure_keeps_pending_and_continues_independent_target',
 'test_mapped_preclaim_malformed_remote_json_keeps_pending_and_independent_target',
 'test_mapped_postclaim_malformed_remote_json_stays_unknown_without_resend',
 'test_mapped_partial_issue_success_does_not_repeat_when_project_fails',
)
SELECTORS = tuple('python:' + SCRIPT + ':__main__.GithubWorkTest.' + name for name in NAMES)
LOOKUPS = ('.github/scripts/_host.py', 'core/pysrc/_host.py')
MAX_MEMBERS = 2048
MAX_TOTAL = 64 * 1024 * 1024

def _owner():
    import major_qualification_report
    return major_qualification_report

def _require(condition, message):
    _owner().require(condition, message)

def _entries(repo, source):
    r = _owner()
    namespace_cache = {}
    for root in ROOTS:
        _require(r.readiness._lookup_present(repo,source,{'path':root,'path_style':'windows'},namespace_cache),
                 'mapped immutable Windows source root is absent or ambiguous')
    raw = r.git(repo, 'ls-tree', '-rz', '--full-tree', source, '--', *ROOTS, *sorted(EXTRA), raw=True)
    rows = []
    for item in raw.split(b'\0'):
        if not item: continue
        head, name = item.split(b'\t', 1)
        mode, kind, blob = head.decode('ascii').split()
        name = name.decode('utf8')
        _require(kind == 'blob' and mode in ('100644', '100755')
                 and r.readiness.SHA.fullmatch(blob), 'mapped source member is not ordinary Git data')
        _require(not any(part in ('__pycache__', 'node_modules') for part in PurePosixPath(name).parts),
                 'mapped source cannot contain tracked runtime caches')
        rows.append((name, mode, blob))
    _require(0 < len(rows) <= MAX_MEMBERS and len({x[0].casefold() for x in rows}) == len(rows)
             and EXTRA <= {x[0] for x in rows}
             and all(any(n.startswith(root + '/') for n, _, _ in rows) for root in ROOTS),
             'mapped source membership is incomplete, ambiguous or unbounded')
    return sorted(rows)

def _immutable(repo, source):
    r = _owner(); entries = _entries(repo, source)
    raw = r.git(repo, 'cat-file', '--batch', raw=True,
                input=''.join(blob + '\n' for _, _, blob in entries).encode('ascii'))
    _require(len(raw) <= MAX_TOTAL, 'mapped source exceeds byte bound')
    cursor = 0; result = []; values = {}
    for name, mode, expected in entries:
        end = raw.index(b'\n', cursor)
        blob, kind, size = raw[cursor:end].decode('ascii').split(); size = int(size); cursor = end + 1
        _require(blob == expected and kind == 'blob' and 0 <= size <= 8 * 1024 * 1024,
                 'mapped source blob is invalid')
        value = raw[cursor:cursor + size]; cursor += size
        _require(len(value) == size and raw[cursor:cursor + 1] == b'\n', 'mapped source blob truncated')
        cursor += 1
        result.append({'path':name, 'sha256':r.readiness.digest(value), 'bytes':size, 'git_mode':mode})
        values[name] = value
    _require(cursor == len(raw), 'mapped source trailing bytes')
    return result, values

def _physical_names(repo):
    found = set(); count = 0
    for root in ROOTS:
        pending = [Path(repo) / root]
        while pending:
            folder = pending.pop(); count += 1
            info = folder.lstat()
            _require(count <= 1024 and stat.S_ISDIR(info.st_mode) and not folder.is_symlink()
                and not getattr(info,'st_file_attributes',0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                'mapped source directory unsafe or unbounded')
            for path in folder.iterdir():
                name = path.relative_to(repo).as_posix(); info = path.lstat()
                # Original copytree excludes runtime directories; private bytecode
                # is required before imports. These are never source witnesses.
                if path.name in ('__pycache__','node_modules'): continue
                _require(not path.is_symlink() and not getattr(info,'st_file_attributes',0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                         'mapped source link refused')
                if stat.S_ISDIR(info.st_mode): pending.append(path)
                else:
                    _require(stat.S_ISREG(info.st_mode), 'mapped source nonregular member')
                    found.add(name)
                    _require(len(found) <= MAX_MEMBERS, 'mapped source physical bound exceeded')
    return found | set(EXTRA)

def snapshot(repo):
    r = _owner(); repo = Path(repo).resolve(strict=True)
    identity = r.source_identity(repo)
    _require(identity['clean'], 'mapped source checkout is dirty')
    members, values = _immutable(repo, identity['source_commit']); paths = {x['path'] for x in members}
    _require(_physical_names(repo) == paths, 'mapped source physical membership differs')
    for row in members:
        _require(r._source_file(repo,row['path'],paths) == values[row['path']], 'mapped source physical bytes differ')
    lookup = {}
    for name in LOOKUPS:
        path = repo / name
        _require(not path.exists() and not path.is_symlink(), 'mapped Windows host lookup shadow refused')
        lookup[name] = 'absent'
    return {**identity, 'members':members, 'host_lookup':lookup}

def prepare(repo, output):
    r = _owner(); output = Path(output).absolute(); repo = Path(repo).resolve(strict=True)
    _require(output.parent.resolve(strict=True) == output.parent and not output.exists()
             and not output.is_symlink() and not output.is_relative_to(repo), 'new external mapped source directory required')
    before = snapshot(repo); output.mkdir()
    paths = {x['path'] for x in before['members']}
    for row in before['members']:
        value = r._source_file(repo,row['path'],paths)
        _require(r.readiness.digest(value) == row['sha256'], 'mapped staging source changed')
        target = output / row['path']; target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream: stream.write(value)
    record = {'format':FORMAT,'profile':PROFILE,'source_commit':before['source_commit'],
              'source_tree':before['source_tree'],'ci_run_id':int(os.environ.get('GITHUB_RUN_ID','0')),
              'producer_job_name':JOB,'members':before['members'],'host_lookup':before['host_lookup']}
    _require(record['ci_run_id'] > 0 and snapshot(repo) == before, 'mapped staging source unstable')
    r.new_output(output / MANIFEST,record)
    return record

def validate_manifest(record, *, req, repo, members):
    _require(type(record) is dict and set(record) == {'format','profile','source_commit','source_tree','ci_run_id',
              'producer_job_name','members','host_lookup'} and record['format'] == FORMAT and record['profile'] == PROFILE
              and record['producer_job_name'] == JOB and type(record['ci_run_id']) is int
              and record['ci_run_id'] == req['ci_run_id'] and record['source_commit'] == req['source_commit']
              and record['source_tree'] == req['source_tree'], 'mapped manifest identity differs')
    expected, _ = _immutable(repo,req['source_commit'])
    _require(record['members'] == expected and record['host_lookup'] == {name:'absent' for name in LOOKUPS}
              and not any(row['path'] in LOOKUPS for row in expected), 'mapped immutable source/lookup differs')
    projection = [{'path':row['path'],'sha256':row['sha256']} for row in expected]
    actual = [row for row in members if row['path'] != MANIFEST]
    _require(sorted(actual,key=lambda x:x['path']) == projection and len(members) == len(expected) + 1,
              'mapped archive source membership differs')
    return record

def runtime_snapshot():
    r=_owner(); executable=Path(sys.executable).resolve(strict=True)
    raw=r._source_file(executable.parent,executable.name,{executable.name})
    return {'python_sha256':r.readiness.digest(raw),'version':list(sys.version_info[:3])}


def authenticate_native_consumption(root, component):
    """Reuse the independently authenticated archive, not a second download."""
    r=_owner();root=Path(root).resolve(strict=True)
    members=component['members']
    expected={'artifact-candidate/release.json','artifact-candidate/ca-artifact-windows-amd64.exe',
              'ci20-native-tested.json','native-tests.json','native-observation.json'}
    _require(type(members) is list and len(members) == 5 and {row['path'] for row in members} == expected,
             'mapped original native archive population differs')
    for member in members:
        name=member['path'];parts=PurePosixPath(name).parts
        _require(not PurePosixPath(name).is_absolute() and parts and all(part not in ('','..','.') for part in parts)
                 and not any(':' in part or '\\' in part for part in parts), 'mapped native member path unsafe')
        path=root
        for part in parts:
            path=path/part;info=path.lstat()
            _require(not path.is_symlink() and not getattr(info,'st_file_attributes',0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                     'mapped native consumed link refused')
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 32*1024*1024,
                 'mapped native consumed input is not bounded regular data')
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(fd,'rb') as stream:
            opened=os.fstat(stream.fileno())
            _require((opened.st_dev,opened.st_ino)==(info.st_dev,info.st_ino),'mapped native input replaced before read')
            raw=stream.read(32*1024*1024+1);after=os.fstat(stream.fileno())
        _require(len(raw)<=32*1024*1024 and (opened.st_size,opened.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
                 and r.readiness.digest(raw)==member['sha256'], 'mapped consumed native bytes changed')
    return {key:component[key] for key in ('artifact_id','archive_sha256','members')}


def native_snapshot(repo, installation):
    r = _owner(); installation = Path(installation).resolve(strict=True)
    # Admission is the unchanged ArtifactClient file verifier, not a native call.
    import _artifactlib
    client = _artifactlib.ArtifactClient(repo, installation)
    fd = client._open_binary()
    try: size = os.fstat(fd).st_size
    finally: os.close(fd)
    names = {p.name for p in installation.iterdir()}
    _require(names == {'release.json','ca-artifact-windows-amd64.exe'}, 'mapped installation membership differs')
    manifest = r.load_json(installation/'release.json')
    entry = manifest['binaries'].get('windows/amd64',{})
    _require(entry.get('file') == 'ca-artifact-windows-amd64.exe' and entry.get('native_tested') is True,
              'mapped native Windows candidate required')
    return {'manifest_sha256':r.readiness.digest(r._source_file(installation,'release.json',names)),
            'binary_sha256':entry['sha256'],'binary_bytes':size,'platform':'windows/amd64'}

def admit(observed, *, req, job_id, authenticated_payloads, repo, native_component):
    r = _owner(); binding = observed.get('consumer_binding')
    _require(observed.get('producer') == PRODUCER and observed.get('proof_kind') == 'source-test'
          and type(binding) is dict and set(binding) == {'format','profile','source_manifest_sha256','native_before',
            'native_after','native_admissions','host_lookup_before','host_lookup_after','imported_sources','runtime_before','runtime_after'}
          and binding['format'] == FORMAT and binding['profile'] == PROFILE, 'mapped qualified observer binding missing')
    source = authenticated_payloads.get(SOURCE_PAYLOAD,{}); native = authenticated_payloads.get(NATIVE_PAYLOAD,{})
    _require(source.get('source_upload_job_id') == job_id and source.get('source_manifest_sha256') == binding['source_manifest_sha256'],
              'mapped original same-job source upload missing')
    manifest = source.get('documents',{}).get(MANIFEST)
    validate_manifest(manifest,req=req,repo=repo,members=source.get('members',[]))
    _require(type(native_component) is dict and native_component.get('platform') == 'windows/amd64'
          and native_component.get('artifact_id') == native.get('artifact_id')
          and native_component.get('archive_sha256') == native.get('archive_sha256')
          and native_component.get('members') == native.get('members'), 'original authenticated native builder component differs')
    stamp = native_component.get('native_binding',{})
    before = binding['native_before']
    _require(type(before) is dict and set(before) == {'platform','manifest_sha256','binary_sha256','binary_bytes'}
          and before == binding['native_after'] and before.get('platform') == 'windows/amd64'
          and type(before.get('binary_bytes')) is int and 0 < before['binary_bytes'] <= 32 * 1024 * 1024
          and before['manifest_sha256'] == stamp.get('manifest_sha256') and before['binary_sha256'] == stamp.get('binary_sha256')
          and stamp.get('source_commit') == req['source_commit'] and stamp.get('run_id') == str(req['ci_run_id'])
          and type(before['manifest_sha256']) is str and r.readiness.DIGEST.fullmatch(before['manifest_sha256'])
          and type(before['binary_sha256']) is str and r.readiness.DIGEST.fullmatch(before['binary_sha256'])
          and type(req.get('native_module_sha256')) is dict
          and type(req['native_module_sha256'].get('windows')) is str
          and r.readiness.DIGEST.fullmatch(req['native_module_sha256']['windows'])
          and stamp.get('module_sha256') == req['native_module_sha256']['windows'],
          'mapped native input changed or differs from original builder')
    native_members = {x['path']:x['sha256'] for x in native.get('members',[])}
    _require(native_members.get('artifact-candidate/release.json') == before['manifest_sha256']
          and native_members.get('artifact-candidate/ca-artifact-windows-amd64.exe') == before['binary_sha256'],
          'mapped consumed native bytes differ')
    _require(binding['host_lookup_before'] == binding['host_lookup_after'] == manifest['host_lookup'],
          'mapped host lookup changed')
    imports = binding['imported_sources']; available = {x['path']:x['sha256'] for x in manifest['members']}
    _require(type(imports) is dict and len(imports) <= MAX_MEMBERS
          and {'core/pysrc/_artifactlib.py','core/pysrc/_workgithub.py','.github/scripts/test_artifact_authoring.py'} <= imports.keys()
          and all(available.get(name) == digest for name,digest in imports.items()), 'mapped original imports absent or not source-bound')
    runtime=binding['runtime_before']
    _require(type(runtime) is dict and set(runtime) == {'python_sha256','version'}
          and runtime == binding['runtime_after'] and type(runtime['python_sha256']) is str
          and r.readiness.DIGEST.fullmatch(runtime['python_sha256']) and type(runtime['version']) is list
          and len(runtime['version']) == 3 and all(type(value) is int and value >= 0 for value in runtime['version'])
          and runtime['version'][:2] == [3,14], 'mapped original reference interpreter changed or is unsupported')
    counts = binding['native_admissions']
    _require(type(counts) is dict and set(counts) == set(SELECTORS)
          and all(type(value) is int and 0 < value <= 10000 for value in counts.values()),
          'selected mapped cases lack actual unchanged ArtifactClient admissions')
    rows = observed.get('tests',[])
    _require(all(sum(row == {'id':name,'result':'passed'} for row in rows) == 1 for name in SELECTORS),
          'mapped full clause selectors did not pass exactly once')
    _require(observed.get('argv') and len(observed['argv']) == 2
          and Path(observed['argv'][1]).as_posix().endswith('/'+SCRIPT), 'original whole mapped-work child command differs')
    payloads = [{key:value[key] for key in ('artifact_id','archive_sha256','members')} for value in (source,native)]
    _require(len({x['artifact_id'] for x in payloads}) == 2, 'mapped source/native artifacts must be distinct')
    return {'tests':rows,'payloads':payloads,'primary_payload_name':SOURCE_PAYLOAD,'qualified_cells':[CELL]}

def observe(repo, output, source_payload):
    r = _owner(); repo = Path(repo).resolve(strict=True); output = Path(output).absolute()
    _require(not output.exists() and not output.is_symlink(), 'new mapped observation required')
    _require(sys.platform == 'win32' and sys.flags.no_user_site and sys.pycache_prefix
          and not Path(sys.pycache_prefix).resolve().is_relative_to(repo), 'private Windows Python observer required')
    r.validate_emitter_environment()
    installation = os.environ.get('ARTIFACT_TEST_INSTALLATION')
    _require(installation, 'original supplied native installation required; no local build fallback')
    original_modules = dict(sys.modules)
    original_path = sys.path[:]
    source_names = {Path(row['path']).stem for row in snapshot(repo)['members'] if row['path'].endswith('.py')}
    # A cached module may not substitute external bytes for the owning imports.
    for name,module in list(sys.modules.items()):
        file = getattr(module,'__file__',None)
        if name.split('.')[0] in source_names or file and Path(file).resolve().is_relative_to(repo):
            if module is not r and module is not sys.modules[__name__]: sys.modules.pop(name,None)
    sys.path[:0] = [str(repo/'.github/scripts'),str(repo/'core/pysrc')]
    try:
        import _artifactlib
        before = snapshot(repo); native_before = native_snapshot(repo,installation); runtime_before = runtime_snapshot()
        manifest = r.load_json(Path(source_payload)/MANIFEST)
        raw_manifest = r._source_file(source_payload,MANIFEST,{MANIFEST})
        archive_members = [{'path':row['path'],'sha256':row['sha256']} for row in before['members']]
        archive_members.append({'path':MANIFEST,'sha256':r.readiness.digest(raw_manifest)})
        validate_manifest(manifest,req={**before,'ci_run_id':int(os.environ.get('GITHUB_RUN_ID','0'))},repo=repo,members=archive_members)
        for row in before['members']:
            _require(r.readiness.digest(r._source_file(source_payload,row['path'],{x['path'] for x in before['members']})) == row['sha256'],
                     'mapped staged input bytes differ')
        counts = dict.fromkeys(SELECTORS,0); active = [None]
        original_start = unittest.TestResult.startTest; original_open = _artifactlib.ArtifactClient._open_binary
        def start(result,test):
            active[0] = 'python:'+SCRIPT+':'+test.id()
            return original_start(result,test)
        def opened(client):
            fd = original_open(client)
            try:
                raw = r._source_file(client.installation,'release.json',{'release.json'})
                _require(r.readiness.digest(raw) == native_before['manifest_sha256']
                         and os.fstat(fd).st_size == native_before['binary_bytes'], 'mapped cloned native admission differs')
                if active[0] in counts: counts[active[0]] += 1
                return fd
            except BaseException:
                os.close(fd); raise
        raw_output = output.with_name(output.stem+'.original.json')
        with mock.patch.object(unittest.TestResult,'startTest',start), mock.patch.object(_artifactlib.ArtifactClient,'_open_binary',opened):
            code = r.observe_python(repo,SCRIPT,[],raw_output)
        document = r.load_json(raw_output)
        imported = {}
        paths = {x['path'] for x in before['members']}
        for module in list(sys.modules.values()):
            file = getattr(module,'__file__',None)
            if file and Path(file).resolve().is_relative_to(repo):
                name = Path(file).resolve().relative_to(repo).as_posix()
                _require(name in paths, 'mapped import outside source closure')
                imported[name] = r.readiness.digest(r._source_file(repo,name,paths))
        after = snapshot(repo); native_after = native_snapshot(repo,installation); runtime_after = runtime_snapshot()
        document.update(producer=PRODUCER,source_stable=document['source_stable'] and before == after and native_before == native_after and runtime_before == runtime_after,
          consumer_binding={'format':FORMAT,'profile':PROFILE,'source_manifest_sha256':r.readiness.digest(raw_manifest),
           'native_before':native_before,'native_after':native_after,'native_admissions':counts,
           'runtime_before':runtime_before,'runtime_after':runtime_after,
           'host_lookup_before':before['host_lookup'],'host_lookup_after':after['host_lookup'],'imported_sources':imported})
        r.new_output(output,document)
        return code if document['source_stable'] else 1
    finally:
        sys.path[:] = original_path
        # Restore the exact prior module registry; no stale source escapes.
        for name in list(sys.modules):
            if name not in original_modules: sys.modules.pop(name,None)
        sys.modules.update(original_modules)

@contextmanager
def conformance_invocation(repo, script, interpreter, environment):
    command = conformance_command(repo, script, interpreter, environment)
    if command == [interpreter, str(Path(repo)/'.github/scripts'/script)]:
        yield command, environment
        return
    output = Path(environment['MAJOR_MAPPED_WORK_OBSERVATION']).absolute()
    parent = output.parent.resolve(strict=True)
    _require(output.parent == parent and not parent.is_relative_to(Path(repo).resolve()),
             'mapped private output must be outside source')
    git = shutil.which('git',path=environment.get('PATH',''))
    _require(git is not None, 'mapped original Git executable unavailable')
    # One fresh owned profile per original child. No ambient auth/config/home.
    with tempfile.TemporaryDirectory(prefix='mapped-work-profile-') as private:
        profile=Path(private).resolve(strict=True)
        for name in ('home','temp','appdata','localappdata','cache'): (profile/name).mkdir()
        child={key:value for key,value in environment.items() if key.upper() in
               {'SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATHEXT'}}
        for key in ('GITHUB_ACTIONS','GITHUB_REPOSITORY','GITHUB_SHA','GITHUB_RUN_ID',
                    'GITHUB_RUN_ATTEMPT','GITHUB_EVENT_NAME','GITHUB_REF','ARTIFACT_TEST_INSTALLATION'):
            if key in environment: child[key]=environment[key]
        child.update(PATH=os.pathsep.join((str(Path(interpreter).resolve().parent),str(Path(git).resolve().parent),
                    str(Path(child.get('SYSTEMROOT','C:/Windows'))/'System32'))),
          HOME=str(profile/'home'),USERPROFILE=str(profile/'home'),TMP=str(profile/'temp'),TEMP=str(profile/'temp'),
          APPDATA=str(profile/'appdata'),LOCALAPPDATA=str(profile/'localappdata'),XDG_CACHE_HOME=str(profile/'cache'),
          PYTHONPYCACHEPREFIX=str(profile/'cache/pycache'),PYTHONNOUSERSITE='1',PYTHONIOENCODING='utf-8',
          GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM='1',GIT_TERMINAL_PROMPT='0')
        yield command,child


def conformance_command(repo, script, interpreter, environment):
    """Only replace the original owning child slot; default is byte-for-byte argv."""
    command = [interpreter, str(Path(repo)/'.github/scripts'/script)]
    if script != 'test_work_github.py': return command
    source = environment.get('MAJOR_MAPPED_WORK_SOURCE')
    output = environment.get('MAJOR_MAPPED_WORK_OBSERVATION')
    if not source and not output: return command
    _require(type(source) is str and source and type(output) is str and output,
             'mapped conformance opt-in requires both original source and new output')
    return [interpreter,str(Path(repo)/'.github/scripts/mapped_work_observation.py'),
            'observe','--repo',str(repo),'--source-payload',source,'--output',output]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('prepare','observe'))
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-payload',type=Path)
    args=parser.parse_args(argv)
    if args.operation == 'prepare': prepare(args.repo,args.output); return 0
    _require(args.source_payload is not None,'mapped original source payload required')
    return observe(args.repo,args.output,args.source_payload)

if __name__ == '__main__':
    raise SystemExit(main())
