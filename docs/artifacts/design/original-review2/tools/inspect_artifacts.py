#!/usr/bin/env python3
"""Read-only reference validation and exact extraction. Not a Go/host implementation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from artifact_io import verified_load,records
from reference_validation import ready_errors,eligible

def check_pair(root:Path):
    out={};models={};parsers={}
    for kind in ('spec','plan'):
        m,text,parser=verified_load(root/f'{kind}.html',root)
        if m['kind']!=kind:raise ValueError('WRONG_KIND')
        if m['governance']['state']!='draft' or m['governance']['approvals']:raise ValueError('Reference delivery must remain unapproved drafts')
        models[kind]=m;parsers[kind]=parser
        out[kind]={'bytes':len(text.encode()),'symbols':len(records(m)),**m['integrity'],'draft':True,'schema_integrity_render':'pass'}
    spec,plan=models['spec'],models['plan']
    errors=ready_errors(spec)+ready_errors(plan,spec)
    if errors:raise ValueError('REFERENCE_CONTENT_GAPS: '+'; '.join(errors))
    if any(x['state']!='PENDING' or x['evidence_refs'] for x in plan['execution']['tasks'].values()):raise ValueError('Unearned reference task progress')
    if any(x!='not_satisfied' for x in plan['execution']['prerequisites'].values()):raise ValueError('Unearned prerequisites')
    checked=0
    for kind,parser in parsers.items():
        for href in parser.links:
            if href.startswith('https://'):continue
            if href.startswith('#'):
                if href[1:] not in parser.ids:raise ValueError('DANGLING_LINK: '+href)
            else:
                target,_,anchor=href.partition('#')
                other=target.removesuffix('.html')
                if other not in parsers or (anchor and anchor not in parsers[other].ids):raise ValueError('DANGLING_COMPANION_LINK: '+href)
            checked+=1
    criteria={x['id'] for x in spec['normative']['criteria']}
    targeted={r.split('#')[1] for t in plan['normative']['tasks'] if t['id']!='T-023' for r in t['criterion_refs']}
    if targeted!=criteria:raise ValueError('Missing targeted criterion coverage')
    out['pair']={'criteria':len(criteria),'tasks':len(plan['normative']['tasks']),'checkpoints':len(plan['normative']['checkpoints']),'targeted_criteria':len(targeted),'resolved_internal_links':checked,'dependency_graph':'acyclic with ordered checkpoint partition','spec_binding':'current normative draft hash','readiness':'structural/relationship/content-field checks passed; semantic correctness still requires review',**eligible(plan),'implementation_tests_run':False}
    return out

def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='action',required=True)
    v=sub.add_parser('verify');v.add_argument('directory',type=Path)
    o=sub.add_parser('outline');o.add_argument('artifact',type=Path);o.add_argument('--max-bytes',type=int,default=32768)
    r=sub.add_parser('read');r.add_argument('artifact',type=Path);r.add_argument('symbol');r.add_argument('--max-bytes',type=int,default=32768)
    args=ap.parse_args()
    try:
        if args.action=='verify':out=check_pair(args.directory)
        else:
            m,_,_=verified_load(args.artifact);idx=records(m)
            if args.action=='outline':out={'artifact_id':m['artifact_id'],'model_sha256':m['integrity']['model_sha256'],'context_complete':False,'symbols':[{'id':i,'title':r.get('title') or r.get('topic') or r.get('planned_target') or ''} for i,r in sorted(idx.items())]}
            else:
                if args.symbol not in idx:raise ValueError('NOT_FOUND')
                out={'artifact_id':m['artifact_id'],'model_sha256':m['integrity']['model_sha256'],'mode':'exact','context_complete':False,'execution_eligible':False,'record':idx[args.symbol]}
        raw=json.dumps(out,ensure_ascii=False,indent=2)+'\n'
        limit=getattr(args,'max_bytes',32768)
        if not 1<=limit<=32768 or len(raw.encode())>limit:raise ValueError('OUTPUT_TOO_LARGE: no partial record returned')
        print(raw,end='')
    except (ValueError,OSError,KeyError) as e:
        message=str(e).replace('\x1b','?')
        raise SystemExit(message[:2048]) from e
if __name__=='__main__':main()
