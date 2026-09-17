#!/usr/bin/env python3
"""Generate dependency-free host package metadata from canonical descriptors."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

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


def _artifact_qualification(path: Path, candidate: Path, installer) -> dict:
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
    return receipt


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

    def _directory(self, parts: tuple[str, ...]) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        for index in range(1, len(parts) + 1):
            prefix = parts[:index]
            if prefix in self._fds:
                continue
            parent = self._fds[prefix[:-1]]
            try:
                os.mkdir(prefix[-1], 0o755, dir_fd=parent)
            except FileExistsError:
                pass
            self._fds[prefix] = os.open(prefix[-1], flags, dir_fd=parent)
        return self._fds[parts]

    def write_payload(self, parts: tuple[str, ...], manifest_bytes: bytes,
                      binaries: dict[str, bytes]) -> None:
        directory = self._directory(parts)
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

    def _directory(self, parts: tuple[str, ...]) -> Path:
        current = self.output
        for part in parts:
            current = current / part
            if current not in self._pinned:
                try:
                    current.mkdir()
                except FileExistsError:
                    pass
                handle = _pin_windows_directory(current)
                self._handles.append(handle)
                self._pinned[current] = handle
        return current

    def write_payload(self, parts: tuple[str, ...], manifest_bytes: bytes,
                      binaries: dict[str, bytes]) -> None:
        directory = self._directory(parts)
        for filename in sorted(binaries):
            with (directory / filename).open("xb") as stream:
                stream.write(binaries[filename])
                stream.flush()
                os.fsync(stream.fileno())
        with (directory / "release.json").open("xb") as stream:
            stream.write(manifest_bytes)
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
        receipt = _artifact_qualification(qualification_path, candidate, installer)
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
    with _pinned_artifact_stage(output) as stage:
        for host in hosts:
            parts = tuple(host.plugin_dir.split("/")) + ("helpers", "artifacts")
            stage.write_payload(parts, release_bytes, binaries)
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
        "host_default_enabled": False,
    }


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
    args = parser.parse_args(argv)
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
