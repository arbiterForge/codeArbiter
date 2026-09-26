#!/usr/bin/env python3
"""Prove deterministic brownfield fixture preparation, not product readiness.

Run all cases, or name an explicit test class. Unknown selectors fail with exit 2.
No fixture-declared installation, test, deployment or network command executes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from _context_fixturelib import (
    FixtureError, MAX_CATALOG_BYTES, canonical_digest, load_catalog, materialize,
    snapshot, validate_catalog,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / '.github/fixtures/context-onboarding/cases.json'
EXPECTED_IDS = {
    'tiny-python', 'already-instructed', 'independent-packages',
    'infrastructure-no-database', 'conflicting-command-evidence',
    'partial-onboarding', 'dirty-staged-and-working', 'linked-detached-worktree',
    'unborn-repository', 'sparse-scope', 'ignored-inputs',
}


class TestCampaignSelection(unittest.TestCase):
    """The fixture set has a bounded campaign and does not certify execution."""

    def test_campaign_is_explicit_and_unapproved_oracles_stay_proposed(self):
        """Preparation is never stored as product or authority evidence."""
        catalog = load_catalog(CATALOG)
        self.assertEqual(catalog['campaign'], 'exercise-ready-brownfield')
        self.assertEqual(catalog['oracle_state'], 'proposed')
        self.assertNotIn('approved', catalog)

    def test_required_archetypes_and_task_kinds_are_present(self):
        """Coverage includes no-benefit, incomplete-scope and nonwriting tasks."""
        cases = load_catalog(CATALOG)['cases']
        tags = {tag for case in cases for tag in case['tags']}
        self.assertEqual(tags, {'tiny', 'instructed', 'monorepo', 'infrastructure',
                               'conflict', 'partial', 'dirty', 'linked', 'unborn',
                               'sparse', 'ignored'})
        self.assertEqual({case['task']['kind'] for case in cases}, {'feature', 'fix', 'test', 'review'})


    def test_catalog_only_change_reaches_required_native_hook_cells(self):
        """A JSON-only fixture correction must not skip its own required runner."""
        from test_hook_ci_partition import command, job_block, step_blocks, validate
        workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
        changes = job_block(workflow, 'changes')
        filters = changes.split('            hooks:\n', 1)[1]
        filters = re.split(r'^            [A-Za-z0-9_-]+:', filters, maxsplit=1, flags=re.M)[0]
        self.assertIn("- '.github/fixtures/context-onboarding/**'", [line.strip() for line in filters.splitlines()])
        hook_steps = step_blocks(job_block(workflow, 'hooks'))
        matching = [step for step in hook_steps if command(step) == 'python .github/scripts/test_context_fixtures.py']
        self.assertEqual(len(matching), 1)
        self.assertIn("matrix.partition == 'all' || matrix.partition == 'contracts'", matching[0])
        validate(workflow)  # The existing guard owns the exact inventory and counts.

    def test_fixture_filter_membership_survives_reordering_but_not_sibling_matches(self):
        """Exercise the actual guard with additive order and wrong-scope mutations."""
        workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
        fixture = "              - '.github/fixtures/context-onboarding/**'\n"
        added = "              - 'additional-hook-input/**'\n"
        for replacement in (added + fixture, added + added.replace('additional', 'other') + fixture):
            with self.subTest(replacement=replacement), mock.patch.object(
                    Path, 'read_text', return_value=workflow.replace(fixture, replacement, 1)):
                self.test_catalog_only_change_reaches_required_native_hook_cells()
        for replacement in (
                "              # - '.github/fixtures/context-onboarding/**'\n",
                added + '            other_filter:\n' + fixture,
                added + '            other_filter: # a sibling owns this list\n' + fixture,
                fixture.replace('/**', '/**/different')):
            with self.subTest(replacement=replacement), mock.patch.object(
                    Path, 'read_text', return_value=workflow.replace(fixture, replacement, 1)):
                with self.assertRaises(AssertionError):
                    self.test_catalog_only_change_reaches_required_native_hook_cells()

    def test_removing_fixture_runner_breaks_the_strict_inventory(self):
        """The extended inventory still detects deletion rather than trusting a count."""
        from test_hook_ci_partition import command, job_block, step_blocks, validate
        workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
        step = next(s for s in step_blocks(job_block(workflow, 'hooks'))
                    if command(s) == 'python .github/scripts/test_context_fixtures.py')
        with self.assertRaises(ValueError):
            validate(workflow.replace(step, '', 1))



class TestFixtureInventory(unittest.TestCase):
    """Pin case membership, raw input identity, and evaluator identity."""

    def test_case_membership_and_hashes_are_exact(self):
        """Every declared file and proposed oracle is independently hash checked."""
        cases = load_catalog(CATALOG)['cases']
        self.assertEqual({case['id'] for case in cases}, EXPECTED_IDS)
        self.assertEqual(len(cases), len(EXPECTED_IDS))
        for case in cases:
            with self.subTest(case=case['id']):
                for item in case['files'] + case['staged_edits'] + case['working_edits']:
                    self.assertEqual(hashlib.sha256(item['text'].encode('utf-8')).hexdigest(), item['sha256'])
                self.assertEqual(canonical_digest(case['oracle']), case['oracle_sha256'])
                self.assertEqual(canonical_digest({f['path']: f['sha256'] for f in case['files']}), case['snapshot_sha256'])

    def test_zero_new_files_is_a_real_default_outcome(self):
        """Fixture preparation does not select the optional instruction pilot."""
        for case in load_catalog(CATALOG)['cases']:
            self.assertEqual(case['oracle']['default_new_instruction_files'], 0)
        expected = {case['oracle']['disposition'] for case in load_catalog(CATALOG)['cases']}
        self.assertEqual(expected, {'task_possible', 'needs_decision', 'repair_required'})


class TestFixtureInputRejection(unittest.TestCase):
    """Malformed catalog data cannot start a process or overwrite user files."""

    def setUp(self):
        """Use a canonical test-owned parent on platforms with linked temp roots."""
        self.temporary = tempfile.TemporaryDirectory(prefix='ca-context-fixture-check-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.catalog = load_catalog(CATALOG)

    def test_unknown_keys_recipes_and_case_ids_fail_before_writing(self):
        """Closed control values never become arbitrary setup commands."""
        variants = []
        value = copy.deepcopy(self.catalog); value['run'] = 'anything'; variants.append(value)
        value = copy.deepcopy(self.catalog); value['cases'][0]['setup'] = 'deploy'; variants.append(value)
        value = copy.deepcopy(self.catalog); value['schema_version'] = True; variants.append(value)
        value = copy.deepcopy(self.catalog); value['cases'] = []; variants.append(value)
        for value in variants:
            with self.subTest(value=list(value)), mock.patch('subprocess.run') as command:
                with self.assertRaises(FixtureError):
                    materialize(value, 'tiny-python', self.root / 'not-created')
                command.assert_not_called()
                self.assertFalse((self.root / 'not-created').exists())
        with self.assertRaises(FixtureError):
            materialize(self.catalog, 'not-a-case', self.root / 'not-created')

    def test_unsafe_paths_duplicate_names_and_changed_bytes_reject(self):
        """Reject traversal, Windows aliases, collisions, and stale identities."""
        for path in ('../escape', '/absolute', 'C:/escape', 'a\\b', '.git/config',
                     'a/../b', 'a//b', 'CON.txt', 'a?', 'a.', 'a\nname'):
            value = copy.deepcopy(self.catalog); value['cases'][0]['files'][0]['path'] = path
            with self.subTest(path=repr(path)), self.assertRaises(FixtureError):
                validate_catalog(value)
        value = copy.deepcopy(self.catalog); value['cases'][0]['files'][0]['text'] += 'changed'
        with self.assertRaises(FixtureError): validate_catalog(value)
        value = copy.deepcopy(self.catalog); value['cases'].append(value['cases'][0])
        with self.assertRaises(FixtureError): validate_catalog(value)
        value = copy.deepcopy(self.catalog); value['cases'][0]['files'].append(value['cases'][0]['files'][0])
        with self.assertRaises(FixtureError): validate_catalog(value)
        value = copy.deepcopy(self.catalog); value['cases'][0]['oracle']['checks'][0] = 'changed'
        with self.assertRaises(FixtureError): validate_catalog(value)

    def test_closed_json_rejects_duplicates_nonfinite_and_oversize(self):
        """Limits apply before parsing and JSON key loss cannot hide data."""
        for raw in (b'{"schema_version":1,"schema_version":1}', b'{"value":NaN}',
                    b' ' * (MAX_CATALOG_BYTES + 1), b'\xff'):
            path = self.root / 'invalid.json'; path.write_bytes(raw)
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                load_catalog(path)

    def test_existing_destination_is_preserved(self):
        """A repeated fixture run cannot adopt an existing directory."""
        dest = self.root / 'existing'; dest.mkdir(); sentinel = dest / 'human.txt'
        sentinel.write_bytes(b'human-owned')
        with mock.patch('subprocess.run') as command, self.assertRaises(FixtureError):
            materialize(self.catalog, 'tiny-python', dest)
        command.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b'human-owned')

    def test_linked_parent_rejected_on_real_filesystem(self):
        """A link or junction cannot redirect create-only fixture output."""
        target = self.root / 'target'; target.mkdir(); linked = self.root / 'linked'
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(linked), str(target)], check=True, capture_output=True)
        else:
            linked.symlink_to(target, target_is_directory=True)
        try:
            with self.assertRaises(FixtureError):
                materialize(self.catalog, 'tiny-python', linked / 'case')
            self.assertFalse((target / 'case').exists())
        finally:
            if os.name == 'nt': linked.rmdir()
            else: linked.unlink()

    def test_unknown_selector_does_not_return_zero_tests_success(self):
        """The documented runner rejects unknown selections explicitly."""
        result = subprocess.run([sys.executable, __file__, 'MissingSuite'], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'unknown test selector', result.stderr)


class TestFixtureMaterialization(unittest.TestCase):
    """Exercise actual Git state and on-disk placement with synthetic repositories."""

    def setUp(self):
        """Retain only session-owned fixture directories for automatic cleanup."""
        self.temporary = tempfile.TemporaryDirectory(prefix='ca-context-fixture-real-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.catalog = load_catalog(CATALOG)
        self.git = shutil.which('git')
        self.assertIsNotNone(self.git, 'Git is required, not a skippable qualification')

    def command(self, instance, *args, check=True):
        """Read known fixture Git state; do not execute repository commands."""
        return subprocess.run([self.git, *args], cwd=instance['solver'],
                              capture_output=True, check=check, timeout=20)

    def test_every_case_has_exact_files_and_separate_evaluator_data(self):
        """Materialized file bytes match their declarations in every recipe."""
        for case in self.catalog['cases']:
            with self.subTest(case=case['id']):
                instance = materialize(self.catalog, case['id'], self.root / case['id'])
                expected = {f['path']: f['sha256'] for f in case['files'] + case['staged_edits'] + case['working_edits']}
                if case['setup'] == 'sparse':
                    expected = {p: h for p, h in expected.items() if '/' not in p or p.startswith('app/')}
                self.assertEqual(instance['files'], dict(sorted(expected.items())))
                self.assertEqual(snapshot(instance['solver']), instance['files'])
                self.assertFalse(instance['evaluator'].is_relative_to(instance['solver']))
                oracle = json.loads((instance['evaluator'] / 'oracle.json').read_text())
                self.assertEqual(canonical_digest(oracle), case['oracle_sha256'])
                self.assertEqual(set(instance['task']), {'kind', 'prompt'})
                tracked = self.command(instance, 'ls-files').stdout.decode('utf-8')
                self.assertNotIn('oracle.json', tracked)
                self.assertNotIn('identity.json', tracked)
                self.assertNotIn('UNEXPECTED_EXECUTION', instance['files'])

    def test_staged_working_and_untracked_bytes_remain_distinct(self):
        """A common HEAD never hides a working/index content disagreement."""
        instance = materialize(self.catalog, 'dirty-staged-and-working', self.root / 'case')
        self.assertIn(b'staged:', self.command(instance, 'show', ':app.py').stdout)
        self.assertIn(b'working:', (instance['solver'] / 'app.py').read_bytes())
        status = self.command(instance, 'status', '--porcelain=v1').stdout
        self.assertIn(b'MM app.py', status)
        self.assertIn(b'?? notes.txt', status)

    def test_linked_detached_and_sparse_boundaries_are_real(self):
        """Detached linked state and sparse absence are actual Git configurations."""
        linked = materialize(self.catalog, 'linked-detached-worktree', self.root / 'linked')
        self.assertTrue((linked['solver'] / '.git').is_file())
        self.assertEqual(self.command(linked, 'symbolic-ref', '-q', 'HEAD', check=False).returncode, 1)
        common = self.command(linked, 'rev-parse', '--git-common-dir').stdout.decode().strip()
        self.assertEqual((linked['solver'] / common).resolve(), (self.root / 'linked/primary/.git').resolve())
        sparse = materialize(self.catalog, 'sparse-scope', self.root / 'sparse')
        self.assertFalse((sparse['solver'] / 'other/storage.sql').exists())
        self.assertIn(b'other/storage.sql', self.command(sparse, 'ls-tree', '-r', '--name-only', 'HEAD').stdout)

    def test_detached_primary_recipe_has_no_branch(self):
        """The detached recipe is tested separately from linked worktree storage."""
        catalog = copy.deepcopy(self.catalog)
        catalog['cases'][0]['setup'] = 'detached'
        instance = materialize(catalog, 'tiny-python', self.root / 'detached')
        self.assertTrue((instance['solver'] / '.git').is_dir())
        self.assertEqual(self.command(instance, 'symbolic-ref', '-q', 'HEAD', check=False).returncode, 1)

    def test_unborn_and_ignored_inputs_are_not_promoted(self):
        """No HEAD and ignored data remain distinct from ordinary tracked files."""
        unborn = materialize(self.catalog, 'unborn-repository', self.root / 'unborn')
        self.assertNotEqual(self.command(unborn, 'rev-parse', '--verify', 'HEAD', check=False).returncode, 0)
        ignored = materialize(self.catalog, 'ignored-inputs', self.root / 'ignored')
        self.assertEqual(self.command(ignored, 'check-ignore', 'cache/fixture-note.txt').returncode, 0)
        self.assertNotIn(b'cache/fixture-note.txt', self.command(ignored, 'ls-files').stdout)
        self.assertFalse((ignored['solver'] / 'UNEXPECTED_EXECUTION').exists())


    def test_task_and_dirty_recipe_are_bound_beyond_initial_snapshot(self):
        """Equal initial files cannot hide a changed task or index/working recipe."""
        catalog = load_catalog(CATALOG)
        original_case = next(c for c in catalog['cases'] if c['id'] == 'dirty-staged-and-working')
        with tempfile.TemporaryDirectory(prefix='ca-context-identity-') as temp:
            parent = Path(temp).resolve()
            original = materialize(catalog, original_case['id'], parent / 'original')
            first = json.loads((original['evaluator'] / 'identity.json').read_text())
            changed = copy.deepcopy(catalog)
            second_case = next(c for c in changed['cases'] if c['id'] == original_case['id'])
            second_case['task']['prompt'] += ' Focus only on the staged diff.'
            altered = materialize(changed, second_case['id'], parent / 'changed')
            second = json.loads((altered['evaluator'] / 'identity.json').read_text())
            self.assertEqual(first['fixture_snapshot_sha256'], second['fixture_snapshot_sha256'])
            self.assertEqual(first['worktree_files'], second['worktree_files'])
            self.assertNotEqual(first['case_sha256'], second['case_sha256'])
            self.assertNotEqual(first['task_sha256'], second['task_sha256'])
            self.assertEqual(first['case_sha256'], canonical_digest(original_case))
            edited = copy.deepcopy(original_case)
            edited['staged_edits'][0]['text'] += '# index-only change\n'
            self.assertNotEqual(canonical_digest(original_case), canonical_digest(edited))

    def test_repeated_materialization_has_identical_content_snapshots(self):
        """Instance directory and clock values do not affect input identity."""
        first = materialize(self.catalog, 'tiny-python', self.root / 'first')
        second = materialize(self.catalog, 'tiny-python', self.root / 'second')
        self.assertEqual(first['files'], second['files'])
        self.assertEqual(self.command(first, 'rev-parse', 'HEAD').stdout,
                         self.command(second, 'rev-parse', 'HEAD').stdout)


def main() -> int:
    """Run nonempty known class selections, or every fixture preparation test."""
    allowed = {name: value for name, value in globals().items()
               if name.startswith('Test') and isinstance(value, type) and issubclass(value, unittest.TestCase)}
    selectors = sys.argv[1:] or list(allowed)
    if any(name not in allowed for name in selectors):
        print('unknown test selector; choose: ' + ', '.join(allowed), file=sys.stderr)
        return 2
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(allowed[name]) for name in selectors)
    if suite.countTestCases() == 0:
        print('zero selected tests', file=sys.stderr)
        return 2
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
