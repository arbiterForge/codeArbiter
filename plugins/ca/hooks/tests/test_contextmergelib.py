"""Real-Git recovery and refusal obligations for the missing H-22 merge operation."""
import hashlib
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


CORE = Path(__file__).resolve().parents[4] / "core" / "pysrc"
sys.path.insert(0, str(CORE))
import _artifactlib
import _bashguardlib
import _contextmergelib


CLI = CORE / "resolve-context-conflict.py"
TARGET = ".codearbiter/code-map.md"
PROVENANCE = ".codearbiter/.provenance/code-map.json"
MANIFESTS = {
    "ca_version": "plugins/ca/.claude-plugin/plugin.json",
    "codex_version": "plugins/ca-codex/.codex-plugin/plugin.json",
    "pi_version": "plugins/ca-pi/package.json",
}
CLAIM_MAP = (b"# Code map - fixture\n\nmetadata refreshed on 2026-10-07.\n\n"
             b"- `plugins/ca/` (v2.25.0) - fixture role\n"
             b"- `plugins/ca-codex/` (v0.16.0) - fixture role\n"
             b"- `plugins/ca-pi/` (v0.17.0, npm-published fixture) - fixture role\n"
             b"\nUnselected text mentions 2.25.0 and keeps its exact bytes.\n")


class ContextMergeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "repo"
        self.root.mkdir()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.git("init", "-q", "-b", "current")
        self.git("config", "user.name", "Context merge fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "merge.conflictStyle", "merge")
        self.write(TARGET, b"# Code map\n\n- ca 2.24.0\n- ca-codex 0.15.4\n- ca-pi 0.16.0\n")
        self.write(PROVENANCE, b'{"schema":1,"doc":"code-map","created":"2026-10-07","interview_derived":false,"entries":[]}\n')
        self.write("untouched.txt", b"keep unrelated bytes\n")
        self.commit("base")
        self.git("branch", "incoming")
        self.write(TARGET, b"# Code map\n\n- ca 2.25.0\n- ca-codex 0.16.0\n- ca-pi 0.17.0\n")
        self.commit("prepared current versions")
        self.head = self.git("rev-parse", "HEAD").stdout.strip().decode()
        self.ours = self.git("cat-file", "blob", "HEAD:" + TARGET).stdout
        self.git("checkout", "-q", "incoming")
        self.write(TARGET, b"# Code map\n\n- ca 2.24.1\n- ca-codex 0.15.5\n- ca-pi 0.16.1\n")
        self.commit("incoming patch versions")
        self.git("checkout", "-q", "current")
        merged = self.git("merge", "--no-commit", "incoming", check=False)
        self.assertEqual(merged.returncode, 1, merged.stderr)
        self.assertEqual(len(self.git("ls-files", "-u", "--", TARGET).stdout.splitlines()), 3)
        self.assertIn(b"<<<<<<< HEAD", (self.root / TARGET).read_bytes())

    def git(self, *args, check=True):
        return subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull, *args],
                              cwd=self.root, env=self.env, capture_output=True,
                              shell=False, check=check)

    def write(self, relative, raw):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def commit(self, message):
        self.git("add", "--", ".")
        self.git("commit", "-qm", message, "--no-gpg-sign")

    def state(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for path in self.root.rglob("*")
                if path.is_file() and ".git" not in path.relative_to(self.root).parts}

    def invoke(self, *args):
        self.assertTrue(CLI.is_file(),
                        "No shipped context-conflict recovery operation exists; H-22 blocks ordinary HEAD restore")
        return subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                              cwd=self.root, env=self.env, capture_output=True, text=True,
                              shell=False)

    def inspect(self):
        result = self.invoke("inspect")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def prepare_claims(self, *, crlf=False):
        self.git("merge", "--abort")
        self.write(TARGET, CLAIM_MAP.replace(b"\n", b"\r\n") if crlf else CLAIM_MAP)
        for field, version in (("ca_version", "2.25.7"),
                               ("codex_version", "0.16.7"), ("pi_version", "0.17.8")):
            self.write(MANIFESTS[field], json.dumps({"version": version}).encode() + b"\n")
        self.commit("legacy claim fixture and current source manifests")
        self.write("untouched.txt", b"unrelated staged bytes\n")
        self.git("add", "--", "untouched.txt")

    def inspect_claims(self):
        result = self.invoke("inspect-claims")
        self.assertEqual(result.returncode, 0,
                         "No shipped legacy claim-refresh operation is available: " + result.stderr)
        return json.loads(result.stdout)

    def test_legacy_code_map_claim_refresh_with_qualified_native_writer(self):
        self.prepare_claims()
        before = self.state()
        index = (self.root / ".git/index").read_bytes()
        with mock.patch.object(_artifactlib, "context_writer_qualified", return_value=True), \
                mock.patch.object(_bashguardlib, "block", side_effect=lambda code, _message: (_ for _ in ()).throw(RuntimeError(code))):
            with self.assertRaisesRegex(RuntimeError, "H-22"):
                _bashguardlib._check_h22_state("echo changed > " + TARGET, str(self.root))
            _bashguardlib._check_h22_state(f'python "{CLI}" --root "{self.root}" inspect-claims', str(self.root))
        inspected = self.inspect_claims()
        self.assertEqual(inspected["target_sha256"], hashlib.sha256(before[TARGET]).hexdigest())
        self.assertEqual(inspected["provenance_sha256"], hashlib.sha256(before[PROVENANCE]).hexdigest())
        self.assertEqual(self.state(), before)
        claims = [{"field": "ca_version", "before": "2.25.0", "after": "2.25.7"}]
        result = self.invoke("refresh-claims", "--expected", inspected["binding"], "--claims", json.dumps(claims))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "refreshed")
        expected = CLAIM_MAP.replace(b"`plugins/ca/` (v2.25.0)", b"`plugins/ca/` (v2.25.7)")
        self.assertEqual(self.state(), {**before, TARGET: expected})
        self.assertEqual((self.root / ".git/index").read_bytes(), index)
        self.assertFalse((self.root / ".codearbiter/.artifacts").exists())

    def test_claim_refresh_all_typed_fields_preserves_crlf(self):
        self.prepare_claims(crlf=True)
        before = self.state()
        inspected = self.inspect_claims()
        today = datetime.date.today().isoformat()
        claims = [{"field": field, "before": old, "after": new} for field, old, new in (
            ("ca_version", "2.25.0", "2.25.7"), ("codex_version", "0.16.0", "0.16.7"),
            ("pi_version", "0.17.0", "0.17.8"), ("metadata_date", "2026-10-07", today))]
        result = self.invoke("refresh-claims", "--expected", inspected["binding"], "--claims", json.dumps(claims))
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = before[TARGET]
        for old, new in ((b"(v2.25.0)", b"(v2.25.7)"), (b"(v0.16.0)", b"(v0.16.7)"),
                         (b"(v0.17.0,", b"(v0.17.8,"), (b"on 2026-10-07.", ("on " + today + ".").encode())):
            expected = expected.replace(old, new)
        self.assertEqual(self.state(), {**before, TARGET: expected})

    def test_claim_refresh_refuses_stale_native_and_unsafe_preimages(self):
        self.prepare_claims()
        inspected = self.inspect_claims()
        original = self.state()
        index_path = self.root / ".git/index"
        index = index_path.read_bytes()
        claims = json.dumps([{"field": "ca_version", "before": "2.25.0", "after": "2.25.7"}])
        cases = (
            ("stale binding", lambda: None, "0" * 64),
            ("changed target", lambda: self.write(TARGET, original[TARGET] + b"human note\n"), None),
            ("changed provenance", lambda: self.write(PROVENANCE, original[PROVENANCE] + b"\n"), None),
            ("native provenance", lambda: self.write(PROVENANCE, b'{"schema":2,"doc":"code-map"}\n'), None),
            ("malformed provenance", lambda: self.write(PROVENANCE, b'{"schema":1,"doc":"code-map"}\n'), None),
            ("duplicate provenance keys", lambda: self.write(PROVENANCE, original[PROVENANCE].replace(b'"schema":1', b'"schema":1,"schema":1')), None),
            ("uncertain journal", lambda: self.write(".codearbiter/.artifacts/transactions/context-unknown.json", b"{"), None),
            ("changed source", lambda: self.write(MANIFESTS["ca_version"], b'{"version":"2.25.8"}\n'), None),
            ("changed index", lambda: (self.write("untouched.txt", b"changed staged bytes\n"), self.git("add", "--", "untouched.txt")), None),
            ("missing heading", lambda: self.write(TARGET, original[TARGET].replace(b"# Code map", b"# Other")), None),
            ("unresolved map", lambda: self.write(TARGET, original[TARGET] + b"<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> incoming\n"), None),
        )
        for name, mutate, binding in cases:
            with self.subTest(case=name):
                mutate()
                before = self.state()
                before_index = index_path.read_bytes()
                if name in {"native provenance", "malformed provenance", "duplicate provenance keys",
                            "uncertain journal", "missing heading", "unresolved map"}:
                    self.assertNotEqual(self.invoke("inspect-claims").returncode, 0,
                                        "fresh inspection must reject invalid or native input")
                result = self.invoke("refresh-claims", "--expected", binding or inspected["binding"], "--claims", claims)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self.state(), before)
                self.assertEqual(index_path.read_bytes(), before_index)
                for path, raw in original.items():
                    self.write(path, raw)
                journal = self.root / ".codearbiter/.artifacts/transactions/context-unknown.json"
                if journal.exists():
                    journal.unlink()
                index_path.write_bytes(index)

    def test_claim_refresh_refuses_unreviewed_or_arbitrary_fields(self):
        self.prepare_claims()
        inspected = self.inspect_claims()
        original = self.state()
        index = (self.root / ".git/index").read_bytes()
        valid = {"field": "ca_version", "before": "2.25.0", "after": "2.25.7"}
        selections = ([], {}, [valid, valid], [dict(valid, before="2.25.1")],
                      [dict(valid, after="2.25.8")], [dict(valid, after="2.25.7\nnew text")],
                      [dict(valid, field="body")], [dict(valid, content="replacement")],
                      [dict(valid, after=True)], [dict(valid, after="02.25.7")],
                      [{"field": "metadata_date", "before": "2026-10-07", "after": "2026-02-31"}],
                      [{"field": "metadata_date", "before": "2026-10-07", "after": "2000-01-01"}],
                      [valid] * 5)
        for claims in selections:
            with self.subTest(claims=claims):
                result = self.invoke("refresh-claims", "--expected", inspected["binding"], "--claims", json.dumps(claims))
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self.state(), original)
                self.assertEqual((self.root / ".git/index").read_bytes(), index)

    def test_claim_refresh_refuses_linked_and_ambiguous_targets(self):
        self.prepare_claims()
        original = self.state()
        index = (self.root / ".git/index").read_bytes()
        for relative in (TARGET, PROVENANCE, MANIFESTS["ca_version"]):
            with self.subTest(linked=relative):
                path = self.root / relative
                linked = self.root / "linked-evidence.txt"
                os.link(path, linked)
                before = self.state()
                result = self.invoke("inspect-claims")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.state(), before)
                self.assertEqual((self.root / ".git/index").read_bytes(), index)
                linked.unlink()
        self.write(TARGET, original[TARGET] + b"- `plugins/ca/` (v2.25.0) - ambiguous\n")
        before = self.state()
        self.assertNotEqual(self.invoke("inspect-claims").returncode, 0)
        self.assertEqual(self.state(), before)

    def test_claim_refresh_refuses_committed_or_indexed_native_provenance(self):
        self.prepare_claims()
        legacy = (self.root / PROVENANCE).read_bytes()
        native = legacy.replace(b'"schema":1', b'"schema":2')
        self.write(PROVENANCE, native)
        self.git("add", "--", PROVENANCE)
        self.write(PROVENANCE, legacy)
        before = self.state()
        index = (self.root / ".git/index").read_bytes()
        self.assertNotEqual(self.invoke("inspect-claims").returncode, 0)
        self.assertEqual(self.state(), before)
        self.assertEqual((self.root / ".git/index").read_bytes(), index)
        self.write(PROVENANCE, native)
        self.commit("native provenance fixture")
        self.write(PROVENANCE, legacy)
        self.git("add", "--", PROVENANCE)
        before = self.state()
        index = (self.root / ".git/index").read_bytes()
        self.assertNotEqual(self.invoke("inspect-claims").returncode, 0)
        self.assertEqual(self.state(), before)
        self.assertEqual((self.root / ".git/index").read_bytes(), index)

    def test_claim_refresh_refuses_native_journal_and_concurrent_edits(self):
        self.prepare_claims()
        inspected = self.inspect_claims()
        claims = [{"field": "ca_version", "before": "2.25.0", "after": "2.25.7"}]
        original = self.state()
        index = (self.root / ".git/index").read_bytes()
        operation = "fixture-context967"
        rows = [{"path": path, "stage": f"{Path(path).parent.as_posix()}/.ca-artifact-{operation}-{i}.new",
                 "backup": f".codearbiter/.artifacts/history/{operation}-{i}.before",
                 "before_sha256": None, "after_sha256": hashlib.sha256(original[path]).hexdigest(),
                 "size": len(original[path])} for i, path in enumerate((TARGET, PROVENANCE))]
        journal = {"format": "codearbiter.transaction/0.2.0", "operation_id": operation,
                   "request_sha256": "0" * 64, "state": "committed", "entries": rows,
                   "result": {"document_id": "code-map", "target_path": TARGET, "mode": "adopt",
                              "document_sha256": rows[0]["after_sha256"], "provenance_sha256": rows[1]["after_sha256"]}}
        path = f".codearbiter/.artifacts/transactions/{operation}.json"
        self.write(path, json.dumps(journal).encode())
        before = self.state()
        self.assertNotEqual(self.invoke("inspect-claims").returncode, 0)
        self.assertEqual(self.state(), before)
        self.assertEqual((self.root / ".git/index").read_bytes(), index)
        (self.root / path).unlink()
        atomic = _contextmergelib._write_bytes_atomic
        foreign = original[TARGET] + b"concurrent human note\n"

        def replace_after_snapshot(path, raw, *, expected):
            path.write_bytes(foreign)
            return atomic(path, raw, expected=expected)

        with mock.patch.object(_contextmergelib, "_write_bytes_atomic", side_effect=replace_after_snapshot), \
                self.assertRaises(RuntimeError):
            _contextmergelib.refresh_claims(self.root, inspected["binding"], claims)
        self.assertEqual((self.root / TARGET).read_bytes(), foreign)
        self.assertEqual((self.root / PROVENANCE).read_bytes(), original[PROVENANCE])
        self.assertEqual((self.root / ".git/index").read_bytes(), index)

    def prepare_blocks(self, style="merge"):
        self.git("merge", "--abort")
        self.git("config", "merge.conflictStyle", style)
        middle = b"".join(("unchanged row " + str(i) + "\n").encode() for i in range(16))
        base = b"# Code map\n\nfirst base\n" + middle + b"second base\n\ntail\n"
        self.write(TARGET, base)
        self.commit("multi-block base")
        self.git("branch", "-f", "incoming", "HEAD")
        ours = base.replace(b"first base", b"first ours").replace(b"second base", b"second ours")
        self.write(TARGET, ours)
        self.commit("two current edits")
        self.git("checkout", "-q", "incoming")
        theirs = base.replace(b"first base", b"first theirs").replace(b"second base", b"second theirs") + b"incoming unconflicted row\n"
        self.write(TARGET, theirs)
        self.commit("two incoming edits and new unconflicted row")
        self.git("checkout", "-q", "current")
        self.assertEqual(self.git("merge", "--no-commit", "incoming", check=False).returncode, 1)
        self.assertEqual((self.root / TARGET).read_bytes().count(b"<<<<<<< HEAD"), 2)
        return ours.replace(b"second ours", b"second theirs") + b"incoming unconflicted row\n"

    def test_legacy_code_map_explicit_multi_block_resolution(self):
        expected = self.prepare_blocks()
        before = self.state()
        index = (self.root / ".git/index").read_bytes()
        self.assertNotEqual(self.invoke("inspect").returncode, 0,
                            "the original exact-HEAD restoration contract must stay narrow")
        inspected = self.invoke("inspect-blocks")
        self.assertEqual(inspected.returncode, 0,
                         "No shipped explicit multi-block resolution exists: " + inspected.stderr)
        binding = json.loads(inspected.stdout)
        self.assertEqual(binding["blocks"], 2)
        self.assertEqual(self.state(), before)
        result = self.invoke("resolve-blocks", "--expected", binding["binding"], "--choices", '["ours","theirs"]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "resolved")
        self.assertEqual(self.state(), {**before, TARGET: expected})
        self.assertEqual((self.root / ".git/index").read_bytes(), index)
        self.assertEqual(len(self.git("ls-files", "-u", "--", TARGET).stdout.splitlines()), 3)
        self.assertFalse((self.root / ".codearbiter/.artifacts").exists())

    def test_multi_block_resolution_supports_git_styles_and_crlf(self):
        for style in ("merge", "diff3", "zdiff3"):
            with self.subTest(style=style):
                expected = self.prepare_blocks(style)
                self.write(TARGET, (self.root / TARGET).read_bytes().replace(b"\n", b"\r\n"))
                before = self.state()
                index = (self.root / ".git/index").read_bytes()
                inspected = self.invoke("inspect-blocks")
                self.assertEqual(inspected.returncode, 0, inspected.stderr)
                result = self.invoke("resolve-blocks", "--expected", json.loads(inspected.stdout)["binding"],
                                     "--choices", '["ours","theirs"]')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.state(), {**before, TARGET: expected.replace(b"\n", b"\r\n")})
                self.assertEqual((self.root / ".git/index").read_bytes(), index)

    def test_real_ort_histogram_alignment_preserves_unconflicted_rows(self):
        base = b"# Code map\n\nrow 0\nrow 1\n"
        ours = b"# Code map\n\nrow 1\ntail\n"
        theirs = b"# Code map\n\nrow 1\nrow 0\nrow 4\nrow 1\nrow 3\n"
        for style in ("merge", "diff3", "zdiff3"):
            for algorithm in ("default", "myers"):
                with self.subTest(style=style, algorithm=algorithm):
                    self.git("merge", "--abort")
                    self.git("config", "merge.conflictStyle", style)
                    self.write(TARGET, base)
                    self.commit("repeated-row alignment base")
                    self.git("branch", "-f", "incoming", "HEAD")
                    self.write(TARGET, ours)
                    self.commit("current row deletion and tail")
                    self.git("checkout", "-q", "incoming")
                    self.write(TARGET, theirs)
                    self.commit("incoming repeated rows")
                    self.git("checkout", "-q", "current")
                    options = [] if algorithm == "default" else ["-Xdiff-algorithm=myers"]
                    merged = self.git("merge", "--no-commit", *options, "incoming", check=False)
                    self.assertEqual(merged.returncode, 1, merged.stderr)
                    self.assertEqual(len(self.git("ls-files", "-u", "--", TARGET).stdout.splitlines()), 3)
                    before = self.state()
                    index = (self.root / ".git/index").read_bytes()
                    prefix = b"# Code map\n\n" + (b"row 1\n" if algorithm == "default" else b"")
                    self.assertEqual(before[TARGET].split(b"<<<<<<< HEAD\n")[0], prefix,
                                     "use the real selected Git algorithm's conflict boundaries")
                    try:
                        inspected = _contextmergelib.inspect_blocks(self.root)
                    except _contextmergelib.ResolutionError as error:
                        self.fail("genuine Git rendering refused: " + str(error))
                    blocks = 2 if algorithm == "myers" and style != "merge" else 1
                    self.assertEqual(inspected["blocks"], blocks)
                    self.assertEqual(self.state(), before)
                    self.assertEqual((self.root / ".git/index").read_bytes(), index)
                    for foreign in (before[TARGET].replace(b"# Code map\n", b"# Code map\nhuman note\n"),
                                    before[TARGET].replace(b"tail\n", b"human changed tail\n")):
                        self.write(TARGET, foreign)
                        with self.assertRaisesRegex(_contextmergelib.ResolutionError,
                                                    "not Git's current three-stage rendering"):
                            _contextmergelib.inspect_blocks(self.root)
                        self.assertEqual(self.state(), {**before, TARGET: foreign})
                        self.assertEqual((self.root / ".git/index").read_bytes(), index)
                    self.write(TARGET, before[TARGET])
                    resolved = self.invoke("resolve-blocks", "--expected", inspected["binding"],
                                           "--choices", json.dumps(["theirs"] * blocks))
                    self.assertEqual(resolved.returncode, 0, resolved.stderr)
                    self.assertEqual(self.state(), {**before, TARGET: theirs})
                    self.assertEqual((self.root / ".git/index").read_bytes(), index)
                    self.assertEqual(len(self.git("ls-files", "-u", "--", TARGET).stdout.splitlines()), 3)
                    self.assertFalse((self.root / ".git/index.lock").exists())
                    self.assertFalse((self.root / ".codearbiter/.artifacts").exists())

    def test_multi_block_refusals_preserve_foreign_edits_and_index(self):
        self.prepare_blocks()
        inspected = self.invoke("inspect-blocks")
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        binding = json.loads(inspected.stdout)["binding"]
        original = self.state()
        index_path = self.root / ".git/index"
        index = index_path.read_bytes()
        cases = (
            ("stale binding", lambda: None, "0" * 64),
            ("outside human edit", lambda: self.write(TARGET, original[TARGET] + b"human note\n"), None),
            ("inside human edit", lambda: self.write(TARGET, original[TARGET].replace(b"first ours", b"human changed ours")), None),
            ("changed provenance", lambda: self.write(PROVENANCE, original[PROVENANCE] + b"\n"), None),
            ("native provenance", lambda: self.write(PROVENANCE, b'{"schema":2,"doc":"code-map"}\n'), None),
            ("uncertain journal", lambda: self.write(".codearbiter/.artifacts/transactions/context-unknown.json", b"{"), None),
            ("resolved index", lambda: self.git("add", "--", TARGET), None),
            ("changed unrelated index", lambda: (self.write("untouched.txt", b"unrelated staged change\n"), self.git("add", "--", "untouched.txt")), None),
        )
        for name, mutate, expected in cases:
            with self.subTest(case=name):
                mutate()
                before = self.state()
                before_index = index_path.read_bytes()
                if name in {"outside human edit", "inside human edit", "native provenance", "uncertain journal", "resolved index"}:
                    self.assertNotEqual(self.invoke("inspect-blocks").returncode, 0)
                result = self.invoke("resolve-blocks", "--expected", expected or binding, "--choices", '["ours","theirs"]')
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self.state(), before)
                self.assertEqual(index_path.read_bytes(), before_index)
                for path, raw in original.items():
                    self.write(path, raw)
                journal = self.root / ".codearbiter/.artifacts/transactions/context-unknown.json"
                if journal.exists():
                    journal.unlink()
                index_path.write_bytes(index)
        for choices in ([], ["ours"], ["ours", "theirs", "ours"], ["ours", "base"], ["ours", True],
                        "ours", {"content": "replacement"}, ["ours", "theirs\nhuman replacement"]):
            with self.subTest(choices=choices):
                result = self.invoke("resolve-blocks", "--expected", binding, "--choices", json.dumps(choices))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.state(), original)
                self.assertEqual(index_path.read_bytes(), index)

    def lock_time_mutation(self, kind):
        if kind == "provenance":
            record = json.loads((self.root / PROVENANCE).read_bytes())
            record["created"] = "2026-10-08"
            raw = json.dumps(record).encode() + b"\n"
            return lambda: self.write(PROVENANCE, raw)
        if kind == "source bytes":
            path = MANIFESTS["ca_version"]
            record = json.loads((self.root / path).read_bytes())
            record["description"] = "Competing source metadata, same literal version"
            raw = json.dumps(record).encode() + b"\n"
            return lambda: self.write(path, raw)
        if kind == "head":
            head = self.git("rev-parse", "HEAD").stdout.strip().decode()
            tree = self.git("rev-parse", "HEAD^{tree}").stdout.strip().decode()
            # An actual same-tree Git child retains the conflict's three blobs
            # and merge base. Fresh inspection succeeds; only its binding differs.
            competing = self.git("commit-tree", tree, "-p", head, "-m", "Competing same-tree fixture head").stdout.strip().decode()
            return lambda: self.git("update-ref", "HEAD", competing)
        self.assertEqual(kind, "index")
        index = self.root / ".git/index"
        original = index.read_bytes()
        self.write("untouched.txt", b"Competing staged fixture bytes\n")
        self.git("add", "--", "untouched.txt")
        competing = index.read_bytes()
        self.assertNotEqual(competing, original)
        index.write_bytes(original)
        # The competing index is generated by real Git and retains the actual
        # conflict stages. Copying it under the lock models a noncooperative peer.
        return lambda: index.write_bytes(competing)

    def assert_locked_refusal(self, snapshot_name, operation, binding, selection, kind):
        snapshot = getattr(_contextmergelib, snapshot_name)
        lock = self.root / ".git/index.lock"
        mutation = self.lock_time_mutation(kind)
        snapshots = []
        foreign = {}

        def actual_snapshot(*args, **kwargs):
            if snapshots:
                self.assertEqual(len(snapshots), 1)
                self.assertTrue(lock.is_file(), "mutation must occur inside the actual index lock")
                mutation()
                foreign["files"] = self.state()
                foreign["index"] = (self.root / ".git/index").read_bytes()
                foreign["head"] = self.git("rev-parse", "HEAD").stdout
            result = snapshot(*args, **kwargs)
            snapshots.append(result[-1]["binding"])
            return result

        reason = "stale claim binding" if snapshot_name == "_claim_snapshot" else "stale conflict binding"
        with mock.patch.object(_contextmergelib, snapshot_name, side_effect=actual_snapshot), \
                self.assertRaisesRegex(_contextmergelib.ResolutionError, reason):
            operation(self.root, binding, selection)
        self.assertEqual(len(snapshots), 2, "both real inspections must succeed before the CAS refusal")
        self.assertEqual(snapshots[0], binding)
        self.assertNotEqual(snapshots[1], binding)
        self.assertEqual(self.state(), foreign["files"])
        self.assertEqual((self.root / ".git/index").read_bytes(), foreign["index"])
        self.assertEqual(self.git("rev-parse", "HEAD").stdout, foreign["head"])
        self.assertFalse(lock.exists(), "the refused operation must clean up its owned lock")

    def test_claim_refresh_rechecks_valid_foreign_state_inside_index_lock(self):
        self.prepare_claims()
        selection = [{"field": "ca_version", "before": "2.25.0", "after": "2.25.7"}]
        target = (self.root / TARGET).read_bytes()
        for kind in ("provenance", "source bytes", "head", "index"):
            with self.subTest(changed=kind):
                try:
                    binding = _contextmergelib.inspect_claims(self.root)["binding"]
                    self.assert_locked_refusal("_claim_snapshot", _contextmergelib.refresh_claims,
                                               binding, selection, kind)
                finally:
                    self.write(TARGET, target)

    def test_multi_block_resolution_rechecks_valid_foreign_state_inside_index_lock(self):
        self.prepare_blocks()
        target = (self.root / TARGET).read_bytes()
        for kind in ("provenance", "head", "index"):
            with self.subTest(changed=kind):
                try:
                    binding = _contextmergelib.inspect_blocks(self.root)["binding"]
                    self.assert_locked_refusal("_snapshot", _contextmergelib.resolve_blocks,
                                               binding, ["ours", "theirs"], kind)
                finally:
                    self.write(TARGET, target)

    def test_context_merge_restore_head_legacy_conflict(self):
        before = self.state()
        index = (self.root / ".git/index").read_bytes()
        with mock.patch.object(_artifactlib, "context_writer_qualified", return_value=True), \
                mock.patch.object(_bashguardlib, "block", side_effect=lambda code, _message: (_ for _ in ()).throw(RuntimeError(code))):
            for command in ("git restore --source=HEAD --worktree -- " + TARGET,
                            "echo replacement > " + TARGET):
                with self.subTest(command=command), self.assertRaisesRegex(RuntimeError, "H-22"):
                    _bashguardlib._check_h22_state(command, str(self.root))
            _bashguardlib._check_h22_state(f'python "{CLI}" --root "{self.root}" inspect', str(self.root))
        inspected = self.inspect()
        self.assertEqual(inspected["head"], self.head)
        self.assertEqual(inspected["target"], TARGET)
        self.assertEqual(inspected["head_sha256"], hashlib.sha256(self.ours).hexdigest())
        self.assertEqual(self.state(), before)
        result = self.invoke("restore-head", "--expected", inspected["binding"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "restored")
        self.assertEqual(self.state(), {**before, TARGET: self.ours})
        self.assertEqual((self.root / ".git/index").read_bytes(), index)
        self.assertEqual(len(self.git("ls-files", "-u", "--", TARGET).stdout.splitlines()), 3)

    def test_context_merge_refusals_preserve_state(self):
        inspected = self.inspect()
        original = self.state()
        index_path = self.root / ".git/index"
        index = index_path.read_bytes()
        merge = (self.root / ".git/MERGE_HEAD").read_bytes()

        def incoming_native():
            self.git("merge", "--abort")
            self.git("checkout", "-q", "incoming")
            self.write(PROVENANCE, b'{"schema":2,"doc":"code-map"}\n')
            self.commit("incoming native ownership")
            self.git("checkout", "-q", "current")
            self.assertEqual(self.git("merge", "--no-commit", "incoming", check=False).returncode, 1)
            self.write(PROVENANCE, original[PROVENANCE])

        cases = (
            ("stale binding", lambda: None, ["restore-head", "--expected", "0" * 64]),
            ("worktree changed", lambda: self.write(TARGET, original[TARGET] + b"human note\n"), None),
            ("provenance changed", lambda: self.write(PROVENANCE, original[PROVENANCE] + b"\n"), None),
            ("native provenance", lambda: self.write(PROVENANCE, b'{"schema":2,"doc":"code-map"}\n'), None),
            ("uncertain journal", lambda: self.write(".codearbiter/.artifacts/transactions/context-unknown.json", b"{"), None),
            ("missing conflict", lambda: (self.root / ".git/MERGE_HEAD").unlink(), None),
            ("changed merge", lambda: (self.root / ".git/MERGE_HEAD").write_text(self.head + "\n"), None),
            ("changed head", lambda: self.git("update-ref", "HEAD", self.git("rev-parse", "HEAD^").stdout.strip().decode()), None),
            ("changed index", lambda: self.git("add", "--", "untouched.txt"), None),
            ("arbitrary target", lambda: None, ["restore-head", "--expected", inspected["binding"], "--target", "untouched.txt"]),
            ("arbitrary revision", lambda: None, ["restore-head", "--expected", inspected["binding"], "--revision", "incoming"]),
            ("arbitrary content", lambda: None, ["restore-head", "--expected", inspected["binding"], "--content", "replacement"]),
            ("incoming native", incoming_native, None),
        )
        for name, mutate, arguments in cases:
            with self.subTest(case=name):
                if name == "changed index":
                    self.write("untouched.txt", b"staged unrelated change\n")
                mutate()
                before = self.state()
                before_index = index_path.read_bytes()
                if name in {"native provenance", "uncertain journal", "incoming native"}:
                    self.assertNotEqual(self.invoke("inspect").returncode, 0,
                                        "fresh inspection must refuse native or uncertain ownership")
                result = self.invoke(*(arguments or ["restore-head", "--expected", inspected["binding"]]))
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self.state(), before)
                self.assertEqual(index_path.read_bytes(), before_index)
                for path, raw in original.items():
                    self.write(path, raw)
                journal = self.root / ".codearbiter/.artifacts/transactions/context-unknown.json"
                if journal.exists():
                    journal.unlink()
                index_path.write_bytes(index)
                (self.root / ".git/MERGE_HEAD").write_bytes(merge)
                self.git("update-ref", "HEAD", self.head)


if __name__ == "__main__":
    unittest.main()
