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


def fixture():
    source, tree, run, job = "a" * 40, "b" * 40, 7, 9
    digest = lambda b: hashlib.sha256(b).hexdigest()
    text = lambda v: json.dumps(v, sort_keys=True)
    binary, bridge = "c" * 64, "d" * 64
    manifest = {"format":"codearbiter.artifact-release/0.1.0", "version": "0.1.0", "protocol": "codearbiter.artifact-api/0.1.0", "schema_version": "0.3.2",
                "binaries": {"windows/amd64": {"file": "ca-artifact-windows-amd64.exe", "sha256": binary, "native_tested": True}}}
    manifest["context_qualification"] = {"windows/amd64": {"source_commit":source, "workflow":".github/workflows/ci.yml", "run_id":str(run), "binary_sha256":binary, "observation_sha256":"9"*64, "module_sha256":"0"*64, "native_cases":["TestContextBoundedRender","TestContextDocumentContract","TestContextMarkdownPreservation","TestContextMutationAdmission","TestContextRecoveryAndPaths","TestContextRepresentationBoundary"]}}
    mr = text(manifest)
    promotion = {"format": "codearbiter.artifact-promotion/0.1.0", "source_commit": source,
                 "workflow": ".github/workflows/ci.yml", "run_id": str(run),
                 "version": "0.1.0", "protocol": manifest["protocol"], "schema_version": "0.3.2",
                 "hosts": {"claude": "plugins/ca/helpers/artifacts", "codex": "plugins/ca-codex/helpers/artifacts", "pi": "plugins/ca-pi/helpers/artifacts"},
                 "qualifications": {"windows/amd64": {"binary_sha256": binary}}}
    pr = text(promotion)
    package_members = {"plugins/ca/helpers/artifacts/release.json": {"sha256": digest(mr.encode())},
                       "plugins/ca/helpers/artifacts/ca-artifact-windows-amd64.exe": {"sha256": binary},
                       "plugins/ca/hooks/_artifactlib.py": {"sha256": bridge}}
    package = {"file": "claude.tar.gz", "sha256": "e" * 64, "members": package_members}
    cohort = {"format": "codearbiter.artifact-package-cohort/0.1.0", "source_commit": source, "source_tree": tree,
              "workflow": ".github/workflows/ci.yml", "run_id": str(run), "promotion_receipt_sha256": digest(pr.encode()),
              "artifact_version": "0.1.0", "protocol": manifest["protocol"], "schema_version": "0.3.2",
              "pi_packer": {"qualification": "production"}, "packages": {"claude": package, "codex": {}, "pi": {}}}
    cr = text(cohort)
    receipt = {"format": "codearbiter.artifact-cold-execution/0.3.0", "source_commit": source,
        "workflow": ".github/workflows/ci.yml", "run_id": str(run), "job": "artifact-package-cold", "host": "claude",
        "platform": "windows/amd64", "promotion_receipt_sha256": digest(pr.encode()), "package_sha256": package["sha256"],
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
                {"path": "plugins/ca/helpers/artifacts/ca-artifact-windows-amd64.exe", "sha256": binary}]}}
    consumed = {role: {"artifact_name": name, **payloads[name]} for role, name in (("promoted-stage", stage_name), ("release-packages", packages_name))}
    source_stamp = {"repository":"C:/repo", "source_commit": source, "source_tree": tree, "clean": True,
                    "inputs": {"tools/build-host-packages.py": "6" * 64}, "core_python_members": ["_artifactlib.py"],
                    "host_lookup": {"path": "core/pysrc/_host.py", "path_style": "windows", "present": False}}
    runtime = {"python": {"path": "C:/Python/python.exe", "sha256": "7" * 64},
               "git": {"path": "C:/Git/git.exe", "sha256": "8" * 64}}
    payload_stamp = {role: {"root":"C:/stage" if role=="promoted-stage" else "C:/packages", "members":{m["path"]: m["sha256"] for m in consumed[role]["members"]}} for role in consumed}
    binding = {"format": "codearbiter.installed-observation-binding/1", "profile": "retained-cold-package-v1",
        "source_commit": source, "source_tree": tree, "workflow": ".github/workflows/ci.yml", "ci_run_id": run, "producer_job_id": job,
        "host": "claude", "platform": "windows/amd64", "consumed_payloads": consumed,
        "cohort_sha256": digest(cr.encode()), "promotion_receipt_sha256": digest(pr.encode()),
        "documents": {"cohort": {"path": "artifact-package-cohort.json", "json_utf8": cr},
                      "promotion": {"path": "artifact-promotion.json", "json_utf8": pr},
                      "manifest": {"path": "plugins/ca/helpers/artifacts/release.json", "json_utf8": mr}},
        "cold_receipt": receipt, "source_before": source_stamp, "source_after": copy.deepcopy(source_stamp),
        "runtime_before": runtime, "runtime_after": copy.deepcopy(runtime),
        "payload_before": payload_stamp, "payload_after": copy.deepcopy(payload_stamp)}
    tests = [{"id": "cli:tools/build-host-packages.py:cold:claude:windows/amd64", "result": "passed"}]
    tests += [{"id": "receipt:.github/scripts/test_context_installed.py:" + t["name"], "result": "passed"} for t in receipt["context_installed_tests"]]
    req = {"source_commit": source, "source_tree": tree, "ci_run_id": run,
           "cells": ["installed:claude:workflow"], "cell_jobs": {"installed:claude:workflow": "cold owning job"}}
    observation = {"format": "codearbiter.major-test-observation/1", "source_commit": source, "source_tree": tree,
        "ci_run_id": run, "source_stable": True, "proof_kind": "retained-archive-cli", "producer": "retained-cold-package-observer-v1",
        "argv": ["C:/Python/python.exe", "-I", "-B", "C:/repo/tools/build-host-packages.py",
            "--release-package-stage", "C:/stage", "--cold-package-root", "C:/packages", "--source-repo", "C:/repo",
            "--cold-host", "claude", "--cold-platform", "windows/amd64", "--trusted-source-commit", source,
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
        self.assertEqual(value["installed_cells"], ["installed:claude:workflow"])

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


if __name__ == "__main__": unittest.main(verbosity=2)
