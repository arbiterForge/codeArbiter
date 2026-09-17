#!/usr/bin/env python3
"""Install a verified native candidate into a descriptor-selected host.

No host is enabled by this packaging operation. A failed partial install is
unavailable; it is never a reason to fall back to PATH or enable HTML farm use.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

SCHEMA_VERSION = "0.3.1"
PROTOCOL = "codearbiter.artifact-api/0.1.0"


def read_regular(path: Path, limit: int) -> bytes:
    if path.is_symlink():
        raise ValueError(f"symlink source refused: {path}")
    with path.open('rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError(f"source must be a bounded regular file: {path}")
        data = stream.read(limit+1)
    if len(data) > limit:
        raise ValueError("source grew beyond its limit")
    return data


def _pairs(pairs):
    out={}
    for key,value in pairs:
        if key in out: raise ValueError("duplicate payload manifest key")
        out[key]=value
    return out


def _write_all(fd: int, data: bytes) -> None:
    view=memoryview(data)
    while view:
        written=os.write(fd,view)
        if written<=0:raise OSError('short payload write')
        view=view[written:]


def load_payload(source: Path):
    manifest_bytes = read_regular(source/'release.json', 65536)
    manifest = json.loads(manifest_bytes, object_pairs_hook=_pairs)
    if (not isinstance(manifest,dict)
            or set(manifest) != {'format','version','protocol','schema_version','binaries'}
            or manifest['format'] != 'codearbiter.artifact-release/0.1.0'
            or manifest['protocol'] != PROTOCOL or manifest['schema_version'] != SCHEMA_VERSION
            or not isinstance(manifest['version'],str)):
        raise ValueError('unsupported payload manifest')
    entries=manifest['binaries']
    if not isinstance(entries,dict) or not entries:
        raise ValueError('no native binary mapping')
    payload={}
    for key,entry in entries.items():
        if (key not in ('linux/amd64','linux/arm64','darwin/amd64','darwin/arm64','windows/amd64','windows/arm64') or not isinstance(entry,dict)
                or set(entry) != {'file','sha256','native_tested'}
                or entry['file'] != 'ca-artifact-'+key.replace('/','-')+('.exe' if key.startswith('windows/') else '')
                or entry['native_tested'] is not True):
            raise ValueError('unqualified platform entry')
        data=read_regular(source/entry['file'],32<<20)
        magic={'linux':(b'\x7fELF',),'darwin':(b'\xcf\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca'),'windows':(b'MZ',)}[key.split('/')[0]]
        if not data.startswith(magic) or hashlib.sha256(data).hexdigest()!=entry['sha256']:
            raise ValueError('payload bytes mismatch or unexpected native executable')
        payload[entry['file']]=data
    return manifest_bytes,payload


def install_payload(repo: Path, plugin_dir: str, source: Path) -> Path:
    # The normal caller obtains plugin_dir from validated canonical descriptors;
    # this check prevents an accidental or malformed descriptor escaping repo.
    if (not plugin_dir or plugin_dir.startswith('/') or '\\' in plugin_dir or ':' in plugin_dir
            or any(p in ('','.','..') for p in plugin_dir.split('/'))):
        raise ValueError('unsafe plugin path')
    if os.name == 'nt':
        raise ValueError('Windows payload installation is release-packaging only; the developer installer fails closed')
    manifest,payload=load_payload(source)
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
    current=os.open(repo,flags)
    target=repo
    try:
        parts=(plugin_dir+'/helpers/artifacts').split('/')
        for index,part in enumerate(parts):
            target=target/part
            final=index==len(parts)-1
            if final:
                try:os.mkdir(part,0o755,dir_fd=current)
                except FileExistsError as exc:
                    raise ValueError('payload exists; use a reviewed versioned upgrade, not overwrite') from exc
            else:
                try:next_fd=os.open(part,flags,dir_fd=current)
                except FileNotFoundError:
                    os.mkdir(part,0o755,dir_fd=current)
                    next_fd=os.open(part,flags,dir_fd=current)
                os.close(current);current=next_fd
        target_fd=os.open(parts[-1],flags,dir_fd=current)
        os.close(current);current=target_fd
        # Write the exact verified bytes relative to the pinned target handle.
        # The manifest is written last. No multi-file atomicity is asserted.
        for name,data in payload.items():
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o755,dir_fd=current)
            try:
                _write_all(fd,data);os.fsync(fd);os.fchmod(fd,0o755)
            finally:os.close(fd)
        fd=os.open('release.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=current)
        try:_write_all(fd,manifest);os.fsync(fd)
        finally:os.close(fd)
        os.fsync(current)
        return target
    finally:
        os.close(current)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True)
    parser.add_argument('--from-dir',type=Path,required=True)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(repo/'tools'))
    from host_descriptors import load_host_descriptors
    matches=[h for h in load_host_descriptors(str(repo)) if h.name==args.host]
    if len(matches)!=1:raise ValueError('host must resolve uniquely through existing descriptors')
    source=args.from_dir.resolve(strict=True)
    target=install_payload(repo,matches[0].plugin_dir,source)
    print(f'Copied verified candidate bytes to {target}. Native host, permission, farm and rollout gates remain required.')

if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as exc:raise SystemExit(str(exc))
