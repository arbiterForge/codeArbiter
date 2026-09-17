#!/usr/bin/env python3
"""Bounded stdlib bridge to an installation-pinned ca-artifact executable.

No imports perform I/O. No PATH search, environment-selected executable, schema
parser duplication, command execution from a document, or new host registration.
The caller supplies a trusted installation directory, never a repository setting.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import tempfile
import threading
from typing import Any

PROTOCOL = "codearbiter.artifact-api/0.1.0"
SCHEMA_VERSION = "0.3.1"
MAX_REQUEST = 8 << 20
MAX_RESPONSE = 65536
READ_OPERATIONS = frozenset({"capabilities", "schema", "read", "outline", "identity", "validate", "index", "snapshot", "diff", "repair-preview", "eligible", "farm-verify", "migration-preview"})


class ArtifactError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ArtifactError("INVALID_RESPONSE", "duplicate JSON key")
        value[key] = item
    return value


def _decode(raw: bytes) -> Any:
    if len(raw) > MAX_RESPONSE:
        raise ArtifactError("INVALID_RESPONSE", "oversized JSON envelope")
    # Bound nesting independently of the interpreter's recursion-limit setting.
    depth = 0
    quoted = escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 128:
                raise ArtifactError("INVALID_RESPONSE", "JSON nesting exceeds 128 levels")
        elif byte in (93, 125):
            depth -= 1
    try:
        return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ArtifactError("INVALID_RESPONSE", "invalid bounded JSON") from exc


def helper_installation(helper_file: str) -> Path:
    """Shipped helpers live in <plugin>/hooks; the trusted payload is a sibling.

    Source-checkout callers use an explicit installation instead of guessing a
    binary under the repository being governed.
    """
    return Path(helper_file).resolve().parent.parent / "helpers" / "artifacts"


def _open_pinned_regular(path: Path) -> int:
    """Open without following the final link and pin Windows replacement.

    The Windows handle shares reads only, so a verified executable cannot be
    replaced or opened for writing before CreateProcess consumes its path.
    """
    if os.name != "nt":
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        return os.open(path, flags)
    import ctypes
    import msvcrt
    create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    create_file.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                            ctypes.c_void_p]
    create_file.restype = ctypes.c_void_p
    handle = create_file(str(path), 0x80000000, 0x00000001, None, 3,
                         0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "CreateFileW failed", str(path))
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDONLY)
    except BaseException:
        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)
        raise


def _stage_darwin_executable(fd: int, directory: Path) -> Path:
    """Materialize verified descriptor bytes for macOS executable launch.

    macOS exposes inherited descriptors below /dev/fd but does not permit
    executing a native binary through that path. The caller supplies a fresh,
    private temporary directory; no installation or repository pathname is
    reopened while producing the executable image.
    """
    target = directory / "ca-artifact"
    output = os.open(
        target,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        stat.S_IRUSR | stat.S_IWUSR,
    )
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        while chunk := os.read(fd, 1 << 20):
            remaining = memoryview(chunk)
            while remaining:
                written = os.write(output, remaining)
                if written <= 0:
                    raise OSError("short write while staging verified executable")
                remaining = remaining[written:]
        os.fsync(output)
        os.fchmod(output, stat.S_IRUSR | stat.S_IXUSR)
    finally:
        os.close(output)
    return target


def _trusted_directory(path: str | Path, code: str) -> Path:
    requested = Path(path).absolute()
    try:
        if os.name == "nt":
            import ctypes
            attributes = ctypes.WinDLL("kernel32", use_last_error=True).GetFileAttributesW
            attributes.argtypes = [ctypes.c_wchar_p]
            attributes.restype = ctypes.c_uint32
            current = requested
            while current != current.parent:
                value = attributes(str(current))
                if value == 0xffffffff or value & 0x400:
                    raise OSError("reparse point or unreadable component")
                current = current.parent
        elif Path(os.path.realpath(requested)) != requested:
            raise OSError("symlink component")
        resolved = requested.resolve(strict=True)
        if not resolved.is_dir():
            raise OSError("not a directory")
        return resolved
    except OSError as exc:
        raise ArtifactError(code, "directory must be an existing real path without links or reparse points") from exc


def _bounded_child(argv: list[str], request: bytes, fd: int, timeout: float) -> tuple[int, bytes, bytes]:
    options = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   close_fds=True, start_new_session=True, env={})
    if os.name != "nt":
        options["pass_fds"] = (fd,)
    process = subprocess.Popen(argv, **options)
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()

    def drain(pipe, slot, limit):
        try:
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    return
                if len(buffers[slot]) + len(chunk) > limit:
                    overflow.set()
                    process.kill()
                    return
                buffers[slot].extend(chunk)
        finally:
            pipe.close()

    def write():
        try:
            process.stdin.write(request)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    threads = [threading.Thread(target=drain, args=(process.stdout, 0, MAX_RESPONSE), daemon=True),
               threading.Thread(target=drain, args=(process.stderr, 1, 8192), daemon=True),
               threading.Thread(target=write, daemon=True)]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
    for thread in threads:
        thread.join(timeout=2)
    if timed_out:
        raise ArtifactError("TIMEOUT", "subprocess interrupted; reconcile mutation operation_id before retry")
    if overflow.is_set() or any(t.is_alive() for t in threads):
        raise ArtifactError("RESPONSE_TOO_LARGE", "subprocess output exceeded its contract")
    return process.returncode, bytes(buffers[0]), bytes(buffers[1])


class ArtifactClient:
    def __init__(self, root: str | Path, installation: str | Path, *, timeout: float = 30):
        self.root = _trusted_directory(root, "UNSAFE_ROOT")
        self.installation = _trusted_directory(installation, "CAPABILITY_MISSING")
        self.timeout = timeout

    def _open_binary(self) -> int:
        system = {"Linux":"linux", "Darwin":"darwin", "Windows":"windows"}.get(platform.system())
        arch = {"x86_64":"amd64", "amd64":"amd64", "aarch64":"arm64", "arm64":"arm64"}.get(platform.machine().lower())
        if system is None or arch is None:
            raise ArtifactError("UNSUPPORTED_PLATFORM", "unsupported architecture")
        manifest_path = self.installation / "release.json"
        try:
            mf = _open_pinned_regular(manifest_path)
            try:
                info = os.fstat(mf)
                if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                    raise ArtifactError("INVALID_INSTALLATION", "release manifest must be a bounded regular file")
                raw = os.read(mf, 65537)
                if len(raw) > 65536:
                    raise ArtifactError("INVALID_INSTALLATION", "oversized release manifest")
            finally:
                os.close(mf)
            try:
                manifest = _decode(raw)
            except ArtifactError as exc:
                raise ArtifactError("INVALID_INSTALLATION", "invalid release manifest JSON") from exc
            if not isinstance(manifest, dict) or set(manifest) != {"format", "version", "protocol", "schema_version", "binaries"}:
                raise ArtifactError("INVALID_INSTALLATION", "unexpected release manifest")
            if manifest["format"] != "codearbiter.artifact-release/0.1.0" or manifest["protocol"] != PROTOCOL or manifest["schema_version"] != SCHEMA_VERSION:
                raise ArtifactError("UNSUPPORTED_VERSION", "installed binary/adapter version mismatch")
            if not isinstance(manifest["binaries"], dict) or not isinstance(manifest["version"], str):
                raise ArtifactError("INVALID_INSTALLATION", "malformed release manifest fields")
            entry = manifest["binaries"].get(f"{system}/{arch}")
            if not isinstance(entry, dict) or set(entry) != {"file", "sha256", "native_tested"}:
                raise ArtifactError("CAPABILITY_MISSING", "no matching tested binary in the installation")
            if entry["native_tested"] is not True:
                raise ArtifactError("UNVERIFIED_PLATFORM", "cross-compilation is not native qualification")
            name = entry["file"]
            expected_name = f"ca-artifact-{system}-{arch}" + (".exe" if system == "windows" else "")
            if name != expected_name:
                raise ArtifactError("INVALID_INSTALLATION", "binary filename does not match the selected platform")
            if not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
                raise ArtifactError("INVALID_INSTALLATION", "binary digest is malformed")
            binary_path = self.installation / name
            fd = _open_pinned_regular(binary_path)
        except OSError as exc:
            raise ArtifactError("CAPABILITY_MISSING", "install the pinned artifact payload; no PATH fallback is permitted") from exc
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_size > 32 << 20
                    or (system != "windows" and not info.st_mode & stat.S_IXUSR)):
                raise ArtifactError("INVALID_INSTALLATION", "binary is not a bounded executable regular file")
            digest = hashlib.sha256()
            while chunk := os.read(fd, 1 << 20):
                digest.update(chunk)
            if digest.hexdigest() != entry["sha256"]:
                raise ArtifactError("PACKAGE_INTEGRITY", "installed executable bytes differ from release manifest")
            os.lseek(fd, 0, os.SEEK_SET)
            header = os.read(fd, 4)
            magic = {"linux":(b"\x7fELF",), "darwin":(b"\xcf\xfa\xed\xfe",b"\xca\xfe\xba\xbe",b"\xbe\xba\xfe\xca"), "windows":(b"MZ",)}[system]
            if not header.startswith(magic):
                raise ArtifactError("INVALID_INSTALLATION", "unexpected native executable format")
            os.lseek(fd, 0, os.SEEK_SET)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def call(self, operation: str, request: dict[str, Any] | None = None, *, permit_invalid: bool = False) -> dict:
        if not re.fullmatch(r"[a-z][a-z-]{0,39}", operation):
            raise ArtifactError("UNKNOWN_OPERATION", "invalid internal operation name")
        request = dict(request or {})
        if "protocol" in request and request["protocol"] != PROTOCOL:
            raise ArtifactError("UNSUPPORTED_VERSION", "request protocol mismatch")
        request["protocol"] = PROTOCOL
        try:
            raw = json.dumps(request, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
        except (TypeError, ValueError) as exc:
            raise ArtifactError("INVALID_REQUEST", "request must contain finite JSON values") from exc
        if len(raw) > MAX_REQUEST:
            raise ArtifactError("REQUEST_TOO_LARGE", "request exceeds 8 MiB")
        fd = self._open_binary()
        try:
            # Execute the verified open descriptor, not a raceable pathname.
            if platform.system() == "Linux":
                executable = f"/proc/self/fd/{fd}"
            elif platform.system() == "Darwin":
                with tempfile.TemporaryDirectory(prefix="ca-artifact-exec-") as temporary:
                    try:
                        directory = Path(os.path.realpath(temporary))
                        executable = _stage_darwin_executable(fd, directory)
                        os.chmod(directory, stat.S_IRUSR | stat.S_IXUSR)
                        code, stdout, stderr = _bounded_child(
                            [str(executable), operation, "--root", str(self.root), "--request", "-"],
                            raw, fd, self.timeout)
                    except OSError as exc:
                        raise ArtifactError(
                            "CAPABILITY_MISSING",
                            "could not stage the verified macOS artifact executable",
                        ) from exc
                    finally:
                        os.chmod(directory, stat.S_IRWXU)
                executable = None
            else:
                executable = str(self.installation / self._binary_name())
            if executable is not None:
                code, stdout, stderr = _bounded_child(
                    [executable, operation, "--root", str(self.root), "--request", "-"],
                    raw, fd, self.timeout)
        finally:
            os.close(fd)
        result = _decode(stdout)
        if not isinstance(result, dict) or result.get("protocol") != PROTOCOL or result.get("operation") != operation or not isinstance(result.get("ok"), bool):
            raise ArtifactError("INVALID_RESPONSE", "subprocess response does not match request")
        if not result["ok"]:
            error = result.get("error")
            if (set(result) != {"protocol", "operation", "ok", "error"}
                    or not isinstance(error, dict)
                    or not {"code", "message"} <= set(error)
                    or set(error) - {"code", "message", "symbol", "field", "operation_id"}
                    or any(not isinstance(v, str) for v in error.values())
                    or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", error["code"])
                    or code == 0):
                raise ArtifactError("INVALID_RESPONSE", "malformed failure envelope")
            raise ArtifactError(error["code"], error["message"][:512])
        if set(result) != {"protocol", "operation", "ok", "result"} or not isinstance(result.get("result"), dict):
            raise ArtifactError("INVALID_RESPONSE", "malformed success envelope")
        if code != 0 and not (permit_invalid and operation == "validate" and code == 2 and result["result"].get("valid") is False):
            raise ArtifactError("SUBPROCESS_FAILED", f"operation returned exit {code}")
        if not isinstance(result.get("result"), dict):
            raise ArtifactError("INVALID_RESPONSE", "subprocess result must be an object")
        return result["result"]

    @staticmethod
    def _binary_name() -> str:
        system = {"Linux":"linux", "Darwin":"darwin", "Windows":"windows"}[platform.system()]
        arch = {"x86_64":"amd64", "amd64":"amd64", "aarch64":"arm64", "arm64":"arm64"}[platform.machine().lower()]
        return f"ca-artifact-{system}-{arch}" + (".exe" if system == "windows" else "")

    @staticmethod
    def _check_page(page: dict, offset: int, field: str):
        values = page.get(field)
        if not isinstance(values, list) or "next_offset" not in page:
            raise ArtifactError("INVALID_RESPONSE", "malformed bounded page")
        next_offset = page["next_offset"]
        if next_offset is not None and (type(next_offset) is not int or next_offset <= offset or not values):
            raise ArtifactError("INVALID_RESPONSE", "pagination must make forward progress")

    def index(self, kind: str | None = None):
        request = {"budget": 16384}
        if kind:
            request["kind"] = kind
        for _ in range(1025):
            page = self.call("index", request)
            self._check_page(page, request.get("offset", 0), "entries")
            yield from page["entries"]
            if page["next_offset"] is None:
                return
            request.update(offset=page["next_offset"], catalog_sha256=page["catalog_sha256"])
        raise ArtifactError("INVALID_RESPONSE", "index did not terminate")

    def outline(self, artifact_id: str):
        request = {"artifact_id": artifact_id, "budget": 16384}
        for _ in range(8193):
            page = self.call("outline", request)
            self._check_page(page, request.get("offset", 0), "records")
            yield from page["records"]
            if page["next_offset"] is None:
                return
            request.update(offset=page["next_offset"], model_sha256=page["model_sha256"])
        raise ArtifactError("INVALID_RESPONSE", "outline did not terminate")

    def contextual_pages(self, artifact_id: str, symbol: str, budget: int = 16384):
        request = {"artifact_id": artifact_id, "symbol": symbol, "mode": "contextual", "budget": budget}
        for _ in range(8193):
            page = self.call("read", request)
            complete = page.get("context_complete")
            if type(complete) is not bool:
                raise ArtifactError("INVALID_RESPONSE", "context page lacks a completeness flag")
            if not complete and (not page.get("next_cursor") or page["next_cursor"] == request.get("cursor")):
                raise ArtifactError("INCOMPLETE_CONTEXT", "incomplete context must have an advancing continuation")
            yield page
            if complete:
                return
            request["cursor"] = page["next_cursor"]
        raise ArtifactError("INVALID_RESPONSE", "context did not terminate")


def has_html(root: str | Path) -> bool:
    root = Path(root)
    return any(
        next((root / ".codearbiter" / kind).glob("*.html"), None) is not None for kind in ("specs", "plans"))


def checked_spec_index(root, installation) -> list[dict]:
    """Fresh per-call authority validation, deliberately not an mtime cache."""
    if not has_html(root):
        return []
    client = ArtifactClient(root, installation)
    return [{"spec": x["artifact_id"], "path": x["path"], "globs": x.get("governs") or [], "artifact_html": True}
            for x in client.index("spec") if x["authority"]["authority_verified"] and x.get("governs")]


def resolve_spec_file(filename, installation) -> tuple[ArtifactClient, dict]:
    path = Path(filename).absolute()
    if path.suffix != ".html" or path.parent.name != "specs" or path.parent.parent.name != ".codearbiter":
        raise ArtifactError("INVALID_PATH", "expected canonical HTML spec path")
    root = path.parent.parent.parent
    client = ArtifactClient(root, installation)
    relative = path.relative_to(root).as_posix()
    matches = [x for x in client.index("spec") if x["path"] == relative]
    if len(matches) != 1:
        raise ArtifactError("SPEC_NOT_FOUND", "canonical path did not resolve uniquely")
    return client, matches[0]
