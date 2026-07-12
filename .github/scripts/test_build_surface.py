#!/usr/bin/env python3
"""Unit tests for tools/build-surface.py — the markdown-surface generator.

Run: python .github/scripts/test_build_surface.py

The generator renders core/surface/ templates into both plugin trees
(plugins/ca and plugins/ca-codex). These tests drive it against synthetic
template trees in a temp dir, so every property is provable without touching
the real surface: determinism, idempotence, Claude-render inversion of the
extraction, host-conditional resolution, Codex path rewrites and frontmatter
synthesis, excluded-command hard-fails, LF-only IO, collision detection, and
--check drift in both directions (modified, missing, orphan).
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOL = REPO_ROOT / "tools" / "build-surface.py"

_spec = importlib.util.spec_from_file_location("build_surface", _TOOL)
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)


def _write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        f.write(text.encode("utf-8"))
    return p


class _RepoCase(unittest.TestCase):
    """Base: a synthetic repo with a minimal surface tree."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.repo = self._td.name
        self.addCleanup(self._td.cleanup)
        # A minimal but representative surface.
        _write(self.repo, "core/surface/commands/init.md",
               "---\ndescription: Opt this repo in.\nargument-hint: (none)\n---\n\n"
               "# {{CMD:init}} — first-run\n\n"
               "Run `python \"{{PLUGIN_ROOT}}/hooks/init-codearbiter.py\"` then "
               "route to {{CMD:status}}.\n")
        _write(self.repo, "core/surface/commands/status.md",
               "---\ndescription: Show state.\nargument-hint: (none)\n---\n\n"
               "# {{CMD:status}}\n\nReads {{PROJECT_DIR}}/.codearbiter/CONTEXT.md and the body of\n"
               "{{PLUGIN_ROOT}}/skills/tdd/SKILL.md plus {{PLUGIN_ROOT}}/commands/init.md.\n")
        _write(self.repo, "core/surface/commands/statusline.md",
               "---\ndescription: Statusline wiring.\nargument-hint: (none)\n---\n\n"
               "# {{CMD:statusline}}\n\nClaude-only surface.\n")
        _write(self.repo, "core/surface/skills/tdd/SKILL.md",
               "---\nname: tdd\ndescription: Test-first gate.\n---\n\n# tdd\n\n"
               "{{IF:claude}}\nStatusline note: see {{CMD:statusline}}.\n{{ELSE}}\n"
               "No statusline on this host.\n{{END}}\nShared tail.\n")
        _write(self.repo, "core/surface/includes/notes.md",
               "Shared include; inline {{IF:claude}}slash commands{{ELSE}}skills{{END}} here.\n")
        _write(self.repo, "core/surface/includes/codex-host-notes.md",
               "Codex-only operational notes.\n")
        _write(self.repo, "core/surface/COMMANDS.md",
               "# catalog\n\n| {{CMD:init}} | opt in |\n{{IF:claude}}\n| {{CMD:statusline}} | statusline |\n{{END}}\n")
        _write(self.repo, "core/surface/SPRINT.md", "Sprint doc. {{CMD:init}}.\n")
        _write(self.repo, "core/surface/ORCHESTRATOR.md",
               "Persona. Invoke {{CMD:init}}. Paths: {{PLUGIN_ROOT}}/skills/.\n")
        _write(self.repo, "core/surface/README.md", "Template docs — never rendered.\n")

    def render(self, host):
        return B.render_all(self.repo, host)


class ConditionalTest(_RepoCase):
    def test_claude_keeps_if_claude_branch_and_drops_marker_lines(self):
        out = self.render("claude")
        text = out["skills/tdd/SKILL.md"].decode()
        self.assertIn("Statusline note: see /ca:statusline.\n", text)
        self.assertNotIn("No statusline", text)
        self.assertNotIn("{{", text)
        # Whole-line markers vanish with their line — no blank-line residue.
        self.assertNotIn("\n\nShared tail", text)

    def test_codex_takes_else_branch(self):
        text = self.render("codex")["routines/tdd/SKILL.md"].decode()
        self.assertIn("No statusline on this host.\n", text)
        self.assertNotIn("Statusline note", text)

    def test_inline_conditional_keeps_surrounding_text(self):
        claude = self.render("claude")["includes/notes.md"].decode()
        codex = self.render("codex")["includes/notes.md"].decode()
        self.assertEqual(claude, "Shared include; inline slash commands here.\n")
        self.assertEqual(codex, "Shared include; inline skills here.\n")

    def test_unclosed_conditional_fails(self):
        _write(self.repo, "core/surface/includes/bad.md", "{{IF:claude}}never closed\n")
        with self.assertRaises(B.SurfaceError):
            self.render("claude")

    def test_nested_conditional_fails(self):
        _write(self.repo, "core/surface/includes/bad.md",
               "{{IF:claude}}{{IF:codex}}x{{END}}{{END}}\n")
        with self.assertRaises(B.SurfaceError):
            self.render("claude")


class TokenTest(_RepoCase):
    def test_claude_token_values(self):
        text = self.render("claude")["commands/status.md"].decode()
        self.assertIn("${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md", text)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/tdd/SKILL.md", text)
        self.assertIn("# /ca:status", text)

    def test_codex_token_values_and_path_rewrites(self):
        text = self.render("codex")["skills/ca-status/SKILL.md"].decode()
        self.assertIn("<project-root>/.codearbiter/CONTEXT.md", text)
        # skills/ -> routines/ rewrite, commands/x.md -> skills/ca-x/SKILL.md rewrite.
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/routines/tdd/SKILL.md", text)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/ca-init/SKILL.md", text)
        self.assertIn("# $ca-status", text)

    def test_codex_entry_skill_paths_survive_the_routines_rewrite(self):
        # A codex-side conditional may name an entry skill path directly;
        # skills/ca-* is codex-native and must NOT be rewritten to routines/.
        _write(self.repo, "core/surface/includes/entry.md",
               "{{IF:codex}}see {{PLUGIN_ROOT}}/skills/ca-init/SKILL.md{{END}}\n"
               "shared: {{PLUGIN_ROOT}}/skills/tdd/SKILL.md\n")
        text = self.render("codex")["includes/entry.md"].decode()
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/ca-init/SKILL.md", text)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/routines/tdd/SKILL.md", text)

    def test_unknown_cmd_name_fails(self):
        _write(self.repo, "core/surface/includes/bad.md", "see {{CMD:no-such-cmd}}\n")
        with self.assertRaises(B.SurfaceError):
            self.render("claude")

    def test_excluded_cmd_reaching_codex_render_fails(self):
        _write(self.repo, "core/surface/includes/bad.md", "see {{CMD:statusline}}\n")
        with self.assertRaises(B.SurfaceError):
            self.render("codex")
        # ...but the same reference is legal on Claude.
        self.assertIn("includes/bad.md", self.render("claude"))

    def test_unresolved_marker_fails(self):
        _write(self.repo, "core/surface/includes/bad.md", "stray {{WHAT}} token\n")
        with self.assertRaises(B.SurfaceError):
            self.render("claude")


class ExtractionInversionTest(_RepoCase):
    def test_claude_render_inverts_extract(self):
        original = ("# /ca:commit — gate\n\nRead ${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md;\n"
                    "load ${CLAUDE_PLUGIN_ROOT}/skills/tdd/SKILL.md; then /ca:pr.\n")
        template = B.extract(original)
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", template)
        self.assertNotIn("/ca:", template)
        rendered = B.render_text(template, "claude",
                                 cmd_names=frozenset({"commit", "pr"}), where="t")
        self.assertEqual(rendered, original)

    def test_extract_rejects_preexisting_braces(self):
        with self.assertRaises(B.SurfaceError):
            B.extract("already has {{PLUGIN_ROOT}} tokens\n")


class CodexMappingTest(_RepoCase):
    def test_command_becomes_prefixed_skill_with_synthesized_name(self):
        out = self.render("codex")
        text = out["skills/ca-init/SKILL.md"].decode()
        self.assertTrue(text.startswith("---\nname: ca-init\ndescription: Opt this repo in.\n"))

    def test_codex_quotes_yaml_significant_frontmatter_scalars(self):
        _write(self.repo, "core/surface/commands/init.md",
               "---\ndescription: Initialize safely: preserve shared state.\n"
               "argument-hint: [path] | --force\n---\n\n# {{CMD:init}}\n")
        codex = self.render("codex")["skills/ca-init/SKILL.md"].decode()
        self.assertIn('description: "Initialize safely: preserve shared state."\n', codex)
        self.assertIn('argument-hint: "[path] | --force"\n', codex)
        claude = self.render("claude")["commands/init.md"].decode()
        self.assertIn("description: Initialize safely: preserve shared state.\n", claude)
        self.assertIn("argument-hint: [path] | --force\n", claude)

    def test_codex_quotes_partially_quoted_argument_hint(self):
        _write(self.repo, "core/surface/commands/init.md",
               "---\ndescription: Safe init.\n"
               "argument-hint: \"[path]\" (defaults to cwd)\n---\n\n# {{CMD:init}}\n")
        codex = self.render("codex")["skills/ca-init/SKILL.md"].decode()
        self.assertIn('argument-hint: "\\\"[path]\\\" (defaults to cwd)"\n', codex)

    def test_excluded_commands_produce_no_codex_output(self):
        out = self.render("codex")
        self.assertNotIn("skills/ca-statusline/SKILL.md", out)
        self.assertIn("commands/statusline.md", self.render("claude"))

    def test_codex_only_file_skipped_on_claude(self):
        self.assertNotIn("includes/codex-host-notes.md", self.render("claude"))
        self.assertIn("includes/codex-host-notes.md", self.render("codex"))

    def test_catalog_index_generated_sorted(self):
        text = self.render("codex")["skills/INDEX.md"].decode()
        self.assertIn("$ca-init", text)
        self.assertIn("$ca-status", text)
        self.assertNotIn("$ca-statusline", text)
        self.assertLess(text.index("$ca-init"), text.index("$ca-status"))

    def test_readme_never_rendered(self):
        for host in ("claude", "codex"):
            for rel in self.render(host):
                self.assertNotIn("README", rel)


class DeterminismTest(_RepoCase):
    def test_two_renders_are_byte_identical(self):
        for host in ("claude", "codex"):
            self.assertEqual(self.render(host), self.render(host))

    def test_output_is_lf_only(self):
        for host in ("claude", "codex"):
            for rel, data in self.render(host).items():
                self.assertNotIn(b"\r", data, rel)

    def test_crlf_template_is_rejected(self):
        p = Path(self.repo) / "core/surface/includes/crlf.md"
        with open(p, "wb") as f:
            f.write(b"bad line endings\r\n")
        with self.assertRaises(B.SurfaceError):
            self.render("claude")


class CollisionTest(_RepoCase):
    def test_duplicate_output_path_fails(self):
        # Distinct templates can only collide through the host-specific output
        # mapping; force one by marking a template CODEX_ONLY at the exact
        # path the init command's Codex render owns.
        _write(self.repo, "core/surface/skills/ca-init/SKILL.md",
               "---\nname: x\ndescription: collide\n---\nbody\n")
        patched = B.CODEX_ONLY | {"skills/ca-init/SKILL.md"}
        original = B.CODEX_ONLY
        B.CODEX_ONLY = patched
        try:
            with self.assertRaises(B.SurfaceError):
                self.render("codex")
        finally:
            B.CODEX_ONLY = original


class WriteAndCheckTest(_RepoCase):
    def test_write_then_check_green_then_idempotent(self):
        wrote = B.write_all(self.repo)
        self.assertGreater(wrote, 0)
        self.assertEqual(B.check_all(self.repo), [])
        self.assertEqual(B.write_all(self.repo), 0)  # idempotent

    def test_check_flags_modified_missing_and_orphan(self):
        B.write_all(self.repo)
        ca = Path(self.repo) / "plugins" / "ca"
        # modified
        with open(ca / "commands" / "init.md", "ab") as f:
            f.write(b"hand edit\n")
        # missing
        os.remove(ca / "includes" / "notes.md")
        # orphan
        _write(self.repo, "plugins/ca-codex/skills/ca-rogue/SKILL.md", "rogue\n")
        drift = B.check_all(self.repo)
        joined = "\n".join(drift)
        self.assertIn("plugins/ca/commands/init.md", joined)
        self.assertIn("plugins/ca/includes/notes.md", joined)
        self.assertIn("plugins/ca-codex/skills/ca-rogue/SKILL.md", joined)

    def test_write_removes_orphans(self):
        B.write_all(self.repo)
        _write(self.repo, "plugins/ca/skills/stale/SKILL.md", "stale\n")
        B.write_all(self.repo)
        self.assertFalse((Path(self.repo) / "plugins/ca/skills/stale/SKILL.md").exists())

    def test_main_check_exit_codes(self):
        self.assertEqual(B.main(["--check"], repo=self.repo), 1)  # nothing written yet
        B.write_all(self.repo)
        self.assertEqual(B.main(["--check"], repo=self.repo), 0)
        self.assertEqual(B.main(["--bogus"], repo=self.repo), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
