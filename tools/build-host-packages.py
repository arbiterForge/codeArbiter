#!/usr/bin/env python3
"""Generate dependency-free host package metadata from canonical descriptors."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_descriptors import HostDescriptor, host_descriptor, load_host_descriptors  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

# Issue #530 AC-3: "advance" must mean ONE thing across all four payload gates.
# This guard is the one that already had the rule right, so the definition moved
# to _releaselib (where RELEASE_TAG_PREFIXES already lives) and the other three
# adopted it rather than each carrying a copy that can drift apart.
sys.path.insert(0, str(REPO / ".github" / "scripts"))
from _releaselib import SEMVER, semver_greater, semver_key  # noqa: E402,F401

ARTIFACT_RELEASE_FORMAT = "codearbiter.artifact-release/0.1.0"
ARTIFACT_QUALIFICATION_FORMAT = "codearbiter.artifact-qualification/0.1.0"
ARTIFACT_PROMOTION_FORMAT = "codearbiter.artifact-promotion/0.1.0"
ARTIFACT_COLD_EXECUTION_FORMAT = "codearbiter.artifact-cold-execution/0.1.0"
ARTIFACT_PACKAGE_FORMAT = "codearbiter.artifact-package-cohort/0.1.0"
NPM_PACKER_NAME = "npm"
NPM_PACKER_VERSION = "11.19.1"
NPM_PACKER_INTEGRITY = (
    "sha512-ztsxKxt/kkIaAs+2i0GU6I+DRmUdrNasxTZKJe9TCdSjKxlhah/4r/hl5ygMD6XAg1qZ9c2TNomR4qgOydp10g=="
)
ARTIFACT_PROTOCOL = "codearbiter.artifact-api/0.1.0"
ARTIFACT_SCHEMA_VERSION = "0.3.1"
ARTIFACT_VERSION = "0.1.0"
ARTIFACT_NATIVE_TESTS = frozenset({
    "artifact-bridge", "artifact-conformance", "artifact-native", "artifact-package",
    "go-test", "go-vet",
})
ARTIFACT_PLATFORMS = frozenset({
    "linux/amd64", "linux/arm64", "darwin/amd64", "darwin/arm64",
    "windows/amd64", "windows/arm64",
})


def _artifact_installer_module():
    path = REPO / "tools" / "install-artifact-payload.py"
    spec = importlib.util.spec_from_file_location("install_artifact_payload", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load artifact payload verifier: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _artifact_candidate(candidate: Path) -> tuple[dict, str, str, bytes]:
    """Return one native-tested candidate after the shared payload verifier passes."""
    source = candidate.absolute()
    if (source.is_symlink() or not source.is_dir()
            or os.path.normcase(str(source.resolve(strict=True))) != os.path.normcase(str(source))):
        raise ValueError(f"artifact candidate must be a real directory: {candidate}")
    installer = _artifact_installer_module()
    try:
        manifest_bytes, payload = installer.load_payload(source)
    except ValueError as error:
        if "unsupported payload manifest" in str(error):
            raise ValueError(
                "artifact candidate has unsupported protocol/schema/version identity"
            ) from error
        raise
    manifest = json.loads(manifest_bytes, object_pairs_hook=installer._pairs)
    entries = manifest["binaries"]
    if len(entries) != 1 or len(payload) != 1:
        raise ValueError("each artifact candidate must carry exactly one native platform receipt")
    platform_name, entry = next(iter(entries.items()))
    if platform_name not in ARTIFACT_PLATFORMS:
        raise ValueError(f"unsupported native platform: {platform_name}")
    filename = entry["file"]
    return manifest, platform_name, filename, payload[filename]


def _artifact_qualification(path: Path, candidate: Path, installer) -> tuple[dict, bytes]:
    source = path.absolute()
    candidate_root = candidate.absolute()
    if (source.is_symlink()
            or os.path.normcase(str(source.resolve(strict=True))) != os.path.normcase(str(source))):
        raise ValueError("qualification receipt must be a real file without linked ancestors")
    if source.resolve(strict=True).is_relative_to(candidate_root.resolve(strict=True)):
        raise ValueError("qualification receipt must be supplied independently of its candidate")
    raw = installer.read_regular(source, 65_536)
    receipt = json.loads(raw, object_pairs_hook=installer._pairs)
    expected = {
        "format", "source_commit", "workflow", "run_id", "job", "platform",
        "binary_sha256", "version", "protocol", "schema_version", "native_tests",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected:
        raise ValueError("qualification receipt has an unexpected shape")
    return receipt, raw


def _binary_matches_platform(platform_name: str, data: bytes) -> bool:
    system, architecture = platform_name.split("/", 1)
    if system == "linux":
        if len(data) < 20 or data[:4] != b"\x7fELF" or data[4] != 2:
            return False
        byteorder = {1: "little", 2: "big"}.get(data[5])
        if byteorder is None:
            return False
        machine = int.from_bytes(data[18:20], byteorder)
        return machine == {"amd64": 62, "arm64": 183}[architecture]
    if system == "windows":
        if len(data) < 64 or data[:2] != b"MZ":
            return False
        pe_offset = int.from_bytes(data[0x3C:0x40], "little")
        if pe_offset < 64 or pe_offset + 6 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\0\0":
            return False
        machine = int.from_bytes(data[pe_offset + 4:pe_offset + 6], "little")
        return machine == {"amd64": 0x8664, "arm64": 0xAA64}[architecture]
    if system == "darwin":
        if len(data) < 8 or data[:4] != b"\xcf\xfa\xed\xfe":
            return False
        cpu_type = int.from_bytes(data[4:8], "little")
        return cpu_type == {"amd64": 0x01000007, "arm64": 0x0100000C}[architecture]
    return False


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short artifact package write")
        view = view[written:]


class _UnixArtifactStage:
    def __init__(self, output: Path, parent_fd: int, root_fd: int):
        self.output = output
        self._fds = {(): root_fd}
        self._parent_fd = parent_fd

    def _directory(self, parts: tuple[str, ...], *, new_leaf: bool = False) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        for index in range(1, len(parts) + 1):
            prefix = parts[:index]
            if prefix in self._fds:
                continue
            parent = self._fds[prefix[:-1]]
            try:
                os.mkdir(prefix[-1], 0o755, dir_fd=parent)
            except FileExistsError as error:
                if new_leaf and index == len(parts):
                    raise ValueError("artifact package payload target already exists") from error
            self._fds[prefix] = os.open(prefix[-1], flags, dir_fd=parent)
        return self._fds[parts]

    def write_payload(self, parts: tuple[str, ...], manifest_bytes: bytes,
                      binaries: dict[str, bytes]) -> None:
        directory = self._directory(parts, new_leaf=True)
        for filename in sorted(binaries):
            fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW | os.O_CLOEXEC, 0o755, dir_fd=directory)
            try:
                _write_all(fd, binaries[filename])
                os.fsync(fd)
                os.fchmod(fd, 0o755)
            finally:
                os.close(fd)
        fd = os.open("release.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
        try:
            _write_all(fd, manifest_bytes)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory)

    def write_root_file(self, filename: str, data: bytes) -> None:
        fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self._fds[()])
        try:
            _write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self._fds[()])

    def verify(self) -> None:
        current = os.stat(self.output, follow_symlinks=False)
        pinned = os.fstat(self._fds[()])
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (
                pinned.st_dev, pinned.st_ino):
            raise ValueError("artifact staging root was replaced during packaging")

    def close(self) -> None:
        for fd in reversed(tuple(self._fds.values())):
            os.close(fd)
        os.close(self._parent_fd)


class _WindowsArtifactStage:
    def __init__(self, output: Path, handles: list[object]):
        self.output = output
        self._handles = handles
        self._pinned: dict[Path, object] = {output: handles[-1]}

    def _directory(self, parts: tuple[str, ...], *, new_leaf: bool = False) -> Path:
        current = self.output
        for index, part in enumerate(parts, start=1):
            current = current / part
            if current not in self._pinned:
                try:
                    current.mkdir()
                except FileExistsError as error:
                    if new_leaf and index == len(parts):
                        raise ValueError("artifact package payload target already exists") from error
                handle = _pin_windows_directory(current)
                self._handles.append(handle)
                self._pinned[current] = handle
        return current

    def write_payload(self, parts: tuple[str, ...], manifest_bytes: bytes,
                      binaries: dict[str, bytes]) -> None:
        directory = self._directory(parts, new_leaf=True)
        for filename in sorted(binaries):
            with (directory / filename).open("xb") as stream:
                stream.write(binaries[filename])
                stream.flush()
                os.fsync(stream.fileno())
        with (directory / "release.json").open("xb") as stream:
            stream.write(manifest_bytes)
            stream.flush()
            os.fsync(stream.fileno())

    def write_root_file(self, filename: str, data: bytes) -> None:
        with (self.output / filename).open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

    def verify(self) -> None:
        try:
            _verify_windows_handle_path(self._pinned[self.output], self.output)
        except ValueError as error:
            raise ValueError("artifact staging root was replaced during packaging") from error


def _normal_windows_path(value: str | Path) -> str:
    text = str(value)
    if text.startswith("\\\\?\\UNC\\"):
        text = "\\\\" + text[8:]
    elif text.startswith("\\\\?\\"):
        text = text[4:]
    return os.path.normcase(os.path.abspath(text))


def _verify_windows_handle_path(handle, expected: Path) -> None:
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR,
                                                   wintypes.DWORD, wintypes.DWORD]
    size = kernel32.GetFinalPathNameByHandleW(handle, None, 0, 0)
    if not size:
        raise OSError(ctypes.get_last_error(), "cannot resolve pinned staging directory")
    buffer = ctypes.create_unicode_buffer(size + 1)
    if not kernel32.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0):
        raise OSError(ctypes.get_last_error(), "cannot resolve pinned staging directory")
    if _normal_windows_path(buffer.value) != _normal_windows_path(expected):
        raise ValueError("artifact staging directory resolves through a linked ancestor")


def _pin_windows_directory(path: Path):
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    attributes = kernel32.GetFileAttributesW(str(path))
    invalid_attributes = 0xFFFFFFFF
    directory_attribute = 0x10
    reparse_attribute = 0x400
    if (attributes == invalid_attributes or not attributes & directory_attribute
            or attributes & reparse_attribute):
        raise ValueError("artifact staging path must be a real directory without reparse points")
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                     wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                     wintypes.HANDLE]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    handle = kernel32.CreateFileW(str(path), 0x80, 0x1 | 0x2, None, 3,
                                  0x02000000 | 0x00200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), f"cannot pin staging directory: {path}")
    try:
        _verify_windows_handle_path(handle, path)
    except BaseException:
        kernel32.CloseHandle(handle)
        raise
    return handle


def _open_unix_parent(path: Path, flags: int) -> int:
    return os.open(path, flags)


@contextmanager
def _pinned_artifact_stage(output: Path):
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError(f"artifact staging output already exists: {output}")
    parent = output.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("artifact staging parent must be an already-existing real directory")
    if os.path.normcase(str(parent.resolve(strict=True))) != os.path.normcase(str(parent)):
        raise ValueError("artifact staging parent must be an already-existing real directory")
    parent_identity = os.stat(parent, follow_symlinks=False)
    if os.name == "nt":
        parent_handle = _pin_windows_directory(parent)
        handles = [parent_handle]
        try:
            output.mkdir(exist_ok=False)
            output_handle = _pin_windows_directory(output)
            handles.append(output_handle)
            stage = _WindowsArtifactStage(output, handles)
            yield stage
            stage.verify()
        finally:
            for handle in reversed(handles):
                import ctypes
                ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)
        return
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    parent_fd = _open_unix_parent(parent, flags)
    opened_identity = os.fstat(parent_fd)
    if (opened_identity.st_dev, opened_identity.st_ino) != (
            parent_identity.st_dev, parent_identity.st_ino):
        os.close(parent_fd)
        raise ValueError("artifact staging parent changed during validation")
    try:
        os.mkdir(output.name, 0o755, dir_fd=parent_fd)
        root_fd = os.open(output.name, flags, dir_fd=parent_fd)
    except BaseException:
        os.close(parent_fd)
        raise
    stage = _UnixArtifactStage(output, parent_fd, root_fd)
    try:
        yield stage
        stage.verify()
    finally:
        stage.close()


def stage_artifact_host_payloads(*, candidates: list[Path],
                                 qualification_receipts: list[Path],
                                 trusted_source_commit: str,
                                 trusted_workflow: str,
                                 trusted_workflow_run: str,
                                 output: Path,
                                 required_platforms: list[str],
                                 repo: Path = REPO) -> dict[str, object]:
    """Create a release-only overlay containing verified payloads for every host.

    The destination is create-only and outside the source packages. Applying the
    overlay to a release candidate is the reviewed packaging copy boundary; this
    function never enables a checkout or falls back to PATH, Go, or a network.
    """
    if not candidates:
        raise ValueError("at least one artifact candidate is required")
    if len(qualification_receipts) != len(candidates):
        raise ValueError("each artifact candidate requires one independent qualification receipt")
    if not re.fullmatch(r"[0-9a-f]{40}", trusted_source_commit):
        raise ValueError("trusted source commit must be a full lowercase commit id")
    if trusted_workflow != ".github/workflows/ci.yml":
        raise ValueError("artifact qualification must originate from the protected CI workflow")
    if not re.fullmatch(r"[1-9][0-9]*", trusted_workflow_run):
        raise ValueError("trusted workflow run must be a positive decimal run id")
    required = sorted(set(required_platforms))
    if not required or len(required) != len(required_platforms):
        raise ValueError("required native platforms must be non-empty and unique")
    unknown = set(required) - ARTIFACT_PLATFORMS
    if unknown:
        raise ValueError(f"unsupported required native platform: {', '.join(sorted(unknown))}")

    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError(f"artifact staging output already exists: {output}")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise ValueError("artifact staging parent must be an already-existing real directory")

    binaries: dict[str, bytes] = {}
    entries: dict[str, dict[str, object]] = {}
    qualifications: dict[str, dict[str, object]] = {}
    identity: tuple[str, str, str] | None = None
    installer = _artifact_installer_module()
    for candidate, qualification_path in zip(candidates, qualification_receipts, strict=True):
        manifest, platform_name, filename, data = _artifact_candidate(candidate)
        current_identity = (manifest["version"], manifest["protocol"], manifest["schema_version"])
        if (current_identity[0] != ARTIFACT_VERSION or SEMVER.fullmatch(current_identity[0]) is None):
            raise ValueError(f"candidate does not declare the supported artifact version {ARTIFACT_VERSION}")
        if current_identity[1:] != (ARTIFACT_PROTOCOL, ARTIFACT_SCHEMA_VERSION):
            raise ValueError("artifact candidates disagree with the supported protocol/schema/version identity")
        if identity is None:
            identity = current_identity
        elif current_identity != identity:
            raise ValueError("artifact candidates disagree on protocol/schema/version identity")
        if platform_name in entries:
            raise ValueError(f"duplicate native platform candidate: {platform_name}")
        entry = manifest["binaries"][platform_name]
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"artifact candidate changed after verification: {platform_name}")
        if not _binary_matches_platform(platform_name, data):
            raise ValueError(f"artifact candidate does not match its declared native architecture: {platform_name}")
        receipt, receipt_bytes = _artifact_qualification(qualification_path, candidate, installer)
        expected_receipt = {
            "format": ARTIFACT_QUALIFICATION_FORMAT,
            "source_commit": trusted_source_commit,
            "workflow": trusted_workflow,
            "run_id": trusted_workflow_run,
            "job": "artifact-engine",
            "platform": platform_name,
            "binary_sha256": entry["sha256"],
            "version": current_identity[0],
            "protocol": current_identity[1],
            "schema_version": current_identity[2],
            "native_tests": sorted(ARTIFACT_NATIVE_TESTS),
        }
        if receipt != expected_receipt:
            raise ValueError(
                f"qualification receipt is not bound to the trusted native result for {platform_name}"
            )
        entries[platform_name] = dict(entry)
        binaries[filename] = data
        qualifications[platform_name] = {
            "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "job": receipt["job"],
            "binary_sha256": receipt["binary_sha256"],
            "native_tests": receipt["native_tests"],
        }

    missing = set(required) - set(entries)
    extra = set(entries) - set(required)
    if missing:
        raise ValueError(f"missing required native-tested platform: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"undeclared native platform candidate: {', '.join(sorted(extra))}")
    assert identity is not None
    release = {
        "format": ARTIFACT_RELEASE_FORMAT,
        "version": identity[0],
        "protocol": identity[1],
        "schema_version": identity[2],
        "binaries": {name: entries[name] for name in sorted(entries)},
    }
    release_bytes = (json.dumps(release, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    hosts = sorted(load_host_descriptors(str(repo)), key=lambda host: host.name)
    host_payloads = {
        host.name: "/".join((*host.plugin_dir.split("/"), "helpers", "artifacts"))
        for host in hosts
    }
    payload_hashes = {
        "release.json": hashlib.sha256(release_bytes).hexdigest(),
        **{filename: hashlib.sha256(data).hexdigest()
           for filename, data in sorted(binaries.items())},
    }
    promotion = {
        "format": ARTIFACT_PROMOTION_FORMAT,
        "source_commit": trusted_source_commit,
        "workflow": trusted_workflow,
        "run_id": trusted_workflow_run,
        "version": identity[0],
        "protocol": identity[1],
        "schema_version": identity[2],
        "hosts": host_payloads,
        "qualifications": {name: qualifications[name] for name in sorted(qualifications)},
        "payload": payload_hashes,
    }
    promotion_bytes = (json.dumps(promotion, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    with _pinned_artifact_stage(output) as stage:
        for host in hosts:
            parts = tuple(host.plugin_dir.split("/")) + ("helpers", "artifacts")
            stage.write_payload(parts, release_bytes, binaries)
        stage.write_root_file("artifact-promotion.json", promotion_bytes)
    return {
        "format": ARTIFACT_RELEASE_FORMAT,
        "version": identity[0],
        "protocol": identity[1],
        "schema_version": identity[2],
        "platforms": required,
        "hosts": [host.name for host in hosts],
        "output": str(output),
        "source_commit": trusted_source_commit,
        "workflow": trusted_workflow,
        "workflow_run": trusted_workflow_run,
        "promotion_receipt": str(output / "artifact-promotion.json"),
        "promotion_receipt_sha256": hashlib.sha256(promotion_bytes).hexdigest(),
        "host_default_enabled": False,
    }


def _git_package_output(*args: str, repo: Path, binary: bool = False):
    completed = subprocess.run(
        ["git", *args], cwd=repo, check=False, capture_output=True,
        text=not binary, encoding=None if binary else "utf-8",
    )
    if completed.returncode != 0:
        error = completed.stderr if isinstance(completed.stderr, str) else completed.stderr.decode(
            "utf-8", errors="replace")
        raise ValueError(f"cannot read exact package source from Git: {error[-512:]}")
    return completed.stdout


def _source_identity(source_repo: Path, source_commit: str) -> str:
    source_repo = source_repo.absolute()
    if (source_repo.is_symlink() or not source_repo.is_dir()
            or os.path.normcase(str(source_repo.resolve(strict=True))) !=
            os.path.normcase(str(source_repo))):
        raise ValueError("package source repository must be a real directory")
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("package source commit must be a full lowercase commit id")
    resolved = _git_package_output(
        "rev-parse", f"{source_commit}^{{commit}}", repo=source_repo
    ).strip()
    if resolved != source_commit:
        raise ValueError("package source commit did not resolve exactly")
    return _git_package_output(
        "rev-parse", f"{source_commit}^{{tree}}", repo=source_repo
    ).strip()


def _git_archive_files(source_repo: Path, source_commit: str,
                       paths: tuple[str, ...]) -> dict[str, tuple[bytes, int, str, str]]:
    raw = _git_package_output(
        "archive", "--format=tar", source_commit, "--", *paths,
        repo=source_repo, binary=True,
    )
    files: dict[str, tuple[bytes, int, str, str]] = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive.getmembers():
            name = member.name.rstrip("/")
            if not name or member.isdir():
                continue
            if not member.isfile() or name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"package source contains an unsupported archive member: {name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"package source member is unreadable: {name}")
            mode = 0o755 if member.mode & 0o111 else 0o644
            files[name] = (stream.read(), mode, "source", name)
    if not files:
        raise ValueError("package source archive is empty")
    return files


def _promotion_snapshots(*, stage: Path, source_commit: str, workflow: str,
                         run_id: str, promotion_receipt_sha256: str,
                         repo: Path, installer):
    receipt_path = stage.absolute() / "artifact-promotion.json"
    descriptors = {host.name: host.plugin_dir for host in load_host_descriptors(str(repo))}
    expected = {"claude": "plugins/ca", "codex": "plugins/ca-codex", "pi": "plugins/ca-pi"}
    if descriptors != expected:
        raise ValueError("canonical host descriptors do not define the package cohort")
    snapshots = {}
    for host, relative in expected.items():
        source = stage.absolute().joinpath(*relative.split("/"), "helpers", "artifacts")
        snapshots[host] = installer.load_promotion_receipt(
            source, receipt_path, host=host, source_commit=source_commit,
            workflow=workflow, run_id=run_id,
            receipt_sha256=promotion_receipt_sha256,
        )
    first = snapshots["claude"]
    if any(snapshot != first for snapshot in snapshots.values()):
        raise ValueError("promoted host payload snapshots disagree")
    return first


def _payload_members(snapshot, prefix: str) -> dict[str, tuple[bytes, int, str, str]]:
    result = {
        f"{prefix}/release.json": (
            snapshot.manifest_bytes, 0o644, "promotion", "release.json"
        )
    }
    for filename, data in snapshot.payload:
        result[f"{prefix}/{filename}"] = (data, 0o755, "promotion", filename)
    return result


def _claude_catalog(source: bytes, installer) -> bytes:
    document = json.loads(source, object_pairs_hook=installer._pairs)
    plugins = document.get("plugins") if isinstance(document, dict) else None
    selected = [item for item in plugins or []
                if isinstance(item, dict) and item.get("name") == "ca"]
    if len(selected) != 1 or selected[0].get("source") != "./plugins/ca":
        raise ValueError("source Claude marketplace does not identify one canonical ca package")
    output = {key: value for key, value in document.items() if key != "plugins"}
    output["plugins"] = selected
    return (json.dumps(output, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _codex_catalog(source: bytes, installer) -> bytes:
    document = json.loads(source, object_pairs_hook=installer._pairs)
    plugins = document.get("plugins") if isinstance(document, dict) else None
    selected = [item for item in plugins or []
                if isinstance(item, dict) and item.get("name") == "ca-codex"]
    expected_source = {"source": "local", "path": "./plugins/ca-codex"}
    if len(selected) != 1 or selected[0].get("source") != expected_source:
        raise ValueError("source Codex marketplace does not identify one canonical ca-codex package")
    output = {key: value for key, value in document.items() if key != "plugins"}
    output["plugins"] = selected
    return (json.dumps(output, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _write_member_tree(root: Path,
                       members: dict[str, tuple[bytes, int, str, str]]) -> None:
    for name, (data, mode, _origin, _source) in sorted(members.items()):
        path = root.joinpath(*name.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
        path.chmod(mode)


def _isolated_npm_environment(root: Path) -> dict[str, str]:
    """Build a secret-free npm environment with disposable config and state."""
    root.mkdir(parents=True, exist_ok=True)
    home = root / "home"
    cache = root / "cache"
    logs = root / "logs"
    temporary = root / "tmp"
    appdata = root / "appdata"
    local_appdata = root / "local-appdata"
    for directory in (home, cache, logs, temporary, appdata, local_appdata):
        directory.mkdir()
    user_config = root / "user.npmrc"
    global_config = root / "global.npmrc"
    user_config.write_text("", encoding="utf-8")
    global_config.write_text("", encoding="utf-8")
    environment = {
        key: os.environ[key]
        for key in ("PATH", "SystemRoot", "WINDIR", "ComSpec", "PATHEXT")
        if key in os.environ
    }
    environment.update({
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(appdata),
        "LOCALAPPDATA": str(local_appdata),
        "TMP": str(temporary),
        "TEMP": str(temporary),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
        "npm_config_userconfig": str(user_config),
        "npm_config_globalconfig": str(global_config),
        "npm_config_cache": str(cache),
        "npm_config_logs_dir": str(logs),
        "npm_config_logs_max": "0",
        "npm_config_offline": "true",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
        "npm_config_ignore_scripts": "true",
        "npm_config_update_notifier": "false",
    })
    return environment


def _verified_npm_packer(
    executable: Path, *, package_integrity: str, production: bool
) -> dict[str, object]:
    executable = executable.absolute()
    if (
        executable.is_symlink()
        or not executable.is_file()
        or os.path.normcase(str(executable.resolve(strict=True)))
        != os.path.normcase(str(executable))
    ):
        raise ValueError("npm packer must be an explicit real executable file")
    if package_integrity != NPM_PACKER_INTEGRITY:
        raise ValueError("npm packer package integrity is not the reviewed npm@11.19.1 integrity")
    with tempfile.TemporaryDirectory(prefix="ca-artifact-npm-identity-") as temporary:
        environment = _isolated_npm_environment(Path(temporary) / "runtime")
        completed = subprocess.run(
            [str(executable), "--version"], capture_output=True, text=True,
            encoding="utf-8", timeout=30, check=False, env=environment,
        )
    version = completed.stdout.strip()
    if completed.returncode != 0 or completed.stderr or version != NPM_PACKER_VERSION:
        raise ValueError(f"npm packer must be the reviewed npm@{NPM_PACKER_VERSION} CLI")
    if production and os.name == "nt":
        raise ValueError("production Pi package assembly requires native POSIX mode evidence")
    return {
        "name": NPM_PACKER_NAME,
        "version": version,
        "package_integrity": package_integrity,
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "qualification": "production" if production else "local-portability",
    }


def _npm_selected_pi_members(candidate: Path,
                             members: dict[str, tuple[bytes, int, str, str]],
                             npm_executable: Path,
                             ) -> dict[str, tuple[bytes, int, str, str]]:
    with tempfile.TemporaryDirectory(prefix="ca-artifact-npm-select-") as temporary:
        environment = _isolated_npm_environment(Path(temporary) / "runtime")
        completed = subprocess.run(
            [str(npm_executable), "pack", "--dry-run", "--ignore-scripts", "--json"],
            cwd=candidate, env=environment, capture_output=True, text=True,
            encoding="utf-8", timeout=120, check=False,
        )
    if completed.returncode != 0:
        raise ValueError(
            f"npm could not enumerate the exact Pi package (exit {completed.returncode})"
        )
    try:
        report = json.loads(completed.stdout)
        selected = [entry["path"].replace("\\", "/") for entry in report[0]["files"]]
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("npm returned malformed Pi package membership") from error
    if len(selected) != len(set(selected)) or not selected:
        raise ValueError("npm returned duplicate or empty Pi package membership")
    output = {}
    for relative in selected:
        source = members.get(relative)
        if source is None:
            path = candidate.joinpath(*relative.split("/"))
            if not path.is_file() or path.is_symlink():
                raise ValueError(f"npm selected an undeclared Pi package member: {relative}")
            source = (path.read_bytes(), 0o644, "source", relative)
        data, mode, origin, source_path = source
        if origin == "promotion":
            mode = 0o644 if relative.endswith("/release.json") else 0o755
        else:
            mode = 0o755 if mode & 0o111 else 0o644
        output[f"package/{relative}"] = (data, mode, origin, source_path)
    return output


def _npm_pack_pi_bytes(
    members: dict[str, tuple[bytes, int, str, str]], npm_executable: Path,
    *, production: bool,
) -> bytes:
    """Create the Pi artifact with npm itself, using only the preassembled tree."""
    candidate_members = {
        name.removeprefix("package/"): value for name, value in members.items()
    }
    with tempfile.TemporaryDirectory(prefix="ca-artifact-pi-npm-pack-") as temporary:
        root = Path(temporary)
        candidate = root / "candidate"
        destination = root / "output"
        candidate.mkdir()
        destination.mkdir()
        environment = _isolated_npm_environment(root / "runtime")
        _write_member_tree(candidate, candidate_members)
        completed = subprocess.run(
            [str(npm_executable), "pack", "--ignore-scripts", "--json",
             "--pack-destination", str(destination)],
            cwd=candidate, env=environment, capture_output=True, text=True,
            encoding="utf-8", timeout=120, check=False,
        )
        if completed.returncode != 0:
            raise ValueError(
                f"npm could not create the exact Pi package (exit {completed.returncode})"
            )
        try:
            report = json.loads(completed.stdout)
            filename = report[0]["filename"]
        except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("npm returned malformed Pi package output") from error
        artifact = destination / filename
        outputs = [path for path in destination.iterdir() if path.is_file()]
        if outputs != [artifact] or artifact.is_symlink():
            raise ValueError("npm produced an unexpected Pi package output set")
        npm_bytes = artifact.read_bytes()
        observed = _read_archive(artifact)
        expected = {name: (value[0], value[1]) for name, value in members.items()}
        if set(observed) != set(expected) or any(
            observed[name][0] != expected[name][0] for name in expected
        ):
            raise ValueError("npm package membership or bytes drifted from the preassembled tree")
        if observed == expected:
            return npm_bytes
        mode_drift = {
            name for name in expected if observed[name][1] != expected[name][1]
        }
        if production or os.name != "nt" or any(
            members[name][2] != "promotion"
            or name.endswith("/release.json")
            or observed[name][1] != 0o644
            or expected[name][1] != 0o755
            for name in mode_drift
        ):
            raise ValueError("npm package modes drifted from the preassembled tree")
        # npm on Windows cannot observe POSIX executable bits. Re-emit the exact
        # npm-selected bytes with only the receipt-required native modes restored.
        return _archive_bytes(members)


def _archive_bytes(members: dict[str, tuple[bytes, int, str, str]]) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for name, (data, mode, _origin, _source) in sorted(members.items()):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = mode
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


def _read_archive(
    path: Path, *, expected_members: dict[str, dict] | None = None
) -> dict[str, tuple[bytes, int]]:
    files = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            name = member.name.rstrip("/")
            if not name or member.isdir():
                continue
            if (not member.isfile() or name.startswith("/") or ".." in Path(name).parts
                    or name in files):
                raise ValueError(f"release package has an unsafe member: {name}")
            expected = expected_members.get(name) if expected_members is not None else None
            if expected_members is not None and (
                expected is None
                or member.size != expected["size"]
                or member.mode & 0o777 != int(expected["mode"], 8)
            ):
                raise ValueError(f"release package member metadata drifted: {name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"release package member is unreadable: {name}")
            data = stream.read((expected["size"] if expected is not None else 256 << 20) + 1)
            if expected is not None and (
                len(data) != expected["size"]
                or hashlib.sha256(data).hexdigest() != expected["sha256"]
            ):
                raise ValueError(f"release package member bytes drifted: {name}")
            if expected is None and len(data) > 256 << 20:
                raise ValueError("release package member exceeds the extraction limit")
            files[name] = (data, member.mode & 0o777)
    if expected_members is not None and set(files) != set(expected_members):
        raise ValueError("release package member set drifted")
    return files


def _member_receipt(members: dict[str, tuple[bytes, int, str, str]]) -> dict[str, dict]:
    return {
        name: {
            "type": "file",
            "mode": f"{mode:04o}",
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "origin": origin,
            "source": source,
        }
        for name, (data, mode, origin, source) in sorted(members.items())
    }


def _expected_release_package_members(*, stage: Path, source_repo: Path,
                                      source_commit: str, workflow: str,
                                      run_id: str, promotion_receipt_sha256: str,
                                      npm_executable: Path | None = None,
                                      pi_selected_paths: set[str] | None = None,
                                      repo: Path = REPO):
    installer = _artifact_installer_module()
    snapshot = _promotion_snapshots(
        stage=stage, source_commit=source_commit, workflow=workflow, run_id=run_id,
        promotion_receipt_sha256=promotion_receipt_sha256, repo=repo,
        installer=installer,
    )
    claude = _git_archive_files(source_repo, source_commit, (
        ".claude-plugin/marketplace.json", "plugins/ca",
    ))
    original_catalog = claude.pop(".claude-plugin/marketplace.json")
    claude[".claude-plugin/marketplace.json"] = (
        _claude_catalog(original_catalog[0], installer), 0o644,
        "generated-catalog", ".claude-plugin/marketplace.json",
    )
    if any(name.startswith("plugins/ca/helpers/artifacts/") for name in claude):
        raise ValueError("source commit already contains a Claude artifact payload")
    claude.update(_payload_members(snapshot, "plugins/ca/helpers/artifacts"))

    codex = _git_archive_files(source_repo, source_commit, (
        ".agents/plugins/marketplace.json", "plugins/ca-codex",
    ))
    original_codex_catalog = codex.pop(".agents/plugins/marketplace.json")
    codex[".agents/plugins/marketplace.json"] = (
        _codex_catalog(original_codex_catalog[0], installer), 0o644,
        "generated-catalog", ".agents/plugins/marketplace.json",
    )
    if any(name.startswith("plugins/ca-codex/helpers/artifacts/") for name in codex):
        raise ValueError("source commit already contains a Codex artifact payload")
    codex.update(_payload_members(snapshot, "plugins/ca-codex/helpers/artifacts"))

    pi_source = _git_archive_files(source_repo, source_commit, (
        "package.json", "LICENSE", "README.md", "plugins/ca-pi",
    ))
    if any(name.startswith("plugins/ca-pi/helpers/artifacts/") for name in pi_source):
        raise ValueError("source commit already contains a Pi artifact payload")
    pi_candidate_members = dict(pi_source)
    pi_candidate_members.update(_payload_members(snapshot, "plugins/ca-pi/helpers/artifacts"))
    if pi_selected_paths is None:
        if npm_executable is None:
            raise ValueError("exact npm packer is required to select Pi package membership")
        with tempfile.TemporaryDirectory(prefix="ca-artifact-pi-package-") as temporary:
            candidate = Path(temporary)
            _write_member_tree(candidate, pi_candidate_members)
            pi = _npm_selected_pi_members(
                candidate, pi_candidate_members, npm_executable
            )
    else:
        if not pi_selected_paths or any(
            not isinstance(path, str) or path not in pi_candidate_members
            for path in pi_selected_paths
        ):
            raise ValueError("Pi package receipt selects an unknown or empty source set")
        pi = {
            f"package/{path}": (
                pi_candidate_members[path][0],
                (0o644 if path.endswith("/release.json") else 0o755)
                if pi_candidate_members[path][2] == "promotion"
                else (0o755 if pi_candidate_members[path][1] & 0o111 else 0o644),
                pi_candidate_members[path][2],
                pi_candidate_members[path][3],
            )
            for path in sorted(pi_selected_paths)
        }
    return snapshot, {"claude": claude, "codex": codex, "pi": pi}


def build_artifact_release_packages(*, stage: Path, source_repo: Path,
                                    source_commit: str, workflow: str,
                                    run_id: str, promotion_receipt_sha256: str,
                                    output: Path, npm_executable: Path,
                                    npm_package_integrity: str,
                                    production: bool = True,
                                    repo: Path = REPO) -> dict[str, object]:
    """Build final immutable Claude, Codex, and Pi installation artifacts."""
    source_tree = _source_identity(source_repo, source_commit)
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError(f"artifact package output already exists: {output}")
    packer = _verified_npm_packer(
        npm_executable, package_integrity=npm_package_integrity,
        production=production,
    )
    snapshot, members_by_host = _expected_release_package_members(
        stage=stage, source_repo=source_repo, source_commit=source_commit,
        workflow=workflow, run_id=run_id,
        promotion_receipt_sha256=promotion_receipt_sha256,
        npm_executable=npm_executable, repo=repo,
    )
    manifest = json.loads(snapshot.manifest_bytes)
    versions = {
        "claude": json.loads(members_by_host["claude"][
            "plugins/ca/.claude-plugin/plugin.json"][0])["version"],
        "codex": json.loads(members_by_host["codex"][
            "plugins/ca-codex/.codex-plugin/plugin.json"][0])["version"],
        "pi": json.loads(members_by_host["pi"]["package/package.json"][0])["version"],
    }
    filenames = {
        "claude": f"codearbiter-ca-{versions['claude']}.tar.gz",
        "codex": f"codearbiter-ca-codex-{versions['codex']}.tar.gz",
        "pi": f"arbiterforge-ca-pi-{versions['pi']}.tgz",
    }
    archives = {
        "claude": _archive_bytes(members_by_host["claude"]),
        "codex": _archive_bytes(members_by_host["codex"]),
        "pi": _npm_pack_pi_bytes(
            members_by_host["pi"], npm_executable, production=production
        ),
    }
    receipt = {
        "format": ARTIFACT_PACKAGE_FORMAT,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "workflow": workflow,
        "run_id": run_id,
        "promotion_receipt_sha256": promotion_receipt_sha256,
        "artifact_version": manifest["version"],
        "protocol": manifest["protocol"],
        "schema_version": manifest["schema_version"],
        "pi_packer": packer,
        "packages": {
            host: {
                "file": filenames[host],
                "version": versions[host],
                "size": len(archives[host]),
                "sha256": hashlib.sha256(archives[host]).hexdigest(),
                "members": _member_receipt(members_by_host[host]),
            }
            for host in sorted(archives)
        },
    }
    receipt_bytes = (json.dumps(receipt, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    with _pinned_artifact_stage(output) as package:
        for host in sorted(archives):
            package.write_root_file(filenames[host], archives[host])
        package.write_root_file("artifact-package-cohort.json", receipt_bytes)
    return receipt


def verify_artifact_release_packages(*, package_root: Path, source_repo: Path,
                                     source_commit: str, workflow: str,
                                     run_id: str, promotion_receipt_sha256: str,
                                     stage: Path, require_production: bool = True,
                                     npm_executable: Path | None = None,
                                     repo: Path = REPO) -> dict[str, object]:
    """Re-derive and verify the final package archives against Git and promotion bytes."""
    package_root = package_root.absolute()
    if (package_root.is_symlink() or not package_root.is_dir()
            or os.path.normcase(str(package_root.resolve(strict=True))) !=
            os.path.normcase(str(package_root))):
        raise ValueError("artifact package root must be a real directory")
    installer = _artifact_installer_module()
    raw = installer.read_regular(package_root / "artifact-package-cohort.json", 8 << 20)
    receipt = json.loads(raw, object_pairs_hook=installer._pairs)
    receipt_fields = {
        "format", "source_commit", "source_tree", "workflow", "run_id",
        "promotion_receipt_sha256", "artifact_version", "protocol",
        "schema_version", "pi_packer", "packages",
    }
    if (not isinstance(receipt, dict) or set(receipt) != receipt_fields
            or receipt.get("format") != ARTIFACT_PACKAGE_FORMAT
            or receipt.get("source_commit") != source_commit
            or receipt.get("source_tree") != _source_identity(source_repo, source_commit)
            or receipt.get("workflow") != workflow or receipt.get("run_id") != run_id
            or receipt.get("promotion_receipt_sha256") != promotion_receipt_sha256):
        raise ValueError("artifact package cohort does not match the trusted source context")
    packer = receipt["pi_packer"]
    expected_qualification = "production" if require_production else None
    if (
        not isinstance(packer, dict)
        or set(packer) != {
            "name", "version", "package_integrity", "executable_sha256", "qualification"
        }
        or packer.get("name") != NPM_PACKER_NAME
        or packer.get("version") != NPM_PACKER_VERSION
        or packer.get("package_integrity") != NPM_PACKER_INTEGRITY
        or re.fullmatch(r"[0-9a-f]{64}", packer.get("executable_sha256", "")) is None
        or packer.get("qualification") not in {"production", "local-portability"}
        or expected_qualification is not None
        and packer.get("qualification") != expected_qualification
    ):
        raise ValueError("artifact package cohort has no reviewed Pi packer identity")
    if npm_executable is not None:
        observed_packer = _verified_npm_packer(
            npm_executable, package_integrity=NPM_PACKER_INTEGRITY,
            production=require_production,
        )
        if observed_packer != packer:
            raise ValueError("artifact package cohort Pi packer receipt drifted")
    packages = receipt.get("packages")
    pi_package = packages.get("pi") if isinstance(packages, dict) else None
    pi_members = pi_package.get("members") if isinstance(pi_package, dict) else None
    if not isinstance(pi_members, dict):
        raise ValueError("artifact package cohort Pi membership is malformed")
    pi_selected_paths = {
        name.removeprefix("package/") for name in pi_members
        if isinstance(name, str) and name.startswith("package/")
    }
    if len(pi_selected_paths) != len(pi_members):
        raise ValueError("artifact package cohort Pi membership is malformed")
    snapshot, expected = _expected_release_package_members(
        stage=stage, source_repo=source_repo, source_commit=source_commit,
        workflow=workflow, run_id=run_id,
        promotion_receipt_sha256=promotion_receipt_sha256,
        pi_selected_paths=pi_selected_paths, repo=repo,
    )
    manifest = json.loads(snapshot.manifest_bytes, object_pairs_hook=installer._pairs)
    if (
        receipt["artifact_version"] != manifest["version"]
        or receipt["protocol"] != manifest["protocol"]
        or receipt["schema_version"] != manifest["schema_version"]
    ):
        raise ValueError("artifact package cohort engine identity drifted")
    expected_versions = {
        "claude": json.loads(expected["claude"][
            "plugins/ca/.claude-plugin/plugin.json"][0],
            object_pairs_hook=installer._pairs,
        )["version"],
        "codex": json.loads(expected["codex"][
            "plugins/ca-codex/.codex-plugin/plugin.json"][0],
            object_pairs_hook=installer._pairs,
        )["version"],
        "pi": json.loads(expected["pi"]["package/package.json"][0],
                         object_pairs_hook=installer._pairs)["version"],
    }
    if not isinstance(packages, dict) or set(packages) != set(expected):
        raise ValueError("artifact package cohort host set drifted")
    expected_files = {"artifact-package-cohort.json"}
    for host, members in expected.items():
        package = packages[host]
        if (not isinstance(package, dict)
                or set(package) != {"file", "version", "size", "sha256", "members"}
                or not isinstance(package.get("file"), str)
                or Path(package["file"]).name != package["file"]
                or re.fullmatch(r"[A-Za-z0-9._-]+\.(?:tar\.gz|tgz)", package["file"])
                is None or package.get("version") != expected_versions[host]):
            raise ValueError("artifact package cohort entry is malformed")
        path = package_root / package["file"]
        expected_files.add(package["file"])
        data = installer.read_regular(path, 256 << 20)
        expected_member_receipt = _member_receipt(members)
        if (package.get("size") != len(data)
                or package.get("sha256") != hashlib.sha256(data).hexdigest()
                or package.get("members") != expected_member_receipt):
            drifted_members = sorted(
                set(package.get("members", {})) ^ set(expected_member_receipt)
                | {
                    name for name in set(package.get("members", {})) & set(expected_member_receipt)
                    if package["members"][name] != expected_member_receipt[name]
                }
            )
            detail = ", ".join(drifted_members[:3])
            raise ValueError(f"artifact package cohort receipt drifted: {host}: {detail}")
        observed = _read_archive(path, expected_members=package["members"])
        wanted = {name: (value[0], value[1]) for name, value in members.items()}
        if observed != wanted:
            raise ValueError(f"artifact package members drifted from source or promotion: {host}")
    actual_files = {entry.name for entry in package_root.iterdir()
                    if entry.is_file() and not entry.is_symlink()}
    if actual_files != expected_files or any(entry.is_symlink() or not entry.is_file()
                                             for entry in package_root.iterdir()):
        raise ValueError("artifact package cohort file set drifted")
    checker_path = repo / ".github" / "scripts" / "check_codex_static_package.py"
    spec = importlib.util.spec_from_file_location(
        "codearbiter_artifact_release_static_check", checker_path
    )
    if spec is None or spec.loader is None:
        raise ValueError("trusted Codex static package checker is unavailable")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    codex_members = packages["codex"]["members"]
    verified_large_files = {
        name.removeprefix("plugins/ca-codex/"): {
            key: member[key]
            for key in ("type", "mode", "size", "sha256", "origin")
        }
        for name, member in codex_members.items()
        if (
            name.startswith("plugins/ca-codex/helpers/artifacts/ca-artifact-")
            and member["size"] > 2 * 1024 * 1024
        )
    }
    with tempfile.TemporaryDirectory(prefix="ca-artifact-codex-verify-") as temporary:
        extracted = Path(temporary) / "candidate"
        extract_artifact_release_package(
            package_root / packages["codex"]["file"], extracted, host="codex"
        )
        result = checker.candidate_static_contract(
            extracted / "plugins" / "ca-codex",
            verified_large_files=verified_large_files,
        )
        if result.get("verdict") != "PASS":
            raise ValueError("final Codex package failed its static contract")
    return receipt


def extract_artifact_release_package(artifact: Path, destination: Path, *, host: str) -> Path:
    """Safely extract one already-verified release package for cold-use proof."""
    if host not in {"claude", "codex", "pi"}:
        raise ValueError("unknown artifact release package host")
    if destination.exists() or destination.is_symlink():
        raise ValueError("artifact package extraction output already exists")
    files = _read_archive(artifact)
    destination.mkdir()
    for name, (data, mode) in sorted(files.items()):
        path = destination.joinpath(*name.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
        path.chmod(mode)
    return destination


def cold_execute_artifact_host_payload(*, stage: Path, package_root: Path,
                                       source_repo: Path, host: str,
                                       expected_platform: str,
                                       source_commit: str, workflow: str,
                                       run_id: str,
                                       promotion_receipt_sha256: str,
                                       output: Path,
                                       require_production: bool = True) -> dict[str, object]:
    """Execute one verified host/platform payload and retain a bound receipt.

    The executable is read from the verified immutable final package archive,
    copied into an otherwise empty temporary directory, and launched by absolute
    path with an empty environment. No checkout binary, PATH lookup, Go
    invocation, or network installer can satisfy this check.
    """
    if expected_platform not in ARTIFACT_PLATFORMS:
        raise ValueError(f"unsupported cold-execution platform: {expected_platform}")
    native_system = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}.get(
        platform.system())
    native_arch = {
        "x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64",
    }.get(platform.machine().lower())
    native_platform = f"{native_system}/{native_arch}" if native_system and native_arch else None
    if expected_platform != native_platform:
        raise ValueError(
            f"cold-execution cell expected {expected_platform}, actual host is {native_platform}"
        )
    output = output.absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError("cold-execution receipt output must be a new file in a real directory")
    if (output.parent.is_symlink()
            or os.path.normcase(str(output.parent.resolve(strict=True))) !=
            os.path.normcase(str(output.parent))):
        raise ValueError("cold-execution receipt output must be a new file in a real directory")

    cohort = verify_artifact_release_packages(
        package_root=package_root, source_repo=source_repo,
        source_commit=source_commit, workflow=workflow, run_id=run_id,
        promotion_receipt_sha256=promotion_receipt_sha256, stage=stage,
        require_production=require_production,
    )
    installer = _artifact_installer_module()
    host_descriptors = {descriptor.name: descriptor for descriptor in load_host_descriptors(str(REPO))}
    descriptor = host_descriptors.get(host)
    if descriptor is None:
        raise ValueError("cold-execution host must be a canonical governance host")
    package = cohort["packages"][host]
    archive = package_root / package["file"]
    archived = _read_archive(archive, expected_members=package["members"])
    payload_prefix = {
        "claude": "plugins/ca/helpers/artifacts/",
        "codex": "plugins/ca-codex/helpers/artifacts/",
        "pi": "package/plugins/ca-pi/helpers/artifacts/",
    }[host]
    payload = {
        name.removeprefix(payload_prefix): data
        for name, (data, _mode) in archived.items()
        if name.startswith(payload_prefix)
    }
    manifest_bytes = payload.get("release.json")
    if manifest_bytes is None:
        raise ValueError("final release package has no promoted artifact manifest")
    manifest = json.loads(manifest_bytes, object_pairs_hook=installer._pairs)
    entry = manifest["binaries"].get(expected_platform)
    if not isinstance(entry, dict) or entry.get("native_tested") is not True:
        raise ValueError("promoted payload has no qualified binary for this cold-execution cell")
    binary = payload.get(entry["file"])
    if binary is None or hashlib.sha256(binary).hexdigest() != entry["sha256"]:
        raise ValueError("promoted payload binary drifted before cold execution")

    request = json.dumps({"protocol": ARTIFACT_PROTOCOL}, separators=(",", ":")).encode("ascii")
    with tempfile.TemporaryDirectory(prefix="ca-artifact-cold-") as temporary:
        isolated = Path(temporary)
        repository = isolated / "repository"
        repository.mkdir()
        executable = isolated / entry["file"]
        executable.write_bytes(binary)
        if native_system != "windows":
            executable.chmod(0o700)
        completed = subprocess.run(
            [str(executable.absolute()), "capabilities", "--root", str(repository),
             "--request", "-"],
            input=request, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=30, check=False, cwd=repository, env={},
        )
    if completed.returncode != 0 or completed.stderr:
        raise RuntimeError(
            f"cold execution failed with exit {completed.returncode}: "
            f"{completed.stderr[:512].decode('utf-8', errors='replace')}"
        )
    response = json.loads(completed.stdout, object_pairs_hook=installer._pairs)
    if (not isinstance(response, dict)
            or set(response) != {"protocol", "operation", "ok", "result"}
            or response.get("protocol") != ARTIFACT_PROTOCOL
            or response.get("operation") != "capabilities"
            or response.get("ok") is not True
            or not isinstance(response.get("result"), dict)):
        raise RuntimeError("cold execution returned a malformed capabilities response")
    capabilities = response["result"]
    if (capabilities.get("platform") != expected_platform
            or capabilities.get("repository_operations_available") is not True
            or capabilities.get("runtime_downloads") is not False):
        raise RuntimeError("cold execution did not prove the required native offline capability")

    cold_receipt = {
        "format": ARTIFACT_COLD_EXECUTION_FORMAT,
        "source_commit": source_commit,
        "workflow": workflow,
        "run_id": run_id,
        "job": "artifact-package-cold",
        "host": host,
        "platform": expected_platform,
        "promotion_receipt_sha256": promotion_receipt_sha256,
        "package_sha256": package["sha256"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "binary_sha256": entry["sha256"],
        "response_sha256": hashlib.sha256(completed.stdout).hexdigest(),
        "operation": "capabilities",
        "repository_operations_available": True,
        "runtime_downloads": False,
    }
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(cold_receipt, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return cold_receipt


def render_package(
    host: HostDescriptor,
    version: str,
    license_spdx: str = "AGPL-3.0-only",
) -> bytes:
    """Render root Pi Git-package metadata as deterministic UTF-8 bytes."""
    if host.name != "pi":
        raise ValueError(f"root Git package metadata is unsupported for host {host.name!r}")
    # ADR-0029: the root manifest is also the npm publish unit — scoped name,
    # provenance-ready repository/publishConfig, and a files whitelist shipping
    # exactly the Pi-served payload (never the tools/ dev workspace).
    document = {
        "name": "@arbiterforge/ca-pi",
        "version": version,
        "license": license_spdx,
        "repository": {
            "type": "git",
            "url": "git+https://github.com/arbiterForge/codeArbiter.git",
        },
        "engines": {"node": ">=22.19.0"},
        "publishConfig": {"access": "public", "provenance": True},
        "files": [
            f"{host.plugin_dir}/*.md",
            f"{host.plugin_dir}/agents/",
            f"{host.plugin_dir}/extensions/",
            f"{host.plugin_dir}/generated/",
            f"{host.plugin_dir}/helpers/",
            f"{host.plugin_dir}/hooks/",
            f"{host.plugin_dir}/includes/",
            f"{host.plugin_dir}/routines/",
            f"{host.plugin_dir}/skills/",
        ],
        "pi": {
            "extensions": [f"./{host.plugin_dir}/extensions/codearbiter.js"],
            "skills": [f"./{host.plugin_dir}/skills"],
        },
    }
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def expected_package(repo: Path = REPO) -> bytes:
    host = host_descriptor("pi", str(repo))
    nested = repo / host.plugin_dir / "package.json"
    metadata = json.loads(nested.read_text(encoding="utf-8"))
    version = metadata["version"]
    if not isinstance(version, str) or not version:
        raise ValueError(f"{nested}: version must be a non-empty string")
    license_spdx = metadata.get("license")
    if not isinstance(license_spdx, str) or not license_spdx:
        raise ValueError(f"{nested}: license must be a non-empty SPDX string")
    return render_package(host, version, license_spdx)


def _semver_key(value: str) -> tuple[int, int, int, tuple[tuple[int, object], ...] | None]:
    """`_releaselib.semver_key` with this module's RAISING contract restored.

    The shared helper degrades to None because a release gate that crashes is
    worse than one that refuses; `pi_release_guard` and
    `validate_pi_release_advance` both branch on the exception to report
    "not valid SemVer" rather than the misleading "must strictly advance"."""
    key = semver_key(value)
    if key is None:
        raise ValueError(f"{value!r} is not valid SemVer")
    return key


def _semver_greater(current: str, base: str) -> bool:
    _semver_key(current)
    _semver_key(base)
    return semver_greater(current, base)


def validate_pi_release_advance(
    *,
    current_version: str,
    base_version: str,
    root_version: str,
    changelog: str,
    base_changelog: str,
    root_changed: bool,
    changelog_changed: bool,
) -> str | None:
    """Return an actionable diagnosis when Pi release metadata is inconsistent."""
    try:
        advances = _semver_greater(current_version, base_version)
    except ValueError as error:
        return str(error)
    if not advances:
        return f"ca-pi version must strictly advance from {base_version} to a higher SemVer (got {current_version})"
    if root_version != current_version:
        return f"root Pi version {root_version} does not match ca-pi {current_version}"
    if not root_changed:
        return "ca-pi version advanced without regenerated root metadata"
    if not changelog_changed:
        return "ca-pi version advanced without a changelog change"
    heading = re.compile(rf"^## \[{re.escape(current_version)}\](?: - \d{{4}}-\d{{2}}-\d{{2}})?$", re.MULTILINE)
    if heading.search(changelog) is None:
        return f"missing exact changelog heading for ca-pi {current_version}"
    if heading.search(base_changelog) is not None:
        return f"changelog heading for ca-pi {current_version} was not newly introduced relative to base"
    return None


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=REPO, text=True, encoding="utf-8", capture_output=True, check=check
    )


def pi_release_guard(base_ref: str) -> int:
    plugin_manifest = REPO / "plugins" / "ca-pi" / "package.json"
    changelog_path = REPO / "plugins" / "ca-pi" / "CHANGELOG.md"
    # Issue #435: `plugins/ca-pi/tools/` is a BUILD directory - TypeScript
    # sources, a vitest config, a lockfile - and none of it runs on an installed
    # machine. Scoping the guard to it wholesale made a dev-only dependabot
    # lockfile bump demand a version advance and a changelog heading describing a
    # change no user can observe, which trains contributors to bump a version to
    # silence a gate. That is the exact habit the gate exists to prevent.
    #
    # ca-pi's committed bundles live in `extensions/`, OUTSIDE the excluded
    # directory, so they stay in scope with no re-inclusion needed - which is why
    # payload_scope.SHIPPED_TOOLS_ARTIFACTS declares none for this plugin.
    scope = ("plugins/ca-pi", ":(exclude)plugins/ca-pi/tools", "package.json")
    if _git("diff", "--quiet", f"{base_ref}...HEAD", "--", *scope, check=False).returncode == 0:
        print("no Pi payload change - version bump not required")
        return 0
    if _git("rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}", check=False).returncode != 0:
        print(f"{base_ref} does not resolve to a commit - bad ref or failed fetch", file=sys.stderr)
        return 1
    current = json.loads(plugin_manifest.read_text(encoding="utf-8"))["version"]
    root = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["version"]
    changelog = changelog_path.read_text(encoding="utf-8")
    try:
        _semver_key(current)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    base_file = f"{base_ref}:plugins/ca-pi/package.json"
    if _git("cat-file", "-e", base_file, check=False).returncode != 0:
        if root != current or re.search(rf"^## \[{re.escape(current)}\](?: - \d{{4}}-\d{{2}}-\d{{2}})?$", changelog, re.MULTILINE) is None:
            print("new ca-pi package has inconsistent root version or changelog heading", file=sys.stderr)
            return 1
        print("ca-pi is new on the base - first introduction metadata is consistent")
        return 0
    base = json.loads(_git("show", base_file).stdout)["version"]
    base_changelog = _git("show", f"{base_ref}:plugins/ca-pi/CHANGELOG.md", check=False)
    if base_changelog.returncode != 0:
        print("base ca-pi package is missing CHANGELOG.md", file=sys.stderr)
        return 1
    diagnosis = validate_pi_release_advance(
        current_version=current,
        base_version=base,
        root_version=root,
        changelog=changelog,
        base_changelog=base_changelog.stdout,
        root_changed=_git("diff", "--quiet", f"{base_ref}...HEAD", "--", "package.json", check=False).returncode != 0,
        changelog_changed=_git("diff", "--quiet", f"{base_ref}...HEAD", "--", "plugins/ca-pi/CHANGELOG.md", check=False).returncode != 0,
    )
    if diagnosis:
        print(diagnosis, file=sys.stderr)
        return 1
    if _git("rev-parse", "--verify", "--quiet", f"refs/tags/ca-pi-v{current}", check=False).returncode == 0:
        print(f"ca-pi version {current} is already tagged", file=sys.stderr)
        return 1
    print(f"Pi payload, version, changelog, and root metadata advanced together: {base} -> {current}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--release-guard-base")
    parser.add_argument("--artifact-candidate", action="append", type=Path, default=[])
    parser.add_argument("--artifact-qualification", action="append", type=Path, default=[])
    parser.add_argument("--artifact-stage", type=Path)
    parser.add_argument("--require-platform", action="append", default=[])
    parser.add_argument("--trusted-source-commit")
    parser.add_argument("--trusted-workflow")
    parser.add_argument("--trusted-workflow-run")
    parser.add_argument("--release-package-stage", type=Path)
    parser.add_argument("--release-package-output", type=Path)
    parser.add_argument("--source-repo", type=Path)
    parser.add_argument("--npm-executable", type=Path)
    parser.add_argument("--npm-package-integrity")
    parser.add_argument("--promotion-receipt-sha256")
    parser.add_argument("--cold-package-root", type=Path)
    parser.add_argument("--cold-host")
    parser.add_argument("--cold-platform")
    parser.add_argument("--cold-promotion-receipt-sha256")
    parser.add_argument("--cold-receipt", type=Path)
    args = parser.parse_args(argv)
    package_mode = args.release_package_output is not None
    if package_mode:
        if (args.check or args.release_guard_base or args.artifact_candidate
                or args.artifact_qualification or args.artifact_stage
                or args.require_platform or args.cold_package_root or args.cold_host
                or args.cold_platform or args.cold_promotion_receipt_sha256
                or args.cold_receipt):
            parser.error(
                "release package assembly cannot be combined with checks, staging, or cold execution"
            )
        if (args.release_package_stage is None or args.release_package_output is None
                or args.source_repo is None
                or args.npm_executable is None or not args.npm_package_integrity
                or not args.trusted_source_commit or not args.trusted_workflow
                or not args.trusted_workflow_run or not args.promotion_receipt_sha256):
            parser.error(
                "release package assembly requires stage, output, source repository, reviewed npm, provenance, and receipt digest"
            )
        result = build_artifact_release_packages(
            stage=args.release_package_stage,
            source_repo=args.source_repo,
            source_commit=args.trusted_source_commit,
            workflow=args.trusted_workflow,
            run_id=args.trusted_workflow_run,
            promotion_receipt_sha256=args.promotion_receipt_sha256,
            output=args.release_package_output,
            npm_executable=args.npm_executable,
            npm_package_integrity=args.npm_package_integrity,
        )
        verified = verify_artifact_release_packages(
            package_root=args.release_package_output,
            source_repo=args.source_repo,
            source_commit=args.trusted_source_commit,
            workflow=args.trusted_workflow,
            run_id=args.trusted_workflow_run,
            promotion_receipt_sha256=args.promotion_receipt_sha256,
            stage=args.release_package_stage,
            npm_executable=args.npm_executable,
        )
        if verified != result:
            raise ValueError("release package verification result changed after assembly")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    cold_mode = any((args.cold_package_root, args.cold_host, args.cold_platform,
                     args.cold_promotion_receipt_sha256, args.cold_receipt))
    if cold_mode:
        if (args.check or args.release_guard_base or args.artifact_candidate
                or args.artifact_qualification or args.artifact_stage
                or args.require_platform):
            parser.error("cold execution cannot be combined with package checks or artifact staging")
        if (args.cold_package_root is None or args.release_package_stage is None
                or args.source_repo is None or not args.cold_host or not args.cold_platform
                or not args.trusted_source_commit or not args.trusted_workflow
                or not args.trusted_workflow_run or not args.cold_promotion_receipt_sha256
                or args.cold_receipt is None):
            parser.error("cold execution requires package root, stage, source, host, platform, provenance, and receipt output")
        result = cold_execute_artifact_host_payload(
            stage=args.release_package_stage, package_root=args.cold_package_root,
            source_repo=args.source_repo, host=args.cold_host,
            expected_platform=args.cold_platform,
            source_commit=args.trusted_source_commit,
            workflow=args.trusted_workflow, run_id=args.trusted_workflow_run,
            promotion_receipt_sha256=args.cold_promotion_receipt_sha256,
            output=args.cold_receipt,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    artifact_mode = bool(
        args.artifact_candidate or args.artifact_qualification or args.artifact_stage
        or args.require_platform or args.trusted_source_commit or args.trusted_workflow
        or args.trusted_workflow_run
    )
    if artifact_mode:
        if args.check or args.release_guard_base:
            parser.error("artifact staging cannot be combined with package checks or release guards")
        if (not args.artifact_candidate or not args.artifact_qualification
                or args.artifact_stage is None or not args.require_platform
                or not args.trusted_source_commit or not args.trusted_workflow
                or not args.trusted_workflow_run):
            parser.error(
                "artifact staging requires candidate/qualification pairs, a stage, required "
                "platforms, and trusted source/workflow/run identity"
            )
        result = stage_artifact_host_payloads(
            candidates=args.artifact_candidate,
            qualification_receipts=args.artifact_qualification,
            trusted_source_commit=args.trusted_source_commit,
            trusted_workflow=args.trusted_workflow,
            trusted_workflow_run=args.trusted_workflow_run,
            output=args.artifact_stage,
            required_platforms=args.require_platform,
        )
        print(json.dumps(result, indent=2))
        return 0
    target = REPO / "package.json"
    expected = expected_package()
    if args.check:
        if not target.is_file() or target.read_bytes() != expected:
            print("package.json is stale; run python tools/build-host-packages.py", file=sys.stderr)
            return 1
        print("package.json matches plugins/ca-pi/package.json and the Pi descriptor")
        if not args.release_guard_base:
            return 0
    if args.release_guard_base:
        return pi_release_guard(args.release_guard_base)
    target.write_bytes(expected)
    print("generated package.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
