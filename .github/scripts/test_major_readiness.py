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
spec = importlib.util.spec_from_file_location("major_readiness", path)
owner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = owner
spec.loader.exec_module(owner)


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
        # Serialization/admission capacity fixture, not executed qualification:
        # prerequisite validation and actual named execution remain separate.
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
        req = dict(self.requirements, cells=sorted(cells), cell_jobs={c: job for c in cells})
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as z:
            z.writestr('ca.tar.gz', b'exact package fixture')
        content = output.getvalue()
        report = {'schema': 'codearbiter-major-qualification/2', 'source_commit': self.source,
            'source_tree': req['source_tree'], 'ci_run_id': 7, 'job_id': 20,
            'payloads': [{'artifact_id': 12, 'archive_sha256': owner.digest(content), 'members': owner.members(content)}],
            'results': [{'cell': cell, 'result': 'PASSED', 'commands': [{'argv': ['fixture-only'], 'exit_code': 0}],
                'selected_population': 1, 'executed_population': 1, 'payload_artifact_id': 12} for cell in cells]}
        raw = json.dumps(report, indent=2).encode()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('qualification.json', raw)
        artifacts = [dict(self.build_artifacts[0], digest='sha256:' + owner.digest(content)),
                     {'id': 30, 'name': 'major-qualification-20'}]
        jobs = [{'id': 20, 'name': job, 'conclusion': 'success'}, self.jobs[-1]]
        with mock.patch.object(owner, 'validate_upload'), \
             mock.patch.object(owner, 'artifact_bytes', side_effect=lambda a, req: archive.getvalue() if a['id'] == 30 else content):
            receipt = owner.produce(req, artifacts, jobs)
        self.assertEqual(len(receipt['results']), 2230)
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
        self.overrides = {
            owner.CORPUS + 'execution/progress.json': json.dumps(self.progress).encode(),
            owner.CORPUS + 'execution/coverage-ledger.json': json.dumps(self.ledger).encode(),
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
        with mock.patch.object(owner, 'api', return_value=self.logs if logs is None else logs):
            owner.validate_upload(job or self.job, artifact or self.artifact, 'Upload major qualification report')

    def test_exact_successful_upload_has_original_attribution(self):
        self.check()

    def test_original_actions_log_utf8_bom_is_accepted(self):
        self.check(logs=b'\xef\xbb\xbf' + self.logs)

    def test_report_name_and_json_job_id_do_not_replace_successful_upload_step(self):
        for steps in ([], [dict(self.job['steps'][0], conclusion='skipped')],
                      [dict(self.job['steps'][0], name='Unrelated upload')]):
            with self.assertRaises(owner.ReadinessError):
                self.check(job=dict(self.job, steps=steps))

    def test_another_jobs_artifact_or_different_digest_or_window_refuses(self):
        for artifact in (dict(self.artifact, id=31), dict(self.artifact, digest='sha256:'+'b'*64),
                         dict(self.artifact, created_at='2026-11-13T16:00:00Z')):
            with self.assertRaises(owner.ReadinessError):
                self.check(artifact=artifact)
        with self.assertRaises(owner.ReadinessError):
            self.check(logs=self.logs.replace(owner.UPLOAD_ACTION.encode(), b'actions/other@unknown'))


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

if __name__ == "__main__":
    unittest.main()
