#!/usr/bin/env python3
"""Deterministic renderer for this reference schema. Not the production Go tool."""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
from artifact_io import load, verified_load, records, digests

def e(v): return html.escape(str(v), quote=True)
def refs(ids):
    if not ids:return ''
    return '<div class="refs">Sources: '+''.join(f'<a href="#{e(x)}">{e(x)}</a>' for x in ids)+'</div>'
def wrap(ident,kind,content,tag='div',cls='',extra=''):
    return f'\n<!-- CA:BEGIN:{e(ident)} -->\n<{tag} id="{e(ident)}" data-ca-symbol="{e(ident)}" data-ca-kind="{e(kind)}"'+(f' class="{e(cls)}"' if cls else '')+(' '+extra if extra else '')+'>'+content+f'</{tag}>\n<!-- CA:END:{e(ident)} -->\n'
def table(cols,rows,cls=''):
    return '<div class="table-wrap"><table'+(f' class="{e(cls)}"' if cls else '')+'><thead><tr>'+''.join('<th scope="col">'+e(c)+'</th>' for c in cols)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+cell+'</td>' for cell in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def bullet(items,ordered=False):
    tag='ol' if ordered else 'ul'
    return '<'+tag+'>'+''.join('<li>'+e(i)+'</li>' for i in items)+'</'+tag+'>'
def block(b):
    if b['type']=='paragraph':body='<p>'+e(b['text'])+'</p>'
    elif b['type']=='list':body=bullet(b['items'])
    elif b['type']=='code':body='<pre><code>'+e(b['text'])+'</code></pre>'
    elif b['type']=='table':body=table(b['columns'],[[e(c) for c in r] for r in b['rows']])
    else:raise ValueError('unsupported block')
    return '<div class="block">'+body+refs(b.get('refs',[]))+'</div>'
def section(s):
    return wrap(s['id'],'section','<h2>'+e(s['title'])+'<a class="toplink" href="#main-content">Top</a></h2>'+''.join(block(b) for b in s['blocks']),'section','chapter')
def chapter(ident,title,body):return f'<section id="{e(ident)}" class="chapter"><h2>{e(title)}<a class="toplink" href="#main-content">Top</a></h2>{body}</section>'
def scope(items,kind):
    return ''.join(wrap(r['id'],kind,'<span class="symbol-label">'+e(r['id'])+'</span><p>'+e(r['statement'])+'</p>',cls='scope-item') for r in items)
def criterion(c):
    body='<summary><span class="record-id">'+e(c['id'])+' · '+e(c.get('obligation','unspecified').upper())+' · VERIFICATION DEFINITION</span><strong>'+e(c['title'])+'</strong></summary><div class="record-body">'
    body+='<p class="statement">'+e(c.get('statement') or 'Not yet specified')+'</p>'
    body+='<div class="tags">'+''.join('<a class="tag" href="#'+e(x)+'">'+e(x)+'</a>' for x in c.get('intent_refs',[])+c.get('constraint_refs',[]))+'</div>'
    body+='<p><strong>Kind:</strong> '+e(c.get('kind','unspecified'))+'</p>'
    if c.get('applicability'):body+='<p><strong>Applicability:</strong> '+e(c['applicability']['mode'])+'; '+e(c['applicability']['rationale'])+'</p>'
    body+='<h4>Conditions</h4>'+bullet(c.get('preconditions',[]))+'<h4>Trigger</h4><p>'+e(c.get('trigger') or 'Not specified / not applicable')+'</p>'
    body+='<h4>Required guarantees</h4>'+bullet(c.get('guarantees',[]))+'<h4>Discriminating scenarios</h4>'
    for s in c.get('scenarios',[]):
        inner='<div class="symbol-label">'+e(s['id'])+'</div>'
        inner+=''.join('<p><strong>'+label+'</strong> '+e(s.get(key) or 'Not yet specified')+'</p>' for key,label in [('given','Given'),('when','When'),('then','Then')])
        body+=wrap(s['id'],'scenario',inner,cls='scenario')
    v=c.get('verification')
    if v:
        inner='<h4>Verification definition · '+e(v['id'])+'</h4>'
        for key,label in [('planned_target','Planned target'),('oracle','Oracle'),('negative_control','Negative control'),('method','Method'),('evidence_state','Definition state')]:
            inner+='<p><strong>'+label+':</strong> '+e(v.get(key) or 'Not yet specified')+'</p>'
        body+=wrap(v['id'],'verification',inner,cls='verify')
    else:body+='<p><strong>Verification definition missing; draft is not ready.</strong></p>'
    body+=refs(c.get('source_refs',[]))+'</div>'
    return wrap(c['id'],'criterion',body,'details','record','open')
def decision(d):
    return wrap(d['id'],'decision','<div class="symbol-label">'+e(d['id'])+' · '+e(d['authority'].upper())+'</div><h3>'+e(d['topic'])+'</h3><p><strong>Choice:</strong> '+e(d['choice'])+'</p><p><strong>Reason:</strong> '+e(d['rationale'])+'</p>',cls='decision')
def task(t,model):
    state=model['execution']['tasks'][t['id']]
    body='<summary><span class="record-id">'+e(t['id'])+' · '+e(t['checkpoint'])+' · '+e(state['state'])+'</span><strong>'+e(t['title'])+'</strong></summary><div class="record-body">'
    body+='<p><strong>Execution scope:</strong> '+e(t['execution_scope'])+'. <strong>Depends on:</strong> '+e(', '.join(t.get('depends_on',[])) or 'None; prerequisite gates still apply.')+'</p>'
    body+='<div class="tags">'+''.join('<a class="tag" href="'+e(model['presentation']['companion_path'])+'#'+e(r.split('#')[1])+'">'+e(r.split('#')[1])+'</a>' for r in t.get('criterion_refs',[]))+'</div>'
    body+='<h4>Exact path set</h4><ul class="pathlist">'
    for p in t.get('paths',[]):body+='<li><span class="path-action">'+e(p['action'])+'</span> <code>'+e(p['path'])+'</code></li>'
    body+='</ul><h4>Work sequence</h4>'+bullet(t.get('steps',[]),True)+'<h4>Verification</h4>'
    for v in t.get('verification',[]):
        body+='<div class="verify"><p><span class="tag">'+e(v['availability'])+' invocation</span> <strong>Working directory:</strong> <code>'+e(v['cwd'])+'</code></p>'
        body+='<p>Argument vector, not a shell command:</p><pre><code>'+e(json.dumps(v['argv'],ensure_ascii=False,indent=2))+'</code></pre>'
        body+='<p><strong>Expected exit:</strong> '+e(v['expected_exit'])+'. '+e(v['assertion'])+'</p>'
        if v['required_tests']:body+='<p><strong>Required non-skipped test events:</strong> '+e(', '.join(v['required_tests']))+'</p>'
        body+='</div>'
    body+='<h4>Acceptance for this task</h4>'+bullet(t.get('done_when',[]))
    body+='<p><strong>Recorded evidence refs (not resolved by this renderer):</strong> '+e(', '.join(state['evidence_refs']) or 'None')+'</p>'
    if state['reason']:body+='<p><strong>State reason:</strong> '+e(state['reason'])+'</p>'
    body+='<div class="notice"><strong>Rollback:</strong> '+e(t.get('rollback') or 'Not yet specified')+'</div>'+refs(t.get('source_refs',[]))+'</div>'
    return wrap(t['id'],'task',body,'details','record','open')
def source(s):
    heading='<a href="'+e(s['url'])+'" rel="noreferrer">'+e(s['title'])+'</a>' if s['url'] else e(s['title'])
    body='<div class="symbol-label">'+e(s['id'])+' · '+e(s['type'])+'</div><strong>'+heading+'</strong>'
    if s['locator']:body+='<div class="locator"><code>'+e(s['locator'])+'</code></div>'
    body+='<p>'+e(s['note'])+'</p>'
    return wrap(s['id'],'source',body,cls='source')

def typed_record(record,kind):
    # Closed schema fields rendered transparently; this is not an editable generic blob.
    body='<div class="symbol-label">'+e(record['id'])+'</div>'
    for key,value in sorted(record.items()):
        if key=='id':continue
        label=key.replace('_',' ').capitalize()
        if isinstance(value,list):body+='<h4>'+e(label)+'</h4>'+bullet(value)
        else:body+='<p><strong>'+e(label)+':</strong> '+e(value if value is not None else 'None')+'</p>'
    return wrap(record['id'],kind,body,cls='checkpoint')
def render(model,css):
    n=model['normative'];isplan=model['kind']=='plan';idx=records(model)
    nav=[(s['id'],s['title']) for s in n['sections']]
    extras=([('view-gates','Prerequisite gates'),('view-checkpoints','Six implementation checkpoints'),('view-task-index','Task index'),('view-coverage','Criterion coverage'),('view-tasks','Task contracts')] if isplan else [('view-scope','Scope and non-goals'),('view-decisions','Proposed design decisions'),('view-criteria','Behavioral contracts')])
    nav+=extras+([] if isplan else [('view-typed-core','Typed intent and constraints'),('view-open-decisions','Open decisions')])+[('view-retired','Retired symbols'),('view-sources','Source notes'),('view-machine','Machine structure')]
    peer=model['presentation']['companion_path']; peertext='Open the companion specification' if isplan else 'Open the companion implementation plan'
    title='Implementation plan' if isplan else 'Specification'
    count=len(n['tasks']) if isplan else len(n['criteria'])
    metrics=[(count,'defined tasks'),(len(n['checkpoints']),'review checkpoints'),(sum(x['state']=='ACCEPTED' for x in model['execution']['tasks'].values()),'recorded accepted; authority unchecked')] if isplan else [(count,'behavioral contracts'),(2,'canonical artifact kinds'),(0,'new public surfaces')]
    body='<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    body+='<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; img-src data:; style-src &#39;unsafe-inline&#39;; script-src &#39;none&#39;; base-uri &#39;none&#39;; form-action &#39;none&#39;">'
    body+='<meta name="color-scheme" content="light"><meta name="description" content="'+e(n['summary'])+'"><title>'+e(title+' | '+n['title']+' | '+model['presentation']['brand_name'])+'</title><style>\n'+css+'\n</style></head><body>'
    body+='<a class="skip" href="#main-content">Skip to document</a><aside class="rail" aria-label="Document browsing"><img class="brand" src="'+e(model['presentation']['logo_data_uri'])+'" alt="'+e(model['presentation']['brand_name'])+'" width="200" height="36">'
    body+='<div class="edition">'+e(title)+' / schema '+e(model['schema_version'])+'</div><nav>'+''.join('<a href="#'+e(i)+'">'+e(t)+'</a>' for i,t in nav)+'</nav><details class="mobile-toc"><summary>Document contents</summary><div>'+''.join('<a href="#'+e(i)+'">'+e(t)+'</a>' for i,t in nav)+'</div></details><div class="peer"><a href="'+e(peer)+'">'+peertext+'</a></div><small>Review artifact · not an approved implementation instruction</small><small style="margin-top:10px">'+e(model['artifact_id'])+'<br>Revision '+str(model['revision'])+'</small></aside>'
    body+='<div class="shell"><main id="main-content"><header class="hero"><p class="eyebrow">'+e(model['presentation']['brand_name'])+' / typed artifact engine</p><div class="status">'+e(model['governance']['state'].upper())+' · AUTHORITY NOT VERIFIED · '+('EXECUTION BLOCKED' if isplan else 'REVIEW COPY')+'</div><h1>'+e(n['title'])+'</h1><p class="deck">'+e(n['summary'])+'</p>'
    body+='<div class="meta"><span>'+e(model['artifact_id'])+'</span><span>Schema '+e(model['schema_version'])+' · revision '+str(model['revision'])+'</span><span>Baseline '+e((n['baseline']['commit'] or 'unborn / unrecorded')[:20] if not n['baseline']['commit'] else n['baseline']['commit'][:8])+'</span><span>'+e(n['baseline']['observed_date'])+'</span></div>'
    body+='<div class="metrics">'+''.join('<div class="metric"><strong>'+e(v)+'</strong><span>'+e(t)+'</span></div>' for v,t in metrics)+'</div></header><div class="content">'
    if isplan:
        body+='<div class="notice"><strong>Execution is blocked.</strong> This reference view does not verify workflow authority or resolve execution evidence. Recorded states below are claims in the model, not an authorization to dispatch. The spec binding is content identity, not approval.</div>'
        body+='<p class="digest">Source: '+e(n['spec_ref']['artifact_id'])+'<br>normative_sha256: '+e(n['spec_ref']['normative_sha256'])+'</p>'
    for s in n['sections']:body+=section(s)
    if not isplan:
        body+=chapter('view-typed-core','Typed intent, approach and constraints',typed_record(n['intent'],'intent')+typed_record(n['approach'],'approach')+''.join(typed_record(x,'constraint') for x in n['constraints']))
    if isplan:
        gates=''
        for g in n['prerequisites']:
            gates+=wrap(g['id'],'prerequisite','<div class="symbol-label">'+e(g['id'])+' · '+e(model['execution']['prerequisites'][g['id']].upper())+' (AUTHORITY UNCHECKED)</div><h3>'+e(g['title'])+'</h3><p>'+e(g['requirement'])+'</p>'+refs(g['source_refs']),cls='checkpoint')
        body+=chapter('view-gates','Prerequisite gates',gates)
        cps=''
        for cp in n['checkpoints']:
            text='<div class="symbol-label">'+e(cp['id'])+'</div><h3>'+e(cp['title'])+'</h3><p><strong>Predecessor scopes:</strong> '+e(', '.join(cp['depends_on']) or 'None')+'</p><div class="tags">'+''.join('<a class="tag" href="#'+e(t)+'">'+e(t)+'</a>' for t in cp['tasks'])+'</div><p><strong>Exit:</strong> '+e(cp['exit'])+'</p>'
            cps+=wrap(cp['id'],'checkpoint',text,cls='checkpoint')
        body+=chapter('view-checkpoints','Six implementation checkpoints',cps)
        rows=[]
        for t in n['tasks']:
            rows.append(['<a href="#'+e(t['id'])+'">'+e(t['id'])+'</a>',e(t['title']),'<span class="state">'+e(model['execution']['tasks'][t['id']]['state'])+'</span>',e(', '.join(t.get('depends_on',[])) or 'Gates only')])
        body+=chapter('view-task-index','Task index',table(['ID','Bounded work package','State','Dependencies'],rows,'task-table'))
        cov={}
        for t in n['tasks']:
            for ref in t.get('criterion_refs',[]):cov.setdefault(ref.split('#',1)[1],[]).append(t['id'])
        rows=[[f'<a href="{e(peer)}#{e(ac)}">{e(ac)}</a>',' '.join(f'<a href="#{e(t)}">{e(t)}</a>' for t in ts)] for ac,ts in sorted(cov.items())]
        body+=chapter('view-coverage','Criterion coverage','<p>This table is derived from task references. It is not a second acceptance ledger or proof of semantic completeness.</p>'+table(['Specification criterion','Tasks advancing or verifying it'],rows,'coverage'))
        body+=chapter('view-dispositions','Optional criterion dispositions', '<pre>'+e(json.dumps(n['criterion_dispositions'],ensure_ascii=False,sort_keys=True,indent=2))+'</pre>' if n['criterion_dispositions'] else '<p>No optional criterion omissions.</p>')
        body+=chapter('view-tasks','Task contracts','<p>Proposed commands name tests and files to be created by the corresponding task. They are not evidence that those tests exist or have passed. Expand or collapse individual work packages as needed.</p>'+''.join(task(t,model) for t in n['tasks']))
    else:
        body+=chapter('view-scope','Scope and non-goals','<h3>In scope</h3>'+scope(n['scope'],'scope')+'<h3>Explicit non-goals</h3>'+scope(n['non_goals'],'non_goal'))
        body+=chapter('view-decisions','Proposed design decisions','<p>These choices define the draft under review. They are not yet accepted architectural decisions in the repository.</p>'+''.join(decision(d) for d in n['decisions']))
        body+=chapter('view-criteria','Behavioral contracts','<p>Each criterion is independently assessable, can be exercised by more than one test, and is addressable by its stable ID. All verification definitions below are planned, not observed results.</p>'+''.join(criterion(c) for c in n['criteria']))
        body+=chapter('view-open-decisions','Open decisions', ''.join(typed_record(x,'open_decision') for x in n['open_decisions']) or '<p>None recorded. Readiness and approval are separate checks.</p>')
    body+=chapter('view-retired','Retired symbols',''.join(typed_record(x,'retired') for x in n['retired_symbols']) or '<p>No symbols retired.</p>')
    body+=chapter('view-sources','Source notes','<p>Repository references are pinned to the inspected baseline. Research supports selected content practices, not a claim that this entire artifact schema is empirically optimal.</p>'+''.join(source(s) for s in n['sources']))
    rows=[]
    for ident,r in sorted(idx.items()):
        name=r.get('title') or r.get('topic') or r.get('statement') or r.get('given') or r.get('planned_target') or ident
        rows.append(['<a href="#'+e(ident)+'">'+e(ident)+'</a>',e(name if len(name)<130 else name[:127]+'...')])
    machine='<p>The authoritative structured model is embedded once in <code>script#ca-artifact-model[type="application/json"]</code>. The visible body is its generated projection. Marker IDs map to complete model records, not heading guesses.</p>'
    machine+='<p><strong>Addressable records:</strong> '+str(len(idx))+'. <strong>Renderer:</strong> '+e(model['presentation']['renderer'])+'.</p>'
    machine+='<p class="digest">Normative digest: '+e(model['integrity']['normative_sha256'])+'<br>Model digest: '+e(model['integrity']['model_sha256'])+'</p>'
    machine+='<details><summary>Inspect the symbol manifest</summary>'+table(['Symbol','Record'],rows)+'</details>'
    machine+='<p><strong>Governance:</strong> '+e(model['governance']['state'])+'; '+str(len(model['governance']['approvals']))+' approval records. '+e(' '.join(model['governance']['review_notes']))+'</p>'
    machine+='<details><summary>Recorded governance metadata (authority not verified)</summary><pre>'+e(json.dumps(model['governance'],ensure_ascii=False,sort_keys=True,indent=2))+'</pre></details>'
    if not isplan:
        machine+='<p><strong>Governs:</strong> '+e(', '.join(n['governs']))+'. <strong>Open product decisions:</strong> '+str(len(n['open_decisions']))+'. Prerequisite approval gates are listed in the companion plan.</p>'
    body+=chapter('view-machine','Machine structure',machine)
    body+='</div><footer class="footer">Reference output for review. No repository changes, Go implementation, task execution or approval is represented by this file.<br>One canonical model per HTML artifact. <a href="'+e(peer)+'">'+peertext+'</a>.</footer></main></div>'
    embedded=json.dumps(model,ensure_ascii=False,sort_keys=True,indent=2).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e')
    body+='\n<script id="ca-artifact-model" type="application/json">\n'+embedded+'\n</script>\n</body></html>\n'
    return body

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('artifact',type=Path);ap.add_argument('--check',action='store_true')
    args=ap.parse_args()
    model,text,_=verified_load(args.artifact)
    css=(Path(__file__).resolve().parents[1]/'assets/artifact.css').read_text()
    out=render(model,css)
    if args.check:
        if out!=text:raise SystemExit('RENDER_DRIFT: generated view differs from model/renderer')
        print('Reference render matches embedded model.')
    else:
        raise SystemExit('Read-only reference utility: use --check; mutation belongs to the future Go engine.')
if __name__=='__main__':main()
