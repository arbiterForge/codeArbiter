#!/usr/bin/env python3
"""Three-host shared append-store attribution proof for ADR-0012."""

import collections
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
HOOKS = {
    "claude": REPO / "plugins" / "ca" / "hooks",
    "codex": REPO / "plugins" / "ca-codex" / "hooks",
    "pi": REPO / "plugins" / "ca-pi" / "hooks",
}
EVENT = re.compile(r"^\[[^\]]+\] BLOCK \[H-20\] host=(claude|codex|pi) hook=pre-bash\.py \|")


def run_hook(host: str, payload: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if host == "claude":
        env["CLAUDE_PROJECT_DIR"] = str(cwd)
    else:
        env.pop("CLAUDE_PROJECT_DIR", None)
    return subprocess.run(
        [sys.executable, str(HOOKS[host] / "pre-bash.py")],
        input=json.dumps(payload), cwd=cwd, env=env, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=60,
    )


class PiSharedStoreTest(unittest.TestCase):
    def _exercise_pair(self, left: str, right: str) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            initialized = subprocess.run(
                [sys.executable, str(HOOKS["codex"] / "init-codearbiter.py"), "--root", str(root)],
                cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            log = root / ".codearbiter" / "gate-events.log"
            log.unlink(missing_ok=True)
            payload = {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "cwd": str(root),
                "tool_input": {"command": 'git commit --no-verify -m "shared-store"'},
            }
            jobs = [left] * 24 + [right] * 24
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
                results = list(pool.map(lambda host: run_hook(host, payload, root), jobs))

            self.assertTrue(all(result.returncode == 2 for result in results))
            self.assertTrue(all("H-20" in result.stderr for result in results))
            lines = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), len(jobs))
            parsed = [EVENT.match(line) for line in lines]
            self.assertTrue(all(match is not None for match in parsed), "every append must be parseable and attributed")
            counts = collections.Counter(match.group(1) for match in parsed if match is not None)
            expected = collections.Counter({left: 24, right: 24})
            if left == right:
                expected = collections.Counter({left: 48})
            self.assertEqual(counts, expected)

    def test_claude_pi_concurrent_appends_are_attributed(self):
        self._exercise_pair("claude", "pi")

    def test_codex_pi_concurrent_appends_are_attributed(self):
        self._exercise_pair("codex", "pi")

    def test_pi_pi_concurrent_appends_match_the_same_host_baseline(self):
        self._exercise_pair("pi", "pi")


if __name__ == "__main__":
    unittest.main(verbosity=2)
