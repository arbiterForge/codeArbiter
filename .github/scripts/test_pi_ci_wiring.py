"""Pure-source Pi coordinator/wiring controls; synthetic profiles are not host proof."""
import copy
from contextlib import nullcontext
import hashlib
import shutil
import subprocess
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parent))
import coordinate_pi_host as coordinator
import major_qualification_report as reports
import major_readiness as readiness
import pi_live_report_profile as adapter
from test_observe_pi_installed_rpc import fixture,TEST_ID

ROOT=Path(__file__).resolve().parents[2]
JOB='[CHECK] | [PI  ] | Installed retained package <pi: windows 1.5.0>'
PI_PATHS=['.github/scripts/'+name for name in ('_pi_rpc_profile.py','observe_pi_installed_rpc.py',
    'test_observe_pi_installed_rpc.py','coordinate_pi_host.py','pi_live_report_profile.py','test_pi_ci_wiring.py')]

def job(text,name):
    match=re.search(r'^  '+re.escape(name)+r':\n(.*?)(?=^  [a-zA-Z][a-zA-Z0-9_-]*:|\Z)',text,re.S|re.M)
    if not match:raise AssertionError('missing job '+name)
    return match.group(1)

def assert_wiring(text,policy,selections):
    installed=job(text,'pi-installed-package')
    for item in ("needs: [changes, artifact-package-assembly]","needs.artifact-package-assembly.result == 'success'",
        "github.repository == 'arbiterForge/codeArbiter'","github.event_name == 'push'",
        "github.ref == 'refs/heads/main'","github.ref == 'refs/heads/major/state-contracts'",
        'persist-credentials: false','actions: read','contents: read','timeout-minutes: 15',
        'platform: linux/amd64','platform: windows/amd64','platform: darwin/arm64',
        "steps.program.outputs.enabled == 'true'",'artifact-host-payloads-${{ github.sha }}',
        'artifact-release-packages-${{ github.sha }}','--expected-platform "${{ matrix.platform }}"',
        'python -I -B .github/scripts/coordinate_pi_host.py','github.run_attempt',
        "steps.pi-qualification.outcome == 'success'"):
        if item not in installed:raise AssertionError('missing owned Pi wiring: '+item)
    if 'pi_host_locks.py install' in installed or 'npm install' in installed or 'continue-on-error' in installed:
        raise AssertionError('coordinator producer must own the only acquisition')
    checks=job(text,'ca-pi-checks')
    for command in ('python -B .github/scripts/test_observe_pi_installed_rpc.py','python -B .github/scripts/test_pi_ci_wiring.py'):
        if command not in checks:raise AssertionError('source unit not reached: '+command)
    if 'artifact-package-assembly' in checks:raise AssertionError('required source check depends on production assembly')
    for section in ('ca-pi','artifacts'):
        block=re.search(r'^            '+section+r':\n(.*?)(?=^            [a-zA-Z_-]+:|^      - |\Z)',text,re.S|re.M).group(1)
        for path in PI_PATHS:
            if "- '"+path+"'" not in block:raise AssertionError('missing exact impact path '+section+':'+path)
    for system in ('linux','windows','darwin'):
        name='[CHECK] | [PI  ] | Installed retained package <pi: '+system+' 1.5.0>'
        cell='installed:pi:'+system+':1.5.0'
        if policy['cell_job_bindings'].get(cell)!=name:raise AssertionError('wrong finite Pi owner')
        groups=[g for g in selections['groups'] if g['id']=='pi-live-'+system]
        if len(groups)!=1 or groups[0]['job']!=name or groups[0]['cells']!=[cell] or groups[0]['selectors']!=[TEST_ID]:
            raise AssertionError('wrong finite installed Pi population')

class WiringTests(unittest.TestCase):
    def test_actual_required_source_lane_and_three_installed_jobs_are_connected(self):
        assert_wiring((ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8'),
            json.loads((ROOT/'.github/major-qualification-policy.json').read_text(encoding='utf-8')),
            json.loads((ROOT/'.github/major-test-selections.json').read_text(encoding='utf-8')))

    def test_missing_trust_payload_budget_or_source_reachability_fails_the_same_guard(self):
        text=(ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8')
        policy=json.loads((ROOT/'.github/major-qualification-policy.json').read_text(encoding='utf-8'))
        selections=json.loads((ROOT/'.github/major-test-selections.json').read_text(encoding='utf-8'))
        for operand in ("github.event_name == 'push'",'artifact-host-payloads-${{ github.sha }}','timeout-minutes: 15',
            'python -B .github/scripts/test_pi_ci_wiring.py','platform: darwin/arm64'):
            with self.subTest(operand=operand),self.assertRaises(AssertionError):
                # Mutate only the owning job for shared operands.
                if operand.startswith('python -B'):changed=text.replace(operand,'omitted-command')
                else:
                    old=job(text,'pi-installed-package');changed=text.replace(old,old.replace(operand,'omitted-boundary'))
                assert_wiring(changed,policy,selections)

class ControlTests(unittest.TestCase):
    def test_trusted_program_mode_has_no_pr_fork_or_marker_fallback(self):
        env={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':coordinator.REPOSITORY,'GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/major/state-contracts'}
        self.assertTrue(coordinator.program_mode(env,True))
        for key,value in [('GITHUB_ACTIONS','false'),('GITHUB_REPOSITORY','foreign/repo'),('GITHUB_EVENT_NAME','pull_request'),('GITHUB_REF','refs/heads/topic')]:
            with self.subTest(key=key):self.assertFalse(coordinator.program_mode({**env,key:value},True))
        self.assertFalse(coordinator.program_mode(env,False))

    def test_actual_sequence_admits_before_single_producer_and_reads_original_acquisition(self):
        calls=[];observation=object();acquisition=object()
        def record(name,value=None):
            calls.append(name);return value
        result=coordinator.coordinate_sequence(lambda:record('verify'),lambda:record('produce',observation),
            lambda:record('read-acquisition',acquisition),lambda o,a:record(('report',o is observation,a is acquisition),'reported'))
        self.assertEqual(result,'reported');self.assertEqual(calls,['verify','produce','read-acquisition',('report',True,True)])
        calls=[]
        def refuse():raise ValueError('production refusal')
        with self.assertRaisesRegex(ValueError,'production refusal'):
            coordinator.coordinate_sequence(refuse,lambda:record('produce'),lambda:record('read'),lambda o,a:record('report'))
        self.assertEqual(calls,[])

    def test_public_cli_refuses_wrong_context_before_runtime_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            argv=['--repo',str(root),'--stage',str(root/'stage'),'--package-root',str(root/'packages'),
                '--workspace',str(root/'workspace'),'--output-root',str(root/'output'),'--expected-platform','windows/amd64']
            with (mock.patch.dict(os.environ,{},clear=True),mock.patch.object(coordinator,'selected_runtime',side_effect=AssertionError('effect')),
                    self.assertRaisesRegex(ValueError,'not a trusted')):
                coordinator.main(argv)
            self.assertFalse((root/'output').exists())

class ReportTests(unittest.TestCase):
    def setup_fixture(self):
        req,o,p,a=fixture();req.update(cells=['installed:pi:windows:1.5.0'],cell_jobs={'installed:pi:windows:1.5.0':JOB})
        locks={name:('reviewed-'+name).encode() for name in adapter.LOCK_NAMES}
        a['source_locks']={name:hashlib.sha256(value).hexdigest() for name,value in locks.items()}
        o['installed_binding']['worker']['source_before']['inputs'].update({'.github/fixtures/pi-hosts/1.5.0/'+n:h for n,h in a['source_locks'].items()})
        o['installed_binding']['worker']['source_after']=copy.deepcopy(o['installed_binding']['worker']['source_before'])
        selection={'schema':reports.SELECTIONS,'groups':[{'id':'pi-synthetic','job':JOB,
            'payload_name':'artifact-release-packages-{source_commit}','observation':'pi-live','proof_kind':'live-host',
            'selectors':[TEST_ID],'cells':req['cells'],'scope':'Synthetic admission fixture only; no installed observation.'}]}
        return req,o,p,a,selection,locks

    def build(self,change=None):
        req,o,p,a,s,locks=self.setup_fixture()
        if change:change(req,o,p,a,s)
        def immutable(repo,source,path):
            self.assertEqual(source,req['source_commit']);return locks[path.rsplit('/',1)[1]]
        with mock.patch.object(readiness,'blob',side_effect=immutable):
            return reports.build_report(req,job_name=JOB,job_id=9,selections=s,observations={'pi-live':o},
                payloads=p,runtime_acquisitions={'pi-live':a})

    def test_actual_report_routes_exact_pi_profile_acquisition_and_dual_original_payloads(self):
        result=self.build();self.assertEqual(result['schema'],'codearbiter-major-qualification/3')
        self.assertEqual(result['results'][0]['cell'],'installed:pi:windows:1.5.0')
        self.assertEqual(result['results'][0]['payload_artifact_ids'],[11,12])
        self.assertEqual(result['results'][0]['selected_population'],1)

    def test_label_spoof_wrong_platform_acquisition_lock_and_second_payload_refuse(self):
        changes=[lambda q,o,p,a,s:o.update(producer='python-test-result-observer'),
            lambda q,o,p,a,s:o['installed_binding'].update(profile='unknown'),
            lambda q,o,p,a,s:o['installed_binding'].update(platform='linux/amd64'),
            lambda q,o,p,a,s:a.update(source_locks={}),
            lambda q,o,p,a,s:next(reversed(p.values())).update(artifact_id=99)]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):self.build(change)

    def test_embedded_acquisition_alone_and_unknown_live_profile_are_not_admission(self):
        req,o,p,a,s,locks=self.setup_fixture()
        with self.assertRaisesRegex(ValueError,'acquisition'):
            reports.build_report(req,job_name=JOB,job_id=9,selections=s,observations={'pi-live':o},payloads=p)
        o['producer']='unknown';o['installed_binding']['profile']='unknown'
        with self.assertRaises(ValueError):
            reports.build_report(req,job_name=JOB,job_id=9,selections=s,observations={'pi-live':o},payloads=p)

class OrchestrationTests(unittest.TestCase):
    def run_control(self,*,alter_jobs=None,refuse=False,invalid_marker=False):
        req,o,p,acq=fixture();req.update(cell_jobs={'installed:pi:windows:1.5.0':JOB})
        marker={'schema':'codearbiter-integration-candidate/1','branch':'major/state-contracts',
            'baseline_main_commit':'c'*40,'candidates':dict.fromkeys(('ca','ca-codex','ca-pi','ca-sandbox'),'0.30.0')}
        if invalid_marker:marker['branch']='foreign'
        calls=[];attempt='2'
        jobs=[{'id':9,'name':JOB,'status':'in_progress','run_attempt':2},
            {'id':8,'name':'[CHECK] | [CORE] | Structured artifact package assembly','conclusion':'success','run_attempt':2}]
        if alter_jobs:alter_jobs(jobs)
        artifacts=[{'id':value['artifact_id'],'name':name} for name,value in p.items()]
        cohort=b'{"synthetic":true}'
        def verify(*args):
            calls.append('production')
            if refuse:raise ValueError('original production refusal')
            return json.loads(cohort)
        def produce(config,**kwargs):
            calls.append('produce');self.assertEqual(config['expected']['producer_job_id'],9)
            self.assertEqual(kwargs['authenticated_payloads'],p);self.assertEqual(set(config).intersection({'token','GH_TOKEN','GITHUB_TOKEN'}),set())
            return o
        def original(path):
            calls.append('read-acquisition');self.assertEqual(path.name,'runtime-acquisition.json');return acq
        def report(*args,**kwargs):
            calls.append('report');self.assertIs(kwargs['runtime_acquisitions']['pi-live'],acq)
            self.assertIs(kwargs['observations']['pi-live'],o);return {'schema':'codearbiter-major-qualification/3'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();out=root/'output';out.mkdir()
            a=SimpleNamespace(repo=ROOT,stage=root/'stage',package_root=root/'packages',workspace=root/'workspace',output_root=out,expected_platform='windows/amd64')
            cold=SimpleNamespace(_project_imports=lambda *args:nullcontext(),_verify_production=verify)
            producer=SimpleNamespace(raw=lambda path,limit:cohort if path.name=='artifact-package-cohort.json' else b'promotion',
                pairs=lambda pairs:dict(pairs),produce=produce,load=original)
            env={'GITHUB_SHA':req['source_commit'],'GITHUB_RUN_ID':'7','GITHUB_RUN_ATTEMPT':attempt,'GITHUB_REF':'refs/heads/major/state-contracts'}
            with (mock.patch.dict(os.environ,env,clear=True),mock.patch.object(reports,'validate_emitter_environment'),
                mock.patch.object(readiness,'blob',return_value=json.dumps(marker).encode()),
                mock.patch.object(readiness,'collect',return_value=(req,{'run_attempt':2,'head_branch':'major/state-contracts'},artifacts,jobs)),
                mock.patch.object(reports,'git',return_value=req['source_commit']),mock.patch.object(readiness,'validate_upload',side_effect=lambda *args:calls.append('upload')),
                mock.patch.object(reports,'authenticated_payload',side_effect=lambda metadata,*args:p[metadata['name']]),
                mock.patch.object(reports,'build_report',side_effect=report)):
                try:result=coordinator._run_control(a,cold,producer,root,{'phase':'test'},dict.fromkeys(('python','node','git','npm_launcher','npm_cli','npm_node'),'fixture'))
                except ValueError:return calls,None
        return calls,result

    def test_actual_control_body_authenticates_both_uploads_before_one_producer(self):
        calls,result=self.run_control()
        self.assertEqual(result,0);self.assertEqual(calls,['upload','upload','production','produce','read-acquisition','report'])

    def test_production_refusal_never_enters_producer_or_acquisition(self):
        calls,result=self.run_control(refuse=True)
        self.assertIsNone(result);self.assertEqual(calls,['upload','upload','production'])

    def test_invalid_immutable_program_marker_refuses_before_upload_or_producer(self):
        calls,result=self.run_control(invalid_marker=True)
        self.assertIsNone(result);self.assertEqual(calls,[])

    def test_foreign_attempt_or_ambiguous_current_job_refuses_before_any_payload_or_effect(self):
        for change in (lambda jobs:jobs[0].update(run_attempt=1),lambda jobs:jobs.append(copy.deepcopy(jobs[0])),
            lambda jobs:jobs[1].update(run_attempt=1)):
            with self.subTest(change=change):
                calls,result=self.run_control(alter_jobs=change);self.assertIsNone(result);self.assertEqual(calls,[])


class PublicSourceAdmissionTests(unittest.TestCase):
    def exercise_public(self,tampered):
        # Real immutable Git inventory + real cold import owner; no API/service doubles.
        git=shutil.which('git');self.assertIsNotNone(git)
        with tempfile.TemporaryDirectory(prefix='pi-control-source-') as directory:
            root=Path(directory).resolve();repo=root/'repo';scripts=repo/'.github/scripts';scripts.mkdir(parents=True)
            for folder in ('core/pysrc','core/surface','tools'):(repo/folder).mkdir(parents=True)
            (repo/'core/pysrc/inert.py').write_text('pass\n',encoding='utf-8')
            (repo/'tools/inert.py').write_text('pass\n',encoding='utf-8')
            (repo/'core/hosts.json').write_text('{}\n',encoding='utf-8')
            (repo/'.github/integration-candidate.json').write_text('{}\n',encoding='utf-8')
            shutil.copyfile(ROOT/'.github/scripts/retained_archive_cli_observation.py',scripts/'retained_archive_cli_observation.py')
            shutil.copyfile(Path(coordinator.__file__),scripts/'coordinate_pi_host.py')
            (scripts/'observe_pi_installed_rpc.py').write_text("def actual_platform():return 'windows/amd64'\n",encoding='utf-8')
            shared=scripts/'major_readiness.py'
            shared.write_text("raise ValueError('immutable owned module reached controlled refusal')\n",encoding='utf-8')
            (scripts/'major_qualification_report.py').write_text('pass\n',encoding='utf-8')
            env={k:os.environ[k] for k in ('SystemRoot','SYSTEMROOT','WINDIR','ComSpec','PATHEXT') if k in os.environ}
            env.update(HOME=str(root),USERPROFILE=str(root),GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0',
                PATH=os.pathsep.join([str(Path(git).parent),str(Path(sys.executable).parent),str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32')]))
            def local_git(*args):
                return subprocess.run([git,'-C',str(repo),'-c','core.hooksPath='+str(root/'no-hooks'),
                    '-c','user.name=fixture','-c','user.email=fixture@example.invalid',*args],env=env,capture_output=True,check=True).stdout.decode().strip()
            local_git('init','-q');local_git('config','core.autocrlf','false');local_git('add','.');local_git('commit','-qm','inert source fixture')
            source=local_git('rev-parse','HEAD');marker=root/'untrusted-shared-module-ran'
            injected='from pathlib import Path\nPath('+repr(str(marker))+').write_text("unexpected")\n'+shared.read_text(encoding='utf-8')
            if tampered=='package':
                package=scripts/'major_readiness';package.mkdir();(package/'__init__.py').write_text(injected,encoding='utf-8')
            elif tampered:shared.write_text(injected,encoding='utf-8')
            env.update(GITHUB_ACTIONS='true',GITHUB_REPOSITORY=coordinator.REPOSITORY,GITHUB_EVENT_NAME='push',
                GITHUB_REF='refs/heads/major/state-contracts',GITHUB_SHA=source,GITHUB_RUN_ID='7',GITHUB_RUN_ATTEMPT='1',GH_TOKEN='inert-fixture-control-token')
            runtime=dict.fromkeys(('python','node','npm_launcher','npm_cli','npm_node'),sys.executable);runtime['git']=git
            argv=['--repo',str(repo),'--stage',str(root/'stage'),'--package-root',str(root/'packages'),
                '--workspace',str(root/'workspace'),'--output-root',str(root/'output'),'--expected-platform','windows/amd64']
            # Match the fresh CLI registry; unrelated parent test imports are restored.
            names=('major_qualification_report','major_readiness','ci20_native_binding','_boundedproc','_contextverificationlib',
                'owned_output','host_descriptors','_artifactmanifestlib','_releaselib','_release_mechanism','_gitexec')
            with mock.patch.dict(sys.modules):
                for name in names:sys.modules.pop(name,None)
                with mock.patch.dict(os.environ,env,clear=True),mock.patch.object(coordinator,'selected_runtime',return_value=runtime),self.assertRaises(ValueError) as caught:
                    coordinator.main(argv)
            self.assertFalse(marker.exists(),'changed shared Python ran before immutable admission')
            self.assertFalse((root/'workspace').exists(),'runtime/RPC producer was not reached')
            self.assertFalse((root/'output/qualification.json').exists())
            return str(caught.exception)

    def test_public_bootstrap_rejects_changed_shared_module_before_import_with_control_token_present(self):
        self.assertIn('physical source differs from immutable Git blob',self.exercise_public(True))

    def test_public_bootstrap_rejects_untracked_package_shadow_before_import(self):
        self.assertIn('Python source lookup membership differs',self.exercise_public('package'))

    def test_public_bootstrap_allows_immutable_shared_source_to_reach_controlled_no_effect_refusal(self):
        self.assertIn('immutable owned module reached controlled refusal',self.exercise_public(False))

class PhysicalLookupTests(unittest.TestCase):
    def fixture(self,root):
        inputs={}
        for scope in ('core/pysrc','.github/scripts','tools'):
            folder=root/scope;folder.mkdir(parents=True)
            path=folder/'trusted.py';path.write_text('pass\n',encoding='utf-8');inputs[path.relative_to(root).as_posix()]='unused-already-joined-digest'
        return inputs

    def test_all_lookup_roots_refuse_untracked_python_and_compiled_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();inputs=self.fixture(root)
            coordinator._python_lookup_membership(root,inputs)
            for scope in ('core/pysrc','.github/scripts','tools'):
                for suffix in ('.py','.pyc','.pyo','.pyd','.so'):
                    with self.subTest(scope=scope,suffix=suffix):
                        path=root/scope/('unbound'+suffix);path.write_bytes(b'inert')
                        try:
                            with self.assertRaisesRegex(ValueError,'lookup'):
                                coordinator._python_lookup_membership(root,inputs)
                        finally:path.unlink()

    def test_regular_private_bytecode_is_unused_but_link_or_reparse_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();inputs=self.fixture(root)
            cache=root/'.github/scripts/__pycache__';cache.mkdir();(cache/'unbound.cpython.pyc').write_bytes(b'unused')
            coordinator._python_lookup_membership(root,inputs)
            # A real hard link is not an ordinary owned input either.
            linked=root/'tools/linked.py';os.link(root/'tools/trusted.py',linked)
            with self.assertRaisesRegex(ValueError,'ordinary'):
                coordinator._python_lookup_membership(root,inputs)
            linked.unlink()
            original=Path.lstat;target=root/'tools/trusted.py'
            def reparse(path,*args,**kwargs):
                result=original(path,*args,**kwargs)
                return SimpleNamespace(st_mode=result.st_mode,st_nlink=result.st_nlink,st_file_attributes=0x400) if path==target else result
            with mock.patch.object(Path,'lstat',reparse),self.assertRaisesRegex(ValueError,'linked'):
                coordinator._python_lookup_membership(root,inputs)

if __name__=='__main__':unittest.main()
