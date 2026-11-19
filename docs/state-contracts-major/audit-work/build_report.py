import json, hashlib, re, html, collections, zipfile
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path('/workspace/scratch/6dd9dc5f561f')
WORK=ROOT/'audit-work'
REPO=ROOT/'codeArbiter'
OUT=ROOT/'deliverables'
OUT.mkdir(exist_ok=True)
SHA='fd7eb34b2da439551443d09526ab48fd1d1bb9bf'
BASE=f'https://github.com/arbiterForge/codeArbiter/blob/{SHA}/'
E=html.escape

def load(p): return json.loads((WORK/p).read_text())
def array(x): return x if isinstance(x,list) else [x] if x else []
def source(s):
    if isinstance(s,str):
        s=re.sub(r'^arbiterForge/codeArbiter@[0-9a-f]+:', '', s.strip())
        path,_,symbol=s.partition(':')
        out={'path':path,'symbol':symbol,'ref':f'arbiterForge/codeArbiter@{SHA}:{path}'}
        match=re.fullmatch(r'(.*?):(\d+(?:-\d+)?)',symbol)
        if match:out['symbol'],out['lines']=match.groups()
        return out
    s=dict(s)
    if s.get('path'):s['ref']=f'arbiterForge/codeArbiter@{SHA}:{s["path"]}'
    return s
def sources(value):
    out=[]
    for item in array(value):
        if isinstance(item,str):
            for part in re.split(r';\s+(?=(?:core|plugins|tools|site|docs|\.github|\.codearbiter)/)',item):
                out.append(source(part))
        else:out.append(source(item))
    return out
def source_html(ss):
    parts=[]
    for raw in sources(ss):
        s=source(raw);p=s.get('path',''); sym=s.get('symbol','')
        if p:
            raw_lines=s.get('lines',[])
            nums=[int(n) for n in re.findall(r'\d+',str(raw_lines))]
            anchor=('#L'+str(nums[0])+('-L'+str(nums[-1]) if nums[-1]!=nums[0] else '')) if nums else ''
            detail=str(sym) if sym else ''
            if nums:detail+=(' · ' if detail else '')+'line'+('s ' if len(set(nums))>1 else ' ')+str(nums[0])+('–'+str(nums[-1]) if nums[-1]!=nums[0] else '')
            parts.append(f'<a href="{E(BASE+p+anchor)}" target="_blank" rel="noreferrer">{E(p)}</a>'+ (f'<span class="symbol">{E(detail)}</span>' if detail else ''))
        else: parts.append(E(json.dumps(s,ensure_ascii=False)))
    return '<div class="sources">'+'<br>'.join(parts)+'</div>'
def textvalue(v):
    if isinstance(v,str):return v
    if isinstance(v,list):return '; '.join(textvalue(x) for x in v)
    if isinstance(v,dict):return '; '.join(str(k)+': '+textvalue(x) for k,x in v.items())
    return '' if v is None else str(v)
def para(s): return '<p>'+E(textvalue(s))+'</p>'
def table(headers,rows):
    return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+E(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+v+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'

INPUTS=[('workflows.json','Workflow and resource contracts'),('native.json','Native artifact engine'),('hooks.json','Python hooks and shared state'),('surfaces.json','Pi, farm, sandbox, site and packaging'),('release-ci.json','Hosted CI and release'),('site-extra.json','Site evidence and build projections'),('tooling.json','Maintainer measurement tools'),('generator-extra.json','Site generator contracts'),('sandbox-workflows.json','Sandbox operational instructions'),('pi-qualification-extra.json','Pi qualification tooling')]
datasets=[]; machines=[]; findings=[]; adrs=[]
for filename,domain in INPUTS:
    d=load(filename); datasets.append({'file':filename,'domain':domain,'data':d})
    for m in d['machines']:
        m['domain']=domain
        for i,t in enumerate(m['transitions'],1):
            t['transition_id']=m['id']+':'+str(i).zfill(2)
            t['from']=textvalue(t.get('from',t.get('from_state','')))
            for key in ('event','guard','to','effects','failure_retry'):
                t[key]=textvalue(t.get(key,''))
            t['source']=sources(t.get('source',m.get('sources',[])))
        machines.append(m)
    for f in d.get('findings',[]):
        f['domain']=domain
        f['status']=f.get('status',f.get('evidence_level',f.get('confidence',f.get('classification','source analysis'))))
        if not f.get('sources'):
            raw=f.get('source',f.get('evidence',[]))
            extracted=[]
            for candidate in array(raw):
                if isinstance(candidate,dict) and candidate.get('path'):extracted+=sources(candidate)
                elif isinstance(candidate,str) and re.match(r'^(?:arbiterForge/codeArbiter@[^:]+:)?(?:core|plugins|tools|site|docs|\.github|\.codearbiter)/',candidate):extracted+=sources(candidate)
            f['sources']=extracted
        else:f['sources']=sources(f['sources'])
        findings.append(f)
    adrs+=d.get('adr_assessments',[])

ids=[m['id'] for m in machines]
assert len(ids)==len(set(ids)), 'duplicate machine IDs'
fids=[f['id'] for f in findings]
assert len(fids)==len(set(fids)), 'duplicate finding IDs'
invalid=[]
for m in machines:
    assert m['transitions'],m['id']
    for t in m['transitions']:
        for key in ('from','event','to','effects'): assert t[key],(m['id'],key)
        for s in t['source']:
            s=source(s)
            if s.get('path') and not (REPO/s['path']).is_file():invalid.append(s['path'])
for f in findings:
    for s in array(f.get('sources',f.get('source',[]))):
        s=source(s)
        if s.get('path') and not (REPO/s['path']).is_file():invalid.append(s['path'])
assert not invalid, sorted(set(invalid))

recommendation={
 'decision':'Adopt one explicit transition contract per subsystem owner, with a shared vocabulary for outcomes and effects, and derive capabilities, diagnostics, workflow guidance and conformance checks from those owned contracts.',
 'scope':'An incremental internal architecture decision. Preserve host-specific behavior and the existing native transaction kernel. No repository changes were made by this audit.',
 'axes':[
  ['Progress','pending, active, review, completed, blocked, retired','A user or agent can update progress without manufacturing verification or authorization.'],
  ['Evidence','absent, current, stale, contradicted, partial, unavailable','A result names the source revision, scope and producer; stale proof does not silently rewrite historical progress.'],
  ['Authority','unestablished, granted for exact scope, denied, revoked or expired','A transition description is not an authority grant. Existing explicit user and host constraints remain controlling.'],
  ['Delivery','not requested, intent recorded, attempted, observed, outcome unknown','Committed local state and successfully delivered external effect are different facts. Unknown outcomes require observation before retry.'],
  ['Execution and containment','queued, running, cancel requested, quiescent, cleanup failed','A process exit, timeout request or closed UI is not proof all writers/resources stopped.'],
  ['Identity and generation','subject revision, input digest, operation id, owner/session/epoch','Callbacks and retries must remain bound to the exact operation and owner. Cancellation/disposal invalidates stale UI updates and ordinary execution authority; explicitly owned cleanup and outcome reconciliation remain permitted until settled.']
 ],
 'fields':['owner and contract version','subject identity and generation','state before','event with typed payload','guards and actual authority binding','next state','effect intents and their owning executor','observed effect outcome','user-facing disposition and machine-readable reason','retry/recovery rule','compatibility invariant'],
 'preserve':[
  'Keep existing stable IDs, schema/wire fields, operation-id replay, before-image history, canonical serialization and registered file ownership.',
  'Keep ordinary progress assistive. A missing optional attestation must not become a new permission ceremony or universal blocker.',
  'Preserve actual hard stops, explicit authority and host capability limits. Do not repair Pi child authors by bypassing unavailable confirmation or audit controls.',
  'Retain product/host and explicitly approved timing exceptions. Manual Project sync-now and merge-observed issue effects are not interchangeable.',
  'Use small ordinary Go/Python/TypeScript definitions and pure decisions where useful. A general statechart DSL, database, background daemon and single global machine are unnecessary.',
  'Do not claim transactional rollback of a remote publication, message or merge. Reconcile actual outcome and use the owner’s documented recovery.'
 ],
 'experience_acceptance':[
  ['UX','Truthful visible status and next action; no additional ordinary-work prompts; user changes survive uninstall; canceled UI/resources stay canceled.','Exercise success, refusal, interruption and resume from the user-facing owner. Record extra prompts and misleading readiness/empty-success states.'],
  ['DX','One owner for each capability, output class, state vocabulary and retry rule; generated derivatives stay consistent.','Change a contract once, regenerate the dependent catalog/schema/diagnostics, and prove all handlers/producers/consumers conform.'],
  ['AX','Discoverable current state, valid events, evidence scope, effect result and exact recovery action.','Require an agent to choose the next action from structured results without inferring permission, completion or retry safety from prose labels.']
 ],
 'limit':'No finite audit can guarantee that every future change always improves all three experiences or never breaks anything. The enforceable objective is explicit compatibility invariants, measured acceptance criteria, discriminating event-sequence tests, exact-artifact checks and rollback for each migration slice.'
}

migration=[
 ['0. Bind the baseline','Capture current command grammar, schemas, host events, file classes, exit codes and observable effects at the inspected commit. Label intended bug fixes separately.','All owners; source ledger and exact artifact inventories.','No behavior change. Replay the baseline before refactoring; preserve old records and package identities.'],
 ['1. Repair closed contract mismatches','Fix preview-output recognition, operation discovery, launch-binding bound parity, tombstone history, Pi package identity and sidebar disposal.','Native producer/reader owners; shared hook owner; Pi owner.','Small independent regressions for each reproduced or statically proven sequence. Roll back one code/deployment slice without rewriting stored history or moving immutable release tags.'],
 ['2. Make settlement and uncertainty explicit','Correct persona selection/delivery tracking; release receipt-only recovery; farm receipt recovery and containment propagation; distinguish failed sandbox inventory from empty inventory.','Hooks; release helper/workflow; farm runner; sandbox owner.','Inject failure after each external/local commit point. Prove read-back before retry and prohibit rerunning author work merely to recover a missing report.'],
 ['3. Extract owned transition definitions','Add typed state/event/result definitions alongside current handlers; generate capability and output registries and diagnostic projections first.','Per-domain owners; no global cross-product state enum.','Differential replay preserves public effects, exit codes and rejected events except an explicit approved bugfix list. Preserve unknown fields/old reads as required by actual schemas.'],
 ['4. Resolve actual policy decisions','Choose conflict stop scope, invalid-debug-packet correction, reviewer disposition, task progress/evidence invalidation, and any Pi child delegated authority design.','Maintainer decisions and owner implementation; amend affected ADRs.','These are intentional semantics changes and need a concrete reviewable proposal. Do not disguise them as an extraction/refactor.'],
 ['5. Propagate and qualify','Update the owning host adapters; regenerate shared Python copies, surface/catalog projections and compiled bundles; validate exact built payloads. Propagate verified owner facts into site/reference content and separately scoped training compatibility.','core → generated adapters/build contracts → package checks → documentation/site → separately scoped Academy compatibility.','Platform/host matrix plus installed-artifact checks; then release per target. Keep tags immutable and original provenance/receipts.']
]

approval=[
 ['Conflict scope','Whether a document-level conflict pauses only dependent work, with global host/user stops still global.'],
 ['Debug and reviewer policy','Whether corrected malformed packets can be resubmitted, and how severity differs from gate disposition.'],
 ['Progress versus evidence','Whether task-block/reconcile invalidation changes progress markers, evidence applicability, or both; define migration before changing old records.'],
 ['Pi child authors','Either implement an actually supported scoped parent delegation/audit path, or advertise the child capability as read-only until that exists.'],
 ['New durable interruption recovery','Whether to add a registered bounded residue record for terminal harvest; keep ordinary work nonblocking.'],
 ['Governance changes','Amend the specific ADR/compatibility/release-policy clauses that conflict with the selected implementation, using the normal acceptance owner.']
]

verification=[
 'Native Go branches were fully read, but no Go toolchain was available in this workspace. Native composition failures are source-confirmed, not claimed as executed native integration tests.',
 'The Python and Node probes use actual repository functions with temporary fixtures or injected host/Docker/terminal adapters. They do not constitute installed Claude, Codex or Pi host qualification.',
 'No npm publication, GitHub Release mutation, remote Project/issue write, real Docker containment run or farm provider inference was performed. Publication and process recovery findings use source analysis and bounded pure probes.',
 'Verify native writer/reader closure, launch-binding limits and tombstone preservation on the supported OS/architecture matrix and exact distributed binaries.',
 'Exercise Pi activation/child tools/sidebar under the supported actual host runtime; verify cancellation and callback ordering with real UI and process lifetimes.',
 'Exercise farm process-tree containment and report recovery with injected timeout, cleanup failure and final report-write failure; prove no surviving writer can race a reset/retry.',
 'Exercise sandbox Docker output overflow, cancellation and failed removal; verify workload quiescence independently from client exit and preserve unknown inventory/cleanup outcomes.',
 'Exercise release publication failure after the Release becomes public and before final codearbiter-publication.json attachment; rerun must complete missing evidence without retagging or republishing.',
 'Qualify each exact released payload independently. Source on main, an accepted ADR, a successful packaging validator, or advisory exit0 is not a released-behavior guarantee.'
]

claim_delta=[
 ['Current implementation facts','Product-specific; commit-bound','Add commit-bound findings and transition ownership, including unknown/degraded states and source-vs-probe evidence.','Development claim registry only; do not label main released.'],
 ['Native observation contract','Product-specific with platform-specific behavior','Replace blanket read-lock/read-side-effect descriptions with operation- and platform-specific behavior.','Read mode, operation and platform belong in the claim key.'],
 ['Context and evidence','Product-family shared, with explicit host/consumer exceptions','Distinguish ordinary assistive progress, optional strict consumers, provenance, delivery observations and host qualification.','Old audits and older mandatory-context claims need revalidation.'],
 ['Pi capability','Surface-specific and release-specific','Separate current normal host support, the older narrow approval-entry code path and runtime gate, child execution capability and package identity.','Exact package/runtime evidence is required; no general approval support claim inferred.'],
 ['Release and retirement','Product-specific policy; release-specific observations','Align publication recovery, pre-tag advisory/gating behavior and compatibility-removal metadata with one approved policy.','Publication/clock evidence remains release-specific.'],
 ['Names and catalog counts','Shared product facts with surface-specific projections','Generate command grammar, lens counts, role summaries and hook delivery owner from canonical metadata.','Preserve legitimate host and product differences. No organization-global identity change is proposed.']
]

extra_adrs=[
 {'source':{'path':'.codearbiter/decisions/0030-orchestration-mode-plane-with-composed-persona.md'},'assessment':'Its per-session-and-mode cache description conflicts with its promise of injection on each mode change. The reproduced A→B→A sequence suppresses the return injection. Bind delivery to current selection/generation/content and amend the cache contract; do not treat the accepted text as proof that transitions work.'},
 {'source':{'path':'.codearbiter/decisions/0036-bounded-authorization-cleanup-direction.md'},'assessment':'Retain bounded authorization and actual host/user hard stops. Explicit state contracts can carry existing authority without new approval ceremonies. Any removal of a current confirmation or change in authority semantics is a distinct reviewable decision.'},
 {'source':{'path':'.codearbiter/decisions/0040-independent-per-target-release-with-consumer-safety-gates.md'},'assessment':'The ordinary CI candidate path makes a nominally advisory pre-tag command a gate, and published-without-receipt is not admitted by the outer recovery eligibility path. Reconcile those facts with the ADR rather than claiming its rerun/advisory intent is implemented.'},
 {'source':{'path':'.codearbiter/decisions/0044-trusted-pi-npm-publication.md'},'assessment':'This decision changes Pi publication trust/provenance. It does not by itself supersede the unrelated pre-tag advisory rule or repair the published-release receipt recovery admission gap.'}
]
adrs+=extra_adrs
for a in adrs:
    if 'source' not in a and a.get('path'):a['source']={'path':a['path']}
    if 'assessment' not in a:
        a['assessment']=' '.join(k.capitalize()+': '+textvalue(v) for k,v in a.items() if k not in {'path','source','sources'})

probes=[]
for p in sorted(WORK.glob('probe*')):
    if p.is_file() and p.suffix=='.json':
        probes.append({'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'observation':json.loads(p.read_text())})

# Coverage is supplied by the audit owners. This preserves read granularity.
coverage=load('coverage.json')
head=load('head-final.json')
rows=sum(len(m['transitions']) for m in machines)
model={'repository':'arbiterForge/codeArbiter','branch':'main','commit':SHA,'source_head_recheck':head,
       'date':'2026-11-09','audit_kind':'Read-only development-source state-machine audit; not released-artifact qualification',
       'count_semantics':'Machine families are analytical ownership groupings. Transition rows describe observed branches/temporal protocols; counts are not product feature counts or proof of formal exhaustiveness.',
       'counts':{'machine_families':len(machines),'transition_rows':rows,'findings':len(findings)},
       'recommendation':recommendation,'migration':migration,'approval_decisions':approval,'verification_remaining':verification,
       'claim_registry_delta':claim_delta,'machines':machines,'findings':findings,'adr_assessments':adrs,'coverage':coverage,'probe_observations':probes,
       'source_ledger_metadata':[{'file':x['file'],'domain':x['domain'],'metadata':{k:v for k,v in x['data'].items() if k not in {'machines','findings','adr_assessments'}}} for x in datasets]}
(OUT/'codearbiter_state_machines.json').write_text(json.dumps(model,indent=2,ensure_ascii=False)+'\n')

css='''
:root{--ink:#172138;--muted:#526179;--accent:#3831a6;--line:#d7dfeb;--bg:#f4f6fa;--paper:#fff;--warm:#fff1d6;--error:#9a2d36}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}header{background:#172138;color:white;padding:50px max(4vw,24px) 40px}header p{max-width:980px;color:#e0e5f2}h1{font-size:clamp(32px,4vw,54px);line-height:1.08;margin:10px 0 22px}h2{font-size:29px;line-height:1.2;margin:0 0 20px}h3{font-size:21px;margin:0 0 14px}h4{font-size:16px;margin:18px 0 6px}.eyebrow{letter-spacing:.12em;text-transform:uppercase;font-weight:650;font-size:12px}.stamp{font-family:ui-monospace,monospace;font-size:12px;overflow-wrap:anywhere}.stats{display:flex;gap:30px;flex-wrap:wrap;margin-top:24px}.stats strong{font-size:29px;display:block}.stats span{font-size:12px;color:#c7d1e5}nav{position:sticky;top:0;z-index:10;background:white;border-bottom:1px solid var(--line);padding:13px 4vw;display:flex;gap:18px;flex-wrap:wrap}nav a{color:var(--ink);text-decoration:none;font-size:13px;font-weight:650}main{max-width:1680px;margin:auto;padding:30px max(3vw,18px)}section{scroll-margin-top:90px;background:var(--paper);padding:32px;margin-bottom:28px;border:1px solid var(--line);border-radius:12px}p{margin:0 0 14px}a{color:var(--accent);overflow-wrap:anywhere}code{font:12px/1.5 ui-monospace,monospace;background:#eef0f7;padding:2px 4px;border-radius:3px;overflow-wrap:anywhere}.callout{padding:20px 22px;background:#eeedf9;border-left:4px solid var(--accent);margin-bottom:20px}.note{background:var(--warm);padding:16px 20px;border-radius:7px}.small{font-size:13px;color:var(--muted)}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:6px;margin:16px 0 22px}table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.5}th{text-align:left;background:#edf1f8;color:var(--ink);font-size:12px;letter-spacing:.02em}td,th{padding:12px 13px;vertical-align:top;border-bottom:1px solid var(--line)}tr:last-child td{border-bottom:0}tbody tr:nth-child(even){background:#fafbfe}td{min-width:100px}.matrix table{min-width:1400px;table-layout:fixed}.matrix th:nth-child(1){width:12%}.matrix th:nth-child(2){width:12%}.matrix th:nth-child(3){width:13%}.matrix th:nth-child(4){width:10%}.matrix th:nth-child(5){width:20%}.matrix th:nth-child(6){width:17%}.matrix th:nth-child(7){width:16%}.sources{font-size:11px;line-height:1.4}.symbol{display:block;color:var(--muted);font-family:ui-monospace,monospace}.machine{margin:24px 0 34px;padding-top:24px;border-top:2px solid var(--line);scroll-margin-top:80px}.machine h3{margin-bottom:7px}.pill{display:inline-block;padding:3px 8px;border-radius:5px;background:#edf1f8;font-size:11px;margin-right:5px}.state-list{font-size:13px;color:var(--muted)}.controls{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:20px 0}input,select,button{font:inherit;font-size:14px;padding:10px 12px;border:1px solid #aab7cc;border-radius:6px;background:white;color:var(--ink)}input{flex:1;min-width:240px}button{cursor:pointer}button:hover{background:#edf1f8}.finding{padding:22px;margin:18px 0;border:1px solid var(--line);border-left:4px solid #7e8ba5;border-radius:6px}.finding.high,.finding.critical{border-left-color:var(--error)}.finding h3{font-size:19px}.finding .detail{font-size:15px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.grid>div{padding:20px;background:#f4f6fa;border:1px solid var(--line);border-radius:7px}.index{columns:3;column-gap:25px;list-style:none;padding:0}.index li{break-inside:avoid;padding:6px 0;font-size:13px}.index small{color:var(--muted)}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 ui-monospace,monospace;background:#f1f4f9;padding:18px;border-radius:6px}details{margin:15px 0}summary{cursor:pointer;font-weight:650}.hidden{display:none!important}footer{padding:25px 4vw;color:var(--muted);font-size:12px}@media(max-width:800px){section{padding:20px}.grid{grid-template-columns:1fr}.index{columns:1}nav{position:static}.stats{gap:16px}main{padding:15px}}@media print{body{background:white;font-size:10pt}header{background:white;color:#172138;padding:20px}header p,header .stats span{color:#172138}nav,.controls{display:none}main{padding:0}section{border:0;padding:10px 0;break-before:page}.table-wrap{overflow:visible;border:0}.matrix table{min-width:0;table-layout:auto;font-size:7pt}.matrix td,.matrix th{padding:5px;min-width:0;width:auto!important}.sources{font-size:6pt}.machine{break-before:page}.finding{break-inside:avoid}a{color:#172138;text-decoration:none}.hidden{display:block!important}tr.hidden{display:table-row!important}details>*{display:block!important}h1{font-size:28pt}.index{columns:2}thead{display:table-header-group}}
'''
parts=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>codeArbiter — implicit state machine audit</title><style>'+css+'</style></head><body>']
parts.append('<header><div class="eyebrow">ArbiterForge / development source audit / 09 November 2026</div><h1>codeArbiter<br>Implicit state machines</h1><p>A complete transition ledger for the audited implementation and operational workflow owners: current state × event × guard × next state × side effects × recovery. Every row retains its source.</p><div class="stamp">arbiterForge/codeArbiter@'+SHA+' · branch main</div><div class="stats">'+''.join('<div><strong>'+str(v)+'</strong><span>'+k+'</span></div>' for k,v in [('machine families',len(machines)),('transition rows',rows),('finding and boundary records',len(findings)),('reviewed source files',coverage.get('reviewed_unique_files','see coverage'))])+'</div></header>')
parts.append('<nav><a href="#decision">Decision</a><a href="#findings">Findings</a><a href="#ledger">Full transition table</a><a href="#adrs">ADRs and policy</a><a href="#migration">Migration</a><a href="#coverage">Evidence and coverage</a><a href="#close">Required decisions and verification</a></nav><main>')
parts.append('<section id="decision"><h2>The recommended decision</h2><div class="callout"><strong>'+E(recommendation['decision'])+'</strong></div>'+para(recommendation['scope'])+para('The recurrent failure is a disagreement between state owners: a producer creates a state its consumer rejects, a completion or readiness label combines distinct facts, or a retry repeats a side effect whose outcome was already committed. The recommendation is to make those boundaries explicit and testable.')+table(['Independent axis','Typical observations','Required distinction'],[[E(c) for c in r] for r in recommendation['axes']])+'<h3>Contract contents</h3>'+para('Each owner declares: '+', '.join(recommendation['fields'])+'.')+'<div class="grid">'+''.join('<div>'+E(x)+'</div>' for x in recommendation['preserve'])+'</div><h3 style="margin-top:24px">Acceptance criteria across all three experiences</h3>'+table(['Experience','Expected improvement','How to verify it'],[[E(c) for c in r] for r in recommendation['experience_acceptance']])+'<p class="note">'+E(recommendation['limit'])+'</p></section>')

parts.append('<section id="findings"><h2>Confirmed findings and material contradictions</h2><p>The status on each finding states the evidence level. A bounded probe is not an installed-host or release test. The complete finding records are also preserved in the JSON ledger.</p>')
for f in findings:
    sev=textvalue(f.get('severity','')).lower()
    parts.append(f'<article class="finding {E(sev)}" id="{E(f["id"])}"><span class="pill">{E(f["id"])}</span><span class="pill">{E(f.get("domain",""))}</span><span class="pill">{E(textvalue(f.get("status",f.get("evidence_level","source analysis"))))}</span><h3>{E(f.get("title",f.get("name","Finding")))}</h3>')
    for k,v in f.items():
        if k in {'id','domain','severity','status','evidence_level','title','name','sources','source'}:continue
        parts.append('<h4>'+E(k.replace('_',' ').capitalize())+'</h4>'+para(v))
    parts.append(source_html(f.get('sources',f.get('source',[])))+'</article>')
parts.append('</section>')

parts.append('<section id="ledger"><h2>Full state × events × side effects table</h2><p>All '+str(rows)+' transition rows are present below. Filters hide rows for inspection; Clear filters restores the complete table. Each family keeps its own state, event and effect owner. Shared row guards describe multiple equivalent branches; they are not a claim that arbitrary events are accepted from every state.</p><p class="small">Implemented means code-enforced branches were inspected. Model-guided means installed instructions prescribe the behavior; prose alone does not prove execution. State names are analytical labels unless the row identifies literal values. A parser, classifier or pure reconciliation helper is included when its changing context affects observable interpretation; ordinary stateless formatting and repeated generated copies are not counted as additional product lifecycles.</p>')
parts.append('<div class="controls"><input id="query" type="search" placeholder="Search state, event, effect, recovery, file or family" aria-label="Search transition table"><select id="domain" aria-label="Domain"><option value="">All domains</option>'+''.join('<option>'+E(x['domain'])+'</option>' for x in datasets)+'</select><select id="kind" aria-label="Enforcement"><option value="">All enforcement types</option>'+''.join('<option>'+E(x)+'</option>' for x in sorted(set(m.get('kind','implemented') for m in machines)))+'</select><button id="clear">Clear filters</button><button id="print">Print full report</button><span id="count" class="small"></span></div>')
parts.append('<details open><summary>Machine index</summary><ul class="index">'+''.join('<li><a href="#'+E(m['id'])+'">'+E(m['id']+' · '+m['name'])+'</a> <small>('+str(len(m['transitions']))+' rows)</small></li>' for m in machines)+'</ul></details>')
for m in machines:
    parts.append('<article class="machine" id="'+E(m['id'])+'" data-domain="'+E(m['domain'])+'" data-kind="'+E(m.get('kind','implemented'))+'"><h3>'+E(m['id']+' · '+m['name'])+'</h3><span class="pill">'+E(m['domain'])+'</span><span class="pill">'+E(m.get('kind','implemented'))+'</span><p class="state-list"><strong>State owner/storage:</strong> '+E(textvalue(m.get('state_storage',m.get('storage','See source'))))+'</p>')
    if m.get('state_notation'):parts.append('<p class="small">'+E(m['state_notation'])+'</p>')
    if m.get('scope'):parts.append('<p class="small"><strong>Scope:</strong> '+E(textvalue(m['scope']))+'</p>')
    if m.get('explicitness'):parts.append('<p class="small"><strong>Representation:</strong> '+E(textvalue(m['explicitness']))+'</p>')
    if m.get('notes'):parts.append('<p class="small">'+E(textvalue(m['notes']))+'</p>')
    if m.get('states'):parts.append('<details><summary>State labels in this family</summary>'+para(m['states'])+'</details>')
    parts.append('<div class="table-wrap matrix"><table><thead><tr>'+''.join('<th>'+x+'</th>' for x in ['State before','Event','Guard / scope','State after','Side effects','Failure / retry / recovery','Source'])+'</tr></thead><tbody>')
    for t in m['transitions']:
        parts.append('<tr class="transition" id="'+E(t['transition_id'])+'"><td><span class="pill">'+E(t['transition_id'])+'</span><br>'+E(t['from'])+'</td>'+''.join('<td>'+E(t[k])+'</td>' for k in ['event','guard','to','effects','failure_retry'])+'<td>'+source_html(t['source'])+'</td></tr>')
    parts.append('</tbody></table></div></article>')
parts.append('</section>')

parts.append('<section id="adrs"><h2>ADRs are decisions, not execution evidence</h2><p>These assessments compare current implementation with the relevant decision text. The recommendation preserves decisions that remain useful and calls out specific clauses that require correction or an intentional new decision.</p>')
parts.append(table(['Decision source','Assessment'],[[source_html(a.get('source',a.get('sources',[]))),E(textvalue(a.get('assessment',a.get('detail',a))))] for a in adrs]))
parts.append('<h3>Canon and claim-registry delta</h3>'+table(['Claim area','Scope classification','Proposed correction','Authority boundary'],[[E(c) for c in r] for r in claim_delta])+'<p>No organization canon, claim registry, ADR or public surface was changed by this audit. Historical Project Sources were treated as policy/context and revalidated where current implementation differed.</p></section>')
parts.append('<section id="migration"><h2>Smallest durable migration</h2>'+table(['Slice','Change','Owning surfaces','Verification and rollback'],[[E(c) for c in r] for r in migration])+'<h3>Sequence tests that distinguish real behavior</h3>'+para('Mode A→B→A; mode marker write succeeds then audit append fails; dispose while sidebar metrics are pending; preview write→strict snapshot; accepted launch binding→completion consumer; check history→task retirement; local commit/merge→final report failure→recovery; Release published→receipt attachment fails→rerun; timeout/overflow→cleanup failure→retry; inventory unavailable→display; user edits spinner setting→uninstall.')+para('For each sequence, assert observable effects and retained state, not only return codes or line coverage. During extraction, compare old and new behavior on existing inputs and fail on any unexplained difference. Intentional bug fixes are named exceptions, reviewed independently.')+'</section>')

parts.append('<section id="coverage"><h2>Evidence, coverage and exact boundaries</h2>'+para(coverage.get('overview',''))+'<p class="stamp">Final main-head observation: '+E(textvalue(head))+'</p><p>Source references in this report resolve to <code>arbiterForge/codeArbiter@'+SHA+':path</code>. The branch name is supplied for orientation; the commit is the audit boundary.</p>')
for k,v in coverage.items():
    if k in {'files','overview'}:continue
    parts.append('<h4>'+E(k.replace('_',' ').capitalize())+'</h4>'+para(v))
parts.append('<details><summary>Per-file read and inventory classification</summary>'+table(['Path','Read or inventory classification','Evidence'],[[E(x.get('path','')),E(textvalue(x.get('status',''))),E(textvalue(x.get('evidence','')))] for x in coverage.get('files',[])])+'</details>')
parts.append('<h3>Bounded probe observations</h3><p>These are the captured results, retained without broadening their scope. Probe source and raw result files are included in the evidence archive.</p>')
for p in probes:
    parts.append('<details><summary>'+E(p['file'])+'</summary><div class="stamp">SHA256 '+E(p['sha256'])+'</div><pre>'+E(json.dumps(p['observation'],indent=2,ensure_ascii=False))+'</pre></details>')
parts.append('</section>')
parts.append('<section id="close"><h2>Decisions and remaining verification</h2><h3>Decisions requiring user approval before remediation</h3>'+table(['Decision','Concrete scope'],[[E(c) for c in r] for r in approval])+'<p>These decisions do not block the completed read-only audit. They identify the intentional semantics changes that must be separated from compatible refactoring and defect repair.</p><h3>Verification still required</h3><ol>'+''.join('<li>'+E(x)+'</li>' for x in verification)+'</ol><h3>Affected surfaces</h3>'+para('Within this audit: core/artifacts; core/pysrc; core/surface; the generated ca, ca-codex and ca-pi payloads; Pi TypeScript extension; farm and sandbox tools; build/qualification scripts; GitHub CI/release workflows; and the in-repository documentation site. Other authorized organization repositories were not inspected or changed. Any later propagation into Academy or a separate product site requires its own exact-source compatibility check.')+'<h3>Recommended next action</h3>'+para('Adopt the transition-contract decision, then implement the smallest first slice: native output writer/reader closure and operation discovery, with preview→snapshot and capability/dispatch consistency regressions. In parallel, keep the separately evidenced persona, Pi diagnostics/sidebar and release/farm recovery defects as separate reviewable fixes. Do not start with a whole-system rewrite.')+'</section></main><footer>Read-only audit · arbiterForge/codeArbiter@'+SHA+' · Generated from the complete structured transition ledger. No repository, package, release or website was changed.</footer>')
parts.append('''<script>
const machines=[...document.querySelectorAll('.machine')];const q=document.querySelector('#query'),d=document.querySelector('#domain'),k=document.querySelector('#kind'),count=document.querySelector('#count');
const indexed=machines.map(m=>({m,head:m.querySelector('h3').textContent.toLowerCase(),rows:[...m.querySelectorAll('.transition')].map(r=>({r,text:r.textContent.toLowerCase()}))}));
function apply(){const term=q.value.trim().toLowerCase();let n=0,f=0;for(const x of indexed){const eligible=(!d.value||x.m.dataset.domain===d.value)&&(!k.value||x.m.dataset.kind===k.value);let visible=0;for(const y of x.rows){const show=eligible&&(!term||x.head.includes(term)||y.text.includes(term));y.r.classList.toggle('hidden',!show);if(show)visible++;}x.m.classList.toggle('hidden',!visible);n+=visible;if(visible)f++;}count.textContent=`${n.toLocaleString()} transitions · ${f} families`;}
q.addEventListener('input',apply);d.addEventListener('change',apply);k.addEventListener('change',apply);document.querySelector('#clear').addEventListener('click',()=>{q.value=d.value=k.value='';apply();});document.querySelector('#print').addEventListener('click',()=>{q.value=d.value=k.value='';apply();window.print();});apply();
</script></body></html>''')
(OUT/'codearbiter_state_machine_audit.html').write_text(''.join(parts))
print(json.dumps({'families':len(machines),'rows':rows,'findings':len(findings),'report_bytes':(OUT/'codearbiter_state_machine_audit.html').stat().st_size}))
