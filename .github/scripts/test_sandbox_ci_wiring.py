"""Pure installed-Sandbox wiring controls; no Docker/npm/API execution."""
import copy,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import major_qualification_report as reports
import test_observe_sandbox_installed_docker as fixtures

JOB="[CHECK] | [SBX ] | Installed shipped bundle <docker>"
class WiringContracts(unittest.TestCase):
    def fixture(self,root):
        expected,observed,payloads=fixtures.fixture(root)
        req={k:expected[k] for k in ('source_commit','source_tree','ci_run_id')}
        req.update(cells=['installed:sandbox:docker'],cell_jobs={'installed:sandbox:docker':JOB})
        job={'id':23,'name':JOB,'run_id':17,'run_attempt':1,'status':'in_progress'}
        selections={'schema':reports.SELECTIONS,'groups':[{'id':'sandbox-live','job':JOB,'payload_name':'artifact-sandbox-plugin-{source_commit}-{run_attempt}','observation':'sandbox-live','proof_kind':'live-host','selectors':[r['id'] for r in observed['tests']],'cells':['installed:sandbox:docker'],'scope':'Three real shipped CLI cases only.'}]}
        admitted={'tests':observed['tests'],'payload_artifact_ids':[71],'payloads':list(payloads.values()),'primary_payload_name':next(iter(payloads)),'installed_cells':['installed:sandbox:docker']}
        return req,job,selections,observed,payloads,admitted
    def test_closed_sandbox_dispatch_can_transport_one_original_artifact(self):
        import types
        with tempfile.TemporaryDirectory() as raw:
            req,job,selections,observed,payloads,admitted=self.fixture(Path(raw))
            module=types.ModuleType('sandbox_live_report_profile');module.admit=mock.Mock(return_value=admitted)
            with mock.patch.dict(sys.modules,{'sandbox_live_report_profile':module}):
                result=reports.build_report(req,job_name=JOB,job_id=23,selections=selections,observations={'sandbox-live':observed},payloads=payloads,producer_job=job,runtime_acquisitions={'sandbox-live':{'unit':'receipt'}})
            self.assertEqual(result['schema'],'codearbiter-major-qualification/3')
            self.assertEqual(result['results'][0]['payload_artifact_ids'],[71])
            self.assertEqual(len(result['payloads']),1)
            self.assertEqual(module.admit.call_count,1)
            self.assertEqual(module.admit.call_args.kwargs['runtime_acquisition'],{'unit':'receipt'})
    def test_artifact_attempt_comes_from_actual_owning_job_not_observation(self):
        with tempfile.TemporaryDirectory() as raw:
            req,job,selections,observed,payloads,admitted=self.fixture(Path(raw))
            for bad in [None,{**job,'id':24},{**job,'name':'other'},{**job,'run_id':18},{**job,'run_attempt':True},{**job,'status':'completed'}]:
                with self.subTest(job=bad),self.assertRaises(ValueError):
                    reports.build_report(req,job_name=JOB,job_id=23,selections=selections,observations={'sandbox-live':observed},payloads=payloads,producer_job=bad)

class CoordinatorContracts(unittest.TestCase):
    def fixture(self):
        import coordinate_sandbox_installed as c
        req={'source_commit':'a'*40,'source_tree':'b'*40,'ci_run_id':17,'cell_jobs':{'installed:sandbox:docker':JOB}}
        env={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'arbiterForge/codeArbiter','GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/major/state-contracts','GITHUB_RUN_ATTEMPT':'2'}
        job={'id':23,'name':JOB,'run_id':17,'run_attempt':2,'status':'in_progress','steps':[{'name':c.UPLOAD_STEP,'status':'completed','conclusion':'success','started_at':'2026-11-14T10:00:00Z','completed_at':'2026-11-14T10:01:00Z'}]}
        artifact={'id':71,'name':c.PREFIX+'a'*40+'-2','digest':'sha256:'+'c'*64,'created_at':'2026-11-14T10:00:30Z'}
        return c,req,env,job,artifact
    def test_only_trusted_marked_normal_push_runs_the_installed_coordinator(self):
        c,req,env,job,a=self.fixture()
        self.assertTrue(c.program_mode(env,True))
        self.assertTrue(c.program_mode({**env,'GITHUB_REF':'refs/heads/main'},True))
        self.assertFalse(c.program_mode(env,False))
        for key,value in [('GITHUB_EVENT_NAME','pull_request'),('GITHUB_REPOSITORY','fork/repo'),('GITHUB_REF','refs/heads/other'),('GITHUB_ACTIONS','false')]:
            self.assertFalse(c.program_mode({**env,key:value},True))
    def test_actual_job_attempt_is_not_a_caller_pass_flag(self):
        c,req,env,job,a=self.fixture();run={'run_attempt':2,'head_branch':'major/state-contracts'}
        self.assertEqual(c.select_job(req,run,[job],env),job)
        for jobs in [[],[job,job],[{**job,'run_attempt':1}],[{**job,'id':True}],[{**job,'status':'completed'}],[{**job,'run_id':18}]]:
            with self.subTest(jobs=jobs),self.assertRaises(ValueError):c.select_job(req,run,jobs,env)
    def test_same_job_upload_requires_action_outputs_exact_name_digest_and_successful_window(self):
        c,req,env,job,a=self.fixture()
        def check(j,value):return c.validate_early_upload(j,value,source='a'*40,attempt=2,upload_id=71,upload_digest='c'*64)
        check(job,a)
        for mutation in [{'id':72},{'name':c.PREFIX+'a'*40+'-1'},{'digest':'sha256:'+'d'*64},{'created_at':'2026-11-14T09:59:59Z'},{'created_at':'malformed'}]:
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):check(job,{**a,**mutation})
        for key,value in [('status','in_progress'),('conclusion','failure'),('name','other')]:
            bad=copy.deepcopy(job);bad['steps'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):check(bad,a)
    def test_failed_actual_control_admission_prevents_the_original_test_without_fallback(self):
        import coordinate_sandbox_installed as c
        from contextlib import nullcontext
        from types import ModuleType,SimpleNamespace
        c0,req,env,job,artifact=self.fixture()
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);output=root/'out';output.mkdir()
            producer=SimpleNamespace(control_environment=lambda *_a,**_k:nullcontext(),project_modules=lambda *_:nullcontext(),produce=mock.Mock())
            ready=ModuleType('major_readiness');ready.candidate_marker=mock.Mock();ready.blob=mock.Mock(return_value=b'{}')
            ready.collect=mock.Mock(return_value=(req,{'run_attempt':2,'head_branch':'major/state-contracts'},[{**artifact,'id':72}],[job]))
            report=ModuleType('major_qualification_report');report.validate_emitter_environment=mock.Mock();report.authenticated_payload=mock.Mock()
            args=SimpleNamespace(repo=root,payload_root=root/'payload',output_root=output,artifact_id=71,artifact_digest='c'*64)
            with mock.patch.dict(os.environ,{**env,'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'17'},clear=True),mock.patch.dict(sys.modules,{'major_readiness':ready,'major_qualification_report':report}),self.assertRaisesRegex(ValueError,'upload action identity'):
                c._run(args,producer,root/'private',{'phase':'authentication'})
            producer.produce.assert_not_called();report.authenticated_payload.assert_not_called()

    def test_public_bootstrap_refuses_mutable_source_before_module_effect(self):
        import coordinate_sandbox_installed as c
        import subprocess,shutil
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve();script=root/'.github/scripts/retained_archive_cli_observation.py';script.parent.mkdir(parents=True)
            script.write_text("INERT = True\n");marker=root/'.github/integration-candidate.json';marker.write_text('{}')
            git=shutil.which('git');self.assertIsNotNone(git)
            env={k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','HOME','USERPROFILE')}
            env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0')
            def run(*args):return subprocess.check_output([git,'-C',str(root),*args],env=env,stderr=subprocess.DEVNULL,timeout=10)
            run('init','-q');run('add','.');run('-c','user.name=Inert Unit','-c','user.email=unit@example.invalid','commit','-qm','inert fixture')
            source=run('rev-parse','HEAD').decode().strip();script.write_text("raise AssertionError('must not execute')\n")
            dispatch={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'arbiterForge/codeArbiter','GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/major/state-contracts','GITHUB_SHA':source,'GITHUB_RUN_ATTEMPT':'1'}
            with mock.patch.dict(os.environ,dispatch),self.assertRaisesRegex(ValueError,'bootstrap source differs'):
                c.main(['stage','--repo',str(root),'--payload-root',str(root/'payload')])
            self.assertFalse((root/'payload').exists());self.assertNotIn('sandbox_control_owner',sys.modules)


class AdapterContracts(unittest.TestCase):
    def test_actual_closed_profile_requires_independent_receipt_and_exact_source(self):
        import sandbox_live_report_profile as a
        with tempfile.TemporaryDirectory() as raw:
            expected,observed,payloads=fixtures.fixture(Path(raw));binding=observed['installed_binding']
            req={k:expected[k] for k in ('source_commit','source_tree','ci_run_id')}
            job={'id':23,'name':JOB,'run_id':17,'status':'in_progress','run_attempt':1};receipt=json.loads(binding['runtime_before']['nixpacks_acquisition']['document_utf8'])
            def admit(value=observed,acquisition=receipt):return a.admit(value,req=req,job_id=23,authenticated_payloads=payloads,repo=Path(raw),producer_job=job,runtime_acquisition=acquisition)
            with mock.patch.object(a.producer,'source_snapshot',return_value=binding['source_before']):
                result=admit();self.assertEqual(result['installed_cells'],['installed:sandbox:docker']);self.assertEqual(result['payload_artifact_ids'],[71])
                for bad in [None,{**receipt,'binary_sha256':'f'*64}]:
                    with self.subTest(receipt=bad),self.assertRaises(ValueError):admit(acquisition=bad)
                bad=copy.deepcopy(observed);bad['installed_binding']['payload']['artifact_id']=72
                with self.assertRaises(ValueError):admit(value=bad)
                bad=copy.deepcopy(observed);bad['tests'][0]['result']='skipped'
                with self.assertRaises(ValueError):admit(value=bad)
            with mock.patch.object(a.producer,'source_snapshot',return_value={'changed':'source'}),self.assertRaises(ValueError):admit()
    def test_wrong_profile_or_attempt_never_labels_source_tests_installed(self):
        import sandbox_live_report_profile as a
        with tempfile.TemporaryDirectory() as raw:
            expected,observed,payloads=fixtures.fixture(Path(raw));req={k:expected[k] for k in ('source_commit','source_tree','ci_run_id')}
            for key,value in [('producer','vitest-json-observer'),('proof_kind','source-test')]:
                bad=copy.deepcopy(observed);bad[key]=value
                with self.assertRaises(ValueError):a.admit(bad,req=req,job_id=23,authenticated_payloads=payloads,repo=Path(raw),producer_job={'id':23,'name':JOB,'run_id':17,'status':'in_progress','run_attempt':1},runtime_acquisition={})
            with self.assertRaises(ValueError):a.admit(observed,req=req,job_id=23,authenticated_payloads=payloads,repo=Path(raw),producer_job={'id':23,'name':JOB,'run_id':17,'status':'in_progress','run_attempt':2},runtime_acquisition={})

class SourceContracts(unittest.TestCase):
    def assert_source_image_prerequisite(self, source, image):
        import re
        steps=re.split(r'(?m)^      - ',source)
        pulls=[step for step in steps if re.search(
            r'(?m)^        run: docker pull '+re.escape(image)+r'\s*$',step)]
        self.assertEqual(len(pulls),1,'Required source job must pull the existing exact bundle image once')
        pull=pulls[0]
        self.assertNotRegex(pull,r'(?m)^        (?:if|continue-on-error):',
                            'Required source image acquisition must fail closed')
        self.assertLess(source.index('Docker preflight (REQUIRED prerequisite'),source.index(pull))
        self.assertLess(source.index(pull),source.index('acquire_nixpacks.py'))
        original='run: npm test -- --reporter=default --reporter=github-actions --reporter=json'
        self.assertEqual(source.count(original),1)
        self.assertLess(source.index(pull),source.index(original))
        return '      - '+pull

    def source_image_inputs(self):
        import re
        from test_ci_impact import workflow_jobs
        from _sandbox_docker_profile import IMAGE
        root=HERE.parents[1]
        build=(root/'plugins/ca-sandbox/tools/build.ts').read_text(encoding='utf8')
        pin=re.search(r'export const FALLBACK_BASE_IMAGE\s*=\s*"([^"]+)"',build)
        self.assertIsNotNone(pin)
        self.assertEqual(pin.group(1),IMAGE)
        workflow=(root/'.github/workflows/ci.yml').read_text(encoding='utf8')
        return workflow_jobs(workflow)['ca-sandbox-tools'],IMAGE

    def test_source_job_requires_existing_pinned_bundle_image_before_original_suite(self):
        source,image=self.source_image_inputs()
        self.assert_source_image_prerequisite(source,image)

    def test_source_image_prerequisite_rejects_missing_wrong_late_or_optional_pull(self):
        source,image=self.source_image_inputs()
        pull=self.assert_source_image_prerequisite(source,image)
        mutations={
            'missing':source.replace(pull,'',1),
            'wrong-pin':source.replace('docker pull '+image,'docker pull node:20-slim@sha256:'+'0'*64,1),
            'late':source.replace(pull,'',1)+pull,
            'optional':source.replace(pull,pull.replace('        run:',"        if: false\n        run:",1),1),
            'ignored-failure':source.replace(pull,pull.replace('        run:',"        continue-on-error: true\n        run:",1),1),
        }
        for name,changed in mutations.items():
            with self.subTest(mutation=name),self.assertRaises(AssertionError):
                self.assert_source_image_prerequisite(changed,image)

    def test_required_source_lane_remains_and_new_job_is_trusted_readonly_single_run(self):
        from test_ci_impact import workflow_jobs,paths_filter,aggregate_required_results
        root=HERE.parents[1];text=(root/'.github/workflows/ci.yml').read_text(encoding='utf8');jobs=workflow_jobs(text)
        source=jobs['ca-sandbox-tools'];installed=jobs['sandbox-installed-package']
        self.assertIn('npm test -- --reporter=default --reporter=github-actions --reporter=json',source)
        self.assertIn('Assert every real-container layer executed',source)
        self.assertIn('python3 -B .github/scripts/test_sandbox_ci_wiring.py',source)
        self.assertNotIn('sandbox-installed-package',aggregate_required_results(text))
        self.assertNotIn('continue-on-error:',installed);self.assertIn("github.event_name == 'push'",installed)
        self.assertIn("github.ref == 'refs/heads/major/state-contracts'",installed)
        self.assertIn('persist-credentials: false',installed);self.assertIn('actions: read',installed);self.assertIn('contents: read',installed)
        self.assertIn('artifact-sandbox-plugin-${{ github.sha }}-${{ github.run_attempt }}',installed)
        self.assertIn('include-hidden-files: true',installed);self.assertIn('if-no-files-found: error',installed)
        self.assertEqual(installed.count('coordinate_sandbox_installed.py observe'),1)
        self.assertEqual(installed.count('acquire_nixpacks.py'),1)
        self.assertNotIn('npm test',installed)
        self.assertNotIn('CA_SANDBOX_DOCKER_SENTINEL:',installed)  # producer owns its private sentinel
        self.assertIn('docker pull node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0',installed)
        for name in ['coordinate_sandbox_installed.py','sandbox_live_report_profile.py','test_sandbox_ci_wiring.py','observe_sandbox_installed_docker.py','_sandbox_docker_profile.py','test_observe_sandbox_installed_docker.py','major_qualification_report.py','acquire_nixpacks.py']:
            self.assertIn('.github/scripts/'+name,paths_filter(text,'ca-sandbox'))
    def test_policy_selection_targets_only_one_sandbox_cell_and_three_original_names(self):
        root=HERE.parents[1];policy=json.loads((root/'.github/major-qualification-policy.json').read_bytes());selections=json.loads((root/'.github/major-test-selections.json').read_bytes())
        self.assertEqual(policy['cell_job_bindings']['installed:sandbox:docker'],JOB)
        group=[g for g in selections['groups'] if g['id']=='sandbox-installed-docker'];self.assertEqual(len(group),1)
        self.assertEqual(group[0]['cells'],['installed:sandbox:docker']);self.assertEqual(group[0]['selectors'],['vitest:plugins/ca-sandbox/tools/installed-bundle.test.ts:'+name for name in fixtures.NAMES])
        self.assertEqual(group[0]['payload_name'],'artifact-sandbox-plugin-{source_commit}-{run_attempt}')

if __name__=='__main__':unittest.main()
