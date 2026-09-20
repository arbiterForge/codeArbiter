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

DIRECT = 'python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"'
ISOLATION = 'python .github/scripts/test_suite_hermeticity.py'
GUARD = 'python .github/scripts/test_hook_ci_partition.py'
# sha256(compact JSON of the ordered pre-partition command list). This binds
# the guard to all 56 reviewed commands without duplicating the workflow here.
COMMANDS_SHA256 = '9faff01b461e37dfa821d13e6da766a9476b44f32555242af001686df52f95fd'
MATRIX = '''        os: [ubuntu-latest, windows-latest, macos-latest]
        partition: [all]
        exclude:
          - os: windows-latest
            partition: all
        include:
          - os: windows-latest
            partition: contracts
          - os: windows-latest
            partition: functional
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
        expected_counts={'contracts':54,'functional':1,'isolation':1,'guard':1,'setup':2}
    block=job_block(text,'hooks')
    pre=block.split('    steps:\n',1)[0]
    require(pre.count(MATRIX)==1,'Expected exactly the reviewed five-cell matrix')
    # No additional matrix members/axes may silently create empty cells.
    matrix_tail=pre.split('      matrix:\n',1)[1].split('    runs-on:',1)[0]
    require(matrix_tail == MATRIX, 'Matrix includes unreviewed cells or axes')
    require('      fail-fast: false\n' in pre,'Do not cancel sibling evidence on failure')
    require('    if: needs.changes.outputs.hooks == \'true\'\n' in pre,'Hook applicability changed')
    require('    runs-on: ${{ matrix.os }}\n' in pre,'Native operating systems must remain native')
    require('    timeout-minutes: 20\n' in pre,'Hook cells must retain the bounded 20-minute ceiling')
    require('continue-on-error:' not in block,'Required hook checks cannot soften failures')
    counters={'contracts':0,'functional':0,'isolation':0,'guard':0,'setup':0}
    commands=[]
    for step in step_blocks(block):
        cmd=command(step)
        predicates=re.findall(r'^        if: (.*)$',step,re.M)
        if cmd is None:
            counters['setup']+=1
            require(not predicates,'Shared setup must run in every cell')
            require('uses: actions/checkout@' in step or 'uses: actions/setup-python@' in step,'Review new setup actions before partitioning')
            if 'uses: actions/checkout@' in step:
                for field in ('fetch-depth: 0','fetch-tags: true','persist-credentials: false'):
                    require(field in step,f'Checkout lost {field}')
            continue
        if cmd==GUARD:
            counters['guard']+=1
            require(not predicates,'Partition validator must run in every cell')
            continue
        commands.append(cmd)
        kind='functional' if cmd==DIRECT else 'isolation' if cmd==ISOLATION else 'contracts'
        counters[kind]+=1
        want=f"matrix.partition == 'all' || matrix.partition == '{kind}'"
        require(predicates==[want],f'Command has incorrect partition: {cmd[:100]}')
    require(counters['guard']==1,'Expected one mandatory partition validation')
    require(counters['setup']==2,'Expected checkout plus Python setup')
    require(counters==expected_counts,'Expected reviewed command partition')
    require(command_digest(commands)==expected_digest,'Existing hook command inventory or order changed')
    gate=job_block(text,'ci-passed')
    require(re.search(r'^      - hooks\s*$',gate,re.M) is not None,'Merge readiness no longer awaits hooks')
    require('needs.hooks.result' in gate or "needs['hooks'].result" in gate,'Merge readiness no longer enforces hooks')
    return counters


def fixture() -> str:
    pre="jobs:\n  hooks:\n    needs: changes\n    if: needs.changes.outputs.hooks == 'true'\n    strategy:\n      fail-fast: false\n      matrix:\n"+MATRIX+"    runs-on: ${{ matrix.os }}\n    timeout-minutes: 20\n    steps:\n"
    pre+='      - uses: actions/checkout@'+'1'*40+'\n        with:\n          fetch-depth: 0\n          fetch-tags: true\n          persist-credentials: false\n'
    pre+='      - uses: actions/setup-python@'+'2'*40+'\n'
    pre+='      - name: guard\n        run: '+GUARD+'\n'
    for kind,cmd in [('contracts','python contract.py'),('functional',DIRECT),('isolation',ISOLATION)]:
        pre+=f"      - name: {kind}\n        if: matrix.partition == 'all' || matrix.partition == '{kind}'\n        run: {cmd}\n"
    return pre+"  ci-passed:\n    needs:\n      - hooks\n    steps:\n      - run: echo '${{ needs.hooks.result }}'\n"


class PartitionContractTests(unittest.TestCase):
    fixture_digest=command_digest(['python contract.py',DIRECT,ISOLATION])
    fixture_counts={'contracts':1,'functional':1,'isolation':1,'guard':1,'setup':2}
    def bad(self, before: str, after: str):
        with self.assertRaises(ValueError): validate(fixture().replace(before,after,1),self.fixture_digest,self.fixture_counts)
    def test_valid_five_cell_contract(self): self.assertEqual(validate(fixture(),self.fixture_digest,self.fixture_counts)['functional'],1)
    def test_missing_partition_fails(self): self.bad('            partition: isolation\n','')
    def test_wrong_windows_exclusion_fails(self): self.bad('partition: all','partition: contracts')
    def test_extra_axis_fails(self): self.bad('    runs-on:','        extra: [x]\n    runs-on:')
    def test_wrong_functional_route_fails(self): self.bad("|| matrix.partition == 'functional'","|| matrix.partition == 'isolation'")
    def test_unassigned_contract_fails(self): self.bad("        if: matrix.partition == 'all' || matrix.partition == 'contracts'\n",'')
    def test_guard_cannot_be_skipped(self): self.bad('      - name: guard\n','      - name: guard\n        if: false\n')
    def test_softened_check_fails(self): self.bad('      - name: functional\n','      - name: functional\n        continue-on-error: true\n')
    def test_missing_full_history_fails(self): self.bad('fetch-depth: 0','fetch-depth: 1')
    def test_missing_tags_fails(self): self.bad('fetch-tags: true','fetch-tags: false')
    def test_lost_gate_dependency_fails(self): self.bad('      - hooks\n','')
    def test_lost_gate_result_fails(self): self.bad('needs.hooks.result','needs.other.result')
    def test_missing_direct_suite_fails(self): self.bad(DIRECT,'python different.py')
    def test_fail_fast_cannot_be_enabled(self): self.bad('fail-fast: false','fail-fast: true')
    def test_timeout_ceiling_cannot_expand(self): self.bad('timeout-minutes: 20','timeout-minutes: 30')
    def test_deleted_contract_command_fails(self): self.bad("      - name: contracts\n        if: matrix.partition == 'all' || matrix.partition == 'contracts'\n        run: python contract.py\n",'')
    def test_replaced_contract_command_fails(self): self.bad('python contract.py','python replacement.py')
    def test_duplicated_contract_command_fails(self): self.bad('        run: python contract.py\n','        run: python contract.py\n      - name: duplicate\n        if: matrix.partition == \'all\' || matrix.partition == \'contracts\'\n        run: python contract.py\n')


def main() -> int:
    results=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PartitionContractTests))
    if not results.wasSuccessful() or results.skipped: return 1
    path=Path(__file__).resolve().parents[2]/'.github/workflows/ci.yml'
    try:
        counts=validate(path.read_text(encoding='utf-8'))
    except (OSError,ValueError) as error:
        print(f'Hook partition contract failed: {error}',file=sys.stderr)
        return 1
    print(f'Hook partition contract validated: {counts}')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
