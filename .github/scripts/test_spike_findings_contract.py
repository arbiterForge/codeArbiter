#!/usr/bin/env python3
"""The disposable-spike exit must preserve only findings on the parent branch."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SURFACES = (
    "core/surface/commands/spike.md",
    "plugins/ca/commands/spike.md",
    "plugins/ca-codex/skills/ca-spike/SKILL.md",
    "plugins/ca-pi/skills/ca-spike/SKILL.md",
)


class SpikeFindingsContractTests(unittest.TestCase):
    def test_every_host_preserves_only_a_committed_findings_file(self) -> None:
        for relative in SURFACES:
            with self.subTest(surface=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                normalized = " ".join(text.split())
                commit = normalized.index("commit only that findings file")
                restore = normalized.index("git restore --source spike/<slug>")
                parent_commit = normalized.index("commit that one file through")
                deletion = normalized.casefold().index("then delete the spike branch")
                prohibition = normalized.index("Do not transfer spike code")
                self.assertLess(commit, restore)
                self.assertLess(restore, parent_commit)
                self.assertLess(parent_commit, deletion)
                self.assertLess(deletion, prohibition)


if __name__ == "__main__":
    unittest.main()
