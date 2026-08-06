#!/usr/bin/env python3
"""Unit tests for check_routing_index_parity — the #592 INDEX/routing-surface
invariant checker.

Run: python .github/scripts/test_check_routing_index_parity.py

Two kinds of coverage:

  1. A live-repo invariant: `check(repo=REPO_ROOT)` returns no errors and
     actually measured a non-trivial number of entries (a green run that
     compared zero things would prove nothing).
  2. Mutation proofs for every violation class the module claims to catch —
     missing INDEX row, orphan INDEX row (skill and agent and ca-codex
     wrapper-skill variants), duplicate INDEX row, and a dangling
     routing-table route — each built as a small synthetic fixture on disk
     so the failing branch is actually exercised, not merely read.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_routing_index_parity as G  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _make_skill(root: Path, name: str) -> None:
    _write(root / name / "SKILL.md", f"---\nname: {name}\ndescription: x\n---\n# {name}\n")


class TestLiveRepoIsClean(unittest.TestCase):
    """The invariant this whole gate exists to enforce, checked against the
    actual committed surfaces."""

    def test_no_drift_on_the_real_tree(self):
        errors, stats = G.check(repo=REPO_ROOT)
        self.assertEqual(errors, [])
        # A check that measured nothing would also report zero errors —
        # this half of the assertion is what makes "no errors" meaningful.
        self.assertGreater(stats["surfaces"], 0)
        self.assertGreater(stats["skills_checked"], 0)
        self.assertGreater(stats["agents_checked"], 0)
        self.assertGreater(stats["routing_rows_checked"], 0)


class TestSkillIndexParity(unittest.TestCase):
    def _fixture(self, index_text: str, skill_names=("alpha", "beta")):
        tmp = Path(tempfile.mkdtemp())
        skills_dir = tmp / "skills"
        for n in skill_names:
            _make_skill(skills_dir, n)
        _write(skills_dir / "INDEX.md", index_text)
        return skills_dir

    def _run(self, skills_dir: Path):
        rows = G.parse_link_rows(G.read(skills_dir / "INDEX.md"))
        on_disk = G.dir_skill_names(skills_dir)
        return G.check_link_index_parity(
            "skill", on_disk, rows, lambda n: f"{n}/SKILL.md", "skills/INDEX.md", skills_dir
        )

    def test_clean_fixture_is_error_free(self):
        skills_dir = self._fixture(
            "| [alpha](alpha/SKILL.md) | x | y |\n"
            "| [beta](beta/SKILL.md) | x | y |\n"
        )
        self.assertEqual(self._run(skills_dir), [])

    def test_missing_row_is_caught(self):
        # `beta` exists on disk but never got a row.
        skills_dir = self._fixture("| [alpha](alpha/SKILL.md) | x | y |\n")
        errors = self._run(skills_dir)
        self.assertTrue(any("'beta'" in e and "no INDEX row" in e for e in errors), errors)

    def test_orphan_row_is_caught(self):
        # The row names a skill that was never created on disk.
        skills_dir = self._fixture(
            "| [alpha](alpha/SKILL.md) | x | y |\n"
            "| [beta](beta/SKILL.md) | x | y |\n"
            "| [ghost](ghost/SKILL.md) | x | y |\n"
        )
        errors = self._run(skills_dir)
        self.assertTrue(
            any("'ghost'" in e and "does not point at an existing" in e for e in errors), errors
        )

    def test_duplicate_row_is_caught(self):
        skills_dir = self._fixture(
            "| [alpha](alpha/SKILL.md) | x | y |\n"
            "| [alpha](alpha/SKILL.md) | x | y |\n"
            "| [beta](beta/SKILL.md) | x | y |\n"
        )
        errors = self._run(skills_dir)
        self.assertTrue(any("duplicate INDEX row for 'alpha'" in e for e in errors), errors)

    def test_mismatched_target_is_caught(self):
        # A row for a real skill, pointing at the WRONG file.
        skills_dir = self._fixture(
            "| [alpha](beta/SKILL.md) | x | y |\n"
            "| [beta](beta/SKILL.md) | x | y |\n"
        )
        errors = self._run(skills_dir)
        self.assertTrue(
            any("'alpha'" in e and "links to 'beta/SKILL.md'" in e for e in errors), errors
        )


class TestAgentIndexParity(unittest.TestCase):
    def test_missing_and_orphan_agent_rows_are_caught(self):
        tmp = Path(tempfile.mkdtemp())
        agents_dir = tmp / "agents"
        _write(agents_dir / "reviewer-a.md", "---\nname: reviewer-a\n---\n")
        _write(agents_dir / "reviewer-b.md", "---\nname: reviewer-b\n---\n")
        _write(
            agents_dir / "INDEX.md",
            "| [reviewer-a](reviewer-a.md) | x | y | z |\n"
            "| [ghost-agent](ghost-agent.md) | x | y | z |\n",
        )
        rows = G.parse_link_rows(G.read(agents_dir / "INDEX.md"))
        on_disk = G.dir_agent_names(agents_dir)
        errors = G.check_link_index_parity(
            "agent", on_disk, rows, lambda n: f"{n}.md", "agents/INDEX.md", agents_dir
        )
        self.assertTrue(any("'reviewer-b'" in e and "no INDEX row" in e for e in errors), errors)
        self.assertTrue(
            any("'ghost-agent'" in e and "does not point at an existing" in e for e in errors),
            errors,
        )


class TestWrapperIndexParity(unittest.TestCase):
    """ca-codex's `` `$name` ``-style command-wrapper skills index."""

    def test_missing_and_orphan_wrapper_rows_are_caught(self):
        tmp = Path(tempfile.mkdtemp())
        wrapper_dir = tmp / "skills"
        _make_skill(wrapper_dir, "ca-add-dep")
        _make_skill(wrapper_dir, "ca-adr")
        rows = G.parse_wrapper_rows("| `$ca-add-dep` | x |\n| `$ca-ghost` | x |\n")
        on_disk = G.dir_skill_names(wrapper_dir)
        errors = G.check_wrapper_index_parity(on_disk, rows, "skills/INDEX.md")
        self.assertTrue(any("'ca-adr'" in e and "no INDEX row" in e for e in errors), errors)
        self.assertTrue(
            any("'ca-ghost'" in e and "no such wrapper skill" in e for e in errors), errors
        )


class TestRoutingTableDangling(unittest.TestCase):
    def test_a_valid_route_is_silent(self):
        text = "| Cue | Primary route | Also dispatch | Gate |\n|---|---|---|---|\n| x | `tdd` | `security-reviewer` | y |\n"
        errors = G.check_routing_table_dangling(
            "includes/routing-table.md", text, {"tdd", "security-reviewer"}
        )
        self.assertEqual(errors, [])

    def test_a_renamed_skill_orphans_its_route(self):
        # Simulates the real-world drift: a skill was renamed on disk but
        # the routing table still points at the old name.
        text = "| Cue | Primary route | Also dispatch | Gate |\n|---|---|---|---|\n| x | `decision-variantz` | — | y |\n"
        errors = G.check_routing_table_dangling(
            "includes/routing-table.md", text, {"decision-variance"}
        )
        self.assertTrue(any("`decision-variantz`" in e for e in errors), errors)

    def test_the_allowlist_does_not_false_positive(self):
        text = (
            "| Cue | Primary route | Also dispatch | Gate |\n|---|---|---|---|\n"
            "| x | `core` | `anti-slop-design`, `medium-documents` | y |\n"
        )
        errors = G.check_routing_table_dangling("includes/routing-table.md", text, set())
        self.assertEqual(errors, [])

    def test_command_and_path_tokens_are_out_of_scope(self):
        text = (
            "| Cue | Primary route | Also dispatch | Gate |\n|---|---|---|---|\n"
            "| x | `/commit` → `{{CMD:cleanup}}`, `hooks/taskwrite.py` | `spike/<slug>` | y |\n"
        )
        errors = G.check_routing_table_dangling("includes/routing-table.md", text, set())
        self.assertEqual(errors, [])


class TestMainExitCode(unittest.TestCase):
    def test_main_returns_zero_on_the_real_repo(self):
        self.assertEqual(G.main(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
