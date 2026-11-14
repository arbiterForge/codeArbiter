#!/usr/bin/env python3
"""Validate the deliberately narrow hook-job partition contract (stdlib only).

Run as a required step in each hook matrix cell. These checks complement,
not replace, actionlint, workflow review, and actual native-host execution.
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

# The hermetic isolation run is the hook suite's only execution; a plain
# discovery step would repeat the same population and must not return.
DIRECT = 'python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"'
ISOLATION = 'python .github/scripts/test_suite_hermeticity.py'
GUARD = 'python .github/scripts/test_hook_ci_partition.py'
GO_SETUP = '''      - uses: actions/setup-go@b7ad1dad31e06c5925ef5d2fc7ad053ef454303e # v7.0.0
        with:
          go-version: "1.27.1"
          check-latest: false
          cache: false
          go-download-base-url: https://go.dev/dl
'''
NATIVE_READER_ENV = "    env:\n      ARTIFACT_TEST_INSTALLATION: ${{ github.workspace }}/../hooks-native\n"
NATIVE_PREPARE_COMMAND = 'python tools/build-artifacts.py --output "${{ github.workspace }}/../hooks-native"'
NATIVE_PREPARE = (
    '      - name: Qualify one native reader for hook contracts\n'
    '        env:\n'
    '          ARTIFACT_TEST_INSTALLATION: ""\n'
    '        run: ' + NATIVE_PREPARE_COMMAND + '\n'
)
RECOVERY_NATIVE_ENV = "    env:\n      ARTIFACT_TEST_INSTALLATION: ${{ github.workspace }}/../workflow-recovery-native\n"
RECOVERY_PREPARE_COMMAND = 'python tools/build-artifacts.py --output "${{ github.workspace }}/../workflow-recovery-native"'
RECOVERY_PREPARE = (
    '      - name: Qualify one native installation for workflow recovery\n'
    '        env:\n'
    '          ARTIFACT_TEST_INSTALLATION: ""\n'
    '        run: ' + RECOVERY_PREPARE_COMMAND + '\n'
)
RECOVERY_COMMANDS = (
    'python .github/scripts/test_workflow_recovery.py',
    'python .github/scripts/test_workflow_recovery_cli.py',
    'python .github/scripts/test_workflow_recovery_hosts.py',
    'python .github/scripts/test_workflow_recovery_generator.py',
    'python .github/scripts/test_review_resubmission.py',
)
# sha256(compact JSON of the ordered pre-partition command list). This binds
# the guard to all 73 reviewed command steps without duplicating the workflow here.
# Release-workflow and Codex identity regressions run in separate native steps.
# The guard matrix, ca-codex adapter and dual-host store suites have no direct
# step: the hermetic isolation run is their only execution (HERMETIC_ONLY).
HERMETIC_ONLY = ('test_hook_guards.py', 'test_codex_adapter.py', 'test_dual_host_store.py')
COMMANDS_SHA256 = '95ab7756bb2e806ede61b407931e152433a4f382dec79ed3fb250b3e9d3e98df'
HOOK_TIMEOUT = "    timeout-minutes: ${{ matrix.os == 'windows-latest' && matrix.partition == 'contracts' && 25 || 20 }}\n"
MATRIX = '''        os: [ubuntu-latest, windows-latest, macos-latest]
        partition: [all]
        exclude:
          - os: windows-latest
            partition: all
        include:
          - os: windows-latest
            partition: contracts
          - os: windows-latest
            partition: isolation
'''


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def job_block(text: str, name: str) -> str:
    matches = list(re.finditer(r'^  ' + re.escape(name) + r':\s*$', text, re.M))
    require(len(matches) == 1, f'Expected one {name} job')
    start = matches[0]
    nxt = re.search(r'^  [A-Za-z0-9_-]+:\s*$', text[start.end():], re.M)
    end = start.end() + nxt.start() if nxt else len(text)
    return text[start.start():end]


def step_blocks(block: str) -> list[str]:
    points = list(re.finditer(r'^      - (?:name|uses):', block, re.M))
    return [block[m.start():points[i+1].start() if i+1<len(points) else len(block)] for i,m in enumerate(points)]


def command(block: str) -> str | None:
    hit = re.search(r'^        run: (.*)$', block, re.M)
    if not hit: return None
    if hit[1] not in ('|','>','>-'): return hit[1].strip()
    lines=[]
    for line in block[hit.end()+1:].splitlines():
        if line.startswith('          '): lines.append(line[10:])
        elif not line.strip(): lines.append('')
        else: break
    return '\n'.join(lines).rstrip()


def command_digest(commands: list[str]) -> str:
    payload = json.dumps(commands, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def validate(
    text: str,
    expected_digest: str = COMMANDS_SHA256,
    expected_counts: dict[str, int] | None = None,
) -> dict[str,int]:
    if expected_counts is None:
        expected_counts={'contracts':72,'isolation':1,'guard':1,'setup':3,'native_setup':1}
    block=job_block(text,'hooks')
    pre=block.split('    steps:\n',1)[0]
    require(pre.count(MATRIX)==1,'Expected exactly the reviewed four-cell matrix')
    # No additional matrix members/axes may silently create empty cells.
    matrix_tail=pre.split('      matrix:\n',1)[1].split('    runs-on:',1)[0]
    require(matrix_tail == MATRIX, 'Matrix includes unreviewed cells or axes')
    require('      fail-fast: false\n' in pre,'Do not cancel sibling evidence on failure')
    require('    if: needs.changes.outputs.hooks == \'true\'\n' in pre,'Hook applicability changed')
    require('    runs-on: ${{ matrix.os }}\n' in pre,'Native operating systems must remain native')
    require(HOOK_TIMEOUT in pre,'Only Windows contracts may use the bounded25-minute budget; other hook cells retain20minutes')
    require('continue-on-error:' not in block,'Required hook checks cannot soften failures')
    require(pre.count(NATIVE_READER_ENV)==1,'Use the fixed same-job qualified native reader')
    counters={'contracts':0,'isolation':0,'guard':0,'setup':0,'native_setup':0}
    commands=[]
    for step in step_blocks(block):
        cmd=command(step)
        predicates=re.findall(r'^        if: (.*)$',step,re.M)
        if cmd is None:
            counters['setup']+=1
            require(not predicates,'Shared setup must run in every cell')
            require('uses: actions/checkout@' in step or 'uses: actions/setup-python@' in step
                    or step == GO_SETUP,'Review new setup actions before partitioning')
            if 'uses: actions/checkout@' in step:
                for field in ('fetch-depth: 0','fetch-tags: true','persist-credentials: false'):
                    require(field in step,f'Checkout lost {field}')
            continue
        if cmd==NATIVE_PREPARE_COMMAND:
            counters['native_setup']+=1
            require(not predicates,'Native qualification must run in every cell')
            require(step==NATIVE_PREPARE,'Qualification must clear inherited input and retain full native tests')
            continue
        if cmd==GUARD:
            counters['guard']+=1
            require(not predicates,'Partition validator must run in every cell')
            continue
        require(cmd!=DIRECT,'The hermetic run already executes the complete hook suite')
        commands.append(cmd)
        kind='isolation' if cmd==ISOLATION else 'contracts'
        counters[kind]+=1
        want=f"matrix.partition == 'all' || matrix.partition == '{kind}'"
        require(predicates==[want],f'Command has incorrect partition: {cmd[:100]}')
    require(counters['native_setup']==1,'Expected exactly one ordinary native qualification')
    require(counters['guard']==1,'Expected one mandatory partition validation')
    steps=step_blocks(block)
    require(steps.index(GO_SETUP)<steps.index(NATIVE_PREPARE), 'Pinned Go must precede native qualification')
    guard_index=next(i for i,step in enumerate(steps) if command(step)==GUARD)
    require(steps.index(NATIVE_PREPARE)<guard_index, 'Qualify native input before the contract guard and consumers')
    require(counters['setup']==3,'Expected checkout plus Python and pinned native Go setup')
    require(step_blocks(block).count(GO_SETUP)==1,'Expected one exact native reader toolchain setup')
    require(counters==expected_counts,'Expected reviewed command partition')
    require(command_digest(commands)==expected_digest,'Existing hook command inventory or order changed')
    gate=job_block(text,'ci-passed')
    require(re.search(r'^      - hooks\s*$',gate,re.M) is not None,'Merge readiness no longer awaits hooks')
    require('needs.hooks.result' in gate or "needs['hooks'].result" in gate,'Merge readiness no longer enforces hooks')
    return counters


def fixture() -> str:
    pre="jobs:\n  hooks:\n    needs: changes\n    if: needs.changes.outputs.hooks == 'true'\n    strategy:\n      fail-fast: false\n      matrix:\n"+MATRIX+"    runs-on: ${{ matrix.os }}\n"+HOOK_TIMEOUT+"    steps:\n"
    pre+='      - uses: actions/checkout@'+'1'*40+'\n        with:\n          fetch-depth: 0\n          fetch-tags: true\n          persist-credentials: false\n'
    pre+='      - uses: actions/setup-python@'+'2'*40+'\n'
    pre=pre.replace("    steps:\n",NATIVE_READER_ENV+"    steps:\n")
    pre+=GO_SETUP+NATIVE_PREPARE
    pre+='      - name: guard\n        run: '+GUARD+'\n'
    for kind,cmd in [('contracts','python contract.py'),('isolation',ISOLATION)]:
        pre+=f"      - name: {kind}\n        if: matrix.partition == 'all' || matrix.partition == '{kind}'\n        run: {cmd}\n"
    return pre+"  ci-passed:\n    needs:\n      - hooks\n    steps:\n      - run: echo '${{ needs.hooks.result }}'\n"


def validate_recovery(text: str) -> dict[str, int]:
    block = job_block(text, 'workflow-recovery')
    pre = block.split('    steps:\n', 1)[0]
    require("    if: needs.changes.outputs.hooks == 'true'\n" in pre, 'Recovery applicability changed')
    require('    runs-on: ${{ matrix.os }}\n' in pre, 'Recovery cells must remain native')
    require('    timeout-minutes: 15\n' in pre, 'Recovery must retain the 15-minute budget')
    require(pre.count(RECOVERY_NATIVE_ENV) == 1, 'Recovery consumers require the fixed same-job native installation')
    require(pre.split('    env:\n', 1)[1].split('    permissions:\n', 1)[0]
            == RECOVERY_NATIVE_ENV.split('    env:\n', 1)[1], 'Recovery environment cannot reuse arbitrary ambient inputs')
    require(pre.split('    permissions:\n', 1)[1].split('    strategy:\n', 1)[0]
            == '      contents: read\n', 'Recovery permissions must remain read-only')
    require('      fail-fast: false\n' in pre, 'Recovery cannot cancel sibling evidence')
    require(pre.split('      matrix:\n', 1)[1]
            == '        os: [ubuntu-latest, windows-latest, macos-latest]\n', 'Recovery must retain exactly three OS cells')
    require('continue-on-error:' not in block, 'Recovery failures cannot be softened')
    steps = step_blocks(block)
    require(len(steps) == 9, 'Recovery requires three setup steps, one qualification and five original commands')
    require(not any(re.search(r'^        if:', step, re.M) for step in steps), 'Recovery preparation and consumers must be unconditional')
    require('uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1' in steps[0]
            and 'fetch-depth: 0' in steps[0] and 'persist-credentials: false' in steps[0], 'Recovery checkout pin/history/credential scope changed')
    require(steps[1] == '      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0\n'
            '        with:\n          python-version: "3.14"\n', 'Recovery Python setup changed')
    require(steps[2] == GO_SETUP, 'Recovery qualification requires the existing pinned Go setup')
    require(steps[3] == RECOVERY_PREPARE, 'Recovery must clear inherited installation input and qualify once before consumers')
    require(tuple(command(step) for step in steps[4:]) == RECOVERY_COMMANDS, 'Recovery original five commands or order changed')
    require(not any('        env:\n' in step for step in steps[4:]), 'Recovery consumers cannot override the qualified installation')
    return {'commands': 5, 'native_setup': 1, 'cells': 3}


def recovery_fixture() -> str:
    pre = ("jobs:\n  workflow-recovery:\n    needs: changes\n"
           "    if: needs.changes.outputs.hooks == 'true'\n"
           '    runs-on: ${{ matrix.os }}\n    timeout-minutes: 15\n'
           + RECOVERY_NATIVE_ENV
           + '    permissions:\n      contents: read\n    strategy:\n'
           '      fail-fast: false\n      matrix:\n'
           '        os: [ubuntu-latest, windows-latest, macos-latest]\n    steps:\n')
    pre += ('      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n'
            '        with:\n          fetch-depth: 0\n          persist-credentials: false\n'
            '      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0\n'
            '        with:\n          python-version: "3.14"\n')
    pre += GO_SETUP + RECOVERY_PREPARE
    for index, cmd in enumerate(RECOVERY_COMMANDS):
        pre += f'      - name: recovery {index}\n        run: {cmd}\n'
    return pre


class RecoveryContractTests(unittest.TestCase):
    def bad(self, before: str, after: str):
        with self.assertRaises(ValueError):
            validate_recovery(recovery_fixture().replace(before, after, 1))

    def test_current_recovery_qualifies_once_before_all_five_commands(self):
        text = (Path(__file__).resolve().parents[2] / '.github/workflows/ci.yml').read_text(encoding='utf-8')
        self.assertEqual(validate_recovery(text), {'commands': 5, 'native_setup': 1, 'cells': 3})

    def test_valid_recovery_three_host_contract(self):
        self.assertEqual(validate_recovery(recovery_fixture())['cells'], 3)

    def test_recovery_requires_preparation_and_every_original_command(self):
        self.bad(RECOVERY_PREPARE, '')
        for cmd in RECOVERY_COMMANDS:
            with self.subTest(command=cmd):
                self.bad(cmd, 'python replacement.py')

    def test_recovery_refuses_ambient_reuse_and_qualification_bypass(self):
        self.bad('          ARTIFACT_TEST_INSTALLATION: ""', '          ARTIFACT_TEST_INSTALLATION: unqualified-parent')
        self.bad(RECOVERY_PREPARE_COMMAND, RECOVERY_PREPARE_COMMAND + ' --skip-tests')
        self.bad('      - name: recovery 0\n', '      - name: recovery 0\n        env:\n          ARTIFACT_TEST_INSTALLATION: other-input\n')

    def test_recovery_preserves_budget_matrix_permissions_and_pins(self):
        for before, after in (
            ('timeout-minutes: 15', 'timeout-minutes: 30'),
            ('os: [ubuntu-latest, windows-latest, macos-latest]', 'os: [ubuntu-latest]'),
            ('contents: read', 'contents: write'),
            ('fail-fast: false', 'fail-fast: true'),
            ('go-version: "1.27.1"', 'go-version: "latest"'),
        ):
            with self.subTest(change=before):
                self.bad(before, after)

    def test_recovery_qualification_cannot_move_repeat_or_be_conditional(self):
        self.bad(GO_SETUP + RECOVERY_PREPARE, RECOVERY_PREPARE + GO_SETUP)
        self.bad(RECOVERY_PREPARE, RECOVERY_PREPARE + RECOVERY_PREPARE)
        self.bad(RECOVERY_PREPARE, RECOVERY_PREPARE.replace('        env:', '        if: false\n        env:'))

    def test_recovery_requires_legal_fixed_sibling_environment(self):
        self.bad(RECOVERY_NATIVE_ENV, '')
        self.bad('${{ github.workspace }}/../workflow-recovery-native', '${{ runner.temp }}/workflow-recovery-native')
        self.bad(RECOVERY_PREPARE_COMMAND, RECOVERY_PREPARE_COMMAND.replace('workflow-recovery-native', 'other-input'))


class PartitionContractTests(unittest.TestCase):
    fixture_digest=command_digest(['python contract.py',ISOLATION])
    fixture_counts={'contracts':1,'isolation':1,'guard':1,'setup':3,'native_setup':1}
    def bad(self, before: str, after: str):
        with self.assertRaises(ValueError): validate(fixture().replace(before,after,1),self.fixture_digest,self.fixture_counts)
    def test_valid_four_cell_contract(self): self.assertEqual(validate(fixture(),self.fixture_digest,self.fixture_counts)['isolation'],1)
    def test_current_workflow_qualifies_one_shared_native_reader_before_contracts(self):
        text=(Path(__file__).resolve().parents[2]/'.github/workflows/ci.yml').read_text(encoding='utf-8')
        block=job_block(text,'hooks')
        pre=block.split('    steps:\n',1)[0]
        self.assertIn('      ARTIFACT_TEST_INSTALLATION: ${{ github.workspace }}/../hooks-native\n',pre)
        steps=step_blocks(block)
        builders=[step for step in steps if command(step)=='python tools/build-artifacts.py --output "${{ github.workspace }}/../hooks-native"']
        self.assertEqual(len(builders),1,'one ordinary tested native build must feed all process-local readers')
        self.assertIn('          ARTIFACT_TEST_INSTALLATION: ""',builders[0])
        self.assertNotIn('--skip-tests',builders[0])
        self.assertLess(steps.index(GO_SETUP),steps.index(builders[0]))
        self.assertLess(steps.index(builders[0]),next(i for i,step in enumerate(steps) if command(step)==GUARD))

    def test_current_windows_contract_budget_has_only_the_observed_exception(self):
        text=(Path(__file__).resolve().parents[2]/'.github/workflows/ci.yml').read_text(encoding='utf-8')
        pre=job_block(text,'hooks').split('    steps:\n',1)[0]
        self.assertIn("    timeout-minutes: ${{ matrix.os == 'windows-latest' && matrix.partition == 'contracts' && 25 || 20 }}\n",pre)

    def test_budget_exception_cannot_change_host_partition_or_other_ceiling(self):
        for changed in (
            HOOK_TIMEOUT.replace('windows-latest','macos-latest'),
            HOOK_TIMEOUT.replace("'contracts'","'isolation'"),
            HOOK_TIMEOUT.replace('25 || 20','25 || 25'),
            '    timeout-minutes: 25\n',
            '    timeout-minutes: 20\n',
        ):
            with self.subTest(drift=changed): self.bad(HOOK_TIMEOUT,changed)

    def test_current_job_environment_uses_only_legal_contexts(self):
        text=(Path(__file__).resolve().parents[2]/'.github/workflows/ci.yml').read_text(encoding='utf-8')
        environment=job_block(text,'hooks').split('    steps:\n',1)[0].split('    env:\n',1)[1]
        self.assertNotIn('${{ runner.',environment,'runner is unavailable in jobs.<job_id>.env')

    def test_current_native_preparation_inputs_reach_hooks(self):
        text=(Path(__file__).resolve().parents[2]/'.github/workflows/ci.yml').read_text(encoding='utf-8')
        subjects=text.split('            hooks:\n',1)[1].split('            impact:\n',1)[0]
        for path in ('tools/build-artifacts.py','tools/go_test_parallel.py'):
            with self.subTest(path=path):self.assertIn("- '"+path+"'",subjects)

    def test_missing_shared_native_preparation_fails(self): self.bad(NATIVE_PREPARE,'')
    def test_shared_native_preparation_cannot_skip_tests(self): self.bad(NATIVE_PREPARE_COMMAND,NATIVE_PREPARE_COMMAND+' --skip-tests')
    def test_shared_native_output_cannot_move(self): self.bad(NATIVE_PREPARE_COMMAND,NATIVE_PREPARE_COMMAND.replace('hooks-native','other-input'))
    def test_shared_native_preparation_cannot_be_conditional(self): self.bad(NATIVE_PREPARE,NATIVE_PREPARE.replace('        env:', '        if: false\n        env:'))
    def test_shared_native_preparation_cannot_reuse_parent_input(self): self.bad('          ARTIFACT_TEST_INSTALLATION: ""','          ARTIFACT_TEST_INSTALLATION: unqualified-parent')
    def test_shared_native_preparation_cannot_precede_toolchain(self): self.bad(GO_SETUP+NATIVE_PREPARE,NATIVE_PREPARE+GO_SETUP)
    def test_shared_native_preparation_cannot_repeat(self): self.bad(NATIVE_PREPARE,NATIVE_PREPARE+NATIVE_PREPARE)
    def test_shared_native_consumer_environment_is_required(self): self.bad(NATIVE_READER_ENV,'')
    def test_missing_partition_fails(self): self.bad('            partition: isolation\n','')
    def test_wrong_windows_exclusion_fails(self): self.bad('partition: all','partition: contracts')
    def test_extra_axis_fails(self): self.bad('    runs-on:','        extra: [x]\n    runs-on:')
    def test_wrong_isolation_route_fails(self): self.bad("|| matrix.partition == 'isolation'","|| matrix.partition == 'contracts'")
    def test_unassigned_contract_fails(self): self.bad("        if: matrix.partition == 'all' || matrix.partition == 'contracts'\n",'')
    def test_guard_cannot_be_skipped(self): self.bad('      - name: guard\n','      - name: guard\n        if: false\n')
    def test_missing_guard_keeps_bounded_contract_error(self): self.bad('      - name: guard\n        run: '+GUARD+'\n','')
    def test_softened_check_fails(self): self.bad('      - name: isolation\n','      - name: isolation\n        continue-on-error: true\n')
    def test_missing_full_history_fails(self): self.bad('fetch-depth: 0','fetch-depth: 1')
    def test_missing_tags_fails(self): self.bad('fetch-tags: true','fetch-tags: false')
    def test_missing_native_toolchain_fails(self): self.bad(GO_SETUP,'')
    def test_changed_native_toolchain_pin_fails(self): self.bad('setup-go@b7ad1dad31e06c5925ef5d2fc7ad053ef454303e','setup-go@'+'3'*40)
    def test_changed_native_toolchain_version_fails(self): self.bad('go-version: "1.27.1"','go-version: "latest"')
    def test_conditional_native_toolchain_fails(self): self.bad(GO_SETUP,GO_SETUP.replace('        with:', '        if: false\n        with:'))
    def test_lost_gate_dependency_fails(self): self.bad('      - hooks\n','')
    def test_lost_gate_result_fails(self): self.bad('needs.hooks.result','needs.other.result')
    def test_missing_hermetic_suite_fails(self): self.bad(ISOLATION,'python different.py')
    def test_repeated_plain_suite_fails(self): self.bad('python contract.py',DIRECT)
    def test_fail_fast_cannot_be_enabled(self): self.bad('fail-fast: false','fail-fast: true')
    def test_timeout_ceiling_cannot_expand(self): self.bad(HOOK_TIMEOUT,HOOK_TIMEOUT.replace('25 || 20','30 || 20'))
    def test_deleted_contract_command_fails(self): self.bad("      - name: contracts\n        if: matrix.partition == 'all' || matrix.partition == 'contracts'\n        run: python contract.py\n",'')
    def test_replaced_contract_command_fails(self): self.bad('python contract.py','python replacement.py')
    def test_duplicated_contract_command_fails(self): self.bad('        run: python contract.py\n','        run: python contract.py\n      - name: duplicate\n        if: matrix.partition == \'all\' || matrix.partition == \'contracts\'\n        run: python contract.py\n')


def main() -> int:
    results=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if not results.wasSuccessful() or results.skipped: return 1
    path=Path(__file__).resolve().parents[2]/'.github/workflows/ci.yml'
    try:
        counts=validate(path.read_text(encoding='utf-8'))
        recovery_counts=validate_recovery(path.read_text(encoding='utf-8'))
        hermetic=(path.parents[1]/'scripts/test_suite_hermeticity.py').read_text(encoding='utf-8')
        for script in HERMETIC_ONLY:
            require(f'".github/scripts/{script}"' in hermetic,f'{script} lost its only CI execution')
    except (OSError,ValueError) as error:
        print(f'Hook partition contract failed: {error}',file=sys.stderr)
        return 1
    print(f'Hook partition contract validated: {counts}')
    print(f'Recovery installation contract validated: {recovery_counts}')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
