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
from test_ci_impact import workflow_jobs, native_workflow_jobs, paths_filter, CI_NATIVE_WORKFLOW

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
        cls.ci = (REPO/'.github/workflows/ci.yml').read_text(encoding='utf-8')
        cls.jobs = native_workflow_jobs(cls.ci)

    def test_every_parallel_stage_is_required_by_both_joins_and_merge_gate(self):
        final = self.jobs['artifact-engine']
        self.assertIn('[CHECK] | [CORE] | Structured artifact  <${{ matrix.expected_platform }}>', final)
        self.assertIn('NATIVE_RESULTS: ${{ toJSON(needs) }}', final)
        self.assertIn('python .github/scripts/artifact_ci.py gate', final)
        needed = re.search(r'^    needs: \[(.+)\]$', final, re.M)
        self.assertEqual(set(needed[1].split(', ')), binding.REQUIRED_STAGES)
        self.assertIn('!cancelled()', final)
        gate = self.jobs['ci-passed']
        for name in binding.REQUIRED_STAGES - {'changes'} | {'artifact-engine'}:
            self.assertRegex(gate, r'(?m)^      - '+re.escape(name)+r'$')
            self.assertIn("${{ needs['"+name+"'].result }}", gate)
        self.assertLess(final.index('artifact_ci.py gate'), final.index('--qualify-existing'))
        local = self.jobs['artifact-platform-passed']
        needed = re.search(r'^    needs: \[(.+)\]$', local, re.M)
        self.assertEqual(set(needed[1].split(', ')), binding.PLATFORM_STAGES)
        self.assertIn('!cancelled()', local)
        self.assertIn('artifact_ci.py platform-gate', local)
        self.assertNotIn('continue-on-error', local)

    def test_each_platform_consumes_its_candidate_without_global_build_barrier(self):
        caller = self.jobs['artifact-platform']
        self.assertIn('uses: ./.github/workflows/ci-native-platform.yml', caller)
        self.assertRegex(caller, r'(?m)^    needs: changes$')
        self.assertIn("needs.changes.outputs.artifacts == 'true'", caller)
        for name in ('os', 'expected_platform', 'artifact_binary'):
            self.assertIn(name+': ${{ matrix.'+name+' }}', caller)
        for name in ('artifact-native-default', 'artifact-native-coverage', 'artifact-context'):
            self.assertRegex(self.jobs[name], r'(?m)^    needs: changes$')
        self.assertNotRegex(self.jobs['artifact-candidate'], r'(?m)^    needs:')
        for name in ('artifact-bridges', 'artifact-conformance', 'artifact-authority'):
            self.assertRegex(self.jobs[name], r'(?m)^    needs: artifact-candidate$')
            self.assertIn("needs.artifact-candidate.result == 'success'", self.jobs[name])
            self.assertIn('runs-on: ${{ inputs.os }}', self.jobs[name])
        self.assertIn('needs: [changes, artifact-native-coverage]', self.jobs['artifact-coverage'])

    def test_builder_executes_once_per_platform_and_all_consumers_verify_same_bytes(self):
        command = 'python tools/build-artifacts.py --output "${{ runner.temp }}/artifact-candidate"'
        self.assertEqual([name for name, text in self.jobs.items() if command in text], ['artifact-candidate'])
        self.assertNotIn('--skip-tests', self.jobs['artifact-candidate'])
        for name in ('artifact-bridges', 'artifact-conformance', 'artifact-authority', 'artifact-engine'):
            body = self.jobs[name]
            scope = 'matrix' if name == 'artifact-engine' else 'inputs'
            self.assertIn('name: artifact-candidate-${{ '+scope+'.os }}', body)
            self.assertIn('python .github/scripts/artifact_ci.py verify', body)
            self.assertNotIn('--output "${{ runner.temp }}/artifact-candidate"', body)
        self.assertIn('--qualify-existing', self.jobs['artifact-engine'])
        for name in binding.PLATFORM_STAGES:
            self.assertNotIn('--qualify-existing', self.jobs[name])

    def test_all_platforms_configurations_and_four_authority_shards_remain(self):
        for name in ('artifact-platform', 'artifact-native-default', 'artifact-native-coverage', 'artifact-context', 'artifact-engine'):
            body = self.jobs[name]
            self.assertIn('fail-fast: false', body)
            self.assertNotIn('continue-on-error:', body)
            found = re.findall(r'^            expected_platform: (.+)$', body, re.M)
            self.assertEqual(sorted(found), PLATFORMS)
        for name in binding.PLATFORM_STAGES | {'artifact-native-default','artifact-native-coverage','artifact-context','artifact-engine'}:
            body = self.jobs[name]
            self.assertNotIn('continue-on-error:', body)
            for pin in ('python-version: "3.14"', 'go-version: "1.27.1"', 'check-latest: false', 'cache: false'):
                self.assertIn(pin, body)
        self.assertIn('go test -buildvcs=false ./...', self.jobs['artifact-native-default'])
        self.assertIn('go vet -buildvcs=false ./...', self.jobs['artifact-native-default'])
        self.assertIn('go test -buildvcs=false -race ./...', self.jobs['artifact-native-default'])
        self.assertIn('test_artifact_cli.py --coverage-output', self.jobs['artifact-native-coverage'])
        self.assertIn('artifact-coverage.py collect', self.jobs['artifact-native-coverage'])
        authority = self.jobs['artifact-authority']
        self.assertIn('fail-fast: false', authority)
        self.assertIn('AUTHORITY_SHARD_COUNT: "4"', authority)
        self.assertIn('group: [0, 1]', authority)
        self.assertIn('AUTHORITY_GROUP: ${{ matrix.group }}', authority)
        self.assertEqual(authority.count('run_artifact_authority_group.py'), 1)

    def test_context_observation_and_candidate_both_precede_qualification(self):
        self.assertIn('CONTEXT_NATIVE_OBSERVATION_OUTPUT:', self.jobs['artifact-context'])
        self.assertIn('name: artifact-context-${{ matrix.os }}', self.jobs['artifact-context'])
        final = self.jobs['artifact-engine']
        self.assertIn('name: artifact-context-${{ matrix.os }}', final)
        self.assertLess(final.index('artifact_ci.py verify'), final.index('--qualify-existing'))
        self.assertLess(final.index('name: artifact-context-'), final.index('--qualify-existing'))
        self.assertIn('--context-native-observation "${{ runner.temp }}/context-native-observation.json"', final)
        self.assertIn('name: artifact-native-${{ matrix.os }}', final)
        self.assertIn("needs.artifact-engine.result == 'success'", self.jobs['artifact-package-assembly'])

    def test_conformance_uses_locked_interpreter_and_runs_in_parallel_with_adapters(self):
        body = self.jobs['artifact-conformance']
        self.assertIn('needs: artifact-candidate', body)
        self.assertNotIn('needs: artifact-bridges', body)
        for control in ('--require-hashes', '--no-deps', '--only-binary=:all:',
                        'ARTIFACT_CONFORMANCE_PYTHON', 'test_artifact_conformance.py', 'test_debug_handoff.py'):
            self.assertIn(control, body)
        for suite in ('test_artifact_conformance.py', 'test_debug_handoff.py'):
            self.assertNotIn(suite, self.jobs['artifact-bridges'])
        command = "subprocess.run([os.environ['ARTIFACT_CONFORMANCE_PYTHON'], '.github/scripts/test_artifact_conformance.py']"
        self.assertEqual(sum(text.count(command) for text in self.jobs.values()), 1)

    def test_every_pipeline_subject_reaches_native_jobs_and_early_contract_suite(self):
        self.assertIn('run: python .github/scripts/test_ci_native_pipeline.py', self.jobs['ci-impact'])
        subjects = ('.github/scripts/artifact_ci.py', '.github/scripts/run_artifact_authority_shard.py',
                    '.github/scripts/run_artifact_authority_group.py', '.github/scripts/test_artifact_conformance.py',
                    '.github/scripts/_artifactworkerlib.py',
                    '.github/scripts/test_ci_native_pipeline.py', '.github/fixtures/artifact-authority-timings.json',
                    '.github/workflows/ci-native-platform.yml', '.github/scripts/test_ship_set_inputs.py')
        for subject in subjects:
            for target in ('impact', 'artifacts'):
                with self.subTest(subject=subject, target=target):
                    self.assertIn(subject, paths_filter(self.ci, target))

    def test_pinned_go_keeps_standard_cache_and_mirror_resolution(self):
        # An explicit go.dev URL is interpreted as a custom distribution and
        # bypasses both the ordinary tool cache and the Actions Go mirror.
        # Retain the exact compiler/version checks without forcing that path.
        native = (REPO/'.github/workflows/ci-native-platform.yml').read_text(encoding='utf-8')
        for source, expected_count in ((self.ci, 5), (native, 4)):
            blocks = re.findall(
                r"(?ms)^      - uses: actions/setup-go@[^\n]+\n"
                r"(?P<body>.*?)(?=^      - |\Z)", source)
            self.assertEqual(len(blocks), expected_count)
            for body in blocks:
                for control in ('go-version: "1.27.1"', 'check-latest: false', 'cache: false'):
                    self.assertIn(control, body)
                self.assertNotIn('go-download-base-url:', body)
            self.assertIn("actual == 'go1.27.1'", source)
            self.assertIn('GOTOOLCHAIN: local', source)

    def test_reusable_definition_alone_triggers_main_push_ci(self):
        triggers = self.ci.split("\njobs:\n", 1)[0]
        self.assertIn('      - ".github/workflows/ci-native-platform.yml"', triggers)
        self.assertIn('      - ".github/scripts/**"', triggers)

    def test_ship_set_wiring_contract_is_exercised_in_early_ci_too(self):
        # The hosted failure was missed because only Linux ran this contract.
        # This one method is platform-neutral; the actual Go suite remains Linux-owned.
        from test_ship_set_inputs import ShipSetInputs
        case = ShipSetInputs('test_suite_wired_into_ci')
        result = unittest.TestResult()
        case.run(result)
        self.assertEqual(result.testsRun, 1)
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)

    def test_per_platform_join_rejects_all_skipped_missing_and_non_success_inputs(self):
        needs = {name:{'result':'success'} for name in binding.PLATFORM_STAGES}
        binding.require_stages(json.dumps(needs), platform=True)
        for name in binding.PLATFORM_STAGES:
            for state in ('failure','skipped','cancelled','pending',None):
                mutated = copy.deepcopy(needs)
                mutated[name]['result'] = state
                with self.subTest(name=name,state=state), self.assertRaises(ValueError):
                    binding.require_stages(json.dumps(mutated), platform=True)
            missing = dict(needs)
            del missing[name]
            with self.assertRaises(ValueError):
                binding.require_stages(json.dumps(missing), platform=True)
        with self.assertRaises(ValueError):
            binding.require_stages(json.dumps(successful_needs()), platform=True)
        with self.assertRaises(ValueError):
            binding.require_stages(json.dumps(needs))


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


class AuthorityGroupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import hashlib
        import run_artifact_authority_group as group
        cls.group = group
        partitions, _ = shard.partition(shard.discover(), 4, shard.load_weights())
        cls.plan = [[case.id() for case in part] for part in partitions]
        cls.plan_hash = hashlib.sha256(json.dumps(cls.plan, separators=(",", ":")).encode()).hexdigest()

    def report(self, index):
        return {'format':'codearbiter.authority-shard-observation/1', 'shard':index,
                'shard_count':4, 'discovered_count':sum(map(len,self.plan)),
                'selected_ids':self.plan[index], 'plan_sha256':self.plan_hash,
                'passed':True, 'tests_run':len(self.plan[index]), 'skipped':0,
                'observations':[{'id':name, 'outcome':'pass'} for name in self.plan[index]]}

    def test_groups_preserve_the_same_four_disjoint_complete_shards(self):
        groups = [self.group.selected_group(str(index)) for index in range(2)]
        self.assertEqual(sorted(index for pair in groups for index in pair), list(range(4)))
        all_ids = [name for pair in groups for index in pair for name in self.plan[index]]
        self.assertEqual(len(set(all_ids)), sum(map(len,self.plan)))
        for raw in ('', '-1', '2', 'true', '00', '0 ', None, 0):
            with self.assertRaises(ValueError):
                self.group.selected_group(raw)

    def test_child_proof_rejects_wrong_membership_skip_failure_and_duplicates(self):
        self.group.validate_report(self.report(0), index=0, plan=self.plan, plan_sha256=self.plan_hash)
        mutations = [('shard',1), ('shard_count',4.0), ('discovered_count',0),
                     ('selected_ids',self.plan[1]), ('plan_sha256','wrong'), ('passed',False),
                     ('tests_run',0), ('skipped',len(self.plan[0])), ('observations',[])]
        for key,value in mutations:
            record=self.report(0);record[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.group.validate_report(record,index=0,plan=self.plan,plan_sha256=self.plan_hash)
        for mutation in ('duplicate','failed','unknown','nonstring','all-skipped'):
            record=self.report(0)
            if mutation=='duplicate':record['observations'][1]['id']=record['observations'][0]['id']
            if mutation=='failed':record['observations'][0]['outcome']='failure'
            if mutation=='unknown':record['observations'][0]['outcome']='unknown'
            if mutation=='nonstring':record['observations'][0]['id']=None
            if mutation=='all-skipped':
                for item in record['observations']:item['outcome']='skip'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.group.validate_report(record,index=0,plan=self.plan,plan_sha256=self.plan_hash)

    def test_both_children_execute_concurrently_and_a_failed_child_cannot_pass(self):
        import threading
        for failed in (None, 0):
            barrier=threading.Barrier(2,timeout=10)
            invoked=[]
            def child(index,root,environment):
                invoked.append(index)
                barrier.wait()
                (root/f'shard-{index}.json').write_text(json.dumps(self.report(index)),encoding='utf-8')
                return {'shard':index,'exit':1 if index==failed else 0}
            with tempfile.TemporaryDirectory() as temporary, mock.patch.object(self.group,'run_child',side_effect=child):
                result=self.group.run_group('0',Path(temporary)/'reports')
                self.assertEqual(sorted(invoked),[0,2])
                self.assertEqual(result['passed'],failed is None)
                with self.assertRaises(FileExistsError):
                    self.group.run_group('0',Path(temporary)/'reports')

    def test_missing_or_stale_child_report_cannot_pass_even_after_zero_exit(self):
        for stale in (False,True):
            def child(index,root,environment):
                if stale:
                    record=self.report(index);record['plan_sha256']='stale'
                    (root/f'shard-{index}.json').write_text(json.dumps(record),encoding='utf-8')
                return {'shard':index,'exit':0}
            with tempfile.TemporaryDirectory() as temporary, mock.patch.object(self.group,'run_child',side_effect=child):
                result=self.group.run_group('1',Path(temporary)/'reports')
                self.assertFalse(result['passed'])
                self.assertEqual(len(result['errors']),2)

    def test_worker_roots_are_shallow_unique_and_removed_after_children_finish(self):
        from types import SimpleNamespace
        seen=[]
        def child(argv, *, env, **kwargs):
            temporary=Path(env['TMPDIR'])
            self.assertEqual(temporary.parent,Path(tempfile.gettempdir()))
            self.assertEqual(Path(env['HOME']).parent,temporary)
            self.assertTrue(temporary.is_dir())
            seen.append(temporary)
            return SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(self.group.subprocess,'run',side_effect=child):
            for index in (0,2):
                outcome=self.group.run_child(index,Path(temporary),dict(os.environ))
                self.assertEqual(outcome['exit'],0)
        self.assertEqual(len(set(seen)),2)
        self.assertTrue(all(not path.exists() for path in seen))

    def test_authority_retries_only_cleanup_not_the_successful_child(self):
        from types import SimpleNamespace
        original = tempfile.TemporaryDirectory.cleanup
        seen = set()
        attempts = []
        owners = []
        def cleanup(owner):
            if Path(owner.name).name.startswith('ca-authority-'):
                owners.append(owner)
                attempts.append(owner.name)
                if owner.name not in seen:
                    seen.add(owner.name)
                    error = PermissionError('synthetic transient sharing violation')
                    error.winerror = 32
                    raise error
            return original(owner)
        with tempfile.TemporaryDirectory() as root:
            try:
                with mock.patch.object(tempfile.TemporaryDirectory,'cleanup',new=cleanup), \
                     mock.patch.object(self.group.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as child:
                    result = self.group.run_child(0,Path(root),dict(os.environ))
                self.assertEqual(result,{'shard':0,'exit':0})
                child.assert_called_once()
                self.assertEqual(len(attempts),2)
                self.assertTrue(all(not Path(owner.name).exists() for owner in owners))
            finally:
                for owner in owners:
                    original(owner)

    def test_diagnostics_are_attempt_scoped_and_do_not_upload_worker_homes(self):
        jobs=workflow_jobs((REPO/'.github/workflows/ci-native-platform.yml').read_text(encoding='utf-8'))
        body=jobs['artifact-authority']
        self.assertIn('name: authority-timings-${{ inputs.os }}-group-${{ matrix.group }}-attempt-${{ github.run_attempt }}',body)
        self.assertIn('authority-group/*.json',body)
        self.assertIn('authority-group/*.log',body)
        self.assertNotIn('path: ${{ runner.temp }}/authority-group\n',body)
        self.assertIn('include-hidden-files: false',body)
        self.assertIn('overwrite: false',body)
        self.assertIn('timeout-minutes: 45',body)
        template='authority-timings-{os}-group-{group}-attempt-{attempt}'
        names={template.format(os=os,group=group,attempt=attempt)
               for os in ('linux','windows','macos') for group in range(2) for attempt in (1,2)}
        self.assertEqual(len(names),12)


class ParallelConformanceTest(unittest.TestCase):
    def exercise(self, *, failing=None, mutate=False):
        import subprocess
        import threading
        import test_artifact_conformance as conformance
        case=conformance.ArtifactConformanceTest('test_adversarial_native_candidate_suites_run_as_one_snapshot')
        barrier=threading.Barrier(3,timeout=10)
        first={'test_artifact_package.py','test_artifact_workflow.py','test_artifact_authoring.py'}
        seen=[];homes=[];changed=threading.Event()
        identity=('manifest','file','binary',1,2)
        def current_identity():
            return ('changed',)+identity[1:] if changed.is_set() else identity
        def child(argv, *, env=None, cwd=None):
            script=Path(argv[1]).name
            seen.append(script);homes.append(env['HOME'])
            self.assertTrue(Path(env['HOME']).is_dir())
            self.assertNotEqual(env['HOME'],env['TMPDIR'])
            self.assertEqual(env['ARTIFACT_TEST_INSTALLATION'],'fixture')
            if script in first:barrier.wait()
            if mutate and script=='test_artifact_bridge.py':changed.set()
            if script==failing:raise AssertionError('deliberate child failure')
            names=conformance.EXPECTED_SUITES[script]
            lines=[]
            for name in sorted(names):
                status="skipped 'native Unix only'" if name=='test_unix_parent_swap_after_validation_cannot_redirect_creation' and conformance.platform.system()=='Windows' else 'ok'
                lines.append(f'{name} (__main__.Example.{name}) ... {status}')
            lines.append(f'Ran {len(names)} tests')
            return subprocess.CompletedProcess(argv,0,'\n'.join(lines),'')
        with mock.patch.object(conformance,'INSTALLATION',Path('fixture')), \
             mock.patch.object(conformance,'CANDIDATE_IDENTITY',identity), \
             mock.patch.object(conformance,'candidate_identity',side_effect=current_identity), \
             mock.patch.object(case,'run_checked',side_effect=child):
            result=unittest.TestResult();case.run(result)
        self.assertLessEqual(set(seen),set(conformance.EXPECTED_SUITES))
        if not mutate:
            self.assertEqual(set(seen),set(conformance.EXPECTED_SUITES))
        self.assertEqual(len(seen),len(set(seen)))
        self.assertEqual(len(set(homes)),len(homes))
        self.assertTrue(all(not Path(home).exists() for home in homes))
        return result

    def test_all_suites_overlap_with_isolated_homes_and_unchanged_membership(self):
        result=self.exercise()
        self.assertTrue(result.wasSuccessful(),result.errors+result.failures)

    def test_conformance_retries_transient_worker_cleanup_without_rerunning_suites(self):
        import threading
        original = tempfile.TemporaryDirectory.cleanup
        seen = set()
        owners = {}
        attempts = {}
        lock = threading.Lock()
        def cleanup(owner):
            if Path(owner.name).name.startswith('ca-conformance-worker-'):
                with lock:
                    owners[owner.name] = owner
                    attempts[owner.name] = attempts.get(owner.name,0)+1
                    first = owner.name not in seen
                    seen.add(owner.name)
                if first:
                    error = PermissionError('synthetic transient sharing violation')
                    error.winerror = 32
                    raise error
            return original(owner)
        try:
            with mock.patch.object(tempfile.TemporaryDirectory,'cleanup',new=cleanup):
                result = self.exercise()
            self.assertTrue(result.wasSuccessful(),result.errors+result.failures)
            self.assertEqual(len(owners),5)
            self.assertEqual(set(attempts.values()),{2})
        finally:
            for owner in owners.values():
                original(owner)

    def test_parallel_child_failure_remains_a_failure_after_siblings_finish(self):
        result=self.exercise(failing='test_artifact_package.py')
        self.assertFalse(result.wasSuccessful())

    def test_candidate_change_during_parallel_execution_is_rejected(self):
        result=self.exercise(mutate=True)
        self.assertFalse(result.wasSuccessful())


class WorkerCleanupTest(unittest.TestCase):
    @staticmethod
    def sharing_error():
        error = PermissionError('synthetic worker sharing violation')
        error.winerror = 32
        return error

    def test_success_does_not_sleep_or_retry(self):
        import _artifactworkerlib as worker
        owner = mock.Mock()
        with mock.patch.object(worker.time,'sleep') as wait:
            worker.cleanup_worker(owner)
        owner.cleanup.assert_called_once_with()
        wait.assert_not_called()

    def test_transient_sharing_retries_only_owner_cleanup(self):
        import _artifactworkerlib as worker
        owner = mock.Mock()
        owner.cleanup.side_effect = [self.sharing_error(),None]
        with mock.patch.object(worker.time,'monotonic',return_value=0), \
             mock.patch.object(worker.time,'sleep') as wait:
            worker.cleanup_worker(owner)
        self.assertEqual(owner.cleanup.call_count,2)
        wait.assert_called_once_with(0.05)

    def test_persistent_sharing_is_fatal_after_bounded_attempts(self):
        import _artifactworkerlib as worker
        owner = mock.Mock()
        error = self.sharing_error()
        owner.cleanup.side_effect = error
        with mock.patch.object(worker.time,'monotonic',return_value=0), \
             mock.patch.object(worker.time,'sleep') as wait:
            with self.assertRaises(PermissionError) as caught:
                worker.cleanup_worker(owner)
        self.assertIs(caught.exception,error)
        self.assertEqual(owner.cleanup.call_count,41)
        self.assertEqual(wait.call_count,40)

    def test_wall_deadline_cannot_be_extended_by_more_attempts(self):
        import _artifactworkerlib as worker
        owner = mock.Mock()
        owner.cleanup.side_effect = self.sharing_error()
        with mock.patch.object(worker.time,'monotonic',side_effect=[0,3]), \
             mock.patch.object(worker.time,'sleep') as wait:
            with self.assertRaises(PermissionError):
                worker.cleanup_worker(owner)
        owner.cleanup.assert_called_once_with()
        wait.assert_not_called()

    def test_unrelated_cleanup_errors_are_immediately_fatal(self):
        import _artifactworkerlib as worker
        access = PermissionError('access denied, not a sharing violation')
        access.winerror = 5
        for error in (access,PermissionError('POSIX permissions'),OSError('device error')):
            owner = mock.Mock();owner.cleanup.side_effect = error
            with mock.patch.object(worker.time,'sleep') as wait:
                with self.assertRaises(type(error)) as caught:
                    worker.cleanup_worker(owner)
            self.assertIs(caught.exception,error)
            owner.cleanup.assert_called_once_with()
            wait.assert_not_called()

    def test_test_failure_survives_a_successful_cleanup_retry(self):
        import _artifactworkerlib as worker
        owner = mock.Mock(name='owned-directory')
        owner.name = 'synthetic-only'
        owner.cleanup.side_effect = [self.sharing_error(),None]
        failure = AssertionError('actual child failed')
        with mock.patch.object(worker.tempfile,'TemporaryDirectory',return_value=owner), \
             mock.patch.object(worker.time,'sleep'):
            with self.assertRaises(AssertionError) as caught:
                with worker.worker_directory(prefix='ci-fixture-'):
                    raise failure
        self.assertIs(caught.exception,failure)
        self.assertEqual(owner.cleanup.call_count,2)

    def test_persistent_cleanup_error_never_allows_a_successful_worker(self):
        import _artifactworkerlib as worker
        owner = mock.Mock(name='owned-directory');owner.name='synthetic-only'
        error = PermissionError('access denied')
        owner.cleanup.side_effect = error
        body = mock.Mock()
        with mock.patch.object(worker.tempfile,'TemporaryDirectory',return_value=owner):
            with self.assertRaises(PermissionError) as caught:
                with worker.worker_directory(prefix='ci-fixture-'):
                    body()
        self.assertIs(caught.exception,error)
        body.assert_called_once_with()
        owner.cleanup.assert_called_once_with()


if __name__ == '__main__':
    unittest.main(verbosity=2)
