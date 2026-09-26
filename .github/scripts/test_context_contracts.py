#!/usr/bin/env python3
"""codeArbiter -- closed scout-report contract tests; no host/model claims."""
from __future__ import annotations

import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
if (ROOT / 'core/pysrc').is_dir():
    sys.path.insert(0, str(ROOT / 'core/pysrc'))
try:
    R = importlib.import_module('_contextreportlib')
except ModuleNotFoundError as error:
    if error.name != '_contextreportlib':
        raise
    R = None


def assignment(category='stack', scope=None, assignment_id='SCOUT-A', attempt_id='ATTEMPT-1'):
    return {'assignment_id': assignment_id, 'attempt_id': attempt_id,
            'snapshot_id': 'a' * 64,
            'scope': {'paths': scope or ['.'], 'categories': [category]}}


def report(category='stack'):
    return {'schema_version': 1, **assignment(category), 'transport': 'complete',
            'diagnostic': None, 'outcomes': [{
                'category': category, 'status': 'observed', 'confidence': 'strong',
                'reason': None,
                'coverage': {'searched_paths': ['.'], 'predicates': ['manifests'], 'excluded': []},
                'evidence': [{'id': 'E-1', 'path': 'package.json', 'start_line': 1, 'end_line': 8,
                              'digest_method': 'sha256-raw', 'digest': 'b' * 64}],
                'findings': [{'id': 'F-1', 'name': 'runtime', 'value': 'Node declared in manifest',
                              'evidence_refs': ['E-1']}]}]}


def wire(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode('utf-8')


class TestReportEnvelope(unittest.TestCase):
    """Require a complete, bounded transport before category gaps are considered."""

    def setUp(self):
        self.assertIsNotNone(R, 'T-005 closed report decoder is not implemented')

    def decode(self, value=None, expected=None):
        return R.decode_report(wire(value if value is not None else report()),
                               expected=expected or assignment())

    def bad(self, value, code=None, expected=None):
        with self.assertRaises(R.ReportError) as caught:
            self.decode(value, expected)
        if code:
            self.assertEqual(caught.exception.code, code)
        self.assertNotIn('PRIVATE-CANARY', str(caught.exception))
        self.assertLess(len(str(caught.exception)), 220)
        return caught.exception

    def test_same_source_method_cannot_carry_two_digests(self):
        value = report(); outcome = value['outcomes'][0]
        outcome['evidence'].append({**outcome['evidence'][0], 'id': 'E-2', 'digest': 'c' * 64})
        outcome['findings'][0]['evidence_refs'].append('E-2')
        self.bad(value, 'MIXED_SOURCE_IDENTITY')

    def test_cross_category_source_identity_is_consistent(self):
        value = report(); value['scope']['categories'].append('tests')
        other = report('tests')['outcomes'][0]
        other['findings'][0]['name'] = 'command_ref'
        other['evidence'][0]['digest'] = 'c' * 64
        value['outcomes'].append(other)
        expected = {key: value[key] for key in ('assignment_id', 'attempt_id', 'snapshot_id', 'scope')}
        self.bad(value, 'MIXED_SOURCE_IDENTITY', expected)
        other['evidence'][0]['digest'] = 'b' * 64
        self.assertEqual(len(self.decode(value, expected)['outcomes']), 2)

    def test_cross_category_case_aliases_cannot_bypass_identity_checks(self):
        value = report(); value['scope']['categories'].append('tests')
        other = report('tests')['outcomes'][0]
        other['findings'][0]['name'] = 'command_ref'
        other['evidence'][0]['path'] = 'Package.json'
        value['outcomes'].append(other)
        expected = {key: value[key] for key in ('assignment_id', 'attempt_id', 'snapshot_id', 'scope')}
        self.bad(value, 'PATH_COLLISION', expected)

    def test_named_digest_methods_are_not_compared_as_equal(self):
        value = report(); outcome = value['outcomes'][0]
        outcome['evidence'].append({**outcome['evidence'][0], 'id': 'E-2',
            'digest_method': 'git-blob-normalized-sha1', 'digest': 'c' * 40})
        outcome['findings'][0]['evidence_refs'].append('E-2')
        result = self.decode(value)
        self.assertEqual(len(result['outcomes'][0]['evidence']), 2)

    def test_normalizes_exact_confidence_aliases(self):
        for expected, spellings in {'high': ['high', 'strong', 'HIGH'],
                                   'medium': ['medium', 'moderate', 'MEDIUM'],
                                   'low': ['low', 'weak', 'LOW']}.items():
            for spelling in spellings:
                with self.subTest(spelling=spelling):
                    value = report(); value['outcomes'][0]['confidence'] = spelling
                    self.assertEqual(self.decode(value)['outcomes'][0]['confidence'], expected)
        for spelling in ('High', 'STRONG', ' strong ', 'certain', '', None, True, 1):
            value = report(); value['outcomes'][0]['confidence'] = spelling
            self.bad(value)

    def test_complete_ambiguous_findings_are_gaps_not_failed_transport(self):
        value = report(); outcome = value['outcomes'][0]
        outcome['status'] = 'ambiguous'; outcome['reason'] = 'Two declarations disagree.'
        outcome['findings'].append({'id': 'F-2', 'name': 'runtime', 'value': 'Different runtime',
                                    'evidence_refs': ['E-1']})
        decoded = self.decode(value)
        self.assertEqual(decoded['transport'], 'complete')
        self.assertEqual(decoded['outcomes'][0]['status'], 'ambiguous')
        self.assertEqual(len(decoded['outcomes'][0]['findings']), 2)

    def test_all_seven_outcomes_remain_distinct(self):
        for status in ('observed', 'not_applicable', 'not_found_in_scope', 'not_inspected',
                       'ambiguous', 'failed', 'oversize'):
            with self.subTest(status=status):
                value = report(); o = value['outcomes'][0]; o['status'] = status
                o['reason'] = 'Bounded category disposition.' if status != 'observed' else None
                if status not in ('observed', 'ambiguous'):
                    o['findings'] = []
                if status in ('not_inspected', 'failed', 'oversize'):
                    o['confidence'] = None; o['evidence'] = []
                    o['coverage']['searched_paths'] = []; o['coverage']['predicates'] = []
                if status == 'not_found_in_scope':
                    o['confidence'] = None; o['evidence'] = []
                self.assertEqual(self.decode(value)['outcomes'][0]['status'], status)

    def test_unknown_keys_reject_at_every_object_boundary(self):
        paths = [(), ('scope',), ('outcomes', 0), ('outcomes', 0, 'coverage'),
                 ('outcomes', 0, 'evidence', 0), ('outcomes', 0, 'findings', 0)]
        for path in paths:
            with self.subTest(path=path):
                value = report(); node = value
                for part in path: node = node[part]
                node['approved'] = 'PRIVATE-CANARY'
                self.bad(value, 'UNKNOWN_FIELD')

    def test_all_required_fields_are_required(self):
        for key in report():
            value = report(); del value[key]
            self.bad(value, 'MISSING_FIELD')
        for key in report()['outcomes'][0]:
            value = report(); del value['outcomes'][0][key]
            self.bad(value, 'MISSING_FIELD')

    def test_version_and_enums_reject_without_coercion(self):
        for version in (True, 1.0, '1', 0, 2, None):
            value = report(); value['schema_version'] = version
            self.bad(value)
        for path in ('transport', 'status', 'category'):
            value = report()
            (value if path == 'transport' else value['outcomes'][0])[path] = 'PRIVATE-CANARY'
            self.bad(value)

    def test_binding_requires_assignment_attempt_and_snapshot(self):
        for field, other in [('assignment_id','OTHER'),('attempt_id','OTHER'),('snapshot_id','c'*64)]:
            value = report(); value[field] = other
            self.bad(value, 'BINDING_MISMATCH')
        for field in ('assignment_id', 'attempt_id', 'snapshot_id'):
            expected = assignment(); del expected[field]
            with self.assertRaises(R.ReportError): R.decode_report(wire(report()), expected=expected)

    def test_nested_scope_cannot_expand_to_root_or_sibling(self):
        expected = assignment(scope=['packages/a'])
        self.bad(report(), 'BINDING_MISMATCH', expected)
        value = report(); value['scope'] = copy.deepcopy(expected['scope'])
        o = value['outcomes'][0]; o['coverage']['searched_paths'] = ['packages/a']
        o['evidence'][0]['path'] = 'packages/a/package.json'
        self.decode(value, expected)
        for path in ('packages/ab/package.json','packages/b/package.json','package.json'):
            o['evidence'][0]['path'] = path
            self.bad(value, 'OUT_OF_SCOPE', expected)

    def test_paths_are_lexical_inert_and_portable(self):
        bad_paths = ['../x', '/x', 'C:/x', 'a\\b', '//server/file', 'a//b', 'a/./b',
                     '.git/config', 'a/.git/config', 'NUL', 'a/CON.txt', 'a. /b',
                     'a./b', 'a/b ', 'x\nPRIVATE-CANARY', 'x\x00', '.', 'e\u0301.txt']
        for path in bad_paths:
            with self.subTest(path=repr(path)):
                value = report(); value['outcomes'][0]['evidence'][0]['path'] = path
                self.bad(value)
        value = report(); value['outcomes'][0]['evidence'][0]['path'] = 'docs/é.txt'
        self.decode(value)

    def test_scope_rejects_duplicates_collisions_and_overlapping_roots(self):
        for paths in (['src','src'], ['Src','src'], ['.','src'], ['src','src/deep'], []):
            expected = assignment(scope=paths); expected['scope']['paths'] = paths
            value = report(); value['scope'] = copy.deepcopy(expected['scope'])
            self.bad(value, expected=expected)

    def test_category_membership_is_exact_not_just_a_count(self):
        value = report(); value['outcomes'] = []
        self.bad(value, 'CATEGORY_COVERAGE')
        value = report(); value['outcomes'].append(copy.deepcopy(value['outcomes'][0]))
        self.bad(value, 'DUPLICATE_ID')
        value = report(); value['outcomes'][0]['category'] = 'tests'
        self.bad(value, 'CATEGORY_COVERAGE')

    def test_failed_and_oversize_transport_never_carry_salvaged_findings(self):
        for transport, diagnostic in [('failed','TOOL_FAILURE'),('oversize','REPORT_TOO_LARGE')]:
            value = report(); value['transport'] = transport; value['diagnostic'] = diagnostic
            self.bad(value, 'TRANSPORT_CONTENT')
            value['outcomes'] = []
            self.assertEqual(self.decode(value)['transport'], transport)
        value = report(); value['diagnostic'] = 'TOOL_FAILURE'
        self.bad(value, 'TRANSPORT_CONTENT')

    def test_not_applicable_requires_justification_and_evidence(self):
        value = report(); o = value['outcomes'][0]; o['status'] = 'not_applicable'; o['findings'] = []
        self.bad(value)
        o['reason'] = 'This scope contains only static documentation.'; o['evidence'] = []
        self.bad(value)
        o['evidence'] = report()['outcomes'][0]['evidence']; self.decode(value)

    def test_negative_search_requires_coverage_not_a_zero_match_claim(self):
        value = report(); o = value['outcomes'][0]; o['status'] = 'not_found_in_scope'
        o['reason'] = 'No matches within the declared search.'; o['confidence'] = None
        o['findings'] = []; o['evidence'] = []
        self.decode(value)
        for field in ('searched_paths', 'predicates'):
            malformed = copy.deepcopy(value); malformed['outcomes'][0]['coverage'][field] = []
            self.bad(malformed, 'SEARCH_COVERAGE')

    def test_uninspected_or_failed_category_cannot_assert_facts(self):
        for status in ('not_inspected','failed','oversize'):
            value = report(); o = value['outcomes'][0]; o['status'] = status
            o['reason'] = 'Unavailable scope.'; o['confidence'] = None
            self.bad(value, 'UNSUPPORTED_FINDING')

    def test_excluded_scope_is_not_inspected_evidence(self):
        value = report(); o = value['outcomes'][0]
        o['coverage']['excluded'] = [{'path':'vendor','reason':'vendor'}]
        o['evidence'][0]['path'] = 'vendor/package.json'
        self.bad(value, 'EXCLUDED_EVIDENCE')
        o['evidence'][0]['path'] = 'package.json'; self.decode(value)
        o['coverage']['excluded'][0]['reason'] = 'probably_unimportant'
        self.bad(value)

    def test_evidence_ranges_and_digest_methods_are_explicit(self):
        for field, bad in [('start_line',0),('end_line',0),('start_line',True),('end_line',1.5),
                           ('end_line',10**12),('digest','x'*64),('digest_method','sha1')]:
            value = report(); value['outcomes'][0]['evidence'][0][field] = bad; self.bad(value)
        value = report(); e = value['outcomes'][0]['evidence'][0]
        e['digest_method'] = 'git-blob-normalized-sha1'; e['digest'] = 'c'*40
        self.assertEqual(self.decode(value)['outcomes'][0]['evidence'][0]['digest_method'], e['digest_method'])
        e['digest'] = 'b'*64; self.bad(value)

    def test_finding_references_and_names_cannot_invent_authority(self):
        for field, value in [('evidence_refs',[]),('evidence_refs',['E-MISSING']),
                             ('evidence_refs',['E-1','E-1']),('name','approval'),('value',{'approved':True}),
                             ('value','copied\nraw\nsource'),('id','PRIVATE-CANARY\n')]:
            r = report(); r['outcomes'][0]['findings'][0][field] = value; self.bad(r)

    def test_duplicate_local_ids_and_unused_evidence_reject(self):
        for key in ('evidence','findings'):
            value = report(); value['outcomes'][0][key].append(copy.deepcopy(value['outcomes'][0][key][0]))
            self.bad(value, 'DUPLICATE_ID')
        value = report(); value['outcomes'][0]['evidence'].append({**value['outcomes'][0]['evidence'][0], 'id':'E-2'})
        self.bad(value, 'UNUSED_EVIDENCE')

    def test_duplicate_json_keys_reject_before_semantics(self):
        raw = wire(report()).replace(b'"schema_version":1',b'"schema_version":1,"schema_version":1')
        with self.assertRaises(R.ReportError) as caught: R.decode_report(raw, expected=assignment())
        self.assertEqual(caught.exception.code, 'DUPLICATE_KEY')
        raw = wire(report()).replace(b'"path":"package.json"',b'"path":"package.json","path":"elsewhere"')
        with self.assertRaises(R.ReportError): R.decode_report(raw, expected=assignment())

    def test_json_frame_rejects_bom_fences_nonfinite_and_trailing_payload(self):
        for raw in (b'\xef\xbb\xbf'+wire(report()), b'```json\n'+wire(report())+b'\n```',
                    wire(report())+b'{}', b'{"n":NaN}', b'{"n":Infinity}', b'\xff', b'[]'):
            with self.subTest(raw=raw[:12]), self.assertRaises(R.ReportError):
                R.decode_report(raw, expected=assignment())

    def test_oversized_deep_and_huge_integer_inputs_are_bounded(self):
        for raw in (b' '* (R.MAX_REPORT_BYTES+1), b'['*40+b'0'+b']'*40,
                    b'{"n":'+b'9'*10000+b'}'):
            with self.assertRaises(R.ReportError): R.decode_report(raw, expected=assignment())
        value = report(); value['outcomes'][0]['reason'] = 'x'*600
        self.bad(value, 'TEXT_LIMIT')
        value = report(); value['outcomes'][0]['findings'][0]['value'] = '\ud800'
        self.bad(value)

    def test_each_logical_category_has_its_own_bounded_fact_vocabulary(self):
        names = {'stack':'runtime', 'infrastructure':'command_ref', 'architecture':'entry_point',
                 'security':'boundary', 'tests':'test_boundary', 'data':'datastore'}
        for category, name in names.items():
            with self.subTest(category=category):
                value = report(category); value['outcomes'][0]['findings'][0]['name'] = name
                self.decode(value, assignment(category))
                value['outcomes'][0]['findings'][0]['name'] = 'approved_policy'
                self.bad(value, expected=assignment(category))

    def test_exact_raw_byte_limit_is_not_a_character_limit(self):
        raw = wire(report()); padded = raw + b' '*(R.MAX_REPORT_BYTES-len(raw))
        R.decode_report(padded,expected=assignment())
        with self.assertRaises(R.ReportError) as caught:
            R.decode_report(padded+b' ',expected=assignment())
        self.assertEqual(caught.exception.code,'REPORT_TOO_LARGE')

    def test_inline_command_looking_evidence_is_inert_data(self):
        value = report(); value['outcomes'][0]['findings'][0]['value'] = '$(touch SHOULD_NOT_EXIST)'
        result = self.decode(value)
        self.assertEqual(result['outcomes'][0]['findings'][0]['value'],'$(touch SHOULD_NOT_EXIST)')
        self.assertNotIn('approved',result)

    def test_decoder_is_pure_and_returns_detached_data(self):
        value, expected = report(), assignment(); before = copy.deepcopy((value,expected))
        decoded = self.decode(value,expected); decoded['scope']['paths'].append('other')
        self.assertEqual((value,expected),before)
        with tempfile.TemporaryDirectory() as tmp:
            before_names = list(Path(tmp).iterdir()); cwd = os.getcwd()
            try:
                os.chdir(tmp); self.decode()
                self.assertEqual(list(Path(tmp).iterdir()),before_names)
            finally: os.chdir(cwd)

    def test_report_is_canonical_under_collection_reordering(self):
        value = report(); o = value['outcomes'][0]
        o['evidence'].append({**o['evidence'][0], 'id':'E-2','path':'other.json'})
        o['findings'].append({**o['findings'][0], 'id':'F-2','evidence_refs':['E-2']})
        a = self.decode(value)
        o['evidence'].reverse(); o['findings'].reverse()
        self.assertEqual(self.decode(value),a)

    def test_import_performs_no_file_process_or_network_work(self):
        program = '''import sys
sys.dont_write_bytecode = True
import _contextreportlib
from unittest.mock import patch
sys.modules.pop('_contextreportlib')
with patch('builtins.open', side_effect=AssertionError('unexpected file read')), patch('subprocess.run', side_effect=AssertionError('unexpected process')):
 import _contextreportlib
'''
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PYTHONPATH=str(Path(R.__file__).parent), PYTHONDONTWRITEBYTECODE='1')
            p = subprocess.run([sys.executable,'-c',program],cwd=tmp,env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(list(Path(tmp).iterdir()),[])


def main(argv=None):
    selectors = sys.argv[1:] if argv is None else argv
    allowed = {'TestReportEnvelope': TestReportEnvelope}
    if any(s not in allowed for s in selectors) or len(selectors) != len(set(selectors)):
        print('Unknown or repeated contract-test selector',file=sys.stderr); return 2
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(allowed[s])
                               for s in selectors or allowed)
    if not suite.countTestCases(): return 2
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == '__main__':
    raise SystemExit(main())
