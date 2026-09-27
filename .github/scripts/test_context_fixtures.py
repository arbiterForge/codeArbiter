#!/usr/bin/env python3
"""Prepare deterministic brownfield fixture and evaluator inputs.

This module and cases.json are framework/evaluator preparation inputs, separate
from generated solver fixtures and not ordinary tests delivered with a selected
fixture. materialize writes only the selected case's declared files and its
staged and working edits to destination/solver; a linked fixture has its
declared fixture-owned Git parent. The returned task contains only kind and
prompt. Oracle and identity records go to destination/evaluator. Framework and
catalog files are not copied into solver inventory or fixture history.

The complete harness record includes the evaluator path and is not itself a
model-input object. This suite does not launch a model or deliver that record
as model input. Ordinary solver tests are explicit fixture files such as
tests/test_app.py; this evaluator harness is not one.

This command starts no solving actor and establishes deterministic placement
only. Filesystem path separation is not OS confinement or a completed live
trial. The unchanged approved plan calls for later authorized fresh-session
trials to keep evaluator/framework answers outside the actor's effective
readable files and model input; leakage invalidates such a trial under that
plan.

Run all cases, or name an explicit test class. Unknown selectors fail with exit 2.
The materializer never executes fixture-declared commands. The separately frozen
fix-problem control runs its fixed stdlib unittest argv in a disposable fixture;
it performs no installation, deployment or network operation.
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

# Independently reviewed worktree inventories. These are intentionally not
# derived from the mutable catalog; sparse storage outside the selected scope
# is omitted from the visible inventory.
EXPECTED_SOLVER_FILES = {
    'tiny-python': ('app.py', 'README.md', 'tests/test_app.py'),
    'already-instructed': ('AGENTS.md', 'app.py', 'README.md',
                           'tests/AGENTS.override.md', 'tests/CLAUDE.md',
                           'tests/test_app.py'),
    'independent-packages': ('packages/js/package.json', 'packages/js/test.mjs',
                             'packages/py/app.py', 'packages/py/tests/test_app.py',
                             'README.md'),
    'infrastructure-no-database': ('main.tf', 'README.md'),
    'conflicting-command-evidence': ('AGENTS.md', 'package.json', 'README.md'),
    'partial-onboarding': ('.codearbiter/CONTEXT.md', '.codearbiter/open-tasks.md',
                           '.codearbiter/overrides.log', 'app.py', 'README.md',
                           'tests/test_app.py'),
    'dirty-staged-and-working': ('app.py', 'notes.txt', 'README.md',
                                 'tests/test_app.py'),
    'linked-detached-worktree': ('AGENTS.md', 'app.py', 'README.md',
                                 'tests/test_app.py'),
    'unborn-repository': ('AGENTS.md', 'README.md'),
    'sparse-scope': ('app/service.py', 'README.md'),
    'ignored-inputs': ('.gitignore', 'app.py', 'cache/fixture-note.txt',
                       'do-not-run.py', 'README.md', 'tests/test_app.py'),
}

# Independent reviewed task and mutation inventories. Each path is pinned to raw
# UTF-8 bytes; the static table is never computed from the loaded catalog at run time.
EXPECTED_CASE_INPUTS = {'tiny-python': {'setup': 'committed',
                 'tags': ['tiny'],
                 'task': {'kind': 'feature',
                          'prompt': 'Add a prefix option to label(value) while keeping existing '
                                    'calls compatible.'},
                 'files': {'README.md': '747b97be20702dda3ad639a2312010aa2594a4a2cb8f8c8ebc2f6a969f8be7ce',
                           'app.py': '96ccccb56957c6b8b30c27ab69faad494f5781ea9838048d8374d9ac60117f15',
                           'tests/test_app.py': '85c41e98e83ed5dc839121b95d2a05f3f0efbf01e0013631a37a8a623565d4e9'},
                 'staged_edits': {},
                 'working_edits': {}},
 'already-instructed': {'setup': 'committed',
                        'tags': ['instructed'],
                        'task': {'kind': 'test',
                                 'prompt': 'Add a regression test for an empty string. Keep '
                                           'production code unchanged.'},
                        'files': {'AGENTS.md': '0359c933083159a3fe92b4317c5466c72cafdb65fb10ddf3fa0a4aefc0df950e',
                                  'README.md': '747b97be20702dda3ad639a2312010aa2594a4a2cb8f8c8ebc2f6a969f8be7ce',
                                  'app.py': '96ccccb56957c6b8b30c27ab69faad494f5781ea9838048d8374d9ac60117f15',
                                  'tests/AGENTS.override.md': '92d5589175a917e646ba927dcfb67bf723000e42dfb341cf2f0ed060063a8f2d',
                                  'tests/CLAUDE.md': 'c4fb1f4529d4d6c1f658d94ce59d529e66e41973e1555f78ddd3679cdaa0c754',
                                  'tests/test_app.py': '85c41e98e83ed5dc839121b95d2a05f3f0efbf01e0013631a37a8a623565d4e9'},
                        'staged_edits': {},
                        'working_edits': {}},
 'independent-packages': {'setup': 'committed',
                          'tags': ['monorepo'],
                          'task': {'kind': 'test',
                                   'prompt': 'Extend the Python tests without touching the '
                                             'JavaScript package.'},
                          'files': {'README.md': '54cc67f029f5f190b4690db38d5a28cc264f3df1c3d48583b5c3e7e769a12300',
                                    'packages/js/package.json': 'afbdfa341178e339e6e0cbec9af5762d432c80af6ebe8b81945267f570234bff',
                                    'packages/js/test.mjs': '948ce0a03e32b505e8146ec12b21b7a0ed8e78de7efae11ca5a19e60d2575182',
                                    'packages/py/app.py': '9344fe33a09be455d18787e4d4b0a09b1965cb22758f1562704835a0a1410e16',
                                    'packages/py/tests/test_app.py': '3bcde85d5a8774c829b3e19fca316f1704c793150af00f56d55b2d4fdc85eda0'},
                          'staged_edits': {},
                          'working_edits': {}},
 'infrastructure-no-database': {'setup': 'committed',
                                'tags': ['infrastructure'],
                                'task': {'kind': 'review',
                                         'prompt': 'Review naming and explain the local value. Do '
                                                   'not deploy or edit files.'},
                                'files': {'README.md': 'ddc35f02cc421c9eba66504360fbab57d4136d79a8ce1c1c0665f3ddd673f34a',
                                          'main.tf': '996e6371cc12c758ad351c9e13f7cb170f1919457d4824c5538946231ce049cd'},
                                'staged_edits': {},
                                'working_edits': {}},
 'conflicting-command-evidence': {'setup': 'committed',
                                  'tags': ['conflict'],
                                  'task': {'kind': 'fix',
                                           'prompt': 'Determine which test entry point should be '
                                                     'used before changing the application.'},
                                  'files': {'AGENTS.md': 'c232cdb703b812777161472ca5ccf85b4fc8cec088dbf21dd420083bd7877715',
                                            'README.md': '3f316881f484f97ec56f306ccc13e6cd1b87684cc7246b02c177db39e5f25d3c',
                                            'package.json': 'e4d59c2481f40cd3263530c7f498434bb2ce66336463aaa95789556118a98415'},
                                  'staged_edits': {},
                                  'working_edits': {}},
 'partial-onboarding': {'setup': 'committed',
                        'tags': ['partial'],
                        'task': {'kind': 'feature',
                                 'prompt': 'Resume interrupted onboarding and prepare a bounded '
                                           'contribution without resetting existing records.'},
                        'files': {'.codearbiter/CONTEXT.md': 'a3d73be0db10c4dfd176f0509b46cccf51d5926ccfafe134b264978e6bb37132',
                                  '.codearbiter/open-tasks.md': '78d05d8d9c36e231713b2a7e51db9b318f626d08116ccc40c4cb4a1ded135b03',
                                  '.codearbiter/overrides.log': 'd58ec9523bf334906e3337f47c964897fd6e67fb349c927c0db885de4aa543ee',
                                  'README.md': '747b97be20702dda3ad639a2312010aa2594a4a2cb8f8c8ebc2f6a969f8be7ce',
                                  'app.py': '96ccccb56957c6b8b30c27ab69faad494f5781ea9838048d8374d9ac60117f15',
                                  'tests/test_app.py': '85c41e98e83ed5dc839121b95d2a05f3f0efbf01e0013631a37a8a623565d4e9'},
                        'staged_edits': {},
                        'working_edits': {}},
 'dirty-staged-and-working': {'setup': 'committed',
                              'tags': ['dirty'],
                              'task': {'kind': 'review',
                                       'prompt': 'Review current work and distinguish staged, '
                                                 'unstaged, and untracked changes. Do not modify '
                                                 'or stage anything.'},
                              'files': {'README.md': '747b97be20702dda3ad639a2312010aa2594a4a2cb8f8c8ebc2f6a969f8be7ce',
                                        'app.py': '96ccccb56957c6b8b30c27ab69faad494f5781ea9838048d8374d9ac60117f15',
                                        'tests/test_app.py': '85c41e98e83ed5dc839121b95d2a05f3f0efbf01e0013631a37a8a623565d4e9'},
                              'staged_edits': {'app.py': 'cac682b651fe34215c6ed6dd5fa9b4352d165ce4a87881412fbf0167e8e6c592'},
                              'working_edits': {'app.py': 'd2a3788cb9e770b68797c43d6a0d115d9bd3090d2e926a52e8789b5db3f9c0a0',
                                                'notes.txt': '1a4d79b8392ad185e6a42c7b1555daaa24d4e07f7f0e2ea4d7718c21c75025a9'}},
 'linked-detached-worktree': {'setup': 'linked',
                              'tags': ['linked'],
                              'task': {'kind': 'review',
                                       'prompt': 'Identify the selected worktree and review it '
                                                 'without writing.'},
                              'files': {'AGENTS.md': '5e6ba6563c0cf1560ef0d6657cd62a8a1a2ced1030aa1c4e7a5d6bc69f255650',
                                        'README.md': '747b97be20702dda3ad639a2312010aa2594a4a2cb8f8c8ebc2f6a969f8be7ce',
                                        'app.py': '96ccccb56957c6b8b30c27ab69faad494f5781ea9838048d8374d9ac60117f15',
                                        'tests/test_app.py': '85c41e98e83ed5dc839121b95d2a05f3f0efbf01e0013631a37a8a623565d4e9'},
                              'staged_edits': {},
                              'working_edits': {}},
 'unborn-repository': {'setup': 'unborn',
                       'tags': ['unborn'],
                       'task': {'kind': 'feature',
                                'prompt': 'Describe the first implementation step using only the '
                                          'existing scaffold and guidance.'},
                       'files': {'AGENTS.md': '647af297e5110511b773879e1a466f8bf71c9f43d805c5b2cf0fa768f58f90bd',
                                 'README.md': 'a5f626c93e818f8f12877cfa38a1ca27d63114a845da692d80a14ad4d2dceceb'},
                       'staged_edits': {},
                       'working_edits': {}},
 'sparse-scope': {'setup': 'sparse',
                  'tags': ['sparse', 'monorepo'],
                  'task': {'kind': 'review',
                           'prompt': 'Review app/service.py and state the limits of the inspected '
                                     'scope.'},
                  'files': {'README.md': 'f270a78cf9173a1ba2e0a8ad62f7f83a5ca93f3fa190c26ccfcc5f1d27a97eaf',
                            'app/service.py': 'a9d119e7d1e13d36e999afeb9b84bbe35092cf8eb3c72e333ade29deacf84e94',
                            'other/storage.sql': 'd35ce3191ce611ece4ae2456acf216a3b0d3f5194d4b2eea2663e8c9be8f5be8'},
                  'staged_edits': {},
                  'working_edits': {}},
 'ignored-inputs': {'setup': 'committed',
                    'tags': ['ignored'],
                    'task': {'kind': 'review',
                             'prompt': 'Review tracked application code; do not run scripts or use '
                                       'ignored cache text as guidance.'},
                    'files': {'.gitignore': '695426e943174af72f2a2391c3f48ed02c52873628e79be9fbf1a117f9ab3d9d',
                              'README.md': '747b97be20702dda3ad639a2312010aa2594a4a2cb8f8c8ebc2f6a969f8be7ce',
                              'app.py': '96ccccb56957c6b8b30c27ab69faad494f5781ea9838048d8374d9ac60117f15',
                              'cache/fixture-note.txt': '288af22ee49777f75a2396b6635d8408bdf948335a5862f03707aadf46880813',
                              'do-not-run.py': '6868b541dd18c0941ee52958e22ef713ef71dcf65af3aa653b347ab4b3146025',
                              'tests/test_app.py': '85c41e98e83ed5dc839121b95d2a05f3f0efbf01e0013631a37a8a623565d4e9'},
                    'staged_edits': {},
                    'working_edits': {}}}

# Proposed, fixture-only expectations reviewed against each declared task and its
# ordinary fixture files. This is deliberately authored outside cases.json and
# is not an approved live-trial answer or product-qualification record.
PROPOSED_FIXTURE_ONLY_ORACLE_EXPECTATIONS = {
    'tiny-python': {
        'oracle': {
            'disposition': 'task_possible',
            'default_new_instruction_files': 0,
            'preserve_paths': [],
            'checks': [
                'Preserve the existing one-argument behavior.',
                'Verify only the relevant local tests; a manifest declaration is not command-success evidence.',
            ],
        },
        'oracle_sha256': '8ad9f14b332372c0d93de1646aa2eed3f00b5a04ef007ffe0c0602d40c8a41e2',
    },
    'already-instructed': {
        'oracle': {
            'disposition': 'task_possible',
            'default_new_instruction_files': 0,
            'preserve_paths': ['AGENTS.md', 'tests/CLAUDE.md', 'tests/AGENTS.override.md', 'app.py'],
            'checks': [
                'Do not replace, duplicate, or adopt human instruction files.',
                'A test-only request must not become a production refactor.',
            ],
        },
        'oracle_sha256': '71239b7a435e0cc23035a29bc7a8aee2c3d6b0a229413638cebed203aaccbf17',
    },
    'independent-packages': {
        'oracle': {
            'disposition': 'task_possible',
            'default_new_instruction_files': 0,
            'preserve_paths': ['packages/js/package.json', 'packages/js/test.mjs'],
            'checks': [
                'The working directory is packages/py, not repository root.',
                'Do not run or modify the unrelated JavaScript package.',
            ],
        },
        'oracle_sha256': '551ced11c12d76307e82025e443263fe1aec41e9467a10ffc6e06a579cff7c7f',
    },
    'infrastructure-no-database': {
        'oracle': {
            'disposition': 'task_possible',
            'default_new_instruction_files': 0,
            'preserve_paths': ['README.md', 'main.tf'],
            'checks': [
                'No database guidance or database interview is necessary for this task.',
                'No Terraform installation, initialization, plan, apply, or network operation is authorized.',
            ],
        },
        'oracle_sha256': 'eebc3d54dd161dcc5bceb5508ddc732196568b6a684c24b9904c2b37be71af2b',
    },
    'conflicting-command-evidence': {
        'oracle': {
            'disposition': 'needs_decision',
            'default_new_instruction_files': 0,
            'preserve_paths': ['AGENTS.md', 'package.json'],
            'checks': [
                'Retain both citations and the effective instruction constraint.',
                'Do not execute the contradicted command or claim either command succeeded.',
            ],
        },
        'oracle_sha256': 'd8e3aa6cc5422525e27a30da3520aa8247e984ed0abcb0510e74e4ffe3dc822b',
    },
    'partial-onboarding': {
        'oracle': {
            'disposition': 'repair_required',
            'default_new_instruction_files': 0,
            'preserve_paths': ['.codearbiter/open-tasks.md', '.codearbiter/overrides.log'],
            'checks': [
                'The example sentinel is not genuine completion.',
                'Keep the existing empty task/audit headers; do not invent entries just to make files nonempty.',
            ],
        },
        'oracle_sha256': '146faeabf38ac259a66bda2f08852ffe939460651395534d23828224e4ab56be',
    },
    'dirty-staged-and-working': {
        'oracle': {
            'disposition': 'task_possible',
            'default_new_instruction_files': 0,
            'preserve_paths': ['app.py', 'notes.txt'],
            'checks': [
                'Preserve separately staged and working-tree contents for app.py.',
                'Retain the untracked notes file and report it without adopting its text as policy.',
            ],
        },
        'oracle_sha256': 'bb7f7a3fb072233aa97375f6e7983bf053d35ec6bbf35c870cbfa1302ead51ff',
    },
    'linked-detached-worktree': {
        'oracle': {
            'disposition': 'task_possible',
            'default_new_instruction_files': 0,
            'preserve_paths': ['AGENTS.md', 'app.py'],
            'checks': [
                'Selected worktree is detached and distinct from its primary checkout.',
                'Shared Git storage alone does not establish equal working content.',
            ],
        },
        'oracle_sha256': '6aebe51758e7b2587834ec0ff9e1bf1434dba78c38342f207bad08ea17242b83',
    },
    'unborn-repository': {
        'oracle': {
            'disposition': 'task_possible',
            'default_new_instruction_files': 0,
            'preserve_paths': ['AGENTS.md'],
            'checks': [
                'HEAD does not exist; do not fabricate a commit or upstream branch.',
                'Do not invent deeper directory-specific rules.',
            ],
        },
        'oracle_sha256': '6924b15b4565c3f75c65cefc7888f03b6bbff79fd5952569855e82c3cacea05d',
    },
    'sparse-scope': {
        'oracle': {
            'disposition': 'task_possible',
            'default_new_instruction_files': 0,
            'preserve_paths': ['app/service.py'],
            'checks': [
                'The absent storage file is outside sparse checkout, not proof that the repository has no data layer.',
                'Do not hydrate unrelated sparse paths.',
            ],
        },
        'oracle_sha256': '3ff93f0a4cb672ed3f46be60c82443cc95420a94b2f108a6c6dcb68f31a95e52',
    },
    'ignored-inputs': {
        'oracle': {
            'disposition': 'task_possible',
            'default_new_instruction_files': 0,
            'preserve_paths': ['cache/fixture-note.txt', 'do-not-run.py'],
            'checks': [
                'Ignored synthetic content remains ignored and unmodified.',
                'Materialization and discovery must not execute do-not-run.py.',
            ],
        },
        'oracle_sha256': '2087f2b1172fa444886e5a4f2bcb4034541db1f7e91f39666a9ec705aa5148d6',
    },
}


class TestCampaignSelection(unittest.TestCase):
    """The fixture set has a bounded campaign and does not certify execution."""

    def shortDescription(self):
        return None

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

    def shortDescription(self):
        return None

    def assert_proposed_oracle_contract(self, cases):
        """Require candidate self-hashes and independent fixture-only answers."""
        for case in cases:
            expected = PROPOSED_FIXTURE_ONLY_ORACLE_EXPECTATIONS[case['id']]
            self.assertEqual(canonical_digest(case['oracle']), case['oracle_sha256'])
            self.assertEqual(case['oracle'], expected['oracle'],
                             'candidate answer differs from independent expectation')
            self.assertEqual(case['oracle_sha256'], expected['oracle_sha256'],
                             'candidate digest differs from independent expectation')

    def test_case_membership_and_hashes_are_exact(self):
        """Every declared file and proposed oracle is independently hash checked."""
        cases = load_catalog(CATALOG)['cases']
        self.assertEqual({case['id'] for case in cases}, EXPECTED_IDS)
        self.assertEqual(len(cases), len(EXPECTED_IDS))
        self.assertEqual(set(PROPOSED_FIXTURE_ONLY_ORACLE_EXPECTATIONS), EXPECTED_IDS)
        self.assertEqual(set(EXPECTED_SOLVER_FILES), EXPECTED_IDS)
        self.assertEqual(set(EXPECTED_CASE_INPUTS), EXPECTED_IDS)
        for case in cases:
            with self.subTest(case=case['id']):
                for item in case['files'] + case['staged_edits'] + case['working_edits']:
                    self.assertEqual(hashlib.sha256(item['text'].encode('utf-8')).hexdigest(), item['sha256'])
                expected = PROPOSED_FIXTURE_ONLY_ORACLE_EXPECTATIONS[case['id']]
                self.assertEqual(case['oracle'], expected['oracle'])
                self.assertEqual(case['oracle_sha256'], expected['oracle_sha256'])
                self.assertEqual(canonical_digest(case['oracle']), case['oracle_sha256'])
                self.assertEqual(canonical_digest({f['path']: f['sha256'] for f in case['files']}), case['snapshot_sha256'])
                frozen = EXPECTED_CASE_INPUTS[case['id']]
                self.assertEqual(case['setup'], frozen['setup'], f"{case['id']}: setup recipe")
                self.assertEqual(case['tags'], frozen['tags'], f"{case['id']}: archetype tags")
                self.assertEqual(case['task'], frozen['task'], f"{case['id']}: task identity")
                for phase in ('files', 'staged_edits', 'working_edits'):
                    actual = {item['path']: item for item in case[phase]}
                    self.assertEqual(set(actual), set(frozen[phase]),
                                     f"{case['id']}: {phase} path inventory")
                    for path, expected_hash in frozen[phase].items():
                        self.assertEqual(actual[path]['sha256'], expected_hash,
                                         f"{case['id']}: {phase} {path} raw SHA256")

    def test_recomputed_input_mutations_reach_the_inventory_guard(self):
        """Valid catalog edits cannot silently change the reviewed task inputs."""
        def owning_result(value):
            """Run the declared owning method with ordinary unittest result handling."""
            owner = TestFixtureInventory('test_case_membership_and_hashes_are_exact')
            result = unittest.TestResult()
            owning_module = sys.modules[owner.__class__.__module__]
            with mock.patch.object(owning_module, 'load_catalog', return_value=value):
                owner.run(result)
            self.assertEqual(result.testsRun, 1)
            self.assertEqual(result.errors, [])
            self.assertEqual(result.skipped, [])
            return result

        catalog = load_catalog(CATALOG)
        self.assertTrue(owning_result(catalog).wasSuccessful())

        candidates = []
        changed = copy.deepcopy(catalog)
        case = next(c for c in changed['cases'] if c['id'] == 'conflicting-command-evidence')
        item = next(f for f in case['files'] if f['path'] == 'package.json')
        item['text'] = item['text'].replace('node old-runner.mjs', 'node --test')
        item['sha256'] = hashlib.sha256(item['text'].encode('utf-8')).hexdigest()
        case['snapshot_sha256'] = canonical_digest({f['path']: f['sha256'] for f in case['files']})
        candidates.append(('lost command conflict', changed,
                           'conflicting-command-evidence: files package.json raw SHA256'))

        changed = copy.deepcopy(catalog)
        case = next(c for c in changed['cases'] if c['id'] == 'tiny-python')
        case['task']['kind'] = 'review'
        candidates.append(('task kind reassigned', changed, 'tiny-python: task identity'))

        changed = copy.deepcopy(catalog)
        case = next(c for c in changed['cases'] if c['id'] == 'dirty-staged-and-working')
        item = next(f for f in case['staged_edits'] if f['path'] == 'app.py')
        item['text'] += '# changed index recipe\n'
        item['sha256'] = hashlib.sha256(item['text'].encode('utf-8')).hexdigest()
        candidates.append(('staged recipe changed', changed,
                           'dirty-staged-and-working: staged_edits app.py raw SHA256'))

        changed = copy.deepcopy(catalog)
        tiny = next(c for c in changed['cases'] if c['id'] == 'tiny-python')
        instructed = next(c for c in changed['cases'] if c['id'] == 'already-instructed')
        tiny['tags'], instructed['tags'] = instructed['tags'], tiny['tags']
        candidates.append(('archetype tags swapped', changed, 'tiny-python: archetype tags'))

        changed = copy.deepcopy(catalog)
        case = next(c for c in changed['cases'] if c['id'] == 'tiny-python')
        case['setup'] = 'detached'
        candidates.append(('setup changed', changed, 'tiny-python: setup recipe'))

        changed = copy.deepcopy(catalog)
        case = next(c for c in changed['cases'] if c['id'] == 'tiny-python')
        case['task']['prompt'] += ' Do not inspect the tests.'
        candidates.append(('task prompt changed', changed, 'tiny-python: task identity'))

        changed = copy.deepcopy(catalog)
        case = next(c for c in changed['cases'] if c['id'] == 'dirty-staged-and-working')
        item = next(f for f in case['working_edits'] if f['path'] == 'app.py')
        item['text'] += '# changed working recipe\n'
        item['sha256'] = hashlib.sha256(item['text'].encode('utf-8')).hexdigest()
        candidates.append(('working recipe changed', changed,
                           'dirty-staged-and-working: working_edits app.py raw SHA256'))

        changed = copy.deepcopy(catalog)
        case = next(c for c in changed['cases'] if c['id'] == 'tiny-python')
        case['files'] = [f for f in case['files'] if f['path'] != 'tests/test_app.py']
        case['snapshot_sha256'] = canonical_digest({f['path']: f['sha256'] for f in case['files']})
        candidates.append(('initial path removed', changed, 'tiny-python: files path inventory'))

        changed = copy.deepcopy(catalog)
        case = next(c for c in changed['cases'] if c['id'] == 'dirty-staged-and-working')
        text = 'Extra local note.\n'
        case['working_edits'].append({
            'path': 'extra-note.txt', 'text': text,
            'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
        })
        candidates.append(('working path added', changed,
                           'dirty-staged-and-working: working_edits path inventory'))

        for label, candidate, diagnostic in candidates:
            with self.subTest(candidate=label):
                validate_catalog(candidate)
                result = owning_result(candidate)
                self.assertTrue(result.failures, label)
                self.assertTrue(any(diagnostic in traceback for _, traceback in result.failures),
                                f'{label}: expected owning guard diagnostic {diagnostic}')

    def test_zero_new_files_is_a_real_default_outcome(self):
        """Fixture preparation does not select the optional instruction pilot."""
        cases = load_catalog(CATALOG)['cases']
        expected_dispositions = {
            case_id: expected['oracle']['disposition']
            for case_id, expected in PROPOSED_FIXTURE_ONLY_ORACLE_EXPECTATIONS.items()
        }
        self.assertEqual(
            {case['id']: case['oracle']['disposition'] for case in cases},
            expected_dispositions,
        )
        for case in cases:
            with self.subTest(case=case['id']):
                expected = PROPOSED_FIXTURE_ONLY_ORACLE_EXPECTATIONS[case['id']]['oracle']
                self.assertEqual(case['oracle']['default_new_instruction_files'], 0)
                self.assertEqual(case['oracle']['default_new_instruction_files'],
                                 expected['default_new_instruction_files'])

    def test_recomputed_answer_mutations_are_rejected(self):
        """Recomputed changed answers must fail an independent oracle contract."""
        catalog = load_catalog(CATALOG)
        candidates = []

        with mock.patch(__name__ + '.load_catalog', return_value=catalog):
            self.assert_proposed_oracle_contract(catalog['cases'])

        swapped = copy.deepcopy(catalog)
        conflicting = next(case for case in swapped['cases']
                           if case['id'] == 'conflicting-command-evidence')
        partial = next(case for case in swapped['cases'] if case['id'] == 'partial-onboarding')
        conflicting['oracle']['disposition'], partial['oracle']['disposition'] = (
            partial['oracle']['disposition'], conflicting['oracle']['disposition'])
        conflicting['oracle_sha256'] = canonical_digest(conflicting['oracle'])
        partial['oracle_sha256'] = canonical_digest(partial['oracle'])
        candidates.append(('swapped dispositions', swapped))

        dropped = copy.deepcopy(catalog)
        instructed = next(case for case in dropped['cases'] if case['id'] == 'already-instructed')
        instructed['oracle']['preserve_paths'] = []
        instructed['oracle_sha256'] = canonical_digest(instructed['oracle'])
        candidates.append(('dropped preservation paths', dropped))

        changed = copy.deepcopy(catalog)
        onboarding = next(case for case in changed['cases'] if case['id'] == 'partial-onboarding')
        onboarding['oracle']['checks'][0] = 'The example sentinel proves genuine completion.'
        onboarding['oracle_sha256'] = canonical_digest(onboarding['oracle'])
        candidates.append(('changed partial-onboarding check', changed))

        for label, candidate in candidates:
            with self.subTest(candidate=label), mock.patch(
                    __name__ + '.load_catalog', return_value=candidate):
                with self.assertRaises(AssertionError):
                    self.assert_proposed_oracle_contract(candidate['cases'])


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

    def assert_fixture_placement_boundary(self, case, instance):
        """Require fixture placement and independent expected-input identity."""
        independent = PROPOSED_FIXTURE_ONLY_ORACLE_EXPECTATIONS[case['id']]
        expected_paths = set(EXPECTED_SOLVER_FILES[case['id']])
        declared = {
            item['path']: item['sha256']
            for item in case['files'] + case['staged_edits'] + case['working_edits']
        }
        expected = {path: declared[path] for path in expected_paths}
        if case['setup'] == 'sparse':
            self.assertEqual(set(declared) - expected_paths, {'other/storage.sql'})
        else:
            self.assertEqual(set(declared), expected_paths)
        expected = dict(sorted(expected.items()))
        self.assertEqual(instance['files'], expected)
        self.assertEqual(snapshot(instance['solver']), expected)

        solver = instance['solver'].resolve()
        evaluator = instance['evaluator'].resolve()
        for protected in (ROOT.resolve(), CATALOG.resolve(), Path(__file__).resolve()):
            self.assertNotEqual(solver, protected)
            self.assertFalse(solver.is_relative_to(protected))
            self.assertFalse(protected.is_relative_to(solver))
        self.assertEqual(evaluator.parent, solver.parent)
        self.assertNotEqual(evaluator, solver)
        self.assertFalse(evaluator.is_relative_to(solver))

        oracle_path = evaluator / 'oracle.json'
        expected_oracle_bytes = (
            json.dumps(independent['oracle'], sort_keys=True, indent=2) + '\n'
        ).encode()
        self.assertEqual(oracle_path.read_bytes(), expected_oracle_bytes)
        self.assertEqual(
            canonical_digest(json.loads(oracle_path.read_text(encoding='utf-8'))),
            independent['oracle_sha256'],
        )
        identity = json.loads((evaluator / 'identity.json').read_text(encoding='utf-8'))
        self.assertEqual(identity, {
            'case_id': case['id'],
            'case_sha256': canonical_digest(case),
            'task_sha256': canonical_digest(case['task']),
            'oracle_sha256': independent['oracle_sha256'],
            'fixture_snapshot_sha256': case['snapshot_sha256'],
            'setup': case['setup'],
            'worktree_files': expected,
            'evidence_kind': 'fixture-placement-only',
        })
        self.assertEqual(set(instance['task']), {'kind', 'prompt'})
        self.assertEqual(instance['task'], case['task'])
        self.assertNotIn('oracle.json', expected)
        self.assertNotIn('identity.json', expected)

    def assert_evaluator_oracle_is_unchanged(self, case, instance):
        """Require each owned mutation to leave evaluator data independent."""
        expected = PROPOSED_FIXTURE_ONLY_ORACLE_EXPECTATIONS[case['id']]
        oracle_path = instance['evaluator'] / 'oracle.json'
        self.assertEqual(
            oracle_path.read_bytes(),
            (json.dumps(expected['oracle'], sort_keys=True, indent=2) + '\n').encode(),
        )
        self.assertEqual(
            canonical_digest(json.loads(oracle_path.read_text(encoding='utf-8'))),
            expected['oracle_sha256'],
        )
        identity = json.loads((instance['evaluator'] / 'identity.json').read_text())
        self.assertEqual(identity['case_id'], case['id'])
        self.assertEqual(identity['oracle_sha256'], expected['oracle_sha256'])

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
                self.assert_fixture_placement_boundary(case, instance)

    def test_boundary_rejects_actual_solver_leaks_one_at_a_time(self):
        """Test-owned contamination is rejected by fixture-placement validation."""
        controls = (
            ('catalog bytes', 'leaked-catalog.bin', CATALOG.read_bytes(), False,
             'tiny-python'),
            ('framework test bytes', 'leaked-test-module.bin', Path(__file__).read_bytes(),
             False, 'tiny-python'),
            ('ignored oracle bytes', 'cache/leaked-oracle.json', None, False,
             'ignored-inputs'),
            ('existing path oracle append', 'README.md', None, True, 'tiny-python'),
        )
        for index, (label, relative, payload, append, case_id) in enumerate(controls):
            with self.subTest(control=label):
                case = next(case for case in self.catalog['cases'] if case['id'] == case_id)
                instance = materialize(self.catalog, case_id,
                                       self.root / f'negative-{index}-{case_id}')
                if payload is None:
                    payload = (instance['evaluator'] / 'oracle.json').read_bytes()
                target = instance['solver'] / relative
                if append:
                    target.write_bytes(target.read_bytes() + payload)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(payload)
                with self.assertRaises(AssertionError):
                    self.assert_fixture_placement_boundary(case, instance)
                self.assert_evaluator_oracle_is_unchanged(case, instance)

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


class TestSolvableFixFixture(unittest.TestCase):
    """Qualify the synthetic problem itself, not any solving actor's work."""

    def shortDescription(self):
        return None

    def test_fix_fixture_has_a_discriminating_existing_regression(self):
        catalog = load_catalog(ROOT / '.github/fixtures/context-onboarding/solvable-fix.json')
        self.assertEqual(len(catalog['cases']), 1)
        case = catalog['cases'][0]
        self.assertEqual(case['id'], 'falsy-override-fix')
        self.assertEqual(case['task']['kind'], 'fix')
        self.assertEqual(canonical_digest(case),
                         '866a9ce336cb45479f29a207a409835922cdf320b0c629cd20e5199b5224a871')
        self.assertEqual(case['oracle_sha256'],
                         '8ff26d48eb22214556213fc4bd3fd0fc99a3145d84e7a31eec675b989b4f3369')
        self.assertEqual(case['snapshot_sha256'],
                         '1d2e70e92a8fa90b7c1d85118c9b4c5b359dae6387bada53f7fb16ff72ba74a9')
        with tempfile.TemporaryDirectory(prefix='ca-context-fix-problem-') as temp:
            instance = materialize(catalog, case['id'], Path(temp).resolve() / 'case')
            solver = instance['solver']
            original = snapshot(solver)
            argv = [str(Path(sys.executable).resolve()), '-B', '-m', 'unittest',
                    'discover', '-s', 'tests', '-v']
            baseline = subprocess.run(argv, cwd=solver, capture_output=True,
                                      text=True, timeout=20)
            self.assertEqual(baseline.returncode, 1, baseline.stdout + baseline.stderr)
            self.assertIn('test_false_override (test_app.ChoiceTest.test_false_override) ... FAIL',
                          baseline.stderr)
            self.assertIn('Ran 3 tests', baseline.stderr)
            self.assertIn('FAILED (failures=1)', baseline.stderr)
            self.assertEqual(snapshot(solver), original)
            # This is the fixture author's reference control in a disposable
            # repository, not a product edit or an observed model contribution.
            application = solver / 'app.py'
            application.write_text(
                'def choose_value(key, overrides, defaults):\n'
                '    return overrides[key] if key in overrides else defaults.get(key)\n',
                encoding='utf-8', newline='\n')
            green = subprocess.run(argv, cwd=solver, capture_output=True,
                                   text=True, timeout=20)
            self.assertEqual(green.returncode, 0, green.stdout + green.stderr)
            self.assertIn('Ran 3 tests', green.stderr)
            self.assertIn('test_false_override (test_app.ChoiceTest.test_false_override) ... ok',
                          green.stderr)
            reference_checks = (
                'from app import choose_value\n'
                'for value in (False, 0, "", None):\n'
                '    overrides = {"key": value, "other": 12}\n'
                '    defaults = {"key": "fallback", "other": 13}\n'
                '    assert choose_value("key", overrides, defaults) is value\n'
                '    assert overrides == {"key": value, "other": 12}\n'
                '    assert defaults == {"key": "fallback", "other": 13}\n'
                'assert choose_value("key", {}, {"key": "fallback"}) == "fallback"\n'
                'assert choose_value("missing", {}, {}) is None\n'
            )
            control = subprocess.run([argv[0], '-B', '-c', reference_checks],
                                     cwd=solver, capture_output=True, text=True, timeout=20)
            self.assertEqual(control.returncode, 0, control.stdout + control.stderr)
            self.assertEqual({path for path in original
                              if snapshot(solver)[path] != original[path]}, {'app.py'})
            self.assertFalse((solver / 'oracle.json').exists())
            self.assertNotIn('checks', instance['task'])


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
