#!/usr/bin/env python3
"""Validate the deliberately narrow hook-job partition contract (stdlib only).

Run as a required step in each hook matrix cell. These checks complement,
not replace, actionlint, workflow review, and actual native-host execution.
"""
from __future__ import annotations
import ast
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
# the guard to all 76 reviewed command steps without duplicating the workflow here.
# Release-workflow and Codex identity regressions run in separate native steps.
# The guard matrix, ca-codex adapter and dual-host store suites have no direct
# step: the hermetic isolation run is their only execution (HERMETIC_ONLY).
HERMETIC_ONLY = ('test_hook_guards.py', 'test_codex_adapter.py', 'test_dual_host_store.py')
PREVIOUS_COMMANDS_SHA256 = '091a92554695fbb82b5f3027d5ecb0b1076d350947b960219fddc39dd5f711e2'
COMMANDS_SHA256 = 'ded35eea9a75a8ec9d9a4d76e986dd48763f4258962945ffd527bb0c20d85974'
HOOK_TIMEOUT = "    timeout-minutes: ${{ matrix.os == 'windows-latest' && matrix.partition == 'contracts' && 45 || 20 }}\n"
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


# Finite reviewed roles: original suites stay in the legacy digest; metadata
# does not become a merge-queue test. Exact blocks keep commands, guards,
# credentials and uploader pins reviewable, as for native qualification above.
PYTHON_SOURCE_ROLES = {
    'Prepare Python source-test inputs': r"""      - name: Prepare Python source-test inputs
        id: python_source_prepare
        if: matrix.os == 'windows-latest' && matrix.partition == 'contracts'
        shell: bash
        run: >-
          python -B .github/scripts/major_qualification_report.py prepare-source
          --repo . --output "${{ runner.temp }}/python-source-inputs"
          --job-name "[CHECK] | [CORE] | Hook contract  <os: windows-latest · partition: contracts>"
""",
    'Observe original interrupted output publication tests': r"""      - name: Observe original interrupted output publication tests
        id: python_publisher_observed
        if: matrix.os == 'windows-latest' && matrix.partition == 'contracts'
        shell: bash
        run: >-
          python -B .github/scripts/major_qualification_report.py observe-python
          --repo . --source-payload "${{ runner.temp }}/python-source-inputs"
          --output "${{ runner.temp }}/python-publisher-observation.json"
          -- .github/scripts/test_generated_output.py
""",
    'Prepare Q02 implementation source-test inputs': r"""      - name: Prepare Q02 implementation source-test inputs
        id: q02_source_prepare
        if: matrix.os == 'windows-latest' && matrix.partition == 'contracts'
        shell: bash
        run: >-
          python -B .github/scripts/major_qualification_report.py prepare-source
          --repo . --source-profile major-readiness-implementation-v1
          --output "${{ runner.temp }}/q02-source-inputs"
          --job-name "[CHECK] | [CORE] | Hook contract  <os: windows-latest · partition: contracts>"
""",
    'Observe original Q02 readiness implementation tests': r"""      - name: Observe original Q02 readiness implementation tests
        id: q02_readiness_observed
        if: matrix.os == 'windows-latest' && matrix.partition == 'contracts'
        shell: bash
        run: >-
          python -B .github/scripts/major_qualification_report.py observe-python
          --repo . --source-profile major-readiness-implementation-v1
          --source-payload "${{ runner.temp }}/q02-source-inputs"
          --output "${{ runner.temp }}/python-q02-readiness-observation.json"
          -- .github/scripts/test_major_readiness.py
""",
    'Observe original Q02 publication guard tests': r"""      - name: Observe original Q02 publication guard tests
        id: q02_release_observed
        if: matrix.os == 'windows-latest' && matrix.partition == 'contracts'
        shell: bash
        run: >-
          python -B .github/scripts/major_qualification_report.py observe-python
          --repo . --source-profile major-readiness-implementation-v1
          --source-payload "${{ runner.temp }}/q02-source-inputs"
          --output "${{ runner.temp }}/python-q02-release-observation.json"
          -- .github/scripts/test_release_workflow.py
""",
    'Observe original skill-proof freshness tests': r"""      - name: Observe original skill-proof freshness tests
        id: python_proof_observed
        if: matrix.os == 'windows-latest' && matrix.partition == 'contracts'
        shell: bash
        run: >-
          python -B .github/scripts/major_qualification_report.py observe-python
          --repo . --source-payload "${{ runner.temp }}/python-source-inputs"
          --output "${{ runner.temp }}/python-proof-observation.json"
          -- .github/scripts/test_check_skill_proof_fresh.py
""",
    'Upload Python source-test inputs': r"""      - name: Upload Python source-test inputs
        id: python_source_upload
        if: ${{ !cancelled() && (success() || failure()) && matrix.os == 'windows-latest' && matrix.partition == 'contracts' && steps.python_source_prepare.outcome == 'success' }}
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: major-source-inputs-hooks-windows-contracts
          path: ${{ runner.temp }}/python-source-inputs/
          if-no-files-found: error
          retention-days: 14
          include-hidden-files: true
          overwrite: false
""",
    'Upload Q02 implementation source-test inputs': r"""      - name: Upload Q02 implementation source-test inputs
        id: q02_source_upload
        if: ${{ !cancelled() && (success() || failure()) && matrix.os == 'windows-latest' && matrix.partition == 'contracts' && steps.q02_source_prepare.outcome == 'success' }}
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: major-source-inputs-q02-implementation
          path: ${{ runner.temp }}/q02-source-inputs/
          if-no-files-found: error
          retention-days: 14
          include-hidden-files: true
          overwrite: false
""",
    'Retain original Python source-test observations': r"""      - name: Retain original Python source-test observations
        if: ${{ !cancelled() && (success() || failure()) && matrix.os == 'windows-latest' && matrix.partition == 'contracts' && steps.python_source_prepare.outcome == 'success' }}
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: python-source-observations-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: ${{ runner.temp }}/python-*-observation.json
          if-no-files-found: error
          retention-days: 14
          include-hidden-files: false
          overwrite: false
""",
    'Emit original Python source qualification report': r"""      - name: Emit original Python source qualification report
        id: python_qualification_emit
        if: ${{ !cancelled() && matrix.os == 'windows-latest' && matrix.partition == 'contracts' && github.event_name == 'push' && (github.ref == 'refs/heads/main' || github.ref == 'refs/heads/major/state-contracts') && hashFiles('.github/integration-candidate.json') != '' && steps.python_publisher_observed.outcome == 'success' && steps.python_proof_observed.outcome == 'success' && steps.python_source_upload.outcome == 'success' && steps.q02_readiness_observed.outcome == 'success' && steps.q02_release_observed.outcome == 'success' && steps.q02_source_upload.outcome == 'success' }}
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          python -B .github/scripts/major_qualification_report.py emit \
            --repo . --output "${{ runner.temp }}/qualification.json" \
            --job-name "[CHECK] | [CORE] | Hook contract  <os: windows-latest · partition: contracts>" \
            --observation "publisher=${{ runner.temp }}/python-publisher-observation.json" \
            --observation "skill-proof=${{ runner.temp }}/python-proof-observation.json" \
            --observation "q02-readiness=${{ runner.temp }}/python-q02-readiness-observation.json" \
            --observation "q02-release=${{ runner.temp }}/python-q02-release-observation.json" \
            --payload-root "major-source-inputs-hooks-windows-contracts=${{ github.workspace }}" \
            --payload-root "major-source-inputs-q02-implementation=${{ github.workspace }}"
          python -c 'import json,os; from pathlib import Path; record=json.loads((Path(os.environ["RUNNER_TEMP"])/"qualification.json").read_text()); job_id=record["job_id"]; assert type(job_id) is int and job_id > 0; out=open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8"); print("artifact_name=major-qualification-"+str(job_id),file=out); out.close()'
""",
    'Upload major qualification report': r"""      - name: Upload major qualification report
        if: steps.python_qualification_emit.outcome == 'success'
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: ${{ steps.python_qualification_emit.outputs.artifact_name }}
          path: ${{ runner.temp }}/qualification.json
          if-no-files-found: error
          retention-days: 14
          include-hidden-files: false
          overwrite: false

""",
}

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
    if hit[1] in ('>','>-'):
        # These owned command scalars use ordinary equally-indented lines.
        # Refuse unsupported folded shapes rather than misread shell input.
        require(all(line and not line.startswith((' ', '\t')) for line in lines),
                'Unsupported folded command shape')
        return ' '.join(lines).rstrip()
    return '\n'.join(lines).rstrip()



def python_source_roles(block: str) -> dict[str,str]:
    steps=step_blocks(block)
    found={name:[step for step in steps if step.startswith('      - name: '+name+'\n')]
           for name in PYTHON_SOURCE_ROLES}
    if not any(found.values()):return {}
    for name,expected in PYTHON_SOURCE_ROLES.items():
        require(found[name]==[expected], 'Python source qualification role changed or repeated: '+name)
    pre=block.split('    steps:\n',1)[0]
    require(pre.count('    permissions:\n')==1, 'Python source metadata permissions missing or repeated')
    permission_lines=pre.split('    permissions:\n',1)[1].split('    env:\n',1)[0].splitlines()
    require([line for line in permission_lines if line.strip() and not line.lstrip().startswith('#')]
            == ['      contents: read','      actions: read'], 'Python source metadata permissions changed')
    require(re.findall(r'(?m)^\s+(?:GH_TOKEN|GITHUB_TOKEN):.*$',block)
            == ['          GH_TOKEN: ${{ github.token }}'], 'Python source credentials escaped metadata emission')
    require(block.count('${{ github.token }}')==1 and 'secrets.' not in block,
            'Python source credentials escaped metadata emission')
    expected_order=[steps.index(PYTHON_SOURCE_ROLES[name]) for name in PYTHON_SOURCE_ROLES]
    require(expected_order==sorted(expected_order), 'Python source role ordering changed')
    for name,entry in (('Test interrupted output publication','test_generated_output.py'),
                       ("Run the T-79 skill-proof-freshness guard's own unit tests",'test_check_skill_proof_fresh.py'),
                       ('Test authenticated major readiness admission and refusal','test_major_readiness.py'),
                       ('Run hosted release-workflow contract tests','test_release_workflow.py')):
        selected=[step for step in steps if step.startswith('      - name: '+name+'\n')]
        require(len(selected)==1 and command(selected[0])=='python .github/scripts/'+entry
                and re.findall(r'^        if: (.*)$',selected[0],re.M)==[
                    "(matrix.partition == 'all' || matrix.partition == 'contracts') && !(matrix.os == 'windows-latest' && matrix.partition == 'contracts')"],
                'Python source observer must replace one original invocation on its exact cell')
    return {name:found[name][0] for name in PYTHON_SOURCE_ROLES}


def reviewed_python_source_event_guards(block: str) -> set[str]:
    roles=python_source_roles(block)
    if not roles:return set()
    emit=roles['Emit original Python source qualification report']
    predicate=re.findall(r'^        if: (.*)$',emit,re.M)[0]
    require(re.findall(r'(?m)^\s+if: (.*)$',block).count(predicate)==1,
            'Python metadata predicate reused by an ordinary test')
    return {predicate}


def command_digest(commands: list[str]) -> str:
    payload = json.dumps(commands, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def validate(
    text: str,
    expected_digest: str = COMMANDS_SHA256,
    expected_counts: dict[str, int] | None = None,
) -> dict[str,int]:
    if expected_counts is None:
        expected_counts={'contracts':75,'isolation':1,'guard':1,'setup':3,'native_setup':1}
    block=job_block(text,'hooks')
    pre=block.split('    steps:\n',1)[0]
    require(pre.count(MATRIX)==1,'Expected exactly the reviewed four-cell matrix')
    # No additional matrix members/axes may silently create empty cells.
    matrix_tail=pre.split('      matrix:\n',1)[1].split('    runs-on:',1)[0]
    require(matrix_tail == MATRIX, 'Matrix includes unreviewed cells or axes')
    require('      fail-fast: false\n' in pre,'Do not cancel sibling evidence on failure')
    require('    if: needs.changes.outputs.hooks == \'true\'\n' in pre,'Hook applicability changed')
    require('    runs-on: ${{ matrix.os }}\n' in pre,'Native operating systems must remain native')
    require(HOOK_TIMEOUT in pre,'Only Windows contracts may use the bounded45-minute budget; other hook cells retain20minutes')
    require('continue-on-error:' not in block,'Required hook checks cannot soften failures')
    require(pre.count(NATIVE_READER_ENV)==1,'Use the fixed same-job qualified native reader')
    roles=python_source_roles(block)
    reviewed_python_source_event_guards(block)
    counters={'contracts':0,'isolation':0,'guard':0,'setup':0,'native_setup':0}
    commands=[]
    for step in step_blocks(block):
        if step in roles.values():continue
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
        observed_original = roles and cmd in ('python .github/scripts/test_generated_output.py',
                                               'python .github/scripts/test_check_skill_proof_fresh.py',
                                               'python .github/scripts/test_major_readiness.py',
                                               'python .github/scripts/test_release_workflow.py')
        if not observed_original:
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
        self.assertIn("    timeout-minutes: ${{ matrix.os == 'windows-latest' && matrix.partition == 'contracts' && 45 || 20 }}\n",pre)

    def test_budget_exception_cannot_change_host_partition_or_other_ceiling(self):
        for changed in (
            HOOK_TIMEOUT.replace('windows-latest','macos-latest'),
            HOOK_TIMEOUT.replace("'contracts'","'isolation'"),
            HOOK_TIMEOUT.replace('45 || 20','45 || 45'),
            HOOK_TIMEOUT.replace('45 || 20','25 || 20'),
            '    timeout-minutes: 45\n',
            '    timeout-minutes: 25\n',
            '    timeout-minutes: 20\n',
        ):
            with self.subTest(drift=changed):
                self.assertNotEqual(changed, HOOK_TIMEOUT)
                self.bad(HOOK_TIMEOUT,changed)

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
    def test_timeout_ceiling_cannot_expand(self):
        changed=HOOK_TIMEOUT.replace('45 || 20','46 || 20')
        self.assertNotEqual(changed, HOOK_TIMEOUT)
        self.bad(HOOK_TIMEOUT,changed)
    def test_deleted_contract_command_fails(self): self.bad("      - name: contracts\n        if: matrix.partition == 'all' || matrix.partition == 'contracts'\n        run: python contract.py\n",'')
    def test_replaced_contract_command_fails(self): self.bad('python contract.py','python replacement.py')
    def test_duplicated_contract_command_fails(self): self.bad('        run: python contract.py\n','        run: python contract.py\n      - name: duplicate\n        if: matrix.partition == \'all\' || matrix.partition == \'contracts\'\n        run: python contract.py\n')



class SourceQualificationRoleTests(unittest.TestCase):
    def current(self):
        return (Path(__file__).resolve().parents[2]/'.github/workflows/ci.yml').read_text(encoding='utf8')

    def test_current_roles_keep_the_original_inventory_and_counts(self):
        try:
            counters=validate(self.current())
        except ValueError as error:
            self.fail(str(error))
        self.assertEqual(counters,{'contracts':75,'isolation':1,'guard':1,'setup':3,'native_setup':1})

    def test_folded_scalar_keeps_every_interpolation_and_argument(self):
        block=('      - name: fixed\n        run: >-\n'
               '          python owner.py --output "${{ runner.temp }}/owned.json"\n'
               '          --name "${{ github.job }}"\n')
        self.assertEqual(command(block),'python owner.py --output "${{ runner.temp }}/owned.json" --name "${{ github.job }}"')
        self.assertEqual(command(block.replace('run: >-','run: |')),'python owner.py --output "${{ runner.temp }}/owned.json"\n--name "${{ github.job }}"')

    def test_source_roles_cannot_change_guards_repeat_original_tests_or_forward_credentials(self):
        text=self.current()
        self.assertEqual(validate(text)['contracts'],75)
        for before,after in (
            ("id: python_source_prepare\n        if: matrix.os == 'windows-latest'", "id: python_source_prepare\n        if: matrix.os == 'ubuntu-latest'"),
            ('-- .github/scripts/test_generated_output.py','-- .github/scripts/test_generated_output.py; python .github/scripts/test_generated_output.py'),
            ('-- .github/scripts/test_check_skill_proof_fresh.py','-- .github/scripts/unreviewed.py'),
            ('id: python_source_prepare\n','id: python_source_prepare\n        env:\n          GH_TOKEN: ${{ github.token }}\n'),
            ("github.event_name == 'push' && (github.ref == 'refs/heads/main'", "github.event_name == 'pull_request' && (github.ref == 'refs/heads/main'"),
            ('include-hidden-files: true','include-hidden-files: false'),
            ('--payload-root "major-source-inputs-hooks-windows-contracts=${{ github.workspace }}"','--payload-root "major-source-inputs-hooks-windows-contracts=${{ runner.temp }}"'),
            ('id: python_qualification_emit\n','id: python_qualification_emit\n        continue-on-error: true\n'),
        ):
            # Restrict mutations to hooks so unrelated reviewed roles are intact.
            block=job_block(text,'hooks');self.assertIn(before,block)
            changed=text.replace(block,block.replace(before,after,1),1)
            with self.subTest(change=before),self.assertRaises(ValueError):validate(changed)
        block=job_block(text,'hooks');observer=next(step for step in step_blocks(block) if 'id: python_publisher_observed' in step)
        with self.assertRaises(ValueError):validate(text.replace(observer,observer+observer,1))
        unknown="      - name: unreviewed source command\n        if: matrix.partition == 'all' || matrix.partition == 'contracts'\n        run: python unreviewed.py\n"
        with self.assertRaises(ValueError):validate(text.replace(block,block+unknown,1))

    def test_q02_roles_refuse_changed_profile_payload_results_and_authority(self):
        text=self.current();block=job_block(text,'hooks');self.assertEqual(validate(text)['contracts'],75)
        changes=(
            ('Prepare Q02 implementation source-test inputs','--source-profile major-readiness-implementation-v1','--source-profile python-hooks-v1'),
            ('Prepare Q02 implementation source-test inputs','q02-source-inputs','foreign-source-inputs'),
            ('Observe original Q02 readiness implementation tests','-- .github/scripts/test_major_readiness.py','-- .github/scripts/test_major_readiness.py -k partial'),
            ('Observe original Q02 publication guard tests','-- .github/scripts/test_release_workflow.py','-- .github/scripts/unreviewed.py'),
            ('Emit original Python source qualification report','--observation "q02-readiness=${{ runner.temp }}/python-q02-readiness-observation.json"','--observation "unknown=${{ runner.temp }}/python-q02-readiness-observation.json"'),
            ('Emit original Python source qualification report','--observation "q02-release=${{ runner.temp }}/python-q02-release-observation.json"',''),
            ('Emit original Python source qualification report','major-source-inputs-q02-implementation=${{ github.workspace }}','major-source-inputs-q02-implementation=${{ runner.temp }}'),
            ('Emit original Python source qualification report',"steps.q02_source_upload.outcome == 'success'",'true'),
            ('Emit original Python source qualification report',"steps.q02_readiness_observed.outcome == 'success'",'true'),
            ('Prepare Q02 implementation source-test inputs','        shell: bash\n','        env:\n          GH_TOKEN: ${{ github.token }}\n        shell: bash\n'),
            ('Upload Q02 implementation source-test inputs','actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9','actions/upload-artifact@'+'0'*40),
            ('Upload Q02 implementation source-test inputs','include-hidden-files: true','include-hidden-files: false'),
            ('Upload Q02 implementation source-test inputs','overwrite: false','overwrite: true'),
        )
        for name,before,after in changes:
            original=PYTHON_SOURCE_ROLES[name];self.assertIn(before,original)
            changed=text.replace(original,original.replace(before,after,1),1)
            with self.subTest(role=name,field=before),self.assertRaises(ValueError):validate(changed)
        observed=PYTHON_SOURCE_ROLES['Observe original Q02 readiness implementation tests']
        with self.assertRaises(ValueError):validate(text.replace(observed,observed+observed,1))
        for name in ('Test authenticated major readiness admission and refusal','Run hosted release-workflow contract tests'):
            fallback=next(step for step in step_blocks(block) if step.startswith('      - name: '+name+'\n'))
            exclusive="(matrix.partition == 'all' || matrix.partition == 'contracts') && !(matrix.os == 'windows-latest' && matrix.partition == 'contracts')"
            self.assertIn(exclusive,fallback)
            with self.subTest(fallback=name),self.assertRaises(ValueError):
                validate(text.replace(fallback,fallback.replace(exclusive,"matrix.partition == 'all' || matrix.partition == 'contracts'"),1))

    def test_exact_hw04_addition_preserves_all_prior_ordered_commands(self):
        text=self.current();block=job_block(text,'hooks');roles=python_source_roles(block)
        commands=[command(step) for step in step_blocks(block) if step not in roles.values()
                  and command(step) not in (None,NATIVE_PREPARE_COMMAND,GUARD)]
        added=NPM_PURE_COMMAND
        self.assertEqual(commands.count(added),1)
        self.assertEqual(len(commands),76)
        previous=[value for value in commands if value!=added]
        self.assertEqual(len(previous),75)
        self.assertEqual(command_digest(previous),PREVIOUS_COMMANDS_SHA256)
        self.assertEqual(command_digest(commands),COMMANDS_SHA256)
        owned=next(step for step in step_blocks(block) if command(step)==added)
        with self.assertRaises(ValueError):validate(text.replace(owned,'',1))
        with self.assertRaises(ValueError):validate(text.replace(owned,owned+owned,1))
        changed=owned.replace(added,'python .github/scripts/unreviewed.py')
        with self.assertRaises(ValueError):validate(text.replace(owned,changed,1))



NPM_PURE_COMMAND = 'python .github/scripts/test_npm_binding_observation.py AdmissionTests IdentityLimitTests RuntimePortabilityTests'
NPM_PRODUCER_COMMAND = 'python .github/scripts/test_npm_binding_observation.py ProducerBoundaryTests'
NPM_NATIVE_STEP = ('      - name: Test original Python npm binding producer on the qualified runtime\n'
                   '        run: ' + NPM_PRODUCER_COMMAND + '\n')
NPM_NATIVE_BUILD = '      - name: Build native qualified candidate\n        run: >-\n          python tools/build-artifacts.py\n          --output "${{ runner.temp }}/artifact-candidate"\n          --test-observation "${{ runner.temp }}/native-tests.json"\n          --npm-binding-observations "${{ runner.temp }}/native-npm-binding-identities"\n'

def validate_native_npm_owner(text: str) -> None:
    native = job_block(text, 'artifact-native-build')
    steps = step_blocks(native)
    require(steps.count(NPM_NATIVE_STEP) == 1, 'Pinned native runtime producer unit missing or repeated')
    require(steps.count(NPM_NATIVE_BUILD) == 1, 'Original native builder command changed or repeated')
    require(steps.index(NPM_NATIVE_STEP) < steps.index(NPM_NATIVE_BUILD), 'Producer unit must precede original builder')
    setup = ('      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0\n'
             '        with:\n          python-version: "3.14"\n')
    require(steps.count(setup) == 1 and steps.index(setup) < steps.index(NPM_NATIVE_STEP), 'Producer requires original pinned Python 3.14 setup')
    platforms = re.findall(r'^            expected_platform: (\S+)$', native, re.M)
    require(sorted(platforms) == ['darwin/amd64','darwin/arm64','linux/amd64','linux/arm64','windows/amd64','windows/arm64'], 'Producer must retain all six native platforms')
    require('    runs-on: ${{ matrix.os }}\n' in native, 'Native runtime platform routing changed')
    hooks = job_block(text, 'hooks')
    selected = [command(step) for step in step_blocks(hooks) if command(step) and 'test_npm_binding_observation.py' in command(step)]
    require(selected == [NPM_PURE_COMMAND], 'Hook npm controls must be exactly the three runtime-independent classes')
    native_selected = [command(step) for step in steps if command(step) and 'test_npm_binding_observation.py' in command(step)]
    require(native_selected == [NPM_PRODUCER_COMMAND], 'Native producer must execute once without filtering its method')


class NpmRuntimeOwnerTests(unittest.TestCase):
    def current(self):
        return (Path(__file__).resolve().parents[2]/'.github/workflows/ci.yml').read_text(encoding='utf8')

    def test_full_runtime_producer_uses_each_pinned_native_runtime_once(self):
        try:
            validate_native_npm_owner(self.current())
        except ValueError as error:
            self.fail(str(error))

    def test_runtime_owner_refuses_unpinned_repeated_conditional_or_incomplete_routes(self):
        text=self.current();validate_native_npm_owner(text)
        native=job_block(text,'artifact-native-build')
        changes=(
            (NPM_NATIVE_STEP,''),
            (NPM_NATIVE_STEP,NPM_NATIVE_STEP+NPM_NATIVE_STEP),
            (NPM_NATIVE_STEP,NPM_NATIVE_STEP.replace('        run:', '        if: false\n        run:')),
            (NPM_NATIVE_STEP+NPM_NATIVE_BUILD,NPM_NATIVE_BUILD+NPM_NATIVE_STEP),
            ('python-version: "3.14"','python-version: "3.x"'),
            ('setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0','setup-python@'+'0'*40),
            ('expected_platform: linux/arm64','expected_platform: linux/amd64'),
            (NPM_NATIVE_BUILD,NPM_NATIVE_BUILD.replace('python tools/build-artifacts.py','python tools/other.py')),
            (NPM_PRODUCER_COMMAND,NPM_PRODUCER_COMMAND+' -k subset'),
        )
        for before,after in changes:
            self.assertIn(before,native)
            with self.subTest(field=before),self.assertRaises(ValueError):
                validate_native_npm_owner(text.replace(native,native.replace(before,after,1),1))
        for replacement in (NPM_PRODUCER_COMMAND,NPM_PURE_COMMAND.replace(' RuntimePortabilityTests',''),NPM_PURE_COMMAND+' ProducerBoundaryTests'):
            with self.subTest(hooks=replacement),self.assertRaises(ValueError):
                validate_native_npm_owner(text.replace(NPM_PURE_COMMAND,replacement,1))

    def test_class_selection_is_disjoint_complete_and_preserves_all_twenty_one_methods(self):
        path=Path(__file__).with_name('test_npm_binding_observation.py')
        tree=ast.parse(path.read_text(encoding='utf8'))
        classes={node.name:{m.name for m in node.body if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)) and m.name.startswith('test_')}
                 for node in tree.body if isinstance(node,ast.ClassDef)}
        selected={'AdmissionTests','IdentityLimitTests','RuntimePortabilityTests'}
        self.assertEqual(set(classes),selected|{'ProducerBoundaryTests'})
        self.assertEqual(sum(len(classes[name]) for name in selected),20)
        self.assertEqual(len(classes['ProducerBoundaryTests']),1)
        self.assertEqual(NPM_PURE_COMMAND.split()[2:],['AdmissionTests','IdentityLimitTests','RuntimePortabilityTests'])
        self.assertEqual(NPM_PRODUCER_COMMAND.split()[2:],['ProducerBoundaryTests'])
        self.assertEqual(sum(map(len,classes.values())),21)


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
