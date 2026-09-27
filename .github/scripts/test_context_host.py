#!/usr/bin/env python3
"""Source-contract tests for context-onboarding scout containment.

These checks do not qualify a live child or turn a host capability claim into
observed read-only enforcement. That requires an authorized host exercise.
"""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from pathlib import PurePosixPath
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core/pysrc"))
import _contextselectlib as selector
import _readinjectlib as readinject
DESCRIPTORS = ROOT / "tools/host_descriptors.py"
_spec = importlib.util.spec_from_file_location("host_descriptors", DESCRIPTORS)
_hosts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hosts)


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


NATIVE_CATALOG = ROOT / ".github/fixtures/context-onboarding/host-cells.json"
NATIVE_FORMAT = "codearbiter.native-loading-cells/0.1"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _native_rel(path: str) -> str:
    if not isinstance(path, str) or not path or "\\" in path or ":" in path:
        raise ValueError("native fixture path must be POSIX relative")
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in path.split("/")):
        raise ValueError("native fixture path escapes isolated repository")
    return str(pure)


def _validate_native_rule(path: str, content: str) -> None:
    if not path.startswith(".claude/rules/"):
        return
    lines = content.splitlines()
    if (len(lines) < 5 or lines[:2] != ["---", "paths:"] or
            lines[2] != "  - 'packages/a/**'" or lines[3] != "---"):
        raise ValueError("path rule lacks bounded paths frontmatter")


def _native_hook_command(argv: list[str]) -> str:
    """Render the command string consumed by Claude's command hook."""
    if os.name == "nt":
        return subprocess.list2cmdline([arg.replace("\\", "/") for arg in argv])
    return shlex.join(argv)


def load_native_catalog() -> dict:
    """Read an inert catalog; loading it never invokes a host."""
    catalog = json.loads(NATIVE_CATALOG.read_text(encoding="utf-8"))
    if catalog.get("format") != NATIVE_FORMAT or not isinstance(catalog.get("cells"), list):
        raise ValueError("unsupported native loading catalog")
    ids = set()
    for cell in catalog["cells"]:
        if set(cell) != {"id", "host", "profile", "availability", "phase", "actor",
                         "target", "files", "required", "excluded"}:
            raise ValueError("native loading cell has unexpected fields")
        if cell["id"] in ids or not cell["id"].replace("-", "").isalnum():
            raise ValueError("duplicate or unsafe native loading cell id")
        ids.add(cell["id"])
        if cell["availability"] not in ("selected", "unselected", "disabled"):
            raise ValueError("unsupported native loading availability")
        _native_rel(cell["target"])
        if not isinstance(cell["files"], dict) or not cell["files"]:
            raise ValueError("native loading cell has no files")
        for path, content in cell["files"].items():
            _native_rel(path)
            if not isinstance(content, str) or not content:
                raise ValueError("native loading file must have inert text")
            _validate_native_rule(path, content)
        for key in ("required", "excluded"):
            if not isinstance(cell[key], list) or not all(
                    isinstance(marker, str) and marker.startswith("T039_")
                    for marker in cell[key]):
                raise ValueError("native loading sentinels must be inert and explicit")
        if set(cell["required"]) & set(cell["excluded"]):
            raise ValueError("native loading sentinel is both required and excluded")
        file_text = "\n".join(cell["files"].values())
        if any(marker not in file_text for marker in cell["required"] + cell["excluded"]):
            raise ValueError("native loading sentinel is absent from staged files")
    return catalog


def prepare_native_cell(cell: dict, base: Path) -> dict:
    """Stage only declared harmless files under a fresh home and repository."""
    _native_rel(cell["id"])
    files = {_native_rel(path): content for path, content in cell["files"].items()}
    _native_rel(cell["target"])
    for rel, content in files.items():
        _validate_native_rule(rel, content)
    base.mkdir(parents=True, exist_ok=True)
    case_dir = base / cell["id"]
    case_dir.mkdir()  # Existing cells, including human-owned files, are preserved.
    home, repo = case_dir / "home", case_dir / "repo"
    home.mkdir()
    repo.mkdir()
    digests = {}
    for rel, content in files.items():
        dest = repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("x", encoding="utf-8", newline="\n") as out:
            out.write(content)
        digests[rel] = sha256_file(dest)
    target = repo / cell["target"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(exist_ok=False)
    settings = case_dir / "settings.json"
    event_log = case_dir / "instructions-loaded.jsonl"
    settings.write_text(json.dumps({"hooks": {"InstructionsLoaded": [{"hooks": [{
        "type": "command", "command": _native_hook_command([
            sys.executable, str(Path(__file__).resolve()), "--capture-native-event",
            str(event_log)]),
    }]}]}}, indent=2) + "\n", encoding="utf-8")
    template = {
        "note": "Template only: verify authorization, host version, settings and isolation before invocation.",
        "cwd": str(repo), "home": str(home), "target": str(target),
        "minimum_cli_version_for_restricted": "2.1.248",
        "environment_template": {"HOME": str(home), "USERPROFILE": str(home),
                                 "XDG_CONFIG_HOME": str(home / ".config")},
        "argv": ["claude", "--restricted", "--settings", str(settings), "-p",
                 "--output-format", "stream-json", "--verbose", "--include-hook-events",
                 "--max-turns", "1", "--max-budget-usd", "<AUTHORIZED_BUDGET_USD>",
                 "<AUTHORIZED_READ_ONLY_PROMPT>"],
        "limitations": ["No host is invoked by preparation.",
                        "--init-only event completeness is unobserved.",
                        "Events report CLAUDE.md/rules loads, not direct AGENTS.md loads.",
                        "Native Windows Bash sandboxing is not established by this template."],
    }
    (case_dir / "collector-template.json").write_text(
        json.dumps(template, indent=2) + "\n", encoding="utf-8")
    return {"id": cell["id"], "home": str(home), "repo": str(repo),
            "files": digests, "settings": str(settings), "event_log": str(event_log),
            "collector_template": str(case_dir / "collector-template.json")}


def synthetic_native_observation(cell: dict, prepared: dict, text: str | None) -> dict:
    """Construct unit data explicitly labeled synthetic, never host evidence."""
    return {"host": cell["host"], "profile": cell["profile"], "version": "synthetic",
            "source_kind": "synthetic", "file_digests": dict(prepared["files"]),
            "input_text": text, "input_complete": text is not None, "load_events": []}


def assess_native_cell(cell: dict, prepared: dict, observation: dict) -> dict:
    """Assess supplied capture; never emit a host qualification or approval."""
    paths = []
    repo = Path(prepared["repo"]).resolve()
    for event in observation.get("load_events", []):
        if not isinstance(event, dict) or event.get("hook_event_name") != "InstructionsLoaded":
            raise ValueError("invalid native load event")
        if event.get("memory_type") not in ("User", "Project", "Local", "Managed"):
            raise ValueError("invalid native load event scope")
        if event.get("load_reason") not in ("session_start", "nested_traversal",
                                            "path_glob_match", "include", "compact"):
            raise ValueError("invalid native load reason")
        path = Path(event.get("file_path", ""))
        if not path.is_absolute():
            raise ValueError("native load event path is not absolute")
        try:
            relative = path.resolve().relative_to(repo).as_posix()
        except ValueError as exc:
            raise ValueError("native load event escaped isolated repository") from exc
        paths.append(relative)
    result = {"id": cell["id"], "sentinels": "unverified", "qualification": "unverified",
              "provenance": observation.get("source_kind", "unknown"),
              "observed_event_paths": paths, "eager_load_prevented": False,
              "scope": "loader_only", "reason": "effective host input not completely observed"}
    if cell["availability"] == "unselected":
        result.update(sentinels="not_applicable", reason="projection unselected")
        return result
    if cell["availability"] == "disabled":
        result.update(reason="capability disabled; host behavior unverified")
        return result
    if (observation.get("host") != cell["host"] or
            observation.get("profile") != cell["profile"] or
            not observation.get("version")):
        result.update(sentinels="contradicted", reason="host/profile/version binding mismatch")
        return result
    if observation.get("file_digests") != prepared["files"]:
        result.update(sentinels="contradicted", reason="fixture bytes changed")
        return result
    text = observation.get("input_text")
    if observation.get("input_complete") is not True or not isinstance(text, str):
        return result
    missing = [marker for marker in cell["required"] if marker not in text]
    leaked = [marker for marker in cell["excluded"] if marker in text]
    stale = "T039_STALE_NATIVE_A" in text
    if missing or leaked or stale:
        result.update(sentinels="contradicted", reason="missing, excluded or stale sentinel in supplied input",
                      missing=missing, leaked=leaked, stale_loaded=stale)
    else:
        result.update(sentinels="matched", reason="sentinels match supplied input; independent host proof pending")
    return result


def capture_native_event(destination: Path, raw: str) -> None:
    """Append one bounded raw hook event to the prepared cell's local log."""
    if (destination.name != "instructions-loaded.jsonl" or
            not (destination.parent / "home").is_dir() or
            not (destination.parent / "repo").is_dir() or destination.is_symlink()):
        raise ValueError("event destination is not a prepared isolated cell")
    if len(raw.encode("utf-8")) > 16_384:
        raise ValueError("native event exceeds capture bound")
    event = json.loads(raw)
    if not isinstance(event, dict) or event.get("hook_event_name") != "InstructionsLoaded":
        raise ValueError("not an InstructionsLoaded event")
    line = json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n"
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, line.encode("utf-8"))
    finally:
        os.close(descriptor)


def native_loading_main(argv: list[str]) -> int:
    """Prepare/capture/assess source fixtures; no mode launches a native host."""
    if len(argv) == 2 and argv[0] == "--prepare-native-cells":
        base = Path(argv[1])
        base.mkdir()  # Requires a new location; never adopts existing content.
        catalog = load_native_catalog()
        prepared = {cell["id"]: prepare_native_cell(cell, base)
                    for cell in catalog["cells"]}
        manifest = {"format": NATIVE_FORMAT, "catalog_sha256": sha256_file(NATIVE_CATALOG),
                    "cells": prepared, "qualification": "unverified"}
        (base / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return 0
    if len(argv) == 4 and argv[0] == "--assess-native-cells":
        base, input_path, output_path = map(Path, argv[1:])
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("catalog_sha256") != sha256_file(NATIVE_CATALOG):
            raise ValueError("native catalog changed after fixture preparation")
        raw = input_path.read_bytes()
        supplied = json.loads(raw)
        if supplied.get("format") != NATIVE_FORMAT or not isinstance(supplied.get("cases"), dict):
            raise ValueError("invalid native observation document")
        catalog = load_native_catalog()
        if set(supplied["cases"]) - set(manifest["cells"]):
            raise ValueError("unknown native observation cell")
        results = []
        event_log_sha256 = {}
        for cell in catalog["cells"]:
            prepared = manifest["cells"][cell["id"]]
            case_dir = (base / cell["id"]).resolve()
            if (Path(prepared["repo"]).resolve() != case_dir / "repo" or
                    Path(prepared["home"]).resolve() != case_dir / "home" or
                    Path(prepared["event_log"]).resolve() != case_dir / "instructions-loaded.jsonl"):
                raise ValueError("native preparation manifest path changed")
            for rel, digest in prepared["files"].items():
                _native_rel(rel)
                if sha256_file(Path(prepared["repo"]) / rel) != digest:
                    raise ValueError("native fixture changed after preparation")
            observed = dict(supplied["cases"].get(cell["id"], {}))
            event_log = Path(prepared["event_log"])
            if event_log.exists():
                if observed.get("load_events"):
                    raise ValueError("native events must come from one retained source")
                event_bytes = event_log.read_bytes()
                if len(event_bytes) > 1_048_576:
                    raise ValueError("native event log exceeds bound")
                observed["load_events"] = [json.loads(line) for line in event_bytes.splitlines()]
                event_log_sha256[cell["id"]] = hashlib.sha256(event_bytes).hexdigest()
            results.append(assess_native_cell(cell, prepared, observed))
        assessment = {"format": NATIVE_FORMAT, "qualification": "unverified",
                      "scope": "loader_only", "source_observation_sha256": hashlib.sha256(raw).hexdigest(),
                      "event_log_sha256": event_log_sha256,
                      "results": results,
                      "note": "Assessment of supplied data, not trusted host collection or task correctness."}
        with output_path.open("x", encoding="utf-8") as out:
            json.dump(assessment, out, indent=2)
            out.write("\n")
        return 0
    if len(argv) == 2 and argv[0] == "--capture-native-event":
        capture_native_event(Path(argv[1]), sys.stdin.read())
        return 0
    raise ValueError("unknown native fixture mode")


class ContextScoutContainmentSourceTest(unittest.TestCase):
    """Bound the new context path without changing the legacy scout consumer."""

    def shortDescription(self):
        return None

    def test_t024_scout_containment_profile_positive_controls(self):
        """Require an enforced profile, distinct children and report-only delivery."""
        workflow = _text("core/surface/skills/context-creation/SKILL.md")
        scout = _text("core/surface/agents/scout.md")
        hosts = {host.name: host for host in _hosts.load_host_descriptors(str(ROOT))}

        self.assertEqual(set(hosts), {"claude", "codex", "pi"})
        self.assertFalse(hosts["codex"].capabilities["agents"])
        self.assertTrue(hosts["claude"].capabilities["agents"])
        self.assertTrue(hosts["pi"].capabilities["agents"])
        self.assertIn("## Context-creation containment profile", workflow)
        for requirement in (
            "fresh child identity", "host-enforced read-only", "source read",
            "benign write", "denied", "bounded report", "report-only synthesis",
            "unavailable", "BLOCK before dispatch",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, workflow)
        self.assertIn("## Context-creation assignment", scout)
        self.assertIn("decision-variance", scout)
        self.assertIn("context-creation", scout)
        self.assertIn("report-only synthesis", scout)

        projections = {
            "claude": ("plugins/ca/agents/scout.md", "plugins/ca/skills/context-creation/SKILL.md"),
            "codex": ("plugins/ca-codex/agents/scout.md", "plugins/ca-codex/routines/context-creation/SKILL.md"),
            "pi": ("plugins/ca-pi/agents/scout.md", "plugins/ca-pi/routines/context-creation/SKILL.md"),
        }
        for host, (scout_path, workflow_path) in projections.items():
            with self.subTest(host=host):
                self.assertIn("## Context-creation assignment", _text(scout_path))
                self.assertIn("## Context-creation containment profile", _text(workflow_path))

    def test_t024_scout_containment_profile_negative_controls(self):
        """A writable scout label or agent capability cannot pass containment."""
        workflow = _text("core/surface/skills/context-creation/SKILL.md")
        scout = _text("core/surface/agents/scout.md")
        frontmatter = scout.split("---", 2)[1]
        self.assertIn("Bash", frontmatter)
        pi_roles = json.loads(_text("plugins/ca-pi/generated/roles.json"))
        pi_scout = next(role for role in pi_roles if role["name"] == "scout")
        self.assertIn("bash", pi_scout["tools"])
        self.assertFalse(any(role["name"] == "context-scout" for role in pi_roles))
        self.assertIn("decision-variance", scout)
        self.assertIn("MUST NOT dispatch the existing `scout` role", workflow)
        self.assertIn("Bash", workflow)
        self.assertIn("A role label", workflow)
        self.assertIn("does not qualify", workflow)
        self.assertIn("agents capability", workflow)
        self.assertIn("No inline fallback", workflow)
        self.assertIn("failed or missing report", workflow)
        self.assertIn("MUST NOT proceed to Phase 3", workflow)


class TestContextResumeEpochs(unittest.TestCase):
    def shortDescription(self):
        return None

    @staticmethod
    def packet(paths, instruction_epoch="instruction-1"):
        return {
            "admission": "requires_actor_check", "task_paths": list(paths),
            "map": [], "commands": [], "constraints": [], "unresolved": [],
            "instructions": [{"id": "ROOT", "path": "AGENTS.md", "scope": ".",
                              "epoch": instruction_epoch, "text": "Keep owner files."}],
        }

    @staticmethod
    def selected(paths):
        return selector.select_task_context(
            paths, code_map=("## Work\n- `packages/a/src` -- source A\n"
                                  "- `packages/b/src` -- source B\n"),
            provenance={"identity": "current", "coverage": "complete"},
            commands=[], constraints=[{
                "record": {"id": "SHARED", "kind": "existing_applicable",
                           "source_ref": "AGENTS.md", "scope": ".",
                           "statement": "SHARED-CONSTRAINT", "evidence_refs": ["E1"]},
                "owner": "root", "authority": "native", "epoch": "instruction-1",
                "status": "current"}],
            effective_instructions=[
                {"id": "ROOT", "path": "AGENTS.md", "scope": ".",
                 "epoch": "instruction-1", "text": "ROOT-INSTRUCTION"},
                {"id": "A", "path": "packages/a/AGENTS.md", "scope": "packages/a",
                 "epoch": "instruction-1", "text": "PACKAGE-A-INSTRUCTION"},
                {"id": "B", "path": "packages/b/AGENTS.md", "scope": "packages/b",
                 "epoch": "instruction-1", "text": "PACKAGE-B-INSTRUCTION"}],
            evidence_ids={"E1"})

    def test_t038_context_resume_epochs_positive_controls(self):
        """A fresh actor, expanded scope, changed source or worktree gets delivery."""
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as sibling:
            base = dict(actor="author-1", task_id="T-038", worktree=first,
                        source_epoch="source-a", host_epoch="compact-0")
            packet_a = self.selected(["packages/a/src/app.py"])
            first_delivery = selector.prepare_actor_delivery(packet_a, **base)
            self.assertEqual(first_delivery["action"], "deliver")
            self.assertEqual(first_delivery["attempt"]["number"], 1)
            self.assertEqual(first_delivery["observation"], "unknown")
            self.assertIn("PACKAGE-A-INSTRUCTION", first_delivery["delivery_text"])
            self.assertIn("SHARED-CONSTRAINT", first_delivery["delivery_text"])
            self.assertNotIn("PACKAGE-B-INSTRUCTION", first_delivery["delivery_text"])
            for route in ("core/surface/skills/subagent-driven-development/SKILL.md",
                          "core/surface/skills/tdd/SKILL.md",
                          "core/surface/commands/fix.md",
                          "core/surface/commands/review.md"):
                with self.subTest(route=route):
                    self.assertIn("_contextselectlib.prepare_actor_delivery", _text(route))
            attempts = [first_delivery["attempt"]]
            receipt = {"binding": first_delivery["binding"], "actor": "author-1",
                       "observed": True, "source": "host-load-event"}
            confirmed = selector.prepare_actor_delivery(
                packet_a, **base, attempts=attempts, receipt=receipt)
            self.assertEqual(confirmed["action"], "observed")
            self.assertEqual(confirmed["observation"], "reported")
            self.assertEqual(selector.prepare_actor_delivery(
                packet_a, **{**base, "actor": "reviewer-1"},
                attempts=attempts, receipt=receipt)["action"], "deliver")
            expanded = self.selected(["packages/a/src/app.py", "packages/b/src/app.py"])
            expanded_delivery = selector.prepare_actor_delivery(
                expanded, **base, attempts=attempts, receipt=receipt)
            self.assertIn("PACKAGE-B-INSTRUCTION", expanded_delivery["delivery_text"])
            self.assertIn("SHARED-CONSTRAINT", expanded_delivery["delivery_text"])
            for changed_packet, changed_args in (
                (expanded, base),
                (packet_a, {**base, "source_epoch": "source-b"}),
                (packet_a, {**base, "host_epoch": "compact-1"}),
                (packet_a, {**base, "worktree": sibling}),
                (self.packet(["packages/a/src/app.py"], "instruction-2"), base),
            ):
                with self.subTest(change=changed_args, scope=changed_packet["task_paths"]):
                    result = selector.prepare_actor_delivery(
                        changed_packet, **changed_args, attempts=attempts, receipt=receipt)
                    self.assertEqual(result["action"], "deliver")
                    self.assertEqual(result["attempt"]["number"], 1)

    def test_t038_context_resume_epochs_negative_controls(self):
        """Unknown receipt and surviving read marker never masquerade as delivery."""
        with tempfile.TemporaryDirectory() as root:
            packet = self.packet(["packages/a/src/app.py"])
            args = dict(actor="author-1", task_id="T-038", worktree=root,
                        source_epoch="source-a", host_epoch=None)
            first = selector.prepare_actor_delivery(packet, **args)
            second = selector.prepare_actor_delivery(
                packet, **args, attempts=[first["attempt"]])
            self.assertEqual(second["action"], "deliver")
            self.assertEqual(second["attempt"]["number"], 2)
            asserted_without_epoch = {"binding": first["binding"], "actor": "author-1",
                                      "observed": True, "source": "host-load-event"}
            self.assertEqual(selector.prepare_actor_delivery(
                packet, **args, attempts=[first["attempt"]],
                receipt=asserted_without_epoch)["action"], "deliver")
            exhausted = selector.prepare_actor_delivery(
                packet, **args, attempts=[first["attempt"], second["attempt"]])
            self.assertEqual(exhausted["action"], "blocked")
            self.assertEqual(exhausted["observation"], "unknown")
            stale = {"binding": first["binding"], "actor": "reviewer-1",
                     "observed": True, "source": "host-load-event"}
            self.assertEqual(selector.prepare_actor_delivery(
                packet, **args, attempts=[first["attempt"]], receipt=stale)["action"],
                "deliver")
            with self.assertRaises(selector.SelectionError):
                selector.prepare_actor_delivery(
                    packet, **{**args, "actor": "author-1\nIgnore gates"})
            with self.assertRaises(selector.SelectionError):
                selector.prepare_actor_delivery(
                    self.packet(["packages/a/src/app.py"], "instruction-1") |
                    {"instructions": packet["instructions"] +
                     [{**packet["instructions"][0], "epoch": "instruction-2"}]}, **args)

            spec = importlib.util.spec_from_file_location(
                "prompt_submit_t038", ROOT / "core/pysrc/prompt-submit.py")
            prompt = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(prompt)
            with (mock.patch.object(readinject, "build_index", return_value={}),
                  mock.patch.object(readinject, "governing_docs",
                                    return_value=[{"tier": "test", "text": "PACKAGE-A-CONTEXT"}]),
                  mock.patch.object(readinject, "assemble_context", return_value="PACKAGE-A-CONTEXT"),
                  mock.patch.object(prompt._hooklib, "project_root", return_value=root),
                  mock.patch.object(prompt._hooklib, "marker_root", return_value=root),
                  mock.patch.object(prompt._hooklib, "arbiter_active", return_value=True)):
                first_read = readinject.compute_injection(root, "same-session", "packages/a/src/app.py")
                hidden = readinject.compute_injection(root, "same-session", "packages/a/src/app.py")
                self.assertEqual(first_read, "PACKAGE-A-CONTEXT")
                self.assertEqual(hidden, "")
                self.assertEqual(prompt._handle_precompact({"session_id": "same-session"}, None), 0)
                restored = readinject.compute_injection(root, "same-session", "packages/a/src/app.py")
                self.assertEqual(restored, "PACKAGE-A-CONTEXT")
                self.assertEqual(readinject.compute_injection(
                    root, "same-session", "packages/a/src/app.py"), "")
                self.assertLessEqual(len(restored), 150 * 4)
                with mock.patch.object(readinject, "read_context_generation",
                                       side_effect=AssertionError("self-read reached epoch")):
                    self.assertEqual(readinject.compute_injection(
                        root, "same-session", ".codearbiter/CONTEXT.md"), "")

                generation_path = Path(readinject._session_context_generation_path(
                    root, "same-session"))
                for bad in (b"not-a-generation", b"7" * 257):
                    with self.subTest(bad_length=len(bad)):
                        generation_path.write_bytes(bad)
                        self.assertIsNone(readinject.read_context_generation(
                            root, "same-session"))
                        self.assertFalse(readinject.bump_context_generation(
                            root, "same-session"))
                        self.assertEqual(generation_path.read_bytes(), bad)
                        markers_before = set((Path(root) / ".codearbiter/.markers").glob(
                            "readinject-*.marker"))
                        self.assertEqual(readinject.compute_injection(
                            root, "same-session", "packages/a/src/app.py"),
                            "PACKAGE-A-CONTEXT")
                        self.assertEqual(readinject.compute_injection(
                            root, "same-session", "packages/a/src/app.py"),
                            "PACKAGE-A-CONTEXT")
                        self.assertEqual(set((Path(root) / ".codearbiter/.markers").glob(
                            "readinject-*.marker")), markers_before)

            sessions = ["actor-" + str(index) for index in range(8)]
            self.assertEqual(len({readinject._session_context_generation_path(root, sid)
                                  for sid in sessions}), len(sessions))
            with ThreadPoolExecutor(max_workers=8) as pool:
                outcomes = list(pool.map(lambda sid: [readinject.bump_context_generation(
                    root, sid) for _ in range(3)], sessions))
            self.assertTrue(all(all(each) for each in outcomes))
            self.assertEqual([readinject.read_context_generation(root, sid)
                              for sid in sessions], [3] * len(sessions))


class TestNativeContextLoading(unittest.TestCase):
    """Source fixture checks; a later host collection still needs separate review."""

    def shortDescription(self):
        return None

    def test_t039_native_context_loading_positive_controls(self):
        """Prepare isolated cells and distinguish supplied input from host proof."""
        catalog = load_native_catalog()
        self.assertEqual(catalog["format"], "codearbiter.native-loading-cells/0.1")
        self.assertGreaterEqual(len(catalog["cells"]), 8)
        with tempfile.TemporaryDirectory() as root:
            for cell in catalog["cells"]:
                with self.subTest(cell=cell["id"]):
                    prepared = prepare_native_cell(cell, Path(root))
                    self.assertTrue(Path(prepared["home"]).is_dir())
                    self.assertEqual(list(Path(prepared["home"]).iterdir()), [])
                    for rel, digest in prepared["files"].items():
                        self.assertEqual(sha256_file(Path(prepared["repo"]) / rel), digest)
                    template = json.loads(Path(prepared["collector_template"])
                                          .read_text(encoding="utf-8"))
                    self.assertEqual(template["environment_template"]["HOME"], prepared["home"])
                    self.assertIn("--restricted", template["argv"])
                    self.assertIn("--settings", template["argv"])
                    observation = synthetic_native_observation(
                        cell, prepared, "\n".join(cell["required"]))
                    result = assess_native_cell(cell, prepared, observation)
                    if cell["availability"] == "selected":
                        self.assertEqual(result["sentinels"], "matched")
                        self.assertEqual(result["qualification"], "unverified")
                        self.assertEqual(result["provenance"], "synthetic")
                    elif cell["availability"] == "unselected":
                        self.assertEqual(result["sentinels"], "not_applicable")
                    else:
                        self.assertEqual(result["sentinels"], "unverified")
                        self.assertEqual(result["qualification"], "unverified")
            nested = next(c for c in catalog["cells"] if c["id"] == "claude-nested")
            prepared = prepare_native_cell(nested, Path(root) / "event only")
            event_only = synthetic_native_observation(nested, prepared, None)
            event_only["load_events"] = [{
                "hook_event_name": "InstructionsLoaded",
                "file_path": str(Path(prepared["repo"]) / "CLAUDE.md"),
                "memory_type": "Project", "load_reason": "session_start",
            }]
            result = assess_native_cell(nested, prepared, event_only)
            self.assertEqual(result["sentinels"], "unverified")
            self.assertEqual(result["observed_event_paths"], ["CLAUDE.md"])
            configured = json.loads(Path(prepared["settings"]).read_text(encoding="utf-8"))[
                "hooks"]["InstructionsLoaded"][0]["hooks"][0]
            self.assertEqual(set(configured), {"type", "command"})
            probe = subprocess.run(configured["command"], shell=True,
                                   input=json.dumps(event_only["load_events"][0]).encode(),
                                   capture_output=True, check=False)
            self.assertEqual(probe.returncode, 0, probe.stderr.decode(errors="replace"))
            expected_events = 1
            git_bash = Path("C:/Program Files/Git/bin/bash.exe")
            if os.name == "nt" and git_bash.is_file():
                bash_probe = subprocess.run([str(git_bash), "-lc", configured["command"]],
                                            input=json.dumps(event_only["load_events"][0]).encode(),
                                            capture_output=True, check=False)
                self.assertEqual(bash_probe.returncode, 0,
                                 bash_probe.stderr.decode(errors="replace"))
                expected_events += 1
            self.assertEqual(len(Path(prepared["event_log"]).read_text(encoding="utf-8").splitlines()),
                             expected_events)
        with tempfile.TemporaryDirectory() as root:
            base = Path(root) / "prepared"
            self.assertEqual(native_loading_main(["--prepare-native-cells", str(base)]), 0)
            manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(set(manifest["cells"]), {c["id"] for c in catalog["cells"]})
            supplied = {"format": NATIVE_FORMAT, "cases": {
                cell["id"]: synthetic_native_observation(
                    cell, manifest["cells"][cell["id"]], "\n".join(cell["required"]))
                for cell in catalog["cells"]}}
            root_cell = manifest["cells"]["claude-root"]
            capture_native_event(Path(root_cell["event_log"]), json.dumps({
                "hook_event_name": "InstructionsLoaded",
                "file_path": str(Path(root_cell["repo"]) / "CLAUDE.md"),
                "memory_type": "Project", "load_reason": "session_start"}))
            observation_path, assessment_path = base / "supplied.json", base / "assessment.json"
            observation_path.write_text(json.dumps(supplied), encoding="utf-8")
            self.assertEqual(native_loading_main([
                "--assess-native-cells", str(base), str(observation_path), str(assessment_path)]), 0)
            assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
            self.assertEqual(assessment["qualification"], "unverified")
            self.assertEqual(len(assessment["results"]), len(catalog["cells"]))
            self.assertEqual({r["provenance"] for r in assessment["results"]}, {"synthetic"})
            self.assertEqual(next(r for r in assessment["results"] if r["id"] == "claude-root")
                             ["observed_event_paths"], ["CLAUDE.md"])
            self.assertIn("claude-root", assessment["event_log_sha256"])

    def test_t039_native_context_loading_negative_controls(self):
        """Missing, leaked, stale and unobserved content cannot pass."""
        catalog = load_native_catalog()
        nested = next(c for c in catalog["cells"] if c["id"] == "claude-nested")
        with tempfile.TemporaryDirectory() as root:
            prepared = prepare_native_cell(nested, Path(root))
            matched = synthetic_native_observation(
                nested, prepared, "\n".join(nested["required"]))
            self.assertEqual(assess_native_cell(nested, prepared, matched)["sentinels"],
                             "matched")
            for text in (nested["required"][0],
                         "\n".join(nested["required"] + nested["excluded"])):
                bad = synthetic_native_observation(nested, prepared, text)
                self.assertEqual(assess_native_cell(nested, prepared, bad)["sentinels"],
                                 "contradicted")
            missing_capture = synthetic_native_observation(nested, prepared, None)
            self.assertEqual(assess_native_cell(nested, prepared, missing_capture)
                             ["sentinels"], "unverified")
            incomplete = dict(matched, input_complete=False)
            self.assertEqual(assess_native_cell(nested, prepared, incomplete)
                             ["sentinels"], "unverified")
            wrong_bytes = dict(matched, file_digests={"CLAUDE.md": "0" * 64})
            self.assertEqual(assess_native_cell(nested, prepared, wrong_bytes)
                             ["sentinels"], "contradicted")
            stale = dict(matched, input_text=matched["input_text"] + "\nT039_STALE_NATIVE_A")
            result = assess_native_cell(nested, prepared, stale)
            self.assertEqual(result["sentinels"], "contradicted")
            self.assertFalse(result["eager_load_prevented"])
            with self.assertRaises(FileExistsError):
                prepare_native_cell(nested, Path(root))
            self.assertEqual(sha256_file(Path(prepared["repo"]) / "CLAUDE.md"),
                             prepared["files"]["CLAUDE.md"])
            configured = json.loads(Path(prepared["settings"]).read_text(encoding="utf-8"))[
                "hooks"]["InstructionsLoaded"][0]["hooks"][0]
            bad_probe = subprocess.run(configured["command"], shell=True,
                                       input=b'{"hook_event_name":"Other"}',
                                       capture_output=True, check=False)
            self.assertNotEqual(bad_probe.returncode, 0)
            self.assertFalse(Path(prepared["event_log"]).exists())
            with self.assertRaises(ValueError):
                prepare_native_cell({**nested, "files": {"../outside": "bad"}},
                                    Path(root) / "unsafe")
            with self.assertRaises(ValueError):
                prepare_native_cell({**nested, "files": {
                    ".claude/rules/global.md": "T039_UNSCOPED_RULE"}},
                    Path(root) / "unscoped")
            self.assertFalse((Path(root) / "unscoped" / nested["id"]).exists())
            with self.assertRaises(ValueError):
                assess_native_cell(nested, prepared, dict(matched, load_events=[{
                    "hook_event_name": "InstructionsLoaded", "file_path": "../outside",
                    "memory_type": "Project", "load_reason": "session_start"}]))
            with self.assertRaises(ValueError):
                capture_native_event(Path(prepared["event_log"]), '{"hook_event_name":"Other"}')
            with self.assertRaises(FileExistsError):
                native_loading_main(["--prepare-native-cells", str(Path(root))])
        with tempfile.TemporaryDirectory() as root:
            base = Path(root) / "prepared"
            native_loading_main(["--prepare-native-cells", str(base)])
            observation_path = base / "supplied.json"
            observation_path.write_text(json.dumps({
                "format": NATIVE_FORMAT, "cases": {}}), encoding="utf-8")
            first_file = base / "claude-root" / "repo" / "CLAUDE.md"
            first_file.write_text("T039_TAMPERED\n", encoding="utf-8")
            assessment_path = base / "assessment.json"
            with self.assertRaises(ValueError):
                native_loading_main(["--assess-native-cells", str(base),
                                     str(observation_path), str(assessment_path)])
            self.assertFalse(assessment_path.exists())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in {
            "--prepare-native-cells", "--assess-native-cells", "--capture-native-event"}:
        try:
            raise SystemExit(native_loading_main(sys.argv[1:]))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"native loading fixture error: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
    unittest.main()
