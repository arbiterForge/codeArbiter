#!/usr/bin/env python3
"""Dual-host shared-store contract tests for ADR-0011 and ADR-0012."""

import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CA_HOOKS = REPO / "plugins" / "ca" / "hooks"
CODEX_HOOKS = REPO / "plugins" / "ca-codex" / "hooks"


def run_hook(hooks: Path, script: str, payload: dict, cwd: Path,
             claude_env: bool) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if claude_env:
        env["CLAUDE_PROJECT_DIR"] = str(cwd)
    else:
        env.pop("CLAUDE_PROJECT_DIR", None)
    return subprocess.run(
        [sys.executable, str(hooks / script)], input=json.dumps(payload),
        cwd=cwd, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60)


class DualHostStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _init(self, hooks: Path, *args: str):
        return subprocess.run(
            [sys.executable, str(hooks / "init-codearbiter.py"),
             "--root", str(self.root), *args], cwd=self.root,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60)

    def test_second_host_observes_one_store_without_reinitializing_it(self):
        first = self._init(CODEX_HOOKS)
        self.assertEqual(first.returncode, 0, first.stderr)
        store = self.root / ".codearbiter"
        self.assertTrue(store.is_dir())
        before = {p.relative_to(store): p.read_bytes()
                  for p in store.rglob("*") if p.is_file()}

        second = self._init(CA_HOOKS, "--check")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("ALREADY SCAFFOLDED", second.stdout)
        after = {p.relative_to(store): p.read_bytes()
                 for p in store.rglob("*") if p.is_file()}
        self.assertEqual(after, before)
        self.assertEqual(len(list(self.root.glob(".codearbiter"))), 1)

    def test_concurrent_block_events_append_once_with_host_attribution(self):
        initialized = self._init(CODEX_HOOKS)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        log = self.root / ".codearbiter" / "gate-events.log"
        log.unlink(missing_ok=True)
        payload = {
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "cwd": str(self.root),
            "tool_input": {"command": 'git commit --no-verify -m "x"'},
        }
        jobs = [(CA_HOOKS, True)] * 12 + [(CODEX_HOOKS, False)] * 12
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda job: run_hook(job[0], "pre-bash.py", payload,
                                     self.root, job[1]), jobs))

        self.assertTrue(all(result.returncode == 2 for result in results))
        self.assertTrue(all("H-20" in result.stderr for result in results))
        lines = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), len(jobs))
        self.assertEqual(sum("host=claude" in line for line in lines), 12)
        self.assertEqual(sum("host=codex" in line for line in lines), 12)
        self.assertTrue(all("BLOCK [H-20]" in line for line in lines))


if __name__ == "__main__":
    unittest.main(verbosity=2)
