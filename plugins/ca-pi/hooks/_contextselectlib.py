#!/usr/bin/env python3
# codeArbiter -- bounded task-time context selection.
# The selector is inert: it reads no files and grants no task or action authority.
# Its inputs are already acquired by the owning actor from the existing map,
# provenance assessor, command reports, and effective native instructions.

from __future__ import annotations

import re
import copy
import json
import hashlib
import os

import _contextreportlib as reports
import _provenancelib as provenance_lib

_MAP_ROW = re.compile(r'^- `([^`]+)`\s+(?:--|—)\s+(.+)$')
_STATUSES = frozenset({'current', 'unresolved', 'unknown', 'conflict'})
_WORK_ACTORS = frozenset({'backend-author', 'frontend-author', 'infra-author',
                          'coverage-auditor'})

class SelectionError(ValueError):
    """Invalid selector input. Never grants an action bypass."""


def _path(value):
    try:
        return reports._path(value, 'task_path', root=True)
    except reports.ReportError as exc:
        raise SelectionError(exc.code) from None


def _within(path, scope):
    return scope == '.' or path == scope or path.startswith(scope + '/')


def _touches(paths, scope):
    return any(_within(path, scope) or _within(scope, path) for path in paths)


def _text(value, field, limit=512):
    try:
        valid = (type(value) is str and bool(value.strip()) and
                 len(value.encode('utf-8')) <= limit)
    except UnicodeError:
        valid = False
    if not valid:
        raise SelectionError('INVALID_' + field.upper())
    return value


def _map_rows(code_map, paths):
    if code_map is None:
        return [], ['code map unavailable'], False
    if type(code_map) is not str:
        raise SelectionError('INVALID_CODE_MAP')
    try:
        map_size = len(code_map.encode('utf-8'))
    except UnicodeError:
        return [], ['code map is not valid UTF-8 text'], False
    if map_size > 1024 * 1024:
        return [], ['code map input exceeds read cap'], False
    diagnostics = provenance_lib.lint_code_map(code_map)
    rows = []
    for line in code_map.splitlines():
        match = _MAP_ROW.fullmatch(line)
        if match is None:
            continue
        try:
            path = _path(match.group(1).removesuffix('/'))
        except SelectionError:
            continue  # The existing linter reports malformed map rows.
        role = match.group(2)
        if len(role.encode('utf-8')) > 512:
            continue
        rows.append({'path': path, 'role': role})
    # A generated output may be the only changed path. Include its named source
    # as orientation, but never infer ownership from equal role text alone.
    selected = [row for row in rows if _touches(paths, row['path'])]
    for row in list(selected):
        marker = 'generated from '
        if marker in row['role'].lower():
            source = row['role'][row['role'].lower().index(marker) + len(marker):].split()[0]
            selected.extend(candidate for candidate in rows
                            if candidate['path'] == source and candidate not in selected)
    selected = [row for row in rows if row in selected]
    if (len(selected) > provenance_lib.CODE_MAP_MAX_ENTRIES or
            sum(len(row['path'].encode('utf-8')) +
                len(row['role'].encode('utf-8')) for row in selected) >
            provenance_lib.CODE_MAP_MAX_BYTES):
        return [], diagnostics + ['code map selection exceeds packet cap'], False
    return selected, diagnostics, True


def _provenance_summary(value):
    allowed = frozenset(provenance_lib.V2_DOCUMENTS)
    documents = value.get('documents')
    summary = {'coverage': value.get('coverage') if value.get('coverage') in
               ('complete', 'incomplete') else 'incomplete',
               'identity': value.get('identity') if value.get('identity') in
               ('current', 'stale', 'unknown') else 'unknown',
               'documents': {}}
    if type(documents) is dict:
        for key in sorted(allowed):
            status = documents.get(key)
            if type(status) is str and status in (
                    'v2_current', 'v2_stale', 'v2_unchecked', 'missing',
                    'unsupported', 'legacy_unverified', 'store_unreadable',
                    'first_input_pending', 'corrupt', 'oversize', 'unreadable',
                    'unknown'):
                summary['documents'][key] = status
    return summary


def select_task_context(task_paths, *, code_map, provenance, commands,
                        constraints, effective_instructions, evidence_ids,
                        command_bindings=None, observations=None):
    """Build an inert bounded packet for an actual author or reviewer.

    The caller acquires the effective instruction order from its host; this
    function only filters that order and cannot confer native precedence. A
    current provenance identity is not semantic approval or write admission.
    Observations/bindings must come from the owning execution collector.
    """
    if type(task_paths) not in (list, tuple) or not 1 <= len(task_paths) <= 32:
        raise SelectionError('INVALID_TASK_PATHS')
    paths = [_path(path) for path in task_paths]
    if (type(provenance) is not dict or type(commands) is not list or
            type(constraints) is not list or type(effective_instructions) is not list or
            type(evidence_ids) not in (set, frozenset, list, tuple) or
            len(commands) > 64 or len(constraints) > 64 or
            len(effective_instructions) > 64):
        raise SelectionError('INVALID_CONTEXT_INPUT')
    bindings = command_bindings or {}
    observed = observations or {}
    if type(bindings) is not dict or type(observed) is not dict:
        raise SelectionError('INVALID_COMMAND_EVIDENCE')
    map_rows, diagnostics, map_complete = _map_rows(code_map, paths)
    chosen_commands = []
    seen_commands = {}
    for entry in commands:
        if type(entry) is not tuple or len(entry) != 2:
            raise SelectionError('INVALID_COMMAND_ENTRY')
        command, sources = entry
        if type(command) is not dict:
            raise SelectionError('INVALID_COMMAND')
        cwd = _path(command.get('cwd'))
        if not _touches(paths, cwd):
            continue
        command_id = command.get('id')
        key = (command_id, cwd)
        raw = (command, sources)
        if key in seen_commands:
            if seen_commands[key] != raw:
                raise SelectionError('CONFLICTING_COMMAND')
            continue
        seen_commands[key] = raw
        try:
            resolved = reports.resolve_scoped_command_guidance(
                [raw], command_id=command_id, cwd=cwd,
                current_binding=bindings.get(key), observation=observed.get(key))
        except reports.ReportError as exc:
            raise SelectionError(exc.code) from None
        if 'reported_current_state' not in resolved:
            resolved['reported_current_state'] = (
                'declared' if resolved['verification']['state'] == 'declared' else 'unknown')
        chosen_commands.append(resolved)
    chosen_constraints = []
    unresolved = []
    seen_constraints = {}
    for item in constraints:
        if type(item) is not dict or set(item) != {'record', 'owner', 'authority', 'epoch', 'status'}:
            raise SelectionError('INVALID_CONSTRAINT')
        try:
            record = reports.validate_constraint_reference(item['record'],
                                                          evidence_ids=evidence_ids)
        except reports.ReportError as exc:
            raise SelectionError(exc.code) from None
        if not _touches(paths, record['scope']):
            continue
        owner = _path(item['owner']) if item['owner'] != 'root' else 'root'
        authority = _text(item['authority'], 'authority', 128)
        epoch = _text(item['epoch'], 'epoch', 128)
        status = item['status']
        if status not in _STATUSES:
            raise SelectionError('INVALID_CONSTRAINT_STATUS')
        key = (record['id'], owner, record['scope'], authority, epoch)
        selected = {**record, 'owner': owner, 'reported_authority': authority,
                    'epoch': epoch, 'status': status}
        if key in seen_constraints:
            if seen_constraints[key] != selected:
                seen_constraints[key]['status'] = 'conflict'
                if seen_constraints[key] not in unresolved:
                    unresolved.append(seen_constraints[key])
            continue
        seen_constraints[key] = selected
        chosen_constraints.append(selected)
        if status != 'current':
            unresolved.append(selected)
    chosen_instructions = []
    seen_instructions = {}
    for item in effective_instructions:
        if type(item) is not dict or set(item) != {'id', 'path', 'scope', 'epoch', 'text'}:
            raise SelectionError('INVALID_INSTRUCTION')
        scope, path = _path(item['scope']), _path(item['path'])
        if not _touches(paths, scope):
            continue
        record = {'id': _text(item['id'], 'instruction_id', 128),
                  'path': path, 'scope': scope,
                  'epoch': _text(item['epoch'], 'epoch', 128),
                  'text': _text(item['text'], 'instruction', 8192)}
        key = (record['id'], path, scope, record['epoch'])
        if key in seen_instructions:
            if seen_instructions[key] != record:
                unresolved.append({'code': 'CONFLICTING_INSTRUCTION', 'id': record['id']})
        else:
            chosen_instructions.append(record)
            seen_instructions[key] = record
    if len({item['epoch'] for item in chosen_instructions}) > 1:
        unresolved.append({'code': 'MIXED_INSTRUCTION_EPOCH'})
    if sum(len(item['text'].encode('utf-8')) for item in chosen_instructions) > 24 * 1024:
        for item in chosen_instructions:
            item['text'] = None  # Keep every source reference for bounded on-demand reading.
        unresolved.append({'code': 'INSTRUCTION_PACKET_OVERSIZE'})
    provenance_status = _provenance_summary(provenance)
    for doc, status in provenance_status['documents'].items():
        if status == 'v2_stale':
            unresolved.append({'code': 'PROVENANCE_STALE', 'document': doc})
        elif status != 'v2_current':
            unresolved.append({'code': 'PROVENANCE_UNCHECKED', 'document': doc,
                               'status': status})
    return {'task_paths': paths, 'map': map_rows, 'map_complete': map_complete,
            'map_diagnostics': diagnostics,
            'provenance': provenance_status, 'commands': chosen_commands,
            'constraints': chosen_constraints, 'instructions': chosen_instructions,
            'unresolved': unresolved, 'admission': 'requires_actor_check'}


def prepare_actor_delivery(packet, *, actor, task_id, worktree, source_epoch,
                           host_epoch, attempts=None, receipt=None):
    """Plan a bounded delivery to one actual actor, without claiming authority.

    The caller supplies a freshly selected packet and current source/host epochs.
    It resolves the worktree path but reads no source content and keeps no global
    index. A host receipt is a caller-reported observation; admission to work
    remains with the caller.
    Unknown epochs cannot make a saved receipt current and allow at most two
    counted deliveries of the same binding before an explicit gap is returned.
    """
    if (type(packet) is not dict or packet.get('admission') != 'requires_actor_check'
            or type(packet.get('task_paths')) is not list
            or not packet['task_paths'] or len(packet['task_paths']) > 32
            or type(packet.get('instructions')) is not list):
        raise SelectionError('INVALID_DELIVERY_PACKET')
    paths = [_path(path) for path in packet['task_paths']]
    if paths != packet['task_paths']:
        raise SelectionError('INVALID_DELIVERY_SCOPE')
    for name, value in (('actor', actor), ('task_id', task_id)):
        if (type(value) is not str or len(value) > 128 or
                re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]*', value) is None):
            raise SelectionError('INVALID_DELIVERY_' + name.upper())
    if type(worktree) not in (str, os.PathLike):
        raise SelectionError('INVALID_WORKTREE')
    worktree = os.fspath(worktree)
    if not os.path.isabs(worktree):
        raise SelectionError('INVALID_WORKTREE')
    worktree = os.path.normcase(os.path.realpath(worktree))
    for epoch in (source_epoch, host_epoch):
        if epoch is not None and (type(epoch) is not str or not epoch or len(epoch) > 128):
            raise SelectionError('INVALID_DELIVERY_EPOCH')
    instruction_epochs = set()
    for instruction in packet['instructions']:
        if type(instruction) is not dict or type(instruction.get('epoch')) is not str:
            raise SelectionError('INVALID_DELIVERY_INSTRUCTION')
        instruction_epochs.add(instruction['epoch'])
    if len(instruction_epochs) > 1:
        raise SelectionError('MIXED_INSTRUCTION_EPOCH')
    try:
        encoded = json.dumps(packet, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise SelectionError('INVALID_DELIVERY_PACKET') from exc
    if len(encoded) > 96 * 1024:
        raise SelectionError('DELIVERY_PACKET_OVERSIZE')
    binding = {
        'actor': actor, 'task_id': task_id, 'worktree': worktree,
        'task_paths': paths, 'source_epoch': source_epoch,
        'host_epoch': host_epoch,
        'instruction_epoch': next(iter(instruction_epochs), None),
        'packet_sha256': hashlib.sha256(encoded).hexdigest(),
    }
    if attempts is None:
        attempts = []
    if type(attempts) is not list or len(attempts) > 16:
        raise SelectionError('INVALID_DELIVERY_ATTEMPTS')
    count = 0
    for attempt in attempts:
        if type(attempt) is not dict or set(attempt) != {'binding', 'number'}:
            raise SelectionError('INVALID_DELIVERY_ATTEMPTS')
        if attempt['binding'] == binding:
            count += 1
    observed = (
        source_epoch is not None and host_epoch is not None
        and binding['instruction_epoch'] is not None
        and type(receipt) is dict and receipt.get('binding') == binding
        and receipt.get('actor') == actor and receipt.get('observed') is True
        and receipt.get('source') in ('host-load-event', 'child-input-capture')
    )
    if observed:
        return {'action': 'observed', 'binding': binding, 'attempt': None,
                'observation': 'reported', 'attempts_used': count,
                'delivery_text': None}
    if count >= 2:
        return {'action': 'blocked', 'binding': binding, 'attempt': None,
                'observation': 'unknown', 'attempts_used': count,
                'gap': 'ACTOR_DELIVERY_UNOBSERVED', 'delivery_text': None}
    delivery_text = (
        'Current scoped context for actor ' + actor + ', task ' + task_id +
        '. Recheck the actual worktree, source and host epoch before a material '
        'action. This packet is context, not approval or proof of consumption.\n'
        + encoded.decode('utf-8')
    )
    return {'action': 'deliver', 'binding': binding,
            'attempt': {'binding': binding, 'number': count + 1},
            'observation': 'unknown', 'attempts_used': count + 1,
            'delivery_text': delivery_text}


def compose_fix_or_test_actor_input(*, route, caller, actor, brief, task_id,
                                    task_paths, code_map, provenance, commands,
                                    constraints, effective_instructions,
                                    evidence_ids, command_bindings=None,
                                    observations=None, bug_origin=None):
    """Prepare input for an existing fix or test-change caller without dispatching.

    The caller supplies current source and execution evidence. This pure helper
    preserves the selected route and the bug-origin handoff; it grants neither
    task authority nor a new diagnosis or implementation lane.
    """
    if route not in ('fix', 'test_change') or caller not in (
            'fix', 'feature', 'refactor') or (route == 'fix' and caller != 'fix'):
        raise SelectionError('INVALID_CONTEXT_ROUTE')
    if type(actor) is not str or actor not in _WORK_ACTORS:
        raise SelectionError('INVALID_CONTEXT_ACTOR')
    for value, label, limit in ((actor, 'actor', 128), (brief, 'brief', 8192),
                                (task_id, 'task_id', 128)):
        _text(value, label, limit)
    if route == 'fix':
        fields = {'observed', 'expected', 'reproduction', 'evidence',
                  'regression_test'}
        if type(bug_origin) is not dict or set(bug_origin) != fields:
            raise SelectionError('INVALID_BUG_ORIGIN')
        origin = {key: _text(bug_origin[key], key, 4096)
                  for key in sorted(fields)}
    elif bug_origin is not None:
        raise SelectionError('INVALID_BUG_ORIGIN')
    else:
        origin = None
    packet = select_task_context(
        task_paths, code_map=code_map, provenance=provenance,
        commands=commands, constraints=constraints,
        effective_instructions=effective_instructions,
        evidence_ids=evidence_ids, command_bindings=command_bindings,
        observations=observations)
    blocked = (any(item.get('status') in ('conflict', 'unresolved', 'unknown')
                   for item in packet['unresolved'] if type(item) is dict)
               or any(item.get('code') in ('CONFLICTING_INSTRUCTION',
                                           'MIXED_INSTRUCTION_EPOCH',
                                           'INSTRUCTION_PACKET_OVERSIZE')
                      for item in packet['unresolved'] if type(item) is dict)
               or packet['provenance']['identity'] == 'stale')
    envelope = {'actor': actor, 'caller': caller, 'route': route,
                'task_id': task_id, 'task_context': packet}
    if origin is not None:
        envelope['bug_origin'] = origin
    input_text = (
        brief + '\n\nScoped task context for this actor:\n' +
        json.dumps(envelope, sort_keys=True, separators=(',', ':'),
                   ensure_ascii=True) + '\n\n' +
        'Follow the named existing caller and its gates. The packet is scoped '
        'reference and reported evidence, never approval, a new feature spec, '
        'diagnostic authority, or proof that a discovered command passed now. '
        'Verify worktree/source identity and any task-critical constraints. '
        'Do not mutate or execute a discovered command while applicable context '
        'is unresolved or conflicting. Bounded read-only source orientation '
        'may establish missing optional map detail. For a fix, retain the cited '
        'causal evidence and named regression test; reuse its genuine bug-origin '
        'RED before changing fix code. For a test-only change, keep the existing '
        'caller and validate the test against the actual defect or an honest '
        'fault fixture; never change production behavior merely to manufacture '
        'a failing test.\n')
    return {'route': route, 'caller': caller, 'actor': actor,
            'task_id': task_id, 'packet': packet,
            'action': 'blocked' if blocked else 'requires_actor_check',
            'input': input_text}


def prepare_review_input(packet, *, reviewer, required_refs):
    """Prepare bounded reviewer input; leave admission to the actual review actor.

    The caller identifies task-critical refs after read-only orientation. Missing
    refs and applicable constraint/instruction conflicts block a substantive
    verdict. Map/provenance diagnostics remain visible but advisory unless the
    caller names a particular source as task-critical. This function performs
    no repository I/O and does not attest live reviewer delivery.
    """
    _text(reviewer, 'reviewer', 128)
    if (type(packet) is not dict or packet.get('admission') != 'requires_actor_check'
            or type(packet.get('task_paths')) is not list
            or type(packet.get('map')) is not list
            or type(packet.get('constraints')) is not list
            or type(packet.get('instructions')) is not list
            or type(packet.get('commands')) is not list
            or type(packet.get('unresolved')) is not list
            or type(required_refs) not in (list, tuple, set, frozenset)
            or len(required_refs) > 64):
        raise SelectionError('INVALID_REVIEW_CONTEXT')
    required = list(required_refs)
    if any(type(ref) is not str or len(ref.encode('utf-8')) > 512
           or not ref.strip() for ref in required):
        raise SelectionError('INVALID_REQUIRED_REF')
    available = set()
    blockers = []
    for row in packet['map']:
        if type(row) is not dict:
            raise SelectionError('INVALID_REVIEW_CONTEXT')
        if type(row.get('path')) is str:
            available.add('map:' + row['path'])
    for constraint in packet['constraints']:
        if type(constraint) is not dict:
            raise SelectionError('INVALID_REVIEW_CONTEXT')
        source = constraint.get('source_ref')
        if type(source) is str:
            available.add('constraint:' + source)
        if constraint.get('status') != 'current':
            blockers.append('UNRESOLVED_CONSTRAINT')
    for instruction in packet['instructions']:
        if type(instruction) is not dict:
            raise SelectionError('INVALID_REVIEW_CONTEXT')
        path = instruction.get('path')
        if type(path) is str and instruction.get('text') is not None:
            available.add('instruction:' + path)
    for command in packet['commands']:
        if type(command) is not dict:
            raise SelectionError('INVALID_REVIEW_CONTEXT')
        command_id, cwd = command.get('id'), command.get('cwd')
        if type(command_id) is str and type(cwd) is str:
            available.add('command:' + cwd + ':' + command_id)
    for unresolved in packet['unresolved']:
        if type(unresolved) is dict and unresolved.get('code') in (
                'CONFLICTING_INSTRUCTION', 'MIXED_INSTRUCTION_EPOCH',
                'INSTRUCTION_PACKET_OVERSIZE'):
            blockers.append(unresolved['code'])
    missing = [ref for ref in required if ref not in available]
    if missing:
        blockers.append('MISSING_CRITICAL_CONTEXT')
    blockers = list(dict.fromkeys(blockers))
    return {'orientation': 'read_only',
            'verdict_admission': 'blocked' if blockers else 'ready',
            'missing_refs': missing, 'blockers': blockers,
            'reviewer_input': None if blockers else {
                'reviewer': reviewer, 'context': copy.deepcopy(packet),
                'required_refs': required}}
