"""Closed Docs authority: same source, distinct real run, original Pages bytes."""
import copy
import contextlib
import io
import json
import tarfile
import unittest
import zipfile
import os
import pathlib
import tempfile
import subprocess
from unittest import mock
import major_readiness as owner

CELLS = ['disposition:findings:SF16', 'disposition:machines:S62',
         *['disposition:transitions:S62:%02d' % n for n in range(1, 6)],
         *['disposition:transitions:S56:%02d' % n for n in (1, 2, 4, 5, 6)],
         'disposition:transitions:S58:01', 'disposition:transitions:S58:02', 'scenario:SEQ-28']
JOB = 'Site | [Build] - Astro Pages'
STAMP = '2026-11-15T12:00:00Z'
END = '2026-11-15T12:00:10Z'


class DocsAuthorityTests(unittest.TestCase):
    def test_emit_refusal_retains_safe_location_without_exception_contents(self):
        with tempfile.TemporaryDirectory(prefix='ca-docs-refusal-') as folder:
            root = pathlib.Path(folder).resolve()
            output = root / 'qualification.json'
            canary = 'PRIVATE_EXCEPTION_CONTENT_DO_NOT_RETAIN'
            stderr = io.StringIO()
            with mock.patch.object(self.docs.reports, 'validate_emitter_environment',
                                   side_effect=ValueError(canary)), contextlib.redirect_stderr(stderr):
                result = self.docs.main(['emit', '--repo', str(root),
                                         '--observation', str(root / 'observation.json'),
                                         '--output', str(output)])
            self.assertEqual(result, 1)
            self.assertFalse(output.exists())
            diagnostic = root / 'qualification.json.refusal.json'
            self.assertTrue(diagnostic.is_file(), 'refused emitter lost its diagnostic')
            raw = diagnostic.read_text(encoding='utf-8')
            record = json.loads(raw)
            self.assertEqual(record['format'], 'codearbiter-docs-refusal/1')
            self.assertFalse(record['qualified'])
            self.assertEqual(record['phase'], 'environment')
            self.assertEqual(record['location']['module'], 'site_playwright_observation.py')
            self.assertGreater(record['location']['line'], 0)
            self.assertLess(len(raw), 1024)
            self.assertNotIn(canary, raw + stderr.getvalue())

    def test_emit_refusal_never_overwrites_existing_diagnostic_or_masks_failure(self):
        with tempfile.TemporaryDirectory(prefix='ca-docs-retained-refusal-') as folder:
            root = pathlib.Path(folder).resolve()
            output = root / 'qualification.json'
            diagnostic = root / 'qualification.json.refusal.json'
            diagnostic.write_bytes(b'previous original refusal\n')
            with mock.patch.object(self.docs.reports, 'validate_emitter_environment',
                                   side_effect=ValueError('private')), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.docs.main(['emit', '--repo', str(root),
                    '--observation', str(root / 'observation.json'), '--output', str(output)]), 1)
            self.assertEqual(diagnostic.read_bytes(), b'previous original refusal\n')
            self.assertFalse(output.exists())

    def test_refusal_location_identifies_actual_guard_instead_of_shared_raise(self):
        with tempfile.TemporaryDirectory(prefix='ca-docs-guard-location-') as folder:
            root = pathlib.Path(folder).resolve()
            with mock.patch.object(self.docs.reports, 'validate_emitter_environment',
                    side_effect=lambda: self.docs.validate_observation({}, self.req)), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.docs.main(['emit', '--repo', str(root),
                    '--observation', str(root / 'observation.json'),
                    '--output', str(root / 'qualification.json')]), 1)
            record = json.loads((root / 'qualification.json.refusal.json').read_bytes())
            self.assertEqual(record['location'], {
                'module': 'site_playwright_observation.py',
                'line': self.docs.validate_observation.__code__.co_firstlineno + 1})

    def test_emit_refusal_does_not_write_through_owned_directory_alias(self):
        with tempfile.TemporaryDirectory(prefix='ca-docs-refusal-alias-') as folder:
            root = pathlib.Path(folder).resolve()
            target = root / 'target'
            target.mkdir()
            alias = root / 'alias'
            if os.name == 'nt':
                # Use an owned junction without requiring symlink privileges.
                completed = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(alias), str(target)],
                                           capture_output=True, timeout=10)
                self.assertEqual(completed.returncode, 0, 'owned junction setup failed')
            else:
                alias.symlink_to(target, target_is_directory=True)
            with mock.patch.object(self.docs.reports, 'validate_emitter_environment',
                    side_effect=ValueError('private')), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.docs.main(['emit', '--repo', str(root),
                    '--observation', str(root / 'observation.json'),
                    '--output', str(alias / 'qualification.json')]), 1)
            self.assertEqual(list(target.iterdir()), [])

    def test_refusal_location_identifies_json_predicate_instead_of_valueerror_raise(self):
        with tempfile.TemporaryDirectory(prefix='ca-docs-json-guard-') as folder:
            root = pathlib.Path(folder).resolve()
            canary = 'PRIVATE_DUPLICATE_KEY'
            def duplicate():
                return json.loads('{"' + canary + '":1,"' + canary + '":2}',
                                  object_pairs_hook=self.docs.reports.unique)
            stderr = io.StringIO()
            with mock.patch.object(self.docs.reports, 'validate_emitter_environment',
                                   side_effect=duplicate), contextlib.redirect_stderr(stderr):
                self.assertEqual(self.docs.main(['emit', '--repo', str(root),
                    '--observation', str(root / 'observation.json'),
                    '--output', str(root / 'qualification.json')]), 1)
            raw = (root / 'qualification.json.refusal.json').read_text()
            self.assertEqual(json.loads(raw)['location'], {
                'module': 'major_qualification_report.py',
                'line': self.docs.reports.unique.__code__.co_firstlineno + 3})
            self.assertNotIn(canary, raw + stderr.getvalue())

    def test_workflow_retains_original_observation_after_report_refusal(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        workflow = (root / '.github/workflows/docs.yml').read_text()
        self.assertIn('      - name: Retain Docs qualification diagnostics\n', workflow)
        step = workflow.split('      - name: Retain Docs qualification diagnostics\n', 1)[1].split('\n      - name:', 1)[0]
        self.assertIn("!cancelled() && steps.browser-gate.outcome == 'success'", step)
        self.assertIn("steps.program-mode.outputs.active == 'true'", step)
        self.assertIn("github.event_name == 'push'", step)
        self.assertIn('["refs/heads/main","refs/heads/major/state-contracts"]', step)
        self.assertIn('name: site-qualification-diagnostics', step)
        self.assertIn('${{ runner.temp }}/docs-browser-observation.json', step)
        self.assertIn('${{ runner.temp }}/docs-qualification.json.refusal.json', step)
        self.assertIn('overwrite: false', step)
        self.assertNotIn('GH_TOKEN:', step)

    def setUp(self):
        self.req = {'source_commit': 'a' * 40, 'source_tree': 'b' * 40,
                    'ci_run_id': 7, 'task_ids': ['Q-02'], 'required_artifact_names': [],
                    'cells': CELLS, 'cell_jobs': dict.fromkeys(CELLS, JOB)}
        self.run = {'id': 17, 'head_sha': self.req['source_commit'],
                    'head_branch': 'main', 'event': 'push', 'status': 'completed',
                    'conclusion': 'success', 'run_attempt': 1,
                    'path': '.github/workflows/docs.yml',
                    'repository': {'id': 8, 'full_name': owner.REPOSITORY},
                    'head_repository': {'id': 8, 'full_name': owner.REPOSITORY}}
        self.job = {'id': 29, 'run_id': 17, 'run_attempt': 1, 'name': JOB,
                    'status': 'completed', 'conclusion': 'success', 'steps': [
                        {'name': name, 'status': 'completed', 'conclusion': 'success',
                         'started_at': STAMP, 'completed_at': END}
                        for name in ('Upload Pages artifact', 'Upload Docs qualification report')]}
        tar = io.BytesIO()
        with tarfile.open(fileobj=tar, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            entry = tarfile.TarInfo('./index.html')
            entry.size = 6
            entry.mode = 0o644
            archive.addfile(entry, io.BytesIO(b'served'))
        self.tar = tar.getvalue()
        self.pages = self.zip('artifact.tar', self.tar)
        self.report = {'schema': 'codearbiter-major-docs-qualification/1',
                       'source_commit': 'a' * 40, 'source_tree': 'b' * 40,
                       'docs_run_id': 17, 'run_attempt': 1, 'job_id': 29,
                       'pages_artifact_id': 31, 'archive_sha256': owner.digest(self.pages),
                       'tar_sha256': owner.digest(self.tar),
                       'served_members': [{'path': 'index.html', 'mode': 0o644,
                                           'size': 6, 'sha256': owner.digest(b'served')}],
                       'observation': {}}
        import site_playwright_observation as docs
        self.docs = docs
        self.report['observation'] = self.observation()
        self.artifacts = []
        self.data = {}
        self.refresh_artifacts()

    def raw_report(self):
        suites = []
        for index, (file, title) in enumerate(self.docs.CASES):
            relative = file.removeprefix('site/test/browser/')
            suites.append({'title': relative, 'file': relative, 'specs': [{
                'id': 'case-' + str(index), 'title': title, 'file': relative, 'ok': True,
                'tests': [{'projectName': 'chrome', 'projectId': 'chrome', 'expectedStatus': 'passed',
                           'status': 'expected', 'annotations': [], 'results': [{
                               'status': 'passed', 'retry': 0, 'errors': [], 'duration': 10}]}]}]})
        return {'config': {'workers': 1, 'forbidOnly': True, 'projects': [
            {'name': 'chrome', 'id': 'chrome', 'retries': 0, 'repeatEach': 1}]},
            'suites': suites, 'errors': [],
            'stats': {'expected': len(suites), 'unexpected': 0, 'flaky': 0, 'skipped': 0}}

    def observation(self):
        return {'format': self.docs.OBSERVATION, 'source_commit': 'a' * 40,
                'source_tree': 'b' * 40, 'clean': True, 'run_id': 17, 'run_attempt': 1,
                'argv': ['npm', 'run', 'test:browser'], 'cwd': 'site', 'exit_code': 0,
                'tools': {tool: {'sha256': 'e' * 64, 'size': 42} for tool in ('node', 'npm', 'chrome')},
                'served_members': self.report['served_members'],
                'tests': self.docs.parse_playwright(self.raw_report())}

    @staticmethod
    def zip(name, content):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr(name, content)
        return stream.getvalue()

    def refresh_artifacts(self):
        self.data = {31: self.pages,
                     32: self.zip('docs-qualification.json', json.dumps(self.report).encode())}
        self.artifacts = [
            {'id': n, 'name': name, 'expired': False, 'size_in_bytes': len(self.data[n]),
             'digest': 'sha256:' + owner.digest(self.data[n]), 'created_at': STAMP,
             'workflow_run': {'id': 17, 'head_sha': 'a' * 40, 'head_branch': 'main',
                              'repository_id': 8, 'head_repository_id': 8}}
            for n, name in ((31, 'github-pages'), (32, 'major-docs-qualification-29'))]

    def api(self, path, binary=False):
        if path.startswith('actions/workflows/docs.yml/runs?'):
            return {'total_count': 1, 'workflow_runs': [self.run]}
        if path == 'actions/runs/17':
            return self.run
        if path == 'actions/runs/17/jobs?filter=latest&per_page=100':
            return {'total_count': 1, 'jobs': [self.job]}
        if path == 'actions/runs/17/artifacts?per_page=100':
            return {'total_count': 2, 'artifacts': self.artifacts}
        if path == 'actions/jobs/29/logs':
            rows = [owner.UPLOAD_ACTION,
                    'actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9',
                    'actions/upload-artifact@bbbca2ddaa5d8feaa63e36b76fdaad77386f024f']
            text = ''.join(STAMP + ' ##[group]Run ' + row + '\n' for row in rows)
            for item in self.artifacts:
                text += STAMP + ' SHA256 digest of uploaded artifact is ' + item['digest'][7:] + '\n'
                text += STAMP + ' Artifact ' + item['name'] + ' successfully finalized. Artifact ID ' + str(item['id']) + '\n'
            return text.encode()
        if path.startswith('actions/artifacts/') and path.endswith('/zip'):
            return self.data[int(path.split('/')[2])]
        raise AssertionError('unexpected metadata operation')

    def test_distinct_completed_docs_run_is_not_a_core_job(self):
        # A real Docs run/job must not be assigned the Core run's identity.
        with mock.patch.object(owner, 'api', side_effect=self.api):
            result = owner.produce(self.req, [], [{'id': 99, 'name': 'major readiness producer'}])
        self.assertEqual(result['schema'], 'codearbiter-major-readiness/2')
        self.assertEqual(result['ci_run_id'], 7)
        self.assertEqual(result['docs']['run_id'], 17)
        self.assertEqual(result['docs']['job_id'], 29)
        self.assertEqual(len(result['docs']['results']), len(CELLS))

    def test_playwright_actual_shape_and_finite_semantic_union(self):
        parsed = self.docs.parse_playwright(self.raw_report())
        self.assertEqual({row['name'] for row in parsed}, set(self.docs.SELECTORS))
        self.assertEqual(set(self.docs.CELL_SELECTORS), set(CELLS))
        self.assertEqual(self.docs.CELL_SELECTORS['disposition:machines:S62'], (0, 1, 2, 3, 4))
        self.assertEqual(self.docs.CELL_SELECTORS['disposition:findings:SF16'], (3, 4))

    def test_playwright_skip_retry_failure_duplicate_foreign_and_summary_refuse(self):
        def first(record):
            return record['suites'][0]['specs'][0]['tests'][0]
        mutations = [
            lambda r: r.update(errors=[{'message': 'failure'}]),
            lambda r: r['config']['projects'][0].update(name='firefox'),
            lambda r: r['config']['projects'][0].update(retries=1),
            lambda r: r['config'].update(forbidOnly=False),
            lambda r: r['suites'].pop(),
            lambda r: r['suites'].append(copy.deepcopy(r['suites'][0])),
            lambda r: r['suites'][0]['specs'][0].update(file='../foreign.ts'),
            lambda r: r['suites'][0]['specs'][0].update(file='/absolute.ts'),
            lambda r: first(r).update(status='skipped'),
            lambda r: first(r).update(expectedStatus='failed'),
            lambda r: first(r).update(projectId='other'),
            lambda r: first(r)['results'].append(copy.deepcopy(first(r)['results'][0])),
            lambda r: first(r)['results'][0].update(retry=1),
            lambda r: first(r)['results'][0].update(status='failed'),
            lambda r: first(r)['results'][0].update(errors=[{'message': 'failure'}]),
            lambda r: first(r)['results'][0].update(duration=float('nan')),
            lambda r: r['stats'].update(expected=len(r['suites']) + 1),
            lambda r: r['stats'].update(skipped=1),
        ]
        for index, mutation in enumerate(mutations):
            record = self.raw_report()
            mutation(record)
            with self.subTest(index=index), self.assertRaises(owner.ReadinessError):
                self.docs.parse_playwright(record)

    def test_actual_nested_describe_title_is_retained(self):
        record = self.raw_report()
        extra = copy.deepcopy(record['suites'][0]['specs'][0])
        extra.update(title='another assertion', id='another-case')
        record['suites'][0]['suites'] = [{'title': 'nested group', 'specs': [extra]}]
        record['stats']['expected'] += 1
        rows = self.docs.parse_playwright(record)
        self.assertIn('playwright:' + self.docs.PUB + ':chrome:nested group another assertion',
                      [row['name'] for row in rows])

    def test_producing_phase_uses_completed_upload_not_own_unavailable_log(self):
        run = dict(self.run, status='in_progress', conclusion=None)
        job = dict(self.job, status='in_progress', conclusion=None)
        req = dict(self.req, ci_run_id=17)
        with mock.patch.object(owner, 'api', side_effect=AssertionError('own job log is unavailable')):
            result = self.docs.report_from_observation(self.observation(), req, run, job,
                                                       self.artifacts[0], self.pages)
        self.assertEqual(result, self.report)
        bad = copy.deepcopy(job)
        bad['steps'][0]['conclusion'] = 'failure'
        with self.assertRaises(owner.ReadinessError):
            self.docs.report_from_observation(self.observation(), req, run, bad,
                                              self.artifacts[0], self.pages)

    def test_observed_payload_modes_bytes_source_tool_and_command_refuse_drift(self):
        req = dict(self.req, ci_run_id=17)
        run = dict(self.run, status='in_progress', conclusion=None)
        job = dict(self.job, status='in_progress', conclusion=None)
        mutations = [lambda r: r.update(source_tree='f' * 40), lambda r: r.update(clean=False),
                     lambda r: r.update(exit_code=1), lambda r: r.update(argv=['echo', 'passed']),
                     lambda r: r.update(run_attempt=2), lambda r: r['tools'].pop('chrome'),
                     lambda r: r['served_members'][0].update(mode=0o755),
                     lambda r: r['served_members'][0].update(sha256='0' * 64),
                     lambda r: r['tests'].pop()]
        for index, mutation in enumerate(mutations):
            observed = copy.deepcopy(self.observation())
            mutation(observed)
            with self.subTest(index=index), self.assertRaises(owner.ReadinessError):
                self.docs.report_from_observation(observed, req, run, job, self.artifacts[0], self.pages)

    def test_final_admission_requires_whole_success_and_original_both_uploads(self):
        for field, value in [('event', 'pull_request'), ('head_branch', 'major/state-contracts'),
                             ('head_sha', 'f' * 40), ('path', '.github/workflows/ci.yml'),
                             ('status', 'in_progress'), ('conclusion', 'failure'),
                             ('head_repository', {'id': 9, 'full_name': 'fork/repo'})]:
            original = self.run
            self.run = dict(original, **{field: value})
            with self.subTest(field=field), mock.patch.object(owner, 'api', side_effect=self.api), \
                 self.assertRaises(owner.ReadinessError):
                self.docs.admit(self.req, run_id=17)
            self.run = original
        for name in ('Upload Pages artifact', 'Upload Docs qualification report'):
            original = self.job
            self.job = copy.deepcopy(original)
            next(step for step in self.job['steps'] if step['name'] == name)['conclusion'] = 'skipped'
            with self.subTest(name=name), mock.patch.object(owner, 'api', side_effect=self.api), \
                 self.assertRaises(owner.ReadinessError):
                self.docs.admit(self.req, run_id=17)
            self.job = original

    def test_wrong_report_archive_attempt_expiry_and_tar_refuse(self):
        changes = [lambda: self.report.update(source_tree='f' * 40),
                   lambda: self.report.update(docs_run_id=7),
                   lambda: self.report.update(run_attempt=2),
                   lambda: self.report.update(tar_sha256='0' * 64),
                   lambda: self.report.update(served_members=[]),
                   lambda: self.report.update(extra='unadmitted')]
        original = copy.deepcopy(self.report)
        for index, change in enumerate(changes):
            change()
            self.refresh_artifacts()
            with self.subTest(index=index), mock.patch.object(owner, 'api', side_effect=self.api), \
                 self.assertRaises(owner.ReadinessError):
                self.docs.admit(self.req, run_id=17)
            self.report = copy.deepcopy(original)
        self.refresh_artifacts()
        self.artifacts[0]['expired'] = True
        with mock.patch.object(owner, 'api', side_effect=self.api), self.assertRaises(owner.ReadinessError):
            self.docs.admit(self.req, run_id=17)

    def test_ambiguous_docs_discovery_and_broadened_cell_scope_refuse(self):
        def api(path, binary=False):
            if path.startswith('actions/workflows/'):
                return {'total_count': 2, 'workflow_runs': [self.run, dict(self.run, id=18)]}
            return self.api(path, binary)
        with mock.patch.object(owner, 'api', side_effect=api), self.assertRaises(owner.ReadinessError):
            self.docs.admit(self.req)
        for cell in ('installed:pi:linux:1.5.0', 'task:SITE-U02'):
            req = copy.deepcopy(self.req)
            req['cell_jobs'][cell] = JOB
            req['cells'].append(cell)
            with self.assertRaises(owner.ReadinessError):
                owner.produce(req, [], [])

    def test_observer_runs_original_command_once_and_retains_list_plus_json_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / 'site/dist').mkdir(parents=True)
            (root / 'site/dist/index.html').write_bytes(b'served')
            (root / 'node').write_bytes(b'node')
            (root / 'npm').write_bytes(b'npm')
            (root / 'chrome').write_bytes(b'chrome')
            identity = {'source_commit': 'a' * 40, 'source_tree': 'b' * 40, 'clean': True}
            calls = []
            def run(argv, **kwargs):
                calls.append((argv, kwargs))
                self.assertEqual(argv, [str(root / 'npm'), 'run', 'test:browser'])
                self.assertEqual(kwargs['cwd'], root / 'site')
                self.assertNotIn('GH_TOKEN', kwargs['env'])
                pathlib.Path(kwargs['env']['CA_DOCS_PLAYWRIGHT_JSON']).write_text(
                    json.dumps(self.raw_report()), encoding='utf-8')
                return mock.Mock(returncode=0)
            with mock.patch.dict(os.environ, {'GITHUB_RUN_ID': '17', 'GITHUB_RUN_ATTEMPT': '1'}, clear=True), \
                 mock.patch.object(self.docs.reports, 'source_identity', return_value=identity), \
                 mock.patch.object(self.docs.shutil, 'which', side_effect=lambda name: str(root / name)), \
                 mock.patch.object(self.docs.subprocess, 'run', side_effect=run):
                self.assertEqual(self.docs.observe(root, root / 'result.json', browser_binary=root / 'chrome'), 0)
            self.assertEqual(len(calls), 1)
            observed = json.loads((root / 'result.json').read_text())
            self.assertEqual(observed['exit_code'], 0)
            self.assertEqual(len(observed['tests']), len(self.docs.SELECTORS))
            self.assertEqual(observed['served_members'][0]['sha256'], owner.digest(b'served'))

    def test_envelope_keeps_actual_core_verifier_main_success_and_q03_guards(self):
        core_req = self.docs.core_requirements(self.req)
        core_req.update(cells=['scenario:SEQ-01'], cell_jobs={'scenario:SEQ-01': 'original core job'},
                        required_artifact_names=['qualified-payload'])
        req = copy.deepcopy(core_req)
        req['cells'] += CELLS
        req['cell_jobs'].update(dict.fromkeys(CELLS, JOB))
        core = {'schema': owner.SCHEMA, 'program_id': owner.PROGRAM, 'state': 'PREPUBLICATION_READY',
                **core_req, 'producer_job_id': 99,
                'results': [{'cell': 'scenario:SEQ-01', 'result': 'PASSED', 'job_id': 20,
                             'evidence_artifact_id': 12}],
                'artifacts': [{'artifact_id': 12, 'archive_sha256': '1' * 64,
                               'members': [{'path': 'package', 'sha256': '2' * 64}]}]}
        record = {'schema': self.docs.ENVELOPE, 'program_id': owner.PROGRAM,
                  'state': 'PREPUBLICATION_READY', **req, 'core': core, 'docs': {'run_id': 17}}
        run = {'id': 7, 'head_sha': 'a' * 40, 'head_branch': 'main', 'event': 'push',
               'path': '.github/workflows/ci.yml', 'conclusion': 'success',
               'repository': {'full_name': owner.REPOSITORY}}
        artifact = {'id': 11, 'name': 'major-readiness-' + 'a' * 40, 'expired': False,
                    'size_in_bytes': 42, 'digest': 'sha256:' + 'f' * 64,
                    'workflow_run': {'id': 7, 'head_sha': 'a' * 40}}
        payload = {'id': 12, 'name': 'qualified-payload', 'expired': False,
                   'size_in_bytes': 42, 'digest': 'sha256:' + '1' * 64,
                   'workflow_run': {'id': 7, 'head_sha': 'a' * 40}}
        args = dict(record=record, requirements=req, run=run, artifact=artifact,
                    archive_digest='f' * 64, jobs=[
                        {'id': 20, 'name': 'original core job', 'conclusion': 'success'},
                        {'id': 99, 'name': 'major readiness producer', 'conclusion': 'success'}],
                    build_artifacts=[payload], payload_members={12: core['artifacts'][0]['members']})
        with mock.patch.object(self.docs, 'admit', return_value=record['docs']), \
             mock.patch.object(owner, 'validate_upload'):
            self.assertEqual(owner.verify(**args)['docs_run_id'], 17)
            for field, value in [('head_branch', 'major/state-contracts'), ('event', 'pull_request'),
                                 ('conclusion', 'failure'), ('head_sha', 'e' * 40)]:
                with self.subTest(field=field), self.assertRaises(owner.ReadinessError):
                    owner.verify(**dict(args, run=dict(run, **{field: value})))
            args['record']['core']['task_ids'] = ['Q-03']
            args['requirements']['task_ids'] = ['Q-03']
            args['record']['task_ids'] = ['Q-03']
            with self.assertRaisesRegex(owner.ReadinessError, 'Q-03'):
                owner.verify(**args)

    def test_promotion_stages_exact_original_tar_only_after_verified_current_main(self):
        with mock.patch.object(owner, 'api', side_effect=self.api):
            admitted = self.docs.admit(self.req)
        record = {'schema': self.docs.ENVELOPE, 'source_tree': 'b' * 40, 'docs': admitted}
        verified = {'state': 'PREPUBLICATION_READY', 'docs_run_id': 17}
        env = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
               'GITHUB_REF': 'refs/heads/main', 'GITHUB_REPOSITORY': owner.REPOSITORY,
               'GITHUB_SHA': 'a' * 40}
        identity = {'source_commit': 'a' * 40, 'source_tree': 'b' * 40, 'clean': True}
        def api(path, binary=False):
            if path == 'actions/artifacts/31':
                return self.artifacts[0]
            return self.api(path, binary)
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory).resolve()
            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(self.docs.reports, 'source_identity', return_value=identity), \
                 mock.patch.object(owner, 'load_verified_receipt', return_value=(record, verified)) as verifier, \
                 mock.patch.object(owner, 'api', side_effect=api), \
                 mock.patch.object(self.docs.subprocess, 'run', side_effect=AssertionError('no rebuild')):
                result = self.docs.prepare_promotion(root, 'a' * 40, 7, root / 'stage')
                self.assertEqual((root / 'stage/artifact.tar').read_bytes(), self.tar)
                self.assertEqual([p.name for p in (root / 'stage').iterdir()], ['artifact.tar'])
                self.assertFalse(result['deployment_observed'])
                self.assertEqual(result['original_pages_artifact_id'], 31)
                verifier.assert_called_once_with(root, 'a' * 40, 7)
                for key, value in [('GITHUB_REF', 'refs/heads/major/state-contracts'),
                                   ('GITHUB_SHA', 'e' * 40), ('GITHUB_EVENT_NAME', 'push')]:
                    with mock.patch.dict(os.environ, {key: value}), self.subTest(key=key), \
                         self.assertRaises(owner.ReadinessError):
                        self.docs.prepare_promotion(root, 'a' * 40, 7, root / 'refused')
                    self.assertFalse((root / 'refused').exists())
                wrong = copy.deepcopy(record)
                wrong['docs']['pages']['tar_sha256'] = '0' * 64
                with mock.patch.object(owner, 'load_verified_receipt', return_value=(wrong, verified)), \
                     self.assertRaises(owner.ReadinessError):
                    self.docs.prepare_promotion(root, 'a' * 40, 7, root / 'wrong-bytes')
                self.assertFalse((root / 'wrong-bytes').exists())

    def test_source_manifest_refuses_symlink_and_includes_all_extra_served_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / 'index.html').write_bytes(b'one')
            first = self.docs.served_snapshot(root)
            (root / 'extra.html').write_bytes(b'two')
            second = self.docs.served_snapshot(root)
            self.assertNotEqual(first, second)
            self.assertEqual({row['path'] for row in second}, {'extra.html', 'index.html'})
            with mock.patch.object(pathlib.Path, 'is_symlink', return_value=True), \
                 self.assertRaises(owner.ReadinessError):
                self.docs.served_snapshot(root)

    def test_actual_observer_before_after_refuses_owned_source_tool_or_served_mutation(self):
        for subject in ('source', 'tool', 'served'):
            with self.subTest(subject=subject), tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory)
                (root / 'site/dist').mkdir(parents=True)
                (root / 'site/dist/index.html').write_bytes(b'before')
                for tool in ('node', 'npm', 'chrome'):
                    (root / tool).write_bytes(tool.encode())
                before = {'source_commit': 'a' * 40, 'source_tree': 'b' * 40, 'clean': True}
                after = dict(before, clean=False) if subject == 'source' else before
                def run(argv, **kwargs):
                    pathlib.Path(kwargs['env']['CA_DOCS_PLAYWRIGHT_JSON']).write_text(
                        json.dumps(self.raw_report()), encoding='utf-8')
                    if subject == 'tool':
                        (root / 'chrome').write_bytes(b'changed browser')
                    elif subject == 'served':
                        (root / 'site/dist/index.html').write_bytes(b'changed served bytes')
                    return mock.Mock(returncode=0)
                with mock.patch.dict(os.environ, {'GITHUB_RUN_ID': '17', 'GITHUB_RUN_ATTEMPT': '1'}, clear=True), \
                     mock.patch.object(self.docs.reports, 'source_identity', side_effect=[before, after]), \
                     mock.patch.object(self.docs.shutil, 'which', side_effect=lambda name: str(root / name)), \
                     mock.patch.object(self.docs.subprocess, 'run', side_effect=run), \
                     self.assertRaises(owner.ReadinessError):
                    self.docs.observe(root, root / 'refused.json', browser_binary=root / 'chrome')
                self.assertFalse((root / 'refused.json').exists())

    def test_linked_original_reporter_output_refuses_before_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / 'site/dist').mkdir(parents=True)
            (root / 'site/dist/index.html').write_bytes(b'served')
            for tool in ('node', 'npm', 'chrome'):
                (root / tool).write_bytes(tool.encode())
            seed = root / 'raw-seed.json'
            seed.write_text(json.dumps(self.raw_report()), encoding='utf-8')
            def run(argv, **kwargs):
                os.link(seed, kwargs['env']['CA_DOCS_PLAYWRIGHT_JSON'])
                return mock.Mock(returncode=0)
            with mock.patch.dict(os.environ, {'GITHUB_RUN_ID': '17', 'GITHUB_RUN_ATTEMPT': '1'}, clear=True), \
                 mock.patch.object(self.docs.reports, 'source_identity', return_value={
                     'source_commit': 'a' * 40, 'source_tree': 'b' * 40, 'clean': True}), \
                 mock.patch.object(self.docs.shutil, 'which', side_effect=lambda name: str(root / name)), \
                 mock.patch.object(self.docs.subprocess, 'run', side_effect=run), \
                 self.assertRaises(owner.ReadinessError):
                self.docs.observe(root, root / 'refused.json', browser_binary=root / 'chrome')
            self.assertFalse((root / 'refused.json').exists())

    def test_duplicate_report_fields_and_wrong_original_log_refuse(self):
        duplicate = json.dumps(self.report).removesuffix('}') + ',"run_attempt":1}'
        self.data[32] = self.zip('docs-qualification.json', duplicate.encode())
        self.artifacts[1].update(digest='sha256:' + owner.digest(self.data[32]), size_in_bytes=len(self.data[32]))
        with mock.patch.object(owner, 'api', side_effect=self.api), self.assertRaises(ValueError):
            self.docs.admit(self.req, run_id=17)
        self.refresh_artifacts()
        def api(path, binary=False):
            if path == 'actions/jobs/29/logs':
                return self.api(path, binary).replace(b'Artifact ID 31', b'Artifact ID 310')
            return self.api(path, binary)
        with mock.patch.object(owner, 'api', side_effect=api), self.assertRaises(owner.ReadinessError):
            self.docs.admit(self.req, run_id=17)

    def test_transfer_readback_checks_current_owned_upload_without_own_incomplete_log(self):
        lineage = {'format': 'codearbiter-qualified-pages-transfer/1', 'source_commit': 'a' * 40,
                   'source_tree': 'b' * 40, 'core_run_id': 7, 'docs_run_id': 17, 'docs_job_id': 29,
                   'original_pages_artifact_id': 31, 'original_pages_archive_sha256': owner.digest(self.pages),
                   'tar_sha256': owner.digest(self.tar), 'served_members': self.report['served_members'],
                   'state': 'QUALIFIED_BYTES_STAGED', 'deployment_observed': False}
        run = dict(self.run, id=27, event='workflow_dispatch', status='in_progress', conclusion=None)
        job = {'id': 41, 'run_id': 27, 'run_attempt': 1, 'name': 'Site | [Prepare] - Qualified Pages',
               'status': 'in_progress', 'conclusion': None, 'steps': [{
                   'name': 'Upload the exact qualified Pages tar', 'status': 'completed', 'conclusion': 'success'}]}
        artifact = dict(self.artifacts[0], id=51, workflow_run=dict(self.artifacts[0]['workflow_run'], id=27))
        env = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
               'GITHUB_REF': 'refs/heads/main', 'GITHUB_REPOSITORY': owner.REPOSITORY,
               'GITHUB_SHA': 'a' * 40, 'GITHUB_RUN_ID': '27', 'GITHUB_RUN_ATTEMPT': '1'}
        def api(path, binary=False):
            if path == 'actions/runs/27':
                return run
            if path == 'actions/runs/27/jobs?filter=latest&per_page=100':
                return {'total_count': 1, 'jobs': [job]}
            if path == 'actions/runs/27/artifacts?per_page=100':
                return {'total_count': 1, 'artifacts': [artifact]}
            if path == 'actions/artifacts/51/zip':
                return self.pages
            raise AssertionError('no incomplete job log or unapproved API operation')
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            original = root / 'lineage.json'
            original.write_text(json.dumps(lineage), encoding='utf-8')
            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(self.docs.reports, 'source_identity', return_value={
                     'source_commit': 'a' * 40, 'source_tree': 'b' * 40, 'clean': True}), \
                 mock.patch.object(owner, 'api', side_effect=api):
                result = self.docs.verify_transfer(root, original, root / 'readback.json')
                self.assertEqual(result['artifact_id'], 51)
                self.assertEqual(result['original_pages_artifact_id'], 31)
                self.assertEqual(result['state'], 'QUALIFIED_BYTES_TRANSFERRED')
                self.assertFalse(result['deployment_observed'])
                lineage['tar_sha256'] = '0' * 64
                original.write_text(json.dumps(lineage), encoding='utf-8')
                with self.assertRaises(owner.ReadinessError):
                    self.docs.verify_transfer(root, original, root / 'wrong.json')
                self.assertFalse((root / 'wrong.json').exists())

    def test_windows_descriptor_ignores_only_synthetic_execute_bits(self):
        # Real owned bytes, controlled portable metadata: Windows path stat
        # supplies filename-derived execute bits absent from descriptor stat.
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(prefix='ca-docs-descriptor-') as folder:
            path = pathlib.Path(folder).resolve() / 'owned.exe'
            payload = b'owned bytes; never executed'
            path.write_bytes(payload)
            actual = path.lstat()
            fields = ('st_dev', 'st_ino', 'st_nlink', 'st_size', 'st_mtime_ns')
            base = {key: getattr(actual, key) for key in fields}
            base['st_file_attributes'] = getattr(actual, 'st_file_attributes', 0)

            def info(mode, **changes):
                return SimpleNamespace(**dict(base, st_mode=mode, **changes))

            class MetadataPath:
                def __init__(self, initial, final=None):
                    self.states = [initial, final or initial]
                    self.index = 0
                def __fspath__(self):
                    return str(path)
                def is_symlink(self):
                    return False
                def lstat(self):
                    value = self.states[min(self.index, 1)]
                    self.index += 1
                    return value

            pathname = info(0o100777)
            descriptor = info(0o100666)
            with mock.patch.object(self.docs.os, 'name', 'nt'), \
                 mock.patch.object(self.docs.os, 'fstat', return_value=descriptor):
                raw, observed = self.docs._regular(MetadataPath(pathname), len(payload))
            self.assertEqual(raw, payload)
            self.assertEqual(observed.st_mode, 0o100777)

            vectors = (
                ('posix-permissions', 'posix', descriptor, pathname),
                ('write-permissions', 'nt', info(0o100644), pathname),
                ('descriptor-type', 'nt', info(0o040666), pathname),
                ('descriptor-links', 'nt', info(0o100666, st_nlink=2), pathname),
                ('descriptor-inode', 'nt', info(0o100666, st_ino=actual.st_ino + 1), pathname),
                ('descriptor-size', 'nt', info(0o100666, st_size=len(payload) + 1), pathname),
                ('descriptor-mtime', 'nt', info(0o100666, st_mtime_ns=actual.st_mtime_ns + 1), pathname),
                ('path-execute-change', 'nt', descriptor, info(0o100666)),
                ('path-reparse', 'nt', descriptor, info(0o100777, st_file_attributes=0x400)),
            )
            for name, platform, opened, final in vectors:
                with self.subTest(vector=name), mock.patch.object(self.docs.os, 'name', platform), \
                     mock.patch.object(self.docs.os, 'fstat', return_value=opened):
                    with self.assertRaises(owner.ReadinessError):
                        self.docs._regular(MetadataPath(pathname, final), len(payload))

    def test_owned_executable_named_file_is_read_without_execution(self):
        with tempfile.TemporaryDirectory(prefix='ca-docs-owned-tool-') as folder:
            for suffix in ('.exe', '.cmd', '.json'):
                path = pathlib.Path(folder).resolve() / ('owned' + suffix)
                path.write_bytes(b'owned tiny file')
                raw, before = self.docs._regular(path, 64)
                self.assertEqual(raw, b'owned tiny file')
                self.assertEqual(before, path.lstat())

    def test_input_growth_during_read_never_consumes_unbounded_bytes(self):
        # Growth after the metadata check must refuse within the read budget.
        with tempfile.TemporaryDirectory(prefix='ca-docs-read-growth-') as folder:
            path = pathlib.Path(folder) / 'owned.json'
            path.write_bytes(b'12345678')
            original_open, original_fdopen = pathlib.Path.open, os.fdopen
            reads = []

            class GrowingRead:
                def __init__(self, stream):
                    self.stream = stream

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return self.stream.__exit__(*args)

                def fileno(self):
                    return self.stream.fileno()

                def read(self, size=-1):
                    with original_open(path, 'ab') as writer:
                        writer.write(b'continued-growth')
                    reads.append(size)
                    if size < 0 or size > 9:
                        raise AssertionError('input growth caused an unbounded read')
                    return self.stream.read(size)

            def guarded_open(target, mode='r', *args, **kwargs):
                stream = original_open(target, mode, *args, **kwargs)
                return GrowingRead(stream) if target == path and mode == 'rb' else stream

            def guarded_fdopen(descriptor, *args, **kwargs):
                return GrowingRead(original_fdopen(descriptor, *args, **kwargs))

            with mock.patch.object(pathlib.Path, 'open', guarded_open), \
                    mock.patch.object(os, 'fdopen', guarded_fdopen):
                with self.assertRaises(owner.ReadinessError):
                    self.docs._regular(path, 8)
            self.assertTrue(reads)
            self.assertTrue(all(0 < size <= 9 for size in reads))

    def test_bookmark_and_directory_cells_use_exact_original_chrome_results(self):
        repo = pathlib.Path(__file__).resolve().parents[2]
        history = repo / 'docs/state-contracts-major/execution/evidence/site-bookmark-directory-d482-docs'
        report = json.loads((history / 'raw/original-docs-qualification.json').read_bytes())
        outcomes = {item['name'].split(':', 3)[3]: item['name'] for item in report['observation']['tests']
                    if item['result'] == 'PASSED'}
        expected = {}
        for section in ('bookmark', 'directory'):
            receipt = json.loads((history / f'{section}-hosted-tested.json').read_bytes())
            for row in receipt['per_cell_assertion_mapping']:
                expected[row['cell']] = [outcomes[name] for name in row['observed_named_cases']]
        self.assertEqual(len(expected), 7)
        policy = json.loads((repo / '.github/major-qualification-policy.json').read_bytes())
        self.assertEqual({cell: policy['cell_job_bindings'].get(cell) for cell in expected}, dict.fromkeys(expected, JOB))
        with mock.patch.object(owner, 'api', side_effect=self.api):
            actual = self.docs.admit(self.req, run_id=17)['results']
        self.assertEqual({row['cell']: row['selectors'] for row in actual if row['cell'] in expected}, expected)
        missing = self.docs.SELECTORS[self.docs.CELL_SELECTORS['disposition:transitions:S56:04'][0]]
        self.report['observation']['tests'] = [row for row in self.report['observation']['tests']
                                               if row['name'] != missing]
        self.refresh_artifacts()
        with mock.patch.object(owner, 'api', side_effect=self.api):
            with self.assertRaisesRegex(owner.ReadinessError, 'Docs required assertion missing'):
                self.docs.admit(self.req, run_id=17)

    def test_selection_fragment_and_non_circular_workflow_retain_original_authority(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        fragment = json.loads((root / '.github/major-test-selections.json').read_text())
        self.docs.validate_selection_map(fragment)
        selected = next(group for group in fragment['groups'] if group['job'] == JOB)
        selected['selectors'].pop()
        with self.assertRaises(owner.ReadinessError):
            self.docs.validate_selection_map(fragment)
        workflow = (root / '.github/workflows/docs.yml').read_text()
        build = workflow.split('  build:\n', 1)[1].split('  deploy:\n', 1)[0]
        prepare = workflow.split('  qualified-pages:\n', 1)[1].split('  deploy-qualified:\n', 1)[0]
        deploy = workflow.split('  deploy-qualified:\n', 1)[1]
        self.assertIn('id: browser-gate', build)
        self.assertIn('site_playwright_observation.py observe --repo ..', build)
        from test_ci_impact import SiteBrowserPublicationWorkflowTest
        import re
        closed_build = re.sub(r'(?m)\s+#.*$', '', '  build:\n' + build)
        workflow_guard = SiteBrowserPublicationWorkflowTest()
        workflow_guard._assert_build_control_flow(closed_build)
        self.assertEqual(workflow_guard._build_commands(closed_build).count('npm run test:components'), 1)
        self.assertIn('npm run test:browser\n', build)
        component = closed_build.split('      - name: Browser component acceptance\n', 1)[1].split('      - name:', 1)[0]
        publication = closed_build.split('      - name: Browser publication gate\n', 1)[1].split('      - name:', 1)[0]
        keys = [line.strip().partition(':')[0] for line in (component + publication).splitlines()]
        self.assertNotIn('GH_TOKEN', keys)
        self.assertNotIn('pages: write', prepare)
        self.assertNotIn('id-token: write', prepare)
        self.assertIn('prepare-promotion', prepare)
        self.assertNotIn('npm ', prepare)
        self.assertIn('qualified-pages/artifact.tar', prepare)
        self.assertIn('needs: qualified-pages', deploy)
        self.assertIn("github.ref == 'refs/heads/main'", deploy)
        self.assertIn('actions/deploy-pages@368f82528645a54fb793d4d04e342629a3f51346', deploy)
        self.assertNotIn('checkout@', deploy)
        self.assertIn("needs.build.outputs.program_candidate != 'true'", workflow)
        config = (root / 'site/playwright.config.ts').read_text()
        self.assertIn('[["list"], ["json", { outputFile:', config)
        self.assertIn('retries: 0', config)
        self.assertIn('timeout: 30_000', config)


if __name__ == '__main__':
    unittest.main()
