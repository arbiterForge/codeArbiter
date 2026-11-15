"""Failure-only Windows RPC observation. Raw debugger output never leaves RAM.

This observes a previously failed wait; it cannot replace that failure or prove
an OS exit from a JavaScript exit event. The existing SDK is optional; its fixed
CDB location identifies the sibling DLLs used by the private typed worker.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import subprocess
import tempfile
import time

MAX_OUTPUT = 128 << 10
MAX_JSON = 32 << 10
SECONDS = 5.0
CDB = Path("C:/Program Files (x86)/Windows Kits/10/Debuggers/x64/cdb.exe")
MODULES = frozenset(("node", "ntdll", "kernel32", "kernelbase", "ucrtbase", "vcruntime140", "msvcp140"))


def _regular(path: Path, *, directory: bool = False) -> Path:
    """No aliases/reparse ancestors, including an SDK or artifact directory."""
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("unsupported file identity")
    info = absolute.stat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError("unsupported file type")
    return absolute.resolve(strict=True)


def _digest(path: Path, deadline: float) -> str:
    digest = hashlib.sha256()
    total = 0
    with _regular(path).open("rb") as stream:
        while chunk := stream.read(65536):
            total += len(chunk)
            if total > 128 << 20 or time.monotonic() >= deadline:
                raise ValueError("identity bound")
            digest.update(chunk)
    return digest.hexdigest()


class WindowsKernel:
    """All pointer-sized arguments/results are declared; never close Popen's handle."""

    def __init__(self):
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        declarations = {
            "OpenProcess": (wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
            "GetProcessId": (wintypes.DWORD, [wintypes.HANDLE]),
            "GetProcessTimes": (wintypes.BOOL, [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4),
            "WaitForSingleObject": (wintypes.DWORD, [wintypes.HANDLE, wintypes.DWORD]),
            "GetExitCodeProcess": (wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]),
            "QueryFullProcessImageNameW": (wintypes.BOOL, [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]),
            "CloseHandle": (wintypes.BOOL, [wintypes.HANDLE]),
            "GetCurrentProcess": (wintypes.HANDLE, []),
            "DuplicateHandle": (wintypes.BOOL, [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                                                ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
                                                wintypes.BOOL, wintypes.DWORD]),
            "PeekNamedPipe": (wintypes.BOOL, [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                                             ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]),
        }
        for name, (result, args) in declarations.items():
            function = getattr(self.api, name)
            function.restype, function.argtypes = result, args

    def open(self, pid: int) -> int:
        handle = self.api.OpenProcess(0x00100000 | 0x1000, False, pid)
        if not handle:
            raise OSError("process query unavailable")
        return handle

    def close(self, handle: int) -> None:
        if not self.api.CloseHandle(handle):
            raise OSError("process handle close failed")

    def duplicate_query(self, handle: int) -> int:
        duplicate = wintypes.HANDLE()
        current = self.api.GetCurrentProcess()
        if not self.api.DuplicateHandle(current, handle, current, ctypes.byref(duplicate),
                                        0x00100000 | 0x1000, True, 0):
            raise OSError("query handle duplication unavailable")
        return duplicate.value

    def snapshot(self, handle: int) -> dict:
        pid = self.api.GetProcessId(handle)
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        code, length = wintypes.DWORD(), wintypes.DWORD(32768)
        image = ctypes.create_unicode_buffer(length.value)
        wait = self.api.WaitForSingleObject(handle, 0)
        if (not pid or wait not in (0, 258)
                or not self.api.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user))
                or not self.api.GetExitCodeProcess(handle, ctypes.byref(code))):
            raise OSError("process state unavailable")
        # The image may already have been torn down after the process signals.
        # A late exit needs no debugger attachment or image lookup.
        if wait == 258 and not self.api.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
            raise OSError("process image unavailable")
        return {"pid": pid, "created": (created.dwHighDateTime << 32) | created.dwLowDateTime,
                "image": image.value, "state": "signaled" if wait == 0 else "running",
                "exitCode": code.value if wait == 0 else None}

    def available(self, stream) -> int:
        import msvcrt
        count = wintypes.DWORD()
        if not self.api.PeekNamedPipe(msvcrt.get_osfhandle(stream.fileno()), None, 0, None, ctypes.byref(count), None):
            if ctypes.get_last_error() == 109:  # ERROR_BROKEN_PIPE is EOF, never target absence.
                return 0
            raise OSError("debugger pipe unavailable")
        return count.value


def _worker_environment(root: Path) -> dict[str, str]:
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}
    for name in ("home", "temp", "appdata", "localappdata"):
        (root / name).mkdir(exist_ok=True)
    env.update(HOME=str(root / "home"), USERPROFILE=str(root / "home"),
               APPDATA=str(root / "appdata"), LOCALAPPDATA=str(root / "localappdata"),
               TEMP=str(root / "temp"), TMP=str(root / "temp"))
    return env


def _collect(process, available, *, deadline, _read=None, _clock=time.monotonic, _sleep=time.sleep):
    """Poll available pipe bytes on Windows; never block a reader thread or communicate."""
    read = _read or (lambda stream, size: os.read(stream.fileno(), size))
    raw = bytearray()
    status = "transport_failed"
    try:
        while _clock() < deadline:
            count = available(process.stdout)
            if count:
                if len(raw) == MAX_OUTPUT:
                    status = "output_limit"
                    break
                block = read(process.stdout, min(count, MAX_OUTPUT - len(raw), 4096))
                raw.extend(block)
                if len(raw) > MAX_OUTPUT:
                    status = "output_limit"
                    break
            elif process.poll() is not None:
                status = "captured" if process.returncode == 0 else "debugger_failed"
                break
            else:
                _sleep(min(0.01, max(0, deadline - _clock())))
        else:
            status = "deadline"
    except Exception:
        status = "transport_failed"
    finally:
        if status != "captured" and process.poll() is None:
            try:
                process.kill()  # Only this Popen-owned debugger, never the observed Node.
            except OSError:
                pass
        try:
            process.wait(timeout=max(0, deadline - _clock()))
        except (OSError, subprocess.TimeoutExpired):
            status = "cleanup_unknown"
    return status, bytes(raw[:MAX_OUTPUT])


def _debugger(pid: int, kernel: WindowsKernel, deadline: float, *, binding: dict) -> dict:
    from _windows_dbgeng import decode_result
    result = {"status": "unavailable", "threads": [], "truncated": False,
              "temporarilySuspends": False, "toolHashes": None,
              "publisherSignature": "not-verified", "toolVersion": "not-observed"}
    try:
        sdk = _regular(CDB.parent, directory=True)
        hashes = {name: _digest(sdk / name, deadline) for name in ("cdb.exe", "dbgeng.dll", "dbghelp.dll")}
    except Exception:
        return result
    result["toolHashes"] = hashes
    process, duplicate = None, None
    try:
        with tempfile.TemporaryDirectory(prefix="ca-rpc-native-") as directory:
            root = _regular(Path(directory), directory=True)
            worker = _regular(Path(__file__).with_name("_windows_dbgeng.py"))
            duplicate = kernel.duplicate_query(binding["handle"])
            request = {"handle": duplicate, "pid": pid, "created": binding["created"],
                       "image": binding["image"], "sdk": str(sdk), "hashes": hashes,
                       "deadline": deadline}
            encoded = json.dumps(request, separators=(",", ":")).encode("utf-8")
            if len(encoded) > 4096 or time.monotonic() >= deadline:
                return {**result, "status": "deadline"}
            startup = subprocess.STARTUPINFO()
            startup.lpAttributeList = {"handle_list": [duplicate]}
            process = subprocess.Popen([sys.executable, "-I", "-B", str(worker), "--worker"],
                cwd=root, env=_worker_environment(root), startupinfo=startup, close_fds=True,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
                creationflags=subprocess.CREATE_NO_WINDOW)
            result["temporarilySuspends"] = True
            kernel.close(duplicate)
            duplicate = None
            if process.stdin.write(encoded) != len(encoded):
                raise OSError("worker input incomplete")
            process.stdin.close()
            status, raw = _collect(process, kernel.available, deadline=deadline)
            if status != "captured":
                result.update(status=status, truncated=status == "output_limit")
            else:
                decoded = decode_result(raw, pid, binding["created"])
                if decoded is None:
                    result["status"] = "transport_failed"
                else:
                    result.update(status=decoded["status"], threads=decoded["threads"],
                                  truncated=decoded["truncated"], temporarilySuspends=decoded["attached"])
            del raw  # Unexpected SDK/worker text is never a retained diagnostic.
    except Exception:
        result.update(status="transport_failed", threads=[])
    finally:
        if duplicate is not None:
            try:
                kernel.close(duplicate)
            except Exception:
                result.update(status="cleanup_unknown", threads=[])
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()  # Only this worker; target cleanup remains the parent's.
                    process.wait(timeout=max(0, deadline - time.monotonic()))
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
                if process.stdout is not None:
                    process.stdout.close()
                process._handle.Close()
            except Exception:
                result.update(status="cleanup_unknown", threads=[])
    return result


def _state(snapshot: dict) -> dict:
    return {"state": snapshot["state"], "exitCode": snapshot["exitCode"]}


def capture(process, expected_node: Path, *, _kernel=None, _debugger=None) -> dict:
    started = time.monotonic()
    deadline = started + SECONDS
    result = {"schemaVersion": 1, "outcome": "original-failure", "identity": "unknown",
              "before": {"state": "unknown", "exitCode": None}, "after": {"state": "unknown", "exitCode": None},
              "processId": None, "creationTime": None, "nodeSha256": None, "debugger": {"status": "not-attempted", "threads": [], "truncated": False}}
    handle = None
    try:
        if os.name != "nt" and _kernel is None:
            result["identity"] = "unsupported-platform"
            return result
        kernel = _kernel or WindowsKernel()
        original = kernel.snapshot(int(process._handle))
        result["before"] = _state(original)
        result.update(processId=original["pid"], creationTime=original["created"])
        if original["pid"] != process.pid:
            result["identity"] = "mismatch"
            return result
        if original["state"] == "signaled":
            result["identity"] = "owned-exited"
            result["after"] = _state(original)
            return result
        handle = kernel.open(process.pid)
        independent = kernel.snapshot(handle)
        if (original["pid"] != process.pid or independent["pid"] != process.pid
                or original["created"] != independent["created"]
                or original["state"] not in ("running", "signaled")
                or independent["state"] not in ("running", "signaled")):
            result["identity"] = "mismatch"
            return result
        # Rundown may complete between snapshots. Verify identity first, then
        # preserve the signaled observation without requiring a torn-down image.
        if independent["state"] == "signaled":
            result["identity"] = "owned-exited"
            result["after"] = _state(independent)
            return result
        if (_regular(Path(original["image"])) != _regular(expected_node)
                or _regular(Path(independent["image"])) != _regular(expected_node)):
            result["identity"] = "mismatch"
            return result
        result["nodeSha256"] = _digest(expected_node, deadline)
        result["identity"] = "matched"
        if original["state"] == "running" and independent["state"] == "running":
            if _debugger is not None:
                result["debugger"] = _debugger(process.pid, kernel, deadline)
            else:
                result["debugger"] = globals()["_debugger"](process.pid, kernel, deadline,
                    binding={"handle": int(process._handle), "created": original["created"],
                             "image": original["image"]})
        after = kernel.snapshot(int(process._handle))
        if after["pid"] != original["pid"] or after["created"] != original["created"]:
            result["identity"] = "mismatch"
        else:
            result["after"] = _state(after)
    except Exception:
        result["identity"] = "query-failed"
    finally:
        if handle is not None:
            try:
                kernel.close(handle)
            except Exception:
                result["identity"] = "close-failed"
        result["elapsedMs"] = min(2**31 - 1, max(0, round((time.monotonic() - started) * 1000)))
    return result


def retain_failure(process, expected_node: Path, destination: Path) -> str | None:
    """An exclusive sidecar after the original failure was retained; never raise."""
    try:
        destination = _regular(destination, directory=True)
        report = capture(process, expected_node)
        encoded = (json.dumps(report, separators=(",", ":")) + "\n").encode("utf-8")
        if len(encoded) > MAX_JSON:
            return None
        with tempfile.NamedTemporaryFile(mode="wb", prefix="rpc-native-exit-", suffix=".json", dir=destination, delete=False) as stream:
            stream.write(encoded)
            return Path(stream.name).name
    except Exception:
        return None
