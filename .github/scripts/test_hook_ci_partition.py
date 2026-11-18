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
RECOVERY_WINDOWS = "        if: matrix.os == 'windows-latest'\n"
RECOVERY_OTHER_HOSTS = "        if: matrix.os != 'windows-latest'\n"
RECOVERY_BINDING_RUN = ('        run: >-\n'
                        '          python -B .github/scripts/major_qualification_report.py ')
RECOVERY_PROFILE = '          --repo . --source-profile workflow-recovery-runtime-v1\n'
RECOVERY_INPUTS = '${{ runner.temp }}/workflow-recovery-runtime-inputs'
RECOVERY_UPLOAD_PIN = 'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2'
RECOVERY_RUN_SUFFIX = '${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}'


def recovery_consumer_steps() -> list[str]:
    def named(name):
        return '      - name: ' + name + '\n'

    def upload(name, artifact, path, hidden='false'):
        return (named(name) + RECOVERY_WINDOWS + '        uses: ' + RECOVERY_UPLOAD_PIN + '\n'
                '        with:\n          name: ' + artifact + '\n          path: ' + path + '\n'
                '          if-no-files-found: error\n          retention-days: 14\n'
                '          include-hidden-files: ' + hidden + '\n          overwrite: false\n')

    steps = [named('Prepare workflow recovery runtime source inputs') + RECOVERY_WINDOWS
             + RECOVERY_BINDING_RUN + 'prepare-source\n' + RECOVERY_PROFILE
             + '          --job-name "[CHECK] | [CORE] | Workflow recovery  <os: windows-latest>"\n'
             + '          --output "' + RECOVERY_INPUTS + '"\n']
    roles = (('runtime', 'Test durable runtime and concurrency', 'Observe original durable runtime and concurrency tests',
              'Retain original workflow recovery runtime observation'),
             ('cli', 'Test actual installed helper and native effects', 'Observe original installed helper and native effects',
              'Retain original workflow recovery CLI observation'),
             ('hosts', 'Test actual host event and readonly notice seams', 'Observe original host event and readonly notice seams',
              'Retain original workflow recovery host observation'))
    uploads = [upload('Upload workflow recovery runtime source inputs',
                      'major-source-inputs-workflow-recovery-runtime', RECOVERY_INPUTS + '/', 'true')]
    for cmd, (role, plain, observed, upload_name) in zip(RECOVERY_COMMANDS[:3], roles):
        steps.append(named(plain) + RECOVERY_OTHER_HOSTS + '        run: ' + cmd + '\n')
        if role == 'runtime':
            env = ''
        else:
            env = ('        env:\n          WORKFLOW_RECOVERY_INSTALLATION_OBSERVATION: '
                   '${{ runner.temp }}/workflow-recovery-' + role + '-installation.json\n')
        observation = 'workflow-recovery-' + role + '-observation'
        steps.append(named(observed) + RECOVERY_WINDOWS + env
                     + RECOVERY_BINDING_RUN + 'observe-python\n' + RECOVERY_PROFILE
                     + '          --source-payload "' + RECOVERY_INPUTS + '"\n'
                     + '          --output "${{ runner.temp }}/' + observation + '.json"\n'
                     + '          -- ' + cmd.removeprefix('python ') + '\n')
        uploads.append(upload(upload_name, observation + '-' + RECOVERY_RUN_SUFFIX,
                              '${{ runner.temp }}/' + observation + '.json'))
    steps.append(named('Test atomic contract generation') + '        run: ' + RECOVERY_COMMANDS[3] + '\n')
    steps.append(named('Test fresh linked review resubmission') + RECOVERY_OTHER_HOSTS + '        run: ' + RECOVERY_COMMANDS[4] + '\n')
    steps.append(named('Observe original fresh linked review resubmission') + RECOVERY_WINDOWS
                 + RECOVERY_BINDING_RUN + 'observe-python\n' + RECOVERY_PROFILE
                 + '          --source-payload "' + RECOVERY_INPUTS + '"\n'
                 + '          --output "${{ runner.temp }}/review-resubmission-observation.json"\n'
                 + '          -- ' + RECOVERY_COMMANDS[4].removeprefix('python ') + '\n')
    uploads.append(upload('Retain original review resubmission observation',
                          'review-resubmission-observation-' + RECOVERY_RUN_SUFFIX,
                          '${{ runner.temp }}/review-resubmission-observation.json'))
    uploads.append(named('Resolve Windows workflow recovery upload directory') + RECOVERY_WINDOWS + r"""        id: recovery-native-upload
        shell: pwsh
        run: |
          $directory = (Resolve-Path -LiteralPath $env:ARTIFACT_TEST_INSTALLATION -ErrorAction Stop).ProviderPath
          foreach ($name in @('release.json', 'ca-artifact-windows-amd64.exe')) {
            if (!(Test-Path -LiteralPath (Join-Path $directory $name) -PathType Leaf)) {
              throw "Missing workflow recovery upload member: $name"
            }
          }
          "directory=$($directory.Replace('\', '/'))" >> $env:GITHUB_OUTPUT
""")
    native = '${{ steps.recovery-native-upload.outputs.directory }}/'
    uploads.append(upload('Upload original workflow recovery native installation',
                          'workflow-recovery-native-' + RECOVERY_RUN_SUFFIX,
                          '|\n            ' + native + 'release.json\n            ' + native + 'ca-artifact-windows-amd64.exe'))
    return steps + uploads


# sha256(compact JSON of the ordered pre-partition command list). This binds
# the guard to all 76 reviewed command steps without duplicating the workflow here.
# Release-workflow and Codex identity regressions run in separate native steps.
# The guard matrix, ca-codex adapter and dual-host store suites have no direct
# step: the hermetic isolation run is their only execution (HERMETIC_ONLY).
HERMETIC_ONLY = ('test_hook_guards.py', 'test_codex_adapter.py', 'test_dual_host_store.py')
PREVIOUS_COMMANDS_SHA256 = '091a92554695fbb82b5f3027d5ecb0b1076d350947b960219fddc39dd5f711e2'
COMMANDS_SHA256 = '02be87b265a36430f8b32554cb726b6bdc557806f830f8d7ea1894e50e97ab6e'
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
EARLY_HOOK_SOURCE_STEPS = ('Prepare single-owner hook source-test inputs',
                           'Observe original sync-core tool unit tests',
                           'Observe original surface-generator unit tests')
PYTHON_SOURCE_ROLES = {'Observe original sync-core tool unit tests': (
                          '      - name: Observe original sync-core tool unit tests\n'
                          '        id: sf13_sync_observed\n'
                          "        if: matrix.os == 'windows-latest' && matrix.partition == 'contracts'\n"
                          '        shell: bash\n'
                          '        run: >-\n'
                          '          python -B .github/scripts/major_qualification_report.py observe-python\n'
                          '          --repo . --source-profile hooks-single-owner-findings-v1\n'
                          '          --source-payload "${{ runner.temp }}/single-owner-hook-source-inputs"\n'
                          '          --output "${{ runner.temp }}/python-sf13-sync-observation.json"\n'
                          '          -- .github/scripts/test_sync_core.py\n'),
 'Observe original surface-generator unit tests': (
                          '      - name: Observe original surface-generator unit tests\n'
                          '        id: route_generator_observed\n'
                          "        if: matrix.os == 'windows-latest' && matrix.partition == 'contracts'\n"
                          '        shell: bash\n'
                          '        run: >-\n'
                          '          python -B .github/scripts/major_qualification_report.py observe-python\n'
                          '          --repo . --source-profile hooks-single-owner-findings-v1\n'
                          '          --source-payload "${{ runner.temp }}/single-owner-hook-source-inputs"\n'
                          '          --output "${{ runner.temp }}/python-route-generator-observation.json"\n'
                          '          -- .github/scripts/test_build_surface.py\n'),
 'Prepare hook finding source-test inputs': '      - name: Prepare hook finding source-test inputs\n'
                                            '        id: hook_finding_source_prepare\n'
                                            "        if: matrix.os == 'windows-latest' && matrix.partition == "
                                            "'contracts'\n"
                                            '        shell: bash\n'
                                            '        run: >-\n'
                                            '          python -B .github/scripts/major_qualification_report.py '
                                            'prepare-source\n'
                                            '          --repo . --source-profile hooks-finding-contracts-v1\n'
                                            '          --output "${{ runner.temp }}/hook-finding-source-inputs"\n'
                                            '          --job-name "[CHECK] | [CORE] | Hook contract  <os: '
                                            'windows-latest · partition: contracts>"\n',
 'Observe original review funnel contract': '      - name: Observe original review funnel contract\n'
                                            '        id: hook_review_observed\n'
                                            "        if: matrix.os == 'windows-latest' && matrix.partition == "
                                            "'contracts'\n"
                                            '        shell: bash\n'
                                            '        run: >-\n'
                                            '          python -B .github/scripts/major_qualification_report.py '
                                            'observe-python\n'
                                            '          --repo . --source-profile hooks-finding-contracts-v1\n'
                                            '          --source-payload "${{ runner.temp '
                                            '}}/hook-finding-source-inputs"\n'
                                            '          --output "${{ runner.temp '
                                            '}}/python-hook-review-observation.json"\n'
                                            '          -- .github/scripts/test_review_funnel.py\n',
 'Prepare single-owner hook source-test inputs': '      - name: Prepare single-owner hook source-test inputs\n'
                                                 '        id: single_hook_prepare\n'
                                                 "        if: matrix.os == 'windows-latest' && matrix.partition == "
                                                 "'contracts'\n"
                                                 '        shell: bash\n'
                                                 '        run: >-\n'
                                                 '          python -B .github/scripts/major_qualification_report.py '
                                                 'prepare-source\n'
                                                 '          --repo . --source-profile hooks-single-owner-findings-v1\n'
                                                 '          --output "${{ runner.temp '
                                                 '}}/single-owner-hook-source-inputs"\n'
                                                 '          --job-name "[CHECK] | [CORE] | Hook contract  <os: '
                                                 'windows-latest · partition: contracts>"\n',
 'Observe original mode transition and audit tests': '      - name: Observe original mode transition and audit tests\n'
                                                     '        id: single_hookf02_modelib_observed\n'
                                                     "        if: matrix.os == 'windows-latest' && matrix.partition == "
                                                     "'contracts'\n"
                                                     '        shell: bash\n'
                                                     '        run: >-\n'
                                                     '          python -B '
                                                     '.github/scripts/major_qualification_report.py observe-python\n'
                                                     '          --repo . --source-profile '
                                                     'hooks-single-owner-findings-v1\n'
                                                     '          --source-payload "${{ runner.temp '
                                                     '}}/single-owner-hook-source-inputs"\n'
                                                     '          --output "${{ runner.temp '
                                                     '}}/python-finite-hookf02-modelib-observation.json"\n'
                                                     '          -- .github/scripts/test_modelib.py\n',
 'Observe original persona transition tests': '      - name: Observe original persona transition tests\n'
                                              '        id: single_hookf01_observed\n'
                                              "        if: matrix.os == 'windows-latest' && matrix.partition == "
                                              "'contracts'\n"
                                              '        shell: bash\n'
                                              '        run: >-\n'
                                              '          python -B .github/scripts/major_qualification_report.py '
                                              'observe-python\n'
                                              '          --repo . --source-profile hooks-single-owner-findings-v1\n'
                                              '          --source-payload "${{ runner.temp '
                                              '}}/single-owner-hook-source-inputs"\n'
                                              '          --output "${{ runner.temp '
                                              '}}/python-finite-hookf01-observation.json"\n'
                                              '          -- .github/scripts/test_prompt_submit.py\n',
 'Observe original shared native manifest contract': (
                          '      - name: Observe original shared native manifest contract\n'
                          '        id: native_manifest_observed\n'
                          "        if: matrix.os == 'windows-latest' && matrix.partition == 'contracts'\n"
                          '        shell: bash\n'
                          '        run: >-\n'
                          '          python -B .github/scripts/major_qualification_report.py observe-python\n'
                          '          --repo . --source-profile hooks-single-owner-findings-v1\n'
                          '          --source-payload "${{ runner.temp }}/single-owner-hook-source-inputs"\n'
                          '          --output "${{ runner.temp }}/python-finite-native-manifest-observation.json"\n'
                          '          -- .github/scripts/test_artifact_manifest_contract.py\n'),
 'Prepare Python source-test inputs': '      - name: Prepare Python source-test inputs\n'
                                      '        id: python_source_prepare\n'
                                      "        if: matrix.os == 'windows-latest' && matrix.partition == 'contracts'\n"
                                      '        shell: bash\n'
                                      '        run: >-\n'
                                      '          python -B .github/scripts/major_qualification_report.py '
                                      'prepare-source\n'
                                      '          --repo . --output "${{ runner.temp }}/python-source-inputs"\n'
                                      '          --job-name "[CHECK] | [CORE] | Hook contract  <os: windows-latest · '
                                      'partition: contracts>"\n',
 'Observe original interrupted output publication tests': '      - name: Observe original interrupted output '
                                                          'publication tests\n'
                                                          '        id: python_publisher_observed\n'
                                                          "        if: matrix.os == 'windows-latest' && "
                                                          "matrix.partition == 'contracts'\n"
                                                          '        shell: bash\n'
                                                          '        run: >-\n'
                                                          '          python -B '
                                                          '.github/scripts/major_qualification_report.py '
                                                          'observe-python\n'
                                                          '          --repo . --source-payload "${{ runner.temp '
                                                          '}}/python-source-inputs"\n'
                                                          '          --output "${{ runner.temp '
                                                          '}}/python-publisher-observation.json"\n'
                                                          '          -- .github/scripts/test_generated_output.py\n',
 'Prepare Q02 implementation source-test inputs': '      - name: Prepare Q02 implementation source-test inputs\n'
                                                  '        id: q02_source_prepare\n'
                                                  "        if: matrix.os == 'windows-latest' && matrix.partition == "
                                                  "'contracts'\n"
                                                  '        shell: bash\n'
                                                  '        run: >-\n'
                                                  '          python -B .github/scripts/major_qualification_report.py '
                                                  'prepare-source\n'
                                                  '          --repo . --source-profile '
                                                  'major-readiness-implementation-v1\n'
                                                  '          --output "${{ runner.temp }}/q02-source-inputs"\n'
                                                  '          --job-name "[CHECK] | [CORE] | Hook contract  <os: '
                                                  'windows-latest · partition: contracts>"\n',
 'Observe original Q02 readiness implementation tests': '      - name: Observe original Q02 readiness implementation '
                                                        'tests\n'
                                                        '        id: q02_readiness_observed\n'
                                                        "        if: matrix.os == 'windows-latest' && matrix.partition "
                                                        "== 'contracts'\n"
                                                        '        shell: bash\n'
                                                        '        run: >-\n'
                                                        '          python -B '
                                                        '.github/scripts/major_qualification_report.py observe-python\n'
                                                        '          --repo . --source-profile '
                                                        'major-readiness-implementation-v1\n'
                                                        '          --source-payload "${{ runner.temp '
                                                        '}}/q02-source-inputs"\n'
                                                        '          --output "${{ runner.temp '
                                                        '}}/python-q02-readiness-observation.json"\n'
                                                        '          -- .github/scripts/test_major_readiness.py\n',
 'Observe original Q02 publication guard tests': '      - name: Observe original Q02 publication guard tests\n'
                                                 '        id: q02_release_observed\n'
                                                 "        if: matrix.os == 'windows-latest' && matrix.partition == "
                                                 "'contracts'\n"
                                                 '        shell: bash\n'
                                                 '        run: >-\n'
                                                 '          python -B .github/scripts/major_qualification_report.py '
                                                 'observe-python\n'
                                                 '          --repo . --source-profile '
                                                 'major-readiness-implementation-v1\n'
                                                 '          --source-payload "${{ runner.temp }}/q02-source-inputs"\n'
                                                 '          --output "${{ runner.temp '
                                                 '}}/python-q02-release-observation.json"\n'
                                                 '          -- .github/scripts/test_release_workflow.py\n',
 'Observe original typed verdict tests': '      - name: Observe original typed verdict tests\n'
                                         '        id: single_cf06_observed\n'
                                         "        if: matrix.os == 'windows-latest' && matrix.partition == "
                                         "'contracts'\n"
                                         '        shell: bash\n'
                                         '        run: >-\n'
                                         '          python -B .github/scripts/major_qualification_report.py '
                                         'observe-python\n'
                                         '          --repo . --source-profile hooks-single-owner-findings-v1\n'
                                         '          --source-payload "${{ runner.temp '
                                         '}}/single-owner-hook-source-inputs"\n'
                                         '          --output "${{ runner.temp }}/python-finite-cf06-observation.json"\n'
                                         '          -- .github/scripts/test_verdictlib.py\n',
 'Observe original bounded verifier-subprocess contract tests': (
     '      - name: Observe original bounded verifier-subprocess contract tests\n'
     '        id: bounded_reader_observed\n'
     "        if: matrix.os == 'windows-latest' && matrix.partition == 'contracts'\n"
     '        shell: bash\n'
     '        run: >-\n'
     '          python -B .github/scripts/major_qualification_report.py observe-python\n'
     '          --repo . --source-profile hooks-single-owner-findings-v1\n'
     '          --source-payload "${{ runner.temp }}/single-owner-hook-source-inputs"\n'
     '          --output "${{ runner.temp }}/python-finite-bounded-reader-observation.json"\n'
     '          -- .github/scripts/test_boundedproc.py\n'
 ),
 'Observe original Git channel contracts after the release planner': (
     '      - name: Observe original Git channel contracts after the release planner\n'
     '        id: git_channel_observed\n'
     "        if: matrix.os == 'windows-latest' && matrix.partition == 'contracts'\n"
     '        run: |\n'
     '          python .github/scripts/test_release_target.py\n'
     '          python -B .github/scripts/major_qualification_report.py observe-python --repo . --source-profile hooks-single-owner-findings-v1 --source-payload "${{ runner.temp }}/single-owner-hook-source-inputs" --output "${{ runner.temp }}/python-finite-git-channel-observation.json" -- .github/scripts/test_marketplace_git_channels.py\n'
 ),
 'Observe original skill-proof freshness tests': '      - name: Observe original skill-proof freshness tests\n'
                                                 '        id: python_proof_observed\n'
                                                 "        if: matrix.os == 'windows-latest' && matrix.partition == "
                                                 "'contracts'\n"
                                                 '        shell: bash\n'
                                                 '        run: >-\n'
                                                 '          python -B .github/scripts/major_qualification_report.py '
                                                 'observe-python\n'
                                                 '          --repo . --source-payload "${{ runner.temp '
                                                 '}}/python-source-inputs"\n'
                                                 '          --output "${{ runner.temp '
                                                 '}}/python-proof-observation.json"\n'
                                                 '          -- .github/scripts/test_check_skill_proof_fresh.py\n',
 'Observe original scoped Pi payload identity tests': '      - name: Observe original scoped Pi payload identity '
                                                      'tests\n'
                                                      '        id: single_hookf03_observed\n'
                                                      "        if: matrix.os == 'windows-latest' && matrix.partition "
                                                      "== 'contracts'\n"
                                                      '        shell: bash\n'
                                                      '        run: >-\n'
                                                      '          python -B '
                                                      '.github/scripts/major_qualification_report.py observe-python\n'
                                                      '          --repo . --source-profile '
                                                      'hooks-single-owner-findings-v1\n'
                                                      '          --source-payload "${{ runner.temp '
                                                      '}}/single-owner-hook-source-inputs"\n'
                                                      '          --output "${{ runner.temp '
                                                      '}}/python-finite-hookf03-observation.json"\n'
                                                      '          -- .github/scripts/test_pi_payload_identity.py\n',
 'Observe original measurement contract tests': '      - name: Observe original measurement contract tests\n'
                                                '        id: single_tf02_observed\n'
                                                "        if: matrix.os == 'windows-latest' && matrix.partition == "
                                                "'contracts'\n"
                                                '        shell: bash\n'
                                                '        run: >-\n'
                                                '          python -B .github/scripts/major_qualification_report.py '
                                                'observe-python\n'
                                                '          --repo . --source-profile hooks-single-owner-findings-v1\n'
                                                '          --source-payload "${{ runner.temp '
                                                '}}/single-owner-hook-source-inputs"\n'
                                                '          --output "${{ runner.temp '
                                                '}}/python-finite-tf02-observation.json"\n'
                                                '          -- tools/test_measurement_contracts.py\n',
 'Upload single-owner hook source-test inputs': '      - name: Upload single-owner hook source-test inputs\n'
                                                '        id: single_hook_upload\n'
                                                '        if: ${{ !cancelled() && (success() || failure()) && matrix.os '
                                                "== 'windows-latest' && matrix.partition == 'contracts' && "
                                                "steps.single_hook_prepare.outcome == 'success' }}\n"
                                                '        uses: '
                                                'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # '
                                                'v7.0.2\n'
                                                '        with:\n'
                                                '          name: major-source-inputs-hooks-single-owner\n'
                                                '          path: ${{ runner.temp }}/single-owner-hook-source-inputs/\n'
                                                '          if-no-files-found: error\n'
                                                '          retention-days: 14\n'
                                                '          include-hidden-files: true\n'
                                                '          overwrite: false\n',
 'Upload hook finding source-test inputs': '      - name: Upload hook finding source-test inputs\n'
                                           '        id: hook_finding_source_upload\n'
                                           '        if: ${{ !cancelled() && (success() || failure()) && matrix.os == '
                                           "'windows-latest' && matrix.partition == 'contracts' && "
                                           "steps.hook_finding_source_prepare.outcome == 'success' }}\n"
                                           '        uses: '
                                           'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2\n'
                                           '        with:\n'
                                           '          name: major-source-inputs-hooks-findings-windows-contracts\n'
                                           '          path: ${{ runner.temp }}/hook-finding-source-inputs/\n'
                                           '          if-no-files-found: error\n'
                                           '          retention-days: 14\n'
                                           '          include-hidden-files: true\n'
                                           '          overwrite: false\n',
 'Upload Python source-test inputs': '      - name: Upload Python source-test inputs\n'
                                     '        id: python_source_upload\n'
                                     '        if: ${{ !cancelled() && (success() || failure()) && matrix.os == '
                                     "'windows-latest' && matrix.partition == 'contracts' && "
                                     "steps.python_source_prepare.outcome == 'success' }}\n"
                                     '        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # '
                                     'v7.0.2\n'
                                     '        with:\n'
                                     '          name: major-source-inputs-hooks-windows-contracts\n'
                                     '          path: ${{ runner.temp }}/python-source-inputs/\n'
                                     '          if-no-files-found: error\n'
                                     '          retention-days: 14\n'
                                     '          include-hidden-files: true\n'
                                     '          overwrite: false\n',
 'Upload Q02 implementation source-test inputs': '      - name: Upload Q02 implementation source-test inputs\n'
                                                 '        id: q02_source_upload\n'
                                                 '        if: ${{ !cancelled() && (success() || failure()) && '
                                                 "matrix.os == 'windows-latest' && matrix.partition == 'contracts' && "
                                                 "steps.q02_source_prepare.outcome == 'success' }}\n"
                                                 '        uses: '
                                                 'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # '
                                                 'v7.0.2\n'
                                                 '        with:\n'
                                                 '          name: major-source-inputs-q02-implementation\n'
                                                 '          path: ${{ runner.temp }}/q02-source-inputs/\n'
                                                 '          if-no-files-found: error\n'
                                                 '          retention-days: 14\n'
                                                 '          include-hidden-files: true\n'
                                                 '          overwrite: false\n',
 'Retain original Python source-test observations': '      - name: Retain original Python source-test observations\n'
                                                    '        if: ${{ !cancelled() && (success() || failure()) && '
                                                    "matrix.os == 'windows-latest' && matrix.partition == 'contracts' "
                                                    "&& steps.python_source_prepare.outcome == 'success' }}\n"
                                                    '        uses: '
                                                    'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 '
                                                    '# v7.0.2\n'
                                                    '        with:\n'
                                                    '          name: python-source-observations-${{ github.sha }}-${{ '
                                                    'github.run_id }}-${{ github.run_attempt }}\n'
                                                    '          path: ${{ runner.temp }}/python-*-observation.json\n'
                                                    '          if-no-files-found: error\n'
                                                    '          retention-days: 14\n'
                                                    '          include-hidden-files: false\n'
                                                    '          overwrite: false\n',
 'Emit original Python source qualification report': '      - name: Emit original Python source qualification report\n'
                                                     '        id: python_qualification_emit\n'
                                                     "        if: ${{ !cancelled() && matrix.os == 'windows-latest' && "
                                                     "matrix.partition == 'contracts' && github.event_name == 'push' "
                                                     "&& (github.ref == 'refs/heads/main' || github.ref == "
                                                     "'refs/heads/major/state-contracts') && "
                                                     "hashFiles('.github/integration-candidate.json') != '' && "
                                                     "steps.python_publisher_observed.outcome == 'success' && "
                                                     "steps.python_proof_observed.outcome == 'success' && "
                                                     "steps.python_source_upload.outcome == 'success' && "
                                                     "steps.q02_readiness_observed.outcome == 'success' && "
                                                     "steps.q02_release_observed.outcome == 'success' && "
                                                     "steps.q02_source_upload.outcome == 'success' && "
                                                     "steps.hook_review_observed.outcome == 'success' && "
                                                     "steps.hook_finding_source_upload.outcome == 'success' && "
                                                     "steps.single_hook_prepare.outcome == 'success' && "
                                                     "steps.single_hookf02_modelib_observed.outcome == 'success' && "
                                                     "steps.single_hookf01_observed.outcome == 'success' && "
                                                     "steps.single_hookf03_observed.outcome == 'success' && "
                                                     "steps.single_cf06_observed.outcome == 'success' && "
                                                     "steps.bounded_reader_observed.outcome == 'success' && "
                                                     "steps.git_channel_observed.outcome == 'success' && "
                                                     "steps.native_manifest_observed.outcome == 'success' && "
                                                     "steps.single_tf02_observed.outcome == 'success' && "
                                                     "steps.single_hook_upload.outcome == 'success' }}\n"
                                                     '        shell: bash\n'
                                                     '        env:\n'
                                                     '          GH_TOKEN: ${{ github.token }}\n'
                                                     '        run: |\n'
                                                     '          python -B '
                                                     '.github/scripts/major_qualification_report.py emit \\\n'
                                                     '            --repo . --output "${{ runner.temp '
                                                     '}}/qualification.json" \\\n'
                                                     '            --job-name "[CHECK] | [CORE] | Hook contract  <os: '
                                                     'windows-latest · partition: contracts>" \\\n'
                                                     '            --observation "publisher=${{ runner.temp '
                                                     '}}/python-publisher-observation.json" \\\n'
                                                     '            --observation "hook-review=${{ runner.temp '
                                                     '}}/python-hook-review-observation.json" \\\n'
                                                     '            --observation "skill-proof=${{ runner.temp '
                                                     '}}/python-proof-observation.json" \\\n'
                                                     '            --observation "q02-readiness=${{ runner.temp '
                                                     '}}/python-q02-readiness-observation.json" \\\n'
                                                     '            --observation "q02-release=${{ runner.temp '
                                                     '}}/python-q02-release-observation.json" \\\n'
                                                     '            --observation "finite-hookf02-modelib=${{ '
                                                     'runner.temp }}/python-finite-hookf02-modelib-observation.json" '
                                                     '\\\n'
                                                     '            --observation "finite-hookf01=${{ runner.temp '
                                                     '}}/python-finite-hookf01-observation.json" \\\n'
                                                     '            --observation "finite-hookf03=${{ runner.temp '
                                                     '}}/python-finite-hookf03-observation.json" \\\n'
                                                     '            --observation "finite-cf06=${{ runner.temp '
                                                     '}}/python-finite-cf06-observation.json" \\\n'
                                                     '            --observation "finite-bounded-reader=${{ runner.temp }}/python-finite-bounded-reader-observation.json" \\\n'
                                                     '            --observation "finite-git-channel=${{ runner.temp }}/python-finite-git-channel-observation.json" \\\n'
                                                     '            --observation "finite-native-manifest=${{ runner.temp '
                                                     '}}/python-finite-native-manifest-observation.json" \\\n'
                                                     '            --observation "finite-tf02=${{ runner.temp '
                                                     '}}/python-finite-tf02-observation.json" \\\n'
                                                     '            --payload-root '
                                                     '"major-source-inputs-hooks-windows-contracts=${{ '
                                                     'github.workspace }}" \\\n'
                                                     '            --payload-root '
                                                     '"major-source-inputs-q02-implementation=${{ github.workspace }}" '
                                                     '\\\n'
                                                     '            --payload-root '
                                                     '"major-source-inputs-hooks-findings-windows-contracts=${{ '
                                                     'github.workspace }}" \\\n'
                                                     '            --payload-root '
                                                     '"major-source-inputs-hooks-single-owner=${{ github.workspace '
                                                     '}}"\n'
                                                     "          python -c 'import json,os; from pathlib import Path; "
                                                     'record=json.loads((Path(os.environ["RUNNER_TEMP"])/"qualification.json").read_text()); '
                                                     'job_id=record["job_id"]; assert type(job_id) is int and job_id > '
                                                     '0; out=open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8"); '
                                                     'print("artifact_name=major-qualification-"+str(job_id),file=out); '
                                                     "out.close()'\n",
 'Upload major qualification report': '      - name: Upload major qualification report\n'
                                      "        if: steps.python_qualification_emit.outcome == 'success'\n"
                                      '        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 '
                                      '# v7.0.2\n'
                                      '        with:\n'
                                      '          name: ${{ steps.python_qualification_emit.outputs.artifact_name }}\n'
                                      '          path: ${{ runner.temp }}/qualification.json\n'
                                      '          if-no-files-found: error\n'
                                      '          retention-days: 14\n'
                                      '          include-hidden-files: false\n'
                                      '          overwrite: false\n'
                                      '\n'}

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
    roles_in_order = [*EARLY_HOOK_SOURCE_STEPS,
                      *(name for name in PYTHON_SOURCE_ROLES if name not in EARLY_HOOK_SOURCE_STEPS)]
    expected_order=[steps.index(PYTHON_SOURCE_ROLES[name]) for name in roles_in_order]
    require(expected_order==sorted(expected_order), 'Python source role ordering changed')
    for name,entry in (('Run sync-core tool unit tests','test_sync_core.py'),
                       ('Run surface-generator unit tests','test_build_surface.py'),
                       ('Test shared native manifest contract', 'test_artifact_manifest_contract.py'),
                       ('Test interrupted output publication','test_generated_output.py'),
                       ('Run read-only review funnel contract','test_review_funnel.py'),
                       ("Run the T-79 skill-proof-freshness guard's own unit tests",'test_check_skill_proof_fresh.py'),
                       ('Test authenticated major readiness admission and refusal','test_major_readiness.py'),
                       ('Run hosted release-workflow contract tests','test_release_workflow.py'),
                       ('Run mode-plane core contract (ADR-0030)', 'test_modelib.py'),
                       ('Run prompt-seam interceptor contract (ADR-0030)', 'test_prompt_submit.py'),
                       ('Run typed qualification-outcome contract tests', 'test_verdictlib.py'),
                       ('Run bounded verifier-subprocess contract tests', 'test_boundedproc.py')
                       ):
        selected=[step for step in steps if step.startswith('      - name: '+name+'\n')]
        require(len(selected)==1 and command(selected[0])=='python .github/scripts/'+entry
                and re.findall(r'^        if: (.*)$',selected[0],re.M)==[
                    "(matrix.partition == 'all' || matrix.partition == 'contracts') && !(matrix.os == 'windows-latest' && matrix.partition == 'contracts')"],
                'Python source observer must replace one original invocation on its exact cell')
    manifest_fallback = next(step for step in steps if step.startswith('      - name: Test shared native manifest contract\n'))
    require(steps.index(manifest_fallback) + 1
            == steps.index(PYTHON_SOURCE_ROLES['Observe original shared native manifest contract']),
            'Manifest observer must replace its original Windows command in place')
    require(sum('.github/scripts/test_boundedproc.py' in (command(step) or '') for step in steps) == 2,
            'bounded reader suite must run once in each original partition')
    direct_channel = [step for step in steps if step.startswith("      - name: Run per-target release planner and Git channel contracts\n")]
    require(len(direct_channel) == 1
            and command(direct_channel[0]) == 'python .github/scripts/test_release_target.py\npython .github/scripts/test_marketplace_git_channels.py'
            and re.findall(r'^        if: (.*)$', direct_channel[0], re.M) == ["(matrix.partition == 'all' || matrix.partition == 'contracts') && !(matrix.os == 'windows-latest' && matrix.partition == 'contracts')"],
            'Git channel and release planner original commands or partition changed')
    channel_observer = PYTHON_SOURCE_ROLES['Observe original Git channel contracts after the release planner']
    require(steps.index(direct_channel[0]) + 1 == steps.index(channel_observer),
            'Git channel observer must replace its original Windows command in place')
    for entry in ('test_release_target.py', 'test_marketplace_git_channels.py'):
        require(sum('.github/scripts/' + entry in (command(step) or '') for step in steps) == 2,
                'Git channel and release planner must run once in each original partition')
    return {name:found[name][0] for name in PYTHON_SOURCE_ROLES}


def reviewed_python_source_event_guards(block: str) -> set[str]:
    roles=python_source_roles(block)
    if not roles:return set()
    emit=roles['Emit original Python source qualification report']
    predicate=re.findall(r'^        if: (.*)$',emit,re.M)[0]
    require(re.findall(r'(?m)^\s+if: (.*)$',block).count(predicate)==1,
            'Python metadata predicate reused by an ordinary test')
    return {predicate}


IMPACT_SOURCE_ROLES = {'Prepare single-owner Impact source-test inputs': '      - name: Prepare single-owner Impact source-test inputs\n'
                                                   '        id: single_impact_prepare\n'
                                                   '        shell: bash\n'
                                                   '        run: >-\n'
                                                   '          python -B .github/scripts/major_qualification_report.py '
                                                   'prepare-source\n'
                                                   '          --repo . --source-profile '
                                                   'impact-single-owner-findings-v1\n'
                                                   '          --output "${{ runner.temp '
                                                   '}}/single-owner-impact-source-inputs"\n'
                                                   '          --job-name "[CHECK] | [REPO] | Impact planner '
                                                   'contract"\n',
 'Observe original impact planner contract tests': '      - name: Observe original impact planner contract tests\n'
                                                   '        id: single_cf05_observed\n'
                                                   '        shell: bash\n'
                                                   '        run: >-\n'
                                                   '          python -B .github/scripts/major_qualification_report.py '
                                                   'observe-python\n'
                                                   '          --repo . --source-profile '
                                                   'impact-single-owner-findings-v1\n'
                                                   '          --source-payload "${{ runner.temp '
                                                   '}}/single-owner-impact-source-inputs"\n'
                                                   '          --output "${{ runner.temp '
                                                   '}}/python-finite-cf05-observation.json"\n'
                                                   '          -- .github/scripts/test_ci_impact.py\n',
 'Observe original payload-version gate tests': '      - name: Observe original payload-version gate tests\n'
                                                '        id: single_cf07_observed\n'
                                                '        shell: bash\n'
                                                '        run: >-\n'
                                                '          python -B .github/scripts/major_qualification_report.py '
                                                'observe-python\n'
                                                '          --repo . --source-profile impact-single-owner-findings-v1\n'
                                                '          --source-payload "${{ runner.temp '
                                                '}}/single-owner-impact-source-inputs"\n'
                                                '          --output "${{ runner.temp '
                                                '}}/python-finite-cf07-observation.json"\n'
                                                '          -- .github/scripts/test_payload_version_gate.py\n',
 'Upload single-owner Impact source-test inputs': '      - name: Upload single-owner Impact source-test inputs\n'
                                                  '        id: single_impact_upload\n'
                                                  '        if: ${{ !cancelled() && (success() || failure()) && '
                                                  "steps.single_impact_prepare.outcome == 'success' }}\n"
                                                  '        uses: '
                                                  'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # '
                                                  'v7.0.2\n'
                                                  '        with:\n'
                                                  '          name: major-source-inputs-impact-single-owner\n'
                                                  '          path: ${{ runner.temp '
                                                  '}}/single-owner-impact-source-inputs/\n'
                                                  '          if-no-files-found: error\n'
                                                  '          retention-days: 14\n'
                                                  '          include-hidden-files: true\n'
                                                  '          overwrite: false\n',
 'Retain original Impact source-test observations': '      - name: Retain original Impact source-test observations\n'
                                                    '        if: ${{ !cancelled() && (success() || failure()) && '
                                                    "steps.single_impact_prepare.outcome == 'success' }}\n"
                                                    '        uses: '
                                                    'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 '
                                                    '# v7.0.2\n'
                                                    '        with:\n'
                                                    '          name: impact-source-observations-${{ github.sha }}-${{ '
                                                    'github.run_id }}-${{ github.run_attempt }}\n'
                                                    '          path: ${{ runner.temp '
                                                    '}}/python-finite-cf0*-observation.json\n'
                                                    '          if-no-files-found: error\n'
                                                    '          retention-days: 14\n'
                                                    '          include-hidden-files: false\n'
                                                    '          overwrite: false\n',
 'Emit original Impact source qualification report': '      - name: Emit original Impact source qualification report\n'
                                                     '        id: single_impact_emit\n'
                                                     "        if: ${{ !cancelled() && github.event_name == 'push' && "
                                                     "(github.ref == 'refs/heads/main' || github.ref == "
                                                     "'refs/heads/major/state-contracts') && "
                                                     "hashFiles('.github/integration-candidate.json') != '' && "
                                                     "steps.single_impact_prepare.outcome == 'success' && "
                                                     "steps.single_cf05_observed.outcome == 'success' && "
                                                     "steps.single_cf07_observed.outcome == 'success' && "
                                                     "steps.single_impact_upload.outcome == 'success' }}\n"
                                                     '        shell: bash\n'
                                                     '        env:\n'
                                                     '          GH_TOKEN: ${{ github.token }}\n'
                                                     '        run: |\n'
                                                     '          python -B '
                                                     '.github/scripts/major_qualification_report.py emit \\\n'
                                                     '            --repo . --output "${{ runner.temp '
                                                     '}}/qualification.json" \\\n'
                                                     '            --job-name "[CHECK] | [REPO] | Impact planner '
                                                     'contract" \\\n'
                                                     '            --observation "finite-cf05=${{ runner.temp '
                                                     '}}/python-finite-cf05-observation.json" \\\n'
                                                     '            --observation "finite-cf07=${{ runner.temp '
                                                     '}}/python-finite-cf07-observation.json" \\\n'
                                                     '            --payload-root '
                                                     '"major-source-inputs-impact-single-owner=${{ github.workspace '
                                                     '}}"\n'
                                                     "          python -c 'import json,os; from pathlib import Path; "
                                                     'record=json.loads((Path(os.environ["RUNNER_TEMP"])/"qualification.json").read_text()); '
                                                     'job_id=record["job_id"]; assert type(job_id) is int and job_id > '
                                                     '0; out=open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8"); '
                                                     'print("artifact_name=major-qualification-"+str(job_id),file=out); '
                                                     "out.close()'\n",
 'Upload major qualification report': '      - name: Upload major qualification report\n'
                                      "        if: steps.single_impact_emit.outcome == 'success'\n"
                                      '        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 '
                                      '# v7.0.2\n'
                                      '        with:\n'
                                      '          name: ${{ steps.single_impact_emit.outputs.artifact_name }}\n'
                                      '          path: ${{ runner.temp }}/qualification.json\n'
                                      '          if-no-files-found: error\n'
                                      '          retention-days: 14\n'
                                      '          include-hidden-files: false\n'
                                      '          overwrite: false\n'
                                      '\n'
                                      '\n'}

def impact_source_roles(block: str) -> dict[str,str]:
    steps=step_blocks(block)
    found={name:[step for step in steps if step.startswith('      - name: '+name+'\n')] for name in IMPACT_SOURCE_ROLES}
    if not any(found.values()):return {}
    for name,expected in IMPACT_SOURCE_ROLES.items():
        require(found[name]==[expected],'Impact source role changed or repeated: '+name)
    pre=block.split('    steps:\n',1)[0]
    require(pre.split('    permissions:\n',1)[1]=='      contents: read\n      actions: read\n','Impact metadata permissions changed')
    require(re.findall(r'(?m)^\s+(?:GH_TOKEN|GITHUB_TOKEN):.*$',block)==['          GH_TOKEN: ${{ github.token }}'],
            'Impact credentials escaped metadata emission')
    require(block.count('${{ github.token }}')==1 and 'secrets.' not in block,'Impact token authority changed')
    checkout=[s for s in steps if 'uses: actions/checkout@' in s]
    require(len(checkout)==1 and 'persist-credentials: false' in checkout[0],'Impact checkout retains credentials')
    require([steps.index(value) for value in IMPACT_SOURCE_ROLES.values()]==sorted(steps.index(value) for value in IMPACT_SOURCE_ROLES.values()),'Impact source role ordering changed')
    for script in ('.github/scripts/test_ci_impact.py','.github/scripts/test_payload_version_gate.py'):
        owners=[s for s in steps if command(s) and ('-- '+script) in command(s)]
        require(len(owners)==1 and owners[0] in IMPACT_SOURCE_ROLES.values(),'Impact original owner absent or repeated')
        require(not any(command(s)=='python '+script for s in steps),'Impact original suite repeated')
    return {name:rows[0] for name,rows in found.items()}


def reviewed_impact_source_event_guards(block: str) -> set[str]:
    roles=impact_source_roles(block)
    require(roles,'Impact original source roles missing')
    predicate=re.findall(r'^        if: (.*)$',roles['Emit original Impact source qualification report'],re.M)[0]
    require(re.findall(r'(?m)^\s+if: (.*)$',block).count(predicate)==1,
            'Impact metadata predicate reused by an ordinary test')
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
        if cmd == 'python .github/scripts/test_ci_impact.py --run-debug-suite .github/scripts/test_debug_workflow.py':
            require("        env:\n          PYTHONDONTWRITEBYTECODE: '1'\n"
                    "          MAJOR_DEBUG_SOURCE_PROFILE: ${{ matrix.os == 'windows-latest' && matrix.partition == 'contracts' && 'hooks-single-owner-findings-v1' || '' }}\n"
                    "        run: " + cmd + "\n" in step,
                    'Debug workflow evidence must use its original Hook contract command')
        commands.append(cmd)
        kind='isolation' if cmd==ISOLATION else 'contracts'
        counters[kind]+=1
        want=f"matrix.partition == 'all' || matrix.partition == '{kind}'"
        observed_original = roles and cmd in ('python .github/scripts/test_review_funnel.py',
                                               'python .github/scripts/test_sync_core.py',
                                               'python .github/scripts/test_build_surface.py',
                                               'python .github/scripts/test_generated_output.py',
                                               'python .github/scripts/test_artifact_manifest_contract.py',
                                               'python .github/scripts/test_check_skill_proof_fresh.py',
                                               'python .github/scripts/test_major_readiness.py',
                                               'python .github/scripts/test_release_workflow.py',
                                               'python .github/scripts/test_prompt_submit.py',
                                               'python .github/scripts/test_verdictlib.py',
                                               'python .github/scripts/test_boundedproc.py',
                                               'python .github/scripts/test_release_target.py\npython .github/scripts/test_marketplace_git_channels.py',
                                               'python .github/scripts/test_modelib.py')
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
    require(len(steps) >= 4, 'Recovery requires three setup steps and one original qualification')
    require(not any(re.search(r'^        if:', step, re.M) for step in steps[:4]), 'Recovery setup and qualification must be unconditional')
    require('uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1' in steps[0]
            and 'fetch-depth: 0' in steps[0] and 'persist-credentials: false' in steps[0], 'Recovery checkout pin/history/credential scope changed')
    require(steps[1] == '      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0\n'
            '        with:\n          python-version: "3.14"\n', 'Recovery Python setup changed')
    require(steps[2] == GO_SETUP, 'Recovery qualification requires the existing pinned Go setup')
    require(steps[3] == RECOVERY_PREPARE, 'Recovery must clear inherited installation input and qualify once before consumers')
    require([step.rstrip('\n') for step in steps[4:]] == [step.rstrip('\n') for step in recovery_consumer_steps()],
            'Recovery original commands, disjoint observer routes or owned artifact uploads changed')
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
    return pre + ''.join(recovery_consumer_steps())


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
        self.bad('      - name: Test durable runtime and concurrency\n',
                 '      - name: Test durable runtime and concurrency\n        env:\n          ARTIFACT_TEST_INSTALLATION: other-input\n')

    def test_recovery_refuses_duplicate_or_mixed_original_authority(self):
        observed = recovery_consumer_steps()[2]
        self.bad(observed, observed + observed)
        self.bad(RECOVERY_OTHER_HOSTS, RECOVERY_WINDOWS)
        self.bad('          -- .github/scripts/test_workflow_recovery.py\n',
                 '          -- .github/scripts/test_workflow_recovery.py -k subset\n')
        self.bad('          include-hidden-files: true\n', '          include-hidden-files: false\n')

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

    def test_recovery_upload_uses_only_existing_files_from_the_resolved_directory(self):
        self.bad('Resolve-Path -LiteralPath $env:ARTIFACT_TEST_INSTALLATION', 'Resolve-Path -LiteralPath .')
        self.bad(' -PathType Leaf', '')
        self.bad('${{ steps.recovery-native-upload.outputs.directory }}/release.json',
                 '${{ github.workspace }}/../workflow-recovery-native/release.json')
        self.bad('ca-artifact-windows-amd64.exe\n          if-no-files-found',
                 '*\n          if-no-files-found')

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

    def test_sync_core_observation_keeps_one_exact_original_invocation(self):
        text = self.current()
        observed = PYTHON_SOURCE_ROLES['Observe original sync-core tool unit tests']
        self.assertIn(observed, text)
        fallback = next(step for step in step_blocks(job_block(text, 'hooks'))
                        if step.startswith('      - name: Run sync-core tool unit tests\n'))
        for old, changed in (
            (observed, observed + observed),
            (observed, observed.replace('test_sync_core.py', 'test_sync_core.py -k subset')),
            (fallback, fallback.replace(" && !(matrix.os == 'windows-latest' && matrix.partition == 'contracts')", '')),
        ):
            self.assertNotEqual(old, changed)
            with self.subTest(changed=changed.splitlines()[0]), self.assertRaises(ValueError):
                validate(text.replace(old, changed, 1))

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



NPM_PURE_COMMAND = 'python .github/scripts/test_npm_binding_observation.py AdmissionTests IdentityLimitTests RuntimePortabilityTests HookF04FiniteFindingAdmissionTests'
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
    require(selected == [NPM_PURE_COMMAND], 'Hook npm controls must be exactly the four runtime-independent classes')
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
        for replacement in (NPM_PRODUCER_COMMAND,NPM_PURE_COMMAND.replace(' RuntimePortabilityTests',''),
                            NPM_PURE_COMMAND.replace(' HookF04FiniteFindingAdmissionTests',''),
                            NPM_PURE_COMMAND+' HookF04FiniteFindingAdmissionTests',
                            NPM_PURE_COMMAND+' ProducerBoundaryTests'):
            with self.subTest(hooks=replacement),self.assertRaises(ValueError):
                validate_native_npm_owner(text.replace(NPM_PURE_COMMAND,replacement,1))

    def test_class_selection_covers_every_declared_npm_test_once(self):
        path = Path(__file__).with_name('test_npm_binding_observation.py')
        tree = ast.parse(path.read_text(encoding='utf8'))
        declarations = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        classes = {
            node.name: [m.name for m in node.body
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name.startswith('test_')]
            for node in declarations
        }
        self.assertEqual(len(classes), len(declarations), 'duplicate npm test class')
        for name, methods in classes.items():
            with self.subTest(test_class=name):
                self.assertTrue(methods, 'npm test class must contribute an executed test')
                self.assertEqual(len(methods), len(set(methods)), 'duplicate npm test method')
        original_selected = {'AdmissionTests', 'IdentityLimitTests', 'RuntimePortabilityTests'}
        finding_class = 'HookF04FiniteFindingAdmissionTests'
        self.assertEqual(set(classes), original_selected | {'ProducerBoundaryTests', finding_class})
        self.assertEqual(classes['ProducerBoundaryTests'], ['test_original_python_producer_exports_opt_in_consumed_identities'])
        self.assertEqual(set(classes[finding_class]), {
            'test_hook_f04_requires_complete_original_six_platform_launch_transport',
            'test_hook_f04_refuses_missing_owner_or_unreviewed_finding_authority',
            'test_hook_f04_refuses_sidecar_identity_incomplete_named_case_and_projection_tampering',
        })
        self.assertEqual(NPM_PURE_COMMAND.split()[2:],[
            'AdmissionTests','IdentityLimitTests','RuntimePortabilityTests',finding_class])
        self.assertEqual(NPM_PRODUCER_COMMAND.split()[2:],['ProducerBoundaryTests'])
        self.assertFalse(set(NPM_PURE_COMMAND.split()[2:]) & set(NPM_PRODUCER_COMMAND.split()[2:]))
        self.assertEqual(set(NPM_PURE_COMMAND.split()[2:]) | set(NPM_PRODUCER_COMMAND.split()[2:]),set(classes))


class SingleOwnerFindingWorkflowTests(unittest.TestCase):
    def current(self):
        return (Path(__file__).resolve().parents[2]/'.github/workflows/ci.yml').read_text(encoding='utf8')

    def test_exact_six_source_owners_keep_original_invocations_and_closed_authority(self):
        text=self.current();hooks=job_block(text,'hooks');impact=job_block(text,'ci-impact')
        validate(text);hroles=python_source_roles(hooks);iroles=impact_source_roles(impact)
        self.assertTrue(iroles)
        for script in ('test_prompt_submit.py','test_verdictlib.py','test_boundedproc.py'):
            original='python .github/scripts/'+script
            self.assertEqual(sum(command(s)==original for s in step_blocks(hooks)),1)
            self.assertEqual(sum(bool(command(s) and command(s).endswith('-- .github/scripts/'+script)) for s in step_blocks(hooks)),1)
        for script in ('.github/scripts/test_pi_payload_identity.py','tools/test_measurement_contracts.py'):
            selected=[s for s in step_blocks(hooks) if command(s) and command(s).endswith('-- '+script)]
            self.assertEqual(len(selected),1)
            self.assertIn(selected[0],hroles.values())
            self.assertNotIn('test_pi_doctor.py',command(selected[0]))
        self.assertEqual(len(reviewed_impact_source_event_guards(impact)),1)

    def test_new_measurement_owner_and_actual_imports_select_its_required_hook_job(self):
        import fnmatch
        root=Path(__file__).resolve().parents[2]
        script=root/'tools/test_measurement_contracts.py'
        tree=ast.parse(script.read_text(encoding='utf8'))
        imports={node.args[0].value for node in ast.walk(tree) if isinstance(node,ast.Call)
                 and isinstance(node.func,ast.Name) and node.func.id=='load' and len(node.args)==1
                 and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str)}
        self.assertTrue(imports)
        subjects={'tools/test_measurement_contracts.py'}|{'tools/'+name+'.py' for name in imports}
        def selected(text):
            hooks=text.split('            hooks:\n',1)[1].split('            impact:\n',1)[0]
            patterns=re.findall(r"^              - '([^']+)'$",hooks,re.M)
            self.assertFalse([path for path in sorted(subjects) if not any(fnmatch.fnmatchcase(path,pattern) for pattern in patterns)],
                             'new unfiltered owner or an actual imported subject skips its hook controls')
        text=self.current();selected(text)
        for path in subjects:
            literal="              - '"+path+"'\n"
            self.assertIn(literal,text)
            with self.subTest(path=path),self.assertRaises(AssertionError):selected(text.replace(literal,'',1))

    def test_git_channel_source_inputs_select_the_existing_hook_job(self):
        workflow = self.current()
        hooks = workflow.split('            hooks:\n', 1)[1].split('            impact:\n', 1)[0]
        sources = {
            '.claude-plugin/marketplace.json', 'tools/build-host-packages.py', 'tools/host_descriptors.py',
            'tools/install-artifact-payload.py', 'tools/owned_output.py',
        }
        self.assertTrue(sources <= set(re.findall(r"^              - '([^']+)'$", hooks, re.M)))
        push = workflow.split('  push:\n', 1)[1].split('\njobs:', 1)[0]
        self.assertIn('      - "tools/owned_output.py"\n', push)

    def test_new_source_roles_refuse_omission_repetition_filtered_commands_and_credential_escape(self):
        text=self.current();impact=job_block(text,'ci-impact')
        predicate=next(iter(reviewed_impact_source_event_guards(impact)))
        with self.assertRaises(ValueError):
            reviewed_impact_source_event_guards(impact+'      - name: unreviewed ordinary test\n        if: '+predicate+'\n        run: python unreviewed.py\n')
        for name,role in IMPACT_SOURCE_ROLES.items():
            for replacement in ('',role+role):
                with self.subTest(role=name,mutation='omitted-or-repeated'),self.assertRaises(ValueError):
                    reviewed_impact_source_event_guards(impact.replace(role,replacement,1))
        for name,role in IMPACT_SOURCE_ROLES.items():
            if 'observe-python' in role:
                for before,after in (('-- .github/scripts/','-- -k one .github/scripts/'),
                                     ('        shell: bash','        env:\n          GH_TOKEN: ${{ github.token }}\n        shell: bash'),
                                     ('--source-profile impact-single-owner-findings-v1','--source-profile python-tools-v1')):
                    self.assertIn(before,role)
                    with self.subTest(role=name,field=before),self.assertRaises(ValueError):
                        reviewed_impact_source_event_guards(impact.replace(role,role.replace(before,after,1),1))
        hooks=job_block(text,'hooks')
        names=('Prepare single-owner hook source-test inputs','Observe original persona transition tests',
               'Observe original scoped Pi payload identity tests','Observe original typed verdict tests',
               'Observe original bounded verifier-subprocess contract tests',
               'Observe original Git channel contracts after the release planner',
               'Observe original measurement contract tests','Upload single-owner hook source-test inputs')
        for name in names:
            role=PYTHON_SOURCE_ROLES[name]
            for replacement in ('',role+role,role.replace("matrix.os == 'windows-latest'","matrix.os != 'windows-latest'",1)):
                with self.subTest(role=name),self.assertRaises(ValueError):python_source_roles(hooks.replace(role,replacement,1))
        with self.assertRaisesRegex(ValueError, 'bounded reader suite must run once'):
            python_source_roles(hooks + '      - name: Extra bounded verifier run\n'
                                '        run: python .github/scripts/test_boundedproc.py\n')


class HookF02CompositionWorkflowTests(unittest.TestCase):
    def current(self):
        return (Path(__file__).resolve().parents[2]/'.github/workflows/ci.yml').read_text(encoding='utf8')

    def test_original_modelib_once_reuses_prior_prompt_and_has_prepared_source_first(self):
        text=self.current();block=job_block(text,'hooks');roles=python_source_roles(block);validate(text)
        steps=step_blocks(block);prepare=roles['Prepare single-owner hook source-test inputs']
        modelib=roles['Observe original mode transition and audit tests'];prompt=roles['Observe original persona transition tests']
        self.assertLess(steps.index(prepare),steps.index(modelib))
        self.assertLess(steps.index(modelib),steps.index(prompt))
        self.assertEqual(sum(command(step)=='python .github/scripts/test_modelib.py' for step in steps),1)
        for entry in ('test_modelib.py','test_prompt_submit.py'):
            self.assertEqual(sum(bool(command(step) and command(step).endswith('-- .github/scripts/'+entry)) for step in steps),1)
        emitter=roles['Emit original Python source qualification report']
        self.assertEqual(emitter.count('--observation "finite-hookf01='),1)
        self.assertEqual(emitter.count('--observation "finite-hookf02-modelib='),1)
        self.assertIn("steps.single_hookf02_modelib_observed.outcome == 'success'",emitter)
        self.assertEqual(emitter.count('--payload-root "major-source-inputs-hooks-single-owner='),1)

    def test_missing_repeated_filtered_or_late_component_cannot_emit_a_complete_finding(self):
        text=self.current();block=job_block(text,'hooks');roles=python_source_roles(block)
        modelib=roles['Observe original mode transition and audit tests'];prepare=roles['Prepare single-owner hook source-test inputs'];emitter=roles['Emit original Python source qualification report']
        mutants=[block.replace(modelib,'',1),block.replace(modelib,modelib+modelib,1),
                 block.replace(prepare,'',1).replace(modelib,modelib+prepare,1)]
        for before,after in (('-- .github/scripts/test_modelib.py','-- .github/scripts/test_modelib.py TestFlip'),
                             ('--source-profile hooks-single-owner-findings-v1','--source-profile python-tools-v1'),
                             ('        shell: bash','        env:\n          GH_TOKEN: ${{ github.token }}\n        shell: bash')):
            self.assertIn(before,modelib);mutants.append(block.replace(modelib,modelib.replace(before,after,1),1))
        for before,after in ((" && steps.single_hookf02_modelib_observed.outcome == 'success'",''),
                             ('--observation "finite-hookf02-modelib=','--observation "foreign=')):
            self.assertIn(before,emitter);mutants.append(block.replace(emitter,emitter.replace(before,after,1),1))
        for value in mutants:
            with self.subTest(mutation=value[-100:]),self.assertRaises(ValueError):validate(text.replace(block,value,1))

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
