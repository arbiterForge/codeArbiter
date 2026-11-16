"""Post-run data sealing only. Does not execute or import the case again."""
import pathlib,json,hashlib,datetime
P=pathlib.Path(__file__).parent
H=lambda b:hashlib.sha256(b).hexdigest()
def ref(path):
    path=pathlib.Path(path);b=path.read_bytes();return {'path':str(path),'bytes':len(b),'sha256':H(b)}
result=json.loads((P/'actual-result.json').read_text());ready=json.loads((P/'ready.json').read_text());plan=json.loads((P/'plan.json').read_text())
assert result['status']=='PASS' and result['case_count']==1 and result['kernel_wait_returned'] and result['kill_requested_on_owned_handle']
assert result['owned_pid']==ready['pid']==64968 and result['exit_code']==1 and result['seconds']<5
assert result['captured_bytes']=={'stdout':3184,'stderr':0}
assert H((P/'supervisor.py').read_bytes())==plan['supervisor_sha256']
assert H((P/'child.mjs').read_bytes())==plan['child_sha256']
assert H(pathlib.Path(plan['node']).read_bytes())==plan['node_sha256']
assert H(pathlib.Path(plan['python']).read_bytes())==plan['python_sha256']
assert H(pathlib.Path(plan['source_original']).read_bytes())==plan['source_sha256']==ready['sourceSha256']
assert (P/'source/setup-disposable-home.ts').read_bytes()==pathlib.Path(plan['source_original']).read_bytes()
root=pathlib.Path(ready['createdRoot']);assert root.resolve(strict=True).parent==(P/'tmp').resolve(strict=True)
assert (root/'.pi/agent/auth.json').is_file() and H((root/'.pi/agent/auth.json').read_bytes())==ready['dummyAuth']['sha256']
assert H((P/'fake-operator-home/.pi/agent/auth.json').read_bytes())==plan['fake_operator_sentinel_sha256']
ctx=pathlib.Path('C:/Users/brenn/AppData/Local/Temp/ca-host-observer-integration-root')
out={'schema':'hw26-owned-abrupt-case-evidence/1','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'scope_verdict':'PASS','canonical_adoption':'PROPOSAL_ONLY','task':'HW-26','criterion':'tests.required_cases[3]',
    'source_epoch':plan['source_epoch'],'source_sha256':plan['source_sha256'],'source_copy_byte_equal':True,
    'platform':'Windows','node_version':ready['nodeVersion'],'node':{'path':plan['node'],'sha256':plan['node_sha256']},
    'python':{'path':plan['python'],'version':plan['python_version'],'sha256':plan['python_sha256']},
    'supervisor_sha256':plan['supervisor_sha256'],'child_observer_sha256':plan['child_sha256'],
    'actual_case':result,'readiness':ref(P/'ready.json'),'raw_stdout':ref(P/'stdout.log'),'raw_stderr':ref(P/'stderr.log'),
    'tree_before':ref(P/'tree-before.json'),'tree_after':ref(P/'tree-after.json'),'plan':ref(P/'plan.json'),
    'recorded_effects':{'owned_pid':ready['pid'],'held_handle_kill_and_wait_confirmed':True,'expected_windows_termination_exit':1,
        'home_and_homedir_redirected_before_dummy_read':True,'no_ambient_home_fallback':True,'setup_source_fs_calls_confined':True,
        'child_spawns':ready['childSpawns'],'network_calls':ready['networkCalls'],'exact_residual_root':str(root),
        'residual_relative_paths':['.pi','.pi/agent','.pi/agent/auth.json'],'dummy_auth_bytes':ready['dummyAuth']['bytes'],
        'dummy_auth_sha256':ready['dummyAuth']['sha256'],'fake_operator_sentinel_unchanged':True,'fake_operator_sentinel_read_by_child':False,
        'exit_cleanup_rm_calls_observed':0,'cleanup_attempted':False,'residue_retained':True},
    'context':{'packet_sha256':'c1b55de5aaad8fe184b65b75c584706f86fbaf34e1a441512881419ffcf9ba42',
        'full_input_and_delivery_consumed':True,'input':ref(ctx/'hw26-owned-abrupt-case-input.txt'),'typed_context':ref(ctx/'hw26-owned-abrupt-case-context.json')},
    'unchanged_prior_evidence':{'delivery':ref('C:/Users/brenn/AppData/Local/Temp/ca-hw26-original-caller-evidence-0ukr0fqv/delivery.json'),
        'scope':'Original benchmark,80unit fixtures and3installed callers remain separate; only Windows/Node24 abrupt-exit gap gains this actual observation.'},
    'limits':result['limits']+['Observed filesystem calls are the unchanged setup module and owned observer APIs, not a global OS/DLL syscall trace.',
        'No source/benchmark/provider/Pi/install/dependency/auth-user/global/canonical/main/publication effects or retries.',
        'Test supervisor/observer were authored by this actor; this is execution evidence, not independent approval of its harness.']}
q=P/'evidence-proposal.json';q.write_text(json.dumps(out,indent=2)+'\n')
files={}
for f in sorted(P.rglob('*')):
    if f.is_file() and f.name!='delivery.json':files[f.relative_to(P).as_posix()]={'bytes':f.stat().st_size,'sha256':H(f.read_bytes())}
d=P/'delivery.json';d.write_text(json.dumps({'schema':'hw26-owned-abrupt-case-delivery/1','scope_verdict':'PASS','case_count':1,
    'evidence_sha256':H(q.read_bytes()),'residue_preserved':True,'files':files},indent=2)+'\n')
print(json.dumps({'delivery':str(d),'sha256':H(d.read_bytes()),'evidence_sha256':H(q.read_bytes()),'files':len(files),'case_count':1,'status':'PASS'}))
