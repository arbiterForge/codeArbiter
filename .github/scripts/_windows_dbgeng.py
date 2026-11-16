"""Private, inherited-handle DbgEng worker. No debugger text callbacks or commands."""
from __future__ import annotations

import ctypes as C
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

MODULES = frozenset(("node", "ntdll", "kernel32", "kernelbase", "ucrtbase", "vcruntime140", "msvcp140"))
POLICY = 0x8 | 0x1000 | 0x8000 | 0x80000
ALLOW_NETWORK = 0x4
MAX_JSON = 32 << 10
U32, U64, PTR, HR = C.c_uint32, C.c_uint64, C.c_void_p, C.c_int32


class GUID(C.Structure):
    _fields_ = [("a", U32), ("b", C.c_uint16), ("c", C.c_uint16), ("d", C.c_uint8 * 8)]


class Frame(C.Structure):
    _fields_ = [("InstructionOffset", U64), ("ReturnOffset", U64), ("FrameOffset", U64),
                ("StackOffset", U64), ("FuncTableEntry", U64), ("Params", U64 * 4),
                ("Reserved", U64 * 6), ("Virtual", C.c_int32), ("FrameNumber", U32)]


# Stable base COM ABI, checked against all STDMETHOD/STDMETHOD_/STDMETHODV/
# STDMETHODV_ entries (including IUnknown) in the actual Microsoft dbgeng.h.
# Interface method counts: Client48, Control95, SystemObjects32, Symbols52.
IIDS = {
    "client": (0x27FE5639, 0x8407, 0x4F47, (0x83, 0x64, 0xEE, 0x11, 0x8F, 0xB0, 0x8A, 0xC8)),
    "control": (0x5182E668, 0x105E, 0x416E, (0xAD, 0x92, 0x24, 0xEF, 0x80, 0x04, 0x24, 0xBA)),
    "systems": (0x6B86FE2C, 0x2C4F, 0x4F0C, (0x9D, 0xA2, 0x17, 0x43, 0x11, 0xAC, 0xC3, 0x27)),
    "symbols": (0x8C31E98C, 0x983A, 0x48A5, (0x90, 0x16, 0x6F, 0xE5, 0xD6, 0x67, 0xA9, 0x50)),
}


def _guid(name):
    a, b, c, tail = IIDS[name]
    return GUID(a, b, c, (C.c_uint8 * 8)(*tail))


def project_frame(name: bytes, address: int, base: int, unique: bool) -> dict:
    unknown = {"module": "Other", "returnOffset": None}
    if (type(name) is not bytes or type(address) is not int or type(base) is not int
            or not unique or not 0 <= base <= address < 2**64):
        return unknown
    try:
        module = name.decode("ascii").lower()
    except UnicodeError:
        return unknown
    return {"module": module, "returnOffset": address - base} if module in MODULES else unknown


def decode_result(raw: bytes, pid: int, created: int, *, profile=None) -> dict | None:
    """The worker cannot expand the parent's public diagnostic vocabulary."""
    try:
        if len(raw) > MAX_JSON:
            return None
        data = json.loads(raw)
        fields = {"schemaVersion", "status", "threads", "truncated", "pid", "created",
                  "bound", "attached", "policy", "detached", "hresult"}
        if type(data) is not dict or type(data.get("schemaVersion")) is not int:
            return None
        version = data["schemaVersion"]
        if version == 2:
            fields.add("profile")
            if (type(data.get("profile")) is not str or data["profile"] not in {"sdk-v1", "inbox-v1"}
                    or (profile is not None and data["profile"] != profile)):
                return None
        elif version != 1 or profile is not None:
            return None
        if (set(data) != fields
                or type(data["pid"]) is not int or type(data["created"]) is not int
                or data["pid"] != pid or data["created"] != created
                or data["status"] not in {"captured", "unrecognized", "engine_failed", "identity_refused",
                                        "deadline", "cleanup_unknown", "input_refused"}
                or any(type(data[k]) is not bool for k in ("truncated", "bound", "attached", "detached"))
                or type(data["policy"]) is not int or not 0 <= data["policy"] <= 0xFFFFFFFF
                or (data["hresult"] is not None and
                    (type(data["hresult"]) is not int or not 0 <= data["hresult"] <= 0xFFFFFFFF))
                or type(data["threads"]) is not list or len(data["threads"]) > 16):
            return None
        known = False
        for thread in data["threads"]:
            if type(thread) is not dict or set(thread) != {"frames"} or type(thread["frames"]) is not list or len(thread["frames"]) > 24:
                return None
            for frame in thread["frames"]:
                if type(frame) is not dict or set(frame) != {"module", "returnOffset"}:
                    return None
                if frame["module"] == "Other":
                    if frame["returnOffset"] is not None:
                        return None
                elif (frame["module"] not in MODULES or type(frame["returnOffset"]) is not int
                      or not 0 <= frame["returnOffset"] < 2**64):
                    return None
                else:
                    known = True
        if data["status"] == "captured" and not (known and data["bound"] and data["attached"]
                and data["detached"] and data["hresult"] == 0
                and data["policy"] & POLICY == POLICY and not data["policy"] & ALLOW_NETWORK):
            return None
        return data
    except (ValueError, TypeError, RecursionError):
        return None


class Engine:
    def __init__(self, sdk: Path):
        if C.sizeof(PTR) != 8 or C.sizeof(GUID) != 16 or C.sizeof(Frame) != 128:
            raise ValueError("unsupported ABI")
        # Preload the checked profile's DbgHelp, then DbgEng. Search only each DLL's
        # directory and System32; never PATH/cwd or arbitrary DLL directories.
        self.help = C.WinDLL(str(sdk / "dbghelp.dll"), winmode=0x100 | 0x800)
        self.dll = C.WinDLL(str(sdk / "dbgeng.dll"), winmode=0x100 | 0x800)
        self.interfaces = {}
        create = self.dll.DebugCreate
        create.restype, create.argtypes = HR, [C.POINTER(GUID), C.POINTER(PTR)]
        try:
            client = PTR()
            self.check(create(C.byref(_guid("client")), C.byref(client)))
            self.interfaces["client"] = client
            for name in ("control", "systems", "symbols"):
                ptr = PTR()
                self.check(self.call("client", 0, [C.POINTER(GUID), C.POINTER(PTR)], C.byref(_guid(name)), C.byref(ptr)))
                self.interfaces[name] = ptr
        except Exception:
            self.close()
            raise

    @staticmethod
    def check(hr):
        if hr != 0:
            raise EngineFailure(int(hr) & 0xFFFFFFFF)

    def call(self, name, index, argtypes, *args, restype=HR):
        ptr = self.interfaces[name]
        table = C.cast(ptr, C.POINTER(C.POINTER(PTR))).contents
        return int(C.WINFUNCTYPE(restype, PTR, *argtypes)(table[index])(ptr, *args))

    def policy(self):
        value = U32()
        self.check(self.call("control", 53, [C.POINTER(U32)], C.byref(value)))
        requested = (value.value & ~ALLOW_NETWORK) | POLICY
        self.check(self.call("control", 56, [U32], requested))
        self.check(self.call("control", 53, [C.POINTER(U32)], C.byref(value)))
        if value.value & POLICY != POLICY or value.value & ALLOW_NETWORK:
            raise EngineFailure(0x80070005)
        return value.value

    def frame(self, address):
        index, base = U32(), U64()
        if self.call("symbols", 15, [U64, U32, C.POINTER(U32), C.POINTER(U64)], address, 0, C.byref(index), C.byref(base)) != 0:
            return project_frame(b"", address, 0, False)
        other_index, other_base = U32(), U64()
        if index.value == 0xFFFFFFFF or self.call("symbols", 15,
                [U64, U32, C.POINTER(U32), C.POINTER(U64)], address, index.value + 1,
                C.byref(other_index), C.byref(other_base)) == 0:
            return project_frame(b"", address, 0, False)
        name, size = C.create_string_buffer(128), U32()
        hr = self.call("symbols", 16,
            [U32, U64, PTR, U32, C.POINTER(U32), PTR, U32, C.POINTER(U32), PTR, U32, C.POINTER(U32)],
            index.value, base.value, None, 0, None, name, len(name), C.byref(size), None, 0, None)
        if hr != 0 or not 1 <= size.value <= len(name) or len(name.value) != size.value - 1:
            return project_frame(b"", address, 0, False)
        return project_frame(name.value, address, base.value, True)

    def threads(self, deadline):
        total = U32()
        self.check(self.call("systems", 9, [C.POINTER(U32)], C.byref(total)))
        count = min(total.value, 16)
        ids = (U32 * count)()
        self.check(self.call("systems", 11, [U32, U32, C.POINTER(U32), C.POINTER(U32)], 0, count, ids, None))
        result, truncated = [], total.value > 16
        for ident in ids:
            if time.monotonic() >= deadline:
                raise TimeoutError()
            if self.call("systems", 6, [U32], ident) != 0:
                truncated = True
                continue
            frames, filled = (Frame * 24)(), U32()
            self.check(self.call("control", 31, [U64, U64, U64, C.POINTER(Frame), U32, C.POINTER(U32)],
                                 0, 0, 0, frames, 24, C.byref(filled)))
            if filled.value > 24:
                raise EngineFailure(0x80004005)
            projected = []
            for frame in frames[:filled.value]:
                if time.monotonic() >= deadline:
                    raise TimeoutError()
                projected.append(self.frame(int(frame.ReturnOffset)))
            result.append({"frames": projected})
            truncated |= filled.value == 24
        return result, truncated

    def close(self):
        okay = True
        if "client" in self.interfaces:
            try:
                okay = self.call("client", 25, []) == 0
            except Exception:
                okay = False
        for name in reversed(tuple(self.interfaces)):
            try:
                self.call(name, 2, [], restype=U32)
            except Exception:
                okay = False
        self.interfaces.clear()
        return okay


class EngineFailure(Exception):
    def __init__(self, hr):
        self.hr = hr


def run(request, native, *, engine_factory=Engine):
    result = {"schemaVersion": 1, "status": "input_refused", "threads": [], "truncated": False,
              "pid": 0, "created": 0, "bound": False, "attached": False,
              "policy": 0, "detached": False, "hresult": None}
    engine, inherited = None, None
    try:
        fields = {"handle", "pid", "created", "image", "sdk", "hashes", "deadline"}
        version = 1
        if type(request) is dict and "schemaVersion" in request:
            version = request["schemaVersion"]
            if (type(version) is not int or version != 2 or type(request.get("profile")) is not str
                    or request["profile"] not in {"sdk-v1", "inbox-v1"}):
                return result
            fields.update(("schemaVersion", "profile"))
            result.update(schemaVersion=2, profile=request["profile"])
        if (type(request) is not dict or set(request) != fields
                or any(type(request[k]) is not int or request[k] <= 0 for k in ("handle", "pid", "created"))
                or request["handle"] >= 2**64 or request["pid"] > 0xFFFFFFFF or request["created"] >= 2**64
                or type(request["image"]) is not str or type(request["sdk"]) is not str
                or type(request["deadline"]) not in (int, float) or not math.isfinite(request["deadline"])):
            return result
        result.update(pid=request["pid"], created=request["created"])
        inherited = request["handle"]
        kernel = native.WindowsKernel()
        snapshot = kernel.snapshot(inherited)
        if (snapshot["pid"] != request["pid"] or snapshot["created"] != request["created"]
                or snapshot["state"] != "running" or native._regular(Path(snapshot["image"])) != native._regular(Path(request["image"]))):
            result["status"] = "identity_refused"
            return result
        result["bound"] = True
        deadline = min(request["deadline"], time.monotonic() + 5.0)
        if version == 2:
            sdk = native._bound_tool_profile(request["profile"], request["sdk"], request["hashes"], deadline)
        else:
            # Historical requests retain their original three-file SDK checks.
            sdk = native._regular(Path(request["sdk"]), directory=True)
            hashes = request["hashes"]
            if (type(hashes) is not dict or set(hashes) != {"cdb.exe", "dbgeng.dll", "dbghelp.dll"}
                    or any(type(v) is not str or len(v) != 64 or any(c not in "0123456789abcdef" for c in v)
                           for v in hashes.values())):
                return result
            for name, digest in hashes.items():
                if native._digest(sdk / name, deadline) != digest:
                    return result
        if time.monotonic() >= deadline:
            raise TimeoutError()
        engine = engine_factory(sdk)
        result["policy"] = engine.policy()
        if result["policy"] & POLICY != POLICY or result["policy"] & ALLOW_NETWORK:
            raise EngineFailure(0x80070005)
        if time.monotonic() >= deadline:
            raise TimeoutError()
        engine.check(engine.call("client", 12, [U64, U32, U32], 0, snapshot["pid"], 1))
        result["attached"] = True
        remaining = max(0, min(5000, int((deadline - time.monotonic()) * 1000)))
        wait = engine.call("control", 93, [U32, U32], 0, remaining)
        if wait == 1:
            raise TimeoutError()
        engine.check(wait)
        result["threads"], result["truncated"] = engine.threads(deadline)
        result["status"] = "captured" if any(f["module"] != "Other" for t in result["threads"] for f in t["frames"]) else "unrecognized"
        result["hresult"] = 0
    except TimeoutError:
        result.update(status="deadline", threads=[])
    except EngineFailure as error:
        result.update(status="engine_failed", threads=[], hresult=error.hr)
    except Exception:
        result.update(status="engine_failed", threads=[])
    finally:
        if engine is not None:
            try:
                result["detached"] = engine.close()
            except Exception:
                result["detached"] = False
            if not result["detached"]:
                result.update(status="cleanup_unknown", threads=[])
        if inherited is not None:
            try:
                kernel.close(inherited)
            except Exception:
                result.update(status="cleanup_unknown", threads=[])
    return result


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit(2)
    try:
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096:
            raise ValueError("input bound")
        spec = importlib.util.spec_from_file_location("worker_native_owner", Path(__file__).with_name("_windows_rpc_timeout.py"))
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
        report = run(json.loads(raw), native)
        encoded = (json.dumps(report, separators=(",", ":")) + "\n").encode("utf-8")
        if len(encoded) > MAX_JSON:
            raise ValueError("output bound")
        sys.stdout.buffer.write(encoded)
    except Exception:
        raise SystemExit(1)
