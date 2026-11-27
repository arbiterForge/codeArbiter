"""Exact reversible metadata serialization; no producer/test is re-executed."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess

OUT=Path(__file__).resolve().parent
REPO=Path(r'C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
GIT=r'C:/Program Files/Git/cmd/git.exe'
SOURCE='edae1b98d8e9b783f71f43b031f862ca99a126c1'
P02=Path(r'C:/Users/brenn/AppData/Local/Temp/ca-P02-six-python-8d04')
C05=Path(r'C:/Users/brenn/AppData/Local/Temp/ca-C05-verdict-lossless-edae')
digest=lambda b:hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def encode(obj):return (json.dumps(obj,indent=2)+'\n').encode('utf-8')
def save(name,value):
    path=OUT/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(encode(value));return path
def git(*args):return subprocess.check_output([GIT,'--no-lazy-fetch',*args],cwd=REPO)
classification=Path(r'C:/Users/brenn/AppData/Local/Temp/ca-qualification-runtime-hash-classification-dze8k670/classification.json')
assert digest(classification.read_bytes())=='73632b567887a7d3422c01c1f7fbda770285a6ef7eeb603a09eaac5a22bccab4'
assert read(classification)['verdict']=='PASS'
assert digest((P02/'delivery.json').read_bytes())=='2e9a197b2ee1d56ee3a328c865139ec7c120e913399f021723f6c9739c5ee760'
assert digest((C05/'delivery.json').read_bytes())=='da49de01f7fcb24dcff17a779477daf6b656bbb7368ac4727e8146558a678ef5'
file_rows={}
for folder in [P02,C05]:
    for row in read(folder/'filemap.json')['files']:
        assert digest(Path(row['path']).read_bytes())==row['sha256']
        file_rows[row['repo_path']]=copy.deepcopy(row)
original_rows=copy.deepcopy(file_rows)
joins=[];runtime_pairs=None
for item in read(classification)['files']:
    name=item['path'];row=file_rows[name];raw=Path(row['path']).read_bytes()
    assert digest(raw)==item['sha256']==row['sha256']
    doc=json.loads(raw);assert encode(doc)==raw,'Original JSON serialization must reproduce bytes exactly'
    member=item['runtime_member'];mapping=doc[member]
    assert isinstance(mapping,dict) and len(mapping)==1905
    if runtime_pairs is None:runtime_pairs=mapping
    else:assert runtime_pairs==mapping
    transformed=copy.deepcopy(doc)
    transformed[member]=[{'path':path,'sha256':value} for path,value in mapping.items()]
    transformed['serialization_profile']={'format':'codearbiter-runtime-records-json/1','transformed_member':member,
        'original_document_sha256':digest(raw),'original_document_bytes':len(raw),
        'original_JSON_serialization':{'indent':2,'ensure_ascii':True,'final_newline':'LF'},
        'record_order':'Original object insertion order; converting records to dict in this order restores original bytes.'}
    path=save('new-files/'+name,transformed)
    restored=copy.deepcopy(transformed);restored.pop('serialization_profile')
    records=restored[member]
    assert all(set(record)=={'path','sha256'} for record in records)
    assert len({record['path'] for record in records})==1905
    restored[member]={record['path']:record['sha256'] for record in records}
    assert encode(restored)==raw and restored==doc
    file_rows[name]={'path':str(path),'repo_path':name,'sha256':digest(path.read_bytes()),'bytes':path.stat().st_size}
    joins.append({'repo_path':name,'expected_owned_WIP_sha256':digest(raw),'new_sha256':file_rows[name]['sha256'],
        'member':member,'records':1905,'exact_original_document_byte_restore':True,'all_other_fields_equal':True})
groups=[]
for folder in [P02,C05]:
    delivery=read(folder/'delivery.json')
    proof_path=Path(delivery['proof']['path'])
    proof_ref=next(name for name,row in original_rows.items() if row['path']==str(proof_path))
    proof=read(proof_path)
    for raw in proof['raw_evidence']:
        if raw.get('path') in file_rows and file_rows[raw['path']]['sha256']!=original_rows[raw['path']]['sha256']:
            assert raw['sha256']==original_rows[raw['path']]['sha256']
            raw['sha256']=file_rows[raw['path']]['sha256']
    new_proof=save('new-files/'+proof_ref,proof)
    file_rows[proof_ref]={'path':str(new_proof),'repo_path':proof_ref,'sha256':digest(new_proof.read_bytes()),'bytes':new_proof.stat().st_size}
    cas_path=Path(delivery['proposal']['path']);cas=read(cas_path)
    cas_ref=next(name for name,row in original_rows.items() if row['path']==str(cas_path))
    for row in cas['updates']:
        for evidence in row['proposed_row']['evidence']:
            assert evidence['ref']==proof_ref and evidence['sha256']==original_rows[proof_ref]['sha256']
            evidence['sha256']=file_rows[proof_ref]['sha256']
    new_cas=save('new-files/'+cas_ref,cas)
    file_rows[cas_ref]={'path':str(new_cas),'repo_path':cas_ref,'sha256':digest(new_cas.read_bytes()),'bytes':new_cas.stat().st_size}
    groups.append({'label':folder.name,'proof_ref':proof_ref,'cas_ref':cas_ref,
        'old_owner_auth_ref':next(name for name,row in original_rows.items() if row['path']==delivery['owner_authentication']['path'])})
ledger=json.loads(git('show',SOURCE+':docs/state-contracts-major/execution/coverage-ledger.json'))
updates=[]
for group in groups:
    cas=read(Path(file_rows[group['cas_ref']]['path']))
    for row in cas['updates']:
        before=ledger[row['table']][row['id']]
        canonical=json.dumps(before,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
        assert digest(canonical)==row['old_row_sha256'] and before==row['expected_before']
        updates.append(copy.deepcopy(row))
assert len(updates)==9
save('combined-nine-cas.json',{'schema':'codearbiter-disposition-cas/1','candidate':SOURCE,
    'ledger_path':'docs/state-contracts-major/execution/coverage-ledger.json',
    'row_hash_encoding':'SHA256 UTF8 json.dumps(row,sort_keys=True,separators=(comma,colon),ensure_ascii=False)',
    'updates':updates,'limits':'Original committed edae expected rows unchanged. Only proposed active proof hashes rebound; source epochs, assertions, commands and history unchanged.'})
save('transport-roundtrip.json',{'format':'codearbiter-runtime-records-transport-roundtrip/1','classification_ref':str(classification),
    'classification_sha256':digest(classification.read_bytes()),'four_documents':joins,'four1905maps_identical':True,
    'all_original_private_packets_unchanged':True,'tests_reexecuted':0,
    'profile':'Each runtime or runtime_after object becomes ordered path/sha256 records. Remove serialization_profile and restore object in record order, then original pretty JSON encoding returns exact original bytes.'})
save('pre-auth-state.json',{'groups':groups,'original_rows':original_rows,'file_rows':file_rows})
print(json.dumps({'state':'FOUR_BYTE_EXACT_ROUNDTRIPS_PASSED','documents':len(joins),'records_each':1905,
    'new_proof_hashes':{group['proof_ref']:file_rows[group['proof_ref']]['sha256'] for group in groups},'CAS_updates':len(updates)}))
