#!/usr/bin/env python3
"""Unit tests for the ca-sandbox real-container execution sentinel verifier.

Run: python .github/scripts/test_sandbox_docker_layers.py

Issue #406.  `docker info` answering once at the top of the job proves the
daemon was alive for one probe; it does not prove that the isolation, mount,
network, lifecycle and teardown suites - the only evidence ca-sandbox really
contains an untrusted repository - actually executed.  The gate appends one
line per layer that STARTED, and this verifier is what turns that append-only
file into a merge-blocking verdict.
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / ".github" / "scripts" / "check_sandbox_docker_layers.py"

_spec = importlib.util.spec_from_file_location("check_sandbox_docker_layers", TOOL)
layers = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = layers
_spec.loader.exec_module(layers)


def fake_tree(root: Path, files: dict[str, str]) -> Path:
    tools = root / "plugins" / "ca-sandbox" / "tools"
    for name, body in files.items():
        path = tools / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8", newline="\n")
    tools.mkdir(parents=True, exist_ok=True)
    return root


class ScanTest(unittest.TestCase):
    def test_declared_layers_come_from_the_shared_gate_call_sites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = fake_tree(
                Path(tmp),
                {
                    "run.test.ts": 'const d = dockerGate("run");\n',
                    "network.test.ts": 'const d = dockerGate("network", { linux: true });\n',
                    "mounts.test.ts": 'describe("pure unit", () => {});\n',
                },
            )
            self.assertEqual(layers.declared_layers(root), {"run", "network"})

    def test_the_gates_own_unit_test_is_not_scanned_as_a_declared_layer(self):
        # docker-gate.test.ts exercises the gate with literal layer names of its
        # own; counting those would demand sentinel lines no suite ever writes.
        with tempfile.TemporaryDirectory() as tmp:
            root = fake_tree(
                Path(tmp),
                {
                    "run.test.ts": 'const d = dockerGate("run");\n',
                    "docker-gate.test.ts": 'expect(dockerGate("probe-fixture"));\n',
                    "__fixtures__/docker-required/gate.fixture.test.ts": (
                        'const d = dockerGate("fixture");\n'
                    ),
                },
            )
            self.assertEqual(layers.declared_layers(root), {"run"})

    def test_nested_test_directories_are_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = fake_tree(
                Path(tmp),
                {"__tests__/isolation.test.ts": 'const d = dockerGate("isolation");\n'},
            )
            self.assertEqual(layers.declared_layers(root), {"isolation"})


class VerifyTest(unittest.TestCase):
    def _root(self, tmp: str) -> Path:
        return fake_tree(
            Path(tmp),
            {
                "run.test.ts": 'const d = dockerGate("run");\n',
                "network.test.ts": 'const d = dockerGate("network", { linux: true });\n',
            },
        )

    def test_a_sentinel_covering_every_layer_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            sentinel = Path(tmp) / "sentinel.txt"
            sentinel.write_text("run\nnetwork\nrun\n", encoding="utf-8", newline="\n")
            code, report = layers.verify(root, sentinel)
            self.assertEqual(code, 0, report)

    def test_a_layer_that_never_executed_fails_and_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            sentinel = Path(tmp) / "sentinel.txt"
            sentinel.write_text("run\n", encoding="utf-8", newline="\n")
            code, report = layers.verify(root, sentinel)
            self.assertEqual(code, 1)
            self.assertIn("network", report)

    def test_a_missing_sentinel_fails_rather_than_reading_as_success(self):
        # The exact #406 failure shape one level up: "nothing recorded" must
        # never be indistinguishable from "everything passed".
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            code, report = layers.verify(root, Path(tmp) / "absent.txt")
            self.assertEqual(code, 1)
            self.assertIn("absent.txt", report)

    def test_an_empty_sentinel_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            sentinel = Path(tmp) / "sentinel.txt"
            sentinel.write_text("\n  \n", encoding="utf-8", newline="\n")
            code, report = layers.verify(root, sentinel)
            self.assertEqual(code, 1)

    def test_a_sentinel_layer_no_source_declares_is_drift_and_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            sentinel = Path(tmp) / "sentinel.txt"
            sentinel.write_text("run\nnetwork\nghost\n", encoding="utf-8", newline="\n")
            code, report = layers.verify(root, sentinel)
            self.assertEqual(code, 1)
            self.assertIn("ghost", report)

    def test_a_tree_declaring_no_layers_fails_instead_of_vacuously_passing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = fake_tree(Path(tmp), {"mounts.test.ts": "describe('unit', () => {});\n"})
            sentinel = Path(tmp) / "sentinel.txt"
            sentinel.write_text("run\n", encoding="utf-8", newline="\n")
            code, report = layers.verify(root, sentinel)
            self.assertEqual(code, 1)
            self.assertIn("no dockerGate", report)


class RepositoryTest(unittest.TestCase):
    def test_the_committed_sandbox_tree_declares_the_containment_layers(self):
        declared = layers.declared_layers(REPO_ROOT)
        self.assertTrue(declared, "the committed ca-sandbox tree declares no docker layers")
        for expected in ("isolation", "lifecycle", "network", "run"):
            self.assertIn(expected, declared)


if __name__ == "__main__":
    unittest.main()
