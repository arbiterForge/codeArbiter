"""Finite original Docs authority controls; no network or npm lifecycle replay."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest import mock
import major_readiness as owner
import site_vitest_observation as docs

STAMP = '2026-11-15T12:00:00Z'
END = '2026-11-15T12:00:10Z'


class OriginalDocsSourceTests(unittest.TestCase):
    @staticmethod
    def archive(values):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as zipped:
            for name, raw in values.items():
                zipped.writestr(name, raw)
        return stream.getvalue()

    def setUp(self):
        self.req = {'source_commit':'a'*40,'source_tree':'b'*40,'ci_run_id':7,
            'task_ids':['Q-02'],'required_artifact_names':[],
            'cells':sorted(docs.CELLS),'cell_jobs':dict.fromkeys(docs.CELLS,docs.JOB)}
        self.run = {'id':17,'head_sha':'a'*40,'head_branch':'main','event':'push',
            'status':'completed','conclusion':'success','run_attempt':1,'path':docs.WORKFLOW,
            'repository':{'id':8,'full_name':owner.REPOSITORY},
            'head_repository':{'id':8,'full_name':owner.REPOSITORY}}
        self.job = {'id':29,'run_id':17,'run_attempt':1,'name':docs.JOB,
            'status':'completed','conclusion':'success','steps':[
                {'name':name,'status':'completed','conclusion':'success',
                 'started_at':STAMP,'completed_at':END} for name in (docs.UPLOAD,docs.REPORT_STEP)]}
        self.values = {s.split(':',2)[1]:b'original fixture source\n'
            for selectors in docs.RECIPES.values() for s in selectors}
        self.values['site/package.json'] = json.dumps({'scripts':docs.SCRIPTS}).encode()
        self.inputs = {p:{'bytes':len(raw),'sha256':owner.digest(raw)} for p,raw in self.values.items()}
        self.namespaces = {'core/pysrc':['_fixture.py'],'.github/scripts':['fixture.py']}
        self.manifest = {'format':docs.MANIFEST_FORMAT,'profile':docs.PROFILE,'workflow':docs.WORKFLOW,
            'job':docs.JOB,'source_commit':'a'*40,'source_tree':'b'*40,
            'inputs':self.inputs,'python_namespaces':self.namespaces}
        self.manifest_raw = json.dumps(self.manifest).encode()
        self.source = self.archive({**self.values,docs.MANIFEST:self.manifest_raw})
        self.observed = {'format':docs.OBSERVATION,'profile':docs.PROFILE,'workflow':docs.WORKFLOW,
            'job':docs.JOB,'source_commit':'a'*40,'source_tree':'b'*40,'docs_run_id':17,
            'run_attempt':1,'argv':docs.ARGV.copy(),'exit_code':0,'source_stable':True,
            'source_manifest_sha256':owner.digest(self.manifest_raw),'primary_raw_sha256':'c'*64,
            'tests':[{'id':s,'result':'passed'} for s in sorted({s for v in docs.RECIPES.values() for s in v})],
            'launch_inputs':[{'path':'/selected/node','resolved_path':'/selected/node','bytes':1,
                'sha256':'d'*64,'filesystem_id':'1:2'}],
            'runtime_scope':'Selected launch inputs only; not an installed host or full third-party graph.',
            'rendered_outputs':{p:{'bytes':1,'sha256':'e'*64} for p in docs.RENDERED},
            'numeric_summary_sha256':'f'*64,
            'numeric_totals':{k:{'total':10,'covered':9,'pct':90} for k in ('lines','branches')}}
        self.refresh_summary()
        self.refresh()

    def refresh_summary(self):
        rows = self.observed['tests']
        self.observed['primary_summary'] = {'total':len(rows),
            'numPassedTests':sum(r['result']=='passed' for r in rows),
            'numFailedTests':sum(r['result']=='failed' for r in rows),
            'numPendingTests':sum(r['result']=='skipped' for r in rows),'numTodoTests':0,'success':True}

    def metadata(self, identity, name, raw):
        return {'id':identity,'name':name,'expired':False,'size_in_bytes':len(raw),
            'digest':'sha256:'+owner.digest(raw),'created_at':STAMP,
            'workflow_run':{'id':17,'head_sha':'a'*40,'head_branch':'main',
                'repository_id':8,'head_repository_id':8}}

    def refresh(self):
        source = self.metadata(31,docs.PAYLOAD,self.source)
        self.report = {'schema':docs.REPORT,'source_commit':'a'*40,'source_tree':'b'*40,
            'docs_run_id':17,'run_attempt':1,'job_id':29,'source_artifact_id':31,
            'source_archive_sha256':owner.digest(self.source),'observation':self.observed,
            'results':docs.named_results(self.observed)}
        report = self.archive({docs.REPORT_FILE:json.dumps(self.report).encode()})
        self.artifacts = [source,self.metadata(32,'major-docs-site-test-qualification-29',report)]
        self.data = {31:self.source,32:report}

    def api(self, path, binary=False):
        if path.startswith('actions/workflows/docs.yml/runs?'):
            return {'total_count':1,'workflow_runs':[self.run]}
        if path == 'actions/runs/17': return self.run
        if path == 'actions/runs/17/jobs?filter=latest&per_page=100':
            return {'total_count':1,'jobs':[self.job]}
        if path == 'actions/runs/17/artifacts?per_page=100':
            return {'total_count':len(self.artifacts),'artifacts':self.artifacts}
        if path == 'actions/jobs/29/logs':
            lines = [STAMP+' ##[group]Run '+owner.UPLOAD_ACTION]
            for artifact in self.artifacts:
                lines += [STAMP+' SHA256 digest of uploaded artifact is '+artifact['digest'][7:],
                    STAMP+f" Artifact {artifact['name']} successfully finalized. Artifact ID {artifact['id']}"]
            return ('\n'.join(lines)+'\n').encode()
        if path.startswith('actions/artifacts/') and binary:
            return self.data[int(path.split('/')[2])]
        raise AssertionError('unexpected API fixture route: '+path)

    @contextlib.contextmanager
    def owned_transport(self):
        # Immutable source/Git acquisition is separately controlled below. This
        # fixture exercises real report/archive/metadata/log admission, no API.
        with mock.patch.object(owner,'api',side_effect=self.api), \
             mock.patch.object(docs,'expected_inputs',return_value=self.inputs), \
             mock.patch.object(docs,'namespace_members',return_value=self.namespaces):
            yield

    def test_sf13_delegates_core_and_requires_original_docs(self):
        cell = 'disposition:findings:SF13'
        core_cell = 'disposition:findings:C-F04'
        req = copy.deepcopy(self.req)
        req['cells'].extend((cell, core_cell))
        req['cell_jobs'].update({cell:'major qualification / packaging', core_cell:'composed core'})
        req['source_finding_composite_cells'] = [core_cell, cell]
        req['source_finding_inputs'] = {'major-readiness-implementation-v1':'1'*64,
            'route-release-state-component-v1':'2'*64, 'hooks-proof-publisher-v1':'3'*64,
            'hooks-single-owner-findings-v1':'4'*64}
        docs_part = {'run_id':17, 'run_attempt':1, 'job_id':29,
                     'sf13_selectors':['candidate selected fixture cases']}
        joined = {'cell':cell,'result':'PASSED','core_components':['original bound proof']}
        with (
            mock.patch.object(docs,'admit',return_value=docs_part),
            mock.patch.object(owner,'produce',return_value={'original core':'retained'}) as core,
            mock.patch.object(docs,'sf13_composition',return_value=joined,create=True) as composite,
        ):
            record = docs.produce(req, [], [])
        self.assertIn('sf13_source',record,'Docs-only envelope erased the complete SF13 composition')
        self.assertEqual(record['sf13_source'],joined)
        self.assertNotIn(cell,core.call_args.args[0]['cells'])
        self.assertIn(core_cell,core.call_args.args[0]['cells'])
        self.assertEqual(core.call_args.args[0]['source_finding_composite_cells'],[core_cell])
        self.assertEqual(set(core.call_args.args[0]['source_finding_inputs']),{
            'major-readiness-implementation-v1','route-release-state-component-v1'})
        composite.assert_called_once()

    def sf13_only_requirements(self):
        cell = docs.reports.SF13_CELL
        return {**self.req, 'cells':[cell], 'cell_jobs':{cell:'major qualification / packaging'},
                'source_finding_composite_cells':[cell], 'source_finding_inputs':{
                    docs.reports.SOURCE_PROFILE:'1'*64, 'hooks-single-owner-findings-v1':'2'*64}}

    def original_core_run(self):
        return {'id':7,'head_sha':'a'*40,'head_branch':'main','event':'push',
            'status':'completed','conclusion':'success','run_attempt':3,'path':'.github/workflows/ci.yml',
            'repository':{'id':8,'full_name':owner.REPOSITORY}}

    def test_sf13_requires_each_original_docs_case(self):
        req = self.sf13_only_requirements()
        self.assertEqual(len(docs.CELLS),18)
        self.assertNotIn(docs.reports.SF13_CELL,docs.CELLS)
        self.assertTrue(docs.docs_required(req))
        self.assertEqual(len(docs.SF13_DOCS_SELECTORS),13)
        observed_ids = {row['id'] for row in self.observed['tests']}
        for selector in docs.SF13_DOCS_SELECTORS:
            if selector not in observed_ids:
                self.observed['tests'].append({'id':selector,'result':'passed'})
            path = selector.split(':',2)[1]
            self.values.setdefault(path,b'original fixture source\\n')
        self.inputs = {p:{'bytes':len(raw),'sha256':owner.digest(raw)} for p,raw in self.values.items()}
        self.manifest['inputs'] = self.inputs
        self.manifest_raw = json.dumps(self.manifest).encode()
        self.observed['source_manifest_sha256'] = owner.digest(self.manifest_raw)
        self.source = self.archive({**self.values,docs.MANIFEST:self.manifest_raw})
        self.refresh_summary(); self.refresh()
        with self.owned_transport():
            got = docs.admit(req)
        self.assertEqual(got['results'],[])
        self.assertEqual(got['sf13_selectors'],list(docs.SF13_DOCS_SELECTORS))
        saved = self.observed['tests']
        for selector in docs.SF13_DOCS_SELECTORS:
            for effect in ('remove','skip'):
                bad = copy.deepcopy(saved)
                row = next(r for r in bad if r['id'] == selector)
                if effect == 'remove': bad.remove(row)
                else: row['result']='skipped'
                self.observed['tests'] = bad
                self.refresh_summary(); self.refresh()
                with self.subTest(selector=selector,effect=effect), self.owned_transport(), self.assertRaisesRegex(
                        owner.ReadinessError,'SF13 original Docs owner cases'):
                    docs.admit(req)
        self.observed['tests'] = saved

    def test_sf13_composes_two_exact_core_sources_from_one_original_capture(self):
        req = self.sf13_only_requirements()
        ci = self.original_core_run()
        job = {'id':51,'run_id':7,'run_attempt':3,'name':docs.reports.SOURCE_JOB,
               'status':'completed','conclusion':'success'}
        docs_part = {'run_id':17,'run_attempt':1,'job_id':29,
                     'sf13_selectors':list(docs.SF13_DOCS_SELECTORS)}
        def authenticate(component, actual_req, run, artifacts, jobs, *, job_log):
            self.assertEqual((actual_req,run,jobs,job_log),(req,ci,[job],b'closed original log'))
            idx = int(component['script'].endswith('test_sync_core.py'))
            return ({'job_id':51,'run_attempt':3,'source_artifact_id':61+idx,
                     'observation_artifact_id':64,'selectors':component['selectors']},
                    {'artifact_id':61+idx,'members':[]})
        with (
            mock.patch.object(owner,'api',return_value=b'closed original log') as api,
            mock.patch.object(docs.reports,'source_component_evidence',side_effect=authenticate) as components,
        ):
            value = docs.sf13_composition(req,docs_part,[],[job],run=ci)
        api.assert_called_once_with('actions/jobs/51/logs',binary=True)
        scripts = [call.args[0]['script'] for call in components.call_args_list]
        self.assertEqual(scripts,['.github/scripts/test_generated_output.py','.github/scripts/test_sync_core.py'])
        self.assertEqual([len(c['selectors']) for c in value['core_components']],[9,3])
        self.assertEqual((value['docs_run_id'],value['docs_run_attempt'],value['docs_job_id']),(17,1,29))

        with mock.patch.object(owner,'api') as api:
            for invalid_run in (dict(ci,head_sha='c'*40),dict(ci,event='pull_request'),
                                dict(ci,head_branch='major/state-contracts'),dict(ci,run_attempt='3')):
                with self.assertRaises(owner.ReadinessError):
                    docs.sf13_composition(req,docs_part,[],[job],run=invalid_run)
            with self.assertRaisesRegex(owner.ReadinessError,'original Core source pins differ'):
                docs.sf13_composition({**req,'source_finding_inputs':{}},docs_part,[],[job],run=ci)
            with self.assertRaisesRegex(owner.ReadinessError,'original Docs complement'):
                docs.sf13_composition(req,{**docs_part,'sf13_selectors':[]},[],[job],run=ci)
            api.assert_not_called()
        with self.assertRaisesRegex(owner.ReadinessError,'both original Core and Docs'):
            docs.reports.source_finding_evidence(req,[],[job],run=ci)

    def test_sf13_final_envelope_recomputes_and_requires_the_complete_composition(self):
        req = self.sf13_only_requirements()
        ci = self.original_core_run()
        docs_part = {'run_id':17,'run_attempt':1,'job_id':29,'sf13_selectors':list(docs.SF13_DOCS_SELECTORS)}
        joined = {'cell':docs.reports.SF13_CELL,'result':'PASSED','core_components':['observed Core fixture']}
        result = {'schema':docs.ENVELOPE,'program_id':owner.PROGRAM,'state':'PREPUBLICATION_READY',
                  **req,'core':{},'docs_source':docs_part,'sf13_source':joined}
        kwargs = dict(record=result,requirements=req,run=ci,build_artifacts=[],jobs=[],artifact={},
                      archive_digest='f'*64)
        with (
            mock.patch.object(docs,'admit',return_value=docs_part),
            mock.patch.object(docs,'sf13_composition',return_value=joined) as actual,
            mock.patch.object(owner,'verify') as core,
        ):
            self.assertEqual(docs.verify(**kwargs)['docs_source_run_id'],17)
            actual.assert_called_once_with(req,docs_part,[],[],run=ci)
            core.assert_called_once()
            for record in ({k:v for k,v in result.items() if k!='sf13_source'},
                           {**result,'sf13_source':{'cell':docs.reports.SF13_CELL,'result':'PASSED'}}):
                with self.assertRaises(owner.ReadinessError): docs.verify(**{**kwargs,'record':record})

    def test_original_docs_generator_is_a_distinct_source_authority(self):
        with self.owned_transport():
            try:
                result = owner.produce(self.req,[],[{'id':99,'name':'major readiness producer'}])
            except owner.ReadinessError as error:
                self.fail('complete original Docs source observation was not admitted: '+str(error))
        self.assertEqual(result['schema'],docs.ENVELOPE)
        self.assertEqual(result['ci_run_id'],7)
        self.assertEqual(result['docs_source']['run_id'],17)
        self.assertEqual({r['cell'] for r in result['docs_source']['results']},docs.CELLS)

    def test_original_site_unit_rows_preserve_each_historical_named_mapping(self):
        repo = Path(__file__).resolve().parents[2]
        history = repo / 'docs/state-contracts-major/execution/evidence/site-unit-current-38bf'
        pagefind = json.loads((history / 'pagefind-remaining.json').read_bytes())
        release = json.loads((history / 'release-derivation-tested.json').read_bytes())
        publication = json.loads((history / 'observed-publication.json').read_bytes())
        raw = json.loads((history / 'selected68-original-projection.json').read_bytes())
        original_passes = {row['fullName'] for row in raw['outcomes'] if row['status'] == 'passed'}
        expected = {'disposition:transitions:' + name: cases
                    for name, cases in pagefind['per_disposition_assertions'].items()}
        expected['disposition:machines:S65'] = list(dict.fromkeys(
            title for titles in expected.values() for title in titles))
        expected['disposition:machines:S65'].append(
            'complete search bundle publication is wired to every Astro build instead of an optional postbuild command')
        expected.update((row['cell'], row['observed_named_cases']) for row in release['per_cell_assertion_mapping'])
        expected['disposition:transitions:SX03:02'] = [row['name'] for row in publication['original_named_assertions']]
        self.assertEqual(len(expected), 14)
        self.assertTrue(all(set(names) <= original_passes for names in expected.values()))
        policy = json.loads((repo / '.github/major-qualification-policy.json').read_bytes())
        self.assertEqual({cell: policy['cell_job_bindings'].get(cell) for cell in expected},
                         dict.fromkeys(expected, docs.JOB))
        with self.owned_transport():
            result = docs.admit(self.req)['results']
        self.assertEqual({row['cell']: [selector.split(':', 2)[2] for selector in row['selectors']]
                          for row in result if row['cell'] in expected}, expected)

    def test_each_required_complement_missing_skipped_or_duplicate_refuses(self):
        original = copy.deepcopy(self.observed)
        for cell, selectors in docs.RECIPES.items():
            for state in ('missing','skipped','duplicate'):
                with self.subTest(cell=cell,state=state):
                    self.observed = copy.deepcopy(original)
                    row = next(r for r in self.observed['tests'] if r['id']==selectors[-1])
                    if state=='missing': self.observed['tests'].remove(row)
                    elif state=='skipped': row['result']='skipped'
                    else:
                        self.observed['tests'].append(dict(row))
                        with self.assertRaises(owner.ReadinessError): docs.named_results(self.observed)
                        continue
                    self.refresh_summary(); self.refresh()
                    with self.owned_transport(), self.assertRaises(owner.ReadinessError): docs.admit(self.req)

    def test_complete_selected_finding_does_not_require_unrelated_finding(self):
        cell = 'disposition:findings:GEN-B01'
        self.observed['tests'] = [r for r in self.observed['tests'] if r['id'] in docs.RECIPES[cell]]
        self.refresh_summary(); self.refresh()
        req = {**self.req,'cells':[cell],'cell_jobs':{cell:docs.JOB}}
        with self.owned_transport(): self.assertEqual(docs.admit(req)['results'][0]['result'],'PASSED')

    def test_foreign_run_workflow_event_branch_attempt_and_job_refuse(self):
        for target,key,value in [('run','id',7),('run','path','.github/workflows/ci.yml'),
            ('run','event','pull_request'),('run','head_branch','major/state-contracts'),
            ('run','conclusion','failure'),('run','head_sha','c'*40),('run','run_attempt',2),
            ('job','name','Site | [Build] - Astro Pages'),('job','conclusion','failure')]:
            with self.subTest(target=target,key=key):
                record = getattr(self,target); old = record[key]; record[key]=value
                try:
                    with self.owned_transport(), self.assertRaises(owner.ReadinessError): docs.admit(self.req)
                finally: record[key]=old

    def test_source_archive_population_digest_and_namespace_are_exact(self):
        with self.owned_transport():
            docs.source_archive(self.artifacts[0],{**self.req,'ci_run_id':17},self.source)
            bad = copy.deepcopy(self.manifest); bad['python_namespaces']['core/pysrc'].append('_host.py')
            with self.assertRaises(owner.ReadinessError): docs.validate_manifest(bad,self.req)
            bad = copy.deepcopy(self.manifest); bad['inputs'].pop(next(iter(self.inputs)))
            with self.assertRaises(owner.ReadinessError): docs.validate_manifest(bad,self.req)
            self.source += b'different'
            with self.assertRaises(owner.ReadinessError):
                docs.source_archive(self.artifacts[0],{**self.req,'ci_run_id':17},self.source)

    def test_metadata_upload_and_report_tampering_refuse(self):
        with self.owned_transport():
            self.job['steps'][0]['conclusion']='failure'
            with self.assertRaises(owner.ReadinessError): docs.admit(self.req)
            self.job['steps'][0]['conclusion']='success'
            self.report['results'][0]['selectors']=['invented']
            raw=self.archive({docs.REPORT_FILE:json.dumps(self.report).encode()})
            self.data[32]=raw; self.artifacts[1]=self.metadata(32,self.artifacts[1]['name'],raw)
            with self.assertRaises(owner.ReadinessError): docs.admit(self.req)

    def test_observation_refuses_incomplete_command_descendants_and_source(self):
        req={**self.req,'ci_run_id':17}
        for field,value in [('argv',['npm','run','coverage','--','--reporter=json']),('exit_code',1),
            ('source_stable',False),('profile','site-browser'),('docs_run_id',7),
            ('rendered_outputs',{}),('numeric_totals',{})]:
            with self.subTest(field=field), self.assertRaises((owner.ReadinessError,KeyError)):
                docs.validate_observation({**self.observed,field:value},req,self.manifest)

    def test_bounded_regular_reader_refuses_links_large_files_and_closes_descriptor(self):
        with tempfile.TemporaryDirectory(prefix='ca-docs-reader-') as folder:
            root=Path(folder); path=root/'small.json'; path.write_bytes(b'{}')
            real_close=os.close
            with mock.patch.object(os,'close',wraps=real_close) as closed:
                self.assertEqual(docs.read_file(path,2),b'{}'); closed.assert_called_once()
            with self.assertRaises(owner.ReadinessError): docs.read_file(path,1)
            alias=root/'hard.json'; os.link(path,alias)
            with self.assertRaises(owner.ReadinessError): docs.read_file(alias,2)
            with self.assertRaises(owner.ReadinessError): docs.read_file(root,2)

    def test_decode_duplicate_nonfinite_and_cli_privacy(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}'):
            with self.assertRaises(ValueError): docs.decode(raw)
        stderr=io.StringIO()
        with mock.patch.object(docs,'emit',side_effect=ValueError('PRIVATE_CANARY')),contextlib.redirect_stderr(stderr):
            self.assertEqual(docs.main(['emit','--output','unused','--observation','unused']),1)
        self.assertNotIn('PRIVATE_CANARY',stderr.getvalue())

    def test_git_source_closure_binds_all_python_and_declared_source_members(self):
        package=json.dumps({'scripts':docs.SCRIPTS}).encode()
        def tree(repo,source,root,recursive=True):
            return {'fixture.py' if root in docs.NAMESPACES else 'fixture.ts':('100644','blob',1)}
        with mock.patch.object(owner,'_tree_entries',side_effect=tree):
            values=docs.expected_inputs(Path('.'),'a'*40,load=lambda s,p:package if p=='site/package.json' else b'x')
            self.assertIn('core/pysrc/fixture.py',values)
            self.assertIn('.github/scripts/fixture.py',values)
            self.assertIn('site/src/fixture.ts',values)
            with mock.patch.object(owner,'_tree_entries',return_value={'_host.py':('100644','blob',1)}), \
                 self.assertRaises(owner.ReadinessError): docs.namespace_members(Path('.'),'a'*40)

    def test_prepared_source_is_exact_and_never_overwrites(self):
        with tempfile.TemporaryDirectory(prefix='ca-docs-prepare-') as folder:
            root=Path(folder)
            for path,raw in self.values.items():
                target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            snapshot={'source_commit':'a'*40,'source_tree':'b'*40,'clean':True,
                'inputs':self.inputs,'python_namespaces':self.namespaces}
            out=root/'out'; manifest,_=docs.prepare_source(root,out,snapshot)
            self.assertEqual(manifest,self.manifest)
            with self.assertRaises(FileExistsError): docs.prepare_source(root,out,snapshot)

    def raw_named(self, root):
        suites={}
        for row in self.observed['tests']:
            _,path,title=row['id'].split(':',2)
            suites.setdefault(path,[]).append({'fullName':title,'status':row['result'],
                'failureMessages':['PRIVATE_FAILURE_CANARY']})
        return {'testResults':[{'name':str(root/path),'assertionResults':cases} for path,cases in suites.items()],
            'numTotalTests':len(self.observed['tests']),'numPassedTests':len(self.observed['tests']),
            'numFailedTests':0,'numPendingTests':0,'numTodoTests':0,'numFailedTestSuites':0,'success':True}

    def test_named_parser_discards_private_failure_details_and_refuses_foreign_summary(self):
        root=Path(tempfile.gettempdir()).resolve(); raw=self.raw_named(root)
        rows,summary=docs.parse_named(raw,root,self.inputs)
        self.assertNotIn('PRIVATE_FAILURE_CANARY',json.dumps([rows,summary]))
        self.assertEqual(len(rows), len(self.observed['tests']))
        for key,value in [('numTotalTests',len(rows)-1),('numFailedTestSuites',1),('success','true')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                docs.parse_named({**raw,key:value},root,self.inputs)
        raw['testResults'][0]['name']=str(root.parent/'outside.test.ts')
        with self.assertRaises(ValueError): docs.parse_named(raw,root,self.inputs)

    def test_observer_runs_original_compound_command_once_with_no_explicit_credential(self):
        with tempfile.TemporaryDirectory(prefix='ca-docs-once-') as folder:
            root=Path(folder).resolve(); (root/'site/coverage').mkdir(parents=True)
            (root/'site/coverage/coverage-summary.json').write_text(json.dumps({'total':self.observed['numeric_totals']}))
            payload=root/'payload';payload.mkdir();(payload/docs.MANIFEST).write_bytes(self.manifest_raw)
            snapshot={'source_commit':'a'*40,'source_tree':'b'*40,'clean':True,
                'inputs':self.inputs,'python_namespaces':self.namespaces}
            raw=root/'primary-vitest.json';out=root/'observation.json'
            process=mock.Mock()
            def completed():
                raw.write_text(json.dumps(self.raw_named(root)));return 0
            process.wait.side_effect=completed
            runtime=self.observed['launch_inputs']
            with mock.patch.object(docs,'source_snapshot',return_value=snapshot), \
                 mock.patch.object(docs.reports,'_vitest_launch',return_value=(['/selected/npm','run','coverage'],runtime)), \
                 mock.patch.object(docs.reports,'_vitest_runtime_file',return_value=runtime[0]), \
                 mock.patch.object(docs,'rendered_outputs',return_value=self.observed['rendered_outputs']), \
                 mock.patch.object(docs,'start',return_value=process) as launched, \
                 mock.patch.dict(os.environ,{'GITHUB_RUN_ID':'17','GITHUB_RUN_ATTEMPT':'1','GH_TOKEN':'PRIVATE_TOKEN_CANARY'}):
                self.assertEqual(docs.observe(root,payload,raw,out),0)
            launched.assert_called_once();process.wait.assert_called_once_with()
            args,kwargs=launched.call_args
            self.assertEqual(args[0],['/selected/npm','run','coverage'])
            self.assertEqual(kwargs['cwd'],root/'site')
            self.assertNotIn('GH_TOKEN',kwargs['env'])
            self.assertNotIn('PRIVATE_TOKEN_CANARY',json.dumps(kwargs['env']))
            self.assertEqual(json.loads(out.read_bytes())['argv'],['npm','run','coverage'])

    def test_observer_retains_only_a_refusal_when_successful_test_names_collide(self):
        with tempfile.TemporaryDirectory(prefix='ca-docs-ambiguous-') as folder:
            root=Path(folder).resolve()
            payload=root/'payload';payload.mkdir();(payload/docs.MANIFEST).write_bytes(self.manifest_raw)
            snapshot={'source_commit':'a'*40,'source_tree':'b'*40,'clean':True,
                'inputs':self.inputs,'python_namespaces':self.namespaces}
            raw=root/'primary-vitest.json';out=root/'observation.json'
            process=mock.Mock()
            def completed():
                data=self.raw_named(root)
                cases=data['testResults'][0]['assertionResults']
                cases.append(cases[0])
                data['numTotalTests']+=1
                data['numPassedTests']+=1
                raw.write_text(json.dumps(data));return 0
            process.wait.side_effect=completed
            with mock.patch.object(docs,'source_snapshot',return_value=snapshot), \
                 mock.patch.object(docs.reports,'_vitest_launch',return_value=(['/selected/npm','run','coverage'],[])), \
                 mock.patch.object(docs,'start',return_value=process) as launched:
                self.assertEqual(docs.observe(root,payload,raw,out),1)
            launched.assert_called_once()
            self.assertEqual(json.loads(out.read_bytes()), {
                'format':'codearbiter-docs-site-refusal/1','code':'PRIMARY_RESULTS_UNAVAILABLE','exit_code':0})
            self.assertNotIn(b'PRIVATE_FAILURE_CANARY',out.read_bytes())

    def test_envelope_keeps_actual_core_main_success_and_q03_guards(self):
        core_req=docs.core_requirements(self.req)
        core_req.update(cells=['scenario:SEQ-01'],cell_jobs={'scenario:SEQ-01':'original core job'},
            required_artifact_names=['qualified-payload'])
        req=copy.deepcopy(core_req);req['cells']+=sorted(docs.CELLS);req['cell_jobs'].update(self.req['cell_jobs'])
        core={'schema':owner.SCHEMA,'program_id':owner.PROGRAM,'state':'PREPUBLICATION_READY',**core_req,
            'producer_job_id':99,'results':[{'cell':'scenario:SEQ-01','result':'PASSED','job_id':20,'evidence_artifact_id':12}],
            'artifacts':[{'artifact_id':12,'archive_sha256':'1'*64,'members':[{'path':'package','sha256':'2'*64}]}]}
        record={'schema':docs.ENVELOPE,'program_id':owner.PROGRAM,'state':'PREPUBLICATION_READY',**req,
            'core':core,'docs_source':{'run_id':17}}
        run={'id':7,'head_sha':'a'*40,'head_branch':'main','event':'push','path':'.github/workflows/ci.yml',
            'conclusion':'success','repository':{'full_name':owner.REPOSITORY}}
        artifact={'id':11,'name':'major-readiness-'+'a'*40,'expired':False,'size_in_bytes':42,
            'digest':'sha256:'+'f'*64,'workflow_run':{'id':7,'head_sha':'a'*40}}
        payload={'id':12,'name':'qualified-payload','expired':False,'size_in_bytes':42,
            'digest':'sha256:'+'1'*64,'workflow_run':{'id':7,'head_sha':'a'*40}}
        args=dict(record=record,requirements=req,run=run,artifact=artifact,archive_digest='f'*64,
            jobs=[{'id':20,'name':'original core job','conclusion':'success'},
                {'id':99,'name':'major readiness producer','conclusion':'success'}],
            build_artifacts=[payload],payload_members={12:core['artifacts'][0]['members']})
        with mock.patch.object(docs,'admit',return_value=record['docs_source']) as admitted, \
             mock.patch.object(owner,'validate_upload'):
            self.assertEqual(owner.verify(**args)['docs_source_run_id'],17)
            for field,value in [('head_branch','major/state-contracts'),('event','pull_request'),
                ('conclusion','failure'),('head_sha','e'*40)]:
                admitted.reset_mock()
                with self.subTest(field=field), self.assertRaises(owner.ReadinessError):
                    owner.verify(**dict(args,run=dict(run,**{field:value})))
                admitted.assert_not_called()
            core['task_ids']=['Q-03'];req['task_ids']=['Q-03'];record['task_ids']=['Q-03']
            with self.assertRaisesRegex(owner.ReadinessError,'Q-03'): owner.verify(**args)

    def test_source_native_docs_browser_grammar_is_closed(self):
        core={'schema':owner.SCHEMA}
        record={'schema':owner.SOURCE_SCHEMA,'runtime':{'schema':'codearbiter-major-readiness/4',
            'runtime':{'schema':docs.ENVELOPE,'core':core}}}
        self.assertEqual(owner.runtime_record(record),core)
        record['runtime']['runtime']['core']={'schema':'invented'}
        with self.assertRaises(owner.ReadinessError): owner.runtime_record(record)

    def test_source_native_docs_source_browser_core_load_reauthenticates_all_authorities(self):
        import test_major_native_observation as native_fixture
        import test_site_playwright_observation as browser_fixture
        native=native_fixture.NativeCompositeAuthorityTests();native.setUp()
        browser=browser_fixture.DocsAuthorityTests();browser.setUp()
        native.req['cells']+=browser_fixture.CELLS+sorted(docs.CELLS)
        native.req['cell_jobs'].update(dict.fromkeys(browser_fixture.CELLS,browser_fixture.JOB))
        native.req['cell_jobs'].update(self.req['cell_jobs'])
        cell='disposition:transitions:inert-source'
        native.req['cells'].append(cell);native.req['cell_jobs'][cell]='major qualification / source'
        native.req['source_dispositions']={cell:{'result':'PRESERVED','proofs':[{
            'ref':'inert-proof.json','ref_commit':'a'*40,'sha256':'e'*64,'source_commit':'a'*40,
            'kind':'conformance-check','result':'PRESERVED','producer':{'class':'source-conformance',
                'identity':'inert schema fixture'},'current_at':'a'*40}]}}
        job=copy.deepcopy(self.job);job['id']=39
        report=copy.deepcopy(self.report);report.update(job_id=39,source_artifact_id=41)
        data={41:self.source,42:self.archive({docs.REPORT_FILE:json.dumps(report).encode()})}
        artifacts=[self.metadata(41,docs.PAYLOAD,data[41]),
            self.metadata(42,'major-docs-site-test-qualification-39',data[42])]
        def api(path,binary=False):
            if path=='actions/runs/17/jobs?filter=latest&per_page=100':
                return {'total_count':2,'jobs':[browser.job,job]}
            if path=='actions/runs/17/artifacts?per_page=100':
                return {'total_count':4,'artifacts':browser.artifacts+artifacts}
            if path=='actions/jobs/39/logs':
                lines=[STAMP+' ##[group]Run '+owner.UPLOAD_ACTION]
                for a in artifacts:
                    lines += [STAMP+' SHA256 digest of uploaded artifact is '+a['digest'][7:],
                        STAMP+f" Artifact {a['name']} successfully finalized. Artifact ID {a['id']}"]
                return ('\n'.join(lines)+'\n').encode()
            if path in ('actions/artifacts/41/zip','actions/artifacts/42/zip'):
                return data[int(path.split('/')[2])]
            if 'docs.yml/runs?' in path or path.startswith('actions/runs/17') or path=='actions/jobs/29/logs' \
                    or path in ('actions/artifacts/31/zip','actions/artifacts/32/zip'):
                return browser.api(path,binary)
            return native.api(path,binary)
        with mock.patch.object(owner,'api',side_effect=api), \
             mock.patch.object(docs,'expected_inputs',return_value=self.inputs), \
             mock.patch.object(docs,'namespace_members',return_value=self.namespaces):
            record=owner.produce(native.req,native.artifacts,native.jobs)
            self.assertEqual(record['runtime']['runtime']['schema'],docs.ENVELOPE)
            self.assertEqual(record['runtime']['runtime']['core']['schema'],docs.browser.ENVELOPE)
            metadata,archive=native.readiness_artifact(record)
            with mock.patch.object(owner,'collect',return_value=(native.req,native.run,native.artifacts+[metadata],native.jobs)):
                actual,result=owner.load_verified_receipt(None,'a'*40,7)
                self.assertEqual(actual,record)
                self.assertEqual(result['docs_source_run_id'],17)
                self.job['conclusion']='failure'  # unrelated fixture does not confer authority
                job['conclusion']='failure'
                with self.assertRaises(owner.ReadinessError): owner.load_verified_receipt(None,'a'*40,7)

    def test_workflow_preserves_original_lifecycle_and_step_local_read_only_emitter(self):
        from test_ci_impact import SiteBrowserPublicationWorkflowTest, workflow_jobs

        root=Path(__file__).resolve().parents[2]
        text=(root/'.github/workflows/docs.yml').read_text()
        jobs=workflow_jobs(text)
        job=jobs['site-check']
        SiteBrowserPublicationWorkflowTest._assert_workflow_authority(self, jobs)
        self.assertIn('success() && steps.docs-source-mode.outputs.active',job)
        self.assertIn("github.event_name == 'push'",job)
        self.assertIn('["refs/heads/main","refs/heads/major/state-contracts"]',job)
        self.assertNotIn('primary-vitest.json\n          ',job)
        self.assertNotIn('npm run coverage --',job)
        self.assertEqual(job.count('            npm run coverage\n'),1)
        self.assertIn('Retain numeric site coverage summary',job)


if __name__ == '__main__':
    unittest.main()
