"""Canonical, cooperatively locked planning-file CAS publication."""

from __future__ import annotations

import contextlib
import ctypes
import hashlib
import os
import re
import secrets
import stat
import tempfile
import time

MAX_CONTENT_BYTES = 92_160
LOCK_WAIT_SECONDS = 2.0
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$")
HASH_RE = re.compile(r"^[a-f0-9]{64}$")
KINDS = {"spec": "specs", "plan": "plans"}
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_WINDOWS_PARENT_HANDLES = {}


class PlanFileError(RuntimeError):
    pass


def _is_reparse(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE)


def _identity(info):
    return info.st_dev, info.st_ino


def _version(info):
    return (_identity(info), info.st_size, getattr(info, "st_mtime_ns", 0),
            getattr(info, "st_ctime_ns", 0), info.st_nlink, info.st_mode)


def _regular_single(info):
    return stat.S_ISREG(info.st_mode) and not _is_reparse(info) and info.st_nlink == 1


def _directory(info):
    return stat.S_ISDIR(info.st_mode) and not _is_reparse(info)


def _aliases(directory, name):
    names = os.listdir(directory)
    return [item for item in names if item.casefold() == name.casefold()]


def _exact_absolute_child(parent, name):
    if _aliases(parent, name) != [name]:
        raise PlanFileError("path_alias")
    path = os.path.join(parent, name)
    info = os.lstat(path)
    if not _directory(info) or os.path.realpath(path) != os.path.abspath(path):
        raise PlanFileError("path_type")
    return path, info


def _request_path(root, slug, kind):
    if not isinstance(root, str) or not os.path.isabs(root) \
            or os.path.realpath(root) != os.path.abspath(root):
        raise PlanFileError("root")
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug) or kind not in KINDS:
        raise PlanFileError("request")
    return os.path.join(root, ".codearbiter", KINDS[kind], f"{slug}.md")


def _windows_handle_identity(handle):
    from ctypes import wintypes

    class ByHandleInfo(ctypes.Structure):
        _fields_ = [
            ("FileAttributes", wintypes.DWORD), ("CreationTime", wintypes.FILETIME),
            ("LastAccessTime", wintypes.FILETIME), ("LastWriteTime", wintypes.FILETIME),
            ("VolumeSerialNumber", wintypes.DWORD), ("FileSizeHigh", wintypes.DWORD),
            ("FileSizeLow", wintypes.DWORD), ("NumberOfLinks", wintypes.DWORD),
            ("FileIndexHigh", wintypes.DWORD), ("FileIndexLow", wintypes.DWORD),
        ]

    info = ByHandleInfo()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
        raise PlanFileError("ancestor_handle")
    return (info.VolumeSerialNumber, (info.FileIndexHigh << 32) | info.FileIndexLow,
            info.FileAttributes)


def _windows_open_directory(path, deny_delete):
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel32.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    sharing = 0x00000001 | 0x00000002
    if not deny_delete:
        sharing |= 0x00000004
    handle = create(path, 0x0080 | 0x00100000, sharing, None, 3,
                    0x02000000 | 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise PlanFileError("ancestor_handle")
    return handle


def _windows_close(handle):
    ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)


def _windows_snapshot(path):
    handle = _windows_open_directory(path, False)
    try:
        return _windows_handle_identity(handle)
    finally:
        _windows_close(handle)


def _validated_windows_path(root, slug, kind):
    target = _request_path(root, slug, kind)
    root_info = os.lstat(root)
    if not _directory(root_info):
        raise PlanFileError("root")
    state_path, state_info = _exact_absolute_child(root, ".codearbiter")
    parent_path, parent_info = _exact_absolute_child(state_path, KINDS[kind])
    leaf = f"{slug}.md"
    aliases = _aliases(parent_path, leaf)
    if aliases not in ([], [leaf]):
        raise PlanFileError("path_alias")
    paths = (root, state_path, parent_path)
    infos = (root_info, state_info, parent_info)
    snapshots = tuple(_windows_snapshot(item) for item in paths)
    for info, snapshot in zip(infos, snapshots):
        if info.st_ino != snapshot[1] or snapshot[2] & _REPARSE or not snapshot[2] & 0x10:
            raise PlanFileError("ancestor_identity")
    return {"root": root, "state": state_path, "parent": parent_path, "target": target,
            "leaf": leaf, "kind": kind, "identities": snapshots, "parent_fd": None}


def _open_posix_directory(name, parent_fd=None, expected=None):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(name, flags, dir_fd=parent_fd)
    opened = os.fstat(fd)
    if not _directory(opened) or expected is not None and _identity(opened) != _identity(expected):
        os.close(fd)
        raise PlanFileError("ancestor_identity")
    return fd, opened


def _exact_fd_child(parent_fd, name):
    if _aliases(parent_fd, name) != [name]:
        raise PlanFileError("path_alias")
    info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not _directory(info):
        raise PlanFileError("path_type")
    fd, opened = _open_posix_directory(name, parent_fd, info)
    return fd, opened


@contextlib.contextmanager
def _held_path(root, slug, kind, fault=None):
    if os.name == "nt":
        path = _validated_windows_path(root, slug, kind)
        if fault:
            fault("after_validate", path)
        handles = []
        try:
            for directory, expected in zip((path["root"], path["state"], path["parent"]),
                                           path["identities"]):
                handle = _windows_open_directory(directory, True)
                actual = _windows_handle_identity(handle)
                if actual != expected:
                    _windows_close(handle)
                    raise PlanFileError("ancestor_identity")
                handles.append(handle)
            _WINDOWS_PARENT_HANDLES[path["parent"]] = handles[-1]
            yield path
        finally:
            _WINDOWS_PARENT_HANDLES.pop(path["parent"], None)
            for handle in reversed(handles):
                with contextlib.suppress(Exception):
                    _windows_close(handle)
        return

    _request_path(root, slug, kind)
    root_before = os.lstat(root)
    if not _directory(root_before):
        raise PlanFileError("root")
    root_fd = state_fd = parent_fd = None
    try:
        root_fd, root_info = _open_posix_directory(root, expected=root_before)
        state_fd, state_info = _exact_fd_child(root_fd, ".codearbiter")
        parent_fd, parent_info = _exact_fd_child(state_fd, KINDS[kind])
        leaf = f"{slug}.md"
        aliases = _aliases(parent_fd, leaf)
        if aliases not in ([], [leaf]):
            raise PlanFileError("path_alias")
        path = {"root": root, "state": os.path.join(root, ".codearbiter"),
                "parent": os.path.join(root, ".codearbiter", KINDS[kind]),
                "target": os.path.join(root, ".codearbiter", KINDS[kind], leaf),
                "leaf": leaf, "kind": kind, "root_fd": root_fd, "state_fd": state_fd,
                "parent_fd": parent_fd,
                "identities": (_identity(root_info), _identity(state_info), _identity(parent_info))}
        if fault:
            fault("after_validate", path)
        yield path
    finally:
        for fd in (parent_fd, state_fd, root_fd):
            if fd is not None:
                with contextlib.suppress(Exception):
                    os.close(fd)


def _chain_current(path):
    if os.name == "nt":
        return True
    try:
        state = os.stat(".codearbiter", dir_fd=path["root_fd"], follow_symlinks=False)
        parent = os.stat(KINDS[path["kind"]], dir_fd=path["state_fd"], follow_symlinks=False)
        return _identity(state) == path["identities"][1] and _identity(parent) == path["identities"][2]
    except (OSError, ValueError):
        return False


def _lock_name(target):
    return hashlib.sha256(os.path.normcase(os.path.abspath(target)).encode("utf-8")).hexdigest() + ".lock"


@contextlib.contextmanager
def _windows_mutex(target):
    name = "Local\\CodeArbiterPiPlan-" + _lock_name(target)[:-5]
    handle = _windows_create_mutex(name)
    if not handle:
        raise PlanFileError("lock_create")
    acquired = False
    try:
        outcome = _windows_wait_mutex(handle, int(LOCK_WAIT_SECONDS * 1000))
        if outcome not in (0x00000000, 0x00000080):
            raise PlanFileError("lock_timeout" if outcome == 0x00000102 else "lock_wait")
        acquired = True  # WAIT_ABANDONED is ownership, not failure.
        yield
    finally:
        if acquired:
            with contextlib.suppress(Exception):
                _windows_release_mutex(handle)
        with contextlib.suppress(Exception):
            _windows_close(handle)


def _windows_create_mutex(name):
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel32.CreateMutexW
    create.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    create.restype = wintypes.HANDLE
    return create(None, False, name)  # Default user DACL; no replaceable lock pathname.


def _windows_wait_mutex(handle, timeout_ms):
    return ctypes.WinDLL("kernel32", use_last_error=True).WaitForSingleObject(handle, timeout_ms)


def _windows_release_mutex(handle):
    if not ctypes.WinDLL("kernel32", use_last_error=True).ReleaseMutex(handle):
        raise OSError(ctypes.get_last_error(), "ReleaseMutex")


@contextlib.contextmanager
def _posix_lock(target, lock_root):
    root = lock_root or os.path.join(tempfile.gettempdir(), "codearbiter-pi-plan-locks")
    try:
        os.mkdir(root, 0o700)
    except FileExistsError:
        pass
    before = os.lstat(root)
    if not _directory(before) or stat.S_IMODE(before.st_mode) != 0o700 \
            or hasattr(os, "getuid") and before.st_uid != os.getuid():
        raise PlanFileError("lock_root")
    root_fd, opened_root = _open_posix_directory(root, expected=before)
    lock_fd = None
    try:
        name = _lock_name(target)
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        try:
            leaf_before = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            lock_fd = os.open(name, flags, dir_fd=root_fd)
        except FileNotFoundError:
            lock_fd = os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=root_fd)
            leaf_before = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        opened = os.fstat(lock_fd)
        if not _regular_single(opened) or _identity(opened) != _identity(leaf_before) \
                or stat.S_IMODE(opened.st_mode) != 0o600 \
                or hasattr(os, "getuid") and opened.st_uid != os.getuid():
            raise PlanFileError("lock_path")
        import fcntl
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    raise PlanFileError("lock_timeout")
                time.sleep(0.005)
        current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if _identity(current) != _identity(opened) or _version(current) != _version(opened):
            raise PlanFileError("lock_race")
        yield
    finally:
        if lock_fd is not None:
            with contextlib.suppress(Exception):
                import fcntl
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            with contextlib.suppress(Exception):
                os.close(lock_fd)
        with contextlib.suppress(Exception):
            os.close(root_fd)


def _lock_for(target, lock_root=None):
    return _windows_mutex(target) if os.name == "nt" else _posix_lock(target, lock_root)


def _target_stat(path):
    aliases = _aliases(path["parent_fd"] if os.name != "nt" else path["parent"], path["leaf"])
    if aliases == []:
        return None
    if aliases != [path["leaf"]]:
        raise PlanFileError("path_alias")
    return (os.stat(path["leaf"], dir_fd=path["parent_fd"], follow_symlinks=False)
            if os.name != "nt" else os.lstat(path["target"]))


def _read_pass(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    chunks, total = [], 0
    while True:
        chunk = os.read(fd, min(65_536, MAX_CONTENT_BYTES + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_CONTENT_BYTES:
            raise PlanFileError("content_overflow")
    return b"".join(chunks)


def _open_temp(path, temp_name):
    if os.name != "nt":
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        return os.open(temp_name, flags, 0o600, dir_fd=path["parent_fd"])
    from ctypes import wintypes
    import msvcrt
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel32.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    handle = create(os.path.join(path["parent"], temp_name),
                    0x80000000 | 0x40000000 | 0x00010000 | 0x00100000,
                    0x00000001 | 0x00000002 | 0x00000004, None, 1,
                    0x00000080 | 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise PlanFileError("temp_create")
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDWR | getattr(os, "O_BINARY", 0))
    except Exception:
        _windows_close(handle)
        raise


def _verify_owned_temp(path, temp_name, fd, owned_identity, data):
    opened_before = os.fstat(fd)
    first = _read_pass(fd)
    opened_middle = os.fstat(fd)
    second = _read_pass(fd)
    opened_after = os.fstat(fd)
    current = (os.stat(temp_name, dir_fd=path["parent_fd"], follow_symlinks=False)
               if os.name != "nt" else os.lstat(os.path.join(path["parent"], temp_name)))
    if not _regular_single(opened_after) or _identity(opened_after) != owned_identity \
            or _identity(current) != owned_identity \
            or not (_version(opened_before) == _version(opened_middle) == _version(opened_after)) \
            or current.st_size != opened_after.st_size or current.st_mtime_ns != opened_after.st_mtime_ns \
            or first != second or first != data:
        raise PlanFileError("temp_race")


def _read_target(path, fault=None, allow_links=1):
    before = _target_stat(path)
    if before is None:
        return None
    if not stat.S_ISREG(before.st_mode) or _is_reparse(before) or before.st_nlink != allow_links:
        raise PlanFileError("target_type")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = (os.open(path["leaf"], flags, dir_fd=path["parent_fd"])
          if os.name != "nt" else os.open(path["target"], flags))
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or _is_reparse(opened) or opened.st_nlink != allow_links \
                or _identity(opened) != _identity(before):
            raise PlanFileError("target_race")
        first_before = _version(opened)
        first = _read_pass(fd)
        first_after = _version(os.fstat(fd))
        if fault:
            fault("read_between", path)
        second_before = _version(os.fstat(fd))
        second = _read_pass(fd)
        second_after = _version(os.fstat(fd))
        current = _target_stat(path)
        path_stable = current is not None and _identity(current) == _identity(opened) \
            and current.st_size == opened.st_size and current.st_nlink == opened.st_nlink \
            and current.st_mtime_ns == opened.st_mtime_ns
        if not path_stable or not _chain_current(path) \
                or not (first_before == first_after == second_before == second_after) \
                or first != second:
            raise PlanFileError("target_race")
        text = first.decode("utf-8", "strict")
        return {"content": text, "hash": hashlib.sha256(first).hexdigest(),
                "identity": _identity(opened), "version": first_before}
    finally:
        os.close(fd)


def _write_all(fd, data):
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise PlanFileError("temp_write")
        offset += written


def _sync_temp(fd):
    os.fsync(fd)


def _close_temp(fd):
    os.close(fd)


def _sync_parent(path):
    if os.name == "nt":
        return False
    os.fsync(path["parent_fd"])
    return True


def _windows_rename_status(handle, parent_handle, leaf, replace):
    from ctypes import wintypes

    class RenameInfo(ctypes.Structure):
        _fields_ = [("ReplaceIfExists", wintypes.BOOLEAN), ("RootDirectory", wintypes.HANDLE),
                    ("FileNameLength", wintypes.DWORD), ("FileName", wintypes.WCHAR * 1)]

    class IoStatusBlock(ctypes.Structure):
        _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_size_t)]

    encoded = leaf.encode("utf-16-le")
    size = ctypes.sizeof(RenameInfo) + len(encoded)
    buffer = ctypes.create_string_buffer(size)
    info = ctypes.cast(buffer, ctypes.POINTER(RenameInfo)).contents
    info.ReplaceIfExists = replace
    info.RootDirectory = parent_handle
    info.FileNameLength = len(encoded)
    ctypes.memmove(ctypes.addressof(buffer) + RenameInfo.FileName.offset, encoded, len(encoded))
    iosb = IoStatusBlock()
    ntdll = ctypes.WinDLL("ntdll")
    function = ntdll.NtSetInformationFile
    function.argtypes = [wintypes.HANDLE, ctypes.POINTER(IoStatusBlock), wintypes.LPVOID,
                         wintypes.ULONG, ctypes.c_int]
    function.restype = wintypes.LONG
    return int(function(handle, ctypes.byref(iosb), buffer, size, 10))


def _windows_publish(path, temp_fd, replace):
    import msvcrt
    parent_handle = _WINDOWS_PARENT_HANDLES.get(path["parent"])
    if parent_handle is None:
        raise PlanFileError("ancestor_handle")
    handle = msvcrt.get_osfhandle(temp_fd)
    status = _windows_rename_status(handle, parent_handle, path["leaf"], replace)
    if status < 0:  # NT_SUCCESS includes success and informational statuses.
        if not replace and (status & 0xFFFFFFFF) in (0xC0000035, 0xC00000BA):
            raise FileExistsError(path["leaf"])
        raise PlanFileError("publish")


def _posix_publish(path, temp_name, replace):
    if replace:
        os.replace(temp_name, path["leaf"], src_dir_fd=path["parent_fd"],
                   dst_dir_fd=path["parent_fd"])
        return
    os.link(temp_name, path["leaf"], src_dir_fd=path["parent_fd"],
            dst_dir_fd=path["parent_fd"], follow_symlinks=False)


def _publish(path, temp_name, temp_fd, replace):
    if os.name == "nt":
        _windows_publish(path, temp_fd, replace)
    else:
        _posix_publish(path, temp_name, replace)


def _unlink_owned(path, name, owned_identity):
    try:
        current = (os.stat(name, dir_fd=path["parent_fd"], follow_symlinks=False)
                   if os.name != "nt" else os.lstat(os.path.join(path["parent"], name)))
        if _identity(current) != owned_identity:
            return
        if os.name == "nt":
            os.unlink(os.path.join(path["parent"], name))
        else:
            os.unlink(name, dir_fd=path["parent_fd"])
    except FileNotFoundError:
        pass


def _cleanup_committed_temp(path, name, owned_identity):
    """Best-effort postcommit cleanup; never lets fallible name work escape."""
    try:
        _unlink_owned(path, name, owned_identity)
        try:
            current = (os.stat(name, dir_fd=path["parent_fd"], follow_symlinks=False)
                       if os.name != "nt" else os.lstat(os.path.join(path["parent"], name)))
        except FileNotFoundError:
            return True
        return _identity(current) != owned_identity
    except Exception:
        return False


def _same_snapshot(left, right):
    if left is None or right is None:
        return left is right
    return left["identity"] == right["identity"] and left["version"] == right["version"] \
        and left["hash"] == right["hash"]


def _result(status, **fields):
    return {"status": status, **fields}


def _committed_result(path, data, content, fault=None, initial_diagnostic=None):
    durable = False
    diagnostic = initial_diagnostic
    if fault:
        with contextlib.suppress(Exception):
            fault("after_publish", path)
    try:
        durable = _sync_parent(path) and diagnostic is None
        if not durable and diagnostic is None:
            diagnostic = diagnostic or "directory_durability_unavailable"
    except Exception:
        diagnostic = diagnostic or "directory_sync_failed"
    try:
        try:
            final = _read_target(path)
        except PlanFileError:
            if initial_diagnostic != "postcommit_cleanup_failed":
                raise
            final = _read_target(path, allow_links=2)
        wanted_hash = hashlib.sha256(data).hexdigest()
        exists = final is not None
        observed_hash = final["hash"] if final is not None else None
        observed_content = final["content"] if final is not None else ""
        if not exists or observed_hash != wanted_hash or observed_content != content:
            diagnostic = "postcommit_changed"
            durable = False
    except Exception:
        return _result("committed", observed=False, exists=None, hash=None, content=None,
                       directoryDurable=False, postCommitDiagnostic="postcommit_unobserved")
    result = _result("committed", observed=True, exists=exists, hash=observed_hash,
                     content=observed_content, directoryDurable=durable)
    if diagnostic:
        result["postCommitDiagnostic"] = diagnostic
    return result


def plan_file_operation(root, request, *, lock_root=None, fault=None):
    """Run a bounded CAS. The lock serializes cooperating codeArbiter Pi writers only."""
    try:
        if not isinstance(request, dict) or set(request) - {"slug", "kind", "action", "expectedHash", "content"}:
            raise PlanFileError("request")
        action = request.get("action")
        if action == "read" and set(request) != {"slug", "kind", "action"}:
            raise PlanFileError("request")
        if action == "replace" and set(request) != {"slug", "kind", "action", "expectedHash", "content"}:
            raise PlanFileError("request")
        if action not in ("read", "replace"):
            raise PlanFileError("request")
        target = _request_path(root, request.get("slug"), request.get("kind"))
        with _lock_for(target, lock_root), _held_path(root, request["slug"], request["kind"], fault) as path:
            chosen = _read_target(path, fault)
            if action == "read":
                if chosen is None:
                    return _result("unchanged", exists=False, hash=None, content="")
                return _result("unchanged", exists=True, hash=chosen["hash"], content=chosen["content"])
            expected = request["expectedHash"]
            if expected is not None and (not isinstance(expected, str) or not HASH_RE.fullmatch(expected)):
                raise PlanFileError("request")
            if (chosen is None) != (expected is None) or chosen is not None and chosen["hash"] != expected:
                return _result("conflict")
            content = request["content"]
            if not isinstance(content, str):
                raise PlanFileError("request")
            data = content.encode("utf-8", "strict")
            if len(data) > MAX_CONTENT_BYTES:
                raise PlanFileError("content_overflow")
            temp_name = f".{path['leaf']}.ca-plan-tmp-{secrets.token_hex(16)}"
            fd = None
            temp_identity = None
            committed = False
            try:
                fd = _open_temp(path, temp_name)
                temp_info = os.fstat(fd)
                if not _regular_single(temp_info):
                    raise PlanFileError("temp_type")
                temp_identity = _identity(temp_info)
                _write_all(fd, data)
                _sync_temp(fd)
                for phase in ("before_publish", "publish"):
                    if fault:
                        fault(phase, path)
                    try:
                        latest = _read_target(path)
                    except Exception:
                        return _result("conflict")
                    if not _same_snapshot(chosen, latest) or not _chain_current(path):
                        return _result("conflict")
                _verify_owned_temp(path, temp_name, fd, temp_identity, data)
                try:
                    _publish(path, temp_name, fd, chosen is not None)
                except FileExistsError:
                    return _result("conflict")
                committed = True  # The successful atomic rename is the irreversible commit point.
                if os.name == "nt" or chosen is not None:
                    temp_identity = None
                else:
                    cleanup_ok = _cleanup_committed_temp(path, temp_name, temp_identity)
                    if cleanup_ok:
                        temp_identity = None
                    cleanup_diagnostic = None if cleanup_ok else "postcommit_cleanup_failed"
                if os.name == "nt" or chosen is not None:
                    cleanup_diagnostic = None
                published_fd = fd
                fd = None
                with contextlib.suppress(Exception):
                    _close_temp(published_fd)
                return _committed_result(path, data, content, fault, cleanup_diagnostic)
            finally:
                if fd is not None:
                    with contextlib.suppress(Exception):
                        _close_temp(fd)
                if temp_identity is not None:
                    with contextlib.suppress(Exception):
                        _unlink_owned(path, temp_name, temp_identity)
    except PlanFileError as exc:
        return _result("error", code=str(exc) if str(exc) else "operation")
    except Exception:
        return _result("error", code="operation")
