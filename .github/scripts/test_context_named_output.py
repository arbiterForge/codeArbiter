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
import sys
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
