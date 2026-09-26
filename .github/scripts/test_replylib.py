#!/usr/bin/env python3
"""Contracts for forgiving, low-friction authority reply capture (_replylib).

Canonicalization tolerates what hosts and keyboards add around a reply
(spacing, invisible characters, code formatting, quotes, a closing period)
but never accepts a reply embedded in other text, never changes a long
token's case, and leaves every non-reply prompt byte-for-byte unchanged.
Short codes expand to the exact armed reply, so downstream hashes and the
engine see nothing new.
"""

import importlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "core" / "pysrc"))

TOKEN = "fixtureReplyValue" + "0" * 15  # not a credential; replies are non-secret
FULL = f"approve SPEC-PI-AUTHORITY-ADAPTER {TOKEN}"


class CanonicalizeTest(unittest.TestCase):
    def setUp(self):
        self.lib = importlib.import_module("_replylib")

    def test_accepts_what_hosts_and_keyboards_add(self):
        cases = {
            "leading spaces": "  " + FULL,
            "trailing newline": FULL + "\n",
            "crlf": FULL + "\r\n",
            "tab separator": FULL.replace(" ", "\t", 1),
            "doubled spaces": FULL.replace(" ", "  "),
            "nbsp": FULL.replace(" ", " "),
            "zero width space": "​" + FULL,
            "zero width joiner inside": FULL.replace("SPEC", "SP‍EC"),
            "bom": "﻿" + FULL,
            "word joiner": FULL + "⁠",
            "soft hyphen": FULL.replace("PI", "P­I"),
            "single backticks": f"`{FULL}`",
            "fence": f"```\n{FULL}\n```",
            "fence with language": f"```text\n{FULL}\n```",
            "straight quotes": f'"{FULL}"',
            "smart quotes": f"“{FULL}”",
            "smart single quotes": f"‘{FULL}’",
            "trailing period": FULL + ".",
            "trailing bang": FULL + "!",
            "capitalized verb": FULL.replace("approve", "Approve"),
            "upper verb": FULL.replace("approve", "APPROVE"),
            "lowercase id": FULL.replace("SPEC-PI-AUTHORITY-ADAPTER", "spec-pi-authority-adapter"),
            "en dash in id": FULL.replace("SPEC-PI", "SPEC–PI"),
            "fullwidth verb": FULL.replace("approve", "ａｐｐｒｏｖｅ"),
        }
        for label, raw in cases.items():
            with self.subTest(label):
                self.assertEqual(self.lib.canonicalize(raw), FULL)

    def test_dash_substitution_inside_an_old_token_is_repaired(self):
        old = "approve SPEC-X ab-cd_efGHijklmnop"
        self.assertEqual(self.lib.canonicalize(old.replace("b-c", "b‑c")), old)
        self.assertEqual(self.lib.canonicalize(old.replace("b-c", "b−c")), old)

    def test_long_token_case_is_never_changed(self):
        self.assertEqual(self.lib.canonicalize(FULL.upper()).split(" ")[-1], TOKEN.upper())
        self.assertNotEqual(self.lib.canonicalize(FULL.upper()), FULL)

    def test_short_codes_are_case_insensitive_and_named_ids_uppercased(self):
        self.assertEqual(self.lib.canonicalize("  approve k7mq. "), "approve K7MQ")
        self.assertEqual(self.lib.canonicalize("approve spec-x k7mq"), "approve SPEC-X K7MQ")
        self.assertEqual(self.lib.canonicalize("Approve-Sprint Delegate k7mq"), "approve-sprint delegate K7MQ")
        self.assertEqual(self.lib.canonicalize("approve-sprint delegate-methods K7MQ"),
                         "approve-sprint delegate K7MQ")
        self.assertEqual(self.lib.canonicalize("satisfy-prerequisite k7mq"), "satisfy-prerequisite K7MQ")
        self.assertEqual(self.lib.canonicalize("reconcile pending k7mq"), "reconcile PENDING K7MQ")

    def test_embedded_or_extended_replies_are_not_repaired_into_a_match(self):
        for raw in (FULL + "?", FULL + ", please", FULL + "\nmore", "don't " + FULL,
                    "looks good, " + FULL, FULL + " " + FULL):
            with self.subTest(raw=raw):
                self.assertNotEqual(self.lib.canonicalize(raw), FULL)

    def test_cyrillic_lookalike_id_stays_distinct(self):
        self.assertNotEqual(self.lib.canonicalize(FULL.replace("SPEC", "СPEC")), FULL)

    def test_non_reply_prompts_are_returned_unchanged(self):
        for raw in ("  please continue\n", "yes", "`approve`", "hello world", "/ca:mode dangerous", ""):
            with self.subTest(raw=raw):
                self.assertIs(self.lib.canonicalize(raw), raw)

    def test_near_miss_detection_needs_a_leading_reply_verb(self):
        for raw in ("`approve`", FULL + ", please", "  Approve k7mq extra", "reconcile"):
            with self.subTest(raw=raw):
                self.assertTrue(self.lib.looks_like_reply(raw))
        for raw in ("please approve", "don't approve SPEC-X", "yes", ""):
            with self.subTest(raw=raw):
                self.assertFalse(self.lib.looks_like_reply(raw))

    def test_idempotent(self):
        for raw in ("  " + FULL, f"```text\n{FULL}\n```", "approve k7mq.", "reconcile pending k7mq"):
            with self.subTest(raw=raw):
                once = self.lib.canonicalize(raw)
                self.assertEqual(self.lib.canonicalize(once), once)

    def test_oversized_input_is_not_rewritten(self):
        raw = "approve " + "x" * 5000
        self.assertIs(self.lib.canonicalize(raw), raw)

    def test_describe_never_returns_the_whole_prompt(self):
        raw = "approve K7MQ ​" + "secret-looking-text " * 40
        text = self.lib.describe(raw)
        self.assertLessEqual(len(text), 1200)
        self.assertIn("U+200B", text)
        self.assertNotIn("secret-looking-text " * 12, text)


class ShortCodeTest(unittest.TestCase):
    def setUp(self):
        self.lib = importlib.import_module("_replylib")
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.original = self.lib.REGISTRY_PARENT
        self.lib.REGISTRY_PARENT = self.base
        self.repo = self.base / "repo"
        (self.repo / ".codearbiter").mkdir(parents=True)

    def tearDown(self):
        self.lib.REGISTRY_PARENT = self.original
        self.temp.cleanup()

    def issue(self, route="approval", artifact="SPEC-X", full=None, names=("SPEC-X",), short=("approve",)):
        return self.lib.issue_code(self.repo, route, artifact, full or f"approve SPEC-X {TOKEN}",
                                   names=list(names), short_prefix=list(short))

    def test_issued_code_uses_the_unambiguous_alphabet(self):
        issued = self.issue()
        code = issued["code"]
        self.assertRegex(code, r"^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$")
        self.assertEqual(issued["short_reply"], f"approve {code}")

    def test_short_reply_expands_to_the_exact_full_reply(self):
        issued = self.issue()
        result = self.lib.expand(issued["short_reply"])
        self.assertEqual(result, {"text": f"approve SPEC-X {TOKEN}", "notice": ""})
        padded = self.lib.expand(self.lib.canonicalize(f"  Approve {issued['code'].lower()}."))
        self.assertEqual(padded["text"], f"approve SPEC-X {TOKEN}")

    def test_named_id_must_match_the_armed_artifact(self):
        code = self.issue()["code"]
        self.assertEqual(self.lib.expand(f"approve SPEC-X {code}")["text"], f"approve SPEC-X {TOKEN}")
        wrong = self.lib.expand(f"approve SPEC-Y {code}")
        self.assertEqual(wrong["text"], f"approve SPEC-Y {code}")
        self.assertIn("SPEC-X", wrong["notice"])

    def test_unknown_or_expired_codes_are_reported_not_silent(self):
        unknown = self.lib.expand("approve ZZZZ")
        self.assertEqual(unknown["text"], "approve ZZZZ")
        self.assertIn("no armed request", unknown["notice"])
        issued = self.issue()
        entry = next(self.lib._registry().glob("*.json"))
        value = json.loads(entry.read_text(encoding="utf-8"))
        value["expires_at"] = int(time.time()) - 1
        unsigned = {k: v for k, v in value.items() if k != "integrity_sha256"}
        value["integrity_sha256"] = self.lib._digest(self.lib._canonical(unsigned))
        entry.write_text(json.dumps(value), encoding="utf-8")
        expired = self.lib.expand(issued["short_reply"])
        self.assertEqual(expired["text"], issued["short_reply"])
        self.assertIn("expired", expired["notice"])

    def test_tampered_entry_never_expands(self):
        issued = self.issue()
        entry = next(self.lib._registry().glob("*.json"))
        value = json.loads(entry.read_text(encoding="utf-8"))
        value["full_reply"] = "approve SPEC-EVIL " + TOKEN
        entry.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(self.lib.expand(issued["short_reply"])["text"], issued["short_reply"])

    def test_rearm_replaces_the_code_and_retire_removes_it(self):
        first = self.issue()
        second = self.issue(full=f"approve SPEC-X {'z' * 32}")
        self.assertEqual(self.lib.expand(second["short_reply"])["text"], f"approve SPEC-X {'z' * 32}")
        if first["code"] != second["code"]:
            self.assertIn("no armed request", self.lib.expand(first["short_reply"])["notice"])
        self.lib.retire_code(self.repo, "approval", "SPEC-X")
        self.assertIn("no armed request", self.lib.expand(second["short_reply"])["notice"])

    def test_codes_never_collide_with_another_live_request(self):
        other = self.base / "other"
        (other / ".codearbiter").mkdir(parents=True)
        draws = iter("AAAA" "AAAA" "BBBB")
        with mock.patch.object(self.lib.secrets, "choice", side_effect=lambda _alphabet: next(draws)):
            first = self.lib.issue_code(self.repo, "approval", "SPEC-1", f"approve SPEC-1 {TOKEN}",
                                        names=["SPEC-1"], short_prefix=["approve"])
            second = self.lib.issue_code(other, "approval", "SPEC-2", f"approve SPEC-2 {TOKEN}",
                                         names=["SPEC-2"], short_prefix=["approve"])
        self.assertEqual(first["code"], "AAAA")
        self.assertEqual(second["code"], "BBBB")
        self.assertEqual(self.lib.expand("approve AAAA")["text"], f"approve SPEC-1 {TOKEN}")
        self.assertEqual(self.lib.expand("approve BBBB")["text"], f"approve SPEC-2 {TOKEN}")

    def test_sprint_short_form_restates_the_armed_mode(self):
        full = f"approve-sprint SPEC-X PLAN-X delegate-methods {TOKEN}"
        issued = self.lib.issue_code(self.repo, "approval", "PLAN-X", full, names=["SPEC-X", "PLAN-X"],
                                     short_prefix=["approve-sprint", "delegate"])
        self.assertEqual(issued["short_reply"], f"approve-sprint delegate {issued['code']}")
        self.assertEqual(self.lib.expand(issued["short_reply"])["text"], full)
        wrong_mode = self.lib.expand(f"approve-sprint approve-only {issued['code']}")
        self.assertNotEqual(wrong_mode["text"], full)
        self.assertIn("delegate", wrong_mode["notice"])

    def test_non_short_text_passes_through_silently(self):
        self.assertEqual(self.lib.expand(FULL), {"text": FULL, "notice": ""})
        self.assertEqual(self.lib.expand("please continue"), {"text": "please continue", "notice": ""})


if __name__ == "__main__":
    unittest.main()
