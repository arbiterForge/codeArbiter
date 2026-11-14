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
        self.map["groups"][0].update(cells=cells, proof_kind="source-test")
        self.observation.update(proof_kind="source-test", producer="python-test-result-observer", argv=[
            "C:/Python314/python.exe", ".github/scripts/major_qualification_report.py", "observe-python", "--repo",
            "C:/Users/runner/work/codeArbiter/codeArbiter", "--output",
            "C:/Users/runner/AppData/Local/Temp/hooks-observation.json", "--", ".github/scripts/test_adr_lifecycle.py"])
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
