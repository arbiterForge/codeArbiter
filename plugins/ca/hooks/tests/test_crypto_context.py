"""H-09b short-name classification against real staged diffs (#678).

O678-05: both admission paths distinguish return-code identifiers from cipher
configuration without a security-pass marker. No hook or git reader is mocked.
"""
import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CryptoContextHookTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self._git("init", "-q", "-b", "feat/context")
        self._git("config", "user.email", "h@example.com")
        self._git("config", "user.name", "harness")
        self._git("config", "commit.gpgSign", "false")
        os.makedirs(os.path.join(self.root, ".codearbiter"))
        self._write(".codearbiter/CONTEXT.md",
                    "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n")
        self._write("sample.py", "value = 1\n")
        self._git("add", ".codearbiter/CONTEXT.md", "sample.py")
        self._git("commit", "-q", "-m", "seed")

    def _run(self, args, timeout=60, **kwargs):
        return subprocess.run(
            args, cwd=self.root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            env={**os.environ, "CLAUDE_PROJECT_DIR": self.root}, **kwargs)

    def _git(self, *args):
        result = self._run(["git", *args])
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def _write(self, rel, content):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as stream:
            stream.write(content)

    def _stage(self, content, rel="sample.py"):
        self._write(rel, content)
        self._git("add", rel)
        self.assertIn(content.splitlines()[0],
                      self._git("diff", "--cached", "--", rel).stdout)
        self.assertFalse(os.path.exists(os.path.join(
            self.root, ".codearbiter", ".markers", "security-gate-passed")))

    def _pre_bash(self, timeout=60, command="git commit -m 'short name context'"):
        payload = {"tool_name": "Bash", "tool_input": {
            "command": command}}
        return self._run([sys.executable, os.path.join(HOOKS, "pre-bash.py")],
                         input=json.dumps(payload), timeout=timeout)

    def _git_enforce(self, timeout=60):
        return self._run([sys.executable, os.path.join(HOOKS, "git-enforce.py"),
                          "pre-commit"], timeout=timeout)

    def _seed_and_stage_context(self, seed, candidate, rel="sample.py"):
        self._write(rel, seed)
        self._git("add", rel)
        self._git("commit", "-q", "-m", "seed contextual boundary")
        self._stage(candidate, rel)

    def _assert_admission(self, blocked):
        for hook, code in ((self._pre_bash, 2), (self._git_enforce, 1)):
            with self.subTest(hook=hook.__name__):
                result = hook()
                self.assertEqual(result.returncode, code if blocked else 0, result.stderr)
                self.assertEqual("H-09b" in result.stderr, blocked)

    def _record_context_pass(self):
        result = self._run([sys.executable, os.path.join(HOOKS, "security-pass.py")])
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(self.root, ".codearbiter", ".markers", "security-gate-passed"),
                  encoding="utf-8") as stream:
            return stream.read()

    def test_rsa_key_type_requires_approval_in_both_gates(self):
        # RSA-01: real staged bytes, with neither consumer nor Git mocked.
        self._stage("key_type = RSA\n")
        self._assert_admission(True)

    def test_rsa_key_type_pass_binds_exact_line(self):
        # RSA-02/03: genuine producer identity, stale refusal, ordinary controls.
        self._stage("key_type = RSA\n")
        marker = self._record_context_pass()
        self.assertIn(hashlib.sha256(b"key_type = RSA").hexdigest(), marker.splitlines())
        self._assert_admission(False)
        self._write("sample.py", "key_type = RSA  # changed configuration\n")
        self._git("add", "sample.py")
        self._assert_admission(True)
        self._write("sample.py", "name = RSA\nrsa = response_status_average\nrc2 = 2\n")
        self._git("add", "sample.py")
        self._assert_admission(False)

    def _with_diff_response(self, entry, diff, exit_code=0):
        # Fault injection at the Git transport only; real gate decisions run.
        response = ("raise subprocess.TimeoutExpired(args,0.01)" if exit_code == "timeout" else
                    f"return subprocess.CompletedProcess(args,{exit_code},{diff!r},'injected context fault')")
        script = (
            "import subprocess,sys,runpy\n"
            "real_run=subprocess.run\n"
            "def run(args,**kwargs):\n"
            " if 'diff' in args and '--name-only' not in args:\n"
            f"  {response}\n"
            " return real_run(args,**kwargs)\n"
            "subprocess.run=run\n"
            f"sys.path.insert(0,{HOOKS!r})\n"
            f"sys.argv={[entry, *(['pre-commit'] if entry == 'git-enforce.py' else [])]!r}\n"
            f"runpy.run_path({os.path.join(HOOKS, entry)!r},run_name='__main__')\n")
        payload = json.dumps({"tool_name": "Bash", "tool_input": {
            "command": "git commit -m 'context transport'"}}) if entry == "pre-bash.py" else None
        return self._run([sys.executable, "-B", "-c", script], input=payload)

    def test_context_pass_binds_destination_and_path(self):
        # O678-A3/A4: identical added lines do not launder a changed destination.
        seed = 'from Crypto.Cipher import (\n    AES,\n)\n'
        candidate = seed.replace("AES", "DES")
        self._seed_and_stage_context(seed, candidate)
        marker = self._record_context_pass()
        self.assertTrue(any(line.startswith("ctx-v1:") for line in marker.splitlines()), marker)
        self._assert_admission(False)
        self._write("sample.py", candidate.replace("import (", "import ( # changed context"))
        self._git("add", "sample.py")
        self._assert_admission(True)
        self._write("sample.py", candidate)
        self._git("add", "sample.py")
        self._assert_admission(False)
        self._write("second.py", candidate)
        self._git("add", "second.py")
        self._assert_admission(True)

    def test_legacy_line_marker_does_not_cover_context(self):
        # O678-A4: raw-line digest and contextual proof have disjoint domains.
        seed = 'from Crypto.Cipher import (\n    AES,\n)\n'
        self._seed_and_stage_context(seed, seed.replace("AES", "DES"))
        os.makedirs(os.path.join(self.root, ".codearbiter", ".markers"))
        legacy = hashlib.sha256(b"    DES,").hexdigest()
        self._write(".codearbiter/.markers/security-gate-passed", legacy + "\n")
        self._assert_admission(True)

    def test_index_and_worktree_context_are_not_mixed(self):
        # O678-A2/A3: the producer covers separate snapshots, never mixed context.
        seed = 'from Crypto.Cipher import (\n    AES,\n)\n'
        crypto = seed.replace("AES", "DES")
        ordinary = 'DES = destinations[0]\nitems = (\n    DES,\n)\n'
        self._seed_and_stage_context(seed, crypto)
        self._write("sample.py", ordinary)
        self._assert_admission(True)
        marker = self._record_context_pass()
        self.assertTrue(any(line.startswith("ctx-v1:") for line in marker.splitlines()), marker)
        self._assert_admission(False)

    def test_staged_ordinary_and_future_worktree_crypto_use_separate_context(self):
        # O678-A2: a plain commit reads index; -a reads the future staged source.
        seed = 'DES = destinations[0]\nitems = (\n    destinations[0],\n)\n'
        ordinary = seed.replace('    destinations[0],', '    DES,')
        self._seed_and_stage_context(seed, ordinary)
        self._write("sample.py", 'from Crypto.Cipher import (\n    DES,\n)\n')
        self._assert_admission(False)
        result = self._pre_bash(command="git commit -a -m 'future context'")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("H-09b", result.stderr)

    def test_context_extent_and_noncode_headers(self):
        # O678-A1/A2: lexical import context, not strings/comments/hunk labels.
        cases = (
            ("far header", 'from Crypto.Cipher import (\n' + '    # item\n' * 8 + '    AES,\n)\n', True),
            ("triple quote", 'message = """\nfrom Crypto.Cipher import (\n    AES,\n)\n"""\n', False),
            ("comment", '# from Crypto.Cipher import (\nitems = (\n    AES,\n)\n', False),
            ("closed unrelated import", 'from Crypto.Cipher import (\n    ARC2,\n)\n'
             'items = (\n    AES,\n)\n', False),
            ("unterminated string", 'message = """\nfrom Crypto.Cipher import (\n    AES,\n)\n', True),
        )
        for name, seed, blocked in cases:
            with self.subTest(case=name):
                self._seed_and_stage_context(seed, seed.replace("AES", "DES"))
                self._assert_admission(blocked)

    def test_context_transport_failures_do_not_admit_or_record(self):
        # O678-A4: malformed/unavailable context is not an ordinary empty scan.
        seed = 'from Crypto.Cipher import (\n    AES,\n)\n'
        self._seed_and_stage_context(seed, seed.replace("AES", "DES"))
        diff = self._git("diff", "--cached", "--unified=2147483647").stdout
        os.makedirs(os.path.join(self.root, ".codearbiter", ".markers"))
        self._write(".codearbiter/.markers/security-gate-passed", "existing-review\n")
        faults = (("truncated", diff.rsplit(" )", 1)[0], 0),
                  ("wrong extent", diff.replace("+1,3", "+2,3"), 0),
                  ("missing hunk", "\n".join(line for line in diff.splitlines()
                                             if not line.startswith("@@")) + "\n", 0),
                  ("unavailable", "", 1),
                  ("timeout", "", "timeout"))
        for name, faulty, exit_code in faults:
            with self.subTest(case=name):
                for entry, blocked_exit in (("pre-bash.py", 2), ("git-enforce.py", 1),
                                            ("security-pass.py", 1)):
                    with self.subTest(entry=entry):
                        result = self._with_diff_response(entry, faulty, exit_code)
                        self.assertEqual(result.returncode, blocked_exit, result.stderr)
                        if entry != "security-pass.py":
                            self.assertIn("H-09b", result.stderr)
                        else:
                            with open(os.path.join(self.root, ".codearbiter", ".markers",
                                                   "security-gate-passed"), encoding="utf-8") as stream:
                                self.assertEqual(stream.read(), "existing-review\n")

    def test_deep_ordinary_import_does_not_stall_admission(self):
        lines = ("import " + "a." * 32 + "helpers",
                 "from sample import " + ", ".join(f"helper{i}" for i in range(32)),
                 "from sample import (" + ", ".join(
                     f"helper{i} as local{i}" for i in range(32)) + ")")
        for line in lines:
            self._stage(line + "\n")
            for hook in (self._pre_bash, self._git_enforce):
                with self.subTest(line=line, hook=hook.__name__):
                    try:
                        result = hook(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.fail("Ordinary import admission exceeded the 3-second bound")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn("H-09b", result.stderr)

    def test_grouped_and_prior_aliased_import_changes_still_block(self):
        lines = (
            'from Crypto.Cipher import (DES as chosen,)',
            'from Crypto.Cipher import (AES, DES as chosen)',
            'from Crypto.Cipher import AES as regular, DES as chosen',
            'from Crypto.Cipher import (AES as regular, DES as chosen)',
            'from Crypto.Cipher import(DES as chosen,)',
            'from Crypto.Cipher import (AES as regular, DES as chosen,) # legacy',
            'import os as system, rsa as chosen',
            'from Crypto.PublicKey import (RSA as chosen,)',
        )
        for line in lines:
            with self.subTest(line=line):
                if "DES" in line:
                    seed_line = line.replace("DES", "AES")
                    use = 'cipher = chosen.new(b"abcdefgh", chosen.MODE_ECB)\n'
                elif "RSA" in line:
                    seed_line = line.replace("RSA", "DSA")
                    use = 'key = chosen.generate(2048)\n'
                else:
                    seed_line = line.replace("rsa", "os")
                    use = 'value = chosen\n'
                self._write("sample.py", seed_line + "\n" + use)
                self._git("add", "sample.py")
                self._git("commit", "-q", "-m", "seed contextual import")
                self._stage(line + "\n" + use)
                diff = self._git("diff", "--cached", "--unified=0", "--", "sample.py").stdout
                added = [item[1:] for item in diff.splitlines()
                         if item.startswith("+") and not item.startswith("+++")]
                self.assertEqual(added, [line])
                for hook, blocked_exit in ((self._pre_bash, 2), (self._git_enforce, 1)):
                    with self.subTest(hook=hook.__name__):
                        result = hook()
                        self.assertEqual(result.returncode, blocked_exit, result.stderr)
                        self.assertIn("H-09b", result.stderr)

    def test_identical_added_item_uses_its_real_staged_context(self):
        # O678-A1 / R6: the added line is identical; its enclosing context is not.
        cases = (
            ("crypto", 'from Crypto.Cipher import (\n    AES,\n)\n',
             'from Crypto.Cipher import (\n    DES,\n)\n', (2, 1)),
            ("ordinary", 'DES = destinations[0]\nitems = (\n    destinations[0],\n)\n',
             'DES = destinations[0]\nitems = (\n    DES,\n)\n', (0, 0)),
        )
        for name, seed, candidate, expected in cases:
            with self.subTest(case=name):
                self._write("sample.py", seed)
                self._git("add", "sample.py")
                self._git("commit", "-q", "-m", "seed identical-line context")
                self._stage(candidate)
                diff = self._git("diff", "--cached", "--unified=0", "--", "sample.py").stdout
                added = [line[1:] for line in diff.splitlines()
                         if line.startswith("+") and not line.startswith("+++")]
                self.assertEqual(added, ['    DES,'])
                for hook, expected_exit in zip((self._pre_bash, self._git_enforce), expected):
                    with self.subTest(hook=hook.__name__):
                        result = hook()
                        self.assertEqual(result.returncode, expected_exit, result.stderr)
                        self.assertEqual("H-09b" in result.stderr, expected_exit != 0)

    def test_candidate_horizontal_spacing_is_bounded(self):
        # Isolate the prefilter as well as exercising the real admission paths.
        script = ("import sys;sys.path.insert(0,sys.argv[1]);"
                  "import _sensitivelib as s;"
                  "print(int(s._is_context_item_line(sys.argv[2])))")
        for whitespace in (" " * 3000, "\t" * 3000):
            with self.subTest(whitespace=repr(whitespace[0])):
                try:
                    result = self._run([sys.executable, "-B", "-c", script,
                                        HOOKS, "rc2" + whitespace + "=2"], timeout=3)
                except subprocess.TimeoutExpired:
                    self.fail("Ordinary candidate prefilter exceeded the 3-second bound")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "0")

    def test_ordinary_horizontal_spacing_has_bounded_admission(self):
        # R9-S1: optional whitespace partitions must not stall ordinary code.
        cases = (("spaces", "rc2" + " " * 3000 + "=2\n"),
                 ("tabs", "rc2" + "\t" * 3000 + "=2\n"),
                 ("comparison", "DES" + " " * 3000 + "==2\n"))
        for name, source in cases:
            self._stage(source)
            for hook in (self._pre_bash, self._git_enforce):
                with self.subTest(case=name, hook=hook.__name__):
                    try:
                        result = hook(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.fail("Ordinary spaced identifier exceeded the 3-second bound")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn("H-09b", result.stderr)

    def test_candidate_spacing_does_not_normalize_context_approval(self):
        # Candidate-only simplification must never change destination binding.
        seed = "from Crypto.Cipher import (\n    AES ,\n)\n"
        candidate = seed.replace("AES", "DES")
        self._seed_and_stage_context(seed, candidate)
        marker = self._record_context_pass()
        self.assertTrue(any(line.startswith("ctx-v1:") for line in marker.splitlines()))
        self._assert_admission(False)
        self._write("sample.py", candidate.replace("DES ,", "DES  ,"))
        self._git("add", "sample.py")
        self._assert_admission(True)
        self._write("sample.py", candidate)
        self._git("add", "sample.py")
        self._assert_admission(False)

    def test_return_code_diff_allowed_by_pre_bash_without_marker(self):
        self._stage("rc2 = 2\nrc2, out2, err2 = invoke()\nself.assertEqual(rc2, 2)\n")
        result = self._pre_bash()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("H-09b", result.stderr)

    def test_cross_line_crypto_calls_fail_closed_in_both_gates(self):
        # CR758-01: joined matching must not produce an unbound crypto verdict.
        for extra in ("", "const prior = md5;\n"):
            with self.subTest(other_sensitive_line=bool(extra)):
                source = "const selected = rc2\n(key);\n" + extra
                self._stage(source, "sample.js")
                diff = self._git("diff", "--cached", "--unified=0", "--", "sample.js").stdout
                added = [line[1:] for line in diff.splitlines()
                         if line.startswith("+") and not line.startswith("+++")]
                self.assertEqual(added, source.splitlines())
                self._assert_admission(True)

    def test_cross_line_crypto_cannot_borrow_another_line_approval(self):
        # An already approved same-line hazard cannot cover an unbound call.
        self._stage("const prior = md5;\n", "sample.js")
        marker = self._record_context_pass()
        self._assert_admission(False)
        self._write("sample.js", "const selected = rc2\n(key);\nconst prior = md5;\n")
        self._git("add", "sample.js")
        self._assert_admission(True)
        result = self._run([sys.executable, os.path.join(HOOKS, "security-pass.py")])
        self.assertEqual(result.returncode, 1, result.stderr)
        with open(os.path.join(self.root, ".codearbiter", ".markers", "security-gate-passed"),
                  encoding="utf-8") as stream:
            self.assertEqual(stream.read(), marker)

    def _assert_new_import_approval(self, mode):
        # CR758-02 / R11-S1: full-source producers must retain Option A proof.
        for index, item in enumerate(("DES,", "AES, DES,",
                                      "AES as regular, DES as chosen,")):
            with self.subTest(mode=mode, item=item):
                rel = f"new_{index}.py"
                source = "from Crypto.Cipher import (\n    " + item + "\n)\n"
                self._write(rel, source)
                if mode == "unborn":
                    self._git("symbolic-ref", "HEAD", f"refs/heads/feat/unborn-{index}")
                    self.assertEqual(self._run(["git", "rev-parse", "--verify", "HEAD"]).returncode, 128)
                if mode != "untracked":
                    self._git("add", rel)
                    self._assert_admission(True)
                marker = self._record_context_pass()
                self.assertTrue(any(line.startswith("ctx-v1:") for line in marker.splitlines()), marker)
                self._git("add", rel)
                self._assert_admission(False)
                self._write(rel, source.replace("import (", "import ( # changed context"))
                self._git("add", rel)
                self._assert_admission(True)
                self._write(rel, source)
                self._git("add", rel)
                self._assert_admission(False)
                self._write(f"other_{index}.py", source)
                self._git("add", f"other_{index}.py")
                self._assert_admission(True)
                self._record_context_pass()

    def test_wholly_new_staged_import_retains_context_approval(self):
        self._assert_new_import_approval("staged")

    def test_untracked_import_retains_context_approval(self):
        self._assert_new_import_approval("untracked")

    def test_unborn_import_retains_context_approval(self):
        self._assert_new_import_approval("unborn")

    def _assert_producer_refuses_existing_approval(self, marker):
        result = self._run([sys.executable, os.path.join(HOOKS, "security-pass.py")])
        self.assertEqual(result.returncode, 1, result.stderr)
        with open(os.path.join(self.root, ".codearbiter", ".markers", "security-gate-passed"),
                  encoding="utf-8") as stream:
            self.assertEqual(stream.read(), marker)

    def test_cross_line_crypto_cannot_borrow_context_approval(self):
        # CR758-01 / R12-C1: only the recognized import span owns this proof.
        valid = "from Crypto.Cipher import (\n    DES,\n)\n"
        unsupported = "const selected = rc2\n(key);\n"
        self._stage(valid)
        marker = self._record_context_pass()
        self.assertTrue(any(line.startswith("ctx-v1:") for line in marker.splitlines()), marker)
        self._assert_admission(False)
        for source in (unsupported + valid, valid + unsupported):
            with self.subTest(source=source):
                self._write("sample.py", source)
                self._git("add", "sample.py")
                self._assert_admission(True)
                self._assert_producer_refuses_existing_approval(marker)

    def test_cross_file_crypto_join_cannot_borrow_context_approval(self):
        # A flattened match cannot use the next file's valid context identity.
        self._stage("from Crypto.Cipher import (\n    DES,\n)\n")
        marker = self._record_context_pass()
        self.assertTrue(any(line.startswith("ctx-v1:") for line in marker.splitlines()), marker)
        self._assert_admission(False)
        self._write("a.js", "const selected = rc2\n")
        self._write("b.js", "(key);\n")
        self._git("add", "a.js", "b.js")
        diff = self._git("diff", "--cached", "--unified=0").stdout
        added = [line[1:] for line in diff.splitlines()
                 if line.startswith("+") and not line.startswith("+++")]
        self.assertEqual(added[:2], ["const selected = rc2", "(key);"])
        self._assert_admission(True)
        self._assert_producer_refuses_existing_approval(marker)

    def test_final_import_item_tails_use_context_not_bare_names(self):
        # R7-S1: final items in the same import need no trailing comma.
        for tail in ("", " # chosen", ")", ",) # chosen"):
            closing = "" if ")" in tail else ")\n"
            for crypto in (True, False):
                with self.subTest(tail=tail, crypto=crypto):
                    header = ("from Crypto.Cipher import (\n" if crypto else
                              "DES = 1\nAES = 2\nitems = (\n")
                    seed = header + "    AES" + tail + "\n" + closing
                    candidate = header + "    DES" + tail + "\n" + closing
                    self._seed_and_stage_context(seed, candidate)
                    diff = self._git("diff", "--cached", "--unified=0").stdout
                    added = [line[1:] for line in diff.splitlines()
                             if line.startswith("+") and not line.startswith("+++")]
                    self.assertEqual(added, ["    DES" + tail])
                    self._assert_admission(crypto)

    def test_large_ordinary_context_has_bounded_admission(self):
        # R7-S2: a sub-limit destination must not be re-split for every row.
        source = "DES = 1\nitems = (\n    DES,\n)\n" + "value = 0\n" * 20_000
        self.assertLess(len(source.encode("utf-8")), 1_000_000)
        self._stage(source)
        for hook in (self._pre_bash, self._git_enforce):
            with self.subTest(hook=hook.__name__):
                try:
                    result = hook(timeout=3)
                except subprocess.TimeoutExpired:
                    self.fail("Ordinary contextual admission exceeded the 3-second bound")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("H-09b", result.stderr)

    def test_contextual_import_list_and_statement_boundaries(self):
        # R8-S1: the trusted import context, not a single-item line shape,
        # decides multi-item, alias, final-statement and continuation rows.
        rows = ("    DES);", "    AES, DES,", "    DES, AES,",
                "    AES as regular, DES,", "    DES, AES as regular,",
                "    AES, DES)", "    AES, DES);",
                "    DES); selected = 1", "    DES \\")
        for row in rows:
            closing = "" if ")" in row else ")\n"
            contexts = [("crypto", "from Crypto.Cipher import (\n", "", True),
                        ("text", 'message = """\nfrom Crypto.Cipher import (\n',
                         '"""\n', False)]
            if " as " not in row:
                contexts.append(("ordinary", "AES = 1\nDES = 2\nitems = (\n", "", False))
            for name, header, footer, blocked in contexts:
                with self.subTest(row=row, context=name):
                    seed = header + row.replace("DES", "AES") + "\n" + closing + footer
                    candidate = header + row + "\n" + closing + footer
                    self._seed_and_stage_context(seed, candidate)
                    diff = self._git("diff", "--cached", "--unified=0").stdout
                    added = [line[1:] for line in diff.splitlines()
                             if line.startswith("+") and not line.startswith("+++")]
                    self.assertEqual(added, [row])
                    self._assert_admission(blocked)

    def test_context_record_requires_actual_short_imported_name(self):
        # A short name in an alias, comment or following ordinary statement
        # cannot turn an AES import into a legacy-cipher contextual record.
        for row in ("    AES as DES,", "    AES, # DES", "    AES); selected = DES"):
            with self.subTest(row=row):
                closing = "" if ")" in row else ")\n"
                header = "from Crypto.Cipher import (\n"
                seed = header + row.replace("DES", "ordinary") + "\n" + closing
                candidate = header + row + "\n" + closing
                self._seed_and_stage_context(seed, candidate)
                self._assert_admission(False)

    def test_lossy_context_cannot_reuse_or_replace_approval(self):
        # R7-S3: distinct original bytes must not share a contextual identity.
        seed = b"# coding: latin-1\n# \xff\nfrom Crypto.Cipher import (\n    AES,\n)\n"
        with open(os.path.join(self.root, "sample.py"), "wb") as stream:
            stream.write(seed)
        self._git("add", "sample.py")
        self._git("commit", "-q", "-m", "seed non-UTF8 context")
        # This is the previously accepted lossy record, not a new approval:
        # both FF and FE decoded to U+FFFD under the broken implementation.
        decoded = seed.replace(b"AES", b"DES").decode("utf-8", "replace")
        destination = hashlib.sha256(decoded.encode("utf-8")).hexdigest()
        old_record = "ctx-v1:" + hashlib.sha256(json.dumps(
            ["sample.py", destination, 4, "    DES,"], separators=(",", ":")
        ).encode("utf-8")).hexdigest() + "\n"
        os.makedirs(os.path.join(self.root, ".codearbiter", ".markers"))
        marker_path = ".codearbiter/.markers/security-gate-passed"
        self._write(marker_path, old_record)
        for comment_byte in (b"\xff", b"\xfe"):
            with self.subTest(comment_byte=comment_byte):
                candidate = seed.replace(b"AES", b"DES").replace(b"\xff", comment_byte)
                with open(os.path.join(self.root, "sample.py"), "wb") as stream:
                    stream.write(candidate)
                self._git("add", "sample.py")
                self._assert_admission(True)
                result = self._run([sys.executable, os.path.join(HOOKS, "security-pass.py")])
                self.assertEqual(result.returncode, 1, result.stderr)
                with open(os.path.join(self.root, marker_path), encoding="utf-8") as stream:
                    self.assertEqual(stream.read(), old_record)

    def test_return_code_diff_allowed_by_git_enforce_without_marker(self):
        self._stage("rc2 = 2\nrc2, out2, err2 = invoke()\nself.assertEqual(rc2, 2)\n")
        result = self._git_enforce()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("H-09b", result.stderr)

    def test_cipher_config_blocked_by_pre_bash_without_marker(self):
        self._stage('cipher = "rc2"\n')
        result = self._pre_bash()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("H-09b", result.stderr)

    def test_cipher_config_blocked_by_git_enforce_without_marker(self):
        self._stage('cipher = "rc2"\n')
        result = self._git_enforce()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("H-09b", result.stderr)

    def _reviewed_api_diffs(self):
        return (
            'from Crypto.Cipher import (\n    DES as chosen,\n)\n'
            'cipher = chosen.new(b"abcdefgh", chosen.MODE_ECB)\n',
            'from Crypto.Cipher import (\n    DES as chosen, # legacy cipher\n)\n'
            'cipher = chosen.new(b"abcdefgh", chosen.MODE_ECB)\n',
            'pub = rsa.RSAPublicNumbers(65537, modulus).public_key()\n',
            'key = rsa.RSAPrivateNumbers(p,q,d,dmp1,dmq1,iqmp,pub).private_key()\n',
        )

    def test_reviewed_api_diffs_blocked_by_pre_bash_without_marker(self):
        for content in self._reviewed_api_diffs():
            with self.subTest(content=content):
                self._stage(content)
                result = self._pre_bash()
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("H-09b", result.stderr)

    def test_reviewed_api_diffs_blocked_by_git_enforce_without_marker(self):
        for content in self._reviewed_api_diffs():
            with self.subTest(content=content):
                self._stage(content)
                result = self._git_enforce()
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("H-09b", result.stderr)

    def test_standalone_cipher_value_with_unchanged_key_still_blocks(self):
        # The only added line is the quoted value, so matching its unchanged
        # cipher key cannot accidentally make either admission path pass.
        self._write("sample.py", '{\n    "cipher":\n    "aes"\n}\n')
        self._git("add", "sample.py")
        self._git("commit", "-q", "-m", "seed multiline configuration")
        self._stage('{\n    "cipher":\n    "rc2"\n}\n')
        diff = self._git("diff", "--cached", "--unified=0", "--", "sample.py").stdout
        added = [line[1:] for line in diff.splitlines()
                 if line.startswith("+") and not line.startswith("+++")]
        self.assertEqual(added, ['    "rc2"'])
        for hook, blocked_exit in ((self._pre_bash, 2), (self._git_enforce, 1)):
            with self.subTest(hook=hook.__name__):
                result = hook()
                self.assertEqual(result.returncode, blocked_exit, result.stderr)
                self.assertIn("H-09b", result.stderr)

    def test_ordinary_quoted_names_allowed_without_marker(self):
        self._stage('label = "rsa"\nmessage = "des"\n# "rc2"\n'
                    '// the label is "RC4"\nlabel = "rc2-status"\n'
                    'name = "rsa"\nmessage = "name: rsa"\n'
                    'name = "rc2-status"\nname = RSA\n')
        for hook in (self._pre_bash, self._git_enforce):
            with self.subTest(hook=hook.__name__):
                result = hook()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("H-09b", result.stderr)

    def test_standalone_cipher_value_with_trailing_syntax_still_blocks(self):
        for suffix, closing in ((" # chosen algorithm", "\n}"), ("}", "")):
            with self.subTest(suffix=suffix):
                seed = 'settings = {\n    "cipher":\n    "aes"' + suffix + closing + "\n"
                self._write("sample.py", seed)
                self._git("add", "sample.py")
                self._git("commit", "-q", "-m", "seed trailing configuration")
                self._stage(seed.replace('"aes"', '"rc2"'))
                diff = self._git("diff", "--cached", "--unified=0", "--", "sample.py").stdout
                added = [line[1:] for line in diff.splitlines()
                         if line.startswith("+") and not line.startswith("+++")]
                self.assertEqual(added, ['    "rc2"' + suffix])
                for hook, blocked_exit in ((self._pre_bash, 2), (self._git_enforce, 1)):
                    with self.subTest(hook=hook.__name__):
                        result = hook()
                        self.assertEqual(result.returncode, blocked_exit, result.stderr)
                        self.assertIn("H-09b", result.stderr)

    def test_multiline_java_factory_value_still_blocks(self):
        cases = (("javax.crypto.Cipher", "AES", "DES", ");"),
                 ("java.security.KeyFactory", "EC", "RSA", ");"),
                 ("javax.crypto.Cipher", "AES", "DES", "); // legacy cipher"))
        for factory, old, new, ending in cases:
            with self.subTest(factory=factory, ending=ending):
                seed = ('class Sample { void configure() throws Exception {\n'
                        f'    Object selected = {factory}.getInstance(\n'
                        f'        "{old}"{ending}\n' + '} }\n')
                self._write("Sample.java", seed)
                self._git("add", "Sample.java")
                self._git("commit", "-q", "-m", "seed multiline Java factory")
                self._stage(seed.replace(f'"{old}"', f'"{new}"'), "Sample.java")
                diff = self._git("diff", "--cached", "--unified=0", "--", "Sample.java").stdout
                added = [line[1:] for line in diff.splitlines()
                         if line.startswith("+") and not line.startswith("+++")]
                self.assertEqual(added, [f'        "{new}"{ending}'])
                for hook, blocked_exit in ((self._pre_bash, 2), (self._git_enforce, 1)):
                    with self.subTest(hook=hook.__name__):
                        result = hook()
                        self.assertEqual(result.returncode, blocked_exit, result.stderr)
                        self.assertIn("H-09b", result.stderr)


if __name__ == "__main__":
    unittest.main()
