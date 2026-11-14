"""One-run retained cold-package observations; no label-only installed admission.

This profile proves direct extracted helper workflows, not upstream TUI discovery,
physical consent, provider access, or versioned Pi/Codex/Docker qualification.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile

FORMAT = "codearbiter.installed-observation-binding/1"
PROFILE = "retained-cold-package-v1"
PRODUCER = "retained-cold-package-observer-v1"
OBSERVATION = "codearbiter.major-test-observation/1"
WORKFLOW = ".github/workflows/ci.yml"
ROOT = Path(__file__).resolve().parents[2]
SHA = re.compile(r"(?!0{40}$)[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")
PLATFORMS = frozenset(s + "/" + a for s in ("linux", "windows", "darwin") for a in ("amd64", "arm64"))
CONTEXT_NAMES = ("test_t044_installed_context_kind", "test_t044_rejects_missing_candidate_identity", "test_t044_rejects_nonisolated_environment")
HOST_DIRS = {"claude": "plugins/ca", "codex": "plugins/ca-codex", "pi": "plugins/ca-pi"}
BINDING_FIELDS = {"format", "profile", "source_commit", "source_tree", "workflow", "ci_run_id", "producer_job_id", "host", "platform", "consumed_payloads", "cohort_sha256", "promotion_receipt_sha256", "documents", "cold_receipt", "source_before", "source_after", "runtime_before", "runtime_after", "payload_before", "payload_after"}
RECEIPT_FIELDS = {"format", "source_commit", "workflow", "run_id", "job", "host", "platform", "promotion_receipt_sha256", "package_sha256", "manifest_sha256", "binary_sha256", "response_sha256", "operation", "repository_operations_available", "runtime_downloads", "installed_workflow_response_sha256", "installed_bridge_sha256", "installed_workflow_format", "approval_evidence_mode", "prerequisite_evidence_mode", "interruption_reconciled", "redispatched", "commit_proof", "finalization_proof", "all_accepted_and_current", "markdown_shadow_count", "context_workflow_scope", "context_installed_tests", "context_installed_output_sha256"}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate installed observation field")
        result[key] = value
    return result


def safe_path(value):
    require(isinstance(value, str) and 0 < len(value.encode()) <= 4096, "invalid installed member path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and str(path) == value and value != "." and ".." not in path.parts
            and ":" not in value and "\\" not in value and not any(ord(c) < 32 for c in value), "unsafe installed member path")
    return value


def members(values):
    require(isinstance(values, list) and 0 < len(values) <= 4096, "missing installed payload members")
    result = {}
    for row in values:
        require(isinstance(row, dict) and set(row) == {"path", "sha256"}, "invalid installed member")
        path = safe_path(row["path"])
        require(path not in result and isinstance(row["sha256"], str) and DIGEST.fullmatch(row["sha256"]), "duplicate/invalid installed member digest")
        result[path] = row["sha256"]
    return result


def payload_projection(value):
    require(isinstance(value, dict), "missing authenticated installed payload")
    result = {key: value.get(key) for key in ("artifact_id", "archive_sha256", "members")}
    require(type(result["artifact_id"]) is int and result["artifact_id"] > 0
            and isinstance(result["archive_sha256"], str) and DIGEST.fullmatch(result["archive_sha256"]), "invalid installed artifact identity")
    members(result["members"])
    return result


def decode_document(binding, key, role, path, payload_maps):
    document = binding["documents"][key]
    require(isinstance(document, dict) and set(document) == {"path", "json_utf8"}
            and document["path"] == path and isinstance(document["json_utf8"], str)
            and 0 < len(document["json_utf8"].encode("utf-8")) <= 8 * 1024 * 1024, "invalid bounded installed document")
    raw = document["json_utf8"].encode("utf-8")
    require(payload_maps[role].get(path) == digest(raw), "installed document differs from authenticated payload")
    value = json.loads(raw, object_pairs_hook=pairs)
    require(isinstance(value, dict), "installed document must be an object")
    return value, digest(raw)


def _admit(observation, *, req, job_id, authenticated_payloads, repo=ROOT):
    """Re-derive profile facts against exact authenticated consumed artifacts."""
    require(observation.get("format") == OBSERVATION and observation.get("proof_kind") == "retained-archive-cli"
            and observation.get("producer") == PRODUCER, "no qualified retained cold observer")
    binding = observation.get("installed_binding")
    require(isinstance(binding, dict) and set(binding) == BINDING_FIELDS
            and binding["format"] == FORMAT and binding["profile"] == PROFILE, "unknown or incomplete installed profile")
    require(SHA.fullmatch(binding["source_commit"] or "") and SHA.fullmatch(binding["source_tree"] or "")
            and binding["source_commit"] == req["source_commit"] == observation.get("source_commit")
            and binding["source_tree"] == req["source_tree"] == observation.get("source_tree")
            and binding["workflow"] == WORKFLOW and type(binding["ci_run_id"]) is int
            and binding["ci_run_id"] > 0 and binding["ci_run_id"] == req["ci_run_id"] == observation.get("ci_run_id")
            and type(binding["producer_job_id"]) is int and binding["producer_job_id"] == job_id > 0
            and observation.get("source_stable") is True and type(observation.get("exit_code")) is int
            and observation["exit_code"] == 0, "installed source/run/job/execution differs")
    require(len(json.dumps(binding, ensure_ascii=True).encode("utf-8")) <= 16 * 1024 * 1024, "installed binding exceeds bound")
    host, platform = binding["host"], binding["platform"]
    require(host in HOST_DIRS and platform in PLATFORMS, "unsupported installed host/platform")
    consumed = binding["consumed_payloads"]
    require(isinstance(consumed, dict) and set(consumed) == {"promoted-stage", "release-packages"}, "exact installed artifact pair required")
    payload_maps, admitted_payloads = {}, []
    for role, prefix in (("promoted-stage", "artifact-host-payloads-"), ("release-packages", "artifact-release-packages-")):
        value = consumed[role]
        require(isinstance(value, dict) and set(value) == {"artifact_name", "artifact_id", "archive_sha256", "members"}
                and value["artifact_name"] == prefix + req["source_commit"], "installed payload name/role differs")
        actual = payload_projection(authenticated_payloads.get(value["artifact_name"]))
        require(payload_projection(value) == actual, "installed payload differs from authenticated consumed archive")
        payload_maps[role] = members(actual["members"])
        admitted_payloads.append(actual)
    require(admitted_payloads[0]["artifact_id"] != admitted_payloads[1]["artifact_id"], "installed artifact roles must be distinct")
    for name in ("source", "runtime", "payload"):
        before, after = binding[name + "_before"], binding[name + "_after"]
        require(isinstance(before, dict) and before and before == after, "installed " + name + " inputs changed or unavailable")
    source = binding["source_before"]
    require(set(source) == {"repository", "source_commit", "source_tree", "clean", "inputs", "core_python_members", "host_lookup"}
            and source["source_commit"] == req["source_commit"] and source["source_tree"] == req["source_tree"]
            and source["clean"] is True and isinstance(source["inputs"], dict) and 0 < len(source["inputs"]) <= 2048, "installed source capture incomplete")
    for path, value in source["inputs"].items():
        safe_path(path)
        require(isinstance(value, str) and DIGEST.fullmatch(value), "invalid source capture digest")
    require(isinstance(source["core_python_members"], list) and source["core_python_members"]
            and source["core_python_members"] == sorted(set(source["core_python_members"])), "invalid core Python membership")
    lookup = source["host_lookup"]
    require(isinstance(lookup, dict) and set(lookup) == {"path", "path_style", "present"}
            and lookup == {"path": "core/pysrc/_host.py", "path_style": "windows" if platform.startswith("windows/") else "posix", "present": False}, "host lookup capture differs")
    runtime = binding["runtime_before"]
    require(set(runtime) == {"python", "git"}, "cold runtime identity incomplete")
    for identity in runtime.values():
        require(isinstance(identity, dict) and set(identity) == {"path", "sha256"}
                and absolute_path(identity["path"])
                and isinstance(identity["sha256"], str) and DIGEST.fullmatch(identity["sha256"]), "invalid cold runtime identity")
    for role in payload_maps:
        stamp = binding["payload_before"].get(role)
        require(isinstance(stamp, dict) and set(stamp) == {"root", "members"}
                and isinstance(stamp["root"], str) and absolute_path(stamp["root"])
                and stamp["members"] == payload_maps[role], "cold physical payload membership differs")
    require(set(binding["payload_before"]) == set(payload_maps), "unexpected cold payload capture")
    require(isinstance(binding["documents"], dict) and set(binding["documents"]) == {"cohort", "promotion", "manifest"}, "cold bound documents incomplete")
    prefix = HOST_DIRS[host] + "/helpers/artifacts/"
    cohort, cohort_sha = decode_document(binding, "cohort", "release-packages", "artifact-package-cohort.json", payload_maps)
    promotion, promotion_sha = decode_document(binding, "promotion", "promoted-stage", "artifact-promotion.json", payload_maps)
    manifest, manifest_sha = decode_document(binding, "manifest", "promoted-stage", prefix + "release.json", payload_maps)
    require(cohort_sha == binding["cohort_sha256"] and promotion_sha == binding["promotion_receipt_sha256"], "cohort/promotion digest differs")
    for value, expected_format in ((cohort, "codearbiter.artifact-package-cohort/0.1.0"), (promotion, "codearbiter.artifact-promotion/0.1.0")):
        require(value.get("format") == expected_format and value.get("source_commit") == req["source_commit"]
                and value.get("workflow") == WORKFLOW and value.get("run_id") == str(req["ci_run_id"]), "cold document source/run differs")
    require(cohort.get("source_tree") == req["source_tree"] and cohort.get("promotion_receipt_sha256") == promotion_sha
            and cohort.get("pi_packer", {}).get("qualification") == "production"
            and isinstance(cohort.get("packages"), dict) and set(cohort["packages"]) == set(HOST_DIRS), "not an exact production cohort")
    spec = importlib.util.spec_from_file_location("cold_shared_manifest", Path(repo) / "core/pysrc/_artifactmanifestlib.py")
    decoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(decoder)
    decoder.validate_release_manifest(manifest)
    native = manifest["binaries"].get(platform)
    require(isinstance(native, dict) and native.get("native_tested") is True, "native target not qualified")
    context = manifest.get("context_qualification", {}).get(platform)
    require(isinstance(context, dict) and context.get("source_commit") == req["source_commit"]
            and context.get("workflow") == WORKFLOW and context.get("run_id") == str(req["ci_run_id"]), "native context qualification differs")
    package = cohort["packages"][host]
    require(isinstance(package, dict) and payload_maps["release-packages"].get(package.get("file")) == package.get("sha256"), "package archive not authenticated")
    require(isinstance(package.get("members"), dict), "package member inventory absent")
    archive_prefix = "package/" if host == "pi" else ""
    def package_digest(path):
        value = package["members"].get(archive_prefix + path)
        return value.get("sha256") if isinstance(value, dict) else None
    require(package_digest(prefix + "release.json") == manifest_sha
            and package_digest(prefix + native["file"]) == native["sha256"]
            and payload_maps["promoted-stage"].get(prefix + native["file"]) == native["sha256"]
            and promotion.get("qualifications", {}).get(platform, {}).get("binary_sha256") == native["sha256"], "native/manifest promotion package join differs")
    receipt = binding["cold_receipt"]
    require(isinstance(receipt, dict) and set(receipt) == RECEIPT_FIELDS, "cold receipt schema not exact")
    expected = {"format": "codearbiter.artifact-cold-execution/0.3.0", "source_commit": req["source_commit"], "workflow": WORKFLOW,
        "run_id": str(req["ci_run_id"]), "job": "artifact-package-cold", "host": host, "platform": platform,
        "promotion_receipt_sha256": promotion_sha, "package_sha256": package["sha256"], "manifest_sha256": manifest_sha,
        "binary_sha256": native["sha256"], "operation": "capabilities", "installed_bridge_sha256": package_digest(HOST_DIRS[host] + "/hooks/_artifactlib.py"),
        "installed_workflow_format": "codearbiter.installed-host-workflow/0.2.0", "context_workflow_scope": "candidate-preflight",
        "approval_evidence_mode": "synthetic-policy-event" if host == "pi" else "host-observed-prompt",
        "prerequisite_evidence_mode": "synthetic-policy-event" if host == "pi" else "host-observed-prompt"}
    require(all(receipt.get(key) == value for key, value in expected.items()), "cold receipt identity or scope differs")
    for key in ("repository_operations_available", "interruption_reconciled", "redispatched", "commit_proof", "finalization_proof", "all_accepted_and_current"):
        require(receipt[key] is True, "cold receipt lacks observed effect: " + key)
    require(receipt["runtime_downloads"] is False and type(receipt["markdown_shadow_count"]) is int
            and receipt["markdown_shadow_count"] == 0, "cold receipt has unsafe or ambiguous outcome")
    for key in ("response_sha256", "installed_workflow_response_sha256", "installed_bridge_sha256", "context_installed_output_sha256"):
        require(isinstance(receipt[key], str) and DIGEST.fullmatch(receipt[key]), "cold response digest absent")
    require(receipt["context_installed_tests"] == [{"name": name, "status": "pass"} for name in CONTEXT_NAMES], "context named outcomes differ")
    tests = [{"id": "cli:tools/build-host-packages.py:cold:" + host + ":" + platform, "result": "passed"}]
    tests += [{"id": "receipt:.github/scripts/test_context_installed.py:" + name, "result": "passed"} for name in CONTEXT_NAMES]
    require(observation.get("tests") == tests, "installed observer named outcomes differ")
    require(isinstance(observation.get("argv"), list) and observation["argv"] and all(isinstance(v, str) and v for v in observation["argv"]), "cold invocation absent")
    validate_invocation(observation["argv"], binding)
    return {"tests": tests, "payload_artifact_ids": sorted(v["artifact_id"] for v in admitted_payloads),
            "payloads": admitted_payloads, "primary_payload_name": consumed["release-packages"]["artifact_name"],
            "installed_cells": ["installed:claude:workflow"] if host == "claude" else []}


def admit(observation, **kwargs):
    try:
        return _admit(observation, **kwargs)
    except (KeyError, TypeError, AttributeError, IndexError, UnicodeError) as error:
        raise ValueError("malformed retained cold observation") from error


def absolute_path(value):
    return isinstance(value, str) and 0 < len(value) <= 4096 and not any(ord(c) < 32 for c in value) and (PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute())


def validate_invocation(argv, binding):
    require(len(argv) == 24 and argv[0] == binding["runtime_before"]["python"]["path"]
            and argv[1:3] == ["-I", "-B"], "not the fixed isolated cold CLI invocation")
    repository = binding["source_before"]["repository"]
    require(absolute_path(repository) and argv[3].replace("\\", "/") == repository.replace("\\", "/").rstrip("/") + "/tools/build-host-packages.py", "cold CLI source owner differs")
    require(argv[4::2] == ["--release-package-stage", "--cold-package-root", "--source-repo", "--cold-host", "--cold-platform", "--trusted-source-commit", "--trusted-workflow", "--trusted-workflow-run", "--cold-promotion-receipt-sha256", "--cold-receipt"], "cold CLI flags differ")
    expected = [binding["payload_before"]["promoted-stage"]["root"], binding["payload_before"]["release-packages"]["root"], repository,
                binding["host"], binding["platform"], binding["source_commit"], WORKFLOW, str(binding["ci_run_id"]), binding["promotion_receipt_sha256"]]
    require(argv[5:-1:2] == expected and absolute_path(argv[-1])
            and argv[-1].replace("\\", "/").endswith("/artifact-package-cold.json"), "cold CLI trusted arguments differ")


def regular_bytes(path, limit=8 * 1024 * 1024):
    info = Path(path).lstat()
    require(stat.S_ISREG(info.st_mode) and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            and info.st_size <= limit, "bounded regular observer input required")
    raw = Path(path).read_bytes()
    require(len(raw) <= limit, "observer input grew beyond bound")
    return raw


def physical_members(root):
    """Complete bounded no-follow enumeration, including unexpected additions."""
    root = Path(root).absolute()
    require(root.resolve(strict=True) == root, "observer payload root is aliased")
    queue, result, total, seen = [root], {}, 0, 0
    while queue:
        parent = queue.pop()
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT, "linked observer payload directory")
        for path in parent.iterdir():
            seen += 1
            require(seen <= 8192, "observer membership exceeds bound")
            info = path.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT, "linked observer payload member")
            if stat.S_ISDIR(info.st_mode):
                queue.append(path)
            else:
                require(stat.S_ISREG(info.st_mode) and info.st_size <= 64 * 1024 * 1024, "invalid observer payload file")
                total += info.st_size
                require(total <= 256 * 1024 * 1024 and len(result) < 4096, "observer payload expansion exceeds bound")
                h = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(block)
                result[safe_path(path.relative_to(root).as_posix())] = h.hexdigest()
    require(result, "empty observer payload")
    return {"root": str(root), "members": result}


def _new_output(path, document):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def _bootstrap(repo):
    """Refuse cached foreign project modules before importing any verifier."""
    repo = Path(repo).resolve(strict=True)
    require(Path(__file__).resolve() == repo / ".github/scripts/retained_archive_cli_observation.py",
            "cold controller must belong to the selected checkout")
    module_paths = {
        "major_qualification_report": ".github/scripts/major_qualification_report.py",
        "major_readiness": ".github/scripts/major_readiness.py",
        "ci20_native_binding": ".github/scripts/ci20_native_binding.py",
        "_boundedproc": ".github/scripts/_boundedproc.py",
        "_contextverificationlib": ".github/scripts/_contextverificationlib.py",
        "owned_output": "tools/owned_output.py",
        "host_descriptors": "tools/host_descriptors.py",
        "_artifactmanifestlib": "core/pysrc/_artifactmanifestlib.py",
        "_releaselib": ".github/scripts/_releaselib.py",
        "_release_mechanism": "core/pysrc/_releaselib.py",
        "_gitexec": "core/pysrc/_gitexec.py",
    }
    for name, relative in module_paths.items():
        loaded = sys.modules.get(name)
        if loaded is not None:
            location = getattr(loaded, "__file__", None)
            require(isinstance(location, str) and Path(location).resolve(strict=True) == repo / relative,
                    "cached project module does not belong to selected source")
    # Project imports cannot fall through to a caller-controlled search directory.
    standard = [str(Path(sys.base_prefix) / "Lib"), str(Path(sys.base_prefix) / "DLLs"),
                str(Path(sys.base_prefix) / ("python" + str(sys.version_info.major) + str(sys.version_info.minor) + ".zip"))]
    if os.name != "nt":
        import sysconfig
        standard = [sysconfig.get_path("stdlib"), str(Path(sysconfig.get_path("stdlib")) / "lib-dynload")]
    sys.path[:] = [str(repo / ".github/scripts"), str(repo / "tools"), str(repo / "core/pysrc"), *standard]


@contextmanager
def _project_imports(repo, bytecode):
    """Fresh source-backed imports, with caller registry/search state restored."""
    original, path, prefix, no_write = dict(sys.modules), sys.path[:], sys.pycache_prefix, sys.dont_write_bytecode
    try:
        _bootstrap(repo)
        project_names = {p.stem for folder in ("core/pysrc", "tools", ".github/scripts")
                         for p in (Path(repo) / folder).glob("*.py")}
        project_names.add("_release_mechanism")
        for name in project_names:
            sys.modules.pop(name, None)
        require(not Path(bytecode).exists(), "fresh bytecode namespace required")
        Path(bytecode).mkdir()
        sys.pycache_prefix, sys.dont_write_bytecode = str(bytecode), True
        yield
    finally:
        for name in set(sys.modules) - set(original):
            sys.modules.pop(name, None)
        sys.modules.update(original)
        sys.path[:], sys.pycache_prefix, sys.dont_write_bytecode = path, prefix, no_write


def _literal_source_inputs(repo, source):
    """One immutable inventory and one batch read, with literal physical joins."""
    git = shutil.which("git")
    require(git is not None, "Git unavailable")
    command = [git, "--no-replace-objects", "--no-lazy-fetch", "-C", str(repo)]
    raw = subprocess.run([*command, "ls-tree", "-rz", "--full-tree", source, "--", "core/pysrc", "core/surface", "core/hosts.json", "tools", ".github/scripts"],
                         capture_output=True, check=True, timeout=30).stdout
    require(len(raw) <= 1024 * 1024, "source inventory exceeds bound")
    selected = []
    for item in raw.split(b"\0"):
        if not item: continue
        meta, path = item.split(b"\t", 1)
        path = safe_path(path.decode("utf-8"))
        if not (path.endswith(".py") or path.startswith("core/surface/") or path == "core/hosts.json"): continue
        mode, kind, sha = meta.decode("ascii").split(" ")
        require(mode in ("100644", "100755") and kind == "blob" and SHA.fullmatch(sha), "unsupported source tree member")
        selected.append((path, sha))
    require(0 < len(selected) <= 2048 and len({p for p,_ in selected}) == len(selected), "source inventory missing/ambiguous/unbounded")
    raw = subprocess.run([*command, "cat-file", "--batch"], input="".join(sha + "\n" for _,sha in selected).encode("ascii"),
                         capture_output=True, check=True, timeout=30).stdout
    require(len(raw) <= 64 * 1024 * 1024, "source blob read exceeds bound")
    position, inputs = 0, {}
    for path, expected in selected:
        end = raw.index(b"\n", position)
        sha, kind, size = raw[position:end].decode("ascii").split(" ")
        size = int(size)
        require(sha == expected and kind == "blob" and 0 <= size <= 8 * 1024 * 1024, "source blob identity/read failure")
        position = end + 1
        blob = raw[position:position + size]
        require(len(blob) == size and raw[position + size:position + size + 1] == b"\n", "truncated source blob")
        position += size + 1
        require(regular_bytes(Path(repo) / path) == blob, "physical source differs from immutable Git blob")
        inputs[path] = digest(blob)
    require(position == len(raw), "unexpected source batch output")
    return inputs


def _source_snapshot(repo):
    import major_qualification_report as reports
    identity = reports.source_identity(repo)
    require(identity["clean"], "observer source checkout is not clean")
    inputs = _literal_source_inputs(repo, identity["source_commit"])
    python_paths = sorted(p.removeprefix("core/pysrc/") for p in inputs if p.startswith("core/pysrc/"))
    actual = []
    for path in (Path(repo) / "core/pysrc").iterdir():
        if path.suffix == ".py":
            regular_bytes(path)
            actual.append(path.name)
    require(sorted(actual) == python_paths, "actual core Python membership differs")
    names = sorted(p.name for p in (Path(repo) / "core/pysrc").iterdir())
    require(os.name != "nt" or all(n.isascii() for n in names), "unsupported Windows host lookup inventory")
    present = any(n.lower() == "_host.py" for n in names) if os.name == "nt" else "_host.py" in names
    require(not present, "unrecorded core host override")
    return {**identity, "repository": str(Path(repo).resolve(strict=True)), "inputs": inputs,
            "core_python_members": python_paths, "host_lookup": {"path": "core/pysrc/_host.py", "path_style": "windows" if os.name == "nt" else "posix", "present": False}}


def _runtime_snapshot():
    git = shutil.which("git")
    require(git is not None, "reviewed Git runtime unavailable")
    return {name: {"path": str(path.resolve(strict=True)), "sha256": digest(regular_bytes(path, 64 * 1024 * 1024))}
            for name, path in (("python", Path(sys.executable)), ("git", Path(git)))}


def _load_packager(repo):
    spec = importlib.util.spec_from_file_location("retained_cold_packager", Path(repo) / "tools/build-host-packages.py")
    require(spec is not None and spec.loader is not None, "cold package owner unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _verify_production(repo, package_root, stage, req, promotion_sha):
    return _load_packager(repo).verify_artifact_release_packages(package_root=package_root, source_repo=repo,
        source_commit=req["source_commit"], workflow=WORKFLOW, run_id=str(req["ci_run_id"]),
        promotion_receipt_sha256=promotion_sha, stage=stage, require_production=True)


@contextmanager
def private_environment(root):
    """Isolate imports/control HOME; only control API retains its explicit token."""
    prior = dict(os.environ)
    git = shutil.which("git")
    gh = shutil.which("gh")
    require(git is not None, "Git unavailable before isolation")
    for part in (root, root / "appdata", root / "localappdata", root / "xdg", root / "tmp"):
        part.mkdir(parents=True, exist_ok=True)
    env = {k: prior[k] for k in ("SystemRoot", "SYSTEMROOT", "WINDIR", "ComSpec", "PATHEXT", "GH_TOKEN", "GITHUB_TOKEN",
        "GITHUB_ACTIONS", "GITHUB_REPOSITORY", "GITHUB_REF", "GITHUB_SHA", "GITHUB_EVENT_NAME", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT") if k in prior}
    env.update(HOME=str(root), USERPROFILE=str(root), APPDATA=str(root / "appdata"), LOCALAPPDATA=str(root / "localappdata"),
        XDG_CONFIG_HOME=str(root / "xdg"), TEMP=str(root / "tmp"), TMP=str(root / "tmp"), PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
        PATH=os.pathsep.join(dict.fromkeys([str(Path(sys.executable).parent), str(Path(git).parent), str(Path(prior.get("SystemRoot", "/")) / "System32")] + ([str(Path(gh).parent)] if gh else []))),
        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    try:
        os.environ.clear()
        os.environ.update(env)
        yield
    finally:
        os.environ.clear()
        os.environ.update(prior)


def child_environment(home, runtime):
    env = {k: os.environ[k] for k in ("SystemRoot", "SYSTEMROOT", "WINDIR", "ComSpec", "PATHEXT") if k in os.environ}
    for part in (home, home / "appdata", home / "localappdata", home / "xdg", home / "tmp"):
        part.mkdir(parents=True, exist_ok=True)
    env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home / "appdata"), LOCALAPPDATA=str(home / "localappdata"),
        XDG_CONFIG_HOME=str(home / "xdg"), TEMP=str(home / "tmp"), TMP=str(home / "tmp"), PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
        PATH=os.pathsep.join([str(Path(runtime["python"]["path"]).parent), str(Path(runtime["git"]["path"]).parent)]),
        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    return env


def observe(*, repo, req, job_id, host, platform, stage, package_root, authenticated_payloads, output, runner=None):
    """Execute the unchanged cold owner once. A receipt-import operation is absent."""
    repo, stage, package_root, output = map(Path, (repo, stage, package_root, output))
    repo = repo.resolve(strict=True)
    stage, package_root, output = stage.absolute(), package_root.absolute(), output.absolute()
    completion = output.with_name(output.name + ".execution.json")
    retained_receipt = output.with_name("artifact-package-cold.json")
    require(output != retained_receipt and not retained_receipt.exists() and not retained_receipt.is_symlink()
            and not output.exists() and not output.is_symlink() and not completion.exists() and output.parent.is_dir()
            and output.parent.resolve(strict=True) == output.parent, "new observer output required")
    require(host in HOST_DIRS and platform in PLATFORMS and type(job_id) is int and job_id > 0, "invalid cold execution cell")
    binding, command, execution, tests = {}, [], {"phase": "admission", "returncode": None, "timed_out": False, "containment": "not-started"}, []
    code, stable = 1, False
    with tempfile.TemporaryDirectory(prefix="ca-retained-cold-observer-") as temporary:
        private = Path(temporary).resolve(strict=True)
        with private_environment(private / "control-home"):
            try:
                with _project_imports(repo, private / "bytecode"):
                    from _boundedproc import run
                    before = _source_snapshot(repo)
                    require(before["source_commit"] == req["source_commit"] and before["source_tree"] == req["source_tree"], "cold producer source differs")
                    runtime = _runtime_snapshot()
                    consumed = {}
                    for role, prefix in (("promoted-stage", "artifact-host-payloads-"), ("release-packages", "artifact-release-packages-")):
                        name = prefix + req["source_commit"]
                        consumed[role] = {"artifact_name": name, **payload_projection(authenticated_payloads.get(name))}
                    payload_before = {"promoted-stage": physical_members(stage), "release-packages": physical_members(package_root)}
                    for role in consumed:
                        require(payload_before[role]["members"] == members(consumed[role]["members"]), "physical input differs from authenticated original archive")
                    paths = {"cohort": package_root / "artifact-package-cohort.json", "promotion": stage / "artifact-promotion.json",
                             "manifest": stage / HOST_DIRS[host] / "helpers/artifacts/release.json"}
                    documents = {k: {"path": p.relative_to(package_root if k == "cohort" else stage).as_posix(), "json_utf8": regular_bytes(p).decode("utf-8")} for k, p in paths.items()}
                    promotion_sha = digest(documents["promotion"]["json_utf8"].encode())
                    _verify_production(repo, package_root, stage, req, promotion_sha)
                    receipt_path = private / "artifact-package-cold.json"
                    command = [runtime["python"]["path"], "-I", "-B", str(repo / "tools/build-host-packages.py"),
                        "--release-package-stage", str(stage.absolute()), "--cold-package-root", str(package_root.absolute()), "--source-repo", str(repo.resolve(strict=True)),
                        "--cold-host", host, "--cold-platform", platform, "--trusted-source-commit", req["source_commit"], "--trusted-workflow", WORKFLOW,
                        "--trusted-workflow-run", str(req["ci_run_id"]), "--cold-promotion-receipt-sha256", promotion_sha, "--cold-receipt", str(receipt_path)]
                    execution["phase"] = "cold-command"
                    done = (runner or run)(command, timeout=360, cwd=str(repo), env=child_environment(private / "child-home", runtime))
                    # Record completion before receipt parsing or postcondition checks.
                    execution.update(returncode=done.returncode, timed_out=done.timed_out, containment=done.containment,
                        stdout_sha256=digest(done.stdout.encode("utf-8")), stdout_bytes=len(done.stdout.encode("utf-8")),
                        stderr_sha256=digest(done.stderr.encode("utf-8")), stderr_bytes=len(done.stderr.encode("utf-8")))
                    _new_output(completion, dict(execution))
                    require(not done.timed_out and done.containment == "exited" and done.returncode == 0, "cold command did not complete affirmatively")
                    execution["phase"] = "receipt"
                    receipt_raw = regular_bytes(receipt_path)
                    with retained_receipt.open("xb") as stream:
                        stream.write(receipt_raw)
                    receipt = json.loads(receipt_raw, object_pairs_hook=pairs)
                    after, runtime_after = _source_snapshot(repo), _runtime_snapshot()
                    payload_after = {"promoted-stage": physical_members(stage), "release-packages": physical_members(package_root)}
                    binding = {"format": FORMAT, "profile": PROFILE, "source_commit": req["source_commit"], "source_tree": req["source_tree"],
                        "workflow": WORKFLOW, "ci_run_id": req["ci_run_id"], "producer_job_id": job_id, "host": host, "platform": platform,
                        "consumed_payloads": consumed, "cohort_sha256": digest(documents["cohort"]["json_utf8"].encode()),
                        "promotion_receipt_sha256": promotion_sha, "documents": documents, "cold_receipt": receipt,
                        "source_before": before, "source_after": after, "runtime_before": runtime, "runtime_after": runtime_after,
                        "payload_before": payload_before, "payload_after": payload_after}
                    tests = [{"id": "cli:tools/build-host-packages.py:cold:" + host + ":" + platform, "result": "passed"}]
                    tests += [{"id": "receipt:.github/scripts/test_context_installed.py:" + n, "result": "passed"} for n in CONTEXT_NAMES]
                    stable = before == after
                    document = {"format": OBSERVATION, "source_commit": req["source_commit"], "source_tree": req["source_tree"],
                        "source_stable": stable, "ci_run_id": req["ci_run_id"], "proof_kind": "retained-archive-cli", "producer": PRODUCER,
                        "argv": command, "exit_code": 0, "tests": tests, "installed_binding": binding}
                    admit(document, req=req, job_id=job_id, authenticated_payloads=authenticated_payloads, repo=repo)
                    code, execution["phase"] = 0, "complete"
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
                execution["failure_text_sha256"] = digest(str(error).encode("utf-8", errors="replace"))
    document = {"format": OBSERVATION, "source_commit": req["source_commit"], "source_tree": req["source_tree"], "source_stable": stable and code == 0,
        "ci_run_id": req["ci_run_id"], "proof_kind": "retained-archive-cli", "producer": PRODUCER, "argv": command,
        "exit_code": code, "tests": tests if code == 0 else [], "installed_binding": binding, "execution": execution}
    _new_output(output, document)
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--package-root", required=True, type=Path)
    parser.add_argument("--host", required=True, choices=tuple(HOST_DIRS))
    parser.add_argument("--platform", required=True, choices=tuple(sorted(PLATFORMS)))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="ca-cold-api-control-") as temporary:
        with private_environment(Path(temporary)), _project_imports(args.repo, Path(temporary) / "bytecode"):
            import major_readiness as readiness
            import major_qualification_report as reports
            require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_REPOSITORY") == readiness.REPOSITORY
                    and os.environ.get("GITHUB_EVENT_NAME") == "push" and os.environ.get("GITHUB_REF") in ("refs/heads/main", "refs/heads/major/state-contracts"), "cold observer requires actual trusted push CI")
            source, run_id = os.environ.get("GITHUB_SHA", ""), int(os.environ.get("GITHUB_RUN_ID", "0"))
            require(SHA.fullmatch(source) and run_id > 0, "cold observer source/run absent")
            run = readiness.api(f"actions/runs/{run_id}")
            require(run.get("head_sha") == source and run.get("event") == "push" and run.get("path") == WORKFLOW
                    and run.get("repository", {}).get("full_name") == readiness.REPOSITORY
                    and run.get("head_branch") in ("main", "major/state-contracts"), "cold original run differs")
            def inventory(route, key):
                pages = json.loads(readiness.command(["gh", "api", "--paginate", "--slurp",
                    "repos/" + readiness.REPOSITORY + "/" + route]))
                require(isinstance(pages, list) and 0 < len(pages) <= 6, "cold observation API pages exceed bound")
                rows = [row for page in pages for row in page[key]]
                require(len(rows) <= 512 and len({row["id"] for row in rows}) == len(rows), "cold API inventory missing/duplicate/unbounded")
                return {key: rows}
            jobs_page = inventory(f"actions/runs/{run_id}/jobs?filter=latest&per_page=100", "jobs")
            artifacts_page = inventory(f"actions/runs/{run_id}/artifacts?per_page=100", "artifacts")
            name = "[CHECK] | [CORE] | Structured artifact cold package  <" + args.platform + ">"
            job = [j for j in jobs_page["jobs"] if j.get("name") == name and j.get("status") == "in_progress"
                   and str(j.get("run_attempt")) == os.environ.get("GITHUB_RUN_ATTEMPT")]
            assembly = [j for j in jobs_page["jobs"] if j.get("name") == "[CHECK] | [CORE] | Structured artifact package assembly" and j.get("conclusion") == "success"]
            require(len(job) == len(assembly) == 1, "actual original cold/assembly job unavailable or ambiguous")
            req = {"source_commit": source, "source_tree": reports.git(args.repo, "rev-parse", source + "^{tree}"), "ci_run_id": run_id}
            payloads = {}
            for prefix, path, step in (("artifact-host-payloads-", args.stage, "Preserve the exact multi-host package overlay"),
                    ("artifact-release-packages-", args.package_root, "Preserve the exact normal release package cohort")):
                matching = [a for a in artifacts_page["artifacts"] if a.get("name") == prefix + source]
                require(len(matching) == 1, "original consumed artifact missing or ambiguous")
                readiness.validate_upload(assembly[0], matching[0], step)
                payloads[prefix + source] = reports.authenticated_payload(matching[0], req, path)
            return observe(repo=args.repo, req=req, job_id=job[0]["id"], host=args.host, platform=args.platform,
                stage=args.stage, package_root=args.package_root, authenticated_payloads=payloads, output=args.output)


def _diagnostic_code(error):
    """Classify only known fixed causes; never render an underlying value."""
    seen, upload = set(), False
    for _ in range(16):
        if error is None or id(error) in seen:
            break
        seen.add(id(error))
        args = error.args
        text = args[0] if len(args) == 1 and type(args[0]) is str else None
        if text == "upload attribution unavailable or malformed":
            upload = True
        elif text in ("required exact upload step did not succeed",
                      "artifact created outside claimed upload step",
                      "upload attribution log exceeds bound",
                      "claimed upload step did not run the pinned artifact uploader",
                      "artifact ID/name/digest not finalized by claimed upload job"):
            return "UPLOAD_ATTRIBUTION_REJECTED"
        elif upload:
            if text == "readiness observation failed: gh":
                return "UPLOAD_LOG_COMMAND_FAILED"
            if text in ("readiness observation timed out; containment=exited",
                        "readiness observation timed out; containment=terminated",
                        "readiness observation timed out; containment=unconfirmed"):
                return "UPLOAD_LOG_TIMEOUT"
            if (text == "invalid upload time identity"
                    or (type(error) is ValueError and text is not None
                        and text.startswith("Invalid isoformat string: "))
                    or (type(error) is KeyError and text in
                        ("id", "name", "digest", "started_at", "completed_at", "created_at"))):
                return "UPLOAD_METADATA_INVALID"
            if type(error) is UnicodeDecodeError:
                return "UPLOAD_LOG_MALFORMED"
        error = error.__cause__
    return "UNKNOWN"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print("::error::Retained cold observer refused; code=" + _diagnostic_code(error) + "; diagnostic_sha256=" + digest(str(error).encode("utf-8", errors="replace")), file=sys.stderr)
        raise SystemExit(1)
