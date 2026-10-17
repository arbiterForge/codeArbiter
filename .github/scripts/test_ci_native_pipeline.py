#!/usr/bin/env python3
"""Regression and negative controls for parallel native CI and complete sharding."""
from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

import artifact_ci as binding
import run_artifact_authority_shard as shard
from test_ci_impact import workflow_jobs

REPO = Path(__file__).resolve().parents[2]
STAGES = set(binding.REQUIRED_STAGES) - {"changes", "artifact-coverage"}
PLATFORMS = sorted(binding.PLATFORMS)


def successful_needs():
    """Make test-only successful needs data; this never writes a real receipt."""
    result = {name: {"result": "success", "outputs": {}} for name in binding.REQUIRED_STAGES}
    result["changes"]["outputs"]["artifacts"] = "true"
    return result


class FinalJoinTest(unittest.TestCase):
    def test_complete_success_is_accepted(self):
        binding.require_stages(json.dumps(successful_needs()))

    def test_every_non_success_stage_is_rejected(self):
        for name in binding.REQUIRED_STAGES:
            for result in ("skipped", "failure", "cancelled", "pending", "", None):
                with self.subTest(name=name, result=result):
                    needs = successful_needs()
                    needs[name]["result"] = result
                    with self.assertRaises(ValueError):
                        binding.require_stages(json.dumps(needs))

    def test_missing_extra_or_malformed_stage_is_rejected(self):
        for name in binding.REQUIRED_STAGES:
            needs = successful_needs()
            del needs[name]
            with self.assertRaises(ValueError):
                binding.require_stages(json.dumps(needs))
        for raw in ('{}', '[]', 'null', '{', 'x' * 65537):
            with self.assertRaises(ValueError):
                binding.require_stages(raw)
        needs = successful_needs()
        needs['undeclared'] = {"result": "success"}
        with self.assertRaises(ValueError):
            binding.require_stages(json.dumps(needs))

    def test_false_impact_and_duplicate_results_cannot_qualify(self):
        needs = successful_needs()
        needs['changes']['outputs']['artifacts'] = 'false'
        with self.assertRaises(ValueError):
            binding.require_stages(json.dumps(needs))
        with self.assertRaises(ValueError):
            binding.require_stages('{"changes":{},"changes":{}}')


class CandidateBindingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ci-candidate-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.candidate = self.root / 'candidate'
        self.candidate.mkdir()
        self.binary = self.candidate / 'ca-artifact-windows-amd64.exe'
        self.binary.write_bytes(b'non-executable synthetic unit-test fixture')
        self.manifest = {
            'format': 'codearbiter.artifact-release/0.1.0', 'version': '0.1.0',
            'protocol': 'codearbiter.artifact-api/0.1.0', 'schema_version': '0.3.2',
            'binaries': {'windows/amd64': {'file': self.binary.name,
                         'sha256': binding.digest(self.binary.read_bytes()), 'native_tested': True}},
        }
        self.write_manifest()
        self.metadata = self.root / 'binding.json'
        self.identity = {
            'format': binding.FORMAT, 'source_commit': 'a' * 40, 'run_id': '100',
            'run_attempt': '1', 'workflow': binding.WORKFLOW, 'producer_job': binding.PRODUCER,
            'platform': 'windows/amd64', 'toolchain': 'go1.27.1',
            'module_sha256': 'b' * 64, 'go_sha256': 'c' * 64,
        }
        patcher = mock.patch.object(binding, 'ci_identity', return_value=self.identity)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_manifest(self):
        (self.candidate / 'release.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def stamp(self):
        with mock.patch.dict(os.environ, GITHUB_JOB=binding.PRODUCER):
            return binding.stamp(self.candidate, self.metadata, 'windows/amd64')

    def test_round_trip_does_not_promote_or_rewrite_manifest(self):
        before = (self.candidate / 'release.json').read_bytes()
        stamped = self.stamp()
        self.assertEqual(binding.verify(self.candidate, self.metadata, 'windows/amd64'), stamped)
        self.assertEqual((self.candidate / 'release.json').read_bytes(), before)
        self.assertEqual(set(self.candidate.iterdir()), {self.binary, self.candidate / 'release.json'})

    def test_other_jobs_cannot_stamp_and_existing_record_cannot_be_overwritten(self):
        with mock.patch.dict(os.environ, GITHUB_JOB='artifact-authority'):
            with self.assertRaises(ValueError):
                binding.stamp(self.candidate, self.metadata, 'windows/amd64')
        self.stamp()
        with self.assertRaises(FileExistsError):
            self.stamp()

    def test_unqualified_or_path_swapped_manifest_is_rejected(self):
        for field, value in (('native_tested', False), ('native_tested', 1),
                             ('file', '../outside.exe'), ('sha256', 'd' * 64)):
            with self.subTest(field=field, value=value):
                entry = self.manifest['binaries']['windows/amd64']
                prior = entry[field]
                entry[field] = value
                self.write_manifest()
                with self.assertRaises(ValueError):
                    binding.candidate_identity(self.candidate, 'windows/amd64')
                entry[field] = prior
        self.write_manifest()
        with self.assertRaises(ValueError):
            binding.candidate_identity(self.candidate, 'linux/amd64')

    def test_source_run_platform_tool_and_digest_substitution_are_rejected(self):
        original = self.stamp()
        for key in original:
            if key == 'run_attempt':
                continue
            mutated = {**original, key: original[key] + '-changed'}
            self.metadata.write_text(json.dumps(mutated), encoding='utf-8')
            with self.subTest(key=key), self.assertRaises(ValueError):
                binding.verify(self.candidate, self.metadata, 'windows/amd64')
        self.metadata.write_text(json.dumps(original), encoding='utf-8')
        self.binary.write_bytes(b'changed fixture')
        with self.assertRaises(ValueError):
            binding.verify(self.candidate, self.metadata, 'windows/amd64')

    def test_same_run_retry_reuses_successful_candidate_but_rejects_future_attempt(self):
        original = self.stamp()
        self.identity['run_attempt'] = '2'
        self.assertEqual(binding.verify(self.candidate, self.metadata, 'windows/amd64'), original)
        self.metadata.write_text(json.dumps({**original, 'run_attempt': '3'}), encoding='utf-8')
        with self.assertRaises(ValueError):
            binding.verify(self.candidate, self.metadata, 'windows/amd64')

    def test_duplicate_json_unknown_fields_and_oversized_metadata_are_rejected(self):
        self.stamp()
        for raw in ('{"run_id":"100","run_id":"101"}', '[]', 'x' * 65537):
            self.metadata.write_text(raw, encoding='utf-8')
            with self.assertRaises(ValueError):
                binding.verify(self.candidate, self.metadata, 'windows/amd64')
        self.manifest['extra'] = 'not allowed'
        self.write_manifest()
        with self.assertRaises(ValueError):
            binding.candidate_identity(self.candidate, 'windows/amd64')


class ShardPartitionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = shard.discover()
        cls.weights = shard.load_weights()

    def test_real_discovery_is_exhaustive_disjoint_and_fixture_preserving(self):
        shards, _ = shard.partition(self.cases, 4, self.weights)
        self.assertEqual(sorted(t.id() for part in shards for t in part), sorted(t.id() for t in self.cases))
        owners = {}
        for index, part in enumerate(shards):
            self.assertTrue(part)
            for test in part:
                name = shard.class_id(test)
                self.assertEqual(owners.setdefault(name, index), index)
        self.assertTrue(any('test_artifact_git_excludes.' in t.id() for t in self.cases))
        self.assertTrue(any('test_artifact_npm_nested_launch.' in t.id() for t in self.cases))

    def test_assignment_is_deterministic_and_uses_measured_duration(self):
        first, totals = shard.partition(self.cases, 4, self.weights)
        second, _ = shard.partition(list(reversed(self.cases)), 4, self.weights)
        self.assertEqual([[t.id() for t in s] for s in first], [[t.id() for t in s] for s in second])
        self.assertGreater(sum(totals), 0)
        # This checks the scheduling algorithm against retained weights, not live speed.
        self.assertLess(max(totals) / min(totals), 1.5)

    def test_new_cases_and_classes_are_never_excluded_by_old_weights(self):
        extra_type = type('FutureAuthorityRegression', (unittest.TestCase,), {'test_new': lambda self: None})
        extra = extra_type('test_new')
        result, _ = shard.partition(self.cases + [extra], 4, self.weights)
        self.assertIn(extra.id(), [t.id() for part in result for t in part])
        self.assertNotIn(shard.class_id(extra), self.weights)

    def test_bad_counts_empty_duplicate_and_missing_fixture_groups_refuse(self):
        for count in (0, -1, 33, True, '4'):
            with self.assertRaises(ValueError):
                shard.partition(self.cases, count, self.weights)
        for cases in ([], self.cases + [self.cases[0]], self.cases[:1]):
            with self.assertRaises(ValueError):
                shard.partition(cases, 4, self.weights)

    def test_measured_results_preserve_failure_skip_and_real_execution(self):
        class Example(unittest.TestCase):
            def test_pass(self):
                self.assertTrue(True)
            def test_fail(self):
                self.fail('deliberate negative control')
            @unittest.skip('deliberate skipped fixture')
            def test_skip(self):
                pass
        runner = unittest.TextTestRunner(stream=io.StringIO(), resultclass=shard.TimedResult)
        result = runner.run(unittest.defaultTestLoader.loadTestsFromTestCase(Example))
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.testsRun, 3)
        self.assertEqual({row['outcome'] for row in result.observations}, {'pass', 'failure', 'skip'})
        self.assertTrue(all(row['seconds'] >= 0 for row in result.observations))


class WorkflowClosureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.jobs = workflow_jobs((REPO/'.github/workflows/ci.yml').read_text(encoding='utf-8'))

    def test_every_parallel_stage_is_required_by_both_join_and_merge_gate(self):
        final = self.jobs['artifact-engine']
        self.assertIn('[CHECK] | [CORE] | Structured artifact  <${{ matrix.expected_platform }}>', final)
        self.assertIn('NATIVE_RESULTS: ${{ toJSON(needs) }}', final)
        self.assertIn('python .github/scripts/artifact_ci.py gate', final)
        needed = re.search(r'^    needs: \[(.+)\]$', final, re.M)
        self.assertEqual(set(needed[1].split(', ')), binding.REQUIRED_STAGES)
        self.assertIn('!cancelled()', final)
        gate = self.jobs['ci-passed']
        for name in STAGES | {'artifact-engine', 'artifact-coverage'}:
            self.assertRegex(gate, r'(?m)^      - '+re.escape(name)+r'$')
            self.assertIn("${{ needs['"+name+"'].result }}", gate)
        self.assertLess(final.index('artifact_ci.py gate'), final.index('--qualify-existing'))

    def test_independent_work_starts_without_waiting_for_the_candidate_or_other_tests(self):
        for name in ('artifact-candidate', 'artifact-native-default', 'artifact-native-coverage', 'artifact-context'):
            self.assertRegex(self.jobs[name], r'(?m)^    needs: changes$')
        for name in ('artifact-bridges', 'artifact-authority'):
            self.assertIn('needs: [changes, artifact-candidate]', self.jobs[name])
        self.assertIn('needs: [changes, artifact-native-coverage]', self.jobs['artifact-coverage'])

    def test_builder_executes_only_once_per_platform_and_final_join_never_rebuilds(self):
        command = 'python tools/build-artifacts.py --output "${{ runner.temp }}/artifact-candidate"'
        owners = [name for name, text in self.jobs.items() if command in text]
        self.assertEqual(owners, ['artifact-candidate'])
        self.assertNotIn('--skip-tests', self.jobs['artifact-candidate'])
        for name in ('artifact-bridges', 'artifact-authority', 'artifact-engine'):
            body = self.jobs[name]
            self.assertIn('name: artifact-candidate-${{ matrix.os }}', body)
            self.assertIn('python .github/scripts/artifact_ci.py verify', body)
            self.assertNotIn('--output "${{ runner.temp }}/artifact-candidate"', body)
        self.assertIn('--qualify-existing', self.jobs['artifact-engine'])
        self.assertNotIn('--qualify-existing', self.jobs['artifact-candidate'])

    def test_all_platforms_and_required_configurations_remain(self):
        for name in STAGES | {'artifact-engine'}:
            body = self.jobs[name]
            self.assertIn('fail-fast: false', body)
            self.assertNotIn('continue-on-error:', body)
            found = re.findall(r'^            expected_platform: (.+)$', body, re.M)
            self.assertEqual(sorted(found), sorted(PLATFORMS * (4 if name == 'artifact-authority' else 1)))
            for pin in ('python-version: "3.14"', 'go-version: "1.27.1"', 'check-latest: false', 'cache: false'):
                self.assertIn(pin, body)
        self.assertIn('go test -buildvcs=false ./...', self.jobs['artifact-native-default'])
        self.assertIn('go vet -buildvcs=false ./...', self.jobs['artifact-native-default'])
        self.assertIn('go test -buildvcs=false -race ./...', self.jobs['artifact-native-default'])
        self.assertIn('test_artifact_cli.py --coverage-output', self.jobs['artifact-native-coverage'])
        self.assertIn('artifact-coverage.py collect', self.jobs['artifact-native-coverage'])
        self.assertIn('AUTHORITY_SHARD_COUNT: "4"', self.jobs['artifact-authority'])
        self.assertEqual(re.findall(r'^            shard: (\d+)$', self.jobs['artifact-authority'], re.M), ['0','1','2','3'] * 6)

    def test_context_observation_and_candidate_both_precede_qualification(self):
        self.assertIn('CONTEXT_NATIVE_OBSERVATION_OUTPUT:', self.jobs['artifact-context'])
        self.assertIn('name: artifact-context-${{ matrix.os }}', self.jobs['artifact-context'])
        final = self.jobs['artifact-engine']
        self.assertIn('name: artifact-context-${{ matrix.os }}', final)
        self.assertLess(final.index('artifact_ci.py verify'), final.index('--qualify-existing'))
        self.assertLess(final.index('name: artifact-context-'), final.index('--qualify-existing'))
        self.assertIn('--context-native-observation "${{ runner.temp }}/context-native-observation.json"', final)
        self.assertIn('name: artifact-native-${{ matrix.os }}', final)
        self.assertIn('needs.artifact-engine.result == \'success\'', self.jobs['artifact-package-assembly'])

    def test_new_contract_suite_is_really_executed_in_early_ci(self):
        self.assertIn('run: python .github/scripts/test_ci_native_pipeline.py', self.jobs['ci-impact'])


class HostedCheckPaginationTest(unittest.TestCase):
    def setUp(self):
        import verify_pi_support
        self.module = verify_pi_support
        self.commit = 'a' * 40
        self.checks = [dict(id=index + 1, name='unrelated-' + str(index), head_sha=self.commit,
                            status='completed', conclusion='success') for index in range(100)]
        self.checks += [dict(id=101 + index, name=name, head_sha=self.commit,
                             status='completed', conclusion='success')
                        for index, name in enumerate(sorted(self.module.REQUIRED_HOSTED_CHECKS))]
        self.pages = [{'total_count': len(self.checks), 'check_runs': self.checks[:100]},
                      {'total_count': len(self.checks), 'check_runs': self.checks[100:]}]

    def evaluate(self, pages, returncode=0):
        from types import SimpleNamespace
        with mock.patch.object(self.module.shutil, 'which', return_value='gh'), \
                mock.patch.object(self.module.subprocess, 'run',
                                  return_value=SimpleNamespace(returncode=returncode, stdout=json.dumps(pages))) as run:
            result = self.module._load_hosted_checks(REPO, self.commit)
            self.assertIn('--paginate', run.call_args.args[0])
            self.assertIn('--slurp', run.call_args.args[0])
            return result

    def test_required_checks_beyond_first_hundred_are_read(self):
        self.assertTrue(self.evaluate(self.pages))
        self.assertFalse(self.evaluate(self.pages[:1]))

    def test_last_page_failure_and_wrong_commit_remain_failures(self):
        for field, value in (('conclusion', 'failure'), ('head_sha', 'b' * 40), ('status', 'in_progress')):
            pages = copy.deepcopy(self.pages)
            pages[-1]['check_runs'][0][field] = value
            with self.subTest(field=field):
                self.assertFalse(self.evaluate(pages))

    def test_duplicate_partial_changed_or_malformed_pages_are_rejected(self):
        cases = [[], {}, [None], [dict(total_count='1', check_runs=[])], self.pages[:1]]
        duplicate = copy.deepcopy(self.pages)
        duplicate[1]['check_runs'][0]['id'] = duplicate[0]['check_runs'][0]['id']
        cases.append(duplicate)
        changed = copy.deepcopy(self.pages)
        changed[1]['total_count'] += 1
        cases.append(changed)
        for pages in cases:
            with self.subTest(pages_type=type(pages).__name__):
                self.assertFalse(self.evaluate(pages))
        self.assertFalse(self.evaluate(self.pages, returncode=1))

    def test_api_timeout_is_unverified_not_an_exception_or_success(self):
        with mock.patch.object(self.module.shutil, 'which', return_value='gh'), \
                mock.patch.object(self.module.subprocess, 'run',
                                  side_effect=self.module.subprocess.TimeoutExpired('gh', 30)):
            self.assertFalse(self.module._load_hosted_checks(REPO, self.commit))


if __name__ == '__main__':
    unittest.main(verbosity=2)
