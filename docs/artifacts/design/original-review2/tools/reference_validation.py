"""Reference schema/relationship/readiness checks. No host authority or execution."""
from __future__ import annotations
import base64
import json
import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from artifact_io import records,canonical

@lru_cache(maxsize=8)
def validators(root_string):
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry,Resource
    except ImportError as exc:
        raise ValueError('DEPENDENCY_MISSING: reference validation requires jsonschema and referencing; no automatic installation') from exc
    root=Path(root_string);schemas={};registry=Registry()
    for kind in ('common','spec','plan'):
        d=json.loads((root/'schemas'/f'{kind}.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(d)
        registry=registry.with_resource(d['$id'],Resource.from_contents(d));schemas[kind]=d
    return {k:Draft202012Validator(schemas[k],registry=registry) for k in ('spec','plan')}

def structural_errors(model,root=None):
    root=root or Path(__file__).resolve().parents[1]
    kind=model.get('kind') if isinstance(model,dict) else None
    if kind not in ('spec','plan'):return ['unsupported artifact kind']
    return [f"{'.'.join(map(str,e.path))}: {e.message}" for e in validators(str(root.resolve()))[kind].iter_errors(model)]

def safe_relative(value,allow_dot=False):
    if not isinstance(value,str) or not value:return False
    if value=='.':return allow_dot
    if value.startswith(('/','\\')) or '\\' in value or ':' in value or any(ord(c)<32 for c in value):return False
    return all(x not in ('','..','.') for x in value.split('/'))

def validate_logo(uri):
    m=re.fullmatch(r'data:image/(svg\+xml|png|jpeg);base64,([A-Za-z0-9+/=]+)',uri or '')
    if not m:raise ValueError('invalid inline logo encoding')
    raw=base64.b64decode(m[2],validate=True)
    if len(raw)>256*1024:raise ValueError('logo exceeds byte cap')
    if m[1]=='png':
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('invalid PNG signature')
    elif m[1]=='jpeg':
        if not raw.startswith(b'\xff\xd8\xff'):raise ValueError('invalid JPEG signature')
    else:
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('SVG declarations forbidden')
        root=ET.fromstring(raw)
        allowed={'svg','title','desc','defs','linearGradient','radialGradient','stop','g','path','rect','circle','ellipse','line','polyline','polygon','text','tspan'}
        for node in root.iter():
            if node.tag.split('}')[-1] not in allowed:raise ValueError('unsupported SVG element')
            for k,v in node.attrib.items():
                k=k.split('}')[-1].lower()
                if k.startswith('on') or k=='style':raise ValueError('active SVG attribute')
                if k in ('href','src') and not v.startswith('#'):raise ValueError('external SVG reference')
                if 'url(' in v and not re.fullmatch(r'url\(#[A-Za-z0-9_-]+\)',v):raise ValueError('external SVG paint')
    return raw

def _dag(graph):
    done=set();todo=set(graph)
    while todo:
        ready={n for n in todo if set(graph[n])<=done}
        if not ready:return False
        done|=ready;todo-=ready
    return True

def semantic_errors(model):
    errors=[];n=model['normative']
    try:idx=records(model)
    except ValueError as e:return [str(e)]
    sources={r['id'] for r in n['sources']}
    def visit(v):
        if isinstance(v,dict):
            for key,value in v.items():
                if key in ('refs','source_refs') and isinstance(value,list) and not set(value)<=sources:errors.append('dangling source reference')
                visit(value)
            if v.get('type')=='table' and any(len(row)!=len(v['columns']) for row in v['rows']):errors.append('ragged table')
        elif isinstance(v,list):
            for x in v:visit(x)
    visit(n)
    if not safe_relative(model['presentation']['companion_path']):errors.append('unsafe companion locator')
    try:validate_logo(model['presentation']['logo_data_uri'])
    except (ValueError,ET.ParseError) as e:errors.append('unsafe logo: '+str(e))
    for r in n.get('retired_symbols',[]):
        if r['retired_in_revision']>model['revision']:errors.append('future tombstone revision')
        target=r['replacement_ref']
        if target and '#' not in target and target not in idx:errors.append('dangling tombstone replacement')
        if target==r['id']:errors.append('self tombstone replacement')
    if model['kind']=='spec':
        scopes={x['id'] for x in n['scope']};cs={x['id'] for x in n['constraints']};criteria={x['id'] for x in n['criteria']};ds={x['id'] for x in n['decisions']}
        if not set(n['approach'].get('binding_decision_refs',[]))<=ds:errors.append('unknown binding decision')
        for c in n['criteria']:
            if not set(c.get('intent_refs',[]))<=scopes:errors.append(c['id']+': unknown scope ref')
            if not set(c.get('constraint_refs',[]))<=cs:errors.append(c['id']+': unknown constraint ref')
        for c in n['constraints']:
            if any(a!='all' and a not in criteria for a in c['applies_to']):errors.append('unknown constraint applicability')
        for d in n['open_decisions']:
            if not set(d['affects'])<=set(idx):errors.append('unknown blocker target')
            if d['status']=='resolved' and not d['resolution']:errors.append('resolved decision lacks resolution')
    else:
        ts={x['id']:x for x in n['tasks']};cps={x['id']:x for x in n['checkpoints']}
        graph={x['id']:x.get('depends_on',[]) for x in n['tasks']}
        if any(not set(deps)<=set(ts) for deps in graph.values()):errors.append('unknown task dependency')
        elif not _dag(graph):errors.append('cyclic task graph')
        cgraph={x['id']:x['depends_on'] for x in n['checkpoints']}
        if any(not set(deps)<=set(cps) for deps in cgraph.values()):errors.append('unknown checkpoint dependency')
        elif not _dag(cgraph):errors.append('cyclic checkpoint graph')
        order={x['id']:i for i,x in enumerate(n['checkpoints'])}
        for cp in n['checkpoints']:
            if any(order.get(d,999)>=order[cp['id']] for d in cp['depends_on']):errors.append('backward checkpoint order')
        listed=[tid for cp in cps.values() for tid in cp['tasks']]
        if len(listed)!=len(set(listed)) or set(listed)!=set(ts):errors.append('checkpoint partition mismatch')
        for t in ts.values():
            if t['checkpoint'] not in cps or t['execution_scope']!=t['checkpoint'] or t['id'] not in cps.get(t['checkpoint'],{}).get('tasks',[]):errors.append('task scope mismatch')
            for dep in t.get('depends_on',[]):
                if dep in ts and order.get(ts[dep]['checkpoint'],999)>order.get(t['checkpoint'],-1):errors.append('task depends on later checkpoint')
            for pp in t.get('paths',[]):
                if not safe_relative(pp['path']):errors.append('unsafe task path')
            for v in t.get('verification',[]):
                if not safe_relative(v['cwd'],True):errors.append('unsafe command cwd')
        if set(model['execution']['tasks'])!=set(ts):errors.append('task state partition mismatch')
        if set(model['execution']['prerequisites'])!={g['id'] for g in n['prerequisites']}:errors.append('prerequisite state mismatch')
        for tid,state in model['execution']['tasks'].items():
            if state['state'] in ('REVIEW','ACCEPTED') and not state['evidence_refs']:errors.append(tid+': state lacks evidence refs')
            if state['state']=='BLOCKED' and not state['reason']:errors.append(tid+': blocked without reason')
    if model['governance']['state']=='approved' and not model['governance']['approvals']:errors.append('approved state has no attestation')
    return errors

def ready_errors(model,spec=None):
    errors=semantic_errors(model);n=model['normative']
    if model['kind']=='spec':
        for key in ('problem','caller','outcome'):
            if not n['intent'].get(key,'').strip():errors.append('intent.'+key+': missing')
        for key in ('choice','tradeoff'):
            if not n['approach'].get(key,'').strip():errors.append('approach.'+key+': missing')
        if not n['scope']:errors.append('scope: missing')
        if not n['criteria']:errors.append('criteria: missing')
        covered=set()
        for c in n['criteria']:
            ident=c['id'];covered.update(c.get('intent_refs',[]))
            for k in ('statement','kind','obligation'):
                if not c.get(k):errors.append(ident+': missing '+k)
            for k in ('applicability','intent_refs','guarantees','scenarios','verification'):
                if not c.get(k):errors.append(ident+': missing '+k)
            for sc in c.get('scenarios',[]):
                if any(not sc.get(k,'').strip() for k in ('given','when','then')):errors.append(ident+': incomplete scenario')
            v=c.get('verification') or {}
            if any(not v.get(k,'').strip() for k in ('method','oracle','negative_control','planned_target')):errors.append(ident+': incomplete verification')
            required={x['id'] for x in n['constraints'] if 'all' in x['applies_to'] or ident in x['applies_to']}
            if not required<=set(c.get('constraint_refs',[])):errors.append(ident+': missing applicable constraint')
        if covered!={x['id'] for x in n['scope']}:errors.append('uncovered scope')
        for d in n['open_decisions']:
            if d['blocking'] and d['status']=='open':errors.append(d['id']+': blocking decision')
    else:
        if spec is None:errors.append('spec required for plan readiness');return errors
        if n['spec_ref']['artifact_id']!=spec['artifact_id'] or n['spec_ref']['normative_sha256']!=spec['integrity']['normative_sha256']:errors.append('stale or wrong spec binding')
        cs={c['id']:c for c in spec['normative']['criteria']};covered=set();disposed=set()
        for t in n['tasks']:
            for k in ('paths','steps','criterion_refs','verification','done_when','rollback'):
                if not t.get(k):errors.append(t['id']+': missing '+k)
            for ref in t.get('criterion_refs',[]):
                owner,cid=ref.split('#')
                if owner!=spec['artifact_id'] or cid not in cs:errors.append('unknown criterion reference')
                else:covered.add(cid)
            for v in t.get('verification',[]):
                if v['argv'][:2]==['go','test'] and '-run' in v['argv'] and not v['required_tests']:errors.append('missing required named tests')
        for d in n['criterion_dispositions']:
            owner,cid=d['criterion_ref'].split('#')
            if owner!=spec['artifact_id'] or cid not in cs or cs[cid].get('obligation')=='must':errors.append('invalid criterion disposition')
            if cid in disposed or cid in covered:errors.append('duplicate or covered disposition')
            disposed.add(cid)
        if covered|disposed!=set(cs):errors.append('uncovered criteria without disposition')
    for ident,r in records(model).items():
        # Section records can be paged as complete records, but must fit readiness cap too.
        if len(canonical(r))>12*1024:errors.append(ident+': exceeds ready record byte cap')
    return errors

def eligible(model):
    # This reference implementation intentionally has no external authority resolver.
    return {'execution_eligible':False,'authority_verified':False,'reason':'External workflow authority, runtime state and evidence are not verified by reference tools.'}
