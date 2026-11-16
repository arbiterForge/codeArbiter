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


class VitestIdentityBudgetTests(unittest.TestCase):
    """Canonical identity bytes include the source path and the full test name."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ca-vitest-id-budget-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve()
        self.before = {"source_commit": "a" * 40, "source_tree": "b" * 40, "clean": True}

    def admit(self, names, *, path="a.test.ts", status="passed", exit_code=0):
        raw = {"testResults": [{"name": str(self.repo / path), "assertionResults": [
            {"fullName": name, "status": status} for name in names]}]}
        return owner.admit_vitest(raw, repo=self.repo, before=self.before, after=self.before,
                                  argv=["npm", "test"], exit_code=exit_code, run_id=7)

    def test_original_public_malformed_input_vector_keeps_its_full_bounded_name(self):
        name = ("Windows startup stage diagnostics rejects malformed or out-of-order stage "
                + "PRIVATE_INPUT_SENTINEL" * 100 + " without echoing it")
        self.assertGreater(len(name.encode("utf-8")), 2048)
        self.assertLess(len(("vitest:a.test.ts:" + name).encode("utf-8")), 4096)
        try:
            observed = self.admit([name])
        except ValueError as error:
            self.fail("Valid complete canonical identity was refused: " + str(error))
        self.assertEqual(observed["tests"], [{"id": "vitest:a.test.ts:" + name, "result": "passed"}])

    def test_exact_complete_ascii_identity_budget_is_accepted(self):
        prefix = "vitest:a.test.ts:"
        name = "x" * (4096 - len(prefix.encode("utf-8")))
        self.assertEqual(len(self.admit([name])["tests"][0]["id"].encode("utf-8")), 4096)

    def test_complete_identity_overflow_is_rejected_without_truncation(self):
        name = "x" * (4097 - len("vitest:a.test.ts:".encode("utf-8")))
        with self.assertRaisesRegex(ValueError, "Vitest.*bound"):
            self.admit([name])

    def test_utf8_bytes_and_full_source_path_share_the_same_budget(self):
        path = "nested/é.test.ts"
        prefix = "vitest:" + path + ":"
        remaining = 4096 - len(prefix.encode("utf-8"))
        name = "é" * (remaining // 2) + "x" * (remaining % 2)
        self.assertEqual(len(self.admit([name], path=path)["tests"][0]["id"].encode("utf-8")), 4096)
        with self.assertRaisesRegex(ValueError, "Vitest.*bound"):
            self.admit([name + "é"], path=path)

    def test_long_path_cannot_hide_a_complete_identity_overflow(self):
        path = "nested/" * 120 + "a.test.ts"
        with self.assertRaisesRegex(ValueError, "Vitest.*bound"):
            self.admit(["é" * 1700], path=path)

    def test_long_duplicate_names_are_still_rejected(self):
        name = "long public vector " + "x" * 2200
        with self.assertRaisesRegex(ValueError, "duplicate Vitest"):
            self.admit([name, name])

    def test_long_pending_and_failed_names_keep_the_actual_result(self):
        name = "long public vector " + "x" * 2200
        self.assertEqual(self.admit([name], status="pending")["tests"][0]["result"], "skipped")
        observed = self.admit([name], status="failed", exit_code=1)
        self.assertEqual((observed["exit_code"], observed["tests"][0]["result"]), (1, "failed"))

    def test_shape_status_population_and_zero_name_refusals_remain(self):
        for name, status in [(None, "passed"), ("", "passed"), ("ok", None), ("ok", "unknown")]:
            with self.subTest(name=name, status=status), self.assertRaises(ValueError):
                self.admit([name], status=status)
        with mock.patch.object(owner, "MAX_TESTS", 2), self.assertRaisesRegex(ValueError, "malformed or unbounded Vitest"):
            self.admit(["first", "second", "third"])


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


    def test_native_child_skip_survives_admission_instead_of_parent_pass_laundering(self):
        record = {"format":"codearbiter.go-test-observation/1","complete":True,
            "module_sha256_before":"f"*64,"module_sha256_after":"f"*64,
            "argv":["python","tools/go_test_parallel.py"],
            "selected":[{"package":"p","test":"TestA"}],
            "observed":[{"package":"p","test":"TestA","result":"pass"}],
            "subtests":[{"package":"p","test":"TestA/workspaces-32","result":"skip"}]}
        value=owner.admit_go(record,self.binding,"b"*40)
        self.assertIn({"id":"go:p:TestA/workspaces-32","result":"skipped"},value["tests"])


    def test_native_child_shapes_cannot_forge_other_parents_or_duplicate_outcomes(self):
        record={"format":"codearbiter.go-test-observation/1","complete":True,
            "module_sha256_before":"f"*64,"module_sha256_after":"f"*64,
            "argv":["python","tools/go_test_parallel.py"],
            "selected":[{"package":"p","test":"TestA"}],
            "observed":[{"package":"p","test":"TestA","result":"pass"}]}
        child={"package":"p","test":"TestA/child","result":"pass"}
        for children in ([child,dict(child)],[{**child,"test":"Other/child"}],
                         [{**child,"result":"fail"}],[{**child,"test":None}],
                         [{**child,"test":"TestA/"+"x"*4096}],
                         [{**child,"unexpected":True}]):
            with self.subTest(children=children),self.assertRaises(ValueError):
                owner.admit_go({**record,"subtests":children},self.binding,"b"*40)
        with mock.patch.object(owner,"MAX_TESTS",1),self.assertRaises(ValueError):
            owner.admit_go({**record,"subtests":[child]},self.binding,"b"*40)


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
    def test_capture_destination_does_not_relocate_the_original_temp_filesystem(self):
        with vitest_source_fixture() as f:
            program = Path(f["command"][2])
            source = program.read_text(encoding="utf-8")
            self.assertIn("'token_present':", source)
            source = source.replace("'token_present':", "'temp_filesystem_root':str(pathlib.Path(os.environ['TEMP']).resolve().parent.parent),'token_present':", 1)
            program.write_text(source, encoding="utf-8")
            captured = f["base"] / "capture-on-independent-filesystem"
            captured.mkdir()
            self.assertEqual(owner.observe_vitest(f["repo"], f["command"], captured / "named.json",
                captured / "observation.json", f["spec"]["root"], f["staged"]), 0)
            runs = json.loads(f["counter"].read_text(encoding="utf-8"))
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["temp_filesystem_root"], str(Path(tempfile.gettempdir()).resolve()))
            self.assertNotEqual(runs[0]["temp_filesystem_root"], str(captured.resolve()))
            self.assertFalse(runs[0]["token_present"])
            observed = owner.load_json(captured / "observation.json")
            self.assertTrue(observed["source_stable"])
            self.assertEqual(observed["original_argv"], f["command"])

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
                        # S51:01/02 and S52:06 have explicit finite routes; 03 remains outside both profiles.
                        selected["cells"] = required["cells"] = ["disposition:transitions:S51:03"]
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


class MappedNativeConsumerDispatchTests(unittest.TestCase):
    def test_closed_mapped_consumer_transports_source_and_original_native_without_reexecution(self):
        import types
        ReportTest.setUp(self)
        cell='disposition:transitions:S38:04';job='[CHECK] | [CORE] | Native adapters and conformance <windows/amd64>'
        source='major-source-inputs-mapped-work-windows';native='ci20-native-tested-windows-2025'
        self.req.update(cells=[cell],cell_jobs={cell:job})
        group=self.map['groups'][0];group.update(job=job,payload_name=source,proof_kind='source-test',cells=[cell])
        self.observation.update(proof_kind='source-test',producer='python-mapped-native-consumer-observer-v1',
            source_input_binding={'profile':'mapped-work-native-consumer-v1'})
        payloads={source:{**self.payload,'artifact_id':8},native:{**self.payload,'artifact_id':10}}
        admission={'tests':self.observation['tests'],'payloads':[{key:value[key] for key in ('artifact_id','archive_sha256','members')} for value in payloads.values()],
            'primary_payload_name':source,'qualified_cells':[cell]}
        module=types.ModuleType('mapped_work_observation');module.admit=mock.Mock(return_value=admission)
        module.CELL=cell;module.SOURCE_PAYLOAD=source;module.JOB=job
        # The admitted native component is an inert transport seam, not a real
        # module/platform observation. The actual adapter owns its closed joins.
        component={'unit_native_component':'inert-only'}
        with mock.patch.dict(sys.modules,{'mapped_work_observation':module}):
            result=owner.build_report(self.req,job_name=job,job_id=9,selections=self.map,
                observations={'native':self.observation},payloads=payloads,
                native_components={'native':component})
        self.assertEqual(result['schema'],'codearbiter-major-qualification/3')
        self.assertEqual(result['results'][0]['payload_artifact_ids'],[8,10])
        self.assertEqual(len(result['payloads']),2)
        self.assertEqual(module.admit.call_count,1)
        self.assertEqual(module.admit.call_args.kwargs['native_component'],component)



class MappedNativeConsumerProfileTests(unittest.TestCase):
    """Pure file/Git/reader controls; never execute the native fixture suite."""
    def setUp(self):
        import mapped_work_observation as profile
        self.profile=profile
        self.owner=tempfile.TemporaryDirectory();self.addCleanup(self.owner.cleanup)
        self.base=Path(self.owner.name).resolve(strict=True)
        self.root=self.base/'repo';self.root.mkdir()
        self.run_git('init','-q');self.run_git('config','user.name','Fixture')
        self.run_git('config','user.email','fixture@example.invalid')
        self.run_git('config','core.autocrlf','false')
        files={'core/pysrc/_artifactlib.py':'# source\n','core/pysrc/_workgithub.py':'# source\n',
               'core/artifacts/go.mod':'module fixture.invalid/source\n',
               'core/surface/fixture.md':'# declared source\n',
               'plugins/ca-codex/helpers/fixture.py':'# original copied first-party input\n',
               '.github/scripts/test_artifact_authoring.py':'# source\n',
               '.github/scripts/test_work_github.py':'# source\n',
               'core/hosts.json':'{}\n','core/artifact-release-manifest.json':'{}\n'}
        files.update({name:'# declared source\n' for name in profile.EXTRA if name not in files})
        for name,value in files.items():
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value,encoding='utf8')
        self.commit()

    def run_git(self,*args):
        return subprocess.run(['git','-C',str(self.root),*args],
                              capture_output=True,check=True,timeout=15).stdout

    def commit(self):
        self.run_git('add','-A');self.run_git('commit','-qm','literal fixture source')

    def fixture(self):
        p=self.profile;snapshot=p.snapshot(self.root)
        req={**snapshot,'ci_run_id':7,'native_module_sha256':{'windows':'9'*64}}
        manifest={'format':p.FORMAT,'profile':p.PROFILE,'source_commit':req['source_commit'],
           'source_tree':req['source_tree'],'ci_run_id':7,'producer_job_name':p.JOB,
           'members':snapshot['members'],'host_lookup':snapshot['host_lookup']}
        raw=json.dumps(manifest).encode();sha=owner.readiness.digest(raw)
        source={'artifact_id':8,'archive_sha256':'c'*64,'members':[{'path':r['path'],'sha256':r['sha256']} for r in snapshot['members']]
                 +[{'path':p.MANIFEST,'sha256':sha}],'source_upload_job_id':9,'source_manifest_sha256':sha,'documents':{p.MANIFEST:manifest}}
        native={'artifact_id':10,'archive_sha256':'d'*64,'members':[
            {'path':'artifact-candidate/release.json','sha256':'e'*64},
            {'path':'artifact-candidate/ca-artifact-windows-amd64.exe','sha256':'f'*64}]}
        state={'manifest_sha256':'e'*64,'binary_sha256':'f'*64,'binary_bytes':123,'platform':'windows/amd64'}
        component={'platform':'windows/amd64',**native,'native_binding':{'manifest_sha256':'e'*64,'binary_sha256':'f'*64,
            'source_commit':req['source_commit'],'run_id':'7','module_sha256':'9'*64}}
        binding={'format':p.FORMAT,'profile':p.PROFILE,'source_manifest_sha256':sha,'native_before':state,
          'native_after':dict(state),'native_admissions':dict.fromkeys(p.SELECTORS,1),
          'runtime_before':{'python_sha256':'1'*64,'version':[3,14,10]},
          'runtime_after':{'python_sha256':'1'*64,'version':[3,14,10]},
          'host_lookup_before':snapshot['host_lookup'],'host_lookup_after':dict(snapshot['host_lookup']),
          'imported_sources':{r['path']:r['sha256'] for r in snapshot['members'] if r['path'].endswith('.py')}}
        observed={'producer':p.PRODUCER,'proof_kind':'source-test','consumer_binding':binding,
             'tests':[{'id':name,'result':'passed'} for name in p.SELECTORS],
             'argv':['python',str(self.root/p.SCRIPT)]}
        return req,observed,{p.SOURCE_PAYLOAD:source,p.NATIVE_PAYLOAD:native},component

    def admit(self,fixture):
        req,observed,payloads,component=fixture
        return self.profile.admit(observed,req=req,job_id=9,authenticated_payloads=payloads,
                                  repo=self.root,native_component=component)

    def test_immutable_source_and_full_physical_namespace_refuse_drift_and_shadows(self):
        p=self.profile;before=p.snapshot(self.root)
        self.assertEqual({r['path'] for r in before['members']},p._physical_names(self.root))
        path=self.root/'core/pysrc/_artifactlib.py';old=path.read_bytes();path.write_bytes(old+b'# drift\n')
        with self.assertRaisesRegex(ValueError,'dirty'):p.snapshot(self.root)
        path.write_bytes(old)
        for name in ('core/pysrc/untracked.pyd','.github/scripts/_host.pyc'):
            with self.subTest(name=name):
                shadow=self.root/name;shadow.write_bytes(b'inert')
                try:
                    with self.assertRaises(ValueError):p.snapshot(self.root)
                finally:shadow.unlink()
        host=self.root/'core/pysrc/_host.py';host.write_text('# tracked shadow\n');self.commit()
        with self.assertRaisesRegex(ValueError,'host lookup shadow'):p.snapshot(self.root)

    def test_source_manifest_binds_exact_original_commit_members_and_closed_job(self):
        fixture=self.fixture();req,observed,payloads,component=fixture;p=self.profile
        source=payloads[p.SOURCE_PAYLOAD];manifest=source['documents'][p.MANIFEST]
        self.assertIs(p.validate_manifest(manifest,req=req,repo=self.root,members=source['members']),manifest)
        for field,value in (('source_commit','a'*40),('source_tree','b'*40),('ci_run_id',8),
                            ('producer_job_name','other job'),('profile','source-test'),('host_lookup',{})):
            with self.subTest(field=field):
                changed=copy.deepcopy(manifest);changed[field]=value
                with self.assertRaises(ValueError):p.validate_manifest(changed,req=req,repo=self.root,members=source['members'])
        for members in (source['members'][:-1],source['members']+[source['members'][0]]):
            with self.assertRaises(ValueError):p.validate_manifest(manifest,req=req,repo=self.root,members=members)

    def test_actual_builder_and_consumer_native_identity_must_join(self):
        fixture=self.fixture();admitted=self.admit(fixture)
        self.assertEqual(admitted['qualified_cells'],[self.profile.CELL])
        self.assertEqual([row['artifact_id'] for row in admitted['payloads']],[8,10])
        mutations=[lambda x:x[3].update(artifact_id=11),lambda x:x[3].update(platform='linux/amd64'),
          lambda x:x[3].update(archive_sha256='0'*64),lambda x:x[3]['native_binding'].update(source_commit='a'*40),
          lambda x:x[3]['native_binding'].update(run_id='8'),
          lambda x:x[3]['native_binding'].update(module_sha256='0'*64),
          lambda x:x[1]['consumer_binding']['native_after'].update(binary_sha256='0'*64),
          lambda x:x[2].pop(self.profile.NATIVE_PAYLOAD),
          lambda x:x[2][self.profile.SOURCE_PAYLOAD].update(source_upload_job_id=8),
          lambda x:x[2][self.profile.NATIVE_PAYLOAD]['members'][1].update(sha256='0'*64)]
        for number,mutation in enumerate(mutations):
            with self.subTest(number=number):
                changed=copy.deepcopy(fixture);mutation(changed)
                with self.assertRaises(ValueError):self.admit(changed)

    def test_consumed_native_archive_bytes_are_checked_without_another_download(self):
        p=self.profile;root=self.base/'consumed';root.mkdir()
        names=('artifact-candidate/release.json','artifact-candidate/ca-artifact-windows-amd64.exe',
               'ci20-native-tested.json','native-tests.json','native-observation.json')
        members=[]
        for name in names:
            value=('inert original '+name).encode();path=root/name
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
            members.append({'path':name,'sha256':owner.readiness.digest(value)})
        component={'artifact_id':10,'archive_sha256':'d'*64,'members':members}
        with mock.patch.object(owner.readiness,'artifact_bytes',side_effect=AssertionError('no second download')):
            self.assertEqual(p.authenticate_native_consumption(root,component),component)
            binary=root/names[1];binary.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'bytes changed'):p.authenticate_native_consumption(root,component)
        for rows in (members[:-1],members[:-1]+[members[0]],members+[members[0]]):
            with self.assertRaisesRegex(ValueError,'population'):p.authenticate_native_consumption(root,{**component,'members':rows})

    def test_real_admission_import_lookup_and_original_seven_outcomes_cannot_be_relabelled(self):
        fixture=self.fixture();p=self.profile
        mutations=[lambda x:x[1]['consumer_binding']['runtime_after'].update(python_sha256='2'*64),
          lambda x:x[1]['consumer_binding']['native_admissions'].update({p.SELECTORS[0]:0}),
          lambda x:x[1]['consumer_binding']['native_admissions'].update({'invented':1}),
          lambda x:x[1]['consumer_binding']['imported_sources'].pop('core/pysrc/_artifactlib.py'),
          lambda x:x[1]['consumer_binding']['imported_sources'].update({'foreign.py':'0'*64}),
          lambda x:x[1]['consumer_binding']['host_lookup_after'].update({'core/pysrc/_host.py':'present'}),
          lambda x:x[1]['tests'].append(dict(x[1]['tests'][0])),
          lambda x:x[1]['tests'][0].update(result='skipped'),
          lambda x:x[1].update(argv=['python',str(self.root/p.SCRIPT),'FilteredCase']),
          lambda x:x[1].update(producer='python-test-result-observer')]
        for number,mutation in enumerate(mutations):
            with self.subTest(number=number):
                changed=copy.deepcopy(fixture);mutation(changed)
                with self.assertRaises(ValueError):self.admit(changed)

    def test_only_original_conformance_child_slot_can_opt_in_and_default_argv_is_unchanged(self):
        p=self.profile;env={'MAJOR_MAPPED_WORK_SOURCE':'private-stage','MAJOR_MAPPED_WORK_OBSERVATION':'private.json'}
        command=p.conformance_command(self.root,'test_work_github.py','locked-python',env)
        self.assertEqual(command,['locked-python',str(self.root/'.github/scripts/mapped_work_observation.py'),
                   'observe','--repo',str(self.root),'--source-payload','private-stage','--output','private.json'])
        for script in ('test_work_github.py','test_artifact_bridge.py'):
            self.assertEqual(p.conformance_command(self.root,script,'locked-python',{}),
                             ['locked-python',str(self.root/'.github/scripts'/script)])
        self.assertEqual(p.conformance_command(self.root,'test_artifact_bridge.py','locked-python',env),
                         ['locked-python',str(self.root/'.github/scripts/test_artifact_bridge.py')])
        for env in ({'MAJOR_MAPPED_WORK_SOURCE':'stage'},{'MAJOR_MAPPED_WORK_OBSERVATION':'out'},
                    {'MAJOR_MAPPED_WORK_SOURCE':'','MAJOR_MAPPED_WORK_OBSERVATION':'out'}):
            with self.assertRaisesRegex(ValueError,'requires both'):p.conformance_command(self.root,'test_work_github.py','python',env)

    def test_public_original_entrypoint_runs_once_restores_modules_and_dispatches_closed_report(self):
        # Inert ArtifactClient file-admission seam only; no binary execution/API.
        # This synthetic supported snapshot belongs to the inert route fixture;
        # it does not relabel the actual test runner or a native observation.
        supported_runtime={'python_sha256':'1'*64,'version':[3,14,10]}
        p=self.profile;private=self.base;installation=private/'installation';installation.mkdir()
        raw=b'{"fixture":"inert-native-file-only"}';(installation/'release.json').write_bytes(raw)
        (installation/'candidate.bin').write_bytes(b'INERT')
        counter=private/'original-entry-count';counter.write_text('0')
        (self.root/'core/pysrc/_artifactlib.py').write_text(
            "import os\nfrom pathlib import Path\nclass ArtifactClient:\n"
            " def __init__(self,installation): self.installation=Path(installation)\n"
            " def _open_binary(self): return os.open(self.installation/'candidate.bin',os.O_RDONLY)\n")
        child=("import os,unittest\nfrom pathlib import Path\nimport _artifactlib,_workgithub,test_artifact_authoring\n"
               +f"counter=Path({str(counter)!r});counter.write_text(str(int(counter.read_text())+1))\n"
               +"class GithubWorkTest(unittest.TestCase):\n")
        for name in p.NAMES:
            child+=(f" def {name}(self):\n  fd=_artifactlib.ArtifactClient({str(installation)!r})._open_binary()\n"
                    "  try: self.assertEqual(os.read(fd,1),b'I')\n  finally: os.close(fd)\n")
        child+="if __name__=='__main__': unittest.main(verbosity=2)\n"
        (self.root/p.SCRIPT).write_text(child)
        selections={'schema':owner.SELECTIONS,'groups':[{'id':'mapped','job':p.JOB,'payload_name':p.SOURCE_PAYLOAD,
           'observation':'mapped','proof_kind':'source-test','selectors':list(p.SELECTORS),'cells':[p.CELL],
           'scope':'Inert producer/reader route unit control; no native qualification.'}]}
        (self.root/'.github/major-test-selections.json').write_text(json.dumps(selections))
        self.commit()
        with mock.patch.dict(os.environ,GITHUB_RUN_ID='7'):manifest=p.prepare(self.root,private/'source-stage')
        before=p.snapshot(self.root)
        state={'platform':'windows/amd64','manifest_sha256':owner.readiness.digest(raw),
               'binary_sha256':owner.readiness.digest(b'INERT'),'binary_bytes':5}
        poisoned=SimpleNamespace(__file__='/untrusted/_artifactlib.py')
        sys.modules['_artifactlib']=poisoned
        self.addCleanup(lambda:sys.modules.pop('_artifactlib',None) if sys.modules.get('_artifactlib') is poisoned else None)
        output=private/'observation.json'
        flags=SimpleNamespace(**({key:getattr(sys.flags,key) for key in dir(sys.flags) if not key.startswith('_')} | {'no_user_site':1}))
        with mock.patch.object(owner,'validate_emitter_environment'), \
             mock.patch.object(owner.readiness,'api',side_effect=AssertionError('observer must not request API')) as api, \
             mock.patch.object(owner.readiness,'artifact_bytes',side_effect=AssertionError('observer must not request archive')) as archive, \
             mock.patch.object(p,'native_snapshot',return_value=state) as native, \
             mock.patch.object(p,'runtime_snapshot',side_effect=lambda:copy.deepcopy(supported_runtime)) as runtime, \
             mock.patch.dict(os.environ,ARTIFACT_TEST_INSTALLATION=str(installation),GITHUB_RUN_ID='7'), \
             mock.patch.object(p.sys,'platform','win32'),mock.patch.object(p.sys,'flags',flags), \
             mock.patch.object(p.sys,'pycache_prefix',str(private/'pycache')):
            self.assertEqual(p.observe(self.root,output,private/'source-stage'),0)
        self.assertEqual(native.call_count,2);self.assertEqual(runtime.call_count,2)
        api.assert_not_called();archive.assert_not_called()
        self.assertIs(sys.modules['_artifactlib'],poisoned)
        self.assertEqual(counter.read_text(),'1')
        self.assertEqual(before,p.snapshot(self.root))
        observation=owner.load_json(output);self.assertEqual(observation['producer'],p.PRODUCER)
        self.assertEqual(observation['tests'],[{'id':name,'result':'passed'} for name in sorted(p.SELECTORS)])
        self.assertEqual(observation['consumer_binding']['native_admissions'],dict.fromkeys(p.SELECTORS,1))
        self.assertEqual(observation['consumer_binding']['runtime_before'],observation['consumer_binding']['runtime_after'])
        self.assertEqual(observation['consumer_binding']['runtime_before'],supported_runtime)
        original=owner.load_json(private/'observation.original.json')
        self.assertEqual(original['producer'],'python-test-result-observer')
        self.assertEqual(original['tests'],observation['tests'])
        sha=owner.readiness.digest((private/'source-stage'/p.MANIFEST).read_bytes())
        source={'artifact_id':8,'archive_sha256':'c'*64,'members':[
            {'path':row['path'],'sha256':row['sha256']} for row in manifest['members']]+[{'path':p.MANIFEST,'sha256':sha}],
            'documents':{p.MANIFEST:manifest},'source_upload_job_id':9,'source_manifest_sha256':sha}
        native_payload={'artifact_id':10,'archive_sha256':'d'*64,'members':[
           {'path':'artifact-candidate/release.json','sha256':state['manifest_sha256']},
           {'path':'artifact-candidate/ca-artifact-windows-amd64.exe','sha256':state['binary_sha256']}]}
        component={'platform':'windows/amd64',**native_payload,'native_binding':{**state,
            'source_commit':before['source_commit'],'run_id':'7','module_sha256':'9'*64}}
        req={**before,'ci_run_id':7,'native_module_sha256':{'windows':'9'*64},'cells':[p.CELL],'cell_jobs':{p.CELL:p.JOB}}
        selections={'schema':owner.SELECTIONS,'groups':[{'id':'mapped','job':p.JOB,'payload_name':p.SOURCE_PAYLOAD,
           'observation':'mapped','proof_kind':'source-test','selectors':list(p.SELECTORS),'cells':[p.CELL],
           'scope':'Inert producer/reader route unit control; no native qualification.'}]}
        with mock.patch.object(owner,'ROOT',self.root):
            report=owner.build_report(req,job_name=p.JOB,job_id=9,selections=selections,
                 observations={'mapped':observation},payloads={p.SOURCE_PAYLOAD:source,p.NATIVE_PAYLOAD:native_payload},
                 native_components={'mapped':component})
        self.assertEqual(report['schema'],'codearbiter-major-qualification/3')
        self.assertEqual(report['results'][0]['payload_artifact_ids'],[8,10])
        self.assertEqual(report['results'][0]['selected_population'],7)
        # Real emit CLI/immutable membership orchestration, inert API/archive
        # authority seams only. It must derive the pin, never accept observation data.
        job={'id':9,'name':p.JOB,'status':'in_progress'}
        artifacts=[{'id':8,'name':p.SOURCE_PAYLOAD},{'id':10,'name':p.NATIVE_PAYLOAD}]
        import types
        native_module=types.ModuleType('major_native_observation')
        def authenticated(req_arg,run_arg,artifacts_arg,jobs_arg,platform):
            self.assertEqual(platform,'windows/amd64')
            self.assertNotEqual(req_arg['native_module_sha256']['windows'],'9'*64)
            self.assertEqual(set(req_arg['native_module_sha256']),{'posix','windows'})
            return {**component,'native_binding':{**component['native_binding'],
                    'module_sha256':req_arg['native_module_sha256']['windows']}}
        native_module.authenticate_component=mock.Mock(side_effect=authenticated)
        emitted=private/'emitted.json'
        with mock.patch.dict(sys.modules,{'major_native_observation':native_module}), \
             mock.patch.dict(os.environ,GITHUB_SHA=before['source_commit'],GITHUB_RUN_ID='7'), \
             mock.patch.object(owner,'ROOT',self.root),mock.patch.object(owner,'validate_emitter_environment'), \
             mock.patch.object(owner.readiness,'collect',return_value=(req,None,artifacts,[job])), \
             mock.patch.object(owner.readiness,'api',return_value={'id':7}) as api, \
             mock.patch.object(owner,'authenticated_payload',return_value=source) as source_auth, \
             mock.patch.object(p,'authenticate_native_consumption',return_value=native_payload) as consumed:
            self.assertEqual(owner.main(['emit','--repo',str(self.root),'--output',str(emitted),
               '--job-name',p.JOB,'--observation','mapped='+str(output),
               '--payload-root',p.SOURCE_PAYLOAD+'='+str(self.root),
               '--payload-root',p.NATIVE_PAYLOAD+'='+str(installation)]),0)
        native_module.authenticate_component.assert_called_once()
        source_auth.assert_called_once();consumed.assert_called_once();api.assert_called_once_with('actions/runs/7')
        self.assertEqual(owner.load_json(emitted),report)
        self.assertEqual(counter.read_text(),'1')

    def test_inert_supported_runtime_fixture_keeps_unsupported_reference_interpreters_refused(self):
        fixture=self.fixture()
        self.assertEqual(self.admit(fixture)['qualified_cells'],[self.profile.CELL])
        for version in ([3,13,9],[3,15,2],[4,14,0]):
            with self.subTest(version=version):
                changed=copy.deepcopy(fixture)
                # Both snapshots agree: refusal must be the closed reference
                # runtime boundary, not a before/after mismatch.
                for name in ('runtime_before','runtime_after'):
                    changed[1]['consumer_binding'][name]['version']=list(version)
                with self.assertRaisesRegex(ValueError,'reference interpreter changed or is unsupported'):
                    self.admit(changed)

    def test_owned_child_profile_is_private_and_never_passes_parent_credentials(self):
        p=self.profile
        source=self.base/'source';output=self.base/'observed.json'
        parent=dict(os.environ,MAJOR_MAPPED_WORK_SOURCE=str(source),MAJOR_MAPPED_WORK_OBSERVATION=str(output),
                    GH_TOKEN='PRIVATE-PARENT-CANARY',GITHUB_TOKEN='PRIVATE-PARENT-CANARY',NODE_OPTIONS='PRIVATE-PARENT-CANARY')
        with p.conformance_invocation(self.root,'test_work_github.py',sys.executable,parent) as (command,env):
            home=Path(env['HOME']);self.assertTrue(home.is_dir())
            self.assertEqual(home.parent.parent,Path(tempfile.gettempdir()).resolve(strict=True))
            self.assertNotEqual(home.parent.parent,output.parent.resolve(strict=True))
            self.assertEqual(home.parent,home.parent.resolve(strict=True))
            self.assertNotEqual(env['HOME'],parent.get('HOME'))
            self.assertEqual(env['USERPROFILE'],env['HOME'])
            self.assertTrue(Path(env['PYTHONPYCACHEPREFIX']).is_relative_to(home.parent))
            self.assertEqual(env['PYTHONNOUSERSITE'],'1')
            self.assertFalse({'GH_TOKEN','GITHUB_TOKEN','NODE_OPTIONS','PYTHONPATH'} & env.keys())
            self.assertNotIn('PRIVATE-PARENT-CANARY',json.dumps(env))
            self.assertEqual(command[0],sys.executable)
        self.assertFalse(home.exists())
        with p.conformance_invocation(self.root,'test_artifact_bridge.py',sys.executable,parent) as (_,env):
            self.assertIs(env,parent)

    def test_public_observer_refuses_unbound_source_before_original_child_execution(self):
        p=self.profile
        (self.root/'core/pysrc/untracked.py').write_text('# unbound shadow\n')
        with mock.patch.object(owner,'observe_python') as execute, mock.patch.object(owner,'validate_emitter_environment'), mock.patch.dict(os.environ,
                ARTIFACT_TEST_INSTALLATION=str(self.base/'not-executed')), \
                mock.patch.object(p.sys,'platform','win32'), \
                mock.patch.object(p.sys,'flags',SimpleNamespace(**({key:getattr(sys.flags,key) for key in dir(sys.flags) if not key.startswith('_')} | {'no_user_site':1}))), \
                mock.patch.object(p.sys,'pycache_prefix',str(self.base/'cache')):
            with self.assertRaisesRegex(ValueError,'dirty'):
                p.observe(self.root,self.base/'out.json',self.base/'stage')
        execute.assert_not_called()
        self.assertFalse((self.base/'out.json').exists())


class MappedNativeConsumerWorkflowTests(unittest.TestCase):
    @staticmethod
    def check_workflow(text):
        import mapped_work_observation as p
        block=text.split('  artifact-native-bridges:\n',1)[1].split('  artifact-authority:\n',1)[0]
        gate="matrix.expected_platform == 'windows/amd64' && github.event_name == 'push' && (github.ref == 'refs/heads/main' || github.ref == 'refs/heads/major/state-contracts') && hashFiles('.github/integration-candidate.json') != ''"
        prepare=block.split('      - name: Prepare mapped-work source-test inputs\n',1)[1].split('      - name:',1)[0]
        emit=block.split('      - name: Emit original mapped-work source qualification report\n',1)[1].split('      - name:',1)[0]
        assert '        if: '+gate+'\n' in prepare
        assert '!cancelled() && '+gate+" && steps.mapped_work_original.outcome == 'success' && steps.mapped_work_source_upload.outcome == 'success'" in emit
        assert 'GH_TOKEN: ${{ github.token }}' in emit and block.count('GH_TOKEN:')==1
        assert '      actions: read\n' in block and '      contents: read\n' in block
        assert 'actions: write' not in block and 'contents: write' not in block
        assert 'continue-on-error:' not in block
        command=('          python .github/scripts/run_concurrent_suites.py\n'
                 '          .github/scripts/test_artifact_approval_adapter.py\n'
                 '          .github/scripts/test_artifact_prerequisite_adapter.py\n'
                 '          .github/scripts/test_artifact_reconciliation_adapter.py\n'
                 '          .github/scripts/test_replylib.py\n'
                 '          .github/scripts/test_literal_python_reads.py\n'
                 '          --interpreter-env ARTIFACT_CONFORMANCE_PYTHON\n'
                 '          .github/scripts/test_artifact_conformance.py\n')
        assert block.count(command)==1
        assert 'python .github/scripts/test_work_github.py' not in block
        assert '--payload-root "'+p.SOURCE_PAYLOAD+'=${{ github.workspace }}"' in emit
        assert '--payload-root "'+p.NATIVE_PAYLOAD+'=${{ runner.temp }}"' in emit
        source=block.split('      - name: Upload mapped-work source-test inputs\n',1)[1].split('      - name:',1)[0]
        assert 'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9' in source
        assert 'include-hidden-files: true' in source and 'if-no-files-found: error' in source and 'overwrite: false' in source
        assert 'name: '+p.SOURCE_PAYLOAD+'\n' in source
        assert "GIT_CONFIG_KEY_0: core.autocrlf\n" in block and "GIT_CONFIG_VALUE_0: 'false'\n" in block

    def test_exact_owning_child_and_trusted_step_local_emitter_keep_nonprogram_flow(self):
        text=(owner.ROOT/'.github/workflows/ci.yml').read_text(encoding='utf8')
        self.check_workflow(text)
        replacements=[("matrix.expected_platform == 'windows/amd64' && github.event_name == 'push'","matrix.expected_platform == 'windows/amd64' && github.event_name == 'pull_request'"),
          ('steps.mapped_work_original.outcome == \'success\'','true'),
          ('GH_TOKEN: ${{ github.token }}','GH_TOKEN: omitted'),
          ('      actions: read\n','      actions: write\n'),
          ('--payload-root "ci20-native-tested-windows-2025=${{ runner.temp }}"','--payload-root "wrong=${{ runner.temp }}"'),
          ('          --interpreter-env ARTIFACT_CONFORMANCE_PYTHON\n','          --filter missing\n'),
          ('          .github/scripts/test_artifact_conformance.py\n','          .github/scripts/test_artifact_conformance.py || true\n'),
          ('        id: mapped_work_original\n','        id: mapped_work_original\n        continue-on-error: true\n')]
        for old,new in replacements:
            self.assertIn(old,text)
            with self.subTest(old=old):
                with self.assertRaises(AssertionError):self.check_workflow(text.replace(old,new))


class SandboxOwnedEffectsRoutingTests(unittest.TestCase):
    """Pure admission/map controls, never Docker/Vitest runtime qualification."""
    EXPECTED = {'disposition:transitions:S51:01': ['vitest:plugins/ca-sandbox/tools/claude-inside-cli.test.ts:#377 '
                                    'parseClaudeCli — what the entry point refuses REFUSES --token, because '
                                    'argv is world-readable',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside-cli.test.ts:#377 '
                                    'runClaudeInsideCli — the process contract passes the token from the '
                                    'ENVIRONMENT, not from argv',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside-cli.test.ts:#377 '
                                    'runClaudeInsideCli — the process contract exits with the usage code '
                                    'when the token is absent, and says where it comes from',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside-cli.test.ts:#377 '
                                    'parseClaudeCli — what the entry point refuses requires both the image '
                                    'and the home volume',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside-cli.test.ts:#377 '
                                    'parseClaudeCli — what the entry point refuses REFUSES --source-volume '
                                    'before a container can exist',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside.test.ts:buildClaudeRunArgs '
                                    '— env-token auth, no host bind (AC-12) backs HOME with a NAMED VOLUME '
                                    '(no host bind of ~/.claude), so state persists',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside.test.ts:buildClaudeRunArgs '
                                    '— hardened posture is enforced, not optional (AC-12) THROWS when the '
                                    'token volume would be co-mounted with an untrusted-code run',
                                    'vitest:plugins/ca-sandbox/tools/cp.test.ts:owned offline effect '
                                    'acceptance [docker] prepares a credential-blind owned home and retains '
                                    'its bytes across restart',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside-cli.test.ts:#377 '
                                    'parseClaudeCli — what the entry point refuses accepts the minimal '
                                    'invocation and defaults to the guaranteed posture',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside-cli.test.ts:#377 '
                                    'parseClaudeCli — what the entry point refuses refuses an unknown flag '
                                    'rather than ignoring it',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside-cli.test.ts:#377 '
                                    'parseClaudeCli — what the entry point refuses refuses any other egress '
                                    'posture, naming why',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside.test.ts:buildClaudeRunArgs '
                                    '— hardened posture is enforced, not optional (AC-12) requires a '
                                    'non-empty image, token, and home volume'],
 'disposition:transitions:S51:02': ['vitest:plugins/ca-sandbox/tools/claude-inside.test.ts:buildClaudeRunArgs '
                                    '— hardening parity with run.ts (architecture-002) carries every shared '
                                    'hardening flag the ordinary sandbox emits',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside.test.ts:buildClaudeRunArgs '
                                    '— env-token auth, no host bind (AC-12) passes only the token name in '
                                    'argv, never the reusable value',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside.test.ts:buildClaudeRunArgs '
                                    '— env-token auth, no host bind (AC-12) NEVER passes --privileged and '
                                    'NEVER mounts the docker socket',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside.test.ts:buildClaudeRunArgs '
                                    '— env-token auth, no host bind (AC-12) defaults egress to offline (the '
                                    'hard default — Spike B caveat)',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside.test.ts:buildClaudeRunArgs '
                                    '— hardened posture is enforced, not optional (AC-12) REFUSES an '
                                    'arbitrary wide-open network policy (no escaping the hard default)',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside.test.ts:#377 - a '
                                    'token-bearing box never runs NET_ADMIN without its firewall supplies '
                                    'the token only to the Docker run process environment',
                                    'vitest:plugins/ca-sandbox/tools/cp.test.ts:owned offline effect '
                                    'acceptance [docker] runs the real Claude builder offline with scoped '
                                    'dummy env and effective hardening',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside-cli.test.ts:#377 '
                                    'runClaudeInsideCli — the process contract passes the token from the '
                                    'ENVIRONMENT, not from argv',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside-cli.test.ts:#377 '
                                    'runClaudeInsideCli — the process contract exits with the usage code '
                                    'when the token is absent, and says where it comes from',
                                    'vitest:plugins/ca-sandbox/tools/claude-inside-cli.test.ts:#377 '
                                    'parseClaudeCli — what the entry point refuses REFUSES --source-volume '
                                    'before a container can exist',
                                    'vitest:plugins/ca-sandbox/tools/cp.test.ts:owned offline effect '
                                    'acceptance [docker] prepares a credential-blind owned home and retains '
                                    'its bytes across restart'],
 'disposition:transitions:S52:06': ['vitest:plugins/ca-sandbox/tools/cp.test.ts:buildCpOutArgs — pull-only '
                                    'direction (AC-10) assembles `cp <id>:<containerPath> <hostDest>` in the '
                                    'pull direction',
                                    'vitest:plugins/ca-sandbox/tools/cp.test.ts:buildCpOutArgs — pull-only '
                                    'direction (AC-10) never produces the reverse direction (host source '
                                    'before container dest)',
                                    'vitest:plugins/ca-sandbox/tools/cp.test.ts:buildCpOutArgs — pull-only '
                                    'direction (AC-10) refuses an empty container id, container path, or '
                                    'host dest',
                                    'vitest:plugins/ca-sandbox/tools/cp.test.ts:assertNoCopyInBind — '
                                    'host->container bind is impossible (AC-10) throws (via the mount '
                                    'chokepoint) on a -v host:container bind copy-in',
                                    'vitest:plugins/ca-sandbox/tools/cp.test.ts:assertNoCopyInBind — '
                                    'host->container bind is impossible (AC-10) throws on an explicit '
                                    'type=bind copy-in spec',
                                    'vitest:plugins/ca-sandbox/tools/cp.test.ts:assertNoCopyInBind — '
                                    'host->container bind is impossible (AC-10) the rejection comes from '
                                    'mounts.ts (cp does not hand-roll its own check)',
                                    'vitest:plugins/ca-sandbox/tools/cp.test.ts:owned offline effect '
                                    'acceptance [docker] retains real partial docker cp bytes after '
                                    'cancellation without rollback metadata',
                                    'vitest:plugins/ca-sandbox/tools/cp.test.ts:cpOut [docker] — pulls a '
                                    'file from /work to the host (AC-10) copies /work/<f> out to a host dest '
                                    'with identical bytes']}
    JOB = "[CHECK] | [SBX ] | Sandbox driver contract"

    def _assert_canonical_groups(self, groups):
        self.assertEqual(len(groups), 3)
        self.assertEqual({cell for group in groups for cell in group["cells"]}, set(self.EXPECTED))
        for group in groups:
            self.assertEqual(len(group["cells"]), 1)
            cell = group["cells"][0]
            self.assertEqual(group["job"], self.JOB)
            self.assertEqual(group["payload_name"], "major-source-inputs-sandbox-driver")
            self.assertEqual(group["observation"], "sandbox-tools")
            self.assertEqual(group["proof_kind"], "source-test")
            self.assertEqual(len(group["selectors"]), len(set(group["selectors"])))
            self.assertEqual(set(group["selectors"]), set(self.EXPECTED[cell]))

    def _groups(self):
        groups = owner.validate_selections(owner.load_json(owner.ROOT / ".github/major-test-selections.json"))
        selected = [copy.deepcopy(group) for group in groups if set(group["cells"]) & set(self.EXPECTED)]
        self._assert_canonical_groups(selected)
        return selected

    def test_canonical_three_cells_require_complete_guard_and_real_effect_unions(self):
        groups = self._groups()
        self.assertEqual(owner.TS_PROFILE_CELLS["sandbox-tools-v1"],
                         frozenset(self.EXPECTED) | {"disposition:transitions:S54:01"})
        self.assertEqual(owner.TS_PROFILE_CELLS["pi-tools-v1"], frozenset(
            "disposition:transitions:pi-qualification:disposable-home:" + number
            for number in ("01", "02", "03")))
        policy = owner.load_json(owner.ROOT / ".github/major-qualification-policy.json")
        for cell in self.EXPECTED:
            self.assertEqual(policy["cell_job_bindings"][cell], self.JOB)
        for index, group in enumerate(groups):
            for selector in group["selectors"]:
                # Removing any guard OR real-effect selector is a semantic map
                # regression, even if all remaining runtime names would pass.
                bad = copy.deepcopy(groups); bad[index]["selectors"].remove(selector)
                with self.subTest(cell=group["cells"][0], missing=selector), self.assertRaises(AssertionError):
                    self._assert_canonical_groups(bad)
        self.assertFalse(any("installed:" in cell or cell.startswith("task:") or ":machines:" in cell
                             for group in groups for cell in group["cells"]))

    def test_all_named_guards_and_effects_must_pass_under_original_bound_source_profile(self):
        groups = self._groups()
        with vitest_source_fixture("sandbox-tools-v1") as fixture:
            payload = VitestSourceProducerTests.authenticate(self, fixture)
            selectors = sorted({name for group in groups for name in group["selectors"]})
            # Inert data seams for the pure reader. These are deliberately not
            # observations from the actual Docker fixture or a live CI job.
            observed = {"format": owner.OBSERVATION, **fixture["identity"], "ci_run_id": 7,
                "source_stable": True, "proof_kind": "source-test", "producer": "vitest-json-observer",
                "argv": fixture["command"], "exit_code": 0,
                "tests": [{"id": name, "result": "passed"} for name in selectors],
                "source_input_binding": {"format": owner.SOURCE_BINDING, "profile": "sandbox-tools-v1",
                    "payload_name": fixture["spec"]["payload"],
                    "manifest_sha256": owner.readiness.digest((fixture["staged"] / owner.SOURCE_MANIFEST).read_bytes())}}
            req = {**fixture["identity"], "ci_run_id": 7, "cells": sorted(self.EXPECTED),
                   "cell_jobs": dict.fromkeys(self.EXPECTED, self.JOB)}
            def build(observation=observed, consumed=payload, selected=groups, required=req):
                return owner.build_report(required, job_name=self.JOB, job_id=9,
                    selections={"schema": owner.SELECTIONS, "groups": selected},
                    observations={"sandbox-tools": observation},
                    payloads={fixture["spec"]["payload"]: consumed})
            result = build()
            self.assertEqual({row["cell"] for row in result["results"]}, set(self.EXPECTED))
            for selector in selectors:
                for state in ("missing", "skipped", "failed", "duplicate"):
                    changed = copy.deepcopy(observed)
                    row = next(row for row in changed["tests"] if row["id"] == selector)
                    if state == "missing": changed["tests"].remove(row)
                    elif state == "duplicate": changed["tests"].append(dict(row))
                    else: row["result"] = state
                    with self.subTest(selector=selector, state=state), self.assertRaises(ValueError): build(changed)
            for failure in ("source", "run", "unstable", "exit", "producer", "profile", "manifest", "uploader", "role"):
                changed, consumed, selected = copy.deepcopy(observed), copy.deepcopy(payload), copy.deepcopy(groups)
                if failure == "source": changed["source_commit"] = "f" * 40
                if failure == "run": changed["ci_run_id"] = 8
                if failure == "unstable": changed["source_stable"] = False
                if failure == "exit": changed["exit_code"] = 1
                if failure == "producer": changed["producer"] = "claimed-docker-pass"
                if failure == "profile": changed["source_input_binding"]["profile"] = "unknown-sandbox-profile"
                if failure == "manifest": consumed["source_manifest_sha256"] = "0" * 64
                if failure == "uploader": consumed["source_upload_job_id"] = True
                if failure == "role": selected[0]["payload_name"] = "foreign-native-archive"
                with self.subTest(failure=failure), self.assertRaises(ValueError): build(changed, consumed, selected)
            for cell in ("disposition:transitions:S51:03", "disposition:machines:S51", "task:SBX-D04", "installed:sandbox:linux"):
                changed = copy.deepcopy(groups[0]); changed["cells"] = [cell]
                required = {**req, "cells": [cell], "cell_jobs": {cell: self.JOB}}
                with self.subTest(unowned=cell), self.assertRaises(ValueError): build(selected=[changed], required=required)

SDK_PYTHON_FIXTURE_PATHS = frozenset(('.github/fixtures/pi-hosts/1.5.0/.npmrc',
 '.github/fixtures/pi-hosts/1.5.0/package-lock.json',
 '.github/fixtures/pi-hosts/1.5.0/package.json',
 '.github/fixtures/pi-hosts/1.5.0/review.json',
 '.github/major-qualification-policy.json',
 '.github/major-test-selections.json',
 '.github/scripts/_boundedproc.py',
 '.github/scripts/_contextverificationlib.py',
 '.github/scripts/_immutable_git_blobs.py',
 '.github/scripts/ci20_native_binding.py',
 '.github/scripts/major_qualification_report.py',
 '.github/scripts/major_readiness.py',
 '.github/scripts/pi_cli_resolver.py',
 '.github/scripts/pi_host_locks.py',
 '.github/scripts/test_pi_package.py',
 '.github/scripts/test_pi_platform_contract.py',
 '.github/workflows/ci.yml',
 'core/pysrc/_artifactauthoritylib.py',
 'core/pysrc/_artifactlib.py',
 'core/pysrc/_artifactmanifestlib.py',
 'core/pysrc/_artifactpromptlib.py',
 'core/pysrc/_gitexec.py',
 'core/pysrc/_replylib.py',
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
 'plugins/ca/tools/redactor.ts'))


@contextmanager
def sdk_python_source_fixture():
    """Real private Git/source transport, inert Python only; never SDK qualification."""
    with tempfile.TemporaryDirectory(prefix="ca-sdk-python-profile-") as temporary:
        base=Path(temporary).resolve(); repo=base/"repo";repo.mkdir()
        # The closed path set is maintained production data, not a fixture override.
        paths = getattr(owner,"SDK_SOURCE_PATHS",SDK_PYTHON_FIXTURE_PATHS)
        for relative in paths:
            target=repo/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((Path(os.environ.get("CA_SDK_CANONICAL_ROOT", owner.ROOT))/relative).read_bytes())
        counter=base/"counter"
        method="test_real_sdk_footer_owner_disposal_restores_native_without_clobbering_replacement"
        # Explicitly synthetic observer control: this method name is not evidence of SDK execution.
        program=("import unittest,pathlib\nclass PiPackageTests(unittest.TestCase):\n"
                 f" def {method}(self):\n"
                 f"  p=pathlib.Path({str(counter)!r});p.write_text(p.read_text()+'x' if p.exists() else 'x')\n"
                 "if __name__=='__main__':unittest.main()\n")
        (repo/".github/scripts/test_pi_package.py").write_text(program,encoding="utf-8",newline="\n")
        git=shutil.which("git");assert git
        environment={key:value for key,value in os.environ.items() if key.upper() in ("SYSTEMROOT","WINDIR","SYSTEMDRIVE","COMSPEC","PATHEXT")}
        environment.update(PATH=os.pathsep.join([str(Path(git).parent),str(Path(sys.executable).parent)]),
                           HOME=str(base),USERPROFILE=str(base),GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM="1",
                           GIT_AUTHOR_NAME="fixture",GIT_AUTHOR_EMAIL="fixture@invalid",GIT_COMMITTER_NAME="fixture",GIT_COMMITTER_EMAIL="fixture@invalid",
                           GITHUB_RUN_ID="7",PYTHONDONTWRITEBYTECODE="1")
        with mock.patch.dict(os.environ,environment,clear=True):
            for arguments in (["init"],["config","core.autocrlf","false"],["add","."],["-c","commit.gpgsign=false","commit","-qm","SDK source fixture"]):
                phase="init" if arguments[0] in ("init","config") else "index" if arguments[0]=="add" else "commit"
                run_git_phase([git,"-C",str(repo),*arguments],phase=phase,trace_dir=base)
            staged=base/"staged"
            yield {"base":base,"repo":repo,"staged":staged,"counter":counter,
                   "profile":"pi-sdk-footer-v1","job":"[CHECK] | [PI  ] | Host-independent adapter contract",
                   "payload":"major-source-inputs-pi-sdk-footer","cell":"disposition:transitions:S18:07"}


class SdkPythonSourceProfileTests(unittest.TestCase):
    def prepare(self,f):
        return owner.prepare_source_payload(f["repo"],f["staged"],f["job"],f["profile"])

    def original(self,f):
        output=f["base"]/"observed.json"
        self.assertEqual(owner.observe_python(f["repo"],".github/scripts/test_pi_package.py",[],output,
                         f["staged"],profile=f["profile"]),0)
        return owner.load_json(output)

    def authenticate(self,f,job=None,mutate=None):
        files={p.relative_to(f["staged"]).as_posix():p.read_bytes() for p in f["staged"].rglob("*") if p.is_file()}
        if mutate:mutate(files)
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,"w") as archive:
            for name,value in files.items():archive.writestr(name,value)
        identity=owner.source_identity(f["repo"],f["profile"])
        req={**identity,"ci_run_id":7,"cells":[f["cell"]],"cell_jobs":{f["cell"]:f["job"]}}
        job=job if job is not None else {"id":9,"name":f["job"],"status":"in_progress","conclusion":None,
             "steps":[{"name":"Upload Pi SDK footer source-test inputs","status":"completed","conclusion":"success"}]}
        with mock.patch.object(owner.readiness,"artifact_bytes",return_value=raw.getvalue()) as archive_read, \
             mock.patch.object(owner.readiness,"validate_upload",side_effect=AssertionError("active own job log is unavailable")) as own_log:
            payload=owner.authenticated_payload({"id":8,"name":f["payload"]},req,f["repo"],source_job=job)
            archive_read.assert_called_once();own_log.assert_not_called()
        return req,payload

    def selection(self,f,observed):
        return {"schema":owner.SELECTIONS,"groups":[{"id":"sdk","job":f["job"],"payload_name":f["payload"],
          "observation":"sdk","proof_kind":"source-test","selectors":[observed["tests"][0]["id"]],"cells":[f["cell"]],
          "scope":"Pure synthetic source-observer admission test; no actual SDK claim"}]}

    def build(self,f,observed,selection=None):
        req,payload=self.authenticate(f)
        selection=selection or self.selection(f,observed)
        req.update(cells=selection["groups"][0]["cells"],cell_jobs={cell:f["job"] for cell in selection["groups"][0]["cells"]})
        return owner.build_report(req,job_name=f["job"],job_id=9,selections=selection,
                                  observations={"sdk":observed},payloads={f["payload"]:payload})

    def test_public_closed_sdk_profile_observes_one_original_python_invocation(self):
        with sdk_python_source_fixture() as f:
            try:self.prepare(f)
            except ValueError as error:self.fail("Existing owning source transport refuses the finite SDK Python profile: "+str(error))
            observed=self.original(f)
            self.assertEqual(f["counter"].read_text(encoding="utf-8"),"x")
            self.assertEqual(observed["producer"],"python-test-result-observer")
            self.assertEqual(observed["source_input_binding"]["profile"],f["profile"])
            self.assertEqual(observed["tests"],[{"id":"python:.github/scripts/test_pi_package.py:__main__.PiPackageTests.test_real_sdk_footer_owner_disposal_restores_native_without_clobbering_replacement","result":"passed"}])
            report=self.build(f,observed)
            self.assertEqual([row["cell"] for row in report["results"]],[f["cell"]])
            self.assertEqual(report["results"][0]["executed_population"],1)

    def test_sdk_original_script_arguments_and_unknown_profile_refuse_before_effect(self):
        with sdk_python_source_fixture() as f:
            self.prepare(f)
            for script,arguments,profile in ((".github/scripts/pi_cli_resolver.py",[],f["profile"]),
                (".github/scripts/test_pi_package.py",["--rpc-commands"],f["profile"]),
                (".github/scripts/test_pi_package.py",["PiPackageTests.test_one"],f["profile"]),
                (".github/scripts/test_pi_package.py",[],"pi-sdk-footer-other")):
                with self.subTest(script=script,arguments=arguments,profile=profile),self.assertRaises(ValueError):
                    owner.observe_python(f["repo"],script,arguments,f["base"]/"not-created.json",f["staged"],profile=profile)
            self.assertFalse(f["counter"].exists())
            self.assertFalse((f["base"]/"not-created.json").exists())

    def test_sdk_one_cell_cap_and_python_identity_refuse_skip_duplicate_and_relabel(self):
        with sdk_python_source_fixture() as f:
            self.prepare(f);observed=self.original(f);selection=self.selection(f,observed)
            for cell in ("disposition:transitions:S18:06","disposition:machines:S18","task:PI-D07","installed:pi:linux:1.5.0"):
                bad=copy.deepcopy(selection);bad["groups"][0]["cells"]=[cell]
                with self.subTest(cell=cell),self.assertRaises(ValueError):self.build(f,observed,bad)
            for failure in ("skipped","failed","missing","duplicate","vitest","arguments","source","run"):
                bad=copy.deepcopy(observed)
                if failure=="missing":bad["tests"]=[]
                elif failure=="duplicate":bad["tests"]*=2
                elif failure=="vitest":bad["producer"]="vitest-json-observer"
                elif failure=="arguments":bad["argv"].append("--rpc-commands")
                elif failure=="source":bad["source_commit"]="e"*40
                elif failure=="run":bad["ci_run_id"]=8
                else:bad["tests"][0]["result"]=failure
                with self.subTest(failure=failure),self.assertRaises(ValueError):self.build(f,bad,selection)

    def test_completed_prior_upload_is_required_but_active_own_job_log_is_not(self):
        with sdk_python_source_fixture() as f:
            self.prepare(f);self.authenticate(f)
            original={"id":9,"name":f["job"],"status":"in_progress","conclusion":None,
                      "steps":[{"name":"Upload Pi SDK footer source-test inputs","status":"completed","conclusion":"success"}]}
            for failure in ("no-step","failed-step","active-step","wrong-job","completed-own-job","wrong-source","extra-member"):
                job=copy.deepcopy(original)
                if failure=="no-step":job["steps"]=[]
                elif failure=="failed-step":job["steps"][0]["conclusion"]="failure"
                elif failure=="active-step":job["steps"][0]["status"]="in_progress"
                elif failure=="wrong-job":job["name"]="another job"
                elif failure=="completed-own-job":job["status"]="completed"
                def mutate(files):
                    if failure=="wrong-source":
                        value=json.loads(files[owner.SOURCE_MANIFEST]);value["source_commit"]="e"*40
                        files[owner.SOURCE_MANIFEST]=json.dumps(value).encode()
                    elif failure=="extra-member":files["unexpected.json"]=b"{}"
                with self.subTest(failure=failure),self.assertRaises(ValueError):self.authenticate(f,job,mutate)

    def test_sdk_source_namespace_and_dirty_inputs_never_become_stable(self):
        with sdk_python_source_fixture() as f:
            self.prepare(f)
            unknown=f["repo"]/"plugins/ca-pi/tools/src/untracked-shadow.ts";unknown.write_text("export {};",encoding="utf-8")
            with self.assertRaises(ValueError):owner.source_input_snapshot(f["repo"],f["profile"])
            self.assertEqual(unknown.read_text(encoding="utf-8"),"export {};")
            unknown.unlink()
            member=f["repo"]/"plugins/ca-pi/tools/src/status.ts";member.write_bytes(member.read_bytes()+b"\n// changed\n")
            with self.assertRaises(ValueError):owner.source_input_snapshot(f["repo"],f["profile"])
            self.assertFalse(f["counter"].exists())

    def test_final_reader_requires_original_sdk_upload_exact_owner_and_completed_job(self):
        cell="disposition:transitions:S18:07";job_name="[CHECK] | [PI  ] | Host-independent adapter contract"
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,"w") as archive:archive.writestr("source-member",b"inert")
        content=raw.getvalue();members=owner.readiness.members(content)
        source={"id":8,"name":"major-source-inputs-pi-sdk-footer"};artifact={"id":10,"name":"major-qualification-9"}
        job={"id":9,"name":job_name,"status":"completed","conclusion":"success"}
        req={"source_commit":"a"*40,"source_tree":"b"*40,"ci_run_id":7,"cells":[cell],"cell_jobs":{cell:job_name},"required_artifact_names":[source["name"]]}
        report={"schema":"codearbiter-major-qualification/2",**{key:req[key] for key in ("source_commit","source_tree","ci_run_id")},"job_id":9,
          "payloads":[{"artifact_id":8,"archive_sha256":owner.readiness.digest(content),"members":members}],
          "results":[{"cell":cell,"result":"PASSED","commands":[{"argv":["python",".github/scripts/test_pi_package.py"],"exit_code":0}],"selected_population":1,"executed_population":1,"payload_artifact_id":8}]}
        jobs=[job,{"id":11,"name":"major readiness producer"}]
        with mock.patch.object(owner.readiness,"read_artifact_json",return_value=report), \
             mock.patch.object(owner.readiness,"artifact_bytes",return_value=content), \
             mock.patch.object(owner.readiness,"validate_upload") as attribution:
            owner.readiness.produce(req,[source,artifact],jobs)
            self.assertEqual(attribution.call_args_list,[mock.call(job,artifact,"Upload major qualification report"),
                mock.call(job,source,"Upload Pi SDK footer source-test inputs")])
            for failure in ("wrong-owner","in-progress","upload-refused"):
                modified=copy.deepcopy(jobs);requirements=copy.deepcopy(req)
                attribution.side_effect=None
                if failure=="wrong-owner":
                    modified[0]["name"]="other";requirements["cell_jobs"][cell]="other"
                elif failure=="in-progress":modified[0].update(status="in_progress",conclusion=None)
                else:attribution.side_effect=owner.readiness.ReadinessError("original source uploader refused")
                with self.subTest(failure=failure),self.assertRaises(owner.readiness.ReadinessError):
                    owner.readiness.produce(requirements,[source,artifact],modified)


if __name__ == "__main__":
    unittest.main(verbosity=2)
