#!/usr/bin/env python3
"""Contract tests for npm_audit_gate.py (the lockfile-bound accepted-advisory gate)."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE_EXCEPTIONS = REPO_ROOT / "site" / "audit-exceptions.json"
TODAY = date(2026, 10, 3)
GHSA_ID = "GHSA-ch52-4w7c-c8xp"
LOCK_BYTES = b'{"lockfileVersion":3}\n'
LOCK_DIGEST = hashlib.sha256(LOCK_BYTES).hexdigest()


def load_gate():
    spec = importlib.util.spec_from_file_location("npm_audit_gate", REPO_ROOT / ".github" / "scripts" / "npm_audit_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exception(**overrides):
    record = {
        "ghsa": GHSA_ID, "package": "http-cache-semantics", "severity": "high",
        "reason": "No patched release; reached only at static-site build time.",
        "approved_by": "maintainer@example.invalid",
        "approved_on": TODAY.isoformat(), "backstop": (TODAY + timedelta(days=14)).isoformat(),
        "lockfiles": {"site/package-lock.json": LOCK_DIGEST},
    }
    record.update(overrides)
    return record


def report(*advisories, extra=None):
    vulnerabilities = {}
    for ghsa, package, severity in advisories:
        entry = vulnerabilities.setdefault(package, {"name": package, "severity": severity, "via": []})
        entry["via"].append({"source": 1, "name": package, "dependency": package, "severity": severity,
                             "url": f"https://github.com/advisories/{ghsa}", "range": "<=4.2.0"})
    # A dependent reached only through the advisory above: judged at its root.
    if advisories:
        vulnerabilities["astro"] = {"name": "astro", "severity": advisories[0][2], "via": [advisories[0][1]]}
    vulnerabilities.update(extra or {})
    counts = {severity: 0 for severity in ("info", "low", "moderate", "high", "critical")}
    for entry in vulnerabilities.values():
        counts[entry["severity"]] += 1
    counts["total"] = len(vulnerabilities)
    return json.dumps({"auditReportVersion": 2, "vulnerabilities": vulnerabilities,
                       "metadata": {"vulnerabilities": counts}})


class NpmAuditGateTest(unittest.TestCase):
    def run_gate(self, records, report_text, level="high", today=TODAY, raw=None, *,
                 graph="site", scope="production", lock_bytes=LOCK_BYTES):
        gate = load_gate()
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            cwd = repo / graph
            cwd.mkdir(parents=True)
            (cwd / "package-lock.json").write_bytes(lock_bytes)
            path = repo / "exceptions.json"
            path.write_text(raw if raw is not None else json.dumps(
                {"schema": gate.SCHEMA, "exceptions": records}), encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
                code = gate.main(["--exceptions", str(path), "--scope", scope, f"--audit-level={level}"],
                                 stdin=report_text, today=today, repo=repo, cwd=cwd)
        return code, stderr.getvalue()

    def test_accepted_advisory_passes_and_dependents_are_judged_at_the_root(self):
        code, _ = self.run_gate([exception()], report((GHSA_ID, "http-cache-semantics", "high")))
        self.assertEqual(code, 0)

    def test_acceptance_is_keyed_by_the_recorded_package(self):
        code, _ = self.run_gate([exception(package="cacache")], report((GHSA_ID, "cacache", "high")))
        self.assertEqual(code, 0)

    def test_exact_graph_bytes_and_scope_are_required(self):
        finding = report((GHSA_ID, "http-cache-semantics", "high"))
        tool = "plugins/ca/tools"
        record = exception(lockfiles={f"{tool}/package-lock.json": LOCK_DIGEST})
        for graph, scope, lock_bytes, expected in (
            (tool, "full", LOCK_BYTES, 0),
            (tool, "production", LOCK_BYTES, 1),
            (tool, "full", LOCK_BYTES + b" ", 1),
            ("plugins/ca-pi/tools", "full", LOCK_BYTES, 1),
            ("site", "production", LOCK_BYTES, 1),
        ):
            with self.subTest(graph=graph, scope=scope, expected=expected):
                code, _ = self.run_gate([record], finding, graph=graph, scope=scope,
                                        lock_bytes=lock_bytes)
                self.assertEqual(code, expected)

    def test_advisory_url_has_to_match_the_canonical_identity(self):
        finding = report((GHSA_ID, "http-cache-semantics", "high"))
        for alternate in ("https://lookalike.invalid/advisories/", "https://github.com/issues/"):
            with self.subTest(alternate=alternate):
                code, _ = self.run_gate([exception()], finding.replace(
                    "https://github.com/advisories/", alternate))
                self.assertEqual(code, 1)

    def test_clean_report_passes_and_an_unused_exception_is_only_noted(self):
        code, stderr = self.run_gate([exception()], report())
        self.assertEqual(code, 0)
        self.assertIn("matches no finding", stderr)

    def test_unaccepted_findings_at_or_above_the_threshold_fail(self):
        cases = {
            "nothing-accepted": ([], report((GHSA_ID, "http-cache-semantics", "high"))),
            "other-high": ([exception()], report((GHSA_ID, "http-cache-semantics", "high"),
                                                 ("GHSA-2222-3333-4444", "devalue", "high"))),
            "critical": ([exception()], report(("GHSA-2222-3333-4444", "devalue", "critical"))),
            "same-ghsa-other-package": ([exception()], report((GHSA_ID, "cacache", "high"))),
            "severity-escalated": ([exception()], report((GHSA_ID, "http-cache-semantics", "critical"))),
        }
        for label, (records, text) in cases.items():
            with self.subTest(label=label):
                code, stderr = self.run_gate(records, text)
                self.assertEqual(code, 1)
                self.assertIn("unaccepted", stderr)

    def test_findings_below_the_threshold_do_not_fail(self):
        code, _ = self.run_gate([], report(("GHSA-2222-3333-4444", "devalue", "moderate")))
        self.assertEqual(code, 0)
        code, _ = self.run_gate([], report(("GHSA-2222-3333-4444", "devalue", "moderate")), level="moderate")
        self.assertEqual(code, 1)

    def test_untrusted_reports_fail_closed(self):
        for label, text in {
            "empty": "",
            "not-json": "npm ERR! network",
            "npm-error-object": json.dumps({"error": {"code": "ENOAUDIT"}}),
            "error-with-empty-inventory": json.dumps({"error": {"code": "ENOAUDIT"}, "vulnerabilities": {}}),
            "no-inventory": json.dumps({"auditReportVersion": 2}),
            "malformed-entry": json.dumps({"vulnerabilities": {"x": {"via": "nope"}}}),
            "malformed-advisory": json.dumps({"vulnerabilities": {"x": {"via": [{"name": "x", "severity": "high"}]}}}),
            "unknown-severity": json.dumps({"vulnerabilities": {"x": {"via": [
                {"name": "x", "severity": "urgent", "url": f"https://github.com/advisories/{GHSA_ID}"}]}}}),
        }.items():
            with self.subTest(label=label):
                code, _ = self.run_gate([exception()], text)
                self.assertEqual(code, 1)

    def test_report_metadata_and_indirect_findings_are_checked(self):
        finding = report((GHSA_ID, "http-cache-semantics", "high"))
        initial = json.loads(finding)
        invalid = [
            {**initial, "auditReportVersion": 1},
            {**initial, "metadata": {}},
            {**initial, "vulnerabilities": {}},
        ]
        for via in ([], ["missing"], ["astro"]):
            invalid.append({**initial, "vulnerabilities": {
                **initial["vulnerabilities"], "astro": {
                    **initial["vulnerabilities"]["astro"], "via": via,
                },
            }})
        for document in invalid:
            with self.subTest(document=document):
                code, _ = self.run_gate([exception()], json.dumps(document))
                self.assertEqual(code, 1)

    def test_exceptions_fail_closed(self):
        finding = report((GHSA_ID, "http-cache-semantics", "high"))
        cases = {
            "expired": [exception(approved_on=(TODAY - timedelta(days=20)).isoformat(),
                                  backstop=(TODAY - timedelta(days=1)).isoformat())],
            "backstop-too-far": [exception(backstop=(TODAY + timedelta(days=31)).isoformat())],
            "backstop-before-approval": [exception(backstop=(TODAY - timedelta(days=1)).isoformat())],
            "approved-in-future": [exception(approved_on=(TODAY + timedelta(days=1)).isoformat(),
                                             backstop=(TODAY + timedelta(days=20)).isoformat())],
            "bad-date": [exception(backstop="soon")],
            "duplicate": [exception(), exception()],
            "unknown-field": [exception(note="x")],
            "missing-field": [{k: v for k, v in exception().items() if k != "approved_by"}],
            "malformed-ghsa": [exception(ghsa="CVE-2026-0001")],
            "bad-package": [exception(package="Not A Package")],
            "bad-severity": [exception(severity="urgent")],
            "empty-reason": [exception(reason="  ")],
            "empty-approver": [exception(approved_by="")],
            "empty-lockfiles": [exception(lockfiles={})],
            "bad-lock-digest": [exception(lockfiles={"site/package-lock.json": "x"})],
            "unknown-lockfile": [exception(lockfiles={"other/package-lock.json": LOCK_DIGEST})],
        }
        for label, records in cases.items():
            with self.subTest(label=label):
                code, _ = self.run_gate(records, finding)
                self.assertEqual(code, 1)
        for label, raw in {
            "unreadable": "{",
            "wrong-schema": json.dumps({"schema": "other", "exceptions": []}),
            "extra-key": json.dumps({"schema": load_gate().SCHEMA, "exceptions": [], "x": 1}),
            "not-a-list": json.dumps({"schema": load_gate().SCHEMA, "exceptions": {}}),
        }.items():
            with self.subTest(label=label):
                code, _ = self.run_gate([], finding, raw=raw)
                self.assertEqual(code, 1)

    def test_backstop_day_itself_still_passes(self):
        code, _ = self.run_gate([exception()], report((GHSA_ID, "http-cache-semantics", "high")),
                                today=TODAY + timedelta(days=14))
        self.assertEqual(code, 0)

    def test_committed_site_exceptions_are_valid_and_current(self):
        # As of today: a misdated (future) approval or an expired record fails
        # at PR time, not only when the site gate next runs.
        load_gate().load_exceptions(SITE_EXCEPTIONS, date.today())


if __name__ == "__main__":
    unittest.main()
