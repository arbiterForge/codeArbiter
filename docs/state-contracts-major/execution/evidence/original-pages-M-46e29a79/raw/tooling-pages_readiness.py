"""Admit original static Pages build data, separately from release readiness.

The caller selects trusted source/run/job/artifact identities and obtains original
records, logs and bytes with the existing GitHub API owner. This pure companion
checks those joins; it never acquires, extracts to disk, serves, executes or publishes.
It is not signed attestation against a cooperative caller able to forge inputs.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import io
import re
import tarfile
import zipfile

import major_readiness as owner

PAGES_ACTION = 'actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9'
# Exact nested action in the immutable outer action.yml, not an alternate direct policy.
NESTED_UPLOAD_ACTION = 'actions/upload-artifact@bbbca2ddaa5d8feaa63e36b76fdaad77386f024f'
JOB_NAME = 'Site | [Build] - Astro Pages'
UPLOAD_STEP = 'Upload Pages artifact'
MAX_LOG_BYTES = 32 * 1024 * 1024
MAX_ZIP_BYTES = owner.MAX_ARCHIVE
MAX_TAR_BYTES = 64 * 1024 * 1024  # existing members() per-file bound, unchanged
MAX_MEMBERS = 4096
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
_RESERVED = re.compile(r'(?i)(?:con|prn|aux|nul|conin\$|conout\$|com[1-9]|lpt[1-9])(?:\..*)?')


def _need(condition, message):
    owner.require(condition, message)


def _positive(value):
    return type(value) is int and 0 < value < 2**63


def _stamp(value):
    _need(isinstance(value, str), 'Pages timestamp missing')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    _need(parsed.tzinfo is not None and parsed.utcoffset() is not None,
          'Pages timestamp lacks timezone')
    return parsed


def _upload_attribution(job, artifact, job_log):
    _need(isinstance(job.get('steps'), list), 'Pages upload steps missing')
    steps = [step for step in job['steps']
             if isinstance(step, dict) and step.get('name') == UPLOAD_STEP]
    _need(len(steps) == 1 and steps[0].get('status') == 'completed'
          and steps[0].get('conclusion') == 'success', 'Pages upload step did not succeed exactly once')
    start = _stamp(steps[0].get('started_at'))
    end = _stamp(steps[0].get('completed_at'))
    created = _stamp(artifact.get('created_at'))
    _need(end >= start and start <= created <= end + timedelta(seconds=1),
          'Pages artifact outside upload window')
    _need(type(job_log) is bytes and 0 < len(job_log) <= MAX_LOG_BYTES,
          'Pages upload log exceeds bound or is missing')
    selected = []
    for line in job_log.decode('utf-8-sig').splitlines():
        stamp, _, message = line.partition(' ')
        if not stamp.endswith('Z'):
            continue
        observed = _stamp(stamp)
        if start <= observed <= end + timedelta(seconds=1):
            selected.append(message)
    for action in (PAGES_ACTION, NESTED_UPLOAD_ACTION):
        _need(selected.count('##[group]Run ' + action) == 1,
              'Pages outer/nested upload action attribution missing or ambiguous')
    expected = [
        'SHA256 digest of uploaded artifact is ' + artifact['digest'].removeprefix('sha256:'),
        f"Artifact github-pages successfully finalized. Artifact ID {artifact['id']}",
    ]
    _need(all(selected.count(line) == 1 for line in expected),
          'Pages original artifact ID/digest finalization missing or ambiguous')


def _path(name):
    # Explicit conservative Windows/POSIX shared profile for this static-data reader.
    # Unicode or ambiguous names remain unsupported, never guessed portable.
    _need(isinstance(name, str) and 0 < len(name) <= 512
          and all(32 <= ord(c) <= 126 for c in name)
          and not name.startswith('/') and '\\' not in name, 'unsafe or unsupported Pages path')
    if name.startswith('./'):
        name = name[2:]
    parts = name.split('/')
    _need(len(parts) <= 32 and all(part and part not in ('.', '..')
              and not any(c in '<>:"|?*' for c in part)
              and len(part) <= 255 and not part.endswith((' ', '.'))
              and not part.startswith(' ')
              and _RESERVED.fullmatch(part.split('.', 1)[0].rstrip(' ')) is None
              for part in parts),
          'unsafe or unsupported Pages path')
    return '/'.join(parts), parts


def _static_files(archive):
    # Keep the existing outer ZIP bounds/path/encryption/symlink policy intact.
    owner.members(archive)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        entries = zipped.infolist()
        _need(len(entries) == 1 and entries[0].filename == 'artifact.tar'
              and not entries[0].is_dir(), 'Pages ZIP must contain only artifact.tar')
        entry = entries[0]
        _need((entry.external_attr >> 16) & 0o170000 in (0, 0o100000)
              and not entry.external_attr & 0x400
              and entry.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
              'unsupported Pages ZIP member')
        _need(0 < entry.file_size <= MAX_TAR_BYTES, 'Pages tar exceeds bound')
        tar_bytes = zipped.read(entry)
    _need(len(tar_bytes) <= MAX_TAR_BYTES, 'Pages tar exceeds bound')
    files, headers, nodes = {}, set(), {}
    total = count = 0
    root_seen = False
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode='r:') as tar:
        for member in tar:
            count += 1
            _need(count <= MAX_MEMBERS, 'Pages tar member count exceeds bound')
            _need(member.type in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE)
                  and not member.linkname and not member.sparse and not member.pax_headers,
                  'unsupported Pages tar member type')
            is_dir = member.type == tarfile.DIRTYPE
            if member.name in ('.', './'):
                _need(is_dir and member.size == 0 and not root_seen, 'duplicate or invalid Pages root')
                root_seen = True
                continue
            name, parts = _path(member.name)
            key = name.lower()
            _need(key not in headers, 'duplicate or ambiguous Pages member')
            headers.add(key)
            for i in range(1, len(parts) + 1):
                literal = '/'.join(parts[:i])
                kind = 'directory' if i < len(parts) or is_dir else 'file'
                prior = nodes.get(literal.lower())
                _need(prior is None or prior == (literal, kind),
                      'Pages path alias or parent conflict')
                nodes[literal.lower()] = (literal, kind)
            if is_dir:
                _need(member.size == 0, 'Pages directory has data')
                continue
            _need(type(member.size) is int and 0 <= member.size <= MAX_FILE_BYTES,
                  'Pages file exceeds bound')
            total += member.size
            _need(total <= MAX_TOTAL_BYTES, 'Pages expansion exceeds bound')
            stream = tar.extractfile(member)
            _need(stream is not None, 'Pages member unreadable')
            value = stream.read(member.size + 1)
            _need(len(value) == member.size, 'Pages member truncated')
            files[name] = value
        offset = tar.offset
    _need(files and len(tar_bytes) - offset >= 1024 and not any(tar_bytes[offset:]),
          'Pages tar empty, incomplete or has unsupported trailing data')
    return files, owner.digest(tar_bytes)


def admit_pages_build(*, source, run_id, branch, job_id, artifact_id,
                     run, job, artifact, archive, job_log):
    """Validate caller-selected identities and return static bytes/provenance only.

    The trusted caller must obtain metadata/logs through the original API owner;
    a JSON file supplied by a third party is not authenticated by this pure call.
    Unsupported archives/metadata fail closed without extracting or executing.
    """
    try:
        _need(isinstance(source, str) and owner.SHA.fullmatch(source)
              and all(_positive(v) for v in (run_id, job_id, artifact_id))
              and branch in ('main', 'major/state-contracts'), 'invalid trusted Pages identities')
        _need(isinstance(run, dict) and isinstance(job, dict) and isinstance(artifact, dict),
              'Pages API records missing')
        repository = run.get('repository')
        head_repository = run.get('head_repository')
        _need(isinstance(repository, dict) and isinstance(head_repository, dict)
              and _positive(repository.get('id'))
              and _positive(head_repository.get('id'))
              and repository.get('full_name') == head_repository.get('full_name') == owner.REPOSITORY
              and head_repository.get('id') == repository['id'], 'foreign Pages repository')
        _need(type(run.get('id')) is int and run['id'] == run_id
              and run.get('head_sha') == source and run.get('head_branch') == branch
              and run.get('event') == 'push' and run.get('status') == 'completed'
              and run.get('conclusion') == 'success' and _positive(run.get('run_attempt'))
              and run.get('path') == '.github/workflows/docs.yml', 'Pages run is not trusted normal docs push')
        _need(type(job.get('id')) is int and job['id'] == job_id
              and type(job.get('run_id')) is int and job['run_id'] == run_id
              and type(job.get('run_attempt')) is int and job['run_attempt'] == run['run_attempt']
              and job.get('name') == JOB_NAME and job.get('status') == 'completed'
              and job.get('conclusion') == 'success', 'Pages build job identity differs')
        artifact_run = artifact.get('workflow_run')
        _need(isinstance(artifact_run, dict) and artifact.get('id') == artifact_id
              and _positive(artifact_run.get('id')) and artifact_run['id'] == run_id
              and _positive(artifact_run.get('repository_id'))
              and _positive(artifact_run.get('head_repository_id'))
              and artifact.get('name') == 'github-pages' and artifact_run.get('head_branch') == branch
              and artifact_run.get('repository_id') == repository['id']
              and artifact_run.get('head_repository_id') == repository['id'], 'Pages artifact identity differs')
        _need(type(archive) is bytes and 0 < len(archive) <= MAX_ZIP_BYTES,
              'Pages archive exceeds bound or is missing')
        archive_digest = owner.digest(archive)
        owner.validate_artifact(artifact, {'source_commit': source, 'ci_run_id': run_id}, archive_digest)
        _upload_attribution(job, artifact, job_log)
        files, tar_digest = _static_files(archive)
        return {'files': files, 'provenance': {
            'kind': 'original-static-pages-build', 'source_commit': source, 'run_id': run_id,
            'run_attempt': run['run_attempt'], 'branch': branch, 'repository': owner.REPOSITORY,
            'workflow': '.github/workflows/docs.yml', 'job_id': job_id, 'artifact_id': artifact_id,
            'archive_sha256': archive_digest, 'tar_sha256': tar_digest,
            'job_log_sha256': owner.digest(job_log), 'outer_action': PAGES_ACTION,
            'nested_action': NESTED_UPLOAD_ACTION,
            'members': [{'path': p, 'size': len(b), 'sha256': owner.digest(b)}
                        for p, b in sorted(files.items())],
        }}
    except owner.ReadinessError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, OSError, RuntimeError,
            zipfile.BadZipFile, tarfile.TarError):
        raise owner.ReadinessError('Pages build evidence malformed or unsupported') from None
