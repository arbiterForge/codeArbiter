#!/usr/bin/env python3
"""Run the three complete native check configurations on one provisioned runner.

The checked-in command plan owns membership; this runner only schedules it.
Workers have distinct homes, temporary directories, reports and output paths.
They may share Go's concurrency-safe compiler cache, never test-result evidence.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from _artifactworkerlib import worker_directory
from artifact_ci import read_regular, unique_object

REPO = Path(__file__).resolve().parents[2]
PLAN = REPO / '.github/ci-native-checks.json'
GROUPS = ('default', 'coverage', 'context')
RUNNERS = {
    'ubuntu-24.04': 'linux/amd64', 'ubuntu-24.04-arm': 'linux/arm64',
    'windows-2025': 'windows/amd64', 'windows-11-arm': 'windows/arm64',
    'macos-15-intel': 'darwin/amd64', 'macos-26': 'darwin/arm64',
}
EXPECTED_STEPS = {
    'default': ('Test artifact engine', 'Vet artifact engine',
                'Race-test Linux persistence paths', 'Verify generated artifact types',
                'Verify artifact public-surface baseline', 'Verify artifact consumer inventory closure',
                'Verify ship-set evidence-input behavior'),
    'coverage': ('Exercise the actual CLI with native statement instrumentation',
                 'Collect native unit and executable statement coverage'),
    'context': ('Verify named native storage and recovery contract',
                'Verify the finite context Go test bridge', 'Verify named context document Go cases',
                'Reject missing and nonisolated installed context candidates',
                'Verify context workflow with the pinned Go toolchain'),
}
FORMAT = 'codearbiter.native-check-group/1'


def load_plan(path: Path = PLAN) -> tuple[dict[str, list[dict[str, Any]]], str]:
    """Refuse missing, extra, reordered, empty or malformed check configurations."""
    raw = read_regular(path, 131072)
    doc = json.loads(raw, object_pairs_hook=unique_object)
    if (not isinstance(doc, dict) or set(doc) != {'format', 'groups'}
            or doc['format'] != 'codearbiter.native-check-plan/1'
            or not isinstance(doc['groups'], dict) or set(doc['groups']) != set(GROUPS)):
        raise ValueError('native command plan is incomplete')
    for group, steps in doc['groups'].items():
        if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps):
            raise ValueError('native steps must be records')
        if tuple(step.get('name') for step in steps) != EXPECTED_STEPS[group]:
            raise ValueError('native check membership or order changed: ' + group)
        for step in steps:
            if (set(step) - {'name', 'argv', 'cwd', 'env', 'only_os'}
                    or not {'name', 'argv', 'cwd', 'env'} <= set(step)
                    or not isinstance(step['argv'], list) or len(step['argv']) < 2
                    or any(not isinstance(arg, str) or not arg or '\x00' in arg for arg in step['argv'])
                    or step['argv'][0] not in ('python', 'go')
                    or step['cwd'] not in ('.', 'core/artifacts')
                    or not isinstance(step['env'], dict)
                    or any(not isinstance(k, str) or not isinstance(v, str) for k, v in step['env'].items())
                    or ('only_os' in step and step['only_os'] != 'ubuntu-24.04')):
                raise ValueError('invalid native command: ' + step['name'])
            expected_os = 'ubuntu-24.04' if group == 'default' and step['name'] in EXPECTED_STEPS['default'][2:] else None
            if step.get('only_os') != expected_os:
                raise ValueError('native command has an unexpected platform exclusion')
    return doc['groups'], hashlib.sha256(raw).hexdigest()


def render(value: str, output: Path, platform: str) -> str:
    """Expand only the two CI-owned data placeholders, never a shell expression."""
    return value.replace('{OUTPUT}', str(output)).replace('{PLATFORM}', platform)


def execute_group(group: str, output: Path, runner_os: str, platform: str,
                  plan: dict[str, list[dict[str, Any]]], plan_hash: str) -> dict[str, Any]:
    """Execute a complete configuration once, preserving every failure and log."""
    if group not in GROUPS or RUNNERS.get(runner_os) != platform:
        raise ValueError('native group or platform identity mismatch')
    output.mkdir(parents=True, exist_ok=False)
    result: dict[str, Any] = {
        'format': FORMAT, 'group': group, 'platform': platform, 'runner_os': runner_os,
        'plan_sha256': plan_hash, 'passed': False, 'steps': [],
    }
    # Resolve before creating a private HOME, so simultaneous Go commands reuse
    # compilation work. Every actual Go test invocation is uncached (-count=1).
    cache = subprocess.check_output(['go', 'env', 'GOCACHE'], cwd=REPO, text=True).strip()
    if not cache or not Path(cache).is_absolute():
        raise ValueError('native compiler cache path is unavailable')
    with worker_directory(prefix='ca-native-' + group + '-') as temporary:
        root = Path(temporary)
        home, temp = root / 'home', root / 'tmp'
        home.mkdir()
        temp.mkdir()
        env = {**os.environ, 'HOME': str(home), 'USERPROFILE': str(home),
               'TMP': str(temp), 'TEMP': str(temp), 'TMPDIR': str(temp),
               'GOCACHE': cache, 'PYTHONUTF8': '1'}
        for index, step in enumerate(plan[group]):
            selected = step.get('only_os', runner_os) == runner_os
            row: dict[str, Any] = {'name': step['name'], 'selected': selected,
                                   'exit': None, 'seconds': 0.0}
            if selected:
                argv = [render(arg, output, platform) for arg in step['argv']]
                if argv[0] == 'python':
                    argv[0] = sys.executable
                local_env = {**env, **{k: render(v, output, platform) for k, v in step['env'].items()}}
                print(f'[{group}] {step["name"]}', flush=True)
                started = time.monotonic()
                with (output / f'{index:02d}.log').open('xb') as log:
                    run = subprocess.run(argv, cwd=REPO / step['cwd'], env=local_env,
                                         stdout=log, stderr=subprocess.STDOUT, check=False)
                row.update(exit=run.returncode, seconds=round(time.monotonic() - started, 6))
            result['steps'].append(row)
    # A failed command does not prevent sibling commands from furnishing their
    # diagnostic output, but no failed, unexecuted or unexpectedly skipped row passes.
    result['passed'] = all(row['exit'] == 0 for row in result['steps'] if row['selected'])
    with (output / 'result.json').open('x', encoding='utf-8', newline='\n') as report:
        json.dump(result, report, indent=2, sort_keys=True)
        report.write('\n')
    return result


def validate_result(record: Any, group: str, runner_os: str, platform: str,
                    plan: dict[str, list[dict[str, Any]]], plan_hash: str) -> None:
    """Require fresh complete observations, not just a worker-provided PASS flag."""
    if (not isinstance(record, dict)
            or set(record) != {'format', 'group', 'platform', 'runner_os', 'plan_sha256', 'passed', 'steps'}
            or any(record.get(key) != value for key, value in {
                'format': FORMAT, 'group': group, 'platform': platform,
                'runner_os': runner_os, 'plan_sha256': plan_hash}.items())
            or record['passed'] is not True or not isinstance(record['steps'], list)
            or len(record['steps']) != len(plan[group])):
        raise ValueError('native worker lacks complete successful evidence: ' + group)
    for step, row in zip(plan[group], record['steps']):
        selected = step.get('only_os', runner_os) == runner_os
        if (not isinstance(row, dict) or set(row) != {'name', 'selected', 'exit', 'seconds'}
                or row['name'] != step['name'] or row['selected'] is not selected
                or (selected and (type(row['exit']) is not int or row['exit'] != 0))
                or (not selected and row['exit'] is not None)
                or type(row['seconds']) not in (int, float) or not 0 <= row['seconds'] < 86400):
            raise ValueError('native worker failed, skipped, or substituted a required command')


def run_child(group: str, root: Path, runner_os: str, platform: str) -> int:
    """Keep each native configuration in a separate Python process."""
    with (root / (group + '.log')).open('xb') as log:
        run = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--group', group,
                              '--output', str(root / group), '--runner-os', runner_os,
                              '--platform', platform], cwd=REPO,
                             stdout=log, stderr=subprocess.STDOUT, check=False)
    return run.returncode


def worker_limit(platform: str, serial: bool = False) -> int:
    """Keep Windows runners below the observed suite-timeout contention point."""
    if platform not in RUNNERS.values():
        raise ValueError('unsupported native worker platform')
    if serial:
        return 1
    # Run 39085371841 exhausted Go's unchanged 10m operations-package limit
    # with three simultaneous configurations on Windows ARM64. Run 39086933353
    # then exposed the same limit on Windows x64 while bounded ARM64 passed.
    # Keep all work and preserve the same test/job time limits on both hosts.
    return 2 if platform.startswith('windows/') else 3


def main() -> None:
    """Run all three bounded parallel workers, or one internal child configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', choices=GROUPS)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runner-os', choices=sorted(RUNNERS), required=True)
    parser.add_argument('--platform', choices=sorted(RUNNERS.values()), required=True)
    parser.add_argument('--serial', action='store_true', help='Same-workload measurement control only')
    args = parser.parse_args()
    if RUNNERS[args.runner_os] != args.platform or (args.group and args.serial):
        parser.error('invalid native worker platform or mode')
    plan, plan_hash = load_plan()
    if args.group:
        record = execute_group(args.group, args.output, args.runner_os, args.platform, plan, plan_hash)
        validate_result(record, args.group, args.runner_os, args.platform, plan, plan_hash)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    failures = []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=worker_limit(args.platform, args.serial)) as pool:
        futures = {pool.submit(run_child, group, args.output, args.runner_os, args.platform): group
                   for group in GROUPS}
        for future in as_completed(futures):
            group = futures[future]
            try:
                code = future.result()
                if code != 0:
                    raise ValueError(f'native worker exit: {code}')
                record = json.loads(read_regular(args.output / group / 'result.json', 131072),
                                    object_pairs_hook=unique_object)
                validate_result(record, group, args.runner_os, args.platform, plan, plan_hash)
                print('Complete native configuration passed: ' + group, flush=True)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                failures.append(group + ': ' + str(error))
    summary = {'format': FORMAT, 'platform': args.platform, 'plan_sha256': plan_hash,
               'groups': list(GROUPS), 'passed': not failures, 'errors': failures,
               'seconds': round(time.monotonic() - started, 6)}
    with (args.output / 'summary.json').open('x', encoding='utf-8', newline='\n') as report:
        json.dump(summary, report, indent=2, sort_keys=True)
        report.write('\n')
    print(json.dumps(summary), flush=True)
    if failures:
        raise SystemExit('Native configurations failed: ' + '; '.join(failures))


if __name__ == '__main__':
    main()
