#!/usr/bin/env python3
# codeArbiter -- bounded, pure decoding of internal scout evidence reports.
#
# Public API: decode_report(payload, *, expected) -> detached normalized dict.
# ReportError(code, field) reports only bounded code-owned diagnostics.
# No filesystem, subprocess, network, dispatch, approval, or artifact mutation.
# A matching supplied identity is not proof that the host actually inspected it.
# This codec admits report transport; category gaps remain gaps. It does not
# establish six-domain coverage, containment, truth, freshness, or readiness.

from __future__ import annotations

import json
import re
import unicodedata

SCHEMA_VERSION = 1
MAX_REPORT_BYTES = 48 * 1024
MAX_DEPTH = 12
MAX_NODES = 4096
MAX_PATHS = 16
MAX_EVIDENCE = 64
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
    for index, entry in enumerate(_list(value, MAX_EVIDENCE, field)):
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
        refs = [_id(ref, part+'.evidence_refs') for ref in _list(entry['evidence_refs'], MAX_EVIDENCE, part)]
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
