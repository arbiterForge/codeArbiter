"""Closed retained-package observer fixtures: synthetic unit data, never installed evidence."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


def fixture(platform="windows/amd64"):
    native_name = "ca-artifact-" + platform.replace("/", "-") + (".exe" if platform.startswith("windows/") else "")
    source, tree, run, job = "a" * 40, "b" * 40, 7, 9
    digest = lambda b: hashlib.sha256(b).hexdigest()
    text = lambda v: json.dumps(v, sort_keys=True)
    binary, bridge = "c" * 64, "d" * 64
    manifest = {"format":"codearbiter.artifact-release/0.1.0", "version": "0.1.0", "protocol": "codearbiter.artifact-api/0.1.0", "schema_version": "0.3.2",
                "binaries": {platform: {"file": native_name, "sha256": binary, "native_tested": True}}}
    manifest["context_qualification"] = {platform: {"source_commit":source, "workflow":".github/workflows/ci.yml", "run_id":str(run), "binary_sha256":binary, "observation_sha256":"9"*64, "module_sha256":"0"*64, "native_cases":["TestContextBoundedRender","TestContextDocumentContract","TestContextMarkdownPreservation","TestContextMutationAdmission","TestContextRecoveryAndPaths","TestContextRepresentationBoundary"]}}
    mr = text(manifest)
    promotion = {"format": "codearbiter.artifact-promotion/0.1.0", "source_commit": source,
                 "workflow": ".github/workflows/ci.yml", "run_id": str(run),
                 "version": "0.1.0", "protocol": manifest["protocol"], "schema_version": "0.3.2",
                 "hosts": {"claude": "plugins/ca/helpers/artifacts", "codex": "plugins/ca-codex/helpers/artifacts", "pi": "plugins/ca-pi/helpers/artifacts"},
                 "qualifications": {platform: {"binary_sha256": binary}}}
    pr = text(promotion)
    package_members = {"plugins/ca/helpers/artifacts/release.json": {"sha256": digest(mr.encode())},
                       "plugins/ca/helpers/artifacts/" + native_name: {"sha256": binary},
                       "plugins/ca/hooks/_artifactlib.py": {"sha256": bridge}}
    package = {"file": "claude.tar.gz", "sha256": "e" * 64, "members": package_members}
    cohort = {"format": "codearbiter.artifact-package-cohort/0.1.0", "source_commit": source, "source_tree": tree,
              "workflow": ".github/workflows/ci.yml", "run_id": str(run), "promotion_receipt_sha256": digest(pr.encode()),
              "artifact_version": "0.1.0", "protocol": manifest["protocol"], "schema_version": "0.3.2",
              "pi_packer": {"qualification": "production"}, "packages": {"claude": package, "codex": {}, "pi": {}}}
    cr = text(cohort)
    receipt = {"format": "codearbiter.artifact-cold-execution/0.3.0", "source_commit": source,
        "workflow": ".github/workflows/ci.yml", "run_id": str(run), "job": "artifact-package-cold", "host": "claude",
        "platform": platform, "promotion_receipt_sha256": digest(pr.encode()), "package_sha256": package["sha256"],
        "manifest_sha256": digest(mr.encode()), "binary_sha256": binary, "response_sha256": "1" * 64,
        "operation": "capabilities", "repository_operations_available": True, "runtime_downloads": False,
        "installed_workflow_response_sha256": "2" * 64, "installed_bridge_sha256": bridge,
        "installed_workflow_format": "codearbiter.installed-host-workflow/0.2.0", "approval_evidence_mode": "host-observed-prompt",
        "prerequisite_evidence_mode": "host-observed-prompt", "interruption_reconciled": True, "redispatched": True,
        "commit_proof": True, "finalization_proof": True, "all_accepted_and_current": True, "markdown_shadow_count": 0,
        "context_workflow_scope": "candidate-preflight", "context_installed_output_sha256": "3" * 64,
        "context_installed_tests": [{"name": n, "status": "pass"} for n in (
            "test_t044_installed_context_kind", "test_t044_rejects_missing_candidate_identity", "test_t044_rejects_nonisolated_environment")]}
    packages_name = "artifact-release-packages-" + source
    stage_name = "artifact-host-payloads-" + source
    payloads = {
        packages_name: {"artifact_id": 8, "archive_sha256": "4" * 64,
            "members": [{"path": "artifact-package-cohort.json", "sha256": digest(cr.encode())}, {"path": package["file"], "sha256": package["sha256"]}]},
        stage_name: {"artifact_id": 10, "archive_sha256": "5" * 64,
            "members": [{"path": "artifact-promotion.json", "sha256": digest(pr.encode())},
                {"path": "plugins/ca/helpers/artifacts/release.json", "sha256": digest(mr.encode())},
                {"path": "plugins/ca/helpers/artifacts/" + native_name, "sha256": binary}]}}
    consumed = {role: {"artifact_name": name, **payloads[name]} for role, name in (("promoted-stage", stage_name), ("release-packages", packages_name))}
    source_stamp = {"repository":"C:/repo", "source_commit": source, "source_tree": tree, "clean": True,
                    "inputs": {"tools/build-host-packages.py": "6" * 64}, "core_python_members": ["_artifactlib.py"],
                    "host_lookup": {"path": "core/pysrc/_host.py", "path_style": "windows" if platform.startswith("windows/") else "posix", "present": False}}
    runtime = {"python": {"path": "C:/Python/python.exe", "sha256": "7" * 64},
               "git": {"path": "C:/Git/git.exe", "sha256": "8" * 64}}
    payload_stamp = {role: {"root":"C:/stage" if role=="promoted-stage" else "C:/packages", "members":{m["path"]: m["sha256"] for m in consumed[role]["members"]}} for role in consumed}
    binding = {"format": "codearbiter.installed-observation-binding/1", "profile": "retained-cold-package-v1",
        "source_commit": source, "source_tree": tree, "workflow": ".github/workflows/ci.yml", "ci_run_id": run, "producer_job_id": job,
        "host": "claude", "platform": platform, "consumed_payloads": consumed,
        "cohort_sha256": digest(cr.encode()), "promotion_receipt_sha256": digest(pr.encode()),
        "documents": {"cohort": {"path": "artifact-package-cohort.json", "json_utf8": cr},
                      "promotion": {"path": "artifact-promotion.json", "json_utf8": pr},
                      "manifest": {"path": "plugins/ca/helpers/artifacts/release.json", "json_utf8": mr}},
        "cold_receipt": receipt, "source_before": source_stamp, "source_after": copy.deepcopy(source_stamp),
        "runtime_before": runtime, "runtime_after": copy.deepcopy(runtime),
        "payload_before": payload_stamp, "payload_after": copy.deepcopy(payload_stamp)}
    tests = [{"id": "cli:tools/build-host-packages.py:cold:claude:" + platform, "result": "passed"}]
    tests += [{"id": "receipt:.github/scripts/test_context_installed.py:" + t["name"], "result": "passed"} for t in receipt["context_installed_tests"]]
    req = {"source_commit": source, "source_tree": tree, "ci_run_id": run,
           "cells": ["installed:claude:workflow"], "cell_jobs": {"installed:claude:workflow": "cold owning job"}}
    observation = {"format": "codearbiter.major-test-observation/1", "source_commit": source, "source_tree": tree,
        "ci_run_id": run, "source_stable": True, "proof_kind": "retained-archive-cli", "producer": "retained-cold-package-observer-v1",
        "argv": ["C:/Python/python.exe", "-I", "-B", "C:/repo/tools/build-host-packages.py",
            "--release-package-stage", "C:/stage", "--cold-package-root", "C:/packages", "--source-repo", "C:/repo",
            "--cold-host", "claude", "--cold-platform", platform, "--trusted-source-commit", source,
            "--trusted-workflow", ".github/workflows/ci.yml", "--trusted-workflow-run", str(run),
            "--cold-promotion-receipt-sha256", digest(pr.encode()), "--cold-receipt", "C:/output/artifact-package-cold.json"], "exit_code": 0,
        "tests": tests, "installed_binding": binding}
    selection = {"schema": "codearbiter.major-test-selections/1", "groups": [{"id": "cold", "job": "cold owning job",
        "payload_name": packages_name, "observation": "cold", "proof_kind": "retained-archive-cli",
        "selectors": [t["id"] for t in tests], "cells": req["cells"][:], "scope": "Actual retained helper workflow, not public Claude TUI."}]}
    return req, selection, observation, payloads


class ColdBindingTest(unittest.TestCase):
    def admit(self, changes=None):
        import retained_archive_cli_observation as owner
        req, _, observed, payloads = fixture()
        if changes: changes(req, observed, payloads)
        return owner.admit(observed, req=req, job_id=9, authenticated_payloads=payloads)

    def test_valid_profile_derives_one_cli_and_three_actual_context_names(self):
        value = self.admit()
        self.assertEqual(value["payload_artifact_ids"], [8, 10])
        self.assertEqual(len(value["tests"]), 4)
        self.assertEqual(value["installed_cells"], ["installed:claude:workflow", "installed:native:windows:amd64"])

    def test_executed_package_qualifies_only_its_native_platform(self):
        import major_qualification_report as report_owner
        import retained_archive_cli_observation as profile
        platforms = ("linux/amd64", "linux/arm64", "windows/amd64", "windows/arm64",
                     "darwin/amd64", "darwin/arm64")
        for platform in platforms:
            with self.subTest(platform=platform):
                req, selection, observed, payloads = fixture(platform)
                native = "installed:native:" + platform.replace("/", ":")
                req["cells"].append(native)
                req["cell_jobs"][native] = "cold owning job"
                selection["groups"][0]["cells"] = req["cells"][:]
                report = report_owner.build_report(
                    req, job_name="cold owning job", job_id=9, selections=selection,
                    observations={"cold": observed}, payloads=payloads,
                )
                self.assertEqual({row["cell"] for row in report["results"]}, set(req["cells"]))
                self.assertTrue(all(row["selected_population"] == row["executed_population"] == 4
                                    and row["payload_artifact_ids"] == [8, 10] for row in report["results"]))
                admitted = profile.admit(observed, req=req, job_id=9, authenticated_payloads=payloads)
                self.assertEqual(admitted["installed_cells"], ["installed:claude:workflow", native])
                for other in platforms:
                    if other == platform:
                        continue
                    cell = "installed:native:" + other.replace("/", ":")
                    req["cells"] = [cell]; req["cell_jobs"] = {cell: "cold owning job"}
                    selection["groups"][0]["cells"] = [cell]
                    with self.subTest(requested=cell), self.assertRaisesRegex(ValueError, "cold profile"):
                        report_owner.build_report(
                            req, job_name="cold owning job", job_id=9, selections=selection,
                            observations={"cold": observed}, payloads=payloads,
                        )

    def test_source_test_argv_cannot_be_relabelled_with_a_copied_binding(self):
        with self.assertRaises(ValueError):
            self.admit(lambda q,o,p:o.update(argv=["python","source_tests.py"]))

    def test_closed_identity_profile_and_source_runtime_payload_drift_refuse(self):
        for mutate in [lambda q,o,p:o["installed_binding"].update(profile="unknown"),
                       lambda q,o,p:o["installed_binding"].update(producer_job_id=8),
                       lambda q,o,p:o["installed_binding"].update(ci_run_id=8),
                       lambda q,o,p:o["installed_binding"].update(extra=True),
                       lambda q,o,p:o["installed_binding"]["source_after"].update(clean=False),
                       lambda q,o,p:o["installed_binding"]["runtime_after"]["python"].update(sha256="0"*64),
                       lambda q,o,p:o["installed_binding"]["payload_after"]["promoted-stage"].clear(),
                       lambda q,o,p:o.update(producer="python-test-result-observer")]:
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):self.admit(mutate)

    def test_receipt_flags_modes_names_and_exact_payload_joins_refuse(self):
        mutations = [lambda q,o,p:o["installed_binding"]["cold_receipt"].update(binary_sha256="9"*64),
                     lambda q,o,p:o["installed_binding"]["cold_receipt"].update(installed_bridge_sha256="9"*64),
                     lambda q,o,p:o["installed_binding"]["cold_receipt"].update(approval_evidence_mode="synthetic-policy-event"),
                     lambda q,o,p:o["installed_binding"]["cold_receipt"].update(markdown_shadow_count=False),
                     lambda q,o,p:o["installed_binding"]["cold_receipt"].update(commit_proof=False),
                     lambda q,o,p:o["installed_binding"]["cold_receipt"]["context_installed_tests"].append(o["installed_binding"]["cold_receipt"]["context_installed_tests"][0]),
                     lambda q,o,p:o["tests"].append({"id":"invented phase", "result":"passed"}),
                     lambda q,o,p:next(iter(p.values())).update(artifact_id=99)]
        for mutate in mutations:
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):self.admit(mutate)



class ColdProducerTest(unittest.TestCase):
    def exercise(self, *, failed=False, deny=False, drift=False, timed_out=False, containment="exited"):
        import retained_archive_cli_observation as owner
        from types import SimpleNamespace
        req, _, observed, payloads = fixture()
        b = observed["installed_binding"]
        with tempfile.TemporaryDirectory(prefix="ca-cold-observer-unit-") as directory:
            root = Path(directory).resolve()
            repo, stage, packages = Path(__file__).resolve().parents[2], root/"stage", root/"packages"
            for d in [repo, stage, packages, repo/"core/pysrc"]:d.mkdir(parents=True, exist_ok=True)
            for key, folder in [("cohort",packages),("promotion",stage),("manifest",stage)]:
                doc=b["documents"][key];path=folder/doc["path"];path.parent.mkdir(parents=True, exist_ok=True);path.write_text(doc["json_utf8"],encoding="utf8")
            source=copy.deepcopy(b["source_before"]);source["repository"]=str(repo)
            stamps={str(stage):{**b["payload_before"]["promoted-stage"],"root":str(stage)},
                    str(packages):{**b["payload_before"]["release-packages"],"root":str(packages)}}
            events=[]
            def verify(*args):
                events.append("production-admission")
                if deny:raise ValueError("production refusal")
                return {}
            def run(argv,**kwargs):
                events.append("cold-command")
                self.assertNotIn("GH_TOKEN",kwargs["env"])
                self.assertEqual(argv[1:3],["-I","-B"])
                self.assertEqual(argv.count("--cold-host"),1)
                self.assertEqual(argv[argv.index("--trusted-source-commit")+1],req["source_commit"])
                Path(argv[-1]).write_text(json.dumps(b["cold_receipt"]),encoding="utf8")
                return SimpleNamespace(returncode=1 if failed else 0,timed_out=timed_out,containment=containment,stdout="",stderr="PrivateFixtureValue" if failed else "")
            after=copy.deepcopy(source)
            if drift:after["clean"]=False
            output=root/"observation.json"
            with mock.patch.object(owner,"_source_snapshot",side_effect=[source,after]), \
                 mock.patch.object(owner,"_runtime_snapshot",return_value=b["runtime_before"]), \
                 mock.patch.object(owner,"physical_members",side_effect=lambda path:copy.deepcopy(stamps[str(path)])), \
                 mock.patch.object(owner,"_verify_production",side_effect=verify), \
                 mock.patch.dict("os.environ",{"GH_TOKEN":"PrivateFixtureValue"}):
                result=owner.observe(repo=repo,req=req,job_id=9,host="claude",platform="windows/amd64",
                    stage=stage,package_root=packages,authenticated_payloads=payloads,output=output,runner=run)
            document=json.loads(output.read_bytes())
            self.assertNotIn("PrivateFixtureValue",output.read_text())
            if not failed and not deny and not timed_out and containment=="exited":
                self.assertEqual((output.parent/"artifact-package-cold.json").read_bytes(), json.dumps(b["cold_receipt"]).encode("utf8"))
            completion=output.with_name(output.name+".execution.json")
            return result,document,events,json.loads(completion.read_bytes()) if completion.exists() else None

    def test_one_original_cold_command_follows_production_admission_and_binds_actual_receipt(self):
        result,doc,events,completion=self.exercise()
        self.assertEqual(result,0)
        self.assertEqual(events,["production-admission","cold-command"])
        self.assertEqual(len(doc["tests"]),4)
        self.assertEqual(completion["returncode"],0)
        self.assertEqual(doc["installed_binding"]["source_before"],doc["installed_binding"]["source_after"])

    def test_production_refusal_prevents_any_command(self):
        result,doc,events,completion=self.exercise(deny=True)
        self.assertEqual(result,1)
        self.assertEqual(events,["production-admission"])
        self.assertEqual(doc["tests"],[])
        self.assertIsNone(completion)

    def test_failed_execution_is_durably_recorded_and_never_qualified_or_leaked(self):
        result,doc,events,completion=self.exercise(failed=True)
        self.assertEqual(result,1)
        self.assertEqual(completion["returncode"],1)
        self.assertEqual(doc["tests"],[])
        self.assertFalse(doc["source_stable"])
        self.assertEqual(events.count("cold-command"),1)

    def test_source_drift_after_one_command_prevents_affirmative_observation(self):
        result,doc,events,completion=self.exercise(drift=True)
        self.assertEqual(result,1)
        self.assertEqual(events.count("cold-command"),1)
        self.assertEqual(completion["returncode"],0)
        self.assertFalse(doc["source_stable"])

    def test_timeout_or_unconfirmed_containment_cannot_qualify_or_retry(self):
        for changes in ({"timed_out":True},{"containment":"unconfirmed"}):
            with self.subTest(changes=changes):
                result,doc,events,completion=self.exercise(**changes)
                self.assertEqual(result,1)
                self.assertEqual(doc["tests"],[])
                self.assertEqual(events.count("cold-command"),1)
                self.assertIsNotNone(completion)

    def test_production_owner_is_called_with_require_production_true(self):
        import retained_archive_cli_observation as owner
        verifier=mock.Mock(return_value={})
        with mock.patch.object(owner,"_load_packager",return_value=type("Pack",(),{"verify_artifact_release_packages":verifier})):
            owner._verify_production(Path("repo"),Path("packages"),Path("stage"),fixture()[0],"a"*64)
        self.assertIs(verifier.call_args.kwargs["require_production"],True)

    def test_public_bootstrap_refuses_cached_foreign_release_shim_before_effects(self):
        import retained_archive_cli_observation as owner
        from types import ModuleType
        foreign = ModuleType("_releaselib")
        foreign.__file__ = str(Path(tempfile.gettempdir()) / "foreign-release-shim.py")
        req, _, _, payloads = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            # Actual current source root; refuse before even snapshot/verifier effects.
            repo = Path(__file__).resolve().parents[2]
            with mock.patch.dict(sys.modules, {"_releaselib": foreign}), \
                 mock.patch.object(owner, "_source_snapshot", side_effect=AssertionError("snapshot must not start")), \
                 mock.patch.object(owner, "_verify_production", side_effect=AssertionError("verifier must not start")):
                result = owner.observe(repo=repo, req=req, job_id=9, host="claude", platform="windows/amd64",
                    stage=root, package_root=root, authenticated_payloads=payloads, output=root/"refusal.json")
            self.assertEqual(result, 1)
            self.assertEqual(json.loads((root/"refusal.json").read_bytes())["tests"], [])


class SourceCheckoutDiagnosticTests(unittest.TestCase):
    def test_dirty_source_refusal_retains_closed_status_provenance(self):
        import retained_archive_cli_observation as owner
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory).resolve()
            tracked = "core/pysrc/helper.py"
            unknown = "private-unknown-name-canary.py"
            file = repo / tracked
            file.parent.mkdir(parents=True)
            file.write_bytes(b"# original public source\n")
            def git(*args):
                return subprocess.run(["git", "--no-lazy-fetch", "-C", str(repo), *args],
                                      check=True, capture_output=True).stdout
            git("init", "-q")
            git("add", ".")
            git("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "-qm", "private fixture")
            file.write_bytes(b"# changed owned fixture\n")
            (repo / unknown).write_bytes(b"# private fixture content must never be retained\n")
            status = git("status", "--porcelain=v1", "--untracked-files=all", "-z")
            self.assertIn(b" M " + tracked.encode() + b"\0", status)
            self.assertIn(b"?? " + unknown.encode() + b"\0", status)
            with self.assertRaisesRegex(ValueError, "observer source checkout is not clean") as caught:
                owner._source_snapshot(repo)
            diagnostic = getattr(caught.exception, "source_checkout_diagnostic", None)
            self.assertIsInstance(diagnostic, dict, "clean refusal must retain bounded status provenance")
            self.assertEqual(diagnostic["format"], "codearbiter.source-checkout-diagnostic/1")
            self.assertEqual(diagnostic["status_sha256"], hashlib.sha256(status).hexdigest())
            entries = {entry["path_sha256"]: entry for entry in diagnostic["entries"]}
            self.assertEqual(len(entries), 2)
            public = entries[hashlib.sha256(tracked.encode()).hexdigest()]
            private = entries[hashlib.sha256(unknown.encode()).hexdigest()]
            self.assertEqual(public["status"], " M")
            self.assertEqual(public["path"], tracked)
            self.assertEqual(private["status"], "??")
            self.assertNotIn("path", private)
            self.assertNotIn(unknown, json.dumps(diagnostic))
            self.assertNotIn("private fixture content", json.dumps(diagnostic))
            self.assertEqual(git("status", "--porcelain=v1", "--untracked-files=all", "-z"), status)


class PhysicalSourceTest(unittest.TestCase):
    def test_project_bootstrap_loads_actual_shim_not_same_path_stale_module_and_restores_registry(self):
        import retained_archive_cli_observation as owner
        from types import ModuleType
        repo=Path(__file__).resolve().parents[2]
        stale=ModuleType("_releaselib");stale.__file__=str(repo/".github/scripts/_releaselib.py")
        stale.SEMVER=object();stale.semver_greater=lambda *a:False;stale.semver_key=lambda *a:None
        prefix=sys.pycache_prefix;original_path=sys.path[:]
        with tempfile.TemporaryDirectory() as temporary,mock.patch.dict(sys.modules,{"_releaselib":stale}):
            with owner._project_imports(repo,Path(temporary)/"bytecode"):
                packager=owner._load_packager(repo)
                self.assertIsNot(packager.SEMVER,stale.SEMVER)
                self.assertTrue(packager.SEMVER.fullmatch("1.2.3"))
                self.assertEqual(sys.pycache_prefix,str(Path(temporary)/"bytecode"))
            self.assertIs(sys.modules["_releaselib"],stale)
        self.assertEqual(sys.pycache_prefix,prefix)
        self.assertEqual(sys.path,original_path)

    def test_literal_git_capture_includes_release_shim_and_rejects_changed_bytes(self):
        import retained_archive_cli_observation as owner
        with tempfile.TemporaryDirectory() as temporary:
            repo=Path(temporary).resolve()
            for name in ("core/pysrc/helper.py","core/pysrc/_releaselib.py",".github/scripts/_releaselib.py","tools/build-host-packages.py"):
                path=repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b"# actual source\n")
            def git(*args):return subprocess.run(["git","-C",str(repo),*args],check=True,capture_output=True).stdout.decode().strip()
            git("init","-q");git("add",".");git("-c","user.name=fixture","-c","user.email=fixture@example.invalid","commit","-qm","fixture")
            source=git("rev-parse","HEAD")
            stamp=owner._source_snapshot(repo)
            self.assertIn(".github/scripts/_releaselib.py",stamp["inputs"])
            self.assertFalse(stamp["host_lookup"]["present"])
            shim=repo/".github/scripts/_releaselib.py";original=shim.read_bytes();shim.write_bytes(b"# replacement\n")
            with self.assertRaisesRegex(ValueError,"physical source differs"):
                owner._literal_source_inputs(repo,source)
            shim.write_bytes(original)
            (repo/"core/pysrc/_host.py").write_bytes(b"# unknown override\n")
            with self.assertRaises(ValueError):owner._source_snapshot(repo)

    def test_physical_membership_observes_addition_and_refuses_linked_member(self):
        import retained_archive_cli_observation as owner
        import os
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();(root/"one").write_bytes(b"one")
            before=owner.physical_members(root)
            (root/"two").write_bytes(b"two")
            self.assertNotEqual(before,owner.physical_members(root))
            # Windows junction creation uses the actual owned paths, no operator data.
            target=root/"target";target.mkdir();link=root/"linked"
            if os.name=="nt":
                subprocess.run([os.environ.get("ComSpec","cmd.exe"),"/d","/c","mklink","/J",str(link),str(target)],check=True,capture_output=True)
            else:link.symlink_to(target,target_is_directory=True)
            try:
                with self.assertRaisesRegex(ValueError,"linked observer"):
                    owner.physical_members(root)
            finally:link.rmdir() if os.name=="nt" else link.unlink()



class ColdCliDiagnosticTest(unittest.TestCase):
    def render_cli_error(self, error):
        import ast
        import contextlib
        import io
        import retained_archive_cli_observation as owner
        tree = ast.parse(Path(owner.__file__).read_bytes())
        branch = next(node for node in tree.body if isinstance(node, ast.If)
                      and isinstance(node.test, ast.Compare)
                      and isinstance(node.test.left, ast.Name)
                      and node.test.left.id == "__name__")
        def fail():
            raise error
        namespace = dict(vars(owner), __name__="__main__", main=fail)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as stopped:
            exec(compile(ast.Module(body=[branch], type_ignores=[]), owner.__file__, "exec"), namespace)
        self.assertEqual(stopped.exception.code, 1)
        expected = hashlib.sha256(str(error).encode("utf-8", errors="replace")).hexdigest()
        self.assertIn("diagnostic_sha256=" + expected, stderr.getvalue())
        return stderr.getvalue()

    def chained(self, cause):
        outer = ValueError("upload attribution unavailable or malformed")
        outer.__cause__ = cause
        return outer

    def test_cli_distinguishes_underlying_upload_log_command_failure(self):
        output = self.render_cli_error(self.chained(ValueError("readiness observation failed: gh")))
        self.assertIn("code=UPLOAD_LOG_COMMAND_FAILED;", output)

    def test_cli_distinguishes_fixed_timeouts_and_attribution_rejections(self):
        for containment in ("exited", "terminated", "unconfirmed"):
            with self.subTest(containment=containment):
                error = self.chained(ValueError("readiness observation timed out; containment=" + containment))
                self.assertIn("code=UPLOAD_LOG_TIMEOUT;", self.render_cli_error(error))
        for reason in ("required exact upload step did not succeed",
                       "artifact created outside claimed upload step",
                       "upload attribution log exceeds bound",
                       "claimed upload step did not run the pinned artifact uploader",
                       "artifact ID/name/digest not finalized by claimed upload job"):
            with self.subTest(reason=reason):
                self.assertIn("code=UPLOAD_ATTRIBUTION_REJECTED;",
                              self.render_cli_error(self.chained(ValueError(reason))))

    def test_cli_classifies_fixed_metadata_and_encoding_failures(self):
        cases = [(KeyError("created_at"), "UPLOAD_METADATA_INVALID"),
                 (ValueError("invalid upload time identity"), "UPLOAD_METADATA_INVALID"),
                 (ValueError("Invalid isoformat string: 'fixture-private-value'"), "UPLOAD_METADATA_INVALID"),
                 (UnicodeDecodeError("utf8", b"\xff", 0, 1, "invalid start"), "UPLOAD_LOG_MALFORMED")]
        for cause, code in cases:
            with self.subTest(code=code):
                output = self.render_cli_error(self.chained(cause))
                self.assertIn("code=" + code + ";", output)
                self.assertNotIn("fixture-private-value", output)

    def test_cli_unknown_secret_and_unrelated_command_failures_stay_unknown(self):
        private = "fixture-private-canary https://example.invalid/?auth=fixture-value"
        for error in (self.chained(ValueError(private)), ValueError(private),
                      ValueError("readiness observation failed: gh"),
                      self.chained(KeyError(private))):
            with self.subTest(error_type=type(error).__name__):
                output = self.render_cli_error(error)
                self.assertIn("code=UNKNOWN;", output)
                self.assertNotIn(private, output)
                self.assertNotIn("example.invalid", output)

    def test_cli_cyclic_or_oversized_cause_chain_is_bounded(self):
        cycle = self.chained(ValueError("unknown"))
        cycle.__cause__.__cause__ = cycle
        self.assertIn("code=UNKNOWN;", self.render_cli_error(cycle))
        chain = self.chained(ValueError("readiness observation failed: gh"))
        for _ in range(20):
            wrapper = ValueError("unknown wrapper")
            wrapper.__cause__ = chain
            chain = wrapper
        self.assertIn("code=UNKNOWN;", self.render_cli_error(chain))

    def test_cli_unknown_cause_string_is_never_rendered(self):
        class UnsafeString(ValueError):
            def __str__(self):
                raise AssertionError("unknown cause string must not be evaluated")
        self.assertIn("code=UNKNOWN;", self.render_cli_error(self.chained(UnsafeString("untrusted"))))



class UploadLogProducerDiagnosticTest(unittest.TestCase):
    def failure(self):
        from test_major_readiness import UploadLogDiagnosticTest
        case = UploadLogDiagnosticTest()
        return case.failed_upload(), case.expected(case.STDERR)

    def cold_details(self, error):
        text = ColdCliDiagnosticTest().render_cli_error(error)
        self.assertNotIn("unit-private-diagnostic", text)
        self.assertNotIn("unit.invalid", text)
        self.assertNotIn("never-report", text)
        marker = "; command_diagnostic="
        detail = json.loads(text.split(marker, 1)[1].strip()) if marker in text else None
        return detail, text

    def test_existing_cold_cli_failure_retains_closed_upload_command_detail(self):
        error, expected = self.failure()
        detail, text = self.cold_details(error)
        self.assertIn("code=UPLOAD_LOG_COMMAND_FAILED;", text)
        self.assertEqual(detail, expected)

    def test_existing_coordinator_failure_artifacts_retain_closed_upload_command_detail(self):
        from contextlib import ExitStack, nullcontext
        from types import SimpleNamespace
        import os
        import coordinate_codex_host
        import coordinate_pi_host
        import retained_archive_cli_observation as cold
        for family, coordinator in (("codex", coordinate_codex_host), ("pi", coordinate_pi_host)):
            with self.subTest(family=family), tempfile.TemporaryDirectory() as temporary:
                error, expected = self.failure()
                root = Path(temporary)
                repo = root / "source"
                repo.mkdir()
                output = root / "output"
                producer = SimpleNamespace(source_binding=lambda *args: None,
                                           actual_platform=lambda: "linux/amd64")
                def bootstrap(_repo, _source, relative, _name, _git):
                    return cold if relative.endswith("retained_archive_cli_observation.py") else producer
                argv = ["--repo", str(repo), "--stage", str(root / "stage"),
                        "--package-root", str(root / "packages"),
                        "--workspace", str(root / "workspace"), "--output-root", str(output)]
                argv += ["--codex-version", "0.143.0"] if family == "codex" else [
                    "--expected-platform", "linux/amd64"]
                # Synthetic refusal setup only: the control boundary raises before
                # acquisition, host execution or any API call. It never qualifies.
                with ExitStack() as stack:
                    stack.enter_context(mock.patch.dict(os.environ, {"GITHUB_SHA": "a" * 40}))
                    stack.enter_context(mock.patch.object(coordinator, "program_mode", return_value=True))
                    stack.enter_context(mock.patch.object(coordinator.shutil, "which", return_value="unit-git"))
                    stack.enter_context(mock.patch.object(coordinator.subprocess, "run",
                        return_value=SimpleNamespace(stdout=("a" * 40 + "\n").encode())))
                    stack.enter_context(mock.patch.object(coordinator, "_verified_bootstrap_module", side_effect=bootstrap))
                    stack.enter_context(mock.patch.object(coordinator, "_run_control", side_effect=error))
                    stack.enter_context(mock.patch.object(cold, "private_environment", side_effect=lambda _root: nullcontext()))
                    stack.enter_context(mock.patch.object(cold, "_literal_source_inputs", return_value={}))
                    if family == "pi":
                        stack.enter_context(mock.patch.object(coordinator, "selected_runtime", return_value={"git": "unit-git"}))
                        stack.enter_context(mock.patch.object(coordinator, "_python_lookup_membership"))
                    with self.assertRaises(type(error)) as caught:
                        coordinator.main(argv)
                self.assertIs(caught.exception, error)
                record = json.loads((output / "coordinator-failure.json").read_text())
                self.assertEqual(record["phase"], "bootstrap")
                self.assertEqual(record["diagnostic_sha256"], hashlib.sha256(str(error).encode()).hexdigest())
                self.assertEqual(record.get("command_diagnostic"), expected)
                serialized = json.dumps(record)
                self.assertNotIn("unit-private-diagnostic", serialized)
                self.assertNotIn("unit.invalid", serialized)
                self.assertNotIn("never-report", serialized)

    def test_closed_upload_diagnostic_projection_refuses_malformed_or_unbounded_causes(self):
        from test_major_readiness import owner as readiness
        error, expected = self.failure()
        class StringSpoof(str):
            pass
        bad = [dict(expected, extra="unit-private-diagnostic"),
               dict(expected, operation=StringSpoof("github-actions-job-log")),
               dict(expected, exit_code=True), dict(expected, http_status="403"),
               dict(expected, stderr_sha256="unit-private-diagnostic")]
        for detail in bad:
            with self.subTest(keys=sorted(detail)):
                error.__cause__.command_diagnostic = detail
                observed, _ = self.cold_details(error)
                self.assertIsNone(observed)
        error.__cause__.command_diagnostic = expected
        for _ in range(20):
            wrapper = readiness.ReadinessError("unit wrapper")
            wrapper.__cause__ = error
            error = wrapper
        self.assertIsNone(self.cold_details(error)[0])
        cycle = readiness.ReadinessError("unit cycle")
        cycle.__cause__ = cycle
        self.assertIsNone(self.cold_details(cycle)[0])



class UploadHTTPReasonProjectionTest(unittest.TestCase):
    def detail(self, **extra):
        return {"operation":"github-actions-job-log", "code":"UPLOAD_LOG_COMMAND_FAILED", "exit_code":9,
                "http_status":403, "stderr_sha256":"a"*64, **extra}

    def render(self, detail):
        from major_readiness import ReadinessError
        error = ReadinessError("upload attribution unavailable or malformed")
        cause = ReadinessError("readiness job log HTTP observation failed")
        cause.command_diagnostic = detail
        error.__cause__ = cause
        return ColdCliDiagnosticTest().render_cli_error(error)

    def test_optional_closed_http_transport_reason_survives_existing_cold_failure_sink(self):
        for reason in ("http_error","redirect_refused","redirect_limit","body_limit","network_error","invalid_request","worker_failed","tls_error","dns_error","timeout"):
            with self.subTest(reason=reason):
                expected = self.detail(transport_reason=reason)
                text = self.render(expected)
                marker = "; command_diagnostic="
                observed = json.loads(text.split(marker,1)[1].strip()) if marker in text else None
                self.assertEqual(observed, expected)
                self.assertIn("code=UPLOAD_LOG_COMMAND_FAILED;", text)

    def test_optional_reason_projection_preserves_legacy_and_refuses_unknown_or_extra_values(self):
        from retained_archive_cli_observation import _command_diagnostic
        from major_readiness import ReadinessError
        legacy=self.detail();error=ReadinessError("fixed")
        error.command_diagnostic=legacy;self.assertEqual(_command_diagnostic(error),legacy)
        class StringSpoof(str):
            pass
        for bad in [self.detail(transport_reason="unit-private-arbitrary"),self.detail(transport_reason=True),
                    self.detail(transport_reason=StringSpoof("http_error")),
                    self.detail(transport_reason="http_error", extra="unit-private-arbitrary")]:
            with self.subTest(keys=sorted(bad)):
                error.command_diagnostic=bad;self.assertIsNone(_command_diagnostic(error))




from contextlib import contextmanager


@contextmanager
def observer_checkout_fixture(checkout_settings):
    """Private Git configuration only; no user/global config or checkout edits."""
    import os
    import shutil
    import retained_archive_cli_observation as owner
    git_executable = shutil.which("git")
    if git_executable is None:
        raise AssertionError("Git is required for the checkout admission fixture")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        repo = root / "repo"; repo.mkdir()
        profile = root / "checkout-home"; profile.mkdir()
        global_config = root / "fixture-global.gitconfig"
        global_config.write_text("[core]\n\tautocrlf = true\n\teol = crlf\n", encoding="utf8")
        base = {key: value for key, value in os.environ.items()
                if key.upper() in {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT"}}
        base.update(PATH=os.pathsep.join([str(Path(git_executable).parent), str(Path(sys.executable).parent)]),
                    HOME=str(profile), USERPROFILE=str(profile), GIT_CONFIG_NOSYSTEM="1",
                    GIT_CONFIG_GLOBAL=str(global_config), GIT_TERMINAL_PROMPT="0")
        def git(*args, settings=None):
            env = dict(base)
            if settings is not None: env.update(settings)
            return subprocess.run([git_executable, "--no-lazy-fetch", "-C", str(repo), *args],
                                  env=env, check=True, capture_output=True, timeout=15).stdout
        git("init", "-q")
        contents = {".gitattributes": b"*.py text eol=lf\n.gitattributes text eol=lf\n/retained.raw -text\n",
                    "core/pysrc/helper.py": b"# fixed LF source input\n",
                    "plugins/ca/tools/.env.example": b"FIXTURE_EXAMPLE=not-a-credential\n",
                    "site/example.html": b"<p>public fixture</p>\n",
                    "retained.raw": b"historical\r\nexact bytes\r\n"}
        for name, value in contents.items():
            target = repo / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(value)
        git("-c", "core.autocrlf=false", "-c", "core.eol=lf", "add", ".")
        git("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-qm", "private line-ending fixture")
        # Only owned fixture files are removed to let Git materialize a fresh
        # checkout. This is not post-checkout normalization or user-file repair.
        for name in contents: (repo / name).unlink()
        git("checkout", "--force", "HEAD", "--", ".", settings=checkout_settings)
        before = {name: (repo / name).read_bytes() for name in contents}
        source = git("rev-parse", "HEAD").decode().strip()
        def snapshot():
            with mock.patch.dict(os.environ, base, clear=True):
                with owner.private_environment(root / "observer-home"):
                    return owner._source_snapshot(repo)
        yield {"repo": repo, "contents": contents, "before": before, "source": source,
               "snapshot": snapshot, "status": lambda: git("status", "--porcelain=v1", "--untracked-files=all", "-z")}


class CheckoutPolicyCharacterizationTests(unittest.TestCase):
    def test_private_git_policy_refuses_crlf_checkout_but_fresh_lf_checkout_preserves_exact_bytes(self):
        # Simulate a runner's global setting using only an explicit private file.
        with observer_checkout_fixture({}) as fixture:
            self.assertEqual(fixture["status"](), b"")
            example = "plugins/ca/tools/.env.example"
            self.assertIn(b"\r\n", fixture["before"][example])
            with self.assertRaisesRegex(ValueError, "observer source checkout is not clean") as caught:
                fixture["snapshot"]()
            detail = getattr(caught.exception, "source_checkout_diagnostic", {})
            self.assertIn(example, [entry.get("path") for entry in detail.get("entries", [])])
            self.assertEqual({name: (fixture["repo"] / name).read_bytes() for name in fixture["before"]}, fixture["before"])
        policy = {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "false",
                  "GIT_CONFIG_KEY_1": "core.eol", "GIT_CONFIG_VALUE_1": "lf"}
        with observer_checkout_fixture(policy) as fixture:
            self.assertEqual(fixture["before"], fixture["contents"])
            snapshot = fixture["snapshot"]()
            self.assertTrue(snapshot["clean"])
            self.assertEqual(snapshot["source_commit"], fixture["source"])
            self.assertEqual(snapshot["inputs"]["core/pysrc/helper.py"], hashlib.sha256(fixture["contents"]["core/pysrc/helper.py"]).hexdigest())
            self.assertEqual((fixture["repo"] / "retained.raw").read_bytes(), b"historical\r\nexact bytes\r\n")
            tracked = fixture["repo"] / "site/example.html"
            tracked.write_bytes(b"<p>real changed bytes</p>\n")
            with self.assertRaisesRegex(ValueError, "observer source checkout is not clean"):
                fixture["snapshot"]()
            self.assertEqual(tracked.read_bytes(), b"<p>real changed bytes</p>\n")

    def test_source_identity_rechecks_foreign_policy_stat_cache_and_preserves_real_staged_guard(self):
        import os
        import major_qualification_report as reports
        import retained_archive_cli_observation as observer
        from _gitexec import local_read_git_env
        policy = {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "false",
                  "GIT_CONFIG_KEY_1": "core.eol", "GIT_CONFIG_VALUE_1": "lf"}
        for label, settings, clean in (("crlf", {}, False), ("lf", policy, True)):
            with self.subTest(checkout=label), observer_checkout_fixture(settings) as fixture:
                repo = fixture["repo"]
                # Seed a real stat cache under the checkout's explicit foreign
                # policy without relying on racy-Git timestamp fallback.
                for name in fixture["before"]:
                    os.utime(repo / name, ns=(1000000000000000000, 1000000000000000000))
                self.assertEqual(fixture["status"](), b"")
                index = repo / ".git/index"
                def retained_index():
                    info = index.stat()
                    return (index.read_bytes(), info.st_dev, info.st_ino, info.st_size,
                            info.st_mode, info.st_mtime_ns, info.st_ctime_ns)
                before_index = retained_index()
                before_bytes = {name: (repo / name).read_bytes() for name in fixture["before"]}
                with observer.private_environment(repo.parent / "explicit-private-home"):
                    identity = reports.source_identity(repo)
                self.assertEqual(identity["clean"], clean, "A cached foreign-policy stat must not stand in for a current-policy worktree read")
                if clean:
                    self.assertTrue(fixture["snapshot"]()["clean"])
                else:
                    with self.assertRaisesRegex(ValueError, "observer source checkout is not clean") as caught:
                        fixture["snapshot"]()
                    detail = getattr(caught.exception, "source_checkout_diagnostic", {})
                    self.assertIn("plugins/ca/tools/.env.example", [row.get("path") for row in detail.get("entries", [])])
                self.assertEqual(retained_index(), before_index)
                self.assertEqual({name: (repo / name).read_bytes() for name in before_bytes}, before_bytes)
                if clean:
                    # A separate real staged-index guard is required even when
                    # the HEAD-based worktree index would be clean.
                    with observer.private_environment(repo.parent / "staged-private-home"):
                        env = local_read_git_env()
                        command = ["git", "--no-lazy-fetch", "-C", str(repo)]
                        blob = subprocess.run([*command, "rev-parse", "HEAD:core/pysrc/helper.py"], env=env, capture_output=True, check=True, timeout=15).stdout.decode().strip()
                        subprocess.run([*command, "update-index", "--cacheinfo", "100644", blob, "plugins/ca/tools/.env.example"], env=env, check=True, capture_output=True, timeout=15)
                        staged = retained_index()
                        self.assertFalse(reports.source_identity(repo)["clean"])
                        self.assertEqual(retained_index(), staged)
                    self.assertEqual({name: (repo / name).read_bytes() for name in before_bytes}, before_bytes)



class RuntimeSnapshotAliasTests(unittest.TestCase):
    def test_runtime_snapshot_hashes_canonical_bytes_for_runtime_aliases(self):
        import retained_archive_cli_observation as owner
        with tempfile.TemporaryDirectory(prefix="ca-runtime-alias-") as temporary:
            root = Path(temporary).resolve()
            python, git = root / "python-target", root / "git-target"
            python.write_bytes(b"inert Python runtime identity fixture\n")
            git.write_bytes(b"inert Git runtime identity fixture\n")
            alias = root / "runtime-alias"
            expected = {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                        for name, path in (("python", python), ("git", git))}
            original = {str(path): path.read_bytes() for path in (python, git)}
            for role, target in (("python", python), ("git", git)):
                with self.subTest(role=role):
                    try:
                        alias.symlink_to(target)
                    except OSError as error:
                        self.skipTest("owned file symlink unavailable: " + str(getattr(error, "winerror", error.errno)))
                    self.assertTrue(alias.is_symlink())
                    self.assertEqual(alias.resolve(strict=True), target)
                    try:
                        with mock.patch.object(owner.sys, "executable", str(alias if role == "python" else python)), \
                             mock.patch.object(owner.shutil, "which", return_value=str(alias if role == "git" else git)):
                            try:
                                observed = owner._runtime_snapshot()
                            except ValueError as error:
                                self.fail("A runtime alias must hash its recorded canonical target: " + str(error))
                        self.assertEqual(observed, expected)
                    finally:
                        self.assertEqual({str(path): path.read_bytes() for path in (python, git)}, original)
                        self.assertTrue(alias.is_symlink())
                        self.assertEqual(alias.resolve(strict=True), target)
                        alias.unlink()

    def test_runtime_snapshot_preserves_regular_input_and_size_guards(self):
        import retained_archive_cli_observation as owner
        with tempfile.TemporaryDirectory(prefix="ca-runtime-guards-") as temporary:
            root = Path(temporary).resolve()
            ordinary = root / "ordinary"
            ordinary.write_bytes(b"inert runtime fixture\n")
            directory = root / "not-a-file"
            directory.mkdir()
            oversized = root / "too-large"
            with oversized.open("wb") as stream:
                stream.truncate(64 * 1024 * 1024 + 1)
            for role in ("python", "git"):
                for invalid in (directory, oversized):
                    with self.subTest(role=role, invalid=invalid.name), \
                         mock.patch.object(owner.sys, "executable", str(invalid if role == "python" else ordinary)), \
                         mock.patch.object(owner.shutil, "which", return_value=str(invalid if role == "git" else ordinary)):
                        with self.assertRaisesRegex(ValueError, "bounded regular observer input required"):
                            owner._runtime_snapshot()
            alias = root / "input-link"
            try:
                alias.symlink_to(ordinary)
            except OSError as error:
                self.skipTest("owned file symlink unavailable: " + str(getattr(error, "winerror", error.errno)))
            with self.assertRaisesRegex(ValueError, "bounded regular observer input required"):
                owner.regular_bytes(alias)
            self.assertEqual(ordinary.read_bytes(), b"inert runtime fixture\n")
            self.assertEqual(oversized.stat().st_size, 64 * 1024 * 1024 + 1)

if __name__ == "__main__": unittest.main(verbosity=2)
