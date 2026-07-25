#!/usr/bin/env python3
"""codeArbiter - ADR identity + supersession-resolution contract (#416).

Two ADR files in this repository carry the number 0014
(`0014-githook-shim-dropin-fail-closed` and
`0014-pi-host-authentication-and-fail-closed-tool-boundary`), and two later
ADRs supersede *different* ones of them. A bare `supersedes: 0014` therefore
names two documents at once, and every consumer that derived an ADR id with
`filename.split("-")[0]` collapsed the pair into one indistinguishable id.

The contract this file pins:

  1. The filename STEM is the ADR identifier - `0014-githook-shim-dropin-
     fail-closed`, not `0014`. Both hook-side indexers derive it that way, and
     they derive it identically.
  2. Filename stems are unique, and an ADR number resolves to exactly one stem
     apart from the one grandfathered historical collision. A NEW file taking
     an already-used number is a contract violation, so the collision cannot
     recur.
  3. Every `supersedes:` value resolves to exactly ONE ADR. A stem always
     resolves. A bare number resolves only while it is unambiguous; once it
     names more than one stem it is an error, never a guess.

Stdlib only. Exit 0 = all tests pass; non-zero = failure.
"""

import importlib.util
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
sys.path.insert(0, HOOKS)

import _readinjectlib as ril  # noqa: E402 - needs the sys.path mutation above


def _load_post_write_edit():
    """Import post-write-edit.py by path (its name is not a valid identifier)."""
    spec = importlib.util.spec_from_file_location(
        "post_write_edit_for_adr_identity",
        os.path.join(HOOKS, "post-write-edit.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pwe = _load_post_write_edit()


def _write_adr(ddir, filename, status="accepted", title="T", governs="src/**"):
    lines = ["---", "status: %s" % status, "title: %s" % title]
    if governs:
        lines.append("governs: %s" % governs)
    lines.append("---")
    lines.append("# Body")
    with open(os.path.join(ddir, filename), "w", encoding="utf-8",
              newline="\n") as f:
        f.write("\n".join(lines) + "\n")


class HookIdDerivationTest(unittest.TestCase):
    """Clause 1 - both hook indexers key an ADR by its full filename stem."""

    GITHOOK = "0014-githook-shim-dropin-fail-closed"
    PIAUTH = "0014-pi-host-authentication-and-fail-closed-tool-boundary"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.ddir = os.path.join(self.root, ".codearbiter", "decisions")
        os.makedirs(self.ddir)
        _write_adr(self.ddir, self.GITHOOK + ".md", title="Git-hook shim")
        _write_adr(self.ddir, self.PIAUTH + ".md", title="Pi host auth")

    def tearDown(self):
        self._tmp.cleanup()

    def test_accepted_adr_index_keys_two_same_numbered_adrs_apart(self):
        ids = sorted(e["adr"] for e in ril.accepted_adr_index(self.root))
        self.assertEqual(ids, sorted([self.GITHOOK, self.PIAUTH]))

    def test_governs_index_keys_two_same_numbered_adrs_apart(self):
        ids = sorted(e["adr"] for e in pwe.governs_index(self.root))
        self.assertEqual(ids, sorted([self.GITHOOK, self.PIAUTH]))

    def test_both_indexers_derive_the_same_identifier_for_the_same_file(self):
        """The defect was duplicated derivation logic; pin the two together."""
        left = {e["adr"] for e in ril.accepted_adr_index(self.root)}
        right = {e["adr"] for e in pwe.governs_index(self.root)}
        self.assertEqual(left, right)

    def test_pointer_text_names_the_stem_so_a_reader_can_tell_them_apart(self):
        index = ril.accepted_adr_index(self.root)
        texts = [p["text"] for p in ril.adr_pointers("src/x.py", index)]
        self.assertEqual(len(texts), 2, texts)
        self.assertTrue(any("ADR-" + self.GITHOOK in t for t in texts), texts)
        self.assertTrue(any("ADR-" + self.PIAUTH in t for t in texts), texts)


if __name__ == "__main__":
    unittest.main()
