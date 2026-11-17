"""Failure-only Windows RPC observation. Raw debugger output never leaves RAM.

This observes a previously failed wait; it cannot replace that failure or prove
an OS exit from a JavaScript exit event. Closed SDK and protected Windows inbox
profiles identify only the checked libraries used by the private typed worker.
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
DEFAULT_CDB = Path("C:/Program Files (x86)/Windows Kits/10/Debuggers/x64/cdb.exe")
CDB = DEFAULT_CDB
TOOL_FILES = {"sdk-v1": ("cdb.exe", "dbgeng.dll", "dbghelp.dll"),
              "inbox-v1": ("dbgeng.dll", "dbghelp.dll")}
MODULES = frozenset(("node", "ntdll", "kernel32", "kernelbase", "ucrtbase", "vcruntime140", "msvcp140"))


class IdentityDeadline(ValueError):
    """A fixed category; no failing filename or exception message is retained."""


def _failure_kind(error: Exception) -> str:
    if isinstance(error, IdentityDeadline):
        return "deadline"
    if isinstance(error, FileNotFoundError):
        return "missing"
    if isinstance(error, ValueError):
        return "refused"
    return "os-error" if isinstance(error, OSError) else "unexpected"


def _phase(progress, name):
    if progress is not None:
        progress["phase"] = name


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
            if time.monotonic() >= deadline:
                raise IdentityDeadline("identity bound")
            if total > 128 << 20:
                raise ValueError("identity bound")
            digest.update(chunk)
    return digest.hexdigest()


def _system_directory() -> Path:
    """The OS supplies this path; environment variables and PATH are not inputs."""
    api = ctypes.WinDLL("kernel32", use_last_error=True, winmode=0x800)
    query = api.GetSystemDirectoryW
    query.restype, query.argtypes = wintypes.UINT, [wintypes.LPWSTR, wintypes.UINT]
    buffer = ctypes.create_unicode_buffer(32768)
    count = query(buffer, len(buffer))
    if not 0 < count < len(buffer) or len(buffer.value) != count:
        raise ValueError("system directory unavailable")
    path = Path(buffer.value)
    if not path.is_absolute():
        raise ValueError("unsupported system directory")
    return _regular(path, directory=True)


def _tool_profile(deadline: float, *, _progress=None) -> tuple[str, Path, dict]:
    # Only absence of the default SDK directory permits the inbox profile.
    # A selected override, incomplete SDK or reparse/tamper failure never does.
    _phase(_progress, "provider-directory")
    try:
        CDB.parent.lstat()
    except FileNotFoundError:
        if CDB != DEFAULT_CDB:
            raise ValueError("selected SDK unavailable") from None
        for component in CDB.parent.absolute().parents:
            try:
                info = component.lstat()
            except FileNotFoundError:
                continue
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & 0x400):
                raise ValueError("unsupported file identity")
        _phase(_progress, "provider-inbox-directory")
        profile, directory = "inbox-v1", _system_directory()
    else:
        profile, directory = "sdk-v1", _regular(CDB.parent, directory=True)
    hashes = {}
    for name in TOOL_FILES[profile]:
        _phase(_progress, {"cdb.exe": "provider-hash-cdb", "dbgeng.dll": "provider-hash-dbgeng",
                           "dbghelp.dll": "provider-hash-dbghelp"}[name])
        hashes[name] = _digest(directory / name, deadline)
    return profile, directory, hashes


def _bound_tool_profile(profile, directory, hashes, deadline) -> Path:
    """Rebind the worker request to the same closed protected provider."""
    if (type(profile) is not str or profile not in TOOL_FILES
            or type(hashes) is not dict or set(hashes) != set(TOOL_FILES[profile])
            or any(type(value) is not str or len(value) != 64
                   or any(c not in "0123456789abcdef" for c in value) for value in hashes.values())):
        raise ValueError("unsupported debugger profile")
    expected = (_regular(CDB.parent, directory=True) if profile == "sdk-v1" else _system_directory())
    actual = _regular(Path(directory), directory=True)
    if actual != expected or any(_digest(actual / name, deadline) != digest for name, digest in hashes.items()):
        raise ValueError("debugger profile identity mismatch")
    return actual


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
    started = time.monotonic()
    result = {"status": "unavailable", "threads": [], "truncated": False,
              "temporarilySuspends": False, "toolHashes": None,
              "publisherSignature": "not-verified", "toolVersion": "not-observed", "profile": None,
              "worker": None, "diagnostic": {"phase": "provider-select", "failure": None,
                  "elapsedMs": 0, "remainingMs": max(0, min(5000, round((deadline - started) * 1000)))}}
    diagnostic = result["diagnostic"]
    try:
        profile, sdk, hashes = _tool_profile(deadline, _progress=diagnostic)
    except Exception as error:
        diagnostic.update(failure=_failure_kind(error),
                          elapsedMs=min(2**31 - 1, max(0, round((time.monotonic() - started) * 1000))))
        return result
    result["toolHashes"] = hashes
    result["profile"] = profile
    process, duplicate = None, None
    try:
        _phase(diagnostic, "worker-prepare")
        with tempfile.TemporaryDirectory(prefix="ca-rpc-native-") as directory:
            root = _regular(Path(directory), directory=True)
            worker = _regular(Path(__file__).with_name("_windows_dbgeng.py"))
            duplicate = kernel.duplicate_query(binding["handle"])
            request = {"schemaVersion": 3, "profile": profile,
                       "handle": duplicate, "pid": pid, "created": binding["created"],
                       "image": binding["image"], "sdk": str(sdk), "hashes": hashes,
                       "deadline": deadline}
            encoded = json.dumps(request, separators=(",", ":")).encode("utf-8")
            if len(encoded) > 4096 or time.monotonic() >= deadline:
                diagnostic["failure"] = "deadline" if time.monotonic() >= deadline else "refused"
                return {**result, "status": "deadline"}
            startup = subprocess.STARTUPINFO()
            startup.lpAttributeList = {"handle_list": [duplicate]}
            _phase(diagnostic, "worker-launch")
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
            _phase(diagnostic, "worker-transport")
            status, raw = _collect(process, kernel.available, deadline=deadline)
            if status != "captured":
                result.update(status=status, truncated=status == "output_limit")
                diagnostic["failure"] = {"deadline": "deadline", "output_limit": "output-limit",
                    "cleanup_unknown": "cleanup", "debugger_failed": "worker-exit"}.get(status, "transport")
            else:
                _phase(diagnostic, "worker-decode")
                decoded = decode_result(raw, pid, binding["created"], profile=profile, version=3)
                if decoded is None:
                    result["status"] = "transport_failed"
                    diagnostic["failure"] = "decode"
                else:
                    result.update(status=decoded["status"], threads=decoded["threads"],
                                  truncated=decoded["truncated"], temporarilySuspends=decoded["attached"])
                    result["worker"] = {key: decoded[key] for key in
                        ("bound", "attached", "detached", "hresult", "policy", "phase", "elapsedMs")}
                    _phase(diagnostic, "worker-result")
                    if decoded["status"] != "captured":
                        diagnostic["failure"] = {"deadline": "deadline", "cleanup_unknown": "cleanup",
                            "identity_refused": "refused", "input_refused": "refused",
                            "unrecognized": "unrecognized"}.get(decoded["status"], "engine")
            del raw  # Unexpected SDK/worker text is never a retained diagnostic.
    except Exception as error:
        result.update(status="transport_failed", threads=[])
        diagnostic["failure"] = _failure_kind(error)
    finally:
        if duplicate is not None:
            try:
                kernel.close(duplicate)
            except Exception:
                result.update(status="cleanup_unknown", threads=[])
                diagnostic["failure"] = diagnostic["failure"] or "cleanup"
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
                diagnostic["failure"] = diagnostic["failure"] or "cleanup"
        diagnostic["elapsedMs"] = min(2**31 - 1, max(0, round((time.monotonic() - started) * 1000)))
    return result


def _state(snapshot: dict) -> dict:
    return {"state": snapshot["state"], "exitCode": snapshot["exitCode"]}


def capture(process, expected_node: Path, *, _kernel=None, _debugger=None) -> dict:
    started = time.monotonic()
    deadline = started + SECONDS
    result = {"schemaVersion": 2, "outcome": "original-failure", "identity": "unknown",
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


WARM_PHASES = frozenset(('provider-select','provider-directory','provider-inbox-directory',
    'provider-hash-cdb','provider-hash-dbgeng','provider-hash-dbghelp',
    'worker-prepare','worker-launch','worker-result'))
WARM_FIELDS = frozenset(('schemaVersion','kind','status','profile','filesHashed','phase','failure','elapsedMs'))


def _warm_valid(value, *, supervised=False):
    fields=WARM_FIELDS | ({'timed_out','containment'} if supervised else set())
    if (type(value) is not dict or set(value)!=fields or type(value['schemaVersion']) is not int
            or value['schemaVersion']!=1
            or value['kind']!=('protected-provider-warm-preflight' if supervised else 'protected-provider-warm-read')
            or value['status'] not in ('complete','unavailable','deadline','refused')
            or value['profile'] not in (None,'sdk-v1','inbox-v1')
            or type(value['filesHashed']) is not int or not 0<=value['filesHashed']<=3
            or type(value['phase']) is not str or value['phase'] not in WARM_PHASES
            or value['failure'] not in (None,'deadline','missing','refused','os-error','unexpected','decode','transport')
            or type(value['elapsedMs']) is not int or not 0<=value['elapsedMs']<=2**31-1):
        return False
    if supervised and (type(value['timed_out']) is not bool
            or value['containment'] not in ('not-started','exited','terminated','unconfirmed')):
        return False
    return (value['profile'] in TOOL_FILES and value['filesHashed']==len(TOOL_FILES[value['profile']])
            and value['failure'] is None and (not supervised or (not value['timed_out'] and value['containment']=='exited'))
        ) if value['status']=='complete' else value['profile'] is None and value['filesHashed']==0


def provider_warm_read():
    """Hash-only child: no DbgEng import/load, target PID, handle or attachment."""
    started=time.monotonic();progress={'phase':'provider-select'}
    result={'schemaVersion':1,'kind':'protected-provider-warm-read','status':'unavailable',
        'profile':None,'filesHashed':0,'phase':'provider-select','failure':None,'elapsedMs':0}
    try:
        if os.name!='nt':raise ValueError('Windows provider required')
        profile,directory,hashes=_tool_profile(started+SECONDS,_progress=progress)
        result.update(status='complete',profile=profile,filesHashed=len(hashes))
        del hashes  # warming is not a cached identity or later authority
    except Exception as error:
        result['failure']=_failure_kind(error)
    result.update(phase=progress['phase'],elapsedMs=min(2**31-1,max(0,round((time.monotonic()-started)*1000))))
    return result


def preflight_provider(home):
    """Optional owned five-second warm read before an observed Windows target.

    This result is diagnostic only. Failure/worker full hashes below are never
    replaced by a cached digest, preflight result or readiness Boolean.
    """
    if os.name!='nt':return None
    from _boundedproc import run
    started=time.monotonic()
    result={'schemaVersion':1,'kind':'protected-provider-warm-preflight','status':'unavailable',
        'profile':None,'filesHashed':0,'phase':'worker-prepare','failure':None,'elapsedMs':0,
        'timed_out':False,'containment':'not-started'}
    try:
        parent=_regular(Path(home).resolve(strict=True),directory=True)
        with tempfile.TemporaryDirectory(prefix='ca-rpc-provider-warm-',dir=parent) as raw:
            root=_regular(Path(raw).resolve(strict=True),directory=True)
            environment=_worker_environment(root)
            environment.update(PATH='',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1')
            startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=subprocess.SW_HIDE
            result['phase']='worker-launch'
            actual=run([sys.executable,'-I','-S','-B','-X','utf8',str(_regular(Path(__file__))),
                '--preflight-provider'],timeout=SECONDS,cwd=root,env=environment,startupinfo=startup,
                stdin=subprocess.DEVNULL,close_fds=True)
            result.update(timed_out=actual.timed_out,containment=actual.containment)
            if actual.timed_out:
                result.update(status='deadline',failure='deadline')
            elif actual.returncode!=0 or actual.containment!='exited':
                result['failure']='transport'
            else:
                result['phase']='worker-result'
                def pairs(rows):
                    value={}
                    for key,item in rows:
                        if key in value:raise ValueError('duplicate closed field')
                        value[key]=item
                    return value
                data=None
                try:
                    if len(actual.stdout.encode('utf8'))<=MAX_JSON:
                        data=json.loads(actual.stdout,object_pairs_hook=pairs)
                except (ValueError,UnicodeError,RecursionError):pass
                if _warm_valid(data):
                    result.update({key:data[key] for key in ('status','profile','filesHashed','phase','failure')})
                else:result.update(status='refused',failure='decode')
    except Exception as error:
        if result['phase']=='worker-launch' and result['containment']=='not-started':
            # An owner/transport exception after launch was attempted supplies
            # no quiescence proof. The caller must not start a second target.
            result['containment']='unconfirmed'
        result.update(status='unavailable',profile=None,filesHashed=0,
            failure=result['failure'] or _failure_kind(error))
    result['elapsedMs']=min(2**31-1,max(0,round((time.monotonic()-started)*1000)))
    return result


def retain_preflight(record, pid, destination):
    """Separate PID association, never an installed/native qualification input."""
    try:
        if not _warm_valid(record,supervised=True):return None
        if pid is None:
            if record['containment']!='unconfirmed':return None
        elif type(pid) is not int or not 0<pid<=0xFFFFFFFF:return None
        destination=Path(destination).absolute()
        _regular(destination.parent,directory=True)
        destination.mkdir(mode=0o700,exist_ok=True)
        destination=_regular(destination,directory=True)
        encoded=(json.dumps({**record,'processId':pid,'targetState':'not-spawned' if pid is None else 'spawned'},separators=(',',':'))+'\n').encode('utf8')
        if len(encoded)>MAX_JSON:return None
        with tempfile.NamedTemporaryFile(mode='wb',prefix='rpc-native-warmup-',suffix='.json',dir=destination,delete=False) as stream:
            stream.write(encoded);return Path(stream.name).name
    except Exception:return None


if __name__=='__main__':
    if sys.argv[1:]!=['--preflight-provider']:raise SystemExit(2)
    # Exactly one closed public diagnostic; no hashes, paths or exception text.
    print(json.dumps(provider_warm_read(),separators=(',',':')))
