"""Pure producer controls with actual checker and a fixed nonexecuting spawn seam."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace, ModuleType
import unittest
from unittest import mock
import subprocess
import platform

HERE=Path(__file__).resolve().parent
# The normal checkout already contains this unchanged pure route validator.
sys.path.insert(0,str(HERE))
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m
P=load('producer_under_test',HERE/'observe_codex_installed_cli.py')
PROFILE=load('_codex_cli_profile',HERE/'_codex_cli_profile.py')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def put(path,raw):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
def js(value):return (json.dumps(value,sort_keys=True)+'\n').encode()

class ProducerTests(unittest.TestCase):
    def fixture(self, fault=None, version='0.143.0'):
        root=Path(self.enterContext(tempfile.TemporaryDirectory(prefix='codex-producer-unit-')))
        workspace=root/'workspace';out=root/'output';packages=root/'packages';stage=root/'stage'
        workspace.mkdir();out.mkdir();packages.mkdir();stage.mkdir()
        runtime=root/'unit-runtime.exe';runtime.write_bytes(b'INERT UNIT RUNTIME; NEVER EXECUTED')
        plugin=root/'original-package/plugins/ca-codex'
        capabilities={'repository_operations_available':True,'host_default_enabled':fault!='inactive-native','runtime_downloads':False}
        bridge=("import json\nfrom _artifactmanifestlib import validate_release_manifest\n"
                "def _bounded_child(*a):return (0,b'unit native raw response',b'')\n"
                "class ArtifactClient:\n def __init__(self,*a):pass\n"
                " def call(self,*a):\n  _bounded_child(['unit-native','capabilities','--root','unit','--request','-'],b'{}',7,30)\n  value="+repr(capabilities)+
                "\n  value['host_default_enabled']=value['host_default_enabled'] and validate_release_manifest({})=='installed'\n  return value"+
                "\ndef helper_installation(*a):return {}\n").encode()
        files={'.codex-plugin/plugin.json':js({'name':'ca-codex','version':'0.30.0'}),
          'hooks/hooks.json':js({'hooks':{'SessionStart':[{'hooks':[{'command':'python3 ${PLUGIN_ROOT}/hooks/example.py'}]}]}}),
          'hooks/example.py':b'# never executed\n','hooks/_host.py':b'HOST="codex"\n','hooks/_artifactlib.py':bridge,
          'hooks/_artifactmanifestlib.py':b'def validate_release_manifest(*a):return "installed"\n',
          'agents/INDEX.md':b'<!-- codearbiter-codex-agent-route-contract: literal_route_lines=0 literal_route_occurrences=0 generic_route_lines=0 generic_route_occurrences=0 -->\n| [fixture](fixture.md) |\n',
          'agents/fixture.md':b'# fixture\n','helpers/artifacts/ca-artifact-windows-amd64.exe':b'INERT UNIT NATIVE; NEVER EXECUTED',
          'helpers/artifacts/release.json':b'unit manifest; owning verifier is a fixed fixture seam'}
        for name,data in files.items():put(plugin/name,data)
        members={'plugins/ca-codex/'+k:{'type':'file','mode':'0644','size':len(v),'sha256':sha(v)} for k,v in files.items()}
        expected=dict(source_commit='a'*40,source_tree='b'*40,ci_run_id=17,producer_job_id=29)
        promotion=b'unit promotion';put(stage/'artifact-promotion.json',promotion)
        for name in ['helpers/artifacts/release.json','helpers/artifacts/ca-artifact-windows-amd64.exe']:
            put(stage/'plugins/ca-codex'/name,files[name])
        archive=b'INERT unit archive; extraction is a fixed seam';put(packages/'codex.tar.gz',archive)
        cohort={**{k:expected[k] for k in ['source_commit','source_tree']},'workflow':'.github/workflows/ci.yml','run_id':'17',
                'promotion_receipt_sha256':sha(promotion),'packages':{'codex':{'file':'codex.tar.gz','sha256':sha(archive),'members':members}}}
        put(packages/'artifact-package-cohort.json',js(cohort))
        def inventory(folder):return [{'path':p.relative_to(folder).as_posix(),'sha256':sha(p.read_bytes())} for p in sorted(folder.rglob('*')) if p.is_file()]
        auth={'packages':dict(artifact_id=71,archive_sha256='d'*64,members=inventory(packages)),
              'stage':dict(artifact_id=72,archive_sha256='e'*64,members=inventory(stage))}
        policy={version:{'platform':'windows/amd64','executable_sha256':sha(runtime.read_bytes()),'provenance':'unit-reviewed-acquisition','integrity':'unit-integrity'}}
        policy_path=root/'runtime-policy.json';put(policy_path,js(policy))
        cfg=dict(expected=expected,source_root=root/'source',workspace=workspace,output=out,package_root=packages,
          stage_root=stage,runtime_executable=runtime,runtime_version=version,runtime_policy=policy_path,
          trusted_runtime_policy_sha256=sha(policy_path.read_bytes()),
          roles=[dict(role='release-packages',artifact_name='packages'),dict(role='promoted-stage',artifact_name='stage')])
        checker=load('actual_candidate_checker_'+str(id(root)),HERE/'check_codex_host.py')
        counts={'checker':0,'verify':0,'spawn':0,'source':0}
        actual_check=checker.check_install
        def check(*a,**kw):counts['checker']+=1;return actual_check(*a,**kw)
        checker.check_install=check
        def verify(**kw):
            counts['verify']+=1;self.assertIs(kw['require_production'],True)
            self.assertEqual(counts['spawn'],0);return cohort
        def extract(artifact,destination,*,host):
            self.assertEqual(host,'codex');shutil.copytree(root/'original-package',destination);return destination
        def snapshot():
            counts['source']+=1
            return {'positive_inputs':{'unit.py':'0'*64},'selected_source':expected['source_commit'],
                    'tree':expected['source_tree'],'stable':not(fault=='source-drift' and counts['source']>1)}
        def spawn(argv,**kw):
            counts['spawn']+=1
            self.assertEqual(Path(argv[0]),runtime);self.assertEqual(kw['timeout'],300)
            self.assertNotIn('OPENAI_API_KEY',kw['env']);self.assertNotIn('CODEX_AUTH_TOKEN',kw['env'])
            tail=argv[1:];stdout='';code=0;timed=False;contain='exited'
            if tail==['--version']:stdout='codex-cli '+version+'\n'
            elif tail==['plugin','add','ca-codex@codearbiter']:
                cache=workspace/'codex-home/plugins/cache/unit/ca-codex/0.30.0'
                shutil.copytree(workspace/'package/plugins/ca-codex',cache)
                if fault=='incomplete-cache':(cache/'agents/fixture.md').unlink()
                if fault=='failed-exit':code=9
                if fault=='timeout':timed=True;code=None;contain='terminated'
            elif tail==['plugin','list']:
                stdout='ca-codex@codearbiter installed enabled 0.30.0\n'
                if fault=='runtime-drift':runtime.write_bytes(b'CHANGED AFTER EXECUTION')
            return SimpleNamespace(returncode=code,stdout=stdout,stderr='',timed_out=timed,containment=contain)
        services=SimpleNamespace(checker=checker,verify=verify,extract=extract,snapshot_source=snapshot,
            spawn=spawn,authenticated_payloads=auth,platform='windows/amd64',profile=PROFILE)
        return cfg,services,counts

    def test_actual_checker_runs_once_and_all_four_original_cli_commands_are_recorded(self):
        for version in ('0.143.0','0.145.0'):
            with self.subTest(version=version):
                cfg,s,count=self.fixture(version=version);result=P._produce(cfg,s)
                self.assertEqual(count['checker'],1);self.assertEqual(count['verify'],1);self.assertEqual(count['spawn'],4)
                self.assertEqual(len(result['tests']),12)
                self.assertEqual(result['installed_binding']['profile'],'codex-cli-installed-cache-v1')
                self.assertTrue((cfg['output']/'observation.json').is_file())
                self.assertTrue((cfg['output']/'native-command-01.exit.json').is_file())
                self.assertFalse((cfg['workspace']/'codex-home').exists())

    def refusal(self,fault,reason):
        cfg,s,count=self.fixture(fault)
        with self.assertRaisesRegex(ValueError,reason):P._produce(cfg,s)
        self.assertFalse((cfg['output']/'observation.json').exists())
        self.assertTrue((cfg['output']/'failure.json').is_file())
        self.assertTrue((cfg['output']/'cleanup.json').is_file())
        self.assertFalse((cfg['workspace']/'codex-home').exists())
        return cfg,count

    def test_failed_cli_exit_is_persisted_before_refusal_and_has_no_success(self):
        cfg,count=self.refusal('failed-exit','CLI')
        result=json.loads((cfg['output']/'command-03.exit.json').read_bytes())
        self.assertEqual(result['exit_code'],9);self.assertEqual(count['checker'],1)

    def test_timeout_retains_containment_and_refuses_success(self):
        cfg,count=self.refusal('timeout','timed')
        result=json.loads((cfg['output']/'command-03.exit.json').read_bytes())
        self.assertTrue(result['timed_out']);self.assertEqual(result['containment'],'terminated')

    def test_runtime_or_selected_source_drift_refuse_after_actual_checker(self):
        self.refusal('runtime-drift','runtime');self.refusal('source-drift','source')

    def test_incomplete_cache_is_not_repaired_or_accepted(self):
        cfg,count=self.refusal('incomplete-cache','cache')
        self.assertEqual(count['checker'],1)

    def test_inactive_installed_native_is_an_actual_checker_failure(self):
        cfg,count=self.refusal('inactive-native','native|checker')
        report=json.loads((cfg['output']/'checker-result.json').read_bytes())
        case=next(r for r in report['results'] if r['code']=='CODEX-HOST-ARTIFACT-CAPABILITY')
        self.assertEqual(case['status'],'fail');self.assertEqual(count['checker'],1)

    def test_runtime_policy_is_independent_and_refuses_before_any_spawn(self):
        cfg,s,count=self.fixture();put(cfg['runtime_policy'],b'{}')
        with self.assertRaisesRegex(ValueError,'policy'):P._produce(cfg,s)
        self.assertEqual(count['spawn'],0);self.assertEqual(count['checker'],0)
        cfg,s,count=self.fixture();cfg['runtime_version']='0.146.0'
        with self.assertRaisesRegex(ValueError,'unsupported'):P._produce(cfg,s)
        self.assertEqual(count['spawn'],0);self.assertEqual(count['checker'],0)

    def test_unmatched_authenticated_payload_refuses_before_any_spawn(self):
        cfg,s,count=self.fixture();s.authenticated_payloads['packages']['members'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'payload'):P._produce(cfg,s)
        self.assertEqual(count['spawn'],0);self.assertEqual(count['checker'],0)

    def test_default_source_checker_keeps_ten_cases_without_native_or_member_optins(self):
        cfg,s,count=self.fixture();workspace=cfg['workspace']
        s.extract(cfg['package_root']/'codex.tar.gz',workspace/'package',host='codex')
        plugin=workspace/'package/plugins/ca-codex';home=workspace/'codex-home';home.mkdir()
        s.checker.REPO=workspace/'package';s.checker.MANIFEST=plugin/'.codex-plugin/plugin.json'
        s.checker.HOOKS_JSON=plugin/'hooks/hooks.json'
        s.checker._run=lambda argv,_home:s.spawn([str(cfg['runtime_executable']),*argv[1:]],timeout=300,env={},cwd=str(workspace))
        result=s.checker.check_install(home)
        self.assertEqual(count['checker'],1);self.assertEqual(count['spawn'],3)
        self.assertEqual(len(result),10);self.assertTrue(all(r['status']=='pass' for r in result))
        self.assertNotIn('CODEX-HOST-ARTIFACT-CAPABILITY',[r['code'] for r in result])

    def test_installed_parser_cannot_be_satisfied_by_preloaded_source_helper(self):
        cfg,s,count=self.fixture();old=sys.modules.get('_artifactmanifestlib')
        sys.modules['_artifactmanifestlib']=SimpleNamespace(validate_release_manifest=lambda *a:'source')
        try:
            result=P._produce(cfg,s)
            self.assertEqual(count['checker'],1);self.assertEqual(len(result['tests']),12)
            self.assertEqual(sys.modules['_artifactmanifestlib'].validate_release_manifest({}),'source')
        finally:
            if old is None:sys.modules.pop('_artifactmanifestlib',None)
            else:sys.modules['_artifactmanifestlib']=old

class PublicBootstrapTests(unittest.TestCase):
    fixture=ProducerTests.fixture
    COPY_FILES=(
      '.github/scripts/check_codex_host.py','.github/scripts/codex_agent_routes.py',
      '.github/scripts/_boundedproc.py','.github/scripts/observe_codex_installed_cli.py',
      '.github/scripts/_codex_cli_profile.py','.github/scripts/_releaselib.py',
      '.github/scripts/check_codex_skill_resources.py','.github/scripts/check_codex_static_package.py',
      'tools/build-host-packages.py','tools/host_descriptors.py','tools/owned_output.py',
      'tools/install-artifact-payload.py','core/pysrc/_releaselib.py',
      'core/pysrc/_artifactmanifestlib.py','core/pysrc/_gitexec.py','core/hosts.json')

    def public_fixture(self):
        cfg,s,count=self.fixture();source=cfg['source_root'];source.mkdir()
        selected=HERE.parents[1]
        for name in self.COPY_FILES:put(source/name,(selected/name).read_bytes())
        put(source/'core/surface/arbiter.md',(selected/'core/surface/arbiter.md').read_bytes())
        git=shutil.which('git')
        self.assertIsNotNone(git,'local Git is a required pure bootstrap test prerequisite')
        env=dict(os.environ);env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=str(source/'absent-config'))
        def run(*args):
            return subprocess.run([git,'-c','user.name=unit-fixture','-c','user.email=fixture@example.invalid',
                 '-c','core.hooksPath='+str(source/'absent-hooks'),*args],cwd=source,env=env,
                 capture_output=True,check=True).stdout
        run('init','-q');run('add','.');run('commit','-qm','inert source fixture')
        head=run('rev-parse','HEAD').decode().strip();tree=run('rev-parse','HEAD^{tree}').decode().strip()
        cfg['expected'].update(source_commit=head,source_tree=tree);cfg['git_executable']=Path(git).resolve()
        cohort=json.loads((cfg['package_root']/'artifact-package-cohort.json').read_bytes())
        cohort.update(source_commit=head,source_tree=tree);put(cfg['package_root']/'artifact-package-cohort.json',js(cohort))
        auth=s.authenticated_payloads['packages']
        auth['members']=[{'path':p.relative_to(cfg['package_root']).as_posix(),'sha256':sha(p.read_bytes())}
                         for p in sorted(cfg['package_root'].rglob('*')) if p.is_file()]
        system={'Windows':'windows','Linux':'linux','Darwin':'darwin'}[platform.system()]
        arch={'amd64':'amd64','x86_64':'amd64','arm64':'arm64','aarch64':'arm64'}[platform.machine().lower()]
        policy=json.loads(cfg['runtime_policy'].read_bytes());policy[cfg['runtime_version']]['platform']=system+'/'+arch
        put(cfg['runtime_policy'],js(policy));cfg['trusted_runtime_policy_sha256']=sha(cfg['runtime_policy'].read_bytes())
        cfg['workspace'].rmdir();cfg['output'].rmdir()
        fake_temp=source.parent/'unrelated-system-temp';fake_temp.mkdir()
        original_popen=subprocess.Popen;effects=[]
        class GitOnlyPopen(original_popen):
            def __init__(self,argv,*args,**kw):
                if Path(argv[0]).resolve()!=cfg['git_executable']:
                    effects.append(list(argv));raise AssertionError('upstream CLI/native effect boundary reached')
                super().__init__(argv,*args,**kw)
        return cfg,s.authenticated_payloads,fake_temp,GitOnlyPopen,effects

    def call_public(self,cfg,auth,fake_temp,popen):
        # Clear unrelated test-owner imports so only explicitly seeded prior
        # owner modules are under test; public produce still owns all loading.
        normal={'_boundedproc','codex_agent_routes','owned_output','host_descriptors','_artifactmanifestlib',
                '_releaselib','_codex_cli_profile','codex_installed_checker','codex_retained_packager'}
        saved={k:sys.modules.pop(k) for k in normal if k in sys.modules}
        try:
            with mock.patch.object(P.tempfile,'gettempdir',return_value=str(fake_temp)),mock.patch.object(subprocess,'Popen',popen):
                return P.produce(cfg,authenticated_payloads=auth)
        finally:
            for k in normal:sys.modules.pop(k,None)
            sys.modules.update(saved)

    def test_public_modified_release_shim_refuses_before_bootstrap_effects(self):
        cfg,auth,temp,popen,effects=self.public_fixture();marker=cfg['source_root'].parent/'shim-executed'
        shim=cfg['source_root']/'.github/scripts/_releaselib.py'
        shim.write_bytes(shim.read_bytes()+('\nopen('+repr(str(marker))+',"w").write("unexpected bootstrap")\n').encode())
        with self.assertRaisesRegex(ValueError,'source|immutable'):
            self.call_public(cfg,auth,temp,popen)
        self.assertFalse(marker.exists());self.assertEqual(effects,[])

    def test_public_unbound_private_cache_poison_refuses_before_effects(self):
        cfg,auth,temp,popen,effects=self.public_fixture();poison=ModuleType('_release_mechanism')
        old=sys.modules.get('_release_mechanism');sys.modules['_release_mechanism']=poison
        try:
            with self.assertRaisesRegex(ValueError,'preloaded|cached'):
                self.call_public(cfg,auth,temp,popen)
            self.assertIs(sys.modules['_release_mechanism'],poison);self.assertEqual(effects,[])
        finally:
            if old is None:sys.modules.pop('_release_mechanism',None)
            else:sys.modules['_release_mechanism']=old

    def test_public_surface_data_named_pycache_is_still_bound(self):
        cfg,auth,temp,popen,effects=self.public_fixture()
        put(cfg['source_root']/'core/surface/__pycache__/x.txt',b'{{IF:untracked-unknown-host}}\n')
        with self.assertRaisesRegex(ValueError,'membership'):
            self.call_public(cfg,auth,temp,popen)
        self.assertEqual(effects,[])

    def test_public_bound_private_cache_is_restored_after_actual_verifier_refusal(self):
        cfg,auth,temp,popen,effects=self.public_fixture();prior=ModuleType('_release_mechanism')
        prior.__file__=str(cfg['source_root']/'core/pysrc/_releaselib.py')
        prior.sentinel='caller-private-object';old=sys.modules.get('_release_mechanism')
        old_prefix=sys.pycache_prefix;sys.modules['_release_mechanism']=prior
        try:
            # The supplied cohort is deliberately not a real production format.
            # This is the real verifier's refusal, with no verifier/snapshot seam.
            with self.assertRaisesRegex(ValueError,'cohort'):
                self.call_public(cfg,auth,temp,popen)
            self.assertIs(sys.modules['_release_mechanism'],prior)
            self.assertEqual(prior.sentinel,'caller-private-object');self.assertEqual(effects,[])
            self.assertEqual(sys.pycache_prefix,old_prefix)
        finally:
            if old is None:sys.modules.pop('_release_mechanism',None)
            else:sys.modules['_release_mechanism']=old

if __name__=='__main__':unittest.main(verbosity=2)
