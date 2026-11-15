"""Failure-only Windows RPC observation. Raw debugger output never leaves RAM.

This observes a previously failed wait; it cannot replace that failure or prove
an OS exit from a JavaScript exit event. CDB is optional, fixed SDK capability.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
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


def parse_stacks(raw: bytes) -> dict:
    """Keep only module-relative return addresses; ignore all symbol/path text."""
    result = {"status": "unrecognized", "threads": [], "truncated": False}
    if len(raw) > MAX_OUTPUT:
        return {**result, "status": "output_limit", "truncated": True}
    ranges = []
    current = None
    for line in raw.decode("ascii", errors="replace").splitlines():
        module = re.fullmatch(r"\s*([0-9a-fA-F`]{4,17})\s+([0-9a-fA-F`]{4,17})\s+([A-Za-z0-9_]+)\s+.*", line)
        if module:
            low, high = (int(module[index].replace("`", ""), 16) for index in (1, 2))
            if 0 <= low < high <= 2**64 and len(ranges) < 256:
                name = module[3].lower()
                ranges.append((low, high, name if name in MODULES else "Other"))
            else:
                result["truncated"] = True
            continue
        if re.match(r"\s*(?:[.#]\s*)?\d+\s+Id:\s+[0-9a-fA-F]+\.[0-9a-fA-F]+\s+", line):
            current = None
            if len(result["threads"]) < 16:
                current = {"frames": []}
                result["threads"].append(current)
            else:
                result["truncated"] = True
            continue
        frame = re.fullmatch(r"\s*[0-9a-fA-F]{1,2}\s+[0-9a-fA-F`]{4,17}\s+([0-9a-fA-F`]{4,17})(?:\s+.*)?", line)
        if frame and current is not None:
            if len(current["frames"]) >= 24:
                result["truncated"] = True
                continue
            address = int(frame[1].replace("`", ""), 16)
            matches = [(low, name) for low, high, name in ranges if low <= address < high]
            name, offset = "Other", None
            if len(matches) == 1 and matches[0][1] != "Other":
                name, offset = matches[0][1], address - matches[0][0]
            current["frames"].append({"module": name, "returnOffset": offset})
    if any(row["frames"] for row in result["threads"]):
        result["status"] = "captured"
    return result


def _profile(pid: int, root: Path) -> tuple[list[str], dict[str, str]]:
    if type(pid) is not int or not 0 < pid <= 0xFFFFFFFF:
        raise ValueError("invalid owned PID")
    root = root.resolve(strict=True)
    for name in ("symbols", "images", "sources", "home", "temp", "appdata", "localappdata"):
        (root / name).mkdir(exist_ok=True)
    commands = root / "empty.commands"
    commands.write_bytes(b"")
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}
    system = Path(env.get("SystemRoot", "C:/Windows")) / "System32"
    env.update(HOME=str(root / "home"), USERPROFILE=str(root / "home"),
               APPDATA=str(root / "appdata"), LOCALAPPDATA=str(root / "localappdata"),
               TEMP=str(root / "temp"), TMP=str(root / "temp"), PATH=os.pathsep.join((str(CDB.parent), str(system))))
    return ([str(CDB), "-pv", "-pd", "-kqm", "-noshell", "-nosqm", "-sins", "-snul", "-netsyms:no",
             "-y", str(root / "symbols"), "-i", str(root / "images"), "-srcpath", str(root / "sources"),
             "-cf", str(commands), "-p", str(pid), "-c", "lm; ~*kL 18; q"], env)


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


def _debugger(pid: int, kernel: WindowsKernel, deadline: float) -> dict:
    result = {"status": "unavailable", "threads": [], "truncated": False,
              "temporarilySuspends": False, "toolHashes": None, "publisherSignature": "not-verified", "toolVersion": "not-observed"}
    try:
        hashes = {name: _digest(CDB.parent / name, deadline) for name in ("cdb.exe", "dbgeng.dll", "dbghelp.dll")}
    except Exception:
        return result
    result["toolHashes"] = hashes
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix="ca-rpc-native-") as directory:
            root = _regular(Path(directory), directory=True)
            argv, env = _profile(pid, root)
            if time.monotonic() >= deadline:
                return {**result, "status": "deadline"}
            process = subprocess.Popen(argv, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            result["temporarilySuspends"] = True
            status, raw = _collect(process, kernel.available, deadline=deadline)
            parsed = parse_stacks(raw) if status == "captured" else {"status": status, "threads": [], "truncated": status == "output_limit"}
            return {**result, **parsed}
    except Exception:
        return {**result, "status": "transport_failed"}
    finally:
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            # We own this debugger handle; never touch the observed Popen handle.
            process._handle.Close()


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
            result["debugger"] = (_debugger or globals()["_debugger"])(process.pid, kernel, deadline)
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
