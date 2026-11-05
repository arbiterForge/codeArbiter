#!/usr/bin/env python3
# codeArbiter — optional absolute executable identities for shared Git helpers.
#
# Claude and Codex retain their historical bare-executable behavior when the
# variables are absent. The Pi bridge supplies validated absolute identities;
# every shared Git subprocess then consumes the same identity, and the managed
# Git hook carries it into the later hook process.
#
# Public API:
#   trusted_git_executable() -> str|None     validated CODEARBITER_GIT_EXECUTABLE, or
#                                             None if unset
#   trusted_python_executable() -> str|None  validated CODEARBITER_PYTHON_EXECUTABLE, or
#                                             None if unset
#   git_executable() -> str                  trusted_git_executable() or the bare "git"
#                                             fallback
#   git_read_error_summary(argv, failure_kind) -> str
#                                             credential-safe failure class and
#                                             executable local continuation
#   read_index_text(root, rel, max_bytes) -> str|None
#                                             exact stage-0 blob text, or None
#   read_head_blob_digest(root, rel) -> str|None bounded HEAD blob SHA-256, or None
#   staged_changes(root) -> dict[str,str]|None exact no-rename index delta

import hashlib
import json
import os
import re
import subprocess
import tempfile


GIT_ENV = "CODEARBITER_GIT_EXECUTABLE"
PYTHON_ENV = "CODEARBITER_PYTHON_EXECUTABLE"
MAX_SECURITY_BINARY_BYTES = 100_000_000
MAX_SECURITY_BINARY_FILES = 32
MAX_SECURITY_BINARY_TOTAL_BYTES = 200_000_000

_ROOT_OVERRIDE_ENV = frozenset({
    # `git rev-parse --local-env-vars` repository/object selectors.
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_OBJECT_DIRECTORY",
    "GIT_DIR", "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE",
    "GIT_GRAFT_FILE", "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS",
    "GIT_REPLACE_REF_BASE", "GIT_PREFIX", "GIT_SHALLOW_FILE",
    "GIT_COMMON_DIR",
    # Discovery indirection can also override an exact root-bound probe.
    "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM",
})


def root_bound_git_env(*, preserve_index=False):
    """Environment for selected Git to describe an explicit checkout root.

    Protected configuration such as safe.directory remains authoritative; only
    repository, object, and discovery selectors that override `-C` are removed.
    A real Git operation's hook may retain its active ``GIT_INDEX_FILE`` so the
    guard examines the index that operation will commit; ordinary read callers
    keep the default scrubbed behavior.
    """
    env = os.environ.copy()
    for name in _ROOT_OVERRIDE_ENV:
        if preserve_index and name == "GIT_INDEX_FILE":
            continue
        env.pop(name, None)
    return env


def _trusted_environment_path(name):
    value = os.environ.get(name)
    if not value:
        return None
    if not os.path.isabs(value):
        raise RuntimeError(f"{name} must be absolute")
    canonical = os.path.realpath(value)
    if not os.path.isfile(canonical):
        raise RuntimeError(f"{name} is unavailable")
    return canonical


def trusted_git_executable():
    return _trusted_environment_path(GIT_ENV)


def trusted_python_executable():
    return _trusted_environment_path(PYTHON_ENV)


def git_executable():
    return trusted_git_executable() or "git"


_GIT_READ_OPERATIONS = (
    "branch", "show-ref", "diff", "rev-parse", "status", "ls-files",
    "ls-tree", "cat-file", "hash-object",
)
_GIT_GLOBAL_OPTIONS_WITH_VALUES = frozenset({
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--super-prefix", "--config-env", "--exec-path",
})


def _git_read_operation(argv):
    """Return a fixed-literal Git subcommand, never an option value/pathspec."""
    arguments = tuple(str(value) for value in (argv or ()))
    index = 0
    if arguments and os.path.basename(arguments[0]).casefold() in ("git", "git.exe"):
        index = 1
    while index < len(arguments):
        value = arguments[index]
        if value == "--":
            break
        if value in _GIT_GLOBAL_OPTIONS_WITH_VALUES:
            index += 2
            continue
        if value.startswith("-"):
            index += 1
            continue
        for candidate in _GIT_READ_OPERATIONS:
            if value == candidate:
                return candidate
        break
    return "operation"


def git_read_error_summary(argv, failure_kind):
    """Return an actionable Git-read diagnostic from a fixed failure class.

    Git can include credential-bearing remote URLs and helper output in stderr.
    Callers must classify the process outcome without passing stderr or an
    exception message across this boundary. Select both output fields only from
    fixed literals; never interpolate argv values into a hook transcript or
    audit log. The local status probe is a safe, executable first diagnostic
    before retrying the refused operation.
    """
    operation = _git_read_operation(argv)
    failure = {
        "timeout": "timed out",
        "spawn": "could not start",
        "access": "was denied filesystem access",
        "output": "returned unreadable output",
        "exit": "exited unsuccessfully",
    }.get(failure_kind, "failed")
    if failure_kind == "spawn":
        continuation = ("Repair the Git executable, PATH, or "
                        "CODEARBITER_GIT_EXECUTABLE, then run `git status --short` "
                        "and retry the same operation.")
    elif failure_kind == "access":
        continuation = ("Repair filesystem access, then run `git status --short` "
                        "and retry the same operation.")
    else:
        continuation = ("Run `git status --short`, repair the Git access issue, "
                        "then retry the same operation.")
    return (f"`git {operation}` {failure}; stderr withheld to prevent credential "
            f"disclosure. {continuation}")


def _blob_sha256(root, oid, max_bytes, env):
    """Read one size-checked Git blob with a real process deadline."""
    try:
        size = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "cat-file", "-s", oid],
            capture_output=True, timeout=10, env=env,
        )
        blob_size = int(size.stdout.strip()) if size.returncode == 0 else -1
    except (OSError, subprocess.SubprocessError, TypeError, ValueError):
        return None
    if blob_size < 0 or blob_size > max_bytes:
        return None
    try:
        with tempfile.TemporaryFile() as blob:
            completed = subprocess.run(
                [git_executable(), "-C", os.fspath(root), "cat-file", "blob", oid],
                stdout=blob, stderr=subprocess.PIPE, timeout=10, env=env,
            )
            if completed.returncode != 0 or completed.stderr or blob.tell() != blob_size:
                return None
            blob.seek(0)
            digest = hashlib.sha256()
            while True:
                chunk = blob.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            return digest.hexdigest()
    except (OSError, subprocess.SubprocessError):
        return None


def read_index_blob_identity(root, rel, max_bytes=MAX_SECURITY_BINARY_BYTES,
                             *, preserve_index=False):
    """Return ``(mode, sha256(bytes))`` for one exact regular stage-0 blob."""
    if not isinstance(rel, str) or not rel or "\0" in rel:
        return None
    env = root_bound_git_env(preserve_index=preserve_index)
    try:
        requested = rel.encode("utf-8", "strict")
        indexed = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "--literal-pathspecs",
             "ls-files", "--stage", "-z", "--", rel],
            capture_output=True, timeout=10, env=env,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    records = [record for record in indexed.stdout.split(b"\0") if record]
    if indexed.returncode != 0 or len(records) != 1 or b"\t" not in records[0]:
        return None
    metadata, returned_path = records[0].split(b"\t", 1)
    fields = metadata.split()
    if (returned_path != requested or len(fields) != 3
            or fields[0] not in (b"100644", b"100755") or fields[2] != b"0"
            or re.fullmatch(rb"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", fields[1]) is None):
        return None
    digest = _blob_sha256(root, fields[1].decode("ascii"), max_bytes, env)
    return (fields[0].decode("ascii"), digest) if digest else None


def read_head_blob_identity(root, rel, max_bytes=MAX_SECURITY_BINARY_BYTES):
    """Return ``(mode, sha256(bytes))`` for one exact bounded HEAD blob."""
    if not isinstance(rel, str) or not rel or "\0" in rel:
        return None
    try:
        requested = rel.encode("utf-8", "strict")
        env = root_bound_git_env()
        result = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "--literal-pathspecs",
             "ls-tree", "-rz", "--full-tree", "HEAD", "--", rel],
            capture_output=True, timeout=10, env=env,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    records = [record for record in result.stdout.split(b"\0") if record]
    if result.returncode != 0 or len(records) != 1 or b"\t" not in records[0]:
        return None
    metadata, returned_path = records[0].split(b"\t", 1)
    fields = metadata.split()
    if (returned_path != requested or len(fields) != 3 or fields[1] != b"blob"
            or re.fullmatch(rb"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", fields[2]) is None):
        return None
    digest = _blob_sha256(root, fields[2].decode("ascii"), max_bytes, env)
    return (fields[0].decode("ascii"), digest) if digest else None


def _index_blob_inventory(root, paths, env):
    if not paths:
        return {}
    try:
        result = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "--literal-pathspecs",
             "ls-files", "--stage", "-z", "--", *paths],
            capture_output=True, timeout=10, env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    inventory = {}
    for record in (item for item in result.stdout.split(b"\0") if item):
        if b"\t" not in record:
            return None
        metadata, raw_path = record.split(b"\t", 1)
        fields = metadata.split()
        try:
            path = raw_path.decode("utf-8", "strict")
        except UnicodeError:
            return None
        if (path in inventory or len(fields) != 3
                or fields[0] not in (b"100644", b"100755") or fields[2] != b"0"
                or re.fullmatch(rb"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", fields[1]) is None):
            return None
        inventory[path] = (fields[0].decode("ascii"), fields[1].decode("ascii"))
    return inventory if result.returncode == 0 and set(inventory) == set(paths) else None


def _head_blob_inventory(root, paths, env):
    if not paths:
        return {}
    try:
        result = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "--literal-pathspecs",
             "ls-tree", "-rz", "--full-tree", "HEAD", "--", *paths],
            capture_output=True, timeout=10, env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    inventory = {}
    for record in (item for item in result.stdout.split(b"\0") if item):
        if b"\t" not in record:
            return None
        metadata, raw_path = record.split(b"\t", 1)
        fields = metadata.split()
        try:
            path = raw_path.decode("utf-8", "strict")
        except UnicodeError:
            return None
        if (path in inventory or len(fields) != 3 or fields[1] != b"blob"
                or fields[0] not in (b"100644", b"100755")
                or re.fullmatch(rb"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", fields[2]) is None):
            return None
        inventory[path] = (fields[0].decode("ascii"), fields[2].decode("ascii"))
    return inventory if result.returncode == 0 and set(inventory) == set(paths) else None


def _batch_blob_digests(root, oids, env):
    """Hash a bounded set of Git blobs with two processes and bounded memory."""
    unique = sorted(set(oids))
    if not unique or len(unique) > MAX_SECURITY_BINARY_FILES * 2:
        return None
    request = ("\n".join(unique) + "\n").encode("ascii")
    try:
        checked = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "cat-file",
             "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
            input=request, capture_output=True, timeout=10, env=env,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    rows = checked.stdout.splitlines()
    sizes = {}
    total = 0
    if checked.returncode != 0 or checked.stderr or len(rows) != len(unique):
        return None
    for expected, row in zip(unique, rows):
        fields = row.split()
        try:
            size = int(fields[2])
        except (IndexError, TypeError, ValueError):
            return None
        if (len(fields) != 3 or fields[0].decode("ascii").casefold() != expected.casefold()
                or fields[1] != b"blob" or size < 0 or size > MAX_SECURITY_BINARY_BYTES):
            return None
        total += size
        if total > MAX_SECURITY_BINARY_TOTAL_BYTES:
            return None
        sizes[expected.casefold()] = size
    try:
        with tempfile.TemporaryFile() as batch:
            completed = subprocess.run(
                [git_executable(), "-C", os.fspath(root), "cat-file", "--batch"],
                input=request, stdout=batch, stderr=subprocess.PIPE, timeout=30, env=env,
            )
            if completed.returncode != 0 or completed.stderr:
                return None
            batch.seek(0)
            digests = {}
            for expected in unique:
                header = batch.readline(256)
                fields = header.split()
                if len(fields) != 3:
                    return None
                try:
                    size = int(fields[2])
                    actual = fields[0].decode("ascii").casefold()
                except (UnicodeError, TypeError, ValueError):
                    return None
                if (actual != expected.casefold() or fields[1] != b"blob"
                        or size != sizes[expected.casefold()]):
                    return None
                remaining = size
                digest = hashlib.sha256()
                while remaining:
                    chunk = batch.read(min(1024 * 1024, remaining))
                    if not chunk:
                        return None
                    digest.update(chunk)
                    remaining -= len(chunk)
                if batch.read(1) != b"\n":
                    return None
                digests[expected.casefold()] = digest.hexdigest()
            if batch.read(1):
                return None
            return digests
    except (OSError, subprocess.SubprocessError):
        return None


def binary_candidate_binding(root, *, preserve_index=False):
    """Bind every staged binary path to exact modes and bounded blob bytes."""
    env = root_bound_git_env(preserve_index=preserve_index)
    try:
        result = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "diff", "--cached",
             "--numstat", "--no-renames", "-z", "--"],
            capture_output=True, timeout=10, env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    changes = staged_changes(root, preserve_index=preserve_index)
    if changes is None:
        return None
    binary_changes = []
    for record in (item for item in result.stdout.split(b"\0") if item):
        fields = record.split(b"\t", 2)
        if len(fields) != 3:
            return None
        added, deleted, raw_path = fields
        if (added, deleted) != (b"-", b"-"):
            continue
        try:
            path = raw_path.decode("utf-8", "strict")
        except UnicodeError:
            return None
        status = changes.get(path)
        if status not in ("A", "M", "D", "T"):
            return None
        binary_changes.append((path, status))
    if not binary_changes or len(binary_changes) > MAX_SECURITY_BINARY_FILES:
        return None
    index_paths = [path for path, status in binary_changes if status != "D"]
    head_paths = [path for path, status in binary_changes if status != "A"]
    indexed = _index_blob_inventory(root, index_paths, env)
    head = _head_blob_inventory(root, head_paths, env)
    if indexed is None or head is None:
        return None
    digests = _batch_blob_digests(
        root,
        [oid for _mode, oid in indexed.values()] + [oid for _mode, oid in head.values()],
        env,
    )
    if digests is None:
        return None
    entries = []
    for path, status in binary_changes:
        staged = None
        preimage = None
        if status != "D":
            mode, oid = indexed[path]
            staged = (mode, digests[oid.casefold()])
        if status != "A":
            mode, oid = head[path]
            preimage = (mode, digests[oid.casefold()])
        entries.append((path, status, staged, preimage))
    return "binary-candidate-v1:" + hashlib.sha256(json.dumps(
        sorted(entries), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8", "surrogatepass")).hexdigest()


def read_index_text(root, rel, max_bytes=1_000_000, *, preserve_index=False):
    """Read one exact stage-0 index blob as strict UTF-8.

    Resolve the object ID with ``ls-files --stage -z`` instead of interpolating
    the path into a revision expression. This keeps unusual path bytes out of
    Git's revision grammar and refuses conflicted or ambiguous index entries.
    """
    if not isinstance(rel, str) or not rel or "\0" in rel:
        return None
    env = root_bound_git_env(preserve_index=preserve_index)
    try:
        requested = rel.encode("utf-8", "strict")
        indexed = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "--literal-pathspecs",
             "ls-files", "--stage", "-z", "--", rel],
            capture_output=True, timeout=10, env=env,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    records = [record for record in indexed.stdout.split(b"\0") if record]
    if indexed.returncode != 0 or len(records) != 1 or b"\t" not in records[0]:
        return None
    metadata, returned_path = records[0].split(b"\t", 1)
    if returned_path != requested:
        return None
    fields = metadata.split()
    if (len(fields) != 3 or fields[0] not in (b"100644", b"100755")
            or fields[2] != b"0"
            or re.fullmatch(rb"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", fields[1]) is None):
        return None
    try:
        oid = fields[1].decode("ascii")
        size = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "cat-file", "-s", oid],
            capture_output=True, timeout=10, env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if size.returncode != 0:
        return None
    try:
        blob_size = int(size.stdout.strip())
    except (TypeError, ValueError):
        return None
    if blob_size < 0 or blob_size > max_bytes:
        return None
    try:
        blob = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "cat-file", "blob", oid],
            capture_output=True, timeout=10, env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if blob.returncode != 0 or len(blob.stdout) != blob_size:
        return None
    try:
        return blob.stdout.decode("utf-8", "strict")
    except UnicodeError:
        return None


def read_head_blob_digest(root, rel, max_bytes=1_000_000):
    """Return the SHA-256 digest of the exact bounded HEAD blob for ``rel``.

    ``ls-tree`` with literal pathspecs avoids revision/path interpolation and
    identifies the object to read. The Git object ID is only a lookup key; the
    review binding hashes the actual bounded bytes with approved SHA-256.
    """
    if not isinstance(rel, str) or not rel or "\0" in rel:
        return None
    try:
        requested = rel.encode("utf-8", "strict")
        env = root_bound_git_env()
        result = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "--literal-pathspecs",
             "ls-tree", "-rz", "--full-tree", "HEAD", "--", rel],
            capture_output=True, timeout=10, env=env,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    records = [record for record in result.stdout.split(b"\0") if record]
    if result.returncode != 0 or len(records) != 1 or b"\t" not in records[0]:
        return None
    metadata, returned_path = records[0].split(b"\t", 1)
    if returned_path != requested:
        return None
    fields = metadata.split()
    if (len(fields) != 3 or fields[1] != b"blob"
            or re.fullmatch(rb"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", fields[2]) is None):
        return None
    oid = fields[2].decode("ascii")
    try:
        size = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "cat-file", "-s", oid],
            capture_output=True, timeout=10, env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if size.returncode != 0:
        return None
    try:
        blob_size = int(size.stdout.strip())
    except (TypeError, ValueError):
        return None
    if blob_size < 0 or blob_size > max_bytes:
        return None
    try:
        blob = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "cat-file", "blob", oid],
            capture_output=True, timeout=10, env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if blob.returncode != 0 or len(blob.stdout) != blob_size:
        return None
    return hashlib.sha256(blob.stdout).hexdigest()


def staged_changes(root, *, preserve_index=False):
    """Return the exact stage delta as ``path -> status`` without rename folding."""
    try:
        result = subprocess.run(
            [git_executable(), "-C", os.fspath(root), "diff", "--cached",
             "--name-status", "--no-renames", "-z", "--"],
            capture_output=True, timeout=10,
            env=root_bound_git_env(preserve_index=preserve_index),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    fields = result.stdout.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        return None
    changes = {}
    for index in range(0, len(fields), 2):
        status_raw, path_raw = fields[index:index + 2]
        if status_raw not in (b"A", b"M", b"D", b"T"):
            return None
        try:
            path = path_raw.decode("utf-8", "strict")
        except UnicodeError:
            return None
        if not path or path in changes:
            return None
        changes[path] = status_raw.decode("ascii")
    return changes
