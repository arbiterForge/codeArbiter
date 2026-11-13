#!/usr/bin/env python3
"""Installed host event seams, bounded notices, and independent presentation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

import test_workflow_recovery_cli as fixtures


class RecoveryHostTest(fixtures.InstalledRecoveryFixture, unittest.TestCase):
    def store_snapshot(self):
        root = self.root / ".git/codearbiter/workflow-recovery/v1"
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def register(self, number=0):
        result, value = self.cli("claude", "register", {"candidates": [self.offer(number)]})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return value["items"][0]["obligation_id"]

    def script(self, host, filename, payload, *, startup=False, timeout=30):
        package = self.hosts[host]
        if startup:
            # Only unrelated background fetch/update launchers are doubled.
            # Real JSON stdin, host adapter, startup, Git install, bounded
            # recovery child and stdout presentation remain exercised.
            source = ("import sys,importlib.util;sys.path.insert(0,sys.argv[1]);import hostapi;"
                      "s=importlib.util.spec_from_file_location('recovery_startup',sys.argv[2]);"
                      "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                      "m.spawn_background_fetch=lambda *a,**k:None;"
                      "m.spawn_background_update_refresh=lambda *a,**k:None;"
                      "m.run(hostapi.load_host())")
            argv = [sys.executable, "-B", "-c", source, str(package / "hooks"), str(package / "hooks" / filename)]
        else:
            argv = [sys.executable, "-B", str(package / "hooks" / filename)]
        return subprocess.run(argv, input=json.dumps(payload), text=True, encoding="utf-8", capture_output=True,
                              cwd=self.root, env=self.environment(host), timeout=timeout)

    def test_real_startup_prompt_and_compaction_keep_notice_separate_from_persona(self):
        self.register()
        baseline = self.store_snapshot()
        for index, host in enumerate(("claude", "codex")):
            with self.subTest(host=host):
                session = "notice-session-" + host
                payload = {"hook_event_name": "SessionStart", "cwd": str(self.root), "session_id": session}
                started = time.monotonic()
                first = self.script(host, "session-start.py", payload, startup=True)
                elapsed = time.monotonic() - started
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertIn(f"workflow recovery page: {index + 1} pending", first.stdout)
                self.assertLess(elapsed, 60)  # Actual Codex startup hook budget.
                repeated = self.script(host, "session-start.py", payload, startup=True)
                self.assertEqual(repeated.returncode, 0, repeated.stderr)
                self.assertNotIn("workflow recovery page:", repeated.stdout)
                prompt = {"hook_event_name": "UserPromptSubmit", "cwd": str(self.root), "session_id": session, "prompt": "continue"}
                first_prompt = self.script(host, "prompt-submit.py", prompt)
                self.assertEqual(first_prompt.returncode, 0, first_prompt.stderr)
                self.assertNotIn("codeArbiter: workflow recovery page:", first_prompt.stdout)
                self.register(1 if host == "claude" else 2)
                changed = self.script(host, "prompt-submit.py", prompt)
                self.assertEqual(changed.returncode, 0, changed.stderr)
                self.assertIn("codeArbiter: workflow recovery page:", changed.stdout)
                if host == "codex":
                    self.assertIn("workflow recovery page:", json.loads(changed.stdout)["hookSpecificOutput"]["additionalContext"])
                compact = dict(prompt, hook_event_name="PreCompact")
                self.assertEqual(self.script(host, "prompt-submit.py", compact).returncode, 0)
                after_compact = self.script(host, "prompt-submit.py", prompt)
                self.assertEqual(after_compact.returncode, 0, after_compact.stderr)
                self.assertNotIn("codeArbiter: workflow recovery page:", after_compact.stdout)
        # Registration above is the only ledger writer. Presentation never
        # marks any record settled or calls a work target.
        _, observed = self.cli("pi", "scan")
        self.assertEqual({item["state"] for item in observed["items"]}, {"pending"})
        self.assertEqual((self.root / ".codearbiter/open-tasks.md").read_text(), "# Tasks\n\n## Backlog\n")
        self.assertTrue(set(baseline).issubset(self.store_snapshot()))
        after = self.store_snapshot()
        for path, raw in baseline.items():
            if path != "index.json" and not path.startswith("pages/"):
                self.assertEqual(after[path], raw)

    def test_codex_pretool_context_does_not_synthesize_allow_or_change_block(self):
        self.register()
        before = self.store_snapshot()
        allowed = {"hook_event_name": "PreToolUse", "tool_name": "exec_command", "cwd": str(self.root),
                   "session_id": "allowed-notice", "tool_input": {"command": "git status --short"}}
        observed = self.script("codex", "pre-tool-adapter.py", allowed)
        self.assertEqual(observed.returncode, 0, observed.stderr)
        body = json.loads(observed.stdout)
        self.assertNotIn("decision", body)
        self.assertNotIn("permissionDecision", body["hookSpecificOutput"])
        self.assertIn("workflow recovery page:", body["hookSpecificOutput"]["additionalContext"])
        blocked = dict(allowed, session_id="blocked-notice", tool_input={"command": "git commit -m blocked-probe"})
        rejected = self.script("codex", "pre-tool-adapter.py", blocked)
        self.assertEqual(rejected.returncode, 0, rejected.stderr)
        body = json.loads(rejected.stdout)
        self.assertEqual(body["decision"], "block")
        self.assertNotIn("hookSpecificOutput", body)
        self.assertEqual(before, self.store_snapshot())

    def test_pi_closed_snapshot_codec_reads_pending_state_without_any_effect(self):
        oid = self.register()
        before = self.store_snapshot()
        request = {"version": 1, "event": "workflow_recovery_snapshot", "cwd": str(self.root), "sessionId": "new-parent-session"}
        result = self.script("pi", "pi-bridge.py", request)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["auditCode"], "PI_WORKFLOW_RECOVERY")
        snapshot = value["resultPatch"]["workflowRecovery"]
        self.assertEqual(set(snapshot), {"status", "revision", "pending", "claimed", "unavailable", "cursor",
                                         "bytesRead", "reason", "notice", "fingerprint"})
        self.assertEqual(snapshot["pending"], 1)
        self.assertEqual(snapshot["claimed"], 0)
        self.assertEqual(snapshot["status"], "complete")
        self.assertNotIn("grant", snapshot)
        self.assertNotIn(oid, snapshot["notice"])
        self.assertEqual(before, self.store_snapshot())

    def test_dormant_snapshot_and_missing_ledger_create_no_state(self):
        for dormant in (False, True):
            if dormant:
                (self.root / ".codearbiter/CONTEXT.md").write_text("---\narbiter: disabled\n---\n")
            request = {"version": 1, "event": "workflow_recovery_snapshot", "cwd": str(self.root)}
            result = self.script("pi", "pi-bridge.py", request)
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshot = json.loads(result.stdout)["resultPatch"]["workflowRecovery"]
            self.assertEqual(snapshot["status"], "absent")
            self.assertEqual(snapshot["notice"], "")
            self.assertFalse((self.root / ".git/codearbiter/workflow-recovery").exists())
            self.assertFalse((self.root / ".codearbiter/.markers").exists())

    def test_corrupt_inventory_notice_never_repairs_or_blocks_real_host_entry(self):
        self.register()
        index = self.root / ".git/codearbiter/workflow-recovery/v1/index.json"
        index.write_bytes(b"not valid JSON\n")
        before = self.store_snapshot()
        for host in ("claude", "codex"):
            result = self.script(host, "session-start.py", {"hook_event_name": "SessionStart", "cwd": str(self.root),
                                                            "session_id": "damaged-" + host}, startup=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("workflow recovery inventory unavailable", result.stdout)
            self.assertIn("Independent authorized work continues", result.stdout)
        result = self.script("pi", "pi-bridge.py", {"version": 1, "event": "workflow_recovery_snapshot", "cwd": str(self.root)})
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)["resultPatch"]["workflowRecovery"]
        self.assertEqual(value["status"], "unavailable")
        self.assertIn("Independent authorized work continues", value["notice"])
        self.assertEqual(before, self.store_snapshot())


if __name__ == "__main__":
    unittest.main()
