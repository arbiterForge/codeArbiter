#!/usr/bin/env python3
"""Contract tests for the read-only review funnel (RA-03)."""

from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MUTATING_TOOLS = {"Bash", "PowerShell", "Write", "Edit", "MultiEdit", "NotebookEdit"}


def _read(relative: str) -> str:
    path = REPO_ROOT / relative
    if not path.is_file():
        raise AssertionError(f"required review-funnel surface is missing: {relative}")
    return path.read_text(encoding="utf-8")


def _snapshot_repository_bytes() -> str:
    """Digest every worktree file except Git metadata; the verifier is read-only."""
    digest = hashlib.sha256()
    for path in sorted(item for item in REPO_ROOT.rglob("*") if item.is_file()):
        relative = path.relative_to(REPO_ROOT)
        if relative.parts and relative.parts[0] == ".git":
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _frontmatter_tools(text: str) -> set[str]:
    match = re.search(r"^tools:\s*(.+)$", text, re.MULTILINE)
    if match is None:
        raise AssertionError("verdict-aggregator must declare an explicit tools contract")
    return {item.strip() for item in match.group(1).split(",") if item.strip()}


def verify_review_route(target_kind: str) -> tuple[str, str]:
    if target_kind not in {"working-diff", "inbound-pr"}:
        raise AssertionError(f"unsupported review target fixture: {target_kind}")

    review = _read("core/surface/commands/review.md")
    dispatch = _read("core/surface/skills/dispatching-parallel-agents/SKILL.md")
    skill_index = _read("core/surface/skills/INDEX.md")
    triage = _read("core/surface/agents/finding-triage.md")
    verdict = _read("core/surface/agents/verdict-aggregator.md")

    target_marker = "current working diff" if target_kind == "working-diff" else "gh pr diff"
    if target_marker not in review:
        raise AssertionError(f"review surface does not support {target_kind}")

    for where, text in (("review", review), ("generic dispatch", dispatch)):
        if "finding-triage" not in text or "verdict-aggregator" not in text:
            raise AssertionError(f"{where} does not close through triage then verdict")
        if text.find("finding-triage") > text.find("verdict-aggregator"):
            raise AssertionError(f"{where} routes verdict before triage")
        if "checkpoint-aggregator" in text:
            raise AssertionError(f"{where} still exposes the checkpoint writer")

    if "finding-triage`→`verdict-aggregator" not in skill_index:
        raise AssertionError("skill index still advertises the writer-coupled funnel")

    tools = _frontmatter_tools(verdict)
    forbidden = tools & MUTATING_TOOLS
    if forbidden:
        raise AssertionError(f"verdict-aggregator exposes mutating tools: {sorted(forbidden)}")
    if "Modify no file" not in verdict:
        raise AssertionError("verdict-aggregator lacks an explicit no-file-mutation rule")
    if "verdict-aggregator" not in triage or "Modify no file" not in triage:
        raise AssertionError("finding-triage is not a read-only producer for verdict aggregation")

    return ("finding-triage", "verdict-aggregator")


class ReadOnlyReviewFunnelTest(unittest.TestCase):
    def _assert_byte_invariant_route(self, target_kind: str) -> None:
        before = _snapshot_repository_bytes()
        self.assertEqual(
            verify_review_route(target_kind),
            ("finding-triage", "verdict-aggregator"),
        )
        self.assertEqual(_snapshot_repository_bytes(), before)

    def test_working_diff_review_route_is_byte_invariant(self):
        self._assert_byte_invariant_route("working-diff")

    def test_inbound_pr_review_route_is_byte_invariant(self):
        self._assert_byte_invariant_route("inbound-pr")

    def test_checkpoint_persistence_is_explicit_and_non_overwriting(self):
        checkpoint = _read("core/surface/commands/checkpoint.md")
        writer = _read("core/surface/agents/checkpoint-aggregator.md")
        verdict_position = checkpoint.find("verdict-aggregator")
        writer_position = checkpoint.find("checkpoint-aggregator")
        self.assertGreaterEqual(verdict_position, 0)
        self.assertGreater(writer_position, verdict_position)
        self.assertIn("verdict-aggregator output", writer)
        self.assertNotIn("Read the finding-triage report", writer)
        self.assertIn("MUST NOT overwrite", writer)

    def test_checkpoint_writer_reports_the_selected_dated_filename(self):
        writer = _read("core/surface/agents/checkpoint-aggregator.md")
        self.assertIn("selected dated checkpoint filename", writer)
        self.assertIn("including any numeric suffix", writer)
        self.assertIn("Report the exact path written in Step 3", writer)

    def test_triage_requires_the_complete_batch_contract(self):
        triage = _read("core/surface/agents/finding-triage.md")
        for required in (
            "current batch",
            "every unit's terminal state",
            "ERRORED",
            "DEFERRED",
            "Remediation",
            "Applicable control",
        ):
            self.assertIn(required, triage)

    def test_verdict_has_unambiguous_incomplete_precedence_and_schema(self):
        verdict = _read("core/surface/agents/verdict-aggregator.md")
        self.assertIn("INCOMPLETE takes precedence over BLOCKING_FINDINGS", verdict)
        self.assertIn("INCOMPLETE_RESULT", verdict)
        self.assertIn("INCOMPLETE_RESULT findings | N", verdict)

    def test_dispatch_contract_uses_canonical_routes_and_preserves_findings(self):
        agent_index = _read("core/surface/agents/INDEX.md")
        routing = _read("core/surface/includes/routing-table.md")
        dispatch = _read("core/surface/skills/dispatching-parallel-agents/SKILL.md")
        self.assertIn("dispatching-parallel-agents", agent_index)
        self.assertIn("reviewer fleet → finding-triage → read-only verdict", routing)
        self.assertNotIn("reviewer fleet → triage →", routing)
        self.assertNotIn("discards noise", dispatch)
        self.assertIn("Every reviewer finding", dispatch)

    def test_curated_review_projection_uses_the_read_only_terminal(self):
        curated_review = _read("site/src/curated/commands/review.md")
        self.assertIn("verdict-aggregator", curated_review)
        self.assertNotIn("checkpoint-aggregator", curated_review)


if __name__ == "__main__":
    unittest.main(verbosity=2)
