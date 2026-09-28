#!/usr/bin/env python3
"""Scoped, inert consumers of brownfield command evidence."""

import copy
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'core' / 'pysrc'))
import _contextreportlib as reports
import _contextselectlib as selector
import _artifactpromptlib as actor_prompts


class TestScopedCommandEvidence(unittest.TestCase):
    def shortDescription(self):
        return None

    @staticmethod
    def command(command_id, cwd, source):
        return {
            'id': command_id,
            'invocation': {'kind': 'literal_argv', 'argv': ['python', '-m', 'unittest']},
            'cwd': cwd, 'prerequisites': ['python-3.14'],
            'evidence_refs': [source],
            'verification': {'state': 'declared', 'observation_ref': None,
                             'binding': None},
        }

    @staticmethod
    def binding(cwd):
        return {
            'source_snapshot_id': 'a' * 64, 'runtime_ref': 'python-3.14',
            'lock_digest': 'b' * 64, 'prerequisites_digest': 'c' * 64,
            'oracle_ref': 'sha256:3a9c0d2e73603a7ca18e76768a19a2c73e7296a853b64e0a869b4d649001bffb',
            'argv': ['python', '-m', 'unittest'],
            'cwd': cwd, 'declared_prerequisites': ['python-3.14'],
            'environment_digest': 'd' * 64,
        }

    @staticmethod
    def observation(cwd):
        return {
            'id': 'RUN-A', 'authorized': True, 'binding': TestScopedCommandEvidence.binding(cwd),
            'source': {'path': cwd + '/package.json',
                       'digest': 'f' * 64 if cwd == 'packages/b' else 'e' * 64},
            'exit': 0, 'collector': 'python-unittest-text/0.1.0',
            'required_tests': ['test_selected'],
            'tests': [{'name': 'test_selected', 'status': 'pass'}],
        }

    def test_t032_scoped_command_evidence_positive_controls(self):
        """Equal command texts retain package identity and real observed outcomes."""
        a = self.command('CMD-A', 'packages/a', 'EA')
        b = self.command('CMD-B', 'packages/b', 'EB')
        entries = [(a, {'EA': {'path': 'packages/a/package.json', 'digest': 'e' * 64}}),
                   (b, {'EB': {'path': 'packages/b/package.json', 'digest': 'f' * 64}})]
        original = copy.deepcopy(entries)
        selected = reports.resolve_scoped_command_guidance(
            entries, command_id='CMD-B', cwd='packages/b',
            current_binding=self.binding('packages/b'),
            observation=self.observation('packages/b'))
        self.assertEqual(entries, original)
        self.assertEqual(selected['id'], 'CMD-B')
        self.assertEqual(selected['source']['path'], 'packages/b/package.json')
        self.assertEqual(selected['cwd'], 'packages/b')
        self.assertEqual(selected['prerequisites'], ['python-3.14'])
        self.assertEqual(selected['reported_current_state'], 'passed')
        self.assertEqual(selected['observation']['tests'],
                         [{'name': 'test_selected', 'status': 'pass'}])
        declaration = self.command('CMD-SHELL', 'packages/a', 'EA')
        declaration['invocation'] = {'kind': 'declaration_ref',
                                     'path': 'packages/a/package.json',
                                     'selector': 'scripts.test',
                                     'text': 'NODE_ENV=ci npm test | tee result.log'}
        selected = reports.resolve_scoped_command_guidance(
            [(declaration, entries[0][1])], command_id='CMD-SHELL', cwd='packages/a',
            current_binding=None, observation=None)
        self.assertEqual(selected['invocation']['kind'], 'declaration_ref')
        self.assertEqual(selected['reported_current_state'], 'declared')
        build = self.command('CMD-BUILD', 'packages/a', 'EA')
        build['invocation']['argv'] = ['python', '-m', 'compileall', 'src']
        build_binding = self.binding('packages/a')
        build_binding['argv'] = list(build['invocation']['argv'])
        build_binding['oracle_ref'] = 'exit-only/0.1.0'
        observed = self.observation('packages/a')
        observed['binding'] = copy.deepcopy(build_binding)
        observed['collector'] = 'exit-only/0.1.0'
        observed['required_tests'] = []
        observed['tests'] = []
        built = reports.resolve_scoped_command_guidance(
            [(build, entries[0][1])], command_id='CMD-BUILD', cwd='packages/a',
            current_binding=build_binding, observation=observed)
        self.assertEqual(built['reported_current_state'], 'passed')

    def test_t032_scoped_command_evidence_negative_controls(self):
        """Stale, unobserved, empty and failed runs cannot confer verification."""
        command = self.command('CMD-A', 'packages/a', 'EA')
        entries = [(command, {'EA': {'path': 'packages/a/package.json',
                                     'digest': 'e' * 64}})]
        kwargs = {'command_id': 'CMD-A', 'cwd': 'packages/a',
                  'current_binding': self.binding('packages/a')}
        for mutation in ('lock_digest', 'runtime_ref', 'source_snapshot_id',
                         'prerequisites_digest', 'environment_digest'):
            observed = self.observation('packages/a')
            observed['binding'][mutation] = ('f' * 64 if mutation != 'runtime_ref'
                                              else 'python-3.13')
            with self.subTest(stale=mutation):
                result = reports.resolve_scoped_command_guidance(
                    entries, **kwargs, observation=observed)
                self.assertEqual(result['reported_current_state'], 'unknown')
        for change in ({'tests': []}, {'tests': [{'name': 'other', 'status': 'pass'}]},
                       {'required_tests': ['other'],
                        'tests': [{'name': 'other', 'status': 'pass'}]},
                       {'tests': [{'name': 'test_selected', 'status': 'skip'}]},
                       {'exit': 1}, {'authorized': False},
                       {'collector': 'exit-only/0.1.0'},
                       {'source': {'path': 'packages/a/package.json', 'digest': 'f' * 64}},
                       {'source': {'path': 'packages/b/package.json', 'digest': 'e' * 64}},
                       {'tests': [{'name': 'test_selected', 'status': 'pass'},
                                  {'name': 'test_selected', 'status': 'pass'}]}):
            with self.subTest(change=change):
                observed = {**self.observation('packages/a'), **change}
                result = reports.resolve_scoped_command_guidance(
                    entries, **kwargs, observation=observed)
                self.assertNotEqual(result['reported_current_state'], 'passed')
        self.assertEqual(reports.resolve_scoped_command_guidance(
            entries, **kwargs, observation=None)['reported_current_state'], 'declared')
        historical = copy.deepcopy(command)
        historical['verification'] = {
            'state': 'passed', 'observation_ref': 'RUN-OLD',
            'binding': self.binding('packages/a'),
        }
        self.assertEqual(reports.resolve_scoped_command_guidance(
            [(historical, entries[0][1])], **kwargs,
            observation=None)['reported_current_state'], 'unknown')
        for bad_entries, wanted in ((entries, {'command_id': 'CMD-A', 'cwd': 'packages/b'}),
                                    ([(command, {'EA': {'path': 'packages/b/package.json',
                                                        'digest': 'e' * 64}})], {}),
                                    (entries + entries, {})):
            with self.subTest(wanted=wanted), self.assertRaises(reports.ReportError):
                reports.resolve_scoped_command_guidance(
                    bad_entries, **{**kwargs, **wanted}, observation=None)


class TestTaskContextSelection(unittest.TestCase):
    def shortDescription(self):
        return None

    def select(self, paths, **changes):
        commands, constraints, code_map = self.fixture()
        inputs = dict(code_map=code_map, provenance={}, commands=commands,
                      constraints=constraints, effective_instructions=[],
                      evidence_ids={'E1', 'E2', 'E3'})
        return selector.select_task_context(paths, **{**inputs, **changes})

    def test_package_prefix_does_not_select_a_sibling_owner(self):
        packet = self.select(['packages/beta/src/main.py'])
        self.assertEqual(packet['commands'], [])
        self.assertEqual(packet['map'], [])
        self.assertEqual([item['id'] for item in packet['constraints']], ['RULE-ROOT'])
        self.assertEqual(packet['admission'], 'requires_actor_check')

    def test_directory_task_selects_all_descendant_owners(self):
        packet = self.select(['packages'])
        self.assertEqual([item['id'] for item in packet['commands']],
                         ['CMD-A', 'CMD-B', 'CMD-C'])
        self.assertEqual([item['id'] for item in packet['constraints']],
                         ['RULE-ROOT', 'RULE-B', 'RULE-C'])
        self.assertEqual(len(packet['map']), 4)

    def test_duplicate_command_is_collapsed_but_conflicting_source_is_rejected(self):
        commands, _, _ = self.fixture()
        duplicate = copy.deepcopy(commands[1])
        packet = self.select(['packages/b'], commands=[commands[1], duplicate])
        self.assertEqual([item['id'] for item in packet['commands']], ['CMD-B'])
        duplicate[1]['EB']['digest'] = 'f' * 64
        with self.assertRaisesRegex(selector.SelectionError, '^CONFLICTING_COMMAND$'):
            self.select(['packages/b'], commands=[commands[1], duplicate])

    def test_instruction_packet_byte_boundary_preserves_source_references(self):
        instructions = [
            {'id': f'I{i}', 'path': f'rules/{i}.md', 'scope': '.',
             'epoch': 'g1', 'text': 'é' * 4096} for i in range(3)]
        original = copy.deepcopy(instructions)
        exact = self.select(['packages/b'], effective_instructions=instructions)
        self.assertEqual(exact['instructions'], instructions)
        self.assertEqual(exact['unresolved'], [])
        instructions.append({'id': 'I3', 'path': 'rules/3.md', 'scope': '.',
                             'epoch': 'g1', 'text': 'x'})
        bounded = self.select(['packages/b'], effective_instructions=instructions)
        self.assertEqual(bounded['instructions'],
                         [{**item, 'text': None} for item in instructions])
        self.assertEqual(bounded['unresolved'], [{'code': 'INSTRUCTION_PACKET_OVERSIZE'}])
        self.assertEqual(instructions[:3], original)

    def test_single_instruction_limit_counts_utf8_bytes(self):
        instruction = {'id': 'ROOT', 'path': 'AGENTS.md', 'scope': '.',
                       'epoch': 'g1', 'text': 'é' * 4096}
        self.assertEqual(self.select(['.'], effective_instructions=[instruction])[
            'instructions'], [instruction])
        instruction['text'] += 'x'
        with self.assertRaisesRegex(selector.SelectionError, '^INVALID_INSTRUCTION$'):
            self.select(['.'], effective_instructions=[instruction])

    def test_duplicate_instructions_keep_host_order_and_report_conflicts(self):
        local = {'id': 'LOCAL', 'path': 'packages/b/AGENTS.md', 'scope': 'packages/b',
                 'epoch': 'g1', 'text': 'Local rule'}
        root = {'id': 'ROOT', 'path': 'AGENTS.md', 'scope': '.',
                'epoch': 'g1', 'text': 'Root rule'}
        packet = self.select(['packages/b'], effective_instructions=[
            local, root, copy.deepcopy(local), {**local, 'text': 'Conflicting rule'}])
        self.assertEqual(packet['instructions'], [local, root])
        self.assertEqual(packet['unresolved'],
                         [{'code': 'CONFLICTING_INSTRUCTION', 'id': 'LOCAL'}])

    def test_task_path_count_boundary(self):
        paths = [f'packages/b/file{i}.py' for i in range(32)]
        self.assertEqual(self.select(paths)['task_paths'], paths)
        for invalid in ([], paths + ['packages/b/extra.py'], 'packages/b'):
            with self.subTest(paths=invalid):
                with self.assertRaisesRegex(selector.SelectionError, '^INVALID_TASK_PATHS$'):
                    self.select(invalid)

    @staticmethod
    def fixture():
        commands = []
        for package, source_id in (('a', 'EA'), ('b', 'EB'), ('c', 'EC')):
            cwd = 'packages/' + package
            command = TestScopedCommandEvidence.command('CMD-' + package.upper(), cwd, source_id)
            commands.append((command, {source_id: {'path': cwd + '/package.json',
                                                  'digest': package.encode().hex().ljust(64, '0')}}))
        constraints = [
            {'record': {'id': 'RULE-ROOT', 'kind': 'existing_applicable', 'source_ref': 'AGENTS.md',
                        'scope': '.', 'statement': 'Keep user files', 'evidence_refs': ['E1']},
             'owner': 'root', 'authority': 'native', 'epoch': 'g1', 'status': 'current'},
            {'record': {'id': 'RULE-B', 'kind': 'existing_applicable', 'source_ref': 'packages/b/AGENTS.md',
                        'scope': 'packages/b', 'statement': 'Check package B', 'evidence_refs': ['E2']},
             'owner': 'packages/b', 'authority': 'native', 'epoch': 'g1', 'status': 'current'},
            {'record': {'id': 'RULE-C', 'kind': 'existing_applicable', 'source_ref': 'packages/c/AGENTS.md',
                        'scope': 'packages/c', 'statement': 'Check package C', 'evidence_refs': ['E3']},
             'owner': 'packages/c', 'authority': 'native', 'epoch': 'g1', 'status': 'current'},
        ]
        map_text = ('## Work\n- `packages/a/src` -- source for A\n'
                    '- `packages/b/src` -- source for B\n'
                    '- `packages/b/dist` -- generated from packages/b/src\n'
                    '- `packages/c/src` -- source for C\n')
        return commands, constraints, map_text

    def test_t034_task_context_selection_positive_controls(self):
        """Union two owners, preserve command cwd and generated ownership."""
        commands, constraints, map_text = self.fixture()
        original = copy.deepcopy((commands, constraints, map_text))
        packet = selector.select_task_context(
            ['packages/a/src/main.py', 'packages/b/dist/main.js'],
            code_map=map_text,
            provenance={'documents': {'code-map': 'v2_current',
                                      'tech-stack': 'v2_current'}},
            commands=commands, constraints=constraints,
            effective_instructions=[{'id': 'ROOT', 'path': 'AGENTS.md', 'scope': '.',
                                     'epoch': 'g1', 'text': 'Root instruction'},
                                    {'id': 'B', 'path': 'packages/b/AGENTS.md',
                                     'scope': 'packages/b', 'epoch': 'g1',
                                     'text': 'B instruction'}],
            evidence_ids={'E1', 'E2', 'E3'})
        self.assertEqual((commands, constraints, map_text), original)
        self.assertEqual([(c['id'], c['cwd']) for c in packet['commands']],
                         [('CMD-A', 'packages/a'), ('CMD-B', 'packages/b')])
        self.assertTrue(all(c['reported_current_state'] == 'declared'
                            for c in packet['commands']))
        self.assertEqual([r['path'] for r in packet['map']],
                         ['packages/a/src', 'packages/b/src', 'packages/b/dist'])
        self.assertEqual([r['id'] for r in packet['constraints']], ['RULE-ROOT', 'RULE-B'])
        self.assertEqual([r['id'] for r in packet['instructions']], ['ROOT', 'B'])
        self.assertEqual(packet['unresolved'], [])
        self.assertEqual(packet['admission'], 'requires_actor_check')

    def test_t034_task_context_selection_negative_controls(self):
        """Unknown, conflicting, and irrelevant context never becomes authority."""
        commands, constraints, map_text = self.fixture()
        constraints.append(copy.deepcopy(constraints[1]))
        constraints.append({**copy.deepcopy(constraints[1]), 'epoch': 'g2',
                            'status': 'unresolved'})
        packet = selector.select_task_context(
            ['packages/b/src/main.py'], code_map=map_text,
            provenance={'documents': {'code-map': 'v2_stale'}},
            commands=commands, constraints=constraints,
            effective_instructions=[], evidence_ids={'E1', 'E2', 'E3'})
        self.assertEqual(len(packet['constraints']), 3)  # root + two epochs
        self.assertEqual([(c['id'], c['cwd']) for c in packet['commands']],
                         [('CMD-B', 'packages/b')])
        self.assertIn('RULE-B', [r.get('id') for r in packet['unresolved']])
        self.assertEqual(packet['provenance']['documents']['code-map'], 'v2_stale')
        self.assertIn({'code': 'PROVENANCE_STALE', 'document': 'code-map'},
                      packet['unresolved'])
        self.assertNotIn('packages/c/src', [r['path'] for r in packet['map']])
        conflicting = copy.deepcopy(constraints[:4])
        conflicting[3]['epoch'] = 'g1'
        conflicting[3]['status'] = 'current'
        conflicting[3]['record']['statement'] = 'Opposite package B rule'
        clash = selector.select_task_context(
            ['packages/b/src/main.py'], code_map=map_text, provenance={},
            commands=commands, constraints=conflicting,
            effective_instructions=[], evidence_ids={'E1', 'E2', 'E3'})
        self.assertEqual([r['status'] for r in clash['unresolved']], ['conflict'])
        mixed = selector.select_task_context(
            ['packages/b/src/main.py'], code_map=None, provenance={},
            commands=[], constraints=[], evidence_ids=set(),
            effective_instructions=[{'id': 'ROOT', 'path': 'AGENTS.md',
                                     'scope': '.', 'epoch': 'g1', 'text': 'Root'},
                                    {'id': 'B', 'path': 'packages/b/AGENTS.md',
                                     'scope': 'packages/b', 'epoch': 'g2', 'text': 'Local'}])
        self.assertEqual(mixed['map_diagnostics'], ['code map unavailable'])
        self.assertIn({'code': 'MIXED_INSTRUCTION_EPOCH'}, mixed['unresolved'])
        huge_map = '## Work\n' + ''.join(
            f'- `packages/b/src/p{i}` -- role {i}\n' for i in range(1000))
        bounded = selector.select_task_context(
            ['packages/b/src'], code_map=huge_map,
            provenance={'documents': {'code-map': 'v2_current'},
                        'unchecked_payload': 'x' * 200000},
            commands=[], constraints=[], effective_instructions=[],
            evidence_ids=set())
        self.assertEqual(bounded['map'], [])
        self.assertFalse(bounded['map_complete'])
        self.assertIn('code map selection exceeds packet cap', bounded['map_diagnostics'])
        self.assertNotIn('unchecked_payload', bounded['provenance'])
        oversized_instructions = [
            {'id': f'I{i}', 'path': f'packages/b/i{i}.md', 'scope': 'packages/b',
             'epoch': 'g1', 'text': 'x' * 8000} for i in range(8)]
        bounded = selector.select_task_context(
            ['packages/b/src'], code_map=None, provenance={}, commands=[],
            constraints=[], effective_instructions=oversized_instructions,
            evidence_ids=set())
        self.assertIn({'code': 'INSTRUCTION_PACKET_OVERSIZE'}, bounded['unresolved'])
        self.assertTrue(all(item['text'] is None for item in bounded['instructions']))
        self.assertEqual(len(bounded['instructions']), 8)
        pending = selector.select_task_context(
            ['packages/b/src'], code_map=None,
            provenance={'documents': {'tech-stack': 'first_input_pending',
                                      'code-map': 'oversize'}}, commands=[],
            constraints=[], effective_instructions=[], evidence_ids=set())
        self.assertEqual(pending['provenance']['documents'],
                         {'tech-stack': 'first_input_pending', 'code-map': 'oversize'})
        self.assertEqual([r['code'] for r in pending['unresolved']],
                         ['PROVENANCE_UNCHECKED', 'PROVENANCE_UNCHECKED'])
        with self.assertRaises(selector.SelectionError):
            selector.select_task_context(['../outside'], code_map=map_text,
                                         provenance={}, commands=[], constraints=[],
                                         effective_instructions=[], evidence_ids=set())
        with self.assertRaises(selector.SelectionError):
            selector.select_task_context(['packages/b/src'], code_map=map_text,
                                         provenance={}, commands=[{'id': 'BAD'}],
                                         constraints=[], effective_instructions=[],
                                         evidence_ids=set())


class TestActorDeliveryReceipts(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.packet = selector.select_task_context(**TestFeatureActorContext.inputs())
        self.args = dict(actor='backend-author', task_id='T-1', worktree=root.name,
                         source_epoch='source-1', host_epoch='host-1')

    def test_receipt_after_retry_exhaustion_records_observation(self):
        first = selector.prepare_actor_delivery(self.packet, **self.args)
        second = selector.prepare_actor_delivery(
            self.packet, **self.args, attempts=[first['attempt']])
        attempts = [first['attempt'], second['attempt']]
        blocked = selector.prepare_actor_delivery(self.packet, **self.args, attempts=attempts)
        self.assertEqual(blocked['action'], 'blocked')
        self.assertEqual(blocked['gap'], 'ACTOR_DELIVERY_UNOBSERVED')
        for source in ('host-load-event', 'child-input-capture'):
            with self.subTest(source=source):
                receipt = dict(binding=first['binding'], actor=self.args['actor'],
                               observed=True, source=source)
                observed = selector.prepare_actor_delivery(
                    self.packet, **self.args, attempts=attempts, receipt=receipt)
                self.assertEqual(observed['action'], 'observed')
                self.assertEqual(observed['attempts_used'], 2)
                self.assertIsNone(observed['attempt'])
                self.assertIsNone(observed['delivery_text'])

    def test_receipt_requires_boolean_observation_and_known_source(self):
        first = selector.prepare_actor_delivery(self.packet, **self.args)
        receipt = dict(binding=first['binding'], actor=self.args['actor'],
                       observed=True, source='host-load-event')
        for changes in ({'observed': 1}, {'observed': 'true'}, {'observed': False},
                        {'source': 'actor-assertion'}, {'actor': 'spec-reviewer'}):
            with self.subTest(changes=changes):
                result = selector.prepare_actor_delivery(
                    self.packet, **self.args, attempts=[first['attempt']],
                    receipt={**receipt, **changes})
                self.assertEqual(result['action'], 'deliver')
                self.assertEqual(result['attempt']['number'], 2)

    def test_packet_content_change_invalidates_receipt_without_changing_epochs(self):
        first = selector.prepare_actor_delivery(self.packet, **self.args)
        receipt = dict(binding=first['binding'], actor=self.args['actor'],
                       observed=True, source='host-load-event')
        packet = copy.deepcopy(self.packet)
        packet['instructions'][0]['text'] = 'Updated root instruction'
        result = selector.prepare_actor_delivery(
            packet, **self.args, attempts=[first['attempt']], receipt=receipt)
        self.assertEqual(result['action'], 'deliver')
        self.assertEqual(result['attempt']['number'], 1)
        self.assertNotEqual(result['binding']['packet_sha256'], first['binding']['packet_sha256'])
        self.assertIn('Updated root instruction', result['delivery_text'])
        self.assertEqual(self.packet['instructions'][0]['text'], 'Root instruction')


class TestFeatureActorContext(unittest.TestCase):
    def shortDescription(self):
        return None

    @staticmethod
    def inputs(*, code_map=None, constraints=None):
        commands, defaults, default_map = TestTaskContextSelection.fixture()
        return {
            'task_paths': ['packages/a/src/main.py', 'packages/b/dist/main.js'],
            'code_map': default_map if code_map is None else code_map,
            'provenance': {'documents': {'code-map': 'v2_current',
                                         'tech-stack': 'v2_current'}},
            'commands': commands,
            'constraints': defaults if constraints is None else constraints,
            'effective_instructions': [
                {'id': 'ROOT', 'path': 'AGENTS.md', 'scope': '.',
                 'epoch': 'g1', 'text': 'Root instruction'},
                {'id': 'B', 'path': 'packages/b/AGENTS.md',
                 'scope': 'packages/b', 'epoch': 'g1', 'text': 'B instruction'}],
            'evidence_ids': {'E1', 'E2', 'E3'},
        }

    def test_t035_feature_actor_context_positive_controls(self):
        """Fresh author and reviewer inputs each carry the scoped packet."""
        inputs = self.inputs()
        before = copy.deepcopy(inputs)
        for actor in ('backend-author', 'spec-reviewer'):
            with self.subTest(actor=actor):
                child = actor_prompts.compose_feature_actor_input(
                    actor=actor, brief='Implement or inspect T-035',
                    spec_id='SPEC-BROWNFIELD', plan_id='PLAN-BROWNFIELD',
                    task_id='T-035', **inputs)
                self.assertEqual(child['actor'], actor)
                self.assertEqual(child['task_id'], 'T-035')
                self.assertEqual(child['spec_id'], 'SPEC-BROWNFIELD')
                self.assertEqual(child['plan_id'], 'PLAN-BROWNFIELD')
                self.assertEqual([(c['id'], c['cwd']) for c in child['packet']['commands']],
                                 [('CMD-A', 'packages/a'), ('CMD-B', 'packages/b')])
                self.assertEqual([r['path'] for r in child['packet']['map']],
                                 ['packages/a/src', 'packages/b/src',
                                  'packages/b/dist'])
                self.assertIn('"id":"RULE-B"', child['input'])
                self.assertIn('"cwd":"packages/a"', child['input'])
                self.assertIn('"cwd":"packages/b"', child['input'])
                self.assertIn('"spec_id":"SPEC-BROWNFIELD"', child['input'])
                self.assertIn('"plan_id":"PLAN-BROWNFIELD"', child['input'])
                self.assertIn('"actor":"' + actor + '"', child['input'])
                self.assertIn('requires_actor_check', child['input'])
        self.assertEqual(inputs, before)
        mini = actor_prompts.compose_feature_actor_input(
            actor='frontend-author', brief='Implement the confirmed small feature',
            spec_id=None, plan_id=None, task_id='SMALL-FEATURE',
            confirmed_mini_spec='Render the requested control', **inputs)
        self.assertIn('"confirmed_mini_spec":"Render the requested control"',
                      mini['input'])
        self.assertIn('"plan_id":null', mini['input'])

    def test_t035_feature_actor_context_negative_controls(self):
        """Unresolved constraints remain visible and stop material action."""
        core = str(Path(__file__).resolve().parents[2] / 'core' / 'pysrc')
        probe = (
            'import sys; sys.path.insert(0, ' + repr(core) + '); '
            'import _artifactpromptlib; '
            'eager = sorted(name for name in '
            '("_contextselectlib", "_provenancelib", "_hooklib", "hostapi") '
            'if name in sys.modules); '
            'print(eager); raise SystemExit(bool(eager))')
        isolated = subprocess.run([sys.executable, '-I', '-c', probe],
                                  capture_output=True, text=True, check=False)
        self.assertEqual(isolated.returncode, 0, isolated.stdout + isolated.stderr)
        inputs = self.inputs()
        inputs['constraints'][1]['status'] = 'conflict'
        child = actor_prompts.compose_feature_actor_input(
            actor='backend-author', brief='Implement T-035',
            spec_id='SPEC-BROWNFIELD', plan_id='PLAN-BROWNFIELD',
            task_id='T-035', **inputs)
        self.assertEqual(child['action'], 'blocked')
        self.assertIn('"status":"conflict"', child['input'])
        self.assertIn('Do not mutate, execute discovered commands, or issue a substantive verdict',
                      child['input'])
        inputs['constraints'][1]['status'] = 'current'
        inputs['code_map'] = None
        reviewer = actor_prompts.compose_feature_actor_input(
            actor='spec-reviewer', brief='Inspect T-035',
            spec_id='SPEC-BROWNFIELD', plan_id='PLAN-BROWNFIELD',
            task_id='T-035', **inputs)
        self.assertEqual(reviewer['action'], 'requires_actor_check')
        self.assertIn('code map unavailable', reviewer['input'])
        self.assertIn('bounded read-only source inspection', reviewer['input'])
        inputs['provenance']['identity'] = 'stale'
        stale = actor_prompts.compose_feature_actor_input(
            actor='spec-reviewer', brief='Inspect T-035',
            spec_id='SPEC-BROWNFIELD', plan_id='PLAN-BROWNFIELD',
            task_id='T-035', **inputs)
        self.assertEqual(stale['action'], 'blocked')
        for bad in ({'actor': 'unknown'}, {'task_id': ''}, {'brief': ''}):
            with self.subTest(bad=bad), self.assertRaises(actor_prompts.PromptRouteError):
                actor_prompts.compose_feature_actor_input(
                    **{**{'actor': 'backend-author', 'brief': 'Implement T-035',
                          'spec_id': 'SPEC-BROWNFIELD', 'plan_id': 'PLAN-BROWNFIELD',
                          'task_id': 'T-035'}, **bad}, **inputs)


class TestReviewContextPreservation(unittest.TestCase):
    def shortDescription(self):
        return None

    @staticmethod
    def packet(*, status='current', provenance_status='v2_current'):
        commands, constraints, map_text = TestTaskContextSelection.fixture()
        constraints[1]['status'] = status
        return selector.select_task_context(
            ['packages/b/src/main.py'], code_map=map_text,
            provenance={'documents': {'code-map': provenance_status}},
            commands=commands, constraints=constraints,
            effective_instructions=[
                {'id': 'ROOT', 'path': 'AGENTS.md', 'scope': '.',
                 'epoch': 'g1', 'text': 'Preserve user files'},
                {'id': 'B', 'path': 'packages/b/AGENTS.md',
                 'scope': 'packages/b', 'epoch': 'g1',
                 'text': 'Review package B carefully'}],
            evidence_ids={'E1', 'E2', 'E3'})

    @staticmethod
    def snapshot(root):
        return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in root.rglob('*') if path.is_file()}

    def test_t037_review_context_preservation_positive_controls(self):
        """Reviewer input retains applicable owners and review leaves all files intact."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tracked.txt').write_bytes(b'tracked user state\r\n')
            (root / 'untracked.txt').write_bytes(b'untracked user state\x00')
            before = self.snapshot(root)
            packet = self.packet()
            source = copy.deepcopy(packet)
            result = selector.prepare_review_input(
                packet, reviewer='security-reviewer',
                required_refs=['constraint:packages/b/AGENTS.md',
                               'instruction:AGENTS.md',
                               'instruction:packages/b/AGENTS.md',
                               'map:packages/b/src',
                               'command:packages/b:CMD-B'])
            self.assertEqual(packet, source)
            self.assertEqual(self.snapshot(root), before)
            self.assertEqual(result['orientation'], 'read_only')
            self.assertEqual(result['verdict_admission'], 'ready')
            self.assertEqual(result['missing_refs'], [])
            context = result['reviewer_input']['context']
            self.assertEqual(result['reviewer_input']['reviewer'], 'security-reviewer')
            self.assertEqual([r['source_ref'] for r in context['constraints']],
                             ['AGENTS.md', 'packages/b/AGENTS.md'])
            self.assertEqual([r['path'] for r in context['instructions']],
                             ['AGENTS.md', 'packages/b/AGENTS.md'])
            self.assertEqual([(c['id'], c['cwd']) for c in context['commands']],
                             [('CMD-B', 'packages/b')])
            self.assertEqual(context['task_paths'], ['packages/b/src/main.py'])
            self.assertEqual([row['path'] for row in context['map']],
                             ['packages/b/src'])
            route = (Path(__file__).resolve().parents[2] /
                     'core/surface/commands/review.md').read_text(encoding='utf-8')
            self.assertIn('prepare_review_input', route)
            self.assertIn('before any substantive verdict',
                          ' '.join(route.lower().split()))
            self.assertIn('bounded read-only', route)

    def test_t037_review_context_preservation_negative_controls(self):
        """Missing critical context blocks verdict, while inspection stays open."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tracked.txt').write_bytes(b'existing source')
            (root / 'untracked.txt').write_bytes(b'user scratch')
            before = self.snapshot(root)
            packet = self.packet()
            result = selector.prepare_review_input(
                packet, reviewer='coverage-auditor',
                required_refs=['instruction:missing/AGENTS.md'])
            self.assertEqual(result['orientation'], 'read_only')
            self.assertEqual(result['verdict_admission'], 'blocked')
            self.assertEqual(result['missing_refs'],
                             ['instruction:missing/AGENTS.md'])
            self.assertIsNone(result['reviewer_input'])
            conflict = selector.prepare_review_input(
                self.packet(status='conflict'), reviewer='coverage-auditor',
                required_refs=['constraint:packages/b/AGENTS.md'])
            self.assertEqual(conflict['verdict_admission'], 'blocked')
            self.assertIn('UNRESOLVED_CONSTRAINT', conflict['blockers'])
            advisory = selector.prepare_review_input(
                self.packet(provenance_status='v2_stale'),
                reviewer='coverage-auditor', required_refs=[])
            self.assertEqual(advisory['verdict_admission'], 'ready')
            self.assertIn({'code': 'PROVENANCE_STALE', 'document': 'code-map'},
                          advisory['reviewer_input']['context']['unresolved'])
            oversized = copy.deepcopy(packet)
            oversized['instructions'][0]['text'] = None
            oversized['unresolved'].append({'code': 'INSTRUCTION_PACKET_OVERSIZE'})
            oversize_result = selector.prepare_review_input(
                oversized, reviewer='coverage-auditor', required_refs=[])
            self.assertEqual(oversize_result['verdict_admission'], 'blocked')
            self.assertIn('INSTRUCTION_PACKET_OVERSIZE',
                          oversize_result['blockers'])
            self.assertEqual(self.snapshot(root), before)
            with self.assertRaises(selector.SelectionError):
                selector.prepare_review_input(packet, reviewer='', required_refs=[])


class TestFixAndTestContext(unittest.TestCase):
    def shortDescription(self):
        return None

    @staticmethod
    def inputs():
        inputs = TestFeatureActorContext.inputs()
        commands = copy.deepcopy(inputs['commands'])
        commands[1][1]['EB']['digest'] = 'f' * 64
        inputs['commands'] = commands
        inputs['command_bindings'] = {
            ('CMD-B', 'packages/b'): TestScopedCommandEvidence.binding('packages/b')}
        inputs['observations'] = {
            ('CMD-B', 'packages/b'): TestScopedCommandEvidence.observation('packages/b')}
        return inputs

    @staticmethod
    def origin():
        return {
            'observed': 'Package B rejects the valid case',
            'expected': 'Package B accepts the valid case',
            'reproduction': 'python -m unittest test_valid_case, cwd packages/b',
            'evidence': 'debug trace RUN-42 identifies the failing branch',
            'regression_test': 'test_valid_case reproduces RUN-42 before the fix',
        }

    def test_t036_fix_and_test_context_positive_controls(self):
        """Fix and test actors receive exact scoped evidence in their own input."""
        inputs = self.inputs()
        before = copy.deepcopy(inputs)
        fixed = selector.compose_fix_or_test_actor_input(
            route='fix', caller='fix', actor='backend-author',
            brief='Repair the confirmed package B defect',
            task_id='T-FIX', bug_origin=self.origin(), **inputs)
        self.assertEqual(inputs, before)
        self.assertEqual(fixed['route'], 'fix')
        self.assertEqual(fixed['caller'], 'fix')
        self.assertEqual(fixed['action'], 'requires_actor_check')
        self.assertEqual([(c['id'], c['cwd'], c['reported_current_state'])
                          for c in fixed['packet']['commands']],
                         [('CMD-A', 'packages/a', 'declared'),
                          ('CMD-B', 'packages/b', 'passed')])
        self.assertIn('"regression_test":"test_valid_case reproduces RUN-42 before the fix"',
                      fixed['input'])
        self.assertIn('"cwd":"packages/a"', fixed['input'])
        self.assertIn('"cwd":"packages/b"', fixed['input'])
        self.assertIn('"reported_current_state":"passed"', fixed['input'])
        self.assertIn('"source_ref":"packages/b/AGENTS.md"', fixed['input'])
        self.assertIn('"route":"fix"', fixed['input'])
        self.assertNotIn('"spec_id"', fixed['input'])
        test_change = selector.compose_fix_or_test_actor_input(
            route='test_change', caller='fix', actor='coverage-auditor',
            brief='Add the regression under the existing fix task',
            task_id='T-TEST', **inputs)
        self.assertEqual(test_change['route'], 'test_change')
        self.assertEqual(test_change['caller'], 'fix')
        self.assertIn('"route":"test_change"', test_change['input'])
        self.assertIn('"caller":"fix"', test_change['input'])
        self.assertIn('"cwd":"packages/b"', test_change['input'])
        self.assertNotIn('"bug_origin"', test_change['input'])
        self.assertIn('never change production behavior merely to manufacture',
                      test_change['input'])
        route = (Path(__file__).resolve().parents[2] /
                 'core/surface/commands/fix.md').read_text(encoding='utf-8')
        tdd = (Path(__file__).resolve().parents[2] /
               'core/surface/skills/tdd/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('compose_fix_or_test_actor_input', route)
        self.assertIn('compose_fix_or_test_actor_input', tdd)
        self.assertIn('returned `input`', route)
        self.assertIn('returned `input`', tdd)
        self.assertIn('named regression', route)
        self.assertIn('manufacture a failing test', tdd)

    def test_t036_fix_and_test_context_negative_controls(self):
        """Unknown origin or caller cannot turn context into implementation authority."""
        inputs = self.inputs()
        inputs['constraints'][1]['status'] = 'conflict'
        blocked = selector.compose_fix_or_test_actor_input(
            route='fix', caller='fix', actor='backend-author', brief='Repair B',
            task_id='T-FIX', bug_origin=self.origin(), **inputs)
        self.assertEqual(blocked['action'], 'blocked')
        self.assertIn('"status":"conflict"', blocked['input'])
        self.assertIn('Do not mutate or execute a discovered command', blocked['input'])
        inputs['constraints'][1]['status'] = 'current'
        inputs['observations'] = {}
        unobserved = selector.compose_fix_or_test_actor_input(
            route='test_change', caller='feature', actor='backend-author',
            brief='Improve the existing feature test', task_id='T-TEST', **inputs)
        self.assertEqual(unobserved['packet']['commands'][1]['reported_current_state'],
                         'declared')
        self.assertNotIn('"reported_current_state":"passed"', unobserved['input'])
        for changes in ({'route': 'feature'}, {'route': 'debug'},
                        {'caller': 'debug'}, {'actor': 'unknown'},
                        {'actor': []},
                        {'brief': ''}, {'task_id': ''},
                        {'bug_origin': {'observed': 'Only a symptom'}},
                        {'route': 'test_change', 'caller': 'chore',
                         'bug_origin': self.origin()}):
            with self.subTest(changes=changes), self.assertRaises(selector.SelectionError):
                selector.compose_fix_or_test_actor_input(
                    **{**{'route': 'fix', 'caller': 'fix',
                          'actor': 'backend-author', 'brief': 'Repair B',
                          'task_id': 'T-FIX', 'bug_origin': self.origin()},
                       **changes}, **inputs)


if __name__ == '__main__':
    unittest.main()
