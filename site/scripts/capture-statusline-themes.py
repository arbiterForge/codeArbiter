#!/usr/bin/env python3
"""Capture the real statusline renderer with isolated deterministic input.

All repository/accounting/session reads are mocked. No account, billing,
provider, installed-host, or live-session verification is claimed.
"""
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SOURCE_COMMIT = 'b41d9803eacb3acf4b93c8bec81e1aa2f086aec7'
HOOKS = ROOT / 'plugins/ca/hooks'
def pinned_source(path):
    relative = path.relative_to(ROOT).as_posix()
    pinned = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{SOURCE_COMMIT}:{relative}'])
    if path.read_bytes() != pinned:
        raise RuntimeError(f'Renderer dependency changed: {relative}; review the source pin before recapture')
    return hashlib.sha256(pinned).hexdigest()


# Bind the entry point before executing it, not only its imported dependencies.
renderer = HOOKS / 'statusline.py'
source_files = {renderer.relative_to(ROOT).as_posix(): pinned_source(renderer)}
sys.path.insert(0, str(HOOKS))
spec = importlib.util.spec_from_file_location('ca_site_statusline', renderer)
if spec is None or spec.loader is None:
    raise RuntimeError('Unable to load the pinned statusline renderer')
sl = importlib.util.module_from_spec(spec)
# Match normal import semantics, including dataclass/annotation module lookup.
sys.modules[spec.name] = sl
spec.loader.exec_module(sl)

# Refuse to attach the pinned source identity to different renderer dependencies.
for module in list(sys.modules.values()):
    filename = getattr(module, '__file__', None)
    if not filename:
        continue
    path = Path(filename).resolve()
    if not path.is_relative_to(HOOKS) or path.suffix != '.py':
        continue
    source_files[path.relative_to(ROOT).as_posix()] = pinned_source(path)

payload = {'session_id': 'documentation-fixture', 'cwd': '/example/saved-searches',
           'workspace': {'current_dir': '/example/saved-searches', 'repo': {'owner': 'example', 'name': 'saved-searches'}},
           'model': {'display_name': 'Example model'},
           'context_window': {'used_percentage': 23, 'context_window_size': 200000}}
fixtures = {'project_root': '/example/saved-searches', 'arbiter_state': {'stage': 1, 'tasks': 3, 'q': 1, 'over': 0},
            'current_mode': 'arbiter', 'head_branch': 'feature/export', 'git_dirty': False,
            'ledger_update': ({'sess_start': 1000}, {'in': 2400, 'out': 400, 'cost': 0.05}, {'in': 4800, 'out': 800, 'cost': 0.10}),
            'session_start': 1000, 'burn_spark': '', 'seg_update': '', 'seg_pr': '', 'seg_prune': '',
            'subagent_dir': 'fixture', 'read_subagents': (1, 1, [{'label': 'Review export', 'model': 'model:fixture', 'inp': 1200, 'out': 340, 'age': 8, 'active': True}], (1200, 340))}
captures = []
with tempfile.TemporaryDirectory(prefix='ca-site-statusline-') as home:
    for theme in ['violet', 'blue', 'green', 'amber', 'mono']:
        with ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, {'HOME': home, 'USERPROFILE': home, 'CODEARBITER_WIDTH': '100', 'CODEARBITER_THEME': theme}, clear=True))
            for name, value in fixtures.items():
                stack.enter_context(mock.patch.object(sl, name, return_value=value))
            stack.enter_context(mock.patch.object(sl.time, 'time', return_value=1060))
            stack.enter_context(mock.patch.object(sl, 'persist_sess_start', side_effect=AssertionError('No fixture writes')))
            text = sl.render(json.dumps(payload))
            if 'stage:1' not in sl.ANSI.sub('', text) or 'Review export' not in sl.ANSI.sub('', text):
                raise RuntimeError('Renderer did not produce expected fixture segments')
            captures.append({'theme': theme, 'ansi': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()})
output = ROOT / 'site/public/examples/statusline-themes.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({'schema_version': 1, 'source_commit': SOURCE_COMMIT, 'source_files': source_files,
    'renderer': 'plugins/ca/hooks/statusline.py',
    'renderer_sha256': hashlib.sha256((HOOKS/'statusline.py').read_bytes()).hexdigest(),
    'boundary': 'Actual renderer, mocked project and usage inputs. Not an installed host capture, live usage, or billing statement.',
    'payload': payload, 'captures': captures}, indent=2) + '\n')
