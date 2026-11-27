"""Retained cold workflow keeps one original execution and bounded evidence upload."""
import json
from pathlib import Path
import sys
import unittest
from test_ci_impact import workflow_jobs

ROOT=Path(__file__).resolve().parents[2]
NAME='[CHECK] | [CORE] | Structured artifact cold package  <linux/amd64>'
UPLOAD='actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9'
class RetainedColdPipelineTest(unittest.TestCase):
 def setUp(self):
  self.text=(ROOT/'.github/workflows/ci.yml').read_text(encoding='utf8')
  self.cold=workflow_jobs(self.text)['artifact-package-cold']
 def test_original_claude_invocation_is_observed_once_and_other_hosts_remain(self):
  self.assertEqual(self.cold.count('python -I -B .github/scripts/retained_archive_cli_observation.py'),1)
  self.assertEqual(self.cold.count('--cold-host "claude"'),1)
  # Explicit complementary CI branches choose one execution; never auth-failure fallback.
  self.assertIn("!(github.event_name == 'push' && (github.ref == 'refs/heads/main' || github.ref == 'refs/heads/major/state-contracts') && hashFiles('.github/integration-candidate.json') != '')",self.cold)
  observed=self.cold.split('id: cold_claude_observed',1)[1].split('- name: Preserve the exact claude',1)[0]
  self.assertIn("github.event_name == 'push' && (github.ref == 'refs/heads/main' || github.ref == 'refs/heads/major/state-contracts') && hashFiles('.github/integration-candidate.json') != ''",observed)
  self.assertEqual(self.cold.count('--host claude'),1)
  for host in ('codex','pi'):
   self.assertEqual(self.cold.count('--cold-host "'+host+'"'),1)
  for host in ('claude','codex','pi'):
   self.assertEqual(self.cold.count('id: cold_'+host+'\n'),1)
   self.assertIn('name: artifact-package-cold-${{ matrix.platform_token }}-'+host+'-${{ github.sha }}',self.cold)
  for pin in ('--stage "${{ runner.temp }}/artifact-host-payloads"',
              '--package-root "${{ runner.temp }}/artifact-release-packages"',
              '--platform "${{ matrix.platform }}"',
              '--output "${{ runner.temp }}/cold-claude/observation.json"'):
   self.assertIn(pin,self.cold)
 def test_report_is_after_original_receipt_and_uses_two_authenticated_payloads(self):
  receipt=self.cold.index('- name: Preserve the exact claude cold-execution receipt')
  capture=self.cold.index('- name: Preserve original installed Claude observation')
  emit=self.cold.index('- name: Emit installed Claude qualification report')
  upload=self.cold.index('- name: Upload major qualification report')
  self.assertLess(receipt,capture);self.assertLess(capture,emit);self.assertLess(emit,upload)
  observation=self.cold[capture:emit]
  self.assertIn('steps.cold_claude_observed.outcome == \'success\'',observation)
  self.assertIn(UPLOAD,observation)
  self.assertIn('path: ${{ runner.temp }}/cold-claude/*.json',observation)
  self.assertIn('overwrite: false',observation)
  report=self.cold[emit:upload]
  for part in ("github.event_name == 'push'", "github.ref == 'refs/heads/main'",
               "github.ref == 'refs/heads/major/state-contracts'",
               "steps.cold_claude_observed.outcome == 'success'",'GH_TOKEN: ${{ github.token }}',
               '--job-name "[CHECK] | [CORE] | Structured artifact cold package  <${{ matrix.platform }}>"',
               '--observation "cold=${{ runner.temp }}/cold-claude/observation.json"',
               '--payload-root "artifact-host-payloads-${{ github.sha }}=${{ runner.temp }}/artifact-host-payloads"',
               '--payload-root "artifact-release-packages-${{ github.sha }}=${{ runner.temp }}/artifact-release-packages"'):
   self.assertIn(part,report)
  self.assertIn('steps.cold-qualification.outputs.artifact_name',self.cold[upload:])
  self.assertIn('path: ${{ runner.temp }}/qualification.json',self.cold[upload:])
 def test_no_extra_permissions_or_hidden_failed_evidence(self):
  self.assertIn('timeout-minutes: 10',self.cold)
  self.assertIn('      actions: read\n      contents: read',self.cold)
  self.assertNotIn('actions: write',self.cold);self.assertNotIn('contents: write',self.cold)
  self.assertNotIn('continue-on-error:',self.cold)
  self.assertNotIn('if: always()',self.cold)
 def test_original_observer_control_suite_runs_on_required_contract_partition(self):
  self.assertIn("run: python .github/scripts/test_retained_archive_cli_observation.py",self.text)
  self.assertIn("run: python .github/scripts/test_retained_cold_observer_pipeline.py",self.text)
 def test_one_explicit_semantic_cell_has_only_actual_original_names(self):
  policy=json.loads((ROOT/'.github/major-qualification-policy.json').read_bytes())
  self.assertEqual(policy['cell_job_bindings']['installed:claude:workflow'],NAME)
  selection=json.loads((ROOT/'.github/major-test-selections.json').read_bytes())
  rows=[row for row in selection['groups'] if 'installed:claude:workflow' in row['cells']]
  self.assertEqual(len(rows),1);row=rows[0]
  self.assertEqual(row['job'],NAME);self.assertEqual(row['proof_kind'],'retained-archive-cli')
  self.assertEqual(row['payload_name'],'artifact-release-packages-{source_commit}')
  self.assertEqual(row['selectors'],[
   'cli:tools/build-host-packages.py:cold:claude:linux/amd64',
   *['receipt:.github/scripts/test_context_installed.py:'+name for name in (
    'test_t044_installed_context_kind','test_t044_rejects_missing_candidate_identity','test_t044_rejects_nonisolated_environment')]])

 def test_every_native_cell_routes_to_the_original_cold_consumer(self):
  policy=json.loads((ROOT/'.github/major-qualification-policy.json').read_bytes())
  groups=json.loads((ROOT/'.github/major-test-selections.json').read_bytes())['groups']
  cells=[cell for cell in policy['required_installed_cells'] if cell.startswith('installed:native:')]
  self.assertEqual(set(cells),{'installed:native:'+system+':'+arch
                             for system in ('linux','windows','darwin') for arch in ('amd64','arm64')})
  missing=[cell for cell in cells if cell not in policy['cell_job_bindings']
           or not any(cell in row['cells'] for row in groups)]
  self.assertEqual(missing,[], 'all six native installed cells need actual cold consumer routes')
  for cell in cells:
   platform=cell.removeprefix('installed:native:').replace(':','/')
   job='[CHECK] | [CORE] | Structured artifact cold package  <'+platform+'>'
   self.assertEqual(policy['cell_job_bindings'][cell],job)
   matching=[row for row in groups if cell in row['cells']]
   self.assertEqual(len(matching),1)
   row=matching[0]
   self.assertEqual(row['job'],job)
   self.assertEqual(row['proof_kind'],'retained-archive-cli')
   self.assertEqual(row['observation'],'cold')
   self.assertEqual(row['payload_name'],'artifact-release-packages-{source_commit}')
   self.assertEqual(row['selectors'],[
    'cli:tools/build-host-packages.py:cold:claude:'+platform,
    *['receipt:.github/scripts/test_context_installed.py:'+name for name in (
     'test_t044_installed_context_kind','test_t044_rejects_missing_candidate_identity',
     'test_t044_rejects_nonisolated_environment')]])
  report=self.cold.split('- name: Emit installed Claude qualification report',1)[1].split('- name: Upload major qualification report',1)[0]
  self.assertNotIn("matrix.platform == 'linux/amd64'",report)
  self.assertIn('--job-name "[CHECK] | [CORE] | Structured artifact cold package  <${{ matrix.platform }}>"',report)
  for clause in ("github.event_name == 'push'", "github.ref == 'refs/heads/main'",
                 "github.ref == 'refs/heads/major/state-contracts'",
                 "steps.cold_claude_observed.outcome == 'success'"):
   self.assertIn(clause,report)


 def _cold_named_step(self, name):
  import re
  matches=[step for step in re.split(r"(?m)^      - name: ",self.cold)[1:]
           if step.splitlines()[0] == name]
  self.assertEqual(len(matches),1)
  return matches[0]

 def _cold_condition_applies(self, step, outcome, cancelled=False):
  """Interpret only this workflow's closed boolean/string guard grammar."""
  import ast
  import re
  expressions=re.findall(r"(?m)^        if: (.+)$",step)
  self.assertEqual(len(expressions),1)
  expression=expressions[0].removeprefix('${{').removesuffix('}}').strip()
  # GitHub adds success() when a condition has no explicit status function.
  if not any(status in expression for status in ('cancelled()','success()','failure()')):
   if outcome == 'failure' or cancelled:return False
  substitutions={"steps.cold_claude_observed.outcome":repr(outcome),
                 "steps.cold-qualification.outcome":repr(outcome),
                 "github.event_name":repr('push'),"github.ref":repr('refs/heads/major/state-contracts'),
                 "hashFiles('.github/integration-candidate.json')":repr('candidate-present'),
                 'cancelled()':repr(cancelled),'success()':repr(outcome != 'failure' and not cancelled),
                 'failure()':repr(outcome == 'failure')}
  for old,new in substitutions.items():expression=expression.replace(old,new)
  expression=expression.replace('&&',' and ').replace('||',' or ')
  expression=re.sub(r'!(?!=)',' not ',expression).strip()
  def boolean(node):
   if isinstance(node,ast.Constant) and type(node.value) in (str,bool):return node.value
   if isinstance(node,ast.BoolOp):
    values=[boolean(value) for value in node.values]
    return all(values) if isinstance(node.op,ast.And) else any(values)
   if isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.Not):return not boolean(node.operand)
   if isinstance(node,ast.Compare) and len(node.ops)==len(node.comparators)==1:
    self.assertIsInstance(node.ops[0],(ast.Eq,ast.NotEq))
    equal=boolean(node.left)==boolean(node.comparators[0])
    return equal if isinstance(node.ops[0],ast.Eq) else not equal
   self.fail('unsupported cold condition node: '+type(node).__name__)
  return bool(boolean(ast.parse(expression,mode='eval').body))

 def test_attempted_failed_original_observation_remains_diagnostic_upload_eligible(self):
  step=self._cold_named_step('Preserve original installed Claude observation')
  for outcome,cancelled,expected in [('success',False,True),('failure',False,True),
                                     ('skipped',False,False),('cancelled',True,False)]:
   with self.subTest(outcome=outcome,cancelled=cancelled):
    self.assertEqual(self._cold_condition_applies(step,outcome,cancelled),expected,
                     'an attempted failed original observer must retain its diagnostic record')
  self.assertIn(UPLOAD,step)
  self.assertIn('path: ${{ runner.temp }}/cold-claude/*.json',step)
  self.assertIn('overwrite: false',step)

 def test_missing_original_observation_does_not_mask_the_primary_failure(self):
  import re
  step=self._cold_named_step('Preserve original installed Claude observation')
  self.assertEqual(re.findall(r'(?m)^          if-no-files-found: (.+)$',step),['ignore'],
                   'an admission refusal before writing a record must keep its primary failure')
  self.assertFalse(self._cold_condition_applies(step,'skipped'))

 def test_failed_or_skipped_observation_cannot_emit_or_upload_qualification(self):
  for name in ('Emit installed Claude qualification report','Upload major qualification report'):
   step=self._cold_named_step(name)
   for outcome,expected in [('success',True),('failure',False),('skipped',False)]:
    with self.subTest(step=name,outcome=outcome):
     self.assertEqual(self._cold_condition_applies(step,outcome),expected)



class ObserverCheckoutPolicyPipelineTests(unittest.TestCase):
 def test_original_observer_jobs_materialize_bytes_for_their_private_git_policy(self):
  import re
  from test_retained_archive_cli_observation import observer_checkout_fixture
  jobs=workflow_jobs((ROOT/'.github/workflows/ci.yml').read_text(encoding='utf8'))
  for job in ('artifact-package-cold','pi-installed-package'):
   with self.subTest(job=job):
    # Only job-level environment before steps controls checkout materialization.
    # A setting introduced after checkout cannot satisfy this behavioral test.
    precheckout=jobs[job].split('    steps:',1)[0]
    settings=dict(re.findall(r'^      (GIT_CONFIG_(?:COUNT|KEY_\d+|VALUE_\d+)): [\'"]?([^\'"\n]+?)[\'"]?\s*$',precheckout,re.M))
    with observer_checkout_fixture(settings) as fixture:
     try: observed=fixture['snapshot']()
     except ValueError as error:
      self.fail('fresh original '+job+' checkout is rejected under its own private Git policy: '+str(error))
     self.assertTrue(observed['clean'])
     self.assertEqual(fixture['before'],fixture['contents'])
     self.assertEqual({name:(fixture['repo']/name).read_bytes() for name in fixture['before']},fixture['before'])

if __name__=='__main__':unittest.main(verbosity=2)
