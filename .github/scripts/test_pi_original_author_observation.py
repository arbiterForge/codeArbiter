"""Focused inert controls for the original author observation reader."""

import io
import json
import unittest
from pathlib import Path
from zipfile import ZipFile

import pi_original_author_observation as reader
import pi_parent_tui_observation as fixture


NONCE = "0123456789abcdef"
WORKSPACE = "/owned/pi-observer-linux-1"
PROJECT = WORKSPACE + "/parent-author-fixture/project"
ROOT = "/checkout/.github/scripts"
SOURCE = "1" * 40
DIGEST = fixture.sha(Path(fixture.__file__).read_bytes())


def case():
    protocol = fixture.ProviderProtocol(NONCE)
    read = {"tool_call_id": "fixture-child-1-" + NONCE, "path": "effect-" + NONCE + ".txt",
            "content_sha256": fixture.sha(("before-" + NONCE).encode())}
    gate = fixture.PromptGate(NONCE)
    for operation in gate.ops:
        exact = fixture.compact(operation["params"])
        gate.feed(("Allow governed operation?\nDelegated " + operation["tool"] + " in " + PROJECT
                   + "\n" + exact + "\nSHA-256: " + fixture.sha(exact.encode())
                   + "\nThe parent executes this exact request\n→ Yes\n  No\n").encode())
        if gate.consent(PROJECT) == b"j":
            gate.feed("   Yes\n→ No\n".encode())
            gate.consent(PROJECT)
    terminal = bytes(gate.raw) + ("PI-D07 fixture completed " + NONCE).encode()
    journal = []
    for index, operation in enumerate(fixture.operations(NONCE)):
        request = f"fixture-request-{index}"
        tool = operation["tool"]
        identity = {
            "profile": fixture.PROFILE, "consentSource": "parent-human-confirmation", "role": "backend-author",
            "callerCorrelation": fixture.sha(protocol.parent_call_id.encode()), "runId": "owned-run",
            "permissionCorrelation": fixture.sha((protocol.parent_call_id + ":" + request).encode()),
            "digest": fixture.sha(fixture.compact({"profile": fixture.PROFILE, **operation}).encode()),
            "operationId": str(index), "requestId": request, "tool": tool,
        }
        if tool != "bash":
            identity["target"] = read["path"]
        phases = ["claimed", "observed"] + (["started"] if tool == "bash" else [])
        journal.extend({"record": {**identity, "phase": phase, "execution": "completed",
                        "containment": "verified-stopped" if tool == "bash" else "not-applicable"}} for phase in phases)
    effects = {name: {"bytes": len(raw), "sha256": fixture.sha(raw.encode()), "utf8": raw}
               for name, raw in {"file": "after-" + NONCE, "command": "command-" + NONCE + "\n"}.items()}
    runtime = {k: {"path": "/tool/" + k} for k in ("python", "git", "node")}
    acquisition = {"runtime_before": runtime, "graph_after": {"owned": True}, "prefix": WORKSPACE + "/pi-host"}
    cli = acquisition["prefix"] + "/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js"
    runner = [runtime["node"]["path"], cli]
    payloads = {"release-packages": {"fixture": True}}
    checks = {"source": {"inputs": {reader.HARNESS: DIGEST}}, "runtime": runtime,
              "graph": acquisition["graph_after"], "installed": {"plugin": "digest"}, "payloads": {"package": "digest"}}
    worker = {"source_before": checks["source"], "installed_before": {"plugin": {"sha256": "digest"}},
              "payload_before": checks["payloads"]}
    observation = {"installed_binding": {"worker": worker, "source_commit": SOURCE, "acquisition": acquisition,
                   "consumed_payloads": payloads, "supervision": {"argv": [None] * 3 + [ROOT + "/observe_pi_installed_rpc.py"]}}}
    process = {"argv": [*runner, "--offline", "--no-session", "--approve", "--no-context-files", "--provider",
                        "openai", "--model", "gpt-fixture", "Run only the deterministic owned PI-D07 fixture " + NONCE + "."],
               "returncode": 0, "timed_out": False, "pid": 42, "forced_cleanup": False, "exit_key_sent": True,
               "group_cleanup": "already-gone"}
    provider = [{"bytes": 42, "request_sha256": f"{index:064x}", "response_finish": finish}
                for index, finish in enumerate(["tool_calls"] * 6 + ["stop", "tool_calls", "tool_calls", "stop", "tool_calls", "stop", "stop"])]
    outcome = {"format": "codearbiter.pi-parent-tui-fixture/1", "source_commit": SOURCE, "actual_case": "executed",
               "inspection_turn": 5, "consent": "scripted-public-TUI-keys-not-human-consent", "author_read": read,
               "consumed_payloads": payloads, "process": process, "provider": provider, "prompts": gate.events}
    for source, target in (("source", "source"), ("runtime", "runtime"), ("graph", "admitted_graph"),
                           ("installed", "installed"), ("payloads", "payload")):
        outcome[target + "_before"] = outcome[target + "_after"] = checks[source]
    files = {
        "original-outcome.json": outcome, "parent-process.json": process, "effects.json": effects, "journal.json": journal,
        "verification.json": {"status": "passed",
                              "scope": "first POSIX scripted public-parent-TUI fixture only; not human/full PI-D07/major qualification"},
        "cleanup.json": {"provider_thread_stopped": True, "private_workspace_retained": True},
        "input-before.json": {**checks, "consumed_payloads": payloads}, "input-after.json": checks,
        "git-init.json": {**process, "exit_key_sent": False,
                          "argv": [runtime["git"]["path"], "init", "-q", "-b", "feature/pi-author-fixture"]},
        "package-install.json": {**process, "exit_key_sent": False,
                                 "argv": [*runner, "install", WORKSPACE + "/installed-pi/package", "--no-approve"]},
        "parent.ansi": terminal,
        "parent.readable.txt": terminal,
    }
    supervision = {
        "argv": [runtime["python"]["path"], "-I", "-B", ROOT + "/pi_parent_tui_observation.py",
                 "--config", WORKSPACE + "/parent-author-config.json", "--authenticated-payloads",
                 WORKSPACE + "/parent-author-payloads.json"],
        "timeout_seconds": 120, "body_seconds": 90, "returncode": 0, "timed_out": False, "containment": "exited",
    }
    return files, supervision, observation


class OriginalAuthorTest(unittest.TestCase):
    def setUp(self):
        self.files, self.supervision, self.observation = case()

    def observe(self, digest=DIGEST):
        raw = io.BytesIO()
        with ZipFile(raw, "w") as archive:
            for name, value in self.files.items():
                data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
                archive.writestr(reader.PARENT + name, data)
            archive.writestr("producer/parent-author-supervision.json", json.dumps(self.supervision))
        with ZipFile(raw) as archive:
            return reader._author_case(archive, self.observation, digest)

    def test_replays_owned_author_case(self):
        observed = self.observe()
        self.assertEqual(observed["author_read"]["path"], "effect-" + NONCE + ".txt")
        self.assertEqual(observed["retained_effect_sha256"]["file"], fixture.sha(("after-" + NONCE).encode()))

    def test_rejects_inspection_only_or_wrong_child_read(self):
        outcome = self.files["original-outcome.json"]
        outcome["author_read"]["tool_call_id"] = "fixture-reviewer-0-" + NONCE
        with self.assertRaisesRegex(ValueError, "author read result identity"):
            self.observe()
        del outcome["author_read"]
        with self.assertRaisesRegex(ValueError, "own read before edit"):
            self.observe()

    def test_rejects_unbound_terminal_and_effect_claims(self):
        self.files["original-outcome.json"]["prompts"][2]["params_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "prompts do not replay"):
            self.observe()
        self.files, self.supervision, self.observation = case()
        self.files["journal.json"][-1]["record"]["runId"] = "separate-child"
        with self.assertRaisesRegex(ValueError, "same original author"):
            self.observe()

    def test_rejects_echo_only_command_evidence(self):
        commands = [row["record"] for row in self.files["journal.json"] if row["record"]["tool"] == "bash"]
        old = {"profile": fixture.PROFILE, "tool": "bash",
               "params": {"command": f"printf 'command-{NONCE}\\n' >> command-{NONCE}.txt", "timeout": 15}}
        for command in commands:
            command["digest"] = fixture.sha(fixture.compact(old).encode())
        with self.assertRaisesRegex(ValueError, "journal-request-digest"):
            self.observe()

    def test_refuses_source_or_runtime_splice(self):
        with self.assertRaisesRegex(ValueError, "fixture source differs"):
            self.observe("0" * 64)
        self.files["input-after.json"]["runtime"] = {}
        with self.assertRaisesRegex(ValueError, "package/runtime differs"):
            self.observe()


if __name__ == "__main__":
    unittest.main()
