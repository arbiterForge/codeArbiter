"""Stage a plain Sandbox payload, then observe one original Docker test run.

The production entry has fixed owners and command construction. Only the private
unit seam accepts inert services. No source-test label, stored log or receipt can
stand in for executing the three actual shipped-bundle cases.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ".github/workflows/ci.yml"
JOB = "[CHECK] | [SBX ] | Sandbox driver contract"
PREFIX = "plugins/ca-sandbox/"
IMAGE = "node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0"
SHA = re.compile(r"(?!0{40}$)[a-f0-9]{40}")
MAX_JSON = 16 * 1024 * 1024


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate Sandbox JSON field")
        result[key] = value
    return result


def relative(value):
    require(isinstance(value, str) and value and len(value.encode()) <= 4096
            and str(PurePosixPath(value)) == value and value != "."
            and not PurePosixPath(value).is_absolute() and ".." not in PurePosixPath(value).parts
            and ":" not in value and "\\" not in value
            and not any(ord(c) < 32 or ord(c) == 127 for c in value), "unsafe Sandbox path")
    return value


def ordinary(path):
    path = Path(path).absolute()
    for part in [*reversed(path.parents), path]:
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode)
                and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                "Sandbox linked/reparse path or ancestor")
    return path


def raw(path, maximum=MAX_JSON):
    path = ordinary(path)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and 0 <= info.st_size <= maximum, "bounded ordinary Sandbox file required")
    value = path.read_bytes()
    require(len(value) == info.st_size, "Sandbox file changed during read")
    return value


def save(path, value):
    encoded = (json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()
    require(len(encoded) <= MAX_JSON, "Sandbox observation exceeds bound")
    with Path(path).open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def file_hash(path, maximum=512 * 1024 * 1024):
    path = ordinary(path)
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
            and 0 <= before.st_size <= maximum, "bounded Sandbox runtime required")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "Sandbox runtime changed during hash")
    return h.hexdigest()


def _probe_nixpacks(path, runner_temp, profile, run, *, env, cwd):
    """Read the owning acquisition output before even executing --version."""
    runner_temp = ordinary(runner_temp)
    receipt_path = runner_temp / "nixpacks-acquisition.json"
    receipt_raw = raw(receipt_path, 8192)
    acquisition = {"runner_temp": str(runner_temp), "path": str(receipt_path),
                   "sha256": sha(receipt_raw), "document_utf8": receipt_raw.decode("utf8")}
    before = file_hash(path, 16 * 1024 * 1024)
    profile.admit_nixpacks_acquisition(acquisition, str(path), before)
    done = run([str(path), "--version"], timeout=30, env=env, cwd=str(cwd))
    require(done.returncode == 0 and not done.timed_out and done.containment == "exited",
            "Sandbox Nixpacks actual version probe failed")
    version = done.stdout.strip()
    require(before == file_hash(path, 16 * 1024 * 1024)
            and raw(receipt_path, 8192) == receipt_raw, "Sandbox Nixpacks acquisition/probe drift")
    profile.admit_nixpacks_acquisition(acquisition, str(path), before, version)
    return {"path": str(path), "sha256": before, "version": version}, acquisition


def git(repo, *args, data=None):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(
        ["git", "--no-replace-objects", "--no-lazy-fetch", "-C", str(repo), *args],
        input=data, capture_output=True, timeout=30, check=True, env=env,
    )
    return result.stdout


def git_files(repo, source, roots, predicate=lambda path: True):
    require(SHA.fullmatch(source or ""), "exact Sandbox Git source required")
    listing = git(repo, "ls-tree", "-rlz", "--full-tree", source, "--", *roots)
    require(len(listing) <= 1024 * 1024, "Sandbox Git tree exceeds bound")
    selected, total = [], 0
    for line in listing.split(b"\0"):
        if not line:
            continue
        header, name = line.split(b"\t", 1)
        name = relative(name.decode("utf8"))
        if not predicate(name):
            continue
        mode, kind, oid, length = header.decode("ascii").split()
        size = int(length)
        require(mode in ("100644", "100755") and kind == "blob" and SHA.fullmatch(oid)
                and 0 <= size <= 8 * 1024 * 1024, "unsupported Sandbox Git member")
        total += size
        require(total <= 64 * 1024 * 1024 and len(selected) < 4096, "Sandbox Git inputs exceed bound")
        selected.append((name, oid, size))
    require(selected and len({p for p, _, _ in selected}) == len(selected), "Sandbox Git inputs missing or repeated")
    batch = git(repo, "cat-file", "--batch",
                data="".join(oid + "\n" for _, oid, _ in selected).encode())
    require(len(batch) <= total + len(selected) * 128, "Sandbox Git batch exceeds bound")
    result, position = {}, 0
    for name, expected_oid, expected_size in selected:
        end = batch.index(b"\n", position)
        oid, kind, size = batch[position:end].decode().split()
        require(oid == expected_oid and kind == "blob" and int(size) == expected_size,
                "Sandbox immutable blob identity differs")
        position = end + 1
        value = batch[position:position + expected_size]
        require(len(value) == expected_size and batch[position + expected_size:position + expected_size + 1] == b"\n",
                "Sandbox immutable blob read truncated")
        result[name] = value
        position += expected_size + 1
    require(position == len(batch), "Sandbox immutable batch has extra bytes")
    return result


def inventory(root, *, modules=False):
    root = ordinary(root)
    require(root.is_dir(), "Sandbox inventory root unavailable")
    result, total, seen = {}, 0, 0
    queue = [root]
    while queue:
        parent = queue.pop()
        for path in sorted(parent.iterdir()):
            name = relative(path.relative_to(root).as_posix())
            if modules and name.split("/", 1)[0] in (".vite", ".vite-temp"):
                continue
            seen += 1
            require(seen <= (65536 if modules else 2048), "Sandbox inventory exceeds bound")
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                require(modules and path.parent == root / ".bin", "Sandbox unexpected symbolic link")
                target = os.readlink(path)
                resolved = path.resolve(strict=True)
                require(not Path(target).is_absolute() and resolved.is_relative_to(root)
                        and resolved.is_file(), "Sandbox npm bin link leaves tool graph")
                result[name] = {"size": len(target.encode()), "sha256": sha(target.encode()), "link": target}
            else:
                require(not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                        "Sandbox inventory contains a reparse object")
                if stat.S_ISDIR(info.st_mode):
                    queue.append(path)
                else:
                    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                            and info.st_size <= (64 if modules else 8) * 1024 * 1024,
                            "Sandbox unsupported inventory member")
                    total += info.st_size
                    require(total <= (256 if modules else 16) * 1024 * 1024,
                            "Sandbox inventory bytes exceed bound")
                    result[name] = {"size": info.st_size, "sha256": file_hash(path)}
    require(result, "Sandbox inventory empty")
    return {"root": str(root), "members": result}


def empty_native_lock(repo):
    path = Path(repo)
    try:
        for name in (".codearbiter", ".artifacts", "store.lock"):
            path = path / name
            info = path.lstat()
            if path.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                return False
            if name != "store.lock" and not stat.S_ISDIR(info.st_mode):
                return False
        return stat.S_ISREG(info.st_mode) and info.st_size == 0 and info.st_nlink == 1
    except OSError:
        return False


def source_snapshot(repo, source):
    repo = ordinary(repo)
    require(git(repo, "rev-parse", "HEAD").decode().strip() == source, "Sandbox source HEAD differs")
    tree = git(repo, "rev-parse", source + "^{tree}").decode().strip()
    rows = git(repo, "status", "--porcelain=v1", "--untracked-files=all", "-z").decode().split("\0")
    require(all(not row or row == "?? .codearbiter/.artifacts/store.lock" and empty_native_lock(repo)
                for row in rows), "Sandbox source is not clean")
    python_roots = (".github/scripts", "core/pysrc", "tools")
    roots = (*python_roots, "core/surface", "core/hosts.json", "plugins/ca-sandbox")
    selected = git_files(repo, source, roots, lambda name:
                         name.endswith(".py") or name.startswith(("core/surface/", PREFIX))
                         or name == "core/hosts.json")
    inputs = {}
    for name, value in selected.items():
        require(raw(repo / name, 8 * 1024 * 1024) == value, "Sandbox physical source differs from immutable Git")
        inputs[name] = sha(value)
    memberships = {}
    for folder in python_roots:
        physical = sorted(p.relative_to(repo).as_posix() for p in (repo / folder).rglob("*.py")
                          if "__pycache__" not in p.relative_to(repo / folder).parts)
        expected = sorted(p for p in selected if p.startswith(folder + "/") and p.endswith(".py"))
        require(physical == expected, "Sandbox Python lookup membership differs")
        memberships[folder] = physical
    for folder in ("core/surface", "plugins/ca-sandbox"):
        physical = []
        for current, directories, files in os.walk(repo / folder, followlinks=False):
            parent = Path(current)
            for name in directories[:]:
                path = parent / name
                if path == repo / "plugins/ca-sandbox/tools/node_modules":
                    directories.remove(name)
                else:
                    ordinary(path)
            for name in files:
                path = parent / name
                raw(path, 8 * 1024 * 1024)
                physical.append(path.relative_to(repo).as_posix())
        expected = sorted(p for p in selected if p.startswith(folder + "/"))
        require(sorted(physical) == expected, "Sandbox data membership differs")
        memberships[folder] = expected
    return {"source_commit": source, "source_tree": tree, "clean": True,
            "inputs": inputs, "memberships": memberships}


def stage_payload(repo, source, output, *, run_attempt):
    """Create only a new plain plugin copy from immutable Git, never build."""
    repo, output = ordinary(repo), Path(output).absolute()
    require(type(run_attempt) is int and 0 < run_attempt < 10000, "positive Sandbox attempt required")
    ordinary(output.parent)
    require(not output.exists() and not output.is_symlink(), "new exclusive Sandbox payload root required")
    values = git_files(repo, source, ["plugins/ca-sandbox"])
    require(len(values) <= 1024 and sum(map(len, values.values())) <= 16 * 1024 * 1024,
            "Sandbox plain plugin exceeds bound")
    manifest = json.loads(values[PREFIX + ".claude-plugin/plugin.json"], object_pairs_hook=pairs)
    require(manifest.get("name") == "ca-sandbox"
            and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", manifest.get("version", "")),
            "Sandbox plain manifest differs")
    receipt = {"format": "codearbiter.sandbox-plain-payload/1", "source_commit": source,
               "source_tree": git(repo, "rev-parse", source + "^{tree}").decode().strip(),
               "workflow": WORKFLOW, "version": manifest["version"], "plugin_root": "plugins/ca-sandbox",
               "execution_run_attempt": run_attempt,
               "members": {name.removeprefix(PREFIX): {"size": len(value), "sha256": sha(value)}
                           for name, value in values.items()}}
    output.mkdir()
    for name, value in values.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(value)
    save(output / "artifact-sandbox-payload.json", receipt)
    return {"artifact_name": "artifact-sandbox-plugin-" + source + "-" + str(run_attempt),
            "receipt": receipt, "payload": inventory(output)}


def child_environment(home, paths, parent=None):
    parent = os.environ if parent is None else parent
    env = {k: v for k, v in parent.items()
           if k.upper() in {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "CI"}}
    home = Path(home).absolute()
    for path in (home, home / "tmp", home / "appdata", home / "localappdata",
                 home / "config", home / "docker", home / "cache"):
        path.mkdir(parents=True, exist_ok=True)
    env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home / "appdata"),
               LOCALAPPDATA=str(home / "localappdata"), XDG_CONFIG_HOME=str(home / "config"),
               XDG_CACHE_HOME=str(home / "cache"), DOCKER_CONFIG=str(home / "docker"),
               TEMP=str(home / "tmp"), TMP=str(home / "tmp"),
               PATH=os.pathsep.join(dict.fromkeys(paths)), PYTHONNOUSERSITE="1",
               PYTHONDONTWRITEBYTECODE="1", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0", NPM_CONFIG_OFFLINE="true", NPM_CONFIG_AUDIT="false",
               NPM_CONFIG_UPDATE_NOTIFIER="false", NPM_CONFIG_USERCONFIG=str(home / "absent.npmrc"),
               NPM_CONFIG_GLOBALCONFIG=str(home / "absent-global.npmrc"))
    if "CA_SANDBOX_REQUIRE_DOCKER" in parent:
        env["CA_SANDBOX_REQUIRE_DOCKER"] = parent["CA_SANDBOX_REQUIRE_DOCKER"]
    return env


@contextmanager
def control_environment(home, paths, *, api_token=False):
    """Private import/API home; only the control process keeps its CI token."""
    before, old_temp = dict(os.environ), tempfile.tempdir
    env = child_environment(home, paths, before)
    allowed = ["GITHUB_ACTIONS", "GITHUB_REPOSITORY", "GITHUB_EVENT_NAME",
               "GITHUB_REF", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"]
    if api_token:
        allowed.extend(("GH_TOKEN", "GITHUB_TOKEN"))
    for name in allowed:
        if name in before:
            env[name] = before[name]
    env.update(GH_PROMPT_DISABLED="1", GH_HOST="github.com")
    try:
        os.environ.clear()
        os.environ.update(env)
        tempfile.tempdir = None
        yield
    finally:
        os.environ.clear()
        os.environ.update(before)
        tempfile.tempdir = old_temp


@contextmanager
def project_modules(repo, bytecode):
    original, paths, prefix, no_write = dict(sys.modules), sys.path[:], sys.pycache_prefix, sys.dont_write_bytecode
    try:
        names = {p.stem for folder in ("core/pysrc", ".github/scripts", "tools")
                 for p in (repo / folder).glob("*.py")} | {"_host", "_release_mechanism"}
        for name in names:
            sys.modules.pop(name, None)
        standard = [p for p in sys.path if p and
                    Path(p).absolute().is_relative_to(Path(sys.base_prefix).absolute())]
        sys.path[:] = [str(repo / ".github/scripts"), str(repo / "tools"),
                       str(repo / "core/pysrc"), *standard]
        Path(bytecode).mkdir()
        sys.pycache_prefix, sys.dont_write_bytecode = str(bytecode), True
        yield
    finally:
        for name in set(sys.modules) - set(original):
            sys.modules.pop(name, None)
        sys.modules.update(original)
        sys.path[:], sys.pycache_prefix, sys.dont_write_bytecode = paths, prefix, no_write


def normalize_results(value, repo):
    require(isinstance(value, dict) and value.get("success") is True
            and isinstance(value.get("testResults"), list), "Sandbox original Vitest JSON failed or absent")
    rows, seen = [], set()
    for suite in value["testResults"]:
        name = Path(suite["name"]).resolve(strict=True).relative_to(repo).as_posix()
        for case in suite["assertionResults"]:
            identity = "vitest:" + name + ":" + case["fullName"]
            require(identity not in seen and case["status"] == "passed", "Sandbox named case failed/repeated/skipped")
            seen.add(identity)
            rows.append({"id": identity, "result": "passed"})
    require(0 < len(rows) <= 32768 and value.get("numTotalTests") == value.get("numPassedTests") == len(rows)
            and value.get("numFailedTests") == value.get("numPendingTests") == 0,
            "Sandbox original named population incomplete")
    return rows


def _observe(config, services):
    """One fixed original run. Services are actual owners or inert unit seams."""
    c, s = config, services
    out = Path(c["output_dir"])
    require(out.is_dir() and not any(out.iterdir()), "new empty Sandbox result directory required")
    completion = out / "suite-execution.json"
    command = []
    error = None
    observation = None
    admitted = False
    with tempfile.TemporaryDirectory(prefix="ca-sandbox-observer-private-") as raw_private:
        private = Path(raw_private).resolve(strict=True)
        try:
            expected = c["expected"]
            s.profile.validate_expected(expected)
            source_before = s.source_snapshot()
            payload_before = s.payload_snapshot()
            receipt_raw = raw(c["payload_root"] / "artifact-sandbox-payload.json", 1024 * 1024)
            manifest_raw = raw(c["payload_root"] / "plugins/ca-sandbox/.claude-plugin/plugin.json", 65536)
            attempt = expected["execution_run_attempt"]
            name = "artifact-sandbox-plugin-" + expected["source_commit"] + "-" + str(attempt)
            auth = s.authenticated_payloads.get(name, {})
            plugin = c["payload_root"] / "plugins/ca-sandbox"
            s.profile.admit_payload_binding({
                "source_before": source_before, "payload_before": payload_before,
                "installed_root": str(plugin), "payload_document_utf8": receipt_raw.decode("utf8"),
                "manifest_document_utf8": manifest_raw.decode("utf8"),
                "payload": {"artifact_name": name, **{
                    k: auth.get(k) for k in ("artifact_id", "archive_sha256", "members")}},
            }, expected, s.authenticated_payloads)
            admitted = True
            runtime_before = s.runtime_snapshot()
            save(out / "inputs-before.json", {"source": source_before, "runtime": runtime_before, "payload": payload_before})
            results, sentinel, trace = out / "sandbox-vitest.json", out / "sandbox-docker-layers.sentinel", out / "sandbox-bundle-cases.jsonl"
            with trace.open("xb"):
                pass
            binaries = runtime_before["binaries"]
            env = child_environment(private / "home", [str(Path(binaries["nixpacks"]["path"]).parent),
                *[str(Path(v["path"]).parent) for v in binaries.values()]])
            require(env.get("CA_SANDBOX_REQUIRE_DOCKER") == "1", "Sandbox original required-Docker mode absent")
            fixture_root = private / "fixtures"
            fixture_root.mkdir()
            env.update(CA_SANDBOX_INSTALLED_PLUGIN=str(plugin),
                       CA_SANDBOX_BUNDLE_OBSERVATION=str(trace), CA_SANDBOX_BUNDLE_TMP_ROOT=str(fixture_root),
                       CA_SANDBOX_DOCKER_SENTINEL=str(sentinel))
            command = [binaries["node"]["path"], binaries["npm"]["path"], "test", "--",
                       "--reporter=default", "--reporter=github-actions", "--reporter=json", "--no-cache",
                       "--outputFile.json=" + str(results)]
            done = s.spawn(command, timeout=2400, cwd=str(c["repo"] / "plugins/ca-sandbox/tools"), env=env)
            terminal = {"argv": command, "returncode": done.returncode, "timed_out": done.timed_out,
                        "containment": done.containment, "stdout_utf8_projection_sha256": sha(done.stdout.encode()),
                        "stderr_utf8_projection_sha256": sha(done.stderr.encode())}
            save(completion, terminal)  # Always before assertions or JSON parsing.
            # Preserve the original trusted CI reporters and their annotations.
            # These are UTF-8 projections from the bounded owner, not raw-byte
            # claims; the exact original Vitest JSON remains separate.
            for stream_name, text in (("stdout", done.stdout), ("stderr", done.stderr)):
                projection = text.encode("utf8")
                require(len(projection) <= 64 * 1024 * 1024, "Sandbox console projection exceeds bound")
                with (out / (stream_name + "-utf8-projection.log")).open("xb") as stream:
                    stream.write(projection)
                print(text, file=sys.stdout if stream_name == "stdout" else sys.stderr, end="", flush=True)
            require(type(done.returncode) is int and done.returncode == 0 and done.timed_out is False
                    and done.containment == "exited", "Sandbox original suite failed or containment unknown")
            result_raw, sentinel_raw, trace_raw = raw(results), raw(sentinel, 65536), raw(trace, 1024 * 1024)
            tests = normalize_results(json.loads(result_raw, object_pairs_hook=pairs), c["repo"])
            layers = s.declared_layers()
            recorded = sorted(set(sentinel_raw.decode("utf8").splitlines()))
            require(recorded == sorted(layers) and all(len(v) == 1 for v in layers.values()),
                    "Sandbox complete source layer sentinel differs")
            witnesses = [json.loads(line, object_pairs_hook=pairs) for line in trace_raw.splitlines()]
            source_after, runtime_after, payload_after = s.source_snapshot(), s.runtime_snapshot(), s.payload_snapshot()
            save(out / "inputs-after.json", {"source": source_after, "runtime": runtime_after, "payload": payload_after})
            selected = [{"id": s.profile.TEST_PREFIX + name, "result": "passed"} for name in s.profile.NAMES]
            binding = {"format": "codearbiter.installed-observation-binding/1", "profile": s.profile.PROFILE,
                       **expected, "workflow": WORKFLOW,
                       "payload": {"artifact_name": name, **{k: auth[k] for k in ("artifact_id", "archive_sha256", "members")}},
                       "payload_document_utf8": receipt_raw.decode("utf8"), "installed_root": str(plugin),
                       "manifest_document_utf8": manifest_raw.decode("utf8"),
                       "source_before": source_before, "source_after": source_after,
                       "runtime_before": runtime_before, "runtime_after": runtime_after,
                       "payload_before": payload_before, "payload_after": payload_after,
                       "suite": {"argv": command, "cwd": str(c["repo"] / "plugins/ca-sandbox/tools"),
                                 "exit_code": done.returncode, "timed_out": done.timed_out, "containment": done.containment,
                                 "raw_sha256": sha(result_raw), "sentinel_sha256": sha(sentinel_raw),
                                 "declared_layers": layers, "recorded_layers": recorded, "tests": tests},
                       "witnesses": witnesses}
            observation = {"format": "codearbiter.major-test-observation/1",
                           **{k: expected[k] for k in ("source_commit", "source_tree", "ci_run_id")},
                           "source_stable": source_before == source_after, "proof_kind": "live-host",
                           "producer": s.profile.PRODUCER, "argv": command, "exit_code": 0,
                           "tests": selected, "installed_binding": binding}
            s.profile.admit(observation, expected=expected, authenticated_payloads=s.authenticated_payloads)
        except BaseException as caught:
            error = caught
            save(out / "failure.json", {"type": type(caught).__name__,
                                      "diagnostic_sha256": sha(str(caught).encode("utf8", errors="replace"))})
        finally:
            snapshots = {}
            readers = [("source", s.source_snapshot), ("payload", s.payload_snapshot)]
            if admitted:
                readers.append(("runtime", s.runtime_snapshot))
            else:
                snapshots["runtime"] = {"not_observed_before_payload_admission": True}
            for key, reader in readers:
                try:
                    snapshots[key] = reader()
                except BaseException as caught:
                    snapshots[key] = {"unavailable": type(caught).__name__}
            save(out / "inputs-terminal-before-cleanup.json", snapshots)
    # TemporaryDirectory performs its finite owned cleanup before affirmative output.
    save(out / "cleanup.json", {"private_home_removed": not private.exists()})
    if error is not None:
        raise error
    require(not private.exists(), "Sandbox private cleanup incomplete")
    require(s.source_snapshot() == source_before and s.runtime_snapshot() == runtime_before
            and s.payload_snapshot() == payload_before, "Sandbox inputs changed after cleanup")
    if c.get("_defer_observation") is not True:
        save(out / "observation.json", observation)
    return observation


def produce(config, *, authenticated_payloads):
    """Actual public producer; it accepts no runner, saved log or pass flag."""
    c = dict(config)
    repo = ordinary(c["repo"]).resolve(strict=True)
    expected = c["expected"]
    # Validate immutable dependencies before any project imports or suite effects.
    require(Path(__file__).resolve() == repo / ".github/scripts/observe_sandbox_installed_docker.py",
            "Sandbox controller is outside selected source")
    source_snapshot(repo, expected["source_commit"])
    runner_temp_value = os.environ.get("RUNNER_TEMP")
    require(runner_temp_value and Path(runner_temp_value).is_absolute(),
            "Sandbox Nixpacks same-job runner temporary directory required")
    runner_temp = ordinary(runner_temp_value)
    require(runner_temp.is_dir(), "Sandbox Nixpacks runner temporary directory unavailable")
    payload_root = ordinary(c["payload_root"]).resolve(strict=True)
    output = Path(c["output_dir"]).absolute()
    ordinary(output.parent)
    require(not output.exists() and not output.is_symlink(), "new Sandbox result directory required")
    require(not output.is_relative_to(repo) and not output.is_relative_to(payload_root),
            "Sandbox durable output must be outside source and consumed payload")
    output.mkdir()
    c.update(repo=repo, payload_root=payload_root, output_dir=output)
    runtime_paths = []
    for name in ("node", "npm", "docker", "git", "nixpacks", "gh"):
        found = shutil.which(name)
        if found:
            runtime_paths.append(str(Path(found).resolve(strict=True).parent))
    runtime_paths.append(str(Path(sys.executable).parent))
    with tempfile.TemporaryDirectory(prefix="ca-sandbox-import-control-") as temporary:
        control = Path(temporary).resolve(strict=True)
        with control_environment(control / "home", runtime_paths), project_modules(repo, control / "bytecode"):
            import _boundedproc
            import _sandbox_docker_profile as profile
            import check_sandbox_docker_layers as scanner
            binaries = {}
            for key in ("node", "docker", "git", "nixpacks"):
                found = shutil.which(key)
                require(found is not None, "Sandbox reviewed runtime unavailable")
                binaries[key] = Path(found).resolve(strict=True)
            binaries["python"] = Path(sys.executable).resolve(strict=True)
            npm = shutil.which("npm")
            require(npm is not None, "Sandbox reviewed npm unavailable")
            binaries["npm"] = Path(npm).resolve(strict=True)
            require(binaries["npm"].name == "npm-cli.js", "Sandbox npm must be the resolved Linux CLI script")
            def runtime_snapshot():
                paths = [str(binaries["nixpacks"].parent), *[str(p.parent) for p in binaries.values()]]
                env = child_environment(control / "runtime-home", paths)
                nixpacks, acquisition = _probe_nixpacks(binaries["nixpacks"], runner_temp, profile,
                                                       _boundedproc.run, env=env, cwd=control)
                identities = {"nixpacks": nixpacks}
                for key, path in binaries.items():
                    if key == "nixpacks":
                        continue
                    before = file_hash(path)
                    argv = ([str(binaries["node"]), str(path), "--version"]
                            if key == "npm" else [str(path), "--version"])
                    done = _boundedproc.run(argv, timeout=30, env=env, cwd=str(control))
                    require(done.returncode == 0 and not done.timed_out and done.containment == "exited",
                            "Sandbox actual runtime version probe failed")
                    version = (done.stdout or done.stderr).strip()
                    require(before == file_hash(path) and 0 < len(version) <= 512, "Sandbox runtime probe drift")
                    identities[key] = {"path": str(path), "sha256": before, "version": version}
                daemon = _boundedproc.run([str(binaries["docker"]), "info", "--format", "{{.OSType}}"],
                                         timeout=30, env=env, cwd=str(control))
                require(daemon.returncode == 0 and not daemon.timed_out and daemon.containment == "exited"
                        and daemon.stdout.strip() == "linux", "Sandbox requires actual Linux Docker")
                inspected = _boundedproc.run([str(binaries["docker"]), "image", "inspect", IMAGE],
                                            timeout=30, env=env, cwd=str(control))
                require(inspected.returncode == 0 and not inspected.timed_out and inspected.containment == "exited",
                        "Sandbox reviewed pinned image is not already available")
                images = json.loads(inspected.stdout, object_pairs_hook=pairs)
                require(isinstance(images, list) and len(images) == 1, "Sandbox image identity ambiguous")
                value = images[0]
                image = {"reference": IMAGE, "id": value["Id"], "repo_digests": sorted(value["RepoDigests"]),
                         "os": value["Os"], "architecture": value["Architecture"]}
                profile.image(image)
                return {"binaries": identities,
                        "modules": inventory(repo / "plugins/ca-sandbox/tools/node_modules", modules=True),
                        "image": image, "nixpacks_acquisition": acquisition}
            services = SimpleNamespace(
                source_snapshot=lambda: source_snapshot(repo, expected["source_commit"]),
                runtime_snapshot=runtime_snapshot,
                payload_snapshot=lambda: {"root": str(payload_root), "members": {
                    p: v["sha256"] for p, v in inventory(payload_root)["members"].items()}},
                declared_layers=lambda: scanner.declared_layer_sites(repo),
                spawn=_boundedproc.run, profile=profile, authenticated_payloads=authenticated_payloads,
            )
            c["_defer_observation"] = True
            observation = _observe(c, services)
    require(not control.exists(), "Sandbox control-home cleanup incomplete")
    binding = observation["installed_binding"]
    require(source_snapshot(repo, expected["source_commit"]) == binding["source_before"]
            and {p: v["sha256"] for p, v in inventory(payload_root)["members"].items()} ==
            binding["payload_before"]["members"], "Sandbox source or payload changed after control cleanup")
    for identity in binding["runtime_before"]["binaries"].values():
        require(file_hash(identity["path"]) == identity["sha256"],
                "Sandbox runtime changed after control cleanup")
    acquisition = binding["runtime_before"]["nixpacks_acquisition"]
    require(raw(acquisition["path"], 8192).decode("utf8") == acquisition["document_utf8"],
            "Sandbox Nixpacks acquisition changed after control cleanup")
    require(inventory(repo / "plugins/ca-sandbox/tools/node_modules", modules=True) ==
            binding["runtime_before"]["modules"], "Sandbox tool graph changed after control cleanup")
    save(output / "control-cleanup.json", {"private_control_home_removed": True,
                                         "module_registry_restored": True,
                                         "immutable_inputs_stable": True})
    save(output / "observation.json", observation)
    return observation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("stage", "observe"))
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--source")
    parser.add_argument("--attempt", type=int)
    parser.add_argument("--payload-root", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.operation == "stage":
        require(args.source and args.attempt, "Sandbox stage requires exact source and attempt")
        record = stage_payload(args.repo, args.source, args.payload_root, run_attempt=args.attempt)
        print(json.dumps({"artifact_name": record["artifact_name"], "source_commit": args.source,
                          "execution_run_attempt": args.attempt}))
        return 0
    require(args.output_dir is not None, "Sandbox observation output directory required")
    source = os.environ.get("GITHUB_SHA", "")
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_REPOSITORY") == "arbiterForge/codeArbiter"
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") in ("refs/heads/main", "refs/heads/major/state-contracts"),
            "Sandbox observer requires actual normal trusted push CI")
    source_snapshot(args.repo, source)
    runtime_paths = []
    for name in ("node", "npm", "docker", "git", "nixpacks", "gh"):
        found = shutil.which(name)
        if found:
            runtime_paths.append(str(Path(found).resolve(strict=True).parent))
    runtime_paths.append(str(Path(sys.executable).parent))
    require(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"),
            "Sandbox control API requires its explicit CI token")
    with tempfile.TemporaryDirectory(prefix="ca-sandbox-api-control-") as temporary:
        with control_environment(Path(temporary) / "home", runtime_paths, api_token=True), project_modules(args.repo.resolve(strict=True), Path(temporary) / "bytecode"):
            import major_readiness as readiness
            import major_qualification_report as reporter
            run_id, attempt = int(os.environ["GITHUB_RUN_ID"]), int(os.environ["GITHUB_RUN_ATTEMPT"])
            run = readiness.api(f"actions/runs/{run_id}")
            require(type(run.get("id")) is int and run.get("id") == run_id
                    and run.get("head_sha") == source and run.get("event") == "push" and run.get("path") == WORKFLOW
                    and run.get("repository", {}).get("full_name") == readiness.REPOSITORY
                    and run.get("head_branch") == os.environ["GITHUB_REF"].removeprefix("refs/heads/"),
                    "Sandbox original workflow source differs")
            def population(route, key):
                pages = json.loads(readiness.command([
                    "gh", "api", "--paginate", "--slurp", "repos/" + readiness.REPOSITORY + "/" + route]))
                require(isinstance(pages, list) and 0 < len(pages) <= 18, "Sandbox API pages exceed bound")
                rows = [row for page in pages for row in page[key]]
                require(len(rows) <= 512 and len({r["id"] for r in rows}) == len(rows),
                        "Sandbox API population invalid")
                return rows
            jobs = population(f"actions/runs/{run_id}/jobs?filter=latest&per_page=30", "jobs")
            selected = [j for j in jobs if j.get("name") == JOB and j.get("status") == "in_progress"
                        and j.get("run_id") == run_id and type(j.get("run_attempt")) is int
                        and j.get("run_attempt") == attempt and type(j.get("id")) is int and j["id"] > 0]
            require(len(selected) == 1, "actual current Sandbox job/attempt missing or ambiguous")
            expected = {"source_commit": source,
                        "source_tree": git(args.repo, "rev-parse", source + "^{tree}").decode().strip(),
                        "ci_run_id": run_id, "producer_job_id": selected[0]["id"],
                        "execution_run_attempt": selected[0]["run_attempt"]}
            name = "artifact-sandbox-plugin-" + source + "-" + str(expected["execution_run_attempt"])
            artifacts = population(f"actions/runs/{run_id}/artifacts?per_page=30", "artifacts")
            found = [a for a in artifacts if a.get("name") == name]
            require(len(found) == 1, "original attempt-qualified Sandbox payload unavailable")
            # Same-job pre-effect payload admission follows the native builder's
            # API/archive byte join. Full successful upload attribution belongs
            # to the final completed-job reader, not invented in-progress logs.
            auth = reporter.authenticated_payload(found[0], expected, args.payload_root)
    # API credentials and module/import scratch end before actual test effects.
    produce({"repo": args.repo, "payload_root": args.payload_root,
             "output_dir": args.output_dir, "expected": expected}, authenticated_payloads={name: auth})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print("::error::Sandbox installed observer refused; diagnostic_sha256=" +
              sha(str(error).encode("utf8", errors="replace")), file=sys.stderr)
        raise SystemExit(1)
