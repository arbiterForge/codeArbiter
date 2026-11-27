#!/usr/bin/env python3
"""Validate handoff structure and retained evidence, never product behavior or release authority."""
from pathlib import Path
import argparse
from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
import sys

def load(path):
    return json.loads(path.read_text())

def require(condition, message):
    if not condition:
        raise ValueError(message)

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids=[]; self.links=[]; self.task_ids=[]; self.machine_ids=[]; self.row_ids=[]
        self.tables=0
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='a':self.links.append(a.get('href',''))
        if 'data-task-id' in a:self.task_ids.append(a['data-task-id'])
        if 'data-machine-id' in a:self.machine_ids.append(a['data-machine-id'])
        if 'data-transition-id' in a:self.row_ids.append(a['data-transition-id'])
        if tag=='table':self.tables+=1
        if tag=='script':
            require(not a.get('src'),'External script in standalone guide')

def validate(root, repo=None, initial=False):
    audit=load(root/'audit/codearbiter_state_machines.json')
    program=load(root/'contracts/program.json')
    tasks_doc=load(root/'contracts/tasks.json')
    tasks=tasks_doc['tasks']
    tids=[t['id'] for t in tasks]; taskset=set(tids)
    require(len(tids)==len(taskset)==82,'Task count/duplicate mismatch')
    require(program['repository']=='arbiterForge/codeArbiter','Wrong repository scope')
    require(program['audit_source_commit']==audit['commit'],'Baseline SHA mismatch')
    findings=load(root/'contracts/finding-dispositions.json')['records']
    machines=load(root/'contracts/machine-coverage.json')['machines']
    transitions=load(root/'contracts/transition-coverage.json')['transitions']
    scenarios=load(root/'contracts/scenarios.json')['scenarios']
    require(len(findings)==70 and len(machines)==287 and len(transitions)==1748 and len(scenarios)==31,'Corpus count mismatch')
    original_machines={m['id']:m for m in audit['machines']}
    original_rows={r['transition_id']:r for m in audit['machines'] for r in m['transitions']}
    require({f['finding_id'] for f in findings}=={f['id'] for f in audit['findings']},'Missing/extra findings')
    require({m['machine_id'] for m in machines}==set(original_machines),'Missing/extra machines')
    require({r['transition_id'] for r in transitions}==set(original_rows),'Missing/extra transitions')
    require(len({s['id'] for s in scenarios})==31,'Duplicate scenario ID')
    sids={s['id'] for s in scenarios}
    dids={'D-CONFLICT','D-RESUBMIT','D-PROGRESS','D-PI','D-RECOVERY','D-ADR','D-BRANCH','D-HIGH','D-GOV-PRETAG'}
    by_id={t['id']:t for t in tasks}
    for t in tasks:
        require(set(t['dependencies']+t['completion_dependencies'])<=taskset,'Unresolved dependency '+t['id'])
        require(t['id'] not in t['dependencies']+t['completion_dependencies'],'Self dependency '+t['id'])
        require(set(t['decision_dependencies'])<=dids,'Unknown decision '+t['id'])
        require((root/t['detailed_specification']['file']).is_file(),'Missing detailed task ledger '+t['id'])
        require('Q-03' not in t['dependencies']+t['completion_dependencies'],'Publication used as a prerequisite '+t['id'])
        for ref in t['source_refs']:
            require(ref.startswith(program['repository']+'@'+audit['commit']+':'),'Unpinned task reference')
        if repo:
            for p in t['source_paths']:
                require((repo/p).is_file(),'Missing existing source path '+p)
        if initial:
            require(t['status']=='PLANNED','Initial handoff claimed implementation '+t['id'])
            require(not t['implementation_evidence'] and not t['qualification_evidence'],'Initial handoff populated future evidence')
    seen=set(); order=[]
    while len(seen)<len(taskset):
        ready=sorted(t['id'] for t in tasks if t['id'] not in seen and set(t['dependencies']+t['completion_dependencies'])<=seen)
        require(bool(ready),'Dependency cycle')
        seen.update(ready);order+=ready
    require(set(tasks_doc['topological_order'])==taskset,'Topological order population mismatch')
    require('PI-D01' in by_id['NT-10']['dependencies'],'Missing Pi/native contract order')
    require('NT-10' in by_id['PI-D04']['dependencies'],'Missing native/Pi effect order')
    require('PI-D07' not in by_id['HW-26']['dependencies']+by_id['HW-26']['completion_dependencies'],'Reversed Pi qualification input')
    require('HW-26' in by_id['PI-D07']['completion_dependencies'],'Missing qualification input to Pi')
    require(by_id['NT-09']['decision_dependencies']==['D-PROGRESS'],'Progress decision silently selected')
    require(by_id['HW-09']['decision_dependencies']==['D-HIGH'],'HIGH decision silently selected')
    require(by_id['R-03']['decision_dependencies']==['D-GOV-PRETAG'],'Pre-tag decision silently selected')
    for f in findings:
        require(f['task_ids'] and set(f['task_ids'])<=taskset,'Finding without owning task')
        require(set(f['decision_ids'])<=dids,'Unknown finding decision')
        require(set(f['composed_scenario_ids'])<=sids,'Unknown scenario')
        if initial:require(f['status']=='PLANNED' and not f['implementation_evidence'] and not f['qualification_evidence'],'Premature finding closure')
    machine_map={m['machine_id']:m for m in machines}
    for m in machines:
        require(m['owner'] and m['closure_task'] in taskset,'Machine without owner/closure')
        require(set(m['task_ids'])<=taskset,'Unknown machine task')
        require(m['transition_count']==len(original_machines[m['machine_id']]['transitions']),'Machine row count drift')
        if initial:require(m['status']=='NOT_RUN' and not m['evidence'],'Premature machine verification')
    for r in transitions:
        require(r['baseline']==original_rows[r['transition_id']],'Changed historical row '+r['transition_id'])
        require(r['machine_id'] in machine_map,'Unknown machine for row')
        require(set(r['task_ids'])<=taskset and r['task_ids'],'Row without valid responsibility')
        require(set(r['proposed_composed_scenario_ids'])<=sids,'Row has unknown proposed scenario')
        if initial:require(r['verification_status']=='NOT_RUN' and not r['evidence'] and r['candidate_transition'] is None,'Premature row verification')
    if initial:
        require(all(s['status']=='NOT_RUN' and not s['evidence'] for s in scenarios),'Premature scenario execution')
        require(not program['product_tests_executed_during_handoff'] and program['source_changes_made_during_handoff'] is False,'False handoff implementation claim')
    predicates=program['delivery_predicates']
    for stage in ['INTEGRATION_QUALIFIED','PREPUBLICATION_READY']:
        require(set(predicates[stage]['required_task_ids'])==taskset-{'Q-03'},'Circular/incomplete prepublication predicate')
    require(set(predicates['DISTRIBUTION_SETTLED']['required_task_ids'])==taskset,'Incomplete final settlement predicate')
    checked_source_paths=len({p for t in tasks for p in t['source_paths']})
    for p,h in program['audit_artifact_sha256'].items():
        require(hashlib.sha256((root/p).read_bytes()).hexdigest()==h,'Original audit artifact changed '+p)

    guide=root/'index.html'
    html_info={'present':guide.exists()}
    if guide.exists():
        page=Page();page.feed(guide.read_text());page.close()
        require(len(page.ids)==len(set(page.ids)),'Duplicate HTML id')
        require(set(page.task_ids)==taskset and len(page.task_ids)==82,'HTML task omission')
        require(set(page.machine_ids)==set(original_machines) and len(page.machine_ids)==287,'HTML machine omission')
        require(set(page.row_ids)==set(original_rows) and len(page.row_ids)==1748,'HTML transition omission')
        for link in page.links:
            require(not link.lower().startswith(('javascript:','data:','file:')),'Unsafe/unusable HTML link')
            if link.startswith('#'):require(link[1:] in set(page.ids),'Broken internal anchor '+link)
            elif link and not link.startswith(('https://','http://','mailto:')):
                require((root/link.split('#',1)[0]).exists(),'Broken local guide link '+link)
        html_info.update({'tasks':len(page.task_ids),'machines':len(page.machine_ids),'transitions':len(page.row_ids),'tables':page.tables,'links':len(page.links)})
    manifest=root/'MANIFEST.json'
    manifest_count=0
    if manifest.exists():
        md=load(manifest)
        listed={f['path'] for f in md['files']}
        actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p!=manifest and '__pycache__' not in p.parts and 'execution' not in p.relative_to(root).parts}
        require(listed==actual,'Manifest file population mismatch')
        for f in md['files']:
            p=root/f['path']
            require(p.stat().st_size==f['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256'],'Manifest hash mismatch '+f['path'])
        manifest_count=len(listed)
    return {
        'kind':'HANDOFF_STRUCTURE_VALIDATION_ONLY','result':'PASSED',
        'counts':program['counts'],'task_graph':'ACYCLIC',
        'all_findings_and_baseline_rows_mapped':True,
        'baseline_rows_unchanged':True,'audit_hashes_unchanged':True,
        'prepublication_predicate':'NONCIRCULAR',
        'source_paths_checked':checked_source_paths if repo else 'not requested',
        'html':html_info,'manifest_files_checked':manifest_count,
        'initial_unexecuted_status_checks':initial,
        'product_runtime_or_release_qualification':False,
    }

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--repo',type=Path,help='Optional current source checkout for path-existence checks only')
    parser.add_argument('--initial-handoff',action='store_true',help='Verify initial PLANNED/NOT_RUN statuses and empty new evidence')
    args=parser.parse_args()
    try:
        result=validate(args.root.resolve(),args.repo.resolve() if args.repo else None,args.initial_handoff)
    except Exception as exc:
        print(json.dumps({'kind':'HANDOFF_STRUCTURE_VALIDATION_ONLY','result':'FAILED','error':str(exc)},indent=2))
        sys.exit(1)
    print(json.dumps(result,indent=2))

