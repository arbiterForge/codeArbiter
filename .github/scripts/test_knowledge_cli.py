#!/usr/bin/env python3
"""Exercise HTML knowledge through the installed knowledge.py helper.

Covers the context-and-decomposition acceptance scenarios that run through
the host helper rather than the engine alone: greenfield initialization with
unknowns, relevant lookup, explicit Markdown conversion, and idempotent promotion.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_artifact_authoring import build_installation

CONTEXT = ".codearbiter/" + "CONTEXT.md"


class KnowledgeCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner, cls.installation = build_installation()
        cls.plugin = cls.installation.parent.parent

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ca-knowledge-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        self.env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "CLAUDE_PROJECT_DIR": str(self.root)}

    def script(self, name, *arguments, success=True):
        result = subprocess.run([sys.executable, "-B", str(self.plugin / "hooks" / name), *arguments],
                                cwd=self.root, env=self.env, capture_output=True, encoding="utf-8", timeout=120)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def knowledge(self, *arguments, success=True):
        result = self.script("knowledge.py", *arguments, success=success)
        return json.loads(result.stdout)

    def scaffold(self, *extra):
        self.script("init-codearbiter.py", "--root", str(self.root), *extra)

    def test_greenfield_saves_unknowns_and_initializes_structurally(self):
        self.scaffold()
        context = (self.root / CONTEXT).read_text(encoding="utf-8")
        self.assertIn("context-format: html\n", context)
        self.assertEqual(self.knowledge("format")["format"], "html")
        created = self.knowledge("create-missing")["created"]
        self.assertEqual(sorted(created), ["CTX-CODE-MAP", "CTX-CODING-STANDARDS", "CTX-PROJECT",
                                           "CTX-SECURITY-CONTROLS", "CTX-TECH-STACK", "DECOMP-PROJECT"])
        self.assertEqual(self.knowledge("create-missing")["created"], [])
        unknown = {"type": "fact", "title": "Database", "statement": "Not decided yet.", "basis": "unknown",
                   "scope": {"paths": []}, "related_refs": [], "source_refs": []}
        first = self.knowledge("add", "tech-stack", "--record", json.dumps(unknown))
        again = self.knowledge("add", "tech-stack", "--record", json.dumps(unknown))
        self.assertEqual((first["record"], again["reused"]), ("FACT-001", True))
        self.knowledge("initialize")
        context = (self.root / CONTEXT).read_text(encoding="utf-8")
        self.assertIn("arbiter: enabled\n", context)
        self.assertIn("<!--INITIALIZED-->", context)
        self.assertEqual(self.knowledge("read", "tech-stack", "FACT-001")["records"][0]["basis"], "unknown")
        self.assertFalse((self.root / ".codearbiter/.artifacts/receipts").exists())

    def test_relevant_lookup_returns_scoped_records_and_unrun_commands(self):
        self.scaffold()
        self.knowledge("create-missing")
        command = {"type": "command", "title": "Unit tests", "statement": "Runs the suite.", "basis": "proposed",
                   "scope": {"paths": []}, "related_refs": [], "source_refs": [],
                   "command": {"argv": ["npm", "test"], "cwd": ".", "purpose": "test", "run_state": "unrun"}}
        auth = {"type": "constraint", "title": "Tokens", "statement": "Never log session tokens.", "basis": "user-reported",
                "scope": {"paths": ["src/auth/**"]}, "related_refs": [], "source_refs": []}
        billing = {"type": "constraint", "title": "Cards", "statement": "Card data stays in the vault.", "basis": "user-reported",
                   "scope": {"paths": ["billing/**"]}, "related_refs": [], "source_refs": []}
        self.knowledge("add", "tech-stack", "--record", json.dumps(command))
        self.knowledge("add", "security-controls", "--record", json.dumps(auth))
        self.knowledge("add", "security-controls", "--record", json.dumps(billing))
        found = self.knowledge("relevant", "src/auth/session.ts")
        refs = {item["ref"] for item in found["knowledge"]}
        self.assertEqual(refs, {"CTX-TECH-STACK#CMD-001", "CTX-SECURITY-CONTROLS#CON-001"})
        self.assertNotIn("requires_actor_check", json.dumps(found))
        commands = self.knowledge("commands", "--purpose", "test")["commands"]
        self.assertEqual(commands[0]["command"]["run_state"], "unrun")

    def test_add_keeps_distinct_commands_with_the_same_summary(self):
        self.scaffold()
        self.knowledge("create-missing")
        first = {"type": "command", "title": "Tests", "statement": "Run tests.", "basis": "proposed",
                 "scope": {"paths": []}, "related_refs": [], "source_refs": [],
                 "command": {"argv": ["npm", "test"], "cwd": "site", "purpose": "test", "run_state": "unrun"}}
        second = json.loads(json.dumps(first))
        second["command"] = {"argv": ["go", "test", "./..."], "cwd": "core/artifacts",
                             "purpose": "test", "run_state": "unrun"}
        added = self.knowledge("add", "tech-stack", "--record", json.dumps(first))
        distinct = self.knowledge("add", "tech-stack", "--record", json.dumps(second))
        self.assertFalse(distinct["reused"], "a distinct command was silently discarded")
        self.assertNotEqual(added["record"], distinct["record"])
        self.assertTrue(self.knowledge("add", "tech-stack", "--record", json.dumps(second))["reused"])

    def test_add_batches_records_and_reuses_exact_retry(self):
        self.scaffold()
        self.knowledge("create-missing")
        records = [{"type": "fact", "title": f"Runtime {n}", "statement": f"Node {n}.",
                    "basis": "user-reported", "scope": {"paths": []},
                    "related_refs": [], "source_refs": []} for n in (22, 24)]
        first = self.knowledge("add", "tech-stack", "--record", json.dumps(records))
        self.assertEqual([item["record"] for item in first["records"]], ["FACT-001", "FACT-002"])
        again = self.knowledge("add", "tech-stack", "--record", json.dumps(records))
        self.assertTrue(all(item["reused"] for item in again["records"]))

    def test_markdown_conversion_requires_records_and_unchanged_sources(self):
        self.scaffold("--format", "markdown")
        state = self.root / ".codearbiter"
        self.assertNotIn("context-format", (state / "CONTEXT.md").read_text(encoding="utf-8"))
        (state / "tech-stack.md").write_text("# Tech stack\n\n## Commands\n\nnpm test\n", encoding="utf-8")
        (state / "security-controls.md").write_text(
            "# Security controls\n\n<!-- deploy-paths -->\n+ ops/**\n<!-- /deploy-paths -->\n", encoding="utf-8")
        self.assertEqual(self.knowledge("format")["format"], "markdown")
        prepared = self.knowledge("convert")
        self.assertTrue((state / "tech-stack.md").exists(), "preparation converted the repository")
        self.assertIn(".codearbiter/tech-stack.md", prepared["read"])
        refused = self.knowledge("convert", "--finish", "0" * 64, success=False)
        self.assertFalse(refused["ok"])
        empty_checklist = [{"section": part["id"], "records": []} for part in prepared["sections"]]
        refused = self.knowledge("convert", "--finish", prepared["token"], "--coverage",
                                 json.dumps(empty_checklist), success=False)
        self.assertFalse(refused["ok"], "a meaningful Markdown section had no mapped record")

        def checklist(inventory):
            slug = {"CTX-PROJECT": "project", "CTX-TECH-STACK": "tech-stack",
                    "CTX-CODE-MAP": "code-map", "CTX-CODING-STANDARDS": "coding-standards",
                    "CTX-SECURITY-CONTROLS": "security-controls", "DECOMP-PROJECT": "decomposition"}
            rows = []
            for part in inventory["sections"]:
                refs = []
                if part["content"]:
                    source = (self.root / part["source"]).read_bytes()[part["start"]:part["end"]].decode("utf-8")
                    note = {"title": part["heading"] or "Preamble", "text": source,
                            "basis": "source-observed", "origin": {"path": part["source"],
                            "start": part["start"], "end": part["end"]}}
                    added = self.knowledge("add", slug[part["artifact_id"]], "--collection", "notes",
                                           "--record", json.dumps(note))
                    refs = [part["artifact_id"] + "#" + added["record"]]
                rows.append({"section": part["id"], "records": refs})
            return rows

        coverage = checklist(prepared)
        changed = state / "tech-stack.md"
        changed.write_text(changed.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        refused = self.knowledge("convert", "--finish", prepared["token"], "--coverage",
                                 json.dumps(coverage), success=False)
        self.assertFalse(refused["ok"], "changed Markdown invalidated the read token")
        prepared = self.knowledge("convert")
        self.knowledge("convert", "--finish", prepared["token"], "--coverage", json.dumps(checklist(prepared)))
        self.assertEqual(self.knowledge("format")["format"], "html")
        self.assertFalse((state / "tech-stack.md").exists())
        self.assertIn("<!-- deploy-paths -->\n+ ops/**\n<!-- /deploy-paths -->",
                      (state / "security-controls.md").read_text(encoding="utf-8"))
        outline = self.knowledge("read", "tech-stack")["records"]
        self.assertEqual([r["id"] for r in outline if r["kind"] == "notes"], ["NOTE-001", "NOTE-002"])

    def test_large_markdown_inventory_is_paged(self):
        self.scaffold("--format", "markdown")
        source = self.root / ".codearbiter/tech-stack.md"
        source.write_text("# Tech stack\n" + "".join(
            f"\n## Rule {i}\nKeep the rule.\n" for i in range(300)), encoding="utf-8")
        prepared = self.knowledge("convert")
        self.assertGreaterEqual(len([part for part in prepared["sections"]
                                     if part["source"] == ".codearbiter/tech-stack.md"]), 301)

    def test_promotion_is_idempotent_across_archive(self):
        self.scaffold()
        self.knowledge("create-missing")
        work = {"type": "work_item", "title": "Build the login form", "statement": "MVP login.", "basis": "user-reported",
                "scope": {"paths": []}, "related_refs": [], "source_refs": []}
        self.knowledge("add", "decomposition", "--record", json.dumps(work))
        promoted = self.knowledge("promote", "WORK-001")
        self.assertRegex(promoted["work_id"], r"^WORK-[A-F0-9]{32}$")
        board = (self.root / ".codearbiter/open-tasks.md").read_text(encoding="utf-8")
        self.assertEqual(board.count("(from DECOMP-PROJECT#WORK-001)"), 1)
        # The task finishes and is archived; a delayed retry must not re-add it.
        self.script("taskwrite.py", "start", "Build the login form")
        self.script("taskwrite.py", "done", "Build the login form")
        self.script("taskwrite.py", "archive", "Build the login form")
        # The board write can succeed while the decomposition back-reference
        # is interrupted. A retry after archival must repair that reference.
        self.knowledge("update", "decomposition", "WORK-001", "--fields",
                       json.dumps({"promotion": None}))
        retried = self.knowledge("promote", "WORK-001")
        self.assertEqual(retried["work_id"], promoted["work_id"])
        self.assertTrue(retried["board"].startswith("already promoted:"), retried)
        board = (self.root / ".codearbiter/open-tasks.md").read_text(encoding="utf-8")
        self.assertNotIn("(from DECOMP-PROJECT#WORK-001)", board)
        record = self.knowledge("read", "decomposition", "WORK-001")["records"][0]
        self.assertEqual(record["promotion"]["origin"], "DECOMP-PROJECT#WORK-001")
        self.assertEqual(record["promotion"]["work_id"], promoted["work_id"])

        # Old decomposition pages carry a title-based board_id. Reading and
        # retrying them upgrades the back-reference without another board row.
        self.knowledge("update", "decomposition", "WORK-001", "--fields",
                       json.dumps({"promotion": {"board_id": "Build the login form",
                                                 "origin": "DECOMP-PROJECT#WORK-001"}}))
        migrated = self.knowledge("promote", "WORK-001")
        self.assertEqual(migrated["work_id"], promoted["work_id"])
        record = self.knowledge("read", "decomposition", "WORK-001")["records"][0]
        self.assertEqual(record["promotion"]["work_id"], promoted["work_id"])

    def test_promotion_uses_native_work_when_no_legacy_board_owns_project(self):
        self.scaffold()
        board = self.root / ".codearbiter/open-tasks.md"
        board.unlink(missing_ok=True)  # disposable fixture selects native ownership
        self.knowledge("create-missing")
        work = {"type": "work_item", "title": "Native candidate", "statement": "Track one result.",
                "basis": "user-reported", "scope": {"paths": []}, "related_refs": [], "source_refs": []}
        self.knowledge("add", "decomposition", "--record", json.dumps(work))
        first = self.knowledge("promote", "WORK-001")
        replay = self.knowledge("promote", "WORK-001")
        self.assertEqual(first["work_id"], replay["work_id"])
        self.assertEqual(first["owner"], "native")
        self.assertNotIn("board", first)
        record = self.knowledge("read", "decomposition", "WORK-001")["records"][0]
        self.assertEqual(record["promotion"]["work_id"], first["work_id"])
        self.assertFalse(board.exists())

    def test_initialized_brownfield_keeps_observation_candidate_and_identity_separate(self):
        self.scaffold()
        board = self.root / ".codearbiter/open-tasks.md"
        self.knowledge("create-missing")
        self.knowledge("initialize")
        board.unlink(missing_ok=True)  # disposable empty-board fixture selects native ownership
        before = (self.root / CONTEXT).read_bytes()
        source = self.root / "src/service.py"
        source.parent.mkdir()
        source.write_text("def run():\n    return None\n", encoding="utf-8")
        cited = self.knowledge("add", "decomposition", "--collection", "sources", "--record",
                               json.dumps({"title": "Service source", "type": "repository", "url": None,
                                           "locator": "src/service.py", "note": "Observed brownfield source"}))
        observed = self.knowledge("add", "decomposition", "--record", json.dumps({
            "type": "capability", "title": "Service entry point", "statement": "Source defines run().",
            "basis": "source-observed", "scope": {"paths": ["src/service.py"]},
            "related_refs": [], "source_refs": [cited["record"]]}))
        candidate = self.knowledge("add", "decomposition", "--record", json.dumps({
            "type": "work_item", "title": "Review service failure path",
            "statement": "Check the service failure path before choosing a change.",
            "basis": "proposed", "scope": {"paths": ["src/service.py"]},
            "related_refs": [observed["record"]], "source_refs": [cited["record"]]}))
        self.assertEqual((self.root / CONTEXT).read_bytes(), before)
        self.assertFalse(board.exists())
        self.assertFalse((self.root / ".codearbiter/work/project.json").exists(),
                         "observation silently published a candidate")
        promoted = self.knowledge("promote", candidate["record"])
        self.assertEqual(promoted["owner"], "native")
        self.assertEqual(self.knowledge("promote", candidate["record"])["work_id"], promoted["work_id"])
        self.assertEqual((self.root / CONTEXT).read_bytes(), before)
        self.assertEqual(self.knowledge("read", "decomposition", observed["record"])["records"][0]["basis"],
                         "source-observed")

    def test_initialized_brownfield_preserves_legacy_backlog_through_selected_adoption(self):
        self.scaffold()
        self.knowledge("create-missing")
        self.knowledge("initialize")
        context = (self.root / CONTEXT).read_bytes()
        board = self.root / ".codearbiter/open-tasks.md"
        self.script("taskwrite.py", "add", "Keep the pre-existing task")
        original_board = board.read_bytes()
        candidate = self.knowledge("add", "decomposition", "--record", json.dumps({
            "type": "work_item", "title": "Inspect another path", "statement": "Review the observed gap.",
            "basis": "proposed", "scope": {"paths": []}, "related_refs": [], "source_refs": []}))
        self.assertEqual(board.read_bytes(), original_board, "candidate publication changed the legacy backlog")
        self.assertFalse((self.root / ".codearbiter/work/project.json").exists())

        promoted = self.knowledge("promote", candidate["record"])
        self.assertEqual(promoted["owner"], "legacy")
        self.assertIn(b"Keep the pre-existing task", board.read_bytes())
        self.assertIn(b"Inspect another path", board.read_bytes())
        adopted = json.loads(self.script("work.py", "adopt", "--operation-id", "brownfield-adopt-001").stdout)
        self.assertEqual(adopted["adopted_count"], 2)
        self.assertFalse(board.exists())
        replay = self.knowledge("promote", candidate["record"])
        self.assertEqual(replay["work_id"], promoted["work_id"])
        self.assertEqual((self.root / CONTEXT).read_bytes(), context)
        self.assertEqual(json.loads(self.script("work.py", "get", promoted["work_id"]).stdout)["title"],
                         "Inspect another path")

    def test_initialized_brownfield_partial_acquisition_keeps_unknowns_and_candidates_local(self):
        self.scaffold()
        self.knowledge("create-missing")
        self.knowledge("initialize")
        board = self.root / ".codearbiter/open-tasks.md"
        board.unlink(missing_ok=True)  # disposable no-backlog native fixture
        context = (self.root / CONTEXT).read_bytes()
        decision = self.root / ".codearbiter/decisions/ADR-0001.md"
        decision.parent.mkdir(exist_ok=True)
        decision.write_bytes(b"# Existing decision\nHuman rationale stays here.\n")
        prior = self.knowledge("add", "decomposition", "--record", json.dumps({
            "type": "question", "title": "Deployment target", "statement": "Deployment target is not known.",
            "basis": "unknown", "scope": {"paths": []}, "related_refs": [], "source_refs": [],
            "status": "open", "answer": None}))
        denied = self.knowledge("add", "decomposition", "--record", json.dumps({
            "type": "component", "title": "Restricted service", "statement": "Source inspection was denied; behavior is unknown.",
            "basis": "unknown", "scope": {"paths": ["src/restricted/**"]},
            "related_refs": [prior["record"]], "source_refs": []}))
        phase = self.knowledge("add", "decomposition", "--record", json.dumps({
            "type": "phase", "title": "Inspect accessible services", "statement": "Inspect permitted paths before selecting a change.",
            "basis": "proposed", "scope": {"paths": ["src/public/**"]},
            "related_refs": [denied["record"]], "source_refs": []}))
        work = {"type": "work_item", "title": "Review public service", "statement": "Review one accessible path.",
                "basis": "proposed", "scope": {"paths": ["src/public/**"]},
                "related_refs": [phase["record"]], "source_refs": []}
        candidate = self.knowledge("add", "decomposition", "--record", json.dumps(work))
        # A second process sees the same saved candidate after interrupted synthesis.
        resumed = self.knowledge("add", "decomposition", "--record", json.dumps(work))
        self.assertEqual(resumed["record"], candidate["record"])
        self.assertTrue(resumed["reused"])
        self.assertEqual((self.root / CONTEXT).read_bytes(), context)
        self.assertEqual(decision.read_bytes(), b"# Existing decision\nHuman rationale stays here.\n")

        self.assertFalse((self.root / ".codearbiter/work/project.json").exists(),
                         "candidate or interrupted synthesis published work")
        self.assertFalse(board.exists(), "acquisition recreated an empty legacy backlog")
        self.assertEqual(self.knowledge("read", "decomposition", denied["record"])["records"][0]["basis"],
                         "unknown")
        promoted = self.knowledge("promote", candidate["record"])
        self.assertEqual(self.knowledge("promote", candidate["record"])["work_id"], promoted["work_id"])
        self.assertEqual((self.root / CONTEXT).read_bytes(), context)
        self.assertEqual(decision.read_bytes(), b"# Existing decision\nHuman rationale stays here.\n")

    def test_initialized_brownfield_duplicate_external_candidates_need_selected_promotion(self):
        self.scaffold()
        self.knowledge("create-missing")
        self.knowledge("initialize")
        board = self.root / ".codearbiter/open-tasks.md"
        board.unlink(missing_ok=True)
        source = self.knowledge("add", "decomposition", "--collection", "sources", "--record",
                                json.dumps({"title": "Existing issue", "type": "repository",
                                            "url": "https://github.com/example/project/issues/7",
                                            "locator": "example/project#7",
                                            "note": "Observed external candidate; identity needs review"}))
        candidates = []
        for title in ("Investigate issue symptom", "Review issue reproduction"):
            result = self.knowledge("add", "decomposition", "--record", json.dumps({
                "type": "work_item", "title": title, "statement": "Candidate from an existing issue.",
                "basis": "proposed", "scope": {"paths": []}, "related_refs": [],
                "source_refs": [source["record"]]}))
            candidates.append(result["record"])
        self.assertNotEqual(*candidates)
        self.assertFalse(board.exists())
        self.assertFalse((self.root / ".codearbiter/work/project.json").exists())
        self.assertTrue(all("promotion" not in self.knowledge("read", "decomposition", record)["records"][0]
                            for record in candidates))
        selected = self.knowledge("promote", candidates[0])
        self.assertEqual(self.knowledge("promote", candidates[0])["work_id"], selected["work_id"])
        self.assertNotIn("promotion", self.knowledge("read", "decomposition", candidates[1])["records"][0])


    def git(self, *arguments):
        subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        *arguments], cwd=self.root, check=False, capture_output=True)

    def test_stale_includes_unstaged_and_staged_source_changes(self):
        self.scaffold()
        self.knowledge("create-missing")
        source = self.root / "src" / "service.py"
        source.parent.mkdir()
        source.write_text("version = 1\n", encoding="utf-8")
        citation = {"title": "Service source", "type": "repository", "url": None,
                    "locator": "src/service.py", "note": "Observed source path"}
        self.knowledge("add", "tech-stack", "--collection", "sources", "--record", json.dumps(citation))
        observed = {"type": "fact", "title": "Service", "statement": "Service source exists.",
                    "basis": "source-observed", "scope": {"paths": ["src/**"]},
                    "related_refs": [], "source_refs": ["SRC-001"]}
        self.knowledge("add", "tech-stack", "--record", json.dumps(observed))
        self.git("add", "-A")
        self.git("commit", "-qm", "baseline")
        self.knowledge("rebaseline", "tech-stack")

        source.write_text("version = 2\n", encoding="utf-8")
        report = self.knowledge("stale", "tech-stack")["documents"][0]
        self.assertTrue(report["stale"], report)
        self.assertEqual(report["stale"][0]["changed_paths"], ["src/service.py"])

        self.git("add", "src/service.py")
        report = self.knowledge("stale", "tech-stack")["documents"][0]
        self.assertEqual(report["stale"][0]["changed_paths"], ["src/service.py"])

        self.git("commit", "-qm", "first source change")
        extra = self.root / "src" / "extra.py"
        extra.write_text("version = 1\n", encoding="utf-8")
        report = self.knowledge("stale", "tech-stack")["documents"][0]
        self.assertEqual(report["stale"][0]["changed_paths"], ["src/extra.py", "src/service.py"])
        self.git("add", "src/extra.py")
        report = self.knowledge("stale", "tech-stack")["documents"][0]
        self.assertEqual(report["stale"][0]["changed_paths"], ["src/extra.py", "src/service.py"])

    def test_git_conflict_merges_record_by_record(self):
        self.scaffold()
        self.knowledge("create-missing")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.git("checkout", "-qb", "other")
        fact = {"type": "fact", "title": "Queue", "statement": "Redis streams.", "basis": "user-reported",
                "scope": {"paths": []}, "related_refs": [], "source_refs": []}
        self.knowledge("add", "tech-stack", "--record", json.dumps(fact))
        self.git("commit", "-qam", "theirs")
        self.git("checkout", "-q", "-")
        fact["title"], fact["statement"] = "Cache", "Memcached."
        self.knowledge("add", "tech-stack", "--record", json.dumps(fact))
        self.git("commit", "-qam", "ours")
        self.git("merge", "other")
        page = ".codearbiter/context/tech-stack.html"
        self.assertIn("<<<<<<<", (self.root / page).read_text(encoding="utf-8"))
        merged = self.knowledge("merge-conflict", page)
        self.assertTrue(merged["merged"], merged)
        titles = sorted(r["title"] for r in self.knowledge("read", "tech-stack", "FACT-001", "FACT-002")["records"])
        self.assertEqual(titles, ["Cache", "Queue"])


if __name__ == "__main__":
    unittest.main()
