"""Measurement regressions; synthetic reports never claim a live provider run."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import copy
from unittest import mock


HERE = Path(__file__).resolve().parent
def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MeasurementContracts(unittest.TestCase):
    def test_nonempty_compatible_subset_compares_and_wrong_harness_refuses(self):
        bench = load('statusline-bench')
        phase = {'renders': 1, 'totals': dict.fromkeys(bench.GATED_COUNTERS, 0),
                 'median_ms': 1.0, 'p95_ms': 1.0, 'partition_files':0}
        name = bench.SCENARIOS[0][0]
        report = {'schema':'codearbiter.statusline-bench/v2','harness_sha256':'a'*64,
                  'python':'fixture','platform':'fixture', 'selection':{'scope':'subset','scenarios':[name]},
                  'scenarios':{name:{p:copy.deepcopy(phase) for p in bench.GATED_PHASES}}}
        with tempfile.TemporaryDirectory() as directory:
            a,b=Path(directory)/'a.json',Path(directory)/'b.json'
            a.write_text(json.dumps(report));b.write_text(json.dumps(report))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bench.cmd_compare(SimpleNamespace(base=a,head=b,structural_only=True)),0)
                report['harness_sha256']='b'*64;b.write_text(json.dumps(report))
                self.assertEqual(bench.cmd_compare(SimpleNamespace(base=a,head=b,structural_only=True)),1)
    def test_empty_statusline_reports_cannot_pass(self):
        bench = load('statusline-bench')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'empty.json'
            path.write_text(json.dumps({'scenarios': {}}))
            with contextlib.redirect_stdout(io.StringIO()):
                result = bench.cmd_compare(SimpleNamespace(base=path, head=path, structural_only=True))
            self.assertEqual(result, 1)

    def test_unknown_statusline_scenario_is_rejected_before_measurement(self):
        bench = load('statusline-bench')
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(checkout=HERE.parent, out=str(Path(directory)/'report.json'), scenario=['no-such-case'])
            with self.assertRaisesRegex(ValueError, 'scenario'):
                bench.cmd_run(args)
            self.assertFalse(Path(args.out).exists())

    def test_smarts_lens_keywords_are_not_material_alternatives(self):
        exercise = load('live-smarts-exercise')
        model = {'normative': {'sections': [{'id': 'SEC-SMARTS', 'blocks': [
            {'type': 'paragraph', 'text': 'Scalable Maintainable Available Reliable Testable Securable'}
        ]}]}}
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(exercise, 'spec_model', return_value=model):
            passed, _ = exercise.judge('material', Path(directory))
        self.assertFalse(passed)

    def test_failed_smarts_child_cannot_pass_from_plausible_output(self):
        exercise = load('live-smarts-exercise')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(exercise.sys, 'argv', ['exercise', '--case', 'single', '--keep']), \
                 mock.patch.object(exercise, 'plugin_root', return_value=root), \
                 mock.patch.object(exercise.tempfile, 'mkdtemp', return_value=str(root)), \
                 mock.patch.object(exercise, 'scaffold'), \
                 mock.patch.object(exercise, 'run', return_value=SimpleNamespace(returncode=1, stdout='plausible text')), \
                 mock.patch.object(exercise, 'judge', return_value=(True, 'fixture criteria passed')), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(exercise.main(), 1)

    def test_screenshot_renderer_failure_is_not_a_good_image(self):
        shot = load('statusline-screenshot')
        for result in [SimpleNamespace(returncode=1,stdout=b'looks fine'), SimpleNamespace(returncode=0,stdout=b'')]:
            with mock.patch.object(shot.subprocess, 'run', return_value=result), self.assertRaises(ValueError):
                shot.render_statusline('fixture', {}, {})

    def test_screenshot_failed_run_cleans_owned_scratch_and_preserves_prior_image(self):
        shot = load('statusline-screenshot')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = root/'prior.png';previous.write_bytes(b'prior image')
            real = tempfile.TemporaryDirectory
            owned = []
            def scratch(**kwargs):
                context = real(dir=root, **kwargs);owned.append(Path(context.name));return context
            with mock.patch.object(shot.tempfile, 'TemporaryDirectory', side_effect=scratch), mock.patch.object(shot, 'render_statusline', side_effect=ValueError('controlled renderer failure')), mock.patch.dict(shot.os.environ, {'SHOT_OUT':str(previous)}):
                with self.assertRaisesRegex(ValueError, 'controlled renderer'): shot.main()
            self.assertTrue(owned);self.assertTrue(all(not path.exists() for path in owned))
            self.assertEqual(previous.read_bytes(),b'prior image')

    def test_screenshot_browser_failure_closes_browser_and_preserves_prior_image(self):
        shot = load('statusline-screenshot')
        browser = mock.Mock()
        browser.new_context.return_value.new_page.return_value.goto.side_effect = RuntimeError('controlled browser failure')
        manager = mock.MagicMock()
        manager.__enter__.return_value.chromium.launch.return_value = browser
        module = SimpleNamespace(sync_playwright=lambda: manager)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'prior.png';target.write_bytes(b'prior image')
            with mock.patch.dict(shot.sys.modules, {'playwright':SimpleNamespace(), 'playwright.sync_api':module}), mock.patch.object(shot, 'render_statusline', return_value='Actual renderer stub for failure boundary'), mock.patch.dict(shot.os.environ, {'SHOT_OUT':str(target)}):
                with self.assertRaisesRegex(RuntimeError, 'controlled browser'): shot.main()
            browser.close.assert_called_once()
            self.assertEqual(target.read_bytes(),b'prior image')
            self.assertEqual(list(Path(directory).iterdir()),[target])

    def test_farm_escalation_does_not_invent_premium_spend_or_abort_cause(self):
        report = load('farm-first-pass')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'report.json'
            path.write_text(json.dumps({'aborted': True, 'results': [{'id':'a','status':'escalate','attempts':1}]}))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(report.main([str(path)]), 0)
            self.assertNotIn('ABORTED by circuit breaker', out.getvalue())
            self.assertNotIn('net-negative this run', out.getvalue())
            self.assertNotIn("each one's labor reverts to the premium path", out.getvalue())
            self.assertIn('unknown', out.getvalue().lower())


if __name__ == '__main__':
    unittest.main()
