#!/usr/bin/env python3
"""Real installed-candidate journey through the local work command."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core/pysrc"))
import _artifactlib  # noqa: E402
import work  # noqa: E402
import taskwrite  # noqa: E402
import _worklib  # noqa: E402


class WorkCLITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.owned_candidate = None
        configured = os.environ.get("ARTIFACT_TEST_INSTALLATION")
        if configured:
            cls.installation = Path(configured).resolve(strict=True)
        else:
            cls.owned_candidate = tempfile.TemporaryDirectory(prefix="ca-work-candidate-")
            cls.installation = Path(cls.owned_candidate.name).resolve() / "payload"
            subprocess.run([sys.executable, str(REPO / "tools/build-artifacts.py"),
                            "--output", str(cls.installation)], cwd=REPO, check=True,
                           capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.owned_candidate is not None:
            cls.owned_candidate.cleanup()

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="ca-work-cli-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve(strict=True)
        self.client = _artifactlib.ArtifactClient(self.root, self.installation)
        root_patch = mock.patch.object(work, "project_root", return_value=str(self.root))
        client_patch = mock.patch.object(work, "_client", return_value=self.client)
        root_patch.start()
        client_patch.start()
        self.addCleanup(root_patch.stop)
        self.addCleanup(client_patch.stop)

    def run_work(self, *argv: str) -> dict:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = work.main(list(argv))
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0, result)
        return result

    def test_first_native_work_survives_fresh_clone(self) -> None:
        first = self.run_work("create", "--title", "Portable work", "--intent",
                              "Retain project identity", "--type", "fix",
                              "--operation-id", "cli-portable-work-001")
        project = self.root / ".codearbiter" / "work" / "project.json"
        self.assertTrue(project.is_file())
        (self.root / ".gitattributes").write_bytes((REPO / ".gitattributes").read_bytes())
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True,
                       capture_output=True, text=True)
        subprocess.run(["git", "-C", str(self.root), "add", "--",
                        ".gitattributes", ".codearbiter/work/project.json", first["path"]],
                       check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit", "--quiet",
                        "-m", "Record first work"], check=True,
                       capture_output=True, text=True)
        with tempfile.TemporaryDirectory(prefix="ca-work-clone-") as directory:
            # macOS temp paths may start at /var, a link to /private/var.
            # Pass the real parent to the engine's strict root guard.
            clone = Path(directory).resolve(strict=True) / "clone"
            subprocess.run(["git", "clone", "--quiet", str(self.root), str(clone)],
                           check=True, capture_output=True, text=True)
            self.assertFalse((clone / ".codearbiter" / ".artifacts").exists())
            restored = _artifactlib.ArtifactClient(clone, self.installation).call(
                "work-get", {"work_id": first["work_id"]})
            self.assertEqual(restored["work_id"], first["work_id"])
            self.assertEqual(restored["title"], "Portable work")

    def test_local_journey_has_stable_identity_and_unknown_check(self) -> None:
        self.client.call("create", {"operation_id": "cli-spec-create-001", "kind": "spec",
                                    "artifact_id": "SPEC-CLI", "slug": "cli", "title": "CLI specification",
                                    "summary": "Attached result"})
        self.client.call("create", {"operation_id": "cli-plan-create-001", "kind": "plan",
                                    "artifact_id": "PLAN-CLI", "slug": "cli", "title": "CLI plan",
                                    "summary": "Attached steps", "spec_id": "SPEC-CLI"})
        first = self.run_work("create", "--title", "Same title", "--intent", "First outcome",
                              "--type", "fix", "--operation-id", "cli-work-create-001")
        replay = self.run_work("create", "--title", "Same title", "--intent", "First outcome",
                               "--type", "fix", "--operation-id", "cli-work-create-001")
        second = self.run_work("create", "--title", "Same title", "--intent", "Second outcome",
                               "--type", "fix", "--operation-id", "cli-work-create-002")
        self.assertEqual(first["work_id"], replay["work_id"])
        self.assertNotEqual(first["work_id"], second["work_id"])
        page = self.run_work("list", "--limit", "1")
        self.assertEqual((page["total"], len(page["entries"])), (2, 1))
        continued = self.run_work("list", "--offset", str(page["next_offset"]),
                                  "--limit", "1", "--membership-sha256", page["membership_sha256"])
        self.assertEqual((len(continued["entries"]), continued["next_offset"]), (1, None))
        work_id = first["work_id"]
        attached = self.run_work("attach", work_id, "--spec-id", "SPEC-CLI", "--plan-id", "PLAN-CLI",
                                 "--operation-id", "cli-work-attach-001")
        self.assertEqual((attached["spec_id"], attached["plan_id"]), ("SPEC-CLI", "PLAN-CLI"))
        self.run_work("start", work_id, "--operation-id", "cli-work-start-001")
        completed = self.run_work("complete", work_id, "--operation-id", "cli-work-complete-001")
        self.assertEqual((completed["state"], completed["check_status"]), ("complete", "unknown"))
        context = self.run_work("context", work_id, "--budget", "4096")
        self.assertFalse(context["context_complete"])
        self.assertEqual(context["spec"]["artifact_id"], "SPEC-CLI")
        self.assertEqual(context["plan"]["artifact_id"], "PLAN-CLI")
        self.assertEqual(self.run_work("get", work_id)["work_id"], work_id)
        self.run_work("reopen", work_id, "--operation-id", "cli-work-reopen-001")
        archived = self.run_work("archive", work_id, "--operation-id", "cli-work-archive-001")
        self.assertEqual((archived["work_id"], archived["state"]), (work_id, "archived"))
        self.assertIn("../plans/cli.html", (self.root / archived["path"]).read_text(encoding="utf-8"))

    def test_selected_view_is_inert_html_and_leaves_no_second_owner(self) -> None:
        self.client.call("create", {"operation_id": "view-cli-spec-001", "kind": "spec",
                                    "artifact_id": "SPEC-VIEW-CLI", "slug": "view-cli",
                                    "title": "Specification", "summary": "Outcome <safe>"})
        self.client.call("create", {"operation_id": "view-cli-plan-001", "kind": "plan",
                                    "artifact_id": "PLAN-VIEW-CLI", "slug": "view-cli",
                                    "title": "Plan", "summary": "Implementation path",
                                    "spec_id": "SPEC-VIEW-CLI"})
        work_item = self.run_work("create", "--title", "View selected work",
                                  "--intent", "One readable overview", "--type", "feature",
                                  "--spec-id", "SPEC-VIEW-CLI", "--plan-id", "PLAN-VIEW-CLI",
                                  "--operation-id", "view-cli-work-001")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(work.main(["view", work_item["work_id"]]), 0)
        page = output.getvalue()
        self.assertTrue(page.startswith("<!doctype html>"))
        for value in ("Outcome &lt;safe&gt;", "Local progress", "Checks", "Delivery",
                      "Tracker sync", "../../specs/view-cli.html", "../../plans/view-cli.html"):
            self.assertIn(value, page)
        self.assertNotIn('id="ca-artifact-model"', page)
        self.assertFalse((self.root / ".codearbiter" / "views").exists())
        self.assertEqual(self.run_work("get", work_item["work_id"])["state"], "queued")

    def test_legacy_board_remains_owner_and_create_returns_stable_identity(self) -> None:
        board = self.root / ".codearbiter" / "open-tasks.md"
        board.parent.mkdir(parents=True)
        board.write_text("# Existing owner\n\n## In-flight\n- [ ] Older unkeyed task\n", encoding="utf-8")
        first = self.run_work("create", "--title", "Same title", "--intent", "Keep one owner",
                              "--type", "fix", "--origin", "DECOMP-1#WORK-1")
        replay = self.run_work("create", "--title", "Same title", "--intent", "Keep one owner",
                               "--type", "fix", "--origin", "DECOMP-1#WORK-1")
        second = self.run_work("create", "--title", "Same title", "--intent", "Other work",
                               "--type", "fix", "--origin", "DECOMP-1#WORK-2")
        self.assertEqual(first["work_id"], replay["work_id"])
        self.assertTrue(replay["reused"])
        self.assertNotEqual(first["work_id"], second["work_id"])
        self.assertEqual(self.run_work("get", first["work_id"])["intent"], "Keep one owner")
        page = self.run_work("list", "--limit", "1")
        self.assertEqual((page["total"], len(page["entries"])), (2, 1))
        self.assertEqual(page["unkeyed_count"], 1)
        continued = self.run_work("list", "--offset", str(page["next_offset"]),
                                  "--limit", "1", "--membership-sha256", page["membership_sha256"])
        self.assertEqual((len(continued["entries"]), continued["next_offset"]), (1, None))
        self.assertEqual(
            {entry["origin"] for entry in page["entries"] + continued["entries"]},
            {"DECOMP-1#WORK-1", "DECOMP-1#WORK-2"},
        )
        self.assertIn("(from DECOMP-1#WORK-1)", board.read_text(encoding="utf-8"))
        self.assertFalse((self.root / ".codearbiter" / "work").exists())

        self.assertFalse((self.root / ".codearbiter" / "work" / "project.json").exists())
        original = board.read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = work.main(["create", "--title", "Other source", "--intent", "Do not duplicate",
                              "--type", "fix", "--origin", "DECOMP-1#WORK-3",
                              "--operation-id", first["operation_id"]])
        self.assertEqual(code, 1)
        self.assertIn("different origin", json.loads(output.getvalue())["error"])
        self.assertEqual(board.read_bytes(), original)

    def test_legacy_context_reads_selected_work_with_budget(self) -> None:
        board = self.root / ".codearbiter" / "open-tasks.md"
        board.parent.mkdir(parents=True)
        board.write_text("# Existing owner\n\n## In-flight\n", encoding="utf-8")
        created = self.run_work("create", "--title", "Selected work", "--intent", "Keep context honest",
                                "--type", "fix", "--origin", "DECOMP#CONTEXT")
        context = self.run_work("context", created["work_id"], "--budget", "4096")
        self.assertEqual(context["work"]["work_id"], created["work_id"])
        self.assertFalse(context["context_complete"])
        large = self.run_work("create", "--title", "Large work", "--intent", "x" * 3000,
                              "--type", "fix", "--origin", "DECOMP#LARGE")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = work.main(["context", large["work_id"], "--budget", "1024"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["code"], "RESPONSE_TOO_LARGE")

    def test_legacy_work_keeps_option_like_values_as_data(self) -> None:
        board = self.root / ".codearbiter" / "open-tasks.md"
        board.parent.mkdir(parents=True)
        board.write_text("# Existing owner\n\n## In-flight\n", encoding="utf-8")
        request = {"operation_id": "dash-values-001", "title": "-h",
                   "intent": "-MVP login.", "work_type": "fix", "origin": "-a#1"}
        created = _worklib.dispatch(str(self.root), "work-create", request)
        self.assertEqual((created["title"], created["intent"], created["origin"]),
                         ("-h", "-MVP login.", "-a#1"))
        started = _worklib.dispatch(str(self.root), "work-update", {
            "operation_id": "dash-values-start-001", "work_id": created["work_id"],
            "expected_board_sha256": created["board_sha256"], "action": "start",
        })
        self.assertEqual((started["work_id"], started["state"]),
                         (created["work_id"], "active"))

    def test_create_requires_a_replay_identity_and_origin_reuses_one_item(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = work.main(["create", "--title", "Unbound", "--intent", "Uncertain response", "--type", "fix"])
        self.assertEqual(code, 1)
        self.assertIn("--operation-id or --origin", json.loads(output.getvalue())["error"])
        source = "checkpoint-2026-10-30#triage-1"
        self.assertEqual(self.run_work("origins", "--origin", source)["matches"], [])
        first = self.run_work("create", "--title", "Promoted", "--intent", "Same logical work",
                              "--type", "fix", "--origin", source)
        retried = self.run_work("create", "--title", "Promoted", "--intent", "Same logical work",
                                "--type", "fix", "--origin", source)
        self.assertEqual((first["work_id"], first["operation_id"]),
                         (retried["work_id"], retried["operation_id"]))
        self.assertEqual(self.run_work("list")["entries"][0]["origin"], source)
        self.assertEqual(self.run_work("origins", "--origin", source)["matches"][0]["work_id"], first["work_id"])
        changed = self.run_work("create", "--title", "Promoted again", "--intent", "Changed wording",
                                "--type", "fix", "--origin", source)
        self.assertEqual(changed["work_id"], first["work_id"])
        self.assertNotEqual(changed["operation_id"], first["operation_id"])
        self.assertTrue(changed["input_differs"])

    def test_legacy_origin_survives_board_archive_and_replay(self) -> None:
        board = self.root / ".codearbiter" / "open-tasks.md"
        board.parent.mkdir(parents=True)
        board.write_text("# Existing owner\n\n## In-flight\n", encoding="utf-8")
        first = self.run_work("create", "--title", "Archived work",
                              "--intent", "Keep identity through archive",
                              "--type", "chore", "--origin", "DECOMP-ARCHIVE#WORK-1")
        for argv in (["start", "ignored", "--from", first["origin"], "--date", "2026-10-29"],
                     ["done", "ignored", "--from", first["origin"], "--date", "2026-10-30"],
                     ["archive", "ignored", "--from", first["origin"]]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(taskwrite.main(argv, root=str(self.root)), 0)
        archived = self.run_work("get", first["work_id"])
        self.assertEqual(archived["state"], "archived")
        self.assertEqual(archived["work_id"], first["work_id"])
        self.assertEqual(self.run_work("origins", "--origin", first["origin"])["matches"][0]["state"], "archived")
        replay = self.run_work("create", "--title", "Archived work",
                               "--intent", "Keep identity through archive",
                               "--type", "chore", "--origin", first["origin"])
        self.assertEqual(replay["work_id"], first["work_id"])
        self.assertTrue(replay["reused"])
        self.assertEqual(board.read_text(encoding="utf-8").count("Archived work"), 0)
        with tempfile.TemporaryDirectory(prefix="ca-work-fresh-clone-") as clone:
            clone_state = Path(clone) / ".codearbiter"
            clone_state.mkdir()
            (clone_state / "open-tasks.md").write_text(
                board.read_text(encoding="utf-8"), encoding="utf-8")
            (clone_state / "done-tasks.md").write_text(
                (self.root / ".codearbiter" / "done-tasks.md").read_text(encoding="utf-8"),
                encoding="utf-8")
            selected = _worklib.dispatch(clone, "work-get", {"work_id": first["work_id"]})
            self.assertEqual(selected["state"], "archived")
            self.assertEqual(selected["work_id"], first["work_id"])

    def test_versioned_request_uses_legacy_owner_without_native_write(self) -> None:
        board = self.root / ".codearbiter" / "open-tasks.md"
        board.parent.mkdir(parents=True)
        board.write_text("# Existing owner\n\n## In-flight\n", encoding="utf-8")
        payload = {"schema": "codearbiter.work-request/0.1.0",
                   "operation": "work-create",
                   "request": {"operation_id": "legacy-json-001", "title": "JSON task",
                               "intent": "One board write", "work_type": "chore"}}
        def invoke(value):
            output = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(json.dumps(value))), contextlib.redirect_stdout(output):
                code = work.main(["--request", "-"])
            return code, json.loads(output.getvalue())
        code, first = invoke(payload)
        self.assertEqual(code, 0, first)
        code, replay = invoke(payload)
        self.assertEqual(code, 0, replay)
        self.assertEqual(first["work_id"], replay["work_id"])
        self.assertEqual(board.read_text(encoding="utf-8").count("JSON task"), 1)
        self.assertFalse((self.root / ".codearbiter" / "work").exists())
        code, refused = invoke({**payload, "request": {**payload["request"], "origin": ["bad"]}})
        self.assertEqual(code, 1)
        self.assertIn("origin must be text", refused["error"])
        code, refused = invoke({"schema": payload["schema"], "operation": "work-origins",
                                "request": {"origins": [["not a source key"]]}})
        self.assertEqual(code, 1)
        self.assertIn("invalid legacy origin query", refused["error"])

    def test_legacy_oversize_board_refuses_before_a_write(self) -> None:
        board = self.root / ".codearbiter" / "open-tasks.md"
        board.parent.mkdir(parents=True)
        original = b"# Existing owner\n" + b"x" * (1 << 20)
        board.write_bytes(original)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = work.main(["create", "--title", "Do not add", "--intent",
                              "Preserve bytes", "--type", "fix",
                              "--operation-id", "legacy-limit-001"])
        self.assertEqual(code, 1)
        self.assertIn("bounded read limit", json.loads(output.getvalue())["error"])
        self.assertEqual(board.read_bytes(), original)

    def test_legacy_owner_refuses_orphan_native_work_files(self) -> None:
        board = self.root / ".codearbiter" / "open-tasks.md"
        board.parent.mkdir(parents=True)
        board.write_text("# Existing owner\n\n## In-flight\n", encoding="utf-8")
        work_dir = board.parent / "work"
        work_dir.mkdir()
        (work_dir / ("WORK-" + "A" * 32 + ".html")).write_text("orphan", encoding="utf-8")
        original = board.read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = work.main(["create", "--title", "Do not add", "--intent",
                              "Keep one owner", "--type", "fix",
                              "--operation-id", "legacy-orphan-001"])
        self.assertEqual(code, 1)
        self.assertIn("both legacy and native", json.loads(output.getvalue())["error"])
        self.assertEqual(board.read_bytes(), original)

    def test_legacy_title_with_origin_words_does_not_strand_create(self) -> None:
        board = self.root / ".codearbiter" / "open-tasks.md"
        board.parent.mkdir(parents=True)
        board.write_text("# Existing owner\n\n## In-flight\n", encoding="utf-8")
        first = self.run_work("create", "--title", "Migrate (from paper)",
                              "--intent", "Keep literal title", "--type", "fix",
                              "--origin", "DECOMP#1")
        self.assertEqual(self.run_work("get", first["work_id"])["title"],
                         "Migrate (from paper)")
        self.assertEqual(self.run_work("create", "--title", "Migrate (from paper)",
                                      "--intent", "Keep literal title", "--type", "fix",
                                      "--origin", "DECOMP#1")["work_id"], first["work_id"])

    def test_legacy_json_request_refuses_unknown_field_before_write(self) -> None:
        board = self.root / ".codearbiter" / "open-tasks.md"
        board.parent.mkdir(parents=True)
        board.write_text("# Existing owner\n\n## In-flight\n", encoding="utf-8")
        original = board.read_bytes()
        payload = {"schema": "codearbiter.work-request/0.1.0", "operation": "work-create",
                   "request": {"operation_id": "legacy-typo-001", "title": "Do not add",
                               "intent": "Plan matters", "work_type": "fix",
                               "plan_idd": "PLAN-INTENDED"}}
        output = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(output):
            code = work.main(["--request", "-"])
        self.assertEqual(code, 1)
        self.assertIn("unknown", json.loads(output.getvalue())["error"])
        self.assertEqual(board.read_bytes(), original)

    def test_legacy_duplicate_identity_metadata_refuses_selected_read(self) -> None:
        board = self.root / ".codearbiter" / "open-tasks.md"
        board.parent.mkdir(parents=True)
        board.write_text(
            "# Existing owner\n\n## In-flight\n"
            "- [ ] Corrupt  (from DECOMP#BAD)\n"
            "  - Work origin: DECOMP#BAD\n"
            "  - Work ID: WORK-" + "A" * 32 + "\n"
            "  - Work ID: WORK-" + "B" * 32 + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate legacy Work ID"):
            _worklib.dispatch(str(self.root), "work-list", {"limit": 1})

    def test_legacy_work_updates_keep_unknown_check_and_exact_identity(self) -> None:
        board = self.root / ".codearbiter" / "open-tasks.md"
        board.parent.mkdir(parents=True)
        board.write_text("# Existing owner\n\n## In-flight\n", encoding="utf-8")
        first = self.run_work("create", "--title", "Same title",
                              "--intent", "Already performed", "--type", "fix",
                              "--origin", "DECOMP#COMPLETE")
        second = self.run_work("create", "--title", "Same title",
                               "--intent", "Later work", "--type", "fix",
                               "--origin", "DECOMP#OTHER")
        completed = self.run_work("complete", first["work_id"],
                                  "--operation-id", "legacy-complete-001")
        self.assertEqual((completed["state"], completed["check_status"]),
                         ("complete", "unknown"))
        self.assertIsNone(completed["started_at"])
        listed = self.run_work("list")["entries"]
        listed_completed = next(item for item in listed if item["work_id"] == first["work_id"])
        self.assertEqual(listed_completed["completed_at"], completed["completed_at"])
        self.assertEqual(self.run_work("get", second["work_id"])["state"], "queued")
        archived = self.run_work("archive", first["work_id"],
                                 "--operation-id", "legacy-archive-001")
        self.assertEqual(archived["state"], "archived")
        self.assertEqual(self.run_work("get", first["work_id"])["work_id"], first["work_id"])

    def test_legacy_update_stale_snapshot_preserves_later_edit(self) -> None:
        board = self.root / ".codearbiter" / "open-tasks.md"
        board.parent.mkdir(parents=True)
        board.write_text("# Existing owner\n\n## In-flight\n", encoding="utf-8")
        first = self.run_work("create", "--title", "Work", "--intent", "CAS",
                              "--type", "fix", "--origin", "DECOMP#CAS")
        self.run_work("start", first["work_id"], "--operation-id", "legacy-start-001")
        current = board.read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = work.main(["complete", first["work_id"],
                              "--operation-id", "legacy-complete-stale",
                              "--expected-model-sha256", first["board_sha256"]])
        self.assertEqual(code, 1)
        refusal = json.loads(output.getvalue())
        self.assertEqual(refusal["code"], "REVISION_CONFLICT")
        self.assertIn("conflict", refusal["error"].lower())
        self.assertEqual(board.read_bytes(), current)

    def test_origin_retry_repairs_archived_work_attachment(self) -> None:
        self.client.call("create", {"operation_id": "cli-repair-spec-001", "kind": "spec",
                                    "artifact_id": "SPEC-REPAIR", "slug": "repair", "title": "Repair",
                                    "summary": "Outcome"})
        self.client.call("create", {"operation_id": "cli-repair-plan-001", "kind": "plan",
                                    "artifact_id": "PLAN-REPAIR", "slug": "repair", "title": "Repair plan",
                                    "summary": "Steps", "spec_id": "SPEC-REPAIR"})
        original = self.run_work("create", "--title", "Promoted", "--intent", "Attach after interruption",
                                 "--type", "fix", "--origin", "DECOMP-CLI#WORK-REPAIR")
        archived = self.run_work("archive", original["work_id"], "--operation-id", "cli-repair-archive-001")
        repaired = self.run_work("create", "--title", "Promoted", "--intent", "Attach after interruption",
                                 "--type", "fix", "--origin", "DECOMP-CLI#WORK-REPAIR",
                                 "--spec-id", "SPEC-REPAIR", "--plan-id", "PLAN-REPAIR")
        self.assertEqual(repaired["work_id"], original["work_id"])
        self.assertEqual((repaired["state"], repaired["check_status"]), ("archived", "unknown"))
        self.assertEqual((repaired["spec_id"], repaired["plan_id"]), ("SPEC-REPAIR", "PLAN-REPAIR"))
        self.assertEqual(repaired["revision"], archived["revision"] + 1)
        self.assertTrue(repaired["attachment_repaired"])
        replay = self.run_work("create", "--title", "Promoted", "--intent", "Attach after interruption",
                               "--type", "fix", "--origin", "DECOMP-CLI#WORK-REPAIR",
                               "--spec-id", "SPEC-REPAIR", "--plan-id", "PLAN-REPAIR")
        self.assertEqual(replay["model_sha256"], repaired["model_sha256"])

    def test_update_requires_replay_identity_to_preserve_later_edit(self) -> None:
        created = self.run_work("create", "--title", "Initial", "--intent", "Preserve later edit",
                                "--type", "fix", "--operation-id", "cli-update-create-001")
        work_id = created["work_id"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = work.main(["rename", work_id, "--title", "First rename"])
        self.assertEqual(code, 1)
        self.assertIn("--operation-id", json.loads(output.getvalue())["error"])
        self.assertEqual(self.run_work("get", work_id)["title"], "Initial")
        expected = ("--expected-revision", str(created["revision"]),
                    "--expected-model-sha256", created["model_sha256"])
        first = self.run_work("rename", work_id, "--title", "First rename",
                              "--operation-id", "cli-update-rename-001", *expected)
        self.run_work("rename", work_id, "--title", "Later rename",
                      "--operation-id", "cli-update-rename-002")
        replay = self.run_work("rename", work_id, "--title", "First rename",
                               "--operation-id", "cli-update-rename-001", *expected)
        self.assertEqual(replay["model_sha256"], first["model_sha256"])
        self.assertEqual(self.run_work("get", work_id)["title"], "Later rename")

    def test_versioned_stdin_request_uses_only_native_work_operations(self) -> None:
        def invoke(payload: str) -> tuple[int, dict]:
            output = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(payload)), contextlib.redirect_stdout(output):
                code = work.main(["--request", "-"])
            return code, json.loads(output.getvalue())

        create = {"schema": "codearbiter.work-request/0.1.0", "operation": "work-create",
                  "request": {"operation_id": "cli-json-create-001", "title": "JSON work",
                              "intent": "One semantic call", "work_type": "fix"}}
        code, first = invoke(json.dumps(create))
        self.assertEqual(code, 0, first)
        code, replay = invoke(json.dumps(create))
        self.assertEqual(code, 0, replay)
        self.assertEqual(first["work_id"], replay["work_id"])
        code, selected = invoke(json.dumps({"schema": create["schema"], "operation": "work-get",
                                            "request": {"work_id": first["work_id"]}}))
        self.assertEqual(code, 0, selected)
        self.assertEqual(selected["title"], "JSON work")

        code, refused = invoke(json.dumps({"schema": create["schema"], "operation": "recover",
                                           "request": {}}))
        self.assertEqual(code, 1)
        self.assertIn("work operation", refused["error"])
        code, refused = invoke(json.dumps({"schema": create["schema"], "operation": [],
                                           "request": {}}))
        self.assertEqual(code, 1)
        self.assertIn("work operation", refused["error"])
        code, refused = invoke("x" * 65537)
        self.assertEqual(code, 1)
        self.assertIn("64 KiB", refused["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
