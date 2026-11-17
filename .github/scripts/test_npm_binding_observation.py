"""Pure owned-file/inert producer and original archive admission controls."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


PRODUCER_UNIT_TIMEOUT_SECONDS = 120
PROGRESS_LIMIT = 32768
PROGRESS_PHASES = ('starting','source-before','runtime-before-enumeration','runtime-before-hashing',
    'runtime-before-done','binding','imports','launch-identities','source-after',
    'runtime-after-enumeration','runtime-after-hashing','runtime-after-done','encode','write','complete')


def read_producer_progress(path):
    """Read only the closed bounded last record, never stderr/source/env data."""
    import stat
    path=Path(path);parent=path.parent
    parent_before=parent.stat();before=path.lstat()
    require= lambda ok: None if ok else (_ for _ in ()).throw(ValueError('producer progress refused'))
    require(parent.resolve(strict=True)==parent and not parent.is_symlink()
        and stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode)
        and not getattr(before,'st_file_attributes',0)&0x400
        and before.st_nlink==1 and 0<before.st_size<=PROGRESS_LIMIT)
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0))
    try:
        opened=os.fstat(fd)
        identity=lambda v:(v.st_dev,v.st_ino,v.st_mode,v.st_nlink,v.st_size,v.st_mtime_ns)
        require(identity(before)==identity(opened))
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(PROGRESS_LIMIT+1)
        require(len(raw)==before.st_size and len(raw)<=PROGRESS_LIMIT
            and identity(before)==identity(os.fstat(fd))==identity(path.lstat())
            and (parent_before.st_dev,parent_before.st_ino)==(parent.stat().st_dev,parent.stat().st_ino))
    finally:os.close(fd)
    def pairs(rows):
        result={}
        for k,v in rows:
            require(k not in result);result[k]=v
        return result
    try:value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False))
    except (ValueError,UnicodeError,RecursionError):raise ValueError('producer progress refused') from None
    bounds={'elapsed_ms':PRODUCER_UNIT_TIMEOUT_SECONDS * 1000,'runtime_ordinal':2,'discovered_files':32768,'completed_files':32768,
            'completed_bytes':512<<20,'directories':2048,'entries':65536,'links':32768}
    require(type(value) is dict and set(value)==set(bounds)|{'format','phase'}
        and value['format']=='codearbiter.npm-producer-progress/1' and value['phase'] in PROGRESS_PHASES)
    require(all(type(value[k]) is int and 0<=value[k]<=limit for k,limit in bounds.items()))
    return value


def producer_progress_report(path):
    try:return {'status':'recorded','record':read_producer_progress(path)}
    except FileNotFoundError:return {'status':'unavailable','record':None}
    except (OSError,ValueError):return {'status':'refused','record':None}


# Executed with -c, not as an imported helper: consumed-import closure never
# gains an uncaptured helper __file__. Original embedded Go source is unchanged.
PRODUCER_PROFILE_BOOTSTRAP = r"""
import sys,os,time,json
_ca_start=time.monotonic()
_ca_state={'format':'codearbiter.npm-producer-progress/1','phase':'starting','elapsed_ms':0,
 'runtime_ordinal':0,'discovered_files':0,'completed_files':0,'completed_bytes':0,'directories':0,'entries':0,'links':0}
_ca_runtime=None
_ca_sources=0
_ca_bucket=-1
_ca_progress=CA_PROGRESS_PATH
_ca_observer=CA_OBSERVER_PATH
_ca_authority=CA_AUTHORITY_PATH
def _ca_flush():
 _ca_state['elapsed_ms']=int((time.monotonic()-_ca_start)*1000)
 _raw=json.dumps(_ca_state,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
 if len(_raw)>32768:return
 _temporary=_ca_progress+'.new'
 _fd=os.open(_temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0),0o600)
 with os.fdopen(_fd,'wb') as _stream:_stream.write(_raw)
 os.replace(_temporary,_ca_progress)
def _ca_phase(value):
 _ca_state['phase']=value;_ca_flush()
def _ca_profile(frame,event,arg):
 global _ca_runtime,_ca_sources,_ca_bucket
 if event not in ('call','return'):return
 _name=frame.f_code.co_name
 try:
  if frame.f_code.co_filename==_ca_authority and _name=='_bind_commands':
   if event=='call':_ca_phase('binding')
   return
  if frame.f_code.co_filename!=_ca_observer:return
  if _name=='require' and event=='call' and _ca_runtime is not None and frame.f_back.f_code.co_name=='runtime_snapshot':
   _local=frame.f_back.f_locals
   _ca_state.update(directories=len(_local.get('directories',{})),entries=_local.get('population',0),
    discovered_files=len(_local.get('paths',{})),links=len(_local.get('links',{})))
   _new_bucket=_ca_state['entries']//128
   if _new_bucket!=_ca_bucket:_ca_bucket=_new_bucket;_ca_flush()
  elif _name=='runtime_snapshot':
   if event=='call':
    _ca_state['runtime_ordinal']+=1
    _ca_runtime='runtime-before' if _ca_state['runtime_ordinal']==1 else 'runtime-after'
    _ca_state.update(discovered_files=0,completed_files=0,completed_bytes=0,directories=0,entries=0,links=0)
    _ca_bucket=-1;_ca_phase(_ca_runtime+'-enumeration')
   elif isinstance(arg,tuple) and isinstance(arg[0],dict):
    _value=arg[0]
    _ca_state.update(discovered_files=len(_value['files']),completed_files=len(_value['files']),
     completed_bytes=sum(v['bytes'] for v in _value['files'].values()),directories=len(_value['directories']),
     entries=sum(len(v) for v in _value['directories'].values()),links=len(_value['links']))
    _ca_phase(_ca_runtime+'-done');_ca_runtime=None
  elif _name=='file_identity' and _ca_runtime is not None:
   if event=='call' and _ca_state['phase']==_ca_runtime+'-enumeration':_ca_phase(_ca_runtime+'-hashing')
   elif event=='return' and isinstance(arg,dict):
    _ca_state['completed_files']+=1;_ca_state['completed_bytes']+=arg['bytes']
    if _ca_state['completed_files']%128==0:_ca_flush()
  elif _name=='source_snapshot' and event=='call':
   _ca_sources+=1;_ca_phase('source-before' if _ca_sources==1 else 'source-after')
  elif _name=='consumed_imports':
   if event=='call':_ca_phase('imports')
   elif isinstance(arg,list):_ca_phase('launch-identities')
  elif _name=='encode_record':
   if event=='call':_ca_phase('encode')
   elif isinstance(arg,bytes):_ca_phase('write')
  elif _name=='observe' and event=='return' and isinstance(arg,list):_ca_phase('complete')
 except Exception:
  pass  # passive capture cannot replace the original producer outcome
try:_ca_flush()
except Exception:pass
sys.setprofile(_ca_profile)
try:
 exec(compile(CA_EXACT_SCRIPT,'<string>','exec'),globals(),globals())
finally:
 sys.setprofile(None)
 try:_ca_flush()
 except Exception:pass
"""


def producer_child_run(argv, **kwargs):
    """Original child/deadline with passive bounded last-phase retention."""
    original=list(argv);position=original.index('-c')+1
    core=Path(original[position+1]).resolve(strict=True)
    path=Path(kwargs['cwd']).resolve(strict=True)/'producer-progress.json'
    if path.exists() or path.is_symlink():raise ValueError('fresh producer progress required')
    script=PRODUCER_PROFILE_BOOTSTRAP
    for key,value in {'CA_PROGRESS_PATH':str(path),'CA_OBSERVER_PATH':str(core.parents[1]/'.github/scripts/npm_binding_observation.py'),
                      'CA_AUTHORITY_PATH':str(core/'_artifactauthoritylib.py'),'CA_EXACT_SCRIPT':original[position]}.items():
        script=script.replace(key,repr(value))
    observed=list(original);observed[position]=script
    try:
        result=subprocess.run(observed,**kwargs)
    except subprocess.TimeoutExpired as error:
        report=producer_progress_report(path)
        error.producer_progress=report
        # Keep class, timeout and original captured streams; no -c source,
        # private paths or arbitrary child content enters the diagnostic text.
        error.cmd=['original-python-npm-binding-producer']
        error.add_note('producer_progress='+json.dumps(report,sort_keys=True,separators=(',',':')))
        raise
    result.args=original;result.producer_progress=producer_progress_report(path)
    return result


class ProducerBoundaryTests(unittest.TestCase):
    def test_original_python_producer_exports_opt_in_consumed_identities(self):
        source = (ROOT / 'core/artifacts/internal/evidence/launch_binding_limits_test.go').read_text()
        scripts = re.findall(r'script := `([^`]+)`', source)
        self.assertEqual(len(scripts), 1)
        self.assertLess(scripts[0].index('sys.pycache_prefix = cache'), scripts[0].index('import npm_binding_observation as observer'))
        with tempfile.TemporaryDirectory(prefix='hw04-inert-producer-') as raw:
            base = Path(raw).resolve()
            repo, work, output = base / 'repo', base / 'work', base / 'output'
            core = repo / 'core/pysrc'
            core.mkdir(parents=True); work.mkdir(); output.mkdir()
            scripts_root = repo / '.github/scripts'; scripts_root.mkdir(parents=True)
            observer = ROOT / '.github/scripts/npm_binding_observation.py'
            if observer.exists():
                (scripts_root / observer.name).write_bytes(observer.read_bytes())
            (work / 'npm').write_bytes(b'inert reviewed npm')
            (work / 'package.json').write_bytes(b'{}')
            (core / '_artifactauthoritylib.py').write_text(
                'import hashlib, os\n'
                'def _bind_commands(root, context, frozen):\n'
                ' def f(name, role):\n'
                '  p=root/name;s=p.stat();return {"path":str(p),"role":role,"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"filesystem_id":str(s.st_dev)+":"+str(s.st_ino)}\n'
                ' return [{"argv":[str(root/"npm"),"test"],"launch_files":[f("npm","declared-executable"),f("package.json","npm-manifest")]}]\n', encoding='utf8')
            env = {k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP'}}
            env.update(HOME=str(base), USERPROFILE=str(base), PYTHONNOUSERSITE='1',
                       PYTHONDONTWRITEBYTECODE='1', CA_NATIVE_NPM_BINDING_OBSERVATION_DIR=str(output),
                       GITHUB_ACTIONS='true', GITHUB_REPOSITORY='arbiterForge/codeArbiter',
                       GITHUB_SHA='a'*40, GITHUB_RUN_ID='7', GITHUB_RUN_ATTEMPT='1',
                       GITHUB_JOB='artifact-native-build')
            platform = {'win32':'windows','darwin':'darwin','linux':'linux'}[sys.platform] + '/amd64'
            result = producer_child_run([sys.executable,'-I','-S','-B','-X','utf8','-c',scripts[0],
                                     str(core),str(work),'0',platform], env=env, cwd=base,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=PRODUCER_UNIT_TIMEOUT_SECONDS)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf8', 'replace')[-2000:])
            self.assertIsInstance(json.loads(result.stdout), list, 'original binding stdout remains a list')
            sidecar = output / 'workspaces-0.json'
            self.assertTrue(sidecar.is_file(), 'original producer must retain its opt-in consumed Python/npm identity')
            observation = json.loads(sidecar.read_bytes())
            self.assertEqual(observation['source_commit'], 'a'*40)
            self.assertEqual(observation['workspace_count'], 0)
            self.assertEqual(observation['runtime_before'], observation['runtime_after'])
            self.assertIn('core/pysrc/_artifactauthoritylib.py', observation['source_before'])
            self.assertEqual(observation['source_before'], observation['source_after'])
            self.assertEqual([x['role'] for x in observation['launch_files']], ['declared-executable','npm-manifest'])




import npm_binding_observation as launch
import major_readiness as readiness
import major_native_observation as native
import ci20_native_binding as binding
import test_major_native_observation as existing


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.f = existing.NativeCompositeAuthorityTests()
        self.f.setUp()
        f = self.f
        old = copy.deepcopy(f.req['native_compositions'])
        recipes = {**old, **{'task:'+task: {p:launch.selectors(p) for p in binding.PLATFORMS}
                            for task in launch.TASKS}}
        f._select_cli_contracts(recipes)
        f.req['native_compositions'] = old
        f.req['task_ids'] = ['HW-04','NT-04','Q-02']
        self.inputs = {'core/pysrc/'+name+'.py':{'bytes':1,'sha256':'e'*64}
                       for name in ('_artifactauthoritylib','_artifactlib','_artifactpromptlib','_gitexec')}
        self.inputs[launch.OBSERVER] = {'bytes':2,'sha256':'f'*64}
        f.req.update(launch_binding_tasks=list(launch.TASKS),launch_binding_inputs=self.inputs)
        self.sidecars = {}
        for index, (runner, platform) in enumerate(sorted(binding.RUNNERS.items())):
            identity = 300+index
            files = {f'workspaces-{n}.json':json.dumps(self.raw(platform,n)).encode() for n in launch.COUNTS}
            job = next(j for j in f.jobs if j['name'].endswith('<'+platform+'>'))
            job['steps'].append(f.job(1,'unused',launch.UPLOAD)['steps'][0])
            data=f.zip(files);f.data[identity]=data;f.artifacts.append(f.metadata(identity,launch.ARTIFACT+runner,data))
            self.sidecars[platform]=identity
        self.sidecar_metadata = {a["id"]:a for a in f.artifacts if a["id"] in self.sidecars.values()}
        self.original_api=f.api
        f.api=self.api

    def raw(self,platform,count):
        runtime={'version':[3,14,1],'implementation':'cpython',
            'sys_platform':{'windows':'win32','linux':'linux','darwin':'darwin'}[platform.split('/')[0]],
            'isolated':1,'no_site':1,'no_user_site':1,'dont_write_bytecode':True,
            'files':{'interpreter':{'bytes':1,'sha256':'d'*64}},'directories':{'stdlib/.':[]},'links':{}}
        roles=['declared-executable','npm-manifest']+['npm-workspace-manifest']*count
        if platform.startswith('windows/'):
            roles+=['node-runtime','npm-cli']+(['npm-prefix'] if count else [])
        return dict(format=launch.FORMAT,profile=launch.PROFILE,source_commit=self.f.source,ci_run_id=7,
            run_attempt=1,producer_job='artifact-native-build',platform=platform,workspace_count=count,
            source_before=copy.deepcopy(self.inputs),source_after=copy.deepcopy(self.inputs),
            runtime_before=runtime,runtime_after=copy.deepcopy(runtime),
            imports=[{'name':Path(p).stem,'kind':'source','path':p} for p in self.inputs if p.startswith('core/')],
            bindings_sha256='e'*64,launch_files=[{'role':r,'bytes':1,'sha256':'f'*64} for r in roles])

    def api(self,path,binary=False):
        if path.startswith('actions/jobs/') and path.endswith('/logs'):
            identity=int(path.split('/')[2]); job=next(j for j in self.f.jobs if j['id']==identity)
            if launch.UPLOAD in [s['name'] for s in job['steps']]:
                platform=job['name'].rsplit('<',1)[1][:-1]
                side=self.sidecar_metadata[self.sidecars[platform]]
                extra=('2026-11-13T15:00:00Z ##[group]Run '+readiness.UPLOAD_ACTION+'\n'
                    '2026-11-13T15:00:01Z SHA256 digest of uploaded artifact is '+side['digest'][7:]+'\n'
                    '2026-11-13T15:00:02Z Artifact '+side['name']+' successfully finalized. Artifact ID '+str(side['id'])+'\n').encode()
                return self.original_api(path,binary)+extra
        return self.original_api(path,binary)

    def mutate_sidecar(self,platform,mutate):
        import io,zipfile
        identity=self.sidecars[platform]
        with zipfile.ZipFile(io.BytesIO(self.f.data[identity])) as zipped:
            files={name:zipped.read(name) for name in zipped.namelist()}
        mutate(files)
        data=self.f.zip(files);self.f.data[identity]=data
        next(a for a in self.f.artifacts if a['id']==identity).update(
            digest='sha256:'+readiness.digest(data),size_in_bytes=len(data))

    def test_six_original_components_and_sidecars_roundtrip_actual_readiness_owner(self):
        record=self.f.produce()
        self.assertEqual({r['cell'] for r in record['native']['results']},
                         {self.f.cell,'task:HW-04','task:NT-04'})
        self.assertEqual(set(record['native']['launch_components']),set(binding.PLATFORMS))
        self.assertEqual(self.f.verify(record)['state'],'PREPUBLICATION_READY')
        # Final whole-run trust remains mandatory even after producer success.
        failed={**self.f.run,'conclusion':'failure'}
        with self.assertRaises(readiness.ReadinessError):self.f.verify(record,run=failed)

    def test_raw_identity_mutations_refuse_before_any_task_verdict(self):
        base=self.raw('windows/amd64',32);req={**self.f.req,'run_attempt':1}
        changes=[lambda r:r.update(source_commit='b'*40),lambda r:r.update(ci_run_id=8),
            lambda r:r.update(run_attempt=2),lambda r:r.update(platform='linux/amd64'),
            lambda r:r.update(workspace_count=31),lambda r:r['source_after'].clear(),
            lambda r:r['runtime_after'].update(isolated=0),lambda r:r.update(imports=[]),
            lambda r:r['imports'].append(copy.deepcopy(r['imports'][0])),
            lambda r:r['imports'][0].update(path='core/pysrc/_host.py'),
            lambda r:r['launch_files'].pop(),lambda r:r['launch_files'][0].update(role='unknown'),
            lambda r:r.update(secret='sentinel'),lambda r:r['runtime_before']['files'].update(
                interpreter={'bytes':True,'sha256':'d'*64})]
        launch.validate(base,req,'windows/amd64',32)
        for index,change in enumerate(changes):
            with self.subTest(index=index):
                value=copy.deepcopy(base);change(value)
                with self.assertRaises((ValueError,readiness.ReadinessError)):
                    launch.validate(value,req,'windows/amd64',32)

    def test_missing_case_platform_and_failed_uploader_refuse(self):
        for platform in sorted(binding.PLATFORMS):
            with self.subTest(platform=platform):
                identity=self.sidecars[platform];saved=self.f.data[identity]
                artifact=next(a for a in self.f.artifacts if a['id']==identity);metadata=copy.deepcopy(artifact)
                self.mutate_sidecar(platform,lambda files:files.pop('workspaces-32.json'))
                with self.assertRaises(readiness.ReadinessError):self.f.produce()
                self.f.data[identity]=saved;artifact.clear();artifact.update(metadata)
                job=next(j for j in self.f.jobs if j['name'].endswith('<'+platform+'>'))
                step=next(s for s in job['steps'] if s['name']==launch.UPLOAD)
                step['conclusion']='failure'
                with self.assertRaises(readiness.ReadinessError):self.f.produce()
                step['conclusion']='success'
        artifact=self.f.artifacts.pop()
        with self.assertRaises(readiness.ReadinessError):self.f.produce()
        self.f.artifacts.append(artifact)

    def test_named_child_skip_and_final_projection_tampering_refuse(self):
        record=self.f.produce();changed=copy.deepcopy(record)
        changed['native']['launch_components']['windows/amd64']['observations'][0]['bindings_sha256']='0'*64
        with self.assertRaises(readiness.ReadinessError):self.f.verify(changed)
        platform='linux/arm64'
        def skip(files):
            raw=json.loads(files['native-tests.json'])
            row=next(r for r in raw['subtests'] if r['test'].endswith('/workspaces-32'));row['result']='skip'
            files['native-tests.json']=json.dumps(raw).encode()
            stamp=json.loads(files['ci20-native-tested.json'])
            files['native-observation.json']=json.dumps(existing.reports.admit_go(raw,stamp,self.f.tree)).encode()
        self.f.rewrite(platform,skip)
        with self.assertRaises(readiness.ReadinessError):self.f.produce()

    def test_same_source_sidecar_and_exact_uploader_log_are_independent_authorities(self):
        platform='windows/arm64';identity=self.sidecars[platform]
        def foreign(files):
            row=json.loads(files['workspaces-31.json']);row['source_commit']='b'*40
            files['workspaces-31.json']=json.dumps(row).encode()
        self.mutate_sidecar(platform,foreign)
        with self.assertRaises(ValueError):self.f.produce()
        self.mutate_sidecar(platform,lambda files:files.update({
            'workspaces-31.json':json.dumps(self.raw(platform,31)).encode()}))
        actual=self.f.api
        self.f.api=lambda path,binary=False: (self.original_api(path,binary)
            if path.startswith('actions/jobs/') and path.endswith('/logs') else actual(path,binary))
        with self.assertRaises(readiness.ReadinessError):self.f.produce()

    def test_expected_inputs_uses_immutable_python_namespace_and_absence(self):
        source='a'*40;rows={'_artifactauthoritylib.py':('100644','blob',3)}
        load=mock.Mock(return_value=b'raw')
        with mock.patch.object(readiness,'_tree_entries',return_value=rows):
            result=launch.expected_inputs(ROOT,source,load)
        self.assertEqual(set(result),{'core/pysrc/_artifactauthoritylib.py',launch.OBSERVER})
        self.assertEqual(load.call_args_list,[mock.call(source,p) for p in result])
        for forbidden in ('_host.py','_HOST.PY'):
            with mock.patch.object(readiness,'_tree_entries',return_value={**rows,forbidden:('100644','blob',3)}):
                with self.assertRaises(ValueError):launch.expected_inputs(ROOT,source,load)

    def test_large_tool_identity_records_share_the_bounded_streaming_limit(self):
        value=self.raw('windows/amd64',32);req={**self.f.req,'run_attempt':1}
        value['runtime_before']['files']['interpreter']['bytes']=93713712
        value['runtime_after']=copy.deepcopy(value['runtime_before'])
        next(row for row in value['launch_files'] if row['role']=='node-runtime')['bytes']=93713712
        launch.validate(value,req,'windows/amd64',32)
        for target in ('runtime','launch'):
            changed=copy.deepcopy(value)
            if target=='runtime':
                changed['runtime_before']['files']['interpreter']['bytes']=launch.IDENTITY_FILE_LIMIT+1
                changed['runtime_after']=copy.deepcopy(changed['runtime_before'])
            else:changed['launch_files'][0]['bytes']=launch.IDENTITY_FILE_LIMIT+1
            with self.assertRaises(ValueError):launch.validate(changed,req,'windows/amd64',32)

    def test_runtime_population_directory_entries_bytes_and_version_overflows_refuse(self):
        cases=('files','directories','entries','bytes','version','links')
        for case in cases:
            value=self.raw('windows/amd64',0);runtime=value['runtime_before']
            if case=='files':runtime['files'].update({f'stdlib/f{i}.py':{'bytes':0,'sha256':'e'*64}
                                                     for i in range(launch.RUNTIME_FILE_LIMIT)})
            elif case=='directories':runtime['directories']={f'stdlib/d{i}':[] for i in range(launch.RUNTIME_DIRECTORY_LIMIT+1)}
            elif case=='entries':runtime['directories']={'stdlib/.':sorted(f'f{i}' for i in range(launch.RUNTIME_ENTRY_LIMIT+1))}
            elif case=='bytes':runtime['files']={name:{'bytes':300<<20,'sha256':'e'*64} for name in ('interpreter','stdlib/large.py')}
            elif case=='version':runtime['version']=[3,15,2]
            else:runtime['links']={'stdlib/link.py':{'target':'../outside.py','identity':{'device':1,'inode':1,'mode':0,'bytes':1,'mtime_ns':1}}}
            value['runtime_after']=copy.deepcopy(runtime)
            with self.subTest(case=case),self.assertRaises(ValueError):
                launch.validate(value,{**self.f.req,'run_attempt':1},'windows/amd64',0)
        value=self.raw('windows/amd64',0)
        value['runtime_before']['links']={'stdlib/link.py':{'target':'inside.py','identity':{'device':1,'inode':1,'mode':0o120777,'bytes':9,'mtime_ns':1}}}
        value['runtime_after']=copy.deepcopy(value['runtime_before'])
        launch.validate(value,{**self.f.req,'run_attempt':1},'windows/amd64',0)
        value['runtime_after']['links']['stdlib/link.py']['target']='other.py'
        with self.assertRaises(ValueError):launch.validate(value,{**self.f.req,'run_attempt':1},'windows/amd64',0)

    def test_large_sidecar_uses_same_document_budget_through_original_archive_consumer(self):
        value=self.raw('linux/amd64',0);runtime=value['runtime_before']
        names=['owned_'+('x'*80)+str(i)+'.py' for i in range(12000)]
        runtime['files'].update({'stdlib/'+name:{'bytes':0,'sha256':'e'*64} for name in names})
        runtime['directories']={'stdlib/.':sorted(names)}
        value['runtime_after']=copy.deepcopy(runtime)
        encoded=launch.encode_record(value)
        self.assertGreater(len(encoded),4<<20)
        self.assertLessEqual(len(encoded),launch.SIDECAR_JSON_LIMIT)
        self.mutate_sidecar('linux/amd64',lambda files:files.update({'workspaces-0.json':encoded}))
        record=self.f.produce()
        self.assertEqual(self.f.verify(record)['state'],'PREPUBLICATION_READY')
        import io,zipfile
        oversized=io.BytesIO()
        with zipfile.ZipFile(oversized,'w') as archive:
            archive.writestr('workspaces-0.json',b'x'*(launch.SIDECAR_JSON_LIMIT+1))
        with zipfile.ZipFile(io.BytesIO(oversized.getvalue())) as archive:
            with self.assertRaisesRegex(readiness.ReadinessError,'native input document exceeds bound'):
                native._document(archive,'workspaces-0.json',launch.SIDECAR_JSON_LIMIT)
        with self.assertRaisesRegex(ValueError,'binding sidecar exceeds bound'):
            launch.encode_record({'padding':'x'*launch.SIDECAR_JSON_LIMIT})

    def test_selected_actual_parents_exist_on_every_required_platform(self):
        recipes={'task:'+task:{p:launch.selectors(p) for p in binding.PLATFORMS} for task in launch.TASKS}
        self.assertEqual(existing._native_recipe_source_errors(ROOT / "core/artifacts",recipes),[])
        for platform in binding.PLATFORMS:
            self.assertEqual(len(launch.selectors(platform)), len(set(launch.selectors(platform))))
            legacy=any(name.endswith(':TestCompletionWorkspaceLegacyWindowsIdentity')
                       for name in launch.selectors(platform))
            self.assertEqual(legacy,platform.startswith('windows/'))

    def test_opt_in_selection_closed_and_default_native_grammar_unchanged(self):
        for value in [[],['OTHER'],['HW-04','HW-04'],[{}]]:
            with self.assertRaises(ValueError):launch.tasks(value)
        original=existing.NativeCompositeAuthorityTests();original.setUp()
        record=original.produce()
        self.assertNotIn('launch_components',record['native'])
        self.assertEqual(original.verify(record)['state'],'PREPUBLICATION_READY')
        self.assertEqual(len(native.RECIPES),40)


class IdentityLimitTests(unittest.TestCase):
    def test_large_identity_streams_while_source_reader_keeps_small_limit(self):
        with tempfile.TemporaryDirectory(prefix='hw04-identity-limit-') as raw:
            path=Path(raw).resolve()/'owned.bin'
            size=(64<<20)+1
            with path.open('wb') as stream:stream.truncate(size)
            expected=hashlib.sha256()
            with path.open('rb') as stream:
                while part:=stream.read(1<<20):expected.update(part)
            original=launch.os.read;populations=[]
            def bounded(fd,n):
                populations.append(n)
                return original(fd,n)
            with mock.patch.object(launch.os,'read',side_effect=bounded):
                self.assertEqual(launch.file_identity(path),{'bytes':size,'sha256':expected.hexdigest()})
            self.assertLessEqual(max(populations),1<<20)
            with self.assertRaises(ValueError):launch.read(path)
            with self.assertRaises(ValueError):launch.file_identity(path,limit=size-1)
            with path.open('r+b') as stream:stream.truncate(launch.IDENTITY_FILE_LIMIT+1)
            with self.assertRaises(ValueError):launch.file_identity(path)

    def test_stream_refuses_growth_and_descriptor_identity_changes(self):
        with tempfile.TemporaryDirectory(prefix='hw04-identity-race-') as raw:
            path=Path(raw).resolve()/'owned.bin';path.write_bytes(b'abc')
            original=launch.os.read;first=True
            def grow(fd,n):
                nonlocal first
                data=original(fd,n)
                if first:
                    first=False
                    with path.open('ab') as stream:stream.write(b'd')
                return data
            with mock.patch.object(launch.os,'read',side_effect=grow):
                with self.assertRaises(ValueError):launch.file_identity(path)
            with mock.patch.object(launch.os,'open',side_effect=lambda *a,**k: (_ for _ in ()).throw(OSError('closed'))):
                with self.assertRaises(OSError):launch.file_identity(path)



    def test_actual_owned_timeout_retains_closed_last_producer_phase(self):
        # One tiny ordinary Python child; no full runtime scan or product tool.
        with tempfile.TemporaryDirectory(prefix='producer-phase-control-') as raw:
            base=Path(raw).resolve();core=base/'repo/core/pysrc';core.mkdir(parents=True)
            observer=base/'repo/.github/scripts/npm_binding_observation.py';observer.parent.mkdir(parents=True)
            tiny='import time\ndef runtime_snapshot():\n time.sleep(2)\nruntime_snapshot()\n'
            script='exec(compile('+repr(tiny)+','+repr(str(observer))+',"exec")) # PRIVATE_PHASE_CANARY'
            env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR'}}
            env.update(HOME=str(base),USERPROFILE=str(base),TEMP=str(base),TMP=str(base),PATH='')
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                producer_child_run([sys.executable,'-I','-S','-B','-X','utf8','-c',script,str(core)],
                    cwd=base,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=0.25)
            report=getattr(caught.exception,'producer_progress',None)
            self.assertEqual(report and report['status'],'recorded','timeout discarded the last bounded producer phase')
            self.assertEqual(report['record']['phase'],'runtime-before-enumeration')
            self.assertEqual(report['record']['runtime_ordinal'],1)
            self.assertEqual(caught.exception.timeout,0.25)
            visible=str(caught.exception)+' '.join(getattr(caught.exception,'__notes__',[]))
            self.assertNotIn('PRIVATE_PHASE_CANARY',visible)
            self.assertNotIn(str(base),visible)
            self.assertLessEqual(len(json.dumps(report).encode()),32768)

    def test_closed_progress_refuses_extra_payload_malformed_links_and_budgets(self):
        with tempfile.TemporaryDirectory(prefix='producer-progress-shape-') as raw:
            root=Path(raw).resolve();path=root/'producer-progress.json'
            good={'format':'codearbiter.npm-producer-progress/1','phase':'runtime-before-hashing',
                  'elapsed_ms':20,'runtime_ordinal':1,'discovered_files':128,'completed_files':127,
                  'completed_bytes':4096,'directories':2,'entries':130,'links':0}
            path.write_text(json.dumps(good));self.assertEqual(read_producer_progress(path),good)
            late={**good,'elapsed_ms':PRODUCER_UNIT_TIMEOUT_SECONDS * 1000}
            path.write_text(json.dumps(late));self.assertEqual(read_producer_progress(path),late)
            for value in ({**good,'elapsed_ms':PRODUCER_UNIT_TIMEOUT_SECONDS * 1000 + 1},{**good,'payload':'PRIVATE_PROGRESS_CANARY'},{**good,'phase':'PRIVATE_PROGRESS_CANARY'},
                          {**good,'completed_bytes':(512<<20)+1},{**good,'elapsed_ms':True},
                          {**good,'completed_files':32769},{**good,'entries':65537},
                          {**good,'directories':2049},{**good,'runtime_ordinal':3}):
                path.write_text(json.dumps(value))
                with self.subTest(shape=tuple(value)),self.assertRaises(ValueError):read_producer_progress(path)
            for data in (b'{bad',b'{"format":1,"format":2}',b'x'*32769):
                path.write_bytes(data)
                with self.assertRaises(ValueError):read_producer_progress(path)
            path.write_text(json.dumps(good));link=root/'second-name';os.link(path,link)
            with self.assertRaises(ValueError):read_producer_progress(path)
            link.unlink()

    def test_progress_refusal_never_echoes_unknown_data_or_hides_timeout(self):
        with tempfile.TemporaryDirectory(prefix='producer-progress-refusal-') as raw:
            root=Path(raw).resolve();path=root/'producer-progress.json'
            path.write_text('{"unknown":"PRIVATE_PROGRESS_CANARY"}')
            self.assertEqual(producer_progress_report(path),{'status':'refused','record':None})
            path.unlink()
            self.assertEqual(producer_progress_report(path),{'status':'unavailable','record':None})

class RuntimePortabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owned=tempfile.TemporaryDirectory(prefix='ca-owned-runtime-8193-')
        cls.base=Path(cls.owned.name).resolve()
        cls.full=cls.base/'full';(cls.full/'stdlib').mkdir(parents=True)
        (cls.full/'owned-python.exe').write_bytes(b'inert owned identity')
        for index in range(8192):(cls.full/'stdlib'/f'f{index:05d}.py').touch()

    @classmethod
    def tearDownClass(cls):cls.owned.cleanup()

    def runtime(self,root):
        from contextlib import ExitStack
        stack=ExitStack()
        stack.enter_context(mock.patch.object(launch.sysconfig,'get_path',return_value=str(root/'stdlib')))
        stack.enter_context(mock.patch.object(launch.sysconfig,'get_config_var',return_value=None))
        stack.enter_context(mock.patch.object(launch.sys,'base_prefix',str(root)))
        stack.enter_context(mock.patch.object(launch.sys,'executable',str(root/'owned-python.exe')))
        return stack

    def test_actual_owned_8193_regular_file_inventory_is_complete(self):
        with self.runtime(self.full):snapshot,paths=launch.runtime_snapshot()
        self.assertEqual(len(snapshot['files']),8193)
        self.assertEqual(len(paths),8193)
        self.assertEqual(sum(row['bytes'] for row in snapshot['files'].values()),len(b'inert owned identity'))
        self.assertIn('stdlib/f08191.py',snapshot['files'])

    def linked(self):
        root=self.base/'linked';stdlib=root/'stdlib';stdlib.mkdir(parents=True,exist_ok=True)
        (root/'owned-python.exe').write_bytes(b'inert owned identity')
        (stdlib/'inside.py').write_bytes(b'inside')
        (root/'outside.py').write_bytes(b'outside')
        (root/'outside-dir').mkdir(exist_ok=True)
        (root/'outside-dir/hidden.py').write_bytes(b'never traversed')
        for name,target,is_directory in [('internal-link.py','inside.py',False),
            ('external-link.py','../outside.py',False),('directory-link','../outside-dir',True),
            ('dangling-link.py','absent.py',False)]:
            path=stdlib/name
            if not path.is_symlink():os.symlink(target,path,target_is_directory=is_directory)
        return root

    def test_actual_owned_links_are_inert_and_never_traversed(self):
        root=self.linked()
        with self.runtime(root):snapshot,paths=launch.runtime_snapshot()
        self.assertEqual(set(snapshot['links']),{'stdlib/internal-link.py','stdlib/external-link.py',
            'stdlib/directory-link','stdlib/dangling-link.py'})
        self.assertEqual(set(snapshot['files']),{'interpreter','stdlib/inside.py'})
        self.assertEqual(snapshot['links']['stdlib/external-link.py']['target'],'../outside.py')
        self.assertNotIn('hidden.py',' '.join(snapshot['files']))
        self.assertNotIn(root/'outside.py',paths.values())


    def test_snapshot_budget_stops_before_hashing_an_over_budget_file(self):
        path=self.full/'stdlib/f00000.py';path.write_bytes(b'x'*40)
        try:
            with self.runtime(self.full),mock.patch.object(launch,'RUNTIME_BYTE_LIMIT',20), \
                 mock.patch.object(launch,'file_identity',wraps=launch.file_identity) as hashed:
                with self.assertRaisesRegex(ValueError,'runtime byte bound exceeded: observed=60 limit=20'):
                    launch.runtime_snapshot()
                self.assertEqual(hashed.call_count,1)
                self.assertEqual(hashed.call_args.args[1],20)
        finally:path.write_bytes(b'')
        with self.runtime(self.full),mock.patch.object(launch,'RUNTIME_FILE_LIMIT',8192):
            with self.assertRaisesRegex(ValueError,'runtime file bound exceeded: observed=8193 limit=8192'):
                launch.runtime_snapshot()
        with self.runtime(self.full),mock.patch.object(launch,'RUNTIME_DIRECTORY_LIMIT',0):
            with self.assertRaisesRegex(ValueError,'runtime directory bound exceeded'):
                launch.runtime_snapshot()
        with self.runtime(self.full),mock.patch.object(launch,'RUNTIME_ENTRY_LIMIT',8191):
            with self.assertRaisesRegex(ValueError,'runtime directory population exceeds bound'):
                launch.runtime_snapshot()

    def test_inert_link_change_and_unrecorded_consumed_imports_are_refused(self):
        root=self.linked();link=root/'stdlib/internal-link.py';original=launch.os.readlink;first=True
        def mutate(path):
            nonlocal first
            target=original(path)
            if first:
                first=False;link.unlink();os.symlink('../outside.py',link)
            return target
        try:
            with mock.patch.object(launch.os,'readlink',side_effect=mutate):
                with self.assertRaisesRegex(ValueError,'runtime link changed during read'):launch.link_identity(link)
        finally:
            link.unlink();os.symlink('inside.py',link)
        with self.runtime(root):snapshot,paths=launch.runtime_snapshot()
        from types import SimpleNamespace
        module=SimpleNamespace(__spec__=None,__file__=str(link))
        with mock.patch.object(launch.sys,'modules',{'owned_alias':module}):
            self.assertEqual(launch.consumed_imports(self.base/'repo',{},paths),
                [{'name':'owned_alias','kind':'runtime','path':'stdlib/inside.py'}])
        for name in ('external-link.py','dangling-link.py'):
            module=SimpleNamespace(__spec__=None,__file__=str(root/'stdlib'/name))
            with mock.patch.object(launch.sys,'modules',{'unrecorded':module}):
                with self.subTest(name=name),self.assertRaises((ValueError,OSError)):
                    launch.consumed_imports(self.base/'repo',{},paths)




class HookF04FiniteFindingAdmissionTests(unittest.TestCase):
    """Finding admission reuses the actual HW04 transport; fixture bytes only."""
    CELL = "disposition:findings:HOOK-F04"

    def fixture(self):
        helper = AdmissionTests()
        helper.setUp()
        f = helper.f
        f.req["cells"].append(self.CELL)
        f.req["cell_jobs"][self.CELL] = "major qualification / native"
        f.req["launch_binding_findings"] = [self.CELL]
        return helper, f

    def test_hook_f04_requires_complete_original_six_platform_launch_transport(self):
        helper, f = self.fixture()
        try:
            record = f.produce()
        except (ValueError, KeyError) as error:
            self.fail("HOOK-F04 original HW04 launch admission is unavailable: " + str(error))
        result, = [row for row in record["native"]["results"] if row["cell"] == self.CELL]
        self.assertEqual({row["platform"] for row in result["components"]}, set(binding.PLATFORMS))
        for row in result["components"]:
            self.assertEqual(row["selectors"], launch.selectors(row["platform"]))
        self.assertEqual(set(record["native"]["launch_components"]), set(binding.PLATFORMS))
        for row in record["native"]["launch_components"].values():
            self.assertEqual({x["workspace_count"] for x in row["observations"]}, set(launch.COUNTS))
        self.assertEqual(f.verify(record)["state"], "PREPUBLICATION_READY")
        policy = json.loads((ROOT / ".github/major-qualification-policy.json").read_bytes())
        self.assertEqual(policy["native_launch_binding_findings"], [self.CELL])
        self.assertEqual(len(native.RECIPES), 40)
        self.assertEqual(tuple(launch.TASKS), ("HW-04", "NT-04"))

    def test_hook_f04_refuses_missing_owner_or_unreviewed_finding_authority(self):
        helper, f = self.fixture()
        original = copy.deepcopy(f.req)
        for mutation in ("missing-selection", "foreign", "duplicate", "empty", "missing-HW04", "missing-inputs", "foreign-job"):
            f.req = copy.deepcopy(original)
            if mutation == "missing-selection": f.req.pop("launch_binding_findings")
            elif mutation == "foreign": f.req["launch_binding_findings"] = ["disposition:findings:HOOK-F01"]
            elif mutation == "duplicate": f.req["launch_binding_findings"] *= 2
            elif mutation == "empty": f.req["launch_binding_findings"] = []
            elif mutation == "missing-HW04": f.req["launch_binding_tasks"] = ["NT-04"]
            elif mutation == "missing-inputs": f.req.pop("launch_binding_inputs")
            else: f.req["cell_jobs"][self.CELL] = "foreign"
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, KeyError)): f.produce()

    def test_hook_f04_refuses_sidecar_identity_incomplete_named_case_and_projection_tampering(self):
        helper, f = self.fixture()
        record = f.produce()
        changed = copy.deepcopy(record)
        result = next(r for r in changed["native"]["results"] if r["cell"] == self.CELL)
        result["components"][0]["selectors"].pop()
        with self.assertRaises(ValueError): f.verify(changed)
        for platform in sorted(binding.PLATFORMS):
            identity = helper.sidecars[platform]
            saved, metadata = f.data[identity], copy.deepcopy(helper.sidecar_metadata[identity])
            helper.mutate_sidecar(platform, lambda files: files.pop("workspaces-32.json"))
            with self.subTest(platform=platform), self.assertRaises(ValueError): f.produce()
            f.data[identity] = saved
            helper.sidecar_metadata[identity].clear(); helper.sidecar_metadata[identity].update(metadata)
        for mutation in ("source", "profile", "runtime", "imports", "count", "launch"):
            platform = "windows/amd64"; identity = helper.sidecars[platform]
            saved, metadata = f.data[identity], copy.deepcopy(helper.sidecar_metadata[identity])
            def corrupt(files):
                raw = json.loads(files["workspaces-32.json"])
                if mutation == "source": raw["source_commit"] = "f" * 40
                elif mutation == "profile": raw["profile"] = "foreign"
                elif mutation == "runtime": raw["runtime_after"]["isolated"] = 0
                elif mutation == "imports": raw["imports"][0]["path"] = "core/pysrc/_host.py"
                elif mutation == "count": raw["workspace_count"] = 31
                else: raw["launch_files"].pop()
                files["workspaces-32.json"] = json.dumps(raw).encode()
            helper.mutate_sidecar(platform, corrupt)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): f.produce()
            f.data[identity] = saved
            helper.sidecar_metadata[identity].clear(); helper.sidecar_metadata[identity].update(metadata)
        def skipped(files):
            raw = json.loads(files["native-tests.json"])
            row = next(r for r in raw["subtests"] if r["test"].endswith("/workspaces-32"))
            row["result"] = "skip"
            files["native-tests.json"] = json.dumps(raw).encode()
            stamp = json.loads(files["ci20-native-tested.json"])
            files["native-observation.json"] = json.dumps(existing.reports.admit_go(raw, stamp, f.tree)).encode()
        f.rewrite("linux/arm64", skipped)
        with self.assertRaises(ValueError): f.produce()


if __name__ == '__main__':
    unittest.main()
