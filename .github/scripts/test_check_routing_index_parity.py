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
import shutil
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


class TestCodexAgentRouteClosure(unittest.TestCase):
    """The shipped Codex package must close every concrete and generic agent
    route against its own indexed charter inventory.

    These fixtures mutate a complete copied surface rather than grepping a
    checker implementation.  That makes each test prove a consumer-visible
    package break: a copied package can no longer resolve the route that its
    Markdown advertises.
    """

    def _repo_copy(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        shutil.copytree(REPO_ROOT / "core", root / "core")
        shutil.copytree(REPO_ROOT / "plugins", root / "plugins")
        return temporary, root

    def _errors_after(self, relative_path: str, old: str, new: str) -> list[str]:
        temporary, repo = self._repo_copy()
        self.addCleanup(temporary.cleanup)
        target = repo / relative_path
        text = target.read_text(encoding="utf-8")
        self.assertIn(old, text, f"fixture anchor missing from {relative_path}")
        target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
        errors, _stats = G.check(repo=repo)
        return errors

    def _symlink_or_skip(self, link: Path, target: Path, *, directory: bool = False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"test platform cannot create symlinks: {error}")

    def test_codex_agent_inventory_is_counted_from_shipped_charters(self):
        errors, stats = G.check(repo=REPO_ROOT)
        self.assertEqual(errors, [])
        expected = sum(
            len(G.dir_agent_names(REPO_ROOT / "plugins" / plugin / "agents"))
            for plugin in ("ca", "ca-codex", "ca-pi")
        ) + len(G.dir_agent_names(REPO_ROOT / "core" / "surface" / "agents"))
        self.assertEqual(stats["agents_checked"], expected)

    def test_missing_literal_codex_agent_route_fails_closed(self):
        errors = self._errors_after(
            "plugins/ca-codex/skills/ca-add-dep/SKILL.md",
            "../../agents/dependency-reviewer.md",
            "../../agents/missing-reviewer.md",
        )
        self.assertTrue(any("missing-reviewer" in error for error in errors), errors)

    def test_deleted_literal_codex_agent_route_fails_the_route_contract(self):
        errors = self._errors_after(
            "plugins/ca-codex/skills/ca-add-dep/SKILL.md",
            "[agents/dependency-reviewer.md](../../agents/dependency-reviewer.md)",
            "the dependency-reviewer agent",
        )
        self.assertTrue(
            any("literal_route_lines" in error for error in errors),
            errors,
        )

    def test_escaping_literal_codex_agent_route_fails_closed(self):
        errors = self._errors_after(
            "plugins/ca-codex/skills/ca-add-dep/SKILL.md",
            "../../agents/dependency-reviewer.md",
            "../../../agents/escape.md",
        )
        self.assertTrue(any("escape" in error for error in errors), errors)

    def test_unsupported_generic_codex_agent_route_fails_closed(self):
        errors = self._errors_after(
            "plugins/ca-codex/routines/subagent-driven-development/SKILL.md",
            "../../agents/<name>.md",
            "../../agents/<role>.md",
        )
        self.assertTrue(any("generic" in error and "role" in error for error in errors), errors)

    def test_wrong_name_or_duplicate_codex_agent_index_row_fails_closed(self):
        errors = self._errors_after(
            "plugins/ca-codex/agents/INDEX.md",
            "| [backend-author](backend-author.md) |",
            "| [backend-author](frontend-author.md) |\n| [backend-author](backend-author.md) |",
        )
        self.assertTrue(any("backend-author" in error and "duplicate" in error for error in errors), errors)
        self.assertTrue(any("backend-author" in error and "expected" in error for error in errors), errors)

    def test_generic_route_rejects_an_indexed_charter_symlink_escape(self):
        temporary, repo = self._repo_copy()
        self.addCleanup(temporary.cleanup)
        plugin = repo / "plugins" / "ca-codex"
        ambient = repo / "ambient-backend-author.md"
        ambient.write_text("# Ambient unreviewed agent\n", encoding="utf-8", newline="\n")
        charter = plugin / "agents" / "backend-author.md"
        charter.unlink()
        self._symlink_or_skip(charter, ambient)

        errors, _stats = G.check(repo=repo)

        self.assertTrue(
            any("backend-author.md" in error and "symlink" in error for error in errors),
            errors,
        )

    def test_agent_directory_symlink_escape_fails_closed(self):
        temporary, repo = self._repo_copy()
        self.addCleanup(temporary.cleanup)
        agents = repo / "plugins" / "ca-codex" / "agents"
        ambient_agents = repo / "ambient-agents"
        shutil.copytree(agents, ambient_agents)
        shutil.rmtree(agents)
        self._symlink_or_skip(agents, ambient_agents, directory=True)

        errors, _stats = G.check(repo=repo)

        self.assertIn(
            "plugins/ca-codex/agents/: directory symlink escapes package",
            errors,
        )

    def test_agent_index_symlink_escape_fails_closed(self):
        temporary, repo = self._repo_copy()
        self.addCleanup(temporary.cleanup)
        plugin = repo / "plugins" / "ca-codex"
        index = plugin / "agents" / "INDEX.md"
        ambient_index = repo / "ambient-agent-index.md"
        ambient_index.write_bytes(index.read_bytes())
        index.unlink()
        self._symlink_or_skip(index, ambient_index)

        errors, _stats = G.check(repo=repo)

        self.assertTrue(
            any("INDEX.md" in error and "symlink" in error for error in errors),
            errors,
        )

    def test_indexed_charter_must_be_a_regular_file(self):
        temporary, repo = self._repo_copy()
        self.addCleanup(temporary.cleanup)
        charter = repo / "plugins" / "ca-codex" / "agents" / "backend-author.md"
        charter.unlink()
        charter.mkdir()

        errors, _stats = G.validate_agent_routes(
            repo / "plugins" / "ca-codex"
        )

        self.assertTrue(
            any("backend-author.md" in error and "regular file" in error for error in errors),
            errors,
        )


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
