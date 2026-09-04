#!/usr/bin/env python3
# codeArbiter — cross-host coverage identity regression and refusal contracts.
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).with_name("coverage_union.py")


def flatten(value):
    """Encode small inert fixtures in Vitest's flatted graph representation."""
    graph = []

    def put(item):
        index = len(graph)
        graph.append(None)
        if isinstance(item, dict):
            graph[index] = {key: put(val) if isinstance(val, (dict, list, str)) else val
                            for key, val in item.items()}
        elif isinstance(item, list):
            graph[index] = [put(val) if isinstance(val, (dict, list, str)) else val for val in item]
        else:
            graph[index] = item
        return str(index)

    put(value)
    return graph


def decode(graph, index):
    value = graph[int(index)]
    if isinstance(value, dict):
        return {key: decode(graph, val) if isinstance(val, str) else val for key, val in value.items()}
    if isinstance(value, list):
        return [decode(graph, val) if isinstance(val, str) else val for val in value]
    return value


def fixture(path, hits):
    locations = [{"start": {"line": n, "column": 0}, "end": {"line": n, "column": 3}} for n in (1, 2)]
    return {"path": path, "statementMap": {"0": locations[0], "1": locations[1]},
            "fnMap": {}, "branchMap": {"0": {"type": "if", "line": 1, "loc": locations[0], "locations": locations}},
            "s": {"0": hits[0], "1": hits[1]}, "f": {}, "b": {"0": hits}}


class CoverageUnionTest(unittest.TestCase):
    def setUp(self):
        self.expected = {"schema": 1, "head": "a" * 40, "tree": "plugins/ca-pi/tools",
                         "vitest": "4.1.9", "config": {"package-lock.json": "b" * 64, "vitest.config.ts": "c" * 64},
                         "sources": {"src/a.ts": "d" * 64, "src/b.ts": "e" * 64},
                         "root": "/current/plugins/ca-pi/tools"}
        self.inputs = []
        for host, root, hits in [("windows-latest", "D:/a/repo/plugins/ca-pi/tools", [1, 0]),
                                 ("ubuntu-latest", "/home/runner/repo/plugins/ca-pi/tools", [0, 1])]:
            proof = {**copy.deepcopy(self.expected), "host": host, "root": root}
            coverage = {f"{root}/{path}": fixture(f"{root}/{path}", hits) for path in self.expected["sources"]}
            self.inputs.append((flatten(["4.1.9", [], [], coverage, 0, {}]), proof))

    def normalize(self, inputs=None):
        values = self.inputs if inputs is None else inputs
        if os.environ.get("COVERAGE_UNION_BASELINE") == "1":
            # Explicit diagnostic mode reproduces the existing workflow's raw
            # Istanbul merge. Never used by the production helper or normal CI.
            return [graph for graph, _ in values], "UNION"
        spec = importlib.util.spec_from_file_location("coverage_union", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.normalize(values, self.expected)

    def summary(self, graphs):
        maps = [decode(graph, graph[0][3]) for graph in graphs]
        javascript = "const{createCoverageMap}=require('istanbul-lib-coverage');let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>{const m=createCoverageMap();for(const c of JSON.parse(s))m.merge(c);console.log(JSON.stringify({files:m.files(),summary:m.getCoverageSummary().toJSON()}));});"
        result = subprocess.run(["node", "-e", javascript], input=json.dumps(maps), text=True,
                                capture_output=True, cwd=REPO / "plugins/ca-pi/tools", timeout=30, check=True)
        return json.loads(result.stdout)

    def test_complementary_hosts_union_without_doubling_distinct_files(self):
        # CU-01: exact defect, executed against installed Istanbul, not a mock.
        graphs, status = self.normalize()
        result = self.summary(graphs)
        self.assertEqual(len(result["files"]), 2, "host checkout paths duplicated source identities")
        self.assertEqual(result["summary"]["lines"]["total"], 4)
        self.assertEqual(result["summary"]["lines"]["covered"], 4)
        self.assertEqual(result["summary"]["branches"]["total"], 4)
        self.assertEqual(result["summary"]["branches"]["covered"], 4)
        self.assertEqual(status, "UNION")

    def test_single_host_is_partial_and_no_hosts_refuses(self):
        graphs, status = self.normalize(self.inputs[:1])
        self.assertEqual(status, "PARTIAL")
        self.assertEqual(self.summary(graphs)["summary"]["lines"]["covered"], 2)
        with self.assertRaises(ValueError):
            self.normalize([])

    def test_mismatched_provenance_refuses(self):
        for field, value in [("head", "f" * 40), ("tree", "plugins/ca/tools"), ("vitest", "0.0.0"),
                             ("config", {}), ("sources", {}), ("host", "other")]:
            with self.subTest(field=field):
                inputs = copy.deepcopy(self.inputs)
                inputs[1][1][field] = value
                with self.assertRaises(ValueError):
                    self.normalize(inputs)

    def test_duplicate_host_and_source_aliases_refuse(self):
        with self.assertRaises(ValueError):
            self.normalize([self.inputs[0], self.inputs[0]])
        for path in ["src/../src/a.ts", "src//a.ts", "src/A.ts", "../outside.ts"]:
            with self.subTest(path=path):
                inputs = copy.deepcopy(self.inputs)
                graph, proof = inputs[0]
                coverage = decode(graph, graph[0][3])
                alias = proof["root"] + "/" + path
                coverage[alias] = fixture(alias, [1, 0])
                inputs[0] = (flatten(["4.1.9", [], [], coverage, 0, {}]), proof)
                with self.assertRaises(ValueError):
                    self.normalize(inputs)

    def test_different_instrumentation_and_key_path_refuse(self):
        for mode in ("map", "path", "missing-source"):
            with self.subTest(mode=mode):
                inputs = copy.deepcopy(self.inputs)
                graph, proof = inputs[1]
                coverage = decode(graph, graph[0][3])
                entry = next(iter(coverage.values()))
                if mode == "map":
                    entry["statementMap"]["0"]["start"]["line"] = 9
                elif mode == "path":
                    entry["path"] += ".other"
                else:
                    coverage.pop(next(iter(coverage)))
                inputs[1] = (flatten(["4.1.9", [], [], coverage, 0, {}]), proof)
                with self.assertRaises(ValueError):
                    self.normalize(inputs)

    def test_malformed_graph_and_unsafe_counts_refuse(self):
        for mode in ("cycle", "reference", "negative"):
            with self.subTest(mode=mode):
                inputs = copy.deepcopy(self.inputs)
                graph, proof = inputs[0]
                if mode == "cycle":
                    graph[int(graph[0][3])]["cycle"] = graph[0][3]
                elif mode == "reference":
                    graph[0][3] = "999999999"
                else:
                    coverage = decode(graph, graph[0][3])
                    next(iter(coverage.values()))["s"]["0"] = -1
                    graph = flatten(["4.1.9", [], [], coverage, 0, {}])
                inputs[0] = (graph, proof)
                with self.assertRaises(ValueError):
                    self.normalize(inputs)

    def test_identical_missing_source_and_missing_location_refuse(self):
        for mode in ("source", "location"):
            inputs = copy.deepcopy(self.inputs)
            for index, (graph, proof) in enumerate(inputs):
                coverage = decode(graph, graph[0][3])
                if mode == "source":
                    coverage.pop(next(iter(coverage)))
                else:
                    next(iter(coverage.values()))["statementMap"]["0"] = {}
                inputs[index] = (flatten(["4.1.9", [], [], coverage, 0, {}]), proof)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.normalize(inputs)

    def test_real_v8_null_end_column_remains_supported(self):
        inputs = copy.deepcopy(self.inputs)
        for index, (graph, proof) in enumerate(inputs):
            coverage = decode(graph, graph[0][3])
            for value in coverage.values():
                value["statementMap"]["0"]["end"]["column"] = None
            inputs[index] = (flatten(["4.1.9", [], [], coverage, 0, {}]), proof)
        self.assertEqual(self.normalize(inputs)[1], "UNION")

    def test_real_v8_implicit_else_location_remains_supported(self):
        inputs = copy.deepcopy(self.inputs)
        for index, (graph, proof) in enumerate(inputs):
            coverage = decode(graph, graph[0][3])
            for value in coverage.values():
                value["branchMap"]["0"]["locations"][1] = {"start": {}, "end": {}}
            inputs[index] = (flatten(["4.1.9", [], [], coverage, 0, {}]), proof)
        self.assertEqual(self.normalize(inputs)[1], "UNION")

    def signed_inputs(self, left, right):
        inputs = copy.deepcopy(self.inputs)
        for index, (graph, proof) in enumerate(inputs):
            coverage = decode(graph, graph[0][3])
            for value in coverage.values():
                value["branchMap"]["0"]["locations"][1] = {"start": {}, "end": {}}
                value["b"]["0"][1] = (left, right)[index]
            inputs[index] = (flatten(["4.1.9", [], [], coverage, 0, {}]), proof)
        return inputs

    def test_real_negative_implicit_else_counts_preserved_without_inventing_hits(self):
        graphs, status = self.normalize(self.signed_inputs(-27, -27))
        self.assertEqual(status, "UNION")
        for graph in graphs:
            for value in decode(graph, graph[0][3]).values():
                self.assertEqual(value["b"]["0"][1], -27)
        self.assertEqual(self.summary(graphs)["summary"]["branches"]["covered"], 2)

    def test_branch_cancellation_and_unsafe_sum_refuse(self):
        for left, right in ((1, -1), (1, -2), (2**53 - 1, 1)):
            with self.subTest(left=left, right=right), self.assertRaises(ValueError):
                self.normalize(self.signed_inputs(left, right))


class CoverageUnionCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="coverage-union-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.tree = self.repo / "plugins/ca/tools"
        self.tree.mkdir(parents=True)
        for name, content in {"a.ts": "const a = 1;\nconst b = 2;\n",
                              "vitest.config.ts": 'export default {test:{coverage:{include: ["*.ts"], exclude: ["*.test.ts", "*.config.ts"]}}};\n',
                              "package.json": '{"private":true}\n',
                              "package-lock.json": '{"packages":{"node_modules/vitest":{"version":"4.1.9"}}}\n'}.items():
            target = self.tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        for command in (["init", "-q"], ["add", "."],
                        ["-c", "user.name=Coverage fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"]):
            subprocess.run(["git", "-C", str(self.repo), *command], capture_output=True, check=True, timeout=30)
        self.inputs = Path(self.temp.name) / "inputs"
        self.inputs.mkdir()
        self.output = Path(self.temp.name) / "verified"

    def cli(self, mode, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), mode, "--repo", str(self.repo),
                               "--tree", "plugins/ca/tools", *map(str, extra)], text=True,
                              capture_output=True, timeout=30)

    def prepared(self, host="ubuntu-latest", seal=True):
        proof = self.inputs / f"{host}.provenance.json"
        result = self.cli("prepare", "--host", host, "--output", proof)
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.tree.as_posix() + "/a.ts"
        graph = flatten(["4.1.9", [], [], {path: fixture(path, [1, 0])}, 0, {}])
        (self.inputs / f"{host}.json").write_text(json.dumps(graph), encoding="utf-8")
        if seal:
            result = self.cli("prepare", "--host", host, "--output", proof, "--check")
            self.assertEqual(result.returncode, 0, result.stderr)
        return proof

    def verify(self):
        return self.cli("verify", "--input", self.inputs, "--output", self.output)

    def test_prepare_check_verify_partial_and_no_overwrite(self):
        proof = self.prepared()
        before = proof.read_bytes()
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "coverage-identity: PARTIAL")
        self.assertEqual([path.name for path in self.output.iterdir()], ["ubuntu-latest.json"])
        self.assertEqual(proof.read_bytes(), before)
        self.assertNotEqual(self.verify().returncode, 0)
        self.assertNotEqual(self.cli("prepare", "--host", "ubuntu-latest", "--output", proof).returncode, 0)

    def test_workflow_relative_repo_path_is_canonical(self):
        proof = self.inputs / "ubuntu-latest.provenance.json"
        result = subprocess.run([sys.executable, str(SCRIPT), "prepare", "--repo", "../../..",
                                 "--tree", "plugins/ca/tools", "--host", "ubuntu-latest", "--output", str(proof)],
                                cwd=self.tree, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(proof.read_text())["root"], self.tree.as_posix())

    def test_posttest_source_mutation_prevents_seal(self):
        proof = self.prepared(seal=False)
        (self.tree / "a.ts").write_text("changed\n", encoding="utf-8")
        result = self.cli("prepare", "--host", "ubuntu-latest", "--output", proof, "--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.inputs / "ubuntu-latest.checked.json").exists())

    def test_missing_seal_refuses_without_output(self):
        self.prepared(seal=False)
        self.assertNotEqual(self.verify().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_blob_mutation_after_seal_refuses_without_output(self):
        self.prepared()
        blob = self.inputs / "ubuntu-latest.json"
        blob.write_bytes(blob.read_bytes() + b" ")
        self.assertNotEqual(self.verify().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_extra_input_and_duplicate_json_keys_refuse(self):
        self.prepared()
        extra = self.inputs / "unexpected.json"
        extra.write_text("{}", encoding="utf-8")
        self.assertNotEqual(self.verify().returncode, 0)
        extra.unlink()
        receipt = self.inputs / "ubuntu-latest.checked.json"
        receipt.write_text('{"schema":1,"schema":1}', encoding="utf-8")
        self.assertNotEqual(self.verify().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_changed_config_and_symlinked_input_refuse(self):
        self.prepared()
        config = self.tree / "vitest.config.ts"
        original = config.read_bytes()
        config.write_bytes(original + b"// change\n")
        self.assertNotEqual(self.verify().returncode, 0)
        config.write_bytes(original)
        link = Path(self.temp.name) / "linked"
        try:
            link.symlink_to(self.inputs, target_is_directory=True)
        except OSError:
            return  # Optional OS privilege, config refusal above still exercised.
        self.assertNotEqual(self.cli("verify", "--input", link, "--output", self.output).returncode, 0)


if __name__ == "__main__":
    unittest.main()
