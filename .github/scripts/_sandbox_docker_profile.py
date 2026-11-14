"""Closed finite join for actual shipped Sandbox CLI Docker observations.

Admission does not execute or authenticate an archive itself. The coordinator
supplies original API-authenticated payload objects; labels and caller pass
flags do not create an installed producer or any whole-Sandbox qualification.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath
import posixpath
import re

PROFILE = "sandbox-installed-docker-v1"
PRODUCER = "sandbox-installed-docker-observer-v1"
WORKFLOW = ".github/workflows/ci.yml"
CELL = "installed:sandbox:docker"
GROUP = "shipped sandbox bundle [docker]"
NAMES = (
    GROUP + " resolves exec through the shipped CLI",
    GROUP + " copies out through the shipped CLI",
    GROUP + " destroys its owned container and volume",
)
TEST_PREFIX = "vitest:plugins/ca-sandbox/tools/installed-bundle.test.ts:"
IMAGE = "node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0"
DIGEST = re.compile(r"[a-f0-9]{64}")
SHA = re.compile(r"(?!0{40}$)[a-f0-9]{40}")
MAX_JSON = 16 * 1024 * 1024
NIXPACKS_VERSION = "1.41.0"
NIXPACKS_ARCHIVE_SHA256 = "0f55de7874507b9cf7502113120bd96f2ab6979f78d10eaf2eb2ade9207b3af6"
NIXPACKS_SCOPE = "Linux amd64; fixed plan generation only; no image or workflow qualification"


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate Sandbox observation field")
        result[key] = value
    return result


def closed(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys.split()),
            "closed " + label + " fields differ")


def digest(value):
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def positive(value):
    return type(value) is int and value > 0


def relative(value):
    require(isinstance(value, str) and 0 < len(value.encode("utf8")) <= 4096
            and value != "." and str(PurePosixPath(value)) == value
            and not PurePosixPath(value).is_absolute()
            and ".." not in PurePosixPath(value).parts and ":" not in value
            and "\\" not in value and not any(ord(c) < 32 or ord(c) == 127 for c in value),
            "unsafe Sandbox member path")
    return value


def absolute(value):
    return (isinstance(value, str) and 0 < len(value.encode("utf8")) <= 4096
            and (PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute())
            and ".." not in PurePosixPath(value.replace("\\", "/")).parts
            and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def member_map(rows):
    require(isinstance(rows, list) and 0 < len(rows) <= 1025,
            "bounded authenticated Sandbox members required")
    result = {}
    for row in rows:
        closed(row, "path sha256", "Sandbox member")
        path = relative(row["path"])
        require(path not in result and digest(row["sha256"]),
                "duplicate or invalid Sandbox member")
        result[path] = row["sha256"]
    return result


def image(value):
    closed(value, "reference id repo_digests os architecture", "Sandbox image")
    require(value["reference"] == IMAGE and value["os"] == "linux"
            and value["architecture"] == "amd64"
            and isinstance(value["id"], str) and value["id"].startswith("sha256:")
            and digest(value["id"].removeprefix("sha256:"))
            and isinstance(value["repo_digests"], list)
            and len(value["repo_digests"]) == len(set(value["repo_digests"]))
            and 0 < len(value["repo_digests"]) <= 16
            and any(isinstance(d, str) and d.endswith("@" + IMAGE.split("@", 1)[1])
                    for d in value["repo_digests"]), "reviewed Sandbox image differs")


def validate_expected(expected):
    closed(expected, "source_commit source_tree ci_run_id producer_job_id execution_run_attempt", "Sandbox expected identity")
    require(all(isinstance(expected[k], str) and SHA.fullmatch(expected[k])
                for k in ("source_commit", "source_tree"))
            and positive(expected["ci_run_id"]) and positive(expected["producer_job_id"])
            and positive(expected["execution_run_attempt"]) and expected["execution_run_attempt"] < 10000,
            "invalid Sandbox expected source/run/job")


def admit_nixpacks_acquisition(acquisition, selected_path, selected_sha256, version=None):
    """Join the independently owned same-job receipt before any helper probe."""
    closed(acquisition, "runner_temp path sha256 document_utf8", "Sandbox Nixpacks acquisition")
    root, path, document = acquisition["runner_temp"], acquisition["path"], acquisition["document_utf8"]
    require(absolute(root) and absolute(path) and path.replace("\\", "/") ==
            root.replace("\\", "/").rstrip("/") + "/nixpacks-acquisition.json"
            and isinstance(document, str) and 0 < len(document.encode()) <= 8192
            and acquisition["sha256"] == sha(document.encode()),
            "Sandbox Nixpacks same-job acquisition receipt differs")
    receipt = json.loads(document, object_pairs_hook=unique)
    closed(receipt, "format version scope archive_sha256 binary_sha256 bin_dir", "Sandbox Nixpacks receipt")
    require(receipt["format"] == "codearbiter.nixpacks-acquisition/1"
            and receipt["version"] == NIXPACKS_VERSION and receipt["scope"] == NIXPACKS_SCOPE
            and receipt["archive_sha256"] == NIXPACKS_ARCHIVE_SHA256
            and absolute(receipt["bin_dir"]) and digest(receipt["binary_sha256"])
            and digest(selected_sha256) and receipt["binary_sha256"] == selected_sha256,
            "Sandbox Nixpacks reviewed acquisition pin differs")
    directory = receipt["bin_dir"].replace("\\", "/")
    prefix = root.replace("\\", "/").rstrip("/") + "/ca-nixpacks-reviewed-"
    require(directory.startswith(prefix) and 0 < len(directory.removeprefix(prefix)) <= 128
            and "/" not in directory.removeprefix(prefix)
            and absolute(selected_path) and selected_path.replace("\\", "/") == directory + "/nixpacks",
            "Sandbox Nixpacks selected executable differs from acquisition")
    if version is not None:
        require(version == "nixpacks " + NIXPACKS_VERSION, "Sandbox Nixpacks actual version differs")
    return receipt


def admit_payload_binding(b, expected, authenticated_payloads):
    """The same exact payload/source admission runs before effects and on report intake."""
    validate_expected(expected)
    source = b["source_before"]
    require(source.get("clean") is True and source.get("source_commit") == expected["source_commit"]
            and source.get("source_tree") == expected["source_tree"]
            and isinstance(source.get("inputs"), dict) and source["inputs"],
            "Sandbox selected source capture incomplete")
    for path, value in source["inputs"].items():
        relative(path)
        require(digest(value), "invalid Sandbox source digest")
    payload = b["payload"]
    closed(payload, "artifact_name artifact_id archive_sha256 members", "Sandbox consumed payload")
    name = "artifact-sandbox-plugin-" + expected["source_commit"] + "-" + str(expected["execution_run_attempt"])
    require(payload["artifact_name"] == name and isinstance(authenticated_payloads, dict),
            "Sandbox original artifact name differs")
    actual = authenticated_payloads.get(name)
    require(isinstance(actual, dict) and positive(actual.get("artifact_id"))
            and digest(actual.get("archive_sha256"))
            and all(payload[k] == actual.get(k) for k in ("artifact_id", "archive_sha256", "members")),
            "Sandbox consumed archive differs from authenticated original")
    files = member_map(payload["members"])
    closed(b["payload_before"], "root members", "Sandbox physical payload")
    require(absolute(b["payload_before"]["root"]) and b["payload_before"]["members"] == files,
            "Sandbox complete physical payload differs")
    require(absolute(b["installed_root"])
            and b["installed_root"].replace("\\", "/") ==
            b["payload_before"]["root"].replace("\\", "/").rstrip("/") + "/plugins/ca-sandbox",
            "Sandbox installed root does not belong to consumed payload")
    document = b["payload_document_utf8"]
    require(isinstance(document, str) and 0 < len(document.encode()) <= 1024 * 1024
            and files.get("artifact-sandbox-payload.json") == sha(document.encode()),
            "Sandbox payload receipt not authenticated")
    receipt = json.loads(document, object_pairs_hook=unique)
    closed(receipt, "format source_commit source_tree workflow version plugin_root execution_run_attempt members", "Sandbox plain payload")
    require(receipt["format"] == "codearbiter.sandbox-plain-payload/1"
            and receipt["source_commit"] == expected["source_commit"]
            and receipt["source_tree"] == expected["source_tree"] and receipt["workflow"] == WORKFLOW
            and type(receipt["execution_run_attempt"]) is int
            and receipt["execution_run_attempt"] == expected["execution_run_attempt"]
            and receipt["plugin_root"] == "plugins/ca-sandbox"
            and isinstance(receipt["version"], str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", receipt["version"])
            and isinstance(receipt["members"], dict) and 0 < len(receipt["members"]) <= 1024,
            "Sandbox plain payload source/version/membership differs")
    declared = {}
    for path, item in receipt["members"].items():
        relative(path)
        closed(item, "size sha256", "Sandbox plugin member")
        require(type(item["size"]) is int and 0 <= item["size"] <= 8 * 1024 * 1024
                and digest(item["sha256"]), "invalid Sandbox plugin size/digest")
        declared["plugins/ca-sandbox/" + path] = item["sha256"]
    require(sum(item["size"] for item in receipt["members"].values()) <= 16 * 1024 * 1024
            and files == {**declared, "artifact-sandbox-payload.json": sha(document.encode())},
            "Sandbox plugin/receipt has missing or extra consumed bytes")
    for needed in (".claude-plugin/plugin.json", "tools/sandbox.js", "tools/claude-inside.js"):
        require(needed in receipt["members"], "Sandbox shipped member absent")
    manifest = b["manifest_document_utf8"]
    require(isinstance(manifest, str) and len(manifest.encode()) <= 65536
            and sha(manifest.encode()) == receipt["members"][".claude-plugin/plugin.json"]["sha256"],
            "Sandbox actual manifest bytes differ")
    manifest = json.loads(manifest, object_pairs_hook=unique)
    require(manifest.get("name") == "ca-sandbox" and manifest.get("version") == receipt["version"],
            "Sandbox manifest/receipt version differs")
    require(declared == {path: value for path, value in source["inputs"].items()
                         if path.startswith("plugins/ca-sandbox/")},
            "Sandbox payload is not the complete selected source plugin")
    return name, actual, receipt


def _admit(observation, *, expected, authenticated_payloads):
    validate_expected(expected)
    closed(observation, "format source_commit source_tree ci_run_id source_stable proof_kind producer argv exit_code tests installed_binding",
           "Sandbox observation")
    require(observation["format"] == "codearbiter.major-test-observation/1"
            and observation["proof_kind"] == "live-host" and observation["producer"] == PRODUCER
            and observation["source_stable"] is True and type(observation["exit_code"]) is int
            and observation["exit_code"] == 0, "no successful closed Sandbox observer")
    for key in ("source_commit", "source_tree", "ci_run_id"):
        require(observation[key] == expected[key] and type(observation[key]) is type(expected[key]),
                "Sandbox observation source/run differs")
    b = observation["installed_binding"]
    closed(b, "format profile source_commit source_tree workflow ci_run_id producer_job_id execution_run_attempt payload payload_document_utf8 manifest_document_utf8 installed_root source_before source_after runtime_before runtime_after payload_before payload_after suite witnesses",
           "Sandbox installed binding")
    require(b["format"] == "codearbiter.installed-observation-binding/1"
            and b["profile"] == PROFILE and b["workflow"] == WORKFLOW,
            "wrong Sandbox profile/workflow")
    for key, value in expected.items():
        require(b[key] == value and type(b[key]) is type(value), "Sandbox bound source/run/job differs")
    require(len(json.dumps(b, ensure_ascii=True).encode()) <= MAX_JSON,
            "Sandbox installed binding exceeds bound")
    for name in ("source", "runtime", "payload"):
        require(isinstance(b[name + "_before"], dict) and b[name + "_before"]
                and b[name + "_before"] == b[name + "_after"],
                "Sandbox " + name + " drift or unavailable capture")
    name, actual, receipt = admit_payload_binding(b, expected, authenticated_payloads)
    runtime = b["runtime_before"]
    closed(runtime, "binaries modules image nixpacks_acquisition", "Sandbox runtime")
    require(set(runtime["binaries"]) == {"node", "npm", "docker", "git", "python", "nixpacks"},
            "Sandbox runtime population incomplete")
    for identity in runtime["binaries"].values():
        closed(identity, "path sha256 version", "Sandbox binary")
        require(absolute(identity["path"]) and digest(identity["sha256"])
                and isinstance(identity["version"], str) and 0 < len(identity["version"]) <= 512,
                "Sandbox runtime identity missing")
    nixpacks = runtime["binaries"]["nixpacks"]
    admit_nixpacks_acquisition(runtime["nixpacks_acquisition"], nixpacks["path"],
                               nixpacks["sha256"], nixpacks["version"])
    closed(runtime["modules"], "root members", "Sandbox Node tool graph")
    require(absolute(runtime["modules"]["root"]) and isinstance(runtime["modules"]["members"], dict)
            and 0 < len(runtime["modules"]["members"]) <= 32768, "Sandbox Node graph missing")
    for path, item in runtime["modules"]["members"].items():
        relative(path)
        require(isinstance(item, dict) and set(item) in ({"size", "sha256"}, {"size", "sha256", "link"}),
                "closed Sandbox Node graph member fields differ")
        require(type(item["size"]) is int and 0 <= item["size"] <= 64 * 1024 * 1024
                and digest(item["sha256"]), "Sandbox Node graph identity differs")
        if "link" in item:
            target = item["link"]
            require(path.startswith(".bin/") and path.count("/") == 1
                    and isinstance(target, str) and target and not target.startswith(("/", "\\"))
                    and ":" not in target and "\\" not in target
                    and not any(ord(c) < 32 or ord(c) == 127 for c in target)
                    and len(target.encode()) == item["size"] and sha(target.encode()) == item["sha256"],
                    "Sandbox npm bin link differs")
            resolved = relative(posixpath.normpath(posixpath.join(".bin", target)))
            require(resolved in runtime["modules"]["members"]
                    and "link" not in runtime["modules"]["members"][resolved],
                    "Sandbox npm bin link target is outside the complete tool graph")
    require(sum(item["size"] for item in runtime["modules"]["members"].values()) <= 256 * 1024 * 1024,
            "Sandbox Node graph bytes exceed bound")
    image(runtime["image"])
    suite = b["suite"]
    closed(suite, "argv cwd exit_code timed_out containment raw_sha256 sentinel_sha256 declared_layers recorded_layers tests",
           "Sandbox original suite")
    require(observation["argv"] == suite["argv"] and isinstance(suite["argv"], list)
            and suite["argv"][:3] == [runtime["binaries"]["node"]["path"], runtime["binaries"]["npm"]["path"], "test"]
            and suite["argv"][3:-1] == ["--", "--reporter=default", "--reporter=github-actions",
                                      "--reporter=json", "--no-cache"]
            and suite["argv"][-1].startswith("--outputFile.json=")
            and absolute(suite["argv"][-1].split("=", 1)[1]) and absolute(suite["cwd"])
            and type(suite["exit_code"]) is int and suite["exit_code"] == 0
            and suite["timed_out"] is False and suite["containment"] == "exited"
            and digest(suite["raw_sha256"]) and digest(suite["sentinel_sha256"]),
            "Sandbox original command/exit/containment differs")
    require(isinstance(suite["declared_layers"], dict) and suite["declared_layers"]
            and suite["declared_layers"].get("installed-bundle") == ["installed-bundle.test.ts"]
            and all(isinstance(v, list) and len(v) == 1 for v in suite["declared_layers"].values())
            and suite["recorded_layers"] == sorted(suite["declared_layers"]),
            "Sandbox original declared/sentinel layer population differs")
    require(isinstance(suite["tests"], list) and 0 < len(suite["tests"]) <= 32768,
            "Sandbox original named outcomes absent")
    named = {}
    for row in suite["tests"]:
        closed(row, "id result", "Sandbox original test")
        require(isinstance(row["id"], str) and row["id"] not in named and row["result"] == "passed",
                "Sandbox original named test missing/repeated/skipped/failed")
        named[row["id"]] = row["result"]
    selected = [{"id": TEST_PREFIX + name, "result": "passed"} for name in NAMES]
    require(observation["tests"] == selected and all(row["id"] in named for row in selected),
            "Sandbox selected bundle cases differ from actual suite")
    require(isinstance(b["witnesses"], list) and len(b["witnesses"]) == 3,
            "Sandbox actual bundle witness population differs")
    ids = set()
    for index, case in enumerate(b["witnesses"]):
        closed(case, "format name plugin_root bundle_sha256 node image fixture commands checks cleanup", "Sandbox bundle case")
        require(case["format"] == "codearbiter.sandbox-bundle-case/1" and case["name"] == NAMES[index]
                and case["plugin_root"] == b["installed_root"]
                and case["bundle_sha256"] == receipt["members"]["tools/sandbox.js"]["sha256"]
                and case["node"] == runtime["binaries"]["node"]["path"]
                and case["image"] == runtime["image"], "Sandbox actual bundled bytes/runtime/image differ")
        fixture = case["fixture"]
        closed(fixture, "id container volume host_dir labels", "Sandbox owned fixture")
        identity = fixture["id"]
        require(isinstance(identity, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}", identity)
                and identity not in ids and digest(fixture["container"]) and absolute(fixture["host_dir"])
                and fixture["volume"] == "ca-sbx-vol-" + identity
                and fixture["labels"] == {"ca.sandbox": "1", "ca.sandbox.id": identity,
                                          "ca.sandbox.qualification": identity},
                "Sandbox fixture is missing, repeated or unowned")
        ids.add(identity)
        closed(case["cleanup"], "container_absent volume_absent owned_only", "Sandbox cleanup")
        require(all(v is True for v in case["cleanup"].values()), "Sandbox owned cleanup incomplete")
        expected_tails = (
            [["exec", identity, "--", "sh", "-c", "printf SBX_INSTALLED_EXEC"]],
            [["exec", identity, "--", "cat", "/work/repo/result"],
             ["cp", identity + ":/work/repo/result", fixture["host_dir"].rstrip("/\\") + "/result"]],
            [["destroy", identity]],
        )[index]
        require(isinstance(case["commands"], list) and len(case["commands"]) == len(expected_tails),
                "Sandbox real CLI command population differs")
        results = []
        for command, tail in zip(case["commands"], expected_tails):
            closed(command, "argv exit_code timed_out containment stdout_utf8 stderr_utf8", "Sandbox real CLI command")
            argv = command["argv"]
            require(isinstance(argv, list) and len(argv) >= 2
                    and argv[0] == case["node"]
                    and argv[1].replace("\\", "/") == b["installed_root"].replace("\\", "/").rstrip("/") + "/tools/sandbox.js"
                    and [v.replace("\\", "/") for v in argv[2:]] == [v.replace("\\", "/") for v in tail]
                    and type(command["exit_code"]) is int and command["exit_code"] == 0
                    and command["timed_out"] is False and command["containment"] == "exited"
                    and all(isinstance(command[k], str) and len(command[k].encode()) <= 65536
                            for k in ("stdout_utf8", "stderr_utf8")), "Sandbox bundled CLI command failed or was substituted")
            results.append(json.loads(command["stdout_utf8"], object_pairs_hook=unique)
                           if tail[0] != "cp" else None)
        closed(case["checks"], "exec_marker copy_sha256 destroy_empty", "Sandbox effect checks")
        if index == 0:
            require(results[0].get("id") == identity and type(results[0].get("exitCode")) is int
                    and results[0].get("exitCode") == 0
                    and results[0].get("stdout") == "SBX_INSTALLED_EXEC" and case["checks"]["exec_marker"] is True,
                    "Sandbox actual exec marker absent")
        elif index == 1:
            require(results[0].get("id") == identity and type(results[0].get("exitCode")) is int
                    and results[0].get("exitCode") == 0
                    and results[0].get("stdout") == "SBX_INSTALLED_COPY"
                    and case["checks"]["copy_sha256"] == sha(b"SBX_INSTALLED_COPY"),
                    "Sandbox actual copy bytes absent")
        else:
            require(results[0].get("id") == identity and type(results[0].get("failureCount")) is int
                    and results[0].get("failureCount") == 0
                    and results[0].get("remainingContainers") == [] and results[0].get("remainingVolumes") == []
                    and case["checks"]["destroy_empty"] is True, "Sandbox actual scoped destroy incomplete")
    retained = {k: actual[k] for k in ("artifact_id", "archive_sha256", "members")}
    return {"tests": selected, "installed_cells": [CELL], "payload_artifact_ids": [actual["artifact_id"]],
            "payloads": [retained], "primary_payload_name": name,
            "scope": "Three actual shipped-CLI Docker cases; no create/provider/OAuth/global-prune or whole-Sandbox claim."}


def admit(observation, **kwargs):
    try:
        return _admit(observation, **kwargs)
    except (KeyError, TypeError, AttributeError, IndexError, UnicodeError) as error:
        raise ValueError("malformed closed Sandbox observation") from error
