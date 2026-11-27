"""Closed existing-version Linux runtime acquisition. Never executes a binary.

The immutable repository pin file, reviewed independently from observations,
binds both npm wrapper and platform package archives. Reuse only the existing
approved HTTPS/SHA512 byte transport; Pi's256MiB admission remains unchanged.
"""
import base64
import hashlib
import hmac
import io
import json
import os
from pathlib import Path,PurePosixPath
import platform
import stat
import tarfile
import tempfile
import time

VERSIONS=('0.143.0','0.145.0')
MAX_MEMBER_BYTES=512*1024*1024
MAX_ARCHIVE_BYTES=256*1024*1024
PIN_PATH='.github/fixtures/codex-host-runtime-linux.json'
BINARY='package/vendor/x86_64-unknown-linux-musl/bin/codex'
def require(value,message):
    if not value:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def unique(pairs):
    d={}
    for k,v in pairs:require(k not in d,'duplicate JSON field');d[k]=v
    return d
def reviewed_pins(repo,source):
    from major_readiness import blob
    raw=blob(repo,source,PIN_PATH)
    require(len(raw)<=1024*1024,'runtime pin file exceeds bound')
    d=json.loads(raw,object_pairs_hook=unique)
    require(d.get('schema')=='codearbiter.codex-linux-runtime-pins/1' and d.get('registry')=='https://registry.npmjs.org'
            and d.get('platform')=='linux/amd64' and set(d.get('versions',{}))==set(VERSIONS),'closed runtime pin population differs')
    return d
def policy_for(pins,version):
    require(version in VERSIONS,'unsupported Codex version')
    row=pins['versions'][version]['linux_amd64'];items={x['path']:x for x in row['members']}
    require(row['package']=='@openai/codex' and row['version']==version+'-linux-x64' and BINARY in items,
            'Linux runtime package identity differs')
    return {version:{'platform':'linux/amd64','executable_sha256':items[BINARY]['sha256'],
                     'provenance':'npm:@openai/codex@'+row['version'],'integrity':row['integrity']}}
def verify_archive(raw,pin):
    require(isinstance(raw,bytes) and len(raw)==pin['archive_bytes']<=MAX_ARCHIVE_BYTES,'runtime archive size differs')
    require(sha(raw)==pin['archive_sha256'],'runtime archive SHA256 differs')
    sri=pin.get('integrity','');require(isinstance(sri,str) and sri.startswith('sha512-'),'runtime SRI missing')
    try:expected=base64.b64decode(sri[7:],validate=True)
    except ValueError:raise ValueError('runtime SRI malformed') from None
    require(len(expected)==64 and hmac.compare_digest(hashlib.sha512(raw).digest(),expected),'runtime SRI differs')
    rows=pin['members'];require(isinstance(rows,list) and 0<len(rows)<=16,'bounded exact runtime members required')
    wanted={x['path']:x for x in rows};require(len(wanted)==len(rows),'duplicate pinned runtime path')
    seen=set();total=0;manifest=None;binary_hash=None
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r|gz') as tar:
        for n,item in enumerate(tar):
            require(n<16 and item.isfile() and not item.issparse() and not item.issym() and not item.islnk(),
                    'runtime archive link/special/member limit')
            path=PurePosixPath(item.name)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in item.name
                    and ':' not in item.name and path.as_posix()==item.name and item.name.startswith('package/'),
                    'unsafe runtime member path')
            require(item.name not in seen and item.name in wanted,'extra/duplicate runtime member')
            expected_item=wanted[item.name];seen.add(item.name);total+=item.size
            require(0<=item.size<=MAX_MEMBER_BYTES and total<=MAX_MEMBER_BYTES,'runtime uncompressed/member limit')
            require(item.size==expected_item['size'] and item.mode==int(expected_item['mode'],8),'runtime member size/mode differs')
            stream=tar.extractfile(item);require(stream is not None,'runtime member unreadable')
            value=hashlib.sha256();count=0;prefix=b'';small=[]
            while chunk:=stream.read(65536):
                if not prefix:prefix=chunk[:64]
                count+=len(chunk);require(count<=item.size,'runtime member exceeds declaration');value.update(chunk)
                if item.size<=65536:small.append(chunk)
            require(count==item.size and value.hexdigest()==expected_item['sha256'],'runtime member bytes differ')
            if item.name=='package/package.json':manifest=json.loads(b''.join(small),object_pairs_hook=unique)
            if item.name==BINARY:
                require(prefix[:7]==b'\x7fELF\x02\x01\x01' and int.from_bytes(prefix[18:20],'little')==62,
                        'runtime is not Linux x86_64 ELF')
                binary_hash=value.hexdigest()
    require(seen==set(wanted),'missing runtime member')
    require(isinstance(manifest,dict) and manifest.get('name')==pin['package'] and manifest.get('version')==pin['version']
            and manifest.get('license')=='Apache-2.0','runtime package manifest identity/license differs')
    return {'binary_sha256':binary_hash,'manifest':manifest,'members':wanted}
def _new_parent(path):
    path=Path(path).absolute()
    require(path.resolve(strict=True)==path,'runtime output parent is linked or nonliteral')
    for part in [path,*path.parents]:
        info=part.lstat();require(stat.S_ISDIR(info.st_mode) and not part.is_symlink()
             and not getattr(info,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT,'runtime output parent is linked')
    return path
def acquire(repo,source,version,parent):
    require(version in VERSIONS,'unsupported Codex version')
    require(platform.system()=='Linux' and platform.machine().lower() in ('x86_64','amd64'),'closed Linux amd64 runtime profile only')
    from pi_host_locks import _download_registry_archive_bytes
    pins=reviewed_pins(repo,source);row=pins['versions'][version];policy=policy_for(pins,version)
    parent=_new_parent(parent);target=Path(tempfile.mkdtemp(prefix='codex-runtime-'+version+'-',dir=parent))
    root_manifest=None;native=None;records=[]
    for role in ('root','linux_amd64'):
        pin=row[role]
        require(pin['url']=='https://registry.npmjs.org/@openai/codex/-/codex-'+pin['version']+'.tgz','unapproved runtime URL')
        archive=target/(role+'.tgz')
        _download_registry_archive_bytes(pin['url'],pin['integrity'],archive,deadline=time.monotonic()+180,byte_budget=MAX_ARCHIVE_BYTES)
        raw=archive.read_bytes();verified=verify_archive(raw,pin)
        records.append({'role':role,'archive_sha256':sha(raw),'integrity':pin['integrity'],'archive_bytes':len(raw)})
        if role=='root':root_manifest=verified['manifest']
        else:
            native=verified
            # Closed exact members were fully verified before any extraction.
            with tarfile.open(fileobj=io.BytesIO(raw),mode='r|gz') as tar:
                for item in tar:
                    destination=target.joinpath(*PurePosixPath(item.name).parts)
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    with destination.open('xb') as stream:
                        source_stream=tar.extractfile(item)
                        while chunk:=source_stream.read(65536):stream.write(chunk)
                        stream.flush();os.fsync(stream.fileno())
                    destination.chmod(item.mode)
    require(root_manifest.get('version')==version and root_manifest.get('optionalDependencies',{}).get('@openai/codex-linux-x64')
            =='npm:@openai/codex@'+version+'-linux-x64','wrapper native alias differs')
    require(native['binary_sha256']==policy[version]['executable_sha256'],'runtime policy native join differs')
    raw=(json.dumps(policy,indent=2)+'\n').encode();policy_path=target/'runtime-policy.json'
    with policy_path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    receipt={'schema':'codearbiter.codex-runtime-acquisition/1','source_commit':source,'version':version,'platform':'linux/amd64',
             'archives':records,'binary_sha256':native['binary_sha256'],'runtime_policy_sha256':sha(raw),
             'scope':'SRI/pinned archive/native acquisition only; executable has not been launched; no installed qualification'}
    with (target/'acquisition.json').open('x',encoding='utf8') as f:json.dump(receipt,f,indent=2);f.flush();os.fsync(f.fileno())
    return {'runtime_executable':target.joinpath(*PurePosixPath(BINARY).parts),'runtime_policy':policy_path,
            'trusted_runtime_policy_sha256':sha(raw),'acquisition_receipt':target/'acquisition.json'}
