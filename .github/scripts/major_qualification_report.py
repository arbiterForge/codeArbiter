#!/usr/bin/env python3
"""Named-test observations and exact-payload reports for Q-02.

Observers reuse an owning test execution. Selection maps are reviewed semantic
claims, not discovery or pass flags. Missing mappings, skipped selected tests,
source drift and source-only claims about installed hosts refuse emission.
Only trusted main/program push CI can emit reports; final readiness remains main-only.
The existing readiness owner
authenticates its original upload job and archive independently.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import runpy
import stat
import subprocess
import sys
import traceback
import unittest
from unittest import mock

import major_readiness as readiness
import ci20_native_binding as native_binding_owner
from _boundedproc import start as start_process, terminate_tree

ROOT = Path(__file__).resolve().parents[2]
OBSERVATION = "codearbiter.major-test-observation/1"
SELECTIONS = "codearbiter.major-test-selections/1"
MAX_JSON = 16 * 1024 * 1024
MAX_TESTS = 32768


def require(value, reason):
    if not value:
        raise ValueError(reason)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON field")
        result[key] = value
    return result


def load_json(path):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not path.is_symlink()
            and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            and info.st_size <= MAX_JSON, "observation must be a bounded regular file")
    raw = path.read_bytes()
    require(len(raw) <= MAX_JSON, "observation exceeds bound")
    return json.loads(raw, object_pairs_hook=unique)


def new_output(path, document):
    # A partial JSON file cannot be admitted by any reader. Never overwrite a
    # retained outcome after uncertain publication or a retry.
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def git(repo, *args):
    env = dict(os.environ)
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                 "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                 "GIT_GRAFT_FILE", "GIT_REPLACE_REF_BASE", "GIT_SHALLOW_FILE"):
        env.pop(name, None)
    result = subprocess.run(["git", "--no-replace-objects", "--no-lazy-fetch", "-C", str(repo), *args],
                            env=env, capture_output=True, timeout=30, check=True)
    return result.stdout.decode("utf-8").strip()


def ordinary_native_read_lock(repo):
    """Recognize only the empty untracked lock created by the native read owner.

    Do not ignore the store namespace: journals, arbitrary additions, tracked
    changes and linked/nonempty lock objects must still invalidate source.
    """
    path = Path(repo)
    try:
        for component in (".codearbiter", ".artifacts", "store.lock"):
            path = path / component
            info = path.lstat()
            if path.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                return False
            if component != "store.lock":
                if not stat.S_ISDIR(info.st_mode):
                    return False
            elif not stat.S_ISREG(info.st_mode) or info.st_size != 0 or info.st_nlink != 1:
                return False
        return True
    except OSError:
        return False


def source_identity(repo):
    status = git(repo, "status", "--porcelain=v1", "--untracked-files=all", "-z")
    clean = all(not entry or (entry == "?? .codearbiter/.artifacts/store.lock" and ordinary_native_read_lock(repo))
                for entry in status.split("\0"))
    return {"source_commit": git(repo, "rev-parse", "HEAD"),
            "source_tree": git(repo, "rev-parse", "HEAD^{tree}"),
            "clean": clean}


def observe_python(repo, script, arguments, output):
    """Run the original Python entry point once, observing actual TestResult calls."""
    repo = Path(repo).resolve(strict=True)
    script = (repo / script).resolve(strict=True)
    relative = script.relative_to(repo).as_posix()
    require(script.suffix == ".py" and not Path(output).exists() and not Path(output).is_symlink(),
            "new Python observation required")
    before = source_identity(repo)
    rows, active = [], {}
    original_argv, original_path = sys.argv[:], sys.path[:]
    original_cwd = Path.cwd()

    def start(original):
        def wrapped(result, test):
            test_id = test.id()
            require(isinstance(test_id, str) and 0 < len(test_id.encode("utf-8")) <= 2048
                    and len(rows) < MAX_TESTS, "Python named observation exceeds bound")
            row = {"id": "python:" + relative + ":" + test_id, "result": "unknown"}
            rows.append(row)
            active[id(test)] = row
            return original(result, test)
        return wrapped

    def outcome(original, name):
        def wrapped(result, test, *args, **kwargs):
            if id(test) in active:
                active[id(test)]["result"] = name
            return original(result, test, *args, **kwargs)
        return wrapped

    def subtest(original):
        def wrapped(result, test, sub, error):
            if error is not None and id(test) in active:
                active[id(test)]["result"] = "failed"
            return original(result, test, sub, error)
        return wrapped

    code = 0
    try:
        os.chdir(repo)
        sys.argv[:] = [str(script), *arguments]
        sys.path[0] = str(script.parent)
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(unittest.TestResult, "startTest", start(unittest.TestResult.startTest)))
            for name, state in (("addSuccess", "passed"), ("addFailure", "failed"), ("addError", "failed"),
                                ("addSkip", "skipped"), ("addExpectedFailure", "expected-failure"),
                                ("addUnexpectedSuccess", "failed")):
                stack.enter_context(mock.patch.object(unittest.TestResult, name, outcome(getattr(unittest.TestResult, name), state)))
            stack.enter_context(mock.patch.object(unittest.TestResult, "addSubTest", subtest(unittest.TestResult.addSubTest)))
            try:
                runpy.run_path(str(script), run_name="__main__")
            except SystemExit as error:
                code = error.code if type(error.code) is int else 0 if error.code is None else 1
            except BaseException:
                traceback.print_exc()
                code = 1
    finally:
        sys.argv[:] = original_argv
        sys.path[:] = original_path
        os.chdir(original_cwd)
    after = source_identity(repo)
    new_output(output, {"format": OBSERVATION, **before,
                       "source_stable": before == after and before["clean"],
                       "ci_run_id": int(os.environ.get("GITHUB_RUN_ID", "0")),
                       "proof_kind": "source-test", "producer": "python-test-result-observer",
                       "argv": [sys.executable, str(script), *arguments],
                       "exit_code": code, "tests": rows})
    return code


def admit_go(record, binding, source_tree):
    """Join the original named run to its existing same-run native stamp."""
    require(record.get("format") == "codearbiter.go-test-observation/1"
            and binding.get("format") == "codearbiter.ci-native-candidate/1",
            "wrong native observation or stamp")
    require(set(binding) == native_binding_owner.RECORD_FIELDS
            and binding["producer_job"] == native_binding_owner.PRODUCER
            and binding["workflow"] == native_binding_owner.WORKFLOW
            and binding["toolchain"] == native_binding_owner.TOOLCHAIN
            and binding["platform"] in native_binding_owner.PLATFORMS
            and readiness.SHA.fullmatch(binding["source_commit"])
            and isinstance(binding["run_id"], str) and binding["run_id"].isdigit() and int(binding["run_id"]) > 0
            and all(readiness.DIGEST.fullmatch(binding[key]) for key in (
                "module_sha256", "go_sha256", "manifest_sha256", "binary_sha256")),
            "native stamp lacks the original producer/source/input binding")
    require(record.get("complete") is True
            and record.get("module_sha256_before") == record.get("module_sha256_after")
            == binding.get("module_sha256")
            and readiness.DIGEST.fullmatch(binding.get("module_sha256", "")),
            "native test inputs changed or run incomplete")
    selected = [(r["package"], r["test"]) for r in record["selected"]]
    observed = [(r["package"], r["test"]) for r in record["observed"]]
    require(selected and len(set(selected)) == len(selected) and sorted(selected) == sorted(observed)
            and len(set(observed)) == len(observed), "native named population differs")
    require(all(r.get("result") in ("pass", "skip") for r in record["observed"]), "native failure cannot qualify")
    return {"format": OBSERVATION, "source_commit": binding["source_commit"],
            "source_tree": source_tree, "source_stable": True, "ci_run_id": int(binding["run_id"]),
            "proof_kind": "native-module", "producer": "go-named-ci20-join",
            "native_binding": binding, "argv": record["argv"], "exit_code": 0,
            "tests": [{"id": "go:" + r["package"] + ":" + r["test"],
                       "result": "passed" if r["result"] == "pass" else "skipped"}
                      for r in record["observed"]]}


def admit_vitest(record, *, repo, before, after, argv, exit_code, run_id):
    require(isinstance(record, dict) and isinstance(record.get("testResults"), list), "Vitest named outcomes missing")
    rows = []
    repo = Path(repo).resolve()
    for suite in record["testResults"]:
        path = Path(suite["name"]).resolve().relative_to(repo).as_posix()
        for case in suite["assertionResults"]:
            state = {"passed": "passed", "failed": "failed", "pending": "skipped",
                     "skipped": "skipped", "todo": "skipped", "disabled": "skipped"}.get(case["status"])
            require(state is not None, "unknown Vitest outcome")
            rows.append({"id": "vitest:" + path + ":" + case["fullName"], "result": state})
    require(rows, "Vitest ran no named tests")
    return {"format": OBSERVATION, **before, "source_stable": before == after and before["clean"],
            "ci_run_id": run_id, "proof_kind": "source-test", "producer": "vitest-json-observer", "argv": argv,
            "exit_code": exit_code, "tests": rows}


def observe_vitest(repo, arguments, raw_results, output):
    """Add a JSON reporter to the one original owning Vitest invocation."""
    require(arguments and raw_results and not Path(raw_results).exists() and not Path(raw_results).is_symlink()
            and not Path(output).exists() and not Path(output).is_symlink(),
            "new Vitest result and observation paths required")
    require(not any(a.startswith(("--reporter", "--outputFile")) for a in arguments),
            "the original invocation must use the one owned JSON reporter")
    before = source_identity(repo)
    command = [*arguments, "--reporter=json", "--outputFile=" + str(Path(raw_results).absolute())]
    process = start_process(command, cwd=repo)
    try:
        code = process.wait(timeout=1200)
    except subprocess.TimeoutExpired:
        containment = terminate_tree(process)
        raise ValueError("original Vitest run timed out; containment=" + containment) from None
    after = source_identity(repo)
    document = admit_vitest(load_json(raw_results), repo=repo, before=before, after=after,
                            argv=command, exit_code=code, run_id=int(os.environ.get("GITHUB_RUN_ID", "0")))
    new_output(output, document)
    return code


def validate_selections(document):
    require(isinstance(document, dict) and document.get("schema") == SELECTIONS
            and set(document) == {"schema", "groups"} and isinstance(document["groups"], list)
            and len(document["groups"]) <= 512, "invalid semantic selection map")
    identities = set()
    for group in document["groups"]:
        require(isinstance(group, dict) and set(group) == {"id", "job", "payload_name", "observation", "proof_kind", "selectors", "cells", "scope"},
                "invalid semantic selection group")
        require(group["id"] not in identities and all(isinstance(group[k], str) and group[k]
                for k in ("id", "job", "payload_name", "observation", "proof_kind", "scope")), "invalid selection identity")
        identities.add(group["id"])
        for name in ("selectors", "cells"):
            values = group[name]
            require(isinstance(values, list) and 0 < len(values) <= 4096
                    and all(isinstance(v, str) and v and len(v.encode()) <= 2048 for v in values)
                    and len(set(values)) == len(values), "empty or ambiguous semantic population")
        require(group["proof_kind"] in ("source-test", "native-module", "retained-archive-cli", "live-host"), "unknown proof kind")
    return document["groups"]


def build_report(req, *, job_name, job_id, selections, observations, payloads):
    require(type(job_id) is int and job_id > 0, "positive actual job identity required")
    groups = validate_selections(selections)
    # One declared original-package role is source-bound; no general formatting
    # or caller-provided replacement expressions are accepted.
    require(isinstance(req["source_commit"], str) and readiness.SHA.fullmatch(req["source_commit"]), "exact report source required")
    groups = [dict(g, payload_name="artifact-release-packages-" + req["source_commit"])
              if g["payload_name"] == "artifact-release-packages-{source_commit}" else g for g in groups]
    expected = {cell for cell in req["cells"] if req["cell_jobs"][cell] == job_name}
    require(expected, "job has no required mapped cells")
    selected_groups = [g for g in groups if g["job"] == job_name and expected.intersection(g["cells"])]
    require({cell for g in selected_groups for cell in g["cells"]} == expected,
            "semantic cell mapping is missing, extra or assigned to another job")
    results, indices, retained_payloads = [], {}, {}
    installed_admissions, dual_payload_report = {}, False
    for cell in sorted(expected):
        evidence, selected, executed, payload_name, native_bindings = [], set(), set(), set(), []
        installed_payloads = {}
        for group in (g for g in selected_groups if cell in g["cells"]):
            observed = observations.get(group["observation"], {})
            require(observed.get("format") == OBSERVATION
                    and observed.get("source_commit") == req["source_commit"]
                    and observed.get("source_tree") == req["source_tree"]
                    and observed.get("ci_run_id") == req["ci_run_id"]
                    and observed.get("source_stable") is True
                    and observed.get("proof_kind") == group["proof_kind"]
                    and type(observed.get("exit_code")) is int and observed["exit_code"] == 0,
                    "original execution is absent, failed, stale or has a different proof kind")
            argv = observed.get("argv")
            require(isinstance(argv, list) and argv and all(isinstance(a, str) and a for a in argv), "original command missing")
            if cell.startswith("installed:"):
                require(group["proof_kind"] in ("native-module", "retained-archive-cli", "live-host"),
                        "source tests cannot qualify installed hosts")
                require(group["proof_kind"] != "native-module" or cell.startswith("installed:native:"),
                        "native module tests cannot qualify an upstream host")
            producers = {"source-test": ("python-test-result-observer", "vitest-json-observer"),
                         "native-module": ("go-named-ci20-join",)}
            if group["proof_kind"] == "retained-archive-cli":
                from retained_archive_cli_observation import admit
                if group["observation"] not in installed_admissions:
                    installed_admissions[group["observation"]] = admit(
                        observed, req=req, job_id=job_id, authenticated_payloads=payloads, repo=ROOT)
                admitted = installed_admissions[group["observation"]]
                require(group["payload_name"] == admitted["primary_payload_name"], "cold primary payload differs")
                require(not cell.startswith("installed:") or cell in admitted["installed_cells"],
                        "cold profile cannot qualify this upstream installed cell")
                require(cell != "task:PI-D07", "cold profile cannot qualify packaged Pi authorship")
                for item in admitted["payloads"]:
                    installed_payloads[item["artifact_id"]] = item
                dual_payload_report = True
            else:
                require(observed.get("producer") in producers.get(group["proof_kind"], ()),
                        "no qualified observer for this proof kind")
            if group["proof_kind"] == "native-module":
                native_bindings.append(observed.get("native_binding"))
            key = group["observation"]
            if key not in indices:
                tests = observed.get("tests")
                require(isinstance(tests, list) and len(tests) <= MAX_TESTS
                        and all(isinstance(test, dict) and set(test) == {"id", "result"}
                                and isinstance(test["id"], str) and test["id"]
                                and len(test["id"].encode("utf-8")) <= 4096 for test in tests),
                        "invalid or unbounded original named outcomes")
                indices[key] = {}
                for test in tests:
                    indices[key].setdefault(test["id"], []).append(test)
            for selector in group["selectors"]:
                matches = indices[key].get(selector, [])
                require(len(matches) == 1 and matches[0].get("result") == "passed",
                        "selected named test missing, repeated, skipped or failed: " + selector)
                selected.add((group["observation"], selector))
                executed.add((group["observation"], selector))
            evidence.append({"argv": argv, "exit_code": 0})
            payload_name.add(group["payload_name"])
        require(len(payload_name) == 1, "one cell requires incompatible payload bindings")
        payload = payloads.get(payload_name.pop(), {})
        require(type(payload.get("artifact_id")) is int and payload["artifact_id"] > 0
                and readiness.DIGEST.fullmatch(payload.get("archive_sha256", ""))
                and payload.get("members"), "authenticated consumed payload missing")
        require(all(binding is not None and binding in payload.get("native_bindings", [])
                    for binding in native_bindings), "native tests do not bind the actual consumed payload")
        retained = {"artifact_id": payload["artifact_id"], "archive_sha256": payload["archive_sha256"],
                    "members": payload["members"]}
        identity = retained["artifact_id"]
        require(identity not in retained_payloads or retained_payloads[identity] == retained,
                "one payload artifact has conflicting consumed bytes")
        retained_payloads[identity] = retained
        for extra_id, extra in installed_payloads.items():
            require(extra_id not in retained_payloads or retained_payloads[extra_id] == extra,
                    "one payload artifact has conflicting consumed bytes")
            retained_payloads[extra_id] = extra
        result = {"cell": cell, "result": "PASSED", "commands": evidence,
                  "selected_population": len(selected), "executed_population": len(executed)}
        if installed_payloads:
            require(identity in installed_payloads and len(installed_payloads) == 2,
                    "cold report requires both distinct original payloads")
            result["payload_artifact_ids"] = sorted(installed_payloads)
        else:
            result["payload_artifact_id"] = identity
        results.append(result)
    if dual_payload_report:
        for result in results:
            if "payload_artifact_id" in result:
                result["payload_artifact_ids"] = [result.pop("payload_artifact_id")]
    return {"schema": "codearbiter-major-qualification/3" if dual_payload_report else "codearbiter-major-qualification/2", "source_commit": req["source_commit"],
            "source_tree": req["source_tree"], "ci_run_id": req["ci_run_id"],
            "job_id": job_id, "results": results,
            "payloads": [retained_payloads[i] for i in sorted(retained_payloads)]}


def authenticated_payload(metadata, req, consumed_root):
    archive = readiness.artifact_bytes(metadata, req)
    members = readiness.members(archive)
    root = Path(consumed_root).resolve(strict=True)
    native_bindings = []
    for member in members:
        path = root
        for part in PurePosixPath(member["path"]).parts:
            path = path / part
            info = path.lstat()
            require(not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    "consumed payload contains a link or reparse point")
        require(path.is_file() and path.stat().st_size <= 64 * 1024 * 1024
                and hashlib.sha256(path.read_bytes()).hexdigest() == member["sha256"],
                "executed payload differs from authenticated archive")
        if path.name == "ci20-native-tested.json":
            binding = load_json(path)
            require(binding.get("format") == native_binding_owner.FORMAT,
                    "consumed native stamp has the wrong format")
            native_bindings.append(binding)
    return {"artifact_id": metadata["id"], "archive_sha256": readiness.digest(archive),
            "members": members, "native_bindings": native_bindings}


def validate_emitter_environment():
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_REPOSITORY") == readiness.REPOSITORY
            and os.environ.get("GITHUB_REF") in ("refs/heads/main", "refs/heads/major/state-contracts")
            and os.environ.get("GITHUB_EVENT_NAME") == "push", "reports require trusted main/program push CI")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("observe-python", "observe-vitest", "admit-go", "emit"))
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--observation", action="append", default=[], help="key=JSON path")
    parser.add_argument("--native-binding", type=Path)
    parser.add_argument("--raw-results", type=Path)
    parser.add_argument("--job-name")
    parser.add_argument("--payload-root", action="append", default=[], help="artifact name=original consumed root")
    parser.add_argument("arguments", nargs="*")
    args = parser.parse_args(argv)
    try:
        if args.operation == "observe-python":
            require(args.arguments, "Python entry point required")
            return observe_python(args.repo, args.arguments[0], args.arguments[1:], args.output)
        if args.operation == "observe-vitest":
            return observe_vitest(args.repo, args.arguments, args.raw_results, args.output)
        if args.operation == "admit-go":
            require(len(args.observation) == 1 and args.native_binding, "native observation and original stamp required")
            binding = load_json(args.native_binding)
            tree = git(args.repo, "rev-parse", binding["source_commit"] + "^{tree}")
            new_output(args.output, admit_go(load_json(args.observation[0]), binding, tree))
            return 0
        validate_emitter_environment()
        source, run_id = os.environ["GITHUB_SHA"], int(os.environ["GITHUB_RUN_ID"])
        identity = source_identity(args.repo)
        require(identity["source_commit"] == source and identity["clean"], "report source differs from actual clean checkout")
        req, _, artifacts, jobs = readiness.collect(args.repo, source, run_id, producing=True, allow_program_branch=True, producer_scope=True)
        matching = [j for j in jobs if j["name"] == args.job_name and j.get("status") == "in_progress"]
        require(len(matching) == 1, "one current original owning job required")
        observations = {}
        for item in args.observation:
            key, path = item.split("=", 1)
            require(key not in observations, "duplicate observation key")
            observations[key] = load_json(path)
        payloads = {}
        for item in args.payload_root:
            name, path = item.split("=", 1)
            require(name not in payloads, "duplicate payload identity")
            found = [a for a in artifacts if a["name"] == name]
            require(len(found) == 1, "original consumed artifact missing or ambiguous")
            payloads[name] = authenticated_payload(found[0], req, path)
        report = build_report(req, job_name=args.job_name, job_id=matching[0]["id"],
                              selections=load_json(args.repo / ".github/major-test-selections.json"),
                              observations=observations, payloads=payloads)
        new_output(args.output, report)
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, readiness.ReadinessError) as error:
        print("::error::Major qualification report pending: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
