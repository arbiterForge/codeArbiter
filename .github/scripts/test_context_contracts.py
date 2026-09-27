#!/usr/bin/env python3
"""codeArbiter -- closed scout-report contract tests; no host/model claims."""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unicodedata
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if (ROOT / 'core/pysrc').is_dir():
    sys.path.insert(0, str(ROOT / 'core/pysrc'))
try:
    R = importlib.import_module('_contextreportlib')
except ModuleNotFoundError as error:
    if error.name != '_contextreportlib':
        raise
    R = None
try:
    S = importlib.import_module('_contextsnapshotlib')
except ModuleNotFoundError as error:
    if error.name != '_contextsnapshotlib':
        raise
    S = None
P = importlib.import_module('_provenancelib')


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


class TestInertDigest(unittest.TestCase):
    """T-006: bounded raw source identity without repository execution."""

    def shortDescription(self):
        return None

    def test_t006_inert_digest_positive_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'worktree'
            (root / 'src').mkdir(parents=True)
            data = b'first\r\nsecond\n\x00last'
            (root / 'src' / 'manifest.txt').write_bytes(data)
            (root / '.gitattributes').write_text('src/manifest.txt filter=sentinel\n', encoding='utf-8')
            (root / '.git').mkdir()
            (root / '.git' / 'config').write_text(
                '[filter "sentinel"]\n\tclean = python sentinel-helper.py\n', encoding='utf-8')
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertIsNotNone(S, 'T-006 inert digest reader is not implemented')
            with patch('subprocess.Popen', side_effect=AssertionError('process launched')), \
                 patch('subprocess.run', side_effect=AssertionError('process launched')), \
                 patch('os.system', side_effect=AssertionError('process launched')), \
                 patch.object(socket.socket, 'connect', side_effect=AssertionError('network used')):
                result = S.digest_file(root, 'src/manifest.txt', scope_paths=('src',))
            self.assertEqual(result, {'path': 'src/manifest.txt', 'digest_method': 'sha256-raw',
                                      'digest': hashlib.sha256(data).hexdigest()})
            self.assertEqual({str(p.relative_to(root)): p.read_bytes()
                              for p in root.rglob('*') if p.is_file()}, before)
            legacy = {'digest_method': 'git-blob-normalized-sha1', 'digest': '0' * 40}
            self.assertNotEqual((result['digest_method'], result['digest']),
                                (legacy['digest_method'], legacy['digest']))
            self.assertEqual(S.digest_file(root, 'src/manifest.txt',
                                           scope_paths=('.',), max_bytes=len(data)), result)

    def test_t006_inert_digest_negative_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'worktree'; root.mkdir()
            (root / 'src').mkdir(); (root / 'outside').mkdir()
            target = root / 'src' / 'manifest.txt'; target.write_bytes(b'ordinary bytes')
            (root / 'outside' / 'file.txt').write_bytes(b'outside scope')
            (root / '.env').write_bytes(b'FAKE_TEST_SECRET=x')
            (root / '.ssh').mkdir(); (root / '.ssh' / 'config').write_bytes(b'fake identity')
            (root / 'src' / 'private.pem').write_bytes(b'fake key')
            self.assertIsNotNone(S, 'T-006 inert digest reader is not implemented')
            for path, scope, code in (
                ('../elsewhere', ('.',), 'UNSAFE_PATH'),
                ('src\\manifest.txt', ('.',), 'UNSAFE_PATH'),
                ('outside/file.txt', ('src',), 'OUT_OF_SCOPE'),
                ('.env', ('.',), 'SENSITIVE_PATH'),
                ('.ssh/config', ('.',), 'SENSITIVE_PATH'),
                ('src/private.pem', ('.',), 'SENSITIVE_PATH'),
                ('src/manifest.txt', ('.',), None),
                ('src/missing.txt', ('.',), 'UNREADABLE'),
            ):
                if code is None:
                    continue
                with self.subTest(path=path):
                    with self.assertRaises(S.DigestError) as caught:
                        S.digest_file(root, path, scope_paths=scope)
                    self.assertEqual(caught.exception.code, code)
            with self.assertRaises(S.DigestError) as caught:
                S.digest_file(root, 'src/manifest.txt', denied_paths=('src/manifest.txt',))
            self.assertEqual(caught.exception.code, 'SENSITIVE_PATH')
            with self.assertRaises(S.DigestError) as caught:
                S.digest_file(root, 'src/manifest.txt', max_bytes=4)
            self.assertEqual(caught.exception.code, 'BYTE_LIMIT')
            with self.assertRaises(S.DigestError) as caught:
                S.digest_file(root, 'src/manifest.txt', max_bytes=16 * 1024 * 1024 + 1)
            self.assertEqual(caught.exception.code, 'BYTE_LIMIT')
            with self.assertRaises(S.DigestError) as caught:
                S.digest_file(root, 'src', scope_paths=('.',))
            self.assertEqual(caught.exception.code, 'NOT_REGULAR')
            outside = Path(tmp) / 'elsewhere.txt'; outside.write_bytes(b'escape')
            link = root / 'src' / 'link.txt'
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                # Some Windows hosts lack symlink privilege. Exercise the same
                # rejection via a reparse attribute on an otherwise regular file.
                link.write_bytes(b'fallback fixture')
                original_lstat = Path.lstat
                reparse = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
                self.assertNotEqual(reparse, 0, 'Neither symlink nor reparse control is available')
                def reparse_lstat(path, *args, **kwargs):
                    if path == link:
                        return SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=reparse)
                    return original_lstat(path, *args, **kwargs)
                with patch.object(Path, 'lstat', reparse_lstat):
                    with self.assertRaises(S.DigestError) as caught:
                        S.digest_file(root, 'src/link.txt')
                    self.assertEqual(caught.exception.code, 'UNSAFE_LINK')
            else:
                with self.assertRaises(S.DigestError) as caught:
                    S.digest_file(root, 'src/link.txt')
                self.assertEqual(caught.exception.code, 'UNSAFE_LINK')
            original_read = os.read
            with patch.object(S.os, 'read', side_effect=OSError('PRIVATE-CANARY')):
                with self.assertRaises(S.DigestError) as caught:
                    S.digest_file(root, 'src/manifest.txt')
                self.assertEqual(caught.exception.code, 'UNREADABLE')
                self.assertNotIn('PRIVATE-CANARY', str(caught.exception))
            def truncated(fd, size):
                chunk = original_read(fd, size)
                if chunk:
                    target.write_bytes(b'')
                return chunk[:2]
            with patch.object(S.os, 'read', side_effect=truncated):
                with self.assertRaises(S.DigestError) as caught:
                    S.digest_file(root, 'src/manifest.txt')
                self.assertIn(caught.exception.code, ('PARTIAL_READ', 'SOURCE_CHANGED'))
            target.write_bytes(b'ordinary bytes')
            def changed(fd, size):
                chunk = original_read(fd, size)
                if chunk:
                    target.write_bytes(b'changed bytes!')
                return chunk
            with patch.object(S.os, 'read', side_effect=changed):
                with self.assertRaises(S.DigestError) as caught:
                    S.digest_file(root, 'src/manifest.txt')
                self.assertEqual(caught.exception.code, 'SOURCE_CHANGED')

    def test_t006_same_size_changed_bytes_with_stable_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'manifest.txt'
            original = b'ordinary bytes'
            replacement = b'changed bytes!'
            self.assertEqual(len(original), len(replacement))
            target.write_bytes(original)
            self.assertEqual(S.digest_file(root, 'manifest.txt')['digest'],
                             hashlib.sha256(original).hexdigest())

            before = S._components(root, ['manifest.txt'])
            opened = target.stat()
            original_read = os.read
            replaced = False

            def change_after_first_read(fd, size):
                nonlocal replaced
                chunk = original_read(fd, size)
                if chunk and not replaced:
                    target.write_bytes(replacement)
                    replaced = True
                return chunk

            # Model a same-size rewrite inside the filesystem timestamp resolution.
            # The bytes and descriptor reads remain real; only metadata is held stable.
            with patch.object(S, '_components', return_value=before), \
                 patch.object(S.os, 'fstat', return_value=opened), \
                 patch.object(S.os, 'read', side_effect=change_after_first_read):
                with self.assertRaises(S.DigestError) as caught:
                    S.digest_file(root, 'manifest.txt')
            self.assertTrue(replaced)
            self.assertEqual(target.read_bytes(), replacement)
            self.assertEqual(caught.exception.code, 'SOURCE_CHANGED')


class TestMembershipCoverage(unittest.TestCase):
    """T-007: finite, bounded path membership with honest boundary gaps."""

    def shortDescription(self):
        return None

    def test_t007_unsafe_name_is_uninspected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'package.json').write_bytes(b'{}')
            unsafe_name = 'zz-e\u0301.txt'
            self.assertNotEqual(unsafe_name, unicodedata.normalize('NFC', unsafe_name))
            (root / unsafe_name).write_bytes(b'fixture')
            self.assertIn(unsafe_name, os.listdir(root),
                          'filesystem normalized the real unsafe-name fixture')
            result = S.membership_snapshot(root, 'manifests')
            self.assertEqual(result['status'], 'not_inspected')
            self.assertEqual(result['matches'], [])
            self.assertEqual(result['excluded'], [{'path': '.', 'reason': 'unreadable'}])
            self.assertIsNone(result['digest'])
            self.assertFalse(result['negative_proof'])

    def test_t007_membership_coverage_positive_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'worktree'; root.mkdir()
            (root / '.git').mkdir()
            (root / 'packages' / 'alpha' / 'src').mkdir(parents=True)
            (root / 'packages' / 'alpha' / 'package.json').write_bytes(b'{"name":"alpha"}')
            leaf = root / 'packages' / 'alpha' / 'src' / 'index.ts'
            leaf.write_bytes(b'export const x = 1;')
            (root / 'packages' / 'alpha' / 'tests').mkdir()
            (root / 'packages' / 'alpha' / 'tests' / 'test_unit.py').write_bytes(b'pass')
            (root / 'packages' / 'alpha' / 'infra').mkdir()
            (root / 'packages' / 'alpha' / 'infra' / 'Dockerfile').write_bytes(b'FROM scratch')
            (root / 'packages' / 'alpha' / 'security').mkdir()
            (root / 'packages' / 'alpha' / 'security' / 'SECURITY.md').write_bytes(b'policy')
            (root / 'packages' / 'alpha' / 'migrations').mkdir()
            (root / 'packages' / 'alpha' / 'migrations' / 'schema.sql').write_bytes(b'-- schema')
            (root / 'packages' / 'alpha' / '.editorconfig').write_bytes(b'root = true')
            scope = ('packages/alpha',)
            before = {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in root.rglob('*') if p.is_file()}
            with patch('subprocess.Popen', side_effect=AssertionError('process launched')), \
                 patch('subprocess.run', side_effect=AssertionError('process launched')), \
                 patch('os.system', side_effect=AssertionError('process launched')), \
                 patch.object(socket.socket, 'connect', side_effect=AssertionError('network used')):
                first = S.membership_snapshot(root, 'manifests', scope_paths=scope)
                again = S.membership_snapshot(root, 'manifests', scope_paths=scope)
                self.assertEqual({path: (root / path).stat().st_mtime_ns for path in before},
                                 {path: value[1] for path, value in before.items()})
                leaf.write_bytes(b'export const x = 2;')
                leaf_edit = S.membership_snapshot(root, 'manifests', scope_paths=scope)
                (root / 'packages' / 'alpha' / 'pyproject.toml').write_bytes(b'[project]\n')
                added = S.membership_snapshot(root, 'manifests', scope_paths=scope)
                instruction_before = S.membership_snapshot(root, 'instructions', scope_paths=scope)
                (root / 'packages' / 'alpha' / 'src' / 'AGENTS.md').write_bytes(b'local instruction')
                instruction_after = S.membership_snapshot(root, 'instructions', scope_paths=scope)
            self.assertEqual(first, again)
            self.assertEqual(first['matches'], ['packages/alpha/package.json'])
            self.assertEqual(first['digest_method'], 'sha256-membership-v1')
            self.assertEqual(first['digest'], leaf_edit['digest'])
            self.assertEqual(added['matches'], ['packages/alpha/package.json',
                                                'packages/alpha/pyproject.toml'])
            self.assertNotEqual(first['digest'], added['digest'])
            self.assertEqual(instruction_before['matches'], [])
            self.assertEqual(instruction_after['matches'], ['packages/alpha/src/AGENTS.md'])
            self.assertNotEqual(instruction_before['digest'], instruction_after['digest'])
            self.assertTrue(instruction_before['negative_proof'])
            for predicate, expected in (
                ('tests', ['packages/alpha/tests', 'packages/alpha/tests/test_unit.py']),
                ('infrastructure', ['packages/alpha/infra', 'packages/alpha/infra/Dockerfile']),
                ('security', ['packages/alpha/security', 'packages/alpha/security/SECURITY.md']),
                ('data', ['packages/alpha/migrations', 'packages/alpha/migrations/schema.sql']),
                ('configuration', ['packages/alpha/.editorconfig']),
            ):
                with self.subTest(predicate=predicate):
                    self.assertEqual(S.membership_snapshot(root, predicate,
                                     scope_paths=scope)['matches'], expected)
            self.assertEqual({path: (root / path).read_bytes() for path in before},
                             {path: value[0] if path != leaf.relative_to(root).as_posix()
                              else b'export const x = 2;' for path, value in before.items()})
            self.assertEqual({path: (root / path).stat().st_mtime_ns for path in before
                              if path != leaf.relative_to(root).as_posix()},
                             {path: value[1] for path, value in before.items()
                              if path != leaf.relative_to(root).as_posix()})
            self.assertEqual({p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()},
                             set(before) | {'packages/alpha/pyproject.toml',
                                            'packages/alpha/src/AGENTS.md'})
            # Repeated acquisition is canonical regardless of directory insertion order.
            sibling = Path(tmp) / 'reordered'; sibling.mkdir()
            (sibling / 'packages' / 'alpha' / 'src').mkdir(parents=True)
            (sibling / 'packages' / 'alpha' / 'pyproject.toml').write_bytes(b'different bytes')
            (sibling / 'packages' / 'alpha' / 'package.json').write_bytes(b'different bytes')
            self.assertEqual(S.membership_snapshot(sibling, 'manifests', scope_paths=scope), added)
            (root / 'packages' / 'alpha' / 'package.json').unlink()
            removed = S.membership_snapshot(root, 'manifests', scope_paths=scope)
            self.assertEqual(removed['matches'], ['packages/alpha/pyproject.toml'])
            self.assertNotEqual(removed['digest'], added['digest'])

    def test_t007_membership_coverage_negative_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'worktree'; root.mkdir()
            for name in ('vendor', 'generated', 'node_modules', 'src', 'nested', 'submodule'):
                (root / name).mkdir()
            (root / 'vendor' / 'package.json').write_bytes(b'vendor')
            (root / 'generated' / 'package.json').write_bytes(b'generated')
            (root / 'node_modules' / 'package.json').write_bytes(b'dependency')
            (root / 'src' / 'package.json').write_bytes(b'owned')
            (root / 'nested' / '.git').mkdir()
            (root / 'nested' / 'child').mkdir()
            (root / 'nested' / 'child' / 'package.json').write_bytes(b'nested child')
            (root / 'nested' / 'package.json').write_bytes(b'nested repo')
            (root / 'submodule' / '.git').write_bytes(b'gitdir: elsewhere')
            (root / 'submodule' / 'package.json').write_bytes(b'submodule')
            (root / 'ordinary-a.txt').write_bytes(b'a')
            (root / 'ordinary-b.txt').write_bytes(b'b')
            result = S.membership_snapshot(root, 'manifests', excluded=[
                {'path': 'src', 'reason': 'ignored'},
                {'path': 'missing-sparse', 'reason': 'sparse'}])
            self.assertEqual(result['matches'], [])
            self.assertEqual(result['excluded'], [
                {'path': 'generated', 'reason': 'generated'},
                {'path': 'missing-sparse', 'reason': 'sparse'},
                {'path': 'nested', 'reason': 'nested_repository'},
                {'path': 'node_modules', 'reason': 'vendor'},
                {'path': 'src', 'reason': 'ignored'},
                {'path': 'submodule', 'reason': 'submodule'},
                {'path': 'vendor', 'reason': 'vendor'}])
            self.assertFalse(result['negative_proof'])
            self.assertEqual(S.membership_snapshot(root, 'manifests',
                             excluded=list(reversed([
                                 {'path': 'src', 'reason': 'ignored'},
                                 {'path': 'missing-sparse', 'reason': 'sparse'}]))), result)
            nested_scope = S.membership_snapshot(root, 'manifests',
                                                  scope_paths=('nested/child',))
            self.assertEqual(nested_scope['matches'], [])
            self.assertEqual(nested_scope['excluded'], [
                {'path': 'nested/child', 'reason': 'nested_repository'}])
            self.assertFalse(nested_scope['negative_proof'])
            vendor_scope = S.membership_snapshot(root, 'manifests', scope_paths=('vendor',))
            self.assertEqual(vendor_scope['matches'], [])
            self.assertEqual(vendor_scope['excluded'], [{'path': 'vendor', 'reason': 'vendor'}])
            for predicate in ('*.json', 'manifests|instructions', '$(touch marker)',
                              'concern_boundaries', 'source', 'entry_points'):
                with self.subTest(predicate=predicate):
                    with self.assertRaises(S.MembershipError) as caught:
                        S.membership_snapshot(root, predicate)
                    self.assertEqual(caught.exception.code, 'UNKNOWN_PREDICATE')
            for kwargs, code in (({'scope_paths': ('../outside',)}, 'UNSAFE_PATH'),
                                 ({'max_files': 1}, 'BOUND_EXCEEDED'),
                                 ({'max_directories': 1}, 'BOUND_EXCEEDED'),
                                 ({'excluded': [{'path': 'src', 'reason': 'invented'}]}, 'UNKNOWN_EXCLUSION')):
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(S.MembershipError) as caught:
                        S.membership_snapshot(root, 'manifests', **kwargs)
                    self.assertEqual(caught.exception.code, code)
            missing = S.membership_snapshot(root, 'manifests', scope_paths=('absent',))
            self.assertEqual(missing['status'], 'not_inspected')
            self.assertIsNone(missing['digest'])
            self.assertFalse(missing['negative_proof'])
            self.assertEqual(missing['excluded'], [{'path': 'absent', 'reason': 'unreadable'}])
            with patch.object(S.os, 'scandir', side_effect=PermissionError('PRIVATE-CANARY')):
                unreadable = S.membership_snapshot(root, 'manifests')
            self.assertEqual(unreadable['status'], 'not_inspected')
            self.assertIsNone(unreadable['digest'])
            self.assertFalse(unreadable['negative_proof'])
            self.assertNotIn('PRIVATE-CANARY', str(unreadable))
            outside = Path(tmp) / 'outside'; outside.mkdir()
            (outside / 'package.json').write_bytes(b'external')
            link = root / 'linked'
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                link.mkdir()
                original_lstat = Path.lstat
                reparse = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
                self.assertNotEqual(reparse, 0)
                def reparse_lstat(path, *args, **kwargs):
                    if path == link:
                        return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=reparse)
                    return original_lstat(path, *args, **kwargs)
                with patch.object(Path, 'lstat', reparse_lstat):
                    linked = S.membership_snapshot(root, 'manifests')
            else:
                linked = S.membership_snapshot(root, 'manifests')
            self.assertEqual(linked['status'], 'not_inspected')
            self.assertIsNone(linked['digest'])
            self.assertFalse(linked['negative_proof'])
            self.assertIn({'path': 'linked', 'reason': 'unreadable'}, linked['excluded'])
            linked_scope = S.membership_snapshot(root, 'manifests',
                                                  scope_paths=('linked/child',))
            self.assertFalse(linked_scope['negative_proof'])
            self.assertIsNone(linked_scope['digest'])


class TestContextSnapshot(unittest.TestCase):
    """T-008: actual Git worktrees and independent source/output identities."""

    def shortDescription(self):
        return None

    def git(self, root, *args):
        return subprocess.run(['git', '-C', str(root), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    def fixture(self, directory):
        root = directory / 'main'
        root.mkdir()
        self.git(root, 'init', '-q', '-b', 'main')
        (root / 'app' / 'nested').mkdir(parents=True)
        (root / 'app' / 'package.json').write_bytes(b'{"name":"first"}\n')
        (root / 'app' / 'AGENTS.md').write_bytes(b'Use the declared tools.\n')
        self.git(root, 'add', '--', 'app/package.json', 'app/AGENTS.md')
        self.git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test',
                 'commit', '-qm', 'initial')
        self.git(root, 'remote', 'add', 'origin', str(root))
        self.git(root, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
        self.git(root, 'branch', '--set-upstream-to=origin/main', 'main')
        return root

    def capture(self, root):
        return S.context_snapshot(root / 'app' / 'nested',
                                  source_paths=('app/package.json', 'app/AGENTS.md'),
                                  source_scopes=('app',),
                                  membership=(('manifests', ('app',)),
                                              ('instructions', ('app',))),
                                  target_paths=('app/result.json',),
                                  allowed_effect_paths=('.codearbiter/marker',
                                                        'generated/view.json',
                                                        'app/view.json'))

    def test_t008_directory_membership_binds_files_without_hashing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.fixture(Path(tmp))
            (root / 'tests').mkdir()
            unit = root / 'tests' / 'test_unit.py'
            unit.write_bytes(b'assert True\n')
            membership = S.membership_snapshot(root, 'tests')
            self.assertEqual(membership['status'], 'complete')
            self.assertEqual(membership['matches'], ['tests', 'tests/test_unit.py'])
            snapshot = S.context_snapshot(root, membership=(('tests', ('.',)),))
            self.assertEqual(snapshot['source']['membership'][0]['digest'], membership['digest'])
            self.assertNotIn('tests', snapshot['source']['files'])
            self.assertEqual(snapshot['source']['files']['tests/test_unit.py']['digest'],
                             hashlib.sha256(unit.read_bytes()).hexdigest())
            self.assertTrue(S.compare_context_snapshot(snapshot, boundary='join')['admitted'])
            unit.write_bytes(b'assert False\n')
            self.assertFalse(S.compare_context_snapshot(snapshot, boundary='join')['admitted'])
            changed = S.context_snapshot(root, membership=(('tests', ('.',)),))
            (root / 'tests' / 'test_new.py').write_bytes(b'assert True\n')
            self.assertFalse(S.compare_context_snapshot(changed, boundary='join')['admitted'])

    def test_t008_context_snapshot_positive_controls(self):
        self.assertTrue(hasattr(S, 'context_snapshot'), 'T-008 source snapshot API is absent')
        self.assertTrue(hasattr(S, 'compare_context_snapshot'), 'T-008 comparison API is absent')
        with tempfile.TemporaryDirectory() as tmp:
            root = self.fixture(Path(tmp))
            (root / '.gitattributes').write_bytes(b'app/package.json filter=sentinel\n')
            (root / 'sentinel-helper.py').write_text(
                'import pathlib,sys\n'
                'pathlib.Path("filter-ran").write_bytes(b"ran")\n'
                'sys.stdout.buffer.write(sys.stdin.buffer.read())\n', encoding='utf-8')
            self.git(root, 'config', 'filter.sentinel.clean', 'python sentinel-helper.py')
            before_index = (root / '.git' / 'index').read_bytes()
            before_source = (root / 'app' / 'package.json').read_bytes()
            snapshot = self.capture(root)
            self.assertEqual(snapshot['worktree']['root'], str(root.resolve()))
            self.assertEqual(snapshot['worktree']['common_dir'], str((root / '.git').resolve()))
            self.assertEqual(snapshot['worktree']['head'],
                             self.git(root, 'rev-parse', 'HEAD').decode().strip())
            self.assertEqual(snapshot['worktree']['branch'], 'main')
            self.assertFalse(snapshot['worktree']['detached'])
            self.assertEqual(snapshot['worktree']['upstream']['ref'], 'refs/remotes/origin/main')
            self.assertEqual(snapshot['worktree']['upstream']['relation'], 'same')
            self.assertEqual(snapshot['worktree']['upstream']['freshness'], 'local_only')
            self.assertEqual(snapshot['worktree']['fork']['status'], 'unknown')
            self.assertEqual(snapshot['source']['digest_method'], 'sha256-source-snapshot-v1')
            self.assertEqual(snapshot['source']['files']['app/package.json']['digest'],
                             hashlib.sha256(before_source).hexdigest())
            self.assertEqual(snapshot['targets']['app/result.json']['status'], 'absent')
            self.assertEqual(snapshot['allowed_effects'],
                             ['.codearbiter/marker', 'app/view.json', 'generated/view.json'])
            self.assertTrue(S.compare_context_snapshot(snapshot, boundary='join')['admitted'])
            self.assertTrue(S.compare_context_snapshot(snapshot, boundary='action')['admitted'])
            (root / '.codearbiter').mkdir()
            (root / '.codearbiter' / 'marker').write_bytes(b'new marker')
            (root / 'generated').mkdir()
            (root / 'generated' / 'view.json').write_bytes(b'{"new":true}')
            (root / 'app' / 'view.json').write_bytes(b'{"new":true}')
            self.assertTrue(S.compare_context_snapshot(snapshot, boundary='join')['admitted'])
            self.assertTrue(S.compare_context_snapshot(snapshot, boundary='action')['admitted'])
            (root / 'app' / 'result.json').write_bytes(b'owner edit')
            self.assertTrue(S.compare_context_snapshot(snapshot, boundary='join')['admitted'])
            changed_target = S.compare_context_snapshot(snapshot, boundary='action')
            self.assertFalse(changed_target['admitted'])
            self.assertTrue(changed_target['source_current'])
            self.assertFalse(changed_target['targets_current'])
            (root / 'app' / 'package.json').write_bytes(b'{"name":"other"}\n')
            changed_source = S.compare_context_snapshot(snapshot, boundary='join')
            self.assertFalse(changed_source['admitted'])
            self.assertFalse(changed_source['source_current'])
            self.assertEqual((root / 'app' / 'result.json').read_bytes(), b'owner edit')
            self.assertEqual((root / '.git' / 'index').read_bytes(), before_index)
            self.assertFalse((root / 'filter-ran').exists())

    def test_t008_context_snapshot_negative_controls(self):
        self.assertTrue(hasattr(S, 'context_snapshot'), 'T-008 source snapshot API is absent')
        self.assertTrue(hasattr(S, 'compare_context_snapshot'), 'T-008 comparison API is absent')
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = self.fixture(base)
            snapshot = self.capture(root)
            sibling = base / 'linked'
            self.git(root, 'worktree', 'add', '-q', '--detach', str(sibling), 'HEAD')
            (sibling / 'app' / 'nested').mkdir()
            sibling_snapshot = self.capture(sibling)
            self.assertEqual(snapshot['worktree']['common_dir'],
                             sibling_snapshot['worktree']['common_dir'])
            self.assertEqual(snapshot['worktree']['head'], sibling_snapshot['worktree']['head'])
            self.assertNotEqual(snapshot['worktree']['git_dir'],
                                sibling_snapshot['worktree']['git_dir'])
            self.assertTrue(sibling_snapshot['worktree']['detached'])
            self.assertIsNone(sibling_snapshot['worktree']['branch'])
            self.assertNotEqual(snapshot['source']['digest'], sibling_snapshot['source']['digest'])
            self.assertFalse(S.compare_context_snapshot(snapshot, sibling,
                                                        boundary='join')['admitted'])
            (sibling / 'app' / 'package.json').write_bytes(b'{"name":"dirty"}\n')
            dirty = self.capture(sibling)
            self.assertIn('app/package.json', dirty['source']['git_state']['raw_dirty'])
            self.assertFalse(S.compare_context_snapshot(sibling_snapshot, sibling,
                                                        boundary='join')['admitted'])
            (root / 'app' / 'pyproject.toml').write_bytes(b'[project]\n')
            untracked = self.capture(root)
            self.assertIn('app/pyproject.toml', untracked['source']['git_state']['untracked'])
            self.assertFalse(S.compare_context_snapshot(snapshot, boundary='join')['admitted'])
            (root / 'app' / 'pyproject.toml').write_bytes(b'[project]\nname="changed"\n')
            self.assertFalse(S.compare_context_snapshot(untracked, boundary='join')['admitted'])
            self.git(root, 'add', '--', 'app/pyproject.toml')
            staged = self.capture(root)
            self.assertIn('app/pyproject.toml', staged['source']['git_state']['staged'])
            self.assertNotIn('app/pyproject.toml', staged['source']['git_state']['untracked'])
            self.assertFalse(S.compare_context_snapshot(untracked, boundary='join')['admitted'])
            with self.assertRaises(S.SnapshotError):
                S.context_snapshot(root, source_paths=('app/package.json',),
                                   allowed_effect_paths=('app/package.json',))
            with self.assertRaises(S.SnapshotError):
                S.context_snapshot(root, source_paths=('app/package.json',),
                                   target_paths=('app/package.json',))
            with self.assertRaises(S.SnapshotError):
                S.context_snapshot(root, source_scopes=('app',),
                                   membership=(('manifests', ('app',)),),
                                   allowed_effect_paths=('app/package.json',))
            with self.assertRaises(S.SnapshotError):
                S.context_snapshot(root)
            with self.assertRaises(S.SnapshotError):
                S.context_snapshot(base / 'not-a-repository', source_paths=('x',))
            malformed = copy.deepcopy(snapshot)
            malformed['source']['digest_method'] = 'git-head-only'
            with self.assertRaises(S.SnapshotError):
                S.compare_context_snapshot(malformed, boundary='action')
            malformed = copy.deepcopy(snapshot)
            malformed['targets']['app/result.json']['digest_method'] = 'git-head-only'
            with self.assertRaises(S.SnapshotError):
                S.compare_context_snapshot(malformed, boundary='join')
            with self.assertRaises(S.SnapshotError):
                S.compare_context_snapshot(snapshot, boundary='invented')
            unborn_root = base / 'unborn'
            unborn_root.mkdir()
            self.git(unborn_root, 'init', '-q', '-b', 'main')
            (unborn_root / 'manifest.txt').write_bytes(b'new source')
            unborn = S.context_snapshot(unborn_root, source_paths=('manifest.txt',))
            self.assertIsNone(unborn['worktree']['head'])
            self.assertEqual(unborn['worktree']['branch'], 'main')
            self.assertIn('manifest.txt', unborn['source']['git_state']['untracked'])
            original_digest = S.digest_file
            touched = False
            def mutate_after_digest(*args, **kwargs):
                nonlocal touched
                result = original_digest(*args, **kwargs)
                if not touched and args[1] == 'app/package.json':
                    (root / 'app' / 'package.json').write_bytes(b'{"name":"raced"}\n')
                    touched = True
                return result
            with patch.object(S, 'digest_file', side_effect=mutate_after_digest):
                with self.assertRaises(S.SnapshotError) as caught:
                    self.capture(root)
            self.assertTrue(touched)
            self.assertEqual(caught.exception.code, 'SOURCE_CHANGED')


class TestInertCommandAndConstraintRecords(unittest.TestCase):
    """Keep command and constraint references inert at the report boundary."""

    def shortDescription(self):
        return None

    @staticmethod
    def command():
        return {
            'id': 'CMD-1',
            'invocation': {'kind': 'literal_argv',
                           'argv': ['python', '-m', 'unittest', 'tests/My Suite.py']},
            'cwd': '.',
            'prerequisites': ['python-3.14', 'fixture-ready'],
            'evidence_refs': ['E-1'],
            'verification': {'state': 'declared', 'observation_ref': None,
                             'binding': None},
        }

    @classmethod
    def binding(cls, command=None):
        command = command or cls.command()
        return {
            'source_snapshot_id': 'a' * 64,
            'runtime_ref': 'python-3.14',
            'lock_digest': 'b' * 64,
            'prerequisites_digest': 'c' * 64,
            'oracle_ref': 'named-test-outcome',
            'argv': list(command['invocation']['argv']),
            'cwd': command['cwd'],
            'declared_prerequisites': list(command['prerequisites']),
            'environment_digest': 'd' * 64,
        }

    @staticmethod
    def constraint():
        return {
            'id': 'CON-1',
            'kind': 'existing_applicable',
            'source_ref': 'AGENTS.md#test-convention',
            'scope': '.',
            'statement': 'Use the local test convention.',
            'evidence_refs': ['E-1'],
        }

    def test_t010_command_and_constraint_records_positive_controls(self):
        self.assertTrue(hasattr(R, 'validate_command_record'))
        self.assertTrue(hasattr(R, 'validate_constraint_reference'))
        literal = self.command()
        before = copy.deepcopy(literal)
        decoded = R.validate_command_record(
            literal, evidence_ids={'E-1'}, observation_ids=set(),
            current_binding=self.binding())
        self.assertEqual(literal, before)
        self.assertEqual(decoded['invocation']['argv'], literal['invocation']['argv'])
        self.assertEqual(decoded['cwd'], '.')
        self.assertEqual(decoded['verification']['state'], 'declared')
        self.assertEqual(decoded['reported_current_state'], 'declared')
        decoded['invocation']['argv'].append('mutation')
        self.assertEqual(literal, before)
        no_prerequisites = {**literal, 'prerequisites': []}
        self.assertEqual(R.validate_command_record(
            no_prerequisites, evidence_ids={'E-1'}, observation_ids=set(),
            current_binding=self.binding())['prerequisites'], [])
        spaced_executable = self.command()
        spaced_executable['invocation']['argv'][0] = 'C:/Program Files/Python/python.exe'
        self.assertEqual(R.validate_command_record(
            spaced_executable, evidence_ids={'E-1'}, observation_ids=set(),
            current_binding=self.binding(spaced_executable))['invocation']['argv'][0],
            'C:/Program Files/Python/python.exe')
        spaced_executable['verification'] = {
            'state': 'passed', 'observation_ref': 'RUN-PATH',
            'binding': self.binding(spaced_executable),
        }
        self.assertEqual(R.validate_command_record(
            spaced_executable, evidence_ids={'E-1'}, observation_ids={'RUN-PATH'},
            current_binding=self.binding(spaced_executable))['reported_current_state'],
            'passed')

        declaration = self.command()
        declaration['invocation'] = {
            'kind': 'declaration_ref',
            'path': 'package.json',
            'selector': 'scripts.test',
            'text': 'NODE_ENV=ci npm test | tee test.log',
        }
        declared = R.validate_command_record(
            declaration, evidence_ids={'E-1'}, observation_ids=set(),
            current_binding=self.binding())
        self.assertEqual(declared['invocation'], declaration['invocation'])
        self.assertEqual(declared['reported_current_state'], 'declared')
        self.assertNotIn('argv', declared['invocation'])
        declaration['invocation']['text'] = 'cmd /c npm test'
        self.assertEqual(R.validate_command_record(
            declaration, evidence_ids={'E-1'}, observation_ids=set(),
            current_binding=self.binding())['invocation']['text'], 'cmd /c npm test')
        declaration['cwd'] = 'packages/app'
        self.assertEqual(R.validate_command_record(
            declaration, evidence_ids={'E-1'}, observation_ids=set(),
            current_binding=self.binding())['cwd'], 'packages/app')

        observed = self.command()
        observed['verification'] = {
            'state': 'passed', 'observation_ref': 'RUN-1',
            'binding': self.binding(),
        }
        self.assertEqual(R.validate_command_record(
            observed, evidence_ids={'E-1'}, observation_ids={'RUN-1'},
            current_binding=self.binding())['reported_current_state'], 'passed')
        observed['verification']['state'] = 'failed'
        self.assertEqual(R.validate_command_record(
            observed, evidence_ids={'E-1'}, observation_ids={'RUN-1'},
            current_binding=self.binding())['reported_current_state'], 'failed')
        observed['verification'] = {
            'state': 'unknown', 'observation_ref': None, 'binding': None,
        }
        self.assertEqual(R.validate_command_record(
            observed, evidence_ids={'E-1'}, observation_ids=set(),
            current_binding=self.binding())['reported_current_state'], 'unknown')

        existing = self.constraint()
        accepted = R.validate_constraint_reference(existing, evidence_ids={'E-1'})
        self.assertEqual(accepted, existing)
        self.assertNotIn('approval', accepted)
        self.assertNotIn('status', accepted)
        for kind in ('observed_upstream', 'proposed_adoption'):
            candidate = {**existing, 'kind': kind, 'source_ref': 'ADR-007#deployment'}
            normalized = R.validate_constraint_reference(
                candidate, evidence_ids={'E-1'})
            self.assertEqual(normalized['kind'], kind)
            self.assertNotIn('effective', normalized)
            self.assertNotIn('approved', normalized)

    def test_t010_command_and_constraint_records_negative_controls(self):
        self.assertTrue(hasattr(R, 'validate_command_record'))
        self.assertTrue(hasattr(R, 'validate_constraint_reference'))
        base = self.command()
        for bad_invocation in (
            {'kind': 'literal_argv', 'argv': ['NODE_ENV=ci', 'npm', 'test']},
            {'kind': 'literal_argv', 'argv': ['cmd', '/c', 'npm test']},
            {'kind': 'literal_argv', 'argv': ['npm.cmd', 'test']},
            {'kind': 'literal_argv', 'argv': ['npm', 'test', '|', 'tee']},
            {'kind': 'literal_argv', 'argv': ['python -m unittest']},
            {'kind': 'literal_argv', 'argv': ['./scripts/test.sh | tee output']},
            {'kind': 'literal_argv', 'argv': 'python -m unittest'},
            {'kind': 'literal_argv', 'argv': []},
            {'kind': 'literal_argv', 'argv': ['python'], 'text': 'python'},
            {'kind': 'declaration_ref', 'path': 'package.json',
             'selector': 'scripts.test', 'text': 'npm test', 'argv': ['npm', 'test']},
            {'kind': 'declaration_ref', 'path': '../package.json',
             'selector': 'scripts.test', 'text': 'npm test'},
        ):
            with self.subTest(invocation=bad_invocation), self.assertRaises(R.ReportError):
                R.validate_command_record(
                    {**base, 'invocation': bad_invocation},
                    evidence_ids={'E-1'}, observation_ids=set(),
                    current_binding=self.binding())
        for bad_cwd in ('', '..', '../other', 'C:/other', '/other'):
            with self.subTest(cwd=bad_cwd), self.assertRaises(R.ReportError):
                R.validate_command_record(
                    {**base, 'cwd': bad_cwd}, evidence_ids={'E-1'},
                    observation_ids=set(), current_binding=self.binding())
        for mutation in (
            {'approved': True},
            {'authority': 'owner'},
            {'evidence_refs': ['E-MISSING']},
            {'prerequisites': None},
            {'verification': {'state': 'passed', 'observation_ref': None,
                              'binding': self.binding()}},
            {'verification': {'state': 'passed', 'observation_ref': 'RUN-MISSING',
                              'binding': self.binding()}},
            {'verification': {'state': 'passed', 'observation_ref': 'RUN-1',
                              'binding': None}},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(R.ReportError):
                R.validate_command_record(
                    {**base, **mutation}, evidence_ids={'E-1'},
                    observation_ids={'RUN-1'}, current_binding=self.binding())
        observed = self.command()
        observed['verification'] = {
            'state': 'passed', 'observation_ref': 'RUN-1', 'binding': self.binding(),
        }
        declaration = copy.deepcopy(observed)
        declaration['invocation'] = {
            'kind': 'declaration_ref', 'path': 'package.json',
            'selector': 'scripts.test', 'text': 'npm test | tee test.log',
        }
        with self.assertRaises(R.ReportError):
            R.validate_command_record(
                declaration, evidence_ids={'E-1'}, observation_ids={'RUN-1'},
                current_binding=self.binding())
        for key, changed in (
            ('cwd', 'another-package'),
            ('invocation', {'kind': 'literal_argv',
                            'argv': ['python', '-m', 'different_tests']}),
            ('prerequisites', ['different-prerequisite']),
        ):
            mutated = copy.deepcopy(observed)
            mutated[key] = changed
            with self.subTest(changed_command=key):
                result = R.validate_command_record(
                    mutated, evidence_ids={'E-1'}, observation_ids={'RUN-1'},
                    current_binding=self.binding())
                self.assertEqual(result['verification']['state'], 'passed')
                self.assertEqual(result['reported_current_state'], 'unknown')
        for field in self.binding():
            stale = self.binding()
            stale[field] = (['changed'] if field in ('argv', 'declared_prerequisites') else
                            'other-package' if field == 'cwd' else
                            'e' * 64 if field.endswith(('id', 'digest')) else 'changed')
            with self.subTest(stale=field):
                result = R.validate_command_record(
                    observed, evidence_ids={'E-1'}, observation_ids={'RUN-1'},
                    current_binding=stale)
                self.assertEqual(result['verification']['state'], 'passed')
                self.assertEqual(result['reported_current_state'], 'unknown')
        raw_environment = self.binding()
        raw_environment['environment_digest'] = {'TOKEN': 'PRIVATE-CANARY'}
        with self.assertRaises(R.ReportError):
            R.validate_command_record(
                {**observed, 'verification': {
                    'state': 'passed', 'observation_ref': 'RUN-1',
                    'binding': raw_environment}},
                evidence_ids={'E-1'}, observation_ids={'RUN-1'},
                current_binding=self.binding())
        for mutation in (
            {'approved': True},
            {'status': 'approved'},
            {'authority': 'owner'},
            {'effective_authority_refs': ['AGENTS.md']},
            {'kind': 'approved'},
            {'evidence_refs': ['E-MISSING']},
            {'source_ref': ''},
            {'scope': '../other'},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(R.ReportError):
                R.validate_constraint_reference(
                    {**self.constraint(), **mutation}, evidence_ids={'E-1'})


class TestContextInvalidationLocality(unittest.TestCase):
    """T-033: assess real per-document dependencies without self invalidation."""

    def shortDescription(self):
        return None

    @staticmethod
    def _git(root, *args):
        subprocess.run(['git', '-C', str(root), *args], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _fixture(self, base):
        root = base / 'repo'
        root.mkdir()
        self._git(root, 'init', '-q', '-b', 'main')
        for folder in ('a', 'b', '.codearbiter', '.codearbiter/.provenance'):
            (root / folder).mkdir(exist_ok=True)
        (root / 'a/package.json').write_bytes(b'{"name":"a"}\n')
        (root / 'b/AGENTS.md').write_bytes(b'Instructions B\n')
        (root / '.codearbiter/tech-stack.md').write_bytes(b'Tech\n')
        (root / '.codearbiter/code-map.md').write_bytes(b'Map\n')
        self._git(root, 'add', '--', 'a/package.json', 'b/AGENTS.md',
                  '.codearbiter/tech-stack.md', '.codearbiter/code-map.md')
        self._git(root, '-c', 'user.name=Fixture', '-c',
                  'user.email=fixture@example.test', 'commit', '-qm', 'initial')
        membership = (('manifests', ('a',)), ('instructions', ('b',)))
        snapshot = S.context_snapshot(root, source_paths=('a/package.json', 'b/AGENTS.md'),
                                      membership=membership,
                                      target_paths=('.codearbiter/tech-stack.md',
                                                    '.codearbiter/code-map.md'),
                                      allowed_effect_paths=('.codearbiter/.provenance/tech-stack.json',
                                                            '.codearbiter/.provenance/code-map.json',
                                                            '.codearbiter/marker'))
        store = root / '.codearbiter/.provenance'
        for doc, path, predicate, scope in (
                ('tech-stack', 'a/package.json', 'manifests', 'a'),
                ('code-map', 'b/AGENTS.md', 'instructions', 'b')):
            member = next(item for item in snapshot['source']['membership']
                          if item['predicate'] == predicate)
            record = {'schema': 2, 'doc': doc, 'created': '2026-09-27',
                      'document': {'path': f'.codearbiter/{doc}.md',
                                   'digest_method': 'sha256-raw',
                                   'digest': snapshot['targets'][f'.codearbiter/{doc}.md']['digest']},
                      'fields': [{'id': 'FIELD-LOCAL', 'owner_ref': 'fixture:local',
                                  'claims': [{'id': 'CLAIM-LOCAL',
                                              'semantic_review': {'state': 'unreviewed',
                                                                  'reference': None},
                                              'evidence': [
                                                  {'kind': 'content', 'path': path,
                                                   'digest_method': 'sha256-raw',
                                                   'digest': snapshot['source']['files'][path]['digest']},
                                                  {'kind': 'membership', 'predicate': predicate,
                                                   'scope_paths': [scope],
                                                   'digest_method': 'sha256-membership-v1',
                                                   'digest': member['digest']}],
                                              'effective_authority_refs': []}]}]}
            self.assertTrue(P.valid_provenance_record(record))
            (store / f'{doc}.json').write_text(json.dumps(record), encoding='utf-8')
        return root, store, snapshot

    def _assess(self, store, snapshot):
        return P.assess_context_provenance(store, ['tech-stack', 'code-map'], snapshot)

    def test_t033_context_invalidation_locality_positive_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, store, snapshot = self._fixture(Path(tmp))
            before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                      for path in store.iterdir()}
            initial = self._assess(store, snapshot)
            self.assertEqual(initial['documents'], {'tech-stack': 'v2_current',
                                                    'code-map': 'v2_current'})
            (root / '.codearbiter/marker').write_bytes(b'own journal timestamp')
            (root / 'unrelated.py').write_bytes(b'leaf edit\n')
            observed = []
            original_digest = S.digest_file
            def bounded_digest(*args, **kwargs):
                observed.append(args[1])
                self.assertIn(args[1], ('a/package.json', 'b/AGENTS.md',
                                        '.codearbiter/tech-stack.md',
                                        '.codearbiter/code-map.md'))
                return original_digest(*args, **kwargs)
            with patch.object(S, 'digest_file', side_effect=bounded_digest):
                repeat = self._assess(store, snapshot)
            self.assertEqual(repeat['documents'], initial['documents'])
            self.assertTrue(observed)
            self.assertEqual({path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                              for path in store.iterdir()}, before)
            self._git(root, 'add', '--', 'unrelated.py')
            self._git(root, '-c', 'user.name=Fixture', '-c',
                      'user.email=fixture@example.test', 'commit', '-qm', 'unrelated')
            self.assertEqual(self._assess(store, snapshot)['documents'], initial['documents'])
            (root / 'a/pyproject.toml').write_bytes(b'[project]\n')
            changed = self._assess(store, snapshot)
            self.assertEqual(changed['documents'], {'tech-stack': 'v2_stale',
                                                    'code-map': 'v2_current'})
            self.assertEqual(changed['identity'], 'stale')

    def test_t033_context_invalidation_locality_negative_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, store, snapshot = self._fixture(Path(tmp))
            forged = copy.deepcopy(snapshot)
            forged['source']['files']['a/package.json']['digest'] = 'f' * 64
            with self.assertRaises(S.SnapshotError):
                S.compare_context_dependencies(forged,
                    source_paths=('a/package.json',),
                    membership=(('manifests', ('a',)),),
                    target_paths=('.codearbiter/tech-stack.md',))
            (root / 'b/nested').mkdir()
            (root / 'b/nested/AGENTS.md').write_bytes(b'new override\n')
            result = self._assess(store, snapshot)
            self.assertEqual(result['documents'], {'tech-stack': 'v2_current',
                                                   'code-map': 'v2_stale'})
            (root / 'b/nested/AGENTS.md').unlink()
            (root / 'a/package.json').write_bytes(b'{"name":"changed"}\n')
            result = self._assess(store, snapshot)
            self.assertEqual(result['documents'], {'tech-stack': 'v2_stale',
                                                   'code-map': 'v2_current'})
            (root / 'a/package.json').write_bytes(b'{"name":"a"}\n')
            (root / '.codearbiter/code-map.md').write_bytes(b'owner edit\n')
            result = self._assess(store, snapshot)
            self.assertEqual(result['documents'], {'tech-stack': 'v2_current',
                                                   'code-map': 'v2_stale'})
            sibling = Path(tmp) / 'sibling'
            self._git(root, 'worktree', 'add', '-q', '--detach', str(sibling), 'HEAD')
            sibling_store = sibling / '.codearbiter/.provenance'
            sibling_store.mkdir(parents=True)
            for path in store.iterdir():
                (sibling_store / path.name).write_bytes(path.read_bytes())
            reused = P.assess_context_provenance(sibling_store,
                                                  ['tech-stack', 'code-map'], snapshot)
            self.assertNotEqual(reused['identity'], 'current')
            self.assertNotIn('v2_current', reused['documents'].values())
            (root / 'b/AGENTS.md').unlink()
            missing = self._assess(store, snapshot)
            self.assertNotEqual(missing['documents']['code-map'], 'v2_current')
            self.assertFalse(missing['verified_fresh'])


def main(argv=None):
    selectors = sys.argv[1:] if argv is None else argv
    allowed = {'TestReportEnvelope': TestReportEnvelope, 'TestInertDigest': TestInertDigest,
               'TestMembershipCoverage': TestMembershipCoverage,
               'TestContextSnapshot': TestContextSnapshot,
               'TestInertCommandAndConstraintRecords': TestInertCommandAndConstraintRecords,
               'TestContextInvalidationLocality': TestContextInvalidationLocality}
    if any(s not in allowed for s in selectors) or len(selectors) != len(set(selectors)):
        print('Unknown or repeated contract-test selector',file=sys.stderr); return 2
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(allowed[s])
                               for s in selectors or allowed)
    if not suite.countTestCases(): return 2
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == '__main__':
    raise SystemExit(main())
