#!/usr/bin/env python3
"""Bounded read-only Python diagnostics, not a general interpreter exemption."""
import importlib.util
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / 'core' / 'pysrc'))
import _bashguardlib as guards


class LiteralPythonReadTest(unittest.TestCase):
    def command(self, body, style='posix', marker='PY'):
        if style == 'powershell':
            return "@'\n" + body + "\n'@ | python -I -B -"
        return "python -I -B - <<'" + marker + "'\n" + body + '\n' + marker

    def body(self, path='.codearbiter/overrides.log'):
        return "import subprocess\nprint(subprocess.check_output(['git', 'show', 'HEAD:" + path + "'], text=True))"

    def test_literal_reads_in_both_shells_have_a_read_only_guard_view(self):
        for path in ('.codearbiter/overrides.log', '.codearbiter/CONTEXT.md',
                     '.codearbiter/decisions/0001-seed.md'):
            for style in ('posix', 'powershell'):
                for newline in ('\n', '\r\n'):
                    with self.subTest(path=path, style=style, newline=repr(newline)):
                        command = self.command(self.body(path), style).replace('\n', newline)
                        view = guards._literal_python_read_view(command)
                        self.assertEqual(view, 'git show HEAD:' + path)
                        self.assertFalse(guards._interp_protected_write(
                            view, guards.LOG_INTERP_RE, guards.LOG_NAME_RE))

    def test_literal_path_reads_and_batched_prints(self):
        body = ("from pathlib import Path\nimport subprocess\n"
                "print(Path('.codearbiter/overrides.log').exists())\n"
                "print(Path('.codearbiter/CONTEXT.md').read_text(encoding='utf-8'))\n"
                "print(subprocess.check_output(['git','show','HEAD:.codearbiter/overrides.log'],text=True))")
        for style in ('posix', 'powershell'):
            view = guards._literal_python_read_view(self.command(body, style))
            self.assertEqual(view.splitlines(), [
                'cat .codearbiter/overrides.log', 'cat .codearbiter/CONTEXT.md',
                'git show HEAD:.codearbiter/overrides.log',
            ])

    def test_unknown_code_and_import_shadowing_are_not_exempted(self):
        bodies = [
            self.body() + "\nopen('.codearbiter/overrides.log','w').write('bad')",
            self.body().replace("'show'", "'checkout'"),
            self.body().replace('text=True', 'shell=True'),
            self.body().replace('text=True', "cwd='/other',text=True"),
            self.body().replace('text=True', "env={},text=True"),
            self.body().replace('text=True', "stdout=open('.codearbiter/overrides.log','w')"),
            self.body().replace('subprocess.check_output', 'subprocess.run'),
            self.body().replace("['git', 'show',", "['git', '--no-pager', 'show',"),
            self.body().replace('HEAD:', '--output='),
            "from pathlib import Path\nprint(Path('.codearbiter/overrides.log').write_text('bad'))",
            "import subprocess as sp\n" + self.body().split('\n')[1].replace('subprocess.', 'sp.'),
            "import subprocess\nsubprocess = unknown\n" + self.body().split('\n')[1],
            self.body().replace('print(', 'custom('),
            self.body().replace('text=True))', "text=True),file=open('.codearbiter/overrides.log','w'))"),
            self.body().replace('HEAD:.codearbiter/overrides.log', 'HEAD:.codearbiter/../outside'),
            self.body().replace('HEAD:.codearbiter/overrides.log', 'HEAD:.markers/security-gate-passed'),
            self.body().replace("'HEAD:.codearbiter/overrides.log'", "f'HEAD:{secret}'"),
            "exec(\"print(Path('.codearbiter/overrides.log').read_text())\")",
        ]
        for body in bodies:
            for style in ('posix', 'powershell'):
                command = self.command(body, style)
                with self.subTest(body=body[:90], style=style):
                    view = guards._literal_python_read_view(command)
                    self.assertTrue(view == command or (
                        view.startswith('python -I -B -\n') and view.endswith(command)
                    ), 'unknown source was hidden instead of retained for all guards')
        command = self.command(self.body()).replace(' -I', '')
        self.assertEqual(guards._literal_python_read_view(command), command,
                         'nonisolated imports may be replaced by workspace modules')

    def test_shell_boundaries_expansion_and_size_limits_remain_closed(self):
        good = self.command(self.body())
        bad = [good + "\nrm .codearbiter/overrides.log",
               good.replace("<<'PY'", '<<PY'),
               good.replace("<<'PY'", "<<-'PY'"),
               good.replace(' -I ', ' -I -c '),
               good.replace('\n', '\r'),
               good.replace('\nprint(', '\nPY\nprint('),
               good.replace("'PY'", "'PY'; rm .codearbiter/overrides.log"),
               self.command(self.body(), 'powershell') + ' > .codearbiter/overrides.log',
               self.command(self.body(), 'powershell').replace("@'", '@"', 1),
               self.command(self.body(), 'powershell').replace("\nprint", "\n'@; rm .codearbiter/overrides.log\nprint"),
               self.command(self.body(), 'powershell').replace("\nprint", "\n\u2019@; rm .codearbiter/overrides.log\nprint"),
               self.command('#' * 33000 + '\n' + self.body())]
        for command in bad:
            with self.subTest(command=command[:100]):
                view = guards._literal_python_read_view(command)
                self.assertTrue(view == command or (
                    view.startswith('python -I -B -\n') and view.endswith(command)
                ))

    def test_literal_validation_data_does_not_select_verifier_authority(self):
        import json
        import _artifactauthoritylib as authority
        helper = ROOT / "core/pysrc/debug-handoff.py"
        data = json.dumps({"source": "artifact-authority's result", "path": ".codearbiter/overrides.log"})
        command = "@'\n" + data + "\n'@ | python -B \"" + str(helper) + "\" validate"
        view = guards._debug_validation_command_view(command)
        self.assertNotEqual(view, command)
        self.assertNotIn("artifact-authority", view)
        self.assertIsNone(authority._verification_selector({
            "tool_name": "exec_command", "tool_input": {"cmd": command},
        }))

    def test_complete_hook_preserves_read_access_and_actual_write_denials(self):
        spec = importlib.util.spec_from_file_location('fixture_hooks', HERE / 'test_hook_guards.py')
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        fixture.PRE_BASH = str(ROOT / 'core/pysrc/pre-bash.py')
        with tempfile.TemporaryDirectory() as temp:
            repo = fixture.make_fixture(temp, 'feature/readonly')
            for path, tag in (('.codearbiter/overrides.log', 'H-05'),
                              ('.codearbiter/decisions/0001-seed.md', 'H-11'),
                              ('.codearbiter/CONTEXT.md', 'H-18')):
                for style in ('posix', 'powershell'):
                    body = self.body(path)
                    allowed = fixture.run_hook(repo, self.command(body, style))
                    self.assertEqual(allowed.returncode, 0, allowed.stderr)
                    denied = fixture.run_hook(repo, self.command(body + f"\nopen({path!r},'w').write('bad')", style))
                    self.assertEqual(denied.returncode, 2, f'{style} {path}: {denied.stderr}')
                    self.assertIn('[' + tag + ']', denied.stderr)
                before = (Path(repo) / path).read_bytes()
                result = subprocess.run([sys.executable, '-I', '-B', '-c', self.body(path)],
                                        cwd=repo, capture_output=True, check=True, timeout=15)
                self.assertTrue(result.stdout)
                self.assertEqual((Path(repo) / path).read_bytes(), before)


class CompoundReadRegression(unittest.TestCase):
    targets = (
        ('.codearbiter/CONTEXT.md', 'H-18', guards.CONTEXT_INTERP_RE, guards.CONTEXT_NAME_RE),
        ('.codearbiter/overrides.log', 'H-05', guards.LOG_INTERP_RE, guards.LOG_NAME_RE),
        ('.codearbiter/decisions/0001-seed.md', 'H-11', guards.DECISIONS_INTERP_RE, guards.DECISIONS_NAME_RE),
    )

    def reader(self):
        # The reported command shape, with portable fixture installation paths.
        return ("& 'C:/runtime/python.exe' -B -X utf8 "
                "'C:/plugins/ca-codex/hooks/knowledge.py' read security-controls")

    def test_actual_knowledge_reader_then_protected_file_reads(self):
        for path, tag, interp, names in self.targets:
            for separator in ('; ', '\n', '\r\n', ' && ', ' || '):
                command = self.reader() + separator + "Get-Content -Raw '" + path + "'"
                with self.subTest(tag=tag, separator=repr(separator)):
                    self.assertFalse(guards._interp_protected_write(command, interp, names),
                                     'Interpreter cannot inherit a later read statement operand')

    def denial_commands(self, path):
        return [
            f'python tool.py {path}',
            f'python -m tool {path}',
            f'python -c "print(1);open(\'{path}\',\'w\').write(\'x\')"',
            f'python -c "\nprint(1);open(\'{path}\',\'w\').write(\'x\')\n"',
            f'bash -c "python tool.py {path}"',
            f"python - <<'EOF'\nfrom pathlib import Path\nPath('{path}').write_text('x')\nEOF",
            f'pwsh -Command "Get-Content other;Set-Content {path} x"',
            f'python reader.py; python writer.py {path}',
            f'python writer.py >& {path}',
            f'python writer.py 2>&1 {path}',
            f'Write-Output "$(python tool.py "x;{path}")"',
        ]

    def test_inline_nested_heredoc_and_later_interpreter_writes_remain_denied(self):
        for path, tag, interp, names in self.targets:
            for command in self.denial_commands(path):
                with self.subTest(tag=tag, command=command):
                    self.assertTrue(guards._interp_protected_write(command, interp, names))

    def test_descriptor_redirection_keeps_each_protected_target_in_its_invocation(self):
        for path, tag, interp, names in self.targets:
            command = f'python writer.py >& {path}'
            with self.subTest(tag=tag, command=command):
                self.assertTrue(guards._interp_protected_write(command, interp, names),
                                'Descriptor ampersand is not an independent statement boundary')

    def test_uncertain_shell_syntax_keeps_conservative_scope(self):
        for path, tag, interp, names in self.targets:
            for command in (
                f'python tool.py \\\n {path}',
                f'python tool.py ^; {path}',
                f'python tool.py --% ; {path}',
                f'cmd.exe /c python tool.py; {path}',
                f'python tool.py `\n {path}',
                f'python tool.py; Get-Content "unterminated {path}',
                f'python tool.py; (Get-Content {path})',
                f'python tool.py; Get-Content \u201c{path}\u201d',
                f'python tool.py; Get-Content ' + ' ' * 33000 + path,
            ):
                with self.subTest(tag=tag, command=command[:100]):
                    self.assertTrue(guards._interp_protected_write(command, interp, names))

    def test_complete_hook_allows_compound_reads_and_keeps_three_write_guards(self):
        spec = importlib.util.spec_from_file_location('compound_fixture_hooks', HERE / 'test_hook_guards.py')
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        fixture.PRE_BASH = str(ROOT / 'core/pysrc/pre-bash.py')
        with tempfile.TemporaryDirectory() as temporary:
            repo = fixture.make_fixture(temporary, 'feature/compound-read')
            for path, tag, interp, names in self.targets:
                before = (Path(repo) / path).read_bytes()
                command = self.reader() + "; Get-Content -Raw '" + path + "'"
                allowed = fixture.run_hook(repo, command, tool_name='PowerShell')
                self.assertEqual(allowed.returncode, 0, allowed.stderr)
                for command in self.denial_commands(path) + [
                        self.reader() + f'; Set-Content {path} rewritten']:
                    denied = fixture.run_hook(repo, command)
                    self.assertEqual(denied.returncode, 2, command + ': ' + denied.stderr)
                    self.assertIn('[' + tag + ']', denied.stderr)
                self.assertEqual((Path(repo) / path).read_bytes(), before)


class PowerShellStdinOwnership(unittest.TestCase):
    def guard_result(self, command):
        # Only the production parser sees these strings. Never execute the
        # here-string or its consumer, and keep the real audit sink private.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / '.codearbiter'
            state.mkdir()
            context = state / 'CONTEXT.md'
            context.write_text('---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n',
                               encoding='utf-8')
            before = context.read_bytes()
            payload = {'tool_name': 'PowerShell', 'cwd': str(root),
                       'tool_input': {'command': command}}
            diagnostic = io.StringIO()
            with (mock.patch.dict(os.environ, {'CLAUDE_PROJECT_DIR': str(root)}),
                  redirect_stderr(diagnostic), redirect_stdout(io.StringIO())):
                with self.assertRaises(SystemExit) as finished:
                    guards.run_guards(payload, str(root), payload['tool_input'])
            self.assertEqual(context.read_bytes(), before, 'inert command body executed')
            return finished.exception.code, diagnostic.getvalue()

    def test_powershell_here_string_stdin_protected_write_precedes_interpreter(self):
        body = "from pathlib import Path\nPath('.codearbiter/CONTEXT.md').write_text('never executed')"
        for consumer in ('C:/Python314/python.exe -I -S -B -X utf8 -', 'python -'):
            for newline in ('\n', '\r\n'):
                command = ("@'\n" + body + "\n'@ | " + consumer).replace('\n', newline)
                with self.subTest(consumer=consumer, newline=repr(newline)):
                    code, diagnostic = self.guard_result(command)
                    self.assertEqual(code, 2, diagnostic)
                    self.assertIn('[H-18]', diagnostic)

    def test_stdin_body_ownership_keeps_audit_and_decision_write_guards(self):
        for path, tag in (('.codearbiter/overrides.log', 'H-05'),
                          ('.codearbiter/decisions/0001-seed.md', 'H-11')):
            body = f"from pathlib import Path\nPath('{path}').write_text('never executed')"
            command = "@'\n" + body + "\n'@ | C:/Python314/python.exe -I -S -B -X utf8 -"
            with self.subTest(tag=tag):
                code, diagnostic = self.guard_result(command)
                self.assertEqual(code, 2, diagnostic)
                self.assertIn('[' + tag + ']', diagnostic)

    def test_existing_visible_write_forms_remain_denied(self):
        body = "from pathlib import Path\nPath('.codearbiter/CONTEXT.md').write_text('never executed')"
        commands = [
            "@'\n" + body + "\n'@ | python -I -B -",
            "python - <<'PY'\n" + body + '\nPY',
            'python -c "' + body.replace('\n', '; ') + '"',
            "@'\n" + body + "\n'@ | & 'C:/runtime bin/python.exe' -I -S -B -X utf8 -",
        ]
        for command in commands:
            with self.subTest(command=command):
                code, diagnostic = self.guard_result(command)
                self.assertEqual(code, 2, diagnostic)
                self.assertIn('[H-18]', diagnostic)

    def test_literal_reads_and_nonexecutor_data_are_not_write_authority(self):
        read_body = "from pathlib import Path\nprint(Path('.codearbiter/CONTEXT.md').read_text())"
        data_body = "from pathlib import Path\nPath('.codearbiter/CONTEXT.md').write_text('never executed')"
        commands = [
            "Get-Content -LiteralPath '.codearbiter/CONTEXT.md' -First 12",
            "@'\n" + read_body + "\n'@ | python -I -B -",
            "@'\n" + data_body + "\n'@ | Write-Output",
        ]
        for command in commands:
            with self.subTest(command=command):
                code, diagnostic = self.guard_result(command)
                self.assertEqual(code, 0, diagnostic)
        conservative = ("@'\nprint('ordinary diagnostic')\n'@ | "
                        "C:/Python314/python.exe -I -S -B -X utf8 -; "
                        "Get-Content -LiteralPath '.codearbiter/CONTEXT.md' -First 12")
        code, diagnostic = self.guard_result(conservative)
        self.assertEqual(code, 2, diagnostic)
        self.assertIn('[H-18]', diagnostic)

    def test_stdin_body_cannot_forge_a_sanctioned_gate_marker(self):
        body = ("from pathlib import Path\n"
                "Path('.codearbiter/.markers/security-gate-passed').write_text('never executed')")
        command = "@'\n" + body + "\n'@ | C:/Python314/python.exe -I -S -B -X utf8 -"
        code, diagnostic = self.guard_result(command)
        self.assertEqual(code, 2, diagnostic)
        self.assertIn('[H-19]', diagnostic)

    def test_registered_state_inline_write_guard_remains_denied(self):
        body = "from pathlib import Path; Path('.codearbiter/open-tasks.md').write_text('never executed')"
        code, diagnostic = self.guard_result('python -c "' + body + '"')
        self.assertEqual(code, 2, diagnostic)
        self.assertIn('[H-22]', diagnostic)

    def test_powershell_visible_stdin_registered_state_write_is_h22_blocked(self):
        body = "from pathlib import Path\nPath('.codearbiter/open-tasks.md').write_text('never executed')"
        for consumer in ('C:/Python314/python.exe -I -S -B -X utf8 -', 'python -'):
            command = "@'\n" + body + "\n'@ | " + consumer
            with self.subTest(consumer=consumer):
                code, diagnostic = self.guard_result(command)
                self.assertEqual(code, 2, diagnostic)
                self.assertIn('[H-22]', diagnostic)

    def test_nonstdin_writer_script_filename_data_keeps_existing_exception(self):
        for command in (
                'python taskwrite.py add -- "fix open-tasks.md schema"',
                'python -B taskwrite.py add -- "fix open-tasks.md schema"',
                "@'\n{\"title\":\"fix open-tasks.md schema\"}\n'@ | python taskwrite.py add"):
            with self.subTest(command=command):
                code, diagnostic = self.guard_result(command)
                self.assertEqual(code, 0, diagnostic)

    def test_python_default_stdin_mode_keeps_visible_state_writes_denied(self):
        body = "from pathlib import Path\nPath('.codearbiter/open-tasks.md').write_text('never executed')"
        for consumer in ('python', 'python -I -B', 'python -I -X utf8'):
            with self.subTest(consumer=consumer):
                code, diagnostic = self.guard_result("@'\n" + body + "\n'@ | " + consumer)
                self.assertEqual(code, 2, diagnostic)
                self.assertIn('[H-22]', diagnostic)

    def test_combined_python_value_options_do_not_hide_visible_stdin_code(self):
        body = "from pathlib import Path\nPath('.codearbiter/open-tasks.md').write_text('never executed')"
        for consumer in ('python -IBX utf8 -', 'python -IBW default -'):
            with self.subTest(consumer=consumer):
                code, diagnostic = self.guard_result("@'\n" + body + "\n'@ | " + consumer)
                self.assertEqual(code, 2, diagnostic)
                self.assertIn('[H-22]', diagnostic)

    def test_visible_stdin_consumer_boundary_does_not_borrow_later_script_argv(self):
        body = "from pathlib import Path\nPath('.codearbiter/open-tasks.md').write_text('never executed')"
        for consumer in ('python', 'python -I -B'):
            for following in ('; Write-Output done', ';Write-Output done',
                              '\nWrite-Output done', '\r\nWrite-Output done',
                              ' | Write-Output', ' |\n Write-Output'):
                command = "@'\n" + body + "\n'@ | " + consumer + following
                with self.subTest(consumer=consumer, following=repr(following)):
                    code, diagnostic = self.guard_result(command)
                    self.assertEqual(code, 2, diagnostic)
                    self.assertIn('[H-22]', diagnostic)

    def test_later_statement_preserves_nonstdin_script_data_owner(self):
        body = '{"title":"fix open-tasks.md schema"}'
        for consumer in (
                'python taskwrite.py add -- "fix open-tasks.md schema"',
                'python -B "C:/runtime bin/taskwrite.py" add -- "fix; open-tasks.md schema"'):
            for following in ('; Write-Output done', '\nWrite-Output done', ' | Write-Output'):
                with self.subTest(consumer=consumer, following=repr(following)):
                    code, diagnostic = self.guard_result("@'\n" + body + "\n'@ | " + consumer + following)
                    self.assertEqual(code, 0, diagnostic)


if __name__ == '__main__':
    unittest.main()
