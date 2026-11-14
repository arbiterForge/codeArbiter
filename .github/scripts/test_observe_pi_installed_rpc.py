"""Synthetic closed-profile controls; no installed qualification or live execution."""
import copy
from contextlib import nullcontext
import hashlib
import importlib.util
import json
from pathlib import Path
import os
import sys
import tempfile
import shutil
import subprocess
from types import SimpleNamespace,ModuleType
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parent))

TEST_ID = "python:.github/scripts/test_pi_package.py:test_pi_package.PiPackageTests.test_real_isolated_rpc_command_discovery_and_keyed_status"


def fixture():
    sha=lambda value:hashlib.sha256(value).hexdigest()
    source,tree="a"*40,"b"*40
    req={"source_commit":source,"source_tree":tree,"ci_run_id":7}
    cohort={"source_commit":source,"source_tree":tree,"workflow":".github/workflows/ci.yml","run_id":"7",
        "promotion_receipt_sha256":"c"*64,"pi_packer":{"qualification":"production"},
        "packages":{"pi":{"file":"pi.tgz","sha256":"d"*64,"members":{"package/package.json":{"type":"file","size":2,"sha256":sha(b"{}")}}}}}
    text=json.dumps(cohort)
    payloads={"artifact-release-packages-"+source:{"artifact_id":11,"archive_sha256":"e"*64,"members":[{"path":"artifact-package-cohort.json","sha256":sha(text.encode())},{"path":"pi.tgz","sha256":"d"*64}]},
        "artifact-host-payloads-"+source:{"artifact_id":12,"archive_sha256":"f"*64,"members":[{"path":"artifact-promotion.json","sha256":"c"*64}]}}
    consumed={role:{"artifact_name":prefix+source,**payloads[prefix+source]} for role,prefix in [("release-packages","artifact-release-packages-"),("promoted-stage","artifact-host-payloads-")]}
    runtime={name:{"path":"C:/runtime/"+name,"sha256":"1"*64} for name in ["python","node","git","npm_launcher","npm_cli","npm_node"]}
    acq={"format":"codearbiter.pi-reviewed-acquisition/1",**req,"producer_job_id":9,"version":"1.5.0","prefix":"C:/owned/pi-host",
        "fresh_prefix":{"enumeration_succeeded":True,"present":False},"source_locks":{n:"2"*64 for n in ["package.json","package-lock.json",".npmrc","review.json"]},
        "command":{"argv":["C:/runtime/python","-I","-B","C:/repo/.github/scripts/pi_host_locks.py","install","--version","1.5.0","--prefix","C:/owned/pi-host"],"returncode":0,"timed_out":False,"containment":"exited"},
        "runtime_before":runtime,"runtime_after":copy.deepcopy(runtime),"graph_after":{"entries":{"package.json":{"kind":"file","bytes":2,"sha256":sha(b"{}")}},"sha256":"3"*64}}
    acq['graph_after']['sha256']=sha(json.dumps(acq['graph_after']['entries'],sort_keys=True,separators=(',',':')).encode())
    entries=cohort["packages"]["pi"]["members"]
    source_stamp={"source_commit":source,"source_tree":tree,"inputs":{"owner.py":"4"*64}}
    source_stamp['inputs'].update({'.github/fixtures/pi-hosts/1.5.0/'+n:v for n,v in acq['source_locks'].items()})
    worker={"format":"codearbiter.pi-installed-rpc-result/1","test":{"id":TEST_ID,"run_count":1,"failures":0,"errors":0,"skips":0,"result":"passed"},
        "routes":[{"name":n,"records":[{"id":"commands","success":True,"data":{"commands":[]}}],"settings":{"packages":["original-package"]}} for n in ["bare","alias","doctor"]],
        "doctor":{"format":"codearbiter-doctor-v1","report":"DEGRADED  active-dispatch: wrapper self-test does not exercise active dispatch.\nDEGRADED  author-delegation: unavailable (no-parent-ui)\ndoctor: DEGRADED"},
        "source_before":source_stamp,"source_after":copy.deepcopy(source_stamp),"runtime_before":runtime,"runtime_after":copy.deepcopy(runtime),
        "graph_before":acq["graph_after"],"graph_after":copy.deepcopy(acq["graph_after"]),
        "payload_before":{r:{m['path']:m['sha256'] for m in x['members']} for r,x in consumed.items()},
        "installed_before":entries,"installed_after":copy.deepcopy(entries)}
    worker["payload_after"]=copy.deepcopy(worker["payload_before"])
    b={"format":"codearbiter.installed-observation-binding/1","profile":"pi-installed-rpc-v1",**req,"producer_job_id":9,"workflow":".github/workflows/ci.yml","platform":"windows/amd64","runtime_version":"1.5.0",
        "consumed_payloads":consumed,"cohort_json":text,"acquisition":acq,"worker":worker,
        "supervision":{"argv":["C:/runtime/python","-I","-B","C:/repo/.github/scripts/observe_pi_installed_rpc.py","--worker","C:/owned/worker-config.json"],"returncode":0,"timed_out":False,"containment":"exited"},
        "cleanup":{"complete":True}}
    observation={"format":"codearbiter.major-test-observation/1",**req,"source_stable":True,"proof_kind":"live-host","producer":"pi-installed-rpc-observer-v1","argv":b['supervision']['argv'],"exit_code":0,"tests":[{"id":TEST_ID,"result":"passed"}],"installed_binding":b}
    return req,observation,payloads,acq


class ProfileTests(unittest.TestCase):
    def admit(self,mutate=None):
        import _pi_rpc_profile as owner
        req,o,p,a=fixture()
        if mutate:mutate(req,o,p,a)
        return owner.admit(o,req=req,job_id=9,authenticated_payloads=p,runtime_acquisition=a)

    def test_one_actual_method_and_one_actual_platform_cell_are_returned(self):
        value=self.admit()
        self.assertEqual(value['tests'],[{'id':TEST_ID,'result':'passed'}])
        self.assertEqual(value['installed_cells'],['installed:pi:windows:1.5.0'])
        self.assertEqual(value['payload_artifact_ids'],[11,12])

    def test_wrong_identity_profile_acquisition_or_second_payload_refuses(self):
        changes=[lambda q,o,p,a:o.update(producer='python-test-result-observer'),lambda q,o,p,a:o['installed_binding'].update(profile='unknown'),
            lambda q,o,p,a:o['installed_binding'].update(producer_job_id=8),lambda q,o,p,a:o['installed_binding'].update(runtime_version='1.0.2'),
            lambda q,o,p,a:o['installed_binding'].update(platform='unsupported'),lambda q,o,p,a:a['fresh_prefix'].update(present=True),
            lambda q,o,p,a:a['command'].update(returncode=1),lambda q,o,p,a:a['command'].update(timed_out=True),
            lambda q,o,p,a:next(reversed(p.values())).update(artifact_id=99)]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):self.admit(change)

    def test_failed_skipped_or_invented_test_doctor_overclaim_and_drift_refuse(self):
        changes=[lambda q,o,p,a:o['tests'].append({'id':'doctor invented test','result':'passed'}),
            lambda q,o,p,a:o['installed_binding']['worker']['test'].update(run_count=True),
            lambda q,o,p,a:o['installed_binding']['worker']['test'].update(skips=1),
            lambda q,o,p,a:o['installed_binding']['worker']['test'].update(failures=1),
            lambda q,o,p,a:o['installed_binding']['worker']['doctor'].update(report='doctor: HEALTHY'),
            lambda q,o,p,a:o['installed_binding']['worker']['source_after'].update(extra=True),
            lambda q,o,p,a:o['installed_binding']['worker']['installed_after'].clear(),
            lambda q,o,p,a:o['installed_binding']['supervision'].update(containment='unconfirmed'),
            lambda q,o,p,a:o['installed_binding']['cleanup'].update(complete=False)]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):self.admit(change)


class HarnessEnvironmentTests(unittest.TestCase):
    def test_actual_rpc_child_environment_disables_installed_python_bytecode_before_effect(self):
        import test_pi_package as owner
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            def refuse(argv,**kwargs):
                self.assertEqual(kwargs['env'].get('PYTHONDONTWRITEBYTECODE'),'1')
                self.assertNotIn('OPENAI_API_KEY',kwargs['env'])
                raise RuntimeError('no-effect-stop')
            with mock.patch.object(owner,'live_pi_cli',return_value=(sys.executable,root/'inert-cli.js')),mock.patch.object(owner.subprocess,'run',side_effect=refuse),self.assertRaisesRegex(RuntimeError,'no-effect-stop'):
                owner.run_rpc_commands(root,root/'agent',root/'home',package_source=root/'original')


class GraphTests(unittest.TestCase):
    def test_graph_captures_full_regular_members_and_declared_posix_bin_link(self):
        import observe_pi_installed_rpc as owner
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();package=root/'node_modules/sample';package.mkdir(parents=True)
            (package/'package.json').write_text(json.dumps({'name':'sample','bin':{'sample':'cli.js'}}));(package/'cli.js').write_bytes(b'// inert\n')
            before=owner.graph_snapshot(root)
            (root/'extra').write_bytes(b'addition')
            self.assertNotEqual(before,owner.graph_snapshot(root))
            if os.name!='nt':
                bins=root/'node_modules/.bin';bins.mkdir();(bins/'sample').symlink_to('../sample/cli.js')
                self.assertEqual(owner.graph_snapshot(root)['entries']['node_modules/.bin/sample']['kind'],'bin-link')

    def test_escaping_or_directory_link_refuses_without_following(self):
        import observe_pi_installed_rpc as owner
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();outside=root/'outside';outside.mkdir();graph=root/'graph';graph.mkdir();(graph/'file').write_bytes(b'one')
            link=graph/'linked'
            if os.name=='nt':
                import subprocess
                subprocess.run([os.environ.get('ComSpec','cmd.exe'),'/d','/c','mklink','/J',str(link),str(outside)],check=True,capture_output=True)
            else:link.symlink_to(outside,target_is_directory=True)
            try:
                with self.assertRaises(ValueError):owner.graph_snapshot(graph)
            finally:link.rmdir() if os.name=='nt' else link.unlink()


class OrchestrationTests(unittest.TestCase):
    def exercise(self,fault=None):
        import observe_pi_installed_rpc as owner
        import retained_archive_cli_observation as cold
        req,observed,payloads,_=fixture();binding=observed['installed_binding'];events=[]
        temporary=self.enterContext(tempfile.TemporaryDirectory());root=Path(temporary).resolve();repo=root/'repo';workspace=root/'workspace';output=root/'output'
        for p in [repo,workspace,output,root/'stage',root/'packages',root/'bin']:p.mkdir()
        script=repo/'.github/scripts';script.mkdir(parents=True)
        shutil.copyfile(Path(__file__).with_name('_pi_rpc_profile.py'),script/'_pi_rpc_profile.py')
        (root/'packages/artifact-package-cohort.json').write_text(binding['cohort_json'],encoding='utf8')
        (root/'stage/artifact-promotion.json').write_bytes(b'inert promotion')
        # Join the actual inert promotion bytes into synthetic cohort/metadata.
        doc=json.loads(binding['cohort_json']);doc['promotion_receipt_sha256']=owner.sha(b'inert promotion');text=json.dumps(doc)
        (root/'packages/artifact-package-cohort.json').write_text(text,encoding='utf8');binding['cohort_json']=text
        for name,payload in payloads.items():
            for member in payload['members']:
                if member['path']=='artifact-promotion.json':member['sha256']=doc['promotion_receipt_sha256']
                if member['path']=='artifact-package-cohort.json':member['sha256']=owner.sha(text.encode())
        runtime={}
        for name in ['python','node','git','npm_launcher','npm_cli','npm_node']:
            file=root/'bin'/({'npm_launcher':'npm.cmd' if os.name=='nt' else 'npm-cli.js','npm_cli':'node_modules/npm/bin/npm-cli.js' if os.name=='nt' else 'npm-cli.js','npm_node':'node.exe' if os.name=='nt' else 'node','node':'node.exe' if os.name=='nt' else 'node'}.get(name,name+'.exe'))
            file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'inert '+file.name.encode());runtime[name]=str(file)
            if os.name!='nt':file.chmod(0o755)
        if os.name!='nt':
            (root/'bin/npm').symlink_to('npm-cli.js');runtime['npm_launcher']=str(root/'bin/npm')
        locks=repo/'.github/fixtures/pi-hosts/1.5.0';locks.mkdir(parents=True)
        for name in owner.LOCK_NAMES:(locks/name).write_bytes(b'{}')
        stamp={'source_commit':req['source_commit'],'source_tree':req['source_tree'],'inputs':{'.github/fixtures/pi-hosts/1.5.0/'+n:owner.sha(b'{}') for n in owner.LOCK_NAMES}}
        config={**runtime,'repo':str(repo),'workspace':str(workspace),'output':str(output),'stage':str(root/'stage'),'packages':str(root/'packages'),'expected':{**req,'producer_job_id':9},'authenticated_payloads':payloads}
        maps={r:{m['path']:m['sha256'] for m in payloads[p+req['source_commit']]['members']} for r,p in [('promoted-stage','artifact-host-payloads-'),('release-packages','artifact-release-packages-')]}
        def verify(*args):
            events.append('production')
            if fault=='production':raise ValueError('production refusal')
        def spawn(argv,**kwargs):
            self.assertNotIn('GITHUB_TOKEN',kwargs['env']);self.assertNotIn('OPENAI_API_KEY',kwargs['env']);self.assertEqual(kwargs['timeout'],240)
            if argv[3].endswith('pi_host_locks.py'):
                events.append('install');prefix=Path(argv[-1]);self.assertFalse(prefix.exists());prefix.mkdir()
                for n in ['package.json','package-lock.json','.npmrc']:shutil.copyfile(locks/n,prefix/n)
                package=prefix/'node_modules/@earendil-works/pi-coding-agent';package.mkdir(parents=True)
                (package/'package.json').write_text(json.dumps({'name':'@earendil-works/pi-coding-agent','version':'1.5.0','bin':{'pi':'cli.js'}}));(package/'cli.js').write_bytes(b'inert')
                return SimpleNamespace(returncode=1 if fault=='install' else 0,timed_out=False,containment='exited',stdout='',stderr='PrivateFixtureValue' if fault=='install' else '')
            events.append('rpc');c=owner.load(argv[-1]);w=copy.deepcopy(binding['worker']);r=owner.runtime_snapshot(c);g=owner.graph_snapshot(Path(c['acquisition']['prefix']))
            w.update(source_before=copy.deepcopy(stamp),source_after=copy.deepcopy(stamp),runtime_before=r,runtime_after=copy.deepcopy(r),graph_before=g,graph_after=copy.deepcopy(g),payload_before=maps,payload_after=copy.deepcopy(maps))
            if fault=='drift':w['source_after']['inputs']['changed']='9'*64
            owner.save(output/'worker-result.json',w)
            return SimpleNamespace(returncode=0,timed_out=fault=='timeout',containment='terminated' if fault=='timeout' else 'exited',stdout='',stderr='')
        cleanup_failure=mock.patch.object(owner.shutil,'rmtree',side_effect=OSError('PrivateFixtureValue')) if fault=='cleanup' else nullcontext()
        with cleanup_failure,owner.process_environment(owner.environment(root/'unit-home',config)),mock.patch.object(owner,'source_snapshot',return_value=stamp),mock.patch.object(cold,'_verify_production',side_effect=verify),mock.patch.object(cold,'physical_members',side_effect=lambda p:{'members':maps['promoted-stage' if str(p)==config['stage'] else 'release-packages']}),mock.patch.object(owner,'actual_platform',return_value='windows/amd64'):
            if fault:
                with self.assertRaises(ValueError):owner._produce(config,cold,spawn)
                result=None
            else:result=owner._produce(config,cold,spawn)
        self.assertFalse((output/'observation.json').exists(),'public bootstrap alone emits after restoration')
        for p in output.glob('*.json'):self.assertNotIn('PrivateFixtureValue',p.read_text())
        return result,events,output

    def test_existing_installer_and_original_worker_each_run_once_after_production_admission(self):
        observed,events,out=self.exercise()
        self.assertEqual(events,['production','install','rpc']);self.assertEqual(len(observed['tests']),1)
        self.assertTrue((out/'install-exit.json').is_file());self.assertTrue((out/'worker-exit.json').is_file());self.assertEqual(json.loads((out/'cleanup.json').read_bytes()),{'complete':True})

    def test_production_refusal_prevents_runtime_or_rpc_effects(self):
        _,events,_=self.exercise('production');self.assertEqual(events,['production'])

    def test_failed_install_is_recorded_before_refusal_and_rpc_does_not_run(self):
        _,events,out=self.exercise('install');self.assertEqual(events,['production','install']);self.assertEqual(json.loads((out/'install-exit.json').read_bytes())['returncode'],1)

    def test_worker_timeout_and_drift_retain_completion_and_never_emit_success(self):
        for fault in ['timeout','drift']:
            with self.subTest(fault=fault):
                _,events,out=self.exercise(fault);self.assertEqual(events,['production','install','rpc']);self.assertTrue((out/'worker-exit.json').is_file())

    def test_cleanup_unknown_retains_completion_and_cannot_emit(self):
        _,events,out=self.exercise('cleanup')
        self.assertEqual(events,['production','install','rpc'])
        self.assertEqual(json.loads((out/'worker-exit.json').read_bytes())['returncode'],0)
        self.assertIs(json.loads((out/'cleanup.json').read_bytes())['complete'],False)


class PublicBootstrapTests(unittest.TestCase):
    # Parent fixture imports must not dirty the exact source under inspection.
    @mock.patch.object(sys, 'dont_write_bytecode', True)
    def call_public(self,mode):
        import observe_pi_installed_rpc as producer
        selected=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();repo=root/'repo';repo.mkdir()
            for folder in ['.github/scripts','core/pysrc','tools']:
                for path in (selected/folder).glob('*.py'):
                    target=repo/folder/path.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
            (repo/'core/surface').mkdir();shutil.copyfile(selected/'core/hosts.json',repo/'core/hosts.json');(repo/'core/surface/inert.md').write_text('# inert\n')
            shutil.copytree(selected/'.github/fixtures/pi-hosts/1.5.0',repo/'.github/fixtures/pi-hosts/1.5.0')
            git=shutil.which('git');self.assertIsNotNone(git)
            def run(*args):return subprocess.run([git,'-C',str(repo),'-c','core.hooksPath='+str(root/'no-hooks'),'-c','user.name=fixture','-c','user.email=fixture@example.invalid',*args],capture_output=True,check=True).stdout.decode().strip()
            run('init','-q');run('config','core.autocrlf','false');run('add','.');run('commit','-qm','inert fixture');source=run('rev-parse','HEAD');tree=run('rev-parse','HEAD^{tree}')
            marker=root/'must-not-execute';shim=repo/'.github/scripts/_releaselib.py'
            if mode=='shim':shim.write_bytes(shim.read_bytes()+('\nopen('+repr(str(marker))+',"w").write("unexpected")\n').encode())
            spec=importlib.util.spec_from_file_location('pi_public_fixture',repo/'.github/scripts/observe_pi_installed_rpc.py');owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
            config={'repo':repo,'workspace':root/'workspace','output':root/'output','expected':{'source_commit':source,'source_tree':tree,'ci_run_id':7,'producer_job_id':9},'git':git,'python':sys.executable,'node':sys.executable,'npm_launcher':Path(sys.executable).parent/'npm.cmd','npm_cli':root/'npm-cli.js','npm_node':sys.executable,'stage':root/'stage','packages':root/'packages'}
            popen=subprocess.Popen;effects=[]
            class GitOnly(popen):
                def __init__(self,argv,*args,**kwargs):
                    actual=Path(argv[0]) if Path(argv[0]).is_absolute() else Path(shutil.which(argv[0],path=kwargs.get('env',os.environ).get('PATH')) or '')
                    if actual.resolve()!=Path(git).resolve():effects.append(list(argv));raise AssertionError('non-Git effect reached')
                    super().__init__(argv,*args,**kwargs)
            poison=ModuleType('_release_mechanism');prior=sys.modules.get('_release_mechanism')
            try:
                if mode=='cache':sys.modules['_release_mechanism']=poison
                if mode=='verifier':
                    req,_,payloads,_=fixture();req.update(source_commit=source,source_tree=tree)
                    packages=root/'packages';stage=root/'stage';packages.mkdir();stage.mkdir()
                    # Deliberately malformed production cohort, actual verifier refuses.
                    (packages/'artifact-package-cohort.json').write_text('{}');(stage/'artifact-promotion.json').write_text('{}')
                    auth={}
                    for role,prefix,folder in [('release-packages','artifact-release-packages-',packages),('promoted-stage','artifact-host-payloads-',stage)]:
                        auth[prefix+source]={'artifact_id':11 if role=='release-packages' else 12,'archive_sha256':'e'*64,'members':[{'path':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in folder.iterdir()]}
                else:auth={}
                with mock.patch.object(subprocess,'Popen',GitOnly),self.assertRaises(ValueError) as caught:owner.produce(config,authenticated_payloads=auth)
                if mode=='cache':self.assertIs(sys.modules['_release_mechanism'],poison)
                self.assertFalse(marker.exists());self.assertEqual(effects,[]);self.assertFalse((root/'output/observation.json').exists())
                return str(caught.exception)
            finally:
                if prior is None:sys.modules.pop('_release_mechanism',None)
                else:sys.modules['_release_mechanism']=prior

    def test_changed_physical_source_shim_refuses_before_any_non_git_process(self):
        self.assertIn('source',self.call_public('shim'))

    def test_foreign_private_cached_mechanism_refuses_and_restores_before_effects(self):
        self.assertIn('cached',self.call_public('cache'))

    def test_bound_public_source_reaches_actual_production_verifier_refusal_without_effects(self):
        self.assertIn('cohort',self.call_public('verifier'))



if __name__=='__main__':unittest.main(verbosity=2)
