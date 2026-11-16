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
                subprocess.run([git,"-C",str(repo),*arguments],check=True,capture_output=True,timeout=15)
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

    def test_six_source_cells_keep_exact_selectors_and_single_original_ci_executions(self):
        from test_ci_impact import workflow_jobs
        selection=json.loads((owner.ROOT/".github/major-test-selections.json").read_text())
        policy=json.loads((owner.ROOT/".github/major-qualification-policy.json").read_text())
        source=[group for group in selection["groups"] if group["proof_kind"]=="source-test"]
        expected={"disposition:transitions:C33:02","disposition:transitions:C33:03",*
            ("disposition:added_transitions:S75:"+name for name in
             ("added-stage-failed","added-rolled-back","added-unusable","added-writer-refused"))}
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
