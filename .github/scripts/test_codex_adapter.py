#!/usr/bin/env python3
"""codeArbiter — tests for the ca-codex host adapter (ADR-0011, codex-support M2).

Covers the M2 contract:

  1. Codex payload -> normalized tool categories (Bash->EXEC,
     apply_patch/Write/Edit->WRITE, Read->READ, mcp__*->OTHER).
  2. apply_patch envelope parsing (grammar source: openai/codex
     codex-rs/prompts/templates/apply_patch_tool_instructions.md):
     Add File / Update File (+ Move to) / Delete File, added-line
     extraction, End of File marker, non-envelope fail-open.
  3. CodexHost.project_root: NO env leg (CLAUDE_PROJECT_DIR ignored);
     payload cwd -> git rev-parse -> cwd precedence.
  4. Claude Host.iter_file_ops maps Write/Edit payloads to the same
     canonical per-file ops (the seam the shared entries consume).
  5. Blocked-verdict parity: the same protected-path scenarios BLOCK
     (exit 2) under BOTH hosts' native payload shapes, via real
     subprocess invocations of each plugin's vendored pre-write.py.
  6. ca-codex hooks.json / plugin.json parse and register only real
     core entries; pre-read and prune-transcript stay unregistered
     (parity ledger: docs/parity.md).

Stdlib only. Exit 0 = all tests pass.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CA_HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
CODEX_HOOKS = os.path.join(REPO, "plugins", "ca-codex", "hooks")
CODEX_PLUGIN = os.path.join(REPO, "plugins", "ca-codex")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def codex_host():
    return _load(os.path.join(CODEX_HOOKS, "_host.py"), "codex_host_under_test").HOST


def claude_host():
    return _load(os.path.join(CA_HOOKS, "_host.py"), "claude_host_under_test").HOST


PATCH_ADD = (
    "*** Begin Patch\n"
    "*** Add File: notes/hello.txt\n"
    "+Hello world\n"
    "+second line\n"
    "*** End Patch\n"
)

PATCH_UPDATE = (
    "*** Begin Patch\n"
    "*** Update File: src/app.py\n"
    "@@ def greet():\n"
    " context line\n"
    "-print(\"Hi\")\n"
    "+print(\"Hello\")\n"
    "+print(\"World\")\n"
    "*** End Patch\n"
)

PATCH_DELETE = (
    "*** Begin Patch\n"
    "*** Delete File: obsolete.txt\n"
    "*** End Patch\n"
)

PATCH_COMBINED = (
    "*** Begin Patch\n"
    "*** Add File: hello.txt\n"
    "+Hello world\n"
    "*** Update File: src/app.py\n"
    "*** Move to: src/main.py\n"
    "@@ def greet():\n"
    "-print(\"Hi\")\n"
    "+print(\"Hello, world!\")\n"
    "*** Delete File: obsolete.txt\n"
    "*** End Patch\n"
)

PATCH_EOF_MARKER = (
    "*** Begin Patch\n"
    "*** Update File: tail.txt\n"
    "@@\n"
    " last old line\n"
    "+appended line\n"
    "*** End of File\n"
    "*** End Patch\n"
)


def _apply_patch_payload(patch, tool_name="apply_patch"):
    return {"hook_event_name": "PreToolUse", "tool_name": tool_name,
            "tool_input": {"command": patch}}


class TestCodexToolNormalization(unittest.TestCase):
    """Codex tool names -> canonical categories (spike §2)."""

    def setUp(self):
        self.host = codex_host()

    def test_name_and_capabilities(self):
        self.assertEqual(self.host.name, "codex")
        self.assertFalse(self.host.has_statusline)
        self.assertFalse(self.host.has_read_tool)

    def test_bash_is_exec(self):
        self.assertEqual(self.host.normalize_tool("Bash"), "EXEC")

    def test_apply_patch_and_aliases_are_write(self):
        # Write/Edit are matcher-only aliases whose payload is still the
        # apply_patch envelope (openai/codex hook_names.rs).
        for name in ("apply_patch", "Write", "Edit"):
            self.assertEqual(self.host.normalize_tool(name), "WRITE", name)

    def test_read_alias_safety(self):
        # Codex has no read tool, but a Read matcher alias must never be
        # misclassified as a write.
        self.assertEqual(self.host.normalize_tool("Read"), "READ")

    def test_mcp_tools_are_other(self):
        self.assertEqual(self.host.normalize_tool("mcp__github__create_issue"), "OTHER")

    def test_unknown_and_empty_are_other(self):
        self.assertEqual(self.host.normalize_tool("PowerShell"), "OTHER")
        self.assertEqual(self.host.normalize_tool(""), "OTHER")
        self.assertEqual(self.host.normalize_tool(None), "OTHER")


class TestApplyPatchParsing(unittest.TestCase):
    """apply_patch envelope -> canonical per-file ops."""

    def setUp(self):
        self.host = codex_host()

    def ops(self, patch, tool_name="apply_patch"):
        return self.host.iter_file_ops(_apply_patch_payload(patch, tool_name))

    def test_add_file(self):
        ops = self.ops(PATCH_ADD)
        self.assertEqual(len(ops), 1)
        op = ops[0]
        self.assertEqual(op["file_path"], "notes/hello.txt")
        self.assertEqual(op["kind"], "write")
        self.assertEqual(op["added_lines"], ["Hello world", "second line"])
        # An Add File's + lines ARE the full new content (H-18 needs it whole).
        self.assertEqual(op["content"], "Hello world\nsecond line\n")

    def test_update_file_extracts_only_added_lines(self):
        ops = self.ops(PATCH_UPDATE)
        self.assertEqual(len(ops), 1)
        op = ops[0]
        self.assertEqual(op["file_path"], "src/app.py")
        self.assertEqual(op["kind"], "edit")
        self.assertEqual(op["added_lines"], ['print("Hello")', 'print("World")'])
        # Context (" ") and removal ("-") lines are never "added" content.
        self.assertNotIn("context line", "\n".join(op["added_lines"]))

    def test_delete_file(self):
        ops = self.ops(PATCH_DELETE)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["file_path"], "obsolete.txt")
        self.assertEqual(ops[0]["kind"], "delete")
        self.assertEqual(ops[0]["added_lines"], [])

    def test_combined_patch_yields_all_ops(self):
        ops = self.ops(PATCH_COMBINED)
        paths = [(o["file_path"], o["kind"]) for o in ops]
        self.assertIn(("hello.txt", "write"), paths)
        self.assertIn(("obsolete.txt", "delete"), paths)
        # The Move to rename touches BOTH paths: the source goes away and the
        # destination receives the (patched) content — both must be guarded.
        self.assertIn(("src/app.py", "delete"), paths)
        dest = [o for o in ops if o["file_path"] == "src/main.py"]
        self.assertEqual(len(dest), 1)
        self.assertEqual(dest[0]["kind"], "edit")
        self.assertEqual(dest[0]["added_lines"], ['print("Hello, world!")'])

    def test_end_of_file_marker_is_not_content(self):
        ops = self.ops(PATCH_EOF_MARKER)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["added_lines"], ["appended line"])

    def test_write_alias_payload_parses_identically(self):
        self.assertEqual(self.ops(PATCH_ADD, tool_name="Write"),
                         self.ops(PATCH_ADD, tool_name="apply_patch"))
        self.assertEqual(self.ops(PATCH_ADD, tool_name="Edit"),
                         self.ops(PATCH_ADD, tool_name="apply_patch"))

    def test_non_envelope_command_fails_open_to_no_ops(self):
        self.assertEqual(self.ops("echo hello"), [])

    def test_crlf_envelope_parses_like_lf(self):
        # Codex's parser is LENIENT (PARSE_IN_STRICT_MODE=false): str::lines()
        # strips one trailing \r per line, so a CRLF envelope is accepted and
        # APPLIED. The adapter must decompose it identically to LF input, or
        # a Windows-flavored patch un-guards every file it touches.
        for fixture in (PATCH_ADD, PATCH_UPDATE, PATCH_DELETE, PATCH_COMBINED,
                        PATCH_EOF_MARKER):
            self.assertEqual(self.ops(fixture.replace("\n", "\r\n")),
                             self.ops(fixture), fixture[:40])

    def test_whitespace_indented_markers_parse(self):
        # The lenient parser trims whitespace around marker lines.
        indented = (
            "  *** Begin Patch\n"
            "   *** Add File: notes/hello.txt\n"
            "+Hello world\n"
            " *** End Patch\n"
        )
        ops = self.ops(indented)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["file_path"], "notes/hello.txt")
        self.assertEqual(ops[0]["kind"], "write")
        self.assertEqual(ops[0]["added_lines"], ["Hello world"])

    def test_envelope_with_zero_ops_fails_closed_as_opaque(self):
        # An envelope marker is present but nothing decomposes: Codex might
        # still apply a shape we cannot mirror, so the adapter emits one
        # "opaque" op that pre-write blocks outright (H-21) — never [] (which
        # would silently un-guard the whole patch).
        ops = self.ops("*** Begin Patch\nsomething unrecognized\n*** End Patch\n")
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["kind"], "opaque")

    def test_empty_and_malformed_payloads(self):
        self.assertEqual(self.host.iter_file_ops({}), [])
        self.assertEqual(self.host.iter_file_ops(None), [])
        self.assertEqual(self.host.iter_file_ops(
            {"tool_name": "apply_patch", "tool_input": {"command": 42}}), [])

    def test_claude_shaped_fallback(self):
        # Defensive: if a future Codex ever ships a Claude-shaped
        # {file_path, content} payload, guard it as a write.
        ops = self.host.iter_file_ops({
            "tool_name": "Write",
            "tool_input": {"file_path": "a.txt", "content": "x\n"}})
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["kind"], "write")
        self.assertEqual(ops[0]["file_path"], "a.txt")


class TestCodexProjectRoot(unittest.TestCase):
    """CodexHost.project_root: payload cwd -> git rev-parse -> cwd; NO env leg."""

    def setUp(self):
        self.host = codex_host()
        self._env = os.environ.get("CLAUDE_PROJECT_DIR")
        self._cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._cwd)
        if self._env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._env

    def test_payload_cwd_wins_and_env_is_ignored(self):
        with tempfile.TemporaryDirectory() as payload_dir, \
                tempfile.TemporaryDirectory() as env_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = env_dir
            got = self.host.project_root({"cwd": payload_dir})
            self.assertEqual(os.path.realpath(got), os.path.realpath(payload_dir))

    def test_env_never_consulted_even_without_payload(self):
        with tempfile.TemporaryDirectory() as env_dir, \
                tempfile.TemporaryDirectory() as plain:
            os.environ["CLAUDE_PROJECT_DIR"] = env_dir
            os.chdir(plain)  # not a git repo -> final cwd fallback
            try:
                got = self.host.project_root(None)
            finally:
                os.chdir(self._cwd)  # release the dir before temp cleanup
            self.assertNotEqual(os.path.realpath(got), os.path.realpath(env_dir))
            self.assertEqual(os.path.realpath(got), os.path.realpath(plain))

    def test_git_leg_between_payload_and_cwd(self):
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            repo = os.path.join(top, "repo")
            sub = os.path.join(repo, "sub")
            os.makedirs(sub)
            r = subprocess.run(["git", "init", "-q"], cwd=repo,
                               capture_output=True, timeout=30)
            if r.returncode != 0:
                self.skipTest("git unavailable")
            os.chdir(sub)
            try:
                got = self.host.project_root({})  # payload with no usable cwd
            finally:
                os.chdir(self._cwd)
            self.assertEqual(os.path.realpath(got), os.path.realpath(repo))

    def test_bad_payload_cwd_falls_through(self):
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        with tempfile.TemporaryDirectory() as plain:
            os.chdir(plain)
            try:
                got = self.host.project_root(
                    {"cwd": os.path.join(plain, "no-such-dir")})
            finally:
                os.chdir(self._cwd)
            self.assertEqual(os.path.realpath(got), os.path.realpath(plain))


class TestClaudeIterFileOps(unittest.TestCase):
    """The Claude side of the seam: Write/Edit payloads -> the SAME canonical
    op shape the shared entries consume (Claude behavior stays identical)."""

    def setUp(self):
        self.host = claude_host()

    def test_write_payload_maps_to_write_op(self):
        ops = self.host.iter_file_ops({
            "tool_name": "Write",
            "tool_input": {"file_path": "a.txt", "content": "x\ny\n"}})
        self.assertEqual(len(ops), 1)
        op = ops[0]
        self.assertEqual(op["file_path"], "a.txt")
        self.assertEqual(op["kind"], "write")
        self.assertEqual(op["content"], "x\ny\n")
        self.assertEqual(op["added_text"], "x\ny\n")
        self.assertEqual(op["added_lines"], ["x", "y"])

    def test_edit_payload_maps_to_edit_op(self):
        ops = self.host.iter_file_ops({
            "tool_name": "Edit",
            "tool_input": {"file_path": "a.txt", "old_string": "x",
                           "new_string": "jwt.verify(t, k)\n"}})
        self.assertEqual(len(ops), 1)
        op = ops[0]
        self.assertEqual(op["kind"], "edit")
        self.assertIsNone(op["content"])
        self.assertEqual(op["added_text"], "jwt.verify(t, k)\n")

    def test_payload_without_tool_name_still_guarded_as_write(self):
        # pre-seam pre-write.py never read tool_name — any payload with a
        # file_path was guarded. The seam must not narrow that.
        ops = self.host.iter_file_ops({
            "tool_input": {"file_path": ".codearbiter/overrides.log",
                           "content": "forged\n"}})
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["kind"], "write")


class _VerdictFixture(unittest.TestCase):
    """Subprocess harness: spawn each plugin's vendored pre-write.py against a
    throwaway arbiter-enabled repo with its host's NATIVE payload shape."""

    ARBITER = "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\nfixture\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        self.ca = os.path.join(self.root, ".codearbiter")
        os.makedirs(os.path.join(self.ca, "decisions"))
        self._write(os.path.join(self.ca, "CONTEXT.md"), self.ARBITER)
        self._write(os.path.join(self.ca, "overrides.log"), "seed\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def _spawn(self, script, payload, claude_env):
        env = dict(os.environ)
        if claude_env:
            env["CLAUDE_PROJECT_DIR"] = self.root
        else:
            # Codex sets no project-dir var; the hook resolves from its cwd.
            env.pop("CLAUDE_PROJECT_DIR", None)
        return subprocess.run(
            [sys.executable, script], input=json.dumps(payload), cwd=self.root,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, env=env)

    def claude_write(self, file_path, content="x\n"):
        return self._spawn(
            os.path.join(CA_HOOKS, "pre-write.py"),
            {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": self.root,
             "tool_input": {"file_path": os.path.join(self.root, file_path),
                            "content": content}},
            claude_env=True)

    def codex_patch(self, patch):
        return self._spawn(
            os.path.join(CODEX_HOOKS, "pre-write.py"),
            {"hook_event_name": "PreToolUse", "tool_name": "apply_patch",
             "cwd": self.root, "tool_input": {"command": patch}},
            claude_env=False)

    def assertBlocked(self, res, tag):
        self.assertEqual(res.returncode, 2,
                         f"expected BLOCK (exit 2); got exit={res.returncode} "
                         f"stderr={res.stderr.strip()[:300]!r}")
        self.assertIn(tag, res.stderr)

    def assertAllowed(self, res):
        self.assertEqual(res.returncode, 0,
                         f"expected ALLOW (exit 0); got exit={res.returncode} "
                         f"stderr={res.stderr.strip()[:300]!r}")


def _patch(body):
    return "*** Begin Patch\n" + body + "*** End Patch\n"


class TestBlockedVerdictParity(_VerdictFixture):
    """The same scenario must BLOCK under both hosts' payload shapes."""

    def test_audit_log_overwrite_blocks_on_both_hosts(self):
        self.assertBlocked(self.claude_write(".codearbiter/overrides.log"), "H-05")
        self.assertBlocked(self.codex_patch(_patch(
            "*** Update File: .codearbiter/overrides.log\n"
            "@@\n-seed\n+rewritten\n")), "H-05")

    def test_audit_log_delete_blocks_on_codex(self):
        self.assertBlocked(self.codex_patch(_patch(
            "*** Delete File: .codearbiter/overrides.log\n")), "H-05")

    def test_adr_write_without_marker_blocks_on_both_hosts(self):
        self.assertBlocked(
            self.claude_write(".codearbiter/decisions/0002-new.md"), "H-11")
        self.assertBlocked(self.codex_patch(_patch(
            "*** Add File: .codearbiter/decisions/0002-new.md\n+# ADR-0002\n")),
            "H-11")

    def test_gate_marker_forge_blocks_on_both_hosts(self):
        self.assertBlocked(
            self.claude_write(".codearbiter/.markers/security-gate-passed"), "H-19")
        self.assertBlocked(self.codex_patch(_patch(
            "*** Add File: .codearbiter/.markers/security-gate-passed\n+deadbeef\n")),
            "H-19")

    def test_context_md_disable_blocks_on_both_hosts(self):
        self.assertBlocked(
            self.claude_write(".codearbiter/CONTEXT.md", "# no frontmatter\n"), "H-18")
        # A patch hunk's resulting frontmatter cannot be verified -> fail closed.
        self.assertBlocked(self.codex_patch(_patch(
            "*** Update File: .codearbiter/CONTEXT.md\n"
            "@@\n-arbiter: enabled\n+arbiter: disabled\n")), "H-18")
        self.assertBlocked(self.codex_patch(_patch(
            "*** Delete File: .codearbiter/CONTEXT.md\n")), "H-18")

    def test_ordinary_write_allowed_on_both_hosts(self):
        self.assertAllowed(self.claude_write("src/util.py", "x = 1\n"))
        self.assertAllowed(self.codex_patch(_patch(
            "*** Add File: src/util.py\n+x = 1\n")))

    def test_dormant_repo_is_untouched_on_codex(self):
        self._write(os.path.join(self.ca, "CONTEXT.md"), "# ctx\nno frontmatter\n")
        self.assertAllowed(self.codex_patch(_patch(
            "*** Update File: .codearbiter/overrides.log\n@@\n-seed\n+rewritten\n")))

    def test_adr_write_with_fresh_marker_allowed_on_codex(self):
        self._write(os.path.join(self.ca, ".markers", "adr-authoring-active"),
                    "active\n")
        self.assertAllowed(self.codex_patch(_patch(
            "*** Add File: .codearbiter/decisions/0002-new.md\n+# ADR-0002\n")))

    def test_crlf_audit_patch_still_blocks_on_codex(self):
        # Regression (M2 security review, HIGH): a CRLF envelope is valid to
        # Codex's lenient parser and must hit the same H-05 verdict as LF.
        crlf = _patch(
            "*** Update File: .codearbiter/overrides.log\n"
            "@@\n-seed\n+rewritten\n").replace("\n", "\r\n")
        self.assertBlocked(self.codex_patch(crlf), "H-05")

    def test_undecomposable_envelope_blocks_on_codex(self):
        # Envelope present, zero ops decomposed -> opaque -> H-21 fail-closed.
        self.assertBlocked(self.codex_patch(
            "*** Begin Patch\nsomething unrecognized\n*** End Patch\n"), "H-21")


class TestCodexPreBashParity(_VerdictFixture):
    """Codex's Bash payload is shape-identical to Claude's — the no-verify
    commit block (H-20) must fire from the Codex plugin's vendored entry."""

    def codex_bash(self, command):
        return self._spawn(
            os.path.join(CODEX_HOOKS, "pre-bash.py"),
            {"hook_event_name": "PreToolUse", "tool_name": "Bash",
             "cwd": self.root, "tool_input": {"command": command}},
            claude_env=False)

    def test_no_verify_commit_blocks(self):
        self.assertBlocked(self.codex_bash('git commit --no-verify -m "x"'), "H-20")

    def test_audit_log_truncation_blocks(self):
        self.assertBlocked(
            self.codex_bash("echo x > .codearbiter/overrides.log"), "H-05")

    def test_plain_command_allowed(self):
        self.assertAllowed(self.codex_bash("ls -la"))


class TestCodexHooksJson(unittest.TestCase):
    """ca-codex hooks.json parses and registers only real core entries."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(CODEX_HOOKS, "hooks.json"), encoding="utf-8") as f:
            cls.cfg = json.load(f)
        cls.hooks = cls.cfg["hooks"]

    def _entries(self, event):
        out = []
        for group in self.hooks.get(event, []):
            for h in group.get("hooks", []):
                out.append((group.get("matcher"), h))
        return out

    def _scripts(self, cmd):
        return re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/hooks/([\w.-]+\.py)", cmd or "")

    def test_every_registered_script_exists(self):
        for event in self.hooks:
            for _, h in self._entries(event):
                for field in ("command", "commandWindows"):
                    for script in self._scripts(h.get(field, "")):
                        self.assertTrue(
                            os.path.isfile(os.path.join(CODEX_HOOKS, script)),
                            f"{event}: registered {script} missing from hooks/")

    def test_session_start_registered(self):
        entries = self._entries("SessionStart")
        self.assertTrue(any("session-start.py" in h["command"] for _, h in entries))

    def test_pre_tool_use_matchers(self):
        entries = self._entries("PreToolUse")
        bash = [h for m, h in entries if m == "Bash"]
        write = [h for m, h in entries if m == "apply_patch|Write|Edit"]
        self.assertTrue(any("pre-bash.py" in h["command"] for h in bash))
        self.assertTrue(any("pre-write.py" in h["command"] for h in write))

    def test_post_tool_use_matcher(self):
        entries = self._entries("PostToolUse")
        self.assertTrue(any(m == "apply_patch|Write|Edit"
                            and "post-write-edit.py" in h["command"]
                            for m, h in entries))

    def test_ledgered_out_surfaces_not_registered(self):
        text = json.dumps(self.cfg)
        self.assertNotIn("pre-read.py", text)       # no read tool on Codex
        self.assertNotIn("prune-transcript.py", text)  # ledgered out
        self.assertNotIn("pre-edit.py", text)       # edits arrive as apply_patch

    def test_windows_fallback_and_timeouts(self):
        for event in self.hooks:
            for _, h in self._entries(event):
                self.assertIn("commandWindows", h)
                self.assertIsInstance(h.get("timeout"), int)


class TestCodexPluginJson(unittest.TestCase):
    def test_manifest(self):
        path = os.path.join(CODEX_PLUGIN, ".codex-plugin", "plugin.json")
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(m["name"], "ca-codex")
        self.assertEqual(m["version"], "0.1.0")
        self.assertEqual(m["license"], "AGPL-3.0-only")
        self.assertIn("beta", m["description"].lower())

    def test_marketplace_lists_ca_codex(self):
        path = os.path.join(REPO, ".agents", "plugins", "marketplace.json")
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        names = [p["name"] for p in m["plugins"]]
        self.assertIn("ca-codex", names)


if __name__ == "__main__":
    unittest.main()
