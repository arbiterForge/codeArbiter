#!/usr/bin/env python3
# codeArbiter -- bounded, pure decoding of internal scout evidence reports.
#
# Public API: decode_report(payload, *, expected) -> detached normalized dict;
# admit_scout_attempt and join_scout_reports validate a bounded host-owned run;
# validate_command_record and validate_constraint_reference normalize inert
# derived records without changing the v1 transport schema.
# resolve_scoped_command_guidance selects one source-bound command and reports
# method-aware execution evidence without executing it or granting authority.
# ReportError(code, field) reports only bounded code-owned diagnostics.
# No filesystem, subprocess, network, dispatch, approval, or artifact mutation.
# A matching supplied identity is not proof that the host actually inspected it.
# This codec admits report transport; category gaps remain gaps. It does not
# establish host containment, truth, freshness, or readiness.

from __future__ import annotations

import hashlib
import json
import re
import unicodedata

SCHEMA_VERSION = 1
MAX_REPORT_BYTES = 64 * 1024
MAX_DEPTH = 12
MAX_NODES = 4096
MAX_PATHS = 16
MAX_REPORT_EVIDENCE = 128
MAX_EVIDENCE = 64  # Derived command/constraint record references, not scout reports.
MAX_FINDINGS = 64
CATEGORIES = frozenset({'stack', 'infrastructure', 'architecture', 'security', 'tests', 'data'})
OUTCOMES = frozenset({'observed', 'not_applicable', 'not_found_in_scope',
                      'not_inspected', 'ambiguous', 'failed', 'oversize'})
PREDICATES = frozenset({'manifests', 'instructions', 'configuration', 'source',
                        'entry_points', 'tests', 'infrastructure', 'security', 'data'})
EXCLUSIONS = frozenset({'ignored', 'vendor', 'generated', 'submodule', 'nested_repository',
                        'sparse', 'outside_authorized_scope', 'unreadable'})
CONFIDENCE = {'high': 'high', 'strong': 'high', 'HIGH': 'high',
              'medium': 'medium', 'moderate': 'medium', 'MEDIUM': 'medium',
              'low': 'low', 'weak': 'low', 'LOW': 'low'}
FINDING_NAMES = {
    'stack': frozenset({'runtime', 'dependency', 'manifest'}),
    'infrastructure': frozenset({'command_ref', 'prerequisite', 'configuration', 'deploy_entry'}),
    'architecture': frozenset({'entry_point', 'source_of_truth', 'generated_path', 'ownership_boundary'}),
    'security': frozenset({'boundary', 'control', 'policy_reference'}),
    'tests': frozenset({'command_ref', 'test_boundary', 'fixture', 'verification_reference'}),
    'data': frozenset({'datastore', 'schema', 'migration', 'dataflow'}),
}
_ID = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,63}\Z')
_DIGESTS = {'sha256-raw': 64, 'git-blob-normalized-sha1': 40}
_RESERVED = re.compile(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z', re.IGNORECASE)


class ReportError(ValueError):
    """Invalid evidence input; never echo source values into diagnostics."""

    def __init__(self, code, field='report'):
        self.code = code
        self.field = field
        super().__init__(f'{code} at {field}')


def _need(condition, code, field):
    if not condition:
        raise ReportError(code, field)


def _object(value, keys, field):
    _need(type(value) is dict, 'OBJECT_REQUIRED', field)
    _need(not set(value) - set(keys), 'UNKNOWN_FIELD', field)
    _need(not set(keys) - set(value), 'MISSING_FIELD', field)
    return value


def _list(value, maximum, field):
    _need(type(value) is list, 'ARRAY_REQUIRED', field)
    _need(len(value) <= maximum, 'ITEM_LIMIT', field)
    return value


def _text(value, maximum, field, nullable=False):
    if value is None and nullable:
        return None
    _need(type(value) is str and bool(value.strip()), 'TEXT_REQUIRED', field)
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        raise ReportError('INVALID_UNICODE', field) from None
    _need(size <= maximum, 'TEXT_LIMIT', field)
    _need(not any(unicodedata.category(c) in ('Cc', 'Cs', 'Cf') for c in value),
          'CONTROL_CHARACTER', field)
    return value


def _enum(value, choices, field):
    _need(type(value) is str and value in choices, 'UNKNOWN_VALUE', field)
    return value


def _id(value, field):
    _need(type(value) is str and _ID.fullmatch(value) is not None, 'INVALID_ID', field)
    return value


def _digest(value, length, field):
    _need(type(value) is str and re.fullmatch('[0-9a-f]{'+str(length)+'}', value) is not None,
          'INVALID_DIGEST', field)
    return value


def _path(value, field, root=False):
    value = _text(value, 1024, field)
    if root and value == '.':
        return value
    parts = value.split('/')
    _need(unicodedata.normalize('NFC', value) == value and '\\' not in value
          and not any(c in value for c in ':*?"<>|')
          and all(p not in ('', '.', '..') and p.casefold() != '.git'
                  and p[-1:] not in (' ', '.') and not _RESERVED.fullmatch(p) for p in parts),
          'UNSAFE_PATH', field)
    return value


def _within(path, parent):
    return parent == '.' or path == parent or path.startswith(parent + '/')


def _unique(values, field, folded=False):
    identities = [s.casefold() if folded else s for s in values]
    _need(len(set(identities)) == len(identities), 'DUPLICATE_ID', field)


def _paths(value, field, parents=None, nonempty=False):
    result = [_path(p, field, root=True) for p in _list(value, MAX_PATHS, field)]
    _unique(result, field, folded=True)
    if nonempty:
        _need(bool(result), 'SEARCH_COVERAGE', field)
    for index, path in enumerate(result):
        if parents is not None:
            _need(any(_within(path, parent) for parent in parents), 'OUT_OF_SCOPE', field)
        _need(not any(_within(path, other) or _within(other, path)
                      for other in result[index+1:]), 'OVERLAPPING_SCOPE', field)
    return sorted(result)


def _scope(value, field):
    _object(value, ('paths', 'categories'), field)
    paths = _paths(value['paths'], field+'.paths', nonempty=True)
    categories = [_enum(c, CATEGORIES, field+'.categories')
                  for c in _list(value['categories'], len(CATEGORIES), field+'.categories')]
    _unique(categories, field+'.categories')
    _need(bool(categories), 'CATEGORY_COVERAGE', field)
    return {'paths': paths, 'categories': sorted(categories)}


def _binding(value, field):
    _object(value, ('assignment_id', 'attempt_id', 'snapshot_id', 'scope'), field)
    return {'assignment_id': _id(value['assignment_id'], field+'.assignment_id'),
            'attempt_id': _id(value['attempt_id'], field+'.attempt_id'),
            'snapshot_id': _digest(value['snapshot_id'], 64, field+'.snapshot_id'),
            'scope': _scope(value['scope'], field+'.scope')}


def _coverage(value, scope, field):
    _object(value, ('searched_paths', 'predicates', 'excluded'), field)
    searched = _paths(value['searched_paths'], field+'.searched_paths', scope['paths'])
    predicates = [_enum(p, PREDICATES, field+'.predicates')
                  for p in _list(value['predicates'], len(PREDICATES), field+'.predicates')]
    _unique(predicates, field+'.predicates')
    excluded = []
    for index, entry in enumerate(_list(value['excluded'], MAX_PATHS, field+'.excluded')):
        part = field+'.excluded['+str(index)+']'
        _object(entry, ('path', 'reason'), part)
        path = _path(entry['path'], part+'.path', root=True)
        _need(any(_within(path, parent) for parent in scope['paths']), 'OUT_OF_SCOPE', part)
        _need(not any(_within(searched_path, path) for searched_path in searched),
              'SEARCH_COVERAGE', part)
        excluded.append({'path': path, 'reason': _enum(entry['reason'], EXCLUSIONS, part+'.reason')})
    _unique([e['path'] for e in excluded], field+'.excluded', folded=True)
    return {'searched_paths': searched, 'predicates': sorted(predicates),
            'excluded': sorted(excluded, key=lambda e: e['path'])}


def _evidence(value, coverage, scope, field):
    result = []
    for index, entry in enumerate(_list(value, MAX_REPORT_EVIDENCE, field)):
        part = field+'['+str(index)+']'
        _object(entry, ('id', 'path', 'start_line', 'end_line', 'digest_method', 'digest'), part)
        path = _path(entry['path'], part+'.path')
        _need(any(_within(path, root) for root in scope['paths'])
              and any(_within(path, root) for root in coverage['searched_paths']), 'OUT_OF_SCOPE', part)
        _need(not any(_within(path, e['path']) for e in coverage['excluded']), 'EXCLUDED_EVIDENCE', part)
        start, end = entry['start_line'], entry['end_line']
        _need(type(start) is int and type(end) is int and 1 <= start <= end <= 10_000_000,
              'INVALID_RANGE', part)
        method = _enum(entry['digest_method'], _DIGESTS, part+'.digest_method')
        result.append({'id': _id(entry['id'], part+'.id'), 'path': path,
                       'start_line': start, 'end_line': end, 'digest_method': method,
                       'digest': _digest(entry['digest'], _DIGESTS[method], part+'.digest')})
    _unique([e['id'] for e in result], field)
    spellings = {}
    for entry in result:
        path = entry['path']; prior = spellings.setdefault(path.casefold(), path)
        _need(prior == path, 'PATH_COLLISION', field)
    return sorted(result, key=lambda e: e['id'])


def _outcome(value, scope, field):
    _object(value, ('category', 'status', 'confidence', 'reason', 'coverage', 'evidence', 'findings'), field)
    category = _enum(value['category'], CATEGORIES, field+'.category')
    _need(category in scope['categories'], 'CATEGORY_COVERAGE', field)
    status = _enum(value['status'], OUTCOMES, field+'.status')
    confidence = value['confidence']
    if confidence is not None:
        confidence = CONFIDENCE[_enum(confidence, CONFIDENCE, field+'.confidence')]
    reason = _text(value['reason'], 512, field+'.reason', nullable=True)
    coverage = _coverage(value['coverage'], scope, field+'.coverage')
    evidence = _evidence(value['evidence'], coverage, scope, field+'.evidence')
    evidence_ids = {e['id'] for e in evidence}
    findings = []
    used = set()
    for index, entry in enumerate(_list(value['findings'], MAX_FINDINGS, field+'.findings')):
        part = field+'.findings['+str(index)+']'
        _object(entry, ('id', 'name', 'value', 'evidence_refs'), part)
        refs = [_id(ref, part+'.evidence_refs') for ref in _list(entry['evidence_refs'], MAX_REPORT_EVIDENCE, part)]
        _unique(refs, part+'.evidence_refs')
        _need(bool(refs) and set(refs) <= evidence_ids, 'DANGLING_EVIDENCE', part)
        used.update(refs)
        findings.append({'id': _id(entry['id'], part+'.id'),
                         'name': _enum(entry['name'], FINDING_NAMES[category], part+'.name'),
                         'value': _text(entry['value'], 256, part+'.value'), 'evidence_refs': sorted(refs)})
    _unique([f['id'] for f in findings], field+'.findings')
    if status in ('observed', 'ambiguous'):
        if findings:
            _need(confidence is not None, 'CONFIDENCE_REQUIRED', field)
            _need(used == evidence_ids, 'UNUSED_EVIDENCE', field)
        if status == 'observed':
            _need(bool(findings) and confidence is not None, 'EVIDENCE_REQUIRED', field)
    else:
        _need(not findings, 'UNSUPPORTED_FINDING', field)
    if status in ('not_inspected', 'failed', 'oversize'):
        _need(confidence is None, 'UNSUPPORTED_CONFIDENCE', field)
    if status != 'observed':
        _need(reason is not None, 'REASON_REQUIRED', field)
    if status == 'not_applicable':
        _need(bool(evidence) and confidence is not None, 'EVIDENCE_REQUIRED', field)
    if status in ('observed', 'not_applicable', 'not_found_in_scope'):
        _need(bool(coverage['searched_paths']) and bool(coverage['predicates']), 'SEARCH_COVERAGE', field)
    return {'category': category, 'status': status, 'confidence': confidence, 'reason': reason,
            'coverage': coverage, 'evidence': evidence, 'findings': sorted(findings, key=lambda f: f['id'])}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, 'DUPLICATE_KEY', 'report')
        result[key] = value
    return result


def _integer(value):
    _need(len(value) <= 16, 'NUMBER_LIMIT', 'report')
    return int(value)


def _invalid_number(_value):
    raise ReportError('NUMBER_SHAPE')


def _decode(payload):
    _need(type(payload) in (bytes, str), 'JSON_REQUIRED', 'report')
    try:
        raw = payload if type(payload) is bytes else payload.encode('utf-8')
        _need(len(raw) <= MAX_REPORT_BYTES, 'REPORT_TOO_LARGE', 'report')
        text = raw.decode('utf-8', errors='strict')
    except UnicodeError:
        raise ReportError('INVALID_UNICODE') from None
    # Bound nesting before the JSON parser allocates nested containers. Ignore
    # brackets inside strings, including escaped quotes and backslashes.
    depth = 0
    string = escaped = False
    for char in text:
        if string:
            if escaped: escaped = False
            elif char == '\\': escaped = True
            elif char == '"': string = False
        elif char == '"': string = True
        elif char in '[{':
            depth += 1
            _need(depth <= MAX_DEPTH, 'DEPTH_LIMIT', 'report')
        elif char in ']}': depth -= 1
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_int=_integer,
                           parse_float=_invalid_number, parse_constant=_invalid_number)
    except (ValueError, RecursionError) as error:
        if isinstance(error, ReportError): raise
        raise ReportError('INVALID_JSON') from None
    pending = [value]; count = 0
    while pending:
        item = pending.pop(); count += 1
        _need(count <= MAX_NODES, 'NODE_LIMIT', 'report')
        if type(item) is dict: pending.extend(item.values())
        elif type(item) is list: pending.extend(item)
    return value


def decode_report(payload, *, expected):
    """Decode one report against a caller-owned assignment/attempt snapshot.

    `expected` has assignment_id, attempt_id, snapshot_id and exact scope.
    Failed/oversize transport is returned distinctly with no outcome content.
    A complete report must account for every assigned category, including gaps.
    Returned text remains untrusted evidence, not commands or normative rules.
    """
    binding = _binding(expected, 'expected')
    value = _decode(payload)
    keys = ('schema_version', 'assignment_id', 'attempt_id', 'snapshot_id', 'scope',
            'transport', 'diagnostic', 'outcomes')
    _object(value, keys, 'report')
    _need(type(value['schema_version']) is int and value['schema_version'] == SCHEMA_VERSION,
          'UNSUPPORTED_VERSION', 'report.schema_version')
    actual = _binding({k: value[k] for k in binding}, 'report.binding')
    _need(actual == binding, 'BINDING_MISMATCH', 'report.binding')
    transport = _enum(value['transport'], ('complete', 'failed', 'oversize'), 'report.transport')
    outcomes = _list(value['outcomes'], len(CATEGORIES), 'report.outcomes')
    if transport != 'complete':
        _need(not outcomes, 'TRANSPORT_CONTENT', 'report.outcomes')
        codes = ('SCOPE_TOO_LARGE', 'REPORT_TOO_LARGE') if transport == 'oversize' else (
            'TIMEOUT', 'UNAVAILABLE', 'TOOL_FAILURE', 'CANCELLED')
        diagnostic = _enum(value['diagnostic'], codes, 'report.diagnostic')
    else:
        _need(value['diagnostic'] is None, 'TRANSPORT_CONTENT', 'report.diagnostic')
        diagnostic = None
        outcomes = [_outcome(o, binding['scope'], 'report.outcomes['+str(i)+']')
                    for i, o in enumerate(outcomes)]
        _unique([o['category'] for o in outcomes], 'report.outcomes')
        _need({o['category'] for o in outcomes} == set(binding['scope']['categories']),
              'CATEGORY_COVERAGE', 'report.outcomes')
        _need(sum(len(o['evidence']) for o in outcomes) <= MAX_REPORT_EVIDENCE,
              'REPORT_EVIDENCE_LIMIT', 'report.outcomes')
    # One snapshot cannot contain conflicting identities for the same source
    # and method, including citations in separate categories. Different named
    # digest methods remain deliberately incomparable.
    spellings = {}
    source_identities = {}
    for outcome in outcomes:
        for source in outcome['evidence']:
            path = source['path']
            prior = spellings.setdefault(path.casefold(), path)
            _need(prior == path, 'PATH_COLLISION', 'report.outcomes')
            key = (path, source['digest_method'])
            digest = source_identities.setdefault(key, source['digest'])
            _need(digest == source['digest'], 'MIXED_SOURCE_IDENTITY', 'report.outcomes')
    result = {'schema_version': SCHEMA_VERSION, **actual, 'transport': transport,
              'diagnostic': diagnostic, 'outcomes': sorted(outcomes, key=lambda o: o['category'])}
    size = len(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    _need(size <= MAX_REPORT_BYTES, 'REPORT_TOO_LARGE', 'report')
    return result


MAX_SCOUT_ATTEMPTS = 24
MAX_SUBDIVISION_DEPTH = 3
MAX_SUBDIVISION_FANOUT = 4
MAX_JOIN_BYTES = 48 * 1024


def _scout_run(run):
    """Validate finite assignments; paths are preflight coverage atoms, not guessed files."""
    _object(run, ('mode', 'snapshot_id', 'deadline_ms', 'budgets', 'assignments'), 'run')
    mode = _enum(run['mode'], ('full', 'scoped'), 'run.mode')
    snapshot = _digest(run['snapshot_id'], 64, 'run.snapshot_id')
    deadline = run['deadline_ms']
    _need(type(deadline) is int and deadline > 0, 'RUN_DEADLINE', 'run.deadline_ms')
    budgets = _object(run['budgets'], ('time_limit_ms', 'token_limit', 'tool_limit'),
                      'run.budgets')
    for name, value in budgets.items():
        _need(type(value) is int and value > 0, 'BUDGET_REQUIRED', 'run.budgets.'+name)
    entries = _list(run['assignments'], MAX_SCOUT_ATTEMPTS, 'run.assignments')
    _need(bool(entries), 'CATEGORY_COVERAGE', 'run.assignments')
    assignments = {}
    children = {}
    for index, item in enumerate(entries):
        field = 'run.assignments['+str(index)+']'
        _need(type(item) is dict, 'OBJECT_REQUIRED', field)
        _need(not set(item) - {'assignment_id', 'parent_id', 'scope', 'overlap_reason'},
              'UNKNOWN_FIELD', field)
        _need({'assignment_id', 'parent_id', 'scope'} <= set(item),
              'MISSING_FIELD', field)
        assignment_id = _id(item['assignment_id'], field+'.assignment_id')
        _need(assignment_id not in assignments, 'DUPLICATE_ID', field+'.assignment_id')
        parent_id = item['parent_id']
        if parent_id is not None:
            parent_id = _id(parent_id, field+'.parent_id')
            _need(parent_id in assignments, 'PARENT_REQUIRED', field+'.parent_id')
        scope = _scope(item['scope'], field+'.scope')
        overlap_reason = item.get('overlap_reason')
        if overlap_reason is not None:
            _need(parent_id is not None, 'OVERLAPPING_SCOPE', field+'.overlap_reason')
            overlap_reason = _text(overlap_reason, 128, field+'.overlap_reason')
        depth = 0 if parent_id is None else assignments[parent_id]['depth'] + 1
        _need(depth <= MAX_SUBDIVISION_DEPTH, 'SUBDIVISION_DEPTH', field)
        assignments[assignment_id] = {'assignment_id': assignment_id,
                                      'parent_id': parent_id,
                                      'scope': scope, 'depth': depth,
                                      'overlap_reason': overlap_reason}
        if parent_id is not None:
            children.setdefault(parent_id, []).append(assignment_id)
    roots = [item for item in assignments.values() if item['parent_id'] is None]
    categories = [item['scope']['categories'][0] for item in roots
                  if len(item['scope']['categories']) == 1]
    _need(len(categories) == len(roots) and len(set(categories)) == len(categories),
          'CATEGORY_COVERAGE', 'run.assignments')
    if mode == 'full':
        _need(set(categories) == CATEGORIES, 'CATEGORY_COVERAGE', 'run.assignments')
    for parent_id, ids in children.items():
        field = 'run.assignments.'+parent_id
        _need(2 <= len(ids) <= MAX_SUBDIVISION_FANOUT, 'SUBDIVISION_FANOUT', field)
        parent = assignments[parent_id]
        covered = {}
        for child_id in ids:
            child = assignments[child_id]
            _need(child['scope']['categories'] == parent['scope']['categories'],
                  'SUBDIVISION_COVERAGE', field)
            paths = set(child['scope']['paths'])
            for path in paths:
                if path in covered:
                    _need(child['overlap_reason'] is not None
                          and child['overlap_reason'] == covered[path],
                          'OVERLAPPING_SCOPE', field)
                covered[path] = child['overlap_reason']
        _need(set(covered) == set(parent['scope']['paths']),
              'SUBDIVISION_COVERAGE', field)
    return mode, snapshot, deadline, assignments, children, sorted(categories)


def _scout_attempts(attempts, assignments):
    items = _list(attempts, MAX_SCOUT_ATTEMPTS, 'attempts')
    counts = {}
    seen = set()
    normalized = []
    for index, item in enumerate(items):
        field = 'attempts['+str(index)+']'
        _object(item, ('assignment_id', 'attempt_id'), field)
        assignment_id = _id(item['assignment_id'], field+'.assignment_id')
        attempt_id = _id(item['attempt_id'], field+'.attempt_id')
        _need(assignment_id in assignments, 'UNKNOWN_ASSIGNMENT', field)
        _need(attempt_id not in seen, 'DUPLICATE_ID', field+'.attempt_id')
        seen.add(attempt_id)
        counts[assignment_id] = counts.get(assignment_id, 0) + 1
        _need(counts[assignment_id] <= 2, 'RETRY_LIMIT', field)
        parent_id = assignments[assignment_id]['parent_id']
        if parent_id is not None:
            _need(counts.get(parent_id, 0) > 0, 'PARENT_REQUIRED', field)
        normalized.append({'assignment_id': assignment_id, 'attempt_id': attempt_id})
    return normalized, counts


def admit_scout_attempt(run, attempts, candidate, *, now_ms):
    """Admit one planned launch against the run's shared deadline and attempt ledger.

    The host still owns containment, concurrency, actual dispatch, and spending.
    Every launched attempt, including failed and subdivided work, stays in the
    caller's ledger. Changing an assignment ID cannot replenish the aggregate.
    """
    _, _, deadline, assignments, _, _ = _scout_run(run)
    _need(type(now_ms) is int and 0 <= now_ms < deadline, 'RUN_DEADLINE', 'now_ms')
    _need(type(attempts) is list, 'ARRAY_REQUIRED', 'attempts')
    _need(len(attempts) < MAX_SCOUT_ATTEMPTS, 'ATTEMPT_LIMIT', 'attempts')
    _scout_attempts(attempts + [candidate], assignments)
    return {'assignment_id': candidate['assignment_id'],
            'attempt_id': candidate['attempt_id']}


def join_scout_reports(run, attempts, payloads, *, now_ms):
    """Join complete leaf transports for the declared full or affected run only."""
    mode, snapshot, deadline, assignments, children, categories = _scout_run(run)
    _need(type(now_ms) is int and 0 <= now_ms < deadline, 'RUN_DEADLINE', 'now_ms')
    ledger, counts = _scout_attempts(attempts, assignments)
    _need(type(payloads) is dict, 'OBJECT_REQUIRED', 'payloads')
    _need(set(payloads) == {item['attempt_id'] for item in ledger},
          'MISSING_REPORT', 'payloads')
    decoded = {}
    for item in ledger:
        assignment = assignments[item['assignment_id']]
        report = decode_report(payloads[item['attempt_id']], expected={
            'assignment_id': item['assignment_id'],
            'attempt_id': item['attempt_id'],
            'snapshot_id': snapshot,
            'scope': assignment['scope']})
        decoded[item['attempt_id']] = report
    leaves = [item for item in assignments.values()
              if item['assignment_id'] not in children]
    selected = []
    for assignment in leaves:
        matching = [item for item in ledger
                    if item['assignment_id'] == assignment['assignment_id']]
        _need(bool(matching), 'MISSING_REPORT', assignment['assignment_id'])
        report = decoded[matching[-1]['attempt_id']]
        _need(report['transport'] == 'complete', 'INCOMPLETE_TRANSPORT',
              assignment['assignment_id'])
        selected.append({**report, 'parent_id': assignment['parent_id']})
    for parent_id in children:
        _need(counts.get(parent_id, 0) > 0, 'MISSING_REPORT', parent_id)
        for item in ledger:
            if item['assignment_id'] == parent_id:
                _need(decoded[item['attempt_id']]['transport'] != 'complete',
                      'SUBDIVISION_AFTER_COMPLETE', parent_id)
    selected.sort(key=lambda item: item['assignment_id'])
    source_ids = {}
    overlap_status = {}
    overlap_facts = {}
    for report in selected:
        for path in report['scope']['paths']:
            for outcome in report['outcomes']:
                key = (path.casefold(), outcome['category'])
                prior = overlap_status.setdefault(key, outcome['status'])
                _need(prior == outcome['status'], 'CONTRADICTORY_OVERLAP',
                      report['assignment_id'])
        for outcome in report['outcomes']:
            evidence_paths = {item['id']: item['path'].casefold()
                              for item in outcome['evidence']}
            for finding in outcome['findings']:
                for evidence_id in finding['evidence_refs']:
                    key = (evidence_paths[evidence_id], outcome['category'],
                           finding['name'])
                    prior = overlap_facts.setdefault(key, finding['value'])
                    _need(prior == finding['value'], 'CONTRADICTORY_OVERLAP',
                          report['assignment_id'])
            for evidence in outcome['evidence']:
                key = (evidence['path'].casefold(), evidence['digest_method'])
                prior = source_ids.setdefault(key, evidence['digest'])
                _need(prior == evidence['digest'], 'CONTRADICTORY_OVERLAP',
                      report['assignment_id'])
    gaps = sorted({outcome['category'] for report in selected
                   for outcome in report['outcomes']
                   if outcome['status'] in ('ambiguous', 'not_inspected', 'failed', 'oversize')})
    result = {'mode': mode, 'coverage': categories, 'full_coverage': mode == 'full',
              'attempt_count': len(ledger), 'reports': selected, 'gaps': gaps}
    try:
        size = len(json.dumps(result, ensure_ascii=False, sort_keys=True,
                              separators=(',', ':')).encode('utf-8'))
    except UnicodeError:
        raise ReportError('INVALID_UNICODE', 'join') from None
    _need(size <= MAX_JOIN_BYTES, 'JOIN_TOO_LARGE', 'join')
    return result


_CONTEXT_EVENT_KINDS = ('attempt', 'retry', 'rescout', 'join',
                        'transient_write', 'native_write')


def summarize_context_events(events, *, run_id, launched_attempt_ids,
                             allowed_effect_paths):
    """Check a bounded, caller-supplied history of context operations.

    The returned counts describe supplied records only. This does not observe
    a host, authenticate an inventory, or authorize dispatch or publication.
    Callers must retain all prior events when resuming after a budget stop.
    """
    run_id = _id(run_id, 'run_id')
    launches = [_id(value, 'launched_attempt_ids') for value in
                _list(launched_attempt_ids, 128, 'launched_attempt_ids')]
    _unique(launches, 'launched_attempt_ids')
    effects = set(_paths(allowed_effect_paths, 'allowed_effect_paths'))
    records = _list(events, 256, 'events')
    seen_events = set()
    attempts = {}
    joined = set()
    assignment_last = {}
    counts = {kind: 0 for kind in _CONTEXT_EVENT_KINDS}
    written = set()
    for index, event in enumerate(records):
        field = 'events[' + str(index) + ']'
        _object(event, ('event_id', 'kind', 'run_id', 'snapshot_id', 'scope',
                        'assignment_id', 'attempt_id', 'related_attempt_ids', 'path'), field)
        event_id = _id(event['event_id'], field+'.event_id')
        _need(event_id not in seen_events, 'DUPLICATE_ID', field+'.event_id')
        seen_events.add(event_id)
        kind = _enum(event['kind'], _CONTEXT_EVENT_KINDS, field+'.kind')
        _need(event['run_id'] == run_id, 'RUN_MISMATCH', field+'.run_id')
        snapshot = _digest(event['snapshot_id'], 64, field+'.snapshot_id')
        scope = _scope(event['scope'], field+'.scope')
        assignment = event['assignment_id']
        attempt = event['attempt_id']
        related = [_id(value, field+'.related_attempt_ids') for value in
                   _list(event['related_attempt_ids'], 128,
                         field+'.related_attempt_ids')]
        _unique(related, field+'.related_attempt_ids')
        path = event['path']
        if kind in ('attempt', 'retry', 'rescout'):
            assignment = _id(assignment, field+'.assignment_id')
            attempt = _id(attempt, field+'.attempt_id')
            _need(attempt in launches and attempt not in attempts,
                  'ATTEMPT_INVENTORY', field+'.attempt_id')
            _need(not related and path is None, 'EVENT_CONTEXT', field)
            previous = assignment_last.get(assignment)
            if kind == 'attempt':
                _need(previous is None, 'RETRY_REQUIRED', field)
            elif kind == 'retry':
                _need(previous == (snapshot, scope), 'RETRY_CONTEXT', field)
            else:
                _need(previous is not None and previous[0] != snapshot,
                      'RESCOUT_CONTEXT', field)
            assignment_last[assignment] = (snapshot, scope)
            attempts[attempt] = (snapshot, scope)
        elif kind == 'join':
            _need(assignment is None and attempt is None and path is None and related,
                  'EVENT_CONTEXT', field)
            _need(all(attempt_id in attempts and attempts[attempt_id][0] == snapshot
                      and set(attempts[attempt_id][1]['categories']) <=
                      set(scope['categories'])
                      and all(any(_within(path, parent) for parent in scope['paths'])
                              for path in attempts[attempt_id][1]['paths'])
                      for attempt_id in related),
                  'JOIN_CONTEXT', field+'.related_attempt_ids')
            joined.update(related)
        else:
            _need(assignment is None and not related and type(path) is str,
                  'EVENT_CONTEXT', field)
            attempt = _id(attempt, field+'.attempt_id')
            _need(attempt in attempts and attempts[attempt] == (snapshot, scope),
                  'WRITE_CONTEXT', field+'.attempt_id')
            path = _path(path, field+'.path')
            _need(path in effects, 'EFFECT_OUT_OF_SCOPE', field+'.path')
            written.add(path)
        counts[kind] += 1
    _need(set(attempts) == set(launches), 'MISSING_ATTEMPT_EVENT', 'events')
    _need(joined == set(attempts), 'MISSING_JOIN', 'events')
    return {'evidence_basis': 'supplied_events', 'counts': counts,
            'covered_attempt_ids': sorted(attempts),
            'joined_attempt_ids': sorted(joined), 'effect_paths': sorted(written)}


_COMMAND_STATES = frozenset({'declared', 'passed', 'failed', 'unknown'})
_SHELL_OPERATORS = frozenset({'|', '||', '&&', ';', '<', '>', '>>', '2>', '2>>'})
_SHELL_LAUNCHERS = frozenset({'cmd', 'cmd.exe', 'powershell', 'powershell.exe',
                              'pwsh', 'pwsh.exe', 'sh', 'sh.exe', 'bash',
                              'bash.exe', 'zsh', 'zsh.exe', 'env', 'env.exe'})
_CONSTRAINT_KINDS = frozenset({'existing_applicable', 'observed_upstream',
                               'proposed_adoption'})


def _known_ids(values, field):
    _need(type(values) in (set, frozenset, list, tuple), 'ARRAY_REQUIRED', field)
    _need(len(values) <= MAX_EVIDENCE, 'ITEM_LIMIT', field)
    ids = [_id(value, field) for value in values]
    _unique(ids, field)
    return set(ids)


def _record_refs(value, known, field):
    refs = [_id(item, field) for item in _list(value, MAX_EVIDENCE, field)]
    _unique(refs, field)
    _need(bool(refs) and set(refs) <= known, 'DANGLING_EVIDENCE', field)
    return sorted(refs)


def _verification_binding(value, field):
    _object(value, ('source_snapshot_id', 'runtime_ref', 'lock_digest',
                    'prerequisites_digest', 'oracle_ref', 'argv', 'cwd',
                    'declared_prerequisites', 'environment_digest'), field)
    argv = [_text(arg, 512, field+'.argv')
            for arg in _list(value['argv'], 32, field+'.argv')]
    _need(bool(argv), 'EMPTY_ARGV', field+'.argv')
    declared_prerequisites = [
        _text(item, 128, field+'.declared_prerequisites')
        for item in _list(value['declared_prerequisites'], 16,
                          field+'.declared_prerequisites')
    ]
    _unique(declared_prerequisites, field+'.declared_prerequisites')
    return {
        'source_snapshot_id': _digest(value['source_snapshot_id'], 64,
                                      field+'.source_snapshot_id'),
        'runtime_ref': _text(value['runtime_ref'], 128, field+'.runtime_ref'),
        'lock_digest': _digest(value['lock_digest'], 64, field+'.lock_digest'),
        'prerequisites_digest': _digest(value['prerequisites_digest'], 64,
                                        field+'.prerequisites_digest'),
        'oracle_ref': _text(value['oracle_ref'], 128, field+'.oracle_ref'),
        'argv': argv,
        'cwd': _path(value['cwd'], field+'.cwd', root=True),
        'declared_prerequisites': declared_prerequisites,
        # The caller supplies a digest of a non-secret environment identity,
        # never raw variable values or a credential-bearing environment dump.
        'environment_digest': _digest(value['environment_digest'], 64,
                                      field+'.environment_digest'),
    }


def validate_command_record(value, *, evidence_ids, observation_ids,
                            current_binding=None):
    """Normalize one inert command claim; supplied IDs/bindings do not prove execution.

    The caller owns observation provenance and authorization. A matching supplied
    binding exposes only a reported current state, never a permission to execute.
    """
    known_evidence = _known_ids(evidence_ids, 'evidence_ids')
    known_observations = _known_ids(observation_ids, 'observation_ids')
    _object(value, ('id', 'invocation', 'cwd', 'prerequisites', 'evidence_refs',
                    'verification'), 'command')
    invocation = value['invocation']
    _need(type(invocation) is dict, 'OBJECT_REQUIRED', 'command.invocation')
    kind = _enum(invocation.get('kind'), ('literal_argv', 'declaration_ref'),
                 'command.invocation.kind')
    if kind == 'literal_argv':
        _object(invocation, ('kind', 'argv'), 'command.invocation')
        argv = [_text(arg, 512, 'command.invocation.argv')
                for arg in _list(invocation['argv'], 32, 'command.invocation.argv')]
        _need(bool(argv), 'EMPTY_ARGV', 'command.invocation.argv')
        executable = argv[0]
        basename = executable.replace('\\', '/').rsplit('/', 1)[-1].casefold()
        first_space = next((i for i, char in enumerate(executable)
                            if char.isspace()), len(executable))
        first_separator = min((i for i, char in enumerate(executable)
                               if char in '/\\'), default=len(executable))
        _need(executable == executable.strip()
              and not executable.startswith(('"', "'"))
              and (first_space == len(executable) or first_separator < first_space)
              and not re.match(r'[A-Za-z_][A-Za-z0-9_]*=', executable)
              and not any(char in executable for char in '|&;<>')
              and basename not in _SHELL_LAUNCHERS
              and not basename.endswith(('.cmd', '.bat'))
              and not any(arg in _SHELL_OPERATORS for arg in argv),
              'DECLARATION_REQUIRED', 'command.invocation.argv')
        normalized_invocation = {'kind': kind, 'argv': argv}
    else:
        _object(invocation, ('kind', 'path', 'selector', 'text'), 'command.invocation')
        normalized_invocation = {
            'kind': kind,
            'path': _path(invocation['path'], 'command.invocation.path'),
            'selector': _text(invocation['selector'], 128, 'command.invocation.selector'),
            'text': _text(invocation['text'], 512, 'command.invocation.text'),
        }
    cwd = _path(value['cwd'], 'command.cwd', root=True)
    prerequisites = [_text(item, 128, 'command.prerequisites')
                     for item in _list(value['prerequisites'], 16,
                                       'command.prerequisites')]
    _unique(prerequisites, 'command.prerequisites')
    refs = _record_refs(value['evidence_refs'], known_evidence,
                        'command.evidence_refs')
    verification = value['verification']
    _object(verification, ('state', 'observation_ref', 'binding'),
            'command.verification')
    state = _enum(verification['state'], _COMMAND_STATES,
                  'command.verification.state')
    observation_ref = verification['observation_ref']
    binding = verification['binding']
    if state in ('passed', 'failed'):
        _need(kind == 'literal_argv', 'DECLARATION_UNVERIFIED',
              'command.verification')
        observation_ref = _id(observation_ref, 'command.verification.observation_ref')
        _need(observation_ref in known_observations, 'UNKNOWN_OBSERVATION',
              'command.verification.observation_ref')
        binding = _verification_binding(binding, 'command.verification.binding')
    else:
        _need(observation_ref is None and binding is None, 'UNSUPPORTED_VERIFICATION',
              'command.verification')
    current = (_verification_binding(current_binding, 'current_binding')
               if current_binding is not None else None)
    same_command = (kind == 'literal_argv' and binding is not None
                    and binding['argv'] == normalized_invocation['argv']
                    and binding['cwd'] == cwd
                    and binding['declared_prerequisites'] == prerequisites)
    reported_current_state = (state if state in ('declared', 'unknown') or
                              (same_command and binding == current) else 'unknown')
    return {
        'id': _id(value['id'], 'command.id'),
        'invocation': normalized_invocation,
        'cwd': cwd,
        'prerequisites': prerequisites,
        'evidence_refs': refs,
        'verification': {'state': state, 'observation_ref': observation_ref,
                         'binding': binding},
        'reported_current_state': reported_current_state,
    }


def resolve_scoped_command_guidance(entries, *, command_id, cwd,
                                    current_binding, observation):
    """Resolve one command by ID and cwd, retaining its source and observed result.

    ``observation`` is supplied by the owning execution workflow. This pure
    consumer checks its shape and result, but cannot attest its provenance.
    A passed report is therefore only a reported state for that supplied run.
    """
    command_id = _id(command_id, 'command_id')
    cwd = _path(cwd, 'cwd', root=True)
    current = (_verification_binding(current_binding, 'current_binding')
               if current_binding is not None else None)
    _need(type(entries) is list and 0 < len(entries) <= MAX_EVIDENCE,
          'ITEM_LIMIT', 'entries')
    matches = []
    for index, entry in enumerate(entries):
        field = 'entries['+str(index)+']'
        _need(type(entry) is tuple and len(entry) == 2,
              'OBJECT_REQUIRED', field)
        record, sources = entry
        _need(type(sources) is dict and 0 < len(sources) <= MAX_EVIDENCE,
              'OBJECT_REQUIRED', field+'.sources')
        normalized_sources = {}
        for evidence_id, source in sources.items():
            evidence_id = _id(evidence_id, field+'.sources.id')
            _object(source, ('path', 'digest'), field+'.sources.'+evidence_id)
            normalized_sources[evidence_id] = {
                'path': _path(source['path'], field+'.sources.path'),
                'digest': _digest(source['digest'], 64, field+'.sources.digest'),
            }
        # A stored observation reference is accepted for shape normalization
        # only. This resolver never treats that self-reported history as fresh.
        historical_ref = (record.get('verification', {}).get('observation_ref')
                          if type(record) is dict and
                          type(record.get('verification')) is dict else None)
        normalized = validate_command_record(
            record, evidence_ids=set(normalized_sources),
            observation_ids={historical_ref} if type(historical_ref) is str else set(),
            current_binding=None)
        if normalized['id'] == command_id and normalized['cwd'] == cwd:
            matches.append((normalized, normalized_sources))
    _need(len(matches) == 1, 'AMBIGUOUS_COMMAND', 'entries')
    command, sources = matches[0]
    _need(len(command['evidence_refs']) == 1, 'AMBIGUOUS_SOURCE', 'command.evidence_refs')
    source = sources[command['evidence_refs'][0]]
    source_path = source['path']
    if source_path.rsplit('/', 1)[-1].casefold() == 'package.json':
        _need(cwd == source_path.rsplit('/', 1)[0] if '/' in source_path else cwd == '.',
              'SOURCE_CWD_MISMATCH', 'command.cwd')
    if command['invocation']['kind'] == 'declaration_ref':
        _need(command['invocation']['path'] == source_path,
              'SOURCE_MISMATCH', 'command.invocation.path')
    result = {**command, 'source': source, 'observation': None}
    if observation is None:
        return result
    _object(observation, ('id', 'authorized', 'binding', 'source', 'exit', 'collector',
                          'required_tests', 'tests'), 'observation')
    observed_id = _id(observation['id'], 'observation.id')
    _need(type(observation['authorized']) is bool,
          'BOOLEAN_REQUIRED', 'observation.authorized')
    observed_binding = _verification_binding(observation['binding'],
                                              'observation.binding')
    _object(observation['source'], ('path', 'digest'), 'observation.source')
    observed_source = {
        'path': _path(observation['source']['path'], 'observation.source.path'),
        'digest': _digest(observation['source']['digest'], 64,
                          'observation.source.digest'),
    }
    exit_code = observation['exit']
    _need(type(exit_code) is int and 0 <= exit_code <= 255,
          'INVALID_EXIT', 'observation.exit')
    collector = _enum(observation['collector'],
                      ('python-unittest-text/0.1.0', 'codearbiter-named-lines/0.1.0',
                       'vitest-verbose/0.1.0', 'playwright-json/0.1.0',
                       'exit-only/0.1.0'), 'observation.collector')
    required = [_text(item, 128, 'observation.required_tests') for item in
                _list(observation['required_tests'], MAX_EVIDENCE,
                      'observation.required_tests')]
    _unique(required, 'observation.required_tests')
    tests = []
    for test in _list(observation['tests'], MAX_EVIDENCE, 'observation.tests'):
        _object(test, ('name', 'status'), 'observation.tests')
        tests.append({'name': _text(test['name'], 128, 'observation.tests.name'),
                      'status': _enum(test['status'], ('pass', 'fail', 'skip'),
                                      'observation.tests.status')})
    names = [test['name'] for test in tests]
    unique = len(set(names)) == len(names)
    named_oracle = 'sha256:' + hashlib.sha256(json.dumps(
        {'collector': collector, 'required_tests': sorted(required)},
        sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    matches_oracle = (collector != 'exit-only/0.1.0' and bool(required)
                      and observed_binding['oracle_ref'] == named_oracle
                      and unique and set(names) == set(required)
                      and all(test['status'] == 'pass' for test in tests))
    exit_oracle = (collector == 'exit-only/0.1.0' and not required and not tests
                   and observed_binding['oracle_ref'] == 'exit-only/0.1.0')
    same_invocation = (command['invocation']['kind'] == 'literal_argv'
                       and observed_binding['argv'] == command['invocation']['argv']
                       and observed_binding['cwd'] == cwd
                       and observed_binding['declared_prerequisites'] ==
                       command['prerequisites'])
    current_run = (observation['authorized'] and same_invocation
                   and observed_source == source
                   and observed_binding == current)
    state = ('passed' if current_run and exit_code == 0 and
             (matches_oracle or exit_oracle) else
             'failed' if current_run and (exit_code != 0 or
                                          any(test['status'] == 'fail' for test in tests))
             else 'unknown')
    result['reported_current_state'] = state
    result['observation'] = {'id': observed_id, 'exit': exit_code,
                             'source': observed_source,
                             'collector': collector, 'required_tests': required,
                             'tests': tests}
    return result


def validate_constraint_reference(value, *, evidence_ids):
    """Normalize a source-scoped reference without adopting or approving a rule."""
    known_evidence = _known_ids(evidence_ids, 'evidence_ids')
    _object(value, ('id', 'kind', 'source_ref', 'scope', 'statement',
                    'evidence_refs'), 'constraint')
    return {
        'id': _id(value['id'], 'constraint.id'),
        'kind': _enum(value['kind'], _CONSTRAINT_KINDS, 'constraint.kind'),
        'source_ref': _text(value['source_ref'], 256, 'constraint.source_ref'),
        'scope': _path(value['scope'], 'constraint.scope', root=True),
        'statement': _text(value['statement'], 512, 'constraint.statement'),
        'evidence_refs': _record_refs(value['evidence_refs'], known_evidence,
                                      'constraint.evidence_refs'),
    }
