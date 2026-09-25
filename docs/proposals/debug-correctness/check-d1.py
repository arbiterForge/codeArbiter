#!/usr/bin/env python3
"""Source-only D1 design checks. NOT the production handoff validator or host proof.

Run with Python -B. Reads only adjacent proposal data; never imports product code,
executes case operations, changes a repository, or confers authority.
"""
from pathlib import Path
import datetime
from decimal import Decimal, InvalidOperation
import json
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / 'D1-CASES.json').read_text(encoding='utf-8'))
TS = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]{1,9})?(?:[Zz]|[+-]([0-9]{2}):([0-9]{2}))')
NUMBER = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?')
SPACE = set(range(9,14)) | {32,133,160,5760,8232,8233,8239,8287,12288} | set(range(8192,8203))


def timestamp(value):
    match = TS.fullmatch(value)
    if not match:
        return False
    y,m,d,h,minute,s = map(int, match.groups()[:6])
    try:
        datetime.date(y,m,d)
    except ValueError:
        return False
    return h < 24 and minute < 60 and s < 60 and (match[7] is None or (int(match[7]) < 24 and int(match[8]) < 60))


def integer_lexeme(value):
    if not NUMBER.fullmatch(value):
        return False
    try:
        dec = Decimal(value)
        digits, exponent = dec.as_tuple().digits, dec.as_tuple().exponent
    except (InvalidOperation, ValueError):
        return False
    if not dec.is_finite():
        return False
    if not any(digits) or exponent >= 0:
        return True
    trailing = next((i for i,x in enumerate(reversed(digits)) if x), len(digits))
    return exponent + trailing >= 0


def primitive(row):
    kind,value = row['kind'],row['input']
    if kind == 'timestamp': return timestamp(value)
    if kind == 'integer_lexeme': return integer_lexeme(value)
    if kind == 'case_id': return re.fullmatch(r'DBG-[A-Za-z0-9][A-Za-z0-9_-]{2,63}',value) is not None
    if kind == 'evidence_id': return re.fullmatch(r'E-[0-9]{2,4}',value) is not None
    if kind == 'text':
        text = value['value']
        return len(text) <= value['limit'] and any(ord(c) not in SPACE for c in text) and all(not 0xD800 <= ord(c) <= 0xDFFF for c in text)
    raise AssertionError('unknown reference primitive')


class D1DesignTest(unittest.TestCase):
    def test_profile_vectors(self):
        self.assertEqual(len({v['id'] for v in DATA['primitive_vectors']}), len(DATA['primitive_vectors']))
        for row in DATA['primitive_vectors']:
            with self.subTest(vector=row['id']): self.assertEqual(primitive(row),row['expected'])

    def test_semantic_matrix(self):
        rows=DATA['semantic_negative_obligations']
        self.assertEqual([r['id'] for r in rows],['SEM-%02d'%i for i in range(1,20)])
        for row in rows:
            self.assertTrue(row['negative'] and row['positive'] and row['oracle'])
            self.assertTrue(set(row['layers']) <= {'D','H','M'})
            self.assertEqual(row['product_status'],'PENDING')
        self.assertIn('M', rows[9]['layers'])
        self.assertEqual(rows[14]['layers'],['M'])

    def test_plan_coverage_and_graph(self):
        text=(ROOT/'PLAN.md').read_text(encoding='utf-8')
        rows=[r.split('|')[1:-1] for r in text.splitlines() if re.match(r'^\| T\d\d \|',r)]
        tasks={r[0].strip():r for r in rows}
        self.assertEqual(len(rows),40); self.assertEqual(len(tasks),40)
        self.assertEqual(set(tasks),{'T%02d'%i for i in range(1,41)})
        covered=set()
        for task,row in tasks.items():
            ids=set(re.findall(r'AC-\d\d',row[3])); self.assertTrue(ids); covered.update(ids)
            num=int(task[1:]); self.assertEqual(row[-1].strip(),'SOURCE_COMPLETE' if num<5 else 'BLOCKED' if num<7 else 'PENDING')
        self.assertEqual(covered,{'AC-%02d'%i for i in range(1,29)})
        graph={t:re.findall(r'T\d\d',r[4]) for t,r in tasks.items()}
        visiting=set(); visited=set()
        def visit(task):
            self.assertNotIn(task,visiting)
            if task in visited:return
            self.assertIn(task,tasks); visiting.add(task)
            for parent in graph[task]:visit(parent)
            visiting.remove(task); visited.add(task)
        for task in tasks:visit(task)
        self.assertIn('T34',graph['T32']); self.assertIn('T36',graph['T32'])

    def test_scenario_inventory_and_oracles(self):
        rows=DATA['scenarios']
        self.assertEqual([r['id'] for r in rows],['V%02d'%i for i in range(1,42)])
        self.assertEqual(len(DATA['paired_ids']),14); self.assertEqual(DATA['candidate_safety_ids'],['V05','V06','V22'])
        self.assertEqual(DATA['repetitions_per_arm_per_configuration'],3)
        for row in rows:
            self.assertTrue(row['required_behavior'] and row['criteria'])
            self.assertEqual(row['product_status'],'PENDING')
        byid={r['id']:r for r in rows}
        self.assertEqual(byid['V01']['required_disposition'],'confirmed_code_defect')
        self.assertEqual(byid['V11']['required_disposition'],'unresolved')
        self.assertEqual(len(byid['V13']['variants']),5); self.assertEqual(len(byid['V25']['variants']),2); self.assertEqual(len(byid['V31']['variants']),3)
        self.assertEqual(DATA['independent_oracle_review'],'PENDING')

    def test_original_examples_retained(self):
        self.assertEqual(len(DATA['original_examples']),14)
        self.assertEqual(len(set(DATA['original_examples'])),14)
        self.assertEqual(sum(x.startswith('valid-') for x in DATA['original_examples']),6)
        self.assertEqual(sum(x.startswith('invalid-') for x in DATA['original_examples']),8)

    def test_native_adoption_not_fabricated(self):
        env=json.loads((ROOT/'D1-ENVIRONMENT.json').read_text(encoding='utf-8'))
        self.assertFalse(env['workflow_preflight_present'])
        for key in ['native_spec','native_plan','approval_receipt']:self.assertIsNone(env[key])
        self.assertEqual(env['adoption_status'],'BLOCKED_INSTALLED_WORKFLOW_MISMATCH')
        proof=json.loads((ROOT/'D1-OWNERSHIP.json').read_text(encoding='utf-8'))
        self.assertFalse(proof['pr854']['merged'])
        self.assertTrue(all(row['byte_identical'] for row in proof['debug_comparison']))

    def test_adjacent_links(self):
        for path in ROOT.glob('*.md'):
            for link in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
                if re.match(r'^[A-Z][A-Z0-9-]*\.(md|json)$',link):
                    self.assertTrue((ROOT/link).is_file(),(path.name,link))


if __name__ == '__main__':
    if len(sys.argv)>1:
        print('This preparation checker accepts no selectors; run the complete finite suite.',file=sys.stderr)
        sys.exit(2)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(D1DesignTest)
    assert suite.countTestCases()>0
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'boundary':'source-only design checks; no product validation','tests':result.testsRun,'primitive_vectors':len(DATA['primitive_vectors']),'semantic_rows':len(DATA['semantic_negative_obligations']),'scenarios':len(DATA['scenarios']),'success':result.wasSuccessful()}))
    sys.exit(0 if result.wasSuccessful() else 1)
