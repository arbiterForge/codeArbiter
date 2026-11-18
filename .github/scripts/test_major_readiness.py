"""Q-02's noncircular, exact-source release barrier."""
import copy
import importlib.util
import io
import json
import sys
import subprocess
import unittest
from unittest import mock
import zipfile
import warnings
from pathlib import Path

path = Path(__file__).with_name("major_readiness.py")
import major_readiness as owner
# Reuse the owning module across combined suites so inert API patches also
# cover dynamic consumers; replacing sys.modules splits their mock boundaries.
if Path(owner.__file__).resolve() != path.resolve():
    raise RuntimeError("readiness test owner resolved outside its source directory")


class ReadinessTest(unittest.TestCase):
    def setUp(self):
        self.source = "a" * 40
        self.marker = {'schema': 'codearbiter-integration-candidate/1', 'branch': 'major/state-contracts',
                       'baseline_main_commit': self.source,
                       'candidates': {'ca': '4.0.0', 'ca-codex': '0.30.0', 'ca-pi': '0.30.0', 'ca-sandbox': '0.2.0'}}
        self.requirements = {
            "source_commit": self.source, "source_tree": "b" * 40,
            "ci_run_id": 7, "task_ids": ["P-00", "Q-01", "Q-02"],
            "task_manifest_sha256": "c" * 64, "dispositions_sha256": "d" * 64,
            "decisions_sha256": "e" * 64,
            "targets": [{"target": "ca", "version": "4.0.0", "tag": "v4.0.0"}],
            "cells": ["scenario:SEQ-01", "installed:pi:linux:1.5.0"],
            "required_artifact_names": ["qualified-payload"],
        }
        self.run = {"id": 7, "head_sha": self.source, "head_branch": "main",
                    "event": "push", "conclusion": "success", "path": ".github/workflows/ci.yml",
                    "repository": {"full_name": owner.REPOSITORY}}
        self.artifact = {"id": 11, "name": "major-readiness-" + self.source,
                         "size_in_bytes": 100,
                         "expired": False, "digest": "sha256:" + "f" * 64,
                         "workflow_run": {"id": 7, "head_sha": self.source}}
        self.record = {"schema": owner.SCHEMA, "program_id": owner.PROGRAM,
                       "producer_job_id": 99,
                       "state": "PREPUBLICATION_READY", **copy.deepcopy(self.requirements),
                       "artifacts": [{"artifact_id": 12, "archive_sha256": "1" * 64,
                                      "members": [{"path": "ca.tar.gz", "sha256": "2" * 64}]}],
                       "results": [{"cell": cell, "result": "PASSED", "job_id": i + 20,
                                    "evidence_artifact_id": 12}
                                   for i, cell in enumerate(self.requirements["cells"])]}
        self.jobs = [{"id": i + 20, "name": "major qualification / " + cell,
                      "conclusion": "success"} for i, cell in enumerate(self.requirements["cells"])]
        self.jobs.append({'id': 99, 'name': 'major readiness producer', 'conclusion': 'success'})
        self.requirements["cell_jobs"] = {cell: "major qualification / " + cell for cell in self.requirements["cells"]}
        self.record["cell_jobs"] = copy.deepcopy(self.requirements["cell_jobs"])
        self.build_artifacts = [{"id": 12, "expired": False, "name": "qualified-payload",
                                 "size_in_bytes": 100,
                                 "digest": "sha256:" + "1" * 64,
                                 "workflow_run": {"id": 7, "head_sha": self.source}}]

    def verify(self, **changes):
        args = dict(record=self.record, requirements=self.requirements, run=self.run,
                    artifact=self.artifact, archive_digest="f" * 64, jobs=self.jobs,
                    build_artifacts=self.build_artifacts)
        args.update(changes)
        with mock.patch.object(owner, 'validate_upload'):
            return owner.verify(**args)

    def test_valid_receipt_is_non_circular(self):
        self.assertNotIn("Q-03", self.record["task_ids"])
        self.assertEqual(self.verify()["state"], "PREPUBLICATION_READY")

    def test_publication_task_cannot_enter_prepublication_population(self):
        self.requirements["task_ids"].append("Q-03")
        self.record["task_ids"].append("Q-03")
        with self.assertRaisesRegex(owner.ReadinessError, "Q-03"):
            self.verify()

    def test_wrong_source_tree_run_and_manifests_refuse(self):
        for field in ("source_commit", "source_tree", "ci_run_id", "task_manifest_sha256",
                      "dispositions_sha256", "decisions_sha256", "targets", "task_ids"):
            record = copy.deepcopy(self.record)
            record[field] = "wrong"
            with self.subTest(field=field), self.assertRaises(owner.ReadinessError):
                self.verify(record=record)

    def test_forged_untrusted_run_refuses(self):
        for field, value in [("event", "pull_request"), ("head_branch", "major/state-contracts"),
                             ("conclusion", "failure"), ("path", ".github/workflows/evil.yml"),
                             ("repository", {"full_name": "fork/codeArbiter"})]:
            run = dict(self.run, **{field: value})
            with self.subTest(field=field), self.assertRaises(owner.ReadinessError):
                self.verify(run=run)

    def test_missing_expired_wrong_archive_refuses(self):
        for artifact in (None, dict(self.artifact, expired=True),
                         dict(self.artifact, digest="sha256:" + "0" * 64),
                         dict(self.artifact, workflow_run={"id": 8, "head_sha": self.source})):
            with self.subTest(artifact=artifact), self.assertRaises(owner.ReadinessError):
                self.verify(artifact=artifact)

    def test_unknown_skipped_missing_duplicate_cells_refuse(self):
        for result in ("SKIPPED", "UNAVAILABLE", "NOT_RUN", "UNKNOWN", "FAILED"):
            record = copy.deepcopy(self.record)
            record["results"][0]["result"] = result
            with self.subTest(result=result), self.assertRaises(owner.ReadinessError):
                self.verify(record=record)
        for rows in ([], self.record["results"] * 2,
                     [dict(self.record["results"][0], cell="scenario:unknown")]):
            record = dict(self.record, results=rows)
            with self.assertRaises(owner.ReadinessError):
                self.verify(record=record)

    def test_caller_pass_cannot_replace_successful_named_job(self):
        for jobs in ([], [dict(job, conclusion="skipped") for job in self.jobs],
                     [dict(job, name="arbitrary") for job in self.jobs]):
            with self.assertRaises(owner.ReadinessError):
                self.verify(jobs=jobs)

    def test_wrong_or_expired_payload_artifact_refuses(self):
        for artifacts in ([], [dict(self.build_artifacts[0], expired=True)],
                          [dict(self.build_artifacts[0], digest="sha256:" + "9" * 64)]):
            with self.assertRaises(owner.ReadinessError):
                self.verify(build_artifacts=artifacts)

    def test_distributed_settlement_is_not_prepublication(self):
        with self.assertRaises(owner.ReadinessError):
            self.verify(record=dict(self.record, state="DISTRIBUTION_SETTLED"))

    def test_exact_member_readback_is_required_by_live_verification(self):
        with self.assertRaisesRegex(owner.ReadinessError, "members differ"):
            self.verify(payload_members={12: [{"path": "ca.tar.gz", "sha256": "0" * 64}]})
        self.assertEqual(self.verify(payload_members={12: self.record["artifacts"][0]["members"]})["state"],
                         "PREPUBLICATION_READY")

    def test_unsettled_version_mismatch_never_bypasses_major_qualification(self):
        with mock.patch.object(owner, "blob", return_value=json.dumps(self.marker).encode()):
            with self.assertRaises(owner.ReadinessError):
                owner.applies(Path('.'), self.source, 'ca', '4.0.1', 'publish')
            with self.assertRaises(owner.ReadinessError):
                owner.applies(Path('.'), self.source, 'ca', '4.0.1', 'receipt')

    def test_receipt_only_does_not_repeat_publication(self):
        with mock.patch.object(owner, "blob", return_value=json.dumps(self.marker).encode()):
            self.assertFalse(owner.applies(Path('.'), self.source, 'ca', '4.0.0', 'receipt'))
            self.assertTrue(owner.applies(Path('.'), self.source, 'ca', '4.0.0', 'tag draft asset channel publish receipt'))
            self.assertTrue(owner.applies(Path('.'), self.source, 'ca', '4.0.0', 'asset channel publish receipt'))

    def test_malformed_marker_is_not_an_ordinary_release_escape(self):
        for marker in (b'not JSON', b'[]', b'{}', json.dumps(dict(self.marker, candidates={'ca': '4.0.0'})).encode()):
            with mock.patch.object(owner, 'blob', return_value=marker):
                with self.assertRaises(owner.ReadinessError):
                    owner.applies(Path('.'), self.source, 'ca', '4.0.1', 'publish')

    def test_matching_candidate_without_required_readiness_remains_pending(self):
        with mock.patch.object(owner, 'blob', return_value=json.dumps(self.marker).encode()), \
             mock.patch.object(owner, 'collect', return_value=(self.requirements, self.run, [], self.jobs)), \
             mock.patch('sys.stderr', new_callable=io.StringIO) as err:
            self.assertEqual(owner.main(['verify', '--source', self.source, '--ci-run-id', '7',
                                         '--target', 'ca', '--version', '4.0.0']), 1)
            self.assertIn('exactly one retained major-readiness artifact required', err.getvalue())

    def test_producer_requires_original_executed_reports(self):
        reports = {}
        for i, cell in enumerate(self.requirements['cells']):
            reports['major-qualification-' + str(20+i)] = {
                'schema': 'codearbiter-major-qualification/1', 'source_commit': self.source,
                'source_tree': self.requirements['source_tree'], 'ci_run_id': 7, 'job_id': 20+i,
                'results': [{'cell': cell, 'result': 'PASSED', 'commands': [{'argv': ['actual-check'], 'exit_code': 0}],
                             'selected_population': 3, 'executed_population': 3, 'payload_artifact_id': 12}]}
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as z:
            z.writestr('ca.tar.gz', b'exact package')
        content = output.getvalue()
        for report in reports.values():
            report['results'][0]['payload_archive_sha256'] = owner.digest(content)
            report['results'][0]['payload_members'] = owner.members(content)
        artifacts = [dict(self.build_artifacts[0], digest='sha256:' + owner.digest(content))]
        artifacts += [{'id': 30+i, 'name': name} for i, name in enumerate(reports)]
        with mock.patch.object(owner, 'read_artifact_json', side_effect=lambda a, req, filename: reports[a['name']]), \
             mock.patch.object(owner, 'validate_upload'), \
             mock.patch.object(owner, 'api', return_value=content):
            record = owner.produce(self.requirements, artifacts, self.jobs)
            self.assertEqual(len(record['results']), 2)
            self.assertEqual(record['artifacts'][0]['members'][0]['sha256'], owner.digest(b'exact package'))
            reports[next(iter(reports))]['results'][0]['payload_archive_sha256'] = '0' * 64
            with self.assertRaisesRegex(owner.ReadinessError, 'qualification bytes differ'):
                owner.produce(self.requirements, artifacts, self.jobs)
            reports[next(iter(reports))]['results'][0]['payload_archive_sha256'] = owner.digest(content)
            reports[next(iter(reports))]['results'][0]['executed_population'] = 0
            with self.assertRaisesRegex(owner.ReadinessError, 'affirmative executed'):
                owner.produce(self.requirements, artifacts, self.jobs)

    def test_producer_refuses_reports_without_the_named_jobs_upload_step(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as z:
            z.writestr('ca.tar.gz', b'exact package')
        content = output.getvalue()
        reports = {}
        artifacts = [dict(self.build_artifacts[0], digest='sha256:' + owner.digest(content))]
        for i, cell in enumerate(self.requirements['cells']):
            name = 'major-qualification-' + str(20+i)
            artifacts.append({'id': 30+i, 'name': name})
            reports[name] = {'schema': 'codearbiter-major-qualification/1', 'source_commit': self.source,
                'source_tree': self.requirements['source_tree'], 'ci_run_id': 7, 'job_id': 20+i,
                'results': [{'cell': cell, 'result': 'PASSED', 'commands': [{'argv': ['actual-check'], 'exit_code': 0}],
                    'selected_population': 3, 'executed_population': 3, 'payload_artifact_id': 12,
                    'payload_archive_sha256': owner.digest(content), 'payload_members': owner.members(content)}]}
        with mock.patch.object(owner, 'read_artifact_json', side_effect=lambda a, req, filename: reports[a['name']]), \
             mock.patch.object(owner, 'api', return_value=content):
            with self.assertRaises(owner.ReadinessError):
                owner.produce(self.requirements, artifacts, self.jobs)

    def test_interned_report_payloads_preserve_exact_archive_and_member_admission(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as z:
            z.writestr('ca.tar.gz', b'exact package')
        content = output.getvalue()
        reports = {}
        artifacts = [dict(self.build_artifacts[0], digest='sha256:' + owner.digest(content))]
        for i, cell in enumerate(self.requirements['cells']):
            name = 'major-qualification-' + str(20 + i)
            artifacts.append({'id': 30 + i, 'name': name})
            reports[name] = {'schema': 'codearbiter-major-qualification/2', 'source_commit': self.source,
                'source_tree': self.requirements['source_tree'], 'ci_run_id': 7, 'job_id': 20 + i,
                'payloads': [{'artifact_id': 12, 'archive_sha256': owner.digest(content), 'members': owner.members(content)}],
                'results': [{'cell': cell, 'result': 'PASSED', 'commands': [{'argv': ['actual-check'], 'exit_code': 0}],
                             'selected_population': 3, 'executed_population': 3, 'payload_artifact_id': 12}]}
        original = copy.deepcopy(reports)
        first = next(iter(reports))
        with mock.patch.object(owner, 'read_artifact_json', side_effect=lambda a, req, filename: reports[a['name']]), \
             mock.patch.object(owner, 'validate_upload'), mock.patch.object(owner, 'artifact_bytes', return_value=content) as fetch:
            receipt = owner.produce(self.requirements, artifacts, self.jobs)
            self.assertEqual(len(receipt['results']), 2)
            self.assertEqual(fetch.call_count, 1)
            mutations = (
                lambda r: r['payloads'][0].update(archive_sha256='0' * 64),
                lambda r: r['payloads'][0]['members'][0].update(sha256='0' * 64),
                lambda r: r.update(payloads=[]),
                lambda r: r['payloads'].append(copy.deepcopy(r['payloads'][0])),
                lambda r: r['payloads'].append(dict(r['payloads'][0], artifact_id=99)),
                lambda r: r['results'][0].update(payload_artifact_id=99),
                lambda r: r['results'][0].update(payload_artifact_id=True),
                lambda r: r['results'][0].update(payload_members=owner.members(content)),
                lambda r: r['results'][0].update(payload_archive_sha256=owner.digest(content)),
                lambda r: r.update(schema='codearbiter-major-qualification/99'),
            )
            for mutation in mutations:
                reports = copy.deepcopy(original)
                mutation(reports[first])
                with self.subTest(mutation=mutations.index(mutation)), self.assertRaises(owner.ReadinessError):
                    owner.produce(self.requirements, artifacts, self.jobs)

    def test_complete_frozen_population_receipt_fits_existing_json_bound(self):
        # Exercise serialization at the full population size with inert evidence.
        import site_vitest_observation as docs

        repo = Path(__file__).resolve().parents[2]
        corpus = repo / owner.CORPUS / 'contracts'
        tasks = json.loads((corpus / 'tasks.json').read_text())['tasks']
        cells = ['task:' + t['id'] for t in tasks if t['required_before_publication'] and t['id'] != 'Q-03']
        for filename, collection, key, group in (
            ('finding-dispositions.json', 'records', 'finding_id', 'findings'),
            ('machine-coverage.json', 'machines', 'machine_id', 'machines'),
            ('transition-coverage.json', 'transitions', 'transition_id', 'transitions'),
        ):
            cells.extend('disposition:' + group + ':' + r[key]
                         for r in json.loads((corpus / filename).read_text())[collection])
        cells.extend('scenario:' + s['id'] for s in json.loads((corpus / 'scenarios.json').read_text())['scenarios'])
        cells.extend(json.loads((repo / '.github/major-qualification-policy.json').read_text())['required_installed_cells'])
        self.assertEqual(len(cells), 2230)
        job = 'capacity fixture original job'
        docs_cells = docs.CELLS.intersection(cells)
        self.assertEqual(docs_cells, docs.CELLS)
        sf13_cell = docs.reports.SF13_CELL
        self.assertIn(sf13_cell, cells)
        core_cells = sorted(set(cells) - docs_cells - {sf13_cell})
        req = dict(self.requirements, cells=sorted(cells),
                   cell_jobs={cell: docs.JOB if cell in docs_cells else job for cell in cells},
                   source_finding_composite_cells=[sf13_cell],
                   source_finding_inputs={profile: "5" * 64
                       for profile in docs.reports.source_finding_profiles([sf13_cell])})
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as z:
            z.writestr('ca.tar.gz', b'exact package fixture')
        content = output.getvalue()
        report = {'schema': 'codearbiter-major-qualification/2', 'source_commit': self.source,
            'source_tree': req['source_tree'], 'ci_run_id': 7, 'job_id': 20,
            'payloads': [{'artifact_id': 12, 'archive_sha256': owner.digest(content), 'members': owner.members(content)}],
            'results': [{'cell': cell, 'result': 'PASSED', 'commands': [{'argv': ['fixture-only'], 'exit_code': 0}],
                'selected_population': 1, 'executed_population': 1, 'payload_artifact_id': 12}
                for cell in core_cells]}
        raw = json.dumps(report, indent=2).encode()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('qualification.json', raw)
        artifacts = [dict(self.build_artifacts[0], digest='sha256:' + owner.digest(content)),
                     {'id': 30, 'name': 'major-qualification-20'}]
        jobs = [{'id': 20, 'name': job, 'conclusion': 'success'}, self.jobs[-1]]
        docs_source = {
            'run_id': 8, 'run_attempt': 1, 'job_id': 21,
            'source_artifact_id': 31, 'source_archive_sha256': '3' * 64,
            'report_artifact_id': 32, 'report_archive_sha256': '4' * 64,
            'results': [{'cell': cell, 'result': 'PASSED', 'commands': [
                {'argv': ['fixture-only'], 'exit_code': 0}],
                'selected_population': len(docs.RECIPES[cell]),
                'executed_population': len(docs.RECIPES[cell]), 'payload_artifact_id': 31}
                for cell in sorted(docs_cells)],
        }
        docs_source['sf13_selectors'] = list(docs.SF13_DOCS_SELECTORS)
        sf13_source = {
            'cell': sf13_cell, 'result': 'PASSED',
            'core_components': [
                {'job_id': 20, 'run_attempt': 1, 'source_artifact_id': 40 + index,
                 'observation_artifact_id': 42, 'observation_archive_sha256': '6' * 64,
                 'selectors': component['selectors']}
                for index, component in enumerate(docs.reports.SOURCE_FINDING_COMPOSITIONS[sf13_cell])
            ],
            'core_source_payloads': [
                {'artifact_id': identity, 'archive_sha256': owner.digest(content),
                 'members': owner.members(content)} for identity in (40, 41)
            ],
            'docs_run_id': 8, 'docs_run_attempt': 1, 'docs_job_id': 21,
            'docs_selectors': docs_source['sf13_selectors'],
        }
        with (mock.patch.object(owner, 'validate_upload'),
              mock.patch.object(owner, 'artifact_bytes',
                                side_effect=lambda a, req: archive.getvalue() if a['id'] == 30 else content),
              mock.patch.object(docs, 'admit', return_value=docs_source) as admit_docs,
              mock.patch.object(docs, 'sf13_composition', return_value=sf13_source) as compose_sf13):
            receipt = owner.produce(req, artifacts, jobs)
        admit_docs.assert_called_once_with(req)
        compose_sf13.assert_called_once_with(req, docs_source, artifacts, jobs, producing=True)
        self.assertEqual(receipt['schema'], docs.ENVELOPE)
        results = receipt['core']['results'] + receipt['docs_source']['results'] + [receipt['sf13_source']]
        self.assertEqual(sorted(row['cell'] for row in results), sorted(cells))
        self.assertLess(len(raw), 4 * 1024 * 1024)
        self.assertLess(len(json.dumps(receipt, indent=2).encode()), 4 * 1024 * 1024)

    def test_unfinished_program_cannot_produce_readiness(self):
        data = {
            'contracts/program.json': {'id': owner.PROGRAM, 'delivery_predicates': {'PREPUBLICATION_READY': {'required_task_ids': ['P-00']}}},
            'contracts/tasks.json': {'tasks': [{'id': 'P-00', 'required_before_publication': True}]},
            'execution/progress.json': {'task_updates': [{'id': 'P-00', 'status': 'IMPLEMENTED_UNQUALIFIED'}]},
        }
        with mock.patch.object(owner, 'blob', side_effect=lambda repo, source, path: json.dumps(data[path.removeprefix(owner.CORPUS)]).encode()):
            with self.assertRaisesRegex(owner.ReadinessError, 'unfinished required task'):
                owner.requirements(Path('.'), self.source, 7)

    def test_archive_members_reject_traversal_symlink_duplicates_and_empty(self):
        for name in ('../escape', '/absolute', 'back\\slash'):
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as z:
                z.writestr(name.replace('\\', '/'), b'x')
            archive = output.getvalue()
            if '\\' in name:
                archive = archive.replace(name.replace('\\', '/').encode(), name.encode())
            with self.subTest(name=name), self.assertRaises(owner.ReadinessError):
                owner.members(archive)
        for mode in ('empty', 'symlink', 'duplicate'):
            output = io.BytesIO()
            with warnings.catch_warnings(), zipfile.ZipFile(output, 'w') as z:
                warnings.simplefilter('ignore', UserWarning)
                if mode == 'symlink':
                    info = zipfile.ZipInfo('link')
                    info.external_attr = 0o120777 << 16
                    z.writestr(info, b'target')
                if mode == 'duplicate':
                    z.writestr('same', b'one')
                    z.writestr('same', b'two')
            with self.subTest(mode=mode), self.assertRaises(owner.ReadinessError):
                owner.members(output.getvalue())

    def test_first_effect_gate_precedes_tag_and_keeps_pi_provenance_check(self):
        action = (Path(__file__).resolve().parents[2] / '.github/actions/publish-target/action.yml').read_text()
        gate = action.index('major_readiness.py verify')
        self.assertLess(gate, action.index('git push'))
        self.assertLess(gate, action.index('gh api --method POST'))
        self.assertIn('if [ "$GITHUB_SHA" != "$SOURCE_COMMIT" ]', action)


class CrossJobSourceFindingTest(unittest.TestCase):
    cell = 'disposition:findings:C-F04'
    surface_profile = 'route-release-state-component-v1'

    def setUp(self):
        from major_qualification_report import Q02_SOURCE_JOB

        self.req = {'source_commit': 'a' * 40, 'source_tree': 'b' * 40, 'ci_run_id': 7,
                    'task_ids': [], 'cells': [self.cell], 'required_artifact_names': [],
                    'cell_jobs': {self.cell: 'major qualification / release-and-integration'},
                    'source_finding_composite_cells': [self.cell]}
        self.run = {'id': 7, 'run_attempt': 3, 'event': 'push', 'head_branch': 'main',
                    'head_sha': self.req['source_commit'], 'conclusion': 'success',
                    'path': '.github/workflows/ci.yml', 'repository': {'full_name': owner.REPOSITORY}}
        self.jobs = [dict(id=i, name=name, run_id=7, run_attempt=3, status='completed', conclusion='success', steps=[])
                     for i, name in enumerate([Q02_SOURCE_JOB, '[CHECK] | [CORE] | Generated surface',
                                               'major readiness producer'], 20)]
        self.artifacts, self.blobs, self.logs = [], {}, {}
        context = mock.patch.object(owner, 'api', side_effect=self.api)
        context.start()
        self.addCleanup(context.stop)

    def api(self, path, binary=False):
        if path == 'actions/runs/7' and not binary:
            return self.run
        return self.blobs.get(path, self.logs.get(path, b''))

    def archive(self, name, job, step, files):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as output:
            for path, raw in files.items():
                output.writestr(zipfile.ZipInfo(path), raw)
        raw = archive.getvalue()
        digest = owner.digest(raw)
        identity = 100 + len(self.artifacts)
        artifact = dict(id=identity, name=name, expired=False, size_in_bytes=len(raw), digest='sha256:' + digest,
                        workflow_run={'id': 7, 'head_sha': self.req['source_commit']}, created_at='2026-01-01T00:00:00Z')
        self.artifacts.append(artifact)
        self.blobs[f'actions/artifacts/{identity}/zip'] = raw
        start = f'2026-01-01T00:00:{len(job["steps"]) * 5:02d}Z'
        job['steps'].append(dict(name=step, status='completed', conclusion='success', started_at=start, completed_at=start))
        key = f'actions/jobs/{job["id"]}/logs'
        messages = ('##[group]Run ' + owner.UPLOAD_ACTION, 'SHA256 digest of uploaded artifact is ' + digest,
                    f'Artifact {name} successfully finalized. Artifact ID {identity}')
        self.logs[key] = self.logs.get(key, b'') + ''.join(f'{start} {message}\n' for message in messages).encode()
        return artifact

    def complete_components(self, modify_surface=None):
        import major_qualification_report as reports

        surface_spec = reports.source_profile(self.surface_profile)
        self.req['source_finding_inputs'] = reports.source_finding_input_pins(
            [self.cell], self.req['source_commit'], lambda _source, _path: b'owned source fixture')
        components = (
            (self.jobs[0], reports.Q02_SOURCE_PROFILE, reports.source_profile(reports.Q02_SOURCE_PROFILE),
             '.github/scripts/test_release_workflow.py', 'python-source-observations-' + self.req['source_commit'] + '-7-3',
             'Retain original Python source-test observations', 'python-q02-release-observation.json',
             {'SourceSelectionTest': ('route_publication_is_observed_after_every_target_settles',)}),
            (self.jobs[1], self.surface_profile, surface_spec, '.github/scripts/test_command_route_release_state.py',
             'route-release-state-observation-' + self.req['source_commit'] + '-7-3',
             'Retain original release-state classifier observation', 'route-release-state-observation.json',
             {'ReleaseStateClassifierTest': ('absent_tag_and_absent_release_is_a_planned_candidate',
                 'exact_non_draft_release_is_published', 'tag_without_a_release_is_not_publication',
                 'draft_release_is_not_publication', 'api_unavailability_is_distinct_and_fail_closed',
                 'release_tag_mismatch_is_not_publication', 'release_target_mismatch_is_not_publication',
                 'tag_payload_mismatch_is_not_publication'), 'ObserveIntegrationTest': (
                 'exact_tags_payloads_and_release_responses_pass_end_to_end',
                 'observer_refuses_missing_retirement_prerequisites_or_unknown_policy',
                 'tag_only_response_fails_the_aggregate_end_to_end')}),
        )
        for job, profile, spec, script, name, upload, member, cases in components:
            files = {path: b'owned source fixture' for path in sorted(spec['paths'])}
            manifest = dict(format=reports.SOURCE_FORMAT, profile=profile, source_commit=self.req['source_commit'],
                            source_tree=self.req['source_tree'], ci_run_id=7, producer_job_name=job['name'],
                            workflow='.github/workflows/ci.yml', members=[dict(path=path, git_mode='100644',
                                bytes=len(data), sha256=owner.digest(data)) for path, data in files.items()])
            raw_manifest = json.dumps(manifest).encode()
            files[reports.SOURCE_MANIFEST] = raw_manifest
            self.archive(spec['payload'], job, spec['upload'], files)
            observation = dict(format=reports.OBSERVATION, source_commit=self.req['source_commit'],
                source_tree=self.req['source_tree'], ci_run_id=7, source_stable=True, clean=True,
                proof_kind='source-test', producer='python-test-result-observer', argv=['python', script], exit_code=0,
                source_input_binding=dict(format=reports.SOURCE_BINDING, profile=profile, payload_name=spec['payload'],
                                          manifest_sha256=owner.digest(raw_manifest)),
                tests=[dict(id=f'python:{script}:__main__.{group}.test_{case}', result='passed')
                       for group, test_names in cases.items() for case in test_names])
            if job is self.jobs[1] and modify_surface:
                modify_surface(observation)
            observations = {member: json.dumps(observation).encode()}
            if job is self.jobs[0]:
                observations['python-publisher-observation.json'] = b'{}'
            self.archive(name, job, upload, observations)

    def test_complete_cross_job_originals_form_the_only_pass(self):
        self.complete_components()
        record = owner.produce(self.req, self.artifacts, self.jobs)
        cell, = record['results']
        self.assertEqual((cell['cell'], cell['result']), (self.cell, 'PASSED'))
        self.assertEqual([c['job_id'] for c in cell['source_components']], [20, 21])
        self.assertEqual([len(c['selectors']) for c in cell['source_components']], [1, 11])
        readiness = self.archive('major-readiness-' + self.req['source_commit'], self.jobs[-1],
                                 'Upload major readiness record', {'major-readiness.json': b'{}'})
        args = dict(record=record, requirements=self.req, run=self.run, artifact=readiness,
                    archive_digest=readiness['digest'][7:], jobs=self.jobs, build_artifacts=self.artifacts)
        self.assertEqual(owner.verify(**args)['state'], 'PREPUBLICATION_READY')
        for run in (dict(self.run, conclusion=None), dict(self.run, head_branch='major/state-contracts')):
            with self.subTest(run=run), self.assertRaisesRegex(owner.ReadinessError, 'trusted main'):
                owner.verify(**dict(args, run=run))
        with self.assertRaisesRegex(owner.ReadinessError, 'original component'):
            owner.verify(**dict(args, record=dict(record, results=[dict(cell, source_components=cell['source_components'][:1])])))

    def test_partial_or_wrong_attempt_component_refuses(self):
        self.complete_components()
        with self.assertRaisesRegex(owner.ReadinessError, 'exact original component artifact'):
            owner.produce(self.req, self.artifacts[:-1], self.jobs)
        with self.assertRaisesRegex(owner.ReadinessError, 'original component job'):
            owner.produce(self.req, self.artifacts, [self.jobs[0], dict(self.jobs[1], run_attempt=2), self.jobs[-1]])
        with self.assertRaisesRegex(owner.ReadinessError, 'original component job'):
            owner.produce(self.req, self.artifacts, [self.jobs[0], dict(self.jobs[1], conclusion='skipped'), self.jobs[-1]])
        self.logs['actions/jobs/21/logs'] = b''
        with self.assertRaisesRegex(owner.ReadinessError, 'upload attribution unavailable'):
            owner.produce(self.req, self.artifacts, self.jobs)

    def test_selected_surface_skip_refuses_otherwise_authenticated_components(self):
        self.complete_components(lambda observation: observation['tests'][0].update(result='skipped'))
        with self.assertRaisesRegex(owner.ReadinessError, 'selected named test'):
            owner.produce(self.req, self.artifacts, self.jobs)

    def test_job_local_report_cannot_claim_composed_cell(self):
        import major_qualification_report as reports

        for job in self.jobs[:2]:
            req = dict(self.req, cell_jobs={self.cell: job['name']})
            with self.subTest(job=job['name']), self.assertRaisesRegex(ValueError, 'require all original owners'):
                reports.build_report(req, job_name=job['name'], job_id=job['id'], observations={}, payloads={},
                                     selections={'schema': reports.SELECTIONS, 'groups': []})

    def test_original_upload_still_requires_immutable_sources_and_trusted_main(self):
        self.complete_components()
        pins = dict(self.req['source_finding_inputs'], **{self.surface_profile: '0' * 64})
        with self.assertRaisesRegex(owner.ReadinessError, 'immutable source'):
            owner.produce(dict(self.req, source_finding_inputs=pins), self.artifacts, self.jobs)
        self.run.update(head_branch='major/state-contracts', conclusion=None)
        with self.assertRaisesRegex(owner.ReadinessError, 'trusted main'):
            owner.produce(self.req, self.artifacts, self.jobs)
        self.run['head_branch'] = 'main'
        self.assertEqual(owner.produce(self.req, self.artifacts, self.jobs)['results'][0]['result'], 'PASSED')

    def test_actual_ci_observes_each_original_entrypoint_once_in_order(self):
        workflow = (path.parents[1] / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
        hooks = workflow.split('      - name: Observe original Q02 publication guard tests\n', 1)[1]
        hooks = hooks.split('      - name:', 1)[0]
        surface = workflow.split('\n  surface:\n', 1)[1].split('\n  codex-host:\n', 1)[0]
        self.assertEqual(hooks.count('-- .github/scripts/test_release_workflow.py'), 1)
        self.assertEqual(surface.count('test_command_route_release_state.py'), 1)
        fragments = ('check_command_route_release_state.py declarations', 'observe-python',
                     '-- .github/scripts/test_command_route_release_state.py', 'test_command_route_compatibility.py',
                     'Upload release-state classifier source-test inputs', 'Retain original release-state classifier observation')
        positions = [surface.index(fragment) for fragment in fragments]
        self.assertEqual(positions, sorted(positions))

    def test_compatibility_observer_uses_the_outer_unittest_result(self):
        import tempfile
        import major_qualification_report as reports

        script = '.github/scripts/test_command_route_compatibility.py'
        profile = reports.ROUTE_RELEASE_SOURCE_PROFILE
        spec = reports.source_profile(profile)
        with tempfile.TemporaryDirectory(prefix='outer-unittest-fixture-') as temporary:
            parent = Path(temporary)
            repo = parent / 'repo'
            fixture = repo / script
            fixture.parent.mkdir(parents=True)
            fixture.write_text('''import unittest

class CompatibilityFixture(unittest.TestCase):
    def test_case(self):
        self.assertFalse(getattr(self, "nested", False))

    def test_negative_control(self):
        nested = self.__class__("test_case")
        nested.nested = True
        result = unittest.TestResult()
        nested.run(result)
        self.assertFalse(result.wasSuccessful())

if __name__ == "__main__":
    unittest.main()
''', encoding='utf-8')
            identity = dict(source_commit=self.req['source_commit'], source_tree=self.req['source_tree'], clean=True)
            output = parent / 'compatibility.json'
            legacy_output = parent / 'legacy.json'
            with (mock.patch.object(reports, 'source_identity', return_value=identity),
                  mock.patch.object(reports, 'source_observation_binding', return_value={'profile': profile}),
                  mock.patch.dict(reports.PYTHON_COMPONENT_PROFILES,
                                  {profile: dict(spec, scripts=tuple({*spec['scripts'], script}))})):
                self.assertEqual(reports.observe_python(repo, script, [], output, parent / 'source', profile), 0)
                self.assertEqual(reports.observe_python(repo, script, [], legacy_output), 0)
            record = json.loads(output.read_bytes())
            self.assertEqual([(test['id'].rsplit('.', 1)[-1], test['result']) for test in record['tests']],
                             [('test_case', 'passed'), ('test_negative_control', 'passed')])
            self.assertEqual(record['test_result_scope'], 'entrypoint-text-runner')
            legacy = json.loads(legacy_output.read_bytes())
            self.assertNotIn('test_result_scope', legacy)
            self.assertEqual([test['result'] for test in legacy['tests']], ['passed', 'passed', 'failed'])

    def test_compatibility_findings_require_their_distinct_original_populations(self):
        import major_qualification_report as reports

        sf14, wf09 = 'disposition:findings:SF14', 'disposition:findings:W-F09'
        source = b'owned immutable source fixture'
        grouped = {}
        for cell in (sf14, wf09):
            for component in reports.SOURCE_FINDING_COMPOSITIONS[cell]:
                _, selectors = grouped.setdefault(component['script'], (component, set()))
                selectors.update(component['selectors'])
        req = dict(self.req, cells=[sf14, wf09], source_finding_composite_cells=[sf14, wf09],
                   cell_jobs=dict.fromkeys((sf14, wf09), 'major qualification / compatibility'))
        req['source_finding_inputs'] = reports.source_finding_input_pins(req['cells'], req['source_commit'],
                                                                       lambda _source, _path: source)

        def fixtures(omit=None, scope=True):
            self.artifacts.clear()
            self.blobs.clear()
            self.logs.clear()
            jobs = [dict(job, steps=[]) for job in self.jobs]
            by_job = {job['name']: job for job in jobs}
            manifests = {}
            for profile in req['source_finding_inputs']:
                spec = reports.source_profile(profile)
                job = by_job[spec['job']]
                files = dict.fromkeys(sorted(spec['paths']), source)
                manifest = dict(format=reports.SOURCE_FORMAT, profile=profile, source_commit=req['source_commit'],
                                source_tree=req['source_tree'], ci_run_id=7, producer_job_name=job['name'],
                                workflow='.github/workflows/ci.yml', members=[dict(path=path, git_mode='100644',
                                    bytes=len(data), sha256=owner.digest(data)) for path, data in files.items()])
                files[reports.SOURCE_MANIFEST] = json.dumps(manifest).encode()
                manifests[profile] = owner.digest(files[reports.SOURCE_MANIFEST])
                self.archive(spec['payload'], job, spec['upload'], files)
            for script, (component, selectors) in grouped.items():
                profile = component['profile']
                spec = reports.source_profile(profile)
                observed = dict(format=reports.OBSERVATION, source_commit=req['source_commit'], source_tree=req['source_tree'],
                    ci_run_id=7, source_stable=True, clean=True, proof_kind='source-test', producer='python-test-result-observer',
                    argv=['python', script], exit_code=0, source_input_binding=dict(format=reports.SOURCE_BINDING,
                        profile=profile, payload_name=spec['payload'], manifest_sha256=manifests[profile]),
                    tests=[dict(id=selector, result='passed') for selector in sorted(selectors) if selector != omit])
                if scope and script == reports.ROUTE_COMPATIBILITY_SCRIPT:
                    observed['test_result_scope'] = reports.OUTER_UNITTEST_RESULT
                members = {component['member']: json.dumps(observed).encode()}
                if script == reports.ROUTE_GENERATOR_SCRIPT:
                    members['python-q02-release-observation.json'] = b'{}'
                self.archive(component['artifact_prefix'] + req['source_commit'] + '-7-3', by_job[spec['job']],
                             component['upload'], members)
            return jobs

        jobs = fixtures()
        record = owner.produce(req, self.artifacts, jobs)
        self.assertEqual([list(map(lambda c: len(c['selectors']), row['source_components'])) for row in record['results']],
                         [[1, 11, 13], [3, 4, 2]])
        self.assertEqual([c['job_id'] for c in record['results'][0]['source_components']], [20, 21, 21])
        self.assertEqual(len(record['artifacts']), 2)
        for own_cell, other_cell, missing in (
            (sf14, wf09, 'ReleaseStateClassifierTest.test_absent_tag_and_absent_release_is_a_planned_candidate'),
            (wf09, sf14, 'ReviewFeedbackRegressionTest.test_tribunal_lens_directory_matches_each_host_surface'),
        ):
            selector = next(s for component in reports.SOURCE_FINDING_COMPOSITIONS[own_cell]
                            for s in component['selectors'] if s.endswith(missing))
            jobs = fixtures(omit=selector)
            with self.subTest(cell=own_cell), self.assertRaisesRegex(owner.ReadinessError, 'selected named test'):
                owner.produce(req, self.artifacts, jobs)
            other_req = dict(req, cells=[other_cell], source_finding_composite_cells=[other_cell],
                             cell_jobs={other_cell: req['cell_jobs'][other_cell]})
            self.assertEqual(owner.produce(other_req, self.artifacts, jobs)['results'][0]['cell'], other_cell)
        jobs = fixtures(scope=False)
        with self.assertRaisesRegex(owner.ReadinessError, 'original entrypoint runner'):
            owner.produce(req, self.artifacts, jobs)

    def test_catalog_finding_joins_three_source_payloads_and_two_members_of_one_hook_upload(self):
        import major_qualification_report as reports

        cell = 'disposition:findings:W-F08'
        profile = 'command-catalog-component-v1'
        script = '.github/scripts/test_command_catalog.py'
        badge_job = '[CHECK] | [CA  ] | Documentation consistency'
        fallback = dict(job=badge_job, payload='major-source-inputs-command-catalog',
                        upload='Upload command catalog source-test inputs', scripts=(script,), paths={script})
        deployed_spec = reports.PYTHON_COMPONENT_PROFILES.get(profile)
        spec = deployed_spec or fallback
        badge = reports.source_component(profile, script, 'command-catalog-observation-',
            'Retain original command catalog observation', 'command-catalog-observation.json', (
                'CommandCatalogGuardTest.test_exact_catalog_passes',
                'CommandCatalogGuardTest.test_extra_catalog_route_fails',
                'CommandCatalogGuardTest.test_live_generated_catalog_is_exact',
                'CommandCatalogGuardTest.test_missing_catalog_route_fails',
            ))
        generator = reports.SOURCE_FINDING_COMPOSITIONS['disposition:findings:W-F09'][0]
        funnel = reports.source_component(reports.HOOK_REVIEW_SOURCE_PROFILE, reports.HOOK_REVIEW_SOURCE_SCRIPT,
            'python-source-observations-', 'Retain original Python source-test observations',
            'python-hook-review-observation.json',
            [selector.split(':__main__.', 1)[1] for selector in reports.HOOK_REVIEW_FINDING_SELECTORS])
        deployed_recipe = reports.SOURCE_FINDING_COMPOSITIONS.get(cell)
        recipe = deployed_recipe or (badge, generator, funnel)
        req = dict(self.req, cells=[cell], source_finding_composite_cells=[cell],
                   cell_jobs={cell: 'major qualification / compatibility'})
        jobs = [dict(self.jobs[0], steps=[]), dict(self.jobs[1], name=badge_job, steps=[]), dict(self.jobs[-1], steps=[])]
        by_job = {job['name']: job for job in jobs}
        source = b'owned original-source fixture'
        with (mock.patch.dict(reports.SOURCE_FINDING_COMPOSITIONS, {cell: recipe}),
              mock.patch.dict(reports.PYTHON_COMPONENT_PROFILES, {profile: spec})):
            req['source_finding_inputs'] = reports.source_finding_input_pins([cell], req['source_commit'],
                                                                           lambda _source, _path: source)
            uploads = {}
            for component in recipe:
                role = component['profile']
                descriptor = reports.source_profile(role)
                job = by_job[descriptor['job']]
                files = dict.fromkeys(sorted(descriptor['paths']), source)
                manifest = dict(format=reports.SOURCE_FORMAT, profile=role, source_commit=req['source_commit'],
                    source_tree=req['source_tree'], ci_run_id=7, producer_job_name=job['name'],
                    workflow='.github/workflows/ci.yml', members=[dict(path=path, git_mode='100644',
                        bytes=len(data), sha256=owner.digest(data)) for path, data in files.items()])
                files[reports.SOURCE_MANIFEST] = json.dumps(manifest).encode()
                manifest_sha = owner.digest(files[reports.SOURCE_MANIFEST])
                self.archive(descriptor['payload'], job, descriptor['upload'], files)
                observation = dict(format=reports.OBSERVATION, source_commit=req['source_commit'], source_tree=req['source_tree'],
                    ci_run_id=7, source_stable=True, clean=True, proof_kind='source-test', producer='python-test-result-observer',
                    argv=['python', component['script']], exit_code=0, source_input_binding=dict(format=reports.SOURCE_BINDING,
                        profile=role, payload_name=descriptor['payload'], manifest_sha256=manifest_sha),
                    tests=[dict(id=selector, result='passed') for selector in component['selectors']])
                key = (job['name'], component['artifact_prefix'], component['upload'])
                uploads.setdefault(key, {})[component['member']] = json.dumps(observation).encode()
            for (job, prefix, step_name), files in uploads.items():
                self.archive(prefix + req['source_commit'] + '-7-3', by_job[job], step_name, files)
            record = owner.produce(req, self.artifacts, jobs)
            row, = record['results']
            self.assertEqual([len(item['selectors']) for item in row['source_components']], [4, 3, 6])
            self.assertEqual(len(row['evidence_artifact_ids']), 3)
            self.assertEqual([item['job_id'] for item in row['source_components']], [21, 20, 20])
            self.assertEqual(row['source_components'][1]['observation_artifact_id'], row['source_components'][2]['observation_artifact_id'])
            self.assertEqual(deployed_recipe, (badge, generator, funnel))
            self.assertIsNotNone(deployed_spec)
            with mock.patch.dict(reports.SOURCE_FINDING_COMPOSITIONS, {
                cell: (badge, generator, dict(funnel, member=generator['member'])),
            }), self.assertRaisesRegex(owner.ReadinessError, 'stale, filtered or unsuccessful'):
                owner.produce(req, self.artifacts, jobs)
            with self.assertRaisesRegex(owner.ReadinessError, 'bounded plural'):
                owner.evidence_payload_ids(row)  # Normal job-local rows retain their original bound.
            ready = self.archive('major-readiness-' + req['source_commit'], jobs[-1], 'Upload major readiness record',
                                 {'major-readiness.json': b'{}'})
            self.assertEqual(owner.verify(record=record, requirements=req, run=self.run, artifact=ready,
                                          archive_digest=ready['digest'][7:], jobs=jobs,
                                          build_artifacts=self.artifacts)['state'], 'PREPUBLICATION_READY')

    def test_badge_owner_retains_the_single_original_catalog_command(self):
        workflow = (path.parents[1] / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
        badge = workflow.split('\n  badge-consistency:\n', 1)[1].split('\n  prose-sandbox:\n', 1)[0]
        parts = ('python3 .github/scripts/check_badge_consistency.py', 'prepare-source', 'observe-python',
                 '-- .github/scripts/test_command_catalog.py', 'Upload command catalog source-test inputs',
                 'Retain original command catalog observation')
        self.assertEqual([badge.count(part) for part in parts], [1] * len(parts))
        self.assertEqual([badge.index(part) for part in parts], sorted(badge.index(part) for part in parts))
        self.assertNotIn('secrets.', badge)
        self.assertNotIn('GH_TOKEN', badge)

    def test_original_debug_launcher_retains_actual_discovered_suite_ids(self):
        import os
        import runpy
        import tempfile
        import major_qualification_report as reports

        launcher = '.github/scripts/test_ci_impact.py'
        suite = '.github/scripts/test_debug_workflow.py'
        profile = 'hooks-single-owner-findings-v1'
        with tempfile.TemporaryDirectory(prefix='original-debug-runner-fixture-') as folder:
            root = Path(folder).resolve() / 'repo'
            (root / launcher).parent.mkdir(parents=True)
            (root / launcher).write_bytes(path.with_name('test_ci_impact.py').read_bytes())
            (root / 'tools').mkdir()
            (root / 'tools/ci-impact.py').write_bytes((path.parents[2] / 'tools/ci-impact.py').read_bytes())
            (root / suite).write_text('import unittest\nclass DiscoveredFixture(unittest.TestCase):\n'
                '    def test_original_name(self):\n        self.assertEqual(3, 3)\n', encoding='utf-8')
            output = root.parent / 'python-debug-workflow-observation.json'
            identity = dict(source_commit=self.req['source_commit'], source_tree=self.req['source_tree'], clean=True)
            env = {'GITHUB_JOB': 'hooks', 'GITHUB_RUN_ID': '7', 'RUNNER_TEMP': str(root.parent),
                   'MAJOR_DEBUG_SOURCE_PROFILE': profile}
            with (mock.patch.object(reports, 'source_identity', return_value=identity),
                  mock.patch.object(reports, 'source_observation_binding', return_value={'profile': profile}),
                  mock.patch.dict(os.environ, env), mock.patch.object(sys, 'argv', [str(root / launcher), '--run-debug-suite', str(root / suite)]),
                  self.assertRaises(SystemExit) as exited):
                runpy.run_path(str(root / launcher), run_name='__main__')
            self.assertEqual(exited.exception.code, 0)
            capture = json.loads(output.read_bytes())
            self.assertEqual(capture['tests'], [{'id': f'python:{suite}:test_debug_workflow.DiscoveredFixture.test_original_name',
                                                 'result': 'passed'}])
            self.assertEqual(capture['argv'][2:], ['--run-debug-suite', suite])
            self.assertEqual(capture['test_result_scope'], reports.OUTER_UNITTEST_RESULT)

    def test_locked_debug_observer_refuses_a_replacement_interpreter(self):
        import os
        import tempfile
        import types
        import major_qualification_report as reports

        with tempfile.TemporaryDirectory(prefix='inert-debug-runtime-') as folder:
            temp = Path(folder).resolve()
            venv = temp / 'artifact-conformance-venv'
            executable = venv / 'bin/python'
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b'inert launcher path')
            runtime = types.SimpleNamespace(executable=str(executable), prefix=str(venv), base_prefix=str(temp),
                                            version_info=(3, 14, 1))
            raw = b'owned locked-source fixture'
            with (mock.patch.object(reports, 'sys', runtime), mock.patch.object(reports, '_source_file', return_value=raw),
                  mock.patch.dict(os.environ, {'RUNNER_TEMP': str(temp), 'ARTIFACT_CONFORMANCE_PYTHON': str(executable)})):
                self.assertEqual(reports.locked_debug_runtime(temp), {'python': '3.14', 'lock_sha256': owner.digest(raw)})
                runtime.executable = str(temp / 'replacement-python')
                with self.assertRaisesRegex(ValueError, 'original Python 3.14 reference interpreter'):
                    reports.locked_debug_runtime(temp)

    def test_debug_resubmission_requires_all_three_original_scope_receipts(self):
        import major_qualification_report as reports

        cell = reports.DEBUG_RESUBMISSION_FINDING
        recipe = reports.SOURCE_FINDING_COMPOSITIONS[cell]
        req = dict(self.req, cells=[cell], source_finding_composite_cells=[cell],
                   cell_jobs={cell: 'major qualification / workflow'})
        raw = b'owned immutable source fixture'
        req['source_finding_inputs'] = reports.source_finding_input_pins([cell], req['source_commit'], lambda _s, _p: raw)

        def fixtures(change=None):
            self.artifacts.clear()
            self.blobs.clear()
            self.logs.clear()
            jobs = []
            for job_id, component in enumerate(recipe, 30):
                profile, script = component['profile'], component['script']
                spec = reports.source_profile(profile)
                job = dict(self.jobs[0], id=job_id, name=spec['job'], steps=[])
                jobs.append(job)
                files = dict.fromkeys(sorted(spec['paths']), raw)
                manifest = dict(format=reports.SOURCE_FORMAT, profile=profile, source_commit=req['source_commit'],
                                source_tree=req['source_tree'], ci_run_id=7, producer_job_name=job['name'],
                                workflow='.github/workflows/ci.yml', members=[dict(path=path, git_mode='100644',
                                    bytes=len(content), sha256=owner.digest(content)) for path, content in files.items()])
                files[reports.SOURCE_MANIFEST] = json.dumps(manifest).encode()
                self.archive(spec['payload'], job, spec['upload'], files)
                observation = dict(format=reports.OBSERVATION, source_commit=req['source_commit'], source_tree=req['source_tree'],
                    ci_run_id=7, source_stable=True, clean=True, proof_kind='source-test', producer='python-test-result-observer',
                    argv=['python', script], exit_code=0, source_input_binding=dict(format=reports.SOURCE_BINDING,
                        profile=profile, payload_name=spec['payload'], manifest_sha256=owner.digest(files[reports.SOURCE_MANIFEST])),
                    tests=[dict(id=selector, result='passed') for selector in component['selectors']])
                if profile in reports.DEBUG_RUNNERS:
                    observation['argv'] = ['python', reports.DEBUG_LAUNCHER, '--run-debug-suite', script]
                    observation['test_result_scope'] = reports.OUTER_UNITTEST_RESULT
                if profile == reports.DEBUG_LOCKED_PROFILE:
                    observation['debug_runtime'] = {'python': '3.14', 'lock_sha256': owner.digest(raw)}
                    if change:
                        change(observation)
                self.archive(component['artifact_prefix'] + req['source_commit'] + '-7-3', job, component['upload'],
                             {component['member']: json.dumps(observation).encode()})
            return [*jobs, dict(self.jobs[-1], steps=[])]

        jobs = fixtures()
        record = owner.produce(req, self.artifacts, jobs)
        result, = record['results']
        self.assertEqual(result['cell'], cell)
        self.assertEqual([len(c['selectors']) for c in result['source_components']], [2, 1, 5])
        self.assertEqual(len(result['evidence_artifact_ids']), 3)
        with self.assertRaisesRegex(owner.ReadinessError, 'exact original component artifact'):
            owner.produce(req, self.artifacts[:-1], jobs)
        for change, expected in (
            (lambda doc: doc['argv'].extend(['-k', 'subset']), 'stale, filtered or unsuccessful'),
            (lambda doc: doc['debug_runtime'].update(lock_sha256='0' * 64), 'locked interpreter differs'),
            (lambda doc: doc['tests'][0].update(result='skipped'), 'selected named test'),
        ):
            jobs = fixtures(change)
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, expected):
                owner.produce(req, self.artifacts, jobs)
        jobs = fixtures()
        ready = self.archive('major-readiness-' + req['source_commit'], jobs[-1], 'Upload major readiness record',
                             {'major-readiness.json': b'{}'})
        self.assertEqual(owner.verify(record=record, requirements=req, run=self.run, artifact=ready,
                                      archive_digest=ready['digest'][7:], jobs=jobs,
                                      build_artifacts=self.artifacts)['state'], 'PREPUBLICATION_READY')

    def test_recovery_runtime_observer_runs_the_unfiltered_source_entry_once(self):
        import tempfile
        import major_qualification_report as reports

        profile = 'workflow-recovery-runtime-v1'
        relative = '.github/scripts/test_workflow_recovery.py'
        with tempfile.TemporaryDirectory(prefix='recovery-observer-fixture-') as owner_dir:
            directory = Path(owner_dir)
            repo = directory / 'repo'
            fixture = repo / relative
            fixture.parent.mkdir(parents=True)
            fixture.write_text('import unittest\nclass RecoveryRuntimeTest(unittest.TestCase):\n'
                               '    def test_owned_fixture(self):\n        self.assertTrue(True)\n'
                               'if __name__ == "__main__":\n    unittest.main()\n', encoding='utf-8')
            output = directory / 'observed.json'
            identity = dict(source_commit=self.req['source_commit'], source_tree=self.req['source_tree'], clean=True)
            with (mock.patch.object(reports, 'source_identity', return_value=identity),
                  mock.patch.object(reports, 'source_observation_binding', return_value={'profile': profile}),
                  mock.patch.dict(reports.os.environ, {'GITHUB_RUN_ID': '7'})):
                result = reports.observe_python(repo, relative, [], output, directory / 'source-inputs', profile)
                with self.assertRaisesRegex(ValueError, 'original unfiltered'):
                    reports.observe_python(repo, relative, ['-k', 'fixture'], directory / 'selected.json',
                                           directory / 'source-inputs', profile)
            self.assertEqual(result, 0)
            observed = json.loads(output.read_bytes())
            self.assertEqual(observed['tests'], [{'id': f'python:{relative}:__main__.RecoveryRuntimeTest.test_owned_fixture',
                                                  'result': 'passed'}])
            self.assertEqual(observed['proof_kind'], 'source-test')

    def test_recovery_transition_cells_use_one_original_runtime_upload_with_exact_selectors(self):
        import major_qualification_report as reports

        repo = Path(__file__).resolve().parents[2]
        frozen = (repo / 'docs/state-contracts-major/execution/evidence/software48-current-7ac01607'
                  / 'recovery/tested.json')
        contract = json.loads(frozen.read_bytes())
        component = reports.RECOVERY_RUNTIME_COMPONENT
        profile, script = component['profile'], component['script']
        spec = reports.source_profile(profile)
        prefix = f'python:{script}:__main__.'
        expected = {'disposition:added_transitions:' + row['transition_id']:
                    sorted(prefix + name.split('.', 1)[1] for name in row['observed_named_assertions'])
                    for row in contract['semantic_mapping']}
        cells = sorted(expected)
        self.assertEqual((len(cells), len({name for names in expected.values() for name in names})), (22, 27))
        policy = json.loads((repo / '.github/major-qualification-policy.json').read_bytes())
        self.assertEqual(sorted(set(policy['source_finding_composite_cells']) & set(cells)), cells)
        self.assertEqual({cell: reports.SOURCE_FINDING_COMPOSITIONS[cell][0]['selectors'] for cell in cells}, expected)

        job = dict(self.jobs[0], name=spec['job'], steps=[])
        files = {path: b'owned fixture' for path in sorted(spec['paths'])}
        manifest = dict(format=reports.SOURCE_FORMAT, profile=profile, source_commit=self.req['source_commit'],
                        source_tree=self.req['source_tree'], ci_run_id=7, producer_job_name=job['name'],
                        workflow='.github/workflows/ci.yml', members=[dict(path=path, git_mode='100644',
                            bytes=len(data), sha256=owner.digest(data)) for path, data in files.items()])
        manifest_bytes = json.dumps(manifest).encode()
        files[reports.SOURCE_MANIFEST] = manifest_bytes
        source = self.archive(spec['payload'], job, spec['upload'], files)
        req = dict(self.req, cells=cells, source_finding_composite_cells=cells,
                   cell_jobs=dict.fromkeys(cells, 'major qualification / workflow-recovery'),
                   source_finding_inputs={profile: reports.source_member_digest(manifest['members'])})
        with self.assertRaisesRegex(owner.ReadinessError, 'exact original component artifact'):
            reports.source_finding_evidence(req, self.artifacts, [job], run=self.run)

        tests = [dict(id=prefix + row['id'].split('.', 1)[1], result='passed')
                 for row in contract['original_named_results']]
        self.assertEqual(len(tests), 29)
        observed = dict(format=reports.OBSERVATION, source_commit=req['source_commit'],
            source_tree=req['source_tree'], ci_run_id=7, source_stable=True, clean=True,
            proof_kind='source-test', producer='python-test-result-observer', argv=['python', script], exit_code=0,
            source_input_binding=dict(format=reports.SOURCE_BINDING, profile=profile, payload_name=spec['payload'],
                                      manifest_sha256=owner.digest(manifest_bytes)), tests=tests)
        def upload(outcomes):
            return self.archive(component['artifact_prefix'] + req['source_commit'] + '-7-3', job,
                component['upload'], {component['member']: json.dumps(dict(observed, tests=outcomes)).encode()})

        log_key = f'actions/jobs/{job["id"]}/logs'
        source_log = self.logs[log_key]
        missing = next(name for name in expected[cells[0]] if name not in expected[cells[-1]])
        upload([test for test in tests if test['id'] != missing])
        with self.assertRaisesRegex(owner.ReadinessError, 'selected named test missing'):
            reports.source_finding_evidence(req, self.artifacts, [job], run=self.run)
        single = dict(req, cells=cells[-1:], source_finding_composite_cells=cells[-1:])
        rows, _ = reports.source_finding_evidence(single, self.artifacts, [job], run=self.run)
        self.assertEqual(list(rows), single['cells'])
        self.artifacts.pop()
        job['steps'].pop()
        self.logs[log_key] = source_log

        capture = upload(tests)
        jobs = [job, self.jobs[-1]]
        with mock.patch.object(owner, 'artifact_bytes', wraps=owner.artifact_bytes) as download:
            record = owner.produce(req, self.artifacts, jobs)
        self.assertEqual([call.args[0]['id'] for call in download.call_args_list], [source['id'], capture['id']])
        self.assertEqual([row['cell'] for row in record['results']], cells)
        for row in record['results']:
            self.assertEqual(row['evidence_artifact_ids'], [source['id']])
            self.assertEqual(len(row['source_components']), 1)
            result = row['source_components'][0]
            self.assertEqual(result['selectors'], expected[row['cell']])
            self.assertEqual(result['observation_artifact_id'], capture['id'])
            self.assertNotIn('consumed_native_installation', result)
        readiness = self.archive('major-readiness-' + req['source_commit'], jobs[-1],
                                 'Upload major readiness record', {'major-readiness.json': b'{}'})
        args = dict(record=record, requirements=req, run=self.run, artifact=readiness,
                    archive_digest=readiness['digest'][7:], jobs=jobs, build_artifacts=self.artifacts)
        self.assertEqual(owner.verify(**args)['state'], 'PREPUBLICATION_READY')
        forged = copy.deepcopy(record)
        forged['results'][0]['source_components'][0]['selectors'] = expected[cells[-1]]
        with self.assertRaisesRegex(owner.ReadinessError, 'readiness differs from original component evidence'):
            owner.verify(**dict(args, record=forged))
        with self.assertRaisesRegex(owner.ReadinessError, 'original component job'):
            reports.source_finding_evidence(req, self.artifacts, [dict(job, run_attempt=2)], run=self.run)
        with self.assertRaisesRegex(owner.ReadinessError, 'exact original component artifact'):
            reports.source_finding_evidence(req, [*self.artifacts, dict(capture, id=1000)], [job], run=self.run)

    def test_recovery_runtime_reader_authenticates_only_the_original_nine_cases(self):
        import major_qualification_report as reports

        profile = reports.RECOVERY_RUNTIME_PROFILE
        spec = reports.source_profile(profile)
        job = dict(self.jobs[0], name=spec['job'])
        source_bytes = b'owned recovery fixture'
        members = [{'path': name, 'sha256': owner.digest(source_bytes), 'bytes': len(source_bytes), 'git_mode': '100644'}
                   for name in sorted(spec['paths'])]
        manifest = {'format': reports.SOURCE_FORMAT, 'profile': profile, 'source_commit': self.req['source_commit'],
                    'source_tree': self.req['source_tree'], 'ci_run_id': 7, 'producer_job_name': job['name'],
                    'workflow': '.github/workflows/ci.yml', 'members': members}
        source_manifest = json.dumps(manifest).encode()
        files = {row['path']: source_bytes for row in members}
        files[reports.SOURCE_MANIFEST] = source_manifest
        source = self.archive(spec['payload'], job, spec['upload'], files)
        load = mock.Mock(return_value=source_bytes)
        with self.assertRaisesRegex(owner.ReadinessError, 'exact original component artifact'):
            reports.workflow_recovery_runtime_evidence(self.req, self.run, self.artifacts, [job], load)
        component = reports.RECOVERY_RUNTIME_COMPONENT
        member = component['member']
        capture_name = component['artifact_prefix'] + self.req['source_commit'] + '-7-3'
        observed = dict(format=reports.OBSERVATION, source_commit=self.req['source_commit'],
                        source_tree=self.req['source_tree'], ci_run_id=7, source_stable=True, clean=True,
                        proof_kind='source-test', producer='python-test-result-observer',
                        argv=['python', component['script']], exit_code=0,
                        source_input_binding=dict(format=reports.SOURCE_BINDING, profile=profile, payload_name=spec['payload'],
                                                  manifest_sha256=owner.digest(source_manifest)),
                        tests=[dict(id=selector, result='passed') for selector in component['selectors']])
        observed['tests'].append(dict(id='python:.github/scripts/test_workflow_recovery.py:__main__.RecoveryRuntimeTest.test_other',
                                      result='passed'))
        self.archive(capture_name, job, component['upload'], {member: json.dumps(observed).encode()})
        receipt = reports.workflow_recovery_runtime_evidence(self.req, self.run, self.artifacts, [job], load)
        self.assertEqual(receipt['schema'], 'codearbiter.workflow-recovery-runtime-component/1')
        self.assertEqual(len(receipt['component']['selectors']), 9)
        self.assertEqual(receipt['component']['job_id'], job['id'])
        self.assertEqual(receipt['source_payload']['artifact_id'], source['id'])
        self.assertEqual(set(receipt), {'schema', 'source_commit', 'source_tree', 'ci_run_id', 'component', 'source_payload'})
        with self.assertRaisesRegex(owner.ReadinessError, 'original component job'):
            reports.workflow_recovery_runtime_evidence(self.req, self.run, self.artifacts, [dict(job, run_attempt=2)], load)
        with self.assertRaisesRegex(owner.ReadinessError, 'trusted main'):
            reports.workflow_recovery_runtime_evidence(self.req, dict(self.run, conclusion=None), self.artifacts, [job], load)
        load.return_value = b'wrong immutable input'
        with self.assertRaisesRegex(owner.ReadinessError, 'immutable source'):
            reports.workflow_recovery_runtime_evidence(self.req, self.run, self.artifacts, [job], load)

    def test_recovery_fixture_reports_consumed_copies_for_both_original_classes(self):
        import os
        import shutil
        import tempfile
        import types
        import test_workflow_recovery_cli as recovery_cli
        import test_workflow_recovery_hosts as recovery_hosts

        binary = b'inert recovery installation fixture'
        name = 'ca-artifact-windows-amd64.exe'
        manifest = {'format': 'codearbiter.artifact-release/0.1.0', 'version': '0.1.0',
                    'protocol': 'codearbiter.artifact-api/0.1.0', 'schema_version': '0.3.2',
                    'binaries': {'windows/amd64': {'file': name, 'sha256': owner.digest(binary), 'native_tested': True}}}
        with tempfile.TemporaryDirectory(prefix='inert-recovery-copy-') as folder:
            scratch = Path(folder).resolve(strict=True)
            root = scratch / 'repo'
            source = scratch / 'workflow-recovery-native'
            source.mkdir()
            raw = json.dumps(manifest).encode()
            (source / 'release.json').write_bytes(raw)
            (source / name).write_bytes(binary)
            for directory in (root / 'core/pysrc', *(root / 'plugins' / name / 'hooks' for name in ('ca', 'ca-codex', 'ca-pi'))):
                directory.mkdir(parents=True)
                for filename in ('_workflowrecoverylib.py', 'workflow-recovery.py'):
                    (directory / filename).write_bytes(b'# inert')
            owner_module = types.ModuleType('test_artifact_authoring')

            def fixture_copy():
                temporary = tempfile.TemporaryDirectory(dir=scratch)
                target = Path(temporary.name) / 'helpers' / 'artifacts'
                shutil.copytree(source, target)
                return temporary, target

            owner_module.build_installation = fixture_copy
            for original_class, role in ((recovery_cli.InstalledRecoveryTest, 'cli'), (recovery_hosts.RecoveryHostTest, 'hosts')):
                cls = type(original_class.__name__, (original_class,), {})
                output = scratch / f'workflow-recovery-{role}-installation.json'
                with (self.subTest(role=role), mock.patch.object(recovery_cli, 'ROOT', root),
                      mock.patch.dict(sys.modules, {'test_artifact_authoring': owner_module}),
                      mock.patch.dict(os.environ, {'ARTIFACT_TEST_INSTALLATION': str(root / '..' / source.name),
                                                  'RUNNER_TEMP': str(scratch),
                                                  'WORKFLOW_RECOVERY_INSTALLATION_OBSERVATION': str(output)})):
                    try:
                        cls.setUpClass()
                        cls.tearDownClass()
                    finally:
                        cls.doClassCleanups()
                    projection = json.loads(output.read_bytes())
                    expected = {'manifest_sha256': owner.digest(raw), 'binary_sha256': owner.digest(binary)}
                    self.assertEqual(projection['fixture'], original_class.__name__)
                    self.assertEqual(projection['platform'], 'windows/amd64')
                    self.assertEqual(projection['installation'], expected)
                    self.assertEqual(projection['fixture_copy'], expected)
                    self.assertEqual(projection['hosts'], dict.fromkeys(('claude', 'codex', 'pi'), expected))

    def test_recovery_finding_receipt_requires_native_archive_and_both_consumed_copies(self):
        import major_qualification_report as reports

        cells = list(reports.RECOVERY_FINDING_CELLS)
        req = dict(self.req, cells=cells, cell_jobs=dict.fromkeys(cells, 'major qualification / workflow-recovery'),
                   source_finding_composite_cells=cells)
        profile = reports.RECOVERY_RUNTIME_PROFILE
        spec = reports.source_profile(profile)
        source_bytes = b'owned immutable fixture'
        req['source_finding_inputs'] = reports.source_finding_input_pins(cells, req['source_commit'],
                                                                      lambda _source, _path: source_bytes)
        binary = b'inert archive fixture'
        filename = reports.RECOVERY_NATIVE_BINARY
        raw = json.dumps({'format': 'codearbiter.artifact-release/0.1.0', 'version': '0.1.0',
            'protocol': 'codearbiter.artifact-api/0.1.0', 'schema_version': '0.3.2',
            'binaries': {'windows/amd64': {'file': filename, 'sha256': owner.digest(binary), 'native_tested': True}}}).encode()
        identity = dict(manifest_sha256=owner.digest(raw), binary_sha256=owner.digest(binary))
        suffix = f"{req['source_commit']}-7-3"

        def fixtures(change_host=None):
            self.artifacts.clear()
            self.blobs.clear()
            self.logs.clear()
            job = dict(self.jobs[0], name=spec['job'], steps=[dict(name='Qualify one native installation for workflow recovery',
                                                                 status='completed', conclusion='success')])
            files = dict.fromkeys(sorted(spec['paths']), source_bytes)
            manifest = dict(format=reports.SOURCE_FORMAT, profile=profile, source_commit=req['source_commit'],
                            source_tree=req['source_tree'], ci_run_id=7, producer_job_name=job['name'],
                            workflow='.github/workflows/ci.yml', members=[dict(path=path, git_mode='100644',
                                bytes=len(data), sha256=owner.digest(data)) for path, data in files.items()])
            manifest_raw = json.dumps(manifest).encode()
            files[reports.SOURCE_MANIFEST] = manifest_raw
            self.archive(spec['payload'], job, spec['upload'], files)
            for component in reports.RECOVERY_COMPONENTS:
                script = component['script']
                observed = dict(format=reports.OBSERVATION, source_commit=req['source_commit'], source_tree=req['source_tree'],
                    ci_run_id=7, source_stable=True, clean=True, proof_kind='source-test', producer='python-test-result-observer',
                    argv=['python', script], exit_code=0,
                    source_input_binding=dict(format=reports.SOURCE_BINDING, profile=profile, payload_name=spec['payload'],
                                              manifest_sha256=owner.digest(manifest_raw)),
                    tests=[dict(id=selector, result='passed') for selector in component['selectors']])
                if script in reports.RECOVERY_INSTALLED_SCRIPTS:
                    role, actual_class = reports.RECOVERY_INSTALLED_SCRIPTS[script]
                    binding = dict(format='codearbiter.workflow-recovery-installation/1', fixture=actual_class,
                                   platform='windows/amd64', installation=identity, fixture_copy=identity,
                                   hosts=dict.fromkeys(('claude', 'codex', 'pi'), identity))
                    if role == 'hosts' and change_host:
                        change_host(observed, binding)
                    observed['workflow_recovery_installation'] = binding
                self.archive(component['artifact_prefix'] + suffix, job, component['upload'],
                             {component['member']: json.dumps(observed).encode()})
            self.archive('workflow-recovery-native-' + suffix, job, 'Upload original workflow recovery native installation',
                         {'release.json': raw, filename: binary})
            return [job, self.jobs[-1]]

        jobs = fixtures()
        record = owner.produce(req, self.artifacts, jobs)
        self.assertEqual([r['cell'] for r in record['results']], cells)
        for result in record['results']:
            self.assertEqual(result['result'], 'PASSED')
            self.assertEqual([len(c['selectors']) for c in result['source_components']], [9, 7, 5])
            self.assertEqual(result['workflow_recovery_installation']['binary_sha256'], owner.digest(binary))
            self.assertEqual([c['consumed_native_installation'] for c in result['source_components'][1:]], [identity] * 2)
        with self.assertRaisesRegex(owner.ReadinessError, 'native installation archive required'):
            owner.produce(req, self.artifacts[:-1], jobs)
        with self.assertRaisesRegex(owner.ReadinessError, 'exact original component artifact'):
            owner.produce(req, [self.artifacts[0], self.artifacts[1], self.artifacts[-1]], jobs)
        bad_copy = fixtures(lambda _observed, binding: binding['hosts'].update(pi=dict(identity, binary_sha256='0' * 64)))
        with self.assertRaisesRegex(owner.ReadinessError, 'consumed installation differs'):
            owner.produce(req, self.artifacts, bad_copy)
        skipped = fixtures(lambda observed, _binding: observed['tests'][0].update(result='skipped'))
        with self.assertRaisesRegex(owner.ReadinessError, 'selected named test'):
            owner.produce(req, self.artifacts, skipped)
        jobs = fixtures()
        readiness = self.archive('major-readiness-' + req['source_commit'], jobs[-1], 'Upload major readiness record',
                                 {'major-readiness.json': b'{}'})
        self.assertEqual(owner.verify(record=record, requirements=req, run=self.run, artifact=readiness,
                                      archive_digest=readiness['digest'][7:], jobs=jobs,
                                      build_artifacts=self.artifacts)['state'], 'PREPUBLICATION_READY')

    def test_recovery_ci_observes_runtime_once_and_keeps_the_native_owners(self):
        workflow = (path.parents[1] / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
        job = workflow.split('\n  workflow-recovery:\n', 1)[1].split('\n  version-bump:\n', 1)[0]
        self.assertIn('permissions:\n      contents: read\n', job)
        direct, observed = job.split('      - name: Test durable runtime and concurrency\n', 1)[1].split(
            '      - name: Observe original durable runtime and concurrency tests\n', 1)
        self.assertIn("if: matrix.os != 'windows-latest'", direct)
        self.assertIn('run: python .github/scripts/test_workflow_recovery.py\n', direct)
        self.assertIn("if: matrix.os == 'windows-latest'", observed.split('      - name:', 1)[0])
        self.assertEqual(job.count('.github/scripts/test_workflow_recovery.py'), 2)
        self.assertEqual(job.count('.github/scripts/test_workflow_recovery_cli.py'), 2)
        self.assertEqual(job.count('.github/scripts/test_workflow_recovery_hosts.py'), 2)
        self.assertEqual(job.count('observe-python'), 4)
        fragments = ('python tools/build-artifacts.py', '-- .github/scripts/test_workflow_recovery.py',
                     'run: python .github/scripts/test_workflow_recovery_cli.py',
                     '-- .github/scripts/test_workflow_recovery_cli.py',
                     'run: python .github/scripts/test_workflow_recovery_hosts.py',
                     '-- .github/scripts/test_workflow_recovery_hosts.py',
                     'run: python .github/scripts/test_review_resubmission.py',
                     '-- .github/scripts/test_review_resubmission.py',
                     'Retain original workflow recovery runtime observation',
                     'Upload original workflow recovery native installation')
        self.assertEqual([job.count(fragment) for fragment in fragments], [1] * len(fragments))
        self.assertEqual([job.index(fragment) for fragment in fragments], sorted(job.index(fragment) for fragment in fragments))


class CompletedPopulationTest(unittest.TestCase):
    """Exercise the full frozen corpus after every metadata task says done."""
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[2]
        cls.source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=cls.repo, text=True).strip()
        cls.tasks = json.loads((cls.repo / owner.CORPUS / 'contracts/tasks.json').read_text())['tasks']
        cls.progress = json.loads((cls.repo / owner.CORPUS / 'execution/progress.json').read_text())
        cls.progress.update(task_updates=[{'id': t['id'], 'status': 'DONE'} for t in cls.tasks],
                            new_required_work=[], pending_user_decisions=[], scoped_blockers=[], unknown_outcomes=[])
        cls.ledger = json.loads((cls.repo / owner.CORPUS / 'execution/coverage-ledger.json').read_text())
        for group in ('findings', 'machines', 'transitions', 'added_transitions'):
            for row in cls.ledger[group].values():
                row.update(status='PRESERVED', evidence=[{'kind': 'review', 'ref': 'does-not-exist.json',
                                                         'sha256': 'e' * 64, 'commit': 'f' * 40}])

    def setUp(self):
        # Launch-binding task and finding archives have their own fixtures.
        # This fixture exercises the complete reviewed source population.
        policy = json.loads((self.repo / '.github/major-qualification-policy.json').read_bytes())
        policy['native_launch_binding_tasks'] = []
        policy['native_launch_binding_findings'] = []
        self.overrides = {
            owner.CORPUS + 'execution/progress.json': json.dumps(self.progress).encode(),
            owner.CORPUS + 'execution/coverage-ledger.json': json.dumps(self.ledger).encode(),
            '.github/major-qualification-policy.json': json.dumps(policy).encode(),
            '.codearbiter/open-questions.md': b'# Open questions\n_None open._\n',
        }

    def load(self, repo, source, path):
        if path in self.overrides:
            return self.overrides[path]
        return (self.repo / path).read_bytes()

    def requirements(self):
        with mock.patch.object(owner, 'blob', side_effect=self.load):
            return owner.requirements(self.repo, self.source, 7)

    def test_completed_metadata_does_not_clear_authoritative_confirmation(self):
        self.overrides['.codearbiter/open-questions.md'] = b'# Open questions\n- [CONFIRM-99] - Decide the sensitive provider authority.\n'
        with self.assertRaisesRegex(owner.ReadinessError, 'CONFIRM-99'):
            self.requirements()

    def test_preserved_rows_do_not_admit_a_nonexistent_evidence_commit(self):
        self.assertNotEqual(subprocess.run(['git', 'cat-file', '-e', 'f' * 40 + '^{commit}'], cwd=self.repo,
                                          capture_output=True).returncode, 0)
        with self.assertRaises(owner.ReadinessError):
            self.requirements()

    def test_existing_evidence_commit_does_not_make_an_unavailable_reference_valid(self):
        ledger = copy.deepcopy(self.ledger)
        for group in ('findings', 'machines', 'transitions', 'added_transitions'):
            for row in ledger[group].values():
                row['evidence'][0]['commit'] = self.source
        self.overrides[owner.CORPUS + 'execution/coverage-ledger.json'] = json.dumps(ledger).encode()
        with self.assertRaises(owner.ReadinessError):
            self.requirements()

    def valid_completed_fixture(self):
        contracts = {
            'findings': ('finding-dispositions.json', 'records', 'finding_id'),
            'machines': ('machine-coverage.json', 'machines', 'machine_id'),
            'transitions': ('transition-coverage.json', 'transitions', 'transition_id'),
        }
        paths, ids = set(), []
        ledger = copy.deepcopy(self.ledger)
        owners = {t['id']: t['owner'] for t in self.tasks}
        for group, (file, collection, field) in contracts.items():
            for row in json.loads((self.repo / owner.CORPUS / 'contracts' / file).read_text())[collection]:
                identity = row[field]
                ids.append('disposition:' + group + ':' + identity)
                paths.update(owner.evidence_paths(row))
                ledger[group][identity]['owner'] = row.get('owner') or owners[row['task_ids'][0]]
        for row in self.progress.get('new_transition_rows', []):
            identity = row['transition_id']
            ids.append('disposition:added_transitions:' + identity)
            paths.update(owner.evidence_paths(row))
            ledger['added_transitions'][identity]['owner'] = row.get('owner') or owners[row['task_ids'][0]]
        raw = b'Fixture: original local review transcript and source observations.'
        proof = {'schema': 'codearbiter-disposition-evidence/1', 'source_commit': self.source,
                 'kind': 'review', 'result': 'PRESERVED', 'disposition_ids': ids,
                 'producer': {'class': 'independent-review', 'identity': 'fixture reviewer'},
                 'raw_evidence': [{'path': 'retained-review.txt', 'sha256': owner.digest(raw)}],
                 'inputs': {path: owner.digest((self.repo/path).read_bytes()) for path in paths}}
        encoded = json.dumps(proof).encode()
        for group in ('findings', 'machines', 'transitions', 'added_transitions'):
            for row in ledger[group].values():
                row['evidence'] = [{'kind': 'review', 'commit': self.source, 'ref': 'retained-review.json',
                                    'sha256': owner.digest(encoded)}]
        self.overrides.update({'retained-review.json': encoded, 'retained-review.txt': raw,
            owner.CORPUS + 'execution/coverage-ledger.json': json.dumps(ledger).encode()})
        return proof, ledger

    def test_complete_reviewed_population_preserves_local_origin_and_non_circularity(self):
        self.valid_completed_fixture()
        result = self.requirements()
        self.assertEqual(result['unresolved_decision_count'], 0)
        self.assertNotIn('Q-03', result['task_ids'])
        self.assertEqual(sum(c.startswith('disposition:') for c in result['cells']),
                         70 + 287 + 1748 + len(self.progress.get('new_transition_rows', [])))
        self.assertEqual(result['cell_jobs']['disposition:transitions:C11:01'],
                         'major qualification / release-and-integration')
        self.assertEqual(result['open_questions_sha256'], owner.digest(self.overrides['.codearbiter/open-questions.md']))

    def test_complete_population_does_not_reopen_resolved_history_prose(self):
        self.valid_completed_fixture()
        self.overrides['.codearbiter/open-questions.md'] = (
            b'# Open questions\nUnresolved entries use `[CONFIRM-NN]`.\n'
            b'_Resolved 2026-11-13 (BY fixture owner): [CONFIRM-98] retained attribution._\n')
        self.assertEqual(self.requirements()['unresolved_decision_count'], 0)

    def test_complete_population_rejects_missing_or_changed_raw_proof_and_inputs(self):
        proof, ledger = self.valid_completed_fixture()
        raw = self.overrides['retained-review.txt']
        self.overrides['retained-review.txt'] = b'changed transcript'
        with self.assertRaisesRegex(owner.ReadinessError, 'evidence bytes differ'):
            self.requirements()
        self.overrides['retained-review.txt'] = raw
        input_path = next(iter(proof['inputs']))
        self.overrides[input_path] = b'changed candidate input'
        with self.assertRaisesRegex(owner.ReadinessError, 'evidence bytes differ'):
            self.requirements()

    def test_complete_population_rejects_a_review_that_does_not_cover_the_row(self):
        proof, ledger = self.valid_completed_fixture()
        proof['disposition_ids'] = proof['disposition_ids'][1:]
        encoded = json.dumps(proof).encode()
        self.overrides['retained-review.json'] = encoded
        for group in ('findings', 'machines', 'transitions', 'added_transitions'):
            for row in ledger[group].values():
                row['evidence'][0]['sha256'] = owner.digest(encoded)
        self.overrides[owner.CORPUS+'execution/coverage-ledger.json'] = json.dumps(ledger).encode()
        with self.assertRaisesRegex(owner.ReadinessError, 'does not cover'):
            self.requirements()


class UploadAttributionTest(unittest.TestCase):
    def setUp(self):
        self.job = {'id': 20, 'steps': [{'name': 'Upload major qualification report', 'status': 'completed',
            'conclusion': 'success', 'started_at': '2026-11-13T15:00:00Z', 'completed_at': '2026-11-13T15:00:03Z'}]}
        self.artifact = {'id': 30, 'name': 'major-qualification-20', 'digest': 'sha256:'+'a'*64,
                         'created_at': '2026-11-13T15:00:01Z'}
        self.logs = ('2026-11-13T15:00:00Z ##[group]Run '+owner.UPLOAD_ACTION+'\n'
                     '2026-11-13T15:00:01Z SHA256 digest of uploaded artifact is '+'a'*64+'\n'
                     '2026-11-13T15:00:02Z Artifact major-qualification-20 successfully finalized. Artifact ID 30\n').encode()

    def check(self, job=None, artifact=None, logs=None):
        with mock.patch.object(owner, 'api', return_value=self.logs if logs is None else logs) as fetch:
            owner.validate_upload(job or self.job, artifact or self.artifact, 'Upload major qualification report')
            fetch.assert_called_once_with(f"actions/jobs/{(job or self.job)['id']}/logs", binary=True)

    def test_exact_successful_upload_has_original_attribution(self):
        self.check()

    def test_artifact_service_clock_offset_does_not_override_authenticated_step_log(self):
        # Original observed service/runner timestamps; IDs/digest use inert fixtures.
        step=dict(self.job['steps'][0],started_at='2026-11-14T13:44:04Z',completed_at='2026-11-14T13:44:07Z')
        artifact=dict(self.artifact,created_at='2026-11-14T13:44:15Z')
        logs=self.logs.replace(b'2026-11-13T15:00:00Z',b'2026-11-14T13:44:04Z').replace(b'2026-11-13T15:00:01Z',b'2026-11-14T13:44:05Z').replace(b'2026-11-13T15:00:02Z',b'2026-11-14T13:44:06Z')
        self.check(job=dict(self.job,steps=[step]),artifact=artifact,logs=logs)

    def test_original_actions_log_utf8_bom_is_accepted(self):
        self.check(logs=b'\xef\xbb\xbf' + self.logs)

    def test_report_name_and_json_job_id_do_not_replace_successful_upload_step(self):
        for steps in ([], [dict(self.job['steps'][0], conclusion='skipped')],
                      [dict(self.job['steps'][0], name='Unrelated upload')], self.job['steps']*2):
            with self.assertRaises(owner.ReadinessError):
                self.check(job=dict(self.job, steps=steps))

    def test_another_jobs_artifact_or_different_digest_or_window_refuses(self):
        for artifact in (dict(self.artifact, id=31), dict(self.artifact, digest='sha256:'+'b'*64),
                         dict(self.artifact, name='another-artifact')):
            with self.assertRaises(owner.ReadinessError):
                self.check(artifact=artifact)
        # Runner log timestamps, rather than the independent API creation clock,
        # must place each exact action/digest/finalization inside this step.
        for stamp in (b'15:00:00Z', b'15:00:01Z', b'15:00:02Z'):
            with self.subTest(stamp=stamp), self.assertRaises(owner.ReadinessError):
                self.check(logs=self.logs.replace(stamp, b'16:00:00Z'))
        with self.assertRaises(owner.ReadinessError):
            self.check(logs=self.logs.replace(owner.UPLOAD_ACTION.encode(), b'actions/other@unknown'))

    def test_metadata_and_step_timestamps_still_require_wellformed_aware_values(self):
        for value in ('not-a-time', '2026-11-13T15:00:01', '', None, 17, {}):
            with self.subTest(created_at=value), self.assertRaises(owner.ReadinessError):
                self.check(artifact=dict(self.artifact, created_at=value))
        missing=dict(self.artifact);del missing['created_at']
        with self.assertRaises(owner.ReadinessError):self.check(artifact=missing)
        for field,value in (('started_at','2026-11-13T15:00:00'), ('completed_at','invalid'),
                            ('started_at',None), ('completed_at','2026-11-13T14:59:00Z')):
            with self.subTest(field=field,value=value), self.assertRaises(owner.ReadinessError):
                self.check(job=dict(self.job, steps=[dict(self.job['steps'][0], **{field:value})]))


class QuestionEntryTest(unittest.TestCase):
    def test_actual_job_binding_preserves_every_cell_and_leaves_unmapped_groups_unready(self):
        original = {'task:NT-09': 'major qualification / native',
                    'disposition:transitions:N09:04': 'major qualification / native'}
        actual = '[CHECK] | [CORE] | Tested native candidate build <windows/amd64>'
        mapped = owner.bind_named_jobs(original, {'cell_job_bindings': {'disposition:transitions:N09:04': actual}})
        self.assertEqual(set(mapped), set(original))
        self.assertEqual(mapped['disposition:transitions:N09:04'], actual)
        self.assertEqual(mapped['task:NT-09'], original['task:NT-09'])
        self.assertEqual(original['disposition:transitions:N09:04'], 'major qualification / native')

    def test_unknown_cells_empty_names_or_control_characters_cannot_change_job_population(self):
        for values in ({'task:invented': 'real job'}, {'task:NT-09': ''}, {'task:NT-09': 'job\nforged'}):
            with self.subTest(values=values), self.assertRaises(owner.ReadinessError):
                owner.bind_named_jobs({'task:NT-09': 'original'}, {'cell_job_bindings': values})

    def test_native_entry_grammar_keeps_real_markers_open(self):
        self.assertEqual(owner.open_decisions(
            b'# Open questions\n- [CONFIRM-01] - resolved wording is still an entry\n'), ['CONFIRM-01'])
        self.assertEqual(owner.open_decisions(
            b'# Open questions\n```text\n[CONFIRM-02] - an entry inside a fence remains ambiguous\n```\n'), ['CONFIRM-02'])

    def test_scaffold_and_attributed_history_are_not_entries(self):
        self.assertEqual(owner.open_decisions(
            b'# Open questions\nExamples use `[CONFIRM-NN]`.\n'
            b'_Resolved by fixture owner: [CONFIRM-03] retained history._\n'), [])

    def test_malformed_duplicate_and_missing_board_refuse(self):
        for raw in (b'wrong header', b'# Open questions\n[CONFIRM-01]\n',
                    b'# Open questions\n[CONFIRM-01] - one\n[CONFIRM-01] - two\n'):
            with self.assertRaises(owner.ReadinessError):
                owner.open_decisions(raw)


class PagesBuildAdmissionTest(unittest.TestCase):
    """Static Pages provenance is distinct from native/release readiness."""

    def setUp(self):
        import tarfile
        self.tarfile = tarfile
        companion = Path(__file__).with_name('pages_readiness.py')
        self.assertTrue(companion.is_file(), 'missing purpose-specific Pages admission companion')
        spec = importlib.util.spec_from_file_location('pages_readiness', companion)
        self.pages = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.pages)
        self.source = 'a' * 40
        self.run = {'id': 7, 'head_sha': self.source, 'head_branch': 'major/state-contracts',
            'event': 'push', 'status': 'completed', 'conclusion': 'success', 'run_attempt': 1,
            'path': '.github/workflows/docs.yml',
            'repository': {'id': 9, 'full_name': owner.REPOSITORY},
            'head_repository': {'id': 9, 'full_name': owner.REPOSITORY}}
        self.job = {'id': 20, 'run_id': 7, 'run_attempt': 1,
            'name': 'Site | [Build] - Astro Pages', 'status': 'completed', 'conclusion': 'success',
            'steps': [{'name': 'Upload Pages artifact', 'status': 'completed', 'conclusion': 'success',
                'started_at': '2026-11-14T15:00:00Z', 'completed_at': '2026-11-14T15:00:03Z'}]}
        self.tar = self.make_tar([('.', 'dir', b''), ('./pagefind', 'dir', b''),
            ('./index.html', 'file', b'<h1>Original Pages</h1>'),
            ('./pagefind/pagefind.js', 'file', b'export async function search() {}')])
        self.archive = self.make_zip([('artifact.tar', self.tar)])
        self.artifact = {'id': 30, 'name': 'github-pages', 'size_in_bytes': len(self.archive),
            'expired': False, 'digest': 'sha256:' + owner.digest(self.archive),
            'created_at': '2026-11-14T15:00:01Z',
            'workflow_run': {'id': 7, 'head_sha': self.source, 'head_branch': 'major/state-contracts',
                             'repository_id': 9, 'head_repository_id': 9}}
        self.logs = self.make_log(self.artifact['digest'])

    def make_log(self, digest):
        return ('2026-11-14T15:00:00Z ##[group]Run '+self.pages.PAGES_ACTION+'\n'
            '2026-11-14T15:00:00Z ##[group]Run '+self.pages.NESTED_UPLOAD_ACTION+'\n'
            '2026-11-14T15:00:01Z SHA256 digest of uploaded artifact is '+digest.removeprefix('sha256:')+'\n'
            '2026-11-14T15:00:02Z Artifact github-pages successfully finalized. Artifact ID 30\n').encode()

    def make_tar(self, entries):
        output = io.BytesIO()
        with self.tarfile.open(fileobj=output, mode='w', format=self.tarfile.USTAR_FORMAT) as archive:
            for name, kind, data in entries:
                info = self.tarfile.TarInfo(name)
                info.type = {'file': self.tarfile.REGTYPE, 'dir': self.tarfile.DIRTYPE,
                    'symlink': self.tarfile.SYMTYPE, 'hardlink': self.tarfile.LNKTYPE,
                    'device': self.tarfile.CHRTYPE, 'fifo': self.tarfile.FIFOTYPE,
                    'sparse': self.tarfile.GNUTYPE_SPARSE}[kind]
                info.linkname = 'index.html' if kind in ('symlink', 'hardlink') else ''
                info.size = len(data) if kind == 'file' else 0
                archive.addfile(info, io.BytesIO(data) if kind == 'file' else None)
        return output.getvalue()

    def make_zip(self, entries):
        output = io.BytesIO()
        with warnings.catch_warnings(), zipfile.ZipFile(output, 'w') as archive:
            warnings.simplefilter('ignore', UserWarning)
            for name, data in entries:
                archive.writestr(name, data)
        return output.getvalue()

    def admit(self, **changes):
        args = {'source': self.source, 'run_id': 7, 'branch': 'major/state-contracts',
            'job_id': 20, 'artifact_id': 30, 'run': self.run, 'job': self.job,
            'artifact': self.artifact, 'archive': self.archive, 'job_log': self.logs}
        args.update(changes)
        # Admission itself must never acquire credentials, call GitHub or spawn children.
        with mock.patch.object(owner, 'api', side_effect=AssertionError('unexpected acquisition')):
            return self.pages.admit_pages_build(**args)

    def admit_archive(self, archive):
        artifact = dict(self.artifact, digest='sha256:'+owner.digest(archive), size_in_bytes=len(archive))
        return self.admit(archive=archive, artifact=artifact, job_log=self.make_log(artifact['digest']))

    def test_original_pages_shape_returns_exact_static_bytes_and_provenance(self):
        result = self.admit()
        self.assertEqual(result['files'], {'index.html': b'<h1>Original Pages</h1>',
            'pagefind/pagefind.js': b'export async function search() {}'})
        proof = result['provenance']
        self.assertEqual(proof['source_commit'], self.source)
        self.assertEqual((proof['run_id'], proof['job_id'], proof['artifact_id']), (7, 20, 30))
        self.assertEqual(proof['archive_sha256'], owner.digest(self.archive))
        self.assertEqual(proof['tar_sha256'], owner.digest(self.tar))
        self.assertEqual(proof['job_log_sha256'], owner.digest(self.logs))
        self.assertNotIn('PREPUBLICATION_READY', json.dumps(proof))
        self.assertEqual(self.admit(job_log=b'\xef\xbb\xbf'+self.logs)['files'], result['files'])
        main_run=copy.deepcopy(self.run);main_run['head_branch']='main'
        main_artifact=copy.deepcopy(self.artifact);main_artifact['workflow_run']['head_branch']='main'
        self.assertEqual(self.admit(branch='main',run=main_run,artifact=main_artifact)['files'],result['files'])

    def test_trusted_source_run_workflow_branch_job_and_attempt_are_exact(self):
        vectors = [('source', '0'*40), ('source', self.source[:39]), ('source', self.source.upper()),
            ('run_id', True), ('job_id', True), ('artifact_id', True), ('branch', 'feature/topic')]
        for field, value in vectors:
            with self.subTest(field=field, value=value), self.assertRaises(owner.ReadinessError):
                self.admit(**{field: value})
        for field, value in [('id',8), ('head_sha','b'*40), ('event','pull_request'),
            ('head_branch','main'), ('path','.github/workflows/ci.yml'), ('conclusion','failure'),
            ('status','in_progress'), ('run_attempt',2), ('repository',{'id':10,'full_name':'fork/codeArbiter'}),
            ('head_repository',{'id':10,'full_name':owner.REPOSITORY})]:
            with self.subTest(run=field), self.assertRaises(owner.ReadinessError):
                self.admit(run=dict(self.run, **{field:value}))
        for field, value in [('id',21), ('run_id',8), ('run_attempt',2), ('name','Unrelated build'),
                             ('status','in_progress'), ('conclusion','failure'), ('steps',[])]:
            with self.subTest(job=field), self.assertRaises(owner.ReadinessError):
                self.admit(job=dict(self.job, **{field:value}))

    def test_both_immutable_upload_pins_and_original_id_digest_window_are_required(self):
        for before, after in [(self.pages.PAGES_ACTION,'actions/upload-pages-artifact@v5'),
            (self.pages.NESTED_UPLOAD_ACTION,owner.UPLOAD_ACTION),
            ('Artifact ID 30','Artifact ID 31'),
            (self.artifact['digest'][7:],'b'*64),
            ('2026-11-14T15:00:02Z','2026-11-14T16:00:02Z')]:
            with self.subTest(before=before), self.assertRaises(owner.ReadinessError):
                self.admit(job_log=self.logs.replace(before.encode(),after.encode()))
        for log in (self.logs+self.logs, b'PrivateFixtureValue\xff', self.logs.replace(b'Z ',b' ')):
            with self.subTest(log=owner.digest(log)), self.assertRaises(owner.ReadinessError) as caught:
                self.admit(job_log=log)
            self.assertNotIn('PrivateFixtureValue', str(caught.exception))
        for step in (dict(self.job['steps'][0],conclusion='skipped'),
                     dict(self.job['steps'][0],started_at='2026-11-14T15:00:00')):
            with self.assertRaises(owner.ReadinessError):
                self.admit(job=dict(self.job,steps=[step]))
        with self.assertRaises(owner.ReadinessError):
            self.admit(job=dict(self.job,steps=self.job['steps']*2))

    def test_foreign_expired_missing_or_changed_artifact_bytes_refuse(self):
        for field,value in [('id',31),('name','site-browser-evidence'),('expired',True),
            ('size_in_bytes',0),('digest','sha256:'+'b'*64),('created_at','2026-11-14T16:00:00Z'),
            ('workflow_run',None),('workflow_run',dict(self.artifact['workflow_run'],repository_id=10)),
            ('workflow_run',dict(self.artifact['workflow_run'],head_sha='b'*40)),
            ('workflow_run',dict(self.artifact['workflow_run'],head_branch='main'))]:
            with self.subTest(field=field), self.assertRaises(owner.ReadinessError):
                self.admit(artifact=dict(self.artifact,**{field:value}))
        with self.assertRaises(owner.ReadinessError):
            self.admit(archive=self.archive+b'changed')
        typed_run=copy.deepcopy(self.run)
        typed_run['repository']['id']=typed_run['head_repository']['id']=1
        typed_artifact=copy.deepcopy(self.artifact)
        typed_artifact['workflow_run']['repository_id']=True
        typed_artifact['workflow_run']['head_repository_id']=1
        with self.assertRaises(owner.ReadinessError):
            self.admit(run=typed_run,artifact=typed_artifact)

    def test_only_one_plain_artifact_tar_zip_member_is_supported(self):
        for entries in ([('other.tar',self.tar)], [('artifact.tar',self.tar),('extra',b'x')],
                        [('artifact.tar',self.tar),('artifact.tar',self.tar)],
                        [('../artifact.tar',self.tar)]):
            with self.subTest(names=[n for n,_ in entries]), self.assertRaises(owner.ReadinessError):
                self.admit_archive(self.make_zip(entries))
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            info=zipfile.ZipInfo('artifact.tar');info.create_system=3;info.external_attr=0o120777<<16
            archive.writestr(info,b'target')
        with self.assertRaises(owner.ReadinessError):self.admit_archive(output.getvalue())
        with self.assertRaises(owner.ReadinessError):self.admit_archive(b'not a ZIP')
        encrypted=bytearray(self.archive)
        for position in (encrypted.index(b'PK\x03\x04')+6, encrypted.index(b'PK\x01\x02')+8):
            flags=int.from_bytes(encrypted[position:position+2],'little')|1
            encrypted[position:position+2]=flags.to_bytes(2,'little')
        with self.assertRaises(owner.ReadinessError):self.admit_archive(bytes(encrypted))
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            info=zipfile.ZipInfo('artifact.tar');info.create_system=3;info.external_attr=0o020600<<16
            archive.writestr(info,self.tar)
        with self.assertRaises(owner.ReadinessError):self.admit_archive(output.getvalue())

    def test_tar_traversal_aliases_links_devices_and_parent_conflicts_refuse(self):
        names=['../escape','/absolute','./../escape','././alias','C:/outside','a\\b','a//b',
               'CON.txt','NUL .txt','CONIN$','CONOUT$.txt','bad?name',' leading','trailing.','trailing ',
               '/'.join(['a']*33),'\u00e9.html','control\x01name']
        for name in names:
            with self.subTest(name=repr(name)), self.assertRaises(owner.ReadinessError):
                self.admit_archive(self.make_zip([('artifact.tar',self.make_tar([(name,'file',b'x')]))]))
        for kind in ('symlink','hardlink','device','fifo','sparse'):
            with self.subTest(kind=kind), self.assertRaises(owner.ReadinessError):
                self.admit_archive(self.make_zip([('artifact.tar',self.make_tar([('unsafe',kind,b'')]))]))
        for entries in ([('index.html','file',b'x'),('./index.html','file',b'y')],
            [('A/a','file',b'x'),('a/b','file',b'y')],
            [('root','file',b'x'),('root/child','file',b'y')],
            [('root/child','file',b'y'),('root','file',b'x')]):
            with self.subTest(entries=entries), self.assertRaises(owner.ReadinessError):
                self.admit_archive(self.make_zip([('artifact.tar',self.make_tar(entries))]))
        with self.assertRaises(owner.ReadinessError):
            self.admit_archive(self.make_zip([('artifact.tar',b'not a tar')]))
        with self.assertRaises(owner.ReadinessError):
            self.admit_archive(self.make_zip([('artifact.tar',self.tar+b'PrivateFixtureValue')]))
        output=io.BytesIO()
        with self.tarfile.open(fileobj=output,mode='w',format=self.tarfile.PAX_FORMAT) as archive:
            info=self.tarfile.TarInfo('index.html');info.pax_headers={'comment':'unsupported'}
            archive.addfile(info,io.BytesIO(b''))
        with self.assertRaises(owner.ReadinessError):
            self.admit_archive(self.make_zip([('artifact.tar',output.getvalue())]))

    def test_archive_tar_member_count_file_and_total_bounds_refuse(self):
        for constant, limit in [('MAX_ZIP_BYTES',32),('MAX_TAR_BYTES',32),('MAX_MEMBERS',2),('MAX_FILE_BYTES',8),('MAX_TOTAL_BYTES',8)]:
            with self.subTest(bound=constant), mock.patch.object(self.pages,constant,limit), self.assertRaises(owner.ReadinessError):
                self.admit()
        with mock.patch.object(self.pages,'MAX_LOG_BYTES',8), self.assertRaises(owner.ReadinessError):
            self.admit()

    def test_existing_direct_uploader_policy_is_not_relaxed_for_pages(self):
        self.assertEqual(owner.UPLOAD_ACTION,'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9')
        with mock.patch.object(owner,'api',return_value=self.logs), self.assertRaises(owner.ReadinessError):
            owner.validate_upload(self.job,self.artifact,'Upload Pages artifact')



class DualPayloadReportTest(unittest.TestCase):
    def test_original_v3_producer_authenticates_both_payloads_and_refuses_second_tamper(self):
        fixture=ReadinessTest("test_valid_receipt_is_non_circular");fixture.setUp()
        req=fixture.requirements
        def archive(name, data):
            output=io.BytesIO()
            with zipfile.ZipFile(output,"w") as z:z.writestr(name,data)
            return output.getvalue()
        content={12:archive("package",b"package bytes"),13:archive("stage",b"stage bytes")}
        table=[{"artifact_id":i,"archive_sha256":owner.digest(raw),"members":owner.members(raw)} for i,raw in content.items()]
        reports={}
        artifacts=[dict(fixture.build_artifacts[0],id=i,name="qualified-payload" if i==12 else "stage-original",digest="sha256:"+owner.digest(raw)) for i,raw in content.items()]
        for i,cell in enumerate(req["cells"]):
            name="major-qualification-"+str(20+i)
            artifacts.append({"id":30+i,"name":name})
            reports[name]={"schema":"codearbiter-major-qualification/3","source_commit":req["source_commit"],"source_tree":req["source_tree"],"ci_run_id":7,"job_id":20+i,"payloads":copy.deepcopy(table),
                "results":[{"cell":cell,"result":"PASSED","commands":[{"argv":["actual-original-check"],"exit_code":0}],"selected_population":1,"executed_population":1,"payload_artifact_ids":[12,13]}]}
        with mock.patch.object(owner,"read_artifact_json",side_effect=lambda a,r,n:reports[a["name"]]),mock.patch.object(owner,"validate_upload"),mock.patch.object(owner,"artifact_bytes",side_effect=lambda a,r:content[a["id"]]) as fetch:
            record=owner.produce(req,artifacts,fixture.jobs)
            self.assertEqual(fetch.call_count,2)
            self.assertEqual({p["artifact_id"] for p in record["artifacts"]},{12,13})
            self.assertTrue(all(r["evidence_artifact_ids"]==[12,13] for r in record["results"]))
            reports[next(iter(reports))]["payloads"][1]["members"][0]["sha256"]="0"*64
            with self.assertRaisesRegex(owner.ReadinessError,"qualification bytes differ"):
                owner.produce(req,artifacts,fixture.jobs)

    def test_v3_exact_dual_payload_table_preserves_distinct_original_identities(self):
        rows=[{"payload_artifact_ids":[12,13]}]
        table=[{"artifact_id":i,"archive_sha256":str(i%10)*64,"members":[{"path":"member","sha256":"a"*64}]} for i in [12,13]]
        result=owner.report_payloads({"schema":"codearbiter-major-qualification/3","payloads":table},rows)
        self.assertEqual(set(result),{12,13})

    def test_v3_duplicate_missing_mixed_scalar_and_unused_references_refuse(self):
        table=[{"artifact_id":i,"archive_sha256":"a"*64,"members":[{"path":"member","sha256":"b"*64}]} for i in [12,13]]
        for row in [{"payload_artifact_ids":[12,12]}, {"payload_artifact_ids":[13,12]},
                    {"payload_artifact_ids":[12,99]}, {"payload_artifact_ids":[12]},
                    {"payload_artifact_ids":[12,13],"payload_artifact_id":12},
                    {"payload_artifact_ids":[True,13]}, {"payload_artifact_ids":[12,13,14]}]:
            with self.subTest(row=row),self.assertRaises(owner.ReadinessError):
                owner.report_payloads({"schema":"codearbiter-major-qualification/3","payloads":table},[row])

    def test_final_readiness_verifies_every_plural_evidence_artifact(self):
        fixture=ReadinessTest("test_valid_receipt_is_non_circular");fixture.setUp()
        for row in fixture.record["results"]:
            row.pop("evidence_artifact_id");row["evidence_artifact_ids"]=[12,13]
        fixture.record["artifacts"].append({"artifact_id":13,"archive_sha256":"3"*64,"members":[{"path":"stage","sha256":"4"*64}]})
        fixture.build_artifacts.append(dict(fixture.build_artifacts[0],id=13,name="second-original",digest="sha256:"+"3"*64))
        self.assertEqual(fixture.verify()["state"],"PREPUBLICATION_READY")
        fixture.record["artifacts"][1]["archive_sha256"]="5"*64
        with self.assertRaises(owner.ReadinessError):fixture.verify()


class ProgramProducingGuardTest(unittest.TestCase):
    def test_finite_producer_catalog_does_not_require_unfinished_program_to_be_ready(self):
        root=Path(__file__).resolve().parents[2]
        source="a"*40
        def blob(repo,commit,path):
            self.assertEqual(commit,source)
            raw=(root/path).read_bytes()
            if path==owner.CORPUS+"execution/progress.json":
                progress=json.loads(raw)
                for task in progress["task_updates"]:task["status"]="PLANNED"
                return json.dumps(progress).encode()
            return raw
        with mock.patch.object(owner,"blob",side_effect=blob),mock.patch.object(owner,"command",return_value=b"b"*40):
            req=owner.producer_requirements(root,source,7)
            self.assertEqual(set(req),{"source_commit","source_tree","ci_run_id","cells","cell_jobs"})
            self.assertIn("installed:claude:workflow",req["cells"])
            self.assertEqual(set(req["cells"]),set(req["cell_jobs"]))
            with self.assertRaisesRegex(owner.ReadinessError,"unfinished required task"):
                owner.requirements(root,source,7)

    def test_program_push_is_producing_only_and_publication_reader_stays_main_only(self):
        fixture=ReadinessTest("test_valid_receipt_is_non_circular");fixture.setUp()
        run=dict(fixture.run,head_branch="major/state-contracts",conclusion=None)
        owner.validate_run(run,fixture.requirements,producing=True,allow_program_branch=True)
        for changes in ({"event":"pull_request"},{"head_branch":"feature/topic"},{"conclusion":"failure"},{"repository":{"full_name":"fork/codeArbiter"}}):
            with self.subTest(changes=changes),self.assertRaises(owner.ReadinessError):
                owner.validate_run(dict(run,**changes),fixture.requirements,producing=True,allow_program_branch=True)
        with self.assertRaises(owner.ReadinessError):
            owner.validate_run(dict(run,conclusion="success"),fixture.requirements,allow_program_branch=True)
        with self.assertRaises(owner.ReadinessError):
            fixture.verify(run=dict(run,conclusion="success"))


class HostedRawAuthenticationCacheTest(unittest.TestCase):
    def fixture(self):
        raw=b"original retained bytes"
        source="a"*40
        def record(commit=source,job=9,digest=None):
            return {"schema":"codearbiter-disposition-evidence/1","source_commit":commit,"kind":"test","result":"PASSED",
                "producer":{"class":"hosted","identity":"original job"},"raw_evidence":[{"run_id":7,"job_id":job,"artifact_id":10,"sha256":digest or owner.digest(raw)}],
                "inputs":{"owner.py":owner.digest(b"original owner")},"commands":[{"argv":["actual-original-check"],"exit_code":0}],
                "disposition_ids":["disposition:transitions:fixture"]}
        def api(path):
            if path=="actions/runs/7":return {"head_sha":source,"event":"push","repository":{"full_name":owner.REPOSITORY},"path":".github/workflows/docs.yml","head_branch":"major/state-contracts","conclusion":"success"}
            if path.startswith("actions/jobs/"):return {"run_id":7,"conclusion":"success" if path.endswith("/9") else "failure"}
            if path=="actions/artifacts/10":return {"id":10}
            raise AssertionError("unexpected API route")
        def call(name,rec,cache):
            blob=json.dumps(rec).encode()
            row={"status":"TESTED","evidence":[{"kind":"test","commit":rec["source_commit"],"ref":name,"sha256":owner.digest(blob)}]}
            def load(commit,path):return b"original owner" if path=="owner.py" else blob
            return owner.authenticate_recorded_disposition(Path.cwd(),source,"disposition:transitions:fixture",row,{"owner.py"},load,cache)
        return raw,record,api,call

    def test_distinct_proofs_share_only_positive_full_identity_raw_authentication(self):
        raw,record,api,call=self.fixture();cache={}
        with mock.patch.object(owner,"command",return_value=b""),mock.patch.object(owner,"api",side_effect=api),mock.patch.object(owner,"artifact_bytes",return_value=raw) as fetch:
            call("proof-one.json",record(),cache)
            call("proof-two.json",record(),cache)
            self.assertEqual(fetch.call_count,1,"same original source/run/job/artifact/digest must authenticate once per transaction")

    def test_other_source_job_digest_and_failed_authentication_never_reuse_success(self):
        raw,record,api,call=self.fixture();cache={}
        with mock.patch.object(owner,"command",return_value=b""),mock.patch.object(owner,"api",side_effect=api),mock.patch.object(owner,"artifact_bytes",return_value=raw) as fetch:
            call("valid.json",record(),cache)
            for name,rec in [("wrong-source.json",record(commit="b"*40)),("wrong-job.json",record(job=8)),("wrong-digest1.json",record(digest="0"*64)),("wrong-digest2.json",record(digest="0"*64))]:
                with self.subTest(name=name),self.assertRaises(owner.ReadinessError):call(name,rec,cache)
            self.assertEqual(fetch.call_count,3,"failed digest authentication must not be cached")


class UploadLogDiagnosticTest(unittest.TestCase):
    STDERR = (b"gh: controlled refusal (HTTP 403)\n"
              b"unit-private-diagnostic https://unit.invalid/?fixture=never-report\n")

    @staticmethod
    def expected(stderr, status=403):
        import hashlib
        return {"operation": "github-actions-job-log",
                "code": "UPLOAD_LOG_COMMAND_FAILED", "exit_code": 7,
                "http_status": status,
                "stderr_sha256": hashlib.sha256(stderr).hexdigest()}

    def failed_upload(self, stderr=None):
        stderr = self.STDERR if stderr is None else stderr
        job = {"id": 7, "steps": [{"name": "Upload exact payload",
            "status": "completed", "conclusion": "success",
            "started_at": "2026-11-15T15:00:00Z",
            "completed_at": "2026-11-15T15:00:01Z"}]}
        artifact = {"id": 11, "name": "unit-payload",
            "created_at": "2026-11-15T15:00:01Z", "digest": "sha256:" + "a" * 64}
        process = mock.Mock(returncode=7)
        process.communicate.return_value = (b"", stderr)
        with mock.patch.object(owner, "start", return_value=process) as start:
            with self.assertRaises(owner.ReadinessError) as caught:
                owner.validate_upload(job, artifact, "Upload exact payload")
        start.assert_called_once()
        self.assertEqual(start.call_args.args[0], ["gh", "api",
            "repos/arbiterForge/codeArbiter/actions/jobs/7/logs"])
        self.assertEqual(str(caught.exception), "upload attribution unavailable or malformed")
        self.assertEqual(str(caught.exception.__cause__), "readiness observation failed: gh")
        return caught.exception

    def test_upload_log_command_failure_retains_closed_diagnostic_through_attribution(self):
        cases = [(self.STDERR, 403),
                 (b"gh: first (HTTP 404)\ngh: second (HTTP 500)\n", None),
                 (b"gh: outside HTTP range (HTTP 999)\n", None),
                 (b"gh: malformed status (HTTP 403x)\n", None),
                 (b"unit-private-diagnostic with no status\n", None),
                 (b"gh: repeated (HTTP 403)\ngh: repeated (HTTP 403)\n", 403)]
        for stderr, status in cases:
            with self.subTest(status=status, stderr_sha256=self.expected(stderr, status)["stderr_sha256"]):
                error = self.failed_upload(stderr)
                # Existing exception API, safe missing-field assertion on old code.
                detail = getattr(error.__cause__, "command_diagnostic", None)
                self.assertEqual(detail, self.expected(stderr, status))
                encoded = json.dumps(detail)
                self.assertNotIn("unit-private-diagnostic", encoded)
                self.assertNotIn("unit.invalid", encoded)
                self.assertNotIn("never-report", encoded)

    def test_unrelated_command_failure_has_no_upload_log_diagnostic(self):
        process = mock.Mock(returncode=7)
        process.communicate.return_value = (b"", self.STDERR)
        with mock.patch.object(owner, "start", return_value=process) as start:
            with self.assertRaises(owner.ReadinessError) as caught:
                owner.command(["gh", "api", "repos/arbiterForge/codeArbiter/actions/runs/7"])
        start.assert_called_once()
        self.assertEqual(str(caught.exception), "readiness observation failed: gh")
        self.assertIsNone(getattr(caught.exception, "command_diagnostic", None))
        self.assertNotIn("unit-private-diagnostic", repr(caught.exception))



class UploadLogHTTPTransportTest(unittest.TestCase):
    TOKEN_LABEL = "unit-environment-credential-label"

    def setUp(self):
        UploadAttributionTest.setUp(self)

    def observe_upload(self, *, token=True, worker_output=None, worker_exit=0, worker_stderr=b"", artifact=None):
        import os
        selected = []
        def launch(argv, **kwargs):
            process = mock.Mock()
            is_http = argv[0] == sys.executable
            process.returncode = worker_exit if is_http else 1
            process.communicate.return_value = ((self.logs if worker_output is None else worker_output), worker_stderr) if is_http else (b"", b"unit opaque gh refusal")
            selected.append((list(argv), kwargs, process))
            return process
        environment = {key:value for key,value in os.environ.items()
                       if key.upper() in {"SYSTEMROOT","WINDIR","TEMP","TMP"}}
        environment["UNIT_OTHER_CREDENTIAL"] = "unit-unrelated-do-not-inherit"
        if token:
            environment["GH_TOKEN"] = self.TOKEN_LABEL
        error = None
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(owner, "start", side_effect=launch):
            try:
                owner.validate_upload(self.job, artifact or self.artifact, "Upload major qualification report")
            except owner.ReadinessError as caught:
                error = caught
        return selected, error

    def assert_http_worker(self, selected):
        self.assertEqual(len(selected), 1, "one transport attempt, no failure fallback")
        argv, kwargs, process = selected[0]
        self.assertEqual(argv[:5], [sys.executable, "-I", "-S", "-B", "-c"], "environment-token job log must select the isolated HTTP worker")
        self.assertGreaterEqual(len(argv), 7)
        self.assertNotIn(self.TOKEN_LABEL, " ".join(argv))
        self.assertEqual(kwargs.get("env", {}).get("GH_TOKEN"), self.TOKEN_LABEL)
        self.assertNotIn("GITHUB_TOKEN", kwargs.get("env", {}))
        self.assertNotIn("UNIT_OTHER_CREDENTIAL", kwargs.get("env", {}))
        import os
        worker_environment={key.upper():value for key,value in kwargs.get("env",{}).items()}
        self.assertLessEqual(set(worker_environment),{"GH_TOKEN","SYSTEMROOT","WINDIR","TEMP","TMP"})
        for key,value in os.environ.items():
            if key.upper() in {"SYSTEMROOT","WINDIR","TEMP","TMP"}:
                self.assertEqual(worker_environment.get(key.upper()),value)
        process.communicate.assert_called_once_with(timeout=120)
        return argv

    def test_environment_token_reads_original_attribution_without_opaque_gh_client(self):
        selected, error = self.observe_upload()
        self.assertIsNone(error, "original valid uploader log must remain readable through environment-token HTTP even when inert gh refuses")
        self.assert_http_worker(selected)

    def test_no_token_selects_existing_gh_once_before_any_http_attempt(self):
        selected, error = self.observe_upload(token=False)
        self.assertIsInstance(error, owner.ReadinessError)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][0], ["gh", "api", "repos/arbiterForge/codeArbiter/actions/jobs/20/logs"])
        selected[0][2].communicate.assert_called_once_with(timeout=120)

    def test_http_failure_keeps_actual_exit_hash_status_and_reason_without_retry(self):
        import hashlib
        stderr = b'{"transport_reason":"http_error","http_status":403}\n'
        selected, error = self.observe_upload(worker_exit=9, worker_stderr=stderr)
        self.assertIsInstance(error, owner.ReadinessError)
        self.assert_http_worker(selected)
        detail = getattr(error.__cause__, "command_diagnostic", None)
        self.assertEqual(detail, {"operation":"github-actions-job-log", "code":"UPLOAD_LOG_COMMAND_FAILED", "exit_code":9,
            "http_status":403, "stderr_sha256":hashlib.sha256(stderr).hexdigest(), "transport_reason":"http_error"})
        self.assertEqual(str(error), "upload attribution unavailable or malformed")
        self.assertNotIn(self.TOKEN_LABEL, repr(error))

    def test_malformed_worker_error_protocol_is_worker_failed_without_reflected_values(self):
        import hashlib
        for stderr in (b"unit-private-malformed", b'{"transport_reason":"http_error","http_status":403,"extra":"unit-private"}',
                       b'{"transport_reason":"unit-private","http_status":403}', b'{"transport_reason":"http_error","http_status":true}'):
            with self.subTest(stderr_digest=hashlib.sha256(stderr).hexdigest()):
                selected,error=self.observe_upload(worker_exit=9,worker_stderr=stderr)
                self.assert_http_worker(selected)
                detail=getattr(error.__cause__,"command_diagnostic",None)
                self.assertIs(type(detail),dict)
                self.assertEqual(detail.get("transport_reason"),"worker_failed")
                self.assertEqual(detail.get("http_status"),None)
                self.assertEqual(detail.get("exit_code"),9)
                self.assertEqual(detail.get("stderr_sha256"),hashlib.sha256(stderr).hexdigest())
                self.assertNotIn("unit-private",json.dumps(detail))

    def test_http_worker_keeps_120s_timeout_and_original_tree_cleanup(self):
        import os
        process=mock.Mock(returncode=None)
        process.communicate.side_effect=[subprocess.TimeoutExpired("unit-worker",120),(b"",b"")]
        with mock.patch.dict(os.environ,{"GH_TOKEN":self.TOKEN_LABEL},clear=True), \
             mock.patch.object(owner,"start",return_value=process) as launch, \
             mock.patch.object(owner,"terminate_tree",return_value="unconfirmed") as cleanup:
            with self.assertRaises(owner.ReadinessError) as caught:
                owner.validate_upload(self.job,self.artifact,"Upload major qualification report")
        self.assertEqual(launch.call_args.args[0][:5],[sys.executable,"-I","-S","-B","-c"])
        self.assertEqual(process.communicate.call_args_list,[mock.call(timeout=120),mock.call(timeout=3)])
        cleanup.assert_called_once_with(process)
        self.assertIn("containment=unconfirmed",str(caught.exception.__cause__))

    def test_token_does_not_change_non_job_log_api_transport(self):
        import os
        process=mock.Mock(returncode=0);process.communicate.return_value=(b"{}",b"")
        with mock.patch.dict(os.environ,{"GH_TOKEN":self.TOKEN_LABEL},clear=True),mock.patch.object(owner,"start",return_value=process) as launch:
            self.assertEqual(owner.api("actions/jobs/20"),{})
        self.assertEqual(launch.call_args.args[0],["gh","api","repos/arbiterForge/codeArbiter/actions/jobs/20"])

    def test_http_transport_never_relaxes_original_artifact_identity_predicates(self):
        for change in ({"id":31}, {"digest":"sha256:"+"b"*64}, {"name":"different-artifact"}):
            with self.subTest(changed=sorted(change)):
                selected, error = self.observe_upload(artifact=dict(self.artifact, **change))
                self.assert_http_worker(selected)
                self.assertIsInstance(error, owner.ReadinessError)




class UploadLogHTTPWorkerBoundaryTest(unittest.TestCase):
    TOKEN_LABEL=UploadLogHTTPTransportTest.TOKEN_LABEL
    setUp=UploadLogHTTPTransportTest.setUp
    observe_upload=UploadLogHTTPTransportTest.observe_upload
    assert_http_worker=UploadLogHTTPTransportTest.assert_http_worker
    def worker_source(self):
        selected, _ = self.observe_upload()
        argv = self.assert_http_worker(selected)
        self.assertIs(type(argv[5]), str)
        self.assertNotIn(self.TOKEN_LABEL, argv[5])
        return argv[5], argv[6:]

    def execute_inert_worker(self, responses):
        import contextlib
        import email.message
        import os
        import socket
        import ssl
        import urllib.request
        import urllib.response
        source, arguments = self.worker_source()
        calls, reads = [], []
        class Body(io.BytesIO):
            def read(self, count=-1):
                reads.append(count)
                return super().read(count)
        class InertHTTPS(urllib.request.AbstractHTTPHandler):
            def __init__(self, *args, **kwargs):
                super().__init__()
            def https_open(self, request):
                calls.append({"url":request.full_url,
                    "headers":{key.lower():value for key,value in request.header_items()}})
                if len(calls) > len(responses):
                    raise AssertionError("inert fixture exhausted; no external request allowed")
                value=responses[len(calls)-1]
                if isinstance(value, BaseException):
                    raise value
                code, headers, payload=value
                message=email.message.Message()
                for key, content in headers.items():
                    message[key]=content
                reply=urllib.response.addinfourl(Body(payload), message, request.full_url, code=code)
                reply.msg="fixture"
                return reply
            https_request=urllib.request.AbstractHTTPHandler.do_request_
        stdout_bytes, stderr_bytes=io.BytesIO(),io.BytesIO()
        stdout=io.TextIOWrapper(stdout_bytes, encoding="utf-8", write_through=True)
        stderr=io.TextIOWrapper(stderr_bytes, encoding="utf-8", write_through=True)
        exit_code=0
        with contextlib.ExitStack() as stack:
            environment={key:value for key,value in os.environ.items()
                         if key.upper() in {"SYSTEMROOT","WINDIR","TEMP","TMP"}}
            environment["GH_TOKEN"]=self.TOKEN_LABEL
            stack.enter_context(mock.patch.dict(os.environ,environment,clear=True))
            stack.enter_context(mock.patch.object(sys,"argv",["-c",*arguments]))
            stack.enter_context(mock.patch.object(sys,"stdout",stdout))
            stack.enter_context(mock.patch.object(sys,"stderr",stderr))
            stack.enter_context(mock.patch.object(urllib.request,"HTTPSHandler",InertHTTPS))
            stack.enter_context(mock.patch.object(socket,"create_connection",side_effect=AssertionError("network forbidden")))
            stack.enter_context(mock.patch.object(socket,"getaddrinfo",side_effect=AssertionError("DNS forbidden")))
            try:
                exec(compile(source,"<fixed-public-job-log-worker>","exec"),{"__name__":"__main__"})
            except SystemExit as stopped:
                exit_code=0 if stopped.code is None else stopped.code
        stdout.flush();stderr.flush()
        observed=(exit_code,stdout_bytes.getvalue(),stderr_bytes.getvalue(),calls,reads)
        stdout.detach();stderr.detach()
        self.assertIs(type(exit_code),int)
        self.assertLessEqual(len(observed[2]),4096)
        self.assertNotIn(self.TOKEN_LABEL.encode(),observed[2])
        self.assertNotIn(b"unit-private",observed[2])
        self.assertNotIn(b"https://",observed[2])
        return observed

    def reason(self, observed, expected, status=None):
        code, stdout, stderr, _, _=observed
        self.assertNotEqual(code,0)
        self.assertEqual(stdout,b"")
        self.assertEqual(json.loads(stderr),{"transport_reason":expected,"http_status":status})

    def test_worker_follows_official_https_redirect_without_forwarding_authorization(self):
        for target in ("https://unit.actions.githubusercontent.com/owned-log?unit-private=signed",
                       "https://unit.blob.core.windows.net/owned-log?unit-private=signed"):
            with self.subTest(storage=target.split('/')[2]):
                observed=self.execute_inert_worker([(302,{"Location":target},b""),(200,{},self.logs)])
                code, stdout, stderr, calls, reads=observed
                self.assertEqual((code,stdout,stderr),(0,self.logs,b""))
                self.assertEqual(len(calls),2)
                self.assertEqual(calls[0]["url"],"https://api.github.com/repos/arbiterForge/codeArbiter/actions/jobs/20/logs")
                self.assertIn(self.TOKEN_LABEL,calls[0]["headers"].get("authorization",""))
                self.assertNotIn("authorization",calls[1]["headers"])
                self.assertTrue(reads)

    def test_worker_refuses_non_https_foreign_userinfo_and_suffix_confusion_redirects(self):
        for target in ("http://unit.blob.core.windows.net/log", "https://foreign.invalid/log",
                       "https://unit.blob.core.windows.net.foreign.invalid/log",
                       "https://unit-private@api.github.com/log", "https://api.github.com:444/log"):
            with self.subTest(kind=target.split(':',1)[0]):
                observed=self.execute_inert_worker([(302,{"Location":target},b"")])
                self.reason(observed,"redirect_refused")
                self.assertEqual(len(observed[3]),1)

    def test_worker_drops_authorization_even_on_api_redirect_and_bounds_redirect_chain(self):
        target="https://api.github.com/repos/arbiterForge/codeArbiter/actions/jobs/20/logs?unit-private=redirect"
        observed=self.execute_inert_worker([(302,{"Location":target},b""),(200,{},self.logs)])
        self.assertEqual(observed[0],0);self.assertNotIn("authorization",observed[3][1]["headers"])
        chain=[(302,{"Location":"https://unit.actions.githubusercontent.com/owned-"+str(i)},b"") for i in range(5)]
        observed=self.execute_inert_worker(chain)
        self.reason(observed,"redirect_limit");self.assertEqual(len(observed[3]),4)
        self.assertTrue(all("authorization" not in call["headers"] for call in observed[3][1:]))

    def test_worker_refuses_over_32mib_body_without_unbounded_read_or_partial_stdout(self):
        bound=32*1024*1024
        observed=self.execute_inert_worker([(200,{},b"x"*(bound+1))])
        self.reason(observed,"body_limit")
        self.assertTrue(observed[4])
        self.assertTrue(all(type(n) is int and 0<n<=bound+1 for n in observed[4]))
        self.assertLessEqual(sum(observed[4]),bound+1)

    def test_worker_http_and_native_errors_have_only_closed_reason_status(self):
        import socket
        import ssl
        import urllib.error
        self.reason(self.execute_inert_worker([(403,{},b"unit-private-provider-body")]),"http_error",403)
        for reason, error in (
            ("dns_error",urllib.error.URLError(socket.gaierror(1,"unit-private-native-error"))),
            ("tls_error",urllib.error.URLError(ssl.SSLError("unit-private-native-error"))),
            ("timeout",urllib.error.URLError(TimeoutError("unit-private-native-error"))),
            ("network_error",urllib.error.URLError("unit-private-native-error"))):
            with self.subTest(reason=reason):
                self.reason(self.execute_inert_worker([error]),reason)




class TypedSourceDispositionTests(unittest.TestCase):
    """Owned immutable proof fixtures; artifact APIs below are inert unit seams."""
    def setUp(self):
        import os
        import tempfile
        self.private = tempfile.TemporaryDirectory()
        self.addCleanup(self.private.cleanup)
        self.repo = Path(self.private.name)
        self.env = {key: value for key, value in os.environ.items()
                    if key.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                        GIT_TERMINAL_PROMPT='0', GIT_AUTHOR_NAME='Inert fixture',
                        GIT_AUTHOR_EMAIL='fixture@example.invalid', GIT_COMMITTER_NAME='Inert fixture',
                        GIT_COMMITTER_EMAIL='fixture@example.invalid')
        self.git('init', '-q')
        (self.repo / 'owner.py').write_bytes(b'# inert source contract\n')
        self.git('add', 'owner.py'); self.git('commit', '-qm', 'owned source fixture')
        self.base = self.git('rev-parse', 'HEAD').decode().strip()
        self.cell = 'disposition:transitions:fixture:01'
        self.proof = {'schema': 'codearbiter-disposition-evidence/1', 'kind': 'conformance-check',
            'result': 'PRESERVED', 'source_commit': self.base,
            'producer': {'class': 'source-conformance', 'identity': 'inert owned unit fixture'},
            'disposition_ids': [self.cell], 'inputs': {'owner.py': owner.digest((self.repo/'owner.py').read_bytes())},
            'raw_evidence': [{'path': 'raw.txt', 'sha256': owner.digest(b'inert inspection witness\n')}]}
        self.retain()

    def git(self, *args):
        return subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'commit.gpgsign=false',
            '-c', 'core.hooksPath=' + str(self.repo/'no-hooks'), *args], cwd=self.repo,
            env=self.env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10).stdout

    def retain(self):
        content = json.dumps(self.proof, sort_keys=True).encode()
        (self.repo/'proof.json').write_bytes(content)
        (self.repo/'raw.txt').write_bytes(b'inert inspection witness\n')
        self.git('add', 'proof.json', 'raw.txt'); self.git('commit', '--allow-empty', '-qm', 'retain original proof')
        self.source = self.git('rev-parse', 'HEAD').decode().strip()
        self.row = {'status': self.proof['result'],
            **({'contract':'fixture:contract'} if self.proof['result']=='NOT_APPLICABLE' else {}), 'evidence': [{
            'kind': self.proof['kind'], 'commit': self.base, 'ref_commit': self.source,
            'ref': 'proof.json', 'sha256': owner.digest(content)}]}
        self.cache = {}

    def authenticate(self):
        return owner.authenticate_disposition(self.repo, self.source, self.cell, self.row,
            {'owner.py'}, lambda commit, path: owner.blob(self.repo, commit, path), self.cache)

    def expected_typed(self):
        item = self.row['evidence'][0]
        return {'result': self.row['status'],
            **({'contract': self.row['contract']} if self.row['status'] == 'NOT_APPLICABLE' else {}), 'proofs': [{
            'ref': item['ref'], 'ref_commit': item['ref_commit'], 'sha256': item['sha256'],
            'source_commit': item['commit'], 'kind': self.proof['kind'], 'result': self.proof['result'],
            'producer': self.proof['producer'], 'current_at': self.source,
            **({'contract': self.proof['contract'], 'rationale': self.proof['rationale']}
               if self.row['status'] == 'NOT_APPLICABLE' else {})}]}

    def producer(self, typed):
        runtime = 'installed:fixture:package'
        req = {'source_commit': self.source, 'source_tree': self.git('rev-parse', 'HEAD^{tree}').decode().strip(),
            'ci_run_id': 7, 'task_ids': ['Q-02'], 'targets': [], 'cells': [self.cell, runtime],
            'cell_jobs': {self.cell: 'major qualification / source fixture', runtime: 'inert runtime owner'},
            'source_dispositions': {self.cell: typed}, 'required_artifact_names': ['qualified-payload'],
            'disposition_evidence_sha256': owner.digest(json.dumps(self.authenticate(), sort_keys=True).encode())}
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as zipped:
            zipped.writestr('package.txt', b'inert package fixture')
        data = output.getvalue()
        payload = {'id': 12, 'name': 'qualified-payload', 'expired': False, 'size_in_bytes': len(data),
            'digest': 'sha256:' + owner.digest(data), 'workflow_run': {'id': 7, 'head_sha': self.source}}
        report_artifact = {'id': 30, 'name': 'major-qualification-20'}
        report = {'schema': 'codearbiter-major-qualification/1', 'source_commit': self.source,
            'source_tree': req['source_tree'], 'ci_run_id': 7, 'job_id': 20, 'results': [{
            'cell': runtime, 'result': 'PASSED', 'commands': [{'argv': ['inert-unit-command'], 'exit_code': 0}],
            'selected_population': 1, 'executed_population': 1, 'payload_artifact_id': 12,
            'payload_archive_sha256': owner.digest(data), 'payload_members': owner.members(data)}]}
        jobs = [{'id': 20, 'name': 'inert runtime owner', 'conclusion': 'success'},
                {'id': 99, 'name': 'major readiness producer', 'conclusion': 'success'}]
        with mock.patch.object(owner, 'validate_upload'), \
             mock.patch.object(owner, 'read_artifact_json', return_value=report), \
             mock.patch.object(owner, 'api', return_value=data):
            record = owner.produce(req, [payload, report_artifact], jobs)
        return req, record, jobs, [payload, report_artifact]

    def test_current_authenticated_source_proof_needs_no_fictional_executed_job(self):
        authenticated = self.authenticate()
        self.assertEqual(authenticated[0]['source_commit'], self.base)
        self.assertTrue(self.cache[('current-proof', self.source,
            ('proof', self.source, 'proof.json', self.row['evidence'][0]['sha256']))])
        req, record, jobs, artifacts = self.producer(self.expected_typed())
        self.assertEqual(record['schema'], 'codearbiter-major-readiness/3')
        self.assertEqual(record['source_dispositions'][self.cell]['result'], 'PRESERVED')
        self.assertEqual([row['cell'] for row in record['runtime']['results']], ['installed:fixture:package'])
        self.assertNotIn('job_id', record['source_dispositions'][self.cell])
        self.assertEqual(record['disposition_evidence_sha256'], req['disposition_evidence_sha256'])


    def test_requirements_derives_source_facts_after_real_immutable_authentication(self):
        corpus = owner.CORPUS
        data = {
            corpus+'contracts/program.json': {'id': owner.PROGRAM, 'counts': {'tasks':82,'findings':70,
                'machines':287,'transitions':1748,'composed_scenarios':31},
                'delivery_predicates': {'PREPUBLICATION_READY': {'required_task_ids':['Q-02']}}},
            corpus+'contracts/tasks.json': {'tasks':[{'id':'Q-02','owner':'fixture', 'required_before_publication':True}]},
            corpus+'execution/progress.json': {'task_updates':[{'id':'Q-02','status':'DONE'}]},
            corpus+'execution/coverage-ledger.json': {'findings':{},'machines':{},'added_transitions':{},
                'transitions':{'fixture:01':self.row}},
            corpus+'contracts/finding-dispositions.json': {'records':[]},
            corpus+'contracts/machine-coverage.json': {'machines':[]},
            corpus+'contracts/transition-coverage.json': {'transitions':[{'transition_id':'fixture:01',
                'task_ids':['Q-02'], 'baseline':{'source':[{'path':'owner.py'}]}}]},
            corpus+'contracts/scenarios.json': {'scenarios':[{'id':'fixture-scenario'}]},
            corpus+'MANIFEST.json': {'files':[]},
            '.github/major-qualification-policy.json': {'program_id':owner.PROGRAM,
                'required_installed_cells':['installed:fixture:package']},
            '.github/integration-candidate.json': {'schema':'codearbiter-integration-candidate/1',
                'branch':'major/state-contracts','baseline_main_commit':self.base,
                'candidates':{'ca':'4.0.0','ca-codex':'0.30.0','ca-pi':'0.30.0','ca-sandbox':'0.2.0'}}}
        for path, value in data.items():
            file = self.repo/path; file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes(json.dumps(value).encode())
        for path, raw in {'.codearbiter/open-questions.md':b'# Open questions\n_None open._\n',
                          '.codearbiter/decisions/adr-lifecycle.jsonl':b''}.items():
            file = self.repo/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(raw)
        self.git('add','.');self.git('commit','-qm','owned requirements fixture')
        self.source = self.git('rev-parse','HEAD').decode().strip()
        original_command = owner.command
        def local(argv, repo=None, **kwargs):
            # The unrelated accepted-ADR child is inert; every Git/proof read is real.
            if kwargs.get('local_adr'):
                return b''
            return original_command(argv, repo, **kwargs)
        with mock.patch.object(owner,'command',side_effect=local):
            req = owner.requirements(self.repo,self.source,7)
        self.assertEqual(req['source_dispositions'],{self.cell:self.expected_typed()})
        self.assertIn('task:Q-02',owner.source_runtime_requirements(req)['cells'])
        self.assertIn('scenario:fixture-scenario',owner.source_runtime_requirements(req)['cells'])
        self.assertIn('installed:fixture:package',owner.source_runtime_requirements(req)['cells'])
        # Metadata DONE does not remove the independently executed task obligation.
        self.assertNotIn(self.cell,owner.source_runtime_requirements(req)['cells'])
        self.assertEqual(req['disposition_evidence_sha256'],owner.digest(json.dumps(
            {self.cell:self.authenticate()},sort_keys=True,separators=(',',':')).encode()))

    def test_exact_contract_not_applicable_keeps_rationale_and_original_history(self):
        self.proof.update(result='NOT_APPLICABLE',contract='fixture:contract',
                          rationale='This inert source contract excludes the unadvertised operation.')
        self.retain();self.authenticate()
        fact = owner.authenticated_source_disposition(self.source,self.cell,self.row,self.cache)
        self.assertEqual(fact,self.expected_typed())
        self.assertEqual(fact['proofs'][0]['source_commit'],self.base)
        self.assertNotEqual(self.base,fact['proofs'][0]['ref_commit'])
        self.row['contract']='different-contract'
        with self.assertRaisesRegex(owner.ReadinessError,'contract/rationale'):
            self.authenticate()
        self.row['contract']='fixture:contract';self.proof['rationale']=''
        self.retain()
        with self.assertRaisesRegex(owner.ReadinessError,'contract/rationale'):
            self.authenticate()

    def test_stale_missing_raw_wrong_scope_and_unavailable_history_never_become_source_facts(self):
        load = lambda commit,path:owner.blob(self.repo,commit,path)
        for label, mutate in [('raw',lambda raw: b'changed raw'),('input',lambda raw:b'changed input')]:
            def changed(commit,path):
                if path == ('raw.txt' if label=='raw' else 'owner.py'):
                    return mutate(load(commit,path))
                return load(commit,path)
            with self.subTest(label=label),self.assertRaises(owner.ReadinessError):
                owner.authenticate_disposition(self.repo,self.source,self.cell,self.row,{'owner.py'},changed,{})
        row = copy.deepcopy(self.row);row['evidence'][0]['ref_commit']='f'*40
        with self.assertRaises(owner.ReadinessError):
            owner.authenticate_disposition(self.repo,self.source,self.cell,row,{'owner.py'},load,{})
        self.proof['disposition_ids']=['disposition:transitions:other:01'];self.retain()
        with self.assertRaisesRegex(owner.ReadinessError,'does not cover'):
            self.authenticate()
        self.proof['disposition_ids']=[self.cell];self.retain()
        (self.repo/'owner.py').write_bytes(b'# current source changed\n')
        self.git('add','owner.py');self.git('commit','-qm','make prior source proof stale')
        self.source=self.git('rev-parse','HEAD').decode().strip()
        with self.assertRaisesRegex(owner.ReadinessError,'retained evidence bytes differ'):
            self.authenticate()

    def test_runtime_mixed_proofs_and_legacy_passed_reviews_stay_on_executed_path(self):
        for kind,result,producer in [('test','PRESERVED','local-host'),
                                    ('review','PASSED','independent-review'),
                                    ('review','PRESERVED','local-host')]:
            self.proof.update(kind=kind,result=result,producer={'class':producer,'identity':'inert fixture'})
            self.retain();self.row['status']='PRESERVED';self.authenticate()
            self.assertIsNone(owner.authenticated_source_disposition(self.source,self.cell,self.row,self.cache))
        for cell in ('task:Q-02','scenario:fixture','installed:fixture'):
            self.assertIsNone(owner.authenticated_source_disposition(self.source,cell,self.row,self.cache))
        self.row['status']='TESTED'
        self.assertIsNone(owner.authenticated_source_disposition(self.source,self.cell,self.row,self.cache))
        self.proof.update(kind='conformance-check',result='PRESERVED',
                          producer={'class':'source-conformance','identity':'inert fixture'})
        self.retain();self.authenticate()
        self.cache.pop(('current-proof',self.source,('proof',self.source,'proof.json',self.row['evidence'][0]['sha256'])))
        with self.assertRaisesRegex(owner.ReadinessError,'strict current'):
            owner.authenticated_source_disposition(self.source,self.cell,self.row,self.cache)

    def test_closed_source_shapes_cannot_omit_duplicate_or_relabel_runtime_population(self):
        self.authenticate();req,record,_,_=self.producer(self.expected_typed())
        mutations = [lambda r:r['source_dispositions'].clear(),
            lambda r:r['cells'].append(self.cell),
            lambda r:r['cell_jobs'].pop('installed:fixture:package'),
            lambda r:r['source_dispositions'][self.cell].update(result='PASSED'),
            lambda r:r['source_dispositions'][self.cell].update(job_id=99),
            lambda r:r['source_dispositions'][self.cell]['proofs'][0].update(kind='test'),
            lambda r:r['source_dispositions'][self.cell]['proofs'][0].update(current_at='e'*40),
            lambda r:r['source_dispositions'][self.cell]['proofs'][0]['producer'].update(**{'class':'hosted'}),
            lambda r:r['source_dispositions'][self.cell]['proofs'].append(copy.deepcopy(r['source_dispositions'][self.cell]['proofs'][0])),
            lambda r:r['source_dispositions'].update({'installed:fixture:package':copy.deepcopy(r['source_dispositions'][self.cell])})]
        for index,mutate in enumerate(mutations):
            wrong=copy.deepcopy(req);mutate(wrong)
            with self.subTest(index=index),self.assertRaises(owner.ReadinessError):
                owner.source_runtime_requirements(wrong)
        self.assertEqual(set(req['cells']),set(req['source_dispositions'])|set(record['runtime']['cells']))
        self.assertFalse(set(req['source_dispositions'])&set(record['runtime']['cells']))

    def test_final_reader_reconstructs_typed_facts_and_keeps_original_main_execution_guards(self):
        self.authenticate();req,record,jobs,artifacts=self.producer(self.expected_typed())
        run={'id':7,'head_sha':self.source,'head_branch':'main','event':'push','conclusion':'success',
             'path':'.github/workflows/ci.yml','repository':{'full_name':owner.REPOSITORY}}
        artifact={'id':11,'name':'major-readiness-'+self.source,'expired':False,'size_in_bytes':100,'digest':'sha256:'+'f'*64,
                  'workflow_run':{'id':7,'head_sha':self.source}}
        args=dict(record=record,requirements=req,run=run,artifact=artifact,archive_digest='f'*64,
                  jobs=jobs,build_artifacts=artifacts,payload_members={12:record['runtime']['artifacts'][0]['members']})
        with mock.patch.object(owner,'validate_upload'):
            self.assertEqual(owner.verify(**args)['state'],'PREPUBLICATION_READY')
            for field,value in [('head_branch','major/state-contracts'),('event','pull_request'),('conclusion','failure')]:
                with self.subTest(field=field),self.assertRaises(owner.ReadinessError):
                    owner.verify(**dict(args,run=dict(run,**{field:value})))
            for label,mutate in [('source',lambda r:r['source_dispositions'][self.cell]['proofs'][0].update(sha256='e'*64)),
                ('omitted',lambda r:r['runtime']['results'].clear()),
                ('skipped',lambda r:r['runtime']['results'][0].update(result='SKIPPED')),
                ('recursive',lambda r:r['runtime'].update(schema=owner.SOURCE_SCHEMA)),
                ('package',lambda r:r['runtime']['artifacts'][0].update(archive_sha256='e'*64)),
                ('task',lambda r:r['runtime']['task_ids'].append('Q-03'))]:
                wrong=copy.deepcopy(record);mutate(wrong)
                with self.subTest(label=label),self.assertRaises(owner.ReadinessError):
                    owner.verify(**dict(args,record=wrong))
            with self.assertRaisesRegex(owner.ReadinessError,'typed source readiness envelope'):
                owner.verify(**dict(args,record=record['runtime']))


    def test_typed_runtime_keeps_docs_separate_success_and_exact_tar_promotion(self):
        import tempfile
        import os
        import test_site_playwright_observation as fixture
        docs_case = fixture.DocsAuthorityTests()
        docs_case.setUp()
        docs = docs_case.docs
        self.authenticate();req,record,jobs,artifacts=self.producer(self.expected_typed())
        runtime_req = owner.source_runtime_requirements(req)
        docs_req = {**copy.deepcopy(runtime_req), 'cells':runtime_req['cells']+fixture.CELLS,
                    'cell_jobs':{**runtime_req['cell_jobs'],**dict.fromkeys(fixture.CELLS,fixture.JOB)}}
        docs_record = {'schema':docs.ENVELOPE,'program_id':owner.PROGRAM,'state':'PREPUBLICATION_READY',
                       **docs_req,'core':record['runtime'],'docs':{'run_id':17}}
        full_req = {**docs_req,'source_dispositions':req['source_dispositions'],
                    'cells':docs_req['cells']+[self.cell],
                    'cell_jobs':{**docs_req['cell_jobs'],self.cell:req['cell_jobs'][self.cell]}}
        envelope = {'schema':owner.SOURCE_SCHEMA,'program_id':owner.PROGRAM,'state':'PREPUBLICATION_READY',
                    **full_req,'runtime':docs_record}
        run={'id':7,'head_sha':self.source,'head_branch':'main','event':'push','conclusion':'success',
             'path':'.github/workflows/ci.yml','repository':{'full_name':owner.REPOSITORY}}
        artifact={'id':11,'name':'major-readiness-'+self.source,'expired':False,'size_in_bytes':100,
                  'digest':'sha256:'+'f'*64,'workflow_run':{'id':7,'head_sha':self.source}}
        args=dict(record=envelope,requirements=full_req,run=run,artifact=artifact,archive_digest='f'*64,
                  jobs=jobs,build_artifacts=artifacts)
        with mock.patch.object(docs,'admit',return_value=docs_record['docs']) as admit, \
             mock.patch.object(owner,'validate_upload'):
            self.assertEqual(owner.verify(**args)['docs_run_id'],17)
            with mock.patch.object(docs,'admit',side_effect=owner.ReadinessError('Docs run not successful')), \
                 self.assertRaisesRegex(owner.ReadinessError,'Docs run not successful'):
                owner.verify(**args)
            wrong=copy.deepcopy(envelope);wrong['runtime']['docs']['run_id']=7
            with self.assertRaises(owner.ReadinessError):
                owner.verify(**dict(args,record=wrong))
        # Promotion receives an already independently verified envelope. It must
        # unwrap, not rebuild, and still authenticate the original exact tar.
        with mock.patch.object(owner,'api',side_effect=docs_case.api):
            admitted=docs.admit(docs_case.req)
        verified={'state':'PREPUBLICATION_READY','docs_run_id':17}
        original={'schema':docs.ENVELOPE,'source_tree':'b'*40,'docs':admitted}
        source_envelope={'schema':owner.SOURCE_SCHEMA,'runtime':original}
        env={'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REF':'refs/heads/main',
             'GITHUB_REPOSITORY':owner.REPOSITORY,'GITHUB_SHA':'a'*40}
        def api(path,binary=False):
            return docs_case.artifacts[0] if path=='actions/artifacts/31' else docs_case.api(path,binary)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            with mock.patch.dict(os.environ,env,clear=True), \
                 mock.patch.object(docs.reports,'source_identity',return_value={
                    'source_commit':'a'*40,'source_tree':'b'*40,'clean':True}), \
                 mock.patch.object(owner,'load_verified_receipt',return_value=(source_envelope,verified)), \
                 mock.patch.object(owner,'api',side_effect=api):
                result=docs.prepare_promotion(root,'a'*40,7,root/'stage')
                self.assertEqual((root/'stage/artifact.tar').read_bytes(),docs_case.tar)
                self.assertFalse(result['deployment_observed'])
                self.assertEqual(result['original_pages_artifact_id'],31)


    def test_mixed_original_proofs_and_unknown_sources_cannot_acquire_source_authority(self):
        self.authenticate()
        runtime_proof={**copy.deepcopy(self.proof),'kind':'review','result':'PASSED',
                       'producer':{'class':'independent-review','identity':'inert execution review'}}
        content=json.dumps(runtime_proof).encode()
        (self.repo/'execution-proof.json').write_bytes(content)
        self.git('add','execution-proof.json');self.git('commit','-qm','retain second distinct original proof')
        self.source=self.git('rev-parse','HEAD').decode().strip()
        self.row['evidence'].append({'kind':'review','commit':self.base,'ref_commit':self.source,
                                    'ref':'execution-proof.json','sha256':owner.digest(content)})
        self.authenticate()
        self.assertIsNone(owner.authenticated_source_disposition(self.source,self.cell,self.row,self.cache))
        self.proof['kind']='unknown-proof-kind';self.retain()
        with self.assertRaisesRegex(owner.ReadinessError,'unknown original evidence class'):
            self.authenticate()
        self.proof['kind']='conformance-check';self.proof['producer']['class']='unknown-class';self.retain()
        with self.assertRaisesRegex(owner.ReadinessError,'producer identity'):
            self.authenticate()

    def test_live_reader_rebuilds_source_and_runtime_from_fresh_authorities(self):
        self.authenticate();req,record,jobs,artifacts=self.producer(self.expected_typed())
        run={'id':7,'head_sha':self.source,'head_branch':'main','event':'push','conclusion':'success',
             'path':'.github/workflows/ci.yml','repository':{'full_name':owner.REPOSITORY}}
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as zipped:
            zipped.writestr('package.txt',b'inert package fixture')
        package=output.getvalue()
        def retained(value):
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w') as zipped:
                zipped.writestr('major-readiness.json',json.dumps(value).encode())
            return output.getvalue()
        archive=retained(record)
        metadata={'id':11,'name':'major-readiness-'+self.source,'expired':False,'size_in_bytes':len(archive),
                  'digest':'sha256:'+owner.digest(archive),'workflow_run':{'id':7,'head_sha':self.source}}
        def payload(item,requirements):
            return archive if item['id']==11 else package
        with mock.patch.object(owner,'collect',return_value=(req,run,artifacts+[metadata],jobs)) as collect, \
             mock.patch.object(owner,'artifact_bytes',side_effect=payload), \
             mock.patch.object(owner,'produce',return_value=record) as reconstruct, \
             mock.patch.object(owner,'validate_upload'):
            actual,result=owner.load_verified_receipt(self.repo,self.source,7)
            self.assertEqual(actual,record);self.assertEqual(result['source'],self.source)
            collect.assert_called_once_with(self.repo,self.source,7)
            reconstruct.assert_called_once_with(req,artifacts+[metadata],jobs)
            # The original bytes still hash correctly; a forged source binding
            # must fail independent reconstruction, before accepting the record.
            wrong=copy.deepcopy(record);wrong['source_dispositions'][self.cell]['proofs'][0]['ref']='foreign.json'
            archive=retained(wrong)
            with self.assertRaisesRegex(owner.ReadinessError,'original qualification evidence'):
                owner.load_verified_receipt(self.repo,self.source,7)


# Keep closed native transport controls in this existing owning CI entrypoint.
from test_major_native_observation import NativeCompositeAuthorityTests


class LedgerRoutingApplicabilityTests(unittest.TestCase):
    path = "docs/state-contracts-major/execution/coverage-ledger.json"
    cell = "disposition:findings:C-F05"

    def setUp(self):
        self.ledger = {
            "findings": {"C-F05": {"owner": "ci", "task_ids": ["P-00"], "status": "PLANNED", "evidence": []}},
            "machines": {}, "transitions": {}, "added_transitions": {},
        }
        routing = {
            "findings": {"C-F05": {"owner": "ci", "task_ids": ["P-00"]}},
            "machines": {}, "transitions": {}, "added_transitions": {},
        }
        encoded = json.dumps(routing, sort_keys=True, separators=(",", ":")).encode()
        original = json.dumps(self.ledger).encode()
        self.proof = {
            "kind": "hosted-run", "result": "PASSED", "producer": {"class": "hosted"},
            "disposition_ids": [self.cell], "inputs": {self.path: owner.digest(original)},
            "input_projections": [{
                "path": self.path, "profile": "qualification-ledger-routing-v1",
                "sha256": owner.digest(b"qualification-ledger-routing-v1\n" + encoded),
            }],
        }
        self.original = original

    def applicability(self, updated, proof=None):
        return owner.disposition_input_applicability(
            Path("."), "b" * 40, self.proof if proof is None else proof,
            lambda commit, path: updated, {},
        )

    def test_finding_evidence_adoption_preserves_current_routing_and_original_full_blob(self):
        owner._authenticate_scope_evidence(
            Path("."), "a" * 40, self.proof, lambda commit, path: self.original, {},
        )
        self.ledger["findings"]["C-F05"].update(
            status="TESTED", evidence=[{"kind": "hosted-run"}], evidence_history=[{"kind": "review"}],
        )
        adopted = json.dumps(self.ledger).encode()
        self.assertEqual(self.applicability(adopted), (set(), set()))
        self.assertEqual(self.proof["inputs"][self.path], owner.digest(self.original))
        self.assertNotEqual(self.proof["inputs"][self.path], owner.digest(adopted))
        raw_proof = {k: v for k, v in self.proof.items() if k != "input_projections"}
        self.assertEqual(self.applicability(adopted, raw_proof), ({self.path}, set()))

    def test_routing_change_still_invalidates_the_original_evidence(self):
        for field, value in (("owner", "other"), ("task_ids", ["Q-01"])):
            with self.subTest(field=field):
                successor = copy.deepcopy(self.ledger)
                successor["findings"]["C-F05"][field] = value
                self.assertEqual(self.applicability(json.dumps(successor).encode()), ({self.path}, set()))
        self.ledger["findings"]["C-F07"] = {"owner": "ci", "task_ids": ["P-00"]}
        self.assertEqual(self.applicability(json.dumps(self.ledger).encode()), ({self.path}, set()))

    def test_projection_refuses_other_cells_original_digest_drift_and_malformed_ledger(self):
        for changes in ({"disposition_ids": ["task:Q-02"]}, {"kind": "conformance-check"},
                        {"producer": {"class": "local-host"}}, {"producer": None}, {"inputs": {}}):
            with self.subTest(changes=changes), self.assertRaises(owner.ReadinessError):
                self.applicability(self.original, {**self.proof, **changes})
        self.ledger["findings"]["C-F05"]["owner"] = "other"
        with self.assertRaises(owner.ReadinessError):
            owner._authenticate_scope_evidence(
                Path("."), "a" * 40, self.proof, lambda commit, path: json.dumps(self.ledger).encode(), {},
            )
        duplicate = self.original.replace(b'"findings": {', b'"findings": {}, "findings": {', 1)
        self.assertEqual(self.applicability(duplicate), (set(), {self.path}))


if __name__ == "__main__":
    unittest.main()
