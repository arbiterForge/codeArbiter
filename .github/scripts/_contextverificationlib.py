#!/usr/bin/env python3
# codeArbiter — finite test-only context verification bridge.
# run_go_case(...) -> GoObservation executes one approved named Go test.
# verify_go_output(...) -> GoObservation checks real Go JSON outcomes.
# build_installed_invocation(...) -> InstalledInvocation checks candidate inputs.
# Neither observation type is a policy receipt or live-host authority source.

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import time


class VerificationError(ValueError):
    """A candidate input or underlying test outcome is not qualified."""

    def __init__(self, message: str, *, raw_stdout: bytes = b"",
                 raw_stderr: bytes = b"", exit_code: int | None = None):
        super().__init__(message)
        self.raw_stdout = raw_stdout
        self.raw_stderr = raw_stderr
        self.exit_code = exit_code


# Selectors are copied from the exact approved plan task records T-011..T-016
# and T-049..T-052/T-054. T-053 declares Python adapter tests, not a Go target.
GO_CASES = frozenset({
    "TestBridgeFixture",
    "TestContextRepresentationBoundary",
    "TestContextDocumentContract",
    "TestContextMarkdownPreservation",
    "TestContextBoundedRender",
    "TestContextMutationAdmission",
    "TestContextRecoveryAndPaths",
    "TestGuidanceContract",
    "TestGuidanceIdentityAndEvidence",
    "TestGuidanceNativeRender",
    "TestGuidancePublicationCAS",
    "TestGuidanceGenerationRecovery",
})
MAX_STDOUT_BYTES = 1_048_576
MAX_STDERR_BYTES = 1_048_576
MAX_JSON_LINES = 8192
MAX_JSON_LINE_BYTES = 65_536
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
HEX_GIT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SUBTEST_NAME = re.compile(r"[A-Za-z0-9_/-]+\Z")


def hash_go_module(module_root: Path) -> str:
    """Bind all bounded module bytes that a Go test could read or compile."""
    try:
        root = Path(module_root).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise VerificationError("Go module is absent") from error
    if not root.is_dir() or not (root / "go.mod").is_file():
        raise VerificationError("Go module lacks go.mod")
    digest = hashlib.sha256()
    total = 0
    count = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise VerificationError("Go module contains a symlink")
        if not path.is_file():
            continue
        count += 1
        total += path.stat().st_size
        if count > 4096 or total > 64 * 1024 * 1024:
            raise VerificationError("Go module exceeds source manifest bound")
        name = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(path.stat().st_size.to_bytes(8, "big"))
        digest.update(bytes.fromhex(_sha256(path)))
    return digest.hexdigest()


@dataclass(frozen=True)
class GoObservation:
    test_name: str
    subtests: tuple[str, ...]
    exit_code: int
    raw_stdout: bytes
    raw_stderr: bytes
    go_executable: Path | None = None
    go_sha256: str = ""
    module_root: Path | None = None
    source_file: Path | None = None
    source_sha256: str = ""
    module_sha256: str = ""
    proof_kind: str = "fixture"
    live_qualified: bool = False


@dataclass(frozen=True)
class InstalledInvocation:
    argv: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]
    host: str
    plugin_root: Path
    repository: Path
    binary_sha256: str
    candidate_commit: str
    candidate_tree: str
    candidate_manifest_sha256: str
    proof_kind: str = "candidate-preflight"
    live_qualified: bool = False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object_without_duplicate_keys(pairs):
    value = {}
    for key, entry in pairs:
        if key in value:
            raise VerificationError("duplicate Go JSON key")
        value[key] = entry
    return value


def _validate_case(case: str, expected_subtests: tuple[str, ...]) -> None:
    if case not in GO_CASES:
        raise VerificationError("Go selector is outside the approved finite set")
    if not isinstance(expected_subtests, tuple) or len(expected_subtests) != len(set(expected_subtests)):
        raise VerificationError("declared Go subtests must be a unique tuple")
    if any(not isinstance(name, str) or not SUBTEST_NAME.fullmatch(name) for name in expected_subtests):
        raise VerificationError("invalid declared Go subtest")


def verify_go_output(
    raw_stdout: bytes,
    raw_stderr: bytes,
    exit_code: int,
    case: str,
    expected_subtests: tuple[str, ...],
) -> GoObservation:
    """Require one observed pass for the named Go test and every declared subtest."""
    _validate_case(case, expected_subtests)
    if not isinstance(raw_stdout, bytes) or not isinstance(raw_stderr, bytes):
        raise VerificationError("Go output must retain raw bytes")
    if not raw_stdout or len(raw_stdout) > MAX_STDOUT_BYTES or len(raw_stderr) > MAX_STDERR_BYTES:
        raise VerificationError("Go output is missing or exceeds its bound")
    if type(exit_code) is not int or exit_code != 0:
        raise VerificationError("Go process did not exit successfully")
    lines = raw_stdout.splitlines(keepends=True)
    if len(lines) > MAX_JSON_LINES or any(len(line) > MAX_JSON_LINE_BYTES for line in lines):
        raise VerificationError("Go JSON exceeds its record bound")
    if not raw_stdout.endswith(b"\n"):
        raise VerificationError("truncated Go JSON stream")

    expected = {case, *(f"{case}/{name}" for name in expected_subtests)}
    actions: dict[str, list[str]] = {name: [] for name in expected}
    selected_package = None
    package_outcomes: dict[str, list[str]] = {}
    for line in lines:
        try:
            entry = json.loads(line.decode("utf-8"), object_pairs_hook=_object_without_duplicate_keys)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise VerificationError("malformed Go JSON") from error
        if not isinstance(entry, dict):
            raise VerificationError("Go JSON record is not an object")
        action, package = entry.get("Action"), entry.get("Package")
        if action not in {"start", "run", "pause", "cont", "pass", "fail", "skip", "output", "bench"} or not isinstance(package, str) or not package:
            raise VerificationError("Go JSON record lacks a valid action or package")
        if action == "fail":
            raise VerificationError("Go reported a failed outcome")
        name = entry.get("Test")
        if name is None:
            # ./... includes packages with no selected tests. Their package
            # skip is allowed only outside the uniquely passing target package.
            if action in {"pass", "skip"}:
                package_outcomes.setdefault(package, []).append(action)
            continue
        if action == "skip":
            raise VerificationError("Go reported a skipped named outcome")
        if not isinstance(name, str) or name not in expected:
            raise VerificationError("Go selected an unexpected test or subtest")
        if selected_package is None:
            selected_package = package
        elif package != selected_package:
            raise VerificationError("named Go result crossed package identity")
        if action in {"run", "pass"}:
            actions[name].append(action)
    if selected_package is None or package_outcomes.get(selected_package) != ["pass"]:
        raise VerificationError("named Go package has no unique passing outcome")
    if any(outcomes != ["run", "pass"] for outcomes in actions.values()):
        raise VerificationError("named Go result is absent, duplicate or incomplete")
    return GoObservation(case, expected_subtests, exit_code, raw_stdout, raw_stderr)


def run_go_case(
    *, case: str, go_executable: Path, module_root: Path, source_file: Path,
    expected_go_sha256: str, expected_source_sha256: str,
    expected_module_sha256: str,
    expected_subtests: tuple[str, ...],
) -> GoObservation:
    """Run only the approved named Go selector from a bound module and source."""
    _validate_case(case, expected_subtests)
    if not all(isinstance(value, str) and HEX_SHA256.fullmatch(value)
               for value in (expected_go_sha256, expected_source_sha256, expected_module_sha256)):
        raise VerificationError("Go executable and source need exact SHA-256 identities")
    try:
        go = Path(go_executable).resolve(strict=True)
        module = Path(module_root).resolve(strict=True)
        source = Path(source_file).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise VerificationError("Go executable, module or source is absent") from error
    if not go.is_file() or go.name.lower() not in {"go", "go.exe"} or _sha256(go) != expected_go_sha256:
        raise VerificationError("Go executable identity does not match")
    if not module.is_dir() or not (module / "go.mod").is_file():
        raise VerificationError("Go cwd is not the declared module")
    if not source.is_file() or source.suffix != ".go" or not source.is_relative_to(module) or _sha256(source) != expected_source_sha256:
        raise VerificationError("Go source identity or containment does not match")
    if hash_go_module(module) != expected_module_sha256:
        raise VerificationError("Go module source identity does not match")

    with tempfile.TemporaryDirectory(prefix="ca-go-observation-") as scratch:
        scratch_path = Path(scratch)
        environment = {
            key: value for key, value in os.environ.items()
            if not key.upper().startswith(("GO", "CGO")) and key.upper() not in {"CC", "CXX", "PATH"}
        }
        environment.update({
            "GOCACHE": str(scratch_path / "gocache"),
            "GOPATH": str(scratch_path / "gopath"),
            "GOMODCACHE": str(scratch_path / "gomodcache"),
            "GOTOOLCHAIN": "local", "GOPROXY": "off", "GOSUMDB": "off",
            "GOWORK": "off", "GOENV": "off", "GOFLAGS": "", "CGO_ENABLED": "0",
            "PATH": str(go.parent),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        argv = (str(go), "test", "./...", "-count=1", "-v", "-run", f"^{case}$", "-json")
        stdout_path, stderr_path = scratch_path / "stdout", scratch_path / "stderr"
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            try:
                process = subprocess.Popen(argv, cwd=module, env=environment, stdout=stdout, stderr=stderr)
            except OSError as error:
                raise VerificationError("bound Go executable could not start") from error
            deadline = time.monotonic() + 120
            while process.poll() is None:
                if stdout_path.stat().st_size > MAX_STDOUT_BYTES or stderr_path.stat().st_size > MAX_STDERR_BYTES or time.monotonic() > deadline:
                    process.kill()
                    process.wait()
                    with stdout_path.open("rb") as captured_stdout, stderr_path.open("rb") as captured_stderr:
                        raise VerificationError(
                            "Go output bound or deadline exceeded",
                            raw_stdout=captured_stdout.read(MAX_STDOUT_BYTES),
                            raw_stderr=captured_stderr.read(MAX_STDERR_BYTES),
                            exit_code=process.returncode,
                        )
                time.sleep(0.05)
            exit_code = process.returncode
        if stdout_path.stat().st_size > MAX_STDOUT_BYTES or stderr_path.stat().st_size > MAX_STDERR_BYTES:
            with stdout_path.open("rb") as captured_stdout, stderr_path.open("rb") as captured_stderr:
                raise VerificationError(
                    "Go output bound exceeded",
                    raw_stdout=captured_stdout.read(MAX_STDOUT_BYTES),
                    raw_stderr=captured_stderr.read(MAX_STDERR_BYTES),
                    exit_code=exit_code,
                )
        raw_stdout, raw_stderr = stdout_path.read_bytes(), stderr_path.read_bytes()
    if hash_go_module(module) != expected_module_sha256 or _sha256(source) != expected_source_sha256 or _sha256(go) != expected_go_sha256:
        raise VerificationError("Go source or executable changed during the run",
                                raw_stdout=raw_stdout, raw_stderr=raw_stderr,
                                exit_code=exit_code)
    try:
        observed = verify_go_output(raw_stdout, raw_stderr, exit_code, case, expected_subtests)
    except VerificationError as error:
        raise VerificationError(str(error), raw_stdout=raw_stdout,
                                raw_stderr=raw_stderr, exit_code=exit_code) from error
    return replace(observed, go_executable=go, go_sha256=expected_go_sha256,
                   module_root=module, source_file=source,
                   source_sha256=expected_source_sha256,
                   module_sha256=expected_module_sha256)


def _native_platform() -> str:
    operating_system = {"Windows": "windows", "Linux": "linux", "Darwin": "darwin"}.get(platform.system())
    architecture = {"amd64": "amd64", "x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().casefold())
    if operating_system is None or architecture is None:
        raise VerificationError("installed host platform is unsupported")
    return f"{operating_system}/{architecture}"


def _bind_candidate_package(
    candidate: Path, plugin: Path, host: str, manifest_path: Path,
    manifest_sha256: str, commit: str, tree: str, binary_sha256: str,
) -> None:
    """Compare existing cohort and release identities with installed bytes."""
    prefix = {"claude": "plugins/ca/", "codex": "plugins/ca-codex/", "pi": "package/plugins/ca-pi/"}[host]
    if not manifest_path.is_file() or not manifest_path.is_relative_to(candidate):
        raise VerificationError("cohort manifest escaped candidate root")
    if manifest_path.stat().st_size > 4 * 1024 * 1024 or _sha256(manifest_path) != manifest_sha256:
        raise VerificationError("candidate cohort bytes do not match")
    try:
        cohort = json.loads(manifest_path.read_text(encoding="utf-8"),
                            object_pairs_hook=_object_without_duplicate_keys)
        if cohort["source_commit"] != commit or cohort["source_tree"] != tree:
            raise VerificationError("candidate source identities do not match cohort")
        members = cohort["packages"][host]["members"]
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError("candidate cohort is malformed or incomplete") from error
    if not isinstance(members, dict):
        raise VerificationError("candidate cohort members are malformed")
    expected = {}
    for name, entry in members.items():
        if not isinstance(name, str) or not name.startswith(prefix):
            continue
        relative = Path(name.removeprefix(prefix))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise VerificationError("candidate cohort path escapes plugin")
        expected[relative.as_posix()] = entry
    if not expected or "helpers/artifacts/release.json" not in expected or "hooks/_artifactlib.py" not in expected:
        raise VerificationError("candidate cohort lacks installed host essentials")
    observed = {}
    for path in plugin.rglob("*"):
        if path.is_symlink():
            raise VerificationError("candidate plugin contains a symlink")
        if path.is_file():
            observed[path.relative_to(plugin).as_posix()] = path
    if set(observed) != set(expected):
        raise VerificationError("installed plugin files differ from cohort")
    for name, path in observed.items():
        entry = expected[name]
        if (not isinstance(entry, dict) or type(entry.get("size")) is not int
                or entry["size"] != path.stat().st_size
                or entry.get("sha256") != _sha256(path)):
            raise VerificationError("installed plugin member bytes differ from cohort")

    installation = plugin / "helpers" / "artifacts"
    release = installation / "release.json"
    try:
        release_bytes = release.read_bytes()
        if len(release_bytes) > 1024 * 1024:
            raise VerificationError("candidate release manifest is unbounded")
        release_data = json.loads(release_bytes, object_pairs_hook=_object_without_duplicate_keys)
        native = release_data["binaries"][_native_platform()]
        filename = native["file"]
        if native["native_tested"] is not True or native["sha256"] != binary_sha256:
            raise VerificationError("native binary identity is not qualified")
        binary = (installation / filename).resolve(strict=True)
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError, OSError) as error:
        raise VerificationError("candidate release manifest is malformed or incomplete") from error
    if (not isinstance(filename, str) or binary.parent != installation
            or not binary.is_file() or _sha256(binary) != binary_sha256):
        raise VerificationError("native binary bytes or location do not match")


def build_installed_invocation(
    *, host: str, candidate_root: Path, plugin_root: Path, repository: Path,
    binary_sha256: str, candidate_commit: str, candidate_tree: str,
    candidate_manifest_path: Path, candidate_manifest_sha256: str, python_executable: Path,
    empty_path_dir: Path, proof_kind: str = "candidate-preflight",
) -> InstalledInvocation:
    """Prepare the existing installed-host CLI without launching a candidate."""
    if host not in {"claude", "codex", "pi"} or proof_kind != "candidate-preflight":
        raise VerificationError("unknown host or unsupported proof claim")
    if not all(isinstance(value, str) and HEX_SHA256.fullmatch(value)
               for value in (binary_sha256, candidate_manifest_sha256)):
        raise VerificationError("binary and manifest need exact SHA-256 identities")
    if not all(isinstance(value, str) and HEX_GIT_ID.fullmatch(value)
               for value in (candidate_commit, candidate_tree)):
        raise VerificationError("candidate commit and tree need exact Git identities")
    try:
        candidate = Path(candidate_root).resolve(strict=True)
        plugin = Path(plugin_root).resolve(strict=True)
        manifest = Path(candidate_manifest_path).resolve(strict=True)
        repo = Path(repository).resolve(strict=True)
        python = Path(python_executable).resolve(strict=True)
        empty = Path(empty_path_dir).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise VerificationError("candidate, repository, interpreter or PATH is absent") from error
    if not candidate.is_dir() or not plugin.is_dir() or plugin == candidate or not plugin.is_relative_to(candidate):
        raise VerificationError("plugin root is outside the candidate")
    if not repo.is_dir() or repo.is_relative_to(candidate) or candidate.is_relative_to(repo):
        raise VerificationError("owned repository overlaps candidate installation")
    if not Path(python_executable).is_absolute() or not python.is_file() or python.name.lower() not in {"python", "python3", "python.exe", "python3.exe"} and not python.name.lower().startswith("python3."):
        raise VerificationError("installed runner needs an absolute Python interpreter")
    if not empty.is_dir() or any(empty.iterdir()):
        raise VerificationError("installed runner PATH must be an existing empty directory")
    _bind_candidate_package(candidate, plugin, host, manifest,
                            candidate_manifest_sha256, candidate_commit,
                            candidate_tree, binary_sha256)
    runner = Path(__file__).with_name("test_artifact_installed_host.py").resolve(strict=True)
    host_environment = {
        "SYSTEMROOT", "WINDIR", "COMSPEC", "TMP", "TEMP", "TMPDIR",
        "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "LANG",
        "LC_ALL", "TZ",
    }
    environment = {
        key: value for key, value in os.environ.items()
        if key.upper() in host_environment
    }
    environment["PATH"] = str(empty)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    argv = (
        str(python), "-I", "-B", str(runner), "--host", host,
        "--plugin-root", str(plugin), "--repository", str(repo),
        "--expected-binary-sha256", binary_sha256,
    )
    return InstalledInvocation(argv, repo, environment, host, plugin, repo,
                               binary_sha256, candidate_commit, candidate_tree,
                               candidate_manifest_sha256)
