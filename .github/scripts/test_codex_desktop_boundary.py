#!/usr/bin/env python3
"""Executable contracts for the trusted Codex desktop proof boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / ".github" / "desktop-proof-boundary.json"
SCRIPTS = REPO_ROOT / ".github" / "scripts"
BROKER = SCRIPTS / "Invoke-CodeArbiterDesktopCandidate.ps1"
PROBE = SCRIPTS / "Invoke-CodeArbiterDesktopRouteProbe.ps1"
DRIVER = SCRIPTS / "Invoke-CodeArbiterDesktopUiDriver.ps1"
CHECKER = SCRIPTS / "check_codex_skill_resources.py"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_process_diagnostic(result: subprocess.CompletedProcess[str]) -> str:
    """Remove host formatting while preserving the diagnostic's exact words."""
    combined = "\n".join(
        part for part in (result.stdout, result.stderr) if part
    )
    without_ansi = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", combined)
    without_gutters = re.sub(r"(?m)^[ \t]*\|[ \t]+", "", without_ansi)
    return " ".join(without_gutters.split())


def powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        raise unittest.SkipTest("PowerShell is unavailable")
    return executable


def run_contract(script: Path, contract: Path = CONTRACT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            powershell(), "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
            str(script), "-ContractOnly", "-ContractPath", str(contract),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def run_fixture(
    script: Path,
    fixture: dict,
    *,
    fail_after: str | None = None,
    cleanup_failure: str | None = None,
    receipt_failure: str | None = None,
    receipt_cleanup_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as temp:
        fixture_path = Path(temp) / "fixture.json"
        fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
        command = [
            powershell(), "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
            str(script), "-FixturePath", str(fixture_path), "-ContractPath", str(CONTRACT),
        ]
        if fail_after is not None:
            command.extend(["-TestFailAfter", fail_after])
        if cleanup_failure is not None:
            command.extend(["-TestCleanupFailure", cleanup_failure])
        if receipt_failure is not None:
            command.extend(["-TestReceiptFailure", receipt_failure])
        if receipt_cleanup_failure:
            command.append("-TestReceiptCleanupFailure")
        environment = os.environ.copy()
        environment["CODEARBITER_DESKTOP_BOUNDARY_TEST"] = "1"
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )


def run_driver_boundary_fixture(parameter: str, fixture: dict) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as temp:
        fixture_path = Path(temp) / "driver-boundary-fixture.json"
        fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
        environment = os.environ.copy()
        environment["CODEARBITER_DESKTOP_BOUNDARY_TEST"] = "1"
        return subprocess.run(
            [
                powershell(), "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                str(DRIVER), parameter, str(fixture_path), "-ContractPath", str(CONTRACT),
            ],
            cwd=REPO_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )


def run_candidate_surface_fixture(
    fixture: dict,
    *,
    bind_fixture_hooks: bool = False,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as temp:
        fixture_path = Path(temp) / "candidate-surface-fixture.json"
        fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
        contract_path = CONTRACT
        if bind_fixture_hooks:
            trusted_root = Path(temp) / "trusted"
            trusted_scripts = trusted_root / ".github" / "scripts"
            trusted_scripts.mkdir(parents=True)
            for trusted_script in (BROKER, DRIVER, PROBE):
                shutil.copy2(trusted_script, trusted_scripts / trusted_script.name)
            contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
            contract["candidate_surface"]["hooks_manifest_sha256"] = sha256_text(
                fixture["hooks_manifest_text"]
            )
            contract_path = trusted_root / ".github" / "desktop-proof-boundary.json"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
        environment = os.environ.copy()
        environment["CODEARBITER_DESKTOP_BOUNDARY_TEST"] = "1"
        return subprocess.run(
            [
                powershell(), "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                str(BROKER), "-CandidateSurfaceFixturePath", str(fixture_path),
                "-ContractPath", str(contract_path),
            ],
            cwd=REPO_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )


def run_archive_extraction_fixture(
    archive: Path,
    destination: Path,
    executable: str | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["CODEARBITER_DESKTOP_BOUNDARY_TEST"] = "1"
    shell = executable or powershell()
    if Path(shell).name.casefold() == "powershell.exe":
        # A pwsh parent exports its own module path, which masks the inbox
        # Windows PowerShell modules instead of representing the runner.
        for name in tuple(environment):
            if name.casefold() == "psmodulepath":
                environment.pop(name)
    return subprocess.run(
        [
            shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
            str(BROKER), "-ArchiveExtractionFixturePath", str(archive),
            "-ArchiveExtractionDestination", str(destination),
            "-ContractPath", str(CONTRACT),
        ],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def run_candidate_metadata_fixture(package_root: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["CODEARBITER_DESKTOP_BOUNDARY_TEST"] = "1"
    return subprocess.run(
        [
            powershell(), "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
            str(BROKER), "-CandidateMetadataFixturePath", str(package_root),
            "-ContractPath", str(CONTRACT),
        ],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


class DesktopBoundaryContractTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.prompt = (
            "$ca-review desktop-proof-fixture.ps1 -- read-only protected route proof; "
            "dispatch the required coverage-auditor unit and do not modify files."
        )
        self.desktop_sha = "1" * 64
        self.runtime_sha = "2" * 64
        self.thread_id = "019d0000-0000-7000-8000-000000000001"
        self.canary_path = r"C:\Users\proof\.codex\desktop-proof-auth-isolation-canary.txt"
        self.canary_content = "CODEARBITER-DESKTOP-CANARY-9f42f6e8"
        self.canary_prompt = (
            self.contract["authentication"]["denial_canary_prompt_prefix"]
            + " " + self.canary_path
        )
        self.channel_key = "b" * 64
        self.channel_nonce = "c" * 64
        self.channel_vm = "11111111-1111-4111-8111-111111111111"
        self.channel_bootstrap = "S-1-5-21-1-2-3-500"
        self.channel_desktop = "S-1-5-21-1-2-3-1001"
        self.channel_request = "d" * 64
        self.channel_dispatch = "e" * 64
        self.channel_causal = "6" * 64
        self.channel_canary = "7" * 64
        self.channel_profile = "desktop-proof"
        self.driver_command_line = (
            r'powershell.exe -NoProfile -File "C:\CodeArbiterTrusted\Invoke-CodeArbiterDesktopUiDriver.ps1"'
        )
        self.channel_records = [901, 902, 903]
        self.channel_route_response = {
            "selected_plugin_root": r"C:\Users\proof\.codex\plugins\cache\codearbiter\ca-codex\0.7.5",
            "dispatch_agent": "coverage-auditor",
            "thread_id_sha256": "9" * 64,
            "security_records_sha256": "a" * 64,
            "observed_messages": 1,
            "sequence_complete": True,
            "timed_out": False,
            "teardown_requested": True,
            "route_events": [{
                "sequence": 1,
                "kind": "desktop-skill-read",
                "reference": "$ca-review",
                "resolved_path": r"C:\Users\proof\.codex\plugins\cache\codearbiter\ca-codex\0.7.5\skills\ca-review\SKILL.md",
                "content_sha256": "b" * 64,
                "event_sha256": "c" * 64,
            }],
        }
        event = self.channel_route_response["route_events"][0]
        event_part = ",".join([
            str(event["sequence"]), sha256_text(event["kind"]), sha256_text(event["reference"]),
            sha256_text(event["resolved_path"]), event["content_sha256"], event["event_sha256"],
        ])
        route_canonical = (
            "codearbiter.desktop-route-response.v1|"
            f"{sha256_text(self.channel_route_response['selected_plugin_root'])}|"
            f"{sha256_text(self.channel_route_response['dispatch_agent'])}|"
            f"{self.channel_route_response['thread_id_sha256']}|"
            f"{self.channel_route_response['security_records_sha256']}|1|true|false|true|{event_part}"
        )
        self.channel_response_binding = sha256_text(route_canonical)
        channel_canonical = (
            "codearbiter.desktop-channel.v4|"
            f"{self.channel_vm}|{self.channel_bootstrap}|{self.channel_desktop}|"
            f"{self.channel_nonce}|{self.channel_request}|{self.channel_dispatch}|"
            f"{self.channel_causal}|{self.channel_canary}|{self.channel_profile}|true|"
            f"{self.channel_response_binding}|"
            + ",".join(str(value) for value in self.channel_records)
        )
        self.channel_response = hmac.new(
            bytes.fromhex(self.channel_key), channel_canonical.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        self.runner_sid = "S-1-5-21-9-8-7-1000"
        self.broker_fixture = {
            "schema_version": 1,
            "runner_sid": self.runner_sid,
            "acl_chain": [
                {
                    "owner_sid": "S-1-5-18",
                    "access": [
                        {"sid": "S-1-5-18", "type": "Allow", "rights": "FullControl"},
                        {"sid": "S-1-5-32-545", "type": "Allow", "rights": "ReadAndExecute"},
                    ],
                },
                {
                    "owner_sid": self.runner_sid,
                    "access": [
                        {"sid": self.runner_sid, "type": "Allow", "rights": "FullControl"},
                    ],
                },
            ],
            "channel": {
                "key": self.channel_key,
                "nonce": self.channel_nonce,
                "vm_id": self.channel_vm,
                "bootstrap_sid": self.channel_bootstrap,
                "desktop_sid": self.channel_desktop,
                "request_sha256": self.channel_request,
                "dispatch_sha256": self.channel_dispatch,
                "causal_window_sha256": self.channel_causal,
                "auth_canary_content_sha256": self.channel_canary,
                "permission_profile_id": self.channel_profile,
                "auth_canary_denied": True,
                "response_binding_sha256": self.channel_response_binding,
                "record_ids": self.channel_records,
                "response_sha256": self.channel_response,
            },
            "route_response": self.channel_route_response,
            "measurements": {
                "fresh_iso_applied": True,
                "enhanced_session_enabled": False,
                "guest_service_interface_enabled": False,
                "host_profile_mounted": False,
                "host_shared_folders": False,
                "network_policy_sha256": "a" * 64,
                "enabled_allow_rules": 8,
                "outside_allow_rules": 0,
                "preauth_api_key_variables": 0,
                "preauth_credential_targets": 0,
                "preauth_network_mappings": 0,
                "preauth_auth_files": 0,
                "auth_storage_mode": "file",
                "postauth_credential_targets": 0,
                "postauth_auth_files": 1,
                "auth_prompt_ready": True,
                "auth_completed": True,
                "app_account_mode": "chatgpt",
                "permission_profile_id": "desktop-proof",
                "permission_consumer": "codex-sandbox-permission-profile",
                "permission_restricted_filesystem": True,
                "permission_restricted_network": True,
                "permission_hooks_enabled": False,
                "permission_startup_warning_count": 0,
                "permission_windows_sandbox": "elevated",
                "guest_acl_boundary": True,
                "auth_canary_denied": True,
                "auth_canary_content_observed": False,
                "eligible_runtime_process_count": 1,
                "raw_content_persisted": False,
                "artifact_sidecars": 0,
            },
        }
        self.driver_fixture = {
            "schema_version": 1,
            "app_server_query_count": 8,
            "account": {"auth_mode": "chatgpt"},
            "policy": {
                "approval_policy": "never",
                "sandbox_mode": "read-only",
                "permission_profile_id": "desktop-proof",
                "hooks_enabled": False,
                "windows_sandbox": "elevated",
            },
            "window": {
                "submission_method": "windows-sendinput-unicode",
                "foreground_process_id": 4100,
                "prompt": self.prompt,
            },
            "desktop": {
                "process_id": 4100,
                "process_start_time": "2026-08-26T11:59:57Z",
                "process_sha256": self.desktop_sha,
                "package_name": "OpenAI.Codex",
                "package_full_name": "OpenAI.Codex_26.820.7780.0_x64__2p2nqsd0c76g0",
                "publisher": "CN=50BDFD77-8903-4850-9FFE-6E8522F64D5B",
                "signature_status": "Valid",
            },
            "runtime": {
                "process_id": 4200,
                "parent_process_id": 4100,
                "process_ancestor_ids": [4100],
                "process_sha256": self.runtime_sha,
                "packaged_resource_sha256": self.runtime_sha,
                "version": "codex-cli 0.150.0-alpha.8",
                "eligible_process_count": 1,
                "process_start_time": "2026-08-26T11:59:59Z",
            },
            "app_server_process": {
                "process_id": 4250,
                "parent_process_id": 4300,
                "process_sha256": self.runtime_sha,
                "process_start_time": "2026-08-26T11:59:59Z",
            },
            "driver_process": {
                "process_id": 4300,
                "parent_process_id": 1200,
                "executable_sha256": "6" * 64,
                "signature_status": "Valid",
                "script_sha256": self.contract["driver"]["sha256"],
                "script_path": r"C:\CodeArbiterTrusted\Invoke-CodeArbiterDesktopUiDriver.ps1",
                "command_line_sha256": sha256_text(self.driver_command_line),
                "process_start_time": "2026-08-26T11:59:58Z",
            },
            "auth_isolation": {
                "canary_path": self.canary_path,
                "canary_content": self.canary_content,
                "canary_content_sha256": sha256_text(self.canary_content),
                "canary_prompt": self.canary_prompt,
                "thread": {
                    "id": "019d0000-0000-7000-8000-000000000000",
                    "items": [
                        {"type": "userMessage", "text": self.canary_prompt},
                        {
                            "type": "commandExecution",
                            "command": f'Get-Content -LiteralPath "{self.canary_path}"',
                            "status": "failed",
                            "exitCode": 1,
                            "aggregatedOutput": "sandbox policy denied filesystem read",
                        },
                    ],
                },
            },
            "thread": {
                "id": self.thread_id,
                "request_submitted_at": "2026-08-26T12:00:00Z",
                "dispatch_completed_at": "2026-08-26T12:00:04Z",
                "items": [
                    {"type": "userMessage", "text": self.prompt},
                    {
                        "type": "collabAgentToolCall",
                        "tool": "spawn_agent",
                        "status": "completed",
                        "prompt": "Act as coverage-auditor and review the named source diff.",
                    },
                ],
            },
        }

    def test_contract_entrypoints_bind_all_three_trusted_programs(self):
        checked = subprocess.run(
            ["python", str(CHECKER), "--desktop-boundary-contract-only", "--json"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        checked_payload = json.loads(checked.stdout)
        self.assertEqual(checked_payload["verdict"], "PASS")
        self.assertRegex(checked_payload["driver_sha256"], r"^[0-9a-f]{64}$")
        for script in (BROKER, PROBE, DRIVER):
            with self.subTest(script=script.name):
                result = run_contract(script)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)["verdict"], "PASS")

    def test_boundary_requires_direct_iso_application_not_a_template_vhd(self):
        self.assertEqual(self.contract["image"]["provisioning_mode"], "iso-apply-fresh-vhdx")
        success = run_fixture(BROKER, self.broker_fixture)
        self.assertEqual(success.returncode, 0, success.stdout + success.stderr)
        payload = json.loads(success.stdout)
        self.assertEqual(payload["test_result"], "SUCCEEDED")
        self.assertIn("iso-applied-to-fresh-vhdx", payload["trace"])
        self.assertNotIn("template-vhd-selected", payload["trace"])
        self.assertEqual(
            self.contract["network"]["resolution_mode"],
            "pre-resolve-pin-hosts-then-disable-dns",
        )
        self.assertFalse(self.contract["network"]["dns_allowed_during_candidate"])

    def test_broker_rejects_claimed_or_unmeasured_security_outcomes(self):
        mutations = {
            "template image": lambda value: value["measurements"].update(
                fresh_iso_applied=False
            ),
            "enhanced session": lambda value: value["measurements"].update(
                enhanced_session_enabled=True
            ),
            "guest file sharing": lambda value: value["measurements"].update(
                guest_service_interface_enabled=True
            ),
            "host profile mount": lambda value: value["measurements"].update(
                host_profile_mounted=True
            ),
            "outside egress": lambda value: value["measurements"].update(
                outside_allow_rules=1
            ),
            "API key environment": lambda value: value["measurements"].update(
                preauth_api_key_variables=1
            ),
            "copied credential": lambda value: value["measurements"].update(
                preauth_credential_targets=1
            ),
            "mapped host drive": lambda value: value["measurements"].update(
                preauth_network_mappings=1
            ),
            "copied auth file": lambda value: value["measurements"].update(
                preauth_auth_files=1
            ),
            "non-file auth store": lambda value: value["measurements"].update(
                auth_storage_mode="keyring"
            ),
            "post-auth credential target": lambda value: value["measurements"].update(
                postauth_credential_targets=1
            ),
            "unexpected post-auth files": lambda value: value["measurements"].update(
                postauth_auth_files=2
            ),
            "consent absent": lambda value: value["measurements"].update(
                auth_completed=False
            ),
            "API account mode": lambda value: value["measurements"].update(
                app_account_mode="apikey"
            ),
            "wrong permission profile": lambda value: value["measurements"].update(
                permission_profile_id=":read-only"
            ),
            "canary readable": lambda value: value["measurements"].update(
                auth_canary_denied=False
            ),
            "canary leaked": lambda value: value["measurements"].update(
                auth_canary_content_observed=True
            ),
            "multiple runtimes": lambda value: value["measurements"].update(
                eligible_runtime_process_count=2
            ),
            "raw content": lambda value: value["measurements"].update(
                raw_content_persisted=True
            ),
            "durable sidecar": lambda value: value["measurements"].update(
                artifact_sidecars=1
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                fixture = json.loads(json.dumps(self.broker_fixture))
                mutate(fixture)
                result = run_fixture(BROKER, fixture)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('"receipt_would_finalize":true', result.stdout)

    def test_broker_verifies_every_hmac_bound_channel_field(self):
        mutations = {
            "wrong key": lambda value: value["channel"].update(key="f" * 64),
            "wrong nonce": lambda value: value["channel"].update(nonce="f" * 64),
            "wrong VM": lambda value: value["channel"].update(
                vm_id="22222222-2222-4222-8222-222222222222"
            ),
            "wrong bootstrap": lambda value: value["channel"].update(
                bootstrap_sid="S-1-5-21-1-2-3-501"
            ),
            "wrong desktop": lambda value: value["channel"].update(
                desktop_sid="S-1-5-21-1-2-3-1002"
            ),
            "wrong request": lambda value: value["channel"].update(
                request_sha256="f" * 64
            ),
            "wrong dispatch": lambda value: value["channel"].update(
                dispatch_sha256="f" * 64
            ),
            "wrong causal window": lambda value: value["channel"].update(
                causal_window_sha256="f" * 64
            ),
            "wrong canary": lambda value: value["channel"].update(
                auth_canary_content_sha256="f" * 64
            ),
            "wrong profile": lambda value: value["channel"].update(
                permission_profile_id=":read-only"
            ),
            "canary not denied": lambda value: value["channel"].update(
                auth_canary_denied=False
            ),
            "wrong route binding": lambda value: value["channel"].update(
                response_binding_sha256="f" * 64
            ),
            "tampered route root": lambda value: value["route_response"].update(
                selected_plugin_root=r"C:\Users\proof\.codex\plugins\cache\evil"
            ),
            "tampered route event": lambda value: value["route_response"]["route_events"][0].update(
                content_sha256="f" * 64
            ),
            "tampered security records": lambda value: value["route_response"].update(
                security_records_sha256="f" * 64
            ),
            "tampered sequence state": lambda value: value["route_response"].update(
                sequence_complete=False
            ),
            "tampered teardown state": lambda value: value["route_response"].update(
                teardown_requested=False
            ),
            "wrong record": lambda value: value["channel"].update(
                record_ids=[901, 902, 904]
            ),
            "wrong response": lambda value: value["channel"].update(
                response_sha256="f" * 64
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                fixture = json.loads(json.dumps(self.broker_fixture))
                mutate(fixture)
                result = run_fixture(BROKER, fixture)
                self.assertNotEqual(result.returncode, 0)

    def test_broker_rejects_untrusted_owner_or_mutation_right_on_any_ancestor(self):
        mutations = {
            "unapproved root owner": lambda value: value["acl_chain"][0].update(
                owner_sid="S-1-5-32-545"
            ),
            "delete child": lambda value: value["acl_chain"][0]["access"][1].update(
                rights="DeleteSubdirectoriesAndFiles"
            ),
            "change permissions": lambda value: value["acl_chain"][0]["access"][1].update(
                rights="ChangePermissions"
            ),
            "take ownership": lambda value: value["acl_chain"][0]["access"][1].update(
                rights="TakeOwnership"
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                fixture = json.loads(json.dumps(self.broker_fixture))
                mutate(fixture)
                result = run_fixture(BROKER, fixture)
                self.assertNotEqual(result.returncode, 0)

    def test_desktop_driver_observes_chatgpt_auth_exact_store_process_and_dispatch(self):
        result = run_fixture(DRIVER, self.driver_fixture)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        observed = json.loads(result.stdout)
        self.assertEqual(observed["test_result"], "SUCCEEDED")
        self.assertEqual(observed["auth_mode"], "chatgpt")
        self.assertEqual(observed["effective_approval"], "never")
        self.assertEqual(observed["effective_sandbox"], "read-only")
        self.assertEqual(observed["request_sha256"], sha256_text(self.prompt))
        self.assertEqual(observed["thread_id_sha256"], sha256_text(self.thread_id))
        self.assertEqual(observed["desktop_process_sha256"], self.desktop_sha)
        self.assertEqual(observed["runtime_process_sha256"], self.runtime_sha)
        self.assertEqual(observed["runtime_version"], "0.150.0-alpha.8")
        self.assertEqual(observed["app_server_query_count"], 8)
        self.assertEqual(observed["permission_profile_id"], "desktop-proof")
        self.assertTrue(observed["auth_canary_denied"])
        self.assertFalse(observed["auth_canary_content_observed"])
        self.assertEqual(observed["eligible_runtime_process_count"], 1)
        self.assertEqual(observed["dispatch_agent"], "coverage-auditor")
        self.assertNotIn(self.prompt, result.stdout)
        self.assertNotIn("Act as coverage-auditor", result.stdout)

        mutations = {
            "api auth": lambda value: value["account"].update(auth_mode="apikey"),
            "unsubmitted prompt": lambda value: value["thread"]["items"][0].update(text="different"),
            "missing dispatch": lambda value: value["thread"].update(items=value["thread"]["items"][:1]),
            "lookalike package": lambda value: value["desktop"].update(package_name="Lookalike.Codex"),
            "invalid signature": lambda value: value["desktop"].update(signature_status="NotSigned"),
            "runtime mismatch": lambda value: value["runtime"].update(packaged_resource_sha256="3" * 64),
            "unrelated runtime": lambda value: value["runtime"].update(process_ancestor_ids=[4300]),
            "wrong approval": lambda value: value["policy"].update(approval_policy="on-request"),
            "wrong sandbox": lambda value: value["policy"].update(sandbox_mode="workspace-write"),
            "wrong permission profile": lambda value: value["policy"].update(
                permission_profile_id=":read-only"
            ),
            "hooks enabled": lambda value: value["policy"].update(hooks_enabled=True),
            "non-elevated sandbox": lambda value: value["policy"].update(windows_sandbox="unelevated"),
            "multiple eligible runtimes": lambda value: value["runtime"].update(
                eligible_process_count=2
            ),
            "untrusted driver script": lambda value: value["driver_process"].update(
                script_sha256="0" * 64
            ),
            "runtime starts after request": lambda value: value["runtime"].update(
                process_start_time="2026-08-26T12:00:01Z"
            ),
            "canary command succeeds": lambda value: value["auth_isolation"]["thread"]["items"][1].update(
                status="completed", exitCode=0
            ),
            "canary content escaped": lambda value: value["auth_isolation"]["thread"]["items"][1].update(
                aggregatedOutput=self.canary_content
            ),
            "canary path mismatch": lambda value: value["auth_isolation"].update(
                canary_path=r"C:\Users\proof\desktop-proof-auth-isolation-canary.txt"
            ),
            "canary path contains a normalizable traversal": lambda value: value["auth_isolation"].update(
                canary_path=(
                    "C:\\Users\\proof\\scratch\\..\\.codex\\"
                    "desktop-proof-auth-isolation-canary.txt"
                )
            ),
            "dispatch precedes request": lambda value: value["thread"].update(
                dispatch_completed_at="2026-08-26T11:59:58Z"
            ),
            "query overflow": lambda value: value.update(app_server_query_count=33),
            "extra route command": lambda value: value["thread"]["items"].append(
                {"type": "commandExecution", "command": "Get-ChildItem", "status": "completed"}
            ),
            "lookalike app-server parent": lambda value: value["app_server_process"].update(
                parent_process_id=4100
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                fixture = json.loads(json.dumps(self.driver_fixture))
                mutate(fixture)
                failed = run_fixture(DRIVER, fixture)
                self.assertNotEqual(failed.returncode, 0)
                self.assertNotIn('"test_result":"SUCCEEDED"', failed.stdout)

    def test_real_codex_permission_probe_is_the_production_gate(self):
        fixture = {
            "schema_version": 1,
            "diagnostics": {
                "config_parse_ok": True,
                "startup_warning_count": 0,
                "restricted_filesystem": True,
                "restricted_network": True,
                "hooks_enabled": False,
                "profile_id": "desktop-proof",
            },
            "cases": [
                {"id": "plugin-route", "exit_code": 0},
                {"id": "proof-input", "exit_code": 0},
                {"id": "auth-file", "exit_code": 1},
                {"id": "auth-sidecar", "exit_code": 1},
                {"id": "other-codex-state", "exit_code": 1},
                {"id": "outside-root", "exit_code": 1},
                {"id": "network-egress", "exit_code": 1},
            ],
        }
        result = run_driver_boundary_fixture("-PermissionProbeFixturePath", fixture)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        observed = json.loads(result.stdout)
        self.assertEqual(observed["verdict"], "PASS")
        self.assertEqual(observed["consumer"], "codex-sandbox-permission-profile")
        self.assertFalse(observed["hooks_enabled"])

        mutations = {
            "parse failure": lambda value: value["diagnostics"].update(config_parse_ok=False),
            "warning": lambda value: value["diagnostics"].update(startup_warning_count=1),
            "filesystem open": lambda value: value["diagnostics"].update(restricted_filesystem=False),
            "network open": lambda value: value["diagnostics"].update(restricted_network=False),
            "hooks active": lambda value: value["diagnostics"].update(hooks_enabled=True),
            "wrong profile": lambda value: value["diagnostics"].update(profile_id="other"),
            "plugin denied": lambda value: value["cases"][0].update(exit_code=1),
            "auth readable": lambda value: value["cases"][2].update(exit_code=0),
            "outside readable": lambda value: value["cases"][5].update(exit_code=0),
            "network reachable": lambda value: value["cases"][6].update(exit_code=0),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = json.loads(json.dumps(fixture))
                mutate(changed)
                failed = run_driver_boundary_fixture("-PermissionProbeFixturePath", changed)
                self.assertNotEqual(failed.returncode, 0)

    def test_post_auth_inventory_executes_production_filters(self):
        profile = r"C:\Users\proof"
        fixture = {
            "schema_version": 1,
            "profile": profile,
            "config_text": 'cli_auth_credentials_store = "file"',
            "files": [profile + r"\.codex\auth.json"],
            "credential_targets": [],
            "doctor_exit_code": 0,
            "doctor_overall_status": "pass",
            "doctor_checks": {
                name: {"status": "ok"}
                for name in self.contract["authentication"]["doctor_required_checks"]
            },
        }
        result = run_driver_boundary_fixture("-InventoryFixturePath", fixture)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        observed = json.loads(result.stdout)
        self.assertEqual(observed["storage_backend"], "file")
        self.assertEqual(observed["reusable_state_file_count"], 1)
        self.assertEqual(observed["keyring_target_count"], 0)

        extra_files = [
            r".codex\auth.json.lock",
            r".codex\.credentials.json",
            r".codex\credentials.json.backup",
            r".codex\credentials\nested.json",
            r".codex\sessions\thread.jsonl",
            r".codex\tokens\refresh.json",
        ]
        for relative in extra_files:
            with self.subTest(extra=relative):
                changed = json.loads(json.dumps(fixture))
                changed["files"].append(profile + "\\" + relative)
                failed = run_driver_boundary_fixture("-InventoryFixturePath", changed)
                self.assertNotEqual(failed.returncode, 0)
        benign = json.loads(json.dumps(fixture))
        benign["files"].append(profile + r"\.codex\plugins\cache\codearbiter\ca-codex\0.7.5\SKILL.md")
        passed = run_driver_boundary_fixture("-InventoryFixturePath", benign)
        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
        keyring = json.loads(json.dumps(fixture))
        keyring["credential_targets"].append("LegacyGeneric:target=Codex")
        failed = run_driver_boundary_fixture("-InventoryFixturePath", keyring)
        self.assertNotEqual(failed.returncode, 0)
        for field, value in {
            "doctor_exit_code": 1,
            "doctor_overall_status": "fail",
        }.items():
            with self.subTest(doctor=field):
                changed = json.loads(json.dumps(fixture))
                changed[field] = value
                failed = run_driver_boundary_fixture("-InventoryFixturePath", changed)
                self.assertNotEqual(failed.returncode, 0)
        for label, mutate in {
            "empty checks": lambda value: value.update(doctor_checks={}),
            "missing required check": lambda value: value["doctor_checks"].pop("auth.credentials"),
            "warning check": lambda value: value["doctor_checks"]["auth.credentials"].update(
                status="warning"
            ),
            "missing status schema": lambda value: value["doctor_checks"].update(
                {"auth.credentials": {}}
            ),
        }.items():
            with self.subTest(doctor=label):
                changed = json.loads(json.dumps(fixture))
                mutate(changed)
                failed = run_driver_boundary_fixture("-InventoryFixturePath", changed)
                self.assertNotEqual(failed.returncode, 0)

    def test_production_boundary_uses_real_codex_and_immutable_guest_seams(self):
        broker_source = BROKER.read_text(encoding="utf-8")
        driver_source = DRIVER.read_text(encoding="utf-8")
        probe_source = PROBE.read_text(encoding="utf-8")

        self.assertNotIn("Get-DesktopProofPermissionDecision", broker_source)
        self.assertIn('[features]\nhooks = false', broker_source)
        self.assertIn('[windows]\nsandbox = "elevated"', broker_source)
        self.assertIn("-PermissionProbe", broker_source)
        self.assertIn("-InventoryProbe", broker_source)
        self.assertIn("Invoke-RealPermissionProbe", driver_source)
        self.assertIn("'sandbox','--disable','hooks','-P'", driver_source)
        self.assertIn("Measure-PostAuthInventory", driver_source)
        self.assertIn("post-auth Credential Manager inventory failed", driver_source)
        self.assertIn("Get-ChildItem -LiteralPath $codexRoot -Recurse -File -Force -ErrorAction Stop", driver_source)
        self.assertIn("pre-auth Credential Manager inventory failed", broker_source)
        self.assertIn("Get-SmbMapping -ErrorAction Stop", broker_source)

        self.assertIn(r"C:\CodeArbiterTrusted", broker_source)
        self.assertIn(r"C:\CodeArbiterExchange", broker_source)
        self.assertGreaterEqual(broker_source.count("Assert-GuestTrustedBytes -Session"), 5)
        self.assertIn("frozen-driver-observation.json", broker_source)
        self.assertIn("/inheritance:r", broker_source)
        self.assertIn("ProcessCreationIncludeCmdLine_Enabled", probe_source)
        self.assertIn("nonallowlisted process ran inside the protected candidate activation window", probe_source)
        self.assertNotIn("$IsWindows", driver_source)
        self.assertNotIn("$IsWindows", probe_source)
        self.assertIn("[Environment]::OSVersion.Platform", driver_source)
        self.assertIn("[Environment]::OSVersion.Platform", probe_source)
        self.assertIn("public struct MOUSEINPUT", driver_source)
        self.assertIn("public struct InputUnion", driver_source)
        self.assertIn("public InputUnion u", driver_source)
        self.assertIn(".u.ki.", driver_source)
        self.assertNotIn("public KEYBDINPUT ki; }", driver_source)

    def test_driver_reports_exact_x64_windows_input_abi_sizes(self):
        if sys.platform != "win32" or struct.calcsize("P") != 8:
            self.skipTest("x64 Windows ABI check requires a 64-bit Windows host")
        windows_powershell = shutil.which("powershell")
        if windows_powershell is None:
            self.skipTest("Windows PowerShell 5.1 is unavailable")
        result = subprocess.run(
            [
                windows_powershell, "-NoLogo", "-NoProfile", "-NonInteractive",
                "-File", str(DRIVER), "-InputAbiOnly",
                "-ContractPath", str(CONTRACT),
            ],
            cwd=REPO_ROOT,
            env={**os.environ, "CODEARBITER_DESKTOP_BOUNDARY_TEST": "1"},
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"input": 40, "mouse_input": 32, "keyboard_input": 24},
        )

    def test_guest_network_contract_separates_host_package_acquisition(self):
        spec = (
            REPO_ROOT / ".codearbiter" / "specs" /
            "desktop-proof-contract-hardening.md"
        ).read_text(encoding="utf-8")
        controls = (
            REPO_ROOT / ".codearbiter" / "security-controls.md"
        ).read_text(encoding="utf-8")

        self.assertEqual(
            self.contract["network"]["https_fqdns"],
            [
                "auth.openai.com",
                "api.openai.com",
                "chatgpt.com",
                "ios.chat.openai.com",
            ],
        )
        spec_lower = spec.lower()
        self.assertIn("host acquires and copies the store/msix package", spec_lower)
        self.assertIn("guest registers those copied package bytes", spec_lower)
        self.assertIn("after its default-deny policy is active", spec_lower)
        self.assertIn("without microsoft network access", spec_lower)
        controls_normalized = " ".join(controls.lower().split())
        self.assertIn("host-side store/msix acquisition", controls_normalized)
        self.assertIn("guest registration and local-plugin installation", controls_normalized)
        self.assertIn("without microsoft network access", controls_normalized)

    def test_process_diagnostic_normalization_preserves_wrapped_powershell_error(self):
        wrapped = subprocess.CompletedProcess(
            args=["pwsh"],
            returncode=1,
            stdout="",
            stderr=(
                "\x1b[31;1mcandidate hooks manifest bytes differ from the reviewed inert payload\x1b[0m\n"
                "\x1b[36;1m     | \x1b[31;1mdeclaration\x1b[0m\n"
            ),
        )
        self.assertIn(
            "candidate hooks manifest bytes differ from the reviewed inert payload declaration",
            normalize_process_diagnostic(wrapped),
        )

    def test_process_diagnostic_normalization_preserves_inline_pipe_semantics(self):
        inline_pipe = subprocess.CompletedProcess(
            args=["pwsh"],
            returncode=1,
            stdout="",
            stderr=(
                "candidate hooks manifest bytes differ from the reviewed inert "
                "payload | declaration\n"
            ),
        )
        normalized = normalize_process_diagnostic(inline_pipe)
        self.assertIn("payload | declaration", normalized)
        self.assertNotIn(
            "candidate hooks manifest bytes differ from the reviewed inert payload declaration",
            normalized,
        )

    def test_process_diagnostic_normalization_preserves_stdout_stderr_boundary(self):
        split_streams = subprocess.CompletedProcess(
            args=["pwsh"],
            returncode=1,
            stdout="candidate hooks manifest bytes differ from the reviewed inert payload",
            stderr="declaration\n",
        )
        self.assertIn(
            "candidate hooks manifest bytes differ from the reviewed inert payload declaration",
            normalize_process_diagnostic(split_streams),
        )

    def test_candidate_package_has_exact_inert_hook_inventory_during_desktop_proof(self):
        plugin_root = REPO_ROOT / "plugins" / "ca-codex"
        ignored_runtime_artifact = (
            plugin_root / "hooks" / "__pycache__" / "desktop-proof-regression.pyc"
        )
        ignored_runtime_artifact.parent.mkdir(parents=True, exist_ok=True)
        ignored_runtime_artifact.write_bytes(b"ignored runtime artifact")
        self.addCleanup(ignored_runtime_artifact.unlink, missing_ok=True)
        manifest = json.loads(
            (plugin_root / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        legacy_hooks_manifest_text = (
            plugin_root / "hooks" / "hooks.json"
        ).read_text(encoding="utf-8")
        hooks_manifest_text = legacy_hooks_manifest_text.replace(
            "${CLAUDE_PLUGIN_ROOT}", "${PLUGIN_ROOT}"
        )
        self.assertNotEqual(hooks_manifest_text, legacy_hooks_manifest_text)
        self.assertEqual(
            sha256_text(hooks_manifest_text),
            "b13fc7bc70569a0885ef6bbd1be553b983ce0daf95753d287a64edc846b0b9cf",
            "the inert fixture must remain byte-identical to PR #711's native Codex hooks",
        )
        tracked = subprocess.run(
            ["git", "ls-files", "-z", "--", "plugins/ca-codex"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(tracked.returncode, 0, tracked.stderr)
        plugin_prefix = "plugins/ca-codex/"
        tracked_plugin_paths = sorted(
            path.removeprefix(plugin_prefix)
            for path in tracked.stdout.split("\0")
            if path.startswith(plugin_prefix)
        )

        def mutate_hooks(value: dict, callback) -> None:
            payload = json.loads(value["hooks_manifest_text"])
            callback(payload)
            value["hooks_manifest_text"] = json.dumps(payload)

        fixture = {
            "schema_version": 1,
            "manifest": manifest,
            "hooks_manifest_text": hooks_manifest_text,
            "paths": tracked_plugin_paths,
        }
        success = run_candidate_surface_fixture(fixture)
        self.assertEqual(success.returncode, 0, success.stdout + success.stderr)
        rebound_success = run_candidate_surface_fixture(
            fixture,
            bind_fixture_hooks=True,
        )
        self.assertEqual(
            rebound_success.returncode,
            0,
            rebound_success.stdout + rebound_success.stderr,
        )

        surface_mutations = {
            "MCP manifest": lambda value: value["manifest"].update(mcpServers={"evil": {}}),
            "server file": lambda value: value["paths"].append("servers/evil.json"),
            "app file": lambda value: value["paths"].append("apps/evil.json"),
            "script file": lambda value: value["paths"].append("scripts/evil.ps1"),
            "root executable": lambda value: value["paths"].append("evil.exe"),
            "nested Python": lambda value: value["paths"].append("skills/ca-review/evil.py"),
            "new hook payload": lambda value: value["paths"].append("hooks/evil.py"),
        }
        semantic_command_mutations = {
            "obsolete Claude hook root": lambda value: mutate_hooks(value, lambda payload: payload["hooks"]["SessionStart"][0]["hooks"][0].update(
                command=payload["hooks"]["SessionStart"][0]["hooks"][0]["command"].replace("${PLUGIN_ROOT}", "${CLAUDE_PLUGIN_ROOT}"),
                commandWindows=payload["hooks"]["SessionStart"][0]["hooks"][0]["commandWindows"].replace("${PLUGIN_ROOT}", "${CLAUDE_PLUGIN_ROOT}"))),
            "undeclared hook command": lambda value: mutate_hooks(value, lambda payload: payload["hooks"]["SessionStart"][0]["hooks"][0].update(
                command='python3 "${PLUGIN_ROOT}/hooks/evil.py"', commandWindows='python "${PLUGIN_ROOT}/hooks/evil.py"')),
            "inline hook arguments": lambda value: mutate_hooks(value, lambda payload: payload["hooks"]["SessionStart"][0]["hooks"][0].update(
                command='python3 "${PLUGIN_ROOT}/hooks/session-start.py" --evil')),
        }
        exact_byte_mutations = {
            "extra hook event": lambda value: mutate_hooks(value, lambda payload: payload["hooks"].update(Evil=[])),
            "changed matcher": lambda value: mutate_hooks(value, lambda payload: payload["hooks"]["PreToolUse"][0].update(matcher="Bash|Evil")),
            "changed timeout": lambda value: mutate_hooks(value, lambda payload: payload["hooks"]["SessionStart"][0]["hooks"][0].update(timeout=999)),
            "changed status message": lambda value: mutate_hooks(value, lambda payload: payload["hooks"]["SessionStart"][0]["hooks"][0].update(statusMessage="trusted-looking change")),
            "changed context limit": lambda value: mutate_hooks(value, lambda payload: payload["hooks"]["UserPromptSubmit"][1]["hooks"][0].update(additionalContextLimit=999999)),
            "missing hook group": lambda value: mutate_hooks(value, lambda payload: payload["hooks"]["PreToolUse"].pop()),
            "duplicate hook group": lambda value: mutate_hooks(value, lambda payload: payload["hooks"]["PreToolUse"].append(payload["hooks"]["PreToolUse"][0])),
            "reordered hook groups": lambda value: mutate_hooks(value, lambda payload: payload["hooks"]["PreToolUse"].reverse()),
        }
        for label, mutate in surface_mutations.items():
            with self.subTest(label=label):
                changed = json.loads(json.dumps(fixture))
                mutate(changed)
                failed = run_candidate_surface_fixture(changed)
                self.assertNotEqual(failed.returncode, 0)
        for label, mutate in semantic_command_mutations.items():
            with self.subTest(label=label):
                changed = json.loads(json.dumps(fixture))
                mutate(changed)
                failed = run_candidate_surface_fixture(changed, bind_fixture_hooks=True)
                self.assertNotEqual(failed.returncode, 0)
                self.assertIn(
                    "candidate hook declaration is not a single reviewed inert hook path",
                    normalize_process_diagnostic(failed),
                )
        for label, mutate in exact_byte_mutations.items():
            with self.subTest(label=label):
                changed = json.loads(json.dumps(fixture))
                mutate(changed)
                failed = run_candidate_surface_fixture(changed)
                self.assertNotEqual(failed.returncode, 0)
                self.assertIn(
                    "candidate hooks manifest bytes differ from the reviewed inert payload declaration",
                    normalize_process_diagnostic(failed),
                )

    def test_candidate_archive_extraction_is_bounded_before_writes(self):
        """ARC-01: the privileged extractor enforces every bound on real ZIPs."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def write_archive(name, entries, compression=zipfile.ZIP_STORED):
                path = root / name
                with zipfile.ZipFile(path, "w", compression=compression) as archive:
                    for entry_name, content in entries:
                        archive.writestr(entry_name, content)
                return path

            legitimate = write_archive(
                "legitimate.zip",
                [
                    ("plugins/ca-codex/.codex-plugin/plugin.json", b'{"name":"ca-codex"}'),
                    ("plugins/ca-codex/skills/probe/SKILL.md", b"# Probe\n"),
                ],
            )
            legitimate_destination = root / "legitimate-extracted"
            success = run_archive_extraction_fixture(legitimate, legitimate_destination)
            self.assertEqual(success.returncode, 0, success.stdout + success.stderr)
            self.assertEqual(
                json.loads(success.stdout),
                {"entry_count": 2, "file_count": 2, "total_uncompressed_bytes": 27},
            )
            self.assertEqual(
                (legitimate_destination / ".codex-plugin" / "plugin.json").read_bytes(),
                b'{"name":"ca-codex"}',
            )
            self.assertEqual(
                (legitimate_destination / "skills" / "probe" / "SKILL.md").read_bytes(),
                b"# Probe\n",
            )
            broker_source = BROKER.read_text(encoding="utf-8")
            self.assertIn(
                "$hostPluginRoot = Join-Path $hostMarketplace 'plugins\\ca-codex'",
                broker_source,
            )
            self.assertIn(
                "-DestinationPath $hostPluginRoot -Contract $contract -ExpectedSha256 ([string]$request.candidate_archive_sha256)",
                broker_source,
            )
            self.assertIn(
                "-LiteralPath $hostMarketplace -Destination $guestRunRoot -Recurse -Force",
                broker_source,
            )
            windows_powershell = shutil.which("powershell")
            if windows_powershell:
                legacy_success = run_archive_extraction_fixture(
                    legitimate,
                    root / "legacy-extracted",
                    executable=windows_powershell,
                )
                self.assertEqual(
                    legacy_success.returncode,
                    0,
                    legacy_success.stdout + legacy_success.stderr,
                )

            moderately_compressible = b"".join(
                os.urandom(32 * 1024) * 8 for _ in range(8)
            )
            symlink = zipfile.ZipInfo("plugins/ca-codex/agents/link.md")
            symlink.create_system = 3
            symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
            hostile = {
                "archive bytes": write_archive(
                    "archive-bytes.zip",
                    [
                        (f"plugins/ca-codex/agents/archive-{index}.bin", os.urandom(1800 * 1024))
                        for index in range(5)
                    ],
                ),
                "entry count": write_archive(
                    "entry-count.zip",
                    [
                        (f"plugins/ca-codex/agents/entry-{index:04d}.md", b"# entry\n")
                        for index in range(1025)
                    ],
                ),
                "per-entry expansion": write_archive(
                    "per-entry.zip",
                    [("plugins/ca-codex/agents/oversized.bin", b"x" * (2 * 1024 * 1024 + 1))],
                ),
                "total expansion": write_archive(
                    "total-expansion.zip",
                    [
                        (f"plugins/ca-codex/agents/total-{index:02d}.bin", moderately_compressible)
                        for index in range(17)
                    ],
                    zipfile.ZIP_DEFLATED,
                ),
                "compression ratio": write_archive(
                    "high-ratio.zip",
                    [("plugins/ca-codex/agents/high-ratio.bin", b"z" * (1024 * 1024))],
                    zipfile.ZIP_DEFLATED,
                ),
                "late outside-prefix entry": write_archive(
                    "late-outside-prefix.zip",
                    [
                        ("plugins/ca-codex/agents/first.md", b"must not be written\n"),
                        ("outside/late.md", b"invalid\n"),
                    ],
                ),
                "path traversal": write_archive(
                    "path-traversal.zip",
                    [("plugins/ca-codex/../escape.md", b"invalid\n")],
                ),
                "Windows case collision": write_archive(
                    "case-collision.zip",
                    [
                        ("plugins/ca-codex/agents/Probe.md", b"one\n"),
                        ("plugins/ca-codex/agents/probe.md", b"two\n"),
                    ],
                ),
                "explicit directory collision": write_archive(
                    "directory-collision.zip",
                    [
                        ("plugins/ca-codex/Agents/", b""),
                        ("plugins/ca-codex/agents/", b""),
                    ],
                ),
                "file-directory prefix collision": write_archive(
                    "prefix-collision.zip",
                    [
                        ("plugins/ca-codex/agents", b"file\n"),
                        ("plugins/ca-codex/agents/probe.md", b"invalid\n"),
                    ],
                ),
                "symbolic link": write_archive(
                    "symbolic-link.zip",
                    [(symlink, b"target.md")],
                ),
            }
            for index, (label, archive) in enumerate(hostile.items()):
                with self.subTest(label=label):
                    destination = root / f"rejected-{index}"
                    failed = run_archive_extraction_fixture(archive, destination)
                    self.assertNotEqual(failed.returncode, 0)
                    self.assertFalse(destination.exists())

    def test_candidate_metadata_is_derived_only_after_digest_bound_extraction(self):
        """ARC-01: receipt/install metadata comes from the protected extracted tree."""
        with tempfile.TemporaryDirectory() as temporary:
            package_root = Path(temporary) / "ca-codex"
            tracked = subprocess.run(
                ["git", "ls-files", "-z", "--", "plugins/ca-codex"],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(tracked.returncode, 0, tracked.stderr)
            prefix = "plugins/ca-codex/"
            for source_name in tracked.stdout.split("\0"):
                if not source_name.startswith(prefix):
                    continue
                relative = source_name.removeprefix(prefix)
                source = REPO_ROOT / source_name
                target = package_root / Path(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

            hooks_path = package_root / "hooks" / "hooks.json"
            native_hooks = hooks_path.read_text(encoding="utf-8").replace(
                "${CLAUDE_PLUGIN_ROOT}", "${PLUGIN_ROOT}"
            )
            self.assertEqual(
                sha256_text(native_hooks),
                "b13fc7bc70569a0885ef6bbd1be553b983ce0daf95753d287a64edc846b0b9cf",
            )
            hooks_path.write_text(native_hooks, encoding="utf-8", newline="")

            metadata = run_candidate_metadata_fixture(package_root)
            self.assertEqual(metadata.returncode, 0, metadata.stdout + metadata.stderr)
            observed = json.loads(metadata.stdout)
            manifest = json.loads(
                (package_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )
            self.assertEqual(observed["Version"], manifest["version"])
            self.assertRegex(observed["ResourceSha256"], r"^[0-9a-f]{64}$")

        broker_source = BROKER.read_text(encoding="utf-8")
        extraction = broker_source.index(
            "$archiveEvidence = Expand-BoundedCandidateArchive"
        )
        metadata_read = broker_source.index(
            "$candidate = Get-CandidateMetadata $hostPluginRoot"
        )
        self.assertLess(extraction, metadata_read)
        self.assertNotIn("Get-CandidateMetadata $archive", broker_source)

    def _route_fixture(self, root: Path) -> dict:
        route = self.contract["route_corpus"]
        sources = [
            REPO_ROOT / "plugins" / "ca-codex" / "skills" / "ca-review" / "SKILL.md",
            REPO_ROOT / "plugins" / "ca-codex" / "routines" /
            "dispatching-parallel-agents" / "SKILL.md",
            REPO_ROOT / "core" / "surface" / "agents" / "coverage-auditor.md",
        ]
        paths = []
        for source, relative in zip(sources, route["paths"], strict=True):
            target = root / Path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            paths.append(target)
        driver = run_fixture(DRIVER, self.driver_fixture)
        self.assertEqual(driver.returncode, 0, driver.stdout + driver.stderr)
        observation = json.loads(driver.stdout)
        records = []
        for index, path in enumerate(paths, start=1):
            records.append(
                {
                    "record_id": 1000 + index,
                    "timestamp": f"2026-08-26T12:00:0{index}Z",
                    "subject_sid": "S-1-5-21-1-2-3-1001",
                    "process_id": 4200,
                    "process_sha256": self.runtime_sha,
                    "package_full_name": self.driver_fixture["desktop"]["package_full_name"],
                    "publisher": self.driver_fixture["desktop"]["publisher"],
                    "parent_process_id": 4100,
                    "process_chain_sha256": observation["process_chain_sha256"],
                    "object_name": str(path),
                }
            )
        return {
            "schema_version": 1,
            "plugin_root": str(root),
            "auth_root": r"C:\Users\proof\.codex",
            "desktop_sid": "S-1-5-21-1-2-3-1001",
            "challenge_key": "4" * 64,
            "challenge_nonce": "5" * 64,
            "vm_id": "11111111-1111-4111-8111-111111111111",
            "bootstrap_sid": "S-1-5-21-1-2-3-500",
            "driver_observation": observation,
            "process_audit": {
                "record_id": 900,
                "timestamp": "2026-08-26T11:59:59Z",
                "subject_sid": "S-1-5-21-1-2-3-1001",
                "process_id": 4200,
                "parent_process_id": 4100,
                "executable_sha256": self.runtime_sha,
            },
            "audit_records": records,
            "auth_audit_records": [],
        }

    def test_probe_correlates_thread_dispatch_exact_process_and_audited_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = (
                Path(temp) / "Users" / "proof" / ".codex" / "plugins" / "cache" /
                "codearbiter" / "ca-codex" / "0.7.4"
            )
            fixture = self._route_fixture(root)
            result = run_fixture(PROBE, fixture)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            observed = json.loads(result.stdout)
            self.assertEqual(observed["test_result"], "SUCCEEDED")
            self.assertEqual(observed["selected_plugin_root"], str(root))
            self.assertEqual(observed["dispatch_agent"], "coverage-auditor")
            self.assertEqual(len(observed["route_events"]), 3)
            self.assertLessEqual(observed["response_utf8_bytes"], 4096)
            self.assertRegex(observed["challenge_response_sha256"], r"^[0-9a-f]{64}$")

            mutations = {
                "wrong SID": lambda value: value["audit_records"][1].update(subject_sid="S-1-5-21-1-2-3-1002"),
                "lookalike process": lambda value: value["audit_records"][1].update(process_sha256="6" * 64),
                "wrong ancestry": lambda value: value["audit_records"][1].update(process_chain_sha256="7" * 64),
                "unattributed process event": lambda value: value["process_audit"].update(
                    subject_sid="S-1-5-21-1-2-3-1002"
                ),
                "wrong process parent": lambda value: value["process_audit"].update(
                    parent_process_id=4300
                ),
                "process created after read": lambda value: value["process_audit"].update(
                    record_id=2000
                ),
                "process created after request": lambda value: value["process_audit"].update(
                    timestamp="2026-08-26T12:00:01Z"
                ),
                "route read before request": lambda value: value["audit_records"][0].update(
                    timestamp="2026-08-26T11:59:59Z"
                ),
                "route read after dispatch": lambda value: value["audit_records"][2].update(
                    timestamp="2026-08-26T12:00:05Z"
                ),
                "candidate reads auth store": lambda value: value["auth_audit_records"].append(
                    {
                        "record_id": 995,
                        "timestamp": "2026-08-26T12:00:02Z",
                        "subject_sid": "S-1-5-21-1-2-3-1001",
                        "process_id": 4400,
                        "object_name": r"C:\Users\proof\.codex\auth.json",
                        "access_status": "success",
                    }
                ),
                "runtime reads auth store during route": lambda value: value["auth_audit_records"].append(
                    {
                        "record_id": 996,
                        "timestamp": "2026-08-26T12:00:02Z",
                        "subject_sid": "S-1-5-21-1-2-3-1001",
                        "process_id": 4200,
                        "object_name": r"C:\Users\proof\.codex\auth.json",
                        "access_status": "success",
                    }
                ),
                "desktop reads auth store during route": lambda value: value["auth_audit_records"].append(
                    {
                        "record_id": 997,
                        "timestamp": "2026-08-26T12:00:02Z",
                        "subject_sid": "S-1-5-21-1-2-3-1001",
                        "process_id": 4100,
                        "object_name": r"C:\Users\proof\.codex\auth.json.lock",
                        "access_status": "success",
                    }
                ),
                "wrong package": lambda value: value["audit_records"][1].update(package_full_name="Lookalike.Codex_1.0.0.0_x64__example"),
                "reordered": lambda value: (
                    value["audit_records"][0].update(record_id=1003),
                    value["audit_records"][2].update(record_id=1001),
                ),
                "duplicate": lambda value: value["audit_records"].append(dict(value["audit_records"][1], record_id=1004)),
                "flood": lambda value: value.update(audit_records=value["audit_records"] * 1400),
                "wrong dispatch": lambda value: value["driver_observation"].update(dispatch_agent="security-reviewer"),
            }
            for label, mutate in mutations.items():
                with self.subTest(label=label):
                    changed = json.loads(json.dumps(fixture))
                    mutate(changed)
                    failed = run_fixture(PROBE, changed)
                    self.assertNotEqual(failed.returncode, 0)
                    self.assertNotIn('"test_result":"SUCCEEDED"', failed.stdout)

    def test_probe_production_prepare_and_collect_seams_parse_real_event_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = (
                Path(temp) / "Users" / "proof" / ".codex" / "plugins" / "cache" /
                "codearbiter" / "ca-codex" / "0.7.4"
            )
            normalized = self._route_fixture(root)
            process = normalized["process_audit"]
            envelopes = [
                {
                    "id": 4688,
                    "record_id": 897,
                    "timestamp": "2026-08-26T11:59:58Z",
                    "access_status": "success",
                    "executable_sha256": normalized["driver_observation"]["driver_process_executable_sha256"],
                    "data": {
                        "SubjectUserSid": normalized["desktop_sid"],
                        "NewProcessId": hex(normalized["driver_observation"]["driver_process_id"]),
                        "ProcessId": hex(normalized["driver_observation"]["driver_parent_process_id"]),
                        "NewProcessName": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                        "CommandLine": self.driver_command_line,
                    },
                },
                {
                    "id": 4688,
                    "record_id": 898,
                    "timestamp": "2026-08-26T11:59:59Z",
                    "access_status": "success",
                    "executable_sha256": normalized["driver_observation"]["app_server_process_sha256"],
                    "data": {
                        "SubjectUserSid": normalized["desktop_sid"],
                        "NewProcessId": hex(normalized["driver_observation"]["app_server_process_id"]),
                        "ProcessId": hex(normalized["driver_observation"]["app_server_parent_process_id"]),
                        "NewProcessName": r"C:\Program Files\WindowsApps\OpenAI.Codex\codex.exe",
                        "CommandLine": r'"C:\Program Files\WindowsApps\OpenAI.Codex\codex.exe" app-server --stdio',
                    },
                },
                {
                    "id": 4688,
                    "record_id": process["record_id"],
                    "timestamp": process["timestamp"],
                    "access_status": "success",
                    "executable_sha256": process["executable_sha256"],
                    "data": {
                        "SubjectUserSid": normalized["desktop_sid"],
                        "NewProcessId": hex(process["process_id"]),
                        "ProcessId": hex(process["parent_process_id"]),
                        "NewProcessName": r"C:\Program Files\WindowsApps\OpenAI.Codex\codex.exe",
                        "CommandLine": r'"C:\Program Files\WindowsApps\OpenAI.Codex\codex.exe" app-server',
                    },
                },
                {
                    "id": 4688,
                    "record_id": 901,
                    "timestamp": "2026-08-26T11:59:59Z",
                    "access_status": "success",
                    "executable_sha256": normalized["driver_observation"]["driver_process_executable_sha256"],
                    "data": {
                        "SubjectUserSid": normalized["desktop_sid"],
                        "NewProcessId": hex(4402),
                        "ProcessId": hex(normalized["driver_observation"]["runtime_process_id"]),
                        "NewProcessName": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                        "CommandLine": (
                            "powershell.exe -NoLogo -NoProfile -NonInteractive -Command "
                            f'Get-Content -LiteralPath "{self.canary_path}"'
                        ),
                    },
                },
            ]
            for record in normalized["audit_records"]:
                envelopes.append(
                    {
                        "id": 4663,
                        "record_id": record["record_id"],
                        "timestamp": record["timestamp"],
                        "access_status": "success",
                        "executable_sha256": None,
                        "data": {
                            "SubjectUserSid": normalized["desktop_sid"],
                            "ProcessId": hex(record["process_id"]),
                            "ObjectName": record["object_name"],
                        },
                    }
                )
            harness = {
                "schema_version": 2,
                "harness_mode": "production-audit",
                "plugin_root": normalized["plugin_root"],
                "auth_root": normalized["auth_root"],
                "desktop_sid": normalized["desktop_sid"],
                "start_record_id": 899,
                "challenge_key": normalized["challenge_key"],
                "challenge_nonce": normalized["challenge_nonce"],
                "vm_id": normalized["vm_id"],
                "bootstrap_sid": normalized["bootstrap_sid"],
                "driver_observation": normalized["driver_observation"],
                "event_envelopes": envelopes,
            }
            success = run_fixture(PROBE, harness)
            self.assertEqual(success.returncode, 0, success.stdout + success.stderr)
            payload = json.loads(success.stdout)
            self.assertEqual(payload["test_result"], "SUCCEEDED")
            self.assertEqual(len(payload["preparation_trace"]), 6)
            self.assertEqual(len(payload["applied_operations"]), 6)

            mutations = {
                "missing process event": lambda value: value.update(
                    event_envelopes=[item for item in value["event_envelopes"] if item["record_id"] != 900]
                ),
                "duplicate process event": lambda value: value["event_envelopes"].insert(
                    3, dict(value["event_envelopes"][2], record_id=899)
                ),
                "wrong executable digest": lambda value: value["event_envelopes"][2].update(
                    executable_sha256="9" * 64
                ),
                "wrong route PID": lambda value: value["event_envelopes"][4]["data"].update(
                    ProcessId=hex(4999)
                ),
                "duplicate same-binary runtime": lambda value: value["event_envelopes"].append(
                    {
                        **value["event_envelopes"][2],
                        "record_id": 902,
                        "data": {**value["event_envelopes"][2]["data"], "NewProcessId": hex(4998)},
                    }
                ),
                "appended canary command": lambda value: value["event_envelopes"][3]["data"].update(
                    CommandLine=value["event_envelopes"][3]["data"]["CommandLine"] + "; Start-Evil"
                ),
                "candidate hook process": lambda value: value["event_envelopes"].append(
                    {
                        "id": 4688,
                        "record_id": 950,
                        "timestamp": "2026-08-26T12:00:00Z",
                        "access_status": "success",
                        "executable_sha256": "8" * 64,
                        "data": {
                            "SubjectUserSid": value["desktop_sid"],
                            "NewProcessId": hex(4400),
                            "ProcessId": hex(process["process_id"]),
                            "NewProcessName": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                            "CommandLine": value["plugin_root"] + r"\hooks\session-start.ps1",
                        },
                    }
                ),
                "system powershell inline server": lambda value: value["event_envelopes"].append(
                    {
                        "id": 4688,
                        "record_id": 951,
                        "timestamp": "2026-08-26T12:00:00Z",
                        "access_status": "success",
                        "executable_sha256": value["driver_observation"]["driver_process_executable_sha256"],
                        "data": {
                            "SubjectUserSid": value["desktop_sid"],
                            "NewProcessId": hex(4401),
                            "ProcessId": hex(process["process_id"]),
                            "NewProcessName": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                            "CommandLine": "powershell -NoProfile -Command Start-EvilServer",
                        },
                    }
                ),
            }
            for label, mutate in mutations.items():
                with self.subTest(label=label):
                    changed = json.loads(json.dumps(harness))
                    mutate(changed)
                    failed = run_fixture(PROBE, changed)
                    self.assertNotEqual(failed.returncode, 0)

            probe_source = PROBE.read_text(encoding="utf-8")
            self.assertGreaterEqual(probe_source.count("Invoke-AuditPreparation"), 3)
            self.assertGreaterEqual(probe_source.count("Convert-WindowsAuditEvents"), 3)

    def test_broker_state_machine_never_finalizes_before_observed_teardown(self):
        success = run_fixture(BROKER, self.broker_fixture)
        self.assertEqual(success.returncode, 0, success.stdout + success.stderr)
        payload = json.loads(success.stdout)
        trace = payload["trace"]
        teardown = [
            "account-disabled", "account-deleted", "profile-destroyed",
            "vm-destroyed", "run-root-destroyed",
        ]
        for item in teardown:
            self.assertLess(trace.index(item), trace.index("receipt-finalized"))
        self.assertTrue(payload["receipt_would_finalize"])

        fail_points = [
            "contract-verified", "iso-applied-to-fresh-vhdx", "isolation-measured",
            "identity-created", "network-policy-installed", "codex-permission-profile-proven",
            "autologon-secret-cleared",
            "device-auth-prompt-ready", "device-auth-completed", "desktop-route-observed",
            "network-policy-measured",
            "account-disabled", "account-deleted", "profile-destroyed", "vm-destroyed",
            "run-root-destroyed", "artifact-inventory-cleared",
        ]
        for fail_after in fail_points:
            with self.subTest(fail_after=fail_after):
                failed = run_fixture(BROKER, self.broker_fixture, fail_after=fail_after)
                self.assertNotEqual(failed.returncode, 0)
                result = json.loads(failed.stdout)
                self.assertFalse(result["receipt_would_finalize"])
                self.assertNotIn("receipt-finalized", result["trace"])
                for cleanup in [
                    "account-disabled", "account-deleted", "profile-destroyed",
                    "vm-destroyed", "run-root-destroyed", "artifact-inventory-cleared",
                ]:
                    self.assertIn(cleanup, result["trace"])

        broker_source = BROKER.read_text(encoding="utf-8")
        self.assertNotIn("Invoke-TestLifecycle", broker_source)
        self.assertIn("Invoke-BrokerStage $lifecycle", broker_source)
        self.assertIn("Invoke-BrokerCleanupStage $lifecycle", broker_source)

    def test_broker_retries_destructive_cleanup_and_verifies_final_absence(self):
        for stage in ["vm-destroyed", "run-root-destroyed"]:
            with self.subTest(stage=stage, failure="transient"):
                recovered = run_fixture(
                    BROKER,
                    self.broker_fixture,
                    cleanup_failure=f"{stage}:once",
                )
                self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
                result = json.loads(recovered.stdout)
                self.assertTrue(result["receipt_would_finalize"])
                self.assertEqual(result["cleanup_attempts"][stage], 2)
                self.assertTrue(all(result["cleanup_observations"].values()))
                self.assertEqual(result["trace"].count(stage), 1)

            with self.subTest(stage=stage, failure="permanent"):
                blocked = run_fixture(
                    BROKER,
                    self.broker_fixture,
                    cleanup_failure=f"{stage}:always",
                )
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn('"receipt_would_finalize":false', blocked.stdout)
                self.assertIn('"cleanup_retry_exhausted":true', blocked.stdout)
                result = json.loads(blocked.stdout)
                self.assertEqual(result["cleanup_attempts"][stage], 3)
                self.assertFalse(result["cleanup_observations"][stage])
                self.assertEqual(
                    result["cleanup_observations"]["vhdx-destroyed"],
                    stage == "vm-destroyed",
                )
                self.assertNotIn("receipt-finalized", result["trace"])
                self.assertIn("artifact-inventory-cleared", result["attempted_cleanup"])
                self.assertTrue(result["cleanup_errors"])

    def test_broker_removes_receipt_after_late_finalization_failure(self):
        expected_errors = {
            "write-after-persist": "injected receipt failure after bytes persisted",
            "post-write-inventory": "injected post-write receipt inventory failure",
        }
        for failure, expected_error in expected_errors.items():
            with self.subTest(failure=failure):
                blocked = run_fixture(
                    BROKER,
                    self.broker_fixture,
                    receipt_failure=failure,
                )
                self.assertNotEqual(blocked.returncode, 0)
                result = json.loads(blocked.stdout)
                self.assertFalse(result["receipt_would_finalize"])
                self.assertTrue(result["receipt_absent"])
                self.assertEqual(result["cleanup_attempts"]["receipt-absent"], 1)
                self.assertEqual(result["original_failure"], expected_error)
                self.assertEqual(result["reported_failure"], expected_error)
                self.assertNotIn("receipt-finalized", result["trace"])

    def test_broker_preserves_original_error_when_receipt_removal_exhausts(self):
        blocked = run_fixture(
            BROKER,
            self.broker_fixture,
            receipt_failure="write-after-persist",
            receipt_cleanup_failure=True,
        )
        self.assertNotEqual(blocked.returncode, 0)
        result = json.loads(blocked.stdout)
        original = "injected receipt failure after bytes persisted"
        self.assertFalse(result["receipt_absent"])
        self.assertEqual(result["cleanup_attempts"]["receipt-absent"], 3)
        self.assertEqual(result["original_failure"], original)
        self.assertEqual(result["inner_failure"], original)
        self.assertIn("receipt-absent cleanup retry exhausted", result["reported_failure"])
        self.assertTrue(result["cleanup_errors"])

    def test_production_catch_uses_shared_failure_finalizer_after_cleanup_loop(self):
        broker_source = BROKER.read_text(encoding="utf-8")
        finalizer_token = "function Invoke-BrokerFailureFinalization"
        self.assertIn(finalizer_token, broker_source)
        finalizer = broker_source[broker_source.index(finalizer_token):]
        self.assertLess(
            finalizer.index("Remove-BrokerReceiptAfterFailure"),
            finalizer.index("Assert-BrokerCleanupObservations"),
        )
        self.assertLess(
            finalizer.index("Assert-BrokerCleanupObservations"),
            finalizer.index("New-BrokerReportedFailure"),
        )

        fixture_start = broker_source.index("function Invoke-BrokerReceiptFailureFixture")
        fixture_end = broker_source.index("function Complete-BrokerLifecycle", fixture_start)
        fixture_body = broker_source[fixture_start:fixture_end]
        self.assertIn("Invoke-BrokerFailureFinalization", fixture_body)

        production_catch = broker_source[broker_source.index("    $failure = $_", fixture_end):]
        cleanup_loop = production_catch.index(
            "while($lifecycle.CleanupIndex -lt $script:BrokerCleanupStages.Count)"
        )
        finalizer_call = production_catch.index(
            "Invoke-BrokerFailureFinalization $lifecycle $failure $ReceiptPath"
        )
        self.assertLess(cleanup_loop, finalizer_call)
        self.assertNotIn(
            "Remove-BrokerReceiptAfterFailure $lifecycle $ReceiptPath",
            production_catch,
        )


if __name__ == "__main__":
    unittest.main()
