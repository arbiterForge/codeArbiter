#!/usr/bin/env python3
"""Task 8 generated internal-charter and host-neutral prune prose checks."""

import json
import os
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class PiCompactionSurfaceTests(unittest.TestCase):
    def test_internal_compaction_charter_is_generated_but_not_a_public_role(self):
        source = os.path.join(ROOT, "core", "surface", "includes", "compaction-charter.md")
        rendered = os.path.join(ROOT, "plugins", "ca-pi", "includes", "compaction-charter.md")
        with open(source, encoding="utf-8") as handle:
            source_text = handle.read()
        with open(rendered, encoding="utf-8") as handle:
            rendered_text = handle.read()
        self.assertEqual(rendered_text, source_text.replace("{{PLUGIN_ROOT}}", "<plugin-root>"))
        with open(os.path.join(ROOT, "plugins", "ca-pi", "generated", "roles.json"), encoding="utf-8") as handle:
            roles = json.load(handle)
        self.assertEqual(len(roles), 28)
        self.assertNotIn("compaction", {role["name"] for role in roles})

    def test_pi_prune_guidance_is_native_and_contains_no_claude_resume_contract(self):
        path = os.path.join(ROOT, "plugins", "ca-pi", "skills", "ca-prune", "SKILL.md")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn("claude --resume", text.lower())
        self.assertIn("Pi-native compaction", text)
        self.assertIn("active session", text)
        self.assertIn("inactive", text)


if __name__ == "__main__":
    unittest.main()
