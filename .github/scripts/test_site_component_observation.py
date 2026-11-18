"""Offline component capture/admission controls; no browser or npm execution."""
import copy
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile
import site_component_observation as c

ROOT = Path(__file__).resolve().parents[2]
CELLS = {'disposition:machines:S55', 'disposition:findings:SF11'} | {
    'disposition:transitions:S55:' + str(i).zfill(2) for i in range(1, 12)}


class ComponentCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ca-component-control-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.req = {'source_commit':'a'*40, 'source_tree':'b'*40, 'ci_run_id':7,
                    'cells':sorted(CELLS), 'cell_jobs':dict.fromkeys(CELLS, c.JOB)}
        self.run = {'id':17, 'head_sha':'a'*40, 'head_branch':'main', 'event':'push',
                    'status':'completed', 'conclusion':'success', 'run_attempt':1, 'path':c.browser.WORKFLOW,
                    'repository':{'id':8,'full_name':c.owner.REPOSITORY},
                    'head_repository':{'id':8,'full_name':c.owner.REPOSITORY}}
        self.job = {'id':29, 'run_id':17, 'run_attempt':1, 'name':c.JOB,
                    'status':'completed', 'conclusion':'success', 'steps':[
                        {'name':name, 'status':'completed', 'conclusion':'success',
                         'started_at':'2026-11-18T00:00:00Z', 'completed_at':'2026-11-18T00:01:00Z'}
                        for name in (c.UPLOAD,c.REPORT_STEP)]}
        self.values = {'site/src/components/Search.astro':b'owned source\n', c.CONFIG:b'owned config\n'}
        self.inputs = {p:{'bytes':len(v),'sha256':c.owner.digest(v)} for p,v in self.values.items()}
        self.namespaces = {'core/pysrc':['_owned.py'], '.github/scripts':['owned.py']}
        self.state = {'source_commit':'a'*40,'source_tree':'b'*40,'clean':True,
                      'inputs':self.inputs,'python_namespaces':self.namespaces}
        self.manifest = c.manifest_document(self.state)
        self.manifest_raw = json.dumps(self.manifest).encode()
        self.source_zip = self.archive({**self.values,c.MANIFEST:self.manifest_raw})
        self.observed = {'format':c.OBSERVATION,'profile':c.PROFILE,**self.state,'run_id':17,'run_attempt':1,
                         'argv':c.ARGV,'cwd':'site','exit_code':0,
                         'tools':{k:{'sha256':'c'*64,'size':1} for k in ('node','npm','chrome')},
                         'source_manifest_sha256':c.owner.digest(self.manifest_raw),
                         'tests':[{'name':s,'result':'PASSED'} for s in sorted(c.SELECTORS)]}
        self.refresh()

    @staticmethod
    def archive(values):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as zipped:
            for p,v in values.items(): zipped.writestr(p,v)
        return out.getvalue()

    def metadata(self, identity, name, raw):
        return {'id':identity,'name':name,'expired':False,'size_in_bytes':len(raw),
                'digest':'sha256:'+c.owner.digest(raw),'created_at':'2026-11-18T00:00:30Z',
                'workflow_run':{'id':17,'head_sha':'a'*40,'head_branch':'main',
                                'repository_id':8,'head_repository_id':8}}

    def refresh(self):
        self.report = {'schema':c.REPORT,'source_commit':'a'*40,'source_tree':'b'*40,
                       'docs_run_id':17,'run_attempt':1,'job_id':29,'source_artifact_id':31,
                       'source_archive_sha256':c.owner.digest(self.source_zip),'observation':self.observed,
                       'results':[{'cell':cell,'result':'PASSED','selectors':c.RECIPES[cell]} for cell in sorted(CELLS)]}
        report_zip = self.archive({c.REPORT_FILE:json.dumps(self.report).encode()})
        self.artifacts = [self.metadata(31,c.PAYLOAD,self.source_zip),
                          self.metadata(32,'major-docs-component-qualification-29',report_zip)]
        self.data = {31:self.source_zip,32:report_zip}

    def api(self, path, binary=False):
        if path.startswith('actions/workflows/docs.yml/runs?'):
            return {'total_count':1,'workflow_runs':[self.run]}
        if path == 'actions/runs/17': return self.run
        if path == 'actions/runs/17/jobs?filter=latest&per_page=100':
            return {'total_count':1,'jobs':[self.job]}
        if path == 'actions/runs/17/artifacts?per_page=100':
            return {'total_count':len(self.artifacts),'artifacts':self.artifacts}
        if path.startswith('actions/artifacts/') and binary:
            return self.data[int(path.split('/')[2])]
        if path == 'actions/jobs/29/logs' and binary:
            return '\n'.join('2026-11-18T00:00:30Z '+line for a in self.artifacts for line in (
                '##[group]Run '+c.owner.UPLOAD_ACTION,
                'SHA256 digest of uploaded artifact is '+a['digest'][7:],
                f"Artifact {a['name']} successfully finalized. Artifact ID {a['id']}"
            )).encode()
        raise AssertionError('unexpected inert API path')

    @contextlib.contextmanager
    def transport(self):
        with mock.patch.object(c.owner,'api',side_effect=self.api), \
             mock.patch.object(c,'expected_inputs',return_value=self.inputs), \
             mock.patch.object(c.source,'namespace_members',return_value=self.namespaces):
            yield

    def raw_report(self):
        suites=[]
        for path in dict(c.CASES):
            specs=[]
            for i,(file,title) in enumerate(c.CASES):
                if file != path: continue
                specs.append({'title':title,'file':file,'ok':True,'id':str(i),
                    'tests':[{'projectName':'','projectId':'','expectedStatus':'passed','status':'expected',
                              'annotations':[],'results':[{'status':'passed','retry':0,'errors':[],'duration':1}]}]})
            suites.append({'title':path,'file':path,'specs':specs})
        return {'config':{'workers':1,'forbidOnly':False,'projects':[{'name':'','id':'','retries':0,
                    'repeatEach':1,'timeout':10000}]},'errors':[],'suites':suites,
                'stats':{'expected':16,'unexpected':0,'flaky':0,'skipped':0}}

    def test_declared_component_route_is_complete_and_separate_from_pages(self):
        document = json.loads((ROOT / '.github/major-test-selections.json').read_text())
        groups = [g for g in document['groups'] if g['observation'] == 'docs-original-component-browser']
        self.assertEqual({c for g in groups for c in g['cells']}, CELLS)
        self.assertEqual(len(groups), 13)
        self.assertTrue(all(g['proof_kind'] == 'source-test'
                            and g['payload_name'] == 'major-source-inputs-site-components'
                            and g['job'] == 'Site | [Build] - Astro Pages' for g in groups))

    def test_actual_component_shape_is_distinct_from_pages_and_complete(self):
        self.assertEqual(c.parse_playwright(self.raw_report()),self.observed['tests'])
        with self.assertRaises(c.owner.ReadinessError): c.browser.parse_playwright(self.raw_report())
        document=json.loads((ROOT/'.github/major-test-selections.json').read_text())
        c.validate_selection_map(document)
        c.browser.validate_selection_map(document)
        legacy=copy.deepcopy(document)
        legacy['groups']=[g for g in legacy['groups'] if g['observation']!=c.ROLE]
        c.browser.validate_selection_map(legacy)

    def test_parser_refuses_each_missing_case_and_nonaffirmative_outcome(self):
        for index in range(16):
            raw=self.raw_report()
            for suite in raw['suites']:
                suite['specs']=[s for s in suite['specs'] if s['id']!=str(index)]
            raw['stats']['expected']-=1
            with self.subTest(missing=index),self.assertRaises(c.owner.ReadinessError): c.parse_playwright(raw)
        for change in ('skipped','failed','flaky','retry','duplicate','foreign-file','wrong-project','global-error'):
            raw=self.raw_report(); spec=raw['suites'][0]['specs'][0]; test=spec['tests'][0]
            if change in ('skipped','failed'): test['results'][0]['status']=change
            elif change=='flaky': test['status']='flaky'
            elif change=='retry': test['results'][0]['retry']=1
            elif change=='duplicate': raw['suites'][0]['specs'].append(copy.deepcopy(spec))
            elif change=='foreign-file': spec['file']='../browser/publication.spec.ts'
            elif change=='wrong-project': test['projectName']='chrome'
            else: raw['errors']=[{'message':'inert'}]
            with self.subTest(change=change),self.assertRaises(c.owner.ReadinessError): c.parse_playwright(raw)

    def test_capture_runs_original_once_and_records_prepared_source(self):
        repo=self.root/'repo'; (repo/'site').mkdir(parents=True)
        payload=self.root/'payload';payload.mkdir();(payload/c.MANIFEST).write_bytes(self.manifest_raw)
        output=self.root/'observed.json'
        def original(argv,**kwargs):
            self.assertEqual(argv,['selected-npm','run','test:components'])
            self.assertEqual(kwargs['cwd'],repo/'site')
            Path(kwargs['env']['CA_COMPONENT_PLAYWRIGHT_JSON']).write_text(json.dumps(self.raw_report()))
            return SimpleNamespace(returncode=0)
        with mock.patch.dict(os.environ,{'GITHUB_RUN_ID':'17','GITHUB_RUN_ATTEMPT':'1'},clear=True), \
             mock.patch.object(c,'snapshot',return_value=self.state), \
             mock.patch.object(c.shutil,'which',side_effect=['selected-node','selected-npm']), \
             mock.patch.object(c.browser,'tool_identity',return_value={'sha256':'c'*64,'size':1}), \
             mock.patch.object(c.subprocess,'run',side_effect=original) as invoked:
            self.assertEqual(c.observe(repo,payload,output,browser_binary='selected-chrome'),0)
        invoked.assert_called_once()
        self.assertEqual(json.loads(output.read_text()),self.observed)

    def test_capture_refuses_credentials_old_source_and_failed_original(self):
        with mock.patch.dict(os.environ,dict.fromkeys(('GH_TOKEN',), 'test'), clear=True), \
             mock.patch.object(c.subprocess,'run') as invoked:
            with self.assertRaises(c.owner.ReadinessError):
                c.observe(self.root,self.root,self.root/'absent',browser_binary='unused')
            invoked.assert_not_called()
        for mutation in ('source','exit'):
            repo=self.root/mutation;(repo/'site').mkdir(parents=True)
            payload=repo/'payload';payload.mkdir();(payload/c.MANIFEST).write_bytes(self.manifest_raw)
            changed=copy.deepcopy(self.state);changed['clean']=False
            def original(argv,**kwargs):
                Path(kwargs['env']['CA_COMPONENT_PLAYWRIGHT_JSON']).write_text(json.dumps(self.raw_report()))
                return SimpleNamespace(returncode=1 if mutation=='exit' else 0)
            with mock.patch.dict(os.environ,{'GITHUB_RUN_ID':'17','GITHUB_RUN_ATTEMPT':'1'},clear=True), \
                 mock.patch.object(c,'snapshot',side_effect=[self.state,changed if mutation=='source' else self.state]), \
                 mock.patch.object(c.shutil,'which',side_effect=['node','npm']), \
                 mock.patch.object(c.browser,'tool_identity',return_value={'sha256':'c'*64,'size':1}), \
                 mock.patch.object(c.subprocess,'run',side_effect=original):
                with self.subTest(mutation=mutation),self.assertRaises(c.owner.ReadinessError):
                    c.observe(repo,payload,repo/'observed.json',browser_binary='chrome')
            self.assertFalse((repo/'observed.json').exists())

    def test_producer_authenticates_completed_source_upload_before_whole_run_completion(self):
        run = {**self.run, 'status': 'in_progress', 'conclusion': None}
        job = copy.deepcopy(self.job)
        job.update(status='in_progress', conclusion=None)
        req = {**self.req, 'ci_run_id': 17}
        arguments = self.observed, req, run, job, self.artifacts[0], self.source_zip
        with self.transport():
            for status in ('in_progress', 'queued', 'requested', 'waiting', 'pending'):
                with self.subTest(run_status=status):
                    run['status'] = status
                    self.assertEqual(c.report_from_observation(*arguments), self.report)
                    with self.assertRaisesRegex(c.owner.ReadinessError, 'Docs whole run did not succeed'):
                        c.browser._run(run, req['source_commit'], req['ci_run_id'])
            invalid_states = (('completed', None), ('completed', 'failure'), ('queued', 'cancelled'), ('unknown', None))
            for status, conclusion in invalid_states:
                with self.subTest(run_status=status, conclusion=conclusion), self.assertRaises(c.owner.ReadinessError):
                    run.update(status=status, conclusion=conclusion)
                    c.report_from_observation(*arguments)
            run['status'] = 'queued'
            del run['conclusion']
            with self.assertRaisesRegex(c.owner.ReadinessError, 'Docs whole run did not succeed'):
                c.report_from_observation(*arguments)
            run.update(status='queued', conclusion=None)
            job['status'] = 'queued'
            with self.assertRaisesRegex(c.owner.ReadinessError, 'component producer job differs'):
                c.report_from_observation(*arguments)
            job['status'] = 'in_progress'
            job['steps'][0]['conclusion'] = 'failure'
            with self.assertRaisesRegex(c.owner.ReadinessError, 'component original source upload incomplete'):
                c.report_from_observation(*arguments)

    def test_final_admission_uses_both_original_uploads_and_reconstructs_all_thirteen(self):
        with self.transport(): result=c.admit(self.req)
        self.assertEqual({r['cell'] for r in result['results']},CELLS)
        self.assertEqual((result['run_id'],result['job_id'],result['source_artifact_id'],result['report_artifact_id']),
                         (17,29,31,32))
        self.assertNotIn('pages',result)
        self.assertNotIn('tar_sha256',result)

    def test_final_refuses_wrong_run_source_attempt_upload_report_and_population(self):
        for mutation in ('failed-run','pull-request','wrong-source','wrong-job','wrong-attempt','failed-upload',
                         'forged-log','mixed-archive','forged-report','missing-case','skipped-case','program-final',
                         'forged-source-member','extra-source-member','fork'):
            with self.subTest(mutation=mutation):
                self.setUp()
                if mutation=='failed-run':self.run['conclusion']='failure'
                elif mutation=='pull-request':self.run['event']='pull_request'
                elif mutation=='wrong-source':self.run['head_sha']='d'*40
                elif mutation=='wrong-job':self.job['name']='Site | [Test] - Generator'
                elif mutation=='wrong-attempt':self.job['run_attempt']=2
                elif mutation=='failed-upload':self.job['steps'][0]['conclusion']='failure'
                elif mutation=='mixed-archive':self.artifacts[0]['digest']='sha256:'+'d'*64
                elif mutation=='forged-report':
                    self.report['job_id']=30
                    raw=self.archive({c.REPORT_FILE:json.dumps(self.report).encode()})
                    self.data[32]=raw;self.artifacts[1]=self.metadata(32,self.artifacts[1]['name'],raw)
                elif mutation=='missing-case':self.observed['tests'].pop();self.refresh()
                elif mutation=='skipped-case':self.observed['tests'][0]['result']='SKIPPED';self.refresh()
                elif mutation=='program-final':self.run['head_branch']='major/state-contracts'
                elif mutation in ('forged-source-member','extra-source-member'):
                    values=copy.deepcopy(self.values)
                    values['site/src/components/Search.astro' if mutation=='forged-source-member'
                           else 'site/test/components/unreviewed.spec.ts']=b'changed fixture bytes\n'
                    self.source_zip=self.archive({**values,c.MANIFEST:self.manifest_raw});self.refresh()
                elif mutation=='fork':self.run['head_repository']['id']=9
                with self.transport():
                    if mutation=='forged-log':
                        actual=self.api
                        with mock.patch.object(c.owner,'api',side_effect=lambda p,binary=False:
                            b'' if p=='actions/jobs/29/logs' else actual(p,binary)):
                            with self.assertRaises(c.owner.ReadinessError):c.admit(self.req)
                    else:
                        with self.assertRaises(c.owner.ReadinessError):c.admit(self.req)

    def test_component_map_cannot_borrow_pages_or_omit_a_clause(self):
        original=json.loads((ROOT/'.github/major-test-selections.json').read_text())
        for field,value in (('payload_name','github-pages'),('job','Site | [Test] - Generator'),
                            ('proof_kind','live-host'),('selectors',[c.SELECTORS[0]])):
            doc=copy.deepcopy(original);g=next(g for g in doc['groups'] if g['observation']==c.ROLE)
            g[field]=value
            with self.subTest(field=field),self.assertRaises(c.owner.ReadinessError):c.validate_selection_map(doc)
        doc=copy.deepcopy(original);doc['groups']=[g for g in doc['groups'] if g['cells']!=['disposition:transitions:S55:11']]
        with self.assertRaises(c.owner.ReadinessError):c.validate_selection_map(doc)

    def test_runtime_dispatch_preserves_native_docs_core_and_rejects_recursive_or_unknown(self):
        core={'schema':c.owner.SCHEMA}
        docs={'schema':'codearbiter-major-readiness/2'}
        native={'schema':'codearbiter-major-readiness/4','runtime':docs}
        component={'schema':c.ENVELOPE,'core':native}
        record={'schema':c.owner.SOURCE_SCHEMA,'runtime':component}
        self.assertIs(c.owner.runtime_record(record),docs)
        for inner in ({'schema':c.ENVELOPE,'core':core},{'schema':'unknown'}):
            with self.assertRaises(c.owner.ReadinessError):c.owner.runtime_record({'schema':c.ENVELOPE,'core':inner})
        with mock.patch.object(c,'admit',return_value={'run_id':17,'results':[]}), \
             mock.patch.object(c.owner,'produce',return_value=core) as delegated:
            produced=c.produce(self.req,[],[])
        self.assertEqual(delegated.call_args.args[0]['cells'],[])
        actual_core_run={**self.run,'id':7,'path':'.github/workflows/ci.yml'}
        with mock.patch.object(c,'admit',return_value=produced['components']), \
             mock.patch.object(c.owner,'verify',return_value={'state':'PREPUBLICATION_READY'}) as verify:
            c.verify(record=produced,requirements=self.req,run=actual_core_run)
        self.assertEqual(verify.call_args.kwargs['requirements']['cells'],[])

    def test_bounded_regular_json_refuses_duplicate_link_and_oversize(self):
        with self.assertRaises(ValueError):c.source.decode(b'{"x":1,"x":2}')
        p=self.root/'large';p.write_bytes(b'12345')
        with self.assertRaises(c.owner.ReadinessError):c.source.read_file(p,4)
        link=self.root/'alias';os.link(p,link)
        with self.assertRaises(c.owner.ReadinessError):c.source.read_file(p,10)

    def test_source_retention_roundtrips_exact_bytes_and_refuses_changed_member(self):
        repo=self.root/'source'
        for path,raw in self.values.items():
            target=repo/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        with mock.patch.object(c,'snapshot',return_value=self.state):
            output=self.root/'retained';c.prepare_source(repo,output)
            self.assertEqual(json.loads((output/c.MANIFEST).read_text()),self.manifest)
            self.assertEqual({p:(output/p).read_bytes() for p in self.values},self.values)
            (repo/'site/src/components/Search.astro').write_bytes(b'drift\n')
            with self.assertRaises(c.owner.ReadinessError):c.prepare_source(repo,self.root/'refused')

    def test_original_workflow_invocation_and_token_authority_remain_separate(self):
        text=(ROOT/'.github/workflows/docs.yml').read_text()
        component=text.split('      - name: Browser component acceptance\n',1)[1].split('      - name: Browser publication gate',1)[0]
        command=component.split('      - name: Upload original component source-test inputs',1)[0]
        self.assertEqual(command.count('npm run test:components'),1)
        self.assertEqual(command.count('site_component_observation.py observe'),1)
        self.assertIn('else\n            npm run test:components\n          fi',command)
        self.assertNotIn('GH_TOKEN',command)
        keys = [line.strip().partition(':')[0] for line in component.splitlines()]
        self.assertEqual(keys.count('GH_TOKEN'), 1)
        self.assertIn('steps.component-source.outcome == \'success\'',component)
        self.assertIn('steps.component-gate.outcome == \'success\'',component)
        self.assertIn("github.event_name == 'push'",component)
        self.assertIn('refs/heads/major/state-contracts',component)
        self.assertNotIn('pages: write',component)
        self.assertNotIn('id-token: write',component)


if __name__ == '__main__':
    unittest.main()
