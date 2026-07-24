#!/usr/bin/env python3
"""Three-host enforcement parity and descriptor mapping fixtures for ca-pi."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
HOOKS = {
    "claude": REPO / "plugins" / "ca" / "hooks",
    "codex": REPO / "plugins" / "ca-codex" / "hooks",
    "pi": REPO / "plugins" / "ca-pi" / "hooks",
}
RULE_RE = re.compile(r"\[((?:H|PI)-[A-Za-z0-9]+)\]")
PI_EXTENSION_NATIVE_TOOL_CLASSES = {"codearbiter_background_bash": "EXEC"}


def run(args, cwd, *, payload=None, env=None, timeout=60):
    return subprocess.run(
        [str(item) for item in args], cwd=cwd,
        input=None if payload is None else json.dumps(payload),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=timeout,
    )


def git(root, *args):
    result = run(["git", *args], root)
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def fixture(base, enabled=True):
    root = Path(base) / "repo"
    root.mkdir()
    git(base, "init", "-q", "-b", "feat/pi-parity", root)
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "Pi parity fixture")
    ca = root / ".codearbiter"
    (ca / "decisions").mkdir(parents=True)
    context = "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n" if enabled else "# dormant\n"
    (ca / "CONTEXT.md").write_text(context, encoding="utf-8")
    (ca / "overrides.log").write_text("seed\n", encoding="utf-8")
    (ca / "decisions" / "0001-seed.md").write_text("# seed\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('seed')\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "seed")
    return root


def environment(root, host):
    env = dict(os.environ)
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "CODEARBITER_BASE_BRANCH": "main",
    })
    if host == "claude":
        env["CLAUDE_PROJECT_DIR"] = str(root)
    else:
        env.pop("CLAUDE_PROJECT_DIR", None)
    return env


def patch_add(path, content):
    lines = "".join(f"+{line}\n" for line in content.splitlines())
    return f"*** Begin Patch\n*** Add File: {path}\n{lines}*** End Patch\n"


def verdict(host, root, *, command=None, path=None, content="x\n"):
    if command is not None:
        script = HOOKS[host] / "pre-bash.py" if host != "pi" else HOOKS[host] / "pi-bridge.py"
        if host == "pi":
            payload = {"version": 1, "event": "tool_call", "cwd": str(root), "tool": "bash", "input": {"command": command}}
        else:
            payload = {"hook_event_name": "PreToolUse", "cwd": str(root), "tool_name": "Bash", "tool_input": {"command": command}}
    else:
        script = HOOKS[host] / "pre-write.py" if host != "pi" else HOOKS[host] / "pi-bridge.py"
        absolute = str(root / path)
        if host == "claude":
            payload = {"hook_event_name": "PreToolUse", "cwd": str(root), "tool_name": "Write", "tool_input": {"file_path": absolute, "content": content}}
        elif host == "codex":
            payload = {"hook_event_name": "PreToolUse", "cwd": str(root), "tool_name": "apply_patch", "tool_input": {"command": patch_add(path, content)}}
        else:
            payload = {"version": 1, "event": "tool_call", "cwd": str(root), "tool": "write", "input": {"path": absolute, "content": content}}
    result = run([sys.executable, script], root, payload=payload, env=environment(root, host))
    if host == "pi":
        if result.returncode != 0:
            return "bridge-error", None, result.stderr
        response = json.loads(result.stdout)
        return response["outcome"], response.get("ruleId"), response.get("message", "")
    match = RULE_RE.search(result.stderr)
    if result.returncode not in (0, 2):
        return "hook-error", None, result.stderr
    return ("block" if result.returncode == 2 else "allow"), (match.group(1) if match else None), result.stderr


def runtime_hook_tool_map(host):
    hooks = HOOKS[host]
    code = (
        "import json,sys; "
        f"sys.path.insert(0,{str(hooks)!r}); "
        "import hostapi; "
        + ("value=hostapi.Host().TOOL_MAP; " if host == "claude" else f"value=hostapi.load_host({str(hooks)!r}).TOOL_MAP; ")
        + "print(json.dumps(value,sort_keys=True))"
    )
    result = run([sys.executable, "-c", code], REPO)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def load_pi_bridge():
    import importlib.util
    path = HOOKS["pi"] / "pi-bridge.py"
    sys.path.insert(0, str(HOOKS["pi"]))
    try:
        spec = importlib.util.spec_from_file_location("pi_bridge_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class PiParityFixtures(unittest.TestCase):
    def test_parity_ledger_classifies_the_new_pi_surfaces_exactly(self):
        parity = (REPO / "docs" / "parity.md").read_text(encoding="utf-8")
        for capability in (
            "Rich footer",
            "Execute permission asks",
            "Read-only plan mode",
            "Session-only background jobs",
            "Generated skill catalog",
            "Cold platform prerequisite",
        ):
            with self.subTest(capability=capability):
                self.assertRegex(parity, rf"(?m)^\| {re.escape(capability)} .*\| SUPPORTED \|")
        self.assertRegex(
            parity,
            r"(?m)^\| Pi rate-window telemetry \| HOST-IMPOSSIBLE \|",
        )
        self.assertNotIn("| Pi complete footer | DEGRADED |", parity)

    def assert_shared(self, root, expected, **operation):
        values = {host: verdict(host, root, **operation) for host in HOOKS}
        for host, (outcome, rule, detail) in values.items():
            self.assertEqual((outcome, rule), ("block", expected), f"{host}: {detail[:500]}")

    def test_descriptor_tool_classes_equal_runtime_hook_maps(self):
        descriptor = json.loads((REPO / "core" / "hosts.json").read_text(encoding="utf-8"))
        configured = {host["name"]: host["tool_classes"] for host in descriptor["hosts"]}
        for host in ("claude", "codex"):
            self.assertEqual(configured[host], runtime_hook_tool_map(host), host)
        pi_runtime = runtime_hook_tool_map("pi")
        pi_extension = {
            name: category
            for name, category in configured["pi"].items()
            if name not in pi_runtime
        }
        self.assertEqual(pi_extension, PI_EXTENSION_NATIVE_TOOL_CLASSES)
        self.assertEqual(
            {name: category for name, category in configured["pi"].items() if name not in pi_extension},
            pi_runtime,
        )

    def test_extension_native_tool_uses_the_live_registration_seam(self):
        npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm") or shutil.which("npm")
        self.assertIsNotNone(npm, "npm is required for the focused Pi registration contract")
        result = run([
            npm,
            "--prefix",
            "plugins/ca-pi/tools",
            "exec",
            "vitest",
            "run",
            "test/tool-guard.test.ts",
            "-t",
            "registers the core-descriptor background tool through the enforcement installer",
        ], REPO)
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-2_000:])

    def test_h01_protected_branch_push(self):
        with tempfile.TemporaryDirectory() as td:
            self.assert_shared(fixture(td), "H-01", command="git push origin main")

    def test_h03_broad_stage(self):
        with tempfile.TemporaryDirectory() as td:
            self.assert_shared(fixture(td), "H-03", command="git add -A")

    def test_h05_audit_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            self.assert_shared(fixture(td), "H-05", path=".codearbiter/overrides.log")

    def test_h09b_crypto_commit_without_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = fixture(td)
            (root / "src" / "app.py").write_text("const h = createHash('sha256');\n", encoding="utf-8")
            git(root, "add", "src/app.py")
            self.assert_shared(root, "H-09b", command="git commit -m crypto")

    def test_h10b_secret_commit_without_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = fixture(td)
            (root / "src" / "app.py").write_text('API_KEY = "hardcoded-secret-value"\n', encoding="utf-8")
            git(root, "add", "src/app.py")
            self.assert_shared(root, "H-10b", command="git commit -m secret")

    def test_h11_decision_write_without_marker(self):
        with tempfile.TemporaryDirectory() as td:
            self.assert_shared(fixture(td), "H-11", path=".codearbiter/decisions/0002-new.md", content="# ADR\n")

    def test_h18_context_disable(self):
        with tempfile.TemporaryDirectory() as td:
            self.assert_shared(fixture(td), "H-18", path=".codearbiter/CONTEXT.md", content="# disabled\n")

    def test_h19_marker_forge(self):
        with tempfile.TemporaryDirectory() as td:
            self.assert_shared(fixture(td), "H-19", path=".codearbiter/.markers/security-gate-passed", content="forged\n")

    def test_h20_no_verify_commit(self):
        with tempfile.TemporaryDirectory() as td:
            self.assert_shared(fixture(td), "H-20", command="git commit --no-verify -m x")

    def test_enabled_repo_allows_benign_operations_on_every_host(self):
        with tempfile.TemporaryDirectory() as td:
            root = fixture(td)
            for host in HOOKS:
                outcome, rule, detail = verdict(host, root, command="git status")
                self.assertIn(outcome, ("allow", "notice"), f"{host} command: {detail[:500]}")
                self.assertIsNone(rule, f"{host} command: {detail[:500]}")
                outcome, rule, detail = verdict(host, root, path="src/new_module.py", content="print('benign')\n")
                self.assertIn(outcome, ("allow", "notice"), f"{host} write: {detail[:500]}")
                self.assertIsNone(rule, f"{host} write: {detail[:500]}")

    def test_dormant_repo_allows_equivalent_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = fixture(td, enabled=False)
            for host in HOOKS:
                outcome, rule, detail = verdict(host, root, path=".codearbiter/overrides.log")
                self.assertEqual((outcome, rule), ("allow", None), f"{host}: {detail}")

    def test_unknown_pi_tool_is_stricter_and_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root = fixture(td)
            payload = {"version": 1, "event": "tool_call", "cwd": str(root), "tool": "opaque_extension", "input": {}}
            result = run([sys.executable, HOOKS["pi"] / "pi-bridge.py"], root, payload=payload, env=environment(root, "pi"))
            self.assertEqual(result.returncode, 0, result.stderr)
            response = json.loads(result.stdout)
            self.assertEqual((response["outcome"], response["ruleId"]), ("block", "PI-UNKNOWN"))

    def test_malformed_and_oversized_pi_protocol_fail_before_shared_entry(self):
        with tempfile.TemporaryDirectory() as td:
            root = fixture(td)
            malformed = subprocess.run(
                [sys.executable, HOOKS["pi"] / "pi-bridge.py"], cwd=root,
                input=b"not-json", capture_output=True, timeout=10,
            )
            self.assertNotEqual(malformed.returncode, 0)
            self.assertNotIn(b"not-json", malformed.stderr)
            oversized = subprocess.run(
                [sys.executable, HOOKS["pi"] / "pi-bridge.py"], cwd=root,
                input=b"x" * 262_145, capture_output=True, timeout=10,
            )
            self.assertNotEqual(oversized.returncode, 0)
            self.assertIn(b"ProtocolError", oversized.stderr)

            nonstandard = subprocess.run(
                [sys.executable, HOOKS["pi"] / "pi-bridge.py"], cwd=root,
                input=(f'{{"version":1,"event":"tool_call","cwd":{json.dumps(str(root))},"tool":"read","input":{{"offset":NaN}}}}').encode(),
                capture_output=True, timeout=10,
            )
            self.assertNotEqual(nonstandard.returncode, 0)
            self.assertIn(b"ProtocolError", nonstandard.stderr)

    def test_shared_output_capture_is_bounded_during_writes(self):
        bridge = load_pi_bridge()
        capture = bridge.BoundedText(64)
        capture.write("x" * 10_000)
        self.assertTrue(capture.overflowed)
        self.assertLessEqual(len(capture.getvalue().encode("utf-8")), 64)

    def test_strict_protocol_rejects_duplicates_nonfinite_events_and_wrong_shapes(self):
        bridge = load_pi_bridge()
        with tempfile.TemporaryDirectory() as td:
            root = fixture(td)
            cwd = json.dumps(str(root))
            invalid = [
                f'{{"version":true,"event":"session_start","cwd":{cwd}}}',
                f'{{"version":1.0,"event":"session_start","cwd":{cwd}}}',
                f'{{"version":1,"version":1,"event":"session_start","cwd":{cwd}}}',
                f'{{"version":1,"event":"tool_call","cwd":{cwd},"tool":"read","input":{{"offset":1e400}}}}',
                f'{{"version":1,"event":"unknown","cwd":{cwd}}}',
                f'{{"version":1,"event":"session_start","cwd":{cwd},"tool":"read"}}',
                f'{{"version":1,"event":"tool_call","cwd":{cwd},"tool":"read"}}',
                f'{{"version":1,"event":"tool_result","cwd":{cwd},"tool":"write","input":{{}}}}',
            ]
            for raw in invalid:
                with self.subTest(raw=raw), self.assertRaises(bridge.ProtocolError):
                    bridge._request(raw.encode("utf-8"))

    def test_pi_read_and_edit_payload_normalization(self):
        bridge = load_pi_bridge()
        host = bridge.PiHost()
        self.assertEqual(host.normalize_tool_input("read", {"path": "README.md"}), {"file_path": "README.md"})
        self.assertEqual(host.normalize_tool_input("read", {"file_path": "README.md"}), {"file_path": "README.md"})
        batched = host.iter_file_ops({"tool_name": "edit", "tool_input": {
            "path": "src/app.py",
            "edits": [{"oldText": "a", "newText": "b"}, {"oldText": "c", "newText": "d"}],
        }})
        self.assertEqual([item["added_text"] for item in batched], ["b", "d"])
        self.assertTrue(all(item["batched"] for item in batched))
        legacy = host.iter_file_ops({"tool_name": "edit", "tool_input": {
            "path": "src/app.py", "oldText": "old", "newText": "new",
        }})
        self.assertEqual(len(legacy), 1)
        self.assertEqual((legacy[0]["old_string"], legacy[0]["added_text"]), ("old", "new"))

        with tempfile.TemporaryDirectory() as td:
            root = fixture(td)
            operations = [
                ("read", {"path": str(root / "src" / "app.py")}),
                ("edit", {"path": str(root / "src" / "app.py"), "edits": [
                    {"oldText": "print('seed')", "newText": "print('one')"},
                    {"oldText": "print('one')", "newText": "print('two')"},
                ]}),
                ("edit", {"path": str(root / "src" / "app.py"), "oldText": "print('seed')", "newText": "print('legacy')"}),
            ]
            for tool, tool_input in operations:
                with self.subTest(tool=tool, tool_input=tool_input):
                    result = run([sys.executable, HOOKS["pi"] / "pi-bridge.py"], root, payload={
                        "version": 1, "event": "tool_call", "cwd": str(root),
                        "tool": tool, "input": tool_input,
                    }, env=environment(root, "pi"))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(json.loads(result.stdout)["outcome"], ("allow", "notice"))

    def test_pi_bridge_native_read_matches_canonical_shared_context(self):
        with tempfile.TemporaryDirectory() as td:
            root = fixture(td)
            target = root / "src" / "app.py"
            (root / ".codearbiter" / "decisions" / "0015-pi-read.md").write_text(
                "---\n"
                "title: Model-visible read contract\n"
                "status: accepted\n"
                "governs: src/app.py\n"
                "---\n"
                "# Model-visible read contract\n",
                encoding="utf-8",
                newline="\n",
            )

            def bridge_read(session_id, tool_input):
                result = run([sys.executable, HOOKS["pi"] / "pi-bridge.py"], root, payload={
                    "version": 1,
                    "event": "tool_call",
                    "cwd": str(root),
                    "sessionId": session_id,
                    "tool": "read",
                    "input": tool_input,
                }, env=environment(root, "pi"))
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            canonical = bridge_read("canonical-read", {"file_path": str(target)})
            native = bridge_read("native-read", {"path": str(target)})

            self.assertEqual(canonical["outcome"], "notice", canonical)
            self.assertIn("ADR-0015", canonical.get("context", ""))
            self.assertEqual(native["outcome"], "notice", native)
            self.assertEqual(native.get("context"), canonical["context"])

    def test_transport_failure_corpus_is_pinned_in_bridge_tests(self):
        source = (REPO / "plugins" / "ca-pi" / "tools" / "test" / "bridge.test.ts").read_text(encoding="utf-8")
        for required in ("malformed protocol", "bridge failure", "overflowing protocol", "hung bridge", "outside the installed package"):
            self.assertIn(required, source)

    def test_pi_adapter_contains_no_h_rule_implementation(self):
        text = "\n".join((HOOKS["pi"] / name).read_text(encoding="utf-8") for name in ("_host.py", "pi-bridge.py"))
        self.assertIsNone(re.search(r"H-\d{2}[a-z]?", text))


if __name__ == "__main__":
    if "--fixtures-only" in sys.argv:
        sys.argv.remove("--fixtures-only")
    unittest.main()
