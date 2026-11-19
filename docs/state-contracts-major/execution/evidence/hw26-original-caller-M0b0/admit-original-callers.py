"""Use unchanged source-bound data admission; never runs the installed observer."""
import pathlib,sys,json,zipfile,subprocess,hashlib,importlib.util
P=pathlib.Path(__file__).parent
W=pathlib.Path('C:/Users/brenn/AppData/Local/Temp/ca-normal-M0b0-watch-2h4aggb0')
R=pathlib.Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
M='0b0ae193496335c0d87337e5993f032a9385fffb';C='ef63f8c306c8e47c111afec12a9d980d0e8927d6'
H=lambda b:hashlib.sha256(b).hexdigest()
subjects={}
for path in ['.github/scripts/pi_live_report_profile.py','.github/scripts/_pi_rpc_profile.py']:
    vals={}
    for rev in [M,C]:
        r=subprocess.run(['git','-C',str(R),'show',rev+':'+path],capture_output=True);assert r.returncode==0
        vals[rev]=H(r.stdout)
        if rev==M:(P/'M-source'/path).write_bytes(r.stdout)
    assert vals[M]==vals[C]
    subjects[path]={'M_sha256':vals[M],'current_sha256':vals[C],'byte_equal':True}
sys.dont_write_bytecode=True
sys.path.insert(0,str(W/'owner-source/.github/scripts'))
sys.path.insert(0,str(P/'M-source/.github/scripts'))
import pi_live_report_profile as profile
auth=json.loads((W/'authenticated-M-package-inputs.json').read_text())
payloads={x['name']:{'artifact_id':x['artifact_id'],'archive_sha256':x['sha256'],'members':x['members']} for x in auth['archives']}
req={'source_commit':M,'source_tree':auth['source_tree'],'ci_run_id':int(auth['run_id'])}
acquired=json.loads((P/'original-caller-acquisition.json').read_text())
out=[]
for obj in acquired['objects']:
    with zipfile.ZipFile(obj['archive_path']) as z:
        observation=json.loads(z.read('producer/observation.json'))
        acquisition=json.loads(z.read('producer/runtime-acquisition.json'))
        result=profile.admit(observation,req=req,job_id=obj['job_id'],authenticated_payloads=payloads,runtime_acquisition=acquisition,repo=R)
        original_test=json.loads(z.read('producer/original-test-result.json'))
        coordinator=json.loads(z.read('coordinator-complete.json'))
        cleanup=json.loads(z.read('producer/cleanup.json'))
    b=observation['installed_binding'];w=b['worker'];graph=acquisition['graph_after']['entries']
    runtime_root='node_modules/@earendil-works/pi-coding-agent/'
    package_entries={k:v for k,v in graph.items() if k==runtime_root+'package.json' or k.startswith(runtime_root+'dist/') and k.endswith(('cli.js','index.js'))}
    out.append({'system':obj['system'],'platform':b['platform'],'job_id':obj['job_id'],'artifact_id':obj['artifact_id'],
        'archive_sha256':obj['archive_sha256'],'profile':'pi-installed-rpc-v1','data_admission':'PASS','runtime_version':b['runtime_version'],
        'runtime_files':acquisition['runtime_before'],'reviewed_lock_sha256':acquisition['source_locks'],'runtime_graph_sha256':acquisition['graph_after']['sha256'],
        'runtime_graph_entry_count':len(graph),'runtime_package_members':package_entries,
        'fresh_prefix':acquisition['fresh_prefix'],'acquisition_success':acquisition['command']['returncode']==0,
        'runtime_source_graph_payload_installed_stable':all(w[k+'_before']==w[k+'_after'] for k in ['runtime','source','graph','payload','installed']),
        'original_test':original_test,'actual_routes':[x['name'] for x in w['routes']],
        'cleanup':cleanup,'doctor_boundary':{'last_line':w['doctor']['report'].splitlines()[-1],'no_parent_ui':'no-parent-ui' in w['doctor']['report']},
        'coordinator_complete':coordinator,'admitted_installed_cells':result['installed_cells'],
        'installed_package_sha256':auth['verified_cohort']['packages']['pi']['sha256'],
        'source_inputs_sha256':H(json.dumps(w['source_before'],sort_keys=True,separators=(',',':')).encode()),
        'proof_scope':'actual retained-package command discovery/alias/keyed-status/doctor isolation; no authored tool effects or user consent'})
q=P/'original-installed-caller-admission.json'
q.write_text(json.dumps({'schema':'hw26-original-installed-pi-caller-admission/1','source_commit':M,'current_source':C,
    'ci_run_id':req['ci_run_id'],'ci':'SUCCESS','docs':'FAILURE','whole_normal_verdict':'BLOCK',
    'owner':'pi_live_report_profile.admit + _pi_rpc_profile.admit','owner_subjects':subjects,'results':out,
    'limits':['No generic readiness record or basename fallback.','Exact source/package/lock/runtime/graph/member joins from original3successful installed owners.','No rerun/install/provider/auth-store/global effects; discovery/isolation does not imply PI-D07 authorship, parent TUI or consent.']},indent=2)+'\n')
print(json.dumps({'receipt':str(q),'sha256':H(q.read_bytes()),'callers':[{'system':x['system'],'platform':x['platform'],'admission':x['data_admission'],'runtime_version':x['runtime_version'],'graph_entries':x['runtime_graph_entry_count']} for x in out]}))
