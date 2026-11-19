"""One bounded owned-child characterization. No product source modification."""
import pathlib,subprocess,hashlib,json,os,sys,time,threading,queue,datetime,stat
P=pathlib.Path(__file__).resolve().parent
NODE=pathlib.Path('D:/dev/Users/brenn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
EXPECTED_NODE='c0b01496cf3da5cceca86eb6e1b2ef5d088cd46ad4e97cf502e2c937fa7f56b9'
SOURCE=pathlib.Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter/plugins/ca-pi/tools/test/setup-disposable-home.ts')
EARLIER=pathlib.Path('C:/Users/brenn/AppData/Local/Temp/ca-hw26-original-caller-evidence-0ukr0fqv')
CAP=1048576;DEADLINE=5.0
H=lambda b:hashlib.sha256(b).hexdigest()
def write(name,value):
    with (P/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
def tree():
    out={}
    for path in sorted(P.rglob('*')):
        info=path.lstat();assert not path.is_symlink() and not getattr(info,'st_file_attributes',0)&1024
        name=path.relative_to(P).as_posix()
        out[name]={'kind':'directory'} if path.is_dir() else {'kind':'file','bytes':info.st_size,'sha256':H(path.read_bytes())}
    return out
def main():
    assert sys.version_info[:2]==(3,14)
    assert H(NODE.read_bytes())==EXPECTED_NODE
    expected=json.loads((EARLIER/'source-joins.json').read_text())['subjects']['plugins/ca-pi/tools/test/setup-disposable-home.ts']
    assert expected['byte_equal'] and H(SOURCE.read_bytes())==expected['current']['sha256']
    source_bytes=SOURCE.read_bytes();assert source_bytes==(EARLIER/'M-source/plugins/ca-pi/tools/test/setup-disposable-home.ts').read_bytes()
    (P/'source').mkdir();(P/'source/setup-disposable-home.ts').write_bytes(source_bytes)
    (P/'package.json').write_text('{"private":true,"type":"module"}\n')
    fake=P/'fake-operator-home';agent=fake/'.pi/agent';agent.mkdir(parents=True)
    sentinel=agent/'auth.json';sentinel.write_bytes(b'{"fixture":"owned-fake-operator-sentinel-not-a-credential"}\n')
    sentinel_hash=H(sentinel.read_bytes())
    temp=P/'tmp';temp.mkdir()
    safe={k:os.environ[k] for k in ['SystemRoot','WINDIR'] if k in os.environ}
    safe.update(HOME=str(fake),USERPROFILE=str(fake),PI_CODING_AGENT_DIR=str(agent),TEMP=str(temp),TMP=str(temp))
    argv=[str(NODE),'--experimental-strip-types',str(P/'child.mjs')]
    plan={'source_epoch':'ef63f8c306c8e47c111afec12a9d980d0e8927d6','source_sha256':H(source_bytes),
        'source_original':str(SOURCE),'source_copy':str(P/'source/setup-disposable-home.ts'),
        'node':str(NODE),'node_sha256':EXPECTED_NODE,'python':sys.executable,'python_version':sys.version,
        'python_sha256':H(pathlib.Path(sys.executable).read_bytes()),'child_sha256':H((P/'child.mjs').read_bytes()),
        'supervisor_sha256':H(pathlib.Path(__file__).read_bytes()),'argv':argv,'environment':safe,
        'outer_seconds':DEADLINE,'per_stream_cap':CAP,'case_count':1,'fixture_parent':str(P),
        'fake_operator_sentinel_sha256':sentinel_hash,'cleanup_requested':False}
    write('plan.json',plan)
    (P/'stdout.log').touch(exist_ok=False);(P/'stderr.log').touch(exist_ok=False)
    before=tree();write('tree-before.json',before)
    readiness=queue.Queue();overflow=threading.Event();sizes={'stdout':0,'stderr':0}
    process=None;ready=None;reason=None;kill_requested=False;exit_code=None;readers=[]
    start=time.monotonic()
    def drain(stream,name):
        pending=b''
        with (P/(name+'.log')).open('wb') as f:
            while True:
                chunk=os.read(stream.fileno(),8192)
                if not chunk:break
                keep=max(0,CAP-sizes[name]);accepted=chunk[:keep];sizes[name]+=len(accepted);f.write(accepted);f.flush()
                if len(accepted)<len(chunk):overflow.set()
                if name=='stdout':
                    pending+=accepted
                    while b'\n' in pending:
                        line,pending=pending.split(b'\n',1);readiness.put(line)
    status='SETUP_FAILURE'
    try:
        process=subprocess.Popen(argv,cwd=P,env=safe,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        readers=[threading.Thread(target=drain,args=(getattr(process,name),name),daemon=True) for name in ['stdout','stderr']]
        for t in readers:t.start()
        while time.monotonic()-start<DEADLINE-.5:
            if overflow.is_set():raise RuntimeError('output_cap')
            try:line=readiness.get(timeout=.02)
            except queue.Empty:
                if process.poll() is not None:raise RuntimeError('child_exited_before_ready')
                continue
            ready=json.loads(line)
            assert ready['phase']=='ready' and type(ready['pid']) is int and ready['pid']==process.pid
            assert ready['nodeVersion']=='v24.22.1' and ready['platform']=='win32'
            assert pathlib.Path(ready['executable']).resolve()==NODE.resolve() and ready['sourceSha256']==H(source_bytes)
            root=pathlib.Path(ready['createdRoot']).resolve(strict=True)
            assert root.parent==temp.resolve(strict=True) and root.name.startswith('ca-pi-operator-home-')
            assert pathlib.Path(ready['after']['HOME']).resolve()==root and pathlib.Path(ready['after']['USERPROFILE']).resolve()==root
            assert pathlib.Path(ready['after']['homedir']).resolve()==root
            assert ready['after']['HOMEDRIVE'] is None and ready['after']['HOMEPATH'] is None
            assert ready['childSpawns']==ready['networkCalls']==0
            assert process.poll() is None
            write('ready.json',ready)
            process.kill();kill_requested=True
            exit_code=process.wait(timeout=max(.01,DEADLINE-(time.monotonic()-start)))
            for t in readers:t.join(timeout=max(.01,DEADLINE-(time.monotonic()-start)))
            assert all(not t.is_alive() for t in readers) and not overflow.is_set()
            assert readiness.empty() and exit_code is not None
            after=tree();write('tree-after.json',after)
            assert H(sentinel.read_bytes())==sentinel_hash
            assert (P/'source/setup-disposable-home.ts').read_bytes()==source_bytes and SOURCE.read_bytes()==source_bytes
            actual_dirs=[x for x in temp.iterdir()];assert actual_dirs==[root]
            expected_relative={'.pi','.pi/agent','.pi/agent/auth.json'}
            assert {x.relative_to(root).as_posix() for x in root.rglob('*')}==expected_relative
            auth=root/'.pi/agent/auth.json';raw_auth=auth.read_bytes()
            assert H(raw_auth)==ready['dummyAuth']['sha256'] and len(raw_auth)==ready['dummyAuth']['bytes']
            assert json.loads(raw_auth)=={'openai':{'type':'api_key','key':'dummy-disposable-home-not-a-credential'}}
            assert not any(x['operation']=='rmSync' for x in ready['fsOperations'])
            for event in ready['fsOperations']:
                value=event.get('path',event.get('created',event.get('prefix')))
                assert pathlib.Path(value).resolve().is_relative_to(P)
                assert not (event['operation']=='readFileSync' and pathlib.Path(value).resolve()==sentinel.resolve())
            # Harness logs/receipts are explicit parent-owned changes. Setup may
            # change only its one TMP subtree; every original other file stays.
            for name,value in before.items():
                if value['kind']=='file' and name not in ['stdout.log','stderr.log']:
                    assert after[name]==value
            assert all(name.startswith('tmp/') or name in ['tree-before.json','ready.json'] for name in set(after)-set(before))
            assert time.monotonic()-start<DEADLINE
            status='PASS'
            break
        else:raise RuntimeError('outer_deadline')
    except Exception as error:
        reason={'class':type(error).__name__,'message':str(error)}
        if process is not None and process.poll() is None:
            process.kill();kill_requested=True
            try:exit_code=process.wait(timeout=max(.01,DEADLINE-(time.monotonic()-start)))
            except subprocess.TimeoutExpired:reason['containment']='UNCONFIRMED'
        elif process is not None:exit_code=process.returncode
        for t in readers:t.join(timeout=max(.01,DEADLINE-(time.monotonic()-start)))
    result={'schema':'hw26-owned-abrupt-exit-case/1','status':status,'case_count':1,'ready_observed':ready is not None,
        'owned_pid':process.pid if process else None,'kill_requested_on_owned_handle':kill_requested,
        'termination':'Python Popen.kill on owned Windows process handle','exit_code':exit_code,
        'kernel_wait_returned':process is not None and process.poll() is not None,'seconds':round(time.monotonic()-start,6),
        'deadline_seconds':DEADLINE,'captured_bytes':sizes,'reason':reason,
        'residue_preserved':True,'cleanup_attempted':False,'fake_operator_sentinel_unchanged':H(sentinel.read_bytes())==sentinel_hash,
        'plan_sha256':H((P/'plan.json').read_bytes()),'stdout_sha256':H((P/'stdout.log').read_bytes()),'stderr_sha256':H((P/'stderr.log').read_bytes()),
        'limits':['One Windows/Node24.22.1 actual setup-module hard-kill case, not M historical runtime or all-platform qualification.',
            'Actual setup/observer filesystem calls are confined/recorded and spawn/network entry points deny calls; no complete OS/DLL syscall trace claimed.',
            'No real operator auth store, Pi/provider/model, package install, dependency/global/canonical effects or benchmark replay.']}
    write('actual-result.json',result)
    print(json.dumps({'folder':str(P),'status':status,'seconds':result['seconds'],'actual_result_sha256':H((P/'actual-result.json').read_bytes()),'reason':reason}))
    return 0 if status=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
