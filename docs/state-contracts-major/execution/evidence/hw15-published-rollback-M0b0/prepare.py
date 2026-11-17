"""Read-only post-run evidence checks; never imports or reruns the characterization."""
import pathlib,json,hashlib,tarfile,collections,subprocess,shutil,datetime,ast
P=pathlib.Path(__file__).parent
T=pathlib.Path('C:/Users/brenn/AppData/Local/Temp')
A=T/'ca-hw15-actual-akezabox'
D=T/'ca-hw15-retained-rollback-2c0fd13010'
W=T/'ca-normal-M0b0-watch-2h4aggb0'
S='0b0ae193496335c0d87337e5993f032a9385fffb'
H=lambda b:hashlib.sha256(b).hexdigest()
def ref(path):
    path=pathlib.Path(path);b=path.read_bytes()
    return {'path':str(path),'bytes':len(b),'sha256':H(b)}
def load(path):return json.loads(pathlib.Path(path).read_bytes())
authority_path=W/'authenticated-M-package-inputs.json'
assert ref(authority_path)['sha256']=='3177c3c9bd5bd155777eeddb5d55b4b06392297085d576df579c862dc50d0b04'
auth=load(authority_path);result=load(A/'actual-result.json');supervised=load(A/'supervisor-result.json')
cfg_path=T/'ca-hw15-M0b0-root-input-oah5rd64/config.M.json';cfg=load(cfg_path)
assert result['status']==supervised['status']=='PASS' and result['tests_run']==1
assert result['failures']==result['errors']==result['skips']==0 and supervised['returncode']==0
assert supervised['stop_reason'] is None and supervised['containment']=='exited' and supervised['seconds']==19.359
assert supervised['driver_sha256']==ref(D/'characterization.py')['sha256']=='c3ae7032227549156235a3709825e908abf8d52efb0782f5cce63f6384189698'
assert supervised['config_sha256']==ref(cfg_path)['sha256']=='a71c7c7d22dff835e667d6a8edd730fc8e73f4b99520299ca37576f0b4926cdd'
assert supervised['package_authority']['sha256']==ref(authority_path)['sha256']
assert auth['source_commit']==cfg['trusted_source_commit']==S and auth['run_id']==cfg['trusted_workflow_run']=='43960617519'
assert auth['ci']=='SUCCESS' and auth['docs']=='FAILURE' and auth['whole_normal_verdict']=='BLOCK'
assert auth['package_verifier']=='PASS' and auth['require_production'] is True
assert pathlib.Path(cfg['cohort_path'])==pathlib.Path(auth['cohort'])
assert ref(cfg['cohort_path'])['sha256']==auth['cohort_sha256']
assert cfg['promotion_receipt_sha256']==auth['promotion_receipt_sha256']
assert pathlib.Path(cfg['release_package_stage'])==pathlib.Path(auth['promoted_stage'])
old=pathlib.Path(cfg['published_old_archive'])
assert ref(old)['sha256']=='df348d8926a6590346ab333abfefbeba88347dfdc665760d874e37c5f24c09ee'
published=load(D/'published-old/codearbiter-publication.json')
assert published['source_commit']=='3f1bd13762ed9f25320e58907f9bf98a81128504' and published['tag']=='ca-codex-v0.26.9'
assert published['package_sha256']==ref(old)['sha256']
foot=load(A/'controller-footprint.json')
assert foot['changed_observed_code_files']==[]
assert len(foot['installed_prefix_observations'])==1
prefixes=foot['installed_prefix_observations'][0]
assert prefixes['before']==prefixes['after'] and len(prefixes['before'])==4
joins=[];prefix_by_host={}
for host,prefix in [('claude','plugins/ca'),('codex','plugins/ca-codex'),('pi','package/plugins/ca-pi')]:
    expected={k.removeprefix(prefix+'/'):{'sha256':v['sha256'],'bytes':v['size']}
              for k,v in auth['verified_cohort']['packages'][host]['members'].items() if k.startswith(prefix+'/')}
    found=[k for k in prefixes['before'] if pathlib.Path(k).as_posix().endswith('/'+host+'/'+prefix)]
    assert len(found)==1
    actual=prefixes['before'][found[0]];assert actual==expected and prefixes['after'][found[0]]==expected
    prefix_by_host[host]=found[0]
    joins.append({'role':'M-'+host,'member_count':len(expected),'before_after_and_archive_bytes_equal':True,
                  'membership_sha256':H(json.dumps(expected,sort_keys=True,separators=(',',':')).encode())})
old_members={}
with tarfile.open(old,'r:gz') as archive:
    for m in archive.getmembers():
        if m.isfile() and m.name.startswith('plugins/ca-codex/'):
            b=archive.extractfile(m).read();name=m.name.removeprefix('plugins/ca-codex/')
            assert name not in old_members
            old_members[name]={'bytes':len(b),'sha256':H(b)}
old_prefix=[k for k in prefixes['before'] if '/published-old/' in pathlib.Path(k).as_posix()]
assert len(old_prefix)==1 and prefixes['before'][old_prefix[0]]==old_members
assert 'hooks/workflow-recovery.py' not in old_members
joins.append({'role':'published-codex-0.26.9','member_count':len(old_members),'before_after_and_archive_bytes_equal':True,
              'membership_sha256':H(json.dumps(old_members,sort_keys=True,separators=(',',':')).encode())})
expected_codex=prefixes['before'][prefix_by_host['codex']]
assert prefixes['codex_members_after_case']==expected_codex
assert '/fresh-M/' in pathlib.Path(prefixes['codex_prefix_after_case']).as_posix()
assert prefixes['codex_prefix_after_case']!=prefix_by_host['codex']
joins.append({'role':'fresh-M-codex','member_count':len(expected_codex),'original_M_and_fresh_extraction_bytes_equal':True,
              'membership_sha256':H(json.dumps(expected_codex,sort_keys=True,separators=(',',':')).encode())})
rows=[json.loads(line) for line in (A/'lifecycle-observations.jsonl').read_text().splitlines()]
assert len(rows)==20 and all(x['exit']==0 for x in rows)
assert [i for i,x in enumerate(rows) if x['phase']=='published-old-read']==[0,10]
assert all(rows[i]['before']==rows[i]['after'] for i in [0,10])
assert rows[0]['before'][0]=={}
actions=['register','register','register','get','get','claim','get','resume','compact',
         'get','get','get','register','register','register','reconcile','get','resume']
assert [x['action'] for x in rows if x['phase']=='current-package']==actions
ids=[rows[i]['response']['items'][0]['obligation_id'] for i in [1,2,3]]
assert len(set(ids))==3
assert rows[4]['response']['record']['state']=='pending'
assert rows[6]['response']['record']['state']=='claimed' and rows[8]['response']['record']['state']=='settled'
assert rows[8]['snapshot'][1]!=rows[7]['snapshot'][1]
assert rows[9]['response']['record']['state']=='settled' and len(rows[9]['response']['record']['history'])==1
history_before={k:v for k,v in rows[8]['snapshot'][0].items() if k.startswith('history/')}
assert history_before and all(rows[9]['snapshot'][0].get(k)==v for k,v in history_before.items())
assert rows[10]['before'][1]!=rows[9]['snapshot'][1]
assert rows[11]['response']['record']==rows[4]['response']['record']
assert rows[12]['response']['record']==rows[6]['response']['record']
assert rows[13]['response']['record']==rows[9]['response']['record']
assert rows[11]['snapshot']==rows[10]['after']
for i,oid in zip([14,15,16],ids):
    assert rows[i]['response']['items'][0]['obligation_id']==oid and rows[i]['response']['items'][0]['reused'] is True
    assert rows[i]['snapshot']==rows[i-1]['snapshot']
assert rows[17]['response']['status']=='absent-effect' and rows[17]['response']['record']['state']=='pending'
assert rows[17]['snapshot'][1]==rows[16]['snapshot'][1]
assert rows[19]['snapshot']==rows[18]['snapshot']
assert rows[19]['response']['record']==rows[9]['response']['record']
snapshots=[x.get('snapshot',x.get('before')) for x in rows]
assert len({x[2] for x in snapshots})==1
assert all(x[1]==snapshots[10][1] for x in snapshots[10:])
launches=foot['actual_child_launches']
counts=collections.Counter(pathlib.Path(x['executable']).name.lower() for x in launches)
assert counts=={'git.exe':7,'python.exe':20}
assert all(x['sha256']==(foot['python_sha256'] if pathlib.Path(x['executable']).name.lower()=='python.exe' else foot['git_sha256']) for x in launches)
py=[x for x in launches if pathlib.Path(x['executable']).name.lower()=='python.exe']
assert len(py)==len(rows)
for launch,row in zip(py,rows):
    argv=launch['argv'];assert argv[1]=='-B'
    if row['phase']=='published-old-read':
        assert argv[2]==str(pathlib.Path(old_prefix[0])/'hooks/work.py') and argv[3]=='list'
    else:
        assert argv[2].endswith('hooks\\workflow-recovery.py') and argv[3]==row['action']
assert foot['python_sha256']==ref('C:/Python314/python.exe')['sha256']
assert foot['git_sha256']==ref('C:/Program Files/Git/cmd/git.exe')['sha256']
declared=load(D/'source-inputs.json')['inputs'];source_joins={}
for path,item in declared.items():
    r=subprocess.run(['git','-C',str(cfg['controller_source_repo']),'show',S+':'+path],capture_output=True)
    assert r.returncode==0 and H(r.stdout)==item['source_sha256']
    source_joins[path]={'sha256':H(r.stdout),'bytes':len(r.stdout),'immutable_M_join':True}
setup=[]
for suffix,cause in [('wm5tvddw','supervisor Path(None) executable decoding'),('bnzh1t6s','supervisor unresolved Windows string argv executable')]:
    directory=T/('ca-hw15-actual-'+suffix);a=load(directory/'actual-result.json');s=load(directory/'supervisor-result.json')
    assert a['tests_run']==0 and a['errors']==1 and s['returncode']==1 and s['containment']=='exited'
    assert (directory/'lifecycle-observations.jsonl').stat().st_size==0
    setup.append({'classification':'SETUP_FAILURE_NOT_PRODUCT_RED','cause':cause,'test_cases':0,
        'original_outputs':{n:ref(directory/n) for n in ['actual-result.json','supervisor-result.json','stderr.log','stdout.log','lifecycle-observations.jsonl','controller-footprint.json']}})
originals={n:ref(A/n) for n in ['actual-result.json','supervisor-result.json','stderr.log','stdout.log','lifecycle-observations.jsonl','controller-footprint.json']}
proof={'schema':'hw15-scoped-lifecycle-evidence-proposal/1','recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'scope_verdict':'PASS','adoption':'PROPOSE_SCOPED_ACTUAL_CASE_ONLY','work_id':'WORK-2A68C3051D5A477EAC131493FF8A85AF','task':'HW-15',
    'test_id':'RetainedLifecycle.test_published_downgrade_and_fresh_reinstall_preserve_pending_state',
    'source_commit':S,'source_tree':auth['source_tree'],'ci_run_id':int(auth['run_id']),'whole_ci':'SUCCESS','whole_docs':'FAILURE','whole_normal_verdict':'BLOCK',
    'platform':'Windows','runtime':'C:/Python314/python.exe','runtime_sha256':foot['python_sha256'],'git_sha256':foot['git_sha256'],
    'actual_test_result':result,'supervisor_seconds':supervised['seconds'],'reported_test_seconds':19.002,
    'driver':ref(D/'characterization.py'),'final_inspected_supervisor':ref(T/'ca-run-hw15-retained-lifecycle.py'),'config':ref(cfg_path),
    'package_authority':ref(authority_path),'old_archive':ref(old),'old_publication':ref(D/'published-old/codearbiter-publication.json'),
    'original_outputs':originals,'prefix_membership_checks':joins,'original_helper_calls':20,'published_old_reads':2,'current_helper_calls':18,
    'effect_checks':{'old_reads_recovery_board_source_unchanged':True,'pending_claimed_compacted_records_survive_fresh_M':True,
        'three_origin_ids_reused_without_store_or_target_changes':True,'older_history_hashes_survive_compaction':True,
        'independent_board_edit_retained_through_old_read_fresh_M_reconcile_replay':True,'absent_effect_reconciliation_returns_claimed_to_pending_without_board_write':True,
        'settled_replay_changes_no_store_board_or_source_bytes':True,'fixture_source_hash_unchanged':True},
    'controller_footprint_summary':{'observed_code_read_files':len(foot['actual_controller_code_reads']),'observed_child_launches':len(launches),
        'executable_counts':dict(counts),'changed_observed_code_files':[],'raw_footprint_retained_by_reference':True},
    'source_input_joins':source_joins,'prior_setup_failures':setup,
    'proposal_refs':{'implementation[2]':'one older/no-ledger read and literal 0.26.9 downgrade preserve unresolved records and target in this fixture',
        'acceptance[2]':'one disposable installed-helper rollback/reinstall retaining pending state',
        'rollback[1]':'this case retains history and an independently edited target',
        'tests.required_cases[1]':'only local legacy-board settled replay/no duplicate local effect; external-effect clause untested'},
    'no_full_task_or_program_qualification':True,
    'limits':['One Windows/Python legacy-board case, Codex0.26.9 ->M0.30.0 ->0.26.9 ->fresh M0.30.0; all3 M prefixes byte-checked but Claude/Pi lifecycle not executed.',
        'No full interruption/concurrency/disk/notification/unknown-schema/capacity/TUI/consent/provider/model/native/SDK/multiplatform matrix or external-effect replay qualification.',
        'Controller audit records observed reads/processes only; it is not a complete child Python import or OS/DLL closure, as the raw footprint states.',
        'Prefix footprint carries membership/bytes, not modes; independent authenticated package verifier owns archive/member/mode provenance.',
        'Final supervisor source is inspected/hash-bound at packaging; prior supervisor versions were not separately retained and are not retroactively bound to it.',
        'PREPARED_NOT_EXECUTED author packet remains historical; these separately retained actual outputs are the new observation.',
        'Both zero-case attempts are supervisor setup defects, not product RED. No additional execution/download/API/canonical mutation during this inspection.']}
(P/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
selected=['actual-result.json','supervisor-result.json','stderr.log','stdout.log','lifecycle-observations.jsonl']
out=P/'original-small';out.mkdir()
for name in selected:shutil.copyfile(A/name,out/name)
for suffix in ['wm5tvddw','bnzh1t6s']:
    q=out/('setup-'+suffix);q.mkdir()
    for name in ['actual-result.json','supervisor-result.json','stderr.log','stdout.log','lifecycle-observations.jsonl']:
        shutil.copyfile(T/('ca-hw15-actual-'+suffix)/name,q/name)
for name,path in [('characterization.py',D/'characterization.py'),('supervisor.py',T/'ca-run-hw15-retained-lifecycle.py'),('config.M.json',cfg_path),('published-old-publication.json',D/'published-old/codearbiter-publication.json')]:
    shutil.copyfile(path,out/name)
print(json.dumps({'proof':str(P/'proof.json'),'sha256':H((P/'proof.json').read_bytes()),'scope_verdict':'PASS','prefix_members':[{'role':x['role'],'members':x['member_count']} for x in joins],'actual_calls':len(rows),'old_and_fresh_records_and_replay':'PASS','prior_setup_failures':len(setup)}))
