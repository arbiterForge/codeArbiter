"""Real-run and refusal contracts for Q-02's named selection reports."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

import major_qualification_report as owner
from _git_fixture_diagnostics import run_git_phase


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.cell = "disposition:transitions:N09:04"
        self.req = {"source_commit": "a" * 40, "source_tree": "b" * 40, "ci_run_id": 7,
                    "cells": [self.cell], "cell_jobs": {self.cell: "owning native job"}}
        self.map = {"schema": owner.SELECTIONS, "groups": [{"id": "progress", "job": "owning native job",
                    "payload_name": "candidate", "observation": "native", "proof_kind": "native-module",
                    "selectors": ["go:package:TestPreservesProgress"], "cells": [self.cell],
                    "scope": "Block preserves downstream recorded progress; not all lifecycle transitions."}]}
        self.observation = {"format": owner.OBSERVATION, "source_commit": "a" * 40, "source_tree": "b" * 40,
                            "ci_run_id": 7, "source_stable": True, "proof_kind": "native-module",
                            "argv": ["python", "tools/go_test_parallel.py"], "exit_code": 0,
                            "tests": [{"id": "go:package:TestPreservesProgress", "result": "passed"}]}
        self.binding = {"format": owner.native_binding_owner.FORMAT, "source_commit": "a" * 40,
                        "run_id": "7", "run_attempt": "1", "workflow": ".github/workflows/ci.yml",
                        "producer_job": "artifact-native-build", "platform": "windows/amd64", "toolchain": "go1.27.1",
                        "module_sha256": "f" * 64, "go_sha256": "e" * 64,
                        "manifest_sha256": "d" * 64, "binary_sha256": "c" * 64}
        self.observation.update(producer="go-named-ci20-join", native_binding=self.binding)
        self.payload = {"artifact_id": 8, "archive_sha256": "c" * 64,
                        "members": [{"path": "candidate.exe", "sha256": "d" * 64}],
                        "native_bindings": [self.binding]}

    def build(self):
        return owner.build_report(self.req, job_name="owning native job", job_id=9,
                                  selections=self.map, observations={"native": self.observation},
                                  payloads={"candidate": self.payload})

    def test_one_actual_named_test_can_substantiate_explicit_semantic_rows_without_reexecution(self):
        self.req["cells"].append("disposition:transitions:N11:03")
        self.req["cell_jobs"][self.req["cells"][-1]] = "owning native job"
        self.map["groups"][0]["cells"].append(self.req["cells"][-1])
        result = self.build()
        self.assertEqual(len(result["results"]), 2)
        self.assertTrue(all(r["selected_population"] == r["executed_population"] == 1 for r in result["results"]))

    def test_real_largest_owner_population_and_overlay_inventory_fit_retained_report_bound(self):
        # Capacity fixture only: use the real frozen owner population and the
        # packager's outer member paths, never turn these synthetic outcomes
        # into qualification evidence or a semantic selection map.
        repo = Path(owner.__file__).resolve().parents[2]
        corpus = repo / "docs/state-contracts-major/contracts"
        tasks = json.loads((corpus / "tasks.json").read_text())["tasks"]
        owners = {t["id"]: t["owner"] for t in tasks}
        cells = ["task:" + t["id"] for t in tasks if t["owner"] == "hooks-workflows"
                 and t["required_before_publication"] and t["id"] != "Q-03"]
        for filename, collection, key, group in (
            ("finding-dispositions.json", "records", "finding_id", "findings"),
            ("machine-coverage.json", "machines", "machine_id", "machines"),
            ("transition-coverage.json", "transitions", "transition_id", "transitions"),
        ):
            for row in json.loads((corpus / filename).read_text())[collection]:
                if (row.get("owner") or owners[row["task_ids"][0]]) == "hooks-workflows":
                    cells.append("disposition:" + group + ":" + row[key])
        self.assertEqual(len(cells), 895)
        hosts = json.loads((repo / "core/hosts.json").read_text())["hosts"]
        files = ["release.json"] + ["ca-artifact-" + p + (".exe" if p.startswith("windows") else "")
            for p in ("darwin-amd64", "darwin-arm64", "linux-amd64", "linux-arm64", "windows-amd64", "windows-arm64")]
        members = [{"path": h["plugin_dir"] + "/helpers/artifacts/" + name, "sha256": "d" * 64}
                   for h in hosts for name in files] + [{"path": "artifact-promotion.json", "sha256": "e" * 64}]
        self.assertEqual(len(members), 22)
        self.req.update(cells=cells, cell_jobs={cell: "owning native job" for cell in cells})
        self.map["groups"][0].update(cells=cells, proof_kind="native-module")
        self.observation.update(proof_kind="native-module", producer="go-named-ci20-join",
            argv=["C:/Python314/python.exe", "tools/go_test_parallel.py", "--module", "core/artifacts"])
        self.payload["members"] = members
        result = self.build()
        encoded = json.dumps(result, indent=2).encode()
        self.assertLess(len(encoded), 4 * 1024 * 1024)
        self.assertEqual(len(result["results"]), len(cells))
        self.assertEqual(result["payloads"], [{"artifact_id": 8, "archive_sha256": "c" * 64, "members": members}])
        self.assertTrue(all("payload_members" not in row for row in result["results"]))

    def test_skip_failure_missing_duplicate_and_unknown_outcomes_refuse(self):
        for state in ("failed", "skipped", "unknown", "expected-failure"):
            with self.subTest(state=state):
                self.observation["tests"][0]["result"] = state
                with self.assertRaisesRegex(ValueError, "named test"):
                    self.build()
        self.observation["tests"] = []
        with self.assertRaisesRegex(ValueError, "named test"):
            self.build()
        self.observation["tests"] = [{"id": "go:package:TestPreservesProgress", "result": "passed"}] * 2
        with self.assertRaisesRegex(ValueError, "named test"):
            self.build()

    def test_stale_source_run_drift_exit_and_proof_kind_refuse(self):
        original = copy.deepcopy(self.observation)
        for key, value in (("source_commit", "e" * 40), ("source_tree", "e" * 40), ("ci_run_id", 8),
                           ("source_stable", False), ("exit_code", 1), ("exit_code", False),
                           ("proof_kind", "source-test")):
            with self.subTest(key=key):
                self.observation = dict(original, **{key: value})
                with self.assertRaises(ValueError):
                    self.build()

    def test_unmapped_or_extra_cells_do_not_inherit_suite_success(self):
        self.map["groups"][0]["cells"] = ["task:NT-09"]
        with self.assertRaisesRegex(ValueError, "mapping"):
            self.build()

    def test_source_only_tests_cannot_qualify_installed_upstream_hosts(self):
        self.req["cells"] = ["installed:pi:windows:1.5.0"]
        self.req["cell_jobs"] = {self.req["cells"][0]: "owning native job"}
        self.map["groups"][0]["cells"] = self.req["cells"][:]
        with self.assertRaisesRegex(ValueError, "upstream host"):
            self.build()
        self.map["groups"][0]["proof_kind"] = self.observation["proof_kind"] = "source-test"
        with self.assertRaisesRegex(ValueError, "installed hosts"):
            self.build()

    def test_source_native_module_cannot_qualify_installed_native_cell(self):
        cell = "installed:native:windows:amd64"
        self.req["cells"] = [cell]
        self.req["cell_jobs"] = {cell: "owning native job"}
        self.map["groups"][0]["cells"] = [cell]
        with self.assertRaisesRegex(ValueError, "installed"):
            self.build()

    def test_changing_a_proof_kind_string_does_not_create_an_installed_observer(self):
        self.req["cells"] = ["installed:claude:workflow"]
        self.req["cell_jobs"] = {self.req["cells"][0]: "owning native job"}
        self.map["groups"][0]["cells"] = self.req["cells"][:]
        self.map["groups"][0]["proof_kind"] = self.observation["proof_kind"] = "live-host"
        with self.assertRaisesRegex(ValueError, "qualified observer"):
            self.build()

    def test_native_test_outcomes_must_join_the_original_consumed_payload_stamp(self):
        self.observation["native_binding"] = {"binary_sha256": "e" * 64}
        with self.assertRaisesRegex(ValueError, "native.*payload"):
            self.build()

    def test_payload_names_cannot_alias_one_artifact_id_to_different_consumed_bytes(self):
        other = "disposition:transitions:N11:03"
        self.req["cells"].append(other)
        self.req["cell_jobs"][other] = "owning native job"
        group = dict(self.map["groups"][0], id="other", cells=[other], payload_name="other-payload")
        self.map["groups"].append(group)
        changed = copy.deepcopy(self.payload)
        changed["members"][0]["sha256"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "conflicting consumed bytes"):
            owner.build_report(self.req, job_name="owning native job", job_id=9,
                               selections=self.map, observations={"native": self.observation},
                               payloads={"candidate": self.payload, "other-payload": changed})

    def test_native_admission_preserves_skips_and_checks_actual_membership_and_input_stamp(self):
        record = {"format": "codearbiter.go-test-observation/1", "complete": True,
                  "module_sha256_before": "f" * 64, "module_sha256_after": "f" * 64,
                  "argv": ["python", "tools/go_test_parallel.py"],
                  "selected": [{"package": "p", "test": "TestA"}, {"package": "p", "test": "TestB"}],
                  "observed": [{"package": "p", "test": "TestA", "result": "pass"},
                               {"package": "p", "test": "TestB", "result": "skip"}]}
        binding = self.binding
        value = owner.admit_go(record, binding, "b" * 40)
        self.assertEqual(value["tests"][1]["result"], "skipped")
        for field, replacement in (("module_sha256_after", "e" * 64), ("complete", False),
                                   ("observed", record["observed"][:1]),
                                   ("selected", record["selected"] * 2)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                owner.admit_go(dict(record, **{field: replacement}), binding, "b" * 40)

    def test_vitest_admission_uses_actual_names_and_never_counts_pending_as_passed(self):
        before = {"source_commit": "a" * 40, "source_tree": "b" * 40, "clean": True}
        raw = {"testResults": [{"name": str(Path.cwd() / "a.test.ts"), "assertionResults": [
            {"fullName": "fault keeps unrelated work", "status": "passed"},
            {"fullName": "Docker real worker", "status": "pending"}]}]}
        value = owner.admit_vitest(raw, repo=Path.cwd(), before=before, after=before,
                                  argv=["npm", "test"], exit_code=0, run_id=7)
        self.assertEqual([r["result"] for r in value["tests"]], ["passed", "skipped"])
        self.assertIn("fault keeps unrelated work", value["tests"][0]["id"])

    def test_payload_requires_original_archive_bytes_and_actual_consumed_member_equality(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            archive.writestr("candidate/binary", b"actual binary")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "candidate").mkdir()
            (root / "candidate/binary").write_bytes(b"actual binary")
            with mock.patch.object(owner.readiness, "artifact_bytes", return_value=raw.getvalue()):
                value = owner.authenticated_payload({"id": 8}, self.req, root)
                self.assertEqual(value["artifact_id"], 8)
                (root / "candidate/binary").write_bytes(b"different binary")
                with self.assertRaisesRegex(ValueError, "differs"):
                    owner.authenticated_payload({"id": 8}, self.req, root)


class SourceIdentityTest(unittest.TestCase):
    def test_only_exact_untracked_ordinary_empty_native_read_lock_is_nonsource_metadata(self):
        with tempfile.TemporaryDirectory(prefix="ca-observer-source-identity-") as temp:
            repo = Path(temp).resolve()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            source = repo / "source.py"
            source.write_text("# original\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                            "commit", "-qm", "source fixture"], check=True)
            original = owner.source_identity(repo)
            lock = repo / ".codearbiter/.artifacts/store.lock"
            lock.parent.mkdir(parents=True)
            lock.write_bytes(b"")
            self.assertEqual(owner.source_identity(repo), original)
            other = lock.parent / "unrecognized.json"
            other.write_text("{}", encoding="utf-8")
            self.assertFalse(owner.source_identity(repo)["clean"])
            other.unlink()
            lock.write_bytes(b"not native lock contents")
            self.assertFalse(owner.source_identity(repo)["clean"])
            lock.write_bytes(b"")
            source.write_text("# changed source\n", encoding="utf-8")
            self.assertFalse(owner.source_identity(repo)["clean"])
            source.write_text("# original\n", encoding="utf-8")
            with mock.patch.object(Path, "is_symlink", return_value=True):
                self.assertFalse(owner.ordinary_native_read_lock(repo))
            reparse = SimpleNamespace(st_mode=owner.stat.S_IFDIR, st_file_attributes=owner.stat.FILE_ATTRIBUTE_REPARSE_POINT)
            with mock.patch.object(Path, "lstat", return_value=reparse):
                self.assertFalse(owner.ordinary_native_read_lock(repo))
            alias = repo / "lock-alias"
            os.link(lock, alias)
            self.assertFalse(owner.ordinary_native_read_lock(repo))
            alias.unlink()
            subprocess.run(["git", "-C", str(repo), "add", str(lock)], check=True)
            self.assertFalse(owner.source_identity(repo)["clean"])
            lock.unlink()
            self.assertFalse(owner.source_identity(repo)["clean"])
            self.assertFalse(owner.ordinary_native_read_lock(repo))


class ActualPythonObserverTest(unittest.TestCase):
    def test_actual_native_read_creates_only_owned_lock_without_invalidating_source(self):
        from test_artifact_authoring import build_installation
        installation_owner, installation = build_installation()
        self.addCleanup(installation_owner.cleanup)
        source = Path(owner.__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix="ca-observer-native-read-") as temp:
            base = Path(temp).resolve()
            repo = base / "repo"
            (repo / ".codearbiter/context").mkdir(parents=True)
            shutil.copyfile(source / ".codearbiter/context/tech-stack.html", repo / ".codearbiter/context/tech-stack.html")
            shutil.copyfile(source / ".codearbiter/CONTEXT.md", repo / ".codearbiter/CONTEXT.md")
            script = repo / "read_context.py"
            script.write_text("import unittest,sys,pathlib\n"
                f"sys.path.insert(0,{str(source / 'core/pysrc')!r})\n"
                "from _artifactlib import ArtifactClient\n"
                "class ReadContext(unittest.TestCase):\n"
                " def test_read_current_identity(self):\n"
                f"  value=ArtifactClient(pathlib.Path.cwd(),pathlib.Path({str(installation)!r})).call('identity',{{'artifact_id':'CTX-TECH-STACK'}})\n"
                "  self.assertEqual(value['artifact_id'],'CTX-TECH-STACK')\n"
                "if __name__=='__main__': unittest.main()\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                            "commit", "-qm", "native read fixture"], check=True)
            before = owner.source_identity(repo)
            output = base / "observation.json"
            result = subprocess.run([sys.executable, str(Path(owner.__file__).resolve()), "observe-python", "--repo", str(repo),
                "--output", str(output), "--", "read_context.py"], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            record = owner.load_json(output)
            self.assertEqual(record["tests"][0]["result"], "passed")
            self.assertTrue(record["source_stable"])
            self.assertEqual(before, owner.source_identity(repo))
            lock = repo / ".codearbiter/.artifacts/store.lock"
            status = subprocess.check_output(
                ["git", "-C", str(repo), "status", "--porcelain=v1", "--untracked-files=all"], text=True)
            if sys.platform == "linux":
                # Linux takes flock on the anchored repository directory and
                # needs no metadata file; assert the stronger no-write result.
                self.assertFalse(lock.exists())
                self.assertEqual(status, "")
            else:
                self.assertEqual(lock.read_bytes(), b"")
                self.assertEqual(status.strip(), "?? .codearbiter/.artifacts/store.lock")

    def test_vitest_protocol_wrapper_invokes_one_original_process_and_retains_its_named_json(self):
        with tempfile.TemporaryDirectory(prefix="ca-vitest-observer-") as temp:
            base = Path(temp)
            repo = base / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            counter, raw, output = (base / name for name in ("runs.txt", "vitest.json", "observation.json"))
            # A protocol fixture, explicitly not a live Vitest or host claim.
            script = repo / "stub.py"
            named_json = json.dumps({'testResults': [{'name': str(repo / 'sample.test.ts'), 'assertionResults': [
                {'fullName': 'preserves unrelated work', 'status': 'passed'}]}]})
            script.write_text("import pathlib,json,sys\n"
                              f"p=pathlib.Path({str(counter)!r});p.write_text(p.read_text()+'x' if p.exists() else 'x')\n"
                              "out=pathlib.Path(next(a.split('=',1)[1] for a in sys.argv if a.startswith('--outputFile=')))\n"
                              f"out.write_text({named_json!r})\n",
                              encoding="utf-8")
            (repo / "sample.test.ts").write_text("// protocol fixture\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "stub.py", "sample.test.ts"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                            "commit", "-qm", "fixture"], check=True)
            command = [sys.executable, str(Path(owner.__file__).resolve()), "observe-vitest", "--repo", str(repo),
                       "--output", str(output), "--raw-results", str(raw), "--", sys.executable, str(script)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            value = owner.load_json(output)
            self.assertTrue(value["source_stable"])
            self.assertEqual(value["tests"], [{"id": "vitest:sample.test.ts:preserves unrelated work", "result": "passed"}])
            self.assertEqual(counter.read_text(), "x")
            refused = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(counter.read_text(), "x")

    def test_original_entrypoint_executes_once_and_named_skip_failure_and_subtest_are_observed(self):
        with tempfile.TemporaryDirectory(prefix="ca-observer-") as temp:
            base = Path(temp)
            repo = base / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            script = repo / "cases.py"
            counter = base / "runs.txt"
            script.write_text("import unittest, pathlib\n"
                              f"p=pathlib.Path({str(counter)!r});p.write_text(p.read_text()+'x' if p.exists() else 'x')\n"
                              "class Cases(unittest.TestCase):\n"
                              " def test_pass(self): self.assertTrue(True)\n"
                              " @unittest.skip('unsupported platform')\n"
                              " def test_skip(self): pass\n"
                              " def test_subtest_failure(self):\n"
                              "  with self.subTest('negative'): self.fail('actual failure')\n"
                              "if __name__=='__main__': unittest.main()\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "cases.py"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                            "commit", "-qm", "fixture"], check=True)
            output = base / "observation.json"
            result = subprocess.run([sys.executable, str(Path(owner.__file__).resolve()), "observe-python",
                                     "--repo", str(repo), "--output", str(output), "--", "cases.py"],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(counter.read_text(), "x")
            value = owner.load_json(output)
            self.assertTrue(value["source_stable"])
            self.assertEqual({r["id"].rsplit(".", 1)[-1]: r["result"] for r in value["tests"]},
                             {"test_pass": "passed", "test_skip": "skipped", "test_subtest_failure": "failed"})
            self.assertEqual(value["exit_code"], 1)
            original = output.read_bytes()
            refused = subprocess.run(result.args, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(counter.read_text(), "x")



class RetainedColdReportTest(unittest.TestCase):
    def test_only_explicit_source_bound_package_placeholder_is_rendered(self):
        from test_retained_archive_cli_observation import fixture
        req,selection,observed,payloads=fixture()
        selection["groups"][0]["payload_name"]="artifact-release-packages-{source_commit}"
        report=owner.build_report(req,job_name="cold owning job",job_id=9,selections=selection,observations={"cold":observed},payloads=payloads)
        self.assertEqual(report["results"][0]["payload_artifact_ids"],[8,10])
        selection["groups"][0]["payload_name"]="arbitrary-{source_commit}"
        with self.assertRaises(ValueError):owner.build_report(req,job_name="cold owning job",job_id=9,selections=selection,observations={"cold":observed},payloads=payloads)

    def test_emission_accepts_only_normal_main_or_program_push(self):
        import os
        env={"GITHUB_ACTIONS":"true","GITHUB_REPOSITORY":owner.readiness.REPOSITORY,"GITHUB_EVENT_NAME":"push","GITHUB_REF":"refs/heads/major/state-contracts"}
        with mock.patch.dict(os.environ,env,clear=True):owner.validate_emitter_environment()
        for key,value in [("GITHUB_REF","refs/heads/topic"),("GITHUB_EVENT_NAME","pull_request"),("GITHUB_REPOSITORY","fork/codeArbiter"),("GITHUB_ACTIONS","false")]:
            with self.subTest(key=key),mock.patch.dict(os.environ,{**env,key:value},clear=True),self.assertRaises(ValueError):owner.validate_emitter_environment()

    def test_valid_closed_installed_observer_retains_both_distinct_original_payloads(self):
        from test_retained_archive_cli_observation import fixture
        req, selection, observed, payloads = fixture()
        report = owner.build_report(req, job_name="cold owning job", job_id=9,
            selections=selection, observations={"cold": observed}, payloads=payloads)
        self.assertEqual(report["schema"], "codearbiter-major-qualification/3")
        self.assertEqual(report["results"][0]["payload_artifact_ids"], [8, 10])
        self.assertEqual({p["artifact_id"] for p in report["payloads"]}, {8, 10})
        self.assertNotIn("payload_artifact_id", report["results"][0])

    def test_cold_profile_never_qualifies_versioned_hosts_or_docker(self):
        from test_retained_archive_cli_observation import fixture
        for cell in ["installed:pi:windows:1.5.0", "installed:codex:0.145.0", "installed:sandbox:docker"]:
            req, selection, observed, payloads = fixture()
            req["cells"] = [cell];req["cell_jobs"] = {cell:"cold owning job"};selection["groups"][0]["cells"]=[cell]
            with self.subTest(cell=cell), self.assertRaises(ValueError):
                owner.build_report(req, job_name="cold owning job", job_id=9,
                    selections=selection, observations={"cold":observed}, payloads=payloads)

class CanonicalNativeWholeClauseMapTest(unittest.TestCase):
    """Unit fixtures test declarations, never supply hosted qualification evidence."""

    def native_case(self):
        import hashlib
        root = Path(owner.__file__).resolve().parents[2]
        proof_bytes = (root / "docs/state-contracts-major/execution/evidence/native-M94-R43599120794/native-go120-hosted.json").read_bytes()
        self.assertEqual(hashlib.sha256(proof_bytes).hexdigest(),
                         "765e7310413276e52c9370250ee7897d4f0c5ada399bea1e3e9a3e9258b321e4")
        proof = json.loads(proof_bytes)
        groups = {group["id"]: group for group in proof["semantic_groups"]}
        expected = {}
        for group in groups.values():
            for cell in group.get("transition_cells", group.get("disposition_ids", [])):
                expected.setdefault(cell, set()).update(item["id"] for item in group["selectors"])
        for override in proof["semantic_mapping"]:
            expected[override["cell"]] = {item["id"] for item in override["original_named_results"]}
        # Current D-PROGRESS tests are stronger than the retained dependent group.
        expected["disposition:transitions:N09:04"].update(
            "go:github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations:" + name
            for name in ("TestNT09TaskBlockPreservesDependentRecordedProgress",
                         "TestNT09PreservedProgressKeepsDependencyReadinessIndependent",
                         "TestNT09BlockingDependencyPreservesEveryRecordedProgressLabel"))
        for cell, composition in proof["machine_compositions"].items():
            expected[cell] = set().union(*(expected["disposition:transitions:" + transition]
                                          for transition in composition["transition_ids"]))
        for cell, group_ids in proof["finding_groups"].items():
            expected[cell] = {item["id"] for group_id in group_ids
                              for item in groups[group_id]["selectors"]}
        self.assertEqual(set(expected), set(proof["disposition_ids"]))
        # Its positive export journey is mixed-schema, not these two Go CAS tests.
        del expected["disposition:transitions:N27:03"]
        supported = {'disposition:transitions:N02:06', 'disposition:transitions:N09:04', 'disposition:transitions:N39:02', 'disposition:transitions:N36:02', 'disposition:transitions:N39:03', 'disposition:transitions:N14:01', 'disposition:machines:N39', 'disposition:transitions:N12:02', 'disposition:transitions:N29:07', 'disposition:findings:N-F06', 'disposition:transitions:N14:03', 'disposition:transitions:N39:01', 'disposition:transitions:N02:08', 'disposition:transitions:N02:07', 'disposition:transitions:N36:01', 'disposition:transitions:N01:06'}
        expected = {cell: selectors for cell, selectors in expected.items() if cell in supported}
        self.assertEqual(set(expected), supported)
        self.assertEqual(len(expected), 16)
        selections = json.loads((root / ".github/major-test-selections.json").read_text())
        policy = json.loads((root / ".github/major-qualification-policy.json").read_text())
        job = "[CHECK] | [CORE] | Tested native candidate build <windows/amd64>"
        all_cells = set(expected) | set(policy["cell_job_bindings"]) | {
            "disposition:transitions:N27:03", "task:NT-10"}
        unresolved = {cell: "major qualification / native" for cell in all_cells}
        cell_jobs = owner.readiness.bind_named_jobs(unresolved, policy)
        ReportTest.setUp(self)
        self.req.update(cells=sorted(expected), cell_jobs=cell_jobs)
        selectors = set().union(*expected.values())
        self.observation["tests"] = [{"id": selector, "result": "passed"} for selector in sorted(selectors)]
        observations = {"native-module": self.observation}
        payloads = {"ci20-native-tested-windows-2025": self.payload}
        return expected, selections, job, observations, payloads

    def test_canonical_native_map_uses_reconciled_per_cell_named_evidence(self):
        expected, selections, job, observations, payloads = self.native_case()
        # Call the maintained routing and emitter, not a reconstructed reporting model.
        report = owner.build_report(self.req, job_name=job, job_id=9, selections=selections,
                                    observations=observations, payloads=payloads)
        self.assertEqual({row["cell"] for row in report["results"]}, set(expected),
                         "canonical semantic/job map must cover exactly the complete 16 native cells")
        declared = {cell for group in selections["groups"] if group["job"] == job for cell in group["cells"]}
        self.assertEqual(declared, set(expected), "partial historical scopes cannot become extra whole-cell reports")
        self.assertNotEqual(self.req["cell_jobs"]["disposition:transitions:N27:03"], job)
        self.assertNotEqual(self.req["cell_jobs"]["task:NT-10"], job)
        for cell, selectors in expected.items():
            selected = [group for group in selections["groups"] if cell in group["cells"]]
            with self.subTest(cell=cell):
                self.assertEqual({selector for group in selected for selector in group["selectors"]}, selectors)
                self.assertTrue(all(group["job"] == job and group["observation"] == "native-module"
                                    and group["proof_kind"] == "native-module"
                                    and group["payload_name"] == "ci20-native-tested-windows-2025"
                                    for group in selected))
                row = next(row for row in report["results"] if row["cell"] == cell)
                self.assertEqual((row["selected_population"], row["executed_population"]),
                                 (len(selectors), len(selectors)))

    def test_canonical_native_map_refuses_incomplete_or_unbound_original_evidence(self):
        expected, selections, job, observations, payloads = self.native_case()
        chosen = ["TestNT09PreservedProgressKeepsDependencyReadinessIndependent",
                  "TestNT01JournalOutcomeCodesStayDistinct", "TestSMARTSDecisionStrongRefusedWithCriticalUnknown"]
        for name in chosen:
            selector = next(selector for values in expected.values() for selector in values
                            if selector.endswith(":" + name))
            for failure in ("missing", "skipped", "failed", "repeated"):
                broken = copy.deepcopy(observations)
                tests = broken["native-module"]["tests"]
                test = next(test for test in tests if test["id"] == selector)
                if failure == "missing":
                    tests.remove(test)
                elif failure == "repeated":
                    tests.append(dict(test))
                else:
                    test["result"] = failure
                with self.subTest(selector=name, failure=failure), self.assertRaisesRegex(
                        ValueError, "selected named test missing, repeated, skipped or failed"):
                    owner.build_report(self.req, job_name=job, job_id=9, selections=selections,
                                       observations=broken, payloads=payloads)
        for failure in ("source", "payload"):
            broken, consumed = copy.deepcopy(observations), copy.deepcopy(payloads)
            if failure == "source":
                broken["native-module"]["source_commit"] = "e" * 40
            else:
                consumed["ci20-native-tested-windows-2025"]["native_bindings"] = []
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                owner.build_report(self.req, job_name=job, job_id=9, selections=selections,
                                   observations=broken, payloads=consumed)


    def test_canonical_map_cannot_erase_explicit_platform_or_behavior_limits(self):
        root = Path(owner.__file__).resolve().parents[2]
        transitions = json.loads((root / "docs/state-contracts-major/contracts/transition-coverage.json").read_text())["transitions"]
        clause = next(row["baseline"] for row in transitions if row["transition_id"] == "N01:03")
        # This exclusion follows the actual frozen effects plus compiled test source.
        for branch in ("Windows", "Linux", "Darwin"):
            self.assertIn(branch, clause["effects"])
        windows_test = (root / "core/artifacts/internal/operations/read_only_windows_test.go").read_text()
        self.assertTrue(windows_test.startswith("//go:build windows\n"))
        self.assertIn('fault.Code(err) != "NO_LOCAL_STORE"', windows_test)
        proof = json.loads((root / "docs/state-contracts-major/execution/evidence/native-M94-R43599120794/native-go120-hosted.json").read_text())
        limitation = next(row["limits"] for row in proof["semantic_mapping"] if row["cell"] == "disposition:transitions:N01:03")
        self.assertIn("Linux no-metadata and Darwin lock-file behavior remain unexecuted/pending", limitation)
        selections = json.loads((root / ".github/major-test-selections.json").read_text())
        policy = json.loads((root / ".github/major-qualification-policy.json").read_text())
        prohibited = {"disposition:transitions:N01:03", "disposition:transitions:N01:05",
                      "disposition:transitions:N27:03", "disposition:transitions:N38:04",
                      "disposition:transitions:N38:05", "disposition:machines:N14"}
        job = "[CHECK] | [CORE] | Tested native candidate build <windows/amd64>"
        mapped = {cell for group in selections["groups"] if group["job"] == job for cell in group["cells"]}
        self.assertFalse(mapped & prohibited, "scoped observations cannot discard frozen branch/behavior limits")
        self.assertFalse({cell for cell in prohibited if policy["cell_job_bindings"].get(cell) == job})


class SourcePayloadAdmissionTest(unittest.TestCase):
    def test_source_test_cannot_qualify_from_unbound_native_archive(self):
        ReportTest.setUp(self)
        self.map["groups"][0]["proof_kind"] = "source-test"
        self.observation.update(proof_kind="source-test", producer="python-test-result-observer")
        with self.assertRaisesRegex(ValueError, "source.*(binding|payload|manifest)"):
            owner.build_report(self.req, job_name="owning native job", job_id=9,
                selections=self.map, observations={"native":self.observation}, payloads={"candidate":self.payload})


from contextlib import contextmanager


@contextmanager
def source_payload_fixture():
    """Real private Git/source files; no native/provider/runtime qualification."""
    with tempfile.TemporaryDirectory(prefix="ca-source-payload-") as temporary:
        base = Path(temporary).resolve(); repo = base / "repo"; repo.mkdir()
        for relative in owner.SOURCE_PATHS:
            target = repo / relative; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((owner.ROOT / relative).read_bytes())
        counters = {}
        for relative in (".github/scripts/test_check_skill_proof_fresh.py", ".github/scripts/test_generated_output.py"):
            counter = base / (Path(relative).stem + ".count")
            child_counter = base / (Path(relative).stem + ".child-count")
            child = ("import unittest,pathlib\nclass Child(unittest.TestCase):\n"
                     f" def test_child(self): pathlib.Path({str(child_counter)!r}).write_text('x')\n"
                     "unittest.main()\n")
            text = ("import unittest,pathlib,subprocess,sys\nclass Parent(unittest.TestCase):\n"
                    " def test_owned(self):\n"
                    f"  p=pathlib.Path({str(counter)!r});p.write_text(p.read_text()+'x' if p.exists() else 'x')\n"
                    f"  self.assertEqual(subprocess.run([sys.executable,'-I','-S','-B','-c',{child!r}],capture_output=True).returncode,0)\n"
                    "if __name__=='__main__': unittest.main()\n")
            (repo / relative).write_text(text, encoding="utf8", newline="\n")
            counters[relative] = (counter, child_counter)
        (repo / ".gitignore").write_text("core/surface/ignored-extra\n", newline="\n")
        git = shutil.which("git")
        if git is None: raise AssertionError("Git required for source fixture")
        env = {k:v for k,v in os.environ.items() if k.upper() in {"SYSTEMROOT","WINDIR","SYSTEMDRIVE","COMSPEC","PATHEXT"}}
        env.update(PATH=os.pathsep.join([str(Path(git).parent),str(Path(sys.executable).parent)]),
                   HOME=str(base),USERPROFILE=str(base),GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM="1",
                   GIT_TERMINAL_PROMPT="0",GITHUB_RUN_ID="7",PYTHONDONTWRITEBYTECODE="1",PYTHONNOUSERSITE="1")
        with mock.patch.dict(os.environ, env, clear=True):
            for arguments in (("init","-q"),("add","."),("-c","user.name=fixture","-c","user.email=fixture@example.invalid",
                              "-c","commit.gpgsign=false","commit","-qm","source payload fixture")):
                phase="init" if arguments[0]=="init" else "index" if arguments[0]=="add" else "commit"
                run_git_phase([git,"-C",str(repo),*arguments],phase=phase,trace_dir=base)
            staged = base / "inputs"
            manifest = owner.prepare_source_payload(repo, staged, owner.SOURCE_JOB)
            identity = owner.source_identity(repo)
            binding = owner.source_observation_binding(repo, staged, identity)
            req = {**identity,"ci_run_id":7,"cells":["disposition:transitions:C33:02"],
                   "cell_jobs":{"disposition:transitions:C33:02":owner.SOURCE_JOB}}
            def archive(mutate=None):
                files = {path.relative_to(staged).as_posix():path.read_bytes() for path in staged.rglob("*") if path.is_file()}
                if mutate is not None: mutate(files)
                output = io.BytesIO()
                with zipfile.ZipFile(output,"w") as zipped:
                    for relative,value in sorted(files.items()): zipped.writestr(relative,value)
                return output.getvalue()
            def authenticate(raw=None, source_job=None):
                with mock.patch.object(owner.readiness,"artifact_bytes",return_value=archive() if raw is None else raw), \
                     mock.patch.object(owner.readiness,"validate_upload") as attribution:
                    payload = owner.authenticated_payload({"id":8,"name":owner.SOURCE_PAYLOAD},req,repo,
                        source_job={"id":9,"name":owner.SOURCE_JOB,"status":"in_progress","conclusion":None,
                            "steps":[{"name":owner.SOURCE_UPLOAD,"status":"completed","conclusion":"success"}]}
                        if source_job is None else source_job)
                    attribution.assert_not_called()
                    return payload
            yield {"base":base,"repo":repo,"staged":staged,"manifest":manifest,"binding":binding,
                   "req":req,"archive":archive,"authenticate":authenticate,"counters":counters}


class BoundSourcePayloadTests(unittest.TestCase):
    def test_running_source_producer_never_reads_its_own_unavailable_job_log(self):
        with source_payload_fixture() as fixture:
            job={"id":9,"name":owner.SOURCE_JOB,"status":"in_progress","conclusion":None,
                 "steps":[{"name":owner.SOURCE_UPLOAD,"status":"completed","conclusion":"success"}]}
            with mock.patch.object(owner.readiness,"artifact_bytes",return_value=fixture["archive"]()), \
                 mock.patch.object(owner.readiness,"validate_upload",side_effect=AssertionError("own job log unavailable")) as final_attribution:
                payload=owner.authenticated_payload({"id":8,"name":owner.SOURCE_PAYLOAD},fixture["req"],fixture["repo"],source_job=job)
                self.assertEqual(payload["source_upload_job_id"],9)
                final_attribution.assert_not_called()
                for state in ("missing","failed","running","wrong-job","completed-job"):
                    bad=copy.deepcopy(job)
                    if state=="missing":bad["steps"]=[]
                    elif state=="failed":bad["steps"][0]["conclusion"]="failure"
                    elif state=="running":bad["steps"][0]["status"]="in_progress"
                    elif state=="wrong-job":bad["name"]="other"
                    else:bad["status"]="completed"
                    with self.subTest(state=state),self.assertRaises(ValueError):
                        owner.authenticated_payload({"id":8,"name":owner.SOURCE_PAYLOAD},fixture["req"],fixture["repo"],source_job=bad)

    def test_final_readiness_authenticates_both_original_source_and_report_uploads(self):
        cell="disposition:transitions:C33:02";raw=io.BytesIO()
        with zipfile.ZipFile(raw,"w") as archive:archive.writestr("owned-input",b"source")
        content=raw.getvalue();members=owner.readiness.members(content)
        source={"id":8,"name":owner.SOURCE_PAYLOAD};report_artifact={"id":10,"name":"major-qualification-9"}
        job={"id":9,"name":owner.SOURCE_JOB,"status":"completed","conclusion":"success"}
        req={"source_commit":"a"*40,"source_tree":"b"*40,"ci_run_id":7,"cells":[cell],
             "cell_jobs":{cell:owner.SOURCE_JOB},"required_artifact_names":[owner.SOURCE_PAYLOAD]}
        report={"schema":"codearbiter-major-qualification/2",**{key:req[key] for key in
            ("source_commit","source_tree","ci_run_id")},"job_id":9,
            "payloads":[{"artifact_id":8,"archive_sha256":owner.readiness.digest(content),"members":members}],
            "results":[{"cell":cell,"result":"PASSED","commands":[{"argv":["python","owning.py"],"exit_code":0}],
                "selected_population":1,"executed_population":1,"payload_artifact_id":8}]}
        jobs=[job,{"id":11,"name":"major readiness producer"}]
        with mock.patch.object(owner.readiness,"read_artifact_json",return_value=report), \
             mock.patch.object(owner.readiness,"artifact_bytes",return_value=content), \
             mock.patch.object(owner.readiness,"validate_upload") as attribution:
            owner.readiness.produce(req,[source,report_artifact],jobs)
            self.assertEqual(attribution.call_args_list,[
                mock.call(job,report_artifact,"Upload major qualification report"),
                mock.call(job,source,owner.SOURCE_UPLOAD)])
            def refuse_input(_job,_artifact,step):
                if step==owner.SOURCE_UPLOAD:raise owner.readiness.ReadinessError("input uploader refused")
            attribution.side_effect=refuse_input
            with self.assertRaises(owner.readiness.ReadinessError):
                owner.readiness.produce(req,[source,report_artifact],jobs)
            attribution.side_effect=None
            for status in ("in_progress","failure"):
                bad={**job,"conclusion":status}
                with self.subTest(status=status),self.assertRaises(owner.readiness.ReadinessError):
                    owner.readiness.produce(req,[source,report_artifact],[bad,jobs[1]])

    def synthetic_case(self, fixture):
        observed = {"format":owner.OBSERVATION,**owner.source_identity(fixture["repo"]),"ci_run_id":7,
            "source_stable":True,"proof_kind":"source-test","producer":"python-test-result-observer",
            "argv":[sys.executable,".github/scripts/test_check_skill_proof_fresh.py"],"exit_code":0,
            "source_input_binding":fixture["binding"],
            "tests":[{"id":"python:.github/scripts/test_check_skill_proof_fresh.py:__main__.Parent.test_owned","result":"passed"}]}
        group={"id":"source","job":owner.SOURCE_JOB,"payload_name":owner.SOURCE_PAYLOAD,
            "observation":"source","proof_kind":"source-test","selectors":[observed["tests"][0]["id"]],
            "cells":fixture["req"]["cells"],"scope":"Synthetic software admission fixture only"}
        return observed,{"schema":owner.SELECTIONS,"groups":[group]}

    def build(self, fixture, observed, selection, payload):
        return owner.build_report(fixture["req"],job_name=owner.SOURCE_JOB,job_id=9,selections=selection,
                                  observations={"source":observed},payloads={owner.SOURCE_PAYLOAD:payload})

    def test_bound_original_entrypoints_execute_once_and_never_infer_child_test_ids(self):
        with source_payload_fixture() as fixture:
            before = owner.source_input_snapshot(fixture["repo"])
            for relative,counters in fixture["counters"].items():
                output = fixture["base"] / (Path(relative).stem + ".observation.json")
                self.assertEqual(owner.observe_python(fixture["repo"],relative,[],output,fixture["staged"]),0)
                result=owner.load_json(output)
                self.assertEqual(result["tests"],[{"id":"python:"+relative+":__main__.Parent.test_owned","result":"passed"}])
                self.assertEqual(result["source_input_binding"],fixture["binding"])
                self.assertTrue(result["source_stable"])
                self.assertEqual([path.read_text() for path in counters],["x","x"])
            self.assertEqual(owner.source_input_snapshot(fixture["repo"]),before)
            observed,selection=self.synthetic_case(fixture)
            report=self.build(fixture,observed,selection,fixture["authenticate"]())
            self.assertEqual(len(report["results"]),1)
            self.assertEqual(report["results"][0]["executed_population"],1)

    def test_source_binding_and_manifest_identity_fail_closed(self):
        with source_payload_fixture() as fixture:
            observed,selection=self.synthetic_case(fixture);payload=fixture["authenticate"]()
            for failure in ("binding-absent","profile","role","manifest-digest","uploader","source","tree","run","extra-key","member","oversize"):
                bad,chosen,consumed=copy.deepcopy(observed),copy.deepcopy(selection),copy.deepcopy(payload)
                manifest=consumed["documents"][owner.SOURCE_MANIFEST]
                if failure=="binding-absent":del bad["source_input_binding"]
                elif failure=="profile":bad["source_input_binding"]["profile"]="foreign"
                elif failure=="role":chosen["groups"][0]["payload_name"]="unrelated-native"
                elif failure=="manifest-digest":consumed["source_manifest_sha256"]="0"*64
                elif failure=="uploader":consumed["source_upload_job_id"]=True
                elif failure in ("source","tree"):manifest["source_commit" if failure=="source" else "source_tree"]="e"*40
                elif failure=="run":manifest["ci_run_id"]=True
                elif failure=="extra-key":manifest["claim_passed"]=True
                elif failure=="member":manifest["members"][0]["path"]=".git/config"
                else:manifest["members"][0]["bytes"]=8*1024*1024+1
                with self.subTest(failure=failure),self.assertRaises(ValueError):self.build(fixture,bad,chosen,consumed)
            for state in ("skipped","failed","missing","repeated"):
                bad=copy.deepcopy(observed)
                if state=="missing":bad["tests"]=[]
                elif state=="repeated":bad["tests"].append(dict(bad["tests"][0]))
                else:bad["tests"][0]["result"]=state
                with self.subTest(state=state),self.assertRaises(ValueError):self.build(fixture,bad,selection,payload)

    def test_authenticated_archive_requires_exact_input_bytes_profile_and_original_upload(self):
        with source_payload_fixture() as fixture:
            def bad_manifest(files,field,value):
                document=json.loads(files[owner.SOURCE_MANIFEST]);document[field]=value
                files[owner.SOURCE_MANIFEST]=json.dumps(document).encode()
            for failure in ("changed","extra","missing","profile","source","duplicate-json","no-uploader"):
                def mutate(files):
                    first=sorted(owner.SOURCE_PATHS)[0]
                    if failure=="changed":files[first]+=b"changed"
                    elif failure=="extra":files["foreign-secret-name"]=b"inert"
                    elif failure=="missing":del files[first]
                    elif failure=="profile":bad_manifest(files,"profile","foreign")
                    elif failure=="source":bad_manifest(files,"source_commit","e"*40)
                    elif failure=="duplicate-json":files[owner.SOURCE_MANIFEST]=b'{"format":"x","format":"y"}'
                raw=fixture["archive"](mutate)
                with self.subTest(failure=failure),self.assertRaises(ValueError):
                    fixture["authenticate"](raw,{} if failure=="no-uploader" else None)
            with mock.patch.object(owner.readiness,"artifact_bytes",return_value=fixture["archive"]()):
                with self.assertRaises(ValueError):
                    owner.authenticated_payload({"id":8,"name":owner.SOURCE_PAYLOAD},fixture["req"],fixture["repo"],
                        source_job={"id":9,"name":owner.SOURCE_JOB,"status":"in_progress","conclusion":None,"steps":[]})

    def test_actual_source_membership_and_staged_bytes_drift_refuse_without_rewriting(self):
        with source_payload_fixture() as fixture:
            repo,staged=fixture["repo"],fixture["staged"]
            with self.assertRaises(ValueError):owner.prepare_source_payload(repo,staged,owner.SOURCE_JOB)
            extra=repo/"core/surface/ignored-extra";extra.write_bytes(b"unobserved source")
            with self.assertRaises(ValueError):owner.source_input_snapshot(repo)
            self.assertEqual(extra.read_bytes(),b"unobserved source");extra.unlink()
            first=sorted(owner.SOURCE_PATHS)[0];path=staged/first;original=path.read_bytes();path.write_bytes(original+b"changed")
            with self.assertRaises(ValueError):owner.source_observation_binding(repo,staged,owner.source_identity(repo))
            self.assertEqual(path.read_bytes(),original+b"changed");path.write_bytes(original)
            (staged/"foreign").mkdir()
            with self.assertRaises(ValueError):owner.source_observation_binding(repo,staged,owner.source_identity(repo))

    def test_source_reparse_metadata_refuses_before_file_open(self):
        from types import SimpleNamespace
        with source_payload_fixture() as fixture:
            relative=sorted(owner.SOURCE_PATHS)[0];target=fixture["repo"]/relative;original=Path.lstat
            def reparse(path,*args,**kwargs):
                info=original(path,*args,**kwargs)
                if path==target:
                    return SimpleNamespace(st_mode=info.st_mode,st_nlink=info.st_nlink,st_size=info.st_size,
                        st_dev=info.st_dev,st_ino=info.st_ino,st_file_attributes=owner.stat.FILE_ATTRIBUTE_REPARSE_POINT)
                return info
            with mock.patch.object(Path,"lstat",reparse),mock.patch.object(owner.os,"open") as opening:
                with self.assertRaisesRegex(ValueError,"link/reparse"):owner._source_file(fixture["repo"],relative)
                opening.assert_not_called()

    def test_python_source_profile_cannot_qualify_other_software_or_tasks(self):
        with source_payload_fixture() as fixture:
            observed,selection=self.synthetic_case(fixture);payload=fixture['authenticate']()
            self.assertEqual(len(self.build(fixture,observed,selection,payload)['results']),1)
            for cell in ('disposition:transitions:C33:99','task:Q-01','disposition:machines:S75'):
                chosen=copy.deepcopy(selection);chosen['groups'][0]['cells']=[cell]
                fixture['req'].update(cells=[cell],cell_jobs={cell:owner.SOURCE_JOB})
                with self.subTest(cell=cell),self.assertRaisesRegex(ValueError,'Python profile cannot qualify another software scope'):
                    self.build(fixture,observed,chosen,payload)

    def test_complete_checker_and_publisher_groups_require_each_named_pass(self):
        selection=json.loads((owner.ROOT/'.github/major-test-selections.json').read_text())
        cells={'disposition:transitions:C33:01','disposition:machines:C33','disposition:transitions:S75:05'}
        groups=[g for g in selection['groups'] if cells.intersection(g['cells'])]
        self.assertEqual({cell for group in groups for cell in group['cells']},cells)
        self.assertEqual(len(groups),3)
        with source_payload_fixture() as fixture:
            observed,_=self.synthetic_case(fixture);payload=fixture['authenticate']()
            for group in groups:
                fixture['req'].update(cells=group['cells'],cell_jobs={cell:owner.SOURCE_JOB for cell in group['cells']})
                observed['tests']=[{'id':selector,'result':'passed'} for selector in group['selectors']]
                chosen={'schema':owner.SELECTIONS,'groups':[group]}
                observations={group['observation']:observed}
                def build():
                    return owner.build_report(fixture['req'],job_name=owner.SOURCE_JOB,job_id=9,selections=chosen,
                        observations=observations,payloads={owner.SOURCE_PAYLOAD:payload})
                result=build()['results'][0]
                self.assertEqual(result['selected_population'],len(group['selectors']))
                self.assertEqual(result['executed_population'],len(group['selectors']))
                for index,selector in enumerate(group['selectors']):
                    for state in ('missing','skipped','failed','repeated'):
                        original=copy.deepcopy(observed['tests'])
                        if state=='missing':observed['tests'].pop(index)
                        elif state=='repeated':observed['tests'].append(dict(observed['tests'][index]))
                        else:observed['tests'][index]['result']=state
                        with self.subTest(cell=group['cells'],selector=selector,state=state),self.assertRaisesRegex(ValueError,'selected named test'):
                            build()
                        observed['tests']=original

    def test_six_source_cells_keep_exact_selectors_and_single_original_ci_executions(self):
        from test_ci_impact import workflow_jobs
        selection=json.loads((owner.ROOT/".github/major-test-selections.json").read_text())
        policy=json.loads((owner.ROOT/".github/major-qualification-policy.json").read_text())
        source=[group for group in selection["groups"] if group["proof_kind"]=="source-test" and group["payload_name"]==owner.SOURCE_PAYLOAD]
        expected={"disposition:transitions:C33:02","disposition:transitions:C33:03",*
            ("disposition:added_transitions:S75:"+name for name in
             ("added-stage-failed","added-rolled-back","added-unusable","added-writer-refused"))}
        expected.update({'disposition:transitions:C33:01', 'disposition:transitions:S75:05', 'disposition:machines:C33'})
        self.assertEqual({cell for group in source for cell in group["cells"]},expected)
        exact_selectors = {'disposition:added_transitions:S75:added-rolled-back': {'python:.github/scripts/test_generated_output.py:__main__.GeneratedOutputTests.test_late_rename_failure_rolls_back_and_clean_rerun_converges'},
         'disposition:added_transitions:S75:added-stage-failed': {'python:.github/scripts/test_generated_output.py:__main__.GeneratedOutputTests.test_late_stage_failure_preserves_old_complete_set'},
         'disposition:added_transitions:S75:added-unusable': {'python:.github/scripts/test_generated_output.py:__main__.GeneratedOutputTests.test_rollback_failure_retains_explicit_unusable_marker_and_journal'},
         'disposition:added_transitions:S75:added-writer-refused': {'python:.github/scripts/test_generated_output.py:__main__.GeneratedOutputTests.test_concurrent_writer_refuses_without_deleting_other_marker'},
         'disposition:transitions:C33:02': {'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_hash_mismatch',
                                            'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_recorded_path_is_not_a_rendered_payload',
                                            'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckLiveRepoTest.test_the_live_artifact_still_fails_when_the_recorded_hash_is_wrong'},
         'disposition:transitions:C33:03': {'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckLiveRepoTest.test_historical_hash_map_is_bound_to_its_own_exercise',
                                            'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.PayloadDerivationTest.test_composed_commands_do_not_become_independent_owner_proof',
                                            'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.PayloadDerivationTest.test_derives_exactly_the_three_full_prose_payloads_on_live_repo'}}
        exact_selectors.update({'disposition:transitions:C33:01': {'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_proof_current_missing_entirely', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_recorded_path_is_not_a_rendered_payload', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_exercise_object_missing', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_fresh_document_passes', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_json_null_top_level_reports_cleanly_not_attributeerror', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_recorded_path_no_longer_exists_on_disk', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.PayloadDerivationTest.test_a_host_that_no_longer_renders_the_source_raises', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_exercised_skill_sha256_missing', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_unparseable_json', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_exercised_skill_path_missing', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_proof_current_false', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_json_array_top_level_reports_cleanly_not_attributeerror', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_hash_mismatch', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_missing_artifact_file'}, 'disposition:machines:C33': {'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_proof_current_missing_entirely', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_recorded_path_is_not_a_rendered_payload', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_exercise_object_missing', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.PayloadDerivationTest.test_derives_exactly_the_three_full_prose_payloads_on_live_repo', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_fresh_document_passes', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_json_null_top_level_reports_cleanly_not_attributeerror', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_recorded_path_no_longer_exists_on_disk', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.PayloadDerivationTest.test_a_host_that_no_longer_renders_the_source_raises', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_exercised_skill_sha256_missing', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckLiveRepoTest.test_historical_hash_map_is_bound_to_its_own_exercise', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_unparseable_json', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_exercised_skill_path_missing', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_proof_current_false', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_json_array_top_level_reports_cleanly_not_attributeerror', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_hash_mismatch', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckLiveRepoTest.test_the_live_artifact_still_fails_when_the_recorded_hash_is_wrong', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.PayloadDerivationTest.test_composed_commands_do_not_become_independent_owner_proof', 'python:.github/scripts/test_check_skill_proof_fresh.py:__main__.CheckFailureModeTest.test_missing_artifact_file'}, 'disposition:transitions:S75:05': {'python:.github/scripts/test_generated_output.py:__main__.GeneratedOutputTests.test_surface_write_success_changes_only_owned_drift_and_preserves_equal_files'}})
        for group in source:
            self.assertEqual((group["job"],group["payload_name"]),(owner.SOURCE_JOB,owner.SOURCE_PAYLOAD))
            for cell in group["cells"]: self.assertEqual(set(group["selectors"]), exact_selectors[cell])
            for cell in group["cells"]:self.assertEqual(policy["cell_job_bindings"][cell],owner.SOURCE_JOB)
        hooks=workflow_jobs((owner.ROOT/".github/workflows/ci.yml").read_text())["hooks"]
        self.assertEqual(hooks.count('id: python_source_prepare'),1)
        self.assertEqual(hooks.count('id: python_publisher_observed'),1)
        self.assertEqual(hooks.count('id: python_proof_observed'),1)
        for entry in ("test_generated_output.py","test_check_skill_proof_fresh.py"):
            self.assertEqual(hooks.count('-- .github/scripts/'+entry),1)
            self.assertEqual(hooks.count('run: python .github/scripts/'+entry),1)
        self.assertLess(hooks.index('id: python_source_prepare'),hooks.index('id: python_publisher_observed'))
        self.assertLess(hooks.index('id: python_proof_observed'),hooks.index('id: python_source_upload'))
        self.assertIn('include-hidden-files: true',hooks)
        emit=hooks.split('id: python_qualification_emit',1)[1].split('- name: Upload major qualification report',1)[0]
        for condition in ("github.event_name == 'push'","github.ref == 'refs/heads/main'",
                          "github.ref == 'refs/heads/major/state-contracts'",'GH_TOKEN: ${{ github.token }}',
                          '--payload-root "'+owner.SOURCE_PAYLOAD+'=${{ github.workspace }}"',
                          '--output "${{ runner.temp }}/qualification.json"'):
            self.assertIn(condition,emit)
        self.assertIn('path: ${{ runner.temp }}/qualification.json',hooks)
        before_emit=hooks.split('- name: Emit original Python source qualification report',1)[0]
        self.assertNotIn('GH_TOKEN:',before_emit)
        self.assertNotIn('GITHUB_TOKEN:',before_emit)




class LocalReadGitEnvironmentTests(unittest.TestCase):
    def test_readiness_local_git_cannot_inherit_parent_metadata_credentials(self):
        from types import SimpleNamespace
        process=SimpleNamespace(returncode=0,communicate=lambda **kwargs:(b"head\n",b""))
        with mock.patch.dict(os.environ,{"GH_TOKEN":"inert-metadata-canary","GITHUB_TOKEN":"inert-other-canary","UNRELATED_SECRET":"inert-secret"}), \
             mock.patch.object(owner.readiness,"start",return_value=process) as start:
            owner.readiness.command(["git","rev-parse","HEAD"])
            child=start.call_args.kwargs.get("env",dict(os.environ))
            self.assertFalse(any(k.upper() in {"GH_TOKEN","GITHUB_TOKEN","UNRELATED_SECRET"} for k in child),
                             "local Git inherited credential fields")
            self.assertEqual(os.environ["GH_TOKEN"],"inert-metadata-canary")
            start.reset_mock()
            owner.readiness.command(["gh","api","repos/arbiterForge/codeArbiter/actions/runs/7"])
            metadata=start.call_args.kwargs.get("env",dict(os.environ))
            self.assertEqual(metadata["GH_TOKEN"],"inert-metadata-canary")

    def test_local_env_scrubs_config_carriers_and_root_selectors_without_changing_default_env(self):
        import _gitexec
        values={"GH_TOKEN":"inert-metadata-canary","GITHUB_TOKEN":"inert-other-canary","UNRELATED_SECRET":"inert-secret",
                "GIT_DIR":"foreign-git","GIT_WORK_TREE":"foreign-tree","GIT_INDEX_FILE":"selected-index",
                "GIT_CONFIG_COUNT":"1","GIT_CONFIG_KEY_0":"http.extraheader","GIT_CONFIG_VALUE_0":"inert-carrier",
                "GIT_CONFIG_GLOBAL":"protected-global-file","GIT_CONFIG_SYSTEM":"protected-system-file",
                "GIT_CONFIG_NOSYSTEM":"1","HOME":"private-profile","LANG":"C.UTF-8"}
        with mock.patch.dict(os.environ,values):
            original=dict(os.environ);blind=_gitexec.local_read_git_env()
            for key in values:
                if key in {"GIT_CONFIG_GLOBAL","GIT_CONFIG_SYSTEM","GIT_CONFIG_NOSYSTEM","HOME","LANG"}:
                    self.assertEqual(blind[key],values[key])
                else:self.assertNotIn(key,blind)
            self.assertEqual(blind["GIT_TERMINAL_PROMPT"],"0")
            self.assertEqual(_gitexec.local_read_git_env(preserve_index=True)["GIT_INDEX_FILE"],"selected-index")
            default=_gitexec.root_bound_git_env()
            self.assertEqual(default["GH_TOKEN"],values["GH_TOKEN"])
            self.assertEqual(default["GIT_CONFIG_VALUE_0"],values["GIT_CONFIG_VALUE_0"])
            self.assertNotIn("GIT_DIR",default)
            self.assertEqual(dict(os.environ),original)

    def test_local_git_keeps_protected_file_config_and_only_explicit_alternate_index(self):
        import _gitexec
        with tempfile.TemporaryDirectory(prefix="ca-local-git-env-") as directory:
            base=Path(directory);repo=base/"repo";repo.mkdir();config=base/"protected.gitconfig"
            config.write_text("[safe]\n    directory = /owned-fixture\n",newline="\n")
            with mock.patch.dict(os.environ,{"GH_TOKEN":"inert-metadata-canary","GIT_CONFIG_GLOBAL":str(config),
                    "GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_COUNT":"1","GIT_CONFIG_KEY_0":"http.extraheader",
                    "GIT_CONFIG_VALUE_0":"inert-config-carrier"}):
                env=_gitexec.local_read_git_env()
                def git(*args,environment=env):
                    return subprocess.run(["git","-C",str(repo),*args],env=environment,check=True,
                                          capture_output=True,timeout=15).stdout
                self.assertEqual(git("config","--global","--get","safe.directory").strip(),b"/owned-fixture")
                git("init","-q");(repo/"one").write_bytes(b"one");git("add","one")
                git("-c","user.name=fixture","-c","user.email=fixture@example.invalid","-c","commit.gpgsign=false","commit","-qm","index fixture")
                alternate=base/"alternate-index";alternate.write_bytes((repo/".git/index").read_bytes())
                (repo/"two").write_bytes(b"two");other={**env,"GIT_INDEX_FILE":str(alternate)}
                git("add","two",environment=other)
                with mock.patch.dict(os.environ,{"GIT_INDEX_FILE":str(alternate),"GIT_DIR":"foreign-root"}):
                    self.assertEqual(git("ls-files",environment=_gitexec.local_read_git_env()),b"one\n")
                    self.assertEqual(git("ls-files",environment=_gitexec.local_read_git_env(preserve_index=True)),b"one\ntwo\n")
                self.assertEqual(os.environ["GH_TOKEN"],"inert-metadata-canary")

    def test_report_and_immutable_reader_pass_blind_local_environment(self):
        from types import SimpleNamespace
        import _immutable_git_blobs as transport
        with mock.patch.dict(os.environ,{"GH_TOKEN":"inert-metadata-canary","GITHUB_TOKEN":"inert-other-canary"}):
            original=dict(os.environ)
            with mock.patch.object(owner.subprocess,"run",return_value=SimpleNamespace(stdout=b"head\n")) as run:
                owner.git(Path.cwd(),"rev-parse","HEAD")
                self.assertFalse(any(k.upper() in {"GH_TOKEN","GITHUB_TOKEN"} for k in run.call_args.kwargs["env"]))
            with mock.patch.object(transport,"start",return_value=SimpleNamespace()) as start, \
                 mock.patch.object(transport.threading,"Thread") as thread:
                reader=transport.Reader(Path.cwd());reader._start()
                child=start.call_args.kwargs["env"]
                self.assertFalse(any(k.upper() in {"GH_TOKEN","GITHUB_TOKEN"} for k in child))
                self.assertNotIn("GIT_INDEX_FILE",child)
                self.assertEqual(child["GIT_TERMINAL_PROMPT"],"0")
                thread.return_value.start.assert_called_once()
            self.assertEqual(dict(os.environ),original)

    def test_readiness_git_role_cannot_be_used_for_network_or_mutating_commands(self):
        with mock.patch.object(owner.readiness,"start") as start:
            for arguments in (["git","fetch","origin"],["git","push","origin"],["git","checkout","--force"],
                              ["git","-c","http.extraheader=inert-carrier","rev-parse","HEAD"]):
                with self.subTest(operation=arguments[1]),self.assertRaises(owner.readiness.ReadinessError):
                    owner.readiness.command(arguments)
            start.assert_not_called()

    def test_only_owned_adr_child_receives_the_blind_python_environment(self):
        process=SimpleNamespace(returncode=0,communicate=lambda **kwargs:(b"valid\n",b""))
        checker=str(Path(owner.readiness.__file__).with_name("check_adr_lifecycle.py"))
        arguments=[sys.executable,checker,"--root","owned-root","--current-ref","a"*40]
        with mock.patch.dict(os.environ,{"GH_TOKEN":"inert-metadata-canary","GITHUB_TOKEN":"inert-other-canary",
                "PYTHONPATH":"foreign-imports","PYTHONSTARTUP":"foreign-startup"}), \
             mock.patch.object(owner.readiness,"start",return_value=process) as start:
            original=dict(os.environ)
            self.assertEqual(owner.readiness.command(arguments,local_adr=True),b"valid\n")
            self.assertEqual(start.call_args.args[0],arguments)
            child=start.call_args.kwargs["env"]
            for key in ("GH_TOKEN","GITHUB_TOKEN","PYTHONPATH","PYTHONSTARTUP"):
                self.assertNotIn(key,child)
            self.assertEqual({key:child[key] for key in
                ("PYTHONNOUSERSITE","PYTHONDONTWRITEBYTECODE","PYTHONIOENCODING")},
                {"PYTHONNOUSERSITE":"1","PYTHONDONTWRITEBYTECODE":"1","PYTHONIOENCODING":"utf-8"})
            start.reset_mock()
            for unowned in ([sys.executable,"foreign/check_adr_lifecycle.py"],
                            [sys.executable,"-c","pass"],
                            [sys.executable,"-I",checker],
                            ["foreign-python",checker]):
                with self.subTest(command=unowned[1]),self.assertRaises(owner.readiness.ReadinessError):
                    owner.readiness.command(unowned,local_adr=True)
            start.assert_not_called()
            for operation in ("rev-parse","cat-file","merge-base","ls-tree"):
                owner.readiness.command(["git",operation,"HEAD"])
                self.assertNotIn("GH_TOKEN",start.call_args.kwargs["env"])
            self.assertEqual(dict(os.environ),original)

    def test_actual_owned_adr_child_reads_a_private_committed_ledger(self):
        import _gitexec
        with tempfile.TemporaryDirectory(prefix="ca-local-adr-read-") as directory:
            repo=Path(directory);decisions=repo/".codearbiter/decisions";decisions.mkdir(parents=True)
            (decisions/"adr-lifecycle.jsonl").write_bytes(b"")
            env=_gitexec.local_read_git_env()
            def git(*args):
                return subprocess.run(["git","-C",str(repo),*args],env=env,check=True,
                                      capture_output=True,timeout=15).stdout
            git("init","-q");git("add",".codearbiter/decisions/adr-lifecycle.jsonl")
            git("-c","user.name=fixture","-c","user.email=fixture@example.invalid",
                "-c","commit.gpgsign=false","commit","-qm","private ADR read fixture")
            checker=str(Path(owner.readiness.__file__).with_name("check_adr_lifecycle.py"))
            arguments=[sys.executable,checker,"--root",str(repo),"--current-ref","HEAD"]
            with mock.patch.dict(os.environ,{"GH_TOKEN":"inert-metadata-canary","GITHUB_TOKEN":"inert-other-canary"}):
                output=owner.readiness.command(arguments,repo,local_adr=True)
                self.assertIn(b"ADR lifecycle bindings valid",output)
                with self.assertRaises(owner.readiness.ReadinessError):
                    owner.readiness.command(arguments[:-1]+["0"*40],repo,local_adr=True)
            self.assertFalse(list(repo.rglob("__pycache__")))




class VitestInvocationTests(unittest.TestCase):
    """One inert original-command process; never real Vitest/host evidence."""

    def invocation_fixture(self, *, document=None, mode="write", exit_code=0, drift=False):
        temporary = tempfile.TemporaryDirectory(prefix="ca-vitest-original-")
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve(strict=True)
        repo = base / "repo"
        project = repo / "plugins" / "fixture" / "tools"
        project.mkdir(parents=True)
        sample = project / "sample.test.ts"
        sample.write_text("// inert protocol sample\n", encoding="utf-8")
        counter, raw, observation, blob = [base / name for name in
            ("counter.json", "vitest.json", "observation.json", "original.blob")]
        runner = repo / "inert-vitest.py"
        named = {"testResults": [{"name": str(sample), "assertionResults": [
            {"fullName": "original owner keeps one named result", "status": "passed"}]}]}
        if document is not None:
            named = document(sample)
        runner.write_text("import json,os,pathlib,sys\n"
            f"counter=pathlib.Path({str(counter)!r})\n"
            "calls=json.loads(counter.read_text()) if counter.exists() else []\n"
            "calls.append({'argv':sys.argv[1:],'cwd':os.getcwd()});counter.write_text(json.dumps(calls))\n"
            "outputs={};args=iter(sys.argv[1:])\n"
            "for arg in args:\n"
            " if arg.startswith('--outputFile'):\n"
            "  key,value=arg.split('=',1) if '=' in arg else (arg,next(args))\n"
            "  outputs[key]=pathlib.Path(value)\n"
            "for key,path in outputs.items():\n"
            " path.parent.mkdir(parents=True,exist_ok=True)\n"
            f" if key in ('--outputFile','--outputFile.json') and {mode!r}=='missing':continue\n"
            f" if key in ('--outputFile','--outputFile.json') and {mode!r}=='replaced':\n"
            f"  other=path.with_name('replacement.json');other.write_text(json.dumps({named!r}));os.replace(other,path);continue\n"
            f" if key in ('--outputFile','--outputFile.json') and {mode!r}=='hardlinked':os.link(path,path.with_name('extra-link'))\n"
            f" if key in ('--outputFile','--outputFile.json') and {mode!r}=='oversize':\n"
            f"  with path.open('wb') as stream:stream.truncate({owner.MAX_JSON + 1})\n"
            "  continue\n"
            f" path.write_text(json.dumps({named!r}) if key in ('--outputFile','--outputFile.json') else 'opaque original blob')\n"
            f"if {drift!r}:pathlib.Path({str(sample)!r}).write_text('// changed source')\n"
            f"raise SystemExit({exit_code})\n",
            encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-qm", "inert original reporter fixture"], check=True)
        return SimpleNamespace(base=base, repo=repo, project=project, counter=counter, raw=raw,
                               output=observation, blob=blob, runner=runner, named=named)

    def test_original_multi_reporter_invocations_are_preserved_and_run_once(self):
        for style in ("sandbox", "pi"):
            with self.subTest(original_style=style):
                fixture = self.invocation_fixture()
                flags = (["--reporter=default", "--reporter=github-actions", "--reporter=json",
                          "--outputFile.json=" + str(fixture.raw)] if style == "sandbox" else
                         ["--coverage", "--reporter=blob", "--reporter=default",
                          "--outputFile.blob=" + str(fixture.blob)])
                arguments = [sys.executable, "-B", str(fixture.runner), "run", *flags]
                try:
                    code = owner.observe_vitest(fixture.repo, arguments, fixture.raw, fixture.output)
                except ValueError as error:
                    count = len(json.loads(fixture.counter.read_text())) if fixture.counter.exists() else 0
                    self.fail(f"original {style} invocation refused; actual_processes={count}; {error}")
                self.assertEqual(code, 0)
                calls = json.loads(fixture.counter.read_text())
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]["cwd"], str(fixture.repo))
                self.assertEqual(calls[0]["argv"][:len(arguments)-3], arguments[3:])
                observed = owner.load_json(fixture.output)
                self.assertEqual(observed["original_argv"], arguments)
                self.assertEqual(observed["argv"][:len(arguments)], arguments)
                self.assertTrue(observed["source_stable"])
                self.assertEqual(observed["tests"], [{"id": "vitest:plugins/fixture/tools/sample.test.ts:original owner keeps one named result", "result": "passed"}])
                if style == "sandbox":
                    self.assertEqual(observed["argv"], arguments)
                else:
                    self.assertEqual(fixture.blob.read_text(), "opaque original blob")
                    self.assertEqual(observed["argv"].count("--reporter=json"), 1)



    def test_project_cwd_and_split_reporter_arguments_use_the_original_process(self):
        fixture = self.invocation_fixture()
        arguments = [sys.executable, "-B", str(fixture.runner), "run", "--coverage",
                     "--reporter", "blob", "--reporter", "default", "--outputFile.blob", str(fixture.blob)]
        self.assertEqual(owner.observe_vitest(fixture.repo, arguments, fixture.raw, fixture.output,
                                              execution_cwd="plugins/fixture/tools"), 0)
        calls = json.loads(fixture.counter.read_text())
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["cwd"], str(fixture.project))
        self.assertEqual(calls[0]["argv"][:len(arguments)-3], arguments[3:])
        observed = owner.load_json(fixture.output)
        self.assertEqual(observed["cwd"], str(fixture.project))
        self.assertEqual(observed["original_argv"], arguments)
        self.assertEqual(observed["raw_results_sha256"], owner.hashlib.sha256(fixture.raw.read_bytes()).hexdigest())
        self.assertEqual(fixture.blob.read_text(), "opaque original blob")

    def test_cli_project_cwd_is_forwarded_without_changing_original_flags(self):
        fixture = self.invocation_fixture()
        original = [sys.executable, "-B", str(fixture.runner), "run", "--reporters=json",
                    "--outputFile.json", str(fixture.raw)]
        self.assertEqual(owner.main(["observe-vitest", "--repo", str(fixture.repo),
            "--execution-cwd", str(fixture.project), "--raw-results", str(fixture.raw),
            "--output", str(fixture.output), "--", *original]), 0)
        observed = owner.load_json(fixture.output)
        self.assertEqual(observed["argv"], original)
        self.assertEqual(observed["original_argv"], original)
        self.assertEqual(len(json.loads(fixture.counter.read_text())), 1)
        self.assertEqual(observed["cwd"], str(fixture.project))

    def test_duplicate_conflicting_json_ownership_refuses_before_execution(self):
        variants = [lambda f: ["--reporter=json", "--reporter=json"],
            lambda f: ["--reporter=json", "--reporters=json"],
            lambda f: ["--reporter=json", "--outputFile="+str(f.raw), "--outputFile.json="+str(f.raw)],
            lambda f: ["--outputFile.json="+str(f.raw), "--outputFile.json="+str(f.raw)],
            lambda f: ["--reporter=json", "--outputFile.json="+str(f.base/"wrong.json")],
            lambda f: ["--reporter=blob", "--outputFile.blob="+str(f.raw)],
            lambda f: ["--reporter=blob", "--outputFile="+str(f.blob)],
            lambda f: ["--reporter"], lambda f: ["--outputFile.json"]]
        for index, variant in enumerate(variants):
            with self.subTest(vector=index):
                f = self.invocation_fixture()
                with self.assertRaises(ValueError):
                    owner.observe_vitest(f.repo, [sys.executable, "-B", str(f.runner), *variant(f)], f.raw, f.output)
                self.assertFalse(f.counter.exists())
                self.assertFalse(f.output.exists())

    def test_stale_or_linked_json_and_observation_paths_refuse_before_execution(self):
        for vector in ("stale-result", "stale-observation", "linked-result", "same-output"):
            with self.subTest(vector=vector):
                f = self.invocation_fixture()
                target = f.output
                if vector == "stale-result": f.raw.write_text(json.dumps(f.named))
                if vector == "stale-observation": f.output.write_text("{}")
                if vector == "linked-result":
                    other=f.base/"foreign.json";other.write_text(json.dumps(f.named));f.raw.symlink_to(other)
                if vector == "same-output": target=f.raw
                with self.assertRaises(ValueError):
                    owner.observe_vitest(f.repo, [sys.executable, "-B", str(f.runner)], f.raw, target)
                self.assertFalse(f.counter.exists())

    def test_missing_replaced_hardlinked_or_oversize_results_cannot_be_admitted(self):
        for mode in ("missing", "replaced", "hardlinked", "oversize"):
            with self.subTest(mode=mode):
                f=self.invocation_fixture(mode=mode)
                with self.assertRaises((ValueError, OSError)):
                    owner.observe_vitest(f.repo, [sys.executable, "-B", str(f.runner)], f.raw, f.output)
                self.assertEqual(len(json.loads(f.counter.read_text())), 1)
                self.assertFalse(f.output.exists())

        # Exercise the replacement-identity check itself even where Windows
        # refuses renaming the wrapper-held open file before the child exits.
        f=self.invocation_fixture()
        f.raw.write_text(json.dumps(f.named))
        original=f.raw.stat()
        f.raw.rename(f.base/"old-owned.json")
        f.raw.write_text(json.dumps(f.named))
        descriptor=os.open(f.raw,os.O_RDONLY | getattr(os,"O_BINARY",0))
        try:
            with self.assertRaisesRegex(ValueError,"replaced, linked or exceeds bound"):
                owner._vitest_owned_json(f.raw,descriptor,original)
        finally:
            os.close(descriptor)

    def test_malformed_duplicate_or_outside_named_json_is_not_a_named_pass(self):
        variants = [lambda sample: {"testResults": [{"name":str(sample),"assertionResults":[{"fullName":"same","status":"passed"}]*2}]},
            lambda sample: {"testResults": [{"name":str(sample),"assertionResults":[{"fullName":"","status":"passed"}]}]},
            lambda sample: {"testResults": [{"name":str(sample),"assertionResults":[{"fullName":"name","status":{}}]}]},
            lambda sample: {"testResults": [{"name":str(sample.parents[4]/"outside.test.ts"),"assertionResults":[{"fullName":"name","status":"passed"}]}]},
            lambda sample: {"testResults": []}, lambda sample: {"blobGraph":"not named JSON"}]
        for index, document in enumerate(variants):
            with self.subTest(vector=index):
                f=self.invocation_fixture(document=document)
                with self.assertRaises(ValueError):
                    owner.observe_vitest(f.repo, [sys.executable, "-B", str(f.runner)], f.raw, f.output)
                self.assertEqual(len(json.loads(f.counter.read_text())),1)
                self.assertFalse(f.output.exists())

    def test_pending_failed_exit_and_source_drift_remain_nonqualifying_observations(self):
        for status, exit_code, drift in [("pending",0,False),("failed",7,False),("passed",0,True)]:
            with self.subTest(status=status,exit_code=exit_code,drift=drift):
                document=lambda sample:{"testResults":[{"name":str(sample),"assertionResults":[{"fullName":"original","status":status}]}]}
                f=self.invocation_fixture(document=document,exit_code=exit_code,drift=drift)
                self.assertEqual(owner.observe_vitest(f.repo,[sys.executable,"-B",str(f.runner)],f.raw,f.output),exit_code)
                observed=owner.load_json(f.output)
                self.assertEqual(observed["tests"][0]["result"],"skipped" if status=="pending" else status)
                self.assertEqual(observed["exit_code"],exit_code)
                self.assertEqual(observed["source_stable"],not drift)
                self.assertEqual(len(json.loads(f.counter.read_text())),1)

    def test_outside_nonexistent_and_reparse_project_cwd_refuse_before_execution(self):
        for vector in ("outside","missing","file","linked"):
            with self.subTest(vector=vector):
                f=self.invocation_fixture()
                cwd={"outside":f.base,"missing":f.repo/"missing","file":f.runner}.get(vector)
                if vector=="linked":
                    cwd=f.repo/"linked-project";cwd.symlink_to(f.project,target_is_directory=True)
                with self.assertRaises(ValueError):
                    owner.observe_vitest(f.repo,[sys.executable,"-B",str(f.runner)],f.raw,f.output,execution_cwd=cwd)
                self.assertFalse(f.counter.exists())

    def test_timeout_keeps_original_containment_and_never_writes_a_pass(self):
        f=self.invocation_fixture()
        process=SimpleNamespace(wait=mock.Mock(side_effect=subprocess.TimeoutExpired("owned inert",1200)))
        with mock.patch.object(owner,"start_process",return_value=process) as start, \
             mock.patch.object(owner,"terminate_tree",return_value="confirmed") as terminate:
            with self.assertRaisesRegex(ValueError,"timed out; containment=confirmed"):
                owner.observe_vitest(f.repo,[sys.executable,"-B",str(f.runner)],f.raw,f.output)
        process.wait.assert_called_once_with(timeout=1200)
        start.assert_called_once();terminate.assert_called_once_with(process)
        self.assertFalse(f.output.exists())




class SourceFixtureDiagnosticTests(unittest.TestCase):
    def test_index_timeout_retains_closed_note_and_original_error_before_cleanup(self):
        problem=subprocess.TimeoutExpired(["git","add","."],15,output=b"PRIVATE_STDOUT_CANARY",stderr=b"PRIVATE_STDERR_CANARY")
        calls=[];trace_paths=[];real_run=subprocess.run
        def run(argv,**kwargs):
            calls.append((argv,kwargs))
            if argv[-2:]==["add","."]:
                value=kwargs.get("env",os.environ).get("GIT_TRACE2_EVENT")
                if value:
                    trace=Path(value);trace_paths.append(trace)
                    trace.write_text(json.dumps({"event":"region_enter","category":"index","label":"do_read_index","t_rel":0.125,
                        "argv":["PRIVATE_TRACE_CANARY"],"path":"PRIVATE_PATH_CANARY"})+"\n",newline="\n")
                raise problem
            return real_run(argv,**kwargs)
        with mock.patch.object(subprocess,"run",side_effect=run):
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                with source_payload_fixture():self.fail("setup unexpectedly succeeded")
        self.assertIs(caught.exception,problem)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[-1][0][-2:],["add","."])
        self.assertTrue(all(options["timeout"]==15 and options["check"] and options["capture_output"] for _,options in calls))
        notes=getattr(problem,"__notes__",[])
        self.assertTrue(notes,"fixture Git timeout lost the closed phase diagnostic before cleanup")
        note=next(item for item in notes if item.startswith("Fixture Git diagnostic: "))
        diagnostic=json.loads(note.removeprefix("Fixture Git diagnostic: "))
        self.assertEqual(diagnostic["phase"],"index")
        self.assertEqual(diagnostic["failure"],"timeout")
        self.assertEqual(diagnostic["trace"]["events"][0]["event"],"region_enter")
        for secret in ("PRIVATE_STDOUT_CANARY","PRIVATE_STDERR_CANARY","PRIVATE_TRACE_CANARY","PRIVATE_PATH_CANARY"):
            self.assertNotIn(secret,note)
        self.assertTrue(trace_paths)
        self.assertTrue(all(not path.exists() for path in trace_paths))

    def test_real_success_keeps_three_commands_and_trace_outside_clean_source(self):
        real_run=subprocess.run;calls=[]
        def run(argv,**kwargs):
            if "-C" in argv and argv[-1:] in (["."],["source payload fixture"],["-q"]):
                calls.append((list(argv),kwargs))
            return real_run(argv,**kwargs)
        with mock.patch.object(subprocess,"run",side_effect=run):
            with source_payload_fixture() as fixture:
                traces=sorted(fixture["base"].glob("fixture-git-*.trace.jsonl"))
                self.assertEqual(len(traces),3)
                self.assertTrue(all(path.parent==fixture["base"] and path.stat().st_size>0 for path in traces))
                self.assertTrue(owner.source_identity(fixture["repo"])["clean"])
        self.assertEqual(len(calls),3)
        self.assertEqual([argv[-2:] for argv,_ in calls[:2]],[["init","-q"],["add","."]])
        self.assertTrue(all(options["timeout"]==15 and options["check"] and options["capture_output"] for _,options in calls))

    def test_projection_drops_unsafe_fields_and_rejects_malformed_nonfinite_data(self):
        import _git_fixture_diagnostics as diagnostics
        safe={"event":"region_enter","category":"index","label":"do_read_index","t_rel":0.125,"nesting":1,
              "argv":["PRIVATE_TRACE_CANARY"],"path":"PRIVATE_PATH_CANARY"}
        projected=diagnostics._project((json.dumps(safe)+"\n").encode())
        self.assertEqual(projected["events"],[{"event":"region_enter","category":"index","label":"do_read_index","t_rel":0.125,"nesting":1}])
        self.assertEqual(len(projected["unknown_sha256"]),1)
        for raw in (b'{"event":"region_enter","t_rel":NaN}',b'{"event":"region_enter","t_rel":Infinity}',
                    b'{"event":"region_enter","t_rel":true}',b'{"event":"start","event":"exit"}',
                    b'not-json-PRIVATE_TRACE_CANARY',b'{"event":["PRIVATE_TRACE_CANARY"]}'):
            with self.subTest(raw_hash=owner.readiness.digest(raw)):
                value=diagnostics._project(raw)
                self.assertEqual(value["status"],"invalid")
                self.assertEqual(value["events"],[])
                self.assertNotIn("PRIVATE_TRACE_CANARY",json.dumps(value))
        secret={"event":"data","category":"PRIVATE_CATEGORY_CANARY","label":"PRIVATE_LABEL_CANARY","value":"PRIVATE_VALUE_CANARY"}
        value=diagnostics._project(json.dumps(secret).encode())
        self.assertEqual(value["events"],[{"event":"data","category":"other","label":"other"}])
        self.assertNotIn("CANARY",json.dumps(value))

    def test_owned_reader_refuses_large_linked_and_reparse_sources_before_open(self):
        import _git_fixture_diagnostics as diagnostics
        with tempfile.TemporaryDirectory(prefix="ca-trace-owned-") as directory:
            root=Path(directory);trace=root/"trace.jsonl"
            trace.write_bytes(b"x"*(diagnostics.MAX_TRACE_BYTES+1))
            with mock.patch.object(diagnostics.os,"open") as opened:
                self.assertEqual(diagnostics._read_trace(trace,root)["status"],"over_limit")
                opened.assert_not_called()
            trace.unlink();other=root/"other";other.write_bytes(b'{"event":"start"}\n')
            os.link(other,trace)
            with mock.patch.object(diagnostics.os,"open") as opened:
                self.assertEqual(diagnostics._read_trace(trace,root)["status"],"unavailable")
                opened.assert_not_called()
            trace.unlink();trace.write_bytes(b'{"event":"start"}\n')
            original=Path.lstat
            def lstat(path,*args,**kwargs):
                info=original(path,*args,**kwargs)
                if path==trace:
                    return SimpleNamespace(st_mode=info.st_mode,st_nlink=info.st_nlink,st_size=info.st_size,
                        st_file_attributes=0x400)
                return info
            with mock.patch.object(Path,"lstat",lstat),mock.patch.object(diagnostics.os,"open") as opened:
                self.assertEqual(diagnostics._read_trace(trace,root)["status"],"unavailable")
                opened.assert_not_called()

    def test_event_and_note_caps_never_reflect_unknown_payloads(self):
        import _git_fixture_diagnostics as diagnostics
        record={"event":"region_enter","category":"index","label":"do_read_index","t_rel":0.5,"secret":"PRIVATE_TRACE_CANARY"}
        raw=((json.dumps(record)+"\n")*(diagnostics.MAX_LINES+20)).encode()
        value=diagnostics._project(raw)
        self.assertEqual(value["status"],"truncated")
        self.assertEqual(len(value["events"]),diagnostics.MAX_EVENTS)
        self.assertLessEqual(len(value["unknown_sha256"]),8)
        self.assertGreater(value["dropped"],0)
        with mock.patch.object(diagnostics,"_read_trace",return_value=value):
            note=diagnostics._failure_note(subprocess.TimeoutExpired("owned",15),"index",None,None,None)
        self.assertLessEqual(len(note.encode()),diagnostics.MAX_NOTE_BYTES)
        self.assertNotIn("PRIVATE_TRACE_CANARY",note)

    def test_diagnostic_setup_or_note_failure_preserves_original_process_error(self):
        import _git_fixture_diagnostics as diagnostics
        for broken in ("_prepare_trace","_failure_note"):
            problem=subprocess.CalledProcessError(7,["git","add","."],output=b"PRIVATE_STDOUT_CANARY",stderr=b"PRIVATE_STDERR_CANARY")
            before=dict(os.environ)
            with tempfile.TemporaryDirectory(prefix="ca-trace-failure-") as directory, \
                 mock.patch.object(diagnostics,broken,side_effect=RuntimeError("PRIVATE_DIAG_CANARY")), \
                 mock.patch.object(diagnostics.subprocess,"run",side_effect=problem) as run:
                with self.assertRaises(subprocess.CalledProcessError) as caught:
                    diagnostics.run_git_phase(["git","add","."],phase="index",trace_dir=directory)
                self.assertIs(caught.exception,problem)
                run.assert_called_once()
                self.assertEqual(run.call_args.kwargs["timeout"],15)
                self.assertEqual(dict(os.environ),before)
                self.assertNotIn("CANARY","\n".join(getattr(problem,"__notes__",[])))


TS_PROFILE_FIXTURES = {'pi-tools-v1': {'job': 'Coverage union (Pi)  <os: windows-latest>',
                 'paths': ['.github/major-qualification-policy.json',
                           '.github/major-test-selections.json',
                           '.github/scripts/_boundedproc.py',
                           '.github/scripts/_contextverificationlib.py',
                           '.github/scripts/_immutable_git_blobs.py',
                           '.github/scripts/ci20_native_binding.py',
                           '.github/scripts/major_qualification_report.py',
                           '.github/scripts/major_readiness.py',
                           '.github/workflows/ci.yml',
                           'core/hosts.json',
                           'core/pysrc/_artifactauthoritylib.py',
                           'core/pysrc/_artifactlib.py',
                           'core/pysrc/_artifactmanifestlib.py',
                           'core/pysrc/_artifactpromptlib.py',
                           'core/pysrc/_gitexec.py',
                           'core/pysrc/_replylib.py',
                           'plugins/ca-pi/extensions/codearbiter-child.js',
                           'plugins/ca-pi/extensions/codearbiter.js',
                           'plugins/ca-pi/tools/build.mjs',
                           'plugins/ca-pi/tools/package-lock.json',
                           'plugins/ca-pi/tools/package.json',
                           'plugins/ca-pi/tools/src/activation.ts',
                           'plugins/ca-pi/tools/src/activity.ts',
                           'plugins/ca-pi/tools/src/approval-dialog.ts',
                           'plugins/ca-pi/tools/src/approval-entry.ts',
                           'plugins/ca-pi/tools/src/attestation.ts',
                           'plugins/ca-pi/tools/src/audit-sink.ts',
                           'plugins/ca-pi/tools/src/background-jobs.ts',
                           'plugins/ca-pi/tools/src/bridge.ts',
                           'plugins/ca-pi/tools/src/child-env.ts',
                           'plugins/ca-pi/tools/src/child-extension.ts',
                           'plugins/ca-pi/tools/src/command-ownership.ts',
                           'plugins/ca-pi/tools/src/commands.ts',
                           'plugins/ca-pi/tools/src/compaction.ts',
                           'plugins/ca-pi/tools/src/compatibility.ts',
                           'plugins/ca-pi/tools/src/contracts.ts',
                           'plugins/ca-pi/tools/src/delegated-executor.ts',
                           'plugins/ca-pi/tools/src/delegation-client.ts',
                           'plugins/ca-pi/tools/src/delegation-contract.ts',
                           'plugins/ca-pi/tools/src/delegation-journal.ts',
                           'plugins/ca-pi/tools/src/delegation-session.ts',
                           'plugins/ca-pi/tools/src/dispatch.ts',
                           'plugins/ca-pi/tools/src/doctor.ts',
                           'plugins/ca-pi/tools/src/extension.ts',
                           'plugins/ca-pi/tools/src/farm.ts',
                           'plugins/ca-pi/tools/src/footer-state.ts',
                           'plugins/ca-pi/tools/src/footer.ts',
                           'plugins/ca-pi/tools/src/git-facts.ts',
                           'plugins/ca-pi/tools/src/inference-broker.ts',
                           'plugins/ca-pi/tools/src/native-background.ts',
                           'plugins/ca-pi/tools/src/native-plan.ts',
                           'plugins/ca-pi/tools/src/notices.ts',
                           'plugins/ca-pi/tools/src/parent-delegation.ts',
                           'plugins/ca-pi/tools/src/path-boundary.ts',
                           'plugins/ca-pi/tools/src/pi-api.d.ts',
                           'plugins/ca-pi/tools/src/plan-mode.ts',
                           'plugins/ca-pi/tools/src/policy.ts',
                           'plugins/ca-pi/tools/src/process-tree.ts',
                           'plugins/ca-pi/tools/src/redaction.ts',
                           'plugins/ca-pi/tools/src/roles.ts',
                           'plugins/ca-pi/tools/src/runner.ts',
                           'plugins/ca-pi/tools/src/runtime-resolver.ts',
                           'plugins/ca-pi/tools/src/session-identity.ts',
                           'plugins/ca-pi/tools/src/sidebar-compositor.ts',
                           'plugins/ca-pi/tools/src/sidebar-data.ts',
                           'plugins/ca-pi/tools/src/sidebar-manager.ts',
                           'plugins/ca-pi/tools/src/sidebar.ts',
                           'plugins/ca-pi/tools/src/status.ts',
                           'plugins/ca-pi/tools/src/tool-guard.ts',
                           'plugins/ca-pi/tools/src/windows-supervisor.ts',
                           'plugins/ca-pi/tools/test/activation.test.ts',
                           'plugins/ca-pi/tools/test/activity.test.ts',
                           'plugins/ca-pi/tools/test/approval-dialog.test.ts',
                           'plugins/ca-pi/tools/test/audit-sink.test.ts',
                           'plugins/ca-pi/tools/test/background-jobs.test.ts',
                           'plugins/ca-pi/tools/test/benchmark-boundary.ts',
                           'plugins/ca-pi/tools/test/bridge.test.ts',
                           'plugins/ca-pi/tools/test/child-env.test.ts',
                           'plugins/ca-pi/tools/test/commands.test.ts',
                           'plugins/ca-pi/tools/test/compaction.test.ts',
                           'plugins/ca-pi/tools/test/delegated-executor.test.ts',
                           'plugins/ca-pi/tools/test/delegation-contract.test.ts',
                           'plugins/ca-pi/tools/test/delegation-journal.test.ts',
                           'plugins/ca-pi/tools/test/delegation-session.test.ts',
                           'plugins/ca-pi/tools/test/dispatch.test.ts',
                           'plugins/ca-pi/tools/test/doctor.test.ts',
                           'plugins/ca-pi/tools/test/farm.test.ts',
                           'plugins/ca-pi/tools/test/final-arguments-live.test.ts',
                           'plugins/ca-pi/tools/test/final-arguments.test.ts',
                           'plugins/ca-pi/tools/test/fixtures/live-governed-extension.mjs',
                           'plugins/ca-pi/tools/test/fixtures/live-later-extension.mjs',
                           'plugins/ca-pi/tools/test/fixtures/pi-0.80.5-help.txt',
                           'plugins/ca-pi/tools/test/fixtures/pi-0.80.6-help.txt',
                           'plugins/ca-pi/tools/test/footer.test.ts',
                           'plugins/ca-pi/tools/test/git-facts.test.ts',
                           'plugins/ca-pi/tools/test/inference-broker.test.ts',
                           'plugins/ca-pi/tools/test/live-pi-host.ts',
                           'plugins/ca-pi/tools/test/module-structure.test.ts',
                           'plugins/ca-pi/tools/test/notices.test.ts',
                           'plugins/ca-pi/tools/test/package.test.ts',
                           'plugins/ca-pi/tools/test/parent-delegation.test.ts',
                           'plugins/ca-pi/tools/test/path-boundary.test.ts',
                           'plugins/ca-pi/tools/test/plan-mode.test.ts',
                           'plugins/ca-pi/tools/test/policy.test.ts',
                           'plugins/ca-pi/tools/test/process-tree.test.ts',
                           'plugins/ca-pi/tools/test/runner-broker-lifecycle.test.ts',
                           'plugins/ca-pi/tools/test/runner-isolation.test.ts',
                           'plugins/ca-pi/tools/test/runtime-resolver.test.ts',
                           'plugins/ca-pi/tools/test/security.test.ts',
                           'plugins/ca-pi/tools/test/setup-disposable-home.ts',
                           'plugins/ca-pi/tools/test/sidebar-compositor.test.ts',
                           'plugins/ca-pi/tools/test/sidebar-data.test.ts',
                           'plugins/ca-pi/tools/test/sidebar-manager.test.ts',
                           'plugins/ca-pi/tools/test/sidebar-probe-live.test.ts',
                           'plugins/ca-pi/tools/test/sidebar-window-contract.test.ts',
                           'plugins/ca-pi/tools/test/sidebar.test.ts',
                           'plugins/ca-pi/tools/test/status.test.ts',
                           'plugins/ca-pi/tools/test/tool-guard.test.ts',
                           'plugins/ca-pi/tools/test/windows-supervisor.test.ts',
                           'plugins/ca-pi/tools/test/workflow-recovery.test.ts',
                           'plugins/ca-pi/tools/tsconfig.json',
                           'plugins/ca-pi/tools/vitest.config.ts',
                           'plugins/ca/hooks/secret-detection-corpus.json',
                           'plugins/ca/tools/redactor.ts'],
                 'payload': 'major-source-inputs-pi-windows-coverage',
                 'root': 'plugins/ca-pi/tools',
                 'test': 'plugins/ca-pi/tools/test/security.test.ts'},
 'sandbox-tools-v1': {'job': '[CHECK] | [SBX ] | Sandbox driver contract',
                      'paths': ['.github/major-qualification-policy.json',
                                '.github/major-test-selections.json',
                                '.github/scripts/_boundedproc.py',
                                '.github/scripts/_contextverificationlib.py',
                                '.github/scripts/_immutable_git_blobs.py',
                                '.github/scripts/ci20_native_binding.py',
                                '.github/scripts/major_qualification_report.py',
                                '.github/scripts/major_readiness.py',
                                '.github/workflows/ci.yml',
                                'core/pysrc/_artifactauthoritylib.py',
                                'core/pysrc/_artifactlib.py',
                                'core/pysrc/_artifactmanifestlib.py',
                                'core/pysrc/_artifactpromptlib.py',
                                'core/pysrc/_gitexec.py',
                                'core/pysrc/_replylib.py',
                                'plugins/ca-sandbox/tools/__fixtures__/docker-required/gate.fixture.test.ts',
                                'plugins/ca-sandbox/tools/__fixtures__/docker-required/vitest.config.ts',
                                'plugins/ca-sandbox/tools/__fixtures__/go/go.mod',
                                'plugins/ca-sandbox/tools/__fixtures__/go/main.go',
                                'plugins/ca-sandbox/tools/__fixtures__/node/index.js',
                                'plugins/ca-sandbox/tools/__fixtures__/node/package.json',
                                'plugins/ca-sandbox/tools/__fixtures__/py/main.py',
                                'plugins/ca-sandbox/tools/__fixtures__/py/requirements.txt',
                                'plugins/ca-sandbox/tools/__fixtures__/rust/Cargo.lock',
                                'plugins/ca-sandbox/tools/__fixtures__/rust/Cargo.toml',
                                'plugins/ca-sandbox/tools/__fixtures__/rust/src/main.rs',
                                'plugins/ca-sandbox/tools/__tests__/isolation.test.ts',
                                'plugins/ca-sandbox/tools/build-pinned-base.test.ts',
                                'plugins/ca-sandbox/tools/build.test.ts',
                                'plugins/ca-sandbox/tools/build.ts',
                                'plugins/ca-sandbox/tools/builder-observation.test.ts',
                                'plugins/ca-sandbox/tools/cache-provenance.test.ts',
                                'plugins/ca-sandbox/tools/claude-inside-cli.test.ts',
                                'plugins/ca-sandbox/tools/claude-inside-cli.ts',
                                'plugins/ca-sandbox/tools/claude-inside.js',
                                'plugins/ca-sandbox/tools/claude-inside.test.ts',
                                'plugins/ca-sandbox/tools/claude-inside.ts',
                                'plugins/ca-sandbox/tools/cli-resolve.test.ts',
                                'plugins/ca-sandbox/tools/cli.test.ts',
                                'plugins/ca-sandbox/tools/cli.ts',
                                'plugins/ca-sandbox/tools/cp.test.ts',
                                'plugins/ca-sandbox/tools/cp.ts',
                                'plugins/ca-sandbox/tools/create-failure-diagnostics.test.ts',
                                'plugins/ca-sandbox/tools/create-partial-compensation.test.ts',
                                'plugins/ca-sandbox/tools/create.test.ts',
                                'plugins/ca-sandbox/tools/create.ts',
                                'plugins/ca-sandbox/tools/deadline.test.ts',
                                'plugins/ca-sandbox/tools/dephash.test.ts',
                                'plugins/ca-sandbox/tools/dephash.ts',
                                'plugins/ca-sandbox/tools/destroy.ts',
                                'plugins/ca-sandbox/tools/docker-gate.test.ts',
                                'plugins/ca-sandbox/tools/docker-gate.ts',
                                'plugins/ca-sandbox/tools/docker.ts',
                                'plugins/ca-sandbox/tools/exec.test.ts',
                                'plugins/ca-sandbox/tools/exec.ts',
                                'plugins/ca-sandbox/tools/installed-bundle.test.ts',
                                'plugins/ca-sandbox/tools/layering.test.ts',
                                'plugins/ca-sandbox/tools/lifecycle.test.ts',
                                'plugins/ca-sandbox/tools/mounts.test.ts',
                                'plugins/ca-sandbox/tools/mounts.ts',
                                'plugins/ca-sandbox/tools/multistack.test.ts',
                                'plugins/ca-sandbox/tools/native-build-inputs.test.ts',
                                'plugins/ca-sandbox/tools/network.test.ts',
                                'plugins/ca-sandbox/tools/network.ts',
                                'plugins/ca-sandbox/tools/package-lock.json',
                                'plugins/ca-sandbox/tools/package.json',
                                'plugins/ca-sandbox/tools/registry.ts',
                                'plugins/ca-sandbox/tools/run.test.ts',
                                'plugins/ca-sandbox/tools/run.ts',
                                'plugins/ca-sandbox/tools/sandbox.js',
                                'plugins/ca-sandbox/tools/smoke.test.ts',
                                'plugins/ca-sandbox/tools/smoke.ts',
                                'plugins/ca-sandbox/tools/state-contracts.test.ts',
                                'plugins/ca-sandbox/tools/supply-chain.test.ts',
                                'plugins/ca-sandbox/tools/teardown.test.ts',
                                'plugins/ca-sandbox/tools/tsconfig.json',
                                'plugins/ca-sandbox/tools/vitest.config.ts'],
                      'payload': 'major-source-inputs-sandbox-driver',
                      'root': 'plugins/ca-sandbox/tools',
                      'test': 'plugins/ca-sandbox/tools/cli.test.ts'}}

@contextmanager
def vitest_source_fixture(profile="pi-tools-v1"):
    """Real private checkout/archive and inert once-only named JSON process."""
    with tempfile.TemporaryDirectory(prefix="ca-ts-source-fixture-") as temporary:
        base = Path(temporary).resolve(); repo = base / "repo"; repo.mkdir()
        spec = TS_PROFILE_FIXTURES[profile]
        for relative in spec["paths"]:
            target = repo / relative; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"inert declared source fixture\n")
        (repo / ".gitignore").write_text(spec["root"] + "/node_modules/\n" + spec["root"] + "/coverage/\n", encoding="utf-8")
        git = shutil.which("git")
        if git is None: raise AssertionError("Git required for private source fixture")
        env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT"}}
        env.update(PATH=os.pathsep.join([str(Path(git).parent), str(Path(sys.executable).parent)]),
            HOME=str(base), USERPROFILE=str(base), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0", GITHUB_RUN_ID="7", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
        with mock.patch.dict(os.environ, env, clear=True):
            for args in (("init", "-q"), ("add", "."), ("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                           "-c", "commit.gpgsign=false", "commit", "-qm", "source fixture")):
                phase = "init" if args[0] == "init" else "index" if args[0] == "add" else "commit"
                run_git_phase([git, "-C", str(repo), *args], phase=phase, trace_dir=base)
            identity = owner.source_identity(repo)
            staged = base / "staged"; staged.mkdir()
            rows = []
            for relative in spec["paths"]:
                value = (repo / relative).read_bytes(); target = staged / relative
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(value)
                rows.append({"path": relative, "sha256": owner.readiness.digest(value), "bytes": len(value), "git_mode": "100644"})
            manifest = {"format": owner.SOURCE_FORMAT, "profile": profile, "workflow": ".github/workflows/ci.yml",
                "source_commit": identity["source_commit"], "source_tree": identity["source_tree"], "ci_run_id": 7,
                "producer_job_name": spec["job"], "members": rows}
            owner.new_output(staged / owner.SOURCE_MANIFEST, manifest)
            raw, observation, counter = base / "named.json", base / "observation.json", base / "counter.json"
            program = base / "inert-original.py"
            suite = str(repo / spec["test"])
            program.write_text("import pathlib,json,sys,os\n"
                f"p=pathlib.Path({str(counter)!r});rows=json.loads(p.read_text())if p.exists()else[]\n"
                "rows.append({'argv':sys.argv[1:],'cwd':os.getcwd(),'token_present':bool(os.environ.get('GH_TOKEN')or os.environ.get('OPENAI_API_KEY'))});p.write_text(json.dumps(rows))\n"
                "args=sys.argv[1:];out=next(a.split('=',1)[1]for a in args if a.startswith(('--outputFile.json=','--outputFile=')))\n"
                f"pathlib.Path(out).write_text(json.dumps({{'testResults':[{{'name':{suite!r},'assertionResults':[{{'fullName':'owned inert original case','status':'passed'}}]}}]}}))\n", encoding="utf-8")
            command = [sys.executable, "-B", str(program), "--coverage", "--reporter=blob", "--reporter=default", "--outputFile.blob=original.blob"]
            yield {"base": base, "repo": repo, "spec": spec, "staged": staged, "manifest": manifest,
                "identity": identity, "raw": raw, "observation": observation, "counter": counter, "command": command}


class VitestSourceProducerTests(unittest.TestCase):
    def test_original_vitest_invocation_retains_authenticated_source_binding_once(self):
        for profile in TS_PROFILE_FIXTURES:
            with self.subTest(profile=profile), vitest_source_fixture(profile) as f:
                args = ["observe-vitest", "--repo", str(f["repo"]), "--output", str(f["observation"]),
                    "--raw-results", str(f["raw"]), "--source-payload", str(f["staged"]),
                    "--execution-cwd", f["spec"]["root"], "--", *f["command"]]
                self.assertEqual(owner.main(args), 0)
                self.assertEqual(len(json.loads(f["counter"].read_text())), 1)
                document = owner.load_json(f["observation"])
                self.assertEqual(document["original_argv"], f["command"])
                self.assertEqual(document["cwd"], str(f["repo"] / f["spec"]["root"]))
                self.assertEqual(document.get("source_input_binding"), {
                    "format": owner.SOURCE_BINDING, "profile": profile,
                    "payload_name": f["spec"]["payload"],
                    "manifest_sha256": owner.readiness.digest((f["staged"] / owner.SOURCE_MANIFEST).read_bytes())})

    def authenticate(self, f, mutate=None, job=None):
        files = {p.relative_to(f["staged"]).as_posix(): p.read_bytes() for p in f["staged"].rglob("*") if p.is_file()}
        if mutate: mutate(files)
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            for name, value in sorted(files.items()): archive.writestr(name, value)
        metadata = {"id": 8, "name": f["spec"]["payload"]}
        req = {**f["identity"], "ci_run_id": 7}
        job = job if job is not None else {"id": 9, "name": f["spec"]["job"], "status": "in_progress", "conclusion": None,
            "steps": [{"name": "Upload Pi source-test inputs" if f["spec"]["root"].endswith("ca-pi/tools") else "Upload Sandbox source-test inputs", "status": "completed", "conclusion": "success"}]}
        with mock.patch.object(owner.readiness, "artifact_bytes", return_value=raw.getvalue()) as authenticated, \
             mock.patch.object(owner.readiness, "validate_upload", side_effect=AssertionError("own incomplete log must not be read")):
            result = owner.authenticated_payload(metadata, req, f["repo"], source_job=job)
            authenticated.assert_called_once_with(metadata, req)
            return result

    def test_closed_profiles_stage_exact_consumed_members_and_admit_only_four_cells(self):
        cells = {"pi-tools-v1": "disposition:transitions:pi-qualification:disposable-home:01",
                 "sandbox-tools-v1": "disposition:transitions:S54:01"}
        for profile in TS_PROFILE_FIXTURES:
            with self.subTest(profile=profile), vitest_source_fixture(profile) as f:
                stage = f["base"] / "prepared"
                self.assertEqual(owner.prepare_source_payload(f["repo"], stage, f["spec"]["job"], profile), f["manifest"])
                self.assertEqual(owner.observe_vitest(f["repo"], f["command"], f["raw"], f["observation"], f["spec"]["root"], f["staged"]), 0)
                observed = owner.load_json(f["observation"])
                payload = self.authenticate(f)
                cell = cells[profile]
                req = {**f["identity"], "ci_run_id": 7, "cells": [cell], "cell_jobs": {cell: f["spec"]["job"]}}
                group = {"id": "synthetic-source", "job": f["spec"]["job"], "payload_name": f["spec"]["payload"],
                    "observation": "owning", "proof_kind": "source-test", "selectors": [observed["tests"][0]["id"]],
                    "cells": [cell], "scope": "Inert source-admission fixture only; no actual TypeScript qualification"}
                def build(o=observed, p=payload, gr=group, required=req):
                    return owner.build_report(required, job_name=f["spec"]["job"], job_id=9,
                        selections={"schema": owner.SELECTIONS, "groups": [gr]}, observations={"owning": o}, payloads={f["spec"]["payload"]: p})
                self.assertEqual(build()["results"][0]["cell"], cell)
                for failure in ("missing-binding", "unknown-profile", "wrong-role", "digest", "uploader", "pending", "failure", "duplicate", "dirty", "nonzero", "other-cell"):
                    bad, consumed, selected, required = copy.deepcopy(observed), copy.deepcopy(payload), copy.deepcopy(group), copy.deepcopy(req)
                    if failure == "missing-binding": bad.pop("source_input_binding")
                    if failure == "unknown-profile": bad["source_input_binding"]["profile"] = "unknown-ts-profile"
                    if failure == "wrong-role": selected["payload_name"] = "unrelated-native-archive"
                    if failure == "digest": consumed["source_manifest_sha256"] = "0" * 64
                    if failure == "uploader": consumed["source_upload_job_id"] = True
                    if failure == "pending": bad["tests"][0]["result"] = "skipped"
                    if failure == "failure": bad["tests"][0]["result"] = "failed"
                    if failure == "duplicate": bad["tests"].append(dict(bad["tests"][0]))
                    if failure == "dirty": bad["source_stable"] = False
                    if failure == "nonzero": bad["exit_code"] = 1
                    if failure == "other-cell":
                        selected["cells"] = required["cells"] = ["disposition:transitions:S51:01"]
                        required["cell_jobs"] = {required["cells"][0]: f["spec"]["job"]}
                    with self.subTest(failure=failure), self.assertRaises(ValueError): build(bad, consumed, selected, required)

    def test_archive_profile_source_member_and_original_upload_fail_closed(self):
        for profile in TS_PROFILE_FIXTURES:
            with self.subTest(profile=profile), vitest_source_fixture(profile) as f:
                for failure in ("changed", "missing", "foreign", "profile", "source", "duplicate-json"):
                    def mutate(files):
                        first = f["spec"]["paths"][0]
                        if failure == "changed": files[first] += b"changed"
                        if failure == "missing": del files[first]
                        if failure == "foreign": files["foreign-input"] = b"inert"
                        if failure in ("profile", "source"):
                            manifest = json.loads(files[owner.SOURCE_MANIFEST]); manifest["profile" if failure == "profile" else "source_commit"] = "foreign" if failure == "profile" else "f" * 40
                            files[owner.SOURCE_MANIFEST] = json.dumps(manifest).encode()
                        if failure == "duplicate-json": files[owner.SOURCE_MANIFEST] = b'{"profile":"pi-tools-v1","profile":"sandbox-tools-v1"}'
                    with self.subTest(failure=failure), self.assertRaises(ValueError): self.authenticate(f, mutate)
                for failure in ("owner", "upload-missing", "upload-running", "upload-failed", "job-completed"):
                    upload = "Upload Pi source-test inputs" if profile == "pi-tools-v1" else "Upload Sandbox source-test inputs"
                    job = {"id": 9, "name": f["spec"]["job"], "status": "in_progress", "conclusion": None,
                        "steps": [{"name": upload, "status": "completed", "conclusion": "success"}]}
                    if failure == "owner": job["name"] = "foreign owner"
                    if failure == "upload-missing": job["steps"] = []
                    if failure == "upload-running": job["steps"][0]["status"] = "in_progress"
                    if failure == "upload-failed": job["steps"][0]["conclusion"] = "failure"
                    if failure == "job-completed": job.update(status="completed", conclusion="success")
                    with self.subTest(failure=failure), self.assertRaises(ValueError): self.authenticate(f, job=job)

    def test_source_namespace_stage_and_after_drift_do_not_become_a_stable_pass(self):
        for kind in ("tracked", "namespace", "coverage-output", "stage"):
            with self.subTest(kind=kind), vitest_source_fixture() as f:
                if kind == "stage":
                    target = f["staged"] / f["spec"]["paths"][0]
                    target.write_bytes(target.read_bytes() + b"changed")
                    with self.assertRaises(ValueError):
                        owner.observe_vitest(f["repo"], f["command"], f["raw"], f["observation"], f["spec"]["root"], f["staged"])
                    self.assertFalse(f["counter"].exists())
                    continue
                target = f["repo"] / (f["spec"]["paths"][0] if kind == "tracked" else f["spec"]["root"] + "/unobserved-source.ts")
                if kind == "coverage-output":
                    folder = f["repo"] / f["spec"]["root"] / "coverage-inputs"
                    folder.mkdir()
                    target = folder / "foreign-output.json"
                script = Path(f["command"][2]); script.write_text(script.read_text() + f"pathlib.Path({str(target)!r}).write_bytes(b'actual changed source')\n", encoding="utf-8")
                self.assertEqual(owner.observe_vitest(f["repo"], f["command"], f["raw"], f["observation"], f["spec"]["root"], f["staged"]), 1)
                observed = owner.load_json(f["observation"])
                self.assertFalse(observed["source_stable"])
                self.assertEqual(observed["exit_code"], 0, "Original process exit is retained separately from admission")
                self.assertEqual(len(json.loads(f["counter"].read_text())), 1)
                self.assertEqual(target.read_bytes(), b"actual changed source")

    def test_pi_generated_outputs_are_exact_bounded_exclusions_only_for_that_profile(self):
        with vitest_source_fixture() as f:
            folder = f["repo"] / f["spec"]["root"] / "coverage-inputs"; folder.mkdir()
            for name in ("windows-latest.provenance.json", "windows-latest.json", "windows-latest.checked.json"):
                (folder / name).write_bytes(b"{}")
            self.assertFalse(owner.source_identity(f["repo"])["clean"])
            self.assertTrue(owner.source_identity(f["repo"], "pi-tools-v1")["clean"])
            owner.source_input_snapshot(f["repo"], "pi-tools-v1")
            foreign = folder / "foreign.ts"; foreign.write_bytes(b"unexpected source")
            with self.assertRaises(ValueError): owner.source_identity(f["repo"], "pi-tools-v1")
            self.assertEqual(foreign.read_bytes(), b"unexpected source"); foreign.unlink()
            target = folder / "windows-latest.json"; target.unlink(); target.symlink_to(folder / "windows-latest.provenance.json")
            with self.assertRaises(ValueError): owner.source_identity(f["repo"], "pi-tools-v1")
            target.unlink(); target.mkdir()
            with self.assertRaises(ValueError): owner.source_identity(f["repo"], "pi-tools-v1")
            with self.assertRaises(ValueError): owner.source_identity(f["repo"], "unknown-profile")

    def test_observed_child_is_credential_blind_and_preserves_original_docker_prerequisites(self):
        with vitest_source_fixture("sandbox-tools-v1") as f, mock.patch.dict(os.environ, {
            "GH_TOKEN": "PrivateFixtureValue", "OPENAI_API_KEY": "PrivateFixtureValue", "ACTIONS_RUNTIME_TOKEN": "PrivateFixtureValue",
            "CA_SANDBOX_REQUIRE_DOCKER": "1", "CA_SANDBOX_DOCKER_SENTINEL": str(f["base"] / "owned.sentinel")}):
            self.assertEqual(owner.observe_vitest(f["repo"], f["command"], f["raw"], f["observation"], f["spec"]["root"], f["staged"]), 0)
            self.assertFalse(json.loads(f["counter"].read_text())[0]["token_present"])
            private = f["base"] / "env-profile"; private.mkdir()
            env = owner._vitest_environment(private)
            self.assertNotIn("PrivateFixtureValue", json.dumps(env))
            self.assertEqual(env["CA_SANDBOX_REQUIRE_DOCKER"], "1")
            self.assertEqual(env["CA_SANDBOX_DOCKER_SENTINEL"], str(f["base"] / "owned.sentinel"))
            for name in ("HOME", "USERPROFILE", "TEMP", "APPDATA", "LOCALAPPDATA", "NPM_CONFIG_CACHE"):
                self.assertTrue(Path(env[name]).is_relative_to(private))

    def test_windows_npx_uses_the_qualified_adjacent_native_launch_without_a_shell(self):
        import _artifactauthoritylib as authority
        from types import SimpleNamespace
        npm_wrapper = r''':: Created by npm, please don't edit manually.
@ECHO OFF
SETLOCAL
SET "NODE_EXE=%~dp0\node.exe"
IF NOT EXIST "%NODE_EXE%" (
  SET "NODE_EXE=node"
)
SET "NPM_PREFIX_JS=%~dp0\node_modules\npm\bin\npm-prefix.js"
SET "NPM_CLI_JS=%~dp0\node_modules\npm\bin\npm-cli.js"
FOR /F "delims=" %%F IN ('CALL "%NODE_EXE%" "%NPM_PREFIX_JS%"') DO (
  SET "NPM_PREFIX_NPM_CLI_JS=%%F\node_modules\npm\bin\npm-cli.js"
)
IF EXIST "%NPM_PREFIX_NPM_CLI_JS%" (
  SET "NPM_CLI_JS=%NPM_PREFIX_NPM_CLI_JS%"
)
"%NODE_EXE%" "%NPM_CLI_JS%" %*'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            npm, npx, node = root / "npm.cmd", root / "npx.cmd", root / "node.exe"
            cli = root / "node_modules/npm/bin/npm-cli.js"; cli.parent.mkdir(parents=True)
            npm.write_text(npm_wrapper, encoding="utf-8")
            npx_wrapper = npm_wrapper.replace("NPM_PREFIX_NPM_CLI_JS", "NPM_PREFIX_NPX_CLI_JS").replace("NPM_CLI_JS", "NPX_CLI_JS").replace("npm-cli.js", "npx-cli.js")
            npx.write_text(npx_wrapper, encoding="utf-8")
            npx.chmod(0o755); npm.chmod(0o755)
            for path in (node, cli, cli.with_name("npx-cli.js")): path.write_bytes(b"inert runtime data; never executed")
            args = [str(npx), "vitest", "run", "--coverage", "--reporter=blob", "--reporter=default", "--outputFile.blob=coverage-inputs/windows-latest.json"]
            proxy = SimpleNamespace(**vars(os)); proxy.name = "nt"
            with mock.patch.object(owner, "os", proxy), mock.patch.object(authority, "os", proxy):
                actual, records = owner._vitest_launch(args)
                self.assertEqual(actual, [str(node), str(cli.with_name("npx-cli.js")), *args[1:]])
                self.assertEqual({row["resolved_path"] for row in records}, {str(p) for p in (npm, npx, node, cli, cli.with_name("npx-cli.js"))})
                self.assertTrue(all(row["sha256"] == owner.readiness.digest(Path(row["resolved_path"]).read_bytes()) for row in records))
                self.assertNotIn("cmd.exe", actual)
                before = list(records)
                cli.with_name("npx-cli.js").write_bytes(b"actual modified entry")
                self.assertNotEqual([owner._vitest_runtime_file(row["path"]) for row in records], before)
                npx.write_text(npx_wrapper + "\necho unexpected\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "unqualified npx wrapper"): owner._vitest_launch(args)
                npx.write_text(npx_wrapper, encoding="utf-8"); node.unlink()
                with self.assertRaises(authority.AuthorityError): owner._vitest_launch(args)

    def test_final_ts_reports_authenticate_the_original_source_upload_and_owner(self):
        for profile in TS_PROFILE_FIXTURES:
            with self.subTest(profile=profile):
                spec = TS_PROFILE_FIXTURES[profile]
                cell = "disposition:transitions:pi-qualification:disposable-home:01" if profile == "pi-tools-v1" else "disposition:transitions:S54:01"
                raw = io.BytesIO()
                with zipfile.ZipFile(raw, "w") as archive: archive.writestr("owned-input", b"source")
                content = raw.getvalue(); members = owner.readiness.members(content)
                req = {"source_commit": "a" * 40, "source_tree": "b" * 40, "ci_run_id": 7,
                    "cells": [cell], "cell_jobs": {cell: spec["job"]}, "required_artifact_names": [spec["payload"]]}
                source = {"id": 8, "name": spec["payload"]}
                report_artifact = {"id": 10, "name": "major-qualification-9"}
                job = {"id": 9, "name": spec["job"], "status": "completed", "conclusion": "success"}
                report = {"schema": "codearbiter-major-qualification/2", **{k: req[k] for k in ("source_commit", "source_tree", "ci_run_id")},
                    "job_id": 9, "payloads": [{"artifact_id": 8, "archive_sha256": owner.readiness.digest(content), "members": members}],
                    "results": [{"cell": cell, "result": "PASSED", "commands": [{"argv": ["original-owning-command"], "exit_code": 0}],
                        "selected_population": 1, "executed_population": 1, "payload_artifact_id": 8}]}
                upload = "Upload Pi source-test inputs" if profile == "pi-tools-v1" else "Upload Sandbox source-test inputs"
                with mock.patch.object(owner.readiness, "read_artifact_json", return_value=report), \
                     mock.patch.object(owner.readiness, "artifact_bytes", return_value=content), \
                     mock.patch.object(owner.readiness, "validate_upload") as attribution:
                    jobs = [job, {"id": 11, "name": "major readiness producer"}]
                    owner.readiness.produce(req, [source, report_artifact], jobs)
                    self.assertEqual(attribution.call_args_list, [mock.call(job, report_artifact, "Upload major qualification report"), mock.call(job, source, upload)])
                    def refuse(_job, _artifact, step):
                        if step == upload: raise owner.readiness.ReadinessError("original source uploader refused")
                    attribution.side_effect = refuse
                    with self.assertRaises(owner.readiness.ReadinessError): owner.readiness.produce(req, [source, report_artifact], jobs)
                    attribution.side_effect = None
                    foreign = {**job, "name": "foreign source owner"}
                    with self.assertRaises(owner.readiness.ReadinessError):
                        owner.readiness.produce({**req, "cell_jobs": {cell: foreign["name"]}}, [source, report_artifact], [foreign, jobs[1]])



@contextmanager
def autocrlf_source_checkout(profile):
    """Actual declared input bytes and attributes in a disposable local Git clone."""
    with tempfile.TemporaryDirectory(prefix="ca-source-autocrlf-") as temporary:
        base=Path(temporary).resolve();seed=base/'seed';seed.mkdir()
        paths=owner.TS_PROFILE_PATHS[profile]
        for relative in paths:
            path=seed/relative;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((owner.ROOT/relative).read_bytes())
        (seed/'.gitattributes').write_bytes((owner.ROOT/'.gitattributes').read_bytes())
        raw=seed/'.codearbiter/legacy/byte-policy-control.md';raw.parent.mkdir(parents=True);raw.write_bytes(b'raw\r\nkept\r\n')
        (seed/'ordinary.txt').write_bytes(b'ordinary\nconversion\n')
        owner.git(seed,'init','-q');owner.git(seed,'config','core.autocrlf','false')
        owner.git(seed,'add','.')
        owner.git(seed,'-c','user.name=fixture','-c','user.email=fixture@example.invalid',
            '-c','commit.gpgsign=false','commit','-qm','source byte-policy fixture')
        original={relative:owner.git(seed,'rev-parse','HEAD:'+relative) for relative in paths}
        checkout=base/'checkout'
        owner.git(base,'clone','--no-hardlinks','--no-checkout','--quiet',str(seed),str(checkout))
        owner.git(checkout,'config','core.autocrlf','true')
        owner.git(checkout,'checkout','--force','HEAD')
        with mock.patch.dict(os.environ,{'GITHUB_RUN_ID':'7'}):
            yield {'base':base,'seed':seed,'repo':checkout,'paths':paths,'blob_ids':original}


class SourceBytePolicyTests(unittest.TestCase):
    def test_actual_ts_profiles_prepare_from_fresh_autocrlf_checkout_without_changing_blobs(self):
        for profile in owner.TS_PROFILE_PATHS:
            with self.subTest(profile=profile),autocrlf_source_checkout(profile) as f:
                before=owner.source_identity(f['repo'],profile)
                try:
                    manifest=owner.prepare_source_payload(f['repo'],f['base']/'payload',
                        owner.TS_PROFILE_JOBS[profile],profile)
                except ValueError as error:
                    self.fail('actual prepare-source refused a fresh autocrlf checkout: '+str(error))
                self.assertEqual({row['path'] for row in manifest['members']},f['paths'])
                for relative in f['paths']:
                    with self.subTest(member=relative):
                        self.assertEqual(owner.git(f['repo'],'rev-parse','HEAD:'+relative),f['blob_ids'][relative])
                        self.assertEqual((f['repo']/relative).read_bytes(),owner.git(f['repo'],'show','HEAD:'+relative,raw=True))
                self.assertEqual((f['repo']/'.codearbiter/legacy/byte-policy-control.md').read_bytes(),b'raw\r\nkept\r\n')
                self.assertEqual((f['repo']/'ordinary.txt').read_bytes(),b'ordinary\r\nconversion\r\n')
                self.assertEqual(owner.source_identity(f['repo'],profile),before)
                # An unrelated dirty source still refuses before byte diagnostics.
                target=f['repo']/'.github/major-qualification-policy.json'
                target.write_bytes(target.read_bytes()+b'changed\n')
                with self.assertRaisesRegex(ValueError,'checkout is not clean'):
                    owner.source_input_snapshot(f['repo'],profile)
                with self.assertRaisesRegex(ValueError,'unknown source input profile'):
                    owner.source_input_snapshot(f['repo'],'foreign-profile')

    def test_byte_diagnostic_rejects_foreign_unbounded_or_extra_data_and_never_emits_content(self):
        relative='.github/major-qualification-policy.json'
        canary='PRIVATE_SOURCE_PAYLOAD_CANARY'
        message=owner._source_byte_mismatch(relative,b'public\n',canary.encode()+b'\r\n')
        self.assertNotIn(canary,message);self.assertNotIn(relative,message)
        record=json.loads(message.split(': ',1)[1])
        self.assertEqual(set(record),{'format','member_sha256','expected','actual'})
        self.assertEqual(set(record['expected']),{'sha256','bytes','lf','crlf','cr'})
        self.assertEqual(set(record['actual']),{'sha256','bytes','lf','crlf','cr'})
        self.assertLess(len(message.encode()),1024)
        with self.assertRaisesRegex(ValueError,'outside fixed profiles') as foreign:
            owner._source_byte_mismatch(canary,b'public',b'other')
        self.assertNotIn(canary,str(foreign.exception))
        for expected,actual in [(b'x'*(8*1024*1024+1),b'x'),(b'x',bytearray(b'x')),(b'x',{'private':canary})]:
            with self.subTest(kind=type(actual).__name__),self.assertRaisesRegex(ValueError,'bounded source bytes') as bounded:
                owner._source_byte_mismatch(relative,expected,actual)
            self.assertNotIn(canary,str(bounded.exception))
        with self.assertRaises(TypeError):
            owner._source_byte_mismatch(relative,b'x',b'y',raw_content=canary)

    def test_actual_mismatch_reports_closed_hashed_member_and_exact_byte_counts(self):
        profile='pi-tools-v1';relative='.github/major-qualification-policy.json'
        with autocrlf_source_checkout(profile) as f:
            # Private local override simulates unexpected checkout conversion
            # even after the maintained attributes are correct. No tracked input
            # is normalized, and the immutable/physical mismatch must refuse.
            (f['repo']/'.git/info/attributes').write_text('/'+relative+' text eol=crlf\n',encoding='utf8')
            (f['repo']/relative).unlink();owner.git(f['repo'],'checkout','--',relative)
            self.assertTrue(owner.source_identity(f['repo'],profile)['clean'])
            expected=owner.git(f['repo'],'show','HEAD:'+relative,raw=True)
            actual=(f['repo']/relative).read_bytes();self.assertNotEqual(actual,expected)
            with self.assertRaisesRegex(ValueError,'source payload physical bytes differ from Git') as caught:
                owner.prepare_source_payload(f['repo'],f['base']/'refused',owner.TS_PROFILE_JOBS[profile],profile)
            prefix='source payload physical bytes differ from Git: '
            self.assertTrue(str(caught.exception).startswith(prefix),'actual mismatch must retain closed byte diagnosis')
            diagnostic=json.loads(str(caught.exception)[len(prefix):])
            self.assertEqual(set(diagnostic),{'format','member_sha256','expected','actual'})
            self.assertEqual(diagnostic['format'],'codearbiter.source-input-byte-mismatch/1')
            self.assertEqual(diagnostic['member_sha256'],owner.readiness.digest(relative.encode('utf8')))
            for key,value in [('expected',expected),('actual',actual)]:
                row=diagnostic[key]
                self.assertEqual(set(row),{'sha256','bytes','lf','crlf','cr'})
                self.assertEqual(row,{'sha256':owner.readiness.digest(value),'bytes':len(value),
                    'lf':value.count(b'\n')-value.count(b'\r\n'),'crlf':value.count(b'\r\n'),
                    'cr':value.count(b'\r')-value.count(b'\r\n')})
            self.assertNotIn(relative,str(caught.exception));self.assertNotIn(str(f['repo']),str(caught.exception))
            self.assertLess(len(str(caught.exception).encode('utf8')),1024)
            self.assertFalse((f['base']/'refused').exists())
            from contextlib import redirect_stderr
            emitted=io.StringIO()
            with redirect_stderr(emitted):
                code=owner.main(['prepare-source','--repo',str(f['repo']),'--output',str(f['base']/'cli-refused'),
                    '--job-name',owner.TS_PROFILE_JOBS[profile],'--source-profile',profile])
            self.assertEqual(code,1)
            self.assertEqual(emitted.getvalue().strip(),'::error::Major qualification report pending: '+str(caught.exception))
            self.assertFalse((f['base']/'cli-refused').exists())

if __name__ == "__main__":
    unittest.main(verbosity=2)
