#!/usr/bin/env python3
"""Keep grouped native configurations exhaustive, isolated and failure-sensitive."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

import run_native_check_group as runner
from test_ci_impact import workflow_jobs


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.plan, self.digest = runner.load_plan()

    def test_all_original_groups_commands_and_conditions_are_retained(self):
        self.assertEqual(set(self.plan), set(runner.GROUPS))
        self.assertEqual(sum(map(len, self.plan.values())), 14)
        self.assertEqual(self.plan['default'][0]['argv'], ['go','test','-count=1','-buildvcs=false','./...'])
        self.assertEqual(self.plan['default'][1]['argv'], ['go','vet','-buildvcs=false','./...'])
        self.assertEqual(self.plan['default'][2]['argv'], ['go','test','-count=1','-buildvcs=false','-race','./...'])
        for index, step in enumerate(self.plan['default']):
            self.assertEqual(step.get('only_os'), 'ubuntu-24.04' if index >= 2 else None)
        for group in ('coverage','context'):
            self.assertTrue(all('only_os' not in s for s in self.plan[group]))
        self.assertIn('test_artifact_cli.py', self.plan['coverage'][0]['argv'][1])
        self.assertIn('--extra-profile', self.plan['coverage'][1]['argv'])
        self.assertEqual(self.plan['context'][2]['env'], {
            'CONTEXT_NATIVE_OBSERVATION_OUTPUT':'{OUTPUT}/context-native-observation.json'})

    def test_omitted_extra_duplicate_reordered_and_empty_groups_are_rejected(self):
        doc = json.loads(runner.PLAN.read_text(encoding='utf-8'))
        mutations = []
        for group in runner.GROUPS:
            changed = copy.deepcopy(doc)
            del changed['groups'][group]
            mutations.append(changed)
            changed = copy.deepcopy(doc)
            changed['groups'][group] = []
            mutations.append(changed)
            changed = copy.deepcopy(doc)
            changed['groups'][group].reverse()
            mutations.append(changed)
        extra = copy.deepcopy(doc)
        extra['groups']['optional'] = doc['groups']['default']
        mutations += [extra, [], {}]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'plan.json'
            for value in mutations:
                with self.subTest(type=type(value).__name__):
                    path.write_text(json.dumps(value), encoding='utf-8')
                    with self.assertRaises(ValueError):
                        runner.load_plan(path)
            path.write_text('{"format":1,"format":2}', encoding='utf-8')
            with self.assertRaises(ValueError):
                runner.load_plan(path)

    def test_shells_unsafe_cwds_unknown_fields_and_conditions_are_rejected(self):
        doc = json.loads(runner.PLAN.read_text(encoding='utf-8'))
        for field, value in [('argv',['sh','-c','true']), ('argv', []), ('cwd','../outside'),
                             ('only_os','windows-2025'), ('extra','value'), ('env',[]),
                             ('only_os','ubuntu-24.04')]:
            changed = copy.deepcopy(doc)
            changed['groups']['context'][0][field] = value
            with tempfile.TemporaryDirectory() as root:
                path = Path(root) / 'plan.json'
                path.write_text(json.dumps(changed), encoding='utf-8')
                with self.subTest(field=field), self.assertRaises(ValueError):
                    runner.load_plan(path)


class WorkerTest(unittest.TestCase):
    def setUp(self):
        self.owner = tempfile.TemporaryDirectory(prefix='native-group-contract-')
        self.addCleanup(self.owner.cleanup)
        self.root = Path(self.owner.name)
        self.plan, self.digest = runner.load_plan()
        self.calls = []

    def execute(self, group='context', fail_at=None, platform='windows/amd64', os_label='windows-2025'):
        def run(argv, **kwargs):
            self.calls.append((argv, kwargs))
            return SimpleNamespace(returncode=5 if len(self.calls) == fail_at else 0)
        with mock.patch.object(runner.subprocess,'check_output',return_value=str(self.root/'compiler-cache')), \
                mock.patch.object(runner.subprocess,'run',side_effect=run):
            result = runner.execute_group(group,self.root/group,os_label,platform,self.plan,self.digest)
        return result

    def test_complete_worker_executes_each_command_once_with_owned_isolation(self):
        result = self.execute()
        runner.validate_result(result,'context','windows-2025','windows/amd64',self.plan,self.digest)
        self.assertEqual(len(self.calls), 5)
        for argv, options in self.calls:
            self.assertEqual(argv[0], runner.sys.executable)
            env = options['env']
            self.assertEqual(env['HOME'], env['USERPROFILE'])
            self.assertEqual(env['TMP'], env['TEMP'])
            self.assertNotEqual(env['HOME'], env['TEMP'])
            self.assertFalse(Path(env['HOME']).exists(), 'owned worker directory must be removed')
            self.assertEqual(env['GOCACHE'],str(self.root/'compiler-cache'))
            self.assertFalse(options['check'])
        self.assertTrue((self.root/'context/result.json').is_file())

    def test_failure_is_preserved_without_retry_or_hiding_sibling_results(self):
        result = self.execute(fail_at=2)
        self.assertEqual(len(self.calls), 5)
        self.assertFalse(result['passed'])
        self.assertEqual([r['exit'] for r in result['steps']], [0,5,0,0,0])
        with self.assertRaises(ValueError):
            runner.validate_result(result,'context','windows-2025','windows/amd64',self.plan,self.digest)

    def test_existing_output_is_not_reused_as_fresh_proof(self):
        self.execute()
        with self.assertRaises(FileExistsError):
            self.execute()

    def test_native_default_preserves_only_the_existing_linux_only_skips(self):
        result = self.execute(group='default')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([r['selected'] for r in result['steps']], [True,True,False,False,False,False,False])
        runner.validate_result(result,'default','windows-2025','windows/amd64',self.plan,self.digest)

    def test_linux_executes_race_and_all_five_platform_specific_commands(self):
        result = self.execute(group='default',platform='linux/amd64',os_label='ubuntu-24.04')
        self.assertEqual(len(self.calls), 7)
        self.assertTrue(all(r['selected'] for r in result['steps']))
        self.assertIn('-race', self.calls[2][0])

    def test_missing_changed_skipped_duplicate_and_foreign_reports_refuse(self):
        good = self.execute()
        mutations=[]
        for key,value in [('group','coverage'),('platform','linux/amd64'),('plan_sha256','x'),('passed',False)]:
            mutations.append({**good,key:value})
        for field,value in [('selected',False),('exit',None),('exit',True),('exit',7),('seconds',float('nan')),('name','different')]:
            changed=copy.deepcopy(good)
            changed['steps'][0][field]=value
            mutations.append(changed)
        mutations.extend([{**good,'steps':good['steps'][:-1]}, {**good,'steps':good['steps']+[good['steps'][0]]}, []])
        for record in mutations:
            with self.subTest(type=type(record).__name__), self.assertRaises(ValueError):
                runner.validate_result(record,'context','windows-2025','windows/amd64',self.plan,self.digest)


class WorkflowTest(unittest.TestCase):
    def test_all_groups_remain_required_at_qualification_and_merge_boundaries(self):
        jobs=workflow_jobs((runner.REPO/'.github/workflows/ci.yml').read_text(encoding='utf-8'))
        grouped=jobs['artifact-native-checks']
        self.assertIn('needs: changes',grouped)
        self.assertIn('run_native_check_group.py',grouped)
        self.assertNotIn('--serial',grouped)
        self.assertNotIn('continue-on-error',grouped)
        for platform in runner.RUNNERS.values():
            self.assertIn('expected_platform: '+platform,grouped)
        for name in ('artifact-engine','artifact-coverage'):
            self.assertIn('artifact-native-checks',jobs[name].split('    needs:',1)[1].splitlines()[0])
        self.assertIn('      - artifact-native-checks\n',jobs['ci-passed'])
        self.assertIn("${{ needs['artifact-native-checks'].result }}",jobs['ci-passed'])
        self.assertIn('name: artifact-statements-${{ matrix.os }}',grouped)
        self.assertIn('name: artifact-context-${{ matrix.os }}',grouped)
        self.assertIn('attempt-${{ github.run_attempt }}',grouped)
        self.assertIn('run: python .github/scripts/test_native_check_group.py',jobs['ci-impact'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
