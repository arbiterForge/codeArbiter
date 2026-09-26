#!/usr/bin/env python3
"""codeArbiter -- test-owned usage observations, not a dispatcher or scorer.

This file owns the small observation contract and generates its JSON Schema view.
It interprets recorded measurements only. References and identity hashes do not
prove authenticity, containment, correctness, approval, or authorization to spend.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
import copy
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / '.github/fixtures/context-onboarding/observation.schema.json'
MAX_BYTES = 256 * 1024


def _obj(properties):
    return {'type': 'object', 'additionalProperties': False,
            'required': list(properties), 'properties': properties}


def _text(nullable=False, pattern=None):
    rule = {'type': ['string', 'null'] if nullable else 'string', 'minLength': 1, 'maxLength': 256}
    if pattern: rule['pattern'] = pattern
    return rule


def _number(nullable=True, minimum=0, maximum=10**12):
    return {'type': ['integer', 'null'] if nullable else 'integer', 'minimum': minimum, 'maximum': maximum}


def observation_schema():
    """Generate the only checked-in view of this test-owned shape contract."""
    ident = _text(pattern=r'^[A-Za-z][A-Za-z0-9_.-]{0,63}$')
    digest = _text(True, r'^[0-9a-f]{64}$')
    usage = _obj({
        'source': {'enum': ['provider', 'host', 'unavailable']}, 'reference': _text(True),
        'input_convention': {'enum': ['includes_cache', 'excludes_cache', 'unknown']},
        **{key: _number() for key in ('input_tokens','cache_read_tokens','cache_write_tokens','output_tokens')}})
    launch = _obj({'attempt_id': ident, 'role': {'enum': ['scout','synthesis','review','task']},
                   'assignment_id': ident, 'parent_assignment_id': {**ident, 'type': ['string','null']},
                   'depth': _number(False, maximum=128), 'retry': _number(False, maximum=128)})
    attempt = _obj({'attempt_id': ident, 'status': {'enum': ['completed','failed','cancelled','oversize']},
                    'elapsed_ms': _number(), 'tool_calls': _number(), 'usage': usage,
                    'loaded_context': _obj({'bytes': _number(),
                        'basis': {'enum': ['effective_input','loader_event','self_report','unavailable']},
                        'reference': _text(True)}),
                    'cost': _obj({'amount': _text(True,r'^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,12})?$'),
                                  'currency': _text(True,r'^[A-Z]{3}$'), 'source_ref': _text(True)})})
    schema = _obj({
        'schema_version': {'const': 1, 'type': 'integer'}, 'run_id': ident,
        'evidence_kind': {'enum': ['static','synthetic_loading','host_loading','task_behavior']},
        'profile': _obj({**{key: _text(True) for key in ('host_name','host_version','package_version','platform','model','provider')},
                         'package_sha256': digest, 'settings_sha256': digest}),
        'snapshot_sha256': digest, 'launch_inventory_complete': {'type': 'boolean'},
        'launches': {'type': 'array', 'maxItems': 128, 'items': launch},
        'observations': {'type': 'array', 'maxItems': 128, 'items': attempt},
        'bounds': _obj({'max_scout_attempts': _number(False,1,24), 'max_tokens': _number(True,1),
                        'max_tool_calls': _number(True,1), 'deadline_ms': _number(True,1)}),
        'elapsed_ms': _number(), 'task_result': {'enum': ['not_run','passed','failed','inconclusive']},
        'independent_oracle_ref': _text(True)})
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema',
            'title': 'Test-owned brownfield observation v1', **schema}


def _require(ok, message):
    if not ok: raise ValueError(message)


def _shape(value, rule, field='observation'):
    """Check only the finite schema subset generated above; refuse extensions."""
    allowed = {'$schema','title','type','const','enum','required','properties','additionalProperties',
               'items','maxItems','minLength','maxLength','pattern','minimum','maximum'}
    _require(not set(rule)-allowed, 'Unsupported observation-schema keyword')
    types = rule.get('type', [])
    if isinstance(types, str): types = [types]
    actual = {dict:'object', list:'array', str:'string', int:'integer', bool:'boolean', type(None):'null'}.get(type(value))
    _require(not types or actual in types, 'Invalid type at '+field)
    if 'const' in rule: _require(value == rule['const'], 'Wrong version at '+field)
    if 'enum' in rule: _require(type(value) is str and value in rule['enum'], 'Unknown enum at '+field)
    if value is None: return
    if type(value) is dict:
        _require(rule.get('additionalProperties') is False, 'Observation objects must be closed')
        _require(set(value) == set(rule['required']) == set(rule['properties']), 'Wrong fields at '+field)
        for key, child in rule['properties'].items(): _shape(value[key],child,field+'.'+key)
    elif type(value) is list:
        _require(len(value) <= rule['maxItems'], 'Array too large at '+field)
        for child in value: _shape(child,rule['items'],field+'[]')
    elif type(value) is str:
        _require(rule.get('minLength',0) <= len(value) <= rule.get('maxLength',256), 'Text limit at '+field)
        _require(not any(ord(c)<32 or 0xD800 <= ord(c) <= 0xDFFF for c in value), 'Invalid text at '+field)
        if 'pattern' in rule: _require(re.fullmatch(rule['pattern'],value) is not None,'Invalid value at '+field)
    elif type(value) is int:
        _require(rule.get('minimum',0) <= value <= rule.get('maximum',10**12), 'Number limit at '+field)


def _unique_pairs(pairs):
    result = {}
    for key,value in pairs:
        _require(key not in result,'Duplicate observation key'); result[key]=value
    return result


def decode_observation(raw):
    """Reject duplicate-key, nonfinite, huge, and over-nested recorded input."""
    _require(type(raw) is bytes and len(raw)<=MAX_BYTES,'Observation byte limit/type')
    text=raw.decode('utf-8'); depth=0; string=escaped=False
    for char in text:
        if string:
            if escaped: escaped=False
            elif char=='\\': escaped=True
            elif char=='"': string=False
        elif char=='"': string=True
        elif char in '[{':
            depth+=1; _require(depth<=16,'Observation nesting limit')
        elif char in ']}': depth-=1
    def no_float(_value): raise ValueError('Non-integer observation number')
    def integer(value):
        _require(len(value)<=16,'Observation integer limit'); return int(value)
    value=json.loads(text,object_pairs_hook=_unique_pairs,parse_float=no_float,
                     parse_constant=no_float,parse_int=integer)
    _shape(value,observation_schema())
    return value


def summarize_observation(value):
    """Account all recorded attempts; unknown coverage never becomes zero use."""
    _shape(value,observation_schema())
    launches=value['launches']; observations=value['observations']
    launch_ids=[l['attempt_id'] for l in launches]; ids=[o['attempt_id'] for o in observations]
    _require(len(set(launch_ids))==len(launch_ids),'Duplicate launch identity')
    _require(len(set(ids))==len(ids),'Duplicate observation identity')
    _require(set(ids)<=set(launch_ids),'Orphan observation')
    missing=sorted(set(launch_ids)-set(ids)); by_id={o['attempt_id']:o for o in observations}
    measured=[]; unknown=[]; effective=[]; costs=defaultdict(Decimal); money_missing=[]
    for ident in launch_ids:
        observation=by_id.get(ident)
        if observation is None:
            unknown.append(ident); money_missing.append(ident); continue
        usage=observation['usage']; fields=[usage[k] for k in ('input_tokens','cache_read_tokens','cache_write_tokens','output_tokens')]
        if usage['source']=='unavailable':
            _require(all(f is None for f in fields) and usage['reference'] is None
                     and usage['input_convention']=='unknown','Unavailable usage has measurements')
        else: _require(usage['reference'] is not None,'Measured usage needs a source reference')
        if usage['input_convention']=='includes_cache' and fields[0] is not None:
            _require(sum(v for v in fields[1:3] if v is not None)<=fields[0],
                     'Known cache already exceeds inclusive input')
        if all(f is not None for f in fields) and usage['input_convention']!='unknown':
            input_tokens, read, write, output=fields
            if usage['input_convention']=='includes_cache':
                _require(read+write<=input_tokens,'Cache exceeds inclusive input')
                fresh=input_tokens-read-write
            else: fresh=input_tokens
            measured.append({'fresh_input':fresh,'cache_read':read,'cache_write':write,'output':output,
                             'total':fresh+read+write+output})
        else: unknown.append(ident)
        loaded=observation['loaded_context']
        if loaded['basis']=='unavailable':
            _require(loaded['bytes'] is None and loaded['reference'] is None,'Unavailable loading has data')
        elif loaded['bytes'] is not None:
            _require(loaded['reference'] is not None,'Loaded bytes need an observation reference')
        if loaded['basis']=='effective_input' and loaded['bytes'] is not None: effective.append(loaded['bytes'])
        cost=observation['cost']; fields=list(cost.values())
        _require(all(f is None for f in fields) or all(f is not None for f in fields),'Partial cost observation')
        if cost['amount'] is None: money_missing.append(ident)
        else: costs[cost['currency']]+=Decimal(cost['amount'])
    inventory=value['launch_inventory_complete'] and not missing
    usage_complete=inventory and bool(launches) and not unknown
    totals={field:sum(m[field] for m in measured) for field in ('fresh_input','cache_read','cache_write','output','total')}
    known_tokens=totals['total']; tools=sum(o['tool_calls'] or 0 for o in observations)
    tool_complete=inventory and bool(launches) and all(o['tool_calls'] is not None for o in observations)
    scout=[l for l in launches if l['role']=='scout']; bounds=value['bounds']
    def limit(measured_value,bound,complete):
        if bound is None: return 'unknown'
        if measured_value is not None and measured_value>bound: return 'exceeded'
        return 'within' if complete and measured_value is not None else 'unknown'
    structural=[]; assignments=Counter(l['assignment_id'] for l in scout); children=defaultdict(set)
    for launch in scout:
        if launch['depth']>3: structural.append('SUBDIVISION_DEPTH')
        if launch['retry']>1 or assignments[launch['assignment_id']]>2: structural.append('RETRY_LIMIT')
        if launch['parent_assignment_id']: children[launch['parent_assignment_id']].add(launch['assignment_id'])
    if any(len(c)>4 for c in children.values()): structural.append('SUBDIVISION_FANOUT')
    if value['evidence_kind']!='task_behavior':
        _require(value['task_result']=='not_run' and value['independent_oracle_ref'] is None,
                 'Loading/static observation is not task evidence')
    elif value['task_result'] in ('passed','failed'):
        _require(value['independent_oracle_ref'] is not None,'Task result needs evaluator-side evidence')
    return {'launched_attempts':len(launches),'scout_attempts':len(scout),
            'failed_or_cancelled':sum(o['status'] in ('failed','cancelled','oversize') for o in observations),
            'missing_attempts':missing,'inventory_complete':inventory,'usage_complete':usage_complete,
            'tokens': totals if usage_complete else None,'known_complete_attempt_tokens':known_tokens,
            'unknown_usage_attempts':unknown,
            'money':{'known_by_currency':{k:str(v) for k,v in sorted(costs.items())},
                     'complete':inventory and bool(launches) and not money_missing,
                     'unknown_attempts':money_missing},
            'elapsed_ms':value['elapsed_ms'],
            'effective_loaded_bytes':sum(effective) if inventory and bool(launches) and len(effective)==len(launches) else None,
            'profile_complete':all(v is not None for v in value['profile'].values()) and value['snapshot_sha256'] is not None,
            'limits_complete':all(v is not None for v in bounds.values()),
            'budget':{'scout_attempts':limit(len(scout),bounds['max_scout_attempts'],value['launch_inventory_complete']),
                      'tokens':limit(known_tokens,bounds['max_tokens'],usage_complete),
                      'tool_calls':limit(tools,bounds['max_tool_calls'],tool_complete),
                      'elapsed':limit(value['elapsed_ms'],bounds['deadline_ms'],value['elapsed_ms'] is not None)},
            'structural_budget_findings':sorted(set(structural)),
            'evidence_kind':value['evidence_kind'],'reported_task_result':value['task_result']}


def example_observation():
    """Explicitly synthetic measurement fixture; it proves no product outcome."""
    return {'schema_version':1,'run_id':'RUN-1','evidence_kind':'synthetic_loading',
            'profile':{k:None for k in observation_schema()['properties']['profile']['properties']},
            'snapshot_sha256':None,'launch_inventory_complete':True,
            'launches':[{'attempt_id':'A-1','role':'scout','assignment_id':'SCOUT-1','parent_assignment_id':None,'depth':0,'retry':0}],
            'observations':[{'attempt_id':'A-1','status':'completed','elapsed_ms':100,'tool_calls':2,
                'usage':{'source':'provider','reference':'synthetic-usage','input_convention':'includes_cache',
                         'input_tokens':100,'cache_read_tokens':20,'cache_write_tokens':10,'output_tokens':5},
                'loaded_context':{'bytes':1000,'basis':'effective_input','reference':'synthetic-input'},
                'cost':{'amount':None,'currency':None,'source_ref':None}}],
            'bounds':{'max_scout_attempts':24,'max_tokens':1000,'max_tool_calls':100,'deadline_ms':1000},
            'elapsed_ms':100,'task_result':'not_run','independent_oracle_ref':None}


class TestObservationAccounting(unittest.TestCase):
    def test_inclusive_and_exclusive_cache_normalize_to_same_total(self):
        inclusive=example_observation(); exclusive=copy.deepcopy(inclusive)
        exclusive['observations'][0]['usage'].update(input_convention='excludes_cache',input_tokens=70)
        a=summarize_observation(inclusive); b=summarize_observation(exclusive)
        self.assertEqual(a['tokens'],b['tokens']); self.assertEqual(a['tokens']['total'],105)
        self.assertEqual(a['tokens']['fresh_input'],70)

    def test_missing_cache_measurement_is_unknown_not_zero(self):
        v=example_observation(); v['observations'][0]['usage']['cache_read_tokens']=None
        out=summarize_observation(v); self.assertIsNone(out['tokens']); self.assertFalse(out['usage_complete'])
        self.assertEqual(out['budget']['tokens'],'unknown')

    def test_explicit_zero_is_known_and_unknown_profile_stays_unknown(self):
        v=example_observation(); usage=v['observations'][0]['usage']
        for field in ('input_tokens','cache_read_tokens','cache_write_tokens','output_tokens'): usage[field]=0
        out=summarize_observation(v); self.assertEqual(out['tokens']['total'],0)
        self.assertFalse(out['profile_complete']); self.assertFalse(out['money']['complete'])

    def test_failed_retries_and_synthesis_all_count_tokens(self):
        v=example_observation()
        for ident,role,status in [('A-2','scout','failed'),('A-3','synthesis','completed')]:
            v['launches'].append({**v['launches'][0],'attempt_id':ident,'role':role,'retry':1 if role=='scout' else 0})
            v['observations'].append({**copy.deepcopy(v['observations'][0]),'attempt_id':ident,'status':status})
        out=summarize_observation(v); self.assertEqual(out['tokens']['total'],315)
        self.assertEqual(out['launched_attempts'],3); self.assertEqual(out['scout_attempts'],2)
        self.assertEqual(out['failed_or_cancelled'],1); self.assertEqual(out['elapsed_ms'],100)

    def test_omitted_attempt_prevents_complete_usage(self):
        v=example_observation(); v['launches'].append({**v['launches'][0],'attempt_id':'A-2'})
        out=summarize_observation(v); self.assertEqual(out['missing_attempts'],['A-2'])
        self.assertIsNone(out['tokens']); self.assertEqual(out['known_complete_attempt_tokens'],105)

    def test_untrusted_or_empty_launch_inventory_is_not_complete_measurement(self):
        v=example_observation(); v['launch_inventory_complete']=False
        self.assertFalse(summarize_observation(v)['usage_complete'])
        v['launch_inventory_complete']=True; v['launches']=[];v['observations']=[]
        self.assertIsNone(summarize_observation(v)['tokens'])

    def test_duplicate_and_orphan_attempts_reject(self):
        for field in ('launches','observations'):
            v=example_observation(); v[field]*=2
            with self.assertRaises(ValueError): summarize_observation(v)
        v=example_observation();v['observations'][0]['attempt_id']='ORPHAN'
        with self.assertRaises(ValueError): summarize_observation(v)

    def test_renaming_assignments_cannot_reset_aggregate_limit(self):
        v=example_observation();v['launches']=[{**v['launches'][0],'attempt_id':f'A-{i}','assignment_id':f'S-{i}'} for i in range(25)]
        v['observations']=[]
        self.assertEqual(summarize_observation(v)['budget']['scout_attempts'],'exceeded')

    def test_depth_fanout_and_retry_overruns_are_recordable_not_hidden(self):
        v=example_observation();v['launches']=[{**v['launches'][0],'attempt_id':f'A-{i}',
             'assignment_id':f'S-{i}','parent_assignment_id':'PARENT','depth':4,'retry':2} for i in range(5)]
        v['observations']=[]
        self.assertEqual(summarize_observation(v)['structural_budget_findings'],
                         ['RETRY_LIMIT','SUBDIVISION_DEPTH','SUBDIVISION_FANOUT'])

    def test_missing_bound_cannot_qualify_dispatch_budget(self):
        v=example_observation();v['bounds']['max_tokens']=None
        out=summarize_observation(v);self.assertFalse(out['limits_complete']);self.assertEqual(out['budget']['tokens'],'unknown')

    def test_known_partial_usage_already_over_budget_is_exceeded(self):
        v=example_observation();v['bounds']['max_tokens']=100;v['launch_inventory_complete']=False
        self.assertEqual(summarize_observation(v)['budget']['tokens'],'exceeded')

    def test_money_is_decimal_separate_and_never_estimated_from_tokens(self):
        v=example_observation();v['observations'][0]['cost']={'amount':'0.10','currency':'USD','source_ref':'synthetic-bill'}
        v['launches'].append({**v['launches'][0],'attempt_id':'A-2'})
        v['observations'].append({**copy.deepcopy(v['observations'][0]),'attempt_id':'A-2'})
        out=summarize_observation(v);self.assertEqual(out['money']['known_by_currency'],{'USD':'0.20'})
        v['observations'][1]['cost']['currency']='EUR'
        self.assertEqual(set(summarize_observation(v)['money']['known_by_currency']),{'USD','EUR'})
        self.assertNotIn('savings',out)

    def test_partial_cost_and_bad_cache_arithmetic_reject(self):
        v=example_observation();v['observations'][0]['cost']['amount']='1'
        with self.assertRaises(ValueError):summarize_observation(v)
        v=example_observation();v['observations'][0]['usage']['cache_read_tokens']=101
        with self.assertRaises(ValueError):summarize_observation(v)

    def test_loading_self_report_is_not_effective_input_or_task_evidence(self):
        v=example_observation();v['observations'][0]['loaded_context']['basis']='self_report'
        self.assertIsNone(summarize_observation(v)['effective_loaded_bytes'])
        v['task_result']='passed';v['independent_oracle_ref']='some-ref'
        with self.assertRaises(ValueError):summarize_observation(v)

    def test_reported_behavior_needs_evaluator_reference_but_is_not_approval(self):
        v=example_observation();v['evidence_kind']='task_behavior';v['task_result']='passed'
        with self.assertRaises(ValueError):summarize_observation(v)
        v['independent_oracle_ref']='synthetic-evaluator'
        out=summarize_observation(v);self.assertEqual(out['reported_task_result'],'passed')
        self.assertNotIn('approved',out);self.assertNotIn('ready',out)

    def test_unknown_fields_invalid_types_and_nonfinite_numbers_reject(self):
        for field,val in [('schema_version',True),('elapsed_ms',1.0),('elapsed_ms',-1),('invented_approval',True)]:
            v=example_observation();v[field]=val
            with self.assertRaises(ValueError):summarize_observation(v)
        for raw in (b'{"n":NaN}', b'{"n":1e4}', b'{"n":1,"n":2}', b'['*17+b'0'+b']'*17,b' '*(MAX_BYTES+1)):
            with self.assertRaises(ValueError):decode_observation(raw)

    def test_canonical_schema_and_input_roundtrip(self):
        self.assertEqual(decode_observation(json.dumps(example_observation()).encode()),example_observation())
        if SCHEMA_PATH.is_file():
            self.assertEqual(json.loads(SCHEMA_PATH.read_text()),observation_schema())
        else:
            # The reduced source copy used by platform tests has no repository.
            self.assertFalse((ROOT/'core/pysrc').is_dir(),'Required observation schema is missing')

    def test_partial_cache_arithmetic_cannot_hide_a_known_contradiction(self):
        v=example_observation();usage=v['observations'][0]['usage']
        usage['cache_read_tokens']=101;usage['cache_write_tokens']=None;usage['output_tokens']=None
        with self.assertRaises(ValueError): summarize_observation(v)

    def test_observation_does_not_mutate_input(self):
        v=example_observation();before=copy.deepcopy(v);summarize_observation(v);self.assertEqual(v,before)


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if any(arg!='TestObservationAccounting' for arg in args) or len(args)>1:
        print('Unknown or repeated evaluation-test selector',file=sys.stderr);return 2
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(TestObservationAccounting)
    if not suite.countTestCases():return 2
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__=='__main__':
    raise SystemExit(main())
