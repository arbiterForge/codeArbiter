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
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

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
    token_lower_bound=0
    for ident in launch_ids:
        observation=by_id.get(ident)
        if observation is None:
            unknown.append(ident); money_missing.append(ident); continue
        usage=observation['usage']; fields=[usage[k] for k in ('input_tokens','cache_read_tokens','cache_write_tokens','output_tokens')]
        if usage['source']=='unavailable':
            _require(all(f is None for f in fields) and usage['reference'] is None
                     and usage['input_convention']=='unknown','Unavailable usage has measurements')
        else: _require(usage['reference'] is not None,'Measured usage needs a source reference')
        known_cache=sum(v for v in fields[1:3] if v is not None)
        if usage['input_convention']=='includes_cache' and fields[0] is not None:
            _require(known_cache<=fields[0],
                     'Known cache already exceeds inclusive input')
        # Partial counts prove only a lower bound, never a complete token total.
        # Inclusive or unknown input may already contain the measured cache.
        input_floor=fields[0] or 0
        input_floor=(input_floor+known_cache if usage['input_convention']=='excludes_cache'
                     else max(input_floor,known_cache))
        token_lower_bound+=input_floor+(fields[3] or 0)
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
                      'tokens':limit(token_lower_bound,bounds['max_tokens'],usage_complete),
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


def _trial_digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _trial_option(argv, flag):
    if argv.count(flag) != 1:
        return None
    index = argv.index(flag)
    return argv[index + 1] if index + 1 < len(argv) else None


def _trial_hook_command(argv):
    return (subprocess.list2cmdline(argv) if os.name == 'nt'
            else shlex.join(argv))


_TRIAL_EVENT_COLLECTOR = '''import json, os, sys
raw = sys.stdin.buffer.read(16385)
if len(raw) > 16384:
    raise SystemExit(2)
event = json.loads(raw)
if type(event) is not dict or event.get("hook_event_name") != "InstructionsLoaded":
    raise SystemExit(2)
line = (json.dumps(event, sort_keys=True, ensure_ascii=False) + "\\n").encode("utf-8")
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
try:
    os.write(fd, line)
finally:
    os.close(fd)
'''


def prepare_qualification_pair(catalog, case_id, destination):
    """Create matched, fresh Git workspaces with evaluator data outside both solvers.

    This prepares inert local fixtures only. Inaccessibility to a future actor
    still requires an observed host permission probe for the exact profile.
    """
    from _context_fixturelib import canonical_digest, materialize, validate_catalog
    validate_catalog(catalog)
    selected = [case for case in catalog['cases'] if case['id'] == case_id]
    if len(selected) != 1:
        raise ValueError('unknown qualification fixture')
    destination = Path(destination).absolute()
    if destination.exists() or not destination.parent.is_dir():
        raise ValueError('qualification pair needs a new trusted destination')
    destination.mkdir()
    controller = destination / 'controller'
    controller.mkdir()
    hook_script = controller / 'capture-native-event.py'
    hook_script.write_text(_TRIAL_EVENT_COLLECTOR, encoding='utf-8', newline='\n')
    arms = {}
    for arm in ('A', 'B'):
        instance = materialize(catalog, case_id, destination / arm)
        evaluator = destination / arm / 'evaluator'
        # The materializer's evaluator sibling is moved under the controller
        # before any actor is dispatched. The move is within this new pair.
        controlled_evaluator = controller / ('evaluator-' + arm)
        evaluator.rename(controlled_evaluator)
        evaluator = controlled_evaluator
        identity = json.loads((evaluator / 'identity.json').read_text(encoding='utf-8'))
        if identity['oracle_sha256'] != selected[0]['oracle_sha256']:
            raise ValueError('paired oracle identity mismatch')
        home = destination / arm / 'home'
        home.mkdir()
        event_log = destination / arm / 'instructions-loaded.jsonl'
        settings = destination / arm / 'settings.json'
        settings.write_text(json.dumps({'hooks': {'InstructionsLoaded': [{'hooks': [{
            'type': 'command', 'command': _trial_hook_command(
                [sys.executable, str(hook_script), str(event_log)])}]}]}},
            sort_keys=True, indent=2)+'\n', encoding='utf-8')
        arms[arm] = {'solver': str(instance['solver']), 'evaluator': str(evaluator),
                     'files': instance['files'], 'oracle_sha256': identity['oracle_sha256'],
                     'case_sha256': identity['case_sha256'], 'home': str(home),
                     'settings': str(settings), 'settings_sha256': _trial_digest(settings.read_bytes()),
                     'event_log': str(event_log)}
    if arms['A']['files'] != arms['B']['files']:
        raise ValueError('paired fixture snapshots differ')
    pair = {'case_id': case_id, 'case_sha256': canonical_digest(selected[0]),
            'task': dict(selected[0]['task']), 'task_sha256': canonical_digest(selected[0]['task']),
            'oracle_sha256': selected[0]['oracle_sha256'],
            'fixture_snapshot_sha256': selected[0]['snapshot_sha256'], 'arms': arms,
            'controller': str(controller), 'hook_script': str(hook_script),
            'hook_script_sha256': _trial_digest(hook_script.read_bytes()),
            'qualification': 'unverified'}
    (controller / 'pair.json').write_text(json.dumps(pair, sort_keys=True, indent=2)+'\n',
                                          encoding='utf-8')
    return pair


def prepare_qualification_delivery(pair, *, arm, selected_packet, actor, task_id,
                                   host_epoch, attempts=None, receipt=None,
                                   mode='source_fixture', installed_selector=None,
                                   selector_sha256=None, candidate_sha256=None):
    """Bind source fixtures or use a verified installed selector for B only."""
    from _context_fixturelib import canonical_digest, snapshot
    if arm not in pair['arms']:
        raise ValueError('unknown qualification arm')
    solver = pair['arms'][arm]['solver']
    source_epoch = canonical_digest(snapshot(solver))
    kwargs = {'actor': actor, 'task_id': task_id, 'worktree': solver,
              'source_epoch': source_epoch, 'host_epoch': host_epoch,
              'attempts': attempts, 'receipt': receipt}
    if mode == 'source_fixture':
        if any(value is not None for value in
               (installed_selector, selector_sha256, candidate_sha256)):
            raise ValueError('source fixture cannot claim an installed selector')
        core_path = str(ROOT / 'core/pysrc')
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        import _contextselectlib
        result = _contextselectlib.prepare_actor_delivery(selected_packet, **kwargs)
        return {**result, 'delivery_mode': 'source_fixture'}
    if mode != 'controlled_host' or not isinstance(candidate_sha256, str) or not re.fullmatch(
            r'[0-9a-f]{64}', candidate_sha256):
        raise ValueError('invalid installed candidate delivery mode')
    if arm == 'A':
        if installed_selector is not None or selector_sha256 is not None:
            raise ValueError('baseline cannot load candidate selector')
        return {'action': 'baseline', 'delivery_text': None, 'attempt': None,
                'binding': {'source_epoch': source_epoch, 'worktree': os.path.normcase(
                    os.path.realpath(solver))}, 'candidate_sha256': candidate_sha256,
                'delivery_mode': 'installed_candidate'}
    helper = Path(installed_selector).resolve() if installed_selector is not None else None
    if (helper is None or helper.name != '_contextselectlib.py' or
            not Path(installed_selector).is_absolute() or
            not helper.is_file() or helper.is_relative_to(ROOT.resolve()) or
            not isinstance(selector_sha256, str) or
            not re.fullmatch(r'[0-9a-f]{64}', selector_sha256) or
            _trial_digest(helper.read_bytes()) != selector_sha256):
        raise ValueError('installed selector identity missing or changed')
    # A fresh isolated interpreter prevents an already-imported source helper
    # or its dependencies from satisfying the installed-candidate call.
    script = ('import json,sys; sys.path.insert(0,sys.argv[1]); '
              'import _contextselectlib as s; q=json.load(sys.stdin); '
              'print(json.dumps(s.prepare_actor_delivery(q.pop("packet"), **q)))')
    input_bytes = json.dumps({'packet': selected_packet, **kwargs},
                             separators=(',', ':')).encode('utf-8')
    if len(input_bytes) > 128 * 1024:
        raise ValueError('installed selector input too large')
    process = subprocess.run([sys.executable, '-I', '-c', script, str(helper.parent)],
                             input=input_bytes, cwd=pair['controller'],
                             capture_output=True, timeout=15)
    if process.returncode != 0 or len(process.stdout) > 128 * 1024:
        raise ValueError('installed selector failed')
    result = json.loads(process.stdout)
    if type(result) is not dict or result.get('action') not in ('deliver', 'blocked', 'observed'):
        raise ValueError('installed selector returned invalid delivery')
    return {**result, 'delivery_mode': 'installed_candidate',
            'candidate_sha256': candidate_sha256,
            'installed_selector_path': str(helper),
            'installed_selector_sha256': selector_sha256}


def capture_qualification_attempt(pair, *, arm, attempt_id, argv, actor_input,
                                  delivery_text, evidence_kind, timeout_seconds=300,
                                  launch_contract=None, environment=None,
                                  delivery_plan=None):
    """Send exact input to a process and retain raw outcome before interpretation.

    The caller owns the separate live-trial decision and exact CLI/profile gate.
    A returned record proves only this local subprocess boundary, not model
    consumption, policy approval, task correctness or provider accounting.
    """
    if arm not in ('A', 'B') or arm not in pair['arms']:
        raise ValueError('unknown qualification arm')
    if (type(attempt_id) is not str or re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{0,63}', attempt_id) is None
            or type(argv) is not list or not argv or not all(type(x) is str and x for x in argv)
            or type(actor_input) is not str or not actor_input
            or not ((type(delivery_text) is str and bool(delivery_text)) or
                    (delivery_text is None and evidence_kind == 'controlled_host' and arm == 'A'))
            or evidence_kind not in ('harness_only', 'controlled_host')
            or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600):
        raise ValueError('invalid qualification launch')
    if evidence_kind == 'controlled_host':
        from _context_fixturelib import canonical_digest, snapshot
        expected = {'authorization_ref', 'executable_sha256', 'model',
                    'candidate_sha256', 'settings_sha256', 'max_budget_usd',
                    'max_turns', 'argv_sha256', 'environment_sha256'}
        source_epoch = canonical_digest(snapshot(pair['arms'][arm]['solver']))
        binding = delivery_plan.get('binding') if type(delivery_plan) is dict else None
        delivery_valid = (type(delivery_plan) is dict and
                          delivery_plan.get('delivery_mode') == 'installed_candidate' and
                          delivery_plan.get('candidate_sha256') == (
                              launch_contract.get('candidate_sha256')
                              if type(launch_contract) is dict else None) and
                          type(binding) is dict and
                          binding.get('source_epoch') == source_epoch and
                          binding.get('worktree') == os.path.normcase(
                              os.path.realpath(pair['arms'][arm]['solver'])))
        if arm == 'A':
            delivery_valid = (delivery_valid and delivery_plan.get('action') == 'baseline'
                              and delivery_plan.get('delivery_text') is None
                              and delivery_plan.get('attempt') is None)
        elif delivery_valid:
            helper = Path(delivery_plan.get('installed_selector_path', ''))
            delivery_valid = (delivery_plan.get('action') == 'deliver'
                              and delivery_plan.get('delivery_text') == delivery_text
                              and type(delivery_plan.get('attempt')) is dict
                              and delivery_plan['attempt'].get('binding') == binding
                              and helper.is_file()
                              and not helper.resolve().is_relative_to(ROOT.resolve())
                              and _trial_digest(helper.read_bytes()) ==
                                  delivery_plan.get('installed_selector_sha256'))
        if (type(launch_contract) is not dict or set(launch_contract) != expected
                or not delivery_valid
                or type(environment) is not dict or not all(
                    type(key) is str and type(value) is str
                    for key, value in environment.items())):
            raise ValueError('controlled host needs an exact external launch contract')
        banned = ('--tools', '--add-dir', '--dangerously-skip-permissions',
                  '--permission-mode')
        if (not all(type(launch_contract[key]) is str and launch_contract[key]
                    for key in expected) or
                not Path(argv[0]).is_file() or
                _trial_digest(Path(argv[0]).read_bytes()) != launch_contract['executable_sha256'] or
                _trial_digest(json.dumps(argv, separators=(',', ':')).encode('utf-8'))
                    != launch_contract['argv_sha256'] or
                _trial_digest(json.dumps(environment, sort_keys=True,
                    separators=(',', ':')).encode('utf-8'))
                    != launch_contract['environment_sha256'] or
                launch_contract['settings_sha256'] != pair['arms'][arm]['settings_sha256'] or
                environment.get('HOME') != pair['arms'][arm]['home'] or
                environment.get('USERPROFILE') != pair['arms'][arm]['home'] or
                environment.get('XDG_CONFIG_HOME') != str(Path(pair['arms'][arm]['home']) / '.config') or
                argv.count('--restricted') != 1 or
                any(arg == flag or arg.startswith(flag + '=')
                    for arg in argv for flag in banned) or
                _trial_option(argv, '--settings') != pair['arms'][arm]['settings'] or
                _trial_option(argv, '--model') != launch_contract['model'] or
                _trial_option(argv, '--max-budget-usd') != launch_contract['max_budget_usd'] or
                _trial_option(argv, '--max-turns') != launch_contract['max_turns'] or
                _trial_option(argv, '--output-format') != 'stream-json' or
                '--include-hook-events' not in argv or '--verbose' not in argv or
                '-p' not in argv or
                re.fullmatch(r'[1-9][0-9]{0,2}', launch_contract['max_turns']) is None or
                int(launch_contract['max_turns']) > 64 or
                re.fullmatch(r'(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,2})?',
                             launch_contract['max_budget_usd']) is None or
                Decimal(launch_contract['max_budget_usd']) <= 0):
            raise ValueError('controlled host launch differs from frozen profile')
    elif launch_contract is not None or environment is not None or delivery_plan is not None:
        raise ValueError('harness launch has no host authorization contract')
    controller = Path(pair['controller'])
    stem = arm + '-' + attempt_id
    record_path = controller / (stem + '.json')
    if record_path.exists() or (controller / (stem + '.stdin')).exists():
        raise FileExistsError('qualification attempt already recorded')
    payload = (actor_input + ('\n\n' + delivery_text if delivery_text else '') + '\n').encode('utf-8')
    if len(payload) > 96 * 1024:
        raise ValueError('qualification actor input too large')
    stdin_path = controller / (stem + '.stdin')
    stdin_path.write_bytes(payload)
    with (controller / 'launches.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'arm': arm, 'attempt_id': attempt_id,
                                 'stdin_sha256': _trial_digest(payload)}, sort_keys=True)+'\n')
        stream.flush()
        os.fsync(stream.fileno())
    started = time.monotonic_ns()
    try:
        process = subprocess.run(argv, input=payload, cwd=pair['arms'][arm]['solver'],
                                 env=environment, capture_output=True,
                                 timeout=timeout_seconds)
        exit_code, stdout, stderr = process.returncode, process.stdout, process.stderr
        status = 'completed' if exit_code == 0 else 'failed'
    except subprocess.TimeoutExpired as exc:
        exit_code, stdout, stderr = None, exc.stdout or b'', exc.stderr or b''
        status = 'cancelled'
    elapsed_ms = (time.monotonic_ns() - started) // 1_000_000
    # Retain a bounded prefix if the process exceeded the local evidence limit.
    # The record remains explicitly incomplete and cannot support qualification.
    limit = 4 * 1024 * 1024
    incomplete = len(stdout) > limit or len(stderr) > limit
    if incomplete:
        status = 'oversize'
    stdout_path, stderr_path = controller / (stem + '.stdout'), controller / (stem + '.stderr')
    stdout_path.write_bytes(stdout[:limit]); stderr_path.write_bytes(stderr[:limit])
    record = {'arm': arm, 'attempt_id': attempt_id, 'argv': argv,
              'stdin': str(stdin_path), 'stdin_sha256': _trial_digest(payload),
              'stdout': str(stdout_path), 'stdout_sha256': _trial_digest(stdout[:limit]),
              'stderr': str(stderr_path), 'stderr_sha256': _trial_digest(stderr[:limit]),
              'exit_code': exit_code, 'elapsed_ms': elapsed_ms,
              'status': status, 'output_incomplete': incomplete,
              'evidence_kind': evidence_kind, 'delivery_status': 'sent_to_process_stdin',
              'launch_contract': launch_contract,
              'delivery_binding': delivery_plan['binding'] if delivery_plan else None,
              'delivery_attempt': delivery_plan['attempt'] if delivery_plan else None,
              'qualification': 'unverified'}
    with record_path.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, sort_keys=True, indent=2); stream.write('\n')
    return record


def assess_qualification_pair(pair, observations=None):
    """Check retained bytes and optional supplied accounting; never qualify a host."""
    from _context_fixturelib import canonical_digest, snapshot
    controller = Path(pair['controller'])
    saved = json.loads((controller / 'pair.json').read_text(encoding='utf-8'))
    if saved != pair or set(pair['arms']) != {'A', 'B'}:
        raise ValueError('qualification pair identity changed')
    if _trial_digest(Path(pair['hook_script']).read_bytes()) != pair['hook_script_sha256']:
        raise ValueError('trial event collector changed')
    records = {}
    native_event_logs = {}
    workspace_effects = {}
    for arm in ('A', 'B'):
        info = pair['arms'][arm]
        solver = Path(info['solver']).resolve()
        evaluator = Path(info['evaluator']).resolve()
        if evaluator.is_relative_to(solver) or solver.is_relative_to(evaluator):
            raise ValueError('oracle is in actor workspace')
        oracle_bytes = (evaluator / 'oracle.json').read_bytes()
        oracle = json.loads(oracle_bytes)
        if canonical_digest(oracle) != pair['oracle_sha256']:
            raise ValueError('evaluator oracle changed')
        identity = json.loads((evaluator / 'identity.json').read_text(encoding='utf-8'))
        if (identity['case_sha256'] != pair['case_sha256'] or
                identity['oracle_sha256'] != pair['oracle_sha256'] or
                identity['task_sha256'] != pair['task_sha256'] or
                identity['worktree_files'] != info['files']):
            raise ValueError('fixture identity changed')
        if _trial_digest(Path(info['settings']).read_bytes()) != info['settings_sha256']:
            raise ValueError('trial hook settings changed')
        event_log = Path(info['event_log'])
        event_bytes = event_log.read_bytes() if event_log.exists() else None
        if event_bytes is not None:
            if len(event_bytes) > 1024 * 1024:
                raise ValueError('trial native event log exceeds bound')
            for line in event_bytes.splitlines():
                event = json.loads(line)
                if type(event) is not dict or event.get('hook_event_name') != 'InstructionsLoaded':
                    raise ValueError('invalid trial native event')
        native_event_logs[arm] = (_trial_digest(event_bytes)
                                  if event_bytes is not None else None)
        after_files = snapshot(solver)
        for rel in after_files:
            if oracle_bytes in (solver / rel).read_bytes():
                raise ValueError('evaluator oracle leaked into actor workspace')
        before_files = info['files']
        changed = sorted(path for path in set(before_files) | set(after_files)
                         if before_files.get(path) != after_files.get(path))
        broken_preservation = sorted(path for path in oracle['preserve_paths']
                                     if before_files.get(path) != after_files.get(path))
        new_instructions = sorted(path for path in after_files.keys() - before_files.keys()
                                  if Path(path).name in ('AGENTS.md', 'CLAUDE.md')
                                  or path.startswith('.claude/rules/'))
        workspace_effects[arm] = {'changed_paths': changed,
                                  'preservation': ('contradicted' if broken_preservation else 'matched'),
                                  'broken_preserve_paths': broken_preservation,
                                  'new_instruction_paths': new_instructions,
                                  'after_files': after_files}
        records[arm] = []
    inventory = controller / 'launches.jsonl'
    launches = [] if not inventory.exists() else [json.loads(line) for line in
              inventory.read_text(encoding='utf-8').splitlines()]
    ids = [(row['arm'], row['attempt_id']) for row in launches]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate qualification launch')
    for launch in launches:
        arm, attempt_id = launch['arm'], launch['attempt_id']
        if arm not in records or re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{0,63}', attempt_id) is None:
            raise ValueError('invalid qualification inventory')
        stem = arm + '-' + attempt_id
        record_path = controller / (stem + '.json')
        if not record_path.is_file():
            raise ValueError('launched attempt has no retained outcome')
        record = json.loads(record_path.read_text(encoding='utf-8'))
        if record['arm'] != arm or record['attempt_id'] != attempt_id:
            raise ValueError('attempt identity mismatch')
        for key in ('stdin', 'stdout', 'stderr'):
            path = Path(record[key]).resolve()
            if path.parent != controller.resolve() or _trial_digest(path.read_bytes()) != record[key+'_sha256']:
                raise ValueError('attempt evidence changed')
        if launch['stdin_sha256'] != record['stdin_sha256']:
            raise ValueError('launch input changed')
        records[arm].append(record)
    accounting = None
    if observations is not None:
        if type(observations) is not dict or set(observations) != {'A', 'B'}:
            raise ValueError('paired observations require both arms')
        accounting = {}
        for arm in ('A', 'B'):
            observed = decode_observation(observations[arm])
            if observed['snapshot_sha256'] != pair['fixture_snapshot_sha256']:
                raise ValueError('observation snapshot differs from frozen fixture')
            if not {record['attempt_id'] for record in records[arm]} <= {
                    launch['attempt_id'] for launch in observed['launches']}:
                raise ValueError('captured process absent from observation inventory')
            accounting[arm] = summarize_observation(observed)
    return {'qualification': 'unverified', 'pairing': 'matched',
            'attempts': records, 'missing_arms': [arm for arm in ('A', 'B') if not records[arm]],
            'native_event_log_sha256': native_event_logs,
            'workspace_effects': workspace_effects,
            'reported_accounting': accounting,
            'note': 'Raw local process capture needs independent host, usage and task review.'}


def assess_scoped_readiness(pair, *, profile, installed_evidence, task_states,
                            observations=None, p1_disposition='not_selected',
                            greenfield_profile=None):
    """Check a supplied T-044/T-045 report without granting live readiness.

    The retained pair is re-assessed here. A supplied installed-status label or
    usage report cannot establish host confinement, model behavior, authority,
    or independent acceptance. Those remain separate observed qualifications.
    """
    observation_profile_keys = set(observation_schema()['properties']['profile']['properties'])
    profile_keys = observation_profile_keys | {'shell', 'git_version',
        'worktree_mode', 'permission_profile', 'executable_sha256'}
    if (type(profile) is not dict or set(profile) != profile_keys or
            any(type(value) is not str or not value for value in profile.values()) or
            any(re.fullmatch(r'[0-9a-f]{64}', profile[key]) is None
                for key in ('package_sha256', 'settings_sha256', 'executable_sha256')) or
            profile['settings_sha256'] != pair['arms']['B']['settings_sha256']):
        raise ValueError('readiness needs one exact declared profile')
    if (type(installed_evidence) is not dict or
            set(installed_evidence) != {'profile', 'candidate_sha256', 'status'} or
            installed_evidence['profile'] != profile or
            installed_evidence['candidate_sha256'] != profile['package_sha256'] or
            installed_evidence['status'] not in ('source_checked',
                                                'cold_installed_observed')):
        raise ValueError('installed candidate differs from declared profile')
    required_tasks = {'T-044', 'T-045', 'T-046'}
    if (type(task_states) is not dict or not required_tasks <= set(task_states) or
            any(type(task) is not str or type(state) is not str or
                state not in ('pending', 'in_progress', 'accepted', 'blocked')
                for task, state in task_states.items())):
        raise ValueError('readiness needs explicit live task states')
    if p1_disposition not in ('not_selected', 'no_go', 'selected_pending'):
        raise ValueError('unsupported P1 disposition')
    if greenfield_profile is not None and (type(greenfield_profile) is not dict or
                                           set(greenfield_profile) != profile_keys):
        raise ValueError('greenfield reuse needs a complete profile')

    assessment = assess_qualification_pair(pair, observations)
    if observations is not None:
        for arm in ('A', 'B'):
            observed = decode_observation(observations[arm])
            expected = {key: profile[key] for key in observation_profile_keys}
            expected['settings_sha256'] = pair['arms'][arm]['settings_sha256']
            if observed['profile'] != expected:
                raise ValueError('reported observation differs from exact arm profile')
    for arm, attempts in assessment['attempts'].items():
        for attempt in attempts:
            if attempt['evidence_kind'] == 'controlled_host':
                contract = attempt['launch_contract']
                if (type(contract) is not dict or
                        contract.get('candidate_sha256') != profile['package_sha256'] or
                        contract.get('settings_sha256') !=
                            pair['arms'][arm]['settings_sha256'] or
                        contract.get('executable_sha256') !=
                            profile['executable_sha256'] or
                        contract.get('model') != profile['model']):
                    raise ValueError('controlled attempt differs from exact profile')

    accounted = assessment['reported_accounting']
    accounting_complete = (accounted is not None and
                           all(accounted[arm]['usage_complete'] for arm in ('A', 'B')))
    pending = sorted(task for task, state in task_states.items()
                     if state != 'accepted')
    g1_status = ('unverified' if greenfield_profile == profile else
                 'unsupported_profile' if greenfield_profile is not None else
                 'not_requested')
    return {'profile': profile.copy(), 'installed_report_status': installed_evidence['status'],
            'paired_qualification': assessment['qualification'],
            'missing_arms': assessment['missing_arms'],
            'reported_accounting_complete': accounting_complete,
            'core_readiness': 'unverified',
            'pending_tasks': pending,
            'plan_completion': 'pending' if pending else 'unverified',
            'p1': {'disposition': p1_disposition,
                   'implementation': ('absent' if p1_disposition in
                                      ('not_selected', 'no_go') else 'unverified')},
            'g1_reuse': {'scope': 'first_input_only', 'status': g1_status},
            'other_hosts': 'unverified',
            'commit_authority': 'not_granted', 'release_authority': 'not_granted'}


class TestObservationAccounting(unittest.TestCase):
    def shortDescription(self):
        return None

    @staticmethod
    def _t041_helpers():
        sys.path.insert(0, str(ROOT / 'core' / 'pysrc'))
        import _contextreportlib as reports
        import _contextsnapshotlib as snapshots
        return reports, snapshots

    def test_decode_observation_accepts_legitimate_positive_control(self):
        raw=json.dumps(example_observation(),separators=(',',':')).encode()
        self.assertEqual(decode_observation(raw),example_observation())

    def test_decode_observation_accepts_complete_observation_at_byte_limit(self):
        base=json.dumps(example_observation(),separators=(',',':')).encode()
        at_limit=base+b' '*(MAX_BYTES-len(base))
        self.assertEqual(len(at_limit),MAX_BYTES)
        self.assertEqual(decode_observation(at_limit),example_observation())
        with self.assertRaisesRegex(ValueError,'Observation byte limit/type'):
            decode_observation(at_limit+b' ')

    def test_decode_observation_rejects_duplicate_existing_field_even_same_value(self):
        raw=json.dumps(example_observation(),separators=(',',':')).encode()
        duplicate=raw.replace(b'"schema_version":1,',b'"schema_version":1,"schema_version":1,',1)
        self.assertEqual(json.loads(duplicate),example_observation())
        with self.assertRaisesRegex(ValueError,'Duplicate observation key'):
            decode_observation(duplicate)

    def test_decode_observation_rejects_deep_nesting_before_schema_validation(self):
        raw=b'['*17+b'0'+b']'*17
        with self.assertRaisesRegex(ValueError,'Observation nesting limit'):
            decode_observation(raw)

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

    def test_partial_token_counts_prove_overruns_without_inventing_totals(self):
        cases = [
            ('includes_cache', 200, None, None, None, 'exceeded'),
            ('includes_cache', 80, 20, 10, None, 'unknown'),
            ('includes_cache', 100, 20, None, 1, 'exceeded'),
            ('includes_cache', None, 60, 50, None, 'exceeded'),
            ('excludes_cache', 60, 30, None, 20, 'exceeded'),
            ('excludes_cache', 70, 20, None, 10, 'unknown'),
            ('unknown', 80, 60, 50, None, 'exceeded'),
            ('unknown', 80, 20, 10, 20, 'unknown'),
            ('unknown', None, None, None, 101, 'exceeded'),
            ('unknown', None, None, None, None, 'unknown'),
        ]
        for convention, input_tokens, read, write, output, status in cases:
            with self.subTest(convention=convention, fields=(input_tokens,read,write,output)):
                v=example_observation();v['bounds']['max_tokens']=100
                v['observations'][0]['usage'].update(
                    input_convention=convention,input_tokens=input_tokens,
                    cache_read_tokens=read,cache_write_tokens=write,output_tokens=output)
                out=summarize_observation(v)
                self.assertEqual(out['budget']['tokens'],status)
                self.assertIsNone(out['tokens']);self.assertFalse(out['usage_complete'])
                self.assertEqual(out['known_complete_attempt_tokens'],0)
                self.assertEqual(out['unknown_usage_attempts'],['A-1'])

    def test_partial_and_complete_attempt_lower_bounds_accumulate(self):
        v=example_observation();v['bounds']['max_tokens']=200
        for ident,role,status in [('A-2','scout','failed'),('A-3','synthesis','cancelled')]:
            v['launches'].append({**v['launches'][0],'attempt_id':ident,'role':role})
            observation=copy.deepcopy(v['observations'][0])
            observation.update(attempt_id=ident,status=status)
            observation['usage'].update(input_tokens=70,output_tokens=None)
            v['observations'].append(observation)
        v['launches'].append({**v['launches'][0],'attempt_id':'A-4'})
        out=summarize_observation(v)
        self.assertEqual(out['budget']['tokens'],'exceeded')
        self.assertIsNone(out['tokens']);self.assertFalse(out['usage_complete'])
        self.assertEqual(out['known_complete_attempt_tokens'],105)
        self.assertEqual(out['unknown_usage_attempts'],['A-2','A-3','A-4'])

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
        for field in ('input_tokens','cache_read_tokens','cache_write_tokens','output_tokens'):
            for invalid in (-1,True,'200',1.5):
                with self.subTest(field=field,invalid=invalid):
                    v=example_observation();v['observations'][0]['usage']['output_tokens']=None
                    v['observations'][0]['usage'][field]=invalid
                    with self.assertRaises(ValueError): summarize_observation(v)

    def test_observation_does_not_mutate_input(self):
        v=example_observation();before=copy.deepcopy(v);summarize_observation(v);self.assertEqual(v,before)

    def _t041_events(self):
        scope = {'paths': ['src'], 'categories': ['architecture']}
        context = {'run_id': 'RUN-1', 'scope': scope}
        return [
            {**context, 'event_id': 'E-1', 'kind': 'attempt', 'snapshot_id': 'a'*64,
             'assignment_id': 'ARCH', 'attempt_id': 'A-1', 'related_attempt_ids': [], 'path': None},
            {**context, 'event_id': 'E-2', 'kind': 'retry', 'snapshot_id': 'a'*64,
             'assignment_id': 'ARCH', 'attempt_id': 'A-2', 'related_attempt_ids': [], 'path': None},
            {**context, 'event_id': 'E-3', 'kind': 'join', 'snapshot_id': 'a'*64,
             'assignment_id': None, 'attempt_id': None, 'related_attempt_ids': ['A-1','A-2'], 'path': None},
            {**context, 'event_id': 'E-4', 'kind': 'rescout', 'snapshot_id': 'b'*64,
             'assignment_id': 'ARCH', 'attempt_id': 'A-3', 'related_attempt_ids': [], 'path': None},
            {**context, 'event_id': 'E-5', 'kind': 'transient_write', 'snapshot_id': 'b'*64,
             'assignment_id': None, 'attempt_id': 'A-3', 'related_attempt_ids': [], 'path': 'out/.candidate'},
            {**context, 'event_id': 'E-6', 'kind': 'native_write', 'snapshot_id': 'b'*64,
             'assignment_id': None, 'attempt_id': 'A-3', 'related_attempt_ids': [], 'path': 'out/view.txt'},
            {**context, 'event_id': 'E-7', 'kind': 'join', 'snapshot_id': 'b'*64,
             'assignment_id': None, 'attempt_id': None, 'related_attempt_ids': ['A-3'], 'path': None},
        ]

    def test_t041_context_cost_and_noop_positive_controls(self):
        """All supplied operations and costs remain attributed across resume and no-op."""
        reports, snapshots = self._t041_helpers()
        events = self._t041_events()
        ledger = reports.summarize_context_events(
            events, run_id='RUN-1', launched_attempt_ids=['A-1','A-2','A-3'],
            allowed_effect_paths=['out/.candidate','out/view.txt'])
        self.assertEqual(ledger['counts'], {'attempt':1, 'retry':1, 'rescout':1,
                         'join':2, 'transient_write':1, 'native_write':1})
        self.assertEqual(ledger['covered_attempt_ids'], ['A-1','A-2','A-3'])
        self.assertEqual(ledger['joined_attempt_ids'], ['A-1','A-2','A-3'])
        self.assertEqual(ledger['effect_paths'], ['out/.candidate','out/view.txt'])
        self.assertEqual(ledger['evidence_basis'], 'supplied_events')
        self.assertEqual(events, self._t041_events())
        another = copy.deepcopy(events[0])
        another.update(event_id='E-8', assignment_id='TESTS', attempt_id='A-4',
                       scope={'paths':['tests'], 'categories':['tests']})
        combined = copy.deepcopy(events[2])
        combined.update(event_id='E-9', related_attempt_ids=['A-1','A-4'],
                        scope={'paths':['src','tests'],
                               'categories':['architecture','tests']})
        mixed = reports.summarize_context_events([events[0],another,combined],
            run_id='RUN-1', launched_attempt_ids=['A-1','A-4'],
            allowed_effect_paths=[])
        self.assertEqual(mixed['joined_attempt_ids'], ['A-1','A-4'])

        value = example_observation()
        for ident, role, status in [('A-2','scout','failed'),('A-3','scout','completed'),
                                    ('A-4','synthesis','completed'),('A-5','review','completed'),
                                    ('A-6','task','completed')]:
            value['launches'].append({**value['launches'][0], 'attempt_id':ident,
                                       'role':role, 'assignment_id':ident})
            value['observations'].append({**copy.deepcopy(value['observations'][0]),
                                           'attempt_id':ident, 'status':status})
        for index, item in enumerate(value['observations']):
            item['cost'] = {'amount':'0.10', 'currency':'USD', 'source_ref':f'supplied-{index}'}
        measured = summarize_observation(value)
        self.assertEqual(measured['launched_attempts'], 6)
        self.assertEqual(measured['failed_or_cancelled'], 1)
        self.assertEqual(measured['tokens']['total'], 630)
        self.assertEqual(measured['money']['known_by_currency'], {'USD':'0.60'})
        self.assertTrue(measured['money']['complete'])

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'; root.mkdir()
            def git(*args):
                subprocess.run(['git','-C',str(root),*args], check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            git('init','-q','-b','main')
            (root/'src').mkdir(); (root/'out').mkdir()
            (root/'src/package.json').write_bytes(b'{"name":"fixture"}\n')
            output = root/'out/view.txt'; output.write_bytes(b'view\n')
            git('add','--','src/package.json')
            git('-c','user.name=Fixture','-c','user.email=fixture@example.test',
                'commit','-qm','initial')
            snapshot = snapshots.context_snapshot(root,
                source_paths=('src/package.json',), source_scopes=('src',),
                target_paths=('out/view.txt',), allowed_effect_paths=('out/.candidate',))
            before = snapshots.capture_context_effects(snapshot)
            for _ in range(2):
                self.assertTrue(snapshots.compare_context_dependencies(snapshot,
                    source_paths=('src/package.json',),
                    target_paths=('out/view.txt',))['admitted'])
            (root/'unrelated.py').write_bytes(b'leaf edit\n')
            reads = []
            original_digest = snapshots.digest_file
            def observed_digest(*args, **kwargs):
                reads.append(args[1]); return original_digest(*args, **kwargs)
            with patch.object(snapshots, 'digest_file', side_effect=observed_digest):
                self.assertTrue(snapshots.compare_context_dependencies(snapshot,
                    source_paths=('src/package.json',),
                    target_paths=('out/view.txt',))['admitted'])
            self.assertTrue(reads)
            self.assertEqual(set(reads), {'src/package.json','out/view.txt'})
            after = snapshots.capture_context_effects(snapshot)
            self.assertEqual((output.read_bytes(),output.stat().st_mtime_ns),
                             (b'view\n',before['files']['out/view.txt']['mtime_ns']))
            self.assertTrue(snapshots.compare_context_effects(before,after)['no_op'])
            candidate = root/'out/.candidate'
            candidate.write_bytes(b'transient report\n')
            during = snapshots.capture_context_effects(snapshot)
            self.assertEqual(snapshots.compare_context_effects(before,during)['byte_changes'],
                             ['out/.candidate'])
            candidate.unlink()
            self.assertTrue(snapshots.compare_context_effects(before,
                snapshots.capture_context_effects(snapshot))['no_op'])

    def test_t041_context_cost_and_noop_negative_controls(self):
        """Incomplete ledgers, budget reset, unknown usage and timestamp churn fail closed."""
        reports, snapshots = self._t041_helpers()
        events = self._t041_events()
        kwargs = {'run_id':'RUN-1', 'launched_attempt_ids':['A-1','A-2','A-3'],
                  'allowed_effect_paths':['out/.candidate','out/view.txt']}
        for missing in ('E-2','E-4','E-7'):
            with self.subTest(missing=missing), self.assertRaises(reports.ReportError):
                reports.summarize_context_events(
                    [event for event in events if event['event_id'] != missing], **kwargs)
        for changed in (
            {'event_id':'E-1'}, {'run_id':'OTHER'}, {'snapshot_id':'c'*64},
            {'scope':{'paths':['other'], 'categories':['architecture']}},
            {'path':'outside/view.txt'}, {'related_attempt_ids':['UNKNOWN']},
        ):
            bad = copy.deepcopy(events)
            index = 5 if 'path' in changed else 6 if 'related_attempt_ids' in changed else 1
            bad[index].update(changed)
            with self.subTest(changed=changed), self.assertRaises(reports.ReportError):
                reports.summarize_context_events(bad, **kwargs)

        value=example_observation()
        value['launches'].append({**value['launches'][0], 'attempt_id':'A-2'})
        incomplete=summarize_observation(value)
        self.assertIsNone(incomplete['tokens'])
        self.assertEqual(incomplete['unknown_usage_attempts'], ['A-2'])
        self.assertFalse(incomplete['money']['complete'])
        self.assertEqual(incomplete['money']['unknown_attempts'], ['A-1','A-2'])
        value['observations'][0]['usage']['cache_read_tokens']=None
        self.assertEqual(summarize_observation(value)['budget']['tokens'], 'unknown')

        categories = sorted(reports.CATEGORIES)
        assignments = []
        for category in categories:
            parent = 'root_' + category
            assignments.append({'assignment_id':parent, 'parent_id':None,
                'scope':{'paths':[f'{category}/a',f'{category}/b'],
                         'categories':[category]}})
            for suffix in ('a','b'):
                assignments.append({'assignment_id':parent+'_'+suffix,
                    'parent_id':parent,
                    'scope':{'paths':[f'{category}/{suffix}'],
                             'categories':[category]}})
        run={'mode':'full', 'snapshot_id':'a'*64, 'deadline_ms':1000,
             'budgets':{'time_limit_ms':1000,'token_limit':1000,'tool_limit':100},
             'assignments':assignments}
        attempts=[{'assignment_id':item['assignment_id'],
                   'attempt_id':'A'+str(index)}
                  for index,item in enumerate(assignments)]
        attempts += [{'assignment_id':'root_'+category,
                      'attempt_id':'R'+str(index)}
                     for index,category in enumerate(categories)]
        self.assertEqual(len(attempts),24)
        for index,candidate in enumerate(attempts):
            self.assertEqual(reports.admit_scout_attempt(run,attempts[:index],
                candidate,now_ms=10),candidate)
        resume_candidate={'assignment_id':'root_'+categories[0]+'_a',
                          'attempt_id':'AFTER_LIMIT'}
        for _ in range(2):
            with self.assertRaisesRegex(reports.ReportError,'ATTEMPT_LIMIT'):
                reports.admit_scout_attempt(run,attempts,resume_candidate,now_ms=10)
        with self.assertRaisesRegex(reports.ReportError,'RUN_DEADLINE'):
            reports.admit_scout_attempt(run,attempts[:1],
                {'assignment_id':'root_'+categories[0], 'attempt_id':'TOO_LATE'},
                now_ms=1000)
        one=attempts[:1]
        retry={'assignment_id':one[0]['assignment_id'],'attempt_id':'RETRY'}
        self.assertEqual(reports.admit_scout_attempt(run,one,retry,now_ms=10),retry)
        with self.assertRaisesRegex(reports.ReportError,'RETRY_LIMIT'):
            reports.admit_scout_attempt(run,one+[retry],
                {'assignment_id':one[0]['assignment_id'],'attempt_id':'RESET_TRY'},
                now_ms=10)

        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'repo'; root.mkdir(); (root/'src').mkdir(); (root/'out').mkdir()
            subprocess.run(['git','-C',str(root),'init','-q','-b','main'], check=True,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            (root/'src/package.json').write_bytes(b'{}\n')
            output=root/'out/view.txt'; output.write_bytes(b'same\n')
            subprocess.run(['git','-C',str(root),'add','--','src/package.json'], check=True,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            subprocess.run(['git','-C',str(root),'-c','user.name=Fixture',
                            '-c','user.email=fixture@example.test','commit','-qm','initial'],
                           check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            snapshot=snapshots.context_snapshot(root,source_paths=('src/package.json',),
                target_paths=('out/view.txt',),allowed_effect_paths=('out/.candidate',))
            before=snapshots.capture_context_effects(snapshot)
            output.write_bytes(b'same\n')
            later=before['files']['out/view.txt']['mtime_ns']+2_000_000_000
            os.utime(output,ns=(later,later))
            churn=snapshots.compare_context_effects(before,
                snapshots.capture_context_effects(snapshot))
            self.assertFalse(churn['no_op'])
            self.assertEqual(churn['timestamp_only_changes'], ['out/view.txt'])
            output.write_bytes(b'changed\n')
            changed=snapshots.compare_context_effects(before,
                snapshots.capture_context_effects(snapshot))
            self.assertEqual(changed['byte_changes'], ['out/view.txt'])

    def test_t045_a_b_qualification_evidence_positive_controls(self):
        """Prepare real paired fixture repos and retain a local process attempt."""
        from _context_fixturelib import load_catalog, snapshot
        catalog = load_catalog(ROOT / '.github/fixtures/context-onboarding/cases.json')
        with tempfile.TemporaryDirectory() as root:
            pair = prepare_qualification_pair(catalog, 'tiny-python', Path(root).resolve() / 'pair')
            self.assertEqual(set(pair['arms']), {'A', 'B'})
            self.assertEqual(snapshot(pair['arms']['A']['solver']),
                             snapshot(pair['arms']['B']['solver']))
            for arm in ('A', 'B'):
                solver = Path(pair['arms'][arm]['solver'])
                evaluator = Path(pair['arms'][arm]['evaluator'])
                self.assertFalse(evaluator.is_relative_to(solver))
                self.assertFalse((solver / 'oracle.json').exists())
                self.assertEqual(pair['arms'][arm]['oracle_sha256'],
                                 pair['oracle_sha256'])
            self.assertEqual(pair['qualification'], 'unverified')
            settings_text = Path(pair['arms']['A']['settings']).read_text(encoding='utf-8')
            self.assertNotIn(str(ROOT), settings_text)
            configured = json.loads(settings_text)['hooks']['InstructionsLoaded'][0]['hooks'][0]
            self.assertEqual(set(configured), {'type', 'command'})
            selected = {'admission': 'requires_actor_check', 'task_paths': ['app.py'],
                        'instructions': [{'epoch': 'fixture-v1'}]}
            delivery = prepare_qualification_delivery(
                pair, arm='A', selected_packet=selected, actor='author-1',
                task_id='tiny-python', host_epoch='host-v1')
            self.assertEqual(delivery['action'], 'deliver')
            self.assertIn('fixture-v1', delivery['delivery_text'])
            record = capture_qualification_attempt(
                pair, arm='A', attempt_id='ATTEMPT-1',
                argv=[sys.executable, '-c', 'import sys; print(sys.stdin.read())'],
                actor_input='Fixture task', delivery_text=delivery['delivery_text'],
                timeout_seconds=10, evidence_kind='harness_only')
            self.assertEqual(record['exit_code'], 0)
            self.assertGreaterEqual(record['elapsed_ms'], 0)
            self.assertEqual(record['qualification'], 'unverified')
            self.assertEqual(record['delivery_status'], 'sent_to_process_stdin')
            self.assertIn(b'fixture-v1', Path(record['stdout']).read_bytes())
            self.assertEqual(len(list(Path(pair['controller']).glob('A-ATTEMPT-1.json'))), 1)
            self.assertEqual(pair['arms']['A']['files'], pair['arms']['B']['files'])
            event_log = Path(pair['arms']['A']['event_log'])
            event = json.dumps({
                'hook_event_name': 'InstructionsLoaded',
                'harness_marker': 'source-test-only'}).encode('utf-8')
            subprocess.run(configured['command'], shell=True,
                           input=event, cwd=pair['arms']['A']['solver'],
                           check=True, capture_output=True)
            assessment = assess_qualification_pair(pair)
            self.assertEqual(assessment['native_event_log_sha256']['A'],
                             _trial_digest(event_log.read_bytes()))
            self.assertEqual(assessment['qualification'], 'unverified')
            reported_a = example_observation()
            reported_a['snapshot_sha256'] = pair['fixture_snapshot_sha256']
            reported_a['launches'][0]['attempt_id'] = 'ATTEMPT-1'
            reported_a['observations'][0]['attempt_id'] = 'ATTEMPT-1'
            reported_b = copy.deepcopy(reported_a)
            reported_b['run_id'] = 'RUN-B'
            reported_b['launches'] = []
            reported_b['observations'] = []
            supplied = {arm: json.dumps(value).encode('utf-8') for arm, value in
                        {'A': reported_a, 'B': reported_b}.items()}
            accounted = assess_qualification_pair(pair, supplied)
            self.assertTrue(accounted['reported_accounting']['A']['usage_complete'])
            self.assertFalse(accounted['reported_accounting']['B']['usage_complete'])
            self.assertEqual(accounted['qualification'], 'unverified')
            fix_catalog = load_catalog(
                ROOT / '.github/fixtures/context-onboarding/solvable-fix.json')
            fix_pair = prepare_qualification_pair(fix_catalog, 'falsy-override-fix',
                                                  Path(root).resolve() / 'fix-pair')
            self.assertEqual(fix_pair['case_sha256'],
                             '866a9ce336cb45479f29a207a409835922cdf320b0c629cd20e5199b5224a871')
            self.assertEqual(fix_pair['arms']['A']['files'], fix_pair['arms']['B']['files'])
            installed = Path(root).resolve() / 'installed-candidate'
            installed.mkdir()
            helper = installed / '_contextselectlib.py'
            helper.write_text('def prepare_actor_delivery(packet, **kw):\n'
                              '    return {"action": "deliver", "delivery_text": "INSTALLED-SELECTOR", '
                              '"binding": {"source_epoch": kw["source_epoch"], '
                              '"worktree": kw["worktree"]}, "attempt": {"number": 1}}\n',
                              encoding='utf-8')
            installed_b = prepare_qualification_delivery(
                pair, arm='B', selected_packet=selected, actor='author-1',
                task_id='tiny-python', host_epoch='host-v1', mode='controlled_host',
                installed_selector=helper, selector_sha256=_trial_digest(helper.read_bytes()),
                candidate_sha256='a' * 64)
            self.assertEqual(installed_b['delivery_text'], 'INSTALLED-SELECTOR')
            self.assertEqual(installed_b['candidate_sha256'], 'a' * 64)
            baseline_a = prepare_qualification_delivery(
                pair, arm='A', selected_packet=selected, actor='author-1',
                task_id='tiny-python', host_epoch='host-v1', mode='controlled_host',
                candidate_sha256='a' * 64)
            self.assertEqual(baseline_a['action'], 'baseline')
            self.assertIsNone(baseline_a['delivery_text'])

    def test_t045_a_b_qualification_evidence_negative_controls(self):
        """Missing, repeated, leaking and fabricated evidence never qualify."""
        from _context_fixturelib import load_catalog
        catalog = load_catalog(ROOT / '.github/fixtures/context-onboarding/cases.json')
        with tempfile.TemporaryDirectory() as root:
            pair = prepare_qualification_pair(catalog, 'already-instructed',
                                               Path(root).resolve() / 'pair')
            with self.assertRaises(ValueError):
                prepare_qualification_pair(catalog, 'already-instructed', Path(root).resolve() / 'pair')
            with self.assertRaises(ValueError):
                capture_qualification_attempt(pair, arm='C', attempt_id='ATTEMPT-1',
                    argv=[sys.executable, '-c', 'print(1)'], actor_input='task',
                    delivery_text='packet', evidence_kind='harness_only')
            with self.assertRaises(ValueError):
                capture_qualification_attempt(pair, arm='B', attempt_id='ATTEMPT-1',
                    argv=[sys.executable, '--restricted'], actor_input='task',
                    delivery_text='packet', evidence_kind='controlled_host')
            self.assertFalse((Path(pair['controller']) / 'launches.jsonl').exists())
            source_selector = ROOT / 'core/pysrc/_contextselectlib.py'
            with self.assertRaises(ValueError):
                prepare_qualification_delivery(pair, arm='B', selected_packet={
                    'admission': 'requires_actor_check', 'task_paths': ['app.py'],
                    'instructions': [{'epoch': 'fixture-v1'}]}, actor='author-1',
                    task_id='already-instructed', host_epoch='host-v1',
                    mode='controlled_host', installed_selector=source_selector,
                    selector_sha256=_trial_digest(source_selector.read_bytes()),
                    candidate_sha256='a' * 64)
            configured = json.loads(Path(pair['arms']['B']['settings']).read_text(
                encoding='utf-8'))['hooks']['InstructionsLoaded'][0]['hooks'][0]
            bad_event = subprocess.run(
                configured['command'], shell=True,
                input=b'{"hook_event_name":"Other"}',
                cwd=pair['arms']['B']['solver'], capture_output=True)
            self.assertNotEqual(bad_event.returncode, 0)
            self.assertFalse(Path(pair['arms']['B']['event_log']).exists())
            first = capture_qualification_attempt(pair, arm='A', attempt_id='ATTEMPT-1',
                argv=[sys.executable, '-c', 'import sys; sys.exit(3)'],
                actor_input='task', delivery_text='packet', evidence_kind='harness_only')
            self.assertEqual(first['exit_code'], 3)
            self.assertEqual(first['status'], 'failed')
            with self.assertRaises(FileExistsError):
                capture_qualification_attempt(pair, arm='A', attempt_id='ATTEMPT-1',
                    argv=[sys.executable, '-c', 'print(1)'], actor_input='task',
                    delivery_text='packet', evidence_kind='harness_only')
            self.assertEqual(len(list(Path(pair['controller']).glob('A-ATTEMPT-1.json'))), 1)
            result = assess_qualification_pair(pair)
            self.assertEqual(result['qualification'], 'unverified')
            self.assertEqual(result['missing_arms'], ['B'])
            unmatched = example_observation()
            unmatched['snapshot_sha256'] = pair['fixture_snapshot_sha256']
            with self.assertRaises(ValueError):
                assess_qualification_pair(pair, {'A': json.dumps(unmatched).encode(),
                    'B': json.dumps(unmatched).encode()})
            record_path = Path(pair['controller']) / 'A-ATTEMPT-1.json'
            original = record_path.read_bytes()
            record_path.unlink()
            with self.assertRaises(ValueError):
                assess_qualification_pair(pair)
            record_path.write_bytes(original)
            output_path = Path(first['stdout'])
            output_before = output_path.read_bytes()
            output_path.write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                assess_qualification_pair(pair)
            output_path.write_bytes(output_before)
            guidance = Path(pair['arms']['A']['solver']) / 'AGENTS.md'
            guidance_before = guidance.read_bytes()
            guidance.write_bytes(b'changed human guidance\n')
            damaged = assess_qualification_pair(pair)
            self.assertEqual(damaged['workspace_effects']['A']['preservation'], 'contradicted')
            self.assertEqual(damaged['workspace_effects']['A']['broken_preserve_paths'], ['AGENTS.md'])
            guidance.write_bytes(guidance_before)
            oracle_bytes = (Path(pair['arms']['A']['evaluator']) / 'oracle.json').read_bytes()
            (Path(pair['arms']['A']['solver']) / 'leaked-oracle.json').write_bytes(oracle_bytes)
            with self.assertRaises(ValueError):
                assess_qualification_pair(pair)

    def test_t046_scoped_readiness_claim_positive_controls(self):
        """Scoped source accounting keeps real host readiness pending."""
        from _context_fixturelib import load_catalog
        catalog = load_catalog(ROOT / '.github/fixtures/context-onboarding/cases.json')
        with tempfile.TemporaryDirectory() as root:
            pair = prepare_qualification_pair(catalog, 'tiny-python', Path(root).resolve() / 'pair')
            observations = {}
            profile = {key: 'fixture-host' for key in
                       observation_schema()['properties']['profile']['properties']}
            profile['package_sha256'] = 'a' * 64
            profile['settings_sha256'] = pair['arms']['B']['settings_sha256']
            profile.update(shell='PowerShell', git_version='fixture-git',
                           worktree_mode='isolated-fixture',
                           permission_profile='fixture-only',
                           executable_sha256='c' * 64)
            for arm in ('A', 'B'):
                attempt = capture_qualification_attempt(pair, arm=arm,
                    attempt_id='ATTEMPT-1', argv=[sys.executable, '-c',
                    'import sys; sys.stdout.write(sys.stdin.read())'],
                    actor_input='Fixture task', delivery_text='Fixture context',
                    evidence_kind='harness_only')
                self.assertEqual(attempt['status'], 'completed')
                observed = example_observation()
                observed['snapshot_sha256'] = pair['fixture_snapshot_sha256']
                observed['profile'] = {key: profile[key] for key in
                    observation_schema()['properties']['profile']['properties']}
                observed['profile']['settings_sha256'] = pair['arms'][arm]['settings_sha256']
                observed['launches'][0]['attempt_id'] = 'ATTEMPT-1'
                observed['observations'][0]['attempt_id'] = 'ATTEMPT-1'
                observations[arm] = json.dumps(observed).encode('utf-8')
            report = assess_scoped_readiness(pair, profile=profile,
                installed_evidence={'profile': profile.copy(),
                                    'candidate_sha256': 'a' * 64,
                                    'status': 'source_checked'},
                task_states={'T-044': 'pending', 'T-045': 'pending',
                             'T-046': 'pending'}, observations=observations,
                p1_disposition='no_go', greenfield_profile=profile.copy())
            self.assertEqual(report['profile'], profile)
            self.assertEqual(report['core_readiness'], 'unverified')
            self.assertEqual(report['paired_qualification'], 'unverified')
            self.assertTrue(report['reported_accounting_complete'])
            self.assertEqual(report['pending_tasks'], ['T-044', 'T-045', 'T-046'])
            self.assertEqual(report['plan_completion'], 'pending')
            self.assertEqual(report['p1'], {'disposition': 'no_go',
                                            'implementation': 'absent'})
            self.assertEqual(report['g1_reuse'], {'scope': 'first_input_only',
                                                   'status': 'unverified'})
            self.assertEqual(report['other_hosts'], 'unverified')
            self.assertEqual(report['commit_authority'], 'not_granted')
            self.assertEqual(report['release_authority'], 'not_granted')

    def test_t046_scoped_readiness_claim_negative_controls(self):
        """Mismatched and self-promoted reports cannot grant readiness."""
        from _context_fixturelib import load_catalog
        catalog = load_catalog(ROOT / '.github/fixtures/context-onboarding/cases.json')
        with tempfile.TemporaryDirectory() as root:
            pair = prepare_qualification_pair(catalog, 'already-instructed',
                                               Path(root).resolve() / 'pair')
            profile = {key: 'fixture-host' for key in
                       observation_schema()['properties']['profile']['properties']}
            profile['package_sha256'] = 'a' * 64
            profile['settings_sha256'] = pair['arms']['B']['settings_sha256']
            profile.update(shell='PowerShell', git_version='fixture-git',
                           worktree_mode='isolated-fixture',
                           permission_profile='fixture-only',
                           executable_sha256='c' * 64)
            installed = {'profile': profile.copy(), 'candidate_sha256': 'a' * 64,
                         'status': 'cold_installed_observed'}
            states = {'T-044': 'accepted', 'T-045': 'accepted', 'T-046': 'pending'}
            report = assess_scoped_readiness(pair, profile=profile,
                installed_evidence=installed, task_states=states,
                p1_disposition='not_selected')
            self.assertEqual(report['core_readiness'], 'unverified')
            self.assertEqual(report['missing_arms'], ['A', 'B'])
            self.assertEqual(report['p1']['implementation'], 'absent')
            self.assertEqual(report['commit_authority'], 'not_granted')
            all_reported_accepted = assess_scoped_readiness(pair, profile=profile,
                installed_evidence=installed,
                task_states={task: 'accepted' for task in states})
            self.assertEqual(all_reported_accepted['plan_completion'], 'unverified')
            self.assertEqual(all_reported_accepted['commit_authority'], 'not_granted')
            mismatched = copy.deepcopy(installed)
            mismatched['profile']['model'] = 'other-model'
            with self.assertRaises(ValueError):
                assess_scoped_readiness(pair, profile=profile,
                    installed_evidence=mismatched, task_states=states)
            incomplete = profile.copy()
            incomplete.pop('permission_profile')
            with self.assertRaises(ValueError):
                assess_scoped_readiness(pair, profile=incomplete,
                    installed_evidence=installed, task_states=states)
            false_claim = copy.deepcopy(installed)
            false_claim['status'] = 'qualified'
            with self.assertRaises(ValueError):
                assess_scoped_readiness(pair, profile=profile,
                    installed_evidence=false_claim, task_states=states)
            other_profile = profile.copy()
            other_profile['host_version'] = 'other-version'
            unqualified_g1 = assess_scoped_readiness(pair, profile=profile,
                installed_evidence=installed, task_states=states,
                greenfield_profile=other_profile)
            self.assertEqual(unqualified_g1['g1_reuse']['status'], 'unsupported_profile')
            with self.assertRaises(ValueError):
                assess_scoped_readiness(pair, profile=profile,
                    installed_evidence=installed,
                    task_states={'T-044': 'accepted', 'T-045': 'accepted'})
            wrong_observation = example_observation()
            wrong_observation['snapshot_sha256'] = pair['fixture_snapshot_sha256']
            wrong_observation['profile'] = {key: profile[key] for key in
                observation_schema()['properties']['profile']['properties']}
            wrong_observation['profile']['model'] = 'other-model'
            supplied = json.dumps(wrong_observation).encode('utf-8')
            with self.assertRaises(ValueError):
                assess_scoped_readiness(pair, profile=profile,
                    installed_evidence=installed, task_states=states,
                    observations={'A': supplied, 'B': supplied})
            oracle = Path(pair['arms']['A']['evaluator']) / 'oracle.json'
            original = oracle.read_bytes()
            oracle.write_bytes(b'{}')
            with self.assertRaises(ValueError):
                assess_scoped_readiness(pair, profile=profile,
                    installed_evidence=installed, task_states=states)
            oracle.write_bytes(original)


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
