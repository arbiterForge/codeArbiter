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
               "github.ref == 'refs/heads/major/state-contracts'", "matrix.platform == 'linux/amd64'",
               "steps.cold_claude_observed.outcome == 'success'",'GH_TOKEN: ${{ github.token }}',
               '--job-name "[CHECK] | [CORE] | Structured artifact cold package  <linux/amd64>"',
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

if __name__=='__main__':unittest.main(verbosity=2)
