#!/usr/bin/env python3
# codeArbiter — qualify local unittest output without changing test outcomes.
"""Run docstring-bearing cases through the real runner and named collector.

Only the participating fixture classes supply the output adaptation. Nested
cases exercise their inherited shortDescription behavior with actual success,
failure, error, skip, duplicate and empty-suite results. No result text is
fabricated, and no collector or unittest implementation is patched.
"""
from __future__ import annotations

import io
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'core/pysrc'))
from _artifactauthoritylib import AuthorityError, _unittest_collector


def fixture_case(base: type[unittest.TestCase], events: list[str]):
    """Keep the same meaningful case bodies under each output contract."""
    class DocstringCase(base):
        def setUp(self):
            events.append('setUp')
            self.value = ['ready']

        def tearDown(self):
            events.append('tearDown')

        def test_pass(self):
            """A real assertion executes before the successful result is emitted."""
            self.assertEqual(self.value, ['ready'])
            events.append('test_pass assertion completed')

        def test_failure(self):
            """A real failed assertion remains a failed assertion."""
            events.append('test_failure')
            self.assertEqual(self.value, ['unexpected'])

        def test_error(self):
            """An unexpected exception remains an error result."""
            events.append('test_error')
            raise RuntimeError('deliberate named-output fixture error')

        def test_skip(self):
            """A runtime skip remains visible and never qualifies as a pass."""
            events.append('test_skip')
            self.skipTest('deliberate named-output fixture skip')

    return DocstringCase


class TestNamedOutput(unittest.TestCase):
    """Qualify formatting against outcome objects and unmodified raw output."""

    def shortDescription(self):
        return None

    def setUp(self):
        # Keep the complete stream and actual result objects for each run until
        # this outer test finishes; failures include the exact captured stream.
        self.runs = []

    def run_cases(self, base, names):
        events = []
        case = fixture_case(base, events)
        cases = [case(name) for name in names]
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.TestSuite(cases))
        raw = stream.getvalue()
        self.runs.append((raw, result, events, cases))
        return raw, result, events, cases

    def collect(self, raw, names):
        return _unittest_collector(b'', raw.encode('utf-8'), names)

    def rejected(self, raw, names, code):
        with self.assertRaises(AuthorityError, msg=raw) as raised:
            self.collect(raw, names)
        self.assertEqual(raised.exception.code, code, raw)

    def participating_classes(self):
        from test_context_fixtures import TestCampaignSelection, TestFixtureInventory
        return TestCampaignSelection, TestFixtureInventory

    def run_real_unittest(self, names, *, direct_identity=False):
        """Execute importable fixture modules with the untouched verbose runner."""
        source = textwrap.dedent('''\
            import unittest
            from pathlib import Path

            class Alpha(unittest.TestCase):
                def record(self, outcome):
                    with Path('events.txt').open('a', encoding='utf-8') as stream:
                        stream.write(self.id() + ':' + outcome + '\\n')

                def test_pass(self):
                    self.assertEqual(sum([2, 3]), 5)
                    self.record('assertion completed')

                def test_failure(self):
                    self.record('failure')
                    self.assertEqual(2 + 3, 6)

                def test_error(self):
                    self.record('error')
                    raise RuntimeError('deliberate full-identity error')

                def test_skip(self):
                    self.record('skip')
                    self.skipTest('deliberate full-identity skip')

            class Beta(Alpha):
                pass
            ''')
        if direct_identity:
            # A fixture-owned display adaptation emits the already supported
            # direct identity row. The runner and its result handling stay intact.
            source = source.replace('    def record(self, outcome):',
                                    '    def __str__(self):\n'
                                    '        return self.id()\n\n'
                                    '    def record(self, outcome):')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for module in ('identity_alpha', 'identity_beta'):
                (root / (module + '.py')).write_text(source, encoding='utf-8')
            process = subprocess.run(
                [sys.executable, '-B', '-m', 'unittest', '-v', *names],
                cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=30, check=False)
            raw = (process.stdout + process.stderr).decode('utf-8')
            event_path = root / 'events.txt'
            events = event_path.read_text('utf-8').splitlines() if event_path.exists() else []
        self.runs.append((raw, process, events, names))
        return raw, process, events

    def collect_real_identity(self, raw, names):
        try:
            return self.collect(raw, names)
        except AuthorityError as error:
            self.fail(f'actual fully qualified unittest result was rejected: {error}\n{raw}')

    def test_real_unittest_fully_qualified_identity_is_collected(self):
        """An exact ordinary row proves its actually executed qualified case."""
        name = 'identity_alpha.Alpha.test_pass'
        raw, process, events = self.run_real_unittest([name])
        self.assertEqual(process.returncode, 0, raw)
        self.assertIn(f'test_pass ({name}) ... ok', raw)
        self.assertEqual(events, [name + ':assertion completed'])
        self.assertEqual(self.collect_real_identity(raw, [name]),
                         [{'name': name, 'status': 'pass'}], raw)

    def test_real_unittest_full_identities_preserve_class_and_module(self):
        """Shared leaf names never substitute another class or module result."""
        names = ['identity_alpha.Alpha.test_pass', 'identity_alpha.Beta.test_pass',
                 'identity_beta.Alpha.test_pass']
        raw, process, events = self.run_real_unittest(names)
        self.assertEqual(process.returncode, 0, raw)
        self.assertEqual(events, [name + ':assertion completed' for name in names])
        self.assertEqual(self.collect_real_identity(raw, names),
                         [{'name': name, 'status': 'pass'} for name in names], raw)
        for absent in ('identity_beta.Beta.test_pass', 'other.Alpha.test_pass',
                       'Alpha.test_pass', 'identity_alpha.Alpha.test_pass_extra'):
            with self.subTest(absent=absent):
                self.rejected(raw, [absent], 'MISSING_TEST_RESULT')
        self.rejected(raw, ['test_pass'], 'DUPLICATE_TEST_RESULT')
        single, process, events = self.run_real_unittest([names[0]])
        self.assertEqual(process.returncode, 0, single)
        self.assertEqual(events, [names[0] + ':assertion completed'])
        self.assertEqual(self.collect_real_identity(single, [names[0]]),
                         [{'name': names[0], 'status': 'pass'}], single)
        for absent in names[1:]:
            with self.subTest(single_result_absent=absent):
                self.rejected(single, [absent], 'MISSING_TEST_RESULT')

    def test_real_unittest_full_identity_keeps_nonpass_and_missing_refusals(self):
        """Failure, error, skip and no execution cannot qualify as success."""
        names = ['identity_alpha.Alpha.' + leaf for leaf in
                 ('test_pass', 'test_failure', 'test_error', 'test_skip')]
        raw, process, events = self.run_real_unittest(names)
        self.assertEqual(process.returncode, 1, raw)
        self.assertEqual(events, [names[0] + ':assertion completed', names[1] + ':failure',
                                 names[2] + ':error', names[3] + ':skip'])
        self.assertIn(f'test_failure ({names[1]}) ... FAIL', raw)
        self.assertIn(f'test_error ({names[2]}) ... ERROR', raw)
        self.assertIn(f"test_skip ({names[3]}) ... skipped 'deliberate full-identity skip'", raw)
        self.assertIn('FAILED (failures=1, errors=1, skipped=1)', raw)
        self.assertEqual(self.collect_real_identity(raw, [names[0]]),
                         [{'name': names[0], 'status': 'pass'}], raw)
        for name in names[1:] + ['identity_alpha.Alpha.test_absent']:
            with self.subTest(name=name):
                self.rejected(raw, [name], 'MISSING_TEST_RESULT')
        self.rejected(raw, names, 'MISSING_TEST_RESULT')
        empty, zero, events = self.run_real_unittest([])
        # CLI versions distinguish no tests with exit 5 or the older exit 0.
        # Neither status supplies an executed result to this collector.
        self.assertIn(zero.returncode, (0, 5), empty)
        self.assertIn('Ran 0 tests', empty)
        self.assertEqual(events, [])
        self.rejected(empty, [names[0]], 'MISSING_TEST_RESULT')

    def test_real_unittest_full_identity_supports_lf_and_crlf(self):
        """Only line framing changes; every row came from a real execution."""
        name = 'identity_alpha.Alpha.test_pass'
        raw, process, events = self.run_real_unittest([name])
        self.assertEqual(process.returncode, 0, raw)
        self.assertEqual(events, [name + ':assertion completed'])
        for newline in ('\n', '\r\n'):
            with self.subTest(newline=repr(newline)):
                framed = raw.replace('\r\n', '\n').replace('\n', newline)
                self.assertEqual(self.collect_real_identity(framed, [name]),
                                 [{'name': name, 'status': 'pass'}], framed)

    def test_real_unittest_full_identity_rejects_duplicate_and_mixed_rows(self):
        """Both supported row forms count toward the same exact identity."""
        name = 'identity_alpha.Alpha.test_pass'
        repeated, process, events = self.run_real_unittest([name, name])
        self.assertEqual(process.returncode, 0, repeated)
        self.assertEqual(events, [name + ':assertion completed'] * 2)
        self.rejected(repeated, [name], 'DUPLICATE_TEST_RESULT')
        ordinary, process, events = self.run_real_unittest([name])
        self.assertEqual(process.returncode, 0, ordinary)
        self.assertEqual(events, [name + ':assertion completed'])
        direct, process, events = self.run_real_unittest([name], direct_identity=True)
        self.assertEqual(process.returncode, 0, direct)
        self.assertEqual(events, [name + ':assertion completed'])
        self.assertIn(f'{name} ... ok', direct)
        self.assertEqual(self.collect(direct, [name]), [{'name': name, 'status': 'pass'}], direct)
        for raw in (ordinary + direct, direct + ordinary):
            for newline in ('\n', '\r\n'):
                with self.subTest(direct_first=raw.startswith(name), newline=repr(newline)):
                    framed = raw.replace('\r\n', '\n').replace('\n', newline)
                    self.rejected(framed, [name], 'DUPLICATE_TEST_RESULT')

    def test_named_output_preserves_real_docstring_case_execution(self):
        """The existing classes preserve execution and docstrings with named output."""
        plain, baseline, events, cases = self.run_cases(unittest.TestCase, ['test_pass'])
        self.assertEqual(baseline.testsRun, 1, plain)
        self.assertTrue(baseline.wasSuccessful(), plain)
        self.assertEqual(events, ['setUp', 'test_pass assertion completed', 'tearDown'])
        original_docstring = cases[0].test_pass.__doc__
        self.assertIn(original_docstring, plain)
        self.rejected(plain, ['test_pass'], 'MISSING_TEST_RESULT')
        for base in self.participating_classes():
            with self.subTest(participating_class=base.__name__):
                raw, result, actual_events, actual_cases = self.run_cases(base, ['test_pass'])
                self.assertEqual(result.testsRun, baseline.testsRun, raw)
                self.assertTrue(result.wasSuccessful(), raw)
                self.assertEqual(actual_events, events)
                self.assertEqual(actual_cases[0].test_pass.__doc__, original_docstring)
                self.assertEqual(self.collect(raw, ['test_pass']),
                                 [{'name': 'test_pass', 'status': 'pass'}], raw)
                self.assertNotIn(original_docstring, raw)

    def test_named_output_keeps_failure_error_and_skip_outcomes(self):
        """Formatting cannot turn failed, errored or skipped cases into evidence."""
        names = ['test_pass', 'test_failure', 'test_error', 'test_skip']
        plain, baseline, events, _ = self.run_cases(unittest.TestCase, names)
        self.assertEqual(baseline.testsRun, 4, plain)
        self.assertFalse(baseline.wasSuccessful(), plain)
        for base in self.participating_classes():
            with self.subTest(participating_class=base.__name__):
                raw, result, actual_events, _ = self.run_cases(base, names)
                self.assertEqual(result.testsRun, baseline.testsRun, raw)
                self.assertFalse(result.wasSuccessful(), raw)
                self.assertEqual(actual_events, events)
                self.assertEqual(len(result.failures), 1, raw)
                self.assertEqual(len(result.errors), 1, raw)
                self.assertEqual(len(result.skipped), 1, raw)
                self.assertEqual(result.failures[0][0]._testMethodName, 'test_failure')
                self.assertEqual(result.errors[0][0]._testMethodName, 'test_error')
                self.assertEqual(result.skipped[0][0]._testMethodName, 'test_skip')
                self.assertIn('AssertionError', result.failures[0][1])
                self.assertIn('RuntimeError: deliberate named-output fixture error', result.errors[0][1])
                self.assertEqual(result.skipped[0][1], 'deliberate named-output fixture skip')
                self.assertEqual(self.collect(raw, ['test_pass']),
                                 [{'name': 'test_pass', 'status': 'pass'}], raw)
                for name in names[1:]:
                    self.rejected(raw, [name], 'MISSING_TEST_RESULT')
                self.rejected(raw, names, 'MISSING_TEST_RESULT')

    def test_named_output_rejects_missing_duplicate_and_zero_selected_results(self):
        """Exact names qualify once; omissions, repetitions and no execution do not."""
        for base in self.participating_classes():
            with self.subTest(participating_class=base.__name__):
                raw, result, _, _ = self.run_cases(base, ['test_pass'])
                self.assertEqual(result.testsRun, 1, raw)
                self.assertTrue(result.wasSuccessful(), raw)
                self.assertEqual(self.collect(raw, ['test_pass']),
                                 [{'name': 'test_pass', 'status': 'pass'}], raw)
                self.rejected(raw, ['test_absent'], 'MISSING_TEST_RESULT')
                self.rejected(raw, ['test_pass', 'test_absent'], 'MISSING_TEST_RESULT')
                repeated, duplicate, events, _ = self.run_cases(base, ['test_pass', 'test_pass'])
                self.assertEqual(duplicate.testsRun, 2, repeated)
                self.assertTrue(duplicate.wasSuccessful(), repeated)
                self.assertEqual(events.count('test_pass assertion completed'), 2)
                self.rejected(repeated, ['test_pass'], 'DUPLICATE_TEST_RESULT')
                empty, zero, events, _ = self.run_cases(base, [])
                self.assertEqual(zero.testsRun, 0, empty)
                self.assertTrue(zero.wasSuccessful(), empty)
                self.assertEqual(events, [])
                self.rejected(empty, ['test_pass'], 'MISSING_TEST_RESULT')


if __name__ == '__main__':
    unittest.main(verbosity=2)
