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
            result = subprocess.run([sys.executable,'-I','-S','-B','-X','utf8','-c',scripts[0],
                                     str(core),str(work),'0',platform], env=env, cwd=base,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
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
            'files':{'interpreter':{'bytes':1,'sha256':'d'*64}},'directories':{'stdlib/.':[]}}
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


if __name__ == '__main__':
    unittest.main()
