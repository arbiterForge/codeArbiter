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

    def build(self, *, composed_cells=None):
        req = self.req if composed_cells is None else {
            **self.req, "declared_source_finding_cells": composed_cells}
        return owner.build_report(req, job_name="owning native job", job_id=9,
                                  selections=self.map, observations={"native": self.observation},
                                  payloads={"candidate": self.payload})

    def test_original_job_reports_direct_cells_when_it_also_supplies_a_composed_cell(self):
        scenario = "scenario:SEQ-27"
        self.req["cells"].append(scenario)
        self.req["cell_jobs"][scenario] = "owning native job"
        with self.assertRaisesRegex(ValueError, "composed source findings"):
            self.build()
        actual = self.build(composed_cells=[scenario])
        self.assertEqual([row["cell"] for row in actual["results"]], [self.cell])

        with self.assertRaisesRegex(ValueError, "outside the original requirement population"):
            self.build(composed_cells=["scenario:SEQ-21", scenario])
        with self.assertRaisesRegex(ValueError, "invalid original source finding composition selection"):
            self.build(composed_cells=[self.cell])
        self.map["groups"][0]["cells"].append(scenario)
        with self.assertRaisesRegex(ValueError, "also has a direct report selection"):
            self.build(composed_cells=[scenario])

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
        # Keep dedicated source-test and cross-job admissions separate from
        # this ordinary report serialization fixture.
        source_cells = {*owner.SOURCE_FINDING_COMPOSITIONS, *owner.RECOVERY_FINDING_CELLS,
                        *owner.PYTHON_FINDING_RECIPES, *owner.SOURCE_PROFILE_CELLS,
                        owner.HOOK_F02_CELL, "task:Q-02"}
        cells = [cell for cell in cells if cell not in source_cells]
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



class SourceIdentityFreshIndexTests(unittest.TestCase):
    def fixture(self):
        from test_retained_archive_cli_observation import observer_checkout_fixture
        return observer_checkout_fixture({"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "false",
                                          "GIT_CONFIG_KEY_1": "core.eol", "GIT_CONFIG_VALUE_1": "lf"})

    def tree_state(self, root):
        return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_dev, p.stat().st_ino,
                 p.stat().st_mode, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                for p in root.rglob("*") if p.is_file()}

    def test_staged_and_conflict_changes_refuse_when_HEAD_worktree_is_clean(self):
        from retained_archive_cli_observation import private_environment
        from _gitexec import local_read_git_env
        for kind in ("staged", "conflict"):
            with self.subTest(kind=kind), self.fixture() as f, private_environment(f["repo"].parent / "control-home"):
                repo = f["repo"]; env = local_read_git_env()
                def git(*args, data=None):
                    return subprocess.run(["git", "-C", str(repo), *args], input=data, env=env,
                                          capture_output=True, check=True, timeout=15).stdout
                target = "plugins/ca/tools/.env.example"
                blob = git("rev-parse", "HEAD:core/pysrc/helper.py").decode().strip()
                if kind == "staged":
                    git("update-index", "--cacheinfo", "100644", blob, target)
                else:
                    rows = "0 " + "0" * len(blob) + "\t" + target + "\n"
                    rows += "".join("100644 " + blob + " " + str(stage) + "\t" + target + "\n" for stage in (1, 2, 3))
                    git("update-index", "--index-info", data=rows.encode())
                before = self.tree_state(repo)
                identity, status = owner.source_checkout(repo)
                self.assertFalse(identity["clean"])
                self.assertIn(target.encode(), status)
                if kind == "conflict": self.assertIn(b"UU ", status)
                self.assertEqual(self.tree_state(repo), before)

    @unittest.skipUnless(os.name == "nt", "Git for Windows path policy")
    def test_fresh_index_reads_clean_and_modified_long_paths(self):
        from retained_archive_cli_observation import private_environment
        from _gitexec import local_read_git_env

        with self.fixture() as fixture, private_environment(fixture["repo"].parent / "control-home"):
            repo = fixture["repo"]
            name = Path("a" * 95, "b" * 95, "c" * 95, "candidate.txt")
            self.assertGreater(len(str(repo / name)), 260)
            physical = Path("\\\\?\\" + str(repo / name))
            physical.parent.mkdir(parents=True)
            physical.write_bytes(b"original owned bytes\n")
            argv = ["git", "-C", str(repo), "-c", "core.longpaths=true", "-c", "commit.gpgsign=false",
                    "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid"]
            env = local_read_git_env()
            subprocess.run([*argv, "add", "--", name.as_posix()], env=env,
                           check=True, capture_output=True, timeout=15)
            subprocess.run([*argv, "commit", "-qm", "long path fixture"], env=env,
                           check=True, capture_output=True, timeout=15)
            subprocess.run([*argv, "config", "core.longpaths", "false"], env=env,
                           check=True, capture_output=True, timeout=15)
            before = (repo / ".git/index").read_bytes()
            self.assertTrue(owner.source_checkout(repo)[0]["clean"])
            physical.write_bytes(b"changed owned bytes\n")
            identity, status = owner.source_checkout(repo)
            self.assertFalse(identity["clean"])
            self.assertIn(b" M " + name.as_posix().encode("ascii") + b"\0", status)
            self.assertEqual((repo / ".git/index").read_bytes(), before)

    def test_source_read_is_credential_blind_and_only_private_index_commands_disable_caches(self):
        from retained_archive_cli_observation import private_environment
        with self.fixture() as f, private_environment(f["repo"].parent / "control-home"):
            repo = f["repo"]
            protected = repo.parent / "protected.gitconfig"
            protected.write_text("[safe]\n\tdirectory = " + str(repo).replace("\\", "/") + "\n", encoding="utf8")
            calls=[]; actual=owner.subprocess.run
            def observe(argv, **kwargs):
                calls.append((list(argv), dict(kwargs["env"])))
                return actual(argv, **kwargs)
            values={"GH_TOKEN":"inert-source-canary", "GITHUB_TOKEN":"inert-source-canary",
                    "UNRELATED_SECRET":"inert-source-canary", "GIT_CONFIG_COUNT":"1",
                    "GIT_CONFIG_KEY_0":"http.extraheader", "GIT_CONFIG_VALUE_0":"inert-source-canary",
                    "GIT_CONFIG_GLOBAL":str(protected), "GIT_DIR":"foreign-root", "GIT_INDEX_FILE":"foreign-index"}
            before=self.tree_state(repo)
            with mock.patch.dict(os.environ, values), mock.patch.object(owner.subprocess,"run",side_effect=observe):
                self.assertTrue(owner.source_identity(repo)["clean"])
                self.assertEqual(os.environ["GH_TOKEN"], "inert-source-canary")
            private=[]
            for argv, env in calls:
                self.assertIn("--no-optional-locks",argv)
                self.assertEqual(env["GIT_OPTIONAL_LOCKS"],"0")
                self.assertEqual(env["GIT_CONFIG_GLOBAL"],str(protected))
                for key in ("GH_TOKEN","GITHUB_TOKEN","UNRELATED_SECRET","GIT_CONFIG_COUNT","GIT_CONFIG_KEY_0","GIT_CONFIG_VALUE_0","GIT_DIR"):
                    self.assertNotIn(key,env)
                if "GIT_INDEX_FILE" in env:
                    private.append((argv,env))
                    self.assertFalse(Path(env["GIT_INDEX_FILE"]).is_relative_to(repo))
                    for setting in ("core.splitIndex=false","core.fsmonitor=false","core.untrackedCache=false","index.sparse=false","core.sparseCheckout=false"):
                        self.assertIn(setting,argv)
                else:
                    self.assertNotIn("-c",argv)
                    self.assertEqual(argv[argv.index("-C")+2],"rev-parse")
            self.assertEqual(len(private),3)
            self.assertEqual({next(name for name in ("diff","read-tree","status") if name in argv) for argv,_ in private},{"diff","read-tree","status"})
            self.assertEqual(self.tree_state(repo),before)
            # Switch the real index to an authentic split representation after
            # descriptor validation, immediately before the staged diff. Only
            # the owned byte-identical ordinary copy may be consumed by Git.
            ordinary=(repo/".git/index").read_bytes()
            from _gitexec import local_read_git_env
            subprocess.run(["git","-C",str(repo),"update-index","--split-index"],env=local_read_git_env(),check=True,capture_output=True,timeout=15)
            split=(repo/".git/index").read_bytes()
            (repo/".git/index").write_bytes(ordinary)
            shared={p.name:(p.read_bytes(),p.stat().st_mtime_ns,p.stat().st_ctime_ns) for p in (repo/".git").glob("sharedindex.*")}
            self.assertTrue(shared)
            actual_git=owner._source_git
            def switch_index(root,*args,index=None):
                if args[0]=="diff": (Path(root)/".git/index").write_bytes(split)
                return actual_git(root,*args,index=index)
            with mock.patch.object(owner,"_source_git",side_effect=switch_index),self.assertRaisesRegex(ValueError,"split source index"):
                owner.source_identity(repo)
            self.assertEqual({p.name:(p.read_bytes(),p.stat().st_mtime_ns,p.stat().st_ctime_ns) for p in (repo/".git").glob("sharedindex.*")},shared)
            self.assertEqual({name:(repo/name).read_bytes() for name in f["before"]},f["before"])

    def test_HEAD_or_real_index_race_refuses_instead_of_returning_clean(self):
        from retained_archive_cli_observation import private_environment
        for kind in ("HEAD", "index"):
            with self.subTest(kind=kind), self.fixture() as f, private_environment(f["repo"].parent / "control-home"):
                actual=owner._source_git; changed=False
                def racing(repo,*args,index=None):
                    nonlocal changed
                    result=actual(repo,*args,index=index)
                    if index is not None and args[0]=="status": changed=True
                    if changed and kind=="HEAD" and args==("rev-parse","HEAD"):
                        return b"f"*40+b"\n"
                    if changed and kind=="index":
                        with (Path(repo)/".git/index").open("ab") as stream: stream.write(b"owned-race")
                        changed=False
                    return result
                with mock.patch.object(owner,"_source_git",side_effect=racing), self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    owner.source_identity(f["repo"])

    def test_split_index_refuses_before_Git_can_refresh_real_shared_metadata(self):
        from retained_archive_cli_observation import private_environment
        from _gitexec import local_read_git_env
        with self.fixture() as f, private_environment(f["repo"].parent / "control-home"):
            repo=f["repo"]; env=local_read_git_env()
            subprocess.run(["git","-C",str(repo),"update-index","--split-index"],env=env,check=True,capture_output=True,timeout=15)
            before=self.tree_state(repo)
            with mock.patch.object(owner,"_source_git",wraps=owner._source_git) as git,self.assertRaisesRegex(ValueError,"split source index"):
                owner.source_identity(repo)
            self.assertTrue(all(call.args[1]=="rev-parse" for call in git.call_args_list))
            self.assertEqual(self.tree_state(repo),before)

    def test_ordinary_index_versions_and_bounded_extension_scan_keep_actual_Git_validation(self):
        from retained_archive_cli_observation import private_environment
        from _gitexec import local_read_git_env
        for version in (2,3,4):
            with self.subTest(version=version),self.fixture() as f,private_environment(f["repo"].parent/"control-home"):
                repo=f["repo"]; env=local_read_git_env()
                def git(*args):
                    return subprocess.run(["git","-C",str(repo),*args],env=env,check=True,capture_output=True,timeout=15).stdout
                (repo/"link").write_bytes(b"ordinary tracked filename, not an index extension\n")
                git("add","link")
                git("-c","user.name=fixture","-c","user.email=fixture@example.invalid","-c","commit.gpgsign=false","commit","-qm","ordinary link filename")
                git("update-index","--index-version",str(version))
                if version==3: git("update-index","--skip-worktree","core/pysrc/helper.py")
                self.assertEqual(int.from_bytes((repo/".git/index").read_bytes()[4:8],"big"),version)
                before=self.tree_state(repo)
                self.assertTrue(owner.source_identity(repo)["clean"])
                self.assertEqual(self.tree_state(repo),before)
        for size in (20,32):
            header=b"DIRC"+(2).to_bytes(4,"big")+bytes(4)
            # Pure parser vectors only; Git, not this scanner, validates the
            # trailing digest. No SHA-1 calculation or synthetic admission.
            owner._source_index_independent(header+bytes(size),size)
            for raw in (header+b"link"+bytes(4+size),
                        header+b"TREE"+(100).to_bytes(4,"big")+bytes(size),
                        b"BAD!"+header[4:]+bytes(size),
                        b"DIRC"+(5).to_bytes(4,"big")+bytes(4+size),
                        b"DIRC"+(2).to_bytes(4,"big")+bytes([255])*4+bytes(size),
                        b"DIRC"+(4).to_bytes(4,"big")+(1).to_bytes(4,"big")+bytes(42+size)+bytes([128])*10+bytes(1+size),
                        header+b"TREE"+bytes(3+size)):
                with self.subTest(size=size),self.assertRaises(ValueError):
                    owner._source_index_independent(raw,size)
            with self.assertRaises(ValueError): owner._source_index_independent(header+bytes(size),16)

    def test_failed_private_read_and_unreadable_actual_index_never_fall_back_to_cached_clean(self):
        from retained_archive_cli_observation import private_environment
        for kind in ("read-tree", "status", "index"):
            with self.subTest(kind=kind), self.fixture() as f, private_environment(f["repo"].parent / "control-home"):
                actual=owner._source_git
                def failure(repo,*args,index=None):
                    if index is not None and args[0]==kind:
                        raise subprocess.CalledProcessError(128,["git",kind])
                    return actual(repo,*args,index=index)
                if kind=="index":
                    with mock.patch.object(owner,"_source_index_state",side_effect=OSError("owned unavailable index")),self.assertRaises(OSError):
                        owner.source_identity(f["repo"])
                else:
                    with mock.patch.object(owner,"_source_git",side_effect=failure),self.assertRaises(subprocess.CalledProcessError):
                        owner.source_identity(f["repo"])

    def test_index_path_and_descriptor_metadata_must_each_stay_stable(self):
        from retained_archive_cli_observation import private_environment
        with self.fixture() as f, private_environment(f["repo"].parent / "control-home"):
            index=f["repo"] / ".git/index"
            actual=owner.os.fstat
            def stat_with_distinct_creation(fd):
                value=actual(fd)
                return SimpleNamespace(**{key:getattr(value,key) for key in ("st_dev","st_ino","st_mode","st_size","st_mtime_ns")},st_ctime_ns=value.st_ctime_ns+1)
            with mock.patch.object(owner.os,"fstat",side_effect=stat_with_distinct_creation):
                self.assertTrue(owner._source_index_state(index))
            changed=0
            def changing_descriptor(fd):
                nonlocal changed
                changed+=1;value=actual(fd)
                return SimpleNamespace(**{key:getattr(value,key) for key in ("st_dev","st_ino","st_mode","st_size","st_mtime_ns")},st_ctime_ns=value.st_ctime_ns+changed)
            with mock.patch.object(owner.os,"fstat",side_effect=changing_descriptor),self.assertRaisesRegex(ValueError,"source index changed during read"):
                owner._source_index_state(index)
            with mock.patch.object(Path,"is_symlink",return_value=True),self.assertRaisesRegex(ValueError,"bounded regular file"):
                owner._source_index_state(index)

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


class SourceTreeArgumentBudgetTests(unittest.TestCase):
    def test_large_real_source_profile_never_exceeds_windows_launch_arguments(self):
        with tempfile.TemporaryDirectory(prefix="ca-source-tree-argv-") as temporary:
            base = Path(temporary).resolve(); repo = base / "repo"; repo.mkdir()
            paths = frozenset("core/surface/%04d-\u00e9\U0001f600-%s.py" % (n, "x" * 24) for n in range(1132))
            value = b"owned immutable source\n"
            for relative in paths:
                target = repo / relative; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(value)
            git = shutil.which("git")
            self.assertIsNotNone(git)
            env = {k:v for k,v in os.environ.items() if k.upper() in
                   {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "TEMP", "TMP"}}
            env.update(PATH=os.pathsep.join([str(Path(git).parent), str(Path(sys.executable).parent)]),
                       HOME=str(base), USERPROFILE=str(base), GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
            original = subprocess.run
            with mock.patch.dict(os.environ, env, clear=True):
                for args in (("init", "-q"), ("config", "maintenance.autoDetach", "false"),
                             ("add", "."), ("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                             "-c", "commit.gpgsign=false", "commit", "-qm", "owned source profile")):
                    original([git, "-C", str(repo), *args], check=True, capture_output=True, timeout=30)
                before = owner._source_indices(repo)
                calls = []
                def windows_launch(command, *args, **kwargs):
                    if "ls-tree" in command:
                        units = len(subprocess.list2cmdline(command).encode("utf-16-le")) // 2 + 1
                        self.assertLessEqual(units, 32767,
                                             "immutable source query exceeds Windows process argument capacity")
                        calls.append(command[command.index("--") + 1:])
                    return original(command, *args, **kwargs)
                with mock.patch.object(owner, "SOURCE_PATHS", paths), \
                     mock.patch.object(owner.subprocess, "run", side_effect=windows_launch):
                    observed = owner.source_input_snapshot(repo)
                self.assertGreater(len(calls), 1)
                self.assertEqual([path for call in calls for path in call], sorted(paths))
                self.assertEqual(observed["members"], [{"path": path, "sha256": owner.readiness.digest(value),
                    "bytes": len(value), "git_mode": "100644"} for path in sorted(paths)])
                self.assertTrue(observed["clean"])
                self.assertEqual(owner._source_indices(repo), before)


    def test_batches_share_one_deadline_and_output_budget(self):
        paths = {"core/surface/%04d-%s.py" % (n, "x" * 80) for n in range(240)}
        with mock.patch.object(owner.time, "monotonic", side_effect=range(100)), \
             mock.patch.object(owner, "git", return_value=b"chunk") as query:
            rows = owner._source_tree_rows(Path("owned"), "a" * 40, paths)
        self.assertEqual(rows, b"chunk" * query.call_count)
        self.assertGreater(query.call_count, 1)
        timeouts = [call.kwargs["timeout"] for call in query.call_args_list]
        self.assertTrue(all(0 < later < earlier <= 30 for earlier, later in zip(timeouts, timeouts[1:])))
        with mock.patch.object(owner, "MAX_JSON", len(b"chunk")), \
             mock.patch.object(owner, "git", return_value=b"chunk") as query, \
             self.assertRaisesRegex(ValueError, "source tree output exceeds bound"):
            owner._source_tree_rows(Path("owned"), "a" * 40, paths)
        self.assertEqual(query.call_count, 2)

    def test_expired_aggregate_deadline_stops_before_another_launch(self):
        paths = {"core/surface/%04d-%s.py" % (n, "x" * 80) for n in range(240)}
        with mock.patch.object(owner.time, "monotonic", side_effect=[0, 1, 31]), \
             mock.patch.object(owner, "git", return_value=b"row") as query, \
             self.assertRaisesRegex(ValueError, "source tree query deadline exceeded"):
            owner._source_tree_rows(Path("owned"), "a" * 40, paths)
        self.assertEqual(query.call_count, 1)
        self.assertEqual(query.call_args.kwargs["timeout"], 29)

    def test_one_unlaunchable_unicode_argument_is_refused_before_git(self):
        with mock.patch.object(owner, "git") as query, \
             self.assertRaisesRegex(ValueError, "source tree argument exceeds launch bound"):
            owner._source_tree_rows(Path("owned"), "a" * 40, {"\U0001f600" * 9000})
        query.assert_not_called()

    def test_batched_query_still_refuses_missing_duplicate_and_wrong_mode_rows(self):
        with source_payload_fixture() as fixture:
            original = owner._source_tree_rows
            for fault in ("missing", "duplicate", "wrong-mode"):
                def changed(*args):
                    rows = original(*args).split(b"\0")
                    if fault == "missing":
                        rows.pop(0)
                    elif fault == "duplicate":
                        rows.insert(0, rows[0])
                    else:
                        rows[0] = b"120000" + rows[0][6:]
                    return b"\0".join(rows)
                with self.subTest(fault=fault), \
                     mock.patch.object(owner, "_source_tree_rows", side_effect=changed), \
                     self.assertRaisesRegex(ValueError, "source payload immutable (membership differs|member invalid)"):
                    owner.source_input_snapshot(fixture["repo"])


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
        self.assertTrue(all(options["timeout"]==60 and options["check"] and options["capture_output"] for _,options in calls))
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
        self.assertTrue(all(options["timeout"]==60 and options["check"] and options["capture_output"] for _,options in calls))

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
                self.assertEqual(run.call_args.kwargs["timeout"],60)
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
def autocrlf_source_checkout(profile, additional_paths=()):
    """Actual declared input bytes and attributes in a disposable local Git clone."""
    with tempfile.TemporaryDirectory(prefix="ca-source-autocrlf-") as temporary:
        base=Path(temporary).resolve();seed=base/'seed';seed.mkdir()
        paths=owner.source_profile(profile)["paths"]
        for relative in paths.union(additional_paths):
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

    def test_recovery_source_prepares_from_a_fresh_autocrlf_checkout(self):
        profile = owner.RECOVERY_RUNTIME_PROFILE
        spec = owner.source_profile(profile)
        surface = {path for path in owner.SOURCE_PATHS if path.startswith("core/surface/")}
        with autocrlf_source_checkout(profile, surface) as fixture:
            repo = fixture["repo"]
            payload = fixture["base"] / "recovery-source"
            manifest = owner.prepare_source_payload(repo, payload, spec["job"], profile)
            self.assertEqual({member["path"] for member in manifest["members"]}, spec["paths"])
            contract = "core/workflow-recovery-contract.json"
            expected = owner.git(repo, "show", "HEAD:" + contract, raw=True)
            self.assertEqual((repo / contract).read_bytes(), expected)
            self.assertEqual((payload / contract).read_bytes(), expected)

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



class GitHubReportDiagnosticTest(unittest.TestCase):
    def test_scope_refusal_logs_safe_github_operation_and_status(self):
        from contextlib import redirect_stderr
        error = owner.readiness.ReadinessError("readiness observation failed: gh")
        error.github_read_observation = {"operation": "run-jobs", "http_status": 503}
        emitted = io.StringIO()
        with (mock.patch.object(owner, "validate_emitter_environment", side_effect=error),
              redirect_stderr(emitted)):
            code = owner.main(["emit", "--repo", ".", "--output", "qualification.json",
                               "--job-name", "test owner", "--observation", "mock=absent.json"])
        self.assertEqual(code, 1)
        self.assertEqual(emitted.getvalue().strip(),
            "::error::Major qualification report pending: readiness observation failed: gh (run-jobs, HTTP 503)")


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
        run={'id':7,'head_sha':before['source_commit']}
        artifacts=[{'id':8,'name':p.SOURCE_PAYLOAD},{'id':10,'name':p.NATIVE_PAYLOAD}]
        import types
        native_module=types.ModuleType('major_native_observation')
        def authenticated(req_arg,run_arg,artifacts_arg,jobs_arg,platform):
            self.assertEqual(platform,'windows/amd64')
            self.assertIs(run_arg, run)
            self.assertNotEqual(req_arg['native_module_sha256']['windows'],'9'*64)
            self.assertEqual(set(req_arg['native_module_sha256']),{'posix','windows'})
            return {**component,'native_binding':{**component['native_binding'],
                    'module_sha256':req_arg['native_module_sha256']['windows']}}
        native_module.authenticate_component=mock.Mock(side_effect=authenticated)
        emitted=private/'qualification.json'
        with mock.patch.dict(sys.modules,{'major_native_observation':native_module}), \
             mock.patch.dict(os.environ,GITHUB_SHA=before['source_commit'],GITHUB_RUN_ID='7'), \
             mock.patch.object(owner,'ROOT',self.root),mock.patch.object(owner,'validate_emitter_environment'), \
             mock.patch.object(owner.readiness,'collect',return_value=(req,run,artifacts,[job])), \
             mock.patch.object(owner.readiness,'api',return_value={'id':7}) as api, \
             mock.patch.object(owner,'authenticated_payload',return_value=source) as source_auth, \
             mock.patch.object(p,'authenticate_native_consumption',return_value=native_payload) as consumed:
            self.assertEqual(owner.main(['emit','--repo',str(self.root),'--output',str(emitted),
               '--job-name',p.JOB,'--observation','mapped='+str(output),
               '--payload-root',p.SOURCE_PAYLOAD+'='+str(self.root),
               '--payload-root',p.NATIVE_PAYLOAD+'='+str(installation)]),0)
        native_module.authenticate_component.assert_called_once()
        source_auth.assert_called_once();consumed.assert_called_once();api.assert_not_called()
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
        configured = owner.validate_selections(owner.load_json(owner.ROOT / ".github/major-test-selections.json"))
        cells = {cell for group in configured if group["job"] == self.JOB
                 for cell in group["cells"] if cell not in owner.TS_FINDING_RECIPES}
        self.assertEqual(owner.TS_PROFILE_CELLS["sandbox-tools-v1"], cells)
        self.assertLessEqual(frozenset(self.EXPECTED) | {"disposition:transitions:S54:01"}, cells)
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



Q02_FIXTURE_SELECTORS = {'readiness': ('python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_valid_receipt_is_non_circular', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_publication_task_cannot_enter_prepublication_population', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_wrong_source_tree_run_and_manifests_refuse', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_forged_untrusted_run_refuses', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_missing_expired_wrong_archive_refuses', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_unknown_skipped_missing_duplicate_cells_refuse', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_caller_pass_cannot_replace_successful_named_job', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_wrong_or_expired_payload_artifact_refuses', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_distributed_settlement_is_not_prepublication', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_exact_member_readback_is_required_by_live_verification', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_unsettled_version_mismatch_never_bypasses_major_qualification', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_receipt_only_does_not_repeat_publication', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_malformed_marker_is_not_an_ordinary_release_escape', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_matching_candidate_without_required_readiness_remains_pending', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_producer_requires_original_executed_reports', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_producer_refuses_reports_without_the_named_jobs_upload_step', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_interned_report_payloads_preserve_exact_archive_and_member_admission', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_complete_frozen_population_receipt_fits_existing_json_bound', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_unfinished_program_cannot_produce_readiness', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_archive_members_reject_traversal_symlink_duplicates_and_empty', 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_first_effect_gate_precedes_tag_and_keeps_pi_provenance_check', 'python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_completed_metadata_does_not_clear_authoritative_confirmation', 'python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_preserved_rows_do_not_admit_a_nonexistent_evidence_commit', 'python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_existing_evidence_commit_does_not_make_an_unavailable_reference_valid', 'python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_complete_reviewed_population_preserves_local_origin_and_non_circularity', 'python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_complete_population_does_not_reopen_resolved_history_prose', 'python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_complete_population_rejects_missing_or_changed_raw_proof_and_inputs', 'python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_complete_population_rejects_a_review_that_does_not_cover_the_row', 'python:.github/scripts/test_major_readiness.py:__main__.UploadAttributionTest.test_exact_successful_upload_has_original_attribution', 'python:.github/scripts/test_major_readiness.py:__main__.UploadAttributionTest.test_artifact_service_clock_offset_does_not_override_authenticated_step_log', 'python:.github/scripts/test_major_readiness.py:__main__.UploadAttributionTest.test_original_actions_log_utf8_bom_is_accepted', 'python:.github/scripts/test_major_readiness.py:__main__.UploadAttributionTest.test_report_name_and_json_job_id_do_not_replace_successful_upload_step', 'python:.github/scripts/test_major_readiness.py:__main__.UploadAttributionTest.test_another_jobs_artifact_or_different_digest_or_window_refuses', 'python:.github/scripts/test_major_readiness.py:__main__.UploadAttributionTest.test_metadata_and_step_timestamps_still_require_wellformed_aware_values', 'python:.github/scripts/test_major_readiness.py:__main__.ProgramProducingGuardTest.test_finite_producer_catalog_does_not_require_unfinished_program_to_be_ready', 'python:.github/scripts/test_major_readiness.py:__main__.ProgramProducingGuardTest.test_program_push_is_producing_only_and_publication_reader_stays_main_only'), 'release': ('python:.github/scripts/test_release_workflow.py:__main__.TriggerTest.test_releases_follow_successful_main_ci_and_manual_retry', 'python:.github/scripts/test_release_workflow.py:__main__.TriggerTest.test_preflight_requires_a_successful_same_repo_main_push', 'python:.github/scripts/test_release_workflow.py:__main__.TriggerTest.test_dispatch_is_refused_off_the_default_branch', 'python:.github/scripts/test_release_workflow.py:__main__.TriggerTest.test_each_run_releases_its_own_commit_from_its_own_manifests', 'python:.github/scripts/test_release_workflow.py:__main__.TriggerTest.test_every_publisher_receives_the_selected_source_and_ci_run', 'python:.github/scripts/test_release_workflow.py:__main__.SourceSelectionTest.test_workflow_run_event_binds_its_own_run', 'python:.github/scripts/test_release_workflow.py:__main__.IndependenceTest.test_every_release_job_depends_only_on_the_preflight', 'python:.github/scripts/test_release_workflow.py:__main__.IndependenceTest.test_each_release_job_gates_only_on_its_own_eligibility', 'python:.github/scripts/test_release_workflow.py:__main__.IndependenceTest.test_one_targets_planning_error_does_not_block_the_others', 'python:.github/scripts/test_release_workflow.py:__main__.IndependenceTest.test_each_release_job_serializes_only_with_itself', 'python:.github/scripts/test_release_workflow.py:__main__.ConsumerSafetyGateTest.test_pi_publish_refuses_a_different_workflow_commit', 'python:.github/scripts/test_release_workflow.py:__main__.ConsumerSafetyGateTest.test_package_cohort_is_verified_before_anything_is_published', 'python:.github/scripts/test_release_workflow.py:__main__.ConsumerSafetyGateTest.test_attached_package_reads_back_byte_identical', 'python:.github/scripts/test_release_workflow.py:__main__.ConsumerSafetyGateTest.test_release_goes_public_only_after_every_channel', 'python:.github/scripts/test_release_workflow.py:__main__.ConsumerSafetyGateTest.test_receipt_is_written_after_the_release_is_public', 'python:.github/scripts/test_release_workflow.py:__main__.ReceiptShellBoundaryTest.test_missing_receipt_is_uploaded_once_and_replay_only_reads', 'python:.github/scripts/test_release_workflow.py:__main__.ReceiptShellBoundaryTest.test_same_named_wrong_receipt_is_downloaded_and_refused_without_overwrite', 'python:.github/scripts/test_release_workflow.py:__main__.ReceiptShellBoundaryTest.test_uploaded_receipt_with_lost_response_is_observed_before_retry')}


@contextmanager
def q02_python_source_fixture():
    """Synthetic transport controls, never an executed Q02 product qualification."""
    with tempfile.TemporaryDirectory(prefix="ca-q02-python-profile-") as temporary:
        base=Path(temporary).resolve();repo=base/"repo";repo.mkdir()
        canonical=Path(os.environ.get("CA_Q02_CANONICAL_ROOT",owner.ROOT))
        paths=getattr(owner,"Q02_SOURCE_PATHS",frozenset((".github/scripts/test_major_readiness.py",".github/scripts/test_release_workflow.py")))
        for relative in paths:
            target=repo/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((canonical/relative).read_bytes())
        counter=base/"counter"
        for key,script in (("readiness","test_major_readiness.py"),("release","test_release_workflow.py")):
            classes={}
            for selector in Q02_FIXTURE_SELECTORS[key]:
                cls,method=selector.rsplit(":",1)[1].removeprefix("__main__.").split(".")
                classes.setdefault(cls,[]).append(method)
            program="import unittest,pathlib\n"+f"p=pathlib.Path({str(counter)!r});p.write_text((p.read_text() if p.exists() else '')+{key[0]!r})\n"
            for cls,methods in classes.items():
                program+=f"class {cls}(unittest.TestCase):\n"
                for method in methods:program+=f" def {method}(self): self.assertTrue(True)\n"
            program+="if __name__=='__main__': unittest.main()\n"
            (repo/".github/scripts"/script).write_text(program,encoding="utf-8",newline="\n")
        git=shutil.which("git");assert git
        env={k:v for k,v in os.environ.items() if k.upper() in ("SYSTEMROOT","WINDIR","SYSTEMDRIVE","COMSPEC","PATHEXT")}
        env.update(PATH=os.pathsep.join([str(Path(git).parent),str(Path(sys.executable).parent)]),
                   HOME=str(base),USERPROFILE=str(base),GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM="1",
                   GIT_AUTHOR_NAME="fixture",GIT_AUTHOR_EMAIL="fixture@invalid",GIT_COMMITTER_NAME="fixture",GIT_COMMITTER_EMAIL="fixture@invalid",
                   GITHUB_RUN_ID="7",PYTHONDONTWRITEBYTECODE="1")
        with mock.patch.dict(os.environ,env,clear=True):
            for args in (["init"],["config","core.autocrlf","false"],["add","."],["-c","commit.gpgsign=false","commit","-qm","Q02 fixture"]):
                run_git_phase([git,"-C",str(repo),*args],phase="init" if args[0] in ("init","config") else "index" if args[0]=="add" else "commit",trace_dir=base)
            yield {"base":base,"repo":repo,"staged":base/"staged","counter":counter,
                   "profile":"major-readiness-implementation-v1","job":"[CHECK] | [CORE] | Hook contract  <os: windows-latest · partition: contracts>",
                   "payload":"major-source-inputs-q02-implementation","cell":"task:Q-02"}


class Q02ReadinessSourceProfileTests(unittest.TestCase):
    def original(self,f):
        owner.prepare_source_payload(f["repo"],f["staged"],f["job"],f["profile"])
        observed={}
        for key,script in (("readiness","test_major_readiness.py"),("release","test_release_workflow.py")):
            output=f["base"]/(key+".json")
            self.assertEqual(owner.observe_python(f["repo"],".github/scripts/"+script,[],output,f["staged"],f["profile"]),0)
            observed[key]=owner.load_json(output)
        self.assertEqual(f["counter"].read_text(),"rr")
        return observed

    def selection(self,f):
        return {"schema":owner.SELECTIONS,"groups":[{"id":"q02-"+key,"job":f["job"],"payload_name":f["payload"],"observation":key,
                "proof_kind":"source-test","selectors":list(selectors),"cells":[f["cell"]],
                "scope":"Synthetic transport fixture; no production readiness or publication claim"}
                for key,selectors in Q02_FIXTURE_SELECTORS.items()]}

    def authenticate(self,f):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,"w") as archive:
            for p in f["staged"].rglob("*"):
                if p.is_file():archive.writestr(p.relative_to(f["staged"]).as_posix(),p.read_bytes())
        req={**owner.source_identity(f["repo"],f["profile"]),"ci_run_id":7,"cells":[f["cell"]],"cell_jobs":{f["cell"]:f["job"]}}
        job={"id":9,"name":f["job"],"status":"in_progress","conclusion":None,
             "steps":[{"name":"Upload Q02 implementation source-test inputs","status":"completed","conclusion":"success"}]}
        with mock.patch.object(owner.readiness,"artifact_bytes",return_value=buffer.getvalue()), \
             mock.patch.object(owner.readiness,"validate_upload",side_effect=AssertionError("active job has no completed log")):
            payload=owner.authenticated_payload({"id":8,"name":f["payload"]},req,f["repo"],source_job=job)
        return req,payload

    def build(self,f,observed,selection=None):
        if "authenticated" not in f:f["authenticated"]=self.authenticate(f)
        req,payload=copy.deepcopy(f["authenticated"]);selection=selection or self.selection(f)
        cells=selection["groups"][0]["cells"];req.update(cells=cells,cell_jobs={c:f["job"] for c in cells})
        return owner.build_report(req,job_name=f["job"],job_id=9,selections=selection,observations=observed,payloads={f["payload"]:payload})

    def test_closed_readiness_profile_preserves_original_once_and_emits_only_implementation_task(self):
        with q02_python_source_fixture() as f:
            try:observed=self.original(f)
            except ValueError as error:self.fail("Original source observer cannot carry Q02's own readiness invocation: "+str(error))
            self.assertEqual({t["id"] for value in observed.values() for t in value["tests"]},{s for values in Q02_FIXTURE_SELECTORS.values() for s in values})
            report=self.build(f,observed)
            self.assertEqual([row["cell"] for row in report["results"]],["task:Q-02"])
            self.assertEqual(report["results"][0]["executed_population"],sum(map(len,Q02_FIXTURE_SELECTORS.values())))

    def test_q02_observation_rejects_another_profile_from_the_same_job(self):
        with q02_python_source_fixture() as fixture:
            observed = self.original(fixture)["release"]
            req, payload = self.authenticate(fixture)
            owner.admit_source_observation(observed, payload, req, fixture["job"], 9)

            other = owner.source_profile(owner.SOURCE_PROFILE)
            self.assertEqual(other["job"], fixture["job"])
            observed["source_input_binding"].update(
                profile=owner.SOURCE_PROFILE, payload_name=other["payload"],
            )
            with self.assertRaisesRegex(ValueError, "source test manifest profile differs"):
                owner.admit_source_observation(observed, payload, req, fixture["job"], 9)

    def test_q02_requires_all_original_named_assertions_and_refuses_skip_failure_duplicate(self):
        with q02_python_source_fixture() as f:
            observed=self.original(f)
            for failure in ("omitted","skipped","failed","duplicate","empty-selection"):
                bad=copy.deepcopy(observed);selection=self.selection(f)
                if failure=="omitted":bad["readiness"]["tests"].pop()
                elif failure=="duplicate":bad["readiness"]["tests"].append(copy.deepcopy(bad["readiness"]["tests"][0]))
                elif failure=="empty-selection":selection["groups"][0]["selectors"]=selection["groups"][0]["selectors"][:1]
                else:bad["readiness"]["tests"][0]["result"]=failure
                with self.subTest(failure=failure),self.assertRaises(ValueError):self.build(f,bad,selection)

    def test_q02_never_relabels_final_main_other_tasks_installed_or_old_profile(self):
        with q02_python_source_fixture() as f:
            observed=self.original(f)
            for cell in ("task:Q-03","task:P-02","scenario:SEQ-01","installed:pi:windows:1.5.0"):
                selection=self.selection(f);
                for group in selection["groups"]:group["cells"]=[cell]
                with self.subTest(cell=cell),self.assertRaises(ValueError):self.build(f,observed,selection)
            for kind in ("native-module","retained-archive-cli","live-host"):
                selection=self.selection(f)
                for group in selection["groups"]:group["proof_kind"]=kind
                with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,"Q02 implementation requires original source"):
                    self.build(f,observed,selection)
            for profile in (owner.SOURCE_PROFILE,owner.SDK_SOURCE_PROFILE,"unreviewed-task-profile"):
                bad=copy.deepcopy(observed);bad["readiness"]["source_input_binding"]["profile"]=profile
                with self.subTest(profile=profile),self.assertRaises(ValueError):self.build(f,bad)

    def test_q02_filtered_or_foreign_entrypoint_refuses_before_execution(self):
        with q02_python_source_fixture() as f:
            owner.prepare_source_payload(f["repo"],f["staged"],f["job"],f["profile"])
            for script,args in ((".github/scripts/test_major_readiness.py",["ReadinessTest"]),
                                (".github/scripts/major_readiness.py",["verify"]),
                                (".github/scripts/test_major_readiness.py",["--help"])):
                with self.subTest(script=script,args=args),self.assertRaises(ValueError):
                    owner.observe_python(f["repo"],script,args,f["base"]/"absent.json",f["staged"],f["profile"])
            self.assertFalse(f["counter"].exists());self.assertFalse((f["base"]/"absent.json").exists())

    def test_final_reader_authenticates_q02_source_upload_and_unchanged_owner_job(self):
        cell="task:Q-02";job_name="[CHECK] | [CORE] | Hook contract  <os: windows-latest · partition: contracts>"
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,"w") as archive:archive.writestr("source-member",b"inert")
        content=raw.getvalue();members=owner.readiness.members(content)
        source={"id":8,"name":"major-source-inputs-q02-implementation"};artifact={"id":10,"name":"major-qualification-9"}
        job={"id":9,"name":job_name,"status":"completed","conclusion":"success"}
        req={"source_commit":"a"*40,"source_tree":"b"*40,"ci_run_id":7,"cells":[cell],"cell_jobs":{cell:job_name},"required_artifact_names":[source["name"]]}
        report={"schema":"codearbiter-major-qualification/2",**{key:req[key] for key in ("source_commit","source_tree","ci_run_id")},"job_id":9,
          "payloads":[{"artifact_id":8,"archive_sha256":owner.readiness.digest(content),"members":members}],
          "results":[{"cell":cell,"result":"PASSED","commands":[{"argv":["python",".github/scripts/test_major_readiness.py"],"exit_code":0}],"selected_population":1,"executed_population":1,"payload_artifact_id":8}]}
        jobs=[job,{"id":11,"name":"major readiness producer"}]
        with mock.patch.object(owner.readiness,"read_artifact_json",return_value=report), \
             mock.patch.object(owner.readiness,"artifact_bytes",return_value=content), \
             mock.patch.object(owner.readiness,"validate_upload") as attribution:
            owner.readiness.produce(req,[source,artifact],jobs)
            self.assertEqual(attribution.call_args_list,[mock.call(job,artifact,"Upload major qualification report"),
                mock.call(job,source,"Upload Q02 implementation source-test inputs")])
            for failure in ("wrong-owner","in-progress","upload-refused"):
                modified=copy.deepcopy(jobs);requirements=copy.deepcopy(req)
                attribution.side_effect=None
                if failure=="wrong-owner":
                    modified[0]["name"]="other";requirements["cell_jobs"][cell]="other"
                elif failure=="in-progress":modified[0].update(status="in_progress",conclusion=None)
                else:attribution.side_effect=owner.readiness.ReadinessError("original source uploader refused")
                with self.subTest(failure=failure),self.assertRaises(owner.readiness.ReadinessError):
                    owner.readiness.produce(requirements,[source,artifact],modified)

    def test_q02_ci_keeps_two_original_invocations_exact_once_and_trusted_emission(self):
        from test_ci_impact import workflow_jobs
        hooks=workflow_jobs((owner.ROOT/".github/workflows/ci.yml").read_text(encoding="utf-8"))["hooks"]
        def check(text):
            for script,identifier in (("test_major_readiness.py","q02_readiness_observed"),("test_release_workflow.py","q02_release_observed")):
                self.assertEqual(text.count("run: python .github/scripts/"+script),1)
                self.assertEqual(text.count("-- .github/scripts/"+script+"\n"),1)
                self.assertEqual(text.count("id: "+identifier),1)
            self.assertEqual(text.count("id: q02_source_prepare"),1)
            self.assertEqual(text.count("id: q02_source_upload"),1)
            self.assertLess(text.index("id: q02_source_prepare"),text.index("id: q02_readiness_observed"))
            self.assertLess(text.index("id: q02_release_observed"),text.index("id: q02_source_upload"))
            for title in ("Test authenticated major readiness admission and refusal","Run hosted release-workflow contract tests"):
                fallback=text.split("- name: "+title+"\n",1)[1].split("      - name:",1)[0]
                self.assertIn("if: (matrix.partition == 'all' || matrix.partition == 'contracts') && !(matrix.os == 'windows-latest' && matrix.partition == 'contracts')",fallback)
            emit=text.split("id: python_qualification_emit",1)[1].split("- name: Upload major qualification report",1)[0]
            for value in ("github.event_name == 'push'","github.ref == 'refs/heads/main'","github.ref == 'refs/heads/major/state-contracts'",
                          "hashFiles('.github/integration-candidate.json') != ''","steps.q02_source_upload.outcome == 'success'",
                          "steps.q02_readiness_observed.outcome == 'success'","steps.q02_release_observed.outcome == 'success'",
                          '--payload-root "major-source-inputs-q02-implementation=${{ github.workspace }}"'):
                self.assertIn(value,emit)
            self.assertNotIn('GH_TOKEN:',text.split('- name: Emit original Python source qualification report',1)[0])
        check(hooks)
        for bad in (hooks.replace('-- .github/scripts/test_major_readiness.py\n','-- .github/scripts/test_major_readiness.py ReadinessTest\n',1),
                    hooks.replace('-- .github/scripts/test_release_workflow.py\n','',1),
                    hooks+'\n-- .github/scripts/test_release_workflow.py\n',
                    hooks.replace("github.event_name == 'push'","github.event_name != 'pull_request'"),
                    hooks.replace("steps.q02_source_upload.outcome == 'success'","true")):
            with self.subTest(mutation=len(bad)),self.assertRaises(AssertionError):check(bad)
        maps=json.loads((owner.ROOT/".github/major-test-selections.json").read_text(encoding="utf-8"))
        groups=[g for g in maps["groups"] if "task:Q-02" in g["cells"]]
        self.assertEqual({x for g in groups for x in g["selectors"]},set(owner.Q02_REQUIRED_SELECTORS))
        self.assertEqual({g["payload_name"] for g in groups},{owner.Q02_SOURCE_PAYLOAD})


class QualificationOutputFilenameTests(unittest.TestCase):
    """Real emit CLI/file writer and unchanged singleton archive reader."""

    def emit(self, base, name):
        fixture=ReportTest();fixture.setUp()
        repo=base/'repo';(repo/'.github').mkdir(parents=True,exist_ok=True)
        (repo/'.github/major-test-selections.json').write_text(json.dumps(fixture.map),encoding='utf8')
        observation=base/'native.json';observation.write_text(json.dumps(fixture.observation),encoding='utf8')
        output=base/name
        job={'name':'owning native job','id':9,'status':'in_progress'}
        env={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':owner.readiness.REPOSITORY,
             'GITHUB_REF':'refs/heads/major/state-contracts','GITHUB_EVENT_NAME':'push',
             'GITHUB_SHA':fixture.req['source_commit'],'GITHUB_RUN_ID':'7'}
        with mock.patch.dict(os.environ,env),mock.patch.object(owner,'source_identity',return_value={
                'source_commit':fixture.req['source_commit'],'source_tree':'b'*40,'clean':True}), \
             mock.patch.object(owner.readiness,'collect',return_value=(fixture.req,None,
                 [{'name':'candidate','id':8}],[job])) as collect, \
             mock.patch.object(owner,'authenticated_payload',return_value=fixture.payload) as payload, \
             mock.patch('sys.stderr',new=io.StringIO()):
            result=owner.main(['emit','--repo',str(repo),'--output',str(output),
                '--job-name',job['name'],'--observation','native='+str(observation),
                '--payload-root','candidate='+str(base)])
        return result,output,fixture,collect.call_count,payload.call_count

    def test_emit_refuses_noncanonical_report_names_before_metadata_or_write(self):
        for name in ('pi-qualification.json','sandbox-qualification.json','pi-sdk-qualification.json'):
            with self.subTest(name=name),tempfile.TemporaryDirectory(prefix='ca-report-name-') as raw:
                code,path,_,collect,payload=self.emit(Path(raw).resolve(),name)
                self.assertEqual(code,1,'a valid emitter must refuse an archive basename its reader cannot consume')
                self.assertFalse(path.exists())
                self.assertEqual((collect,payload),(0,0))

    def test_canonical_emit_archive_roundtrips_unchanged_exact_filename_reader(self):
        with tempfile.TemporaryDirectory(prefix='ca-report-canonical-') as raw:
            code,path,fixture,collect,payload=self.emit(Path(raw).resolve(),'qualification.json')
            self.assertEqual((code,collect,payload),(0,1,1))
            self.assertEqual(owner.load_json(path),fixture.build())
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w') as zipped:zipped.writestr(path.name,path.read_bytes())
            with mock.patch.object(owner.readiness,'artifact_bytes',return_value=archive.getvalue()):
                self.assertEqual(owner.readiness.read_artifact_json({'id':8},fixture.req,'qualification.json'),fixture.build())
            wrong=io.BytesIO()
            with zipfile.ZipFile(wrong,'w') as zipped:zipped.writestr('pi-sdk-qualification.json',path.read_bytes())
            with mock.patch.object(owner.readiness,'artifact_bytes',return_value=wrong.getvalue()):
                with self.assertRaises(owner.readiness.ReadinessError):
                    owner.readiness.read_artifact_json({'id':8},fixture.req,'qualification.json')

    def test_original_non_emit_operations_keep_arbitrary_output_filenames(self):
        with tempfile.TemporaryDirectory(prefix='ca-other-output-') as raw:
            base=Path(raw).resolve()
            with mock.patch.object(owner,'prepare_source_payload') as prepare, \
                 mock.patch.object(owner,'observe_python',return_value=0) as python, \
                 mock.patch.object(owner,'observe_vitest',return_value=0) as vitest, \
                 mock.patch.object(owner,'validate_emitter_environment') as emitter:
                self.assertEqual(owner.main(['prepare-source','--output',str(base/'inputs')]),0)
                self.assertEqual(owner.main(['observe-python','--output',str(base/'observed.json'),'entry.py']),0)
                self.assertEqual(owner.main(['observe-vitest','--output',str(base/'vitest.json')]),0)
                prepare.assert_called_once();python.assert_called_once();vitest.assert_called_once();emitter.assert_not_called()
            with mock.patch.object(owner,'load_json',return_value={'source_commit':'a'*40}), \
                 mock.patch.object(owner,'git',return_value='b'*40), \
                 mock.patch.object(owner,'admit_go',return_value={'fixture':'inert'}), \
                 mock.patch.object(owner,'validate_emitter_environment') as emitter:
                self.assertEqual(owner.main(['admit-go','--output',str(base/'go.json'),
                    '--observation','raw.json','--native-binding','stamp.json']),0)
                self.assertEqual(json.loads((base/'go.json').read_bytes()),{'fixture':'inert'})
                self.assertTrue((base/'go.json').is_file());emitter.assert_not_called()

    def test_every_generic_ci_emit_upload_and_readback_uses_canonical_report_name(self):
        import re
        source=(Path(__file__).resolve().parents[2]/'.github/workflows/ci.yml').read_text(encoding='utf8')
        blocks=re.split(r'(?m)^      - ',source)
        emitters=[block for block in blocks if re.search(r'python(?: -B)? \.github/scripts/major_qualification_report\.py emit\b',block)]
        self.assertGreaterEqual(len(emitters),7)
        for block in emitters:
            output=re.search(r'--output\s+"([^"]+)"',block)
            self.assertIsNotNone(output)
            self.assertEqual(output.group(1).rsplit('/',1)[-1],'qualification.json',block.splitlines()[0])
        for legacy in ('pi-qualification.json','sandbox-qualification.json','pi-sdk-qualification.json'):
            self.assertNotIn(legacy,source)



HOOK_REVIEW_FIXTURE_PATHS = frozenset(['.codearbiter/reports/agent-lane-proof.json', '.github/major-qualification-policy.json', '.github/major-test-selections.json', '.github/scripts/_boundedproc.py', '.github/scripts/_contextverificationlib.py', '.github/scripts/_immutable_git_blobs.py', '.github/scripts/check_skill_proof_fresh.py', '.github/scripts/ci20_native_binding.py', '.github/scripts/major_qualification_report.py', '.github/scripts/major_readiness.py', '.github/scripts/test_check_skill_proof_fresh.py', '.github/scripts/test_generated_output.py', '.github/scripts/test_hook_ci_partition.py', '.github/scripts/test_review_funnel.py', '.github/workflows/ci.yml', 'core/artifact-release-manifest.json', 'core/hosts.json', 'core/pysrc/_artifactmanifestlib.py', 'core/pysrc/_gitexec.py', 'core/surface/COMMANDS.md', 'core/surface/README.md', 'core/surface/SPRINT.md', 'core/surface/agents/INDEX.md', 'core/surface/agents/architecture-drift-reviewer.md', 'core/surface/agents/auth-crypto-reviewer.md', 'core/surface/agents/authority-reviewer.md', 'core/surface/agents/backend-author.md', 'core/surface/agents/checkpoint-aggregator.md', 'core/surface/agents/coverage-auditor.md', 'core/surface/agents/decision-challenger.md', 'core/surface/agents/dependency-reviewer.md', 'core/surface/agents/design-quality-reviewer.md', 'core/surface/agents/finding-triage.md', 'core/surface/agents/frontend-author.md', 'core/surface/agents/grader.md', 'core/surface/agents/infra-author.md', 'core/surface/agents/map-deps.md', 'core/surface/agents/map-structure.md', 'core/surface/agents/migration-reviewer.md', 'core/surface/agents/scout.md', 'core/surface/agents/security-reviewer.md', 'core/surface/agents/tribunal-lens-reviewer.md', 'core/surface/agents/verdict-aggregator.md', 'core/surface/arbiter.md', 'core/surface/command-routes.json', 'core/surface/commands/add-dep.md', 'core/surface/commands/adr-status.md', 'core/surface/commands/adr.md', 'core/surface/commands/audit.md', 'core/surface/commands/checkpoint.md', 'core/surface/commands/chore.md', 'core/surface/commands/cleanup.md', 'core/surface/commands/commit.md', 'core/surface/commands/conflict.md', 'core/surface/commands/context-check.md', 'core/surface/commands/create-context.md', 'core/surface/commands/debug.md', 'core/surface/commands/decompose.md', 'core/surface/commands/doctor.md', 'core/surface/commands/feature.md', 'core/surface/commands/fix.md', 'core/surface/commands/init.md', 'core/surface/commands/override.md', 'core/surface/commands/pr.md', 'core/surface/commands/prune.md', 'core/surface/commands/reconcile.md', 'core/surface/commands/refactor.md', 'core/surface/commands/release.md', 'core/surface/commands/review.md', 'core/surface/commands/spike.md', 'core/surface/commands/sprint.md', 'core/surface/commands/standup.md', 'core/surface/commands/status.md', 'core/surface/commands/statusline.md', 'core/surface/commands/task.md', 'core/surface/commands/threat-model.md', 'core/surface/commands/tribunal.md', 'core/surface/commands/watch.md', 'core/surface/includes/anti-slop-design/INDEX.md', 'core/surface/includes/anti-slop-design/color.md', 'core/surface/includes/anti-slop-design/core.md', 'core/surface/includes/anti-slop-design/images.md', 'core/surface/includes/anti-slop-design/layout.md', 'core/surface/includes/anti-slop-design/medium-cli.md', 'core/surface/includes/anti-slop-design/medium-dataviz.md', 'core/surface/includes/anti-slop-design/medium-diagram.md', 'core/surface/includes/anti-slop-design/medium-documents.md', 'core/surface/includes/anti-slop-design/medium-slides.md', 'core/surface/includes/anti-slop-design/medium-web.md', 'core/surface/includes/anti-slop-design/typography.md', 'core/surface/includes/artifacts-attestation.md', 'core/surface/includes/artifacts.md', 'core/surface/includes/author-tdd-workflow.md', 'core/surface/includes/codex-host-notes.md', 'core/surface/includes/command-compatibility.md', 'core/surface/includes/compaction-charter.md', 'core/surface/includes/cut-docs.md', 'core/surface/includes/dangerous-mode.md', 'core/surface/includes/farm.md', 'core/surface/includes/fresh-verification.md', 'core/surface/includes/harvest.md', 'core/surface/includes/helper-invocation.md', 'core/surface/includes/knowledge.md', 'core/surface/includes/maturity-coverage.md', 'core/surface/includes/ops-mode.md', 'core/surface/includes/pi-host-notes.md', 'core/surface/includes/redirect.md', 'core/surface/includes/reference-map.md', 'core/surface/includes/review-matrix.md', 'core/surface/includes/reviewer-contract.md', 'core/surface/includes/routing-table.md', 'core/surface/includes/safety-core.md', 'core/surface/includes/security-gate-record.md', 'core/surface/includes/smarts/core.md', 'core/surface/includes/smarts/decision-log-format.md', 'core/surface/includes/smarts/lenses.md', 'core/surface/includes/sprint-authority.md', 'core/surface/includes/verification-boundary.md', 'core/surface/skills/INDEX.md', 'core/surface/skills/brainstorming/SKILL.md', 'core/surface/skills/commit-gate/SKILL.md', 'core/surface/skills/context-check/SKILL.md', 'core/surface/skills/context-creation/SKILL.md', 'core/surface/skills/context-creation/references/markdown-format.md', 'core/surface/skills/crypto-compliance/SKILL.md', 'core/surface/skills/debug/SKILL.md', 'core/surface/skills/debug/references/debug-handoff.schema.json', 'core/surface/skills/debug/references/handoff.md', 'core/surface/skills/debug/references/minimal-unresolved.json', 'core/surface/skills/debug/references/preparation.md', 'core/surface/skills/decision-lifecycle/SKILL.md', 'core/surface/skills/decision-lifecycle/references/adr-template.md', 'core/surface/skills/decision-lifecycle/references/authoring.md', 'core/surface/skills/decision-variance/SKILL.md', 'core/surface/skills/decision-variance/references/analysis.md', 'core/surface/skills/decompose/SKILL.md', 'core/surface/skills/decompose/references/markdown-format.md', 'core/surface/skills/dispatching-parallel-agents/SKILL.md', 'core/surface/skills/executing-plans/SKILL.md', 'core/surface/skills/finishing-a-development-branch/SKILL.md', 'core/surface/skills/post-merge-cleanup/SKILL.md', 'core/surface/skills/refactor/SKILL.md', 'core/surface/skills/release/SKILL.md', 'core/surface/skills/secret-handling/SKILL.md', 'core/surface/skills/security-architecture/SKILL.md', 'core/surface/skills/subagent-driven-development/SKILL.md', 'core/surface/skills/subagent-driven-development/references/farm-dispatch.md', 'core/surface/skills/tdd/SKILL.md', 'core/surface/skills/tribunal/SKILL.md', 'core/surface/skills/tribunal/references/ai-markers.md', 'core/surface/skills/tribunal/references/cost-and-models.md', 'core/surface/skills/tribunal/references/finding-record.md', 'core/surface/skills/tribunal/references/issue-filing.md', 'core/surface/skills/tribunal/references/lenses/appsec.md', 'core/surface/skills/tribunal/references/lenses/architecture.md', 'core/surface/skills/tribunal/references/lenses/change-closure.md', 'core/surface/skills/tribunal/references/lenses/coverage.md', 'core/surface/skills/tribunal/references/lenses/infra.md', 'core/surface/skills/tribunal/references/lenses/migration.md', 'core/surface/skills/tribunal/references/lenses/observability.md', 'core/surface/skills/tribunal/references/lenses/performance.md', 'core/surface/skills/tribunal/references/lenses/reliability.md', 'core/surface/skills/tribunal/references/lenses/secrets-supply.md', 'core/surface/skills/tribunal/references/lenses/semantic-contract.md', 'core/surface/skills/tribunal/references/lenses/test-fidelity.md', 'core/surface/skills/tribunal/references/lenses/typesafety.md', 'core/surface/skills/tribunal/references/report.md', 'core/surface/skills/tribunal/references/review-risk.md', 'core/surface/skills/tribunal/references/schemas.md', 'core/surface/skills/tribunal/references/telemetry.md', 'core/surface/skills/tribunal/references/triage.md', 'core/surface/skills/tribunal/references/verification-quality.md', 'core/surface/skills/using-git-worktrees/SKILL.md', 'core/surface/skills/writing-plans/SKILL.md', 'core/surface/skills/writing-plans/references/farm-plan.md', 'docs/state-contracts-major/PROGRAM.md', 'docs/state-contracts-major/contracts/decisions.json', 'docs/state-contracts-major/contracts/finding-dispositions.json', 'docs/state-contracts-major/contracts/tasks.json', 'plugins/ca-codex/agents/INDEX.md', 'plugins/ca-codex/agents/architecture-drift-reviewer.md', 'plugins/ca-codex/agents/auth-crypto-reviewer.md', 'plugins/ca-codex/agents/backend-author.md', 'plugins/ca-codex/agents/checkpoint-aggregator.md', 'plugins/ca-codex/agents/coverage-auditor.md', 'plugins/ca-codex/agents/decision-challenger.md', 'plugins/ca-codex/agents/dependency-reviewer.md', 'plugins/ca-codex/agents/design-quality-reviewer.md', 'plugins/ca-codex/agents/finding-triage.md', 'plugins/ca-codex/agents/frontend-author.md', 'plugins/ca-codex/agents/grader.md', 'plugins/ca-codex/agents/infra-author.md', 'plugins/ca-codex/agents/map-deps.md', 'plugins/ca-codex/agents/map-structure.md', 'plugins/ca-codex/agents/migration-reviewer.md', 'plugins/ca-codex/agents/scout.md', 'plugins/ca-codex/agents/security-reviewer.md', 'plugins/ca-codex/agents/tribunal-lens-reviewer.md', 'plugins/ca-codex/agents/verdict-aggregator.md', 'plugins/ca-codex/includes/reviewer-contract.md', 'plugins/ca-pi/agents/INDEX.md', 'plugins/ca-pi/agents/architecture-drift-reviewer.md', 'plugins/ca-pi/agents/auth-crypto-reviewer.md', 'plugins/ca-pi/agents/backend-author.md', 'plugins/ca-pi/agents/checkpoint-aggregator.md', 'plugins/ca-pi/agents/coverage-auditor.md', 'plugins/ca-pi/agents/decision-challenger.md', 'plugins/ca-pi/agents/dependency-reviewer.md', 'plugins/ca-pi/agents/design-quality-reviewer.md', 'plugins/ca-pi/agents/finding-triage.md', 'plugins/ca-pi/agents/frontend-author.md', 'plugins/ca-pi/agents/grader.md', 'plugins/ca-pi/agents/infra-author.md', 'plugins/ca-pi/agents/map-deps.md', 'plugins/ca-pi/agents/map-structure.md', 'plugins/ca-pi/agents/migration-reviewer.md', 'plugins/ca-pi/agents/scout.md', 'plugins/ca-pi/agents/security-reviewer.md', 'plugins/ca-pi/agents/tribunal-lens-reviewer.md', 'plugins/ca-pi/agents/verdict-aggregator.md', 'plugins/ca-pi/includes/reviewer-contract.md', 'plugins/ca/agents/INDEX.md', 'plugins/ca/agents/architecture-drift-reviewer.md', 'plugins/ca/agents/auth-crypto-reviewer.md', 'plugins/ca/agents/authority-reviewer.md', 'plugins/ca/agents/backend-author.md', 'plugins/ca/agents/checkpoint-aggregator.md', 'plugins/ca/agents/coverage-auditor.md', 'plugins/ca/agents/decision-challenger.md', 'plugins/ca/agents/dependency-reviewer.md', 'plugins/ca/agents/design-quality-reviewer.md', 'plugins/ca/agents/finding-triage.md', 'plugins/ca/agents/frontend-author.md', 'plugins/ca/agents/grader.md', 'plugins/ca/agents/infra-author.md', 'plugins/ca/agents/map-deps.md', 'plugins/ca/agents/map-structure.md', 'plugins/ca/agents/migration-reviewer.md', 'plugins/ca/agents/scout.md', 'plugins/ca/agents/security-reviewer.md', 'plugins/ca/agents/tribunal-lens-reviewer.md', 'plugins/ca/agents/verdict-aggregator.md', 'plugins/ca/includes/reviewer-contract.md', 'plugins/ca/skills/release/SKILL.md', 'site/src/curated/commands/review.md', 'tools/build-artifact-manifest-contract.py', 'tools/build-surface.py', 'tools/command_compatibility.py', 'tools/host_descriptors.py', 'tools/owned_output.py'])
HOOK_REVIEW_FIXTURE_SELECTORS = frozenset(['python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_author_collection_does_not_invoke_review_verdict', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_checkpoint_persistence_is_explicit_and_non_overwriting', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_checkpoint_writer_reports_the_selected_dated_filename', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_curated_review_projection_uses_the_read_only_terminal', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_dispatch_contract_uses_canonical_routes_and_preserves_findings', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_inbound_pr_review_route_is_byte_invariant', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_triage_requires_the_complete_batch_contract', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_verdict_has_unambiguous_incomplete_precedence_and_schema', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_working_diff_review_route_is_byte_invariant', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_dependency_owner_assigns_medium_to_maintenance_only', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_index_blocks_column_matches_owner_severities', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_no_reviewer_body_declares_a_non_blocking_high', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_security_highs_block_in_the_dependency_owner', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_shared_contract_states_one_rule_and_the_single_exception', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_triage_never_conditions_high_blocking'])


class HookReviewObservationProfileTests(unittest.TestCase):
    """Original unfiltered suite; only its complete W-F03 policy group is mapped."""
    fixture = None

    @classmethod
    def tearDownClass(cls):
        if cls.fixture is not None:
            cls.fixture["environment"].stop()
            cls.fixture["temporary"].cleanup()
            cls.fixture = None

    def original(self):
        cls = type(self)
        if cls.fixture is None:
            temporary = tempfile.TemporaryDirectory(prefix="ca-hook-review-profile-")
            base = Path(temporary.name).resolve(); repo = base / "repo"; repo.mkdir()
            canonical = Path(os.environ.get("CA_HOOKS_CANONICAL_ROOT", owner.ROOT))
            for relative in HOOK_REVIEW_FIXTURE_PATHS:
                target = repo / relative; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((canonical / relative).read_bytes())
            git = shutil.which("git"); self.assertIsNotNone(git)
            env = {k: v for k, v in os.environ.items() if k.upper() in
                   ("SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT")}
            env.update(PATH=os.pathsep.join([str(Path(git).parent), str(Path(sys.executable).parent)]),
                       HOME=str(base), USERPROFILE=str(base), TEMP=str(base), TMP=str(base),
                       GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_OPTIONAL_LOCKS="0",
                       GIT_AUTHOR_NAME="fixture", GIT_AUTHOR_EMAIL="fixture@invalid",
                       GIT_COMMITTER_NAME="fixture", GIT_COMMITTER_EMAIL="fixture@invalid",
                       GITHUB_RUN_ID="7", PYTHONDONTWRITEBYTECODE="1")
            environment = mock.patch.dict(os.environ, env, clear=True); environment.start()
            cls.fixture = f = dict(temporary=temporary, environment=environment, base=base, repo=repo,
                staged=base/"inputs", output=base/"observation.json", profile="hooks-finding-contracts-v1",
                job="[CHECK] | [CORE] | Hook contract  <os: windows-latest · partition: contracts>",
                payload="major-source-inputs-hooks-findings-windows-contracts")
            for args in (["init"], ["config", "core.autocrlf", "false"], ["add", "."],
                         ["-c", "commit.gpgsign=false", "commit", "-qm", "Hook source fixture"]):
                run_git_phase([git, "-C", str(repo), *args], phase="init" if args[0] in ("init", "config")
                              else "index" if args[0] == "add" else "commit", trace_dir=base)
            try:
                owner.prepare_source_payload(repo, f["staged"], f["job"], f["profile"])
                with mock.patch.object(owner.runpy, "run_path", wraps=owner.runpy.run_path) as original:
                    self.assertEqual(owner.observe_python(repo, ".github/scripts/test_review_funnel.py", [],
                        f["output"], f["staged"], f["profile"]), 0)
                    self.assertEqual(original.call_count, 1)
            except ValueError as error:
                self.fail("The existing original review-suite observation route is unavailable: " + str(error))
            f["observed"] = owner.load_json(f["output"])
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as z:
                for path in sorted(f["staged"].rglob("*")):
                    if path.is_file(): z.writestr(path.relative_to(f["staged"]).as_posix(), path.read_bytes())
            f["req"] = {**owner.source_identity(repo, f["profile"]), "ci_run_id": 7}
            job = {"id": 9, "name": f["job"], "status": "in_progress", "conclusion": None,
                   "steps": [{"name": "Upload hook finding source-test inputs", "status": "completed", "conclusion": "success"}]}
            with mock.patch.object(owner.readiness, "artifact_bytes", return_value=archive.getvalue()),                  mock.patch.object(owner.readiness, "validate_upload", side_effect=AssertionError("producer has no completed job log")):
                f["authenticated"] = owner.authenticated_payload({"id": 8, "name": f["payload"]},
                    f["req"], repo, source_job=job)
        self.assertIn("observed", cls.fixture, "Earlier original invocation must succeed before admission controls")
        return cls.fixture

    def selection(self, f):
        return {"schema": owner.SELECTIONS, "groups": [{"id": "hook-severity-policy", "job": f["job"],
            "payload_name": f["payload"], "observation": "review", "proof_kind": "source-test",
            "selectors": sorted(s for s in HOOK_REVIEW_FIXTURE_SELECTORS if ".SeverityDispositionPolicyTest." in s),
            "cells": ["disposition:findings:W-F03"],
            "scope": "W-F03 declarative severity policy only, not model behavior or task/installed acceptance"}]}

    def admit(self, f, observed=None, payload=None, req=None, job=None, selection=None):
        req = req or {**f["req"], "cells": ["disposition:findings:W-F03"],
                      "cell_jobs": {"disposition:findings:W-F03": f["job"]}}
        return owner.build_report(req, job_name=job or f["job"], job_id=9,
            selections=selection or self.selection(f), observations={"review": observed or copy.deepcopy(f["observed"])},
            payloads={f["payload"]: payload if payload is not None else copy.deepcopy(f["authenticated"])})

    def test_a_original_unfiltered_review_suite_is_observed_once_with_only_its_finite_finding(self):
        f = self.original()
        self.assertEqual({t["id"] for t in f["observed"]["tests"]}, HOOK_REVIEW_FIXTURE_SELECTORS)
        self.assertTrue(all(t["result"] == "passed" for t in f["observed"]["tests"]))
        report = self.admit(f)
        self.assertEqual([r["cell"] for r in report["results"]], ["disposition:findings:W-F03"])
        self.assertEqual(report["results"][0]["selected_population"], 6)
        self.assertEqual(report["results"][0]["executed_population"], 6)

    def test_b_foreign_filtered_and_missing_payload_commands_refuse_before_original_execution(self):
        f = self.original()
        with mock.patch.object(owner.runpy, "run_path", side_effect=AssertionError("must not execute")):
            for script, args, payload in ((".github/scripts/test_review_funnel.py", ["SeverityDispositionPolicyTest"], f["staged"]),
                 (".github/scripts/major_qualification_report.py", [], f["staged"]),
                 (".github/scripts/test_review_funnel.py", [], None)):
                with self.subTest(script=script, args=args, payload=payload), self.assertRaises(ValueError):
                    owner.observe_python(f["repo"], script, args, f["base"]/"refused.json", payload, f["profile"])
        self.assertFalse((f["base"]/"refused.json").exists())

    def test_c_reader_refuses_missing_duplicate_skipped_and_failed_selected_results(self):
        f = self.original()
        for failure in ("missing", "duplicate", "skipped", "failed"):
            bad = copy.deepcopy(f["observed"])
            index = next(i for i, row in enumerate(bad["tests"]) if ".SeverityDispositionPolicyTest." in row["id"])
            if failure == "missing": bad["tests"].pop(index)
            elif failure == "duplicate": bad["tests"].append(copy.deepcopy(bad["tests"][index]))
            else: bad["tests"][index]["result"] = failure
            with self.subTest(failure=failure), self.assertRaises(ValueError): self.admit(f, bad)

    def test_d_reader_refuses_foreign_source_run_job_payload_profile_and_arguments(self):
        f = self.original()
        for key, value in (("source_commit", "f"*40), ("source_tree", "f"*40), ("ci_run_id", 8),
                           ("source_stable", False), ("exit_code", 1), ("argv", ["python", ".github/scripts/test_review_funnel.py", "-k", "partial"])):
            bad = copy.deepcopy(f["observed"]); bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.admit(f, bad)
        for key, value in (("profile", owner.SOURCE_PROFILE), ("payload_name", "foreign"), ("manifest_sha256", "f"*64)):
            bad = copy.deepcopy(f["observed"]); bad["source_input_binding"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.admit(f, bad)
        with self.assertRaises(ValueError): self.admit(f, payload={})
        with self.assertRaises(ValueError): self.admit(f, job="other job")
        bad = copy.deepcopy(f["authenticated"]); bad["source_upload_job_id"] = 10
        with self.assertRaises(ValueError): self.admit(f, payload=bad)

    def test_e_changed_source_or_agent_inventory_cannot_be_freshened(self):
        f = self.original(); path = f["repo"]/"plugins/ca/agents/dependency-reviewer.md"; raw = path.read_bytes()
        try:
            path.write_bytes(raw+b"\nchanged\n")
            with self.assertRaises(ValueError): owner.source_observation_binding(f["repo"], f["staged"], f["req"], f["profile"])
        finally: path.write_bytes(raw)
        extra = f["repo"]/"plugins/ca/agents/unreviewed.md"
        try:
            extra.write_text("unreviewed", encoding="utf-8")
            with self.assertRaises(ValueError): owner._hook_review_members(f["repo"])
        finally: extra.unlink()

    def test_f_profile_rejects_incomplete_composition_other_findings_tasks_and_hosts(self):
        f = self.original()
        for cell in ("disposition:findings:W-F08", "task:HW-09", "installed:claude:workflow"):
            req = {**f["req"], "cells": [cell], "cell_jobs": {cell: f["job"]}}
            selection = self.selection(f); selection["groups"][0]["cells"] = [cell]
            with self.subTest(cell=cell), self.assertRaises(ValueError): self.admit(f, req=req, selection=selection)
        for changed in ("missing-selector", "extra-selector", "duplicate-selector"):
            selection = self.selection(f); selectors = selection["groups"][0]["selectors"]
            if changed == "missing-selector": selectors.pop()
            elif changed == "extra-selector": selectors.append(next(s for s in HOOK_REVIEW_FIXTURE_SELECTORS if ".ReadOnlyReviewFunnelTest." in s))
            else: selectors.append(selectors[0])
            with self.subTest(change=changed), self.assertRaises(ValueError): self.admit(f, selection=selection)

    def test_g_final_reader_authenticates_original_hook_source_upload_and_owner(self):
        cell="disposition:findings:W-F03";job_name="[CHECK] | [CORE] | Hook contract  <os: windows-latest · partition: contracts>"
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,"w") as archive:archive.writestr("source-member",b"inert")
        content=raw.getvalue();members=owner.readiness.members(content)
        source={"id":8,"name":"major-source-inputs-hooks-findings-windows-contracts"};artifact={"id":10,"name":"major-qualification-9"}
        job={"id":9,"name":job_name,"status":"completed","conclusion":"success"}
        req={"source_commit":"a"*40,"source_tree":"b"*40,"ci_run_id":7,"cells":[cell],"cell_jobs":{cell:job_name},"required_artifact_names":[source["name"]]}
        report={"schema":"codearbiter-major-qualification/2",**{key:req[key] for key in ("source_commit","source_tree","ci_run_id")},"job_id":9,
          "payloads":[{"artifact_id":8,"archive_sha256":owner.readiness.digest(content),"members":members}],
          "results":[{"cell":cell,"result":"PASSED","commands":[{"argv":["python",".github/scripts/test_review_funnel.py"],"exit_code":0}],"selected_population":1,"executed_population":1,"payload_artifact_id":8}]}
        jobs=[job,{"id":11,"name":"major readiness producer"}]
        with mock.patch.object(owner.readiness,"read_artifact_json",return_value=report), \
             mock.patch.object(owner.readiness,"artifact_bytes",return_value=content), \
             mock.patch.object(owner.readiness,"validate_upload") as attribution:
            owner.readiness.produce(req,[source,artifact],jobs)
            self.assertEqual(attribution.call_args_list,[mock.call(job,artifact,"Upload major qualification report"),
                mock.call(job,source,"Upload hook finding source-test inputs")])
            for failure in ("wrong-owner","in-progress","upload-refused"):
                modified=copy.deepcopy(jobs);requirements=copy.deepcopy(req)
                attribution.side_effect=None
                if failure=="wrong-owner":
                    modified[0]["name"]="other";requirements["cell_jobs"][cell]="other"
                elif failure=="in-progress":modified[0].update(status="in_progress",conclusion=None)
                else:attribution.side_effect=owner.readiness.ReadinessError("original source uploader refused")
                with self.subTest(failure=failure),self.assertRaises(owner.readiness.ReadinessError):
                    owner.readiness.produce(requirements,[source,artifact],modified)


    def test_h_ci_wraps_one_original_execution_and_keeps_closed_source_roles(self):
        import test_hook_ci_partition as partition
        text = (owner.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        def check(value):
            block = partition.job_block(value, "hooks")
            self.assertEqual(block.count("--source-profile hooks-finding-contracts-v1"), 2)
            self.assertEqual(block.count("-- .github/scripts/test_review_funnel.py\n"), 1)
            self.assertEqual(block.count("run: python .github/scripts/test_review_funnel.py\n"), 1)
            fallback = next(step for step in partition.step_blocks(block)
                            if step.startswith("      - name: Run read-only review funnel contract\n"))
            self.assertIn("if: (matrix.partition == 'all' || matrix.partition == 'contracts') && !(matrix.os == 'windows-latest' && matrix.partition == 'contracts')", fallback)
            self.assertLess(block.index("id: hook_finding_source_prepare"), block.index("id: hook_review_observed"))
            self.assertLess(block.index("id: hook_review_observed"), block.index("id: hook_finding_source_upload"))
            self.assertIn("steps.hook_review_observed.outcome == 'success'", block)
            self.assertIn("steps.hook_finding_source_upload.outcome == 'success'", block)
            self.assertIn('--observation "hook-review=${{ runner.temp }}/python-hook-review-observation.json"', block)
            self.assertIn('--payload-root "major-source-inputs-hooks-findings-windows-contracts=${{ github.workspace }}"', block)
            self.assertEqual(partition.validate(value)["contracts"], 75)
        check(text)
        for before, after in (("-- .github/scripts/test_review_funnel.py\n", "-- .github/scripts/test_review_funnel.py -k partial\n"),
             ("steps.hook_review_observed.outcome == 'success'", "true"),
             ("steps.hook_finding_source_upload.outcome == 'success'", "true"),
             ("--source-profile hooks-finding-contracts-v1", "--source-profile unreviewed"),
             ("Upload hook finding source-test inputs", "Upload unknown inputs")):
            self.assertIn(before, text)
            with self.subTest(change=before), self.assertRaises((AssertionError, ValueError)): check(text.replace(before, after, 1))



class PiSandboxFiniteFindingRoutingTests(unittest.TestCase):
    """Pure report admission over inert named outcomes; no TS/Docker/Pi execution."""
    EXPECTED = {'disposition:findings:SF01': {'profile': 'pi-tools-v1', 'selectors': ['vitest:plugins/ca-pi/tools/test/parent-delegation.test.ts:parent-authorized delegated file effects child proxy crosses real channel and parent final gate before durable file effect', 'vitest:plugins/ca-pi/tools/test/delegation-session.test.ts:parent-owned delegation session lifecycle loss aborts active execution while its owned cleanup can settle', 'vitest:plugins/ca-pi/tools/test/delegation-session.test.ts:parent-owned delegation session real loopback client sends only exact tool data, serializes concurrent requests and revokes', 'vitest:plugins/ca-pi/tools/test/delegation-session.test.ts:parent-owned delegation session authenticates and joins duplicate requests; changed request identity never repeats effects', 'vitest:plugins/ca-pi/tools/test/delegation-session.test.ts:parent-owned delegation session bounds sequence and grant operation population', 'vitest:plugins/ca-pi/tools/test/delegation-session.test.ts:parent-owned delegation session expiry, lifecycle loss, explicit revoke and forged authority never admit effects'], 'scope': 'Finite SF01 source-test behavior: real loopback child proxy and parent gate precede exact owned file effects; bridge refusal, disabled/untrusted lifecycle, token/replay/expiry/sequence bounds refuse effects. Permission callback and native factories are fixture ports. No human TUI, installed author, shell containment or whole PI-D task qualification.'}, 'disposition:findings:SF02': {'profile': 'pi-tools-v1', 'selectors': ['vitest:plugins/ca-pi/tools/test/activation.test.ts:Pi activation persona readiness is independent of bridge health (PI-L01) persona failure followed by bridge success alone stays persona-unavailable', 'vitest:plugins/ca-pi/tools/test/activation.test.ts:Pi activation persona readiness is independent of bridge health (PI-L01) a successful persona retry in the current lifecycle restores prompt and readiness once', 'vitest:plugins/ca-pi/tools/test/activation.test.ts:Pi activation persona readiness is independent of bridge health (PI-L01) a healthy start reports starting then governed, never persona unavailable', 'vitest:plugins/ca-pi/tools/test/activation.test.ts:Pi activation persona readiness is independent of bridge health (PI-L01) an empty persona cannot mark the session governed', 'vitest:plugins/ca-pi/tools/test/activation.test.ts:Pi activation persona readiness is independent of bridge health (PI-L01) a late persona from a retired session never populates the next session'], 'scope': 'Finite SF02 source-test persona readiness, failure, healthy/retry and retired-session behavior through shipped parent installation with fixture host/bridge ports; no model or installed-host qualification.'}, 'disposition:findings:SF03': {'profile': 'pi-tools-v1', 'selectors': ['vitest:plugins/ca-pi/tools/test/sidebar-manager.test.ts:sidebar manager disposal while installation is pending (PI-L02) off while metrics are pending keeps native hooks after metrics resolve', 'vitest:plugins/ca-pi/tools/test/sidebar-manager.test.ts:sidebar manager disposal while installation is pending (PI-L02) dispose while metrics are pending, then resolve: nothing installs', 'vitest:plugins/ca-pi/tools/test/sidebar-manager.test.ts:sidebar manager disposal while installation is pending (PI-L02) off during pending metrics does not persist into a new session', 'vitest:plugins/ca-pi/tools/test/sidebar-manager.test.ts:sidebar manager disposal while installation is pending (PI-L02) a metrics failure after dispose does not report the next session degraded', 'vitest:plugins/ca-pi/tools/test/sidebar-manager.test.ts:sidebar manager disposal while installation is pending (PI-L02) old and new session metrics resolve old-first: only the new session installs, once', 'vitest:plugins/ca-pi/tools/test/sidebar-manager.test.ts:sidebar manager disposal while installation is pending (PI-L02) old and new session metrics resolve new-first: only the new session installs, once'], 'scope': 'Finite SF03 source-test late metrics cannot install into disposed/off sessions or degrade the current session; both completion orders preserve current-session installation and native rendering. Fixture TUI ports; no visible-host or terminal qualification.'}, 'disposition:findings:SF12': {'profile': 'pi-tools-v1', 'selectors': ['vitest:plugins/ca-pi/tools/test/package.test.ts:ca-pi package private artifact approval stays unavailable on the admitted host and legacy evidence grants no ordinary support', 'vitest:plugins/ca-pi/tools/test/approval-dialog.test.ts:isolated Pi native approval dialog passes only the exact native return with pending, session and fresh generation bindings', 'vitest:plugins/ca-pi/tools/test/approval-dialog.test.ts:isolated Pi native approval dialog refuses RPC, missing trust and active tools before constructing a bridge', 'vitest:plugins/ca-pi/tools/test/approval-dialog.test.ts:isolated Pi native approval dialog does not normalize a wrong reply into an approval', 'vitest:plugins/ca-pi/tools/test/approval-dialog.test.ts:isolated Pi native approval dialog reports an uncertain outcome after a consume transport failure', 'vitest:plugins/ca-pi/tools/test/approval-dialog.test.ts:isolated Pi native approval dialog requires one exact closed CLI launch and rejects added commands, tools, extensions or preloads'], 'scope': 'Finite SF12 source-test compatibility declares private approval unavailable on Pi 1.5.0 and legacy runtime-gated only; isolated dialog controls are synthetic and never ordinary installed approval or human consent evidence. No production doctor or host-observed approval qualification.'}, 'disposition:findings:SF08': {'profile': 'sandbox-tools-v1', 'selectors': ['vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 equal inputs in different checkout basenames select a verified stable key', 'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 existence alone is a cache miss and toolchain identity changes the tag', 'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 malformed builder observation blocks reuse and invalid provenance forces rebuild', 'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 real probe output cannot launder malformed version prose into a cache identity', 'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 create uses the observed immutable image despite a mutable cache tag', 'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 manifest observation distinguishes absent inputs, valid bytes and unreadable declared inputs', 'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 dangling declared configuration is unavailable rather than a missing input', 'vitest:plugins/ca-sandbox/tools/cache-provenance.test.ts:SBX-C01 real two-create cache provenance dockerfile-fallback: distinct staging names reuse the exact labeled image and preserve another box', 'vitest:plugins/ca-sandbox/tools/cache-provenance.test.ts:SBX-C01 real two-create cache provenance nixpacks: distinct staging names reuse the exact labeled image and preserve another box'], 'scope': 'Finite SF08 requires pure cache-key/provenance/refusal guards AND both original real Docker builder cases: distinct staging names reuse the labeled immutable image, changed dependency bytes rebuild, concurrent cold requests converge and deleting one box preserves another. No remote clone/auth, arbitrary image or installed CLI credit.'}, 'disposition:findings:SF10': {'profile': 'sandbox-tools-v1', 'selectors': ['vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C03 reports failed resource observations as unavailable, not empty', 'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C03 cancellation cannot cancel compensation and unknown cleanup retains exact references', 'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C03 cancelled firewall setup keeps exact cleanup live and never invents destruction', 'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C03 partial failure stdout cannot authorize destruction of an unobserved target'], 'scope': 'Finite SF10 source-test unavailable discovery, cancellation-independent compensation, retained unknown cleanup references and refusal to destroy unobserved targets through actual production functions with injected Docker observations. No universal cleanup, real daemon outage or host containment claim.'}, 'disposition:findings:SF09': {'profile': 'sandbox-tools-v1', 'selectors': ['vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C02 treats overflow as lost observation and verifies target containment', 'vitest:plugins/ca-sandbox/tools/deadline.test.ts:#394 — a real hung command terminates within its deadline SBX-C02 real output overflow stops only its exact target and preserves another running box'], 'scope': 'Finite SF09 requires the original real Docker overflow case plus unit stop/inspect guard: actual capped exec overflows without timeout, exact target independently inspects stopped and a separate running box remains alive. No arbitrary workload, global cleanup or installed CLI qualification.'}}

    def test_original_sandbox_deadline_and_cache_rows_use_existing_observer(self):
        history = owner.ROOT / 'docs/state-contracts-major/execution/evidence'
        deadlines = history / 'farm-sandbox-remaining-ae237d'
        assertions = {case['id']: case['exact_selector'] for case in
                      owner.load_json(deadlines / 'raw/selected-named-observations.json')['assertions']}
        expected = {row['cell']: [assertions[ref] for ref in row['assertion_refs']]
                    for row in owner.load_json(deadlines / 'sandbox-client-and-required-gate-tested.json')['semantic_mapping']}
        cache = owner.load_json(history / 'post-intake-deltas-9e3b2ea5/sandbox-cache-cancel-tested.json')
        row, = cache['semantic_groups']
        expected[row['cells'][0]] = ['vitest:plugins/ca-sandbox/tools/build.test.ts:' + title
                                     for title in row['named_cases']]
        selections = owner.validate_selections(owner.load_json(owner.ROOT / '.github/major-test-selections.json'))
        policy = owner.load_json(owner.ROOT / '.github/major-qualification-policy.json')
        groups = [group for group in selections if set(group['cells']) & expected.keys()]
        self.assertEqual({group['cells'][0]: group['selectors'] for group in groups}, expected)
        profile = 'sandbox-tools-v1'
        self.assertEqual({cell: policy['cell_job_bindings'].get(cell) for cell in expected},
                         dict.fromkeys(expected, owner.TS_PROFILE_JOBS[profile]))
        with vitest_source_fixture(profile) as fixture:
            observations, _, _, build = self.fixture_report(fixture, groups)
            report = build()
            self.assertEqual({row['cell'] for row in report['results']}, expected.keys())
            for cell, selectors in expected.items():
                changed = {**observations, 'tests': [case for case in observations['tests']
                           if case['id'] != selectors[-1]]}
                with self.subTest(cell=cell), self.assertRaisesRegex(ValueError, 'selected named test'):
                    build(o=changed)

    def groups(self, profile):
        return [{"id": "finite-" + cell.rsplit(":", 1)[1], "job": owner.TS_PROFILE_JOBS[profile],
            "payload_name": owner.TS_PROFILE_PAYLOADS[profile], "observation": "pi-tools" if profile == "pi-tools-v1" else "sandbox-tools",
            "proof_kind": "source-test", "selectors": row["selectors"], "cells": [cell], "scope": row["scope"]}
            for cell, row in self.EXPECTED.items() if row["profile"] == profile]

    def fixture_report(self, fixture, groups):
        profile = fixture["spec"]["root"]
        payload = VitestSourceProducerTests.authenticate(self, fixture)
        names = sorted({name for group in groups for name in group["selectors"]})
        observed = {"format": owner.OBSERVATION, **fixture["identity"], "ci_run_id": 7,
            "source_stable": True, "proof_kind": "source-test", "producer": "vitest-json-observer",
            "argv": fixture["command"], "exit_code": 0,
            "tests": [{"id": name, "result": "passed"} for name in names],
            "source_input_binding": {"format": owner.SOURCE_BINDING, "profile": fixture["manifest"]["profile"],
                "payload_name": fixture["spec"]["payload"],
                "manifest_sha256": owner.readiness.digest((fixture["staged"] / owner.SOURCE_MANIFEST).read_bytes())}}
        req = {**fixture["identity"], "ci_run_id": 7, "cells": sorted(g["cells"][0] for g in groups),
            "cell_jobs": {g["cells"][0]: fixture["spec"]["job"] for g in groups}}
        def build(o=observed, p=payload, selected=groups, required=req, job=fixture["spec"]["job"]):
            return owner.build_report(required, job_name=job, job_id=9,
                selections={"schema": owner.SELECTIONS, "groups": selected},
                observations={groups[0]["observation"]: o}, payloads={fixture["spec"]["payload"]: p})
        return observed, payload, req, build

    def test_a_complete_existing_finite_findings_reach_the_original_report_boundary(self):
        for profile in TS_PROFILE_FIXTURES:
            with self.subTest(profile=profile), vitest_source_fixture(profile) as f:
                groups = self.groups(profile)
                _, _, req, build = self.fixture_report(f, groups)
                try:
                    report = build()
                except ValueError as exc:
                    self.fail("original report boundary lacks complete finite finding mapping: " + str(exc))
                self.assertEqual({r["cell"] for r in report["results"]}, set(req["cells"]))

    def test_b_configuration_requires_exact_complete_finite_compositions_and_existing_source_closure(self):
        groups = owner.validate_selections(owner.load_json(owner.ROOT / ".github/major-test-selections.json"))
        policy = owner.load_json(owner.ROOT / ".github/major-qualification-policy.json")
        selected = [g for g in groups if set(g["cells"]) & set(self.EXPECTED)]
        self.assertEqual(len(selected), len(self.EXPECTED))
        for cell, row in self.EXPECTED.items():
            group, = [g for g in selected if cell in g["cells"]]
            self.assertEqual(group["cells"], [cell])
            self.assertEqual(group["job"], owner.TS_PROFILE_JOBS[row["profile"]])
            self.assertEqual(policy["cell_job_bindings"][cell], group["job"])
            self.assertEqual(group["payload_name"], owner.TS_PROFILE_PAYLOADS[row["profile"]])
            self.assertEqual(group["observation"], "pi-tools" if row["profile"] == "pi-tools-v1" else "sandbox-tools")
            self.assertEqual(group["proof_kind"], "source-test")
            self.assertEqual(set(group["selectors"]), set(row["selectors"]))
            for selector in group["selectors"]:
                path, title = selector[len("vitest:"):].split(":", 1)
                self.assertIn(path, owner.TS_PROFILE_PATHS[row["profile"]])
                body = (owner.ROOT / path).read_text(encoding="utf-8")
                # Concrete source name witnesses: dynamic builder/order titles
                # retain their exact two finite expansions, not regex selectors.
                if ": distinct staging names" in title:
                    self.assertIn("distinct staging names reuse the exact labeled image and preserve another box", body)
                    self.assertIn('["dockerfile-fallback", "nixpacks"]', body)
                elif "old and new session metrics resolve" in title:
                    self.assertIn('"old and new session metrics resolve %s: only the new session installs, once"', body)
                    self.assertIn('["old-first", "new-first"]', body)
                else:
                    self.assertTrue(any(title.endswith(t) for t in __import__('re').findall(r'(?:test|it)\("([^"\n]+)"', body)), selector)
        from site_component_observation import JOB, PAYLOAD, RECIPES, ROLE

        component_cell = "disposition:findings:SF11"
        component, = (group for group in groups if component_cell in group["cells"])
        self.assertEqual(component["cells"], [component_cell])
        self.assertEqual(policy["cell_job_bindings"][component_cell], JOB)
        self.assertEqual((component["job"], component["payload_name"], component["observation"],
                          component["proof_kind"], component["selectors"]),
                         (JOB, PAYLOAD, ROLE, "source-test", RECIPES[component_cell]))

    def test_c_no_missing_skipped_failed_or_duplicate_outcome_can_qualify_a_finding(self):
        for profile in TS_PROFILE_FIXTURES:
            with vitest_source_fixture(profile) as f:
                groups = self.groups(profile); observed, _, _, build = self.fixture_report(f, groups)
                self.assertTrue(build()["results"])
                for name in sorted({s for g in groups for s in g["selectors"]}):
                    for state in ("missing", "skipped", "failed", "duplicate"):
                        changed = copy.deepcopy(observed); item = next(t for t in changed["tests"] if t["id"] == name)
                        if state == "missing": changed["tests"].remove(item)
                        elif state == "duplicate": changed["tests"].append(dict(item))
                        else: item["result"] = state
                        with self.subTest(selector=name, state=state), self.assertRaisesRegex(ValueError, "selected named test"):
                            build(o=changed)

    def test_d_partial_added_cross_profile_and_unowned_scope_compositions_refuse(self):
        for profile in TS_PROFILE_FIXTURES:
            with vitest_source_fixture(profile) as f:
                groups = self.groups(profile); observed, payload, req, build = self.fixture_report(f, groups)
                for index, group in enumerate(groups):
                    for selector in group["selectors"]:
                        changed = copy.deepcopy(groups); changed[index]["selectors"].remove(selector)
                        with self.subTest(cell=group["cells"], missing=selector), self.assertRaisesRegex(ValueError, "complete exact finite finding"):
                            build(selected=changed)
                    changed = copy.deepcopy(groups); changed[index]["selectors"].append("vitest:foreign.test.ts:invented")
                    with self.assertRaisesRegex(ValueError, "complete exact finite finding"): build(selected=changed)
                for failure in ("source", "run", "unstable", "exit", "profile", "manifest", "uploader", "role", "job"):
                    o, p, selected, required = copy.deepcopy(observed), copy.deepcopy(payload), copy.deepcopy(groups), copy.deepcopy(req)
                    job = f["spec"]["job"]
                    if failure == "source": o["source_commit"] = "f" * 40
                    if failure == "run": o["ci_run_id"] = 8
                    if failure == "unstable": o["source_stable"] = False
                    if failure == "exit": o["exit_code"] = 1
                    if failure == "profile": o["source_input_binding"]["profile"] = "sandbox-tools-v1" if profile == "pi-tools-v1" else "pi-tools-v1"
                    if failure == "manifest": p["source_manifest_sha256"] = "0" * 64
                    if failure == "uploader": p["source_upload_job_id"] = True
                    if failure == "role": selected[0]["payload_name"] = "foreign-native-archive"
                    if failure == "job":
                        job = "unrelated job"
                        for g in selected: g["job"] = job
                        required["cell_jobs"] = dict.fromkeys(required["cells"], job)
                    with self.subTest(failure=failure), self.assertRaises(ValueError): build(o, p, selected, required, job)
                for cell in ("disposition:findings:SF11", "task:PI-D07", "task:SBX-C01", "installed:pi:1.5.0", "disposition:machines:S01"):
                    changed = copy.deepcopy(groups[:1]); changed[0]["cells"] = [cell]
                    required = {**req, "cells": [cell], "cell_jobs": {cell: f["spec"]["job"]}}
                    with self.subTest(unowned=cell), self.assertRaises(ValueError): build(selected=changed, required=required)

    def test_e_real_overflow_target_and_survivor_assertions_reach_existing_report_admission(self):
        with vitest_source_fixture("sandbox-tools-v1") as f:
            group, = [g for g in self.groups("sandbox-tools-v1") if g["cells"] == ["disposition:findings:SF09"]]
            _, _, _, build = self.fixture_report(f, [group])
            try:
                report = build()
            except ValueError as exc:
                self.fail("original overflow report boundary lacks its real target/survivor composition: " + str(exc))
            self.assertEqual([r["cell"] for r in report["results"]], ["disposition:findings:SF09"])


class FarmFiniteFindingObservationPrerequisiteTests(unittest.TestCase):
    """Criterion for original Farm source-test report admission, not runtime proof."""
    PROFILE = "farm-tools-v1"
    JOB = "[CHECK] | [CA  ] | Farm dispatcher contract"
    PAYLOAD = "major-source-inputs-farm-dispatcher"
    UPLOAD = "Upload Farm source-test inputs"
    PATHS = frozenset(('.github/fixtures/artifact-release-manifest.json',
 '.github/major-qualification-policy.json',
 '.github/major-test-selections.json',
 '.github/scripts/_boundedproc.py',
 '.github/scripts/_contextverificationlib.py',
 '.github/scripts/_immutable_git_blobs.py',
 '.github/scripts/ci20_native_binding.py',
 '.github/scripts/major_qualification_report.py',
 '.github/scripts/major_readiness.py',
 '.github/workflows/ci.yml',
 'core/artifact-release-manifest.json',
 'core/pysrc/_artifactauthoritylib.py',
 'core/pysrc/_artifactlib.py',
 'core/pysrc/_artifactmanifestlib.py',
 'core/pysrc/_artifactpromptlib.py',
 'core/pysrc/_gitexec.py',
 'core/pysrc/_replylib.py',
 'plugins/ca/tools/.env.example',
 'plugins/ca/tools/__fixtures__/simple.plan.json',
 'plugins/ca/tools/artifact-manifest.test.ts',
 'plugins/ca/tools/artifact-manifest.ts',
 'plugins/ca/tools/exec.test.ts',
 'plugins/ca/tools/exec.ts',
 'plugins/ca/tools/farm-cleanup-observation.test.ts',
 'plugins/ca/tools/farm-dist.test.ts',
 'plugins/ca/tools/farm-interruption.test.ts',
 'plugins/ca/tools/farm-recovery.test.ts',
 'plugins/ca/tools/farm-recovery.ts',
 'plugins/ca/tools/farm-registry-lock.test.ts',
 'plugins/ca/tools/farm-surface.test.ts',
 'plugins/ca/tools/farm.js',
 'plugins/ca/tools/farm.test.ts',
 'plugins/ca/tools/farm.ts',
 'plugins/ca/tools/farm.unit.test.ts',
 'plugins/ca/tools/mutation.test.ts',
 'plugins/ca/tools/mutation.ts',
 'plugins/ca/tools/package-lock.json',
 'plugins/ca/tools/package.json',
 'plugins/ca/tools/plan-contract.test.ts',
 'plugins/ca/tools/plan.schema.json',
 'plugins/ca/tools/redactor.test.ts',
 'plugins/ca/tools/redactor.ts',
 'plugins/ca/tools/state-contracts.test.ts',
 'plugins/ca/tools/tsconfig.json',
 'plugins/ca/tools/vitest.config.ts',
 'plugins/ca/tools/worktree-fs.test.ts',
 'plugins/ca/tools/worktree-fs.ts'))
    EXPECTED = {'disposition:findings:SF04': {'selectors': ['vitest:plugins/ca/tools/artifact-manifest.test.ts:shared '
                                             'native manifest declarations candidate-five-fields',
                                             'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared '
                                             'native manifest declarations qualified-declaration-six-fields',
                                             'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared '
                                             'native manifest declarations unknown-field',
                                             'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared '
                                             'native manifest declarations unknown-format',
                                             'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared '
                                             'native manifest declarations malformed-context',
                                             'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared '
                                             'native manifest declarations unknown-context-platform',
                                             'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared '
                                             'native manifest declarations wrong-context-binary',
                                             'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared '
                                             'native manifest declarations unknown-context-field',
                                             'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared '
                                             'native manifest declarations wrong-platform-path',
                                             'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared '
                                             'native manifest declarations unqualified-context',
                                             'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared '
                                             'native manifest declarations bounds UTF-8 bytes before parsing',
                                             'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared '
                                             'native manifest declarations rejects duplicate and '
                                             'escaped-duplicate keys'],
                               'scope': 'Finite shared Farm parser acceptance of the optional sixth '
                                        'context_qualification declaration and all original '
                                        'malformed/unknown/duplicate/bounded input refusals. Fixtures are '
                                        'synthetic schema declarations, never native runtime or context '
                                        'qualification.'},
 'disposition:findings:SF05': {'selectors': ['vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R01 '
                                             'exclusive identities preserve evidence under a same-ID race',
                                             'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R01 '
                                             'reconciles a post-merge crash in real Git without changing a '
                                             'ref or calling an author',
                                             'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 '
                                             'real post-merge process interruption preserves unknown cleanup '
                                             'and concurrent receipt-only recovery (source)',
                                             'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 '
                                             'real post-merge process interruption preserves unknown cleanup '
                                             'and concurrent receipt-only recovery (bundle)',
                                             'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 '
                                             'real post-commit process interruption retains unacknowledged '
                                             'candidate without recovered green (source)',
                                             'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 '
                                             'real post-commit process interruption retains unacknowledged '
                                             'candidate without recovered green (bundle)',
                                             'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 '
                                             'real pre-merge interruption preserves pending merge resources '
                                             'through receipt-only recovery (source)',
                                             'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 '
                                             'real pre-merge interruption preserves pending merge resources '
                                             'through receipt-only recovery (bundle)',
                                             'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 '
                                             'unblocked real post-merge hook control publishes normal green '
                                             'receipt (bundle)',
                                             'vitest:plugins/ca/tools/farm.test.ts:farm artifact publication '
                                             '(#397 / #387) #397: a failed report publication leaves the '
                                             "previous run's complete report intact — never a truncated one",
                                             'vitest:plugins/ca/tools/farm.test.ts:farm artifact publication '
                                             '(#397 / #387) #387: a green run whose farm-report.json cannot '
                                             'be published exits non-zero and never claims a Report path',
                                             'vitest:plugins/ca/tools/farm.test.ts:farm artifact publication '
                                             '(#397 / #387) FARM-R01 journal publication failure drains '
                                             'independent tasks and retains their real outcomes',
                                             'vitest:plugins/ca/tools/farm.test.ts:farm artifact publication '
                                             '(#397 / #387) #387: a failure to publish farm-report.md also '
                                             'fails the run'],
                               'scope': 'Finite JSON/Markdown/effect-journal receipt failure remains '
                                        'explicit, previous complete report survives and independently '
                                        'running tasks drain; receipt-only recovery through actual '
                                        'source/bundle interruptions never calls an author or changes '
                                        'recorded refs/registry/original evidence. Deterministic local HTTP '
                                        'replies substitute model/provider; no real provider, installed '
                                        'approval or global process-containment qualification.'},
 'disposition:findings:SF06': {'selectors': ['vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R02 '
                                             'preserves failed containment and admits no reset or second '
                                             'author',
                                             'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R02 gate '
                                             'retains executor outcome instead of flattening code 125 into '
                                             'test failure',
                                             'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R02 '
                                             'uncontained sample setup retains scratch resources without '
                                             'authoring or reset'],
                               'scope': 'Finite preservation of failed containment through actual '
                                        'gate/runTask/setup consumers: no reset, mutation or second author; '
                                        'retained outcome and scratch resources remain unknown. Executor '
                                        'observations are injected, not OS containment proof.'},
 'disposition:findings:SF07': {'selectors': ['vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R03 '
                                             'refuses unknown Git drift instead of inventing a clean '
                                             'observation',
                                             'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R03 '
                                             'bounded read-only retry accepts only a successful current '
                                             'observation',
                                             'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R03 fresh '
                                             'pre-stage dirty drift controls dependent mutations',
                                             'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R03 fresh '
                                             'pre-stage unavailable drift controls dependent mutations',
                                             'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R03 fresh '
                                             'pre-stage clean drift controls dependent mutations'],
                               'scope': 'Finite failed/malformed Git observation refusal, bounded read-only '
                                        'retry and fresh pre-stage dirty/unavailable/clean mutation '
                                        'decisions; fixture observations do not qualify arbitrary '
                                        'repository/concurrency or installed host state.'}}

    EXPECTED["scenario:SEQ-17"] = {"selectors": [
        'vitest:plugins/ca/tools/farm.test.ts:farm artifact publication (#397 / #387) #387: a green run whose farm-report.json cannot be published exits non-zero and never claims a Report path',
        'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 real post-merge process interruption preserves unknown cleanup and concurrent receipt-only recovery (source)',
        'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 real post-merge process interruption preserves unknown cleanup and concurrent receipt-only recovery (bundle)',
    ], "scope": 'Real disposable Git and Farm source/bundle receipt-only recovery on exact same run identity after a post-merge report write failure or producer interruption. Recovery preserves a single author dispatch, refs and prior evidence. Local deterministic HTTP replies only.'}

    def test_original_unfiltered_farm_findings_have_closed_source_and_named_report_admission(self):
        # Existing public API must admit this finite original owner. The current
        # absence is an assertion failure, never a missing method/import seam.
        try:
            spec = owner.source_profile(self.PROFILE)
        except ValueError as exc:
            self.fail("original Farm finding source profile is unavailable: " + str(exc))
        self.assertEqual(spec, {"paths": self.PATHS, "job": self.JOB,
            "payload": self.PAYLOAD, "upload": self.UPLOAD, "root": "plugins/ca/tools"})
        configured = owner.validate_selections(owner.load_json(owner.ROOT / ".github/major-test-selections.json"))
        groups = [g for g in configured if set(g["cells"]) & set(self.EXPECTED)]
        self.assertEqual(len(groups), len(self.EXPECTED))
        policy = owner.load_json(owner.ROOT / ".github/major-qualification-policy.json")
        for cell, row in self.EXPECTED.items():
            group, = [g for g in groups if cell in g["cells"]]
            self.assertEqual(group["cells"], [cell])
            self.assertEqual(group["job"], self.JOB)
            self.assertEqual(policy["cell_job_bindings"][cell], self.JOB)
            self.assertEqual(group["payload_name"], self.PAYLOAD)
            self.assertEqual(group["observation"], "farm-tools")
            self.assertEqual(group["proof_kind"], "source-test")
            self.assertEqual(set(group["selectors"]), set(row["selectors"]))
        fixture_spec = {"job": self.JOB, "payload": self.PAYLOAD, "root": "plugins/ca/tools",
            "test": "plugins/ca/tools/state-contracts.test.ts", "paths": sorted(self.PATHS)}
        with mock.patch.dict(TS_PROFILE_FIXTURES, {self.PROFILE: fixture_spec}), vitest_source_fixture(self.PROFILE) as f:
            source_job = {"id": 9, "name": self.JOB, "status": "in_progress", "conclusion": None,
                "steps": [{"name": self.UPLOAD, "status": "completed", "conclusion": "success"}]}
            payload = VitestSourceProducerTests.authenticate(self, f, job=source_job)
            observed = {"format": owner.OBSERVATION, **f["identity"], "ci_run_id": 7,
                "source_stable": True, "proof_kind": "source-test", "producer": "vitest-json-observer",
                "argv": f["command"], "exit_code": 0,
                "tests": [{"id": s, "result": "passed"} for s in sorted({s for r in self.EXPECTED.values() for s in r["selectors"]})],
                "source_input_binding": {"format": owner.SOURCE_BINDING, "profile": self.PROFILE,
                    "payload_name": self.PAYLOAD,
                    "manifest_sha256": owner.readiness.digest((f["staged"] / owner.SOURCE_MANIFEST).read_bytes())}}
            required = {**f["identity"], "ci_run_id": 7, "cells": sorted(self.EXPECTED),
                "cell_jobs": dict.fromkeys(self.EXPECTED, self.JOB)}
            report = owner.build_report(required, job_name=self.JOB, job_id=9,
                selections={"schema": owner.SELECTIONS, "groups": groups}, observations={"farm-tools": observed},
                payloads={self.PAYLOAD: payload})
            self.assertEqual({r["cell"] for r in report["results"]}, set(self.EXPECTED))
            self.assertTrue(all(r["result"] == "PASSED" for r in report["results"]))

    @contextmanager
    def bound_farm(self):
        fixture = {"job": self.JOB, "payload": self.PAYLOAD, "root": "plugins/ca/tools",
            "test": "plugins/ca/tools/state-contracts.test.ts", "paths": sorted(self.PATHS)}
        with mock.patch.dict(TS_PROFILE_FIXTURES, {self.PROFILE: fixture}), vitest_source_fixture(self.PROFILE) as f:
            source_job = {"id": 9, "name": self.JOB, "status": "in_progress", "conclusion": None,
                "steps": [{"name": self.UPLOAD, "status": "completed", "conclusion": "success"}]}
            payload = VitestSourceProducerTests.authenticate(self, f, job=source_job)
            groups = [g for g in owner.validate_selections(owner.load_json(owner.ROOT / ".github/major-test-selections.json"))
                if set(g["cells"]) & set(self.EXPECTED)]
            observed = {"format": owner.OBSERVATION, **f["identity"], "ci_run_id": 7,
                "source_stable": True, "proof_kind": "source-test", "producer": "vitest-json-observer",
                "argv": ["npm", "test"], "exit_code": 0,
                "tests": [{"id": name, "result": "passed"} for name in sorted({s for r in self.EXPECTED.values() for s in r["selectors"]})],
                "source_input_binding": {"format": owner.SOURCE_BINDING, "profile": self.PROFILE,
                    "payload_name": self.PAYLOAD, "manifest_sha256": payload["source_manifest_sha256"]}}
            req = {**f["identity"], "ci_run_id": 7, "cells": sorted(self.EXPECTED),
                "cell_jobs": dict.fromkeys(self.EXPECTED, self.JOB)}
            def build(o=observed, consumed=payload, selected=groups, required=req, job=self.JOB):
                return owner.build_report(required, job_name=job, job_id=9,
                    selections={"schema": owner.SELECTIONS, "groups": selected},
                    observations={"farm-tools": o}, payloads={self.PAYLOAD: consumed})
            yield f, observed, payload, groups, req, build

    def test_farm_exact_selector_unions_and_source_identities_refuse_partial_or_forged_credit(self):
        with self.bound_farm() as (f, observed, payload, groups, req, build):
            self.assertEqual(len(build()["results"]), len(self.EXPECTED))
            for name in sorted({s for g in groups for s in g["selectors"]}):
                for state in ("missing", "skipped", "failed", "duplicate"):
                    changed = copy.deepcopy(observed); row = next(t for t in changed["tests"] if t["id"] == name)
                    if state == "missing": changed["tests"].remove(row)
                    elif state == "duplicate": changed["tests"].append(dict(row))
                    else: row["result"] = state
                    with self.subTest(selector=name, state=state), self.assertRaisesRegex(ValueError, "selected named test"):
                        build(o=changed)
            for index, group in enumerate(groups):
                for selector in group["selectors"]:
                    selected = copy.deepcopy(groups); selected[index]["selectors"].remove(selector)
                    with self.subTest(reduced=selector), self.assertRaisesRegex(ValueError, "complete exact finite finding"):
                        build(selected=selected)
                selected = copy.deepcopy(groups); selected[index]["selectors"].append("vitest:foreign.test.ts:invented")
                with self.assertRaises(ValueError): build(selected=selected)
            for failure in ("source", "run", "unstable", "exit", "profile", "manifest", "upload", "role", "job"):
                o, consumed, selected, required = copy.deepcopy(observed), copy.deepcopy(payload), copy.deepcopy(groups), copy.deepcopy(req)
                job = self.JOB
                if failure == "source": o["source_commit"] = "f" * 40
                if failure == "run": o["ci_run_id"] = 8
                if failure == "unstable": o["source_stable"] = False
                if failure == "exit": o["exit_code"] = 1
                if failure == "profile": o["source_input_binding"]["profile"] = "sandbox-tools-v1"
                if failure == "manifest": consumed["source_manifest_sha256"] = "0" * 64
                if failure == "upload": consumed["source_upload_job_id"] = True
                if failure == "role": selected[0]["payload_name"] = "unrelated-native-archive"
                if failure == "job":
                    job = "foreign Farm owner"
                    for g in selected: g["job"] = job
                    required["cell_jobs"] = dict.fromkeys(required["cells"], job)
                with self.subTest(failure=failure), self.assertRaises(ValueError): build(o, consumed, selected, required, job)
            for cell in ("task:FARM-R01", "installed:farm:linux", "disposition:machines:S29", "disposition:findings:SF01"):
                selected = copy.deepcopy(groups[:1]); selected[0]["cells"] = [cell]
                required = {**req, "cells": [cell], "cell_jobs": {cell: self.JOB}}
                with self.subTest(unowned=cell), self.assertRaises(ValueError): build(selected=selected, required=required)

    def test_external_manifest_inputs_and_exact_farm_namespace_are_actually_bound(self):
        with self.bound_farm() as (f, *_):
            stage = f["base"] / "prepared"
            self.assertEqual(owner.prepare_source_payload(f["repo"], stage, self.JOB, self.PROFILE), f["manifest"])
            for name in ("core/artifact-release-manifest.json", ".github/fixtures/artifact-release-manifest.json"):
                target = f["repo"] / name; before = target.read_bytes()
                try:
                    target.write_bytes(before + b"changed external declaration\n")
                    with self.subTest(input=name), self.assertRaises(ValueError):
                        owner.prepare_source_payload(f["repo"], f["base"] / "refused", self.JOB, self.PROFILE)
                finally: target.write_bytes(before)
            extra = f["repo"] / "plugins/ca/tools/unbound-contract.ts"; extra.write_bytes(b"unbound")
            try:
                with self.assertRaises(ValueError): owner._ts_members(f["repo"], self.PROFILE)
            finally: extra.unlink()
            self.assertEqual(owner.source_profile(self.PROFILE)["paths"], self.PATHS)

    def test_final_farm_reader_authenticates_exact_original_upload_owner(self):
        cell = "disposition:findings:SF05"; source = {"id": 8, "name": self.PAYLOAD}
        artifact = {"id": 10, "name": "major-qualification-9"}
        job = {"id": 9, "name": self.JOB, "status": "completed", "conclusion": "success"}
        req = {"source_commit": "a" * 40, "source_tree": "b" * 40, "ci_run_id": 7,
            "cells": [cell], "cell_jobs": {cell: self.JOB}, "required_artifact_names": [self.PAYLOAD]}
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive: archive.writestr("source-member", b"inert final-reader role fixture")
        content = raw.getvalue(); members = owner.readiness.members(content)
        report = {"schema": "codearbiter-major-qualification/2", **{k: req[k] for k in ("source_commit", "source_tree", "ci_run_id")},
            "job_id": 9, "payloads": [{"artifact_id": 8, "archive_sha256": owner.readiness.digest(content), "members": members}],
            "results": [{"cell": cell, "result": "PASSED", "commands": [{"argv": ["npm", "test"], "exit_code": 0}],
                "selected_population": 1, "executed_population": 1, "payload_artifact_id": 8}]}
        jobs = [job, {"id": 11, "name": "major readiness producer"}]
        with mock.patch.object(owner.readiness, "read_artifact_json", return_value=report), \
             mock.patch.object(owner.readiness, "artifact_bytes", return_value=content), \
             mock.patch.object(owner.readiness, "validate_upload") as attribution:
            owner.readiness.produce(req, [source, artifact], jobs)
            self.assertEqual(attribution.call_args_list, [mock.call(job, artifact, "Upload major qualification report"),
                                                       mock.call(job, source, self.UPLOAD)])
            def refuse(_job, _artifact, step):
                if step == self.UPLOAD: raise owner.readiness.ReadinessError("original Farm source upload refused")
            attribution.side_effect = refuse
            with self.assertRaises(owner.readiness.ReadinessError): owner.readiness.produce(req, [source, artifact], jobs)
            attribution.side_effect = None
            foreign = {**job, "name": "foreign Farm source owner"}
            with self.assertRaises(owner.readiness.ReadinessError):
                owner.readiness.produce({**req, "cell_jobs": {cell: foreign["name"]}}, [source, artifact], [foreign, jobs[1]])

    @staticmethod
    def farm_workflow_contract(ci):
        import re
        import test_ci_impact as reader
        block = reader.workflow_jobs(ci)["tools"]
        predicate, = reader.reviewed_vitest_source_event_guards(block, "tools")
        if block.count('GH_TOKEN: ${{ github.token }}') != 1 or 'continue-on-error:' in block:
            raise ValueError("Farm authority or suppression differs")
        if '    permissions:\n      contents: read\n      actions: read\n' not in block:
            raise ValueError("Farm metadata permissions differ")
        steps = {part.splitlines()[0]: part for part in re.split(r'(?m)^      - name: ', block)[1:]}
        original = steps["Test"]
        required = ['id: farm_tools_observed', '--execution-cwd plugins/ca/tools', '--source-payload "$RUNNER_TEMP/farm-source-inputs"',
            '-- npm test -- --reporter=default --reporter=json', '--outputFile.json="$RUNNER_TEMP/farm-vitest.json"']
        if any(t not in original for t in required) or block.count('-- npm test') != 1 or re.search(r'(?m)^        if:', original):
            raise ValueError("original Farm execution differs or repeats")
        if any(t in original for t in ('--filter', '--testNamePattern', 'GH_TOKEN:', '|| true')):
            raise ValueError("original Farm population or credentials differ")
        prepare, upload, emit = (steps[n] for n in ('Prepare Farm source-test inputs', 'Upload Farm source-test inputs',
                                                   'Emit original Farm source qualification report'))
        if not block.index('      - name: Fail if committed farm.js is stale') < block.index('      - name: Prepare Farm source-test inputs') < block.index('      - name: Test'):
            raise ValueError("Farm build/source/test ordering differs")
        if ('--source-profile farm-tools-v1' not in prepare or 'GH_TOKEN:' in prepare or
            'name: major-source-inputs-farm-dispatcher' not in upload or
            '--observation "farm-tools=$RUNNER_TEMP/farm-vitest-observation.json"' not in emit or
            '--payload-root "major-source-inputs-farm-dispatcher=${{ github.workspace }}"' not in emit or
            '--output "$RUNNER_TEMP/qualification.json"' not in emit):
            raise ValueError("closed Farm producer role differs")
        if block.index('      - name: Upload Farm source-test inputs') > block.index('      - name: Emit original Farm source qualification report'):
            raise ValueError("Farm report precedes source upload")
        return predicate

    def test_farm_original_once_workflow_and_closed_authority_refuse_mutants(self):
        ci = (owner.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("github.event_name == 'push'", self.farm_workflow_contract(ci))
        for before, after in (
            ('--source-profile farm-tools-v1', '--source-profile sandbox-tools-v1'),
            ('-- npm test -- --reporter=default --reporter=json', '-- npm test -- --filter selected --reporter=default --reporter=json'),
            ('--reporter=default --reporter=json', '--reporter=json'),
            ('id: farm_tools_observed\n', 'id: farm_tools_observed\n        if: false\n'),
            ('id: farm_tools_observed\n', 'id: farm_tools_observed\n        env:\n          GH_TOKEN: ${{ github.token }}\n'),
            ('steps.farm_tools_observed.outcome == \'success\'', 'steps.farm_tools_observed.outcome != \'skipped\''),
            ('steps.farm_source_upload.outcome == \'success\'', 'steps.farm_source_upload.outcome != \'skipped\''),
            ('Emit original Farm source qualification report', 'Emit unreviewed Farm source qualification report'),
            ('major-source-inputs-farm-dispatcher=${{ github.workspace }}', 'foreign-inputs=${{ github.workspace }}'),
            ('--observation "farm-tools=', '--observation "foreign-tools='),
        ):
            self.assertIn(before, ci)
            with self.subTest(mutation=before), self.assertRaises((ValueError, KeyError)): self.farm_workflow_contract(ci.replace(before, after, 1))


class ReleaseSelectionFiniteFindingTests(unittest.TestCase):
    """Synthetic original-transport admission; no release execution."""
    CELL = "disposition:findings:C-F02"
    METHODS = (
        "test_newer_failed_head_selects_the_older_successful_source_and_says_so",
        "test_route_publication_is_observed_after_every_target_settles",
        "test_route_observer_uses_only_read_permission_and_declares_public_visibility",
        "test_no_successful_ci_is_refused",
        "test_source_no_longer_on_main_is_refused",
        "test_expired_or_missing_artifacts_are_reported_not_hidden",
        "test_selection_that_differs_from_the_approved_candidate_is_refused",
        "test_workflow_run_event_binds_its_own_run",
    )
    SELECTORS = tuple("python:.github/scripts/test_release_workflow.py:__main__.SourceSelectionTest." + name for name in METHODS)

    @contextmanager
    def fixture(self):
        with q02_python_source_fixture() as f:
            owner.prepare_source_payload(f["repo"], f["staged"], f["job"], f["profile"])
            req, payload = Q02ReadinessSourceProfileTests().authenticate(f)
            req.update(cells=[self.CELL], cell_jobs={self.CELL: f["job"]})
            group = {"id": "finite-cf02", "job": f["job"], "payload_name": f["payload"],
                     "observation": "q02-release", "proof_kind": "source-test", "cells": [self.CELL],
                     "selectors": list(self.SELECTORS), "scope": "Inert finite admission fixture, not release qualification."}
            observed = {"format": owner.OBSERVATION, "source_commit": req["source_commit"],
                        "source_tree": req["source_tree"], "ci_run_id": 7, "source_stable": True,
                        "proof_kind": "source-test", "producer": "python-test-result-observer",
                        "argv": [sys.executable, ".github/scripts/test_release_workflow.py"], "exit_code": 0,
                        "tests": [{"id": s, "result": "passed"} for s in self.SELECTORS],
                        "source_input_binding": {"format": owner.SOURCE_BINDING, "profile": f["profile"],
                            "payload_name": f["payload"], "manifest_sha256": payload["source_manifest_sha256"]}}
            def build(observation=observed, selected=group, required=req, consumed=payload):
                return owner.build_report(required, job_name=f["job"], job_id=9,
                    selections={"schema": owner.SELECTIONS, "groups": [selected]},
                    observations={"q02-release": observation}, payloads={f["payload"]: consumed})
            yield f, observed, group, req, payload, build

    def test_c_f02_uses_complete_original_release_selection_transport(self):
        with self.fixture() as (f, observed, group, req, payload, build):
            try:
                report = build()
            except ValueError as error:
                self.fail("C-F02 original release observer admission is unavailable: " + str(error))
            self.assertEqual([row["cell"] for row in report["results"]], [self.CELL])
            self.assertEqual(report["results"][0]["executed_population"], 8)
            self.assertFalse(f["counter"].exists(), "Admission must not reexecute either original suite")
            maps = owner.load_json(owner.ROOT / ".github/major-test-selections.json")
            actual, = [g for g in maps["groups"] if g["cells"] == [self.CELL]]
            self.assertEqual(set(actual["selectors"]), set(self.SELECTORS))
            self.assertEqual((actual["observation"], actual["payload_name"], actual["job"]),
                             ("q02-release", f["payload"], f["job"]))
            self.assertEqual(owner.load_json(owner.ROOT / ".github/major-qualification-policy.json")
                             ["cell_job_bindings"][self.CELL], f["job"])

    def test_c_f02_refuses_incomplete_foreign_source_profile_entrypoint_and_named_results(self):
        with self.fixture() as (f, observed, group, req, payload, build):
            for selector in self.SELECTORS:
                for state in ("missing", "skipped", "failed", "duplicate", "reduced-map"):
                    o, g = copy.deepcopy(observed), copy.deepcopy(group)
                    row = next(t for t in o["tests"] if t["id"] == selector)
                    if state == "missing": o["tests"].remove(row)
                    elif state == "duplicate": o["tests"].append(dict(row))
                    elif state == "reduced-map": g["selectors"].remove(selector)
                    else: row["result"] = state
                    with self.subTest(selector=selector, state=state), self.assertRaises(ValueError): build(o, g)
            for mutation in ("source", "run", "manifest", "profile", "script", "filtered", "extra-map", "foreign-cell", "payload", "job"):
                o, g, q, p = copy.deepcopy(observed), copy.deepcopy(group), copy.deepcopy(req), copy.deepcopy(payload)
                if mutation == "source": o["source_commit"] = "f" * 40
                elif mutation == "run": o["ci_run_id"] = 8
                elif mutation == "manifest": p["source_manifest_sha256"] = "0" * 64
                elif mutation == "profile": o["source_input_binding"]["profile"] = owner.SOURCE_PROFILE
                elif mutation == "script": o["argv"][-1] = ".github/scripts/test_major_readiness.py"
                elif mutation == "filtered": o["argv"].append("SourceSelectionTest")
                elif mutation == "extra-map": g["selectors"].append("python:foreign.py:unexecuted")
                elif mutation == "foreign-cell": g["cells"] = ["disposition:findings:C-F04"]; q.update(cells=g["cells"], cell_jobs=dict.fromkeys(g["cells"], f["job"]))
                elif mutation == "payload": g["payload_name"] = "foreign"
                elif mutation == "job": g["job"] = "foreign"
                with self.subTest(mutation=mutation), self.assertRaises(ValueError): build(o, g, q, p)
            extra = f["repo"] / "core/pysrc/unbound_finding_helper.py"
            extra.write_text("# inert namespace control\n")
            with self.assertRaises(ValueError): owner.prepare_source_payload(f["repo"], f["base"] / "refused", f["job"], f["profile"])



class SingleOwnerPythonFindingProfileTests(unittest.TestCase):
    """Inert source/report fixture assertions; never executes the represented owners."""
    EXPECTED = {'disposition:findings:HOOK-F01': {'profile': 'hooks-single-owner-findings-v1',
                                   'script': '.github/scripts/test_prompt_submit.py',
                                   'observation': 'finite-hookf01',
                                   'selectors': ['python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_arbiter_dangerous_arbiter_redelivers_arbiter_claude',
                                                 'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_ops_arbiter_ops_redelivers_ops_claude',
                                                 'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_arbiter_dangerous_arbiter_redelivers_arbiter_codex',
                                                 'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_ops_arbiter_ops_redelivers_ops_codex',
                                                 'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_unchanged_mode_and_repeated_same_mode_token_do_not_repeat_persona',
                                                 'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_round_trip_without_an_ordinary_prompt_between_is_not_a_transition',
                                                 'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_compaction_redelivers_the_current_mode_once',
                                                 'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_new_session_gets_its_own_delivery',
                                                 'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_failed_audit_then_recovery_delivers_the_eventual_effective_persona',
                                                 'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_failed_delivery_record_write_does_not_suppress_return_persona',
                                                 'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_double_denied_delivery_record_update_reports_remaining_limit',
                                                 'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_unreadable_delivery_record_fails_toward_redelivery',
                                                 'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_legacy_modeinject_marker_does_not_suppress_delivery'],
                                   'scope': 'Actual prompt/mode persona revisit, no-op, generation/session '
                                            'and storage-failure fixture behavior; no live host or universal '
                                            'double-denial redelivery.'},
 'disposition:findings:HOOK-F03': {'profile': 'hooks-single-owner-findings-v1',
                                   'script': '.github/scripts/test_pi_payload_identity.py',
                                   'observation': 'finite-hookf03',
                                   'selectors': ['python:.github/scripts/test_pi_payload_identity.py:__main__.PiPayloadIdentityTest.test_real_scoped_package_and_host_agree_without_a_probe',
                                                 'python:.github/scripts/test_pi_payload_identity.py:__main__.PiPayloadIdentityTest.test_missing_bare_foreign_prefix_and_wrong_type_identity_refuse',
                                                 'python:.github/scripts/test_pi_payload_identity.py:__main__.PiPayloadIdentityTest.test_discovery_must_be_the_exact_single_extension_and_skills',
                                                 'python:.github/scripts/test_pi_payload_identity.py:__main__.PiPayloadIdentityTest.test_malformed_manifest_refuses_and_missing_core_stays_independent'],
                                   'scope': 'Actual check_payload predicate and actual PiHost/package '
                                            'identity on owned files only; no doctor.main, native/npm, host '
                                            'probe or installed health.'},
 'disposition:findings:C-F05': {'profile': 'impact-single-owner-findings-v1',
                                'script': '.github/scripts/test_ci_impact.py',
                                'observation': 'finite-cf05',
                                'selectors': ['python:.github/scripts/test_ci_impact.py:__main__.WorkflowContractTest.test_docs_pull_request_selection_covers_every_push_input',
                                              'python:.github/scripts/test_ci_impact.py:__main__.WorkflowContractTest.test_docs_validation_triggers_never_grant_deploy'],
                                'scope': 'Actual workflow input/event and deploy-authority declaration '
                                         'controls; no Pages deployment.'},
 'disposition:findings:C-F06': {'profile': 'hooks-single-owner-findings-v1',
                                'script': '.github/scripts/test_verdictlib.py',
                                'observation': 'finite-cf06',
                                'selectors': ['python:.github/scripts/test_verdictlib.py:__main__.SourceIdentityTest.test_recovery_checkout_is_distinct_from_later_workflow_event',
                                              'python:.github/scripts/test_verdictlib.py:__main__.SourceIdentityTest.test_unavailable_checkout_is_not_replaced_by_event_identity',
                                              'python:.github/scripts/test_verdictlib.py:__main__.RequiredAggregationTest.test_only_affirmative_evidence_satisfies_a_required_check',
                                              'python:.github/scripts/test_verdictlib.py:__main__.RequiredAggregationTest.test_missing_duplicate_or_other_source_evidence_is_not_a_pass',
                                              'python:.github/scripts/test_verdictlib.py:__main__.RequiredAggregationTest.test_not_applicable_needs_a_declaration_and_evidence',
                                              'python:.github/scripts/test_verdictlib.py:__main__.RequiredAggregationTest.test_ordinary_consumers_declare_their_own_accepted_outcomes',
                                              'python:.github/scripts/test_verdictlib.py:__main__.RequiredAggregationTest.test_malformed_observations_are_refused',
                                              'python:.github/scripts/test_verdictlib.py:__main__.CheckerObservationTest.test_branch_protection_forbidden_read_is_unavailable_not_verified',
                                              'python:.github/scripts/test_verdictlib.py:__main__.CheckerObservationTest.test_branch_protection_without_token_is_skipped',
                                              'python:.github/scripts/test_verdictlib.py:__main__.CheckerObservationTest.test_branch_protection_violation_and_compliance',
                                              'python:.github/scripts/test_verdictlib.py:__main__.CheckerObservationTest.test_tag_audit_without_token_is_skipped_and_unavailable_api_is_unavailable',
                                              'python:.github/scripts/test_verdictlib.py:__main__.CheckerObservationTest.test_optional_codex_host_absent_is_skipped_required_absent_is_unavailable',
                                              'python:.github/scripts/test_verdictlib.py:__main__.CheckerObservationTest.test_payload_gate_records_first_introduction_and_invalid_base_distinctly'],
                                'scope': 'Typed injected outcomes and required-affirmative/source/refusal '
                                         'contract; no actual branch/tag/Codex protection observation.'},
 'disposition:findings:C-F07': {'profile': 'impact-single-owner-findings-v1',
                                'script': '.github/scripts/test_payload_version_gate.py',
                                'observation': 'finite-cf07',
                                'selectors': ['python:.github/scripts/test_payload_version_gate.py:__main__.TestTheGateStillAllowsWhatItShould.test_a_first_introduction_passes',
                                              'python:.github/scripts/test_payload_version_gate.py:__main__.TestTheGateRefusesTheOtherDirections.test_an_unresolvable_base_fails_rather_than_passing',
                                              'python:.github/scripts/test_payload_version_gate.py:__main__.TestTheGateRefusesTheOtherDirections.test_an_invalid_BASE_manifest_is_not_first_introduction',
                                              'python:.github/scripts/test_payload_version_gate.py:__main__.TestTheGateStillAllowsWhatItShould.test_advancing_the_version_passes',
                                              'python:.github/scripts/test_payload_version_gate.py:__main__.TestTheGateStillAllowsWhatItShould.test_no_payload_change_passes_without_a_bump'],
                                'scope': 'Owned Git base absent/valid/invalid/unresolved manifest '
                                         'distinction; no release qualification.'},
 'disposition:findings:T-F02': {'profile': 'hooks-single-owner-findings-v1',
                                'script': 'tools/test_measurement_contracts.py',
                                'observation': 'finite-tf02',
                                'selectors': ['python:tools/test_measurement_contracts.py:__main__.MeasurementContracts.test_smarts_lens_keywords_are_not_material_alternatives',
                                              'python:tools/test_measurement_contracts.py:__main__.MeasurementContracts.test_failed_smarts_child_cannot_pass_from_plausible_output'],
                                'scope': 'Actual SMARTS predicate/producer-refusal on inert output fixtures; '
                                         'model reasoning quality and whole T01 remain unassessed.'}}

    EXPECTED.update({
        'disposition:findings:C-F08': {
            'id': 'finite-c-f08',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_boundedproc.py',
            'observation': 'finite-bounded-reader',
            'selectors': [
                'python:.github/scripts/test_boundedproc.py:__main__.CodexHostCommandDeadlineTest.test_hanging_codex_command_fails_with_timeout_and_containment',
                'python:.github/scripts/test_boundedproc.py:__main__.CodexHostCommandDeadlineTest.test_a_timed_out_marketplace_add_is_a_recorded_failure',
                'python:.github/scripts/test_boundedproc.py:__main__.PiBenchmarkReadinessDeadlineTest.test_no_ready_line_is_a_bounded_failure_with_containment',
                'python:.github/scripts/test_boundedproc.py:__main__.PiBenchmarkReadinessDeadlineTest.test_partial_ready_line_is_refused',
                'python:.github/scripts/test_boundedproc.py:__main__.PiBenchmarkReadinessDeadlineTest.test_immediate_exit_is_refused',
                'python:.github/scripts/test_boundedproc.py:__main__.PiBenchmarkReadinessDeadlineTest.test_hang_after_ready_is_bounded',
                'python:.github/scripts/test_boundedproc.py:__main__.PiBenchmarkReadinessDeadlineTest.test_well_behaved_boundary_completes',
                'python:.github/scripts/test_boundedproc.py:__main__.PiBenchmarkReadinessDeadlineTest.test_partial_early_exit_retains_readiness_failure_when_group_signal_is_denied',
            ],
            'scope': 'Controlled subprocess watchdog outcomes for Codex host commands and the Pi benchmark.',
        },
        'disposition:added_transitions:C36:added-prefetched-completion': {
            'id': 'finite-added-prefetched-completion',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_boundedproc.py',
            'observation': 'finite-bounded-reader',
            'selectors': [
                'python:.github/scripts/test_boundedproc.py:__main__.ReadinessWaitTest.test_binary_readiness_preserves_completion_from_one_write',
                'python:.github/scripts/test_boundedproc.py:__main__.ReadinessWaitTest.test_binary_early_eof_reports_closed_and_finishes_empty',
                'python:.github/scripts/test_boundedproc.py:__main__.PiBenchmarkReadinessDeadlineTest.test_well_behaved_boundary_completes',
            ],
            'scope': 'Owned stdout keeps prefetched completion and observes actual early EOF.',
        },
        'disposition:added_transitions:C36:added-stdin-eof': {
            'id': 'finite-added-stdin-eof',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_boundedproc.py',
            'observation': 'finite-bounded-reader',
            'selectors': [
                'python:.github/scripts/test_boundedproc.py:__main__.ReadinessWaitTest.test_communicate_without_input_closes_stdin_after_readiness',
            ],
            'scope': 'Communicate without input closes the owned child stdin and receives completion.',
        },
        'disposition:added_transitions:C36:added-input-once': {
            'id': 'finite-added-input-once',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_boundedproc.py',
            'observation': 'finite-bounded-reader',
            'selectors': [
                'python:.github/scripts/test_boundedproc.py:__main__.ReadinessWaitTest.test_communicate_sends_text_or_binary_input_after_readiness',
                'python:.github/scripts/test_boundedproc.py:__main__.ReadinessWaitTest.test_communicate_timeout_retry_sends_the_original_payload_once',
            ],
            'scope': 'Owned child receives exact text and binary input once across a timed-out write.',
        },
        'disposition:added_transitions:C36:added-input-timeout': {
            'id': 'finite-added-input-timeout',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_boundedproc.py',
            'observation': 'finite-bounded-reader',
            'selectors': [
                'python:.github/scripts/test_boundedproc.py:__main__.ReadinessWaitTest.test_unread_stdin_stays_bounded_and_cleanup_settles_writer',
            ],
            'scope': 'Unread stdin stays bounded and owned cleanup settles the writer.',
        },
        'disposition:added_transitions:C36:added-cleanup-denied': {
            'id': 'finite-added-cleanup-denied',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_boundedproc.py',
            'observation': 'finite-bounded-reader',
            'selectors': [
                'python:.github/scripts/test_boundedproc.py:__main__.PiBenchmarkReadinessDeadlineTest.test_partial_early_exit_retains_readiness_failure_when_group_signal_is_denied',
            ],
            'scope': 'An injected group-signal denial retains the actual child readiness failure.',
        },
    })

    EXPECTED.update({
        'disposition:transitions:S73:01': {
            'id': 'finite-channel-s73-01',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_channel_carries_the_native_payload_under_the_git_subdir_path',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_version_must_match_the_qualified_manifest',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_package_without_native_payload_is_refused',
            ],
            'scope': 'Fixture archive/version/payload admission produces actual deterministic local Git distribution/channel refs; qualified binary contents are synthetic fixture bytes, not real engine qualification.',
        },
        'disposition:transitions:S73:02': {
            'id': 'finite-channel-s73-02',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_channel_carries_the_native_payload_under_the_git_subdir_path',
            ],
            'scope': 'Absent immutable ref is created and exact remote tag equals returned distribution commit.',
        },
        'disposition:transitions:S73:03': {
            'id': 'finite-channel-s73-03',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_rerun_with_identical_inputs_is_a_no_op',
            ],
            'scope': 'Repeated same input observes existing distribution and reuses channel commit without duplicate promotion.',
        },
        'disposition:transitions:S73:04': {
            'id': 'finite-channel-s73-04',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_same_version_with_different_bytes_is_refused',
            ],
            'scope': 'Existing same-version identity refuses changed archive bytes.',
        },
        'disposition:transitions:S73:05': {
            'id': 'finite-channel-s73-05',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_channel_refuses_to_roll_back',
            ],
            'scope': 'Older version refuses before moving local remote channel.',
        },
        'disposition:transitions:S73:06': {
            'id': 'finite-channel-s73-06',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_rerun_with_identical_inputs_is_a_no_op',
            ],
            'scope': 'Same tree reuses current marketplace commit and previous commit identity.',
        },
        'disposition:transitions:S73:07': {
            'id': 'finite-channel-s73-07',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_newer_version_advances_as_a_descendant',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_unknown_current_channel_version_cannot_advance',
            ],
            'scope': 'Changed tree advances descendant; unreadable current version now refuses with channel unchanged.',
        },
        'disposition:transitions:S73:08': {
            'id': 'finite-channel-s73-08',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_channel_carries_the_native_payload_under_the_git_subdir_path',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_push_response_loss_recovers_only_by_readback_without_repush',
            ],
            'scope': 'Tag publication/readback uses expected deterministic commit; response-loss path attempts immutable push once.',
        },
        'disposition:transitions:S73:09': {
            'id': 'finite-channel-s73-09',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_newer_version_advances_as_a_descendant',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_push_response_loss_recovers_only_by_readback_without_repush',
            ],
            'scope': 'Channel update goes through current lease/readback helper, advances descendant, and response-loss observation does not repush.',
        },
        'disposition:transitions:S73:10': {
            'id': 'finite-channel-s73-10',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_push_response_loss_recovers_only_by_readback_without_repush',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.UncertainPushTests.test_conflicting_or_unobservable_readback_never_retries',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_readback_finds_the_promotion_after_the_channel_moved_on',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_readback_never_pushes',
            ],
            'scope': 'Uncertain push may succeed only by exact observed remote identity; unknown/conflict refuses after one attempt; explicit recovery reads history without pushing.',
        },
        'disposition:transitions:S74:03': {
            'id': 'finite-channel-s74-03',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.CodexGitChannelTests.test_default_git_mode_pins_the_channel_to_the_immutable_dist_tag',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.CodexGitChannelTests.test_git_mode_needs_no_npm_package',
            ],
            'scope': 'Codex first call creates immutable tag, second channel promotion names that exact tag/commit without acquiring npm.',
        },
        'disposition:transitions:S74:04': {
            'id': 'finite-channel-s74-04',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.CodexGitChannelTests.test_default_git_mode_pins_the_channel_to_the_immutable_dist_tag',
            ],
            'scope': 'Actual successful channel advance uses independently precreated immutable distribution tag; missing-tag/expected-head adversarial branches not independently claimed.',
        },
        'disposition:transitions:S74:08': {
            'id': 'finite-channel-s74-08',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.CodexGitChannelTests.test_default_git_mode_pins_the_channel_to_the_immutable_dist_tag',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.CodexGitChannelTests.test_readback_finds_the_channel_promotion_after_a_newer_release',
            ],
            'scope': 'Actual local leased channel updates name immutable source and preserve recoverable prior distribution ancestry.',
        },
        'disposition:transitions:S74:09': {
            'id': 'finite-channel-s74-09',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.UncertainPushTests.test_conflicting_or_unobservable_readback_never_retries',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.CodexGitChannelTests.test_readback_finds_the_channel_promotion_after_a_newer_release',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.CodexGitChannelTests.test_readback_refuses_a_distribution_tag_the_channel_never_promoted',
            ],
            'scope': 'Shared exact push/readback helper refuses conflicting/unobservable remote without retry; Codex recovery reads old completed promotion and rejects an unpromoted tag.',
        },
        'disposition:findings:SF15': {
            'id': 'finite-channel-sf15',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_marketplace_git_channels.py',
            'observation': 'finite-git-channel',
            'selectors': [
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_push_response_loss_recovers_only_by_readback_without_repush',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.UncertainPushTests.test_conflicting_or_unobservable_readback_never_retries',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_unknown_current_channel_version_cannot_advance',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.CodexGitChannelTests.test_default_git_mode_pins_the_channel_to_the_immutable_dist_tag',
                'python:.github/scripts/test_marketplace_git_channels.py:__main__.ClaudeChannelTests.test_readback_never_pushes',
            ],
            'scope': 'Preserve intentional Claude tag+channel vs Codex preexisting-tag channel protocol; uncertain responses cannot authorize blind mutation retries; unknown current Claude version refuses.',
        },
    })

    EXPECTED.update({
        'disposition:findings:W-F01': {
            'id': 'finite-scoped-conflict-wf01',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_routing_and_cleanup_surface.py',
            'observation': 'finite-scoped-conflict',
            'selectors': [
                'python:.github/scripts/test_routing_and_cleanup_surface.py:__main__.TestDependentConflictScope.test_conflict_keeps_sources_and_records_affected_dependencies',
                'python:.github/scripts/test_routing_and_cleanup_surface.py:__main__.TestDependentConflictScope.test_independent_work_continues_but_global_stops_remain',
                'python:.github/scripts/test_routing_and_cleanup_surface.py:__main__.TestDependentConflictScope.test_sprint_and_context_refresh_propagate_the_same_scope',
            ],
            'scope': 'Original source instruction contract for the dependent-conflict finding across canonical and rendered host surfaces.',
        },
        'disposition:transitions:WF-02:01': {
            'id': 'finite-scoped-conflict-wf02-01',
            'profile': 'hooks-single-owner-findings-v1',
            'script': '.github/scripts/test_routing_and_cleanup_surface.py',
            'observation': 'finite-scoped-conflict',
            'selectors': [
                'python:.github/scripts/test_routing_and_cleanup_surface.py:__main__.TestDependentConflictScope.test_conflict_keeps_sources_and_records_affected_dependencies',
                'python:.github/scripts/test_routing_and_cleanup_surface.py:__main__.TestDependentConflictScope.test_independent_work_continues_but_global_stops_remain',
                'python:.github/scripts/test_routing_and_cleanup_surface.py:__main__.TestDependentConflictScope.test_sprint_and_context_refresh_propagate_the_same_scope',
            ],
            'scope': 'Original dependent-conflict transition instructions for explicit global stops and independent authorized continuation.',
        },
    })

    def test_a_six_existing_single_owner_findings_have_closed_original_profiles(self):
        expected_jobs = {
            "hooks-single-owner-findings-v1": "[CHECK] | [CORE] | Hook contract  <os: windows-latest · partition: contracts>",
            "impact-single-owner-findings-v1": "[CHECK] | [REPO] | Impact planner contract",
        }
        for profile, job in expected_jobs.items():
            with self.subTest(profile=profile):
                try:
                    spec = owner.source_profile(profile)
                except ValueError as error:
                    self.fail("actual source-profile boundary lacks the original single-owner finding route: " + str(error))
                self.assertEqual(spec["job"], job)
                self.assertTrue(spec["paths"])
                self.assertTrue(all(row["script"] in spec["paths"] for row in self.EXPECTED.values() if row["profile"] == profile))

    def fixture(self, cell):
        recipe=self.EXPECTED[cell];spec=owner.source_profile(recipe['profile'])
        req={'source_commit':'a'*40,'source_tree':'b'*40,'ci_run_id':7,
             'cells':[cell],'cell_jobs':{cell:spec['job']}}
        rows=[{'path':p,'sha256':'c'*64,'bytes':1,'git_mode':'100644'} for p in sorted(spec['paths'])]
        manifest={'format':owner.SOURCE_FORMAT,'profile':recipe['profile'],'source_commit':req['source_commit'],
                  'source_tree':req['source_tree'],'workflow':'.github/workflows/ci.yml','ci_run_id':7,
                  'producer_job_name':spec['job'],'members':rows}
        payload={'artifact_id':8,'archive_sha256':'d'*64,'source_manifest_sha256':'e'*64,
                 'source_upload_job_id':9,'documents':{owner.SOURCE_MANIFEST:manifest},
                 'members':[{'path':r['path'],'sha256':r['sha256']} for r in rows]+[
                     {'path':owner.SOURCE_MANIFEST,'sha256':'e'*64}]}
        observed={'format':owner.OBSERVATION,'source_commit':req['source_commit'],'source_tree':req['source_tree'],
                  'ci_run_id':7,'source_stable':True,'proof_kind':'source-test',
                  'producer':'python-test-result-observer','argv':['python',recipe['script']],'exit_code':0,
                  'tests':[{'id':x,'result':'passed'} for x in recipe['selectors']],
                  'source_input_binding':{'format':owner.SOURCE_BINDING,'profile':recipe['profile'],
                     'payload_name':spec['payload'],'manifest_sha256':'e'*64}}
        group={'id':recipe.get('id', recipe['observation']),'job':spec['job'],'payload_name':spec['payload'],
               'observation':recipe['observation'],'proof_kind':'source-test','cells':[cell],
               'selectors':list(recipe['selectors']),'scope':recipe['scope']}
        def build(o=observed,g=group,r=req,p=payload,job=spec['job']):
            return owner.build_report(r,job_name=job,job_id=9,
                selections={'schema':owner.SELECTIONS,'groups':[g]},
                observations={recipe['observation']:o},payloads={spec['payload']:p})
        return recipe,spec,req,payload,observed,group,build

    def test_b_complete_original_finite_compositions_and_policy_are_consumed(self):
        selections=owner.load_json(owner.ROOT/'.github/major-test-selections.json')
        policy=owner.load_json(owner.ROOT/'.github/major-qualification-policy.json')
        for cell in self.EXPECTED:
            recipe,spec,req,payload,observed,group,build=self.fixture(cell)
            with self.subTest(cell=cell):
                report=build();result,=report['results']
                self.assertEqual(result['cell'],cell)
                self.assertEqual(result['executed_population'],len(recipe['selectors']))
                self.assertEqual(result['selected_population'],len(recipe['selectors']))
                self.assertEqual(report['schema'],'codearbiter-major-qualification/2')
                actual,=[g for g in selections['groups'] if g['cells']==[cell]]
                self.assertEqual(actual,group)
                self.assertEqual(policy['cell_job_bindings'][cell],spec['job'])

    def test_release_library_rows_require_the_exact_original_classifier_assertions(self):
        history = owner.ROOT / ('docs/state-contracts-major/execution/evidence/'
                                'release-bindings-b7a75fca/classifier-tested.json')
        proof = owner.load_json(history)
        binding = 'finite-release-library'
        script = '.github/scripts/test_release_lib.py'
        expected = {
            cell: [f"python:{script}:__main__." + name.removeprefix('test_release_lib.')
                   for name in proof['per_disposition_assertions'][cell.split(':', 2)[2]]]
            for cell in proof['disposition_ids']
        }
        self.assertEqual(len(expected), 11)
        selections = owner.load_json(owner.ROOT / '.github/major-test-selections.json')
        policy = owner.load_json(owner.ROOT / '.github/major-qualification-policy.json')
        groups = [group for group in selections['groups'] if group['observation'] == binding]
        self.assertEqual({group['cells'][0]: group['selectors'] for group in groups}, expected)
        _, spec, req, payload, observed, _, _ = self.fixture('disposition:findings:T-F02')
        self.assertLessEqual(set(proof['inputs']), spec['paths'])
        self.assertEqual({cell: policy['cell_job_bindings'][cell] for cell in expected},
                         dict.fromkeys(expected, spec['job']))
        req.update(cells=sorted(expected), cell_jobs=dict.fromkeys(expected, spec['job']))
        selectors = sorted({selector for names in expected.values() for selector in names})
        self.assertEqual(len(selectors), 23)
        observed.update(argv=['python', script], tests=[{'id': name, 'result': 'passed'} for name in selectors])

        def build():
            return owner.build_report(req, job_name=spec['job'], job_id=9,
                selections={'schema': owner.SELECTIONS, 'groups': groups},
                observations={binding: observed}, payloads={spec['payload']: payload})

        report = build()
        self.assertEqual(len(report['payloads']), 1)
        self.assertEqual({row['cell']: row['executed_population'] for row in report['results']},
                         {cell: len(names) for cell, names in expected.items()})
        observed['tests'].pop()
        with self.assertRaisesRegex(ValueError, 'selected named test missing'):
            build()

    def test_release_receipt_finding_requires_the_exact_original_planner_assertions(self):
        history = owner.ROOT / ('docs/state-contracts-major/execution/evidence/'
                                'release-receipt-current-74057')
        proof = owner.load_json(history / 'c-f01-tested.json')
        assertions = owner.load_json(history / 'assertion-map.json')['finding']
        cell, = proof['disposition_ids']
        script = '.github/scripts/test_release_target.py'
        key = 'finite-release-receipt'
        selectors = [f'python:{script}:__main__.' + name.removeprefix('test_release_target.')
                     for name in assertions['named_assertion_ids']]
        self.assertEqual(len(set(selectors)), 11)
        selections = owner.load_json(owner.ROOT / '.github/major-test-selections.json')
        _, spec, req, payload, observed, _, _ = self.fixture('disposition:findings:T-F02')
        self.assertFalse(set(proof['inputs']).difference(spec['paths']))
        self.assertEqual(spec['paths'].difference(owner._HOOK_SINGLE_OWNER_PATHS), {
            '.github/actions/publish-target/action.yml',
            'docs/state-contracts-major/contracts/transition-coverage.json',
        })
        policy = owner.load_json(owner.ROOT / '.github/major-qualification-policy.json')
        self.assertEqual(policy['cell_job_bindings'][cell], spec['job'])
        group, = [item for item in selections['groups'] if item['cells'] == [cell]]
        self.assertEqual(group['selectors'], selectors)
        self.assertEqual(group['observation'], key)
        req.update(cells=[cell], cell_jobs={cell: spec['job']})
        observed.update(argv=['python', script], tests=[{'id': name, 'result': 'passed'} for name in selectors])

        def build():
            return owner.build_report(req, job_name=spec['job'], job_id=9,
                selections={'schema': owner.SELECTIONS, 'groups': [group]},
                observations={key: observed}, payloads={spec['payload']: payload})

        row, = build()['results']
        self.assertEqual((row['cell'], row['executed_population']), (cell, 11))
        observed['tests'].pop()
        with self.assertRaisesRegex(ValueError, 'selected named test missing'):
            build()

    def test_native_manifest_cell_requires_the_four_original_python_outcomes(self):
        history = owner.ROOT / 'docs/state-contracts-major/execution/evidence/packaging-local-94b/pure-manifest.json'
        receipt = owner.load_json(history)
        cell, = receipt['disposition_ids']
        script = '.github/scripts/test_artifact_manifest_contract.py'
        selectors = [f'python:{script}:' + row['id'] for row in receipt['original_named_assertions']]
        selection = owner.load_json(owner.ROOT / '.github/major-test-selections.json')
        group, = [group for group in selection['groups'] if group['cells'] == [cell]]
        self.assertEqual(group['selectors'], selectors)
        self.assertEqual(len(selectors), 4)
        _, spec, req, payload, observed, _, _ = self.fixture('disposition:findings:T-F02')
        self.assertIn('.github/fixtures/artifact-release-manifest.json', spec['paths'])
        req.update(cells=[cell], cell_jobs={cell: spec['job']})
        observed.update(argv=['python', script], tests=[{'id': name, 'result': 'passed'} for name in selectors])

        def build():
            return owner.build_report(req, job_name=spec['job'], job_id=9,
                selections={'schema': owner.SELECTIONS, 'groups': [group]},
                observations={'finite-native-manifest': observed}, payloads={spec['payload']: payload})

        row, = build()['results']
        self.assertEqual((row['cell'], row['executed_population']), (cell, 4))
        observed['tests'].pop()
        with self.assertRaisesRegex(ValueError, 'selected named test missing'):
            build()

    def test_scoped_conflict_cells_share_one_original_capture(self):
        self.assert_shared_original_capture("finite-scoped-conflict", 2, 3)
        retained = owner.load_json(owner.ROOT / "docs/state-contracts-major/execution/evidence/wf01-scoped-conflict-bf2f4b41/tested.json")
        profile = owner.source_profile("hooks-single-owner-findings-v1")
        self.assertLessEqual(set(retained["inputs"]), profile["paths"])
        for row in retained["per_cell_assertion_mapping"]:
            expected = self.EXPECTED[row["cell"]]
            script = expected["script"]
            original = [f"python:{script}:__main__.{case.split('.', 1)[1]}"
                        for case in row["observed_named_cases"]]
            self.assertEqual(expected["selectors"], original)

    def test_bounded_reader_cells_share_one_original_capture(self):
        self.assert_shared_original_capture("finite-bounded-reader", 6, 14)

    def test_git_channel_cells_share_one_original_capture(self):
        spec = owner.source_profile("hooks-single-owner-findings-v1")
        self.assertIn(".claude-plugin/marketplace.json", spec["paths"])
        self.assert_shared_original_capture("finite-git-channel", 15, 16)

    def test_measurement_and_illustration_cells_use_one_original_contract_observation(self):
        history = owner.ROOT / 'docs/state-contracts-major/execution/evidence'
        expected = {}
        for path in ('packaging-remaining-40b9/benchmark-empty-finding.json',
                     'tools-local-af5f/measurement-verdict-controls.json',
                     'tools-local-af5f/illustration-failure-boundaries.json',
                     'packaging-remaining-40b9/illustration-failure-finding.json'):
            receipt = owner.load_json(history / path)
            for cell in receipt['disposition_ids']:
                expected[cell] = ['python:tools/test_measurement_contracts.py:' + name
                                  for name in receipt['named_assertions']]
        self.assertEqual(len(expected), 8)
        original = 'disposition:findings:T-F02'
        _, spec, req, payload, observed, group, _ = self.fixture(original)
        expected[original] = group['selectors']
        selection = owner.load_json(owner.ROOT / '.github/major-test-selections.json')
        policy = owner.load_json(owner.ROOT / '.github/major-qualification-policy.json')
        groups = [g for g in selection['groups'] if g['observation'] == 'finite-tf02']
        self.assertEqual(len(groups), 9)
        self.assertEqual({g['cells'][0]: g['selectors'] for g in groups}, expected)
        self.assertEqual({c: policy['cell_job_bindings'][c] for c in expected}, dict.fromkeys(expected, spec['job']))
        req.update(cells=sorted(expected), cell_jobs=dict.fromkeys(expected, spec['job']))
        selectors = sorted({name for names in expected.values() for name in names})
        self.assertEqual(len(selectors), 7)
        observed['tests'] = [{'id': name, 'result': 'passed'} for name in selectors]

        def build(selected=groups, outcomes=observed):
            return owner.build_report(req, job_name=spec['job'], job_id=9,
                selections={'schema': owner.SELECTIONS, 'groups': selected},
                observations={'finite-tf02': outcomes}, payloads={spec['payload']: payload})

        report = build()
        self.assertEqual(len(report['payloads']), 1)
        self.assertEqual({row['cell']: row['executed_population'] for row in report['results']},
                         {cell: len(names) for cell, names in expected.items()})
        for name in selectors:
            outcomes = {**observed, 'tests': [row for row in observed['tests'] if row['id'] != name]}
            with self.subTest(selector=name), self.assertRaisesRegex(ValueError, 'selected named test missing'):
                build(outcomes=outcomes)
        reduced = copy.deepcopy(groups)
        next(g for g in reduced if g['cells'] == ['disposition:findings:T-F01'])['selectors'].pop()
        with self.assertRaisesRegex(ValueError, 'complete exact finite finding'):
            build(selected=reduced)

    def assert_shared_original_capture(self, key, cell_count, selector_count):
        cells = [cell for cell, recipe in self.EXPECTED.items() if recipe["observation"] == key]
        fixtures = [self.fixture(cell) for cell in cells]
        _, spec, req, payload, observed, _, _ = fixtures[0]
        groups = [fixture[5] for fixture in fixtures]
        req.update(cells=cells, cell_jobs=dict.fromkeys(cells, spec["job"]))
        selectors = {selector for group in groups for selector in group["selectors"]}
        self.assertEqual(len(cells), cell_count)
        self.assertEqual(len(selectors), selector_count)
        observed["tests"] = [{"id": selector, "result": "passed"} for selector in sorted(selectors)]

        def build():
            return owner.build_report(req, job_name=spec["job"], job_id=9,
                selections={"schema": owner.SELECTIONS, "groups": groups},
                observations={key: observed}, payloads={spec["payload"]: payload})

        report = build()
        self.assertEqual(len(report["payloads"]), 1)
        self.assertEqual({row["cell"]: row["executed_population"] for row in report["results"]},
                         {group["cells"][0]: len(group["selectors"]) for group in groups})
        observed["tests"].pop()
        with self.assertRaisesRegex(ValueError, "selected named test missing"):
            build()

    def test_c_every_required_named_case_and_exact_single_owner_group_is_mandatory(self):
        for cell in self.EXPECTED:
            recipe,spec,req,payload,observed,group,build=self.fixture(cell)
            for selector in recipe['selectors']:
                for state in ('missing','duplicate','failed','skipped','reduced-map'):
                    o,g=copy.deepcopy(observed),copy.deepcopy(group)
                    row=next(r for r in o['tests'] if r['id']==selector)
                    if state=='missing':o['tests'].remove(row)
                    elif state=='duplicate':o['tests'].append(dict(row))
                    elif state=='reduced-map':g['selectors'].remove(selector)
                    else:row['result']=state
                    with self.subTest(cell=cell,selector=selector,state=state),self.assertRaises(ValueError):build(o,g)

    def test_d_original_source_script_profile_job_and_payload_never_cross_authority(self):
        for cell in self.EXPECTED:
            recipe,spec,req,payload,observed,group,build=self.fixture(cell)
            for mutation in ('source','tree','run','unstable','exit','filtered','script','profile','payload','manifest',
                             'uploader','foreign-cell','composite','extra-selector','wrong-job','missing-member'):
                o,g,r,p=map(copy.deepcopy,(observed,group,req,payload))
                if mutation=='source':o['source_commit']='f'*40
                elif mutation=='tree':o['source_tree']='f'*40
                elif mutation=='run':o['ci_run_id']=8
                elif mutation=='unstable':o['source_stable']=False
                elif mutation=='exit':o['exit_code']=1
                elif mutation=='filtered':o['argv'].append('-k')
                elif mutation=='script':o['argv'][-1]='.github/scripts/test_major_readiness.py'
                elif mutation=='profile':o['source_input_binding']['profile']=owner.SOURCE_PROFILE
                elif mutation=='payload':g['payload_name']='foreign'
                elif mutation=='manifest':p['source_manifest_sha256']='f'*64
                elif mutation=='uploader':p['source_upload_job_id']=10
                elif mutation=='foreign-cell':g['cells']=['disposition:findings:HOOK-F02'];r.update(cells=g['cells'],cell_jobs=dict.fromkeys(g['cells'],spec['job']))
                elif mutation=='composite':g['cells'].append('task:HW-27');r.update(cells=g['cells'],cell_jobs=dict.fromkeys(g['cells'],spec['job']))
                elif mutation=='extra-selector':g['selectors'].append('python:foreign.py:unexecuted')
                elif mutation=='wrong-job':g['job']='foreign'
                else:p['members'].pop(0)
                with self.subTest(cell=cell,mutation=mutation),self.assertRaises(ValueError):build(o,g,r,p)

    def test_e_nested_refusal_examples_are_retained_but_grant_no_additional_credit(self):
        recipe,spec,req,payload,observed,group,build=self.fixture('disposition:findings:C-F05')
        nested='python:'+recipe['script']+':__main__.OwnedNestedExample.test_expected_refusal'
        observed['tests'].extend([{'id':nested,'result':'failed'},{'id':nested,'result':'skipped'}])
        result,=build()['results']
        self.assertEqual(result['executed_population'],len(recipe['selectors']))
        self.assertEqual(len(observed['tests']),len(recipe['selectors'])+2)
        observed['exit_code']=1
        with self.assertRaises(ValueError):build()

    def test_f_filtered_and_foreign_observer_calls_refuse_before_any_original_execution(self):
        with tempfile.TemporaryDirectory(prefix='ca-six-profile-refusal-') as td:
            base=Path(td).resolve();script='.github/scripts/test_prompt_submit.py';path=base/script
            path.parent.mkdir(parents=True);path.write_text('# inert boundary only\n')
            other=base/'.github/scripts/test_major_readiness.py';other.write_text('# inert foreign boundary\n')
            with mock.patch.object(owner.runpy,'run_path',side_effect=AssertionError('must not execute')):
                for name,args,payload in ((script,['-k','partial'],base/'payload'),(script,[],None),
                                           (other.relative_to(base).as_posix(),[],base/'payload')):
                    with self.subTest(script=name,args=args),self.assertRaises(ValueError):
                        owner.observe_python(base,name,args,base/'absent.json',payload,'hooks-single-owner-findings-v1')
            self.assertFalse((base/'absent.json').exists())

    def test_g_final_reader_authenticates_each_original_upload_after_whole_run_success(self):
        for profile in ('hooks-single-owner-findings-v1','impact-single-owner-findings-v1'):
            cell=next(c for c,r in self.EXPECTED.items() if r['profile']==profile)
            recipe,spec,req,payload,observed,group,build=self.fixture(cell)
            raw=io.BytesIO()
            with zipfile.ZipFile(raw,'w') as archive:archive.writestr('source-member',b'inert')
            content=raw.getvalue();members=owner.readiness.members(content)
            source={'id':8,'name':spec['payload']};artifact={'id':10,'name':'major-qualification-9'}
            job={'id':9,'name':spec['job'],'status':'completed','conclusion':'success'}
            req['required_artifact_names']=[source['name']]
            report={'schema':'codearbiter-major-qualification/2',**{k:req[k] for k in ('source_commit','source_tree','ci_run_id')},'job_id':9,
                'payloads':[{'artifact_id':8,'archive_sha256':owner.readiness.digest(content),'members':members}],
                'results':[{'cell':cell,'result':'PASSED','commands':[{'argv':observed['argv'],'exit_code':0}],
                    'selected_population':1,'executed_population':1,'payload_artifact_id':8}]}
            with mock.patch.object(owner.readiness,'read_artifact_json',return_value=report), \
                 mock.patch.object(owner.readiness,'artifact_bytes',return_value=content), \
                 mock.patch.object(owner.readiness,'validate_upload') as upload:
                owner.readiness.produce(req,[source,artifact],[job,{'id':11,'name':'major readiness producer'}])
                self.assertEqual(upload.call_args_list,[mock.call(job,artifact,'Upload major qualification report'),mock.call(job,source,spec['upload'])])
                for mutation in ('wrong-owner','in-progress','upload-refused'):
                    jobs=[copy.deepcopy(job),{'id':11,'name':'major readiness producer'}];q=copy.deepcopy(req);upload.side_effect=None
                    if mutation=='wrong-owner':jobs[0]['name']='foreign';q['cell_jobs'][cell]='foreign'
                    elif mutation=='in-progress':jobs[0].update(status='in_progress',conclusion=None)
                    else:upload.side_effect=owner.readiness.ReadinessError('original uploader refused')
                    with self.subTest(profile=profile,mutation=mutation),self.assertRaises(owner.readiness.ReadinessError):
                        owner.readiness.produce(q,[source,artifact],jobs)

    def test_h_real_owned_source_payload_and_safe_original_identity_owner_run_once(self):
        profile='hooks-single-owner-findings-v1';spec=owner.source_profile(profile)
        canonical=Path(os.environ.get('CA_HOOKS_CANONICAL_ROOT',owner.ROOT))
        with tempfile.TemporaryDirectory(prefix='ca-single-owner-source-') as td:
            base=Path(td).resolve();repo=base/'repo';repo.mkdir()
            for relative in spec['paths']:
                source=owner.ROOT/relative
                if not source.is_file():source=canonical/relative
                target=repo/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
            git=shutil.which('git');self.assertIsNotNone(git)
            env={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATHEXT','PATH')}
            env.update(HOME=str(base),USERPROFILE=str(base),TEMP=str(base),TMP=str(base),
                GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM='1',GIT_OPTIONAL_LOCKS='0',GIT_TERMINAL_PROMPT='0',
                GIT_AUTHOR_NAME='fixture',GIT_AUTHOR_EMAIL='fixture@invalid',GIT_COMMITTER_NAME='fixture',GIT_COMMITTER_EMAIL='fixture@invalid',
                GITHUB_RUN_ID='7',PYTHONDONTWRITEBYTECODE='1')
            with mock.patch.dict(os.environ,env,clear=True):
                for args in (['init'],['config','core.autocrlf','false'],['add','.'],['-c','commit.gpgsign=false','commit','-qm','source fixture']):
                    run_git_phase([git,'-C',str(repo),*args],phase='init' if args[0] in ('init','config') else 'index' if args[0]=='add' else 'commit',trace_dir=base)
                staged=base/'inputs';owner.prepare_source_payload(repo,staged,spec['job'],profile)
                output=base/'observation.json'
                with (mock.patch.object(sys, "dont_write_bytecode", False),
                      mock.patch.object(owner.runpy, "run_path", wraps=owner.runpy.run_path) as original):
                    self.assertEqual(owner.observe_python(
                        repo, ".github/scripts/test_pi_payload_identity.py", [], output, staged, profile), 0)
                    self.assertEqual(original.call_count, 1)
                    self.assertFalse(sys.dont_write_bytecode)
                observed=owner.load_json(output)
                self.assertEqual({r['id'] for r in observed['tests']},set(self.EXPECTED['disposition:findings:HOOK-F03']['selectors']))
                self.assertTrue(all(r['result']=='passed' for r in observed['tests']))
                archive=io.BytesIO()
                with zipfile.ZipFile(archive,'w') as z:
                    for path in staged.rglob('*'):
                        if path.is_file():z.writestr(path.relative_to(staged).as_posix(),path.read_bytes())
                req={**owner.source_identity(repo,profile),'ci_run_id':7}
                job={'id':9,'name':spec['job'],'status':'in_progress','conclusion':None,
                     'steps':[{'name':spec['upload'],'status':'completed','conclusion':'success'}]}
                with mock.patch.object(owner.readiness,'artifact_bytes',return_value=archive.getvalue()), \
                     mock.patch.object(owner.readiness,'validate_upload',side_effect=AssertionError('producer job has no completed log')):
                    payload=owner.authenticated_payload({'id':8,'name':spec['payload']},req,repo,source_job=job)
                    owner.admit_source_observation(observed,payload,req,spec['job'],9)
                    bad=copy.deepcopy(job);bad['steps'][0]['conclusion']='failure'
                    with self.assertRaises(ValueError):owner.authenticated_payload({'id':8,'name':spec['payload']},req,repo,source_job=bad)
                extra=repo/'core/pysrc/unbound_finding_shadow.py';extra.write_text('# inert namespace refusal\n')
                with self.assertRaises(ValueError):owner.source_input_snapshot(repo,profile)
                extra.unlink()
                path=staged/'.github/scripts/test_pi_payload_identity.py';path.write_bytes(path.read_bytes()+b'\n# changed stage\n')
                with self.assertRaises(ValueError):owner.source_observation_binding(repo,staged,owner.source_identity(repo,profile),profile)

    def test_i_both_closed_physical_namespaces_refuse_missing_and_shadow_sources(self):
        with tempfile.TemporaryDirectory(prefix='ca-finding-members-') as td:
            base=Path(td).resolve()
            for profile,spec in owner.PYTHON_FINDING_PROFILES.items():
                repo=base/profile;repo.mkdir()
                for relative in spec['paths']:
                    path=repo/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'inert namespace fixture\n')
                owner._finding_python_members(repo,profile)
                extra=repo/'.github/scripts/unbound_finding_shadow.py';extra.write_text('# extra\n')
                with self.subTest(profile=profile,mutation='extra'),self.assertRaises(ValueError):owner._finding_python_members(repo,profile)
                extra.unlink()
                path=repo/'tools/test_measurement_contracts.py';path.unlink()
                with self.subTest(profile=profile,mutation='missing'),self.assertRaises(ValueError):owner._finding_python_members(repo,profile)

    def test_emit_joins_both_python_finding_source_payloads_to_their_uploaders(self):
        for cell in ('disposition:findings:HOOK-F03', 'disposition:findings:C-F07'):
            profile = self.EXPECTED[cell]['profile']
            # Keep the actual profile's role and uploader. Use one inert input
            # to exercise the report and archive join without replaying a suite.
            original = owner.PYTHON_FINDING_PROFILES[profile]
            path = self.EXPECTED[cell]['script']
            tiny = dict(original, paths=frozenset({path}))
            with (self.subTest(profile=profile),
                  tempfile.TemporaryDirectory(prefix='ca-python-source-emit-') as directory,
                  mock.patch.dict(owner.PYTHON_FINDING_PROFILES, {profile: tiny})):
                root = Path(directory).resolve()
                repo = root / 'repo'
                code = b'# inert source for emitter join\n'
                source = repo / path
                source.parent.mkdir(parents=True)
                source.write_bytes(code)
                recipe, spec, req, payload, observed, group, _ = self.fixture(cell)
                manifest = payload['documents'][owner.SOURCE_MANIFEST]
                manifest['members'][0].update(sha256=owner.readiness.digest(code), bytes=len(code))
                raw = json.dumps(manifest).encode('utf8')
                observed['source_input_binding']['manifest_sha256'] = owner.readiness.digest(raw)
                archive = io.BytesIO()
                with zipfile.ZipFile(archive, 'w') as zipped:
                    zipped.writestr(path, code)
                    zipped.writestr(owner.SOURCE_MANIFEST, raw)
                (repo / '.github/major-test-selections.json').write_text(
                    json.dumps({'schema': owner.SELECTIONS, 'groups': [group]}), encoding='utf8')
                observation = root / 'observation.json'
                observation.write_text(json.dumps(observed), encoding='utf8')
                metadata = {'id': 8, 'name': spec['payload']}
                step = {'name': spec['upload'], 'status': 'completed', 'conclusion': 'success'}
                job = {'id': 9, 'name': spec['job'], 'status': 'in_progress', 'conclusion': None, 'steps': [step]}
                identity = {**req, 'clean': True}
                env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': owner.readiness.REPOSITORY,
                       'GITHUB_REF': 'refs/heads/major/state-contracts', 'GITHUB_EVENT_NAME': 'push',
                       'GITHUB_SHA': req['source_commit'], 'GITHUB_RUN_ID': str(req['ci_run_id'])}
                out = root / 'qualification.json'
                stderr = io.StringIO()
                argv = ['emit', '--repo', str(repo), '--output', str(out), '--job-name', spec['job'],
                        '--observation', recipe['observation'] + '=' + str(observation),
                        '--payload-root', spec['payload'] + '=' + str(repo)]
                with (mock.patch.dict(os.environ, env, clear=True),
                      mock.patch.object(owner, 'source_identity', return_value=identity),
                      mock.patch.object(owner, 'source_input_snapshot', return_value={**identity, 'members': manifest['members']}),
                      mock.patch.object(owner.readiness, 'collect', return_value=(req, None, [metadata], [job])),
                      mock.patch.object(owner.readiness, 'artifact_bytes', return_value=archive.getvalue()),
                      mock.patch('sys.stderr', stderr)):
                    # Refuse a merely named step that did not actually complete.
                    step['conclusion'] = 'failure'
                    self.assertEqual(owner.main(argv), 1)
                    self.assertFalse(out.exists())
                    step['conclusion'] = 'success'
                    stderr.seek(0)
                    stderr.truncate()
                    self.assertEqual(owner.main(argv), 0, stderr.getvalue())
                result, = owner.load_json(out)['results']
                self.assertEqual(result['cell'], cell)
                self.assertEqual(result['selected_population'], len(recipe['selectors']))
                self.assertEqual(result['payload_artifact_id'], metadata['id'])


class StatuslineIsolationObservationTests(unittest.TestCase):
    def setUp(self):
        self.profile = owner.STATUSLINE_PROFILE
        self.spec = owner.source_profile(self.profile)
        self.cells = sorted(owner._STATUSLINE_CASES)
        self.commit = "e" * 40
        self.tree = "a" * 40
        self.owner_job = 678
        self.run = {"id": 731, "run_attempt": 1, "head_sha": self.commit,
                    "event": "push", "head_branch": "main", "conclusion": "success",
                    "path": ".github/workflows/ci.yml", "repository": {"full_name": owner.readiness.REPOSITORY}}
        self.job = {"id": self.owner_job, "name": self.spec["job"], "run_id": self.run["id"],
                    "run_attempt": 1, "status": "completed", "conclusion": "success"}
        self.inputs = {path: path.encode() for path in self.spec["paths"]}
        self.manifest = {"format": owner.SOURCE_FORMAT, "profile": self.profile,
                         "source_commit": self.commit, "source_tree": self.tree,
                         "workflow": self.run["path"], "ci_run_id": self.run["id"],
                         "producer_job_name": self.spec["job"], "members": [
            {"path": path, "sha256": owner.readiness.digest(raw), "bytes": len(raw), "git_mode": "100644"}
            for path, raw in sorted(self.inputs.items())
        ]}
        self.manifest_raw = json.dumps(self.manifest).encode()
        self.req = {"source_commit": self.commit, "source_tree": self.tree, "ci_run_id": self.run["id"],
                    "cells": self.cells, "cell_jobs": dict.fromkeys(self.cells, self.spec["job"]),
                    "source_finding_composite_cells": self.cells,
                    "source_finding_inputs": {self.profile: owner.source_member_digest(self.manifest["members"])}}
        named = sorted({test for cell in self.cells for test in owner.SOURCE_FINDING_COMPOSITIONS[cell][0]["selectors"]})
        self.observation = {"format": owner.OBSERVATION, "source_commit": self.commit, "source_tree": self.tree,
            "ci_run_id": self.run["id"], "run_attempt": 1, "clean": True, "source_stable": True,
            "proof_kind": "source-test", "producer": "python-test-result-observer",
            "test_result_scope": owner.STATUSLINE_RESULT_SCOPE, "exit_code": 0,
            "argv": ["python", owner.STATUSLINE_SCRIPT, "--statusline-results", owner.STATUSLINE_RAW_MEMBER],
            "tests": [{"id": test, "result": "passed"} for test in named],
            "source_input_binding": {"format": owner.SOURCE_BINDING, "profile": self.profile,
                "payload_name": self.spec["payload"], "manifest_sha256": owner.readiness.digest(self.manifest_raw)}}

    @staticmethod
    def archive(values):
        result = io.BytesIO()
        with zipfile.ZipFile(result, "w") as archive:
            for name, value in values.items():
                archive.writestr(name, value)
        return result.getvalue()

    def artifacts(self, observation=None, *, source=None, wrong_upload=False):
        source_bytes = self.archive({**(self.inputs if source is None else source),
                                     owner.SOURCE_MANIFEST: self.manifest_raw})
        captured = self.archive({owner.STATUSLINE_CAPTURE_MEMBER: json.dumps(
            self.observation if observation is None else observation).encode()})
        fingerprint = f"{self.commit}-{self.run['id']}-{self.run['run_attempt']}"
        transport = [(110, self.spec["payload"], self.spec["upload"], source_bytes),
                     (111, owner.STATUSLINE_CAPTURE_PREFIX + fingerprint, owner.STATUSLINE_CAPTURE_UPLOAD, captured)]
        self.job["steps"] = []
        logs = []
        metadata = []
        archives = {}
        for index, (artifact_id, name, step, raw) in enumerate(transport, 1):
            digest = owner.readiness.digest(raw)
            timestamp = f"2026-11-18T12:00:0{index}"
            self.job["steps"].append({"name": step, "status": "completed", "conclusion": "success",
                                      "started_at": timestamp + "Z", "completed_at": timestamp + ".930Z"})
            logs.extend(f"{timestamp}.{position}00Z {line}" for position, line in enumerate((
                        "##[group]Run " + owner.readiness.UPLOAD_ACTION,
                        "SHA256 digest of uploaded artifact is " + digest,
                        f"Artifact {name} successfully finalized. Artifact ID {artifact_id}"), 1))
            metadata.append({"id": artifact_id, "name": name, "size_in_bytes": len(raw), "expired": False,
                             "digest": "sha256:" + digest, "created_at": timestamp + "Z",
                             "workflow_run": {"id": self.run["id"], "head_sha": self.commit}})
            archives[artifact_id] = raw
        if wrong_upload:
            logs = logs[:-1]
        return metadata, archives, "\n".join(logs).encode()

    def reconstruct(self, observation=None, *, source=None, wrong_upload=False):
        metadata, contents, upload_log = self.artifacts(observation, source=source, wrong_upload=wrong_upload)
        def read_log(url, *, binary=False):
            self.assertEqual((url, binary), (f"actions/jobs/{self.owner_job}/logs", True))
            return upload_log
        def read_archive(artifact, req):
            raw = contents[artifact["id"]]
            owner.readiness.validate_artifact(artifact, req, owner.readiness.digest(raw))
            return raw
        with mock.patch.object(owner.readiness, "api", side_effect=read_log) as log, \
             mock.patch.object(owner.readiness, "artifact_bytes", side_effect=read_archive) as read:
            rows = owner.source_finding_evidence(self.req, metadata, [self.job], run=self.run)
        self.assertEqual((log.call_count, read.call_count), (1, 2))
        return rows

    def test_closed_rows_and_composition_reuse_one_original_isolation_capture(self):
        policy = owner.load_json(owner.ROOT / ".github/major-qualification-policy.json")
        self.assertEqual({cell: policy["cell_job_bindings"][cell] for cell in self.cells}, self.req["cell_jobs"])
        self.assertLessEqual(set(self.cells), set(policy["source_finding_composite_cells"]))
        rows, artifacts = self.reconstruct()
        self.assertEqual(set(rows), set(self.cells))
        self.assertEqual(set(artifacts), {110})
        self.assertEqual(sorted(len(row["source_components"][0]["selectors"]) for row in rows.values()),
                         [3, 4, 8, 8, 8, 12, 14, 16, 34, 67])
        scenario_selectors = rows["scenario:SEQ-21"]["source_components"][0]["selectors"]
        self.assertEqual(scenario_selectors, sorted(owner._statusline_test_id(case)
                                                  for case in owner._STATUSLINE_CASES["scenario:SEQ-21"]))
        self.assertEqual({r["source_components"][0]["observation_artifact_id"] for r in rows.values()}, {111})

    def test_refuse_stale_foreign_filtered_missing_duplicate_or_nonpassing_observation(self):
        def altered(transform):
            changed = copy.deepcopy(self.observation)
            transform(changed)
            return changed
        for name, observation in (
            ("attempt", altered(lambda o: o.update(run_attempt=2))),
            ("tree", altered(lambda o: o.update(source_tree="b" * 40))),
            ("ordinary-outer", altered(lambda o: o.update(test_result_scope=owner.OUTER_UNITTEST_RESULT))),
            ("filtered", altered(lambda o: o["argv"].append("-k"))),
            ("wrong-command", altered(lambda o: o["argv"].__setitem__(1, ".github/scripts/test_generated_output.py"))),
            ("wrong-result-file", altered(lambda o: o["argv"].__setitem__(3, "foreign.json"))),
            ("missing-case", altered(lambda o: o["tests"].pop())),
            ("duplicate-case", altered(lambda o: o["tests"].append(o["tests"][0]))),
            ("failed-case", altered(lambda o: o["tests"][0].update(result="skipped"))),
            ("foreign-module", altered(lambda o: o["tests"][0].update(id="python:wrong.py:wrong.Test.test_ok"))),
        ):
            with self.subTest(name=name), self.assertRaises((ValueError, owner.readiness.ReadinessError)):
                self.reconstruct(observation)

    def test_refuse_foreign_owner_wrong_event_bad_source_bytes_and_unattributed_upload(self):
        source = dict(self.inputs)
        source[owner.STATUSLINE_SCRIPT] += b"changed"
        with self.assertRaises((ValueError, owner.readiness.ReadinessError)):
            self.reconstruct(source=source)
        with self.assertRaises((ValueError, owner.readiness.ReadinessError)):
            self.reconstruct(wrong_upload=True)
        self.job["name"] = self.spec["job"].replace("isolation", "contracts")
        with self.assertRaises((ValueError, owner.readiness.ReadinessError)):
            self.reconstruct()
        self.job["name"] = self.spec["job"]
        self.req["cell_jobs"][self.cells[0]] = self.spec["job"].replace("isolation", "contracts")
        with self.assertRaises((ValueError, owner.readiness.ReadinessError)):
            self.reconstruct()
        self.req["cell_jobs"][self.cells[0]] = self.spec["job"]
        self.run["event"] = "pull_request"
        with self.assertRaises((ValueError, owner.readiness.ReadinessError)):
            self.reconstruct()


class HookF02CompleteCompositionTests(unittest.TestCase):
    CELL='disposition:findings:HOOK-F02'
    COMPONENTS=[{'script': '.github/scripts/test_modelib.py',
  'observation': 'finite-hookf02-modelib',
  'selectors': ['python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_a_flip_whose_row_never_landed_reports_failure',
                'python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_a_writable_trail_still_reports_a_flip_and_writes_exactly_one_row',
                'python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_an_unwritable_trail_leaves_the_enter_row_owed_not_lost',
                'python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_repeat_request_recovers_an_unsettled_enter_instead_of_reporting_noop',
                'python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_repeat_request_stays_failed_when_only_an_older_session_settles',
                'python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_repeat_request_stays_failed_while_the_enter_row_cannot_settle',
                'python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_the_owed_row_replays_on_the_next_settle',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_double_flip_to_the_same_mode_is_a_noop_with_byte_identical_log',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_existing_debt_does_not_prove_new_transition_was_recorded',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_explicitly_entered_arbiter_is_exited_on_its_next_transition',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_failed_queue_and_trail_do_not_claim_persisted_debt',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_fallback_arbiter_with_old_enter_has_no_invented_exit',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_first_flip_transitions_and_appends_one_enter_row',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_flip_to_the_default_arbiter_when_already_arbiter_is_also_a_noop',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_implicit_arbiter_and_unbacked_raw_modes_have_no_invented_exit',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_legacy_backed_dangerous_transition_keeps_history_and_records_exit',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_marker_failure_leaves_prior_audit_and_mode_unchanged',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_partial_pair_retries_even_with_old_requested_mode_backing',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_same_second_cycle_debt_is_not_satisfied_by_older_rows',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_transition_exit_is_attributed_only_to_its_session',
                'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_transition_exits_prior_mode_exactly_once',
                'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_clean_flip_outcome_is_fully_settled',
                'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_failure_before_marker_commit_reports_nothing_changed',
                'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_failure_during_owed_row_replay_keeps_order_and_counts_all_debt',
                'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_flip_wrapper_keeps_the_legacy_sentinels',
                'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_marker_committed_audit_owed_is_raw_ops_effective_arbiter',
                'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_owed_row_settles_at_restart_without_duplicate_history',
                'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_retry_of_same_token_settles_owed_row_once',
                'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_return_to_arbiter_with_owed_row_reports_effective_arbiter',
                'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_unbacked_raw_with_no_owed_row_can_still_be_settled',
                'python:.github/scripts/test_modelib.py:__main__.TestSettleGenericModeExitRow.test_interrupted_mode_exit_row_is_owed_and_settles_exactly_once']},
 {'script': '.github/scripts/test_prompt_submit.py',
  'observation': 'finite-hookf01',
  'selectors': ['python:.github/scripts/test_prompt_submit.py:__main__.TestFlipMessagesReportTheActualOutcome.test_bare_mode_reports_effective_and_the_unbacked_raw_marker',
                'python:.github/scripts/test_prompt_submit.py:__main__.TestFlipMessagesReportTheActualOutcome.test_codex_envelope_carries_the_same_truthful_partial',
                'python:.github/scripts/test_prompt_submit.py:__main__.TestFlipMessagesReportTheActualOutcome.test_marker_write_failure_says_nothing_changed',
                'python:.github/scripts/test_prompt_submit.py:__main__.TestFlipMessagesReportTheActualOutcome.test_marker_written_audit_owed_names_raw_effective_and_next_action',
                'python:.github/scripts/test_prompt_submit.py:__main__.TestFlipMessagesReportTheActualOutcome.test_no_runtime_mode_message_claims_modes_switch_gates',
                'python:.github/scripts/test_prompt_submit.py:__main__.TestFlipMessagesReportTheActualOutcome.test_return_to_arbiter_with_owed_row_does_not_claim_the_old_mode']}]

    def fixture(self):
        _,spec,base_req,payload,prompt,old_group,_=SingleOwnerPythonFindingProfileTests().fixture('disposition:findings:HOOK-F01')
        req=copy.deepcopy(base_req);req.update(cells=[self.CELL],cell_jobs={self.CELL:spec['job']})
        groups=[];observations={}
        for component in self.COMPONENTS:
            o=copy.deepcopy(prompt);o['argv']=['python',component['script']]
            if component['script'].endswith('test_modelib.py'):o['tests']=[]
            o['tests'].extend({'id':selector,'result':'passed'} for selector in component['selectors'])
            observations[component['observation']]=o
            groups.append({'id':'finite-hookf02-'+('modelib' if component['script'].endswith('test_modelib.py') else 'prompt'),
                'job':spec['job'],'payload_name':spec['payload'],'observation':component['observation'],
                'proof_kind':'source-test','selectors':list(component['selectors']),'cells':[self.CELL],
                'scope':'HOOK-F02 actual raw/effective mode outcome, refusal, audit debt/retry/no-op and prompt-message assertion composition; no universal durability or task/installed credit.'})
        def build(obs=observations,gs=groups,r=req,p=payload):
            return owner.build_report(r,job_name=spec['job'],job_id=9,
                selections={'schema':owner.SELECTIONS,'groups':gs},observations=obs,payloads={spec['payload']:p})
        return spec,req,payload,observations,groups,build

    def test_a_complete_two_original_owners_admit_one_finite_finding(self):
        spec,req,payload,observations,groups,build=self.fixture()
        try:report=build()
        except ValueError as error:self.fail('actual same-job source-report boundary lacks complete HOOK-F02 composition: '+str(error))
        result,=report['results']
        self.assertEqual(result['cell'],self.CELL)
        self.assertEqual(result['selected_population'],37)
        self.assertEqual(result['executed_population'],37)
        self.assertEqual(len(result['commands']),2)
        self.assertEqual(len(report['payloads']),1)

    def test_b_both_complete_components_and_each_named_guard_effect_and_retry_are_required(self):
        spec,req,payload,observations,groups,build=self.fixture()
        for index in range(2):
            for mode in ('missing-group','repeat-group','missing-observation','one-observation-twice'):
                obs,gs=copy.deepcopy(observations),copy.deepcopy(groups)
                if mode=='missing-group':gs.pop(index)
                elif mode=='repeat-group':extra=copy.deepcopy(gs[index]);extra['id']+='-duplicate';gs.append(extra)
                elif mode=='missing-observation':obs.pop(gs[index]['observation'])
                else:gs[index]['observation']=gs[1-index]['observation']
                with self.subTest(component=index,mode=mode),self.assertRaises(ValueError):build(obs,gs)
        for component in self.COMPONENTS:
            key=component['observation']
            for selector in component['selectors']:
                for mode in ('missing','duplicate','skipped','failed','partial-group'):
                    obs,gs=copy.deepcopy(observations),copy.deepcopy(groups)
                    row=next(r for r in obs[key]['tests'] if r['id']==selector)
                    if mode=='missing':obs[key]['tests'].remove(row)
                    elif mode=='duplicate':obs[key]['tests'].append(dict(row))
                    elif mode=='partial-group':next(g for g in gs if g['observation']==key)['selectors'].remove(selector)
                    else:row['result']=mode
                    with self.subTest(selector=selector,mode=mode),self.assertRaises(ValueError):build(obs,gs)

    def test_c_no_component_can_borrow_foreign_source_script_command_job_or_authority(self):
        spec,req,payload,observations,groups,build=self.fixture()
        for key in observations:
            for mode in ('source','tree','run','stable','exit','filtered','wrong-script','profile','payload','manifest','producer'):
                obs=copy.deepcopy(observations);o=obs[key]
                if mode=='source':o['source_commit']='f'*40
                elif mode=='tree':o['source_tree']='f'*40
                elif mode=='run':o['ci_run_id']=8
                elif mode=='stable':o['source_stable']=False
                elif mode=='exit':o['exit_code']=1
                elif mode=='filtered':o['argv'].append('-k')
                elif mode=='wrong-script':o['argv'][-1]='.github/scripts/test_verdictlib.py'
                elif mode=='profile':o['source_input_binding']['profile']='impact-single-owner-findings-v1'
                elif mode=='payload':o['source_input_binding']['payload_name']='major-source-inputs-hooks-windows-contracts'
                elif mode=='manifest':o['source_input_binding']['manifest_sha256']='f'*64
                else:o['producer']='go-named-ci20-join'
                with self.subTest(component=key,mode=mode),self.assertRaises(ValueError):build(obs)
        for index in range(2):
            for mode in ('job','different-payload','proof-kind','extra-selector','foreign-cell','composite-cell'):
                gs,r=copy.deepcopy(groups),copy.deepcopy(req);g=gs[index]
                if mode=='job':g['job']='foreign'
                elif mode=='different-payload':g['payload_name']='major-source-inputs-hooks-windows-contracts'
                elif mode=='proof-kind':g['proof_kind']='native-module'
                elif mode=='extra-selector':g['selectors'].append('python:foreign.py:unexecuted')
                elif mode=='foreign-cell':g['cells']=['disposition:findings:W-F02'];r.update(cells=g['cells'],cell_jobs=dict.fromkeys(g['cells'],spec['job']))
                else:g['cells'].append('task:HW-02');r.update(cells=[self.CELL,'task:HW-02'],cell_jobs={self.CELL:spec['job'],'task:HW-02':spec['job']})
                with self.subTest(component=index,mode=mode),self.assertRaises(ValueError):build(gs=gs,r=r)
        obs,gs,p=copy.deepcopy(observations),copy.deepcopy(groups),copy.deepcopy(payload)
        binding={'inert':'foreign native authority'};p['native_bindings']=[binding]
        for o in obs.values():o.update(proof_kind='native-module',producer='go-named-ci20-join',native_binding=binding)
        for g in gs:g['proof_kind']='native-module'
        with self.assertRaises(ValueError):build(obs,gs,p=p)
        for mutation in ('missing-uploader','wrong-uploader','missing-manifest-member'):
            p=copy.deepcopy(payload)
            if mutation=='missing-uploader':p.pop('source_upload_job_id')
            elif mutation=='wrong-uploader':p['source_upload_job_id']=10
            else:p['members'].pop(0)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):build(p=p)

    def test_d_prompt_record_is_reused_without_another_execution_or_payload(self):
        spec,req,payload,observations,groups,build=self.fixture()
        _,_,_,_,_,existing,_=SingleOwnerPythonFindingProfileTests().fixture('disposition:findings:HOOK-F01')
        req.update(cells=['disposition:findings:HOOK-F01',self.CELL],cell_jobs={'disposition:findings:HOOK-F01':spec['job'],self.CELL:spec['job']})
        groups.append(existing)
        with mock.patch.object(owner.runpy,'run_path',side_effect=AssertionError('admission must never execute original suites')):
            report=build()
        results={r['cell']:r for r in report['results']}
        self.assertEqual(results[self.CELL]['executed_population'],37)
        self.assertEqual(results['disposition:findings:HOOK-F01']['executed_population'],13)
        self.assertEqual(len(observations),2)
        self.assertEqual(len(report['payloads']),1)
        self.assertEqual(results[self.CELL]['payload_artifact_id'],results['disposition:findings:HOOK-F01']['payload_artifact_id'])

    def test_e_configuration_contains_only_the_complete_finite_two_group_finding(self):
        spec,req,payload,observations,groups,build=self.fixture()
        actual=owner.load_json(owner.ROOT/'.github/major-test-selections.json')
        selected=[g for g in actual['groups'] if self.CELL in g['cells']]
        self.assertEqual(selected,groups)
        self.assertEqual(owner.load_json(owner.ROOT/'.github/major-qualification-policy.json')['cell_job_bindings'][self.CELL],spec['job'])
        self.assertNotIn(self.CELL, owner.PYTHON_FINDING_RECIPES)
        self.assertTrue({'.github/scripts/test_modelib.py','.github/scripts/test_prompt_submit.py','core/pysrc/_modelib.py','core/pysrc/prompt-submit.py'}<=spec['paths'])

if __name__ == "__main__":
    unittest.main(verbosity=2)
