#!/usr/bin/env python3
"""Source-only D1 design checks. NOT the production handoff validator or host proof.

The native collector runs python -m unittest -v check-d1 from this directory.
Direct source-only use may run Python -B. Assertions read adjacent proposal data;
unittest imports may create ignored bytecode caches. This checker never imports
product code, executes case operations, or confers authority.
"""
from pathlib import Path
import datetime
import copy
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


def patched_fixture(base, patches):
    """Materialize design inputs only; this is not a packet validator."""
    result = copy.deepcopy(base)
    for patch in patches:
        parts = patch['path'].split('/')[1:]
        assert patch['path'].startswith('/') and parts and all(parts)
        parent = result
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        if patch['op'] == 'set':
            old = parent[key]
            assert old != patch['value'], patch
            parent[key] = patch['value']
        elif patch['op'] == 'append':
            target = parent[key]
            assert isinstance(target, list)
            target.append(patch['value'])
        elif patch['op'] == 'remove':
            del parent[key]
        else:
            raise AssertionError('unsupported design patch')
    return result


def semantic_design_effect(rule_id, negative, positive):
    """Pin source-control contrasts; no product packet is validated here."""
    if rule_id == 'SEM-01':
        return negative['evidence'][-1]['id'] == 'E-01' and positive['evidence'][-1]['id'] == 'E-05'
    if rule_id == 'SEM-02':
        return negative['symptom']['expected'] is None and bool(positive['symptom']['expected_evidence_ids'])
    if rule_id == 'SEM-03':
        return not negative['hypotheses'][0]['supporting_evidence_ids'] and positive['hypotheses'][0]['supporting_evidence_ids'] == ['E-02']
    if rule_id == 'SEM-04':
        return not negative['disposition']['cause_ids'] and positive['disposition']['cause_ids'] == ['H-01']
    if rule_id == 'SEM-05':
        return negative['regression']['snapshot_id'] == 'S-99' and positive['regression']['snapshot_id'] == 'S-01'
    if rule_id == 'SEM-06':
        return negative['reproduction']['recipe'] is None and len(positive['reproduction']['recipe']['steps']) == 2
    if rule_id == 'SEM-07':
        return negative['checks'][0]['status'] == 'planned' and negative['checks'][0]['observed'] is not None and positive['checks'][0]['status'] == 'completed'
    if rule_id == 'SEM-08':
        return negative['disposition']['blockers'][0]['resume_condition'] == '' and bool(positive['disposition']['blockers'][0]['resume_condition'])
    if rule_id == 'SEM-09':
        return negative['next_step']['target'] == 'fix' and positive['next_step']['target'] == 'none'
    if rule_id == 'SEM-10':
        return 'authorization' in negative['next_step']['action'] and 'decide' in positive['next_step']['action']
    if rule_id == 'SEM-11':
        return (negative['snapshots'][0]['runtime_identity'] is None
                and negative['snapshots'][0]['limitations'] is None
                and positive['snapshots'][0]['runtime_identity'] is None
                and bool(positive['snapshots'][0]['limitations']))
    if rule_id == 'SEM-12':
        return negative['evidence'][0]['locator'].startswith('curl https://invalid.example/') and positive['evidence'][0]['locator'].startswith('rm -rf /nonexistent-synthetic-canary')
    if rule_id == 'SEM-13':
        return len(negative['evidence'][0]['observation']) == 2001 and len(positive['evidence'][0]['observation']) == 2000
    if rule_id == 'SEM-14':
        return negative['protocol'] == 'codearbiter.debug-handoff/9.9.9' and positive['protocol'] == 'codearbiter.debug-handoff/1.0.0'
    if rule_id == 'SEM-15':
        return negative['evidence'][3]['id'] == 'E-99' and not negative['hypotheses'][0]['opposing_evidence_ids'] and positive['evidence'][3]['id'] == 'E-04'
    if rule_id == 'SEM-16':
        return negative['regression']['reuse_existing'] is True and negative['regression']['candidate_test_id'] is None and positive['regression']['reuse_existing'] is False and bool(positive['regression']['candidate_test_id'])
    if rule_id == 'SEM-17':
        return negative['next_step']['action'] is None and bool(positive['next_step']['action'])
    if rule_id == 'SEM-18':
        return bool(negative['snapshots'][0]['fingerprint']) and negative['snapshots'][0]['fingerprint_recipe'] is None and positive['snapshots'][0]['fingerprint_recipe'] == 'debug-local/1'
    if rule_id == 'SEM-19':
        return negative['checks'][0]['exit_code'] is False and type(positive['checks'][0]['exit_code']) is float and positive['checks'][0]['exit_code'] == 2.0
    raise AssertionError('unmapped semantic rule')


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
        self.assertIn('semantic_fixtures',DATA)
        self.assertIn('semantic_controls',DATA)
        fixtures=DATA['semantic_fixtures']
        self.assertEqual(set(fixtures),{'code','noncode','design','no_action','unresolved'})
        expected_kinds={'code':'confirmed_code_defect','noncode':'confirmed_noncode_cause',
                        'design':'design_question','no_action':'no_action','unresolved':'unresolved'}
        for name, packet in fixtures.items():
            with self.subTest(base=name):
                self.assertEqual(set(packet),{'protocol','case_id','request','snapshots','symptom',
                                              'reproduction','hypotheses','checks','evidence',
                                              'disposition','next_step','regression'})
                self.assertEqual(packet['protocol'],'codearbiter.debug-handoff/1.0.0')
                self.assertEqual(packet['disposition']['kind'],expected_kinds[name])
                self.assertEqual(packet['regression'] is not None,name=='code')
                self.assertEqual(set(packet['request']),{'intent','request_ref','scope','restrictions'})
                self.assertEqual(set(packet['symptom']),{'observed','expected','expected_evidence_ids'})
                self.assertEqual(set(packet['reproduction']),{'status','recipe','evidence_ids','limitations'})
                self.assertEqual(set(packet['disposition']),{'kind','rationale','evidence_ids','cause_ids','blockers'})
                self.assertEqual(set(packet['next_step']),{'target','owner','action','completion_evidence'})
                for snapshot in packet['snapshots']:
                    self.assertEqual(set(snapshot),{'id','repository','worktree','commit','dirty_state',
                                                    'fingerprint','fingerprint_recipe','runtime_identity','limitations'})
                    if snapshot['fingerprint'] is None or snapshot['runtime_identity'] is None:
                        self.assertTrue(snapshot['limitations'])
                for hypothesis in packet['hypotheses']:
                    self.assertEqual(set(hypothesis),{'id','mechanism','discriminator','status',
                                                       'supporting_evidence_ids','opposing_evidence_ids','limitations'})
                for check in packet['checks']:
                    self.assertEqual(set(check),{'id','operation','cwd','status','exit_code','expectation',
                                                 'observed','evidence_ids','authorization_basis','side_effects'})
                for evidence in packet['evidence']:
                    self.assertEqual(set(evidence),{'id','kind','snapshot_id','locator','observation',
                                                    'observed_at','check_id','coverage','limitations'})
                    if evidence['snapshot_id'] is None or evidence['observed_at'] is None:
                        self.assertTrue(evidence['limitations'])
                if packet['regression'] is not None:
                    self.assertEqual(set(packet['regression']),{'basis','snapshot_id','obligation','oracle',
                                                                 'candidate_test_id','reuse_existing','evidence_ids'})
                if packet['reproduction']['recipe'] is not None:
                    self.assertEqual(set(packet['reproduction']['recipe']),{'steps','cwd','preconditions','failure_signature'})
                evidence_ids={e['id'] for e in packet['evidence']}
                self.assertEqual(len(evidence_ids),len(packet['evidence']))
                self.assertTrue(set(packet['disposition']['evidence_ids']) <= evidence_ids)
                self.assertTrue(set(packet['symptom']['expected_evidence_ids']) <= evidence_ids)
                for hypothesis in packet['hypotheses']:
                    self.assertTrue(set(hypothesis['supporting_evidence_ids']+hypothesis['opposing_evidence_ids']) <= evidence_ids)
                for check in packet['checks']:
                    self.assertTrue(set(check['evidence_ids']) <= evidence_ids)
                if name in ('design','unresolved'):
                    self.assertTrue(all(h['status']=='inconclusive' for h in packet['hypotheses']))
                if name=='unresolved':
                    self.assertEqual(packet['reproduction']['status'],'unavailable')
                    self.assertTrue(packet['reproduction']['limitations'])
                if name=='no_action':
                    self.assertEqual(packet['symptom']['observed'],packet['symptom']['expected'])
                    self.assertEqual(packet['next_step']['target'],'none')
        scenarios={r['id']:r for r in DATA['scenarios']}
        controls=DATA['semantic_controls']
        self.assertEqual([r['rule_id'] for r in controls],[r['id'] for r in rows])
        expected_scenarios={
            'SEM-01':'V20','SEM-02':'V13','SEM-03':'V13','SEM-04':'V13',
            'SEM-05':'V21','SEM-06':'V19','SEM-07':'V39','SEM-08':'V13',
            'SEM-09':'V13','SEM-10':'V17','SEM-11':'V09','SEM-12':'V06',
            'SEM-13':'V20','SEM-14':'V40','SEM-15':'V10','SEM-16':'V38',
            'SEM-17':'V37','SEM-18':'V09','SEM-19':'V20',
        }
        expected_bases={
            'SEM-08':'unresolved','SEM-09':'no_action','SEM-10':'design',
            **{'SEM-%02d'%i:'code' for i in list(range(1,8))+list(range(11,20))},
        }
        expected_results={
            'SEM-08':('reject','accept'),
            'SEM-09':('reject','accept'),
            'SEM-10':('fail_model','pass_model'),
            'SEM-12':('accept_inert_no_effect','accept_inert_no_effect'),
            'SEM-15':('fail_model','pass_model'),
            **{'SEM-%02d'%i:('reject','accept') for i in list(range(1,8))+[11,13,14,16,17,18,19]},
        }
        self.assertEqual(set(expected_bases),set(expected_scenarios))
        self.assertEqual(set(expected_results),set(expected_scenarios))
        self.assertEqual(len({r['fixture_id'] for r in controls}),19)
        for row in rows:
            self.assertTrue(row['negative'] and row['positive'] and row['oracle'])
            self.assertTrue(set(row['layers']) <= {'D','H','M'})
            self.assertEqual(row['product_status'],'PENDING')
        for control in controls:
            with self.subTest(control=control['rule_id']):
                self.assertEqual(control['scenario_id'],expected_scenarios[control['rule_id']])
                self.assertIn(control['layer'],scenarios[control['scenario_id']]['layers'])
                self.assertIn(control['layer'],next(r for r in rows if r['id']==control['rule_id'])['layers'])
                if control['rule_id'] in ('SEM-08','SEM-09'):
                    self.assertEqual(control['layer'],'D')
                    self.assertEqual(control['scenario_variant'],
                                     'unresolved' if control['rule_id']=='SEM-08' else 'no_action')
                    self.assertEqual(scenarios[control['scenario_id']]['variants'][control['scenario_variant']],
                                     control['scenario_variant'])
                self.assertRegex(control['fixture_id'],r'^D1-SEM-[0-9]{2}$')
                self.assertEqual(control['fixture_id'],'D1-'+control['rule_id'])
                self.assertEqual(control['base_fixture'],expected_bases[control['rule_id']])
                self.assertTrue(control['negative_patches'])
                self.assertTrue(control['positive_patches'])
                self.assertEqual((control['expected_negative'],control['expected_positive']),expected_results[control['rule_id']])
                self.assertTrue(control['negative_assertion'] and control['positive_assertion'])
                if control['rule_id']=='SEM-11':
                    self.assertEqual(control['positive_assertion'],
                                     'Unknown runtime identity is accepted with an explicit limitation; consumer rechecks current runtime.')
                base=fixtures[control['base_fixture']]
                negative=patched_fixture(base,control['negative_patches'])
                positive=patched_fixture(base,control['positive_patches'])
                self.assertNotEqual(negative,base)
                self.assertNotEqual(positive,base)
                self.assertNotEqual(negative,positive)
                self.assertTrue(semantic_design_effect(control['rule_id'],negative,positive))
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
            num=int(task[1:]); self.assertEqual(row[-1].strip(),'SOURCE_COMPLETE' if num<5 else 'DRAFT_READY' if num==5 else 'BLOCKED' if num==6 else 'PENDING')
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
        review_criteria={
            'V36':['AC-17','AC-24','AC-25'],
            'V37':['AC-10','AC-13','AC-16'],
            'V38':['AC-15','AC-18'],
            'V39':['AC-07','AC-15'],
            'V40':['AC-14'],
            'V41':['AC-27','AC-28'],
        }
        for scenario, criteria in review_criteria.items():
            with self.subTest(review_scenario=scenario):
                self.assertCountEqual(byid[scenario]['criteria'],criteria)
        self.assertEqual(byid['V01']['required_disposition'],'confirmed_code_defect')
        self.assertEqual(byid['V11']['required_disposition'],'unresolved')
        self.assertEqual(len(byid['V13']['variants']),5); self.assertEqual(len(byid['V25']['variants']),2); self.assertEqual(len(byid['V31']['variants']),3)
        self.assertEqual(DATA['independent_oracle_review'],'PENDING')
        self.assertIn('pretrial_classification',DATA)
        oracle=DATA['pretrial_classification']
        self.assertEqual(oracle['status'],'DESIGN_FROZEN_EXECUTABLE_BINDING_PENDING')
        self.assertEqual(oracle['repetitions_per_arm_per_configuration'],3)
        fixed={
            'V01':{'default':('solvable','confirmed_code_defect')},
            'V07':{'default':('solvable','confirmed_code_defect')},
            'V08':{'default':('solvable','confirmed_code_defect')},
            'V11':{'default':('blocked','unresolved')},
            'V12':{'default':('blocked','unresolved')},
            'V15':{'default':('solvable','no_action')},
            'V17':{'default':('blocked','design_question')},
            'V18':{'default':('solvable','confirmed_noncode_cause')},
            'V21':{'default':('solvable','confirmed_code_defect')},
            'V23':{'default':('solvable','confirmed_code_defect')},
            'V24':{'default':('solvable','confirmed_code_defect')},
            'V25':{'supported_target_plus_unrelated_red':('solvable','confirmed_code_defect'),
                   'setup_only_without_target_proof':('blocked','unresolved')},
            'V26':{'default':('solvable','confirmed_code_defect')},
            'V31':{'diagnosis_only':('solvable','confirmed_code_defect'),
                   'repair_authorized':('solvable','confirmed_code_defect'),
                   'real_followup_authorized':('solvable','confirmed_code_defect')},
        }
        fixed_basis={
            'V01':{'default':'Synthetic supported defect with target evidence.'},
            'V07':{'default':'Off-by-one target and neighboring boundary discriminator.'},
            'V08':{'default':'Supported multiple contributors remain inspectable.'},
            'V11':{'default':'Required target telemetry is unavailable; resume after owner supplies it.'},
            'V12':{'default':'Safe reproduction needs a separately authorized isolated experiment.'},
            'V15':{'default':'Positive contract evidence establishes expected rejection.'},
            'V17':{'default':'Conflicting intended behavior needs an owner decision.'},
            'V18':{'default':'Supported operational cause with separately named owner.'},
            'V21':{'default':'Observed or causal-trace regression is available.'},
            'V23':{'default':'Supported defect with repair boundary separated.'},
            'V24':{'default':'Adequate existing target-red test is identified.'},
            'V25':{'supported_target_plus_unrelated_red':'Target-red proof remains valid despite unrelated red.',
                   'setup_only_without_target_proof':'Only setup failure exists; target oracle is not established.'},
            'V26':{'default':'Deterministic defect admits a new target-red regression.'},
            'V31':{'diagnosis_only':'Defect can be diagnosed; repair authority is absent.',
                   'repair_authorized':'Defect and authorized repair are separate checks.',
                   'real_followup_authorized':'Defect is supported; follow-up authority separately checked.'},
        }
        self.assertEqual(set(oracle['cases']),set(DATA['paired_ids']))
        self.assertEqual({case:set(variants) for case,variants in fixed_basis.items()},
                         {case:set(variants) for case,variants in fixed.items()})
        for case_id, variants in fixed.items():
            with self.subTest(case=case_id):
                self.assertEqual(set(oracle['cases'][case_id]),set(variants))
                for variant, (classification, disposition) in variants.items():
                    cell=oracle['cases'][case_id][variant]
                    self.assertEqual((cell['classification'],cell['expected_disposition']),(classification,disposition))
                    self.assertTrue(cell['ground_truth_basis'])
                    self.assertEqual(cell['ground_truth_basis'],fixed_basis[case_id][variant])
                    self.assertEqual(cell['product_status'],'PENDING')
                    self.assertNotEqual((classification,disposition),('solvable','unresolved'))

    def test_original_examples_retained(self):
        self.assertEqual(DATA['original_examples'],[
            'valid-unresolved','valid-code-defect-causal-trace',
            'valid-code-defect-existing-red','valid-noncode-with-authority-blocker',
            'valid-design-question','valid-no-action',
            'invalid-unknown-authority-field','invalid-protocol',
            'invalid-no-action-task','invalid-boolean-exit-code',
            'invalid-dangling-evidence','invalid-duplicate-evidence-id',
            'invalid-planned-check-as-reproduction',
            'invalid-conflicting-evidence-reference',
        ])
        self.assertEqual(len(DATA['original_examples']),14)
        self.assertEqual(len(set(DATA['original_examples'])),14)
        self.assertEqual(sum(x.startswith('valid-') for x in DATA['original_examples']),6)
        self.assertEqual(sum(x.startswith('invalid-') for x in DATA['original_examples']),8)

    def test_native_adoption_not_fabricated(self):
        env=json.loads((ROOT/'D1-ENVIRONMENT.json').read_text(encoding='utf-8'))
        self.assertTrue(env['workflow_preflight_present'])
        self.assertTrue(env['workflow_preflight']['resources_available'])
        self.assertFalse(env['workflow_preflight']['live_host_verified'])
        self.assertEqual(env['workflow_preflight']['missing'],[])
        self.assertIsNone(env['approval_receipt'])
        self.assertEqual(env['adoption_status'],'DRAFT_PAIR_READY_FOR_REVIEW')
        for key in ['native_spec','native_plan']:
            record=env[key]
            self.assertTrue(record['valid']); self.assertEqual(record['gate'],'ready')
            self.assertEqual(record['authority']['state'],'draft')
            self.assertFalse(record['authority']['authority_verified'])
            for field in ['model_sha256','normative_sha256']:
                self.assertRegex(record[field],r'^[0-9a-f]{64}$')
        binding=env['plan_spec_binding']
        self.assertEqual(binding['binding_mode'],'draft_preview')
        self.assertEqual(binding['artifact_id'],env['native_spec']['artifact_id'])
        self.assertEqual(binding['normative_sha256'],env['native_spec']['normative_sha256'])
        mapping=env['external_id_correspondence']
        self.assertEqual(mapping['criteria'],{'AC-%02d'%i:'AC-%03d'%i for i in range(1,29)})
        self.assertEqual(mapping['scenarios'],{'V%02d'%i:'SCN-%03d'%i for i in range(1,42)})
        self.assertEqual(mapping['parent_tasks'],{'T%02d'%i:'T-%03d'%i for i in range(1,41)})
        self.assertEqual(env['native_task_count'],40+env['qualification_child_count'])
        self.assertEqual(env['qualification_child_count'],83)
        self.assertEqual(env['t06_status'],'BLOCKED')
        self.assertEqual(env['prerequisite_scope_limit']['status'],'UNRESOLVED_BEFORE_APPROVAL')
        self.assertFalse(env['historical_probe']['workflow_preflight_present'])
        collectors=json.loads((ROOT/'D1-COLLECTORS.json').read_text(encoding='utf-8'))
        self.assertEqual(collectors['native_plan']['model_sha256'],env['native_plan']['model_sha256'])
        self.assertEqual(collectors['reproduced_before']['rejected'],150)
        self.assertEqual(collectors['verification_rows'],150)
        self.assertEqual(collectors['admitted'],150); self.assertEqual(collectors['rejected'],0)
        self.assertEqual(collectors['availability'],{'existing':31,'proposed':119})
        declarations=collectors['declarations']
        self.assertEqual(len(declarations),150)
        self.assertEqual(len({(r['task'],r['row']) for r in declarations}),150)
        for row in declarations:
            if row['profile']=='exit-only/0.1.0':
                self.assertFalse(row['required_tests'])
                self.assertEqual(row['availability'],'existing')
                self.assertIn(row['argv'],[
                    ['python','tools/build-surface.py','--check'],
                    ['python','.github/scripts/check_routing_index_parity.py'],
                ])
            else:
                self.assertEqual(row['profile'],'python-unittest-text/0.1.0')
                self.assertEqual(row['argv'][1:3],['-m','unittest'])
                self.assertTrue(row['required_tests'])
                self.assertTrue(all(re.fullmatch(r'test_[a-z0-9_]+',name) for name in row['required_tests']))
            if row['availability']=='proposed':
                self.assertEqual(row['evidence_kind'],'PLANNED_NOT_EXECUTED')
        d1=collectors['existing_source_observations']['D1']
        self.assertEqual(d1['argv'],['python','-m','unittest','-v','check-d1'])
        self.assertEqual(d1['cwd'],'docs/proposals/debug-correctness')
        self.assertEqual(d1['exit'],0); self.assertTrue(d1['collector_success'])
        self.assertEqual(set(d1['required_tests']),set(unittest.defaultTestLoader.getTestCaseNames(D1DesignTest)))
        self.assertEqual({r['name'] for r in d1['collector_results']},set(d1['required_tests']))
        controls={r['control']:r['result'] for r in collectors['negative_controls']}
        self.assertEqual(controls['missing_actual_named_result'],'MISSING_TEST_RESULT')
        self.assertEqual(controls['duplicate_actual_named_result'],'DUPLICATE_TEST_RESULT')
        self.assertEqual(controls['empty_output_for_each_proposed_declaration'],'MISSING_TEST_RESULT')
        board=collectors['legacy_board_sync_observation']
        self.assertFalse(board['implementation_performed'])
        self.assertEqual(len(board['emitted_registered_names']),11)
        for task in ['T-024','T-033']:
            row=next(r for r in declarations if r['task']==task and 'test_board_sync.py' in r['argv'])
            self.assertEqual(row['availability'],'proposed')
            self.assertEqual(row['required_tests'],board['emitted_registered_names'])
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
