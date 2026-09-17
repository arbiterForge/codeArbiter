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
import re
import stat
import sys
from typing import NamedTuple

SCHEMA_VERSION = "0.3.1"
PROTOCOL = "codearbiter.artifact-api/0.1.0"
PROMOTION_FORMAT = "codearbiter.artifact-promotion/0.1.0"
NATIVE_TESTS = [
    'artifact-bridge', 'artifact-conformance', 'artifact-native', 'artifact-package',
    'go-test', 'go-vet',
]


class VerifiedPromotionPayload(NamedTuple):
    """Immutable bytes proven by one trusted promotion receipt."""
    receipt_bytes: bytes
    manifest_bytes: bytes
    payload: tuple[tuple[str, bytes], ...]

    @property
    def receipt(self) -> dict:
        # Return a fresh object so callers cannot mutate the verified snapshot.
        return json.loads(self.receipt_bytes, object_pairs_hook=_pairs)


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


def load_promotion_receipt(source: Path, receipt_path: Path, *, host: str,
                           source_commit: str, workflow: str, run_id: str,
                           receipt_sha256: str) -> VerifiedPromotionPayload:
    """Verify one staged host payload against its immutable promotion receipt."""
    receipt_source = receipt_path.absolute()
    if (receipt_source.is_symlink()
            or os.path.normcase(str(receipt_source.resolve(strict=True))) !=
            os.path.normcase(str(receipt_source))):
        raise ValueError('promotion receipt must be a real file without linked ancestors')
    receipt_bytes = read_regular(receipt_source, 65_536)
    if (not isinstance(receipt_sha256, str)
            or hashlib.sha256(receipt_bytes).hexdigest() != receipt_sha256):
        raise ValueError('promotion receipt bytes drifted from the trusted digest')
    receipt = json.loads(receipt_bytes, object_pairs_hook=_pairs)
    expected_keys = {
        'format', 'source_commit', 'workflow', 'run_id', 'version', 'protocol',
        'schema_version', 'hosts', 'qualifications', 'payload',
    }
    if (not isinstance(receipt, dict) or set(receipt) != expected_keys
            or receipt['format'] != PROMOTION_FORMAT
            or receipt['source_commit'] != source_commit
            or receipt['workflow'] != workflow or receipt['run_id'] != run_id):
        raise ValueError('promotion receipt does not match the trusted release context')
    hosts = receipt['hosts']
    if (not isinstance(hosts, dict) or host not in hosts or not isinstance(hosts[host], str)):
        raise ValueError('promotion receipt does not authorize this host payload')
    expected_source = receipt_source.parent.joinpath(*hosts[host].split('/')).absolute()
    actual_source = source.absolute()
    if (actual_source.is_symlink()
            or os.path.normcase(str(actual_source.resolve(strict=True))) !=
            os.path.normcase(str(actual_source))):
        raise ValueError('promotion receipt host payload must be a real directory')
    if (os.path.normcase(str(actual_source.resolve(strict=True))) !=
            os.path.normcase(str(expected_source.resolve(strict=True)))):
        raise ValueError('promotion receipt does not authorize this host payload')

    payload = receipt['payload']
    if (not isinstance(payload, dict) or 'release.json' not in payload
            or any(not isinstance(name, str) or not isinstance(value, str)
                   for name, value in payload.items())):
        raise ValueError('promotion receipt payload map is invalid')
    expected_files = set(payload)
    actual_files = {entry.name for entry in actual_source.iterdir()}
    if actual_files != expected_files or any(not entry.is_file() or entry.is_symlink()
                                             for entry in actual_source.iterdir()):
        raise ValueError('promotion receipt payload file set drifted')
    try:
        manifest_bytes, binaries = load_payload(actual_source)
    except ValueError as error:
        raise ValueError('promotion receipt payload bytes drifted') from error
    manifest = json.loads(manifest_bytes, object_pairs_hook=_pairs)
    if (receipt['version'], receipt['protocol'], receipt['schema_version']) != (
            manifest['version'], manifest['protocol'], manifest['schema_version']):
        raise ValueError('promotion receipt identity drifted from the payload manifest')
    if expected_files != {'release.json', *binaries}:
        raise ValueError('promotion receipt payload file set drifted')
    current = {
        'release.json': hashlib.sha256(manifest_bytes).hexdigest(),
        **{filename: hashlib.sha256(data).hexdigest()
           for filename, data in binaries.items()},
    }
    if current != payload:
        raise ValueError('promotion receipt payload bytes drifted')
    qualifications = receipt['qualifications']
    if (not isinstance(qualifications, dict)
            or set(qualifications) != set(manifest['binaries'])):
        raise ValueError('promotion receipt qualification set drifted')
    for platform_name, entry in manifest['binaries'].items():
        qualification = qualifications[platform_name]
        if (not isinstance(qualification, dict)
                or set(qualification) != {
                    'receipt_sha256', 'job', 'binary_sha256', 'native_tests'}
                or qualification['job'] != 'artifact-engine'
                or qualification['binary_sha256'] != entry['sha256']
                or not isinstance(qualification['receipt_sha256'], str)
                or re.fullmatch(r'[0-9a-f]{64}', qualification['receipt_sha256']) is None
                or qualification['native_tests'] != NATIVE_TESTS):
            raise ValueError('promotion receipt qualification binding is invalid')
    return VerifiedPromotionPayload(
        receipt_bytes=receipt_bytes,
        manifest_bytes=manifest_bytes,
        payload=tuple(sorted(binaries.items())),
    )


def _install_payload_bytes(repo: Path, plugin_dir: str, manifest: bytes,
                           payload: dict[str, bytes]) -> Path:
    # The normal caller obtains plugin_dir from validated canonical descriptors;
    # this check prevents an accidental or malformed descriptor escaping repo.
    if (not plugin_dir or plugin_dir.startswith('/') or '\\' in plugin_dir or ':' in plugin_dir
            or any(p in ('','.','..') for p in plugin_dir.split('/'))):
        raise ValueError('unsafe plugin path')
    if os.name == 'nt':
        raise ValueError('Windows payload installation is release-packaging only; the developer installer fails closed')
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


def install_payload(repo: Path, plugin_dir: str, source: Path) -> Path:
    """Install an ordinary verified payload without promotion provenance."""
    if os.name == 'nt':
        raise ValueError('Windows payload installation is release-packaging only; the developer installer fails closed')
    manifest, payload = load_payload(source)
    return _install_payload_bytes(repo, plugin_dir, manifest, payload)


def install_promoted_payload(repo: Path, plugin_dir: str, source: Path,
                             receipt_path: Path, *, host: str, source_commit: str,
                             workflow: str, run_id: str, receipt_sha256: str) -> Path:
    """Verify and consume one immutable promotion snapshot without reopening source."""
    verified = load_promotion_receipt(
        source, receipt_path, host=host, source_commit=source_commit,
        workflow=workflow, run_id=run_id, receipt_sha256=receipt_sha256)
    return _install_payload_bytes(
        repo, plugin_dir, verified.manifest_bytes, dict(verified.payload))


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
