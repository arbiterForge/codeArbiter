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
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


_VISIBILITY_ORDER = ["core", "advanced", "alias", "internal", "deprecated"]
_WORKFLOW_ORDER = [
    "evaluate", "initialize", "change", "review", "decide", "ship",
    "operate", "extend", "help",
]
_COMPATIBILITY = {
    "clockStarts": "published-release",
    "removalRequires": "separately-approved-major",
    "targets": {
        "claude": {
            "publishedWithoutMetadata": "2.16.0",
            "firstContainingRelease": None,
            "retainThrough": "2.x",
            "earliestRemoval": "3.0.0",
        },
        "codex": {
            "publishedWithoutMetadata": "0.8.0",
            "firstContainingRelease": None,
            "retainThrough": "0.x",
            "earliestRemoval": "1.0.0",
        },
        "pi": {
            "publishedWithoutMetadata": "0.9.0",
            "firstContainingRelease": None,
            "retainThrough": "0.x",
            "earliestRemoval": "1.0.0",
        },
    },
}


def _write_registry(root, commands, **overrides):
    document = {
        "schemaVersion": 1,
        "visibilityOrder": _VISIBILITY_ORDER,
        "workflowOrder": _WORKFLOW_ORDER,
        "compatibility": _COMPATIBILITY,
        "commands": dict(sorted(commands.items())),
    }
    document.update(overrides)
    return _write(
        root,
        "core/surface/command-routes.json",
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
    )


def _frontmatter(text):
    end = text.find("\n---\n", 4)
    if not text.startswith("---\n") or end < 0:
        raise AssertionError("rendered command has no complete frontmatter")
    return text[:end + len("\n---\n")]


class _RepoCase(unittest.TestCase):
    """Base: a synthetic repo with a minimal surface tree."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.repo = self._td.name
        self.addCleanup(self._td.cleanup)
        _write(
            self.repo,
            "core/hosts.json",
            (REPO_ROOT / "core" / "hosts.json").read_text(encoding="utf-8"),
        )
        _write_registry(
            self.repo,
            {
                "init": {
                    "visibility": "core", "workflow": "initialize",
                    "canonical": "init", "legacyRoutes": [],
                },
                "status": {
                    "visibility": "core", "workflow": "operate",
                    "canonical": "status", "legacyRoutes": [],
                },
                "statusline": {
                    "visibility": "advanced", "workflow": "operate",
                    "canonical": "statusline", "legacyRoutes": [],
                },
            },
        )
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
               "# catalog\n\n<!-- command-visibility-summary -->\n\n"
               "| {{CMD:init}} | opt in |\n{{IF:claude}}\n| {{CMD:statusline}} | statusline |\n{{END}}\n")
        _write(self.repo, "core/surface/SPRINT.md", "Sprint doc. {{CMD:init}}.\n")
        _write(self.repo, "core/surface/arbiter.md",
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
        self.assertIn("[routines/tdd/SKILL.md](../../routines/tdd/SKILL.md)", text)
        self.assertIn("[skills/ca-init/SKILL.md](../ca-init/SKILL.md)", text)
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", text)
        self.assertNotIn("${PLUGIN_ROOT}", text)
        self.assertIn("# $ca-status", text)

    def test_codex_entry_skill_paths_survive_the_routines_rewrite(self):
        # A codex-side conditional may name an entry skill path directly;
        # skills/ca-* is codex-native and must NOT be rewritten to routines/.
        _write(self.repo, "core/surface/includes/entry.md",
               "{{IF:codex}}see {{PLUGIN_ROOT}}/skills/ca-init/SKILL.md{{END}}\n"
               "shared: {{PLUGIN_ROOT}}/skills/tdd/SKILL.md\n")
        text = self.render("codex")["includes/entry.md"].decode()
        self.assertIn("[skills/ca-init/SKILL.md](../skills/ca-init/SKILL.md)", text)
        self.assertIn("[routines/tdd/SKILL.md](../routines/tdd/SKILL.md)", text)

    def test_codex_links_only_concrete_packaged_resources(self):
        _write(
            self.repo,
            "core/surface/includes/resource-links.md",
            "existing: {{PLUGIN_ROOT}}/skills/tdd/SKILL.md\n"
            "generic: {{PLUGIN_ROOT}}/skills/<name>/SKILL.md\n"
            "absent: {{PLUGIN_ROOT}}/tools/farm.js\n",
        )
        text = self.render("codex")["includes/resource-links.md"].decode()
        self.assertIn(
            "existing: [routines/tdd/SKILL.md](../routines/tdd/SKILL.md)", text
        )
        self.assertIn(
            "generic: [routines/<name>/SKILL.md](../routines/<name>/SKILL.md)",
            text,
        )
        self.assertIn("absent: tools/farm.js", text)
        self.assertNotIn("[tools/farm.js]", text)

    def test_executable_root_token_survives_while_navigation_links_render(self):
        _write(
            self.repo,
            "plugins/ca-codex/hooks/_releaselib.py",
            "#!/usr/bin/env python3\n",
        )
        _write(
            self.repo,
            "core/surface/includes/release-helper.md",
            "run `\"$PY\" \"{{PLUGIN_ROOT}}/hooks/_releaselib.py\" list-targets`; "
            "then see {{PLUGIN_ROOT}}/skills/tdd/SKILL.md\n",
        )
        codex = self.render("codex")["includes/release-helper.md"].decode()
        self.assertIn('"${PLUGIN_ROOT}/hooks/_releaselib.py" list-targets', codex)
        self.assertIn("[routines/tdd/SKILL.md](../routines/tdd/SKILL.md)", codex)
        self.assertNotIn("[hooks/_releaselib.py]", codex)
        claude = self.render("claude")["includes/release-helper.md"].decode()
        self.assertIn('"${CLAUDE_PLUGIN_ROOT}/hooks/_releaselib.py" list-targets', claude)

    def test_packaged_python_hook_in_executable_position_keeps_runtime_root(self):
        _write(
            self.repo,
            "plugins/ca-codex/hooks/tribunal-usage.py",
            "#!/usr/bin/env python3\n",
        )
        for interpreter in ('"$PY"', "python", "python3"):
            with self.subTest(interpreter=interpreter):
                _write(
                    self.repo,
                    "core/surface/includes/tribunal-helper.md",
                    f'run `{interpreter} "{{{{PLUGIN_ROOT}}}}/'
                    'hooks/tribunal-usage.py" observe`\n',
                )
                codex = self.render("codex")[
                    "includes/tribunal-helper.md"
                ].decode()
                self.assertIn(
                    '"${PLUGIN_ROOT}/hooks/tribunal-usage.py" observe', codex
                )
                self.assertNotIn("[hooks/tribunal-usage.py]", codex)

    def test_missing_python_hook_is_not_promoted_to_executable_path(self):
        for interpreter in ('"$PY"', "python", "python3"):
            with self.subTest(interpreter=interpreter):
                _write(
                    self.repo,
                    "core/surface/includes/missing-helper.md",
                    f'run `{interpreter} "{{{{PLUGIN_ROOT}}}}/'
                    'hooks/not-packaged.py" observe`\n',
                )
                codex = self.render("codex")[
                    "includes/missing-helper.md"
                ].decode()
                self.assertIn('"hooks/not-packaged.py" observe', codex)
                self.assertNotIn("${PLUGIN_ROOT}/hooks/not-packaged.py", codex)

    def test_packaged_python_hook_outside_executable_position_stays_a_link(self):
        _write(
            self.repo,
            "plugins/ca-codex/hooks/tribunal-usage.py",
            "#!/usr/bin/env python3\n",
        )
        _write(
            self.repo,
            "core/surface/includes/tribunal-helper.md",
            "read {{PLUGIN_ROOT}}/hooks/tribunal-usage.py first\n",
        )
        codex = self.render("codex")["includes/tribunal-helper.md"].decode()
        self.assertIn(
            "[hooks/tribunal-usage.py](../hooks/tribunal-usage.py)", codex
        )
        self.assertNotIn("${PLUGIN_ROOT}/hooks/tribunal-usage.py", codex)

    def test_packaged_python_hook_requires_same_line_exact_interpreter_token(self):
        _write(
            self.repo,
            "plugins/ca-codex/hooks/tribunal-usage.py",
            "#!/usr/bin/env python3\n",
        )
        for prefix in ("python\n", "notpython ", "not-python ", "my_python "):
            with self.subTest(prefix=prefix):
                _write(
                    self.repo,
                    "core/surface/includes/tribunal-helper.md",
                    f"{prefix}{{{{PLUGIN_ROOT}}}}/hooks/tribunal-usage.py\n",
                )
                codex = self.render("codex")[
                    "includes/tribunal-helper.md"
                ].decode()
                self.assertIn(
                    "[hooks/tribunal-usage.py](../hooks/tribunal-usage.py)",
                    codex,
                )
                self.assertNotIn("${PLUGIN_ROOT}/hooks/tribunal-usage.py", codex)

    def test_codex_normalizes_backslash_resource_links_to_posix(self):
        _write(
            self.repo,
            "core/surface/skills/foo/SKILL.md",
            "---\nname: foo\ndescription: Foo.\n---\n\n# foo\n",
        )
        _write(
            self.repo,
            "core/surface/includes/backslash-link.md",
            "see {{PLUGIN_ROOT}}/routines\\foo\\SKILL.md\n",
        )
        codex = self.render("codex")["includes/backslash-link.md"].decode()
        self.assertIn(
            "[routines/foo/SKILL.md](../routines/foo/SKILL.md)", codex
        )
        self.assertNotIn("\\", codex)

    def test_codex_rejects_unsafe_resource_path_before_rendering_link(self):
        for resource in (
                "../escaped.md", "./escaped.md", "nested/./escaped.md",
                "/escaped.md", "C:/escaped.md", r"C:\escaped.md",
                r"nested\..\escaped.md"):
            with self.subTest(resource=resource):
                _write(
                    self.repo,
                    "core/surface/includes/escaped.md",
                    f"load {{{{PLUGIN_ROOT}}}}/{resource}\n",
                )
                with self.assertRaises(B.SurfaceError):
                    self.render("codex")

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


class ReviewFeedbackRegressionTest(unittest.TestCase):
    def test_surface_readme_describes_active_codex_agent_output(self):
        text = (REPO_ROOT / "core" / "surface" / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "| `agents/**` | `agents/**` | `agents/**` "
            "(Markdown resource charters; never native registration) |",
            text,
        )
        self.assertNotIn("reserved for Task 3 resource-charter generation", text)

    def test_codex_tribunal_usage_receipt_resolves_interpreter_and_hook(self):
        codex = B.render_all(REPO_ROOT, "codex")[
            "routines/tribunal/SKILL.md"
        ].decode()
        self.assertIn(
            "PY=python3; { command -v python3 >/dev/null 2>&1 && "
            "python3 --version >/dev/null 2>&1; } || PY=python",
            codex,
        )
        self.assertIn(
            '"$PY" "${PLUGIN_ROOT}/hooks/tribunal-usage.py" observe '
            "--thread-id <agent-thread-id>",
            codex,
        )
        self.assertNotIn(
            "Run `hooks/tribunal-usage.py observe --thread-id", codex
        )

    def test_tribunal_lens_directory_matches_each_host_surface(self):
        codex = B.render_all(REPO_ROOT, "codex")[
            "agents/tribunal-lens-reviewer.md"
        ].decode()
        self.assertIn("under routines/tribunal/references/lenses/", codex)
        self.assertIn(
            "names a card under routines/tribunal/references/lenses/", codex
        )
        claude = B.render_all(REPO_ROOT, "claude")[
            "agents/tribunal-lens-reviewer.md"
        ].decode()
        self.assertIn("under skills/tribunal/references/lenses/", claude)
        self.assertIn(
            "names a card under skills/tribunal/references/lenses/", claude
        )
        pi = B.render_all(REPO_ROOT, "pi")[
            "agents/tribunal-lens-reviewer.md"
        ].decode()
        self.assertIn("under skills/tribunal/references/lenses/", pi)
        self.assertIn(
            "names a card under skills/tribunal/references/lenses/", pi
        )

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

    def test_codex_catalog_location_is_unchanged(self):
        out = self.render("codex")
        self.assertIn("skills/INDEX.md", out)
        self.assertNotIn("SKILLS.md", out)

    def test_readme_never_rendered(self):
        for host in ("claude", "codex"):
            for rel in self.render(host):
                self.assertNotIn("README", rel)

    def test_codex_charter_strips_executable_frontmatter_and_keeps_policy_metadata(self):
        _write(
            self.repo,
            "core/surface/agents/backend-author.md",
            "---\nname: backend-author\ndescription: bounded author\n"
            "tools: Read, Write\nclassification: author\npi-skills: [tdd]\n"
            "model: sonnet\n---\n\n# Backend Author\n\n"
            "Writes only inside the assigned worktree.\n",
        )
        charter = self.render("codex")["agents/backend-author.md"].decode()
        self.assertIn("name: backend-author\n", charter)
        self.assertIn("description: bounded author\n", charter)
        self.assertIn("classification: author\n", charter)
        self.assertNotIn("\ntools:", charter)
        self.assertNotIn("\npi-skills:", charter)
        self.assertNotIn("\nmodel:", charter)
        self.assertIn("Writes only inside the assigned worktree.", charter)

    def test_real_codex_charters_have_exact_inventory_and_dispatch_policy(self):
        out = B.render_all(str(REPO_ROOT), "codex")
        expected = {
            "architecture-drift-reviewer", "auth-crypto-reviewer", "backend-author",
            "checkpoint-aggregator", "coverage-auditor", "decision-challenger",
            "dependency-reviewer", "design-quality-reviewer", "finding-triage",
            "frontend-author", "grader", "infra-author", "map-deps", "map-structure",
            "migration-reviewer", "scout", "security-reviewer", "tribunal-lens-reviewer",
            "verdict-aggregator",
        }
        actual = {
            path.removeprefix("agents/").removesuffix(".md")
            for path in out
            if path.startswith("agents/") and path.endswith(".md")
            and path != "agents/INDEX.md"
        }
        self.assertEqual(actual, expected)
        index = out["agents/INDEX.md"].decode()
        self.assertIn("generic agent thread", index)
        self.assertIn("not native Codex registrations", index)
        self.assertIn("`backend-author`, `frontend-author`, `infra-author`", index)
        self.assertIn("fresh isolated worktree/thread required", index)
        self.assertIn("no file mutation", index)
        self.assertIn("`scout`, map roles", index)
        self.assertIn("`verdict-aggregator`", index)
        self.assertIn("`checkpoint-aggregator`, `tribunal-lens-reviewer`", index)
        self.assertIn("declared checkpoint/finding output path", index)
        self.assertIn("do not translate Claude `haiku`/`sonnet`", index)
        self.assertIn(
            "<!-- codearbiter-codex-agent-route-contract: "
            "literal_route_lines=19 literal_route_occurrences=20 "
            "generic_route_lines=6 generic_route_occurrences=6 -->",
            index,
        )
        self.assertNotIn("\nmodel:", index)
        for name in expected:
            charter = out[f"agents/{name}.md"].decode()
            self.assertIn(f"name: {name}\n", charter)
            self.assertIn("description:", charter)
            self.assertIn("classification:", charter)
            self.assertNotIn("\ntools:", charter)
            self.assertNotIn("\npi-skills:", charter)
            self.assertNotIn("\nmodel:", charter)
        manifest = json.loads(
            (REPO_ROOT / "plugins/ca-codex/.codex-plugin/plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotIn("agents", manifest)


class CommandCatalogTest(_RepoCase):
    def setUp(self):
        super().setUp()
        _write(
            self.repo,
            "core/surface/commands/init.md",
            "---\ndescription: Initialize a project.\nargument-hint: (none)\n---\n\n"
            "# {{CMD:init}}\n\n"
            "<!-- command-mode:--brownfield legacy-route:create-context -->\n",
        )
        _write(
            self.repo,
            "core/surface/commands/status.md",
            "---\ndescription: Show project state.\nargument-hint: (none)\n---\n\n"
            "# {{CMD:status}}\n",
        )
        _write(
            self.repo,
            "core/surface/commands/audit.md",
            "---\ndescription: Assemble an audit packet.\nargument-hint: (none)\n---\n\n"
            "# {{CMD:audit}}\n",
        )
        _write(
            self.repo,
            "core/surface/commands/conflict.md",
            "---\ndescription: Surface a rule conflict.\nargument-hint: (none)\n---\n\n"
            "# {{CMD:conflict}}\n",
        )
        _write(
            self.repo,
            "core/surface/commands/create-context.md",
            "---\ndescription: Populate brownfield context.\nargument-hint: (none)\n---\n\n"
            "# {{CMD:create-context}}\n",
        )
        _write(
            self.repo,
            "core/surface/commands/btw.md",
            "---\ndescription: Answer a quick question.\nargument-hint: <question>\n---\n\n"
            "# {{CMD:btw}}\n",
        )
        _write_registry(
            self.repo,
            {
                "audit": {
                    "visibility": "advanced", "workflow": "operate",
                    "canonical": "audit", "legacyRoutes": [],
                },
                "btw": {
                    "visibility": "deprecated", "workflow": "help",
                    "replacement": "ask the question directly",
                },
                "conflict": {
                    "visibility": "internal", "workflow": "decide",
                    "canonical": "conflict", "legacyRoutes": [],
                },
                "create-context": {
                    "visibility": "alias", "workflow": "initialize",
                    "canonical": "init", "replacement": "init --brownfield",
                },
                "init": {
                    "visibility": "core", "workflow": "initialize",
                    "canonical": "init", "legacyRoutes": ["create-context"],
                    "modes": ["--brownfield"],
                },
                "status": {
                    "visibility": "core", "workflow": "operate",
                    "canonical": "status", "legacyRoutes": [],
                },
                "statusline": {
                    "visibility": "advanced", "workflow": "operate",
                    "canonical": "statusline", "legacyRoutes": [],
                },
            },
        )

    def test_executable_frontmatter_retains_only_loader_facing_fields(self):
        claude = self.render("claude")["commands/init.md"].decode()
        codex = self.render("codex")["skills/ca-init/SKILL.md"].decode()
        pi = self.render("pi")["skills/ca-init/SKILL.md"].decode()
        self.assertEqual(
            _frontmatter(claude),
            "---\ndescription: Initialize a project.\nargument-hint: (none)\n---\n",
        )
        expected_skill = (
            "---\nname: ca-init\ndescription: Initialize a project.\n"
            "argument-hint: (none)\n---\n"
        )
        self.assertEqual(_frontmatter(codex), expected_skill)
        self.assertEqual(_frontmatter(pi), expected_skill)

    def test_pi_catalog_groups_installed_entries_and_reports_visibility_counts(self):
        catalog = self.render("pi")["SKILLS.md"].decode()
        self.assertIn(
            "| Core | 2 |\n"
            "| Advanced | 1 |\n"
            "| Canonical total | 3 |\n"
            "| Compatibility aliases | 1 |\n"
            "| Internal | 1 |\n"
            "| Deprecated | 1 |\n"
            "| **Total** | **6** |",
            catalog,
        )
        self.assertIn(
            "## Core\n\n### Initialize\n\n"
            "| Skill | Purpose |\n|---|---|\n"
            "| `/ca-init` | Initialize a project. |",
            catalog,
        )
        self.assertIn(
            "## Advanced\n\n### Operate\n\n"
            "| Skill | Purpose |\n|---|---|\n"
            "| `/ca-audit` | Assemble an audit packet. |",
            catalog,
        )
        self.assertIn(
            "## Compatibility aliases\n\n### Initialize\n\n"
            "| Skill | Purpose | Replacement |\n|---|---|---|\n"
            "| `/ca-create-context` | Populate brownfield context. | `/ca-init --brownfield` |",
            catalog,
        )

    def test_every_human_command_catalog_reports_host_visibility_counts(self):
        expected = {
            "claude": (2, 2, 1, 1, 1, 7),
            "codex": (2, 1, 1, 1, 1, 6),
            "pi": (2, 1, 1, 1, 1, 6),
        }
        for host, counts in expected.items():
            with self.subTest(host=host):
                catalog = self.render(host)["COMMANDS.md"].decode()
                core, advanced, aliases, internal, deprecated, total = counts
                self.assertIn(
                    "## Installed surface\n\n"
                    "| Visibility | Count |\n"
                    "|---|---:|\n"
                    f"| Core | {core} |\n"
                    f"| Advanced | {advanced} |\n"
                    f"| Canonical total | {core + advanced} |\n"
                    f"| Compatibility aliases | {aliases} |\n"
                    f"| Internal | {internal} |\n"
                    f"| Deprecated | {deprecated} |\n"
                    f"| **Total** | **{total}** |",
                    catalog,
                )

    def test_all_hosts_receive_literal_sidecars_for_their_installed_routes(self):
        claude = json.loads(self.render("claude")["generated/command-catalog.json"])
        codex = json.loads(self.render("codex")["generated/command-catalog.json"])
        pi = json.loads(self.render("pi")["generated/command-catalog.json"])
        expected_entries = [
            {
                "name": "audit", "description": "Assemble an audit packet.",
                "skillPath": "skills/ca-audit/SKILL.md",
                "visibility": "advanced", "workflow": "operate", "canonical": "audit",
                "legacyRoutes": [],
            },
            {
                "name": "btw", "description": "Answer a quick question.",
                "skillPath": "skills/ca-btw/SKILL.md",
                "visibility": "deprecated", "workflow": "help",
                "replacement": "ask the question directly",
            },
            {
                "name": "conflict", "description": "Surface a rule conflict.",
                "skillPath": "skills/ca-conflict/SKILL.md",
                "visibility": "internal", "workflow": "decide", "canonical": "conflict",
                "legacyRoutes": [],
            },
            {
                "name": "create-context", "description": "Populate brownfield context.",
                "skillPath": "skills/ca-create-context/SKILL.md",
                "visibility": "alias", "workflow": "initialize", "canonical": "init",
                "replacement": "init --brownfield",
            },
            {
                "name": "init", "description": "Initialize a project.",
                "skillPath": "skills/ca-init/SKILL.md",
                "visibility": "core", "workflow": "initialize", "canonical": "init",
                "legacyRoutes": ["create-context"],
            },
            {
                "name": "status", "description": "Show project state.",
                "skillPath": "skills/ca-status/SKILL.md",
                "visibility": "core", "workflow": "operate", "canonical": "status",
                "legacyRoutes": [],
            },
        ]
        expected_pi = {
            "schemaVersion": 1,
            "visibilityOrder": _VISIBILITY_ORDER,
            "workflowOrder": _WORKFLOW_ORDER,
            "compatibility": _COMPATIBILITY,
            "commands": {item["name"]: item for item in expected_entries},
        }
        self.assertEqual(pi, expected_pi)
        self.assertEqual(set(codex["commands"]), set(expected_pi["commands"]))
        self.assertEqual(
            set(claude["commands"]),
            {"audit", "btw", "conflict", "create-context", "init", "status", "statusline"},
        )
        self.assertEqual(claude["commands"]["audit"]["commandPath"], "commands/audit.md")
        self.assertEqual(codex["commands"]["audit"]["skillPath"], "skills/ca-audit/SKILL.md")

    def test_invalid_registry_schema_and_alias_graphs_fail_specifically(self):
        def valid_commands():
            return {
                "pr": {
                    "visibility": "core", "workflow": "ship", "canonical": "pr",
                    "legacyRoutes": ["cleanup"], "modes": ["--cleanup"],
                },
                "cleanup": {
                    "visibility": "alias", "workflow": "ship", "canonical": "pr",
                    "replacement": "pr --cleanup",
                },
                "audit": {
                    "visibility": "advanced", "workflow": "operate",
                    "canonical": "audit", "legacyRoutes": [],
                },
                "conflict": {
                    "visibility": "internal", "workflow": "decide",
                    "canonical": "conflict", "legacyRoutes": [],
                },
                "btw": {
                    "visibility": "deprecated", "workflow": "help",
                    "replacement": "ask the question directly",
                },
            }

        cases = []

        def case(label, message, mutate, command_names=None, body_markers=None):
            commands = valid_commands()
            mutate(commands)
            cases.append((label, message, commands, command_names, body_markers))

        case("missing visibility", "visibility", lambda items: items["cleanup"].pop("visibility"))
        case("invalid visibility", "visibility", lambda items: items["cleanup"].update(visibility="public"))
        case("missing workflow", "workflow", lambda items: items["cleanup"].pop("workflow"))
        case("invalid workflow", "workflow", lambda items: items["cleanup"].update(workflow="triage"))
        case("canonical missing", "canonical", lambda items: items["pr"].pop("canonical"))
        case("canonical mismatch", "must equal its route slug", lambda items: items["pr"].update(canonical="review"))
        case("legacy routes missing", "legacyRoutes", lambda items: items["pr"].pop("legacyRoutes"))
        case("legacy routes not a list", "legacyRoutes", lambda items: items["pr"].update(legacyRoutes="cleanup"))
        case("duplicate legacy routes", "legacyRoutes.*duplicate", lambda items: items["pr"].update(legacyRoutes=["cleanup", "cleanup"]))
        case("alias replacement missing", "replacement", lambda items: items["cleanup"].pop("replacement"))
        case("dangling target", "target.*missing", lambda items: items["cleanup"].update(canonical="missing"))
        def drop_reverse_route(items):
            items["pr"].update(legacyRoutes=["cleanup", "ghost"])
        case("reverse legacy route missing", "legacy route closure", drop_reverse_route)
        case("replacement canonical mismatch", "replacement.*canonical", lambda items: items["cleanup"].update(replacement="init --cleanup"))
        case("replacement mode undeclared", "replacement mode", lambda items: items["cleanup"].update(replacement="pr --watch"))
        case("modes missing", "modes", lambda items: items["pr"].pop("modes"))
        case("deprecated guidance missing", "replacement", lambda items: items["btw"].pop("replacement"))

        def alias_chain(items):
            items["redirect"] = {
                "visibility": "alias", "workflow": "ship", "canonical": "cleanup",
                "replacement": "cleanup --again",
            }
        case("alias chain", "alias target", alias_chain)

        def unsorted(items):
            items["watch"] = {
                "visibility": "alias", "workflow": "ship", "canonical": "pr",
                "replacement": "pr --watch",
            }
            items["pr"].update(
                legacyRoutes=["watch", "cleanup"], modes=["--watch", "--cleanup"]
            )
        case("unsorted legacy routes and modes", "sorted", unsorted)

        def host_excluded(items):
            items.clear()
            items["statusline"] = {
                "visibility": "advanced", "workflow": "operate",
                "canonical": "statusline", "legacyRoutes": ["cleanup"],
                "modes": ["--cleanup"],
            }
            items["cleanup"] = {
                "visibility": "alias", "workflow": "operate",
                "canonical": "statusline", "replacement": "statusline --cleanup",
            }
        case("host-excluded target", "not installed.*codex", host_excluded)

        case(
            "registry missing a command", "inventory.*missing",
            lambda items: items.pop("cleanup"),
            command_names=["pr", "cleanup", "audit", "conflict", "btw"],
        )
        case(
            "registry has an extra command", "inventory.*extra",
            lambda items: items.update(ghost={
                "visibility": "advanced", "workflow": "help",
                "canonical": "ghost", "legacyRoutes": [],
            }),
            command_names=["pr", "cleanup", "audit", "conflict", "btw"],
        )
        case(
            "mode marker missing", "command-mode.*missing",
            lambda items: None,
            body_markers={"pr": ""},
        )

        for label, message, commands, command_names, body_markers in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as repo:
                _write(repo, "core/hosts.json",
                       (REPO_ROOT / "core/hosts.json").read_text(encoding="utf-8"))
                names = command_names or list(commands)
                markers = {"pr": "<!-- command-mode:--cleanup legacy-route:cleanup -->\n"}
                markers.update(body_markers or {})
                for name in names:
                    _write(
                        repo,
                        f"core/surface/commands/{name}.md",
                        "---\ndescription: test\nargument-hint: (none)\n---\n\n"
                        f"# {{{{CMD:{name}}}}}\n\n{markers.get(name, '')}",
                    )
                _write_registry(repo, commands)
                with self.assertRaisesRegex(B.SurfaceError, message):
                    B.render_all(repo, "claude")

    def test_registry_json_rejects_duplicate_keys_and_unknown_top_level_fields(self):
        duplicate = (
            '{"schemaVersion":1,"visibilityOrder":[],"workflowOrder":[],'
            '"compatibility":{},"commands":{},"commands":{}}\n'
        )
        _write(self.repo, "core/surface/command-routes.json", duplicate)
        with self.assertRaisesRegex(B.SurfaceError, "duplicate.*commands"):
            self.render("claude")

        _write_registry(self.repo, {}, surprise=True)
        with self.assertRaisesRegex(B.SurfaceError, "unknown.*surprise"):
            self.render("claude")

    def test_first_containing_release_must_follow_the_published_baseline(self):
        registry_path = Path(self.repo) / "core/surface/command-routes.json"
        original = json.loads(registry_path.read_text(encoding="utf-8"))
        for version, message in (
            ("2.16.0", "must follow publishedWithoutMetadata"),
            ("3.0.0", "outside retainThrough"),
        ):
            with self.subTest(version=version):
                document = json.loads(json.dumps(original))
                document["compatibility"]["targets"]["claude"][
                    "firstContainingRelease"
                ] = version
                _write(
                    self.repo,
                    "core/surface/command-routes.json",
                    json.dumps(document, indent=2) + "\n",
                )
                with self.assertRaisesRegex(B.SurfaceError, message):
                    self.render("claude")
        _write(
            self.repo,
            "core/surface/command-routes.json",
            json.dumps(original, indent=2) + "\n",
        )
        self.render("claude")

    def test_real_registry_taxonomy_and_host_gaps_are_frozen(self):
        expected = {
            "core": {
                "add-dep", "adr", "chore", "commit", "doctor", "feature", "fix",
                "init", "override", "pr", "preview", "refactor", "release", "review",
                "spike", "sprint", "status", "task",
            },
            "advanced": {
                "adr-status", "audit", "checkpoint", "commands", "debug", "metrics",
                "new-skill", "prune", "reconcile", "standup", "statusline",
                "threat-model", "tribunal",
            },
            "alias": {"cleanup", "context-check", "create-context", "decompose", "watch"},
            "internal": {"conflict"},
            "deprecated": {"btw"},
        }
        catalogs = {
            host: json.loads(B.render_all(str(REPO_ROOT), host)["generated/command-catalog.json"])
            for host in ("claude", "codex", "pi")
        }
        claude_by_visibility = {
            visibility: {entry["name"] for entry in catalogs["claude"]["commands"].values()
                         if entry["visibility"] == visibility}
            for visibility in expected
        }
        self.assertEqual(claude_by_visibility, expected)
        all_routes = set().union(*expected.values())
        self.assertEqual(set(catalogs["claude"]["commands"]), all_routes)
        self.assertEqual(
            set(catalogs["codex"]["commands"]),
            all_routes - {"prune", "statusline"},
        )
        self.assertEqual(
            set(catalogs["pi"]["commands"]),
            all_routes - {"statusline"},
        )


class PiMappingTest(_RepoCase):
    def test_pi_commands_use_pi_aliases_in_bodies_and_catalog(self):
        out = self.render("pi")
        self.assertIn("# /ca-init", out["skills/ca-init/SKILL.md"].decode())
        catalog = out["SKILLS.md"].decode()
        self.assertIn("`/ca-init`", catalog)
        self.assertNotIn("`$ca-init`", catalog)

    def test_pi_catalog_relocation_removes_loader_scanned_markdown_orphan(self):
        old_catalog = _write(
            self.repo, "plugins/ca-pi/skills/INDEX.md", "stale catalog\n"
        )
        B.write_all(self.repo, hosts=("pi",))
        plugin = Path(self.repo) / "plugins/ca-pi"
        self.assertTrue((plugin / "SKILLS.md").is_file())
        self.assertFalse(old_catalog.exists())
        self.assertEqual(list((plugin / "skills").glob("*.md")), [])

    def test_pi_skill_author_keeps_the_routine_catalog_for_authoring(self):
        template = (
            REPO_ROOT / "core/surface/skills/skill-author/SKILL.md"
        ).read_text(encoding="utf-8")
        _write(self.repo, "core/surface/skills/skill-author/SKILL.md", template)
        _write(self.repo, "core/surface/skills/INDEX.md", "# routine catalog\n")

        pi_text = self.render("pi")["routines/skill-author/SKILL.md"].decode()
        codex_text = self.render("codex")["routines/skill-author/SKILL.md"].decode()
        self.assertIn("<plugin-root>/routines/INDEX.md", pi_text)
        self.assertNotIn("<plugin-root>/SKILLS.md", pi_text)
        self.assertIn("[routines/INDEX.md](../INDEX.md)", codex_text)

    def test_pi_generated_command_catalog_is_an_orphan_cleaned_managed_surface(self):
        B.write_all(self.repo, hosts=("pi",))
        rogue = _write(self.repo, "plugins/ca-pi/generated/rogue.json", "{}\n")
        drift = B.check_all(self.repo, hosts=("pi",))
        self.assertIn(
            "plugins/ca-pi/generated/rogue.json: orphan (no template renders it)",
            drift,
        )
        B.write_all(self.repo, hosts=("pi",))
        self.assertFalse(rogue.exists())

    def test_pi_skill_envelope_terminator_fails_before_outputs_change(self):
        B.write_all(self.repo, hosts=("pi",))
        plugin = Path(self.repo) / "plugins" / "ca-pi"
        before_skill = (plugin / "skills" / "ca-init" / "SKILL.md").read_bytes()
        before_catalog = (plugin / "generated" / "command-catalog.json").read_bytes()
        _write(
            self.repo,
            "core/surface/commands/init.md",
            "---\ndescription: Opt this repo in.\nargument-hint: (none)\n---\n\n"
            "# {{CMD:init}}\n\nreserved </skill> termination\n",
        )
        with self.assertRaisesRegex(B.SurfaceError, "reserved </skill>"):
            B.write_all(self.repo, hosts=("pi",))
        self.assertEqual(
            (plugin / "skills" / "ca-init" / "SKILL.md").read_bytes(),
            before_skill,
        )
        self.assertEqual(
            (plugin / "generated" / "command-catalog.json").read_bytes(),
            before_catalog,
        )

    def test_real_pi_role_catalog_is_a_19_role_explicit_resource_bijection(self):
        out = B.render_all(str(REPO_ROOT), "pi")
        roles = json.loads(out["generated/roles.json"])
        agents = sorted(
            path.removeprefix("agents/").removesuffix(".md")
            for path in out
            if path.startswith("agents/") and path.endswith(".md")
            and path != "agents/INDEX.md"
        )
        self.assertEqual(len(agents), 19)
        self.assertEqual(sorted(role["name"] for role in roles), agents)
        self.assertEqual(len({role["name"] for role in roles}), 19)
        # security-controls.md assumes these three reviewers exist; a count pin
        # alone would stay green if one were swapped for an unrelated role.
        self.assertLessEqual(
            {"security-reviewer", "auth-crypto-reviewer", "dependency-reviewer"},
            {role["name"] for role in roles},
        )

        authors = {"backend-author", "frontend-author", "infra-author"}
        skill_map = {
            "architecture-drift-reviewer": ["decision-variance"],
            "auth-crypto-reviewer": ["secret-handling"],
            "backend-author": ["tdd"],
            "coverage-auditor": ["tdd"],
            "decision-challenger": ["decision-variance"],
            "frontend-author": ["tdd"],
            "grader": ["decision-variance"],
            "infra-author": ["tdd"],
            "map-deps": ["tribunal"],
            "map-structure": ["tribunal"],
            "scout": ["decision-variance", "context-creation"],
            **{
                name: ["tribunal"] for name in agents
                if name.startswith("tribunal-")
            },
        }
        for role in roles:
            name = role["name"]
            self.assertEqual(
                role["classification"],
                "author" if name in authors else "reviewer",
            )
            self.assertEqual(
                role["skillPaths"],
                [f"routines/{skill}/SKILL.md" for skill in skill_map.get(name, [])],
            )
            self.assertIn(role["charterPath"], out)
            for skill_path in role["skillPaths"]:
                self.assertIn(skill_path, out)

        claude = B.render_all(str(REPO_ROOT), "claude")
        for path in (path for path in claude if path.startswith("agents/") and path.endswith(".md")):
            self.assertNotIn("\nclassification:", claude[path].decode())
            self.assertNotIn("\npi-skills:", claude[path].decode())
            self.assertEqual(
                claude[path],
                (REPO_ROOT / "plugins" / "ca" / path).read_bytes(),
            )

    def test_pi_role_frontmatter_rejects_missing_or_unrendered_explicit_skills(self):
        _write(
            self.repo,
            "core/surface/agents/backend-author.md",
            "---\nname: backend-author\ndescription: author\ntools: Read, Write\n"
            "classification: author\npi-skills: [missing]\nmodel: inherit\n---\nbody\n",
        )
        with self.assertRaisesRegex(B.SurfaceError, "skills are missing"):
            self.render("pi")
        _write(
            self.repo,
            "core/surface/agents/backend-author.md",
            "---\nname: backend-author\ndescription: author\ntools: Read, Write\n"
            "classification: guessed\npi-skills: []\nmodel: inherit\n---\nbody\n",
        )
        with self.assertRaisesRegex(B.SurfaceError, "classification"):
            self.render("pi")


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

    def test_one_render_loads_the_descriptor_registry_once(self):
        with mock.patch.object(
            B, "load_host_descriptors", wraps=B.load_host_descriptors
        ) as loader:
            self.render("pi")
        self.assertEqual(loader.call_count, 1)


class CollisionTest(_RepoCase):
    def test_duplicate_output_path_fails(self):
        # Distinct templates can only collide through descriptor output rules.
        _write(self.repo, "core/surface/skills/ca-init/SKILL.md",
               "---\nname: x\ndescription: collide\n---\nbody\n")
        hosts_path = Path(self.repo) / "core" / "hosts.json"
        document = json.loads(hosts_path.read_text(encoding="utf-8"))
        codex = next(host for host in document["hosts"] if host["name"] == "codex")
        codex["surface"]["rules"].insert(0, {
            "source_prefix": "skills/ca-init/SKILL.md",
            "output_pattern": "skills/ca-init/SKILL.md",
            "exclude": [],
        })
        hosts_path.write_text(json.dumps(document), encoding="utf-8", newline="\n")
        with self.assertRaises(B.SurfaceError):
            self.render("codex")


class WriteAndCheckTest(_RepoCase):
    def test_custom_catalog_outside_managed_subtrees_is_discovered_and_replaced(self):
        hosts_path = Path(self.repo) / "core/hosts.json"
        document = json.loads(hosts_path.read_text(encoding="utf-8"))
        pi = next(host for host in document["hosts"] if host["name"] == "pi")
        pi["surface"]["catalog"] = "docs/ENTRY-CATALOG.md"
        hosts_path.write_text(json.dumps(document), encoding="utf-8", newline="\n")
        stale_catalog = _write(
            self.repo,
            "plugins/ca-pi/docs/ENTRY-CATALOG.md",
            "stale descriptor catalog\n",
        )

        descriptor = next(
            host for host in B.load_host_descriptors(self.repo)
            if host.name == "pi"
        )
        self.assertNotIn("docs", descriptor.managed_subtrees)
        self.assertIn(
            "docs/ENTRY-CATALOG.md", B._disk_files(self.repo, descriptor)
        )
        B.write_all(self.repo, hosts=("pi",))
        self.assertNotEqual(stale_catalog.read_text(encoding="utf-8"),
                            "stale descriptor catalog\n")
        self.assertIn("`/ca-init`", stale_catalog.read_text(encoding="utf-8"))

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

    def test_removed_root_rule_is_flagged_and_cleaned_as_an_orphan(self):
        B.write_all(self.repo)
        hosts_path = Path(self.repo) / "core" / "hosts.json"
        document = json.loads(hosts_path.read_text(encoding="utf-8"))
        claude = next(host for host in document["hosts"] if host["name"] == "claude")
        claude["surface"]["rules"] = [
            rule for rule in claude["surface"]["rules"]
            if rule["source_prefix"] != "COMMANDS.md"
        ]
        hosts_path.write_text(json.dumps(document), encoding="utf-8", newline="\n")

        drift = B.check_all(self.repo, hosts=("claude",))
        self.assertIn(
            "plugins/ca/COMMANDS.md: orphan (no template renders it)", drift
        )
        B.write_all(self.repo, hosts=("claude",))
        self.assertFalse((Path(self.repo) / "plugins/ca/COMMANDS.md").exists())

    def test_removed_root_source_and_all_rules_still_clean_the_managed_file(self):
        B.write_all(self.repo)
        os.remove(Path(self.repo) / "core/surface/COMMANDS.md")
        hosts_path = Path(self.repo) / "core" / "hosts.json"
        document = json.loads(hosts_path.read_text(encoding="utf-8"))
        for host in document["hosts"]:
            host["surface"]["rules"] = [
                rule for rule in host["surface"]["rules"]
                if rule["source_prefix"] != "COMMANDS.md"
            ]
        hosts_path.write_text(json.dumps(document), encoding="utf-8", newline="\n")

        drift = B.check_all(self.repo, hosts=("claude",))
        self.assertIn(
            "plugins/ca/COMMANDS.md: orphan (no template renders it)", drift
        )
        B.write_all(self.repo, hosts=("claude",))
        self.assertFalse((Path(self.repo) / "plugins/ca/COMMANDS.md").exists())

    def test_main_check_exit_codes(self):
        self.assertEqual(B.main(["--check"], repo=self.repo), 1)  # nothing written yet
        B.write_all(self.repo)
        self.assertEqual(B.main(["--check"], repo=self.repo), 0)
        self.assertEqual(B.main(["--bogus"], repo=self.repo), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
