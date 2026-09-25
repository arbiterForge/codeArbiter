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
    "clockStarts": "confirmed-non-draft-github-release",
    "removalRequires": "separately-approved-major",
    "targets": {
        "claude": {
            "publishedWithoutMetadata": "2.16.0",
            "firstContainingRelease": "2.17.0",
            "retainThrough": "2.x",
            "earliestRemoval": "3.0.0",
        },
        "codex": {
            "publishedWithoutMetadata": "0.8.0",
            "firstContainingRelease": "0.9.0",
            "retainThrough": "0.x",
            "earliestRemoval": "1.0.0",
        },
        "pi": {
            "publishedWithoutMetadata": "0.9.0",
            "firstContainingRelease": "0.10.0",
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
            "literal_route_lines=23 literal_route_occurrences=25 "
            "generic_route_lines=2 generic_route_occurrences=2 -->",
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
            (None, "must declare firstContainingRelease"),
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
                "prune", "reconcile", "standup", "statusline",
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

    def test_pi_routine_reference_keeps_the_internal_catalog(self):
        # Synthetic fixture: catalog relocation applies to any internal resource.
        template = "---\nname: catalog-reader\ndescription: Inspect routines.\n---\n\nRead `{{PLUGIN_ROOT}}/skills/INDEX.md`.\n"
        _write(self.repo, "core/surface/skills/catalog-reader/SKILL.md", template)
        _write(self.repo, "core/surface/skills/INDEX.md", "# routine catalog\n")
        pi_text = self.render("pi")["routines/catalog-reader/SKILL.md"].decode()
        codex_text = self.render("codex")["routines/catalog-reader/SKILL.md"].decode()
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


class VerificationBoundaryContractTest(unittest.TestCase):
    """The contributor loop stays bounded while hosted CI owns exhaustive proof."""

    def read(self, relative_path):
        return (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    def test_canonical_policy_assigns_exhaustive_proof_to_exact_head_ci(self):
        policy = self.read("core/surface/includes/verification-boundary.md")
        for required in (
            "impact-bounded local verification",
            "exact-head",
            "hosted CI",
            "missing, stale, cancelled, or mismatched",
            "MUST NOT merge",
            "coverage",
            "generated-artifact parity",
            "staged secret scanning",
            "lint",
            "type-check",
            "security",
            "dependency",
            "migration",
            "release",
            "ADR",
            "deployment",
            "live device",
            "private",
            "environment",
        ):
            self.assertIn(required.lower(), policy.lower())

    def test_local_lanes_defer_exhaustive_suites_to_hosted_ci(self):
        paths = (
            "core/surface/skills/commit-gate/SKILL.md",
            "core/surface/skills/tdd/SKILL.md",
            "core/surface/skills/refactor/SKILL.md",
            "core/surface/includes/author-tdd-workflow.md",
            "core/surface/commands/feature.md",
            "core/surface/commands/commit.md",
            "core/surface/commands/chore.md",
            "core/surface/commands/refactor.md",
            "core/surface/agents/backend-author.md",
            "core/surface/agents/frontend-author.md",
            "core/surface/skills/writing-plans/references/farm-plan.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".codearbiter/tech-stack.md",
            "CONTRIBUTING.md",
        )
        obsolete = (
            "Run all of these; ALL must pass before any commit",
            "Run the full suite. A broken pre-existing",
            "Run full suite — every test green",
            "full suite must be green before",
            "MUST NOT commit if the project test suite is not green",
            "Run it before opening a PR",
        )
        for path in paths:
            text = self.read(path)
            if path.startswith("core/surface/commands/"):
                text = B._compose_skill_entry(
                    text, path, str(REPO_ROOT / "core/surface"), {}
                )
            with self.subTest(path=path):
                for phrase in obsolete:
                    self.assertNotIn(phrase, text)
                self.assertIn("verification-boundary", text)

        plan_schema = self.read("plugins/ca/tools/plan.schema.json")
        self.assertNotIn("Typically: run this test, run full suite", plan_schema)
        self.assertIn("exhaustive exact-head proof runs in hosted CI", plan_schema)

    def test_tracked_curated_docs_do_not_restore_the_obsolete_local_rule(self):
        paths = (
            "site/src/curated/commands/chore.md",
            "site/src/curated/commands/commit.md",
            "site/src/curated/commands/feature.md",
            "site/src/curated/commands/refactor.md",
            "site/src/curated/skills/commit-gate.md",
            "site/src/curated/skills/refactor.md",
            "site/src/curated/skills/tdd.md",
        )
        obsolete = (
            "full suite must pass",
            "Run the full suite",
            "Running full suite",
            "before opening a PR",
        )
        for path in paths:
            text = self.read(path)
            with self.subTest(path=path):
                for phrase in obsolete:
                    self.assertNotIn(phrase, text)
                self.assertIn("impact-bounded", text)
                self.assertIn("exact-head", text)
                self.assertIn("hosted CI", text)

        refactor = self.read("site/src/curated/commands/refactor.md")
        self.assertIn("no pre-existing parity test files modified", refactor)
        self.assertNotIn("zero test files touched", refactor)

    def test_every_host_projection_carries_the_same_boundary(self):
        rendered = {
            "claude": B.render_all(REPO_ROOT, "claude"),
            "codex": B.render_all(REPO_ROOT, "codex"),
            "pi": B.render_all(REPO_ROOT, "pi"),
        }
        for host, surface in rendered.items():
            with self.subTest(host=host):
                policy = surface["includes/verification-boundary.md"].decode()
                routine_prefix = "skills" if host == "claude" else "routines"
                self.assertIn("impact-bounded local verification", policy)
                self.assertIn("hosted CI", policy)
                self.assertIn("exact-head", policy)
                self.assertIn("verification-boundary", surface[
                    f"{routine_prefix}/commit-gate/SKILL.md"
                ].decode())
                self.assertIn("verification-boundary", surface[
                    f"{routine_prefix}/tdd/SKILL.md"
                ].decode())
                finishing = surface[
                    f"{routine_prefix}/finishing-a-development-branch/SKILL.md"
                ].decode()
                self.assertIn("verification-boundary", finishing)
                self.assertIn("merge-readiness aggregate", finishing)
                self.assertIn("current exact-head", finishing)



class SkillEntryCompositionTest(_RepoCase):
    """A build-time declaration exposes one full owner without another runtime hop."""

    def setUp(self):
        super().setUp()
        self.owner = (
            '---\nname: commit-gate\ndescription: Create the authorized commit.\n'
            'argument-hint: (none)\n---\n\n'
            '# commit-gate\n\n## Pre-flight\n\n'
            'Read `{{PLUGIN_ROOT}}/skills/tdd/SKILL.md`.\n'
            '## Phase 1 — Permission · gate: BLOCK\n\n'
            'An explicit instruction is required. Gate: actual permission.\n\n'
            '## Hard rules\n\nNever imply a PR or push.\n'
        )
        _write(self.repo, 'core/surface/skills/commit-gate/SKILL.md', self.owner)
        _write(self.repo, 'core/surface/commands/init.md', '{{SKILL_ENTRY:commit-gate}}\n')

    def test_complete_owner_exposed_with_one_discoverable_description(self):
        """Public invocation receives every phase, not the wrapper plus a reload."""
        for host, entry, private in (
            ('claude', 'commands/init.md', 'skills/commit-gate/SKILL.md'),
            ('codex', 'skills/ca-init/SKILL.md', 'routines/commit-gate/SKILL.md'),
            ('pi', 'skills/ca-init/SKILL.md', 'routines/commit-gate/SKILL.md'),
        ):
            with self.subTest(host=host):
                out = self.render(host)
                public = out[entry].decode()
                resource = out[private].decode()
                self.assertIn('## Phase 1 — Permission', public)
                self.assertIn('Never imply a PR or push.', public)
                self.assertNotIn('SKILL_ENTRY', public)
                self.assertEqual('disable-model-invocation: true' in _frontmatter(public),
                                 host == 'claude')
                self.assertNotIn('name: commit-gate', _frontmatter(public))
                self.assertNotIn('disable-model-invocation', _frontmatter(resource))
                self.assertIn('argument-hint: (none)', _frontmatter(public))
                catalog = json.loads(out['generated/command-catalog.json'])
                self.assertEqual(catalog['commands']['init']['description'],
                                 'Create the authorized commit.')
                self.assertNotIn('commit-gate', catalog['commands'])
                if host != 'claude':
                    self.assertEqual(_frontmatter(public).count('name:'), 1)
                    self.assertIn('name: ca-init', _frontmatter(public))
                else:
                    self.assertNotIn('name:', _frontmatter(public))

    def test_json_quoted_owner_scalars_remain_strings_in_host_frontmatter(self):
        """Explicit quoted scalar intent survives comments, YAML types and sigils."""
        cases = ('Fixes issue #612 now', 'true', "'x'", '*alias', '&anchor',
                 '!tag', '- item', '@scope', '%directive', '`literal`',
                 '001', 'null', ' leading and trailing ')
        for value in cases:
            owner = self.owner.replace('description: Create the authorized commit.',
                                       'description: ' + json.dumps(value))
            owner = owner.replace('argument-hint: (none)',
                                  'argument-hint: ' + json.dumps(value))
            _write(self.repo, 'core/surface/skills/commit-gate/SKILL.md', owner)
            for host, entry in (('claude', 'commands/init.md'),
                                ('codex', 'skills/ca-init/SKILL.md'),
                                ('pi', 'skills/ca-init/SKILL.md')):
                with self.subTest(value=value, host=host):
                    out = self.render(host)
                    front = _frontmatter(out[entry].decode())
                    for key in ('description', 'argument-hint'):
                        emitted = next(line.split(': ', 1)[1] for line in front.splitlines()
                                       if line.startswith(key + ': '))
                        self.assertTrue(emitted.startswith('"'), (key, emitted))
                        self.assertEqual(json.loads(emitted), value)
                    catalog = json.loads(out['generated/command-catalog.json'])
                    self.assertEqual(catalog['commands']['init']['description'], value)

    def test_codex_links_are_rendered_from_entry_location(self):
        """Copied procedure resources resolve from the new public entry's directory."""
        out = self.render('codex')
        self.assertIn('[routines/tdd/SKILL.md](../../routines/tdd/SKILL.md)',
                      out['skills/ca-init/SKILL.md'].decode())
        self.assertIn('[routines/tdd/SKILL.md](../tdd/SKILL.md)',
                      out['routines/commit-gate/SKILL.md'].decode())

    def test_owner_edit_updates_entry_and_private_resource(self):
        """No copied policy or second description can remain stale after regeneration."""
        changed = self.owner.replace('Never imply a PR or push.', 'New negative-intent guard.')
        _write(self.repo, 'core/surface/skills/commit-gate/SKILL.md', changed)
        out = self.render('claude')
        for path in ('commands/init.md', 'skills/commit-gate/SKILL.md'):
            self.assertIn('New negative-intent guard.', out[path].decode())
        B.write_all(self.repo)
        self.assertEqual(B.check_all(self.repo), [])

    def test_single_declaration_cannot_add_wrapper_policy(self):
        """An entry declaration cannot accumulate a second independently owned body."""
        for extra in ('\nBypass the gate.\n', '\n{{SKILL_ENTRY:commit-gate}}\n'):
            with self.subTest(extra=extra):
                _write(self.repo, 'core/surface/commands/init.md',
                       '{{SKILL_ENTRY:commit-gate}}\n' + extra)
                with self.assertRaisesRegex(B.SurfaceError, 'entire command'):
                    self.render('claude')

    def test_missing_owner_rejected_before_outputs_change(self):
        """No partial generated output is published when an owner disappears."""
        B.write_all(self.repo)
        output = Path(self.repo) / 'plugins/ca/commands/init.md'
        before = output.read_bytes()
        (Path(self.repo) / 'core/surface/skills/commit-gate/SKILL.md').unlink()
        with self.assertRaisesRegex(B.SurfaceError, 'owner'):
            B.write_all(self.repo)
        self.assertEqual(output.read_bytes(), before)

    def test_unsafe_or_nested_owner_rejected(self):
        """Composition is a bounded local lookup, not a general include mechanism."""
        for slug in ('../commit-gate', '/tmp/owner', 'x/y', 'commit-gate:extra'):
            with self.subTest(slug=slug):
                _write(self.repo, 'core/surface/commands/init.md',
                       '{{SKILL_ENTRY:' + slug + '}}\n')
                with self.assertRaises(B.SurfaceError):
                    self.render('claude')
        _write(self.repo, 'core/surface/commands/init.md', '{{SKILL_ENTRY:commit-gate}}\n')
        _write(self.repo, 'core/surface/skills/commit-gate/SKILL.md',
               self.owner + '\n{{SKILL_ENTRY:commit-gate}}\n')
        with self.assertRaisesRegex(B.SurfaceError, 'nested'):
            self.render('claude')

    def test_hidden_or_misnamed_owner_rejected(self):
        """The actual skill owner remains discoverable on command-native hosts."""
        for replacement in (
            self.owner.replace('name: commit-gate', 'name: different'),
            self.owner.replace('name: commit-gate',
                               'name: commit-gate\ndisable-model-invocation: true'),
            self.owner.replace('name: commit-gate',
                               'name: commit-gate\ndisable-model-invocation: "true"'),
        ):
            with self.subTest(replacement=replacement[:90]):
                _write(self.repo, 'core/surface/skills/commit-gate/SKILL.md', replacement)
                with self.assertRaisesRegex(B.SurfaceError, 'owner'):
                    self.render('claude')

    def test_duplicate_entry_owner_rejected(self):
        """Two public registrations cannot accidentally advertise the same owner."""
        _write(self.repo, 'core/surface/commands/status.md', '{{SKILL_ENTRY:commit-gate}}\n')
        with self.assertRaisesRegex(B.SurfaceError, 'already'):
            self.render('claude')

    def test_privilege_frontmatter_not_silently_discarded(self):
        """Unsupported metadata cannot lose or expand an owner's execution policy."""
        for field in ('allowed-tools: Bash', 'context: fork', 'model: expensive',
                      'description: Duplicate', 'argument-hint: |', 'extra: value'):
            with self.subTest(field=field):
                _write(self.repo, 'core/surface/skills/commit-gate/SKILL.md',
                       self.owner.replace('\n---\n\n#', '\n' + field + '\n---\n\n#'))
                with self.assertRaises(B.SurfaceError):
                    self.render('claude')

    def test_relative_support_link_requires_rooted_owner_reference(self):
        """Changing entry location must not silently strand supporting files."""
        _write(self.repo, 'core/surface/skills/commit-gate/SKILL.md',
               self.owner + '\nRead [support](references/support.md).\n')
        with self.assertRaisesRegex(B.SurfaceError, 'root'):
            self.render('claude')

    @unittest.skipIf(os.name == 'nt', 'Symlink creation may require Windows privilege')
    def test_symlink_owner_cannot_escape_source_tree(self):
        """A source declaration cannot read a hidden external procedure through a link."""
        owner = Path(self.repo) / 'core/surface/skills/commit-gate/SKILL.md'
        outside = Path(self._td.name).parent / (Path(self._td.name).name + '-outside.md')
        outside.write_text(self.owner)
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        owner.unlink()
        owner.symlink_to(outside)
        with self.assertRaisesRegex(B.SurfaceError, 'owner'):
            self.render('claude')



class ActualConsolidatedOwnersTest(unittest.TestCase):
    """Pin adopted owners, host boundaries and gate-preserving composition."""

    def test_selected_wrappers_have_no_separately_authored_policy(self):
        """Only the skill owns its description, arguments and execution procedure."""
        for command, owner in (('commit', 'commit-gate'), ('debug', 'debug'), ('refactor', 'refactor')):
            with self.subTest(command=command):
                declaration = (REPO_ROOT / f'core/surface/commands/{command}.md').read_text()
                self.assertEqual(declaration, '{{SKILL_ENTRY:' + owner + '}}\n')
                skill = (REPO_ROOT / f'core/surface/skills/{owner}/SKILL.md').read_text()
                self.assertNotIn('disable-model-invocation', _frontmatter(skill))
                self.assertIn('argument-hint:', _frontmatter(skill))

    def test_claude_explicit_entries_preserve_complete_owner_bodies(self):
        """ADR-0028 owners stay discoverable; explicit spellings remain available."""
        out = B.render_all(REPO_ROOT, 'claude')
        for command, owner in (('commit', 'commit-gate'), ('debug', 'debug'), ('refactor', 'refactor')):
            with self.subTest(command=command):
                entry = out[f'commands/{command}.md'].decode()
                skill = out[f'skills/{owner}/SKILL.md'].decode()
                self.assertEqual(entry.split('\n---\n', 1)[1],
                                 skill.split('\n---\n', 1)[1])
                self.assertIn('disable-model-invocation: true', _frontmatter(entry))
                self.assertNotIn('user-invocable:', entry)
                self.assertNotIn('disable-model-invocation:', _frontmatter(skill))
                self.assertNotIn('allowed-tools:', _frontmatter(entry))
                self.assertNotIn('model:', _frontmatter(entry))

    def test_codex_pi_entry_names_and_discovery_remain_compatible(self):
        """Routine owners are private resources, so synthesized entries stay visible."""
        for host in ('codex', 'pi'):
            out = B.render_all(REPO_ROOT, host)
            for command, owner in (('commit', 'commit-gate'), ('debug', 'debug'), ('refactor', 'refactor')):
                with self.subTest(host=host, command=command):
                    entry = out[f'skills/ca-{command}/SKILL.md'].decode()
                    self.assertIn(f'name: ca-{command}', _frontmatter(entry))
                    self.assertNotIn('disable-model-invocation', _frontmatter(entry))
                    self.assertIn(f'routines/{owner}/SKILL.md', out)
                    self.assertNotIn(f'skills/{owner}/SKILL.md', out)
                    self.assertIn('## Pre-flight', entry)
                    self.assertIn('## Hard rules', entry)

    def test_commit_gate_authority_and_acceptance_are_not_entry_metadata(self):
        """Every full entry still carries the actual mutation and typed-proof gates."""
        for host, path in (('claude', 'commands/commit.md'),
                           ('codex', 'skills/ca-commit/SKILL.md'),
                           ('pi', 'skills/ca-commit/SKILL.md')):
            with self.subTest(host=host):
                entry = B.render_all(REPO_ROOT, host)[path].decode()
                for obligation in ('Confirm the user explicitly authorized this commit.',
                                   '_preflight_current_acceptance',
                                   'all_accepted_and_current: true',
                                   'verification-boundary', '## Phase 7', '## Phase 9',
                                   'postponing a commit', 'never implies a push or PR'):
                    self.assertIn(obligation, entry)

    def test_no_discovery_or_startup_registration_was_added(self):
        """Catalog visibility and compatibility inventory are unchanged on each host."""
        registry = json.loads((REPO_ROOT / 'core/surface/command-routes.json').read_text())
        descriptors = B.load_host_descriptors(REPO_ROOT)
        for descriptor in descriptors:
            out = B.render_all(REPO_ROOT, descriptor.name)
            catalog = json.loads(out['generated/command-catalog.json'])['commands']
            expected = {name for name in registry['commands']
                        if B._output_rel(f'commands/{name}.md', descriptor)[0] is not None}
            self.assertEqual(set(catalog), expected)
            for name, record in catalog.items():
                for key in ('visibility', 'workflow', 'canonical', 'replacement', 'legacyRoutes'):
                    self.assertEqual(record.get(key), registry['commands'][name].get(key))
            self.assertNotIn('SKILL_ENTRY', out['arbiter.md'].decode())


    def test_debug_entry_preserves_investigation_and_board_writer(self):
        """The complete entry diagnoses without editing code or inventing evidence."""
        for host, target in (('claude', 'commands/debug.md'), ('codex', 'skills/ca-debug/SKILL.md'), ('pi', 'skills/ca-debug/SKILL.md')):
            with self.subTest(host=host):
                entry = B.render_all(REPO_ROOT, host)[target].decode()
                for obligation in ('## Phase 5', 'regression test obligation', 'through the board helper, never by appending', 'taskwrite.py', '[NEEDS-TRIAGE]', 'user attribution', 'three distinct hypotheses', 'MUST NOT modify, refactor'):
                    self.assertIn(obligation, entry)
                self.assertNotIn('symptom and rationale appended to', entry)

    def test_refactor_entry_preserves_scope_and_parity_gates(self):
        """Single ownership does not weaken approval, parity or verification."""
        for host, target in (('claude', 'commands/refactor.md'), ('codex', 'skills/ca-refactor/SKILL.md'), ('pi', 'skills/ca-refactor/SKILL.md')):
            with self.subTest(host=host):
                entry = B.render_all(REPO_ROOT, host)[target].decode()
                for obligation in ('## Phase 6', 'user-signed-off surface table', 'unmodified pre-existing tests', 'BOTH lines and branches', 'No new seams', 'verification-boundary.md', 'MUST NOT inline-suppress', 'explicit user-approved amendment'):
                    self.assertIn(obligation, entry)

    def test_new_owner_metadata_routes_intent_not_required_syntax(self):
        """Descriptions identify the task rather than demanding a command wrapper."""
        for owner in ('debug', 'refactor'):
            with self.subTest(owner=owner):
                skill = (REPO_ROOT / f'core/surface/skills/{owner}/SKILL.md').read_text()
                self.assertIn('argument-hint:', _frontmatter(skill))
                self.assertIn('## Entry boundaries', skill)
                self.assertIn('explanation-only', skill)
                self.assertNotIn('Routed to by /refactor', _frontmatter(skill))
                self.assertNotIn('only permitted entry', skill)

    def test_entry_boundary_distinctions_survive_direct_owner_routing(self):
        """Cycle prevention and non-mutating intents live with their procedure."""
        debug = (REPO_ROOT / 'core/surface/skills/debug/SKILL.md').read_text()
        refactor = (REPO_ROOT / 'core/surface/skills/refactor/SKILL.md').read_text()
        routing = (REPO_ROOT / 'core/surface/includes/routing-table.md').read_text()
        for owner in ('debug', 'refactor', 'commit-gate'):
            self.assertIn('{{PLUGIN_ROOT}}/skills/' + owner + '/SKILL.md', routing)
        self.assertIn('Do not re-enter from an active', debug)
        self.assertIn('known bug with a named regression test', debug)
        self.assertIn('already-completed refactor', refactor)
        self.assertIn('{{PLUGIN_ROOT}}/skills/commit-gate/SKILL.md', refactor)
        self.assertIn('No commit, push, or PR is implied', refactor)




class RemovedSkillAuthorTest(unittest.TestCase):
    """The explicitly retired workflow must not survive as an alias or hidden skill."""

    def test_canonical_command_owner_and_template_are_absent(self):
        self.assertFalse((REPO_ROOT / 'core/surface/commands/new-skill.md').exists())
        self.assertFalse((REPO_ROOT / 'core/surface/skills/skill-author').exists())

    def test_every_host_omits_the_retired_entry_and_owner(self):
        for host in ('claude', 'codex', 'pi'):
            with self.subTest(host=host):
                out = B.render_all(REPO_ROOT, host)
                self.assertNotIn('commands/new-skill.md', out)
                self.assertNotIn('skills/ca-new-skill/SKILL.md', out)
                self.assertFalse(any('/skill-author/' in p for p in out))
                catalog = json.loads(out['generated/command-catalog.json'])['commands']
                self.assertNotIn('new-skill', catalog)
                self.assertIn('commit', catalog)
                self.assertIn('debug', catalog)
                self.assertIn('refactor', catalog)

    def test_no_active_route_or_replacement_extension_entry(self):
        registry = json.loads((REPO_ROOT / 'core/surface/command-routes.json').read_text())
        self.assertNotIn('new-skill', registry['commands'])
        self.assertNotIn('extend', registry['commands'])
        for name in ('COMMANDS.md', 'skills/INDEX.md', 'includes/routing-table.md'):
            text = (REPO_ROOT / 'core/surface' / name).read_text(encoding='utf-8')
            self.assertNotIn('new-skill', text, name)
            self.assertNotIn('skill-author', text, name)
        for category, name in (('commands', 'new-skill'), ('skills', 'skill-author')):
            self.assertFalse((REPO_ROOT / f'site/src/curated/{category}/{name}.md').exists())

    def test_reusable_format_guidance_is_not_a_registered_workflow(self):
        text = (REPO_ROOT / 'core/surface/README.md').read_text(encoding='utf-8')
        self.assertIn('## Authoring governed resources', text)
        self.assertIn('JSON-quoted', text)
        self.assertIn('directly referenced information card', text)
        self.assertIn('check_routing_index_parity.py', text)
        self.assertNotIn('commands/new-skill.md', text)
        self.assertNotIn('Return with evidence', text)


class FirstSliceDiscoveryOwnersTest(unittest.TestCase):
    """D08-D11 and D15 reduce metadata without dropping mode-specific contracts."""

    OWNERS = {'tribunal': 'tribunal', 'threat-model': 'security-architecture', 'context-check': 'context-check', 'cleanup': 'post-merge-cleanup', 'pr': 'finishing-a-development-branch'}

    @classmethod
    def setUpClass(cls):
        cls.outputs = {host: B.render_all(REPO_ROOT, host)
                       for host in ('claude', 'codex', 'pi')}

    def entry(self, host, command):
        path = f'commands/{command}.md' if host == 'claude' else f'skills/ca-{command}/SKILL.md'
        return self.outputs[host][path].decode()

    def test_five_commands_use_one_owner_each_and_concise_intent(self):
        for command, owner in self.OWNERS.items():
            with self.subTest(command=command):
                path = REPO_ROOT / f'core/surface/commands/{command}.md'
                self.assertEqual(path.read_text(encoding='utf-8'), '{{SKILL_ENTRY:' + owner + '}}\n')
                skill = (REPO_ROOT / f'core/surface/skills/{owner}/SKILL.md').read_text(encoding='utf-8')
                description = B._frontmatter_value(skill, 'description', str(path))
                self.assertLessEqual(len(description), 160)
                self.assertNotRegex(description, r'(?i)routed to when|phase [0-9]|only via|_provenancelib')
                self.assertIn('argument-hint:', _frontmatter(skill))
                self.assertIn('explanation-only', skill.lower())

    def test_host_metadata_and_explicit_names_are_preserved(self):
        for command, owner in self.OWNERS.items():
            for host, output in self.outputs.items():
                with self.subTest(host=host, command=command):
                    entry = self.entry(host, command)
                    prefix = 'skills' if host == 'claude' else 'routines'
                    skill = output[f'{prefix}/{owner}/SKILL.md'].decode()
                    self.assertNotIn('disable-model-invocation:', _frontmatter(skill))
                    self.assertNotIn('allowed-tools:', _frontmatter(entry))
                    self.assertNotIn('user-invocable:', _frontmatter(entry))
                    if host == 'claude':
                        self.assertIn('disable-model-invocation: true', _frontmatter(entry))
                        self.assertEqual(entry.split('\n---\n', 1)[1], skill.split('\n---\n', 1)[1])
                    else:
                        self.assertIn(f'name: ca-{command}', _frontmatter(entry))
                        self.assertNotIn('disable-model-invocation:', _frontmatter(entry))
                        self.assertNotIn(f'skills/{owner}/SKILL.md', output)

    def test_description_budget_falls_on_entry_skill_hosts(self):
        # Description characters, not runtime listing count or model prompt tokens.
        for host in ('codex', 'pi'):
            values = [B._frontmatter_value(self.entry(host, c), 'description', c) for c in self.OWNERS]
            self.assertLess(sum(map(len, values)), 927)
            self.assertTrue(all(0 < len(value) <= 160 for value in values))

    def test_tribunal_keeps_applicability_consent_and_rooted_support(self):
        for host in self.outputs:
            text = self.entry(host, 'tribunal')
            for obligation in ('applicability across the full roster', 'launched/skipped',
                               'acknowledging the estimated token cost', 'explicit per-run authorization',
                               'never `open-tasks.md`', 'run-aborted', 'counter_argument',
                               'Usage recovery is best-effort' if host == 'claude' else '## Phase 6'):
                self.assertIn(obligation, text)
            self.assertNotIn('`references/', text)
            self.assertNotIn('The full lens roster still runs', text)
            self.assertIn('MUST NOT edit, refactor, format, or commit project code', text)
            self.assertIn('MUST NOT act as a required gate', text)

    def test_threat_model_retains_readonly_and_nonbinary_verdict(self):
        for host in self.outputs:
            text = self.entry(host, 'threat-model')
            for value in ('PROCEED-WITH-CONSTRAINTS', 'critical unmitigated threat',
                          'Read-only: modify no project file', 'reviewers inherit this read-only',
                          'relevant security ADRs', 'prerequisite failure, separate',
                          'MUST NOT author an ADR', 'MUST NOT force this pass'):
                self.assertIn(value, text)
            self.assertNotIn('CLEAR TO IMPLEMENT', text)
            self.assertNotIn('BLOCKED — resolve findings first', text)
            self.assertNotIn('Routed to only when the user deliberately invokes', text)

    def test_drift_and_cleanup_operational_bodies_are_preserved(self):
        import hashlib
        expected = {'context-check': '0e71c154f4d22f3f109edd4e3e95040e533ecd57d1c4687e3a7a47c6966f7198', 'cleanup': 'bbeed4efed778bb4f6d85149d70772ede5177dc0ca9d09a4edd072bdda69645d'}
        for command, digest in expected.items():
            owner = self.OWNERS[command]
            text = (REPO_ROOT / f'core/surface/skills/{owner}/SKILL.md').read_text(encoding='utf-8')
            body = text.split('## Pre-flight\n', 1)[1]
            self.assertEqual(hashlib.sha256(body.encode()).hexdigest(), digest)
            self.assertIn('neither stages nor commits', ' '.join(text.split()))
        drift = (REPO_ROOT / 'core/surface/commands/status.md').read_text(encoding='utf-8')
        self.assertIn('{{PLUGIN_ROOT}}/skills/context-check/SKILL.md', drift)
        self.assertNotIn('{{PLUGIN_ROOT}}/commands/context-check.md', drift)

    def test_pr_dispatches_noncreation_modes_before_preflight(self):
        for host in self.outputs:
            text = self.entry(host, 'pr')
            self.assertIn('## Pre-flight', text, 'Composed PR entry must carry creation preflight')
            before, after = text.split('## Pre-flight', 1)
            self.assertIn('command-mode:--watch legacy-route:watch', before)
            self.assertIn('command-mode:--cleanup legacy-route:cleanup', before)
            self.assertIn('then returns', before)
            self.assertIn('before reaching that requirement', before)
            self.assertIn('flags are mutually exclusive', before)
            self.assertIn('extra cleanup argument', before)
            self.assertIn('is a title, not a mode', before)
            self.assertNotIn('command-mode:', after)
            self.assertIn('post-merge-cleanup/SKILL.md', before)
            self.assertNotIn('commands/cleanup.md', text)
            self.assertNotIn('skills/ca-cleanup/SKILL.md', text)

    def test_pr_procedure_has_no_wrapper_cycle_and_preserves_review_and_watch(self):
        for host in self.outputs:
            text = self.entry(host, 'pr')
            self.assertEqual(text.count('### Open-PR procedure'), 1)
            self.assertNotIn('commands/pr.md', text)
            self.assertNotIn('skills/ca-pr/SKILL.md', text)
            for obligation in ('auth-crypto-reviewer', 'security-reviewer', 'migration-reviewer',
                               'dependency-reviewer', 'coverage-auditor', 'CRITICAL or HIGH',
                               'anti-slop-design', 'babysit.py', 'CODEARBITER_BABYSIT',
                               'Never enable the flag', '_preflight_current_acceptance',
                               '--match-head-commit', 'all_accepted_and_current: true'):
                self.assertIn(obligation, text)

    def test_pr_respects_direct_choice_and_caller_authority(self):
        for host in self.outputs:
            text = self.entry(host, 'pr')
            self.assertIn('Do not repeat a branch-fate menu', text)
            self.assertIn('feature-terminal handoff keeps its existing terminal', text)
            self.assertIn('sprint-terminal handoff selects open PR only', text)
            self.assertIn('MUST NOT auto-merge under', text)
            self.assertIn('MUST NOT discard a branch without explicit user confirmation', text)
            self.assertIn('MUST NOT delete un-pushed commits silently', text)
            self.assertIn('current exact head', text)

    def test_pr_current_acceptance_and_ancestry_preflight_is_identical(self):
        import hashlib
        text = (REPO_ROOT / 'core/surface/skills/finishing-a-development-branch/SKILL.md').read_text(encoding='utf-8')
        section = text[text.index('## Pre-flight\n'):text.index('## Phase 2')]
        self.assertEqual(hashlib.sha256(section.encode()).hexdigest(), '0df4e08d97542d6273ae5c7d7cf149daec423d7c7587f5123f4bafadb8dc146a')
        inventory = json.loads((REPO_ROOT / 'docs/artifacts/consumer-inventory.json').read_text(encoding='utf-8'))
        consumer = next(row for row in inventory['consumers']
                        if row['id'] == 'finalization-and-worktree-plan-readers')
        for path in ('plugins/ca/commands/pr.md', 'plugins/ca-codex/skills/ca-pr/SKILL.md',
                     'plugins/ca-pi/skills/ca-pr/SKILL.md', 'site/src/content/docs/reference/commands/pr.md'):
            self.assertIn(path, consumer['generated_paths'])
        self.assertFalse(inventory['rollout']['typed_html_farm_enabled'])


    def test_direct_routing_points_to_all_five_owners(self):
        table = (REPO_ROOT / 'core/surface/includes/routing-table.md').read_text(encoding='utf-8')
        for owner in self.OWNERS.values():
            self.assertIn('{{PLUGIN_ROOT}}/skills/' + owner + '/SKILL.md', table)



class ComposedModeClosureTest(_RepoCase):
    """Mode closure must validate the resolved owner, not the empty declaration."""

    def setUp(self):
        super().setUp()
        registry = json.loads((Path(self.repo) / 'core/surface/command-routes.json').read_text())
        registry['commands']['init'].update(modes=['--inspect'], legacyRoutes=['status'])
        registry['commands']['status'].update(visibility='alias', canonical='init', replacement='init --inspect')
        registry['commands']['status'].pop('legacyRoutes')
        _write_registry(self.repo, registry['commands'])
        self.owner = ('---\nname: mode-owner\ndescription: Inspect or initialize.\n'
                      'argument-hint: "(none) | --inspect"\n---\n\n'
                      '# mode owner\n\n<!-- command-mode:--inspect legacy-route:status -->\n'
                      'Inspect is read-only. Initialization requires separate intent.\n')
        _write(self.repo, 'core/surface/skills/mode-owner/SKILL.md', self.owner)
        _write(self.repo, 'core/surface/commands/init.md', '{{SKILL_ENTRY:mode-owner}}\n')

    def test_valid_composed_mode_is_rendered_and_catalogued_on_all_hosts(self):
        for host, path in [('claude', 'commands/init.md'), ('codex', 'skills/ca-init/SKILL.md'),
                           ('pi', 'skills/ca-init/SKILL.md')]:
            with self.subTest(host=host):
                try:
                    out = B.render_all(self.repo, host)
                except B.SurfaceError as error:
                    self.fail(f'Valid composed mode was rejected: {error}')
                self.assertIn('command-mode:--inspect legacy-route:status', out[path].decode())
                metadata = json.loads(out['generated/command-catalog.json'])['commands']['init']
                alias = json.loads(out['generated/command-catalog.json'])['commands']['status']
                self.assertEqual(alias['replacement'], 'init --inspect')
                self.assertEqual(metadata['legacyRoutes'], ['status'])

    def test_composed_modes_still_reject_missing_duplicate_and_wrong_markers(self):
        marker = '<!-- command-mode:--inspect legacy-route:status -->'
        variants = [self.owner.replace(marker, ''), self.owner + marker + '\n',
                    self.owner.replace('--inspect legacy-route:status', '--delete legacy-route:status')]
        for owner in variants:
            _write(self.repo, 'core/surface/skills/mode-owner/SKILL.md', owner)
            for host in ('claude', 'codex', 'pi'):
                with self.subTest(host=host, owner=owner):
                    with self.assertRaisesRegex(B.SurfaceError, 'command-mode marker closure'):
                        B.render_all(self.repo, host)

    def test_mode_composition_does_not_allow_two_entries_for_one_owner(self):
        _write(self.repo, 'core/surface/commands/status.md', '{{SKILL_ENTRY:mode-owner}}\n')
        for host in ('claude', 'codex', 'pi'):
            with self.subTest(host=host):
                with self.assertRaisesRegex(B.SurfaceError, 'already exposed'):
                    B.render_all(self.repo, host)




class AdrModeOwnershipTest(unittest.TestCase):
    """D12/D13 reduce discovery without mixing read-only and authoring authority."""

    owner_path = 'core/surface/skills/decision-lifecycle/SKILL.md'
    author_path = 'core/surface/skills/decision-lifecycle/references/authoring.md'

    def text(self, path):
        """Missing resources are assertion failures, not collection/runtime errors."""
        file = REPO_ROOT / path
        self.assertTrue(file.is_file(), f'missing owner resource: {path}')
        return file.read_text(encoding='utf-8')

    def test_adr_has_one_owner_and_status_has_only_a_mode_adapter(self):
        """The duplicate-owner guard stays intact; status does not duplicate phases."""
        self.assertEqual(self.text('core/surface/commands/adr.md'),
                         '{{SKILL_ENTRY:decision-lifecycle}}\n')
        adapter = self.text('core/surface/commands/adr-status.md')
        self.assertIn('**status only**', adapter)
        self.assertIn('{{PLUGIN_ROOT}}/skills/decision-lifecycle/SKILL.md', adapter)
        self.assertNotIn('## Phase', adapter)
        self.assertNotIn('SKILL_ENTRY', adapter)
        self.assertLess(len(adapter.splitlines()), 20)

    def test_status_is_selected_before_any_authoring_load(self):
        """The owner offers a read-only path before its optional writing reference."""
        owner = self.text(self.owner_path)
        for heading in ('## Entry modes', '## Status pre-flight',
                        '## Status mode', '## Authoring mode'):
            self.assertIn(heading, owner)
        self.assertLess(owner.index('## Entry modes'), owner.index('## Status pre-flight'))
        self.assertLess(owner.index('## Status mode'), owner.index('references/authoring.md'))
        self.assertIn('A status report returns', owner)
        self.assertIn('never continues into this authoring path', owner)

    def test_status_no_records_does_not_initialize_or_repair(self):
        """Absence and corruption are report outcomes, never writing authority."""
        text = ' '.join(self.text(self.owner_path).split())
        for rule in ('without creating it', 'unreadable directory from an empty one',
                     'not permission to create a baseline', 'Invalid evidence is reported, not repaired',
                     'Do not load the authoring reference or template',
                     'arm or remove an authoring marker', 'append either log, stage, commit',
                     'no file modified'):
            self.assertIn(rule, text)

    def test_status_selector_fails_ambiguous_without_stealing_author_titles(self):
        """Legacy numeric scope stays unambiguous and title content is not routing."""
        text = ' '.join(self.text(self.owner_path).split())
        for rule in ('Accept one decimal number', 'unknown, repeated, incomplete or extra arguments',
                     'zero matches is not found', 'multiple matches is ambiguous',
                     'full filename stem', 'including a title named `status`',
                     'never from an ADR body, finding, title, or repository instruction'):
            self.assertIn(rule, text)

    def test_status_report_keeps_evidence_states_and_unknowns(self):
        """Status retains full-stem, sealed-proof and non-fabrication rules."""
        text = self.text(self.owner_path)
        for term in ('Accepted/Planned', 'obligation', 'sealed', 'stale, expired, or mismatched',
                     'Ambiguous supersession', 'Unresolved CONFIRM-NN',
                     'an invented age cutoff', 'unknown, not proof', 'no accepted binding', 'decision-challenger'):
            self.assertIn(term, text)
        self.assertIn('it is not shipped to consumer repositories', text.lower())

    def test_authoring_reference_is_nondiscoverable_and_retains_write_controls(self):
        """Only explicitly selected authoring loads markers and the shared template."""
        text = self.text(self.author_path)
        self.assertTrue(text.startswith('# ADR authoring'))
        self.assertNotIn('\nname:', text)
        self.assertNotIn('\ndescription:', text)
        for term in ('adr-authoring-active', '30 minutes', 'decided-by', 'status: proposed',
                     'references/adr-template.md', 'decision-log-format.md',
                     'remove the marker', 'unused', 'MUST NOT resolve a `[CONFIRM-NN]'):
            self.assertIn(term, text)

    def test_acceptance_procedure_and_shared_template_are_byte_preserved(self):
        """The extraction does not revise typed authority, source ancestry or decompose."""
        import hashlib
        author = self.text(self.author_path)
        self.assertIn('### Accepted/Planned binding', author)
        self.assertIn('## Hard rules', author)
        binding = author[author.index('### Accepted/Planned binding'):author.index('## Hard rules')]
        self.assertEqual(hashlib.sha256(binding.encode()).hexdigest(), '22f3395979eec539d938762659eb831f442c891a811e9a77b7a34ac8207fb0d8')
        template = self.text('core/surface/skills/decision-lifecycle/references/adr-template.md')
        self.assertEqual(hashlib.sha256(template.encode()).hexdigest(), '73135c60393f2c15b92370efeabaf2c376c36ea60bd2fba024dd1141f5d5cdf2')

    def test_all_hosts_retain_both_explicit_entries_and_one_owner(self):
        """Claude hides duplicate descriptions; entry-skill hosts retain both names."""
        for host in ('claude', 'codex', 'pi'):
            with self.subTest(host=host):
                out = B.render_all(REPO_ROOT, host)
                public = 'commands/{}.md' if host == 'claude' else 'skills/ca-{}/SKILL.md'
                for slug in ('adr', 'adr-status'):
                    header = _frontmatter(out[public.format(slug)].decode())
                    self.assertEqual('disable-model-invocation: true' in header, host == 'claude')
                    if host != 'claude': self.assertIn('name: ca-' + slug, header)
                owner = ('skills' if host == 'claude' else 'routines') + '/decision-lifecycle/SKILL.md'
                self.assertNotIn('disable-model-invocation', _frontmatter(out[owner].decode()))
                self.assertIn('argument-hint: "<decision title>"', out[public.format('adr')].decode())
                self.assertIn('argument-hint: "(none) | --adr N"', out[public.format('adr-status')].decode())

    def test_public_entries_never_inline_writing_procedure(self):
        """Read-only selection must not need to load authoring markers or acceptance."""
        for host in ('claude', 'codex', 'pi'):
            out = B.render_all(REPO_ROOT, host)
            prefix = 'skills' if host == 'claude' else 'routines'
            self.assertIn(prefix + '/decision-lifecycle/references/authoring.md', out)
            for slug in ('adr', 'adr-status'):
                path = f'commands/{slug}.md' if host == 'claude' else f'skills/ca-{slug}/SKILL.md'
                text = out[path].decode()
                self.assertNotIn('touch "', text)
                self.assertNotIn('### Accepted/Planned binding', text)
                self.assertNotIn('obligations_sealed: true', text)
                self.assertIn('decision-lifecycle', text)

    def test_metadata_is_shorter_and_public_inventory_is_unchanged(self):
        """Compare descriptions rather than asserting unmeasured token savings."""
        import re
        total = 0
        out = B.render_all(REPO_ROOT, 'codex')
        for slug in ('adr', 'adr-status'):
            text = _frontmatter(out[f'skills/ca-{slug}/SKILL.md'].decode())
            match = re.search(r'^description: (.+)$', text, re.M)
            self.assertIsNotNone(match)
            value = json.loads(match.group(1)) if match.group(1).startswith('"') else match.group(1)
            self.assertLessEqual(len(value), 160)
            total += len(value)
        self.assertLess(total, 232)
        registry = json.loads(self.text('core/surface/command-routes.json'))['commands']
        for host in ('claude', 'codex', 'pi'):
            catalog = json.loads(B.render_all(REPO_ROOT, host)['generated/command-catalog.json'])['commands']
            for slug in ('adr', 'adr-status'):
                self.assertEqual(catalog[slug]['canonical'], registry[slug]['canonical'])
                self.assertEqual(catalog[slug]['visibility'], registry[slug]['visibility'])

    def test_natural_language_routes_directly_without_new_ceremony(self):
        """A request selects the owner; attribution is still required to write."""
        table = self.text('core/surface/includes/routing-table.md')
        self.assertIn('{{PLUGIN_ROOT}}/skills/decision-lifecycle/SKILL.md', table)
        text = self.text(self.owner_path)
        self.assertIn('Natural-language intent', text)
        self.assertIn('explicit instruction and attribution', text)
        self.assertIn('general trust', text)
        self.assertNotIn('only via `/adr`', text)
        resident = self.text('core/surface/includes/safety-core.md')
        self.assertIn('authorized `/adr` workflow (`decision-lifecycle`)', resident)
        self.assertIn('outside that authoring workflow is prohibited, marker or not', resident)

    def test_authoring_distinguishes_absent_from_unreadable_storage(self):
        """Only a new explicitly authorized ADR may initialize absent storage."""
        text = ' '.join(self.text(self.author_path).split())
        self.assertIn('Unreadable existing storage is a STOP, not an empty index', text)
        self.assertIn('Only an explicitly authorized new-record request may create an absent directory', text)
        self.assertIn('changes to an existing record never create a missing directory', text)
        self.assertNotIn('Read these, or STOP and surface the gap', text)

    def test_adr_marker_uses_guard_project_root_and_captured_cleanup_path(self):
        """ADR guards differ from security/migration marker-root escalation."""
        import re
        text = self.text(self.author_path)
        resolver = re.search(r"-c '([^']+)'", text)
        self.assertIsNotNone(resolver)
        self.assertIn('from _hooklib import project_root', resolver.group(1))
        self.assertNotIn('marker_root', resolver.group(1))
        self.assertNotIn('git rev-parse --show-toplevel', text)
        self.assertIn('rm -f "$ADR_MARKER_ROOT/.codearbiter/.markers/adr-authoring-active"', text)
        self.assertIn('Do not resolve a different root during cleanup', text)
        self.assertIn('a resolver failure or empty result stops', text.lower())

    def test_current_progress_rollup_matches_adopted_owner_relationships(self):
        """An agent reading only the current table must not requeue completed work."""
        import re
        text = self.text('docs/reviews/2026-09-21-autonomy-routing-integration.md')
        current = text.split('## Current progress:', 1)[1].split('Active canonical command records', 1)[0]
        rows = re.findall(r'^\| (D\d{2}) \| [^|]+ \| (.+) \|$', current, re.M)
        self.assertEqual(len(rows), 15)
        self.assertEqual({key for key, value in rows if value.startswith('Pending')},
                         {'D03', 'D04', 'D07'})
        self.assertEqual(sum(value.startswith('Complete') for _, value in rows), 11)
        self.assertIn('eleven relationships, not eleven distinct composed owners', current)

    def test_status_adapter_never_becomes_a_second_composed_owner(self):
        """Retain the compiler guard that rejects duplicate discovery ownership."""
        import shutil
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(REPO_ROOT / 'core', root / 'core')
            _write(root, 'core/surface/commands/adr-status.md', '{{SKILL_ENTRY:decision-lifecycle}}\n')
            with self.assertRaisesRegex(B.SurfaceError, 'already exposed'):
                B.render_all(root, 'claude')




class AdrMarkerRootJourneyTest(unittest.TestCase):
    """Fresh-process resolver/guard agreement with real primary and linked roots."""

    def exercise(self, host, root_signal):
        import importlib.util
        import re
        import subprocess
        author = (REPO_ROOT / 'core/surface/skills/decision-lifecycle/references/authoring.md').read_text(encoding='utf-8')
        found = re.search(r"-c '([^']+)'", author)
        self.assertIsNotNone(found, 'authoring must carry a guard-aligned root resolver')
        resolver = found.group(1)
        hooks = REPO_ROOT / f'plugins/{host}/hooks'
        with tempfile.TemporaryDirectory(prefix='adr-root-contract-') as td:
            outer = Path(td).resolve()
            primary, linked = outer / 'primary', outer / 'linked'
            primary.mkdir()
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(('GIT_', 'CLAUDE_', 'CODEX_', 'PI_'))
                   and k not in ('PLUGIN_ROOT', 'PROJECT_DIR')}
            env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_AUTHOR_NAME='Fixture', GIT_COMMITTER_NAME='Fixture',
                       GIT_AUTHOR_EMAIL='fixture@example.invalid', GIT_COMMITTER_EMAIL='fixture@example.invalid')
            def git(*args):
                return subprocess.run(['git', *args], cwd=primary, env=env,
                                      capture_output=True, text=True, check=True, timeout=15)
            git('init', '--initial-branch=main')
            context = primary / '.codearbiter/CONTEXT.md'
            context.parent.mkdir()
            context.write_text('---\narbiter: enabled\n---\n', encoding='utf-8')
            git('add', '--', '.codearbiter/CONTEXT.md')
            git('commit', '-m', 'Isolated root fixture')
            git('worktree', 'add', str(linked), '-b', 'fixture-linked')
            cwd = linked / 'nested'
            cwd.mkdir()
            if root_signal:
                env['CLAUDE_PROJECT_DIR'] = str(primary if root_signal == 'primary' else linked)
            expected = primary if host == 'ca' and root_signal == 'primary' else linked
            selected = subprocess.run([sys.executable, '-c', resolver, str(hooks)],
                                      cwd=cwd, env=env, capture_output=True, text=True,
                                      encoding='utf-8', check=True, timeout=15)
            root = Path(selected.stdout.strip())
            self.assertTrue(root.samefile(expected), (host, root_signal, selected.stdout))
            marker = root / '.codearbiter/.markers/adr-authoring-active'
            other_root = linked if root.samefile(primary) else primary
            if host == 'ca' and root_signal == 'primary':
                legacy = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                                        cwd=cwd, env=env, capture_output=True, text=True,
                                        check=True, timeout=15)
                self.assertTrue(Path(legacy.stdout.strip()).samefile(other_root))
            else:
                # The general security/migration resolver intentionally escalates.
                # That is not the root used by this ADR guard in these cases.
                general = resolver.replace('project_root', 'marker_root')
                other = subprocess.run([sys.executable, '-c', general, str(hooks)],
                                       cwd=cwd, env=env, capture_output=True, text=True,
                                       check=True, timeout=15)
                self.assertTrue(Path(other.stdout.strip()).samefile(other_root))
            wrong_marker = other_root / '.codearbiter/.markers/adr-authoring-active'
            wrong_marker.parent.mkdir(parents=True, exist_ok=True)
            wrong_marker.touch()
            unrelated = wrong_marker.parent / 'unrelated-sentinel'
            unrelated.write_bytes(b'preserve')
            guard_code = ("import sys, importlib.util; sys.path.insert(0, sys.argv[1]); "
                          "from _hooklib import project_root, utf8_stdio; utf8_stdio(); "
                          "s=importlib.util.spec_from_file_location('adr_guard', sys.argv[1]+'/pre-write.py'); "
                          "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                          "m._guard_op(project_root(), {'kind':'write','file_path':sys.argv[2],'content':'# fixture'})")
            target = expected / '.codearbiter/decisions/0001-fixture.md'
            # Start this test-owned child with a deliberately non-UTF-8 pipe
            # encoding. Its production stdio initialization must establish the
            # strict UTF-8 contract, independently of the developer's environment.
            def guard():
                return subprocess.run([sys.executable, '-c', guard_code, str(hooks), str(target)],
                                      cwd=cwd, env=dict(env, PYTHONIOENCODING='cp1252'),
                                      capture_output=True, text=True,
                                      encoding='utf-8', timeout=15)
            denied = guard()
            self.assertEqual(denied.returncode, 2, denied.stdout + denied.stderr)
            self.assertIn('H-11', denied.stderr + denied.stdout)
            self.assertIn('ORCHESTRATOR \u00a73', denied.stderr + denied.stdout)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
            admitted = guard()
            self.assertEqual(admitted.returncode, 0, admitted.stdout + admitted.stderr)
            marker.unlink()  # same captured path, not a new root resolved from cwd
            denied_again = guard()
            self.assertEqual(denied_again.returncode, 2, denied_again.stdout + denied_again.stderr)
            self.assertTrue(wrong_marker.exists())
            self.assertEqual(unrelated.read_bytes(), b'preserve')
            self.assertFalse(target.exists(), 'guard checks must not actually author an ADR')

    def test_claude_main_signal_and_linked_cwd_use_the_guard_root(self):
        """The old Git-toplevel guess arms a marker the env-rooted guard misses."""
        self.exercise('ca', 'primary')

    def test_claude_linked_signal_does_not_unconditionally_escalate_to_main(self):
        """General marker_root escalation would be wrong for this ADR guard."""
        self.exercise('ca', 'linked')

    def test_codex_and_pi_ignore_a_foreign_claude_root_signal(self):
        """Host-local resolver semantics, not a Claude-only path, own the marker."""
        for host in ('ca-codex', 'ca-pi'):
            with self.subTest(host=host):
                self.exercise(host, 'primary')





class ReconcileOwnershipTest(unittest.TestCase):
    """D14 ownership, mode isolation and evidence preservation; not model behavior."""

    owner = 'core/surface/skills/decision-variance/SKILL.md'
    analysis = 'core/surface/skills/decision-variance/references/analysis.md'

    def text(self, path):
        """Read a canonical contract without importing a generated copy."""
        self.assertTrue((REPO_ROOT / path).is_file(), path)
        return (REPO_ROOT / path).read_text(encoding='utf-8')

    def test_one_composed_entry_and_concise_intent_metadata(self):
        """Keep the public name while removing its independently authored wrapper."""
        import re
        self.assertEqual(self.text('core/surface/commands/reconcile.md'), '{{SKILL_ENTRY:decision-variance}}\n')
        header = _frontmatter(self.text(self.owner))
        self.assertIn('name: decision-variance', header)
        self.assertIn('argument-hint: "(none) | \\"<ADR-id | artifact | scope>\\""'.replace('\\\\', '\\'), header)
        description = re.search(r'^description: (.+)$', header, re.M).group(1)
        value = json.loads(description) if description.startswith('"') else description
        self.assertLess(len(value), 160)
        self.assertNotIn('disable-model-invocation', header)

    def test_public_host_entries_and_private_card_are_closed(self):
        """All adapters expose the existing entry and include the inert analysis card."""
        for host in ('claude', 'codex', 'pi'):
            with self.subTest(host=host):
                out = B.render_all(REPO_ROOT, host)
                public = 'commands/reconcile.md' if host == 'claude' else 'skills/ca-reconcile/SKILL.md'
                prefix = 'skills' if host == 'claude' else 'routines'
                body = out[public].decode()
                self.assertEqual('disable-model-invocation: true' in _frontmatter(body), host == 'claude')
                self.assertIn('## Entry and scope', body)
                self.assertIn('## Phase 4', body)
                self.assertNotIn('## Phase 3', body)
                card = out[f'{prefix}/decision-variance/references/analysis.md'].decode()
                self.assertTrue(card.startswith('# Reconciliation analysis'))
                self.assertNotIn('\nname:', card)
                self.assertNotIn('\ndescription:', card)
                registry = json.loads(self.text('core/surface/command-routes.json'))['commands']['reconcile']
                metadata = json.loads(out['generated/command-catalog.json'])['commands']['reconcile']
                for key in ('canonical', 'visibility'):
                    self.assertEqual(metadata[key], registry[key])

    def test_direct_routing_does_not_return_through_wrapper(self):
        """Natural requests reach the existing owner, not another advertised resource."""
        self.assertIn('{{PLUGIN_ROOT}}/skills/decision-variance/SKILL.md', self.text('core/surface/includes/routing-table.md'))
        text = self.text(self.owner)
        self.assertIn('Natural-language requests', text)
        self.assertIn('Do not re-invoke the command wrapper', text)
        self.assertIn('Return to the caller', text)
        self.assertNotIn('Never volunteer this fast-path', text)

    def test_report_only_returns_before_decision_capture(self):
        """A variance report is a result, not consent to enter a writing interview."""
        text = self.text(self.owner)
        entry = text.split('## Phase 4', 1)[0]
        for term in ('report-only', 'no file changes', 'Do not load the analysis card', 'returns before Phase 4'):
            self.assertIn(term, entry)
        self.assertIn('No marker, directory, log, question, ADR, staging or commit', entry)
        self.assertIn('returned report', self.text(self.analysis))
        self.assertIn('no evidence-index file', self.text(self.analysis))

    def test_scoped_inputs_do_not_require_unrelated_decomposition(self):
        """Full passes retain exact-name inputs; bounded targets disclose their coverage."""
        text = self.text(self.analysis)
        for term in ('01-architecture-breakdown.md', '02-phased-build-plan.md', '03-task-backlog.md',
                     'full pass', 'scoped pass', 'not a full-project clearance',
                     'Unreadable', 'exact filename', 'full filename stem'):
            self.assertIn(term, text)
        self.assertIn('do not require unrelated decomposition files', text)
        self.assertIn('not interchangeable with HTML feature specs/plans', ' '.join(text.split()))

    def test_stale_ratification_appends_instead_of_rewriting_hash(self):
        """A refreshed source binding is a new attributed record, never an old-row edit."""
        text = self.text(self.owner) + self.text(self.analysis)
        for term in ('append a new entry', 'Supersedes:', 'current section hash',
                     'not in-place', 'missing or ambiguous section', 'before generating new variances'):
            self.assertIn(term, text)
        self.assertNotIn('keep (update the', text)
        self.assertNotIn('recorded hash to current', text)

    def test_unresolved_report_does_not_stop_all_analysis(self):
        """Staleness and unknown categories remain visible without a new report gate."""
        text = self.text(self.analysis)
        self.assertIn('continue independent analysis', text)
        self.assertIn('category: UNKNOWN', text)
        self.assertIn('not a reason to pause a report', text)
        self.assertIn('same-level-conflict', self.text(self.owner))
        self.assertNotIn('treat both as silent', self.text(self.owner))

    def test_recorded_choice_and_sprint_authority_stay_distinct(self):
        """Do not impose the arbitration interview on delegated sprint methods."""
        text = self.text(self.owner)
        for term in ('already selected', 'do not ask again', 'sprint', 'scoring only',
                     'No mid-sprint reconciliation', 'explicit user choice', 'general trust'):
            self.assertIn(term, text)
        self.assertIn('confirm it back in one sentence, then append the decision', text)
        self.assertIn('(1) an explicit user decision this session, (2) a', text)
        self.assertIn('(6) inferred intent', text)

    def test_outcomes_have_one_authorized_continuation(self):
        """Recording, ADR authoring and implementation are different authorities."""
        text = self.text(self.owner)
        for term in ('**Ratify**', '**Supersede**', '**Defer**', '[CONFIRM-NN]',
                     '{{PLUGIN_ROOT}}/skills/decision-lifecycle/SKILL.md',
                     'separately authorized', 'not authorization to commit', 'Never edit the artifacts'):
            self.assertIn(term, text)
        self.assertIn('re-read the log', text)
        self.assertIn('never duplicate', text)

    def test_scoring_and_adjacent_contracts_are_preserved(self):
        """Extraction changes loading, not SMARTS scoring or another agent's scope."""
        import hashlib
        card = self.text(self.analysis)
        self.assertEqual(hashlib.sha256(card[card.index('## Phase 3'):card.index('## Return boundary')].encode()).hexdigest(), 'd2129e34ce0bd412801d93c6372b5ca09617c90499940028fd9bcb75251d4c37')
        for path, expected in {'core/surface/SPRINT.md': 'f4febee07ef7446307c14cf8a52d40224daaddcf1e43bc1e84e9ca36af1f99ec', 'core/surface/includes/smarts/core.md': 'bec35848cb148b0c1ff8e05c39e561012ab74385074d11cc38d6d8315462b434', 'core/surface/includes/smarts/decision-log-format.md': 'bbdca34a776b9c0c440df79d119f75eedf276aae6c8e6b12aa704e2e7d89c2c6', 'core/surface/command-routes.json': '2ced3f30fea81d5318e5b22dcf05e14edd6d516c2920bf5bcfbd74596d1059cb', 'core/surface/skills/decompose/SKILL.md': 'cd8bdd5b2e7f347fd6d8f07118bdc2bab8fdd74ce2411a1dc64b21f373d05393', 'core/surface/skills/debug/SKILL.md': '86824be48ec461399920bb3ea8d5a9150f7908b928b3f611ea4f4e7b4203436a'}.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest(), expected)

    def test_duplicate_composed_owner_remains_rejected(self):
        """The consolidation cannot add a second model-facing procedure owner."""
        import shutil
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(REPO_ROOT / 'core', root / 'core')
            _write(root, 'core/surface/commands/adr-status.md', '{{SKILL_ENTRY:decision-variance}}\n')
            with self.assertRaisesRegex(B.SurfaceError, 'already exposed'):
                B.render_all(root, 'claude')

    def test_adr_cleanup_covers_controlled_failures_at_captured_path(self):
        """The remaining D12 review finding must not leave a fresh marker on a stop."""
        text = self.text('core/surface/skills/decision-lifecycle/references/authoring.md')
        for term in ('every exit after arming', 'ADR-write', 'decision-log-append', 'status-edit',
                     'before returning or stopping', 'Do not resolve a different root during cleanup',
                     'cleanup failure', 'not crash-safe'):
            self.assertIn(term, text)
        self.assertIn('rm -f "$ADR_MARKER_ROOT/.codearbiter/.markers/adr-authoring-active"', text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
