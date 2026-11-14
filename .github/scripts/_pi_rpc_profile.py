"""Closed Pi original-package RPC joins; no execution or string-only admission."""
import hashlib
import json
import re
from pathlib import PurePosixPath, PureWindowsPath

PROFILE="pi-installed-rpc-v1"
PRODUCER="pi-installed-rpc-observer-v1"
FORMAT="codearbiter.installed-observation-binding/1"
TEST_ID="python:.github/scripts/test_pi_package.py:test_pi_package.PiPackageTests.test_real_isolated_rpc_command_discovery_and_keyed_status"
DIGEST=re.compile(r"[0-9a-f]{64}")
SHA=re.compile(r"(?!0{40}$)[0-9a-f]{40}")
WORKFLOW=".github/workflows/ci.yml"

def require(value,message):
    if not value:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def closed(value,fields,label):
    require(isinstance(value,dict) and set(value)==set(fields.split()),"closed "+label+" differs")
def positive(value):return type(value) is int and value>0
def digest(value):return isinstance(value,str) and DIGEST.fullmatch(value)
def absolute(value):
    return isinstance(value,str) and len(value.encode())<=4096 and not any(ord(c)<32 for c in value) and (PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute())
def members(rows):
    require(isinstance(rows,list) and 0<len(rows)<=4096,"payload membership missing/unbounded")
    result={}
    for row in rows:
        closed(row,"path sha256","member")
        path=row['path'];p=PurePosixPath(path)
        require(isinstance(path,str) and str(p)==path and not p.is_absolute() and '..' not in p.parts and ':' not in path and '\\' not in path
                and path not in result and digest(row['sha256']),"unsafe/duplicate member")
        result[path]=row['sha256']
    return result
def completed(value):
    return isinstance(value,dict) and value.get('returncode')==0 and type(value.get('returncode')) is int and value.get('timed_out') is False and value.get('containment')=='exited'

def graph(value):
    closed(value,'entries sha256','host graph')
    rows=value['entries'];require(isinstance(rows,dict) and 0<len(rows)<=32768,'host graph population invalid')
    require(digest(value['sha256']) and sha(json.dumps(rows,sort_keys=True,separators=(',',':')).encode())==value['sha256'],'host graph digest differs')
    total=0
    for name,row in rows.items():
        path=PurePosixPath(name)
        require(isinstance(name,str) and str(path)==name and not path.is_absolute() and '..' not in path.parts and ':' not in name and '\\' not in name,'unsafe host graph path')
        if row.get('kind')=='file':
            closed(row,'kind bytes sha256','graph file')
            require(type(row['bytes']) is int and 0<=row['bytes']<=256*1024*1024 and digest(row['sha256']),'host graph file invalid');total+=row['bytes']
        else:
            closed(row,'kind target resolved sha256','graph link')
            target=PurePosixPath(row['resolved'])
            require(row['kind']=='bin-link' and '.bin' in path.parts and isinstance(row['target'],str) and 0<len(row['target'])<=4096 and not PurePosixPath(row['target']).is_absolute()
                    and str(target)==row['resolved'] and not target.is_absolute() and '..' not in target.parts and rows.get(row['resolved'],{}).get('kind')=='file'
                    and rows[row['resolved']]['sha256']==row['sha256'],'host graph link invalid')
    require(total<=1024*1024*1024,'host graph exceeds bound')

def _admit(o,*,req,job_id,authenticated_payloads,runtime_acquisition):
    closed(o,"format source_commit source_tree ci_run_id source_stable proof_kind producer argv exit_code tests installed_binding","observation")
    require(o['format']=='codearbiter.major-test-observation/1' and o['proof_kind']=='live-host' and o['producer']==PRODUCER
            and o['source_stable'] is True and type(o['exit_code']) is int and o['exit_code']==0,"not the qualified Pi RPC producer")
    b=o['installed_binding']
    closed(b,"format profile source_commit source_tree ci_run_id producer_job_id workflow platform runtime_version consumed_payloads cohort_json acquisition worker supervision cleanup","Pi binding")
    require(b['format']==FORMAT and b['profile']==PROFILE and b['workflow']==WORKFLOW,"unknown Pi profile")
    for key in ['source_commit','source_tree','ci_run_id']:
        require(b[key]==o[key]==req[key] and type(b[key]) is type(req[key]),"Pi source/run differs")
    require(SHA.fullmatch(b['source_commit']) and SHA.fullmatch(b['source_tree']) and positive(b['ci_run_id']) and positive(job_id)
            and type(b['producer_job_id']) is int and b['producer_job_id']==job_id,"Pi source/run/job invalid")
    require(b['platform'] in [s+'/'+a for s in ['windows','linux','darwin'] for a in ['amd64','arm64']] and b['runtime_version']=='1.5.0',"unsupported Pi runtime/platform")
    require(len(json.dumps(b).encode())<=16*1024*1024,"Pi binding exceeds bound")
    closed(b['consumed_payloads'],"release-packages promoted-stage","consumed roles")
    payloads=[];maps={}
    for role,prefix in [('release-packages','artifact-release-packages-'),('promoted-stage','artifact-host-payloads-')]:
        value=b['consumed_payloads'][role]
        closed(value,"artifact_name artifact_id archive_sha256 members","payload role")
        require(value['artifact_name']==prefix+b['source_commit'],"original Pi payload name differs")
        actual=authenticated_payloads.get(value['artifact_name'],{})
        projection={k:actual.get(k) for k in ['artifact_id','archive_sha256','members']}
        require({k:value[k] for k in projection}==projection and positive(value['artifact_id']) and digest(value['archive_sha256']),"authenticated Pi payload differs")
        maps[role]=members(value['members']);payloads.append(projection)
    require(payloads[0]['artifact_id']!=payloads[1]['artifact_id'],"Pi consumed roles alias one artifact")
    require(isinstance(b['cohort_json'],str) and len(b['cohort_json'].encode())<=8*1024*1024 and maps['release-packages'].get('artifact-package-cohort.json')==sha(b['cohort_json'].encode()),"Pi cohort is not authenticated")
    cohort=json.loads(b['cohort_json'])
    require(all(cohort.get(k)==b[k] for k in ['source_commit','source_tree']) and cohort.get('workflow')==WORKFLOW and cohort.get('run_id')==str(b['ci_run_id'])
            and cohort.get('pi_packer',{}).get('qualification')=='production' and maps['promoted-stage'].get('artifact-promotion.json')==cohort.get('promotion_receipt_sha256'),"Pi original production cohort differs")
    package=cohort['packages']['pi']
    require(maps['release-packages'].get(package['file'])==package['sha256'] and digest(package['sha256']) and isinstance(package['members'],dict) and package['members'],"Pi package archive missing")
    acq=b['acquisition']
    closed(acq,"format source_commit source_tree ci_run_id producer_job_id version prefix fresh_prefix source_locks command runtime_before runtime_after graph_after","acquisition")
    require(acq==runtime_acquisition and acq['format']=='codearbiter.pi-reviewed-acquisition/1' and acq['version']=='1.5.0' and absolute(acq['prefix']),"Pi acquisition owner differs")
    for key in ['source_commit','source_tree','ci_run_id','producer_job_id']:require(type(acq[key]) is type(b[key]) and acq[key]==b[key],"Pi acquisition identity differs")
    require(acq['fresh_prefix']=={'enumeration_succeeded':True,'present':False} and completed(acq['command']),"Pi acquisition was not fresh/successful")
    require(set(acq['source_locks'])=={'package.json','package-lock.json','.npmrc','review.json'} and all(digest(h) for h in acq['source_locks'].values()),"reviewed Pi lock identity absent")
    runtime=acq['runtime_before']
    require(runtime==acq['runtime_after'] and set(runtime)=={'python','node','git','npm_launcher','npm_cli','npm_node'},"Pi acquisition runtime changed")
    for value in runtime.values():
        closed(value,"path sha256","runtime file")
        require(absolute(value['path']) and digest(value['sha256']),"Pi runtime file invalid")
    graph(acq['graph_after'])
    argv=acq['command'].get('argv')
    require(isinstance(argv,list) and len(argv)==9 and argv[:3]==[runtime['python']['path'],'-I','-B'] and argv[3].replace('\\','/').endswith('/.github/scripts/pi_host_locks.py')
            and argv[4:]==['install','--version','1.5.0','--prefix',acq['prefix']],"not the existing fixed Pi installer")
    w=b['worker']
    closed(w,"format test routes doctor source_before source_after runtime_before runtime_after graph_before graph_after payload_before payload_after installed_before installed_after","worker")
    require(w['format']=='codearbiter.pi-installed-rpc-result/1' and w['test']=={'id':TEST_ID,'run_count':1,'failures':0,'errors':0,'skips':0,'result':'passed'},"original one Pi test did not pass")
    require(all(type(w['test'][key]) is int for key in ['run_count','failures','errors','skips']),'Pi original result counts must be actual integers')
    for field in ['source','runtime','graph','payload','installed']:
        require(isinstance(w[field+'_before'],dict) and w[field+'_before'] and w[field+'_before']==w[field+'_after'],"Pi "+field+" drift/unknown")
    require(w['runtime_before']==runtime and w['graph_before']==acq['graph_after'] and w['payload_before']==maps and w['installed_before']==package['members'],"Pi consumed/runtime/install join differs")
    require(w['source_before'].get('source_commit')==b['source_commit'] and w['source_before'].get('source_tree')==b['source_tree'] and w['source_before'].get('inputs'),"Pi source capture missing")
    require(all(w['source_before']['inputs'].get('.github/fixtures/pi-hosts/1.5.0/'+name)==value for name,value in acq['source_locks'].items()),'Pi acquisition lock/source join differs')
    require(isinstance(w['routes'],list) and [r.get('name') for r in w['routes']]==['bare','alias','doctor'],"original Pi route population differs")
    for route in w['routes']:
        closed(route,"name records settings","Pi route")
        require(isinstance(route['records'],list) and 0<len(route['records'])<=4096 and isinstance(route['settings'],dict)
                and isinstance(route['settings'].get('packages'),list) and len(route['settings']['packages'])==1,"Pi route settings/readback missing")
        rows=[r for r in route['records'] if r.get('id')=='commands']
        require(len(rows)==1 and rows[0].get('success') is True,"Pi command readback missing/duplicate/failed")
    doctor=w['doctor']
    closed(doctor,"format report","doctor")
    require(doctor['format']=='codearbiter-doctor-v1' and isinstance(doctor['report'],str) and doctor['report'].splitlines()[-1]=='doctor: DEGRADED'
            and 'DEGRADED  active-dispatch:' in doctor['report'] and 'no-parent-ui' in doctor['report'],"Pi doctor boundary overclaim")
    require(completed(b['supervision']) and b['cleanup']=={'complete':True},"Pi worker/cleanup not affirmative")
    argv=b['supervision'].get('argv')
    require(o['argv']==argv and isinstance(argv,list) and len(argv)==6 and argv[:3]==[runtime['python']['path'],'-I','-B']
            and argv[3].replace('\\','/').endswith('/.github/scripts/observe_pi_installed_rpc.py') and argv[4]=='--worker' and absolute(argv[5]),"not the fixed Pi worker command")
    tests=[{'id':TEST_ID,'result':'passed'}]
    require(o['tests']==tests,"Pi test names were invented/repeated")
    return {'tests':tests,'payload_artifact_ids':sorted(p['artifact_id'] for p in payloads),'payloads':payloads,
            'primary_payload_name':b['consumed_payloads']['release-packages']['artifact_name'],'installed_cells':['installed:pi:'+b['platform'].split('/')[0]+':1.5.0']}

def admit(observation,**kwargs):
    try:return _admit(observation,**kwargs)
    except (KeyError,TypeError,AttributeError,IndexError,UnicodeError) as error:raise ValueError('malformed Pi RPC observation') from error
