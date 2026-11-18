#!/usr/bin/env python3
"""Task 2 package, generation, and independent-release contract tests."""
from __future__ import annotations

import argparse
import ast
import base64
import copy
import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import tarfile
import threading
import time
import unittest
from collections.abc import Callable
from queue import Empty, Queue
from unittest import mock

from pi_cli_resolver import resolve_pi_cli_path as _resolve_pi_cli_path


REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "ca-pi"
TOOLS = PLUGIN / "tools"
PLATFORM_PACKAGE_PARTITION = None


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_pi_package_source(agent_dir: Path) -> str:
    """Mirror Node path.relative, including its absolute cross-volume result."""
    repo = REPO.resolve()
    configured_agent_dir = agent_dir.absolute()
    repo_drive, _ = os.path.splitdrive(str(repo))
    agent_drive, _ = os.path.splitdrive(str(configured_agent_dir))
    if repo_drive.casefold() != agent_drive.casefold():
        return str(repo)
    return os.path.relpath(repo, configured_agent_dir)


def live_pi_cli() -> tuple[str, Path]:
    """Resolve the already-installed Pi CLI from PATH without npm/config reads."""
    executable = shutil.which("pi.cmd" if os.name == "nt" else "pi") or shutil.which("pi")
    if executable is None:
        raise AssertionError("Pi CLI is not available on PATH")
    cli = _resolve_pi_cli_path(executable)
    node = shutil.which("node")
    if node is None:
        raise AssertionError("Node is not available on PATH")
    return node, cli


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Stop an RPC root and descendants using the same OS boundary as Pi fixtures."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=5,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=3)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=5,
            check=False,
        )
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=5)


def rpc_shutdown_observer_source(trace: Path, *, module: bool = False) -> str:
    """Bounded passive observer, also embeddable in the existing provider."""
    return (
        ("import { writeFileSync } from 'node:fs';\n" if module else
         "const { writeFileSync } = require('node:fs');\n")
        + f"const tracePath = {json.dumps(str(trace))};\n"
        "const started = performance.now();\n"
        "const report = {schemaVersion: 1, pid: process.pid, node: process.version, platform: process.platform, phases: [], reallyExitCallEntered: false};\n"
        "function observe(phase, exitCode) {\n"
        "  if (report.phases.length >= 8) return;\n"
        "  report.phases.push({phase, elapsedMs: Math.round(performance.now() - started),\n"
        "    stdinEnded: process.stdin.readableEnded,\n"
        "    resources: process.getActiveResourcesInfo().slice(0, 16).map(value => value.slice(0, 24)),\n"
        "    ...(phase === 'process_exit' ? {exitCode} : {})});\n"
        "  try { writeFileSync(tracePath, JSON.stringify(report), {encoding: 'utf8', mode: 0o600}); }\n"
        "  catch { /* Diagnostics must not change the host's shutdown outcome. */ }\n"
        "}\n"
        "// Entry into this wrapper is not proof of native shutdown or OS exit.\n"
        "try {\n"
        "  const originalReallyExit = process.reallyExit;\n"
        "  if (typeof originalReallyExit === 'function') {\n"
        "    process.reallyExit = function(...args) {\n"
        "      report.reallyExitCallEntered = true;\n"
        "      try { writeFileSync(tracePath, JSON.stringify(report), {encoding: 'utf8', mode: 0o600}); }\n"
        "      catch { /* This diagnostic write may itself be the last observed cut. */ }\n"
        "      return Reflect.apply(originalReallyExit, this, args);\n"
        "    };\n"
        "  }\n"
        "} catch { /* Optional observation must not change process behavior. */ }\n"
        "globalThis.__caPiRpcShutdownObserve = observe;\n"
        "process.stdin.prependOnceListener('end', () => observe('stdin_end'));\n"
        "process.once('exit', code => observe('process_exit', code));\n"
        "observe('started');\n"
    )


def write_rpc_shutdown_observer(home: Path) -> tuple[Path, Path, Path]:
    """Observe EOF, a shutdown hook, and exit without driving them."""
    preload = home / "ca-rpc-shutdown-observer.cjs"
    extension = home / "ca-rpc-shutdown-observer.ts"
    trace = home / "ca-rpc-shutdown-trace.json"
    preload.write_text(rpc_shutdown_observer_source(trace), encoding="utf-8", newline="\n")
    extension.write_text(
        "export default function observeShutdown(pi: any) {\n"
        "  pi.on('session_shutdown', () => {\n"
        "    (globalThis as any).__caPiRpcShutdownObserve?.('session_shutdown_observer');\n"
        "  });\n"
        "}\n",
        encoding="utf-8", newline="\n",
    )
    return preload, extension, trace


RPC_SHUTDOWN_PHASE_SECONDS = 10
RPC_PROCESS_EXIT_SECONDS = 30


def rpc_shutdown_phase_complete(trace: Path, pid: int) -> bool:
    """Accept only this process's ordered, bounded, successful exit-entry trace."""
    try:
        with trace.open("rb") as stream:
            data = stream.read(8193)
        if len(data) > 8192:
            return False
        report = json.loads(data.decode("utf-8", "strict"))
        if (
            not isinstance(report, dict)
            or type(report.get("schemaVersion")) is not int
            or report["schemaVersion"] != 1
        ):
            return False
        if type(report.get("pid")) is not int or report["pid"] != pid:
            return False
        rows = report.get("phases")
        expected = ["started", "stdin_end", "session_shutdown_observer", "process_exit"]
        if not isinstance(rows, list) or len(rows) != len(expected):
            return False
        elapsed = []
        for index, (row, phase) in enumerate(zip(rows, expected)):
            if not isinstance(row, dict) or row.get("phase") != phase:
                return False
            value = row.get("elapsedMs")
            if type(value) is not int or value < 0:
                return False
            if row.get("stdinEnded") is not (index > 0):
                return False
            elapsed.append(value)
        return (
            elapsed == sorted(elapsed)
            and elapsed[-1] - elapsed[1] <= RPC_SHUTDOWN_PHASE_SECONDS * 1000
            and type(rows[-1].get("exitCode")) is int
            and rows[-1]["exitCode"] == 0
        )
    except (OSError, ValueError, UnicodeError, RecursionError):
        # A concurrent best-effort write may be incomplete. The deadline and
        # final process-exit check still reject a missing or malformed trace.
        return False


def wait_for_rpc_shutdown(
    process: subprocess.Popen[str], trace: Path, *, observed: bool,
) -> int:
    """Bound EOF-to-JS exit entry separately from natural process exit.

    Node persists its enabled compile cache synchronously after exit entry.
    Original raw CLI cases prove natural exit; additional observed cases also
    prove orderly runtime disposal reaches exit entry within the shorter bound.
    Both bounds start at EOF, so observing phases never adds thirty more seconds.
    """
    started = time.monotonic()
    if observed:
        while True:
            remaining = RPC_SHUTDOWN_PHASE_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                break
            if rpc_shutdown_phase_complete(trace, process.pid):
                break
            if process.poll() is not None:
                break
            try:
                process.wait(timeout=min(0.05, remaining))
            except subprocess.TimeoutExpired:
                pass
        if (
            time.monotonic() - started >= RPC_SHUTDOWN_PHASE_SECONDS
            or not rpc_shutdown_phase_complete(trace, process.pid)
        ):
            raise AssertionError(
                "Pi RPC orderly shutdown did not complete within 10 seconds of stdin EOF; "
                f"shutdown trace={rpc_shutdown_diagnostics(trace)}"
            )
    remaining = RPC_PROCESS_EXIT_SECONDS - (time.monotonic() - started)
    if remaining <= 0:
        raise subprocess.TimeoutExpired(process.args, RPC_PROCESS_EXIT_SECONDS)
    return process.wait(timeout=remaining)


def rpc_shutdown_diagnostics(trace: Path) -> str:
    report = safe_rpc_shutdown_report(trace)
    return json.dumps(report, separators=(",", ":"))[:2000] if report is not None else "unavailable or invalid trace"


def safe_rpc_shutdown_report(trace: Path) -> dict | None:
    """Project only fixed diagnostic fields; never echo arbitrary file content."""
    try:
        with trace.open("rb") as stream:
            data = stream.read(8193)
        if len(data) > 8192:
            raise ValueError("oversized trace")
        report = json.loads(data.decode("utf-8", "strict"))
        if not isinstance(report, dict) or type(report.get("schemaVersion")) is not int or report["schemaVersion"] != 1:
            return None
        if type(report.get("pid")) is not int or not 0 < report["pid"] <= 2**32:
            return None
        if not isinstance(report.get("node"), str) or re.fullmatch(r"v[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", report["node"]) is None:
            return None
        if report.get("platform") not in ("win32", "linux", "darwin"):
            return None
        phases = report.get("phases")
        if not isinstance(phases, list) or not 1 <= len(phases) <= 8:
            return None
        rows = []
        for row in phases:
            if not isinstance(row, dict) or row.get("phase") not in ("started", "stdin_end", "session_shutdown_observer", "process_exit"):
                return None
            if type(row.get("elapsedMs")) is not int or not 0 <= row["elapsedMs"] <= 86_400_000 or type(row.get("stdinEnded")) is not bool:
                return None
            resources = row.get("resources")
            if not isinstance(resources, list) or len(resources) > 16 or any(not isinstance(x, str) or len(x) > 24 for x in resources):
                return None
            known_resources = {"PipeWrap", "TTYWrap", "TCPWrap", "UDPWrap", "ProcessWrap", "FSReqCallback", "FSReqPromise", "CloseReq", "Timeout", "Immediate", "FileHandle", "Worker", "MessagePort", "TCPSocketWrap", "TCPServerWrap", "SignalWrap", "ConnectWrap", "WriteWrap", "ShutdownWrap"}
            item = {key: row[key] for key in ("phase", "elapsedMs", "stdinEnded")}
            item["resources"] = [value if value in known_resources else "Other" for value in resources]
            if "exitCode" in row:
                if type(row["exitCode"]) is not int or not -(2**31) <= row["exitCode"] < 2**32:
                    return None
                item["exitCode"] = row["exitCode"]
            rows.append(item)
        projected = {"schemaVersion": 1, "pid": report["pid"], "node": report["node"], "platform": report["platform"], "phases": rows}
        if "reallyExitCallEntered" in report:
            if type(report["reallyExitCallEntered"]) is not bool:
                return None
            projected["reallyExitCallEntered"] = report["reallyExitCallEntered"]
        return projected
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None


RPC_PROTOCOL_PHASES = (
    "spawned", "send_commands", "send_state", "send_invoke", "send_capture",
    "receive_commands", "receive_state", "receive_capture", "agent_settled",
    "collection_complete", "collection_deadline", "stdout_eof", "stdin_closed",
    "process_exited", "shutdown_timeout", "error",
)
_NO_RPC_PROTOCOL = object()


def safe_rpc_protocol_report(value: object) -> dict | None:
    """Closed parent observations, never protocol payloads or inferred completion."""
    try:
        keys = {"schemaVersion", "events", "recordCount", "recordCountSaturated",
                "commandsSeen", "stateSeen", "agentSettledSeen", "captureSeen",
                "collection", "eofClosed", "processExited", "exitCode"}
        if type(value) is not dict or any(type(key) is not str for key in value) or set(value) != keys:
            return None
        if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
            return None
        if type(value["recordCount"]) is not int or not 0 <= value["recordCount"] <= 1_000_000:
            return None
        flags = ("recordCountSaturated", "commandsSeen", "stateSeen", "agentSettledSeen", "captureSeen", "eofClosed")
        if any(type(value[key]) is not bool for key in flags):
            return None
        if value["recordCountSaturated"] and value["recordCount"] != 1_000_000:
            return None
        if type(value["collection"]) is not str or value["collection"] not in ("not-started", "complete", "deadline", "stdout-eof", "error"):
            return None
        if value["processExited"] is not None and type(value["processExited"]) is not bool:
            return None
        code = value["exitCode"]
        if value["processExited"] is True:
            if type(code) is not int or not -(2**31) <= code < 2**32:
                return None
        elif code is not None:
            return None
        events = value["events"]
        if type(events) is not list or not 1 <= len(events) <= 16:
            return None
        phases, elapsed = [], []
        for row in events:
            if type(row) is not dict or any(type(key) is not str for key in row) or set(row) != {"phase", "elapsedMs"}:
                return None
            if type(row["phase"]) is not str or row["phase"] not in RPC_PROTOCOL_PHASES or row["phase"] in phases:
                return None
            if type(row["elapsedMs"]) is not int or not 0 <= row["elapsedMs"] <= 86_400_000:
                return None
            phases.append(row["phase"]); elapsed.append(row["elapsedMs"])
        if phases[0] != "spawned" or elapsed != sorted(elapsed):
            return None
        for key, phase in (("commandsSeen", "receive_commands"), ("stateSeen", "receive_state"),
                           ("agentSettledSeen", "agent_settled"), ("captureSeen", "receive_capture"),
                           ("eofClosed", "stdin_closed")):
            if value[key] != (phase in phases):
                return None
        if (value["processExited"] is True) != ("process_exited" in phases):
            return None
        terminal = {"complete": "collection_complete", "deadline": "collection_deadline", "stdout-eof": "stdout_eof", "error": "error"}
        if value["collection"] in terminal and terminal[value["collection"]] not in phases:
            return None
        return json.loads(json.dumps(value))
    except Exception:
        return None


class RpcProtocolDiagnostic:
    """Best-effort fixed-symbol bookkeeping; never owns the RPC verdict."""
    def __init__(self):
        self.started = time.monotonic()
        self.value = {"schemaVersion": 1, "events": [], "recordCount": 0,
                      "recordCountSaturated": False, "commandsSeen": False, "stateSeen": False,
                      "agentSettledSeen": False, "captureSeen": False, "collection": "not-started",
                      "eofClosed": False, "processExited": None, "exitCode": None}
        self.mark("spawned")

    def mark(self, phase):
        try:
            events = self.value["events"]
            if phase in RPC_PROTOCOL_PHASES and len(events) < 16 and not any(row["phase"] == phase for row in events):
                events.append({"phase": phase, "elapsedMs": round((time.monotonic() - self.started) * 1000)})
        except Exception:
            pass

    def observe_record(self, record):
        try:
            count = self.value["recordCount"]
            self.value["recordCount"] = min(count + 1, 1_000_000)
            self.value["recordCountSaturated"] |= count == 1_000_000
            for key, identifier in (("commandsSeen", "commands"), ("stateSeen", "state"), ("captureSeen", "capture")):
                if record.get("id") == identifier:
                    self.value[key] = True
                    self.mark("receive_" + identifier)
            if record.get("type") == "agent_settled":
                self.value["agentSettledSeen"] = True
                self.mark("agent_settled")
        except Exception:
            pass

    def collected(self, outcome):
        self.value["collection"] = outcome
        self.mark({"complete": "collection_complete", "deadline": "collection_deadline", "stdout-eof": "stdout_eof", "error": "error"}[outcome])

    def closed_stdin(self):
        self.value["eofClosed"] = True
        self.mark("stdin_closed")

    def failed(self):
        if self.value["collection"] == "not-started":
            self.value["collection"] = "error"
        self.mark("error")

    def exited(self, code):
        if type(code) is int:
            self.value["processExited"], self.value["exitCode"] = True, code
            self.mark("process_exited")
        elif code is None:
            self.value["processExited"] = False

    def snapshot(self):
        return safe_rpc_protocol_report(self.value)


def rpc_protocol_observe(diagnostic, operation, *args):
    """An optional diagnostic failure cannot become the test's failure."""
    try:
        return getattr(diagnostic, operation)(*args)
    except Exception:
        return None


def retain_rpc_shutdown_failure(trace: Path, *, protocol: object = _NO_RPC_PROTOCOL) -> str | None:
    """Failure-only, exclusive CI artifact; never participates in the verdict."""
    selected = os.environ.get("CA_PI_RPC_DIAGNOSTICS_DIR")
    if not selected:
        return None
    try:
        report = {"schemaVersion": 1, "outcome": "failure", "trace": safe_rpc_shutdown_report(trace)}
        if protocol is not _NO_RPC_PROTOCOL:
            report.update(schemaVersion=2, protocol=safe_rpc_protocol_report(protocol))
        encoded = json.dumps(report, separators=(",", ":")) + "\n"
        if len(encoded.encode("utf-8")) > 8192:
            return None
        destination = Path(selected)
        destination.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink() or not destination.is_dir():
            return None
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="rpc-shutdown-", suffix=".json", dir=destination, delete=False) as stream:
            stream.write(encoded)
            return Path(stream.name).name
    except (OSError, ValueError):
        return None


def rpc_diagnostic_runtime_identity(node: str, cli: Path) -> dict | None:
    """Hash the admitted executable and direct RPC entries, without logging paths."""
    try:
        entry = cli.parent / "cli-runtime.js"
        with entry.open("rb") as stream:
            source = stream.read(16_385)
        if len(source) > 16_384:
            return None
        imported = re.search(
            rb'import\{configureHttpDispatcher,main\}from"(\./chunks/[A-Za-z0-9_-]+\.js)"',
            source,
        )
        if imported is None:
            return None
        runtime = cli.parent / imported[1].decode("ascii")
        paths = {"nodeSha256": Path(node), "cliSha256": cli,
                 "entrySha256": entry, "rpcModuleSha256": runtime}
        identities = {}
        for name, path in paths.items():
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as stream:
                while block := stream.read(65_536):
                    size += len(block)
                    if size > 128 << 20:
                        return None
                    digest.update(block)
            identities[name] = digest.hexdigest()
        return identities
    except (OSError, ValueError, UnicodeError):
        return None


def retain_rpc_observed_raw_diagnostics(trace: Path, identity: dict | None, *, succeeded: bool) -> str | None:
    """Separate observed-route receipt; never changes the raw compatibility verdict."""
    selected = os.environ.get("CA_PI_RPC_DIAGNOSTICS_DIR")
    if not selected:
        return None
    fields = {"nodeSha256", "cliSha256", "entrySha256", "rpcModuleSha256"}
    if not isinstance(identity, dict) or set(identity) != fields or any(
        not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in identity.values()
    ):
        identity = None
    try:
        destination = Path(selected)
        destination.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink() or not destination.is_dir():
            return None
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="rpc-shutdown-observed-", suffix=".json", dir=destination, delete=False) as stream:
            json.dump({"schemaVersion": 1, "route": "passive-observed-raw-companion",
                       "outcome": "observed-pass" if succeeded is True else "observed-failure",
                       "runtimeIdentity": identity, "trace": safe_rpc_shutdown_report(trace)},
                      stream, separators=(",", ":"))
            stream.write("\n")
            return Path(stream.name).name
    except (OSError, ValueError):
        return None


def run_rpc_commands(
    cwd: Path,
    agent_dir: Path,
    home: Path,
    *,
    package_source: Path = REPO,
    invoke_alias: bool = False,
    invoke_doctor: bool = False,
    invoke_enforcement_fault: bool = False,
    invoke_read_context: bool = False,
    project_trusted: bool = True,
    mutation_path: Path | None = None,
    fault_marker_path: Path | None = None,
    governed_read_path: Path | None = None,
    ungoverned_read_path: Path | None = None,
    _rpc_command: list[str] | None = None,
    _on_process_started: Callable[[subprocess.Popen[str], threading.Thread], None] | None = None,
    _after_install: Callable[[], None] | None = None,
    _observe_shutdown: bool = False,
) -> list[dict]:
    node, cli = live_pi_cli()
    temp_dir = home / "temp"
    for path in (agent_dir, home, temp_dir, home / "appdata", home / "xdg"):
        path.mkdir(parents=True, exist_ok=True)
    environment = {
        "APPDATA": str(home / "appdata"),
        "HOME": str(home),
        "PATH": os.environ.get("PATH", ""),
        "PI_CODING_AGENT_DIR": str(agent_dir),
        "PI_OFFLINE": "1",
        "PI_TELEMETRY": "0",
        # Installed-package proof owns a complete inventory. The real Python
        # bridge must not add untracked bytecode to those original bytes.
        "PYTHONDONTWRITEBYTECODE": "1",
        "TEMP": str(temp_dir),
        "TMP": str(temp_dir),
        "USERPROFILE": str(home),
        "XDG_CONFIG_HOME": str(home / "xdg"),
    }
    for name in ("ComSpec", "PATHEXT", "SystemRoot", "WINDIR"):
        if os.environ.get(name):
            environment[name] = os.environ[name]
    (agent_dir / "settings.json").write_text(
        json.dumps(
            {
                "npmCommand": [
                    "npm",
                    "--offline",
                    "--no-audit",
                    "--no-fund",
                    "--ignore-scripts",
                ]
            }
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    install_environment = dict(environment)
    install_environment.pop("PI_OFFLINE", None)
    installed = subprocess.run(
        [node, str(cli), "install", str(package_source.resolve()), "--no-approve"],
        cwd=cwd,
        env=install_environment,
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        timeout=20,
        check=False,
    )
    if installed.returncode != 0:
        raise AssertionError(
            f"Pi package install exited {installed.returncode}: {installed.stderr[-2000:]}"
        )
    configured = read_json(agent_dir / "settings.json")
    packages = configured.get("packages", [])
    if len(packages) != 1:
        raise AssertionError(f"Pi install did not persist exactly one package: {configured!r}")
    if _after_install is not None:
        _after_install()

    provider = home / "ca-task3-capture-provider.ts"
    shutdown_trace = home / "ca-rpc-shutdown-trace.json"
    if invoke_enforcement_fault:
        if mutation_path is None or fault_marker_path is None:
            raise AssertionError("enforcement fault fixture requires mutation and consumed-fault paths")
        provider.write_text(
            """import { writeFileSync } from 'node:fs';
import { createAssistantMessageEventStream } from '@earendil-works/pi-ai';

const mutationPath = __CA_PI_MUTATION_PATH__;
const faultMarkerPath = __CA_PI_FAULT_MARKER_PATH__;

export default function registerFaultProvider(pi: any) {
  let faultArmed = true;
  pi.on('session_start', () => {
    const originalSet = Map.prototype.set;
    Map.prototype.set = function(key: unknown, value: unknown) {
      if (
        faultArmed
        && key === 'tool_call'
        && Array.isArray(value)
        && value.some((candidate) => typeof candidate === 'function')
      ) {
        faultArmed = false;
        Map.prototype.set = originalSet;
        writeFileSync(
          faultMarkerPath,
          'CA_PI_TEST_ENFORCEMENT_REGISTRATION_FAILURE_CONSUMED\\n',
          { encoding: 'utf8', flag: 'wx' },
        );
        throw new Error('CA_PI_TEST_ENFORCEMENT_REGISTRATION_FAILURE');
      }
      return originalSet.call(this, key, value);
    };
  });

  pi.registerProvider('ca-enforcement-fault', {
    name: 'CA Enforcement Fault',
    baseUrl: 'https://example.invalid',
    apiKey: 'test-only-no-network',
    api: 'ca-enforcement-fault-api',
    models: [{
      id: 'ca-enforcement-fault-model',
      name: 'CA Enforcement Fault Model',
      reasoning: false,
      input: ['text'],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow: 128000,
      maxTokens: 4096,
    }],
    streamSimple(model: any, context: any) {
      const stream = createAssistantMessageEventStream();
      queueMicrotask(() => {
        const completed = context.messages.some(
          (message: any) => message.role === 'toolResult' && message.toolCallId === 'ca-enforcement-fault-write',
        );
        const output: any = {
          role: 'assistant',
          content: [],
          api: model.api,
          provider: model.provider,
          model: model.id,
          usage: {
            input: 0,
            output: 0,
            cacheRead: 0,
            cacheWrite: 0,
            totalTokens: 0,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
          },
          stopReason: completed ? 'stop' : 'toolUse',
          timestamp: Date.now(),
        };
        stream.push({ type: 'start', partial: output });
        if (completed) {
          const text = 'fault injection turn settled';
          output.content.push({ type: 'text', text });
          stream.push({ type: 'text_start', contentIndex: 0, partial: output });
          stream.push({ type: 'text_delta', contentIndex: 0, delta: text, partial: output });
          stream.push({ type: 'text_end', contentIndex: 0, content: text, partial: output });
          stream.push({ type: 'done', reason: 'stop', message: output });
          stream.end();
          return;
        }
        const toolCall = {
          type: 'toolCall',
          id: 'ca-enforcement-fault-write',
          name: 'write',
          arguments: { path: mutationPath, content: 'mutation reached the unguarded executor' },
        };
        output.content.push(toolCall);
        stream.push({ type: 'toolcall_start', contentIndex: 0, partial: output });
        const delta = JSON.stringify(toolCall.arguments);
        stream.push({ type: 'toolcall_delta', contentIndex: 0, delta, partial: output });
        stream.push({ type: 'toolcall_end', contentIndex: 0, toolCall, partial: output });
        stream.push({ type: 'done', reason: 'toolUse', message: output });
        stream.end();
      });
      return stream;
    },
  });
}
"""
            .replace("__CA_PI_MUTATION_PATH__", json.dumps(str(mutation_path.resolve())))
            .replace("__CA_PI_FAULT_MARKER_PATH__", json.dumps(str(fault_marker_path.resolve()))),
            encoding="utf-8",
            newline="\n",
        )
    elif invoke_read_context:
        if governed_read_path is None or ungoverned_read_path is None:
            raise AssertionError("read-context fixture requires governed and ungoverned paths")
        # Keep raw argv and the natural-exit verdict. The explicit companion
        # already has its own preload and must not install a second observer.
        observer_source = ""
        shutdown_handler = ""
        if not _observe_shutdown:
            observer_source = rpc_shutdown_observer_source(shutdown_trace, module=True)
            shutdown_handler = (
                "  try {\n"
                "    pi.on('session_shutdown', () => {\n"
                "      (globalThis as any).__caPiRpcShutdownObserve?.('session_shutdown_observer');\n"
                "    });\n"
                "  } catch { /* Optional diagnostics must not change provider behavior. */ }\n"
            )
        provider.write_text(
            observer_source + """import { createAssistantMessageEventStream } from '@earendil-works/pi-ai';

const governedPath = __CA_PI_GOVERNED_PATH__;
const ungovernedPath = __CA_PI_UNGOVERNED_PATH__;
const governedFirstId = 'ca-read-context-governed-first';
const governedSecondId = 'ca-read-context-governed-second';
const ungovernedId = 'ca-read-context-ungoverned';

export default function registerReadContextProvider(pi: any) {
  pi.registerProvider('ca-read-context', {
    name: 'CA Read Context',
    baseUrl: 'https://example.invalid',
    apiKey: 'test-only-no-network',
    api: 'ca-read-context-api',
    models: [{
      id: 'ca-read-context-model',
      name: 'CA Read Context Model',
      reasoning: false,
      input: ['text'],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow: 128000,
      maxTokens: 4096,
    }],
    streamSimple(model: any, context: any) {
      const stream = createAssistantMessageEventStream();
      queueMicrotask(() => {
        const results = context.messages.filter((message: any) => message.role === 'toolResult');
        const governedFirst = results.find((message: any) => message.toolCallId === governedFirstId);
        const governedSecond = results.find((message: any) => message.toolCallId === governedSecondId);
        const ungoverned = results.find((message: any) => message.toolCallId === ungovernedId);
        const output: any = {
          role: 'assistant',
          content: [],
          api: model.api,
          provider: model.provider,
          model: model.id,
          usage: {
            input: 0,
            output: 0,
            cacheRead: 0,
            cacheWrite: 0,
            totalTokens: 0,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
          },
          stopReason: governedFirst && governedSecond && ungoverned ? 'stop' : 'toolUse',
          timestamp: Date.now(),
        };
        stream.push({ type: 'start', partial: output });
        if (governedFirst && governedSecond && ungoverned) {
          const captured = {
            governedFirst: {
              role: governedFirst.role,
              toolCallId: governedFirst.toolCallId,
              toolName: governedFirst.toolName,
              content: governedFirst.content,
              isError: governedFirst.isError,
            },
            governedSecond: {
              role: governedSecond.role,
              toolCallId: governedSecond.toolCallId,
              toolName: governedSecond.toolName,
              content: governedSecond.content,
              isError: governedSecond.isError,
            },
            ungoverned: {
              role: ungoverned.role,
              toolCallId: ungoverned.toolCallId,
              toolName: ungoverned.toolName,
              content: ungoverned.content,
              isError: ungoverned.isError,
            },
          };
          const text = `CA_PI_READ_RESULT:${Buffer.from(JSON.stringify(captured), 'utf8').toString('base64')}`;
          output.content.push({ type: 'text', text });
          stream.push({ type: 'text_start', contentIndex: 0, partial: output });
          stream.push({ type: 'text_delta', contentIndex: 0, delta: text, partial: output });
          stream.push({ type: 'text_end', contentIndex: 0, content: text, partial: output });
          stream.push({ type: 'done', reason: 'stop', message: output });
          stream.end();
          return;
        }
        const toolCall = {
          type: 'toolCall',
          id: governedFirst ? (governedSecond ? ungovernedId : governedSecondId) : governedFirstId,
          name: 'read',
          arguments: { path: governedFirst && governedSecond ? ungovernedPath : governedPath },
        };
        output.content.push(toolCall);
        stream.push({ type: 'toolcall_start', contentIndex: 0, partial: output });
        stream.push({
          type: 'toolcall_delta',
          contentIndex: 0,
          delta: JSON.stringify(toolCall.arguments),
          partial: output,
        });
        stream.push({ type: 'toolcall_end', contentIndex: 0, toolCall, partial: output });
        stream.push({ type: 'done', reason: 'toolUse', message: output });
        stream.end();
      });
      return stream;
    },
  });
__CA_PI_RPC_SHUTDOWN_HANDLER__}
"""
            .replace("__CA_PI_RPC_SHUTDOWN_HANDLER__", shutdown_handler)
            .replace("__CA_PI_GOVERNED_PATH__", json.dumps(str(governed_read_path.resolve())))
            .replace("__CA_PI_UNGOVERNED_PATH__", json.dumps(str(ungoverned_read_path.resolve()))),
            encoding="utf-8",
            newline="\n",
        )
    elif invoke_alias or invoke_doctor:
        provider.write_text(
            """import { createAssistantMessageEventStream } from '@earendil-works/pi-ai';

export default function registerCaptureProvider(pi: any) {
  pi.registerProvider('ca-task3-capture', {
    name: 'CA Task 3 Capture',
    baseUrl: 'https://example.invalid',
    apiKey: 'test-only-no-network',
    api: 'ca-task3-capture-api',
    models: [{
      id: 'ca-task3-capture-model',
      name: 'CA Task 3 Capture Model',
      reasoning: false,
      input: ['text'],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow: 128000,
      maxTokens: 4096,
    }],
    streamSimple(model: any, context: any) {
      const stream = createAssistantMessageEventStream();
      queueMicrotask(() => {
        const user = [...context.messages].reverse().find((message: any) => message.role === 'user');
        const observed = typeof user?.content === 'string'
          ? user.content
          : (user?.content ?? [])
              .filter((part: any) => part.type === 'text')
              .map((part: any) => part.text)
              .join('');
        const text = `CA_PI_CAPTURE:${Buffer.from(observed, 'utf8').toString('base64')}`;
        const output: any = {
          role: 'assistant',
          content: [],
          api: model.api,
          provider: model.provider,
          model: model.id,
          usage: {
            input: 0,
            output: 0,
            cacheRead: 0,
            cacheWrite: 0,
            totalTokens: 0,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
          },
          stopReason: 'stop',
          timestamp: Date.now(),
        };
        stream.push({ type: 'start', partial: output });
        output.content.push({ type: 'text', text: '' });
        stream.push({ type: 'text_start', contentIndex: 0, partial: output });
        output.content[0].text = text;
        stream.push({ type: 'text_delta', contentIndex: 0, delta: text, partial: output });
        stream.push({ type: 'text_end', contentIndex: 0, content: text, partial: output });
        stream.push({ type: 'done', reason: 'stop', message: output });
        stream.end();
      });
      return stream;
    },
  });
}
""",
            encoding="utf-8",
            newline="\n",
        )

    if (invoke_alias or invoke_doctor) and not _observe_shutdown:
        # Embed observation into the already-selected local provider. Raw Node
        # argv and the natural-exit verdict remain unchanged; this captures the
        # previously missing phase when that original compatibility case fails.
        source = provider.read_text(encoding="utf-8")
        source = source.replace(
            "export default function registerCaptureProvider(pi: any) {",
            "export default function registerCaptureProvider(pi: any) {\n"
            "  pi.on('session_shutdown', () => { (globalThis as any).__caPiRpcShutdownObserve?.('session_shutdown_observer'); });",
            1,
        )
        provider.write_text(rpc_shutdown_observer_source(shutdown_trace, module=True) + source, encoding="utf-8", newline="\n")
    command = [
        node,
        str(cli),
        "--mode", "rpc",
        "--offline",
        "--no-session",
        "--approve" if project_trusted else "--no-approve",
        "--no-prompt-templates",
        "--no-themes",
        "--no-context-files",
    ]
    if _observe_shutdown:
        preload, shutdown_observer, shutdown_trace = write_rpc_shutdown_observer(home)
        command[1:1] = ["--require", str(preload)]
        command.extend(["--extension", str(shutdown_observer)])
    if not (invoke_doctor or invoke_enforcement_fault or invoke_read_context):
        command.append("--no-builtin-tools")
    if invoke_alias or invoke_doctor or invoke_enforcement_fault or invoke_read_context:
        provider_name = (
            "ca-enforcement-fault" if invoke_enforcement_fault
            else "ca-read-context" if invoke_read_context
            else "ca-task3-capture"
        )
        model_name = (
            "ca-enforcement-fault-model" if invoke_enforcement_fault
            else "ca-read-context-model" if invoke_read_context
            else "ca-task3-capture-model"
        )
        command.extend(
            [
                "--extension",
                str(provider),
                "--provider",
                provider_name,
                "--model",
                model_name,
                "--api-key",
                "test-only-no-network",
            ]
        )
    if _rpc_command is not None:
        command = _rpc_command
    provider_warmup = None
    diagnostic_dir = os.environ.get("CA_PI_RPC_DIAGNOSTICS_DIR")
    if _observe_shutdown or (os.name == "nt" and diagnostic_dir):
        try:
            from _windows_rpc_timeout import preflight_provider
            provider_warmup = preflight_provider(home)
        except Exception:
            pass  # unavailable warm reads do not replace the RPC case
        if provider_warmup is not None and provider_warmup.get("containment") == "unconfirmed":
            try:
                from _windows_rpc_timeout import retain_preflight
                if diagnostic_dir:
                    retain_preflight(provider_warmup, None, Path(diagnostic_dir))
            except Exception:
                pass
            raise AssertionError("Pi provider hash helper containment unconfirmed; RPC target not spawned")
    if _observe_shutdown or (os.name == "nt" and PLATFORM_PACKAGE_PARTITION == "rpc"):
        # Keep optional cache writes out of the aggregate Windows RPC timing.
        # Standalone discovery, installed qualification and package install use defaults.
        environment["NODE_DISABLE_COMPILE_CACHE"] = "1"
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
        bufsize=1,
        start_new_session=os.name != "nt",
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
    )
    if provider_warmup is not None and diagnostic_dir:
        try:
            from _windows_rpc_timeout import retain_preflight
            retain_preflight(provider_warmup, process.pid, Path(diagnostic_dir))
        except Exception:
            pass
    reader: threading.Thread | None = None
    stderr_reader: threading.Thread | None = None
    # Stderr is diagnostic only: drain raw bytes so malformed UTF-8 cannot stop
    # the reader and let a full pipe stall the child. Protocol stdout stays strict.
    stderr_bytes = b""
    stderr_error: Exception | None = None
    protocol = None
    shutdown_waiting = False

    def stderr_tail() -> str:
        return stderr_bytes.decode("utf-8", errors="replace")[-2000:]
    try:
        try:
            protocol = RpcProtocolDiagnostic()
        except Exception:
            pass
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise AssertionError("Pi RPC did not expose standard streams")

        output: Queue[str | None] = Queue()

        def read_stdout() -> None:
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    output.put(line)
            finally:
                output.put(None)

        reader = threading.Thread(target=read_stdout, name="ca-pi-rpc-stdout", daemon=True)
        reader.start()

        def read_stderr() -> None:
            nonlocal stderr_bytes, stderr_error
            assert process.stderr is not None
            try:
                while chunk := process.stderr.buffer.read1(4096):
                    stderr_bytes = (stderr_bytes + chunk)[-8000:]
            except Exception as error:
                stderr_error = error

        stderr_reader = threading.Thread(target=read_stderr, name="ca-pi-rpc-stderr", daemon=True)
        stderr_reader.start()
        if _on_process_started is not None:
            _on_process_started(process, reader)

        def send(record: dict) -> None:
            assert process.stdin is not None
            process.stdin.write(json.dumps(record, separators=(",", ":")) + "\n")
            process.stdin.flush()
            rpc_protocol_observe(protocol, "mark", "send_" + record["id"])

        def decode(line: str) -> dict:
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise AssertionError(f"Pi RPC emitted non-JSON stdout: {line!r}") from error
            if not isinstance(value, dict):
                raise AssertionError(f"Pi RPC emitted a non-object record: {value!r}")
            return value

        send({"id": "commands", "type": "get_commands"})
        if invoke_read_context:
            send({"id": "state", "type": "get_state"})
        if invoke_alias or invoke_doctor or invoke_enforcement_fault or invoke_read_context:
            send(
                {
                    "id": "invoke",
                    "type": "prompt",
                    "message": (
                        (
                            "read the governed and ungoverned fixtures"
                            if invoke_read_context
                            else "exercise the write tool once"
                            if invoke_enforcement_fault
                            else "/ca-doctor" if invoke_doctor
                            else "/ca-status  __CA_ALIAS_SENTINEL__  "
                        )
                    ),
                }
            )

        records: list[dict] = []
        capture_sent = False
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                line = output.get(timeout=max(0.01, deadline - time.monotonic()))
            except Empty:
                rpc_protocol_observe(protocol, "collected", "deadline")
                break
            if line is None:
                rpc_protocol_observe(protocol, "collected", "stdout-eof")
                break
            value = decode(line)
            records.append(value)
            rpc_protocol_observe(protocol, "observe_record", value)
            if (invoke_alias or invoke_doctor or invoke_read_context) and value.get("type") == "agent_settled" and not capture_sent:
                send({"id": "capture", "type": "get_last_assistant_text"})
                capture_sent = True
            commands_done = any(record.get("id") == "commands" for record in records)
            state_done = not invoke_read_context or any(record.get("id") == "state" for record in records)
            capture_done = any(record.get("id") == "capture" for record in records)
            fault_done = invoke_enforcement_fault and any(
                record.get("type") == "agent_settled" for record in records
            )
            if commands_done and state_done and (
                fault_done
                or not (invoke_alias or invoke_doctor or invoke_enforcement_fault or invoke_read_context)
                or capture_done
            ):
                rpc_protocol_observe(protocol, "collected", "complete")
                break
        else:
            rpc_protocol_observe(protocol, "collected", "deadline")

        process.stdin.close()
        rpc_protocol_observe(protocol, "closed_stdin")
        try:
            shutdown_waiting = True
            returncode = wait_for_rpc_shutdown(process, shutdown_trace, observed=_observe_shutdown)
            shutdown_waiting = False
            rpc_protocol_observe(protocol, "exited", returncode)
        except subprocess.TimeoutExpired as error:
            rpc_protocol_observe(protocol, "mark", "shutdown_timeout")
            raise AssertionError(
                f"Pi RPC did not exit within 30 seconds of stdin EOF; received {len(records)} records; "
                f"stderr tail={stderr_tail()!r}; "
                f"shutdown trace={rpc_shutdown_diagnostics(shutdown_trace)}"
            ) from error
        reader.join(timeout=5)
        if reader.is_alive():
            raise AssertionError("Pi RPC stdout reader did not stop after process exit")
        stderr_reader.join(timeout=5)
        if stderr_reader.is_alive() or stderr_error is not None:
            raise AssertionError(f"Pi RPC stderr reader failed: {stderr_error!r}")
        while True:
            try:
                line = output.get_nowait()
            except Empty:
                break
            if line is not None:
                value = decode(line)
                records.append(value)
                rpc_protocol_observe(protocol, "observe_record", value)
        if returncode != 0:
            raise AssertionError(f"Pi RPC exited {returncode}: {stderr_tail()}")
        if not any(record.get("id") == "commands" for record in records):
            raise AssertionError(f"Pi RPC did not answer get_commands: {records!r}; stderr={stderr_tail()}")
        if invoke_read_context and not any(record.get("id") == "state" for record in records):
            raise AssertionError(f"Pi RPC did not answer get_state: {records!r}; stderr={stderr_tail()}")
        if (invoke_alias or invoke_doctor or invoke_read_context) and not any(record.get("id") == "capture" for record in records):
            raise AssertionError(f"Pi RPC did not capture the alias turn: {records!r}; stderr={stderr_tail()}")
        if invoke_enforcement_fault and not any(record.get("type") == "agent_settled" for record in records):
            raise AssertionError(f"Pi RPC did not settle the fault-injection turn: {records!r}; stderr={stderr_tail()}")
        return records
    except Exception as error:
        rpc_protocol_observe(protocol, "failed")
        try:
            rpc_protocol_observe(protocol, "exited", process.poll())
        except Exception:
            pass
        try:
            retained = retain_rpc_shutdown_failure(
                shutdown_trace, protocol=rpc_protocol_observe(protocol, "snapshot"),
            )
        except Exception:
            retained = None
        if retained is not None:
            error.add_note(f"Pi RPC failure diagnostic artifact: {retained}")
            if shutdown_waiting:
                # Original failure and phase receipt exist before optional OS observation.
                # No later observation may substitute for this failed wait.
                try:
                    from _windows_rpc_timeout import retain_failure
                    native = retain_failure(process, Path(node), Path(os.environ["CA_PI_RPC_DIAGNOSTICS_DIR"]))
                    if native is not None:
                        error.add_note(f"Pi RPC native timeout diagnostic artifact: {native}")
                except Exception:
                    pass
        raise
    finally:
        cleanup_errors: list[str] = []
        if process.stdin is not None and not process.stdin.closed:
            try:
                process.stdin.close()
            except OSError as error:
                cleanup_errors.append(f"stdin close failed: {error}")
        try:
            terminate_process_tree(process)
        except (OSError, subprocess.SubprocessError) as error:
            cleanup_errors.append(f"process-tree termination failed: {error}")
        if reader is not None:
            reader.join(timeout=5)
        if stderr_reader is not None:
            stderr_reader.join(timeout=5)
        if process.stdout is not None and not process.stdout.closed:
            try:
                process.stdout.close()
            except OSError as error:
                cleanup_errors.append(f"stdout close failed: {error}")
        if reader is not None and reader.is_alive():
            reader.join(timeout=2)
            if reader.is_alive():
                cleanup_errors.append("stdout reader remained alive")
        if stderr_reader is not None and stderr_reader.is_alive():
            cleanup_errors.append("stderr reader remained alive")
        if process.stderr is not None and not process.stderr.closed:
            try:
                process.stderr.close()
            except OSError as error:
                cleanup_errors.append(f"stderr close failed: {error}")
        if cleanup_errors:
            active_error = sys.exc_info()[1]
            message = "; ".join(cleanup_errors)
            if active_error is not None:
                active_error.add_note(f"Pi RPC cleanup: {message}")
            else:
                raise AssertionError(f"Pi RPC cleanup failed: {message}")


def durable_pi_package_copy(destination: Path) -> Path:
    """Materialize only regular tracked ca-pi index blobs outside a worktree."""
    package_root = destination / "durable-plugin" / "ca-pi"
    package_dirs = {
        "agents", "extensions", "generated", "helpers", "hooks",
        "includes", "routines", "skills",
    }
    tracked = subprocess.run(
        ["git", "ls-files", "--stage", "-z", "--", "plugins/ca-pi"],
        cwd=REPO,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    entries: list[tuple[str, str, tuple[str, ...]]] = []
    for record in filter(None, tracked):
        metadata, separator, encoded_path = record.partition(b"\t")
        if not separator:
            raise AssertionError("git ls-files returned a malformed index record")
        mode, oid, stage = metadata.decode("ascii").split()
        relative = encoded_path.decode("utf-8")
        indexed_path = PurePosixPath(relative)
        if (
            indexed_path.is_absolute()
            or indexed_path.as_posix() != relative
            or any(part in {"", ".", ".."} for part in indexed_path.parts)
        ):
            raise AssertionError(f"refusing unsafe ca-pi index path: {relative!r}")
        parts = indexed_path.parts
        included = (
            len(parts) >= 3
            and parts[:2] == ("plugins", "ca-pi")
            and (
                (
                    len(parts) == 3
                    and (parts[2] == "package.json" or Path(parts[2]).suffix == ".md")
                )
                or parts[2] in package_dirs
            )
        )
        if not included:
            continue
        if stage != "0" or mode not in {"100644", "100755"}:
            raise AssertionError(
                f"refusing non-regular or unmerged ca-pi index entry: {mode} {stage} {relative}"
            )
        entries.append((mode, oid, parts[2:]))

    batch = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=REPO,
        input=b"".join(oid.encode("ascii") + b"\n" for _mode, oid, _parts in entries),
        check=True,
        capture_output=True,
    ).stdout
    stream = io.BytesIO(batch)
    for mode, oid, relative_parts in entries:
        header = stream.readline().rstrip(b"\n").split()
        if len(header) != 3 or header[0].decode("ascii") != oid or header[1] != b"blob":
            raise AssertionError(f"git cat-file returned an invalid blob header for {oid}")
        size = int(header[2])
        blob = stream.read(size)
        if len(blob) != size or stream.read(1) != b"\n":
            raise AssertionError(f"git cat-file returned a truncated blob for {oid}")
        target = package_root.joinpath(*relative_parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        if mode == "100755":
            target.chmod(target.stat().st_mode | 0o111)
    if stream.read():
        raise AssertionError("git cat-file returned unexpected trailing output")
    return package_root


def load_build_host_packages():
    path = REPO / "tools" / "build-host-packages.py"
    spec = importlib.util.spec_from_file_location("build_host_packages", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _producer_ast() -> ast.Module:
    source = (REPO / "tools" / "build-host-packages.py").read_text(encoding="utf-8")
    return ast.parse(source)


def producer_cold_receipt_keys() -> set[str]:
    """Statically extract the field names the real cold_execute_artifact_host_payload
    receipt literal assigns, without driving its cold process/subprocess execution.

    Sourced from the writer rather than retyped, so a future field added to the
    receipt in tools/build-host-packages.py makes this drift-detectable instead
    of silently outrunning the release-time consumer's COLD_FIELDS allowlist
    (as happened in 4b437153, which broke every release from main)."""
    matches = [
        node for node in ast.walk(_producer_ast())
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "cold_receipt"
            and isinstance(node.value, ast.Dict)
        )
    ]
    if not matches:
        raise AssertionError("could not locate the cold_receipt dict literal in build-host-packages.py")
    if len(matches) > 1:
        raise AssertionError("build-host-packages.py has more than one cold_receipt dict literal")
    keys = set()
    for key in matches[0].value.keys:
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            raise AssertionError("cold_receipt literal has a non-literal-string key")
        keys.add(key.value)
    return keys


def producer_installed_workflow_format() -> str:
    """Statically extract the installed-host-workflow format string the real
    producer compares workflow_result["format"] against, independent of the
    consumer's own INSTALLED_WORKFLOW_FORMAT constant.

    A test that only compared the consumer's constant to itself would not
    catch a typo in that constant while the producer emits a different real
    value — the same class of drift COLD_FIELDS silently outran in 4b437153."""
    pattern = re.compile(r"\Acodearbiter\.installed-host-workflow/\d+\.\d+\.\d+\Z")
    found = {
        node.value for node in ast.walk(_producer_ast())
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and pattern.fullmatch(node.value)
    }
    if len(found) != 1:
        raise AssertionError(
            f"expected exactly one installed-host-workflow format literal in "
            f"build-host-packages.py, found {sorted(found)}"
        )
    return next(iter(found))


def distributable_violations(root: Path, files: list[Path]) -> list[str]:
    """Return prohibited dependency, native, map, and bundled-payload findings."""
    violations = []
    for path in files:
        relative = path.relative_to(root)
        rendered = relative.as_posix()
        parts = {part.lower() for part in relative.parts}
        reasons = []
        if parts & {"node_modules", "dependencies", "vendor", "vite", "rolldown", "lightningcss"}:
            reasons.append("dependency source tree")
        if path.suffix.lower() in {".node", ".wasm", ".map"}:
            reasons.append("native or source-map artifact")
        if parts & {"extensions", "helpers"} and path.suffix.lower() == ".js":
            try:
                lowered = path.read_text(encoding="utf-8", errors="strict").lower()
            except UnicodeDecodeError:
                reasons.append("non-UTF-8 JavaScript")
            else:
                markers = ("sourcemappingurl=", "node_modules/", "node_modules\\", "rolldown", "lightningcss", "lightning css", "vite/dist")
                if any(marker in lowered for marker in markers):
                    reasons.append("bundled dependency or source-map marker")
        if reasons:
            violations.append(f"{rendered}: {', '.join(reasons)}")
    return violations


def pi_ci_contract_violations(ci: str) -> list[str]:
    """Validate executable Pi matrix and aggregate wiring in their owning jobs."""
    violations = []
    filter_match = re.search(
        r"(?ms)^            ca-pi:\n(?P<body>.*?)(?=^            [a-z][a-z0-9-]*:\n)",
        ci,
    )
    filter_body = filter_match.group("body") if filter_match else ""
    for path in (".github/scripts/test_pi_security.py", ".github/workflows/codeql.yml"):
        if f"- '{path}'" not in filter_body:
            violations.append(f"ca-pi filter missing {path}")

    def job(name: str) -> str:
        match = re.search(rf"(?m)^  {re.escape(name)}:\s*$", ci)
        if match is None:
            violations.append(f"missing job {name}")
            return ""
        following = re.search(r"(?m)^  [A-Za-z0-9_-]+:\s*$", ci[match.end():])
        end = len(ci) if following is None else match.end() + following.start()
        return ci[match.start():end]

    matrix = job("ca-pi-tools")
    for token in (
        "os: [ubuntu-latest, windows-latest, macos-latest]",
        "pi-version: ${{ fromJSON(needs.changes.outputs.pi-versions) }}",
        "pi_host_locks.py install --version ${{ matrix.pi-version }}",
        "npm ci --ignore-scripts",
    ):
        if token not in matrix:
            violations.append(f"ca-pi-tools missing {token}")
    host_lock_command = (
        '        run: python .github/scripts/pi_host_locks.py install '
        '--version ${{ matrix.pi-version }} '
        '--prefix "$RUNNER_TEMP/pi-host-${{ matrix.pi-version }}"'
    )
    if host_lock_command not in matrix.splitlines():
        violations.append("ca-pi-tools does not execute the reviewed host-lock install")
    if re.search(r"(?m)^\s{8}run: npm test -- test/package\.test\.ts\s*$", matrix) is None:
        violations.append("ca-pi-tools does not execute the native package test")
    if re.search(
        r"(?m)^\s{8}run: python \.github/scripts/test_pi_package\.py --rpc-commands\s*$",
        matrix,
    ) is None:
        violations.append("ca-pi-tools does not execute the live package RPC test")

    # Issue #390 AC-2: a Vitest file that compares the LIVE process.platform
    # against a literal cannot be attested by the ubuntu-only canonical job -
    # `test.skipIf(process.platform !== "win32")` simply skips there, and
    # `process.platform === "win32" ? "junction" : "dir"` exercises the POSIX
    # primitive only. Every such file must run on all three operating systems.
    # This oracle derives the set from the sources, independently of
    # test_ci_impact.py, so both would have to be wrong to lose the coverage.
    live_platform = re.compile(r"(?:process|os)\.platform\s*(?:===|!==)")
    matrix_vitest: set[str] = set()
    for match in re.finditer(r"(?m)^\s+run: npm test(?P<rest>[^\n]*)$", matrix):
        matrix_vitest |= {
            token.rsplit("/", 1)[-1]
            for token in match.group("rest").split()
            if token.endswith(".test.ts")
        }
    if "test_pi_platform_contract.py" in matrix:
        contract_source = (REPO / ".github" / "scripts" / "test_pi_platform_contract.py").read_text(
            encoding="utf-8"
        )
        matrix_vitest |= {
            name.rsplit("/", 1)[-1]
            for name in re.findall(r'"(test/[A-Za-z0-9._-]+\.test\.ts)"', contract_source)
        }
    pi_tests = REPO / "plugins" / "ca-pi" / "tools" / "test"
    for source in sorted(pi_tests.glob("*.test.ts")):
        if live_platform.search(source.read_text(encoding="utf-8")) and source.name not in matrix_vitest:
            violations.append(
                f"ca-pi-tools does not run platform-gated suite on every OS: {source.name}"
            )

    # Issue #390/#405: the host-independent half of the Pi contract lives in one
    # canonical job, and its Vitest run is deliberately UNFILTERED so every
    # committed test/*.test.ts file is a required merge gate.
    canonical = job("ca-pi-checks")
    if re.search(r"(?m)^\s{8}run: npm test\s*$", canonical) is None:
        violations.append("ca-pi-checks does not execute the complete unfiltered Pi Vitest suite")
    if "strategy:" in canonical:
        violations.append("ca-pi-checks must not fan out across a matrix")
    for token in (
        "run: python tools/build-host-packages.py --check",
        "run: npm run typecheck",
        "run: npm run build",
        "run: python .github/scripts/test_pi_security.py",
        "run: python .github/scripts/test_pi_parity.py",
        "run: python .github/scripts/pi_benchmark.py --samples 100",
    ):
        if token not in canonical:
            violations.append(f"ca-pi-checks missing {token}")
        if token in matrix:
            violations.append(f"ca-pi-tools repeats host-independent step per cell: {token}")

    latest = job("ca-pi-latest")
    # Issue #381: a job-level continue-on-error still reports the check run as
    # FAILURE, which is the false alarm this contract now forbids. The canary is
    # made advisory by absorbing its two upstream probes at STEP level and
    # publishing a receipt, so a harness break can still turn the check red.
    if re.search(r"(?m)^    continue-on-error: true\s*$", latest) is not None:
        violations.append("ca-pi-latest must not carry a job-level continue-on-error")
    if len(re.findall(r"(?m)^\s{8}continue-on-error: true\s*$", latest)) != 2:
        violations.append(
            "ca-pi-latest must absorb exactly its two upstream-compatibility probes at step level",
        )
    if re.search(r"(?m)^\s{8}if: always\(\)\s*$", latest) is None:
        violations.append("ca-pi-latest must always publish its advisory receipt")
    if "GITHUB_STEP_SUMMARY" not in latest:
        violations.append("ca-pi-latest must publish the advisory verdict to the job summary")
    canary_sequence = re.search(
        r'(?ms)^\s{10}npm install --global @earendil-works/pi-coding-agent@latest --ignore-scripts\s*$'
        r'.*?^\s{10}pi --version\s*$'
        r'.*?^\s{10}npm test -- test/package\.test\.ts '
        r'-t "installed Pi runtime is admitted by the production boundary"\s*$'
        r'.*?^\s{10}npm test -- test/package\.test\.ts\s*$',
        latest,
    )
    if canary_sequence is None:
        violations.append(
            "ca-pi-latest must install latest, report Pi, run installed-runtime admission, then run package tests",
        )

    aggregate = job("ci-passed")
    needs_match = re.search(r"(?ms)^    needs:\s*\n(?P<body>.*?)(?=^    [A-Za-z0-9_-]+:)", aggregate)
    needs = set()
    if needs_match is not None:
        needs = {
            line.strip()[2:].strip()
            for line in needs_match.group("body").splitlines()
            if line.strip().startswith("- ")
        }
    for dependency in ("ca-pi-checks", "ca-pi-tools", "ca-pi-latest", "version-bump-pi"):
        if dependency not in needs:
            violations.append(f"ci-passed.needs missing {dependency}")
    required_results = re.search(
        r'(?m)^\s{10}required_results="(?P<body>[^"\n]*)"\s*$',
        aggregate,
    )
    if required_results is None:
        violations.append("ci-passed must enumerate required results separately from the advisory canary")
    elif "needs.ca-pi-latest.result" in required_results.group("body"):
        violations.append("ci-passed must not promote the advisory ca-pi-latest result into required results")
    elif "needs['ca-pi-checks'].result" not in required_results.group("body"):
        # Registering a job in `needs:` alone makes the gate wait for it without
        # ever enforcing its verdict - the silent coverage drop issue #390 calls out.
        violations.append("ci-passed.required_results missing ca-pi-checks")
    if 'canary_result="${{ needs.ca-pi-latest.result }}"' not in aggregate:
        violations.append("ci-passed must report the advisory ca-pi-latest result separately")
    return violations


class PiPackageTests(unittest.TestCase):
    def test_real_sdk_footer_owner_disposal_restores_native_without_clobbering_replacement(self):
        """Real supported SDK owner/render component; no CLI, agent or model turn."""
        import stat
        node, cli = live_pi_cli()
        cli = cli.resolve(strict=True)

        def manifest_at(directory, name, version=None):
            manifest = directory / "package.json"
            info = manifest.lstat()
            self.assertTrue(stat.S_ISREG(info.st_mode) and not manifest.is_symlink())
            self.assertLessEqual(info.st_size, 64 * 1024)
            value = read_json(manifest)
            self.assertEqual(value.get("name"), name)
            if version is not None:
                self.assertEqual(value.get("version"), version)
            return value

        roots = []
        for directory in list(cli.parents)[:4]:
            manifest = directory / "package.json"
            if manifest.is_file() and read_json(manifest).get("name") == "@earendil-works/pi-coding-agent":
                roots.append(directory)
        self.assertEqual(len(roots), 1, "one installed supported SDK adjacent to the admitted launcher required")
        sdk = roots[0]
        manifest_at(sdk, "@earendil-works/pi-coding-agent", "1.5.0")
        node_modules = sdk.parent.parent
        self.assertEqual(node_modules.name, "node_modules")
        prefix = node_modules.parent
        reviewed = REPO / ".github/fixtures/pi-hosts/1.5.0"
        self.assertEqual((prefix / "package-lock.json").read_bytes(), (reviewed / "package-lock.json").read_bytes())

        def dependency(name, version):
            candidates = [sdk / "node_modules" / name, node_modules / name]
            matches = [p.resolve(strict=True) for p in candidates if (p / "package.json").is_file()]
            self.assertEqual(len(set(matches)), 1, "one reviewed SDK dependency location required")
            result = matches[0]
            self.assertTrue(result.is_relative_to(node_modules.resolve()))
            manifest_at(result, name, version)
            return result

        tui = dependency("@earendil-works/pi-tui", "1.5.0")
        jiti = dependency("jiti", "2.7.0")
        node = Path(node).resolve(strict=True)

        def installed_inventory():
            entries = []
            for directory, folders, files in os.walk(node_modules, followlinks=False):
                for name in sorted(folders + files):
                    item = Path(directory) / name
                    info = item.lstat()
                    relative = item.relative_to(node_modules).as_posix()
                    self.assertFalse(getattr(info, "st_file_attributes", 0) & 0x400,
                                     "SDK reparse entry refused")
                    if item.is_symlink():
                        # npm's POSIX .bin aliases are data, never invoked by this probe.
                        self.assertEqual(item.parent, node_modules / ".bin")
                        self.assertTrue(item.resolve(strict=True).is_relative_to(node_modules.resolve()))
                        self.assertTrue(item.resolve(strict=True).is_file())
                        entries.append({"path": relative, "kind": "bin-symlink", "target": os.readlink(item)})
                    elif stat.S_ISDIR(info.st_mode):
                        entries.append({"path": relative, "kind": "directory"})
                    else:
                        self.assertTrue(stat.S_ISREG(info.st_mode))
                        self.assertLessEqual(info.st_size, 256 * 1024 * 1024)
                        entries.append({"path": relative, "kind": "file",
                                        "sha256": hashlib.sha256(item.read_bytes()).hexdigest()})
                    self.assertLessEqual(len(entries), 32768)
            return sorted(entries, key=lambda row: row["path"])

        before = installed_inventory()
        node_hash = hashlib.sha256(node.read_bytes()).hexdigest()
        source_paths = (
            "plugins/ca-pi/tools/src/audit-sink.ts", "plugins/ca-pi/tools/src/bridge.ts",
            "plugins/ca-pi/tools/src/footer-state.ts", "plugins/ca-pi/tools/src/footer.ts",
            "plugins/ca-pi/tools/src/path-boundary.ts", "plugins/ca-pi/tools/src/redaction.ts",
            "plugins/ca-pi/tools/src/status.ts", "plugins/ca/tools/redactor.ts",
        )
        source_before = {p: hashlib.sha256((REPO / p).read_bytes()).hexdigest() for p in source_paths}
        with tempfile.TemporaryDirectory(prefix="ca-pi-footer-sdk-") as raw:
            profile = Path(raw).resolve(strict=True)
            for name in ("appdata", "localappdata", "xdg", "cache", "temp", "jiti", "agent", "work", "result"):
                (profile / name).mkdir()
            output = profile / "result"
            configuration = output / "config.json"
            config = {"repo": str(REPO), "sdk": str(sdk), "tui": str(tui), "jiti": str(jiti),
                      "profile": str(profile), "cwd": str(profile / "work"), "output": str(output)}
            configuration.write_text(json.dumps(config), encoding="utf-8")
            environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "ComSpec", "PATHEXT")
                           if key in os.environ}
            environment.update(HOME=str(profile), USERPROFILE=str(profile), APPDATA=str(profile / "appdata"),
                               LOCALAPPDATA=str(profile / "localappdata"), XDG_CONFIG_HOME=str(profile / "xdg"),
                               XDG_CACHE_HOME=str(profile / "cache"), TEMP=str(profile / "temp"),
                               TMP=str(profile / "temp"), TMPDIR=str(profile / "temp"),
                               PI_CODING_AGENT_DIR=str(profile / "agent"), JITI_CACHE_DIR=str(profile / "jiti"),
                               NO_COLOR="1", PATH=str(node.parent), CA_PI_FOOTER_CONFIG=str(configuration))
            script = output / "footer-probe.mjs"
            script.write_text(r'''import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createRequire, registerHooks, syncBuiltinESMExports} from 'node:module';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import childProcess from 'node:child_process';
import net from 'node:net';
import tls from 'node:tls';
import http from 'node:http';
import https from 'node:https';
import dns from 'node:dns';
import workerThreads from 'node:worker_threads';

const config = JSON.parse(fs.readFileSync(process.env.CA_PI_FOOTER_CONFIG, 'utf8'));
const output = config.output;
const originalRead = fs.readFileSync.bind(fs);
const originalWrite = fs.writeFileSync.bind(fs);
const digest = value => createHash('sha256').update(value).digest('hex');
const report = {format:'codearbiter.pi-footer-sdk-component/1', stage:'guards', phases:[],
  peripheralAttempts:[], modules:[], sourceReads:[], cleanup:{}, result:'RUNNING'};
const loaded = new Set();
const sourceReads = new Map();
let terminal, mode, lifecycle, deferredLifecycle, jiti, theme;
const persist = () => originalWrite(path.join(output,'sdk-observation.json'),JSON.stringify(report,null,2)+'\n');
function forbidden(operation) {
  return function () {
    report.peripheralAttempts.push(operation);
    persist();
    throw new Error('forbidden peripheral operation: '+operation);
  };
}
for (const key of ['spawn','spawnSync','exec','execSync','execFile','execFileSync','fork'])
  childProcess[key]=forbidden('child_process.'+key);
net.Socket.prototype.connect=forbidden('net.Socket.connect');
net.Server.prototype.listen=forbidden('net.Server.listen');
net.connect=forbidden('net.connect'); net.createConnection=forbidden('net.createConnection');
tls.connect=forbidden('tls.connect');
for (const [name, module] of [['http',http],['https',https]])
  for (const key of ['request','get']) module[key]=forbidden(name+'.'+key);
for (const key of ['lookup','resolve','resolve4','resolve6','reverse']) {
  dns[key]=forbidden('dns.'+key);
  if (key in dns.promises) dns.promises[key]=forbidden('dns.promises.'+key);
}
globalThis.fetch=forbidden('fetch');
globalThis.WebSocket=forbidden('WebSocket');
process.dlopen=forbidden('process.dlopen');
workerThreads.Worker=forbidden('Worker');
syncBuiltinESMExports();
function noteRead(filename, data) {
  if (typeof filename==='number') return;
  try {
    const p = filename instanceof URL ? fileURLToPath(filename) : String(filename);
    if (/\.(?:[cm]?js|ts|json)$/.test(p)) sourceReads.set(path.resolve(p),digest(data));
  } catch { /* The original file operation still determines its own outcome. */ }
}
fs.readFileSync=function(filename,...args) {
  const data=originalRead(filename,...args); noteRead(filename,data); return data;
};
const promiseRead=fs.promises.readFile.bind(fs.promises);
fs.promises.readFile=async function(filename,...args) {
  const data=await promiseRead(filename,...args); noteRead(filename,data); return data;
};
syncBuiltinESMExports();
registerHooks({
  resolve(specifier,context,next) { const result=next(specifier,context); loaded.add(result.url); return result; },
  load(url,context,next) { const result=next(url,context); loaded.add(url); return result; }
});
class ByteTerminal {
  columns=120; rows=40; kittyProtocolActive=false; started=false; stopped=false; chunks=[]; bytes=0;
  start(input,resize) { this.started=true; this.input=input; this.resize=resize; }
  stop() { this.stopped=true; this.input=undefined; this.resize=undefined; }
  async drainInput() {}
  write(value) { this.bytes+=Buffer.byteLength(value); assert(this.bytes<=262144,'terminal capture cap'); this.chunks.push(value); }
  moveBy() {} hideCursor() {} showCursor() {} clearLine() {} clearFromCursor() {} clearScreen() {}
  setTitle() {} setProgress() {} setProgramStatus() {} restoreOnExit() {}
}
function phase(name) {
  const lines=mode.footerContainer.render(120);
  const before=terminal.chunks.length;
  mode.renderer.renderNow(true);
  const frame=terminal.chunks.slice(before).join('');
  const readback={name, callbackCount:mode.footerDataProvider.branchChangeCallbacks.size,
    isNative:mode.footerContainer.children.length===1 && mode.footerContainer.children[0]===mode.footer,
    custom:mode.customFooter!==undefined, health:lifecycle?.health(), lines, frame};
  report.phases.push(readback); persist(); return readback;
}
try {
  report.stage='imports'; persist();
  const sdk=config.sdk;
  const imp=relative=>import(pathToFileURL(path.join(sdk,relative)).href);
  const {InteractiveMode}=await imp('dist/modes/interactive/interactive-mode.js');
  const {SettingsManager}=await imp('dist/core/settings-manager.js');
  const {SessionManager}=await imp('dist/core/session-manager.js');
  theme=await imp('dist/modes/interactive/theme/theme.js');
  const tui=await import(pathToFileURL(path.join(config.tui,'dist/index.js')).href);
  const {createJiti}=await import(pathToFileURL(path.join(config.jiti,'lib/jiti.mjs')).href);
  jiti=createJiti(import.meta.url,{fsCache:path.join(config.profile,'jiti'),moduleCache:true});
  const {PiFooterLifecycle}=await jiti.import(path.join(config.repo,'plugins/ca-pi/tools/src/status.ts'));
  const manager=SessionManager.inMemory(config.cwd);
  const settings=SettingsManager.inMemory({theme:'dark'});
  const session={settingsManager:settings,sessionManager:manager,state:{},autoCompactionEnabled:false,
    resourceLoader:{getThemes:()=>({themes:[]})},getContextUsage:()=>({tokens:0,contextWindow:0,percent:null})};
  const registrations={};
  const runtimeHost={session,setBeforeSessionInvalidate:fn=>{registrations.invalidate=fn;},
    setRebindSession:fn=>{registrations.rebind=fn;}};
  terminal=new ByteTerminal(); report.stage='constructor'; persist();
  mode=new InteractiveMode(runtimeHost,{terminal,tuiMode:'inline',initialThemeSetting:'dark'});
  assert(mode.renderer instanceof tui.TuiMainScreen);
  assert.equal(mode.footer.constructor.name,'FooterComponent');
  assert.equal(mode.footerDataProvider.constructor.name,'FooterDataProvider');
  mode.renderer.addChild(mode.footerContainer);
  mode.renderer.start();
  const baselineCallbacks=mode.footerDataProvider.branchChangeCallbacks.size;
  report.baselineCallbacks=baselineCallbacks;
  const metrics={visibleWidth:tui.visibleWidth,truncateToWidth:tui.truncateToWidth};
  const parent={getSessionName:()=>manager.getSessionName(),getThinkingLevel:()=> 'off'};
  const noBridge=new Proxy({}, {get:()=>forbidden('bridge')});
  lifecycle=new PiFooterLifecycle(parent,noBridge,async()=>metrics);
  const context=()=>({cwd:config.cwd,hasUI:true,mode:'tui',ui:mode.createExtensionUIContext(),
    sessionManager:manager,isProjectTrusted:()=>false});
  const a=context(), b=context(); assert.notEqual(a.ui,b.ui);
  report.stage='owned-disposal';
  const nativeLines=phase('native-before').lines;
  lifecycle.dispose(); assert.equal(mode.footerContainer.children[0],mode.footer);
  await lifecycle.start(a);
  const owned=phase('owned');
  assert.equal(owned.callbackCount,baselineCallbacks+1); assert(owned.custom); assert(!owned.isNative);
  assert(owned.lines.join('\n').includes('╭')); assert(owned.frame.includes('╭'));
  lifecycle.dispose();
  const restored=phase('owned-disposed');
  assert.equal(restored.callbackCount,baselineCallbacks); assert(restored.isNative); assert(!restored.custom);
  assert.deepEqual(restored.lines,nativeLines); assert.equal(lifecycle.currentTui(),undefined);
  assert.deepEqual(lifecycle.health(),{expected:false,initialized:false});
  lifecycle.dispose(); const repeated=phase('repeat-disposed'); assert.deepEqual(repeated.lines,nativeLines);
  assert.equal(repeated.callbackCount,baselineCallbacks);
  report.stage='foreign-replacement';
  await lifecycle.start(b);
  const foreign=new tui.Text('other extension footer',0,0);
  b.ui.setFooter(()=>foreign);
  const foreignBefore=phase('foreign-installed');
  assert.equal(mode.customFooter,foreign); assert.equal(foreignBefore.callbackCount,baselineCallbacks);
  lifecycle.dispose(); const foreignAfter=phase('foreign-preserved');
  assert.equal(mode.customFooter,foreign); assert.deepEqual(foreignAfter.lines,foreignBefore.lines);
  assert(foreignAfter.frame.includes('other extension footer'));
  report.stage='stale-generation';
  for (const [name,next] of [['same-context',a],['distinct-context',b]]) {
    await lifecycle.start(a); const old=mode.customFooter;
    await lifecycle.start(next); const current=mode.customFooter;
    assert.notEqual(old,current); old.dispose(); old.dispose();
    const retained=phase(name+'-stale-disposed');
    assert.equal(mode.customFooter,current); assert.equal(retained.callbackCount,baselineCallbacks+1);
    assert.deepEqual(lifecycle.health(),{expected:true,initialized:true});
    lifecycle.dispose(); current.dispose();
    const final=phase(name+'-current-disposed');
    assert(final.isNative); assert.equal(final.callbackCount,baselineCallbacks); assert.deepEqual(final.lines,nativeLines);
  }
  report.stage='deferred-metrics';
  let resolveMetrics;
  deferredLifecycle=new PiFooterLifecycle(parent,noBridge,()=>new Promise(resolve=>{resolveMetrics=resolve;}));
  const pending=deferredLifecycle.start(context());
  deferredLifecycle.dispose(); resolveMetrics(metrics); await pending;
  const deferred=phase('deferred-disposed');
  assert(deferred.isNative); assert.equal(deferred.callbackCount,baselineCallbacks);
  assert.deepEqual(deferred.lines,nativeLines);
  assert.deepEqual(deferredLifecycle.health(),{expected:false,initialized:false});
  assert.equal(report.peripheralAttempts.length,0,'caught forbidden peripheral attempt');
  report.result='PASSED';
} catch (error) {
  report.result='FAILED'; report.error={name:error?.name,message:String(error?.message),stack:String(error?.stack)};
  process.exitCode=1;
} finally {
  try {
    deferredLifecycle?.dispose(); lifecycle?.dispose();
    if (mode) {
      mode.setExtensionFooter(undefined);
      report.cleanup.callbackCountBeforeProviderDispose=mode.footerDataProvider.branchChangeCallbacks.size;
      mode.footerDataProvider.dispose(); mode.themeController.dispose(); theme?.stopThemeWatcher();
      mode.renderer.stop();
      report.cleanup.providerDisposed=mode.footerDataProvider.disposed;
      report.cleanup.remainingCallbacks=mode.footerDataProvider.branchChangeCallbacks.size;
      report.cleanup.terminalStopped=terminal.stopped;
      report.cleanup.rendererStopped=mode.renderer.stopped;
    }
    if(terminal) originalWrite(path.join(output,'terminal-capture.json'),JSON.stringify({encoding:'base64',
      bytes:terminal.bytes,data:Buffer.from(terminal.chunks.join('')).toString('base64')})+'\n');
  } catch(error) { report.cleanup.error={name:error?.name,message:String(error?.message)}; report.result='FAILED'; process.exitCode=1; }
  const require=createRequire(import.meta.url);
  for(const key of Object.keys(require.cache)) loaded.add(pathToFileURL(key).href);
  if(jiti) for(const key of Object.keys(jiti.cache)) loaded.add(pathToFileURL(key).href);
  report.modules=[...loaded].sort().map(url=>{
    if(!url.startsWith('file:')) return {url};
    const filename=fileURLToPath(url);
    try{return {url,sha256:digest(originalRead(filename))};}catch{return {url,unreadable:true};}
  });
  report.sourceReads=[...sourceReads].sort(([a],[b])=>a.localeCompare(b)).map(([p,sha256])=>({path:p,sha256}));
  if(report.peripheralAttempts.length) {report.result='FAILED';process.exitCode=1;}
  report.stageAtCompletion=report.stage; persist();
}
''', encoding="utf-8", newline="\n")
            started = time.monotonic()
            done = subprocess.run([str(node), str(script)], cwd=profile / "work", env=environment,
                                  capture_output=True, timeout=30, check=False)
            # Preserve original outcomes before assertions, even if the SDK refused setup.
            (output / "node.stdout.bin").write_bytes(done.stdout)
            (output / "node.stderr.bin").write_bytes(done.stderr)
            (output / "outcome.json").write_text(json.dumps({"returncode": done.returncode,
                "elapsed_seconds": time.monotonic() - started, "argv": [str(node), str(script)]}), encoding="utf-8")
            self.assertEqual(installed_inventory(), before)
            self.assertEqual(hashlib.sha256(node.read_bytes()).hexdigest(), node_hash)
            self.assertEqual({p: hashlib.sha256((REPO / p).read_bytes()).hexdigest() for p in source_paths}, source_before)
            self.assertEqual(done.returncode, 0, "real SDK footer component probe failed")
            observed = read_json(output / "sdk-observation.json")
            self.assertEqual(observed["result"], "PASSED")
            self.assertEqual(observed["peripheralAttempts"], [])
            self.assertEqual(len(observed["phases"]), 11)
            self.assertTrue(observed["cleanup"]["terminalStopped"])
            self.assertTrue(observed["cleanup"]["rendererStopped"])
            self.assertTrue(observed["cleanup"]["providerDisposed"])
            self.assertEqual(observed["cleanup"]["remainingCallbacks"], 0)

    def test_rpc_native_shutdown_stack_projection_is_closed_and_bounded(self):
        import _windows_dbgeng as sdk
        self.assertEqual(sdk.project_frame(b"NODE", 0x1010, 0x1000, True),
                         {"module": "node", "returnOffset": 16})
        for name, address, base, unique in (
            (b"PrivateFixtureValue!private/path", 0x1010, 0x1000, True),
            (b"node", 0x1010, 0x1000, False), (b"node", 1, 2, True),
            (b"node", 2**64, 0, True), (b"node\xff", 0x1010, 0x1000, True)):
            self.assertEqual(sdk.project_frame(name, address, base, unique),
                             {"module": "Other", "returnOffset": None})
        # Exercise the actual metadata lookup, including its overlap refusal.
        for ambiguous in (False, True):
            engine = object.__new__(sdk.Engine)
            seen = []
            def query(interface, index, argtypes, *args):
                seen.append(index)
                if index == 15:
                    if args[1] and not ambiguous:
                        return 0x80004005
                    sdk.C.cast(args[2], sdk.C.POINTER(sdk.U32)).contents.value = args[1]
                    sdk.C.cast(args[3], sdk.C.POINTER(sdk.U64)).contents.value = 0x1000
                    return 0
                self.assertEqual(index, 16)
                args[5].value = b"node"
                sdk.C.cast(args[7], sdk.C.POINTER(sdk.U32)).contents.value = 5
                return 0
            engine.call = query
            self.assertEqual(engine.frame(0x1010),
                {"module": "Other", "returnOffset": None} if ambiguous else
                {"module": "node", "returnOffset": 16})
            self.assertEqual(seen.count(16), int(not ambiguous))
        good = {"schemaVersion": 1, "status": "captured", "threads": [{"frames": [
            {"module": "node", "returnOffset": 16}]}], "truncated": False,
            "pid": 33, "created": 44, "bound": True, "attached": True,
            "policy": sdk.POLICY, "detached": True, "hresult": 0}
        self.assertEqual(sdk.decode_result(json.dumps(good).encode(), 33, 44), good)
        for key, value in (("pid", 99), ("created", 55), ("policy", 0),
                           ("policy", sdk.POLICY | sdk.ALLOW_NETWORK),
                           ("detached", False), ("bound", False), ("hresult", 1),
                           ("threads", [{"frames": [{"module": "PrivateFixtureValue", "returnOffset": 1}]}]),
                           ("threads", [{"frames": [{"module": "Other", "returnOffset": None}]}]),
                           ("threads", [{"frames": [{"module": "node", "returnOffset": 1}] * 25}]),
                           ("threads", [{"frames": []}] * 17)):
            with self.subTest(key=key, value_kind=type(value).__name__):
                changed = {**good, key: value}
                self.assertIsNone(sdk.decode_result(json.dumps(changed).encode(), 33, 44))
        self.assertIsNone(sdk.decode_result(b"x" * (sdk.MAX_JSON + 1), 33, 44))
        self.assertIsNone(sdk.decode_result(b"PrivateFixtureValue", 33, 44))

    def test_rpc_native_shutdown_identity_refuses_foreign_or_unknown_handles(self):
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory).resolve() / "node.exe"
            image.write_bytes(b"owned image")
            for failure in (None, "pid", "created", "image", "query", "wait", "late",
                            "rundown", "rundown-pid", "rundown-created"):
                with self.subTest(failure=failure):
                    class Kernel:
                        closed = []
                        def open(self, pid):
                            self.closed = []
                            return 22
                        def close(self, handle):
                            self.closed.append(handle)
                        def snapshot(self, handle):
                            if failure == "query":
                                raise OSError("PrivateFixtureValue")
                            return {"pid": 77 if failure in ("pid", "rundown-pid") and handle == 22 else 33,
                                    "created": 88 if failure in ("created", "rundown-created") and handle == 22 else 44,
                                    "image": "" if failure and failure.startswith("rundown") and handle == 22 else str(image.parent / "foreign.exe") if failure == "image" else str(image),
                                    "state": "failed" if failure == "wait" else "signaled" if failure == "late" or (failure and failure.startswith("rundown") and handle == 22) else "running",
                                    "exitCode": 0 if failure == "late" or (failure and failure.startswith("rundown") and handle == 22) else None}
                    kernel = Kernel()
                    debugger = mock.Mock(return_value={"status": "unavailable", "threads": [], "truncated": False})
                    process = SimpleNamespace(pid=33, _handle=11)
                    result = native.capture(process, image, _kernel=kernel, _debugger=debugger)
                    self.assertEqual(vars(process), {"pid": 33, "_handle": 11})
                    self.assertEqual(debugger.call_count, int(failure is None))
                    self.assertNotIn(11, kernel.closed)
                    if 22 in kernel.closed:
                        self.assertEqual(kernel.closed, [22])
                    self.assertEqual(result["outcome"], "original-failure")
                    self.assertNotIn("PrivateFixtureValue", json.dumps(result))
                    if failure is None:
                        self.assertEqual(result["identity"], "matched")
                    elif failure == "late":
                        self.assertEqual(result["before"]["state"], "signaled")
                    elif failure == "rundown":
                        self.assertEqual(result["identity"], "owned-exited")
                        self.assertEqual(result["before"], {"state": "running", "exitCode": None})
                        self.assertEqual(result["after"], {"state": "signaled", "exitCode": 0})
                        self.assertEqual(result["processId"], 33)
                        self.assertEqual(result["creationTime"], 44)
                        self.assertEqual(kernel.closed, [22])
                    elif failure in ("rundown-pid", "rundown-created"):
                        self.assertEqual(result["identity"], "mismatch")
                        self.assertEqual(result["after"], {"state": "unknown", "exitCode": None})
                    else:
                        self.assertNotEqual(result["identity"], "matched")

    def _native_progress_fixture(self, root, *, failure=None, expired_after=False):
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        image = root.resolve(strict=True) / "node.exe"
        image.write_bytes(b"owned process image")
        now = [0.0]
        class Kernel:
            reads = []
            closed = []
            snapshots = 0
            def open(self, pid): return 22
            def close(self, handle): self.closed.append(handle)
            def snapshot(self, handle):
                self.snapshots += 1
                return {"pid": 99 if failure == "identity" else 33, "created": 44,
                        "image": str(image), "state": "running", "exitCode": None,
                        "cpuTimes": {"kernelTime100ns": self.snapshots * 100,
                                     "userTime100ns": self.snapshots * 200}}
            def process_counters(self, handle, deadline):
                self.reads.append((handle, deadline))
                if failure == "query": raise OSError("PRIVATE_COUNTER_ERROR")
                return {"readOperations": len(self.reads), "writeOperations": len(self.reads) * 2,
                        "otherOperations": 3, "readBytes": 4, "writeBytes": 5, "otherBytes": 6,
                        "handleCount": 7, "PRIVATE_EXTRA": "PRIVATE_COUNTER_VALUE"}
        kernel = Kernel()
        if failure == "missing": kernel.process_counters = None
        def debug(*args):
            if expired_after: now[0] = 5.1
            return {"status": "unavailable", "threads": [], "truncated": False}
        debugger = mock.Mock(side_effect=debug)
        process = SimpleNamespace(pid=33, _handle=11)
        with mock.patch.object(native.time, "monotonic", side_effect=lambda: now[0]):
            result = native.capture(process, image, _kernel=kernel, _debugger=debugger)
        return result, kernel, debugger, process

    def test_rpc_native_shutdown_progress_is_identity_bound_and_preserves_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            result, kernel, debugger, process = self._native_progress_fixture(Path(directory))
        self.assertIn("processProgress", result, "failed native wait must retain passive process progress")
        before, after = result["processProgress"]["before"], result["processProgress"]["after"]
        self.assertEqual((before["kernelTime100ns"], after["kernelTime100ns"]), (200, 300))
        self.assertEqual((before["userTime100ns"], after["userTime100ns"]), (400, 600))
        self.assertEqual((before["writeOperations"], after["writeOperations"]), (2, 4))
        self.assertEqual(before["handleCount"], 7)
        self.assertEqual(kernel.reads, [(11, 5.0), (11, 5.0)])
        self.assertEqual(kernel.closed, [22])
        self.assertEqual(vars(process), {"pid": 33, "_handle": 11})
        self.assertEqual(debugger.call_count, 1)
        self.assertEqual(result["identity"], "matched")
        self.assertEqual(result["outcome"], "original-failure")
        self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_rpc_native_shutdown_progress_is_optional_and_never_queries_foreign_process(self):
        for failure in ("query", "missing", "identity"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                result, kernel, debugger, _ = self._native_progress_fixture(Path(directory), failure=failure)
                if failure == "identity":
                    self.assertEqual(result["processProgress"], {"before": None, "after": None})
                    self.assertEqual(kernel.reads, [])
                    self.assertEqual(debugger.call_count, 0)
                else:
                    self.assertEqual(result["identity"], "matched")
                    self.assertEqual(result["processProgress"]["before"]["kernelTime100ns"], 200)
                    self.assertIsNone(result["processProgress"]["before"]["writeBytes"])
                    self.assertEqual(debugger.call_count, 1)
                self.assertEqual(result["outcome"], "original-failure")
                self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_rpc_native_shutdown_progress_uses_only_remaining_original_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            result, kernel, debugger, _ = self._native_progress_fixture(Path(directory), expired_after=True)
        self.assertEqual(kernel.reads, [(11, 5.0)])
        self.assertEqual(result["processProgress"]["after"]["kernelTime100ns"], 300)
        self.assertIsNone(result["processProgress"]["after"]["writeOperations"])
        self.assertEqual(result["elapsedMs"], 5100)
        self.assertEqual(result["outcome"], "original-failure")
        self.assertEqual(debugger.call_args.args[-1], 5.0)

    def test_rpc_native_shutdown_progress_projects_only_closed_numeric_values(self):
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        values = {"readOperations": True, "writeOperations": -1, "otherOperations": 2**64,
                  "readBytes": "PRIVATE_COUNTER_VALUE", "writeBytes": 2**64 - 1,
                  "otherBytes": 0, "handleCount": 2**32}
        kernel = SimpleNamespace(process_counters=lambda handle, deadline: values)
        snapshot = {"cpuTimes": {"kernelTime100ns": True, "userTime100ns": 2**64}}
        with mock.patch.object(native.time, "monotonic", return_value=0):
            projected = native._process_progress(kernel, 11, snapshot, 5.0)
        self.assertEqual(projected, {"kernelTime100ns": None, "userTime100ns": None,
            "readOperations": None, "writeOperations": None, "otherOperations": None,
            "readBytes": None, "writeBytes": 2**64 - 1, "otherBytes": 0, "handleCount": None})
        self.assertNotIn("PRIVATE_", json.dumps(projected))

    def test_rpc_native_shutdown_progress_typed_queries_are_optional_and_budgeted(self):
        import ctypes
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        for mode in ("ok", "false", "raise", "missing", "spent", "spent-after-io"):
            with self.subTest(mode=mode):
                now = [6.0 if mode == "spent" else 0.0]
                seen = []
                class Query:
                    def __init__(self, kind): self.kind = kind
                    def __call__(self, handle, destination):
                        self_test.assertEqual(handle, 11)
                        seen.append(self.kind)
                        if mode == "raise": raise OSError("PRIVATE_COUNTER_CALL")
                        if mode == "false": return False
                        if self.kind == "io":
                            value = ctypes.cast(destination, ctypes.POINTER(native._IoCounters)).contents
                            for index, (field, _) in enumerate(value._fields_, 1): setattr(value, field, index)
                            if mode == "spent-after-io": now[0] = 6.0
                        else:
                            ctypes.cast(destination, ctypes.POINTER(native.wintypes.DWORD)).contents.value = 17
                        return True
                self_test = self
                kernel = object.__new__(native.WindowsKernel)
                kernel.api = (SimpleNamespace() if mode == "missing" else
                              SimpleNamespace(GetProcessIoCounters=Query("io"), GetProcessHandleCount=Query("handles")))
                with mock.patch.object(native.time, "monotonic", side_effect=lambda: now[0]):
                    result = kernel.process_counters(11, 5.0)
                if mode in ("ok", "spent-after-io"):
                    self.assertEqual([result[field] for field in ("readOperations", "writeOperations", "otherOperations",
                                     "readBytes", "writeBytes", "otherBytes")], [1, 2, 3, 4, 5, 6])
                    self.assertEqual(result.get("handleCount"), 17 if mode == "ok" else None)
                else: self.assertEqual(result, {})
                self.assertEqual(seen, [] if mode in ("missing", "spent") else ["io"] if mode == "spent-after-io" else ["io", "handles"])
                self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_rpc_native_shutdown_transport_has_one_deadline_and_aggregate_cap(self):
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        for scenario in ("complete", "cap", "deadline", "pipe_failure"):
            with self.subTest(scenario=scenario):
                now = [0.0]
                chunks = [b"closed"] if scenario == "complete" else [b"x" * (native.MAX_OUTPUT + 1)]
                class Process:
                    returncode = 0
                    killed = False
                    stdout = io.BytesIO()
                    def poll(self):
                        return 0 if scenario == "complete" and not chunks else None
                    def kill(self):
                        self.killed = True
                    def wait(self, timeout):
                        return 0
                process = Process()
                def available(stream):
                    if scenario == "pipe_failure":
                        raise OSError("PrivateFixtureValue")
                    return len(chunks[0]) if chunks and scenario != "deadline" else 0
                def read(stream, count):
                    first = chunks[0][:count]
                    chunks[0] = chunks[0][count:]
                    if not chunks[0]:
                        chunks.pop(0)
                    return first
                def sleep(seconds):
                    now[0] += seconds
                result = native._collect(process, available, deadline=0.05,
                                         _read=read, _clock=lambda: now[0], _sleep=sleep)
                expected = {"complete": "captured", "cap": "output_limit", "deadline": "deadline",
                            "pipe_failure": "transport_failed"}[scenario]
                self.assertEqual(result[0], expected)
                self.assertLessEqual(len(result[1]), native.MAX_OUTPUT)
                self.assertLessEqual(now[0], 0.051)
                self.assertEqual(process.killed, scenario != "complete")
                self.assertNotIn(b"PrivateFixtureValue", result[1])

    def test_rpc_native_shutdown_fixed_debugger_profile_and_private_sidecar(self):
        import _windows_rpc_timeout as native
        import _windows_dbgeng as sdk
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with mock.patch.dict(os.environ, {"PRIVATE_TOKEN": "PrivateFixtureValue", "_NT_SYMBOL_PATH": "https://private", "INIT": "private"}):
                env = native._worker_environment(root)
            self.assertNotIn("PrivateFixtureValue", json.dumps(env))
            self.assertNotIn("_NT_SYMBOL_PATH", env)
            self.assertNotIn("INIT", env)
            for key in ("HOME", "USERPROFILE", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA"):
                self.assertTrue(Path(env[key]).is_relative_to(root))
            request = {"handle": 77, "pid": 33, "created": 44, "image": str(root / "node.exe"),
                       "sdk": str(root), "hashes": {name: "a" * 64 for name in
                           ("cdb.exe", "dbgeng.dll", "dbghelp.dll")}, "deadline": time.monotonic() + 5}
            class Kernel:
                def snapshot(self, handle):
                    return {"pid": 33, "created": 44, "state": "running", "image": request["image"]}
                def close(self, handle):
                    self.closed = handle
            kernel = Kernel()
            fake_native = SimpleNamespace(WindowsKernel=lambda: kernel, _regular=lambda path, **kw: path,
                                          _digest=lambda path, deadline: "a" * 64)
            class Backend:
                closed = True
                seen = []
                def __init__(self, path):
                    self.seen = []
                check = staticmethod(sdk.Engine.check)
                def policy(self):
                    return sdk.POLICY
                def call(self, name, index, args, *values):
                    self.seen.append((name, index))
                    return 0
                def threads(self, deadline):
                    return [{"frames": [{"module": "node", "returnOffset": 16}]}], False
                def close(self):
                    return self.closed
            for cleanup in (True, False):
                with self.subTest(cleanup=cleanup):
                    Backend.closed = cleanup
                    actual = sdk.run(request, fake_native, engine_factory=Backend)
                    self.assertEqual(actual["status"], "captured" if cleanup else "cleanup_unknown")
                    self.assertEqual(actual["detached"], cleanup)
                    self.assertEqual(kernel.closed, 77)
                    self.assertNotIn("PrivateFixtureValue", json.dumps(actual))
                    if not cleanup:
                        self.assertEqual(actual["threads"], [])
            # A Detach exception must not skip releasing any queried interface.
            closing = object.__new__(sdk.Engine)
            closing.interfaces = {"client": None, "control": None, "systems": None, "symbols": None}
            released = []
            def release_after_detach_failure(name, index, args, *values, **kwargs):
                if index == 25:
                    raise OSError("PrivateFixtureValue")
                self.assertEqual(index, 2)
                released.append(name)
                return 0
            closing.call = release_after_detach_failure
            self.assertFalse(closing.close())
            self.assertEqual(released, ["symbols", "systems", "control", "client"])
            self.assertEqual(closing.interfaces, {})
            Backend.closed = True
            bad_policy = Backend(root)
            bad_policy.policy = lambda: sdk.ALLOW_NETWORK
            actual = sdk.run(request, fake_native, engine_factory=lambda path: bad_policy)
            self.assertEqual(actual["status"], "engine_failed")
            self.assertNotIn(("client", 12), bad_policy.seen, "reject policy before attaching")
            kernel.snapshot = lambda handle: {"pid": 99, "created": 44, "state": "running", "image": request["image"]}
            factory = mock.Mock(side_effect=AssertionError("must not create an engine"))
            actual = sdk.run(request, fake_native, engine_factory=factory)
            self.assertEqual(actual["status"], "identity_refused")
            factory.assert_not_called()
            report = {"schemaVersion": 1, "outcome": "original-failure", "identity": "unknown"}
            with mock.patch.object(native, "capture", return_value=report):
                first = native.retain_failure(None, Path("node"), root)
                second = native.retain_failure(None, Path("node"), root)
            self.assertNotEqual(first, second)
            self.assertTrue(first.startswith("rpc-native-exit-"))
            self.assertEqual(json.loads((root / first).read_text()), report)
            self.assertLessEqual((root / first).stat().st_size, native.MAX_JSON)
            with mock.patch.object(native, "capture", side_effect=ValueError("PrivateFixtureValue")):
                self.assertIsNone(native.retain_failure(None, Path("node"), root))

    def test_rpc_native_shutdown_failure_hook_preserves_original_then_cleanup(self):
        import _windows_rpc_timeout as native
        current = sys.modules[__name__]
        for observer_fails in (False, True):
            with self.subTest(observer_fails=observer_fails), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                cwd, retained = root / "cwd", root / "retained"
                cwd.mkdir()
                order = []
                original_run, original_cleanup = subprocess.run, terminate_process_tree
                child = ("import sys,json; sys.stdin.readline(); "
                         "print(json.dumps({'id':'commands','success':True}),flush=True); sys.stdin.read()")
                def install(args, **kwargs):
                    if len(args) > 2 and args[2] == "install":
                        return subprocess.CompletedProcess(args, 0, "", "")
                    return original_run(args, **kwargs)
                original_retain = retain_rpc_shutdown_failure
                def phase_receipt(*args, **kwargs):
                    value = original_retain(*args, **kwargs)
                    self.assertIsNotNone(value)
                    order.append("original-retained")
                    return value
                def observe(process, node, destination):
                    self.assertEqual(order, ["original-retained"])
                    self.assertTrue(list(retained.glob("rpc-shutdown-*.json")))
                    order.append("native-observed")
                    if observer_fails:
                        raise ValueError("PrivateFixtureValue")
                    return None
                def cleanup(process):
                    order.append("cleanup")
                    return original_cleanup(process)
                with mock.patch.dict(os.environ, {"CA_PI_RPC_DIAGNOSTICS_DIR": str(retained)}), \
                     mock.patch.object(current, "live_pi_cli", return_value=(sys.executable, root / "unused-cli")), \
                     mock.patch.object(current, "read_json", return_value={"packages": ["fixture"]}), \
                     mock.patch.object(subprocess, "run", side_effect=install), \
                     mock.patch.object(current, "wait_for_rpc_shutdown", side_effect=subprocess.TimeoutExpired("owned", 30)), \
                     mock.patch.object(current, "retain_rpc_shutdown_failure", side_effect=phase_receipt), \
                     mock.patch.object(native, "retain_failure", side_effect=observe), \
                     mock.patch.object(current, "terminate_process_tree", side_effect=cleanup):
                    with self.assertRaisesRegex(AssertionError, "did not exit within 30 seconds") as raised:
                        run_rpc_commands(cwd, root / "agent", root / "home",
                                         _rpc_command=[sys.executable, "-c", child])
                self.assertIsInstance(raised.exception.__cause__, subprocess.TimeoutExpired)
                self.assertEqual(order, ["original-retained", "native-observed", "cleanup"])
                self.assertNotIn("PrivateFixtureValue", str(raised.exception))

    @unittest.skipUnless(os.name == "nt", "Windows owned process HANDLE control")
    def test_rpc_native_shutdown_real_owned_node_handles_and_late_exit(self):
        import _windows_rpc_timeout as native
        node = os.environ.get("CA_PI_DIAGNOSTIC_NODE") or shutil.which("node")
        self.assertIsNotNone(node, "existing approved Node must be available")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
            env.update(HOME=str(root), USERPROFILE=str(root), TEMP=str(root), TMP=str(root))
            process = subprocess.Popen([node, "-e", "setInterval(()=>{},1000)"], cwd=root, env=env,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            original_handle = int(process._handle)
            debugger = mock.Mock(return_value={"status": "unavailable", "threads": [], "truncated": False})
            try:
                alive = native.capture(process, Path(node), _debugger=debugger)
                self.assertEqual(alive["identity"], "matched")
                self.assertEqual(alive["before"]["state"], "running")
                self.assertEqual(debugger.call_count, 1)
                self.assertIsNone(process.poll())
                self.assertEqual(int(process._handle), original_handle)
                # Physical capability is observed, never inferred from the runner label.
                try:
                    available_profile, _, _ = native._tool_profile(time.monotonic() + native.SECONDS)
                except (OSError, ValueError):
                    available_profile = None
                if available_profile is None:
                    unavailable = native.capture(process, Path(node))
                    self.assertEqual(unavailable["debugger"]["status"], "unavailable")
                    self.assertEqual(unavailable["after"]["state"], "running")
                else:
                    # Existing closed SDK or inbox profile only: no installation.
                    # A present tool must demonstrate recognized frames here;
                    # unknown status cannot masquerade as capability proof.
                    actual = native.capture(process, Path(node))
                    self.assertEqual(actual["identity"], "matched")
                    self.assertEqual(actual["before"]["state"], "running")
                    self.assertEqual(actual["after"]["state"], "running")
                    report = actual["debugger"]
                    # Keep the existing closed projections from this same capture.
                    # The job log must distinguish worker transport from SDK cleanup.
                    self.assertEqual(report["status"], "captured", json.dumps({
                        "diagnostic": report.get("diagnostic"),
                        "worker": report.get("worker"),
                    }, sort_keys=True))
                    self.assertEqual(report["profile"], available_profile)
                    self.assertEqual(set(report["toolHashes"]), set(native.TOOL_FILES[available_profile]))
                    for digest in report["toolHashes"].values():
                        self.assertRegex(digest, r"\A[0-9a-f]{64}\Z")
                    self.assertLessEqual(len(json.dumps(actual).encode("utf-8")), native.MAX_JSON)
                    self.assertLessEqual(len(report["threads"]), 16)
                    for thread in report["threads"]:
                        self.assertEqual(set(thread), {"frames"})
                        self.assertLessEqual(len(thread["frames"]), 24)
                        for frame in thread["frames"]:
                            self.assertEqual(set(frame), {"module", "returnOffset", "instructionModule", "instructionOffset"})
                            self.assertIn(frame["module"], native.MODULES | {"Other"})
                            self.assertTrue(frame["returnOffset"] is None or
                                            type(frame["returnOffset"]) is int and 0 <= frame["returnOffset"] < 2**64)
                            self.assertIn(frame["instructionModule"], native.MODULES | {"Other"})
                            self.assertTrue(frame["instructionOffset"] is None or
                                            type(frame["instructionOffset"]) is int and 0 <= frame["instructionOffset"] < 2**64)
                    if report["status"] == "captured":
                        self.assertTrue(any(row["frames"] for row in report["threads"]))
                        self.assertTrue(any(frame["instructionModule"] != "Other"
                            for row in report["threads"] for frame in row["frames"]))
                    # Closed status only; never raw debugger text/symbols/paths.
                    print("owned-node-native-debugger-status=" + report["status"])
                    self.assertIsNone(process.poll(), "debugger quit must preserve the owned Node")
                    self.assertEqual(int(process._handle), original_handle)
                foreign = native.capture(process, Path(sys.executable), _debugger=debugger)
                self.assertNotEqual(foreign["identity"], "matched")
                self.assertEqual(debugger.call_count, 1)
                process.terminate()
                process.wait(timeout=3)
                late = native.capture(process, Path(node), _debugger=debugger)
                self.assertEqual(late["before"]["state"], "signaled")
                self.assertEqual(debugger.call_count, 1)
                self.assertEqual(int(process._handle), original_handle)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=3)

    def test_local_prefix_pi_cli_resolves_declared_bin_above_dot_bin(self) -> None:
        # Pi 1.5.0 ships both dist/cli.js and dist/bundle/cli.js; only the declared bin is the CLI.
        for label, declared, expected in (
            ("string-bin", "dist/bundle/cli.js", "dist/bundle/cli.js"),
            ("map-bin", {"pi": "dist/bundle/cli.js"}, "dist/bundle/cli.js"),
            ("escaping-bin", {"pi": "../outside.js"}, None),
            ("missing-bin", {"pi-ai": "dist/cli.js"}, None),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                prefix = Path(directory) / "prefix"
                executable = prefix / "node_modules" / ".bin" / "pi.cmd"
                package = prefix / "node_modules" / "@earendil-works" / "pi-coding-agent"
                executable.parent.mkdir(parents=True)
                (package / "dist" / "bundle").mkdir(parents=True)
                executable.write_text("@echo off\n", encoding="utf-8")
                for relative in ("dist/cli.js", "dist/bundle/cli.js", "../outside.js"):
                    (package / relative).write_text("// fixture\n", encoding="utf-8")
                (package / "package.json").write_text(json.dumps(
                    {"name": "@earendil-works/pi-coding-agent", "bin": declared}), encoding="utf-8")

                if expected is None:
                    with self.assertRaises(AssertionError):
                        _resolve_pi_cli_path(executable)
                else:
                    self.assertEqual(_resolve_pi_cli_path(executable), (package / expected).resolve())

    def test_parent_embeds_exact_generated_hardened_child_fingerprint(self):
        child = (PLUGIN / "extensions" / "codearbiter-child.js").read_bytes()
        expected = hashlib.sha256(child).hexdigest()
        parent = (PLUGIN / "extensions" / "codearbiter.js").read_text(encoding="utf-8")
        self.assertIn(expected, parent)
        self.assertEqual(len(re.findall(re.escape(expected), parent)), 1)

    def test_root_manifest_is_publishable_dependency_free_pi_metadata(self):
        # ADR-0029 / spec npm-publish-ca-pi AC-1: the root manifest is the npm
        # publish unit — scoped name, no private flag, provenance-ready fields.
        data = read_json(REPO / "package.json")
        self.assertEqual(data["name"], "@arbiterforge/ca-pi")
        self.assertEqual(data["version"], read_json(PLUGIN / "package.json")["version"])
        self.assertNotIn("private", data)
        self.assertEqual(
            data["publishConfig"], {"access": "public", "provenance": True},
        )
        self.assertEqual(
            data["repository"],
            {"type": "git", "url": "git+https://github.com/arbiterForge/codeArbiter.git"},
        )
        self.assertEqual(
            data["files"],
            [
                "plugins/ca-pi/*.md",
                "plugins/ca-pi/LICENSE",
                "plugins/ca-pi/package.json",
                "plugins/ca-pi/agents/",
                "plugins/ca-pi/extensions/",
                "plugins/ca-pi/generated/",
                "plugins/ca-pi/helpers/",
                "plugins/ca-pi/hooks/",
                "plugins/ca-pi/includes/",
                "plugins/ca-pi/routines/",
                "plugins/ca-pi/skills/",
            ],
        )
        self.assertEqual(data["engines"], {"node": ">=22.19.0"})
        self.assertEqual(
            data["pi"]["extensions"],
            ["./plugins/ca-pi/extensions/codearbiter.js"],
        )
        self.assertEqual(data["pi"]["skills"], ["./plugins/ca-pi/skills"])
        for forbidden in ("dependencies", "devDependencies", "workspaces", "scripts"):
            self.assertNotIn(forbidden, data)

    def test_nested_manifest_is_the_single_version_source(self):
        data = read_json(PLUGIN / "package.json")
        self.assertEqual(data["name"], "@arbiterforge/ca-pi")
        changelog = (PLUGIN / "CHANGELOG.md").read_text(encoding="utf-8")
        newest = re.search(r"^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$", changelog, re.M)
        self.assertIsNotNone(newest, "CHANGELOG.md has no dated release section")
        self.assertEqual(data["version"], newest.group(1))
        self.assertIs(data["private"], True)
        self.assertEqual(data["engines"], {"node": ">=22.19.0"})
        self.assertEqual(data["pi"]["extensions"], ["./extensions/codearbiter.js"])
        self.assertEqual(data["pi"]["skills"], ["./skills"])
        for forbidden in ("dependencies", "devDependencies", "workspaces", "scripts"):
            self.assertNotIn(forbidden, data)
        changelog = (PLUGIN / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [0.1.0] - 2026-07-14", changelog)

    def test_pi_runtime_is_not_present_beneath_plugin(self):
        self.assertFalse(list(PLUGIN.rglob("pi-coding-agent")))
        self.assertFalse(list(PLUGIN.rglob("pi-agent-core")))

    def test_pi_tools_node_modules_is_repository_ignored(self):
        relative = "plugins/ca-pi/tools/node_modules"
        result = subprocess.run(
            ["git", "check-ignore", "-q", relative],
            cwd=REPO,
            check=False,
        )
        self.assertEqual(result.returncode, 0, f"{relative} must be ignored")

    def test_build_workspace_is_isolated_and_exactly_pinned(self):
        data = read_json(TOOLS / "package.json")
        self.assertEqual(data["name"], "ca-pi-tools")
        self.assertEqual(data["version"], "0.1.0")
        self.assertEqual(data["engines"], {"node": ">=22.19.0"})
        self.assertEqual(
            data["scripts"],
            {
                "build": "node ./build.mjs",
                "typecheck": "tsc --noEmit",
                "test": "vitest run",
                # Issue #507: tdd Phase 5 and refactor Phase 2/6 read a coverage
                # command from tech-stack.md and forbid guessing one. Before this
                # script existed there was nothing to read, so both gates passed
                # on a gap. Scope and reporters live in vitest.config.ts so the
                # invocation stays argument-free and identical on every platform.
                "coverage": "vitest run --coverage",
            },
        )
        self.assertEqual(
            data["devDependencies"],
            {
                "@types/node": "25.9.4",
                # Peer-pinned to vitest EXACTLY by upstream; the two must move
                # together or `npm ci` ERESOLVEs.
                "@vitest/coverage-v8": "4.1.12",
                "esbuild": "0.28.1",
                "typescript": "5.9.3",
                "vitest": "4.1.12",
            },
        )
        self.assertNotIn("dependencies", data)

    def test_generated_root_manifest_matches_renderer_bytes(self):
        module = load_build_host_packages()
        host = module.host_descriptor("pi", str(REPO))
        expected = module.render_package(host, read_json(PLUGIN / "package.json")["version"])
        self.assertIsInstance(expected, bytes)
        self.assertEqual((REPO / "package.json").read_bytes(), expected)
        self.assertTrue(expected.endswith(b"\n"))
        self.assertNotIn(b"\r\n", expected)

    def test_generated_root_manifest_is_forced_to_lf_on_every_checkout(self):
        attributes = subprocess.run(
            ["git", "check-attr", "text", "eol", "--", "package.json"],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
        self.assertIn("package.json: text: set", attributes)
        self.assertIn("package.json: eol: lf", attributes)

    def test_host_package_write_is_idempotent_in_an_isolated_target(self):
        module = load_build_host_packages()
        with tempfile.TemporaryDirectory(prefix="ca-pi-package-idempotency-") as raw:
            target = Path(raw) / "package.json"
            target.write_bytes(module.expected_package())
            first = target.read_bytes()
            target.write_bytes(module.expected_package())
            self.assertEqual(target.read_bytes(), first)

    def test_release_guard_requires_strict_semver_advance_and_exact_metadata(self):
        module = load_build_host_packages()
        validate = getattr(module, "validate_pi_release_advance", None)
        self.assertTrue(callable(validate), "release guard validator must be reusable and unit tested")
        valid = dict(
            current_version="0.2.0",
            base_version="0.1.0",
            root_version="0.2.0",
            changelog="# Changelog\n\n## [0.2.0] - 2026-07-14\n",
            base_changelog="# Changelog\n\n## [0.1.0] - 2026-07-13\n",
            root_changed=True,
            changelog_changed=True,
        )
        self.assertIsNone(validate(**valid))
        invalid = (
            ({**valid, "current_version": "0.0.9"}, "strictly advance"),
            ({**valid, "current_version": "banana"}, "SemVer"),
            ({**valid, "base_version": "v0.1.0"}, "SemVer"),
            ({**valid, "current_version": "0.1.0"}, "strictly advance"),
            ({**valid, "root_version": "0.1.0"}, "root"),
            ({**valid, "root_changed": False}, "root"),
            ({**valid, "changelog_changed": False}, "changelog"),
            ({**valid, "changelog": "prefix ## [0.2.0] suffix\n"}, "heading"),
            ({
                **valid,
                "base_changelog": "# Changelog\n\n## [0.2.0] - 2026-07-13\n\nOld section.\n",
                "changelog": "# Changelog\n\n## [0.2.0] - 2026-07-13\n\nOld section.\n\nUnrelated edit.\n",
            }, "newly introduced"),
        )
        for case, diagnosis in invalid:
            with self.subTest(case=case):
                self.assertIn(diagnosis, validate(**case))

    def test_bundles_exist_at_only_declared_entrypoints(self):
        extensions = PLUGIN / "extensions"
        self.assertEqual(
            sorted(path.name for path in extensions.glob("*.js")),
            ["codearbiter-child.js", "codearbiter.js"],
        )

    def test_windows_supervisor_is_one_utf8_release_artifact_and_stale_gated(self):
        helpers = PLUGIN / "helpers"
        self.assertEqual(
            sorted(path.name for path in helpers.glob("*.js")),
            ["approval-dialog.js", "windows-supervisor.js"],
        )
        supervisor = helpers / "windows-supervisor.js"
        text = supervisor.read_bytes().decode("utf-8", errors="strict")
        self.assertIn("STARTED", text)
        self.assertNotIn("sourceMappingURL", text)
        build = (TOOLS / "build.mjs").read_text(encoding="utf-8")
        self.assertIn('entryPoints: ["src/windows-supervisor.ts"]', build)
        self.assertIn('outfile: "../helpers/windows-supervisor.js"', build)
        self.assertIn('entryPoints: ["src/approval-entry.ts"]', build)
        self.assertIn('outfile: "../helpers/approval-dialog.js"', build)
        approval = (helpers / "approval-dialog.js").read_bytes().decode("utf-8", errors="strict")
        self.assertNotIn("sourceMappingURL", approval)
        manifest = json.loads((PLUGIN / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["pi"]["extensions"], ["./extensions/codearbiter.js"])
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        stale_scope = "git diff --quiet -- plugins/ca-pi/extensions plugins/ca-pi/helpers"
        diagnostic_scope = "git --no-pager diff -- plugins/ca-pi/extensions plugins/ca-pi/helpers"
        self.assertIn(stale_scope, ci)
        self.assertIn(diagnostic_scope, ci)
        self.assertLess(ci.index(stale_scope), ci.index(diagnostic_scope))

    def test_shared_python_contains_no_direct_bare_git_subprocess(self):
        direct_bare_git = re.compile(
            r"subprocess\.(?:run|Popen|check_call|check_output)\(\s*\[\s*['\"]git['\"]",
            re.MULTILINE,
        )
        offenders = []
        for path in sorted((REPO / "core" / "pysrc").glob("*.py")):
            if direct_bare_git.search(path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(REPO).as_posix())
        self.assertEqual(offenders, [], "Pi-reachable Git subprocesses must use _gitexec.git_executable()")

    def test_declared_release_resources_exclude_dependency_and_native_artifacts(self):
        listed = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "plugins/ca-pi"],
            cwd=REPO,
            check=True,
            text=True,
            encoding="utf-8",
            capture_output=True,
        ).stdout.splitlines()
        selected = [REPO / relative for relative in listed]
        self.assertTrue(selected)
        self.assertEqual(distributable_violations(PLUGIN, selected), [])

    def test_distributable_scanner_rejects_nested_bypasses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = {
                "extensions/nested/addon.node": b"native",
                "skills/example/vendor/vite/index.js": b"export default {}\n",
                "extensions/codearbiter.js.map": b"{}\n",
                "extensions/deep/codearbiter.js": b"//# sourceMappingURL=hidden.map\n",
                "extensions/deep/payload.js": b"const bundled = 'rolldown';\n",
                "helpers/windows-supervisor.js": b"\xff\xfe\x00",
            }
            files = []
            for relative, content in fixtures.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                files.append(path)
            violations = distributable_violations(root, files)
            for relative in fixtures:
                with self.subTest(relative=relative):
                    self.assertTrue(
                        any(relative in violation for violation in violations),
                        f"nested bypass was not rejected: {relative}",
                    )

    def test_ci_has_pi_path_output_matrix_and_independent_version_guard(self):
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        required = (
            "ca-pi: ${{ steps.filter.outputs.ca-pi == 'true' || "
            "(github.event_name == 'push' && github.ref == 'refs/heads/major/state-contracts') }}",
            "- 'plugins/ca-pi/**'",
            "ca-pi-checks:",
            "ca-pi-tools:",
            "version-bump-pi:",
            'os: [ubuntu-latest, windows-latest, macos-latest]',
            "pi-versions: ${{ steps.pi-policy.outputs.versions }}",
            "pi-version: ${{ fromJSON(needs.changes.outputs.pi-versions) }}",
            "pi_host_locks.py install --version ${{ matrix.pi-version }}",
            "npm ci --ignore-scripts",
            "Test package, module identity, compatibility, and native binding",
            "Test the complete Pi adapter suite",
            "Test real package RPC activation and aliases",
            'python tools/build-host-packages.py --check --release-guard-base "$BASE_COMMIT" \\\n'
            '            --integration-base-branch "${BASE_BRANCH#refs/heads/}" --main-ref origin/main',
            "ca-pi-latest:",
            "- ca-pi-checks",
            "- ca-pi-tools",
            "- ca-pi-latest",
            "- version-bump-pi",
        )
        for text in required:
            self.assertIn(text, ci)
        matrix_job = ci.split("  ca-pi-tools:", 1)[1].split("\n  ca-pi-latest:", 1)[0]
        self.assertEqual(matrix_job.count("--ignore-scripts"), 1)
        self.assertIn("pi_host_locks.py install", matrix_job)
        latest_job = ci.split("  ca-pi-latest:", 1)[1].split("\n  hooks:", 1)[0]
        self.assertIn("Report latest version and test installed runtime admission", latest_job)
        self.assertEqual(pi_ci_contract_violations(ci), [])

        hard_coded_matrix = ci.replace(
            "pi-version: ${{ fromJSON(needs.changes.outputs.pi-versions) }}",
            'pi-version: ["1.5.0"]',
            1,
        )
        self.assertNotEqual(hard_coded_matrix, ci)
        self.assertTrue(
            pi_ci_contract_violations(hard_coded_matrix),
            "the matrix must consume the canonical Pi policy output",
        )

        security_contract = (REPO / ".github/scripts/test_pi_security.py").read_text(encoding="utf-8")
        self.assertIn(
            'name: "[CHECK] | [PI  ] | Security analysis  <language: JavaScript/TypeScript>"',
            security_contract,
        )

        for path in (".github/scripts/test_pi_security.py", ".github/workflows/codeql.yml"):
            mutated = ci.replace(f"              - '{path}'\n", "", 1)
            self.assertTrue(
                pi_ci_contract_violations(mutated),
                f"ca-pi path filter must include {path}",
            )

        aggregate_token_moved = ci.replace(
            "      - ca-pi-tools\n",
            "# moved token outside ci-passed: - ca-pi-tools\n",
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(aggregate_token_moved),
            "aggregate dependencies must be scoped to ci-passed.needs",
        )

        native_nooped = ci.replace(
            "        run: npm test -- test/package.test.ts\n",
            "        run: echo npm test -- test/package.test.ts\n",
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(native_nooped),
            "the matrix must execute the native-binding test command, not merely contain its text",
        )

        host_lock_nooped = ci.replace(
            "        run: python .github/scripts/pi_host_locks.py install --version ${{ matrix.pi-version }}",
            "        run: echo python .github/scripts/pi_host_locks.py install --version ${{ matrix.pi-version }}",
            1,
        )
        self.assertNotEqual(host_lock_nooped, ci, "the reviewed host-lock install step vanished")
        self.assertTrue(
            pi_ci_contract_violations(host_lock_nooped),
            "the matrix must execute the reviewed host-lock install, not merely contain its text",
        )

        host_lock_command = (
            '        run: python .github/scripts/pi_host_locks.py install '
            '--version ${{ matrix.pi-version }} '
            '--prefix "$RUNNER_TEMP/pi-host-${{ matrix.pi-version }}"'
        )
        for suffix in (" || true", "; exit 0"):
            with self.subTest(suffix=suffix):
                host_lock_suppressed = ci.replace(
                    host_lock_command,
                    f"{host_lock_command}{suffix}",
                    1,
                )
                self.assertNotEqual(host_lock_suppressed, ci, "the reviewed host-lock install step vanished")
                self.assertTrue(
                    pi_ci_contract_violations(host_lock_suppressed),
                    "the matrix must reject failure-suppression after the reviewed host-lock install",
                )

        full_suite_nooped = ci.replace(
            "      - name: Test the complete Pi adapter suite\n        run: npm test\n",
            "      - name: Test the complete Pi adapter suite\n        run: echo npm test\n",
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(full_suite_nooped),
            "the canonical Pi job must execute the complete unfiltered Vitest suite",
        )

        host_independent_remultiplied = ci.replace(
            "      - name: Test package, module identity, compatibility, and native binding\n",
            "      - name: Typecheck\n        run: npm run typecheck\n"
            "      - name: Test package, module identity, compatibility, and native binding\n",
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(host_independent_remultiplied),
            "a host-independent step must not creep back into the six-cell matrix",
        )

        platform_gated_dropped = ci.replace(" test/activation.test.ts", "", 1)
        self.assertNotEqual(platform_gated_dropped, ci, "the platform-gated matrix step vanished")
        self.assertTrue(
            pi_ci_contract_violations(platform_gated_dropped),
            "a Vitest file that branches on the live platform must run on all three OSes",
        )

        aggregate_result_dropped = ci.replace(
            "${{ needs['ca-pi-checks'].result }} ",
            "",
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(aggregate_result_dropped),
            "ci-passed must enforce ca-pi-checks, not merely wait for it",
        )

        rpc_nooped = ci.replace(
            "        run: python .github/scripts/test_pi_package.py --rpc-commands\n",
            "        run: echo python .github/scripts/test_pi_package.py --rpc-commands\n",
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(rpc_nooped),
            "every matrix cell must execute the live package RPC test",
        )

        latest_nooped = ci.replace(
            '          npm test -- test/package.test.ts -t "installed Pi runtime is admitted by the production boundary"\n',
            '          echo npm test -- test/package.test.ts -t "installed Pi runtime is admitted by the production boundary"\n',
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(latest_nooped),
            "the latest canary must execute installed-runtime admission, not merely contain its text",
        )

        latest_version_nooped = ci.replace(
            "          pi --version\n",
            "          echo pi --version\n",
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(latest_version_nooped),
            "the latest canary must execute the installed Pi version report before admission",
        )

        latest_install_nooped = ci.replace(
            "          npm install --global @earendil-works/pi-coding-agent@latest --ignore-scripts\n",
            "          echo npm install --global @earendil-works/pi-coding-agent@latest --ignore-scripts\n",
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(latest_install_nooped),
            "the latest canary must execute the npm-latest install, not merely contain its text",
        )

        # Issue #381 inverted the old contract: a job-level continue-on-error
        # still renders the check run FAILURE, so re-introducing one - or
        # dropping either step-level absorption, or the always-published
        # receipt - is now the violation.
        latest_job_level_continue = ci.replace(
            "  ca-pi-latest:\n    name:",
            "  ca-pi-latest:\n    continue-on-error: true\n    name:",
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(latest_job_level_continue),
            "a job-level continue-on-error must not mask canary harness failures",
        )

        latest_probe_unabsorbed = ci.replace(
            "        id: platform-contract\n        continue-on-error: true\n",
            "        id: platform-contract\n",
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(latest_probe_unabsorbed),
            "every upstream-compatibility probe must absorb its own failure at step level",
        )

        # Scoped to the ca-pi-latest job body, NOT the whole file. `if: always()`
        # is a generic line, and a bare first-occurrence replace mutates whichever
        # job happens to sit earliest in ci.yml - so this assertion silently
        # stopped testing the Pi receipt the moment an unrelated job above it grew
        # one (issue #521's coverage-union upload, which needs `always()` so a
        # FAILING host still publishes its blob). The mutation must hit the thing
        # the assertion is about, or it proves nothing about it.
        latest_start = ci.index("  ca-pi-latest:\n")
        latest_receipt_dropped = ci[:latest_start] + ci[latest_start:].replace(
            "        if: always()\n",
            "        if: success()\n",
            1,
        )
        self.assertNotEqual(
            latest_receipt_dropped, ci,
            "the ca-pi-latest receipt no longer carries an `if: always()` to drop",
        )
        self.assertTrue(
            pi_ci_contract_violations(latest_receipt_dropped),
            "the advisory receipt must publish even when a probe fails",
        )

        latest_order_drifted = ci.replace(
            '          npm test -- test/package.test.ts -t "installed Pi runtime is admitted by the production boundary"\n'
            "          npm test -- test/package.test.ts\n",
            "          npm test -- test/package.test.ts\n"
            '          npm test -- test/package.test.ts -t "installed Pi runtime is admitted by the production boundary"\n',
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(latest_order_drifted),
            "the latest canary must run named admission before the broad package test",
        )

    def test_task2_generated_and_built_text_is_strict_utf8_lf(self):
        outputs = (
            REPO / "package.json",
            PLUGIN / "package.json",
            PLUGIN / "CHANGELOG.md",
            PLUGIN / "extensions" / "codearbiter.js",
            PLUGIN / "extensions" / "codearbiter-child.js",
            PLUGIN / "helpers" / "windows-supervisor.js",
            TOOLS / "package.json",
            TOOLS / "package-lock.json",
            TOOLS / "tsconfig.json",
            TOOLS / "vitest.config.ts",
        )
        for path in outputs:
            with self.subTest(path=path):
                raw = path.read_bytes()
                decoded = raw.decode("utf-8", errors="strict")
                self.assertFalse(decoded.startswith("\ufeff"), f"{path}: UTF-8 BOM")
                self.assertNotIn("\r", decoded, f"{path}: non-LF newline")
                self.assertTrue(decoded.endswith("\n"), f"{path}: missing final LF")

    def test_real_isolated_rpc_command_discovery_and_keyed_status(self):
        catalog_document = read_json(PLUGIN / "generated" / "command-catalog.json")
        self.assertEqual(catalog_document["schemaVersion"], 1)
        catalog = list(catalog_document["commands"].values())
        expected_aliases = {f"ca-{entry['name']}" for entry in catalog}
        expected_fallbacks = {f"skill:ca-{entry['name']}" for entry in catalog}
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-") as directory:
            root = Path(directory)
            bare = root / "bare"
            enabled = root / "enabled"
            bare.mkdir()
            (enabled / ".codearbiter").mkdir(parents=True)
            (enabled / ".codearbiter" / "CONTEXT.md").write_text(
                "---\narbiter: enabled\n---\n",
                encoding="utf-8",
                newline="\n",
            )
            bare_records = run_rpc_commands(bare, root / "agent-bare", root / "home-bare")
            enabled_records = run_rpc_commands(
                enabled,
                root / "agent-enabled",
                root / "home-enabled",
                invoke_alias=True,
            )
            subprocess.run(["git", "init", "-b", "feature/doctor"], cwd=enabled, check=True, capture_output=True)
            staged_before = subprocess.run(
                ["git", "diff", "--cached", "--name-only"], cwd=enabled, check=True,
                text=True, encoding="utf-8", capture_output=True,
            ).stdout
            doctor_records = run_rpc_commands(
                enabled,
                root / "agent-doctor",
                root / "home-doctor",
                invoke_doctor=True,
            )
            staged_after = subprocess.run(
                ["git", "diff", "--cached", "--name-only"], cwd=enabled, check=True,
                text=True, encoding="utf-8", capture_output=True,
            ).stdout
            expected_bare_source = expected_pi_package_source(root / "agent-bare")
            expected_enabled_source = expected_pi_package_source(root / "agent-enabled")

        def response(records: list[dict]) -> dict:
            matches = [record for record in records if record.get("id") == "commands"]
            self.assertEqual(len(matches), 1, records)
            self.assertTrue(matches[0].get("success"), matches[0])
            return matches[0]

        bare_commands = response(bare_records)["data"]["commands"]
        enabled_commands = response(enabled_records)["data"]["commands"]
        for commands, expected_package_source in (
            (bare_commands, expected_bare_source),
            (enabled_commands, expected_enabled_source),
        ):
            names = [command["name"] for command in commands]
            self.assertEqual(len(names), len(set(names)), "RPC command names must be unique")
            self.assertEqual({name for name in names if name.startswith("ca-")}, expected_aliases)
            self.assertEqual({name for name in names if name.startswith("skill:ca-")}, expected_fallbacks)
            governed = [
                command for command in commands
                if command["name"] in expected_aliases | expected_fallbacks
            ]
            self.assertEqual(len(governed), len(expected_aliases) + len(expected_fallbacks))
            for command in governed:
                source_info = command.get("sourceInfo", {})
                self.assertEqual(source_info.get("origin"), "package", command)
                self.assertEqual(source_info.get("scope"), "user", command)
                self.assertEqual(Path(source_info.get("baseDir", "")).resolve(), REPO, command)
                self.assertEqual(source_info.get("source"), expected_package_source, command)
                if command["name"] in expected_aliases:
                    self.assertEqual(command.get("source"), "extension", command)
                    self.assertEqual(
                        Path(source_info.get("path", "")).resolve(),
                        (PLUGIN / "extensions" / "codearbiter.js").resolve(),
                        command,
                    )
                else:
                    self.assertEqual(command.get("source"), "skill", command)
                    skill_name = command["name"].removeprefix("skill:")
                    self.assertEqual(
                        Path(source_info.get("path", "")).resolve(),
                        (PLUGIN / "skills" / skill_name / "SKILL.md").resolve(),
                        command,
                    )

        def statuses(records: list[dict]) -> list[dict]:
            return [
                record for record in records
                if record.get("type") == "extension_ui_request"
                and record.get("method") == "setStatus"
            ]

        self.assertEqual(statuses(bare_records), [], "bare repo must remain status-silent")
        enabled_statuses = statuses(enabled_records)
        self.assertTrue(enabled_statuses, "enabled repo must emit keyed status")
        self.assertTrue(all(record.get("statusKey") == "codearbiter" for record in enabled_statuses))
        self.assertTrue(
            any("host: pi" in record.get("statusText", "") for record in enabled_statuses),
            enabled_statuses,
        )
        self.assertNotIn(
            "statusText",
            enabled_statuses[-1],
            "RPC serializes a status clear by omitting statusText",
        )
        status_text = "\n".join(
            record.get("statusText", "")
            for record in enabled_statuses
            if isinstance(record.get("statusText"), str)
        ).lower()
        self.assertNotIn("command ownership", status_text, enabled_statuses)
        self.assertNotIn("command surface", status_text, enabled_statuses)

        errors = [record for record in enabled_records if record.get("type") == "extension_error"]
        self.assertEqual(errors, [])
        captures = [record for record in enabled_records if record.get("id") == "capture"]
        self.assertEqual(len(captures), 1, enabled_records)
        self.assertTrue(captures[0].get("success"), captures[0])
        captured = captures[0]["data"]["text"]
        self.assertTrue(captured.startswith("CA_PI_CAPTURE:"), captured)
        import base64
        expanded = base64.b64decode(captured.removeprefix("CA_PI_CAPTURE:"), validate=True).decode("utf-8")
        skill_path = (PLUGIN / "skills" / "ca-status" / "SKILL.md").resolve()
        raw_skill = skill_path.read_text(encoding="utf-8")
        self.assertTrue(raw_skill.startswith("---\n"))
        body = raw_skill.split("\n---\n", 1)[1].strip()
        expected = (
            f'<skill name="ca-status" location="{skill_path}">\n'
            f"References are relative to {skill_path.parent}.\n\n"
            f"{body}\n</skill>\n\n __CA_ALIAS_SENTINEL__  "
        )
        self.assertEqual(expanded, expected)
        self.assertNotIn("/skill:ca-status", expanded)

        doctor_captures = [record for record in doctor_records if record.get("id") == "capture"]
        self.assertEqual(len(doctor_captures), 1, doctor_records)
        doctor_text = doctor_captures[0]["data"]["text"]
        self.assertTrue(doctor_text.startswith("CA_PI_CAPTURE:"), doctor_text)
        doctor_expanded = base64.b64decode(
            doctor_text.removeprefix("CA_PI_CAPTURE:"), validate=True
        ).decode("utf-8")
        self.assertIn('<skill name="ca-doctor"', doctor_expanded)
        self.assertIn("<codearbiter-doctor-report>", doctor_expanded)
        report_prefix = "<codearbiter-doctor-report>\n"
        report_start = doctor_expanded.index(report_prefix) + len(report_prefix)
        report_end = doctor_expanded.index("\n</codearbiter-doctor-report>", report_start)
        report_envelope = json.loads(doctor_expanded[report_start:report_end])
        self.assertEqual(report_envelope["format"], "codearbiter-doctor-v1")
        doctor_report = report_envelope["report"]
        for diagnosis in (
            "package", "trust", "version", "python", "core", "commands", "bridge",
            "child", "ambient-marker", "module-identity", "final-arguments",
            "active-dispatch", "wrapper-self-test",
        ):
            self.assertEqual(
                sum(line.startswith(("HEALTHY  ", "DEGRADED  ", "UNHEALTHY  ")) and
                    f"  {diagnosis}:" in line for line in doctor_report.splitlines()),
                1,
                doctor_report,
            )
        self.assertIn(
            "HEALTHY  wrapper-self-test: The stored governed Pi bash wrapper returned the exact "
            "shared-core H-03 block for git add --all --dry-run; no staging occurred.",
            doctor_report,
        )
        self.assertIn(
            "DEGRADED  active-dispatch: Supported Pi 1.5.0 public extension APIs cannot "
            "submit this deterministic self-test through the active dispatcher; the wrapper "
            "self-test does not exercise active dispatch.",
            doctor_report,
        )
        self.assertIn(
            "REMEDIATION  active-dispatch: Require passing supported-version real-host promotion/CI "
            "evidence before closing PI-AC-28.",
            doctor_report,
        )
        self.assertIn("HEALTHY  child: The exact hardened child enforcement artifact is present", doctor_report)
        self.assertNotIn("Task 6 enforcement is pending", doctor_report)
        self.assertNotIn("live-fire", doctor_report.lower())
        self.assertEqual(doctor_report.splitlines()[-1], "doctor: DEGRADED")
        self.assertEqual(staged_before, staged_after)

    def test_real_rpc_enabled_untrusted_global_session_stays_before_repository_boundary(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-untrusted-") as directory:
            root = Path(directory)
            enabled = root / "enabled"
            (enabled / ".codearbiter").mkdir(parents=True)
            (enabled / ".codearbiter" / "CONTEXT.md").write_text(
                "---\narbiter: enabled\n---\n<!--INITIALIZED-->\nstage: implementation\n",
                encoding="utf-8",
                newline="\n",
            )
            real_git = str(Path(shutil.which("git") or "").resolve())
            self.assertTrue(Path(real_git).is_file(), real_git)
            subprocess.run(
                [real_git, "init", "-q", "-b", "feature/untrusted-boundary"],
                cwd=enabled,
                check=True,
                capture_output=True,
            )

            records = run_rpc_commands(
                enabled,
                root / "agent",
                root / "home",
                invoke_doctor=True,
                project_trusted=False,
            )
            pre_commit_exists = (enabled / ".git" / "hooks" / "pre-commit").exists()
            pre_push_exists = (enabled / ".git" / "hooks" / "pre-push").exists()
            hook_cache_exists = (enabled / ".git" / "codearbiter-hooksdir-cache").exists()
            fetch_head_exists = (enabled / ".git" / "FETCH_HEAD").exists()
            markers_dir = enabled / ".codearbiter" / ".markers"
            standup_markers = list(markers_dir.glob("standup-*") if markers_dir.is_dir() else [])

        self.assertFalse(pre_commit_exists, "untrusted startup installed a managed pre-commit hook")
        self.assertFalse(pre_push_exists, "untrusted startup installed a managed pre-push hook")
        self.assertFalse(hook_cache_exists, "untrusted startup performed managed-hook discovery")
        self.assertFalse(fetch_head_exists, "untrusted startup fetched repository state")
        self.assertEqual(standup_markers, [], "untrusted startup entered shared session-start state")
        errors = [record for record in records if record.get("type") == "extension_error"]
        self.assertEqual(errors, [], records)
        statuses = [
            record for record in records
            if record.get("type") == "extension_ui_request"
            and record.get("method") == "setStatus"
            and isinstance(record.get("statusText"), str)
        ]
        trust_direction = (
            "codeArbiter host: pi waiting for project trust - run /trust in Pi, approve this "
            "project, then start a new session"
        )
        self.assertEqual([record.get("statusText") for record in statuses], [trust_direction])

        captures = [record for record in records if record.get("id") == "capture"]
        self.assertEqual(len(captures), 1, records)
        import base64
        expanded = base64.b64decode(
            captures[0]["data"]["text"].removeprefix("CA_PI_CAPTURE:"),
            validate=True,
        ).decode("utf-8")
        prefix = "<codearbiter-doctor-report>\n"
        start = expanded.index(prefix) + len(prefix)
        end = expanded.index("\n</codearbiter-doctor-report>", start)
        report = json.loads(expanded[start:end])["report"]
        self.assertIn("UNHEALTHY  trust:", report)
        self.assertIn("DEGRADED  python:", report)
        self.assertIn("DEGRADED  bridge:", report)
        self.assertIn("DEGRADED  final-arguments:", report)
        self.assertIn("DEGRADED  wrapper-self-test:", report)
        self.assertIn("project trust", report.lower())

    def test_real_rpc_native_read_context_is_model_visible_once(self):
        import base64

        # #416: the pointer names the ADR's filename stem, not its bare number.
        expected_context = (
            "ADR-0015-pi-read (Model-visible read contract) governs this file"
            " — do not contradict it; route changes via /ca:reconcile or /ca:adr."
        )
        governed_native = "governed native body\n"
        ungoverned_native = "ungoverned native body\n"
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-read-context-") as directory:
            root = Path(directory)
            enabled = root / "enabled"
            state = enabled / ".codearbiter"
            decisions = state / "decisions"
            source = enabled / "src"
            decisions.mkdir(parents=True)
            source.mkdir()
            (state / "CONTEXT.md").write_text(
                "---\narbiter: enabled\n---\n",
                encoding="utf-8",
                newline="\n",
            )
            (decisions / "0015-pi-read.md").write_text(
                "---\n"
                "title: Model-visible read contract\n"
                "status: accepted\n"
                "governs: src/governed.txt\n"
                "---\n"
                "# Model-visible read contract\n",
                encoding="utf-8",
                newline="\n",
            )
            governed = source / "governed.txt"
            ungoverned = source / "ungoverned.txt"
            governed.write_text(governed_native, encoding="utf-8", newline="\n")
            ungoverned.write_text(ungoverned_native, encoding="utf-8", newline="\n")

            sessions = [
                run_rpc_commands(
                    enabled,
                    root / f"agent-{label}",
                    root / f"home-{label}",
                    invoke_read_context=True,
                    governed_read_path=governed,
                    ungoverned_read_path=ungoverned,
                )
                for label in ("a", "b")
            ]

        expected_ids = {
            "governedFirst": "ca-read-context-governed-first",
            "governedSecond": "ca-read-context-governed-second",
            "ungoverned": "ca-read-context-ungoverned",
        }
        observed_session_ids: list[str] = []
        for records in sessions:
            states = [record for record in records if record.get("id") == "state"]
            self.assertEqual(len(states), 1, records)
            self.assertTrue(states[0].get("success"), states[0])
            session_id = states[0].get("data", {}).get("sessionId")
            self.assertIsInstance(session_id, str, states[0])
            self.assertTrue(session_id, "Pi returned an empty RPC session identifier")
            self.assertLessEqual(len(session_id), 1_024)
            observed_session_ids.append(session_id)

            captures = [record for record in records if record.get("id") == "capture"]
            self.assertEqual(len(captures), 1, records)
            self.assertTrue(captures[0].get("success"), captures[0])
            captured_text = captures[0]["data"]["text"]
            self.assertTrue(captured_text.startswith("CA_PI_READ_RESULT:"), captured_text)
            captured = json.loads(base64.b64decode(
                captured_text.removeprefix("CA_PI_READ_RESULT:"),
                validate=True,
            ).decode("utf-8"))

            for key, tool_call_id in expected_ids.items():
                result = captured[key]
                self.assertEqual(result.get("role"), "toolResult", result)
                self.assertEqual(result.get("toolCallId"), tool_call_id, result)
                self.assertEqual(result.get("toolName"), "read", result)
                self.assertFalse(result.get("isError"), result)

            governed_first_content = captured["governedFirst"]["content"]
            self.assertEqual(governed_first_content[0], {"type": "text", "text": governed_native})
            self.assertEqual(len(governed_first_content), 2, governed_first_content)
            self.assertEqual(
                governed_first_content[1].get("codearbiter", {}).get("kind"),
                "codearbiter-notice",
                governed_first_content,
            )
            rendered_governed = json.dumps(governed_first_content, ensure_ascii=False, sort_keys=True)
            self.assertEqual(rendered_governed.count(expected_context), 1, rendered_governed)

            self.assertEqual(
                captured["governedSecond"]["content"],
                [{"type": "text", "text": governed_native}],
            )
            self.assertNotIn("codearbiter-notice", json.dumps(captured["governedSecond"], sort_keys=True))
            self.assertEqual(
                captured["ungoverned"]["content"],
                [{"type": "text", "text": ungoverned_native}],
            )
            self.assertNotIn("codearbiter-notice", json.dumps(captured["ungoverned"], sort_keys=True))

            starts = [
                record for record in records
                if record.get("type") == "tool_execution_start" and record.get("toolName") == "read"
            ]
            ends = [
                record for record in records
                if record.get("type") == "tool_execution_end" and record.get("toolName") == "read"
            ]
            self.assertEqual({record.get("toolCallId") for record in starts}, set(expected_ids.values()), starts)
            self.assertEqual({record.get("toolCallId") for record in ends}, set(expected_ids.values()), ends)
            self.assertTrue(all(record.get("isError") is False for record in ends), ends)

        self.assertEqual(len(set(observed_session_ids)), 2, "real Pi RPC sessions must have distinct identifiers")

    def test_real_rpc_enforcement_registration_failure_stays_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-enforcement-fault-") as directory:
            root = Path(directory)
            enabled = root / "enabled"
            mutation = root / "mutation-reached-executor"
            fault_marker = root / "enforcement-registration-fault-consumed"
            (enabled / ".codearbiter").mkdir(parents=True)
            (enabled / ".codearbiter" / "CONTEXT.md").write_text(
                "---\narbiter: enabled\n---\n",
                encoding="utf-8",
                newline="\n",
            )

            records = run_rpc_commands(
                enabled,
                root / "agent",
                root / "home",
                invoke_enforcement_fault=True,
                mutation_path=mutation,
                fault_marker_path=fault_marker,
            )
            mutation_observed = mutation.exists()
            fault_marker_observed = (
                fault_marker.read_text(encoding="utf-8") if fault_marker.is_file() else None
            )

        lifecycle_errors = [
            record for record in records
            if record.get("type") == "extension_error"
            and record.get("event") == "session_start"
        ]
        self.assertEqual(len(lifecycle_errors), 1, records)
        self.assertIn(
            "enforcement installation failed; run /ca-doctor",
            lifecycle_errors[0].get("error", ""),
        )
        self.assertEqual(
            fault_marker_observed,
            "CA_PI_TEST_ENFORCEMENT_REGISTRATION_FAILURE_CONSUMED\n",
            "the test-only one-shot registration fault was not uniquely consumed",
        )
        self.assertTrue(
            any(record.get("type") == "agent_settled" for record in records),
            "real Pi must continue and settle after reporting the lifecycle error",
        )
        refusal_events = [
            record for record in records
            if record.get("type") == "tool_execution_end"
            and record.get("toolName") == "write"
            and record.get("isError") is True
        ]
        self.assertEqual(len(refusal_events), 1, records)
        self.assertIn("/ca-doctor", json.dumps(refusal_events[0], sort_keys=True))
        self.assertFalse(
            mutation_observed,
            "the real write dispatcher reached its executor after Pi swallowed bootstrap failure",
        )

    def test_durable_package_copy_never_follows_an_escaping_worktree_symlink(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-durable-copy-") as directory:
            root = Path(directory)
            repo = root / "repo"
            charter = repo / "plugins" / "ca-pi" / "hooks" / "pi-bridge.py"
            manifest = repo / "plugins" / "ca-pi" / "package.json"
            charter.parent.mkdir(parents=True)
            expected = b"# indexed reviewed bridge\n"
            charter.write_bytes(expected)
            manifest.write_text(
                '{"name":"@arbiterforge/ca-pi","private":true}\n',
                encoding="utf-8",
                newline="\n",
            )
            subprocess.run(
                ["git", "init", "-q", "-b", "fixture"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "add", "--", "plugins/ca-pi/hooks/pi-bridge.py", "plugins/ca-pi/package.json"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            ambient = root / "ambient-unreviewed.py"
            ambient.write_bytes(b"# arbitrary external executable\n")
            charter.unlink()
            try:
                charter.symlink_to(ambient)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"test platform cannot create symlinks: {error}")

            with mock.patch.object(sys.modules[__name__], "REPO", repo):
                copied = durable_pi_package_copy(root / "copy")

            self.assertEqual((copied / "hooks" / "pi-bridge.py").read_bytes(), expected)

    @unittest.skipUnless(os.name == "nt", "Windows executable search canary")
    def test_real_rpc_enabled_start_never_executes_project_git_and_installs_absolute_hook_identities(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-git-poison-") as directory:
            root = Path(directory)
            package_source = durable_pi_package_copy(root)
            enabled = root / "enabled"
            sentinel = root / "project-git-executed"
            (enabled / ".codearbiter").mkdir(parents=True)
            (enabled / ".codearbiter" / "CONTEXT.md").write_text(
                "---\narbiter: enabled\n---\n",
                encoding="utf-8",
                newline="\n",
            )
            real_git = Path(shutil.which("git") or "").resolve()
            self.assertTrue(real_git.is_file(), real_git)
            subprocess.run(
                [str(real_git), "init", "-q", "-b", "feature/pi-git-boundary"],
                cwd=enabled,
                check=True,
                capture_output=True,
            )

            def poison_project_after_package_install() -> None:
                shutil.copy2(sys.executable, enabled / "git.exe")
                (enabled / "sitecustomize.py").write_text(
                    "import sys\n"
                    "from pathlib import Path\n"
                    "if Path(sys.executable).name.lower() == 'git.exe':\n"
                    f"    Path({str(sentinel)!r}).write_text('executed', encoding='utf-8')\n",
                    encoding="utf-8",
                    newline="\n",
                )

            records = run_rpc_commands(
                enabled,
                root / "agent",
                root / "home",
                package_source=package_source,
                _after_install=poison_project_after_package_install,
            )
            hook_path = enabled / ".git" / "hooks" / "pre-commit"
            # Report WHY the enforcer is missing rather than dying on read_text.
            # An absent hook means session_start never reached the install (the
            # H-01/H-02 backstop that closes `--no-verify`, ADR-0015), and the
            # RPC records carry the startup failure that explains it. A bare
            # FileNotFoundError hides that and sends the next reader hunting.
            if not hook_path.is_file():
                hooks_dir = enabled / ".git" / "hooks"
                present = sorted(p.name for p in hooks_dir.iterdir()) if hooks_dir.is_dir() else "<no hooks dir>"
                # The RPC records report only that the bridge went "degraded";
                # the bridge's own stderr never reaches them. Drive the same
                # session_start request through the bridge DIRECTLY, in the same
                # poisoned fixture, so the failure names itself instead of being
                # inferred from a status string.
                probe_environment = os.environ.copy()
                probe_environment["CODEARBITER_GIT_EXECUTABLE"] = str(real_git)
                probe_environment["CODEARBITER_PYTHON_EXECUTABLE"] = str(Path(sys.executable).resolve())
                probe_environment.pop("CLAUDE_PROJECT_DIR", None)
                try:
                    probe = subprocess.run(
                        [sys.executable, str(package_source / "hooks" / "pi-bridge.py")],
                        input=json.dumps({"version": 1, "event": "session_start", "cwd": str(enabled)}),
                        cwd=enabled, env=probe_environment, text=True, encoding="utf-8",
                        errors="replace", capture_output=True, timeout=120,
                    )
                    probe_report = (f"rc={probe.returncode}\n    stdout={probe.stdout[:2000]!r}\n"
                                    f"    stderr={probe.stderr[-4000:]!r}")
                except Exception as error:  # noqa: BLE001 — a probe must not mask the real failure
                    probe_report = f"probe itself failed: {type(error).__name__}: {error}"
                self.fail(
                    "session_start did not install the git-level enforcement backstop.\n"
                    f"  .git/hooks contains: {present}\n"
                    f"  project-git sentinel fired: {sentinel.exists()}\n"
                    f"  direct bridge session_start probe: {probe_report}\n"
                    "  RPC records follow:\n    "
                    + "\n    ".join(json.dumps(record)[:2000] for record in records))
            hook = hook_path.read_text(encoding="utf-8")
            shell_candidates = [Path(value) for value in [shutil.which("sh.exe"), shutil.which("sh")] if value]
            for parent in real_git.parents:
                shell_candidates.extend([parent / "bin" / "sh.exe", parent / "usr" / "bin" / "sh.exe"])
            shell = next((candidate.resolve() for candidate in shell_candidates if candidate.is_file()), None)
            self.assertIsNotNone(shell, "Git for Windows shell is unavailable")
            hook_environment = os.environ.copy()
            hook_environment["PATH"] = str(enabled)
            hook_result = subprocess.run(
                [str(shell), str(hook_path)],
                cwd=enabled,
                env=hook_environment,
                text=True,
                capture_output=True,
                timeout=30,
            )
            identity_dir = enabled / ".git" / "codearbiter-hooksd"
            identity_lines = (identity_dir / "trusted-executables.identity").read_text(
                encoding="utf-8").splitlines()
            self.assertEqual(len(identity_lines), 3, identity_lines)
            installed_python = Path(identity_lines[0]).resolve()
            installed_git = Path(identity_lines[1]).resolve()
            self.assertEqual(identity_lines[2], "ca-pi")
            poison_observed = sentinel.exists()

        self.assertFalse(poison_observed, "enabled session_start executed project-local git.exe")
        self.assertFalse(
            any(record.get("type") == "extension_error" for record in records),
            records,
        )
        self.assertEqual(hook_result.returncode, 0, hook_result.stdout + hook_result.stderr)
        self.assertTrue(installed_git.is_file(), installed_git)
        self.assertTrue(installed_python.is_file(), installed_python)
        self.assertFalse(installed_git.is_relative_to(enabled), installed_git)
        self.assertFalse(installed_python.is_relative_to(enabled), installed_python)
        self.assertIn("trusted-executables.identity", hook)
        self.assertIn('export CODEARBITER_GIT_EXECUTABLE="$G"', hook)

    def test_rpc_stderr_survives_malformed_utf8_and_pipe_saturation(self):
        # Malformed UTF-8 followed by more stderr than a pipe holds must not stop
        # the drain: a stalled child would surface as a shutdown timeout instead
        # of its real exit status and stderr tail.
        root_code = (
            "import json, sys; "
            "sys.stderr.buffer.write(b'\\xff\\xfe' + b'x' * (1 << 18)); sys.stderr.buffer.flush(); "
            "print(json.dumps({'id': 'commands', 'type': 'response'}), flush=True); "
            "sys.stdin.read(); "
            "sys.stderr.buffer.write(b'tail-marker \\xff'); sys.stderr.buffer.flush(); "
            "raise SystemExit(3)"
        )
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-stderr-") as directory:
            root = Path(directory)
            cwd = root / "cwd"
            cwd.mkdir()
            started = time.monotonic()
            with self.assertRaises(AssertionError) as raised:
                run_rpc_commands(
                    cwd,
                    root / "agent",
                    root / "home",
                    _rpc_command=[sys.executable, "-c", root_code],
                )
            message = str(raised.exception)
            self.assertTrue(message.startswith("Pi RPC exited 3: "), message[:300])
            self.assertTrue(message.endswith("tail-marker \ufffd"), message[-300:])
            self.assertLess(time.monotonic() - started, 20)

    def test_rpc_decode_failure_terminates_process_tree_and_reader(self):
        observed: list[tuple[subprocess.Popen[str], threading.Thread]] = []
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-cleanup-") as directory:
            root = Path(directory)
            cwd = root / "cwd"
            cwd.mkdir()
            child_marker = root / "child.pid"
            child_code = "import time; time.sleep(60)"
            root_code = (
                "import pathlib, subprocess, sys, time; "
                f"child=subprocess.Popen([sys.executable,'-c',{child_code!r}]); "
                f"pathlib.Path({str(child_marker)!r}).write_text(str(child.pid),encoding='utf-8'); "
                "print('not-json',flush=True); time.sleep(60)"
            )
            process: subprocess.Popen[str] | None = None
            reader: threading.Thread | None = None
            child_pid: int | None = None
            try:
                with self.assertRaisesRegex(AssertionError, "non-JSON stdout"):
                    run_rpc_commands(
                        cwd,
                        root / "agent",
                        root / "home",
                        _rpc_command=[sys.executable, "-c", root_code],
                        _on_process_started=lambda proc, thread: observed.append((proc, thread)),
                    )
                self.assertEqual(len(observed), 1)
                process, reader = observed[0]
                child_pid = int(child_marker.read_text(encoding="utf-8"))

                def pid_exists(pid: int) -> bool:
                    if os.name == "nt":
                        result = subprocess.run(
                            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            capture_output=True,
                            timeout=5,
                            check=False,
                        )
                        return f',"{pid}",' in result.stdout
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        return False
                    except PermissionError:
                        return True
                    return True

                deadline = time.monotonic() + 3
                while pid_exists(child_pid) and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(
                    process.poll() is not None and not reader.is_alive() and not pid_exists(child_pid),
                    "decode failure must reap the RPC root, its child, and the stdout reader",
                )
            finally:
                if process is not None and process.poll() is None:
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            text=True,
                            capture_output=True,
                            timeout=5,
                            check=False,
                        )
                    else:
                        if child_pid is None and child_marker.is_file():
                            child_pid = int(child_marker.read_text(encoding="utf-8"))
                        for pid in (child_pid, process.pid):
                            if pid is not None:
                                try:
                                    os.kill(pid, 9)
                                except ProcessLookupError:
                                    pass
                    process.wait(timeout=5)
                if process is not None:
                    for stream in (process.stdin, process.stdout, process.stderr):
                        if stream is not None and not stream.closed:
                            stream.close()
                if reader is not None:
                    reader.join(timeout=2)

    def test_real_rpc_shutdown_probe_uses_the_same_untrusted_fixture(self):
        # The original case keeps its raw CLI arguments. This additional case
        # also observes before provider loading, without substituting a passing
        # diagnostic run for the original natural-exit result.
        real_run = run_rpc_commands
        with mock.patch.object(
            sys.modules[__name__], "run_rpc_commands",
            side_effect=lambda *args, **kwargs: real_run(*args, **kwargs, _observe_shutdown=True),
        ):
            self.test_real_rpc_enabled_untrusted_global_session_stays_before_repository_boundary()

    def test_real_rpc_shutdown_probe_uses_the_same_discovery_and_doctor_fixture(self):
        real_run = run_rpc_commands
        with mock.patch.object(
            sys.modules[__name__], "run_rpc_commands",
            side_effect=lambda *args, **kwargs: real_run(*args, **kwargs, _observe_shutdown=True),
        ):
            self.test_real_isolated_rpc_command_discovery_and_keyed_status()

    def _observe_original_rpc_fixture_shutdown(self, fixture):
        # These are additional observations, never substitutes for raw tests.
        node, cli = live_pi_cli()
        identity = rpc_diagnostic_runtime_identity(node, cli)
        self.assertIsNotNone(identity)
        real_run = run_rpc_commands

        def observed(*args, **kwargs):
            succeeded = False
            try:
                records = real_run(*args, **kwargs, _observe_shutdown=True)
                succeeded = True
                return records
            finally:
                try:
                    retain_rpc_observed_raw_diagnostics(
                        args[2] / "ca-rpc-shutdown-trace.json", identity, succeeded=succeeded,
                    )
                except Exception:
                    pass

        with mock.patch.object(sys.modules[__name__], "run_rpc_commands", side_effect=observed):
            fixture()

    def test_real_rpc_shutdown_probe_uses_the_same_enforcement_failure_fixture(self):
        self._observe_original_rpc_fixture_shutdown(
            self.test_real_rpc_enforcement_registration_failure_stays_fail_closed,
        )

    def test_real_rpc_shutdown_probe_uses_the_same_native_read_context_fixture(self):
        self._observe_original_rpc_fixture_shutdown(
            self.test_real_rpc_native_read_context_is_model_visible_once,
        )

    def _rpc_really_exit_boundary_fixture(self, kind):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the shutdown diagnostic fixtures")
        with tempfile.TemporaryDirectory(prefix="ca-pi-reallyexit-") as directory:
            root = Path(directory)
            preload, _, trace = write_rpc_shutdown_observer(root)
            bootstrap = root / "bootstrap.cjs"
            setup = (
                "// Synthetic callee block, not a claim about actual native shutdown.\n"
                "process.reallyExit = function() { Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0); };\n"
                if kind == "callee" else ""
            )
            bootstrap.write_text(setup + "require(" + json.dumps(str(preload)) + ");\n",
                                 encoding="utf-8", newline="\n")
            script = r"""
const assert = require('node:assert/strict');
if (KIND === 'normal') {
  // Test the exact generated wrapper against a returning/throwing callee in a
  // separate VM, including a failed diagnostic writer. The real process below
  // still exits through its genuine original native callee.
  const source = require('node:fs').readFileSync(PRELOAD, 'utf8');
  const receiver = {}, first = {}, second = {}, returned = {}, thrown = {};
  let calls = 0;
  const fake = {
    pid: 7, version: process.version, platform: process.platform,
    stdin: {readableEnded: false, prependOnceListener() {}},
    once() {}, getActiveResourcesInfo() { return []; },
    reallyExit: function(...args) {
      calls++;
      assert.equal(this, receiver);
      if (args[0] === thrown) throw thrown;
      assert.deepEqual(args, [first, second]);
      return returned;
    },
  };
  require('node:vm').runInNewContext(source, {
    process: fake, performance: {now() { return 0; }},
    require(name) {
      assert.equal(name, 'node:fs');
      return {writeFileSync() { throw new Error('controlled diagnostic write refusal'); }};
    },
  });
  assert.equal(fake.reallyExit.call(receiver, first, second), returned);
  let caught;
  try { fake.reallyExit.call(receiver, thrown); } catch (error) { caught = error; }
  assert.equal(caught, thrown);
  assert.equal(calls, 2);
}
if (KIND === 'listener') {
  process.on('exit', () => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0));
}
process.stdin.on('end', () => {
  globalThis.__caPiRpcShutdownObserve('session_shutdown_observer');
  process.exit(0);
});
process.stdin.resume();
process.stdout.write('ready\n');
""".replace("KIND", json.dumps(kind)).replace("PRELOAD", json.dumps(str(preload)))
            command = [node, "--require", str(bootstrap), "-e", script]
            environment = {"HOME": str(root), "USERPROFILE": str(root),
                           "TEMP": str(root), "TMP": str(root), "PATH": ""}
            for key in ("SystemRoot", "WINDIR", "ComSpec", "PATHEXT"):
                if os.environ.get(key):
                    environment[key] = os.environ[key]
            process = subprocess.Popen(
                command, cwd=root, env=environment, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="strict", start_new_session=os.name != "nt",
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
            )
            stdout = stderr = None
            try:
                if kind == "normal":
                    stdout, stderr = process.communicate(input="", timeout=5)
                    self.assertEqual(process.returncode, 0)
                else:
                    process.stdin.close()
                    process.stdin = None
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        report = safe_rpc_shutdown_report(trace)
                        if report and len(report["phases"]) == 4:
                            if kind != "callee" or report.get("reallyExitCallEntered") is True:
                                break
                        if process.poll() is not None:
                            break
                        time.sleep(0.01)
                    self.assertIsNone(process.poll(), "negative fixture must remain alive before cleanup")
                report = safe_rpc_shutdown_report(trace)
                self.assertIsNotNone(report)
                self.assertEqual(report["pid"], process.pid)
                self.assertTrue(rpc_shutdown_phase_complete(trace, process.pid))
                self.assertIs(report["reallyExitCallEntered"], kind != "listener")
            finally:
                if process.poll() is None:
                    # These two synthetic hangs fail the exit contract. Reaping
                    # this owned fixture is cleanup, never evidence of host success.
                    terminate_process_tree(process)
                if stdout is None:
                    stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(stdout, "ready\n")
            self.assertEqual(stderr, "")
            return report

    def test_rpc_shutdown_reallyexit_normal_is_transparent_and_closed(self):
        report = self._rpc_really_exit_boundary_fixture("normal")
        with tempfile.TemporaryDirectory(prefix="ca-pi-reallyexit-projection-") as directory:
            trace = Path(directory) / "trace.json"
            legacy = {key: value for key, value in report.items() if key != "reallyExitCallEntered"}
            trace.write_text(json.dumps(legacy), encoding="utf-8", newline="\n")
            self.assertEqual(safe_rpc_shutdown_report(trace), legacy)
            for bad in (1, "PrivateFixtureValue", {"payload": "PrivateFixtureValue"}, None):
                trace.write_text(json.dumps({**report, "reallyExitCallEntered": bad}),
                                 encoding="utf-8", newline="\n")
                self.assertIsNone(safe_rpc_shutdown_report(trace))
            trace.write_text(json.dumps({**report, "private": "PrivateFixtureValue"}),
                             encoding="utf-8", newline="\n")
            self.assertEqual(safe_rpc_shutdown_report(trace), report)

    def test_rpc_shutdown_reallyexit_later_js_listener_stays_before_call(self):
        self.assertIs(self._rpc_really_exit_boundary_fixture("listener")["reallyExitCallEntered"], False)

    def test_rpc_shutdown_reallyexit_synthetic_callee_stays_after_call_entry(self):
        self.assertIs(self._rpc_really_exit_boundary_fixture("callee")["reallyExitCallEntered"], True)

    def test_rpc_protocol_failure_report_preserves_order_and_unknown_completion(self):
        pending = RpcProtocolDiagnostic()
        pending.mark("send_commands"); pending.mark("send_invoke")
        pending.observe_record({"id": "commands", "success": True})
        for _ in range(30):
            pending.observe_record({"type": "other", "payload": "PrivateFixtureValue"})
        pending.collected("deadline")
        pending.closed_stdin()
        pending.mark("shutdown_timeout"); pending.exited(None); pending.failed()
        report = pending.snapshot()
        self.assertIsNotNone(report)
        self.assertEqual(report["recordCount"], 31)
        self.assertTrue(report["commandsSeen"])
        self.assertFalse(report["agentSettledSeen"])
        self.assertFalse(report["captureSeen"])
        self.assertEqual(report["collection"], "deadline")
        self.assertTrue(report["eofClosed"])
        self.assertIs(report["processExited"], False)
        self.assertIsNone(report["exitCode"])
        self.assertEqual([event["phase"] for event in report["events"]], [
            "spawned", "send_commands", "send_invoke", "receive_commands",
            "collection_deadline", "stdin_closed", "shutdown_timeout", "error",
        ])
        self.assertNotIn("PrivateFixtureValue", json.dumps(report))

        complete = RpcProtocolDiagnostic()
        for identifier in ("commands", "state", "invoke"):
            complete.mark("send_" + identifier)
        complete.observe_record({"id": "commands"})
        complete.observe_record({"id": "state"})
        complete.observe_record({"type": "agent_settled"})
        complete.mark("send_capture"); complete.observe_record({"id": "capture"})
        complete.collected("complete"); complete.closed_stdin(); complete.exited(0)
        report = complete.snapshot()
        self.assertTrue(all(report[key] for key in ("commandsSeen", "stateSeen", "agentSettledSeen", "captureSeen", "eofClosed", "processExited")))
        self.assertEqual(report["exitCode"], 0)
        complete.value["recordCount"] = 1_000_000
        complete.observe_record({})
        self.assertEqual(complete.snapshot()["recordCount"], 1_000_000)
        self.assertTrue(complete.snapshot()["recordCountSaturated"])
        broken = mock.Mock(snapshot=mock.Mock(side_effect=ValueError("PrivateFixtureValue")))
        self.assertIsNone(rpc_protocol_observe(broken, "snapshot"))

    def test_rpc_protocol_failure_report_is_closed_bounded_and_private(self):
        valid = RpcProtocolDiagnostic().snapshot()
        bad = []
        class PretendEnum(str):
            def __eq__(self, other):
                return True
            __hash__ = str.__hash__

        for key, value in (("private", "PrivateFixtureValue"), ("schemaVersion", True),
                           ("recordCount", True), ("recordCount", 1_000_001),
                           ("commandsSeen", 1), ("collection", "PrivateFixtureValue"),
                           ("collection", PretendEnum("PrivateFixtureValue")),
                           ("processExited", "PrivateFixtureValue"), ("exitCode", True),
                           ("events", [])):
            item = copy.deepcopy(valid); item[key] = value; bad.append(item)
        for key, value in (("phase", "PrivateFixtureValue"), ("elapsedMs", True),
                           ("elapsedMs", -1), ("elapsedMs", 86_400_001),
                           ("payload", "PrivateFixtureValue")):
            item = copy.deepcopy(valid); item["events"][0][key] = value; bad.append(item)
        item = copy.deepcopy(valid); item["events"] *= 2; bad.append(item)
        item = copy.deepcopy(valid)
        item["events"] = [{"phase": "spawned", "elapsedMs": 2}, {"phase": "error", "elapsedMs": 1}]
        bad.extend([item, None, ["PrivateFixtureValue"]])
        with tempfile.TemporaryDirectory(prefix="ca-rpc-protocol-") as directory:
            root = Path(directory); trace = root / "missing-trace"; retained = root / "retained"
            with mock.patch.dict(os.environ, {"CA_PI_RPC_DIAGNOSTICS_DIR": str(retained)}):
                legacy = retain_rpc_shutdown_failure(trace)
                self.assertEqual(json.loads((retained / legacy).read_text(encoding="utf-8")),
                                 {"schemaVersion": 1, "outcome": "failure", "trace": None})
                name = retain_rpc_shutdown_failure(trace, protocol=valid)
                payload = (retained / name).read_bytes()
                self.assertLessEqual(len(payload), 8192)
                self.assertEqual(set(json.loads(payload)), {"schemaVersion", "outcome", "trace", "protocol"})
                self.assertEqual(json.loads(payload)["schemaVersion"], 2)
                self.assertEqual(json.loads(payload)["protocol"], valid)
                for item in bad:
                    with self.subTest(item=item):
                        self.assertIsNone(safe_rpc_protocol_report(item))
                        name = retain_rpc_shutdown_failure(trace, protocol=item)
                        payload = (retained / name).read_bytes()
                        self.assertIsNone(json.loads(payload)["protocol"])
                        self.assertNotIn(b"PrivateFixtureValue", payload)
                        self.assertLessEqual(len(payload), 8192)
                with mock.patch.object(tempfile, "NamedTemporaryFile", side_effect=ValueError("PrivateFixtureValue")):
                    self.assertIsNone(retain_rpc_shutdown_failure(trace, protocol=valid))

    @staticmethod
    def _shutdown_report(pid=731, exit_ms=2000):
        phases = ["started", "stdin_end", "session_shutdown_observer", "process_exit"]
        rows = [
            {"phase": phase, "elapsedMs": elapsed, "stdinEnded": index > 0, "resources": []}
            for index, (phase, elapsed) in enumerate(zip(phases, [0, 100, 101, exit_ms]))
        ]
        rows[-1]["exitCode"] = 0
        return {"schemaVersion": 1, "pid": pid, "node": "v22.19.0", "platform": "win32", "phases": rows}

    def test_rpc_shutdown_phase_requires_exact_order_identity_and_success(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-phase-") as directory:
            trace = Path(directory) / "trace.json"
            good = self._shutdown_report()
            trace.write_text(json.dumps(good), encoding="utf-8")
            self.assertTrue(rpc_shutdown_phase_complete(trace, 731))
            bad = []
            for field, value in (("pid", 732), ("pid", True), ("schemaVersion", True),
                                 ("schemaVersion", 2), ("phases", None)):
                candidate = copy.deepcopy(good)
                candidate[field] = value
                bad.append(candidate)
            for index in range(4):
                candidate = copy.deepcopy(good)
                candidate["phases"].pop(index)
                bad.append(candidate)
            for index, field, value in (
                (0, "phase", "process_exit"), (1, "stdinEnded", False),
                (2, "elapsedMs", 99), (2, "elapsedMs", -1),
                (2, "elapsedMs", True), (3, "exitCode", 1),
                (3, "exitCode", True), (3, "elapsedMs", 10_101),
            ):
                candidate = copy.deepcopy(good)
                candidate["phases"][index][field] = value
                bad.append(candidate)
            bad.extend([None, [], {"phases": "x" * 9000}])
            for candidate in bad:
                with self.subTest(candidate=candidate):
                    trace.write_text(json.dumps(candidate), encoding="utf-8")
                    self.assertFalse(rpc_shutdown_phase_complete(trace, 731))
            trace.write_bytes(b"\xff")
            self.assertFalse(rpc_shutdown_phase_complete(trace, 731))
            valid_bytes = json.dumps(good).encode("utf-8")
            trace.write_bytes(valid_bytes + b" " * (8192 - len(valid_bytes)))
            self.assertTrue(rpc_shutdown_phase_complete(trace, 731))
            trace.write_bytes(valid_bytes + b" " * (8193 - len(valid_bytes)))
            self.assertFalse(rpc_shutdown_phase_complete(trace, 731))
            for malformed in (b"{not-json}", b"[" * 2000 + b"]" * 2000):
                trace.write_bytes(malformed)
                self.assertFalse(rpc_shutdown_phase_complete(trace, 731))
            trace.write_bytes(valid_bytes)
            with mock.patch.object(json, "loads", side_effect=RecursionError("test-owned decoder failure")):
                self.assertFalse(rpc_shutdown_phase_complete(trace, 731))

    def _exercise_shutdown_clock(self, *, observed, phase_at, exit_at, phase_report=None):
        """Drive subprocess wait/trace timing without lengthening real regressions."""
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-budget-") as directory:
            trace = Path(directory) / "trace.json"
            clock = [0.0]
            waits = []
            process = mock.Mock(pid=731, args=["test-owned-process"])
            process.poll.side_effect = lambda: 0 if clock[0] >= exit_at else None

            def wait(timeout):
                waits.append(timeout)
                clock[0] = min(clock[0] + timeout, exit_at)
                if phase_at is not None and clock[0] >= phase_at:
                    trace.write_text(json.dumps(phase_report or self._shutdown_report()), encoding="utf-8")
                if clock[0] >= exit_at:
                    return 0
                raise subprocess.TimeoutExpired(process.args, timeout)

            process.wait.side_effect = wait
            with mock.patch.object(time, "monotonic", side_effect=lambda: clock[0]):
                try:
                    result = wait_for_rpc_shutdown(process, trace, observed=observed)
                except (AssertionError, subprocess.TimeoutExpired) as error:
                    return error, clock[0], waits
            return result, clock[0], waits

    def test_rpc_shutdown_budget_allows_cold_persistence_without_adding_another_thirty_seconds(self):
        result, elapsed, waits = self._exercise_shutdown_clock(
            observed=True, phase_at=2, exit_at=21.64,
        )
        self.assertEqual(result, 0)
        self.assertEqual(elapsed, 21.64)
        self.assertAlmostEqual(waits[-1], 28)

    def test_rpc_shutdown_budget_rejects_missing_late_and_unsuccessful_phase(self):
        wrong_exit = self._shutdown_report()
        wrong_exit["phases"][-1]["exitCode"] = 1
        for phase_at, exit_at, report in (
            (None, 1, None), (None, 100, None), (11, 22, None), (1, 2, wrong_exit),
        ):
            with self.subTest(phase_at=phase_at, exit_at=exit_at):
                result, elapsed, _ = self._exercise_shutdown_clock(
                    observed=True, phase_at=phase_at, exit_at=exit_at, phase_report=report,
                )
                self.assertIsInstance(result, AssertionError)
                self.assertLessEqual(elapsed, 10.001)

    def test_rpc_shutdown_budget_bounds_raw_and_post_exit_entry_hangs(self):
        for observed, phase_at in ((False, None), (False, 2), (True, 2)):
            with self.subTest(observed=observed):
                result, elapsed, _ = self._exercise_shutdown_clock(
                    observed=observed, phase_at=phase_at, exit_at=100,
                )
                self.assertIsInstance(result, subprocess.TimeoutExpired)
                self.assertAlmostEqual(elapsed, 30)

    def test_rpc_shutdown_observer_records_eof_and_exit_without_stdout_changes(self):
        node, _ = live_pi_cli()
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-observer-") as directory:
            root = Path(directory)
            preload, _, trace = write_rpc_shutdown_observer(root)
            result = subprocess.run(
                [node, "--require", str(preload), "-e",
                 "process.stdin.resume(); process.stdin.on('end', () => process.exit(0));"],
                input="", text=True, capture_output=True, timeout=10, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            report = read_json(trace)
            self.assertEqual([row["phase"] for row in report["phases"]],
                             ["started", "stdin_end", "process_exit"])
            self.assertIn('"stdin_end"', rpc_shutdown_diagnostics(trace))
            self.assertIn('"process_exit"', rpc_shutdown_diagnostics(trace))
            self.assertEqual(report["phases"][-1]["exitCode"], 0)

    def test_rpc_shutdown_observer_does_not_force_exit_on_eof(self):
        node, _ = live_pi_cli()
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-observer-passive-") as directory:
            preload, _, _ = write_rpc_shutdown_observer(Path(directory))
            result = subprocess.run(
                [node, "--require", str(preload), "-e",
                 "process.stdin.resume(); process.stdin.on('end', () => {"
                 "setTimeout(() => process.stdout.write('still-running'), 100);"
                 "setTimeout(() => process.exit(0), 200); });"],
                input="", text=True, capture_output=True, timeout=10, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "still-running")
            self.assertEqual(result.stderr, "")

    def test_rpc_shutdown_diagnostics_are_bounded_and_tolerate_missing_or_invalid_trace(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-observer-") as directory:
            trace = Path(directory) / "trace.json"
            self.assertEqual(rpc_shutdown_diagnostics(trace), "unavailable or invalid trace")
            trace.write_bytes(b"{" + b"x" * 20_000)
            self.assertEqual(rpc_shutdown_diagnostics(trace), "unavailable or invalid trace")
            trace.write_text(json.dumps({"large": "x" * 9000}), encoding="utf-8")
            self.assertEqual(rpc_shutdown_diagnostics(trace), "unavailable or invalid trace")
            trace.write_bytes(b"{}" + b" " * 9000)
            self.assertEqual(rpc_shutdown_diagnostics(trace), "unavailable or invalid trace")
            good = json.dumps(self._shutdown_report()).encode("utf-8")
            trace.write_bytes(good + b" " * (8192 - len(good)))
            self.assertIn('"process_exit"', rpc_shutdown_diagnostics(trace))
            trace.write_bytes(b"{not-json}")
            self.assertEqual(rpc_shutdown_diagnostics(trace), "unavailable or invalid trace")
            trace.write_bytes(b"\xff")
            self.assertEqual(rpc_shutdown_diagnostics(trace), "unavailable or invalid trace")
            trace.write_bytes(b"[]")
            self.assertEqual(rpc_shutdown_diagnostics(trace), "unavailable or invalid trace")
            trace.write_bytes(b"[" * 2000 + b"]" * 2000)
            self.assertEqual(rpc_shutdown_diagnostics(trace), "unavailable or invalid trace")
            trace.write_text(json.dumps({"phases": [{"phase": "stdin_end"}]}), encoding="utf-8")
            self.assertEqual(rpc_shutdown_diagnostics(trace), "unavailable or invalid trace")
            trace.write_text(json.dumps({"large": "x" * 3000}), encoding="utf-8")
            self.assertLessEqual(len(rpc_shutdown_diagnostics(trace)), 2000)

    def test_rpc_shutdown_failure_artifact_projects_only_safe_fields_and_is_exclusive(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-retained-") as directory:
            root = Path(directory)
            trace = root / "trace.json"
            report = self._shutdown_report()
            report["secret"] = "NOT_A_REAL_SECRET_FIXTURE"
            report["phases"][-1]["argv"] = "NOT_A_REAL_SECRET_FIXTURE"
            trace.write_text(json.dumps(report), encoding="utf-8")
            output = root / "artifacts"
            with mock.patch.dict(os.environ, {"CA_PI_RPC_DIAGNOSTICS_DIR": str(output)}):
                first = retain_rpc_shutdown_failure(trace)
                second = retain_rpc_shutdown_failure(trace)
            self.assertNotEqual(first, second)
            self.assertIsNotNone(first)
            raw = (output / first).read_text(encoding="utf-8")
            self.assertNotIn("NOT_A_REAL_SECRET_FIXTURE", raw)
            self.assertNotIn("NOT_A_REAL_SECRET_FIXTURE", rpc_shutdown_diagnostics(trace))
            self.assertEqual(json.loads(raw), {"schemaVersion": 1, "outcome": "failure", "trace": self._shutdown_report()})
            report["phases"][-1]["resources"] = ["PrivateFixtureValue", "PipeWrap"]
            trace.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(safe_rpc_shutdown_report(trace)["phases"][-1]["resources"], ["Other", "PipeWrap"])
            self.assertNotIn("PrivateFixtureValue", rpc_shutdown_diagnostics(trace))
            with mock.patch.dict(os.environ, {"CA_PI_RPC_DIAGNOSTICS_DIR": str(output)}):
                sanitized = retain_rpc_shutdown_failure(trace)
            self.assertNotIn("PrivateFixtureValue", (output / sanitized).read_text(encoding="utf-8"))
            for key, value in (("node", "NOT_A_REAL_SECRET_FIXTURE"), ("platform", "NOT_A_REAL_SECRET_FIXTURE"), ("pid", True)):
                candidate = self._shutdown_report()
                candidate[key] = value
                trace.write_text(json.dumps(candidate), encoding="utf-8")
                self.assertIsNone(safe_rpc_shutdown_report(trace))
                self.assertNotIn("NOT_A_REAL_SECRET_FIXTURE", rpc_shutdown_diagnostics(trace))
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertIsNone(retain_rpc_shutdown_failure(trace))
            with mock.patch.dict(os.environ, {"CA_PI_RPC_DIAGNOSTICS_DIR": str(trace)}):
                self.assertIsNone(retain_rpc_shutdown_failure(trace))

    def test_rpc_compile_cache_opt_out_is_target_local(self):
        import _windows_rpc_timeout as native
        cases = (
            (None, False, False),      # Standalone and installed observer owner
            (None, True, True),        # Explicit diagnostic companion
            ("rpc", False, os.name == "nt"),
            ("package", False, False),
        )
        for partition, observed, expected_cache_opt_out in cases:
            with self.subTest(partition=partition, observed=observed), tempfile.TemporaryDirectory(prefix="ca-rpc-cache-scope-") as directory:
                root = Path(directory).resolve()
                agent, home = root / "agent", root / "home"
                node, cli = "owned-node-stub", root / "owned-cli.js"
                installation_environments, target_environments = [], []
                original_environment = dict(os.environ)

                def configure_package(argv, **kwargs):
                    self.assertEqual(argv, [node, str(cli), "install", str(root), "--no-approve"])
                    installation_environments.append(dict(kwargs["env"]))
                    (agent / "settings.json").write_text(json.dumps({"packages": ["owned-fixture"]}), encoding="utf-8")
                    return subprocess.CompletedProcess(argv, 0, "", "")

                class LaunchBoundaryReached(Exception):
                    pass

                def launch(_argv, **kwargs):
                    target_environments.append(dict(kwargs["env"]))
                    raise LaunchBoundaryReached()

                with (mock.patch.object(sys.modules[__name__], "PLATFORM_PACKAGE_PARTITION", partition),
                      mock.patch.object(sys.modules[__name__], "live_pi_cli", return_value=(node, cli)),
                      mock.patch.object(subprocess, "run", side_effect=configure_package),
                      mock.patch.object(subprocess, "Popen", side_effect=launch),
                      mock.patch.object(native, "preflight_provider", return_value=None),
                      self.assertRaises(LaunchBoundaryReached)):
                    run_rpc_commands(root, agent, home, package_source=root, _observe_shutdown=observed)
                self.assertEqual(len(installation_environments), 1)
                self.assertEqual(len(target_environments), 1)
                self.assertNotIn("NODE_DISABLE_COMPILE_CACHE", installation_environments[0])
                self.assertEqual(target_environments[0].get("NODE_DISABLE_COMPILE_CACHE"),
                                 "1" if expected_cache_opt_out else None)
                self.assertTrue(dict(os.environ) == original_environment, "RPC target must not mutate parent environment")

    def test_rpc_read_context_observer_preserves_raw_provider_route(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-read-context-observer-") as directory:
            root = Path(directory).resolve()
            agent = root / "agent"
            home = root / "home"
            provider = home / "ca-task3-capture-provider.ts"
            node, cli = "owned-node-stub", root / "owned-pi-cli-stub.js"

            def configure_package(argv, **_kwargs):
                self.assertEqual(argv, [node, str(cli), "install", str(root), "--no-approve"])
                (agent / "settings.json").write_text(
                    json.dumps({"packages": ["owned-fixture"]}), encoding="utf-8",
                )
                return subprocess.CompletedProcess(argv, 0, "", "")

            class LaunchBoundaryReached(Exception):
                pass

            with (
                mock.patch.object(sys.modules[__name__], "live_pi_cli", return_value=(node, cli)),
                mock.patch.object(subprocess, "run", side_effect=configure_package),
                mock.patch.object(subprocess, "Popen", side_effect=LaunchBoundaryReached) as launch,
                mock.patch.object(
                    sys.modules[__name__], "write_rpc_shutdown_observer",
                    side_effect=AssertionError("the read-context provider needs no preload"),
                ),
                self.assertRaises(LaunchBoundaryReached),
            ):
                run_rpc_commands(
                    root, agent, home, package_source=root, invoke_read_context=True,
                    governed_read_path=root / "governed.txt", ungoverned_read_path=root / "ungoverned.txt",
                )

            launch.assert_called_once()
            self.assertEqual(launch.call_args.args[0], [
                node, str(cli), "--mode", "rpc", "--offline", "--no-session", "--approve",
                "--no-prompt-templates", "--no-themes", "--no-context-files",
                "--extension", str(provider), "--provider", "ca-read-context",
                "--model", "ca-read-context-model", "--api-key", "test-only-no-network",
            ])
            source = provider.read_text(encoding="utf-8")
            self.assertIn(
                "globalThis.__caPiRpcShutdownObserve = observe;", source,
                "raw read-context provider did not install the passive child observer",
            )
            self.assertIn(json.dumps(str(home / "ca-rpc-shutdown-trace.json")), source)
            handler = "pi.on('session_shutdown'"
            self.assertEqual(source.count(handler), 1)
            self.assertLess(source.index("pi.registerProvider('ca-read-context'"), source.index(handler))

    def test_rpc_embedded_observer_is_passive_and_keeps_stdout_clean(self):
        node, _ = live_pi_cli()
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-embedded-") as directory:
            trace = Path(directory) / "trace.json"
            source = rpc_shutdown_observer_source(trace, module=True)
            source += "process.stdin.resume(); process.stdin.on('end', () => { setTimeout(() => { process.stdout.write('still-running'); process.exit(0); }, 100); });"
            result = subprocess.run([node, "--input-type=module", "-e", source], input="", text=True, capture_output=True, timeout=10, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "still-running")
            self.assertEqual(result.stderr, "")
            self.assertEqual([x["phase"] for x in safe_rpc_shutdown_report(trace)["phases"]], ["started", "stdin_end", "process_exit"])

    def test_rpc_shutdown_observer_never_turns_an_eof_hang_into_a_pass(self):
        node, _ = live_pi_cli()
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-observer-hang-") as directory:
            root = Path(directory)
            cwd = root / "cwd"
            home = root / "home"
            cwd.mkdir()
            home.mkdir()
            preload, _, trace = write_rpc_shutdown_observer(home)
            observed = []
            child_code = (
                "process.stdin.once('data', () => process.stdout.write("
                "JSON.stringify({id:'commands',success:true,data:{commands:[]}})+'\\n'));"
                "process.stdin.on('end', () => setInterval(() => {}, 1000));"
            )
            retained = root / "retained"
            with mock.patch.dict(os.environ, {"CA_PI_RPC_DIAGNOSTICS_DIR": str(retained)}), self.assertRaisesRegex(AssertionError, "orderly shutdown did not complete") as raised:
                run_rpc_commands(
                    cwd, root / "agent", home,
                    _rpc_command=[node, "--require", str(preload), "-e", child_code],
                    _on_process_started=lambda process, reader: observed.append((process, reader)),
                    _observe_shutdown=True,
                )
            self.assertIn('"stdin_end"', str(raised.exception))
            self.assertNotIn('"process_exit"', str(raised.exception))
            self.assertEqual(len(observed), 1)
            process, reader = observed[0]
            self.assertIsNotNone(process.poll(), "the failing RPC root must be reaped")
            self.assertFalse(reader.is_alive(), "the failing RPC stdout reader must stop")
            self.assertIn('"stdin_end"', rpc_shutdown_diagnostics(trace))
            artifacts = list(retained.glob("rpc-shutdown-*.json"))
            self.assertEqual(len(artifacts), 1)
            self.assertEqual(read_json(artifacts[0])["outcome"], "failure")
            self.assertEqual(read_json(artifacts[0])["trace"]["phases"][-1]["phase"], "stdin_end")
            self.assertTrue(any(artifacts[0].name in note for note in raised.exception.__notes__))

    def test_rpc_post_exit_entry_hang_reaps_process_tree_and_readers(self):
        node, _ = live_pi_cli()
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-exit-hang-") as directory:
            root = Path(directory)
            cwd, home = root / "cwd", root / "home"
            cwd.mkdir()
            home.mkdir()
            preload, _, trace = write_rpc_shutdown_observer(home)
            child_marker = root / "child-pid.txt"
            observed = []
            code = (
                "const {spawn}=require('node:child_process');"
                "const {writeFileSync}=require('node:fs');"
                "const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],"
                "{stdio:['ignore',1,2]});"
                f"writeFileSync({json.dumps(str(child_marker))},String(child.pid));"
                "process.stdin.once('data',()=>process.stdout.write("
                "JSON.stringify({id:'commands',success:true,data:{commands:[]}})+'\\n'));"
                "process.stdin.on('end',()=>{"
                "globalThis.__caPiRpcShutdownObserve('session_shutdown_observer');process.exit(0);});"
                "process.on('exit',()=>Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0));"
            )
            with self.assertRaisesRegex(AssertionError, "did not exit within 30 seconds"):
                run_rpc_commands(
                    cwd, root / "agent", home,
                    _rpc_command=[node, "--require", str(preload), "-e", code],
                    _on_process_started=lambda process, reader: observed.append((process, reader)),
                    _observe_shutdown=True,
                )
            self.assertEqual(len(observed), 1)
            process, reader = observed[0]
            self.assertTrue(rpc_shutdown_phase_complete(trace, process.pid))
            self.assertIsNotNone(process.poll(), "post-exit-entry hang must reap the RPC root")
            self.assertFalse(reader.is_alive(), "descendant-held stdout must close after cleanup")
            child_pid = int(child_marker.read_text(encoding="utf-8"))
            if os.name == "nt":
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {child_pid}", "/FO", "CSV", "/NH"],
                    text=True, encoding="utf-8", errors="replace", capture_output=True,
                    timeout=5, check=False,
                )
                self.assertNotIn(f',"{child_pid}",', result.stdout)
            else:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    try:
                        os.kill(child_pid, 0)
                    except ProcessLookupError:
                        break
                    time.sleep(0.02)
                else:
                    self.fail("post-exit-entry hang left a descendant alive")

    def test_rpc_observed_raw_identity_and_artifact_are_bounded_and_closed(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-observed-record-") as directory:
            root = Path(directory)
            cli = root / "cli.js"
            node = root / "node.exe"
            entry = root / "cli-runtime.js"
            runtime = root / "chunks" / "chunk-fixture.js"
            runtime.parent.mkdir()
            for path in (cli, node, runtime):
                path.write_bytes(b"owned non-executable identity fixture")
            entry.write_bytes(b'import{configureHttpDispatcher,main}from"./chunks/chunk-fixture.js";')
            identity = rpc_diagnostic_runtime_identity(str(node), cli)
            self.assertEqual(identity, {
                name: hashlib.sha256(path.read_bytes()).hexdigest()
                for name, path in {"nodeSha256": node, "cliSha256": cli,
                                   "entrySha256": entry, "rpcModuleSha256": runtime}.items()
            })
            trace = root / "trace.json"
            report = self._shutdown_report()
            report["private"] = "PrivateFixtureValue"
            report["phases"][0]["resources"] = ["PrivateFixtureValue"]
            trace.write_text(json.dumps(report), encoding="utf-8")
            retained = root / "retained"
            with mock.patch.dict(os.environ, {"CA_PI_RPC_DIAGNOSTICS_DIR": str(retained)}):
                one = retain_rpc_observed_raw_diagnostics(trace, identity, succeeded=True)
                two = retain_rpc_observed_raw_diagnostics(trace, {**identity, "private": "PrivateFixtureValue"}, succeeded=False)
            self.assertNotEqual(one, two)
            first = read_json(retained / one)
            second = read_json(retained / two)
            self.assertEqual(set(first), {"schemaVersion", "route", "outcome", "runtimeIdentity", "trace"})
            self.assertEqual(first["route"], "passive-observed-raw-companion")
            self.assertEqual(first["outcome"], "observed-pass")
            self.assertEqual(first["runtimeIdentity"], identity)
            self.assertEqual(first["trace"]["phases"][0]["resources"], ["Other"])
            self.assertEqual(second["outcome"], "observed-failure")
            self.assertIsNone(second["runtimeIdentity"])
            self.assertNotIn("PrivateFixtureValue", (retained / one).read_text(encoding="utf-8"))
            self.assertNotIn("PrivateFixtureValue", (retained / two).read_text(encoding="utf-8"))
            entry.write_bytes(b'import{configureHttpDispatcher,main}from"../outside.js";')
            self.assertIsNone(rpc_diagnostic_runtime_identity(str(node), cli))
            entry.write_bytes(b"x" * 16_385)
            self.assertIsNone(rpc_diagnostic_runtime_identity(str(node), cli))
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertIsNone(retain_rpc_observed_raw_diagnostics(trace, identity, succeeded=True))

    def test_real_rpc_raw_compatibility_path_keeps_the_original_cli_arguments(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-raw-") as directory:
            root = Path(directory)
            cwd = root / "cwd"
            cwd.mkdir()
            observed = []
            with mock.patch.object(
                sys.modules[__name__], "write_rpc_shutdown_observer",
                side_effect=AssertionError("raw compatibility path must not inject an observer"),
            ):
                records = run_rpc_commands(
                    cwd, root / "agent", root / "home",
                    _on_process_started=lambda process, reader: observed.append(process.args),
                )
            self.assertTrue(records[0]["success"])
            self.assertEqual(len(observed), 1)
            self.assertNotIn("--require", observed[0])
            self.assertFalse(any("ca-rpc-shutdown-observer" in argument for argument in observed[0]))

    def test_real_rpc_passive_observed_raw_companion_retains_runtime_and_phases(self):
        # Separate from the original raw argv/natural-exit qualification above.
        # A pass here does not resolve or replace a failure in that original case.
        node, cli = live_pi_cli()
        identity = rpc_diagnostic_runtime_identity(node, cli)
        self.assertIsNotNone(identity, "the diagnostic must identify the actual direct RPC runtime")
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-raw-observed-") as directory:
            root = Path(directory)
            cwd = root / "cwd"
            cwd.mkdir()
            observed = []
            succeeded = False
            try:
                records = run_rpc_commands(
                    cwd, root / "agent", root / "home", _observe_shutdown=True,
                    _on_process_started=lambda process, reader: observed.append(process.args),
                )
                self.assertTrue(records[0]["success"])
                self.assertEqual(len(observed), 1)
                expected = [node, "--require", str(root / "home/ca-rpc-shutdown-observer.cjs"),
                            str(cli), "--mode", "rpc", "--offline", "--no-session", "--approve",
                            "--no-prompt-templates", "--no-themes", "--no-context-files",
                            "--extension", str(root / "home/ca-rpc-shutdown-observer.ts"),
                            "--no-builtin-tools"]
                self.assertEqual(observed[0], expected)
                report = safe_rpc_shutdown_report(root / "home/ca-rpc-shutdown-trace.json")
                self.assertEqual([row["phase"] for row in report["phases"]],
                                 ["started", "stdin_end", "session_shutdown_observer", "process_exit"])
                self.assertEqual(report["phases"][-1]["exitCode"], 0)
                succeeded = True
            finally:
                retain_rpc_observed_raw_diagnostics(
                    root / "home/ca-rpc-shutdown-trace.json", identity, succeeded=succeeded,
                )

    def test_rpc_stderr_backpressure_does_not_block_shutdown(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-stderr-") as directory:
            root = Path(directory)
            cwd = root / "cwd"
            cwd.mkdir()
            child_code = (
                "import json, sys; "
                "sys.stdin.readline(); "
                "print(json.dumps({'id':'commands','success':True,'data':{'commands':[]}}),flush=True); "
                "sys.stderr.write('x' * 262144); sys.stderr.flush(); "
                "sys.stdin.read()"
            )
            records = run_rpc_commands(
                cwd,
                root / "agent",
                root / "home",
                _rpc_command=[sys.executable, "-c", child_code],
            )
            self.assertEqual([record["id"] for record in records], ["commands"])
            self.assertTrue(records[0]["success"])


class NpmPublishContractTest(unittest.TestCase):
    """ADR-0029 / spec npm-publish-ca-pi: the npm channel ships the same payload
    the Git install serves, synchronously inside the release workflow."""

    WORKFLOW = REPO / ".github" / "workflows" / "release.yml"
    ACTION = REPO / ".github" / "actions" / "publish-target" / "action.yml"

    HELPER = REPO / ".github" / "scripts" / "_npm_publishlib.py"

    def _helper(self):
        self.assertTrue(
            self.HELPER.is_file(),
            "the npm publisher has no executable fail-closed verifier",
        )
        spec = importlib.util.spec_from_file_location("_npm_publishlib", self.HELPER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_npm_pack_contents_match_pi_payload(self):
        # AC-2: the tarball is exactly the Pi-served payload — offline dry-run.
        npm = shutil.which("npm")
        self.assertIsNotNone(npm, "npm is a prerequisite of the package suite")
        completed = subprocess.run(
            [npm, "pack", "--dry-run", "--json"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        report = json.loads(completed.stdout)
        paths = {entry["path"].replace("\\", "/") for entry in report[0]["files"]}
        for required in (
            "package.json",
            "LICENSE",
            "plugins/ca-pi/SKILLS.md",
            "plugins/ca-pi/package.json",
            "plugins/ca-pi/extensions/codearbiter.js",
            "plugins/ca-pi/helpers/windows-supervisor.js",
        ):
            self.assertIn(required, paths)
        self.assertTrue(any(path.startswith("plugins/ca-pi/skills/") for path in paths))
        self.assertTrue(any(path.startswith("plugins/ca-pi/generated/") for path in paths))
        self.assertTrue(any(path.startswith("plugins/ca-pi/hooks/") for path in paths))
        for excluded_prefix in (
            "plugins/ca-pi/tools/",
            "plugins/ca/",
            "plugins/ca-codex/",
            "plugins/ca-sandbox/",
            "core/",
            "site/",
            ".github/",
            ".codearbiter/",
        ):
            leaked = sorted(path for path in paths if path.startswith(excluded_prefix))
            self.assertEqual(leaked, [], f"tarball leaks {excluded_prefix}")

    def test_publish_inputs_reject_ref_injection_and_noncanonical_sha(self):
        helper = self._helper()
        for tag in (
            "ca-pi-v0.10.0;echo owned",
            "refs/heads/main",
            "ca-pi-v01.2.3",
            "ca-pi-v1.2",
            "ca-pi-v1.2.3-rc.1",
        ):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                helper.validate_inputs(tag, "a" * 40)
        for sha in ("A" * 40, "a" * 39, "../" + "a" * 40):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                helper.validate_inputs("ca-pi-v0.10.0", sha)
        self.assertEqual(
            helper.validate_inputs("ca-pi-v0.10.0", "a" * 40), "0.10.0"
        )

    def test_package_identity_requires_both_manifests_and_public_repository(self):
        helper = self._helper()
        root = {
            "name": "@arbiterforge/ca-pi",
            "version": "0.10.0",
            "repository": {
                "type": "git",
                "url": "git+https://github.com/arbiterForge/codeArbiter.git",
            },
            "publishConfig": {"access": "public", "provenance": True},
        }
        nested = {"name": "@arbiterforge/ca-pi", "version": "0.10.0", "private": True}
        helper.validate_package_identity(root, nested, "0.10.0")
        mutations = (
            ({**root, "name": "ca-pi"}, nested),
            ({**root, "version": "0.9.9"}, nested),
            (root, {**nested, "version": "0.9.9"}),
            (root, {**nested, "name": "@attacker/other"}),
            (root, {**nested, "private": False}),
            ({**root, "repository": "https://example.invalid/repo"}, nested),
            ({**root, "publishConfig": {"registry": "https://evil.invalid"}}, nested),
        )
        for changed_root, changed_nested in mutations:
            with self.subTest(root=changed_root), self.assertRaises(ValueError):
                helper.validate_package_identity(changed_root, changed_nested, "0.10.0")

    def test_project_registry_configuration_cannot_redirect_publication(self):
        helper = self._helper()
        self.assertTrue(
            hasattr(helper, "validate_project_registry"),
            "the publisher has no testable project-registry guard",
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            helper.validate_project_registry(repo)
            (repo / ".npmrc").write_text("registry=https://evil.invalid/\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                helper.validate_project_registry(repo)

    def test_lookup_can_mark_attestation_pending_while_readback_retries(self):
        # Readback may classify a same-integrity version without attestation as
        # pending. The Pi action waits for "present" and fails on timeout.
        helper = self._helper()
        unattested = json.dumps({"version": "0.10.0", "dist": {"integrity": "sha512-ok"}})
        self.assertEqual(
            helper.classify_registry_lookup(0, unattested, "", "0.10.0", "sha512-ok",
                                            require_attestation=False),
            "present-unattested")
        with self.assertRaises(ValueError):
            helper.classify_registry_lookup(0, unattested, "", "0.10.0", "sha512-ok")
        for document, version, integrity in (
            ({"version": "0.10.0", "dist": {"integrity": "sha512-other"}}, "0.10.0", "sha512-ok"),
            ({"version": "0.9.9", "dist": {"integrity": "sha512-ok"}}, "0.10.0", "sha512-ok"),
        ):
            with self.subTest(document=document), self.assertRaises(ValueError):
                helper.classify_registry_lookup(0, json.dumps(document), "", version, integrity,
                                                require_attestation=False)

    def test_registry_lookup_distinguishes_absence_from_failure_and_requires_proof(self):
        helper = self._helper()
        expected = "sha512-expected"
        self.assertEqual(
            helper.classify_registry_lookup(
                1,
                '{"error":{"code":"E404"}}',
                "npm error code E404",
                "0.10.0",
                expected,
            ),
            "absent",
        )
        for stderr in (
            "npm error code E401",
            "npm error code E401\nHTTP 503 Service Unavailable",
            "npm error code E404\nnpm error code E401",
            "npm error code E404",
            "npm error code EUSAGE",
            "permanent command failure",
        ):
            with self.subTest(stderr=stderr), self.assertRaises(ValueError) as caught:
                helper.classify_registry_lookup(1, "", stderr, "0.10.0", expected)
            self.assertIs(type(caught.exception), ValueError)
        for stderr in (
            "npm error code E429",
            "npm error code E500",
            "npm error code E502",
            "npm error code E503",
            "npm error code E504",
            "npm error code EAI_FAIL",
            "npm error code ERR_SOCKET_TIMEOUT",
            "npm error code ETIMEDOUT",
            "npm error code ECONNRESET",
            "HTTP 503 Service Unavailable",
        ):
            with self.subTest(stderr=stderr), self.assertRaises(
                helper.RegistryUnavailable
            ):
                helper.classify_registry_lookup(1, "", stderr, "0.10.0", expected)
        with self.assertRaises(ValueError):
            helper.classify_registry_lookup(
                1,
                '{"error":{"code":"E404"}}',
                "npm error code E404\nnpm error code E401",
                "0.10.0",
                expected,
            )
        matching = json.dumps(
            {
                "version": "0.10.0",
                "dist": {
                    "integrity": expected,
                    "attestations": {
                        "url": "https://registry.npmjs.org/-/npm/v1/attestations/@arbiterforge%2fca-pi@0.10.0",
                        "provenance": {
                            "predicateType": "https://slsa.dev/provenance/v1"
                        }
                    },
                },
            }
        )
        self.assertEqual(
            helper.classify_registry_lookup(0, matching, "", "0.10.0", expected),
            "present",
        )
        for mutation in (
            {"version": "0.9.9", "dist": json.loads(matching)["dist"]},
            {"version": "0.10.0", "dist": {"integrity": "sha512-other"}},
            {"version": "0.10.0", "dist": {"integrity": expected}},
            {
                "version": "0.10.0",
                "dist": {
                    **json.loads(matching)["dist"],
                    "attestations": {
                        **json.loads(matching)["dist"]["attestations"],
                        "url": "https://evil.invalid/attestation",
                    },
                },
            },
            {
                "version": "0.10.0",
                "dist": {
                    **json.loads(matching)["dist"],
                    "attestations": {
                        **json.loads(matching)["dist"]["attestations"],
                        "provenance": {"predicateType": "https://example.invalid/predicate"},
                    },
                },
            },
        ):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                helper.classify_registry_lookup(
                    0, json.dumps(mutation), "", "0.10.0", expected
                )

    def test_registry_lookup_and_readback_are_time_bounded(self):
        helper = self._helper()
        parsed = helper.parser().parse_args(
            [
                "verify",
                "--tag", "ca-pi-v0.10.0",
                "--expected-sha", "a" * 40,
                "--trusted-sha", "a" * 40,
                "--integrity", "sha512-expected",
                "--publication-mode", "new",
            ]
        )
        self.assertEqual(parsed.attempts, 120)
        self.assertEqual(parsed.delay_seconds, 5.0)
        self.assertEqual(parsed.readback_seconds, 10 * 60.0)
        self.assertGreaterEqual(
            (parsed.attempts - 1) * parsed.delay_seconds,
            9 * 60,
            "a successful npm publish needs a bounded multi-minute processing window",
        )

        with mock.patch.object(
            helper.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["npm", "view"], 30),
        ) as run:
            with self.assertRaisesRegex(helper.RegistryUnavailable, "timed out"):
                helper.registry_lookup("npm", "0.10.0")
        self.assertIn(helper.SCOPED_REGISTRY_OPTION, run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["timeout"], 30)
        absent = subprocess.CompletedProcess(
            ["npm"],
            1,
            '{"error":{"code":"E404"}}',
            "npm error code E404",
        )
        args = argparse.Namespace(
            tag="ca-pi-v0.10.0",
            expected_sha="a" * 40,
            trusted_sha="a" * 40,
            npm="npm",
            integrity="sha512-expected",
            attempts=2,
            delay_seconds=0,
            repo=".",
            publication_mode="new",
        )
        with mock.patch.object(helper, "validate_release_source_binding"), \
                mock.patch.object(helper, "registry_lookup", return_value=absent):
            with self.assertRaisesRegex(ValueError, "evidence deadline"):
                helper.verify(args)

        deadline_args = argparse.Namespace(**vars(args), readback_seconds=10.0)
        with mock.patch.object(helper, "validate_release_source_binding"), \
                mock.patch.object(
                    helper.time, "monotonic", side_effect=(100.0, 109.0, 111.0, 112.0)
                ), \
                mock.patch.object(helper.time, "sleep") as sleep, \
                mock.patch.object(helper, "registry_lookup", return_value=absent) as lookup:
            with self.assertRaisesRegex(ValueError, "evidence deadline"):
                helper.verify(deadline_args)
        self.assertEqual(lookup.call_args.kwargs["timeout"], 1.0)
        sleep.assert_not_called()

    def test_registry_transport_failures_retry_but_evidence_mismatches_fail_fast(self):
        helper = self._helper()
        args = argparse.Namespace(
            tag="ca-pi-v0.10.0",
            expected_sha="a" * 40,
            trusted_sha="a" * 40,
            npm="npm",
            integrity="sha512-expected",
            publication_mode="new",
            repo=".",
            attempts=3,
            delay_seconds=0,
        )
        unavailable = subprocess.CompletedProcess(
            ["npm"], 1, "", "npm error code ETIMEDOUT"
        )
        with mock.patch.object(helper, "validate_release_source_binding"), \
                mock.patch.object(helper, "registry_lookup", return_value=unavailable) as lookup:
            with self.assertRaisesRegex(helper.RegistryUnavailable, "unavailable"):
                helper.verify(args)
        self.assertEqual(lookup.call_count, 3)

        permanent = subprocess.CompletedProcess(
            ["npm"], 1, "", "npm error code EUSAGE"
        )
        with mock.patch.object(helper, "validate_release_source_binding"), \
                mock.patch.object(helper, "registry_lookup", return_value=permanent) as lookup:
            with self.assertRaisesRegex(ValueError, "without a confirmed 404"):
                helper.verify(args)
        self.assertEqual(lookup.call_count, 1)

        mismatch = subprocess.CompletedProcess(
            ["npm"],
            0,
            json.dumps({"version": "0.9.9", "dist": {}}),
            "",
        )
        with mock.patch.object(helper, "validate_release_source_binding"), \
                mock.patch.object(helper, "registry_lookup", return_value=mismatch) as lookup:
            with self.assertRaisesRegex(ValueError, "version does not match"):
                helper.verify(args)
        self.assertEqual(lookup.call_count, 1)

        present = subprocess.CompletedProcess(
            ["npm"],
            0,
            json.dumps(
                {
                    "version": "0.10.0",
                    "dist": {
                        "integrity": "sha512-expected",
                        "attestations": {
                            "url": "https://registry.npmjs.org/-/npm/v1/attestations/@arbiterforge%2fca-pi@0.10.0",
                            "provenance": {
                                "predicateType": "https://slsa.dev/provenance/v1"
                            },
                        },
                    },
                }
            ),
            "",
        )
        with mock.patch.object(helper, "validate_release_source_binding"), mock.patch.object(helper, "registry_lookup", return_value=present) as lookup, mock.patch.object(
            helper,
            "verify_registry_authenticity",
            side_effect=ValueError("invalid cryptographic evidence"),
        ) as authenticity:
            with self.assertRaisesRegex(ValueError, "invalid cryptographic evidence"):
                helper.verify(args)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(authenticity.call_count, 1)

    def test_attestation_evidence_comes_only_from_the_npm_verifier(self):
        helper = self._helper()
        self.assertFalse(hasattr(helper, "attestation_lookup"))
        source = Path(helper.__file__).read_text(encoding="utf-8")
        self.assertNotIn("urllib", source)
        self.assertNotIn("urlopen", source)

    def test_pack_report_rejects_output_injection_and_malformed_integrity(self):
        helper = self._helper()
        good = [{"filename": "arbiterforge-ca-pi-0.10.0.tgz", "integrity": "sha512-YWJjZA=="}]
        self.assertEqual(
            helper.parse_pack_report(json.dumps(good)),
            ("arbiterforge-ca-pi-0.10.0.tgz", "sha512-YWJjZA=="),
        )
        for report in (
            [{"filename": "$(owned).tgz", "integrity": "sha512-YWJjZA=="}],
            [{"filename": "safe.tgz", "integrity": 'sha512-good";echo owned'}],
            {"filename": "safe.tgz", "integrity": "sha512-YWJjZA=="},
        ):
            with self.subTest(report=report), self.assertRaises(ValueError):
                helper.parse_pack_report(json.dumps(report))

    def test_attestation_bundle_binds_subject_and_github_source_identity(self):
        helper = self._helper()
        version = "0.10.0"
        trusted_sha = "a" * 40
        digest_hex = "ab" * 64
        integrity = "sha512-" + base64.b64encode(bytes.fromhex(digest_hex)).decode("ascii")
        statement = {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": [
                {
                    "name": "pkg:npm/%40arbiterforge/ca-pi@0.10.0",
                    "digest": {"sha512": digest_hex},
                }
            ],
            "predicateType": "https://slsa.dev/provenance/v1",
            "predicate": {
                "buildDefinition": {
                    "externalParameters": {
                        "workflow": {
                            "repository": "https://github.com/arbiterForge/codeArbiter",
                            "ref": "refs/heads/main",
                            "path": ".github/workflows/release.yml",
                        }
                    },
                    "resolvedDependencies": [
                        {
                            "uri": "git+https://github.com/arbiterForge/codeArbiter@refs/heads/main",
                            "digest": {"gitCommit": trusted_sha},
                        }
                    ],
                },
                "runDetails": {
                    "builder": {
                        "id": "https://github.com/actions/runner/github-hosted"
                    }
                },
            },
        }

        def document(value):
            payload = base64.b64encode(
                json.dumps(value, separators=(",", ":")).encode("utf-8")
            ).decode("ascii")
            return {
                "attestations": [
                    {
                        "predicateType": "https://slsa.dev/provenance/v1",
                        "bundle": {"dsseEnvelope": {"payload": payload}},
                    }
                ]
            }

        self.assertEqual(
            helper.validate_attestation_document(
                document(statement), version, integrity, trusted_sha
            ),
            trusted_sha,
        )
        self.assertEqual(
            helper.validate_attestation_document(
                document(statement), version, integrity, trusted_sha,
                source_workflows=helper.PI_RELEASE_WORKFLOWS,
            ),
            trusted_sha,
        )
        wrong_workflow = json.loads(json.dumps(statement))
        wrong_workflow["predicate"]["buildDefinition"]["externalParameters"]["workflow"]["path"] = (
            ".github/workflows/npm-publish.yml"
        )
        with self.assertRaisesRegex(ValueError, "workflow identity"):
            helper.validate_attestation_document(
                document(wrong_workflow), version, integrity, trusted_sha,
                source_workflows=helper.PI_RELEASE_WORKFLOWS,
            )
        self.assertEqual(
            helper.validate_publication_attestation(
                document(statement), version, integrity,
                release_source_sha=trusted_sha, trusted_sha=trusted_sha,
                trusted_repo=Path("."), allow_continuation=False,
                source_workflows=helper.PI_RELEASE_WORKFLOWS,
            ),
            trusted_sha,
        )
        prior_commit = json.loads(json.dumps(statement))
        prior_commit["predicate"]["buildDefinition"]["resolvedDependencies"][0]["digest"]["gitCommit"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "trusted workflow commit"):
            helper.validate_publication_attestation(
                document(prior_commit), version, integrity,
                release_source_sha=trusted_sha, trusted_sha=trusted_sha,
                trusted_repo=Path("."), allow_continuation=False,
                source_workflows=helper.PI_RELEASE_WORKFLOWS,
            )
        with self.assertRaisesRegex(ValueError, "workflow identity"):
            helper.validate_publication_attestation(
                document(wrong_workflow), version, integrity,
                release_source_sha=trusted_sha, trusted_sha=trusted_sha,
                trusted_repo=Path("."), allow_continuation=False,
                source_workflows=helper.PI_RELEASE_WORKFLOWS,
            )
        mutations = []
        for path, replacement in (
            (("subject", 0, "name"), "pkg:npm/%40attacker/other@0.10.0"),
            (("subject", 0, "digest", "sha512"), "00" * 64),
            (("predicate", "buildDefinition", "externalParameters", "workflow", "repository"), "https://github.com/attacker/repo"),
            (("predicate", "buildDefinition", "externalParameters", "workflow", "ref"), "refs/heads/evil"),
            (("predicate", "buildDefinition", "externalParameters", "workflow", "path"), ".github/workflows/evil.yml"),
            (("predicate", "buildDefinition", "resolvedDependencies", 0, "digest", "gitCommit"), "b" * 40),
            (("predicate", "runDetails", "builder", "id"), "https://attacker.invalid/runner"),
        ):
            changed = json.loads(json.dumps(statement))
            cursor = changed
            for segment in path[:-1]:
                cursor = cursor[segment]
            cursor[path[-1]] = replacement
            mutations.append(changed)
        for changed in mutations:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                helper.validate_attestation_document(
                    document(changed), version, integrity, trusted_sha
                )

    def test_registry_authenticity_failure_has_safe_actionable_diagnostics(self):
        helper = self._helper()
        installed = subprocess.CompletedProcess(["npm", "install"], 0, "", "")
        hostile = "PRIVATE-VALUE\n::warning::injected https://user:pass@invalid/"
        cases = (
            ({"invalid": [{"code": "EATTESTATIONVERIFY", "message": hostile}], "missing": []},
             "invalid=EATTESTATIONVERIFY"),
            ({"invalid": [{"code": "EINTEGRITYSIGNATURE", "name": hostile}], "missing": []},
             "invalid=EINTEGRITYSIGNATURE"),
            ({"invalid": [], "missing": [hostile]}, "missing=yes"),
            ({"error": {"code": "E503", "summary": hostile}}, "error=E503"),
            ({"error": {"code": hostile}}, "error=unknown"),
        )
        for evidence, expected in cases:
            with self.subTest(expected=expected):
                audited = subprocess.CompletedProcess(
                    ["npm", "audit", "signatures"], 1, json.dumps(evidence), hostile
                )
                with mock.patch.object(helper.subprocess, "run", side_effect=[installed, audited]), \
                        self.assertRaises(ValueError) as failure:
                    helper.verify_registry_authenticity("npm", "0.10.0")
                diagnostic = str(failure.exception)
                self.assertIn(expected, diagnostic)
                self.assertNotIn("PRIVATE-VALUE", diagnostic)
                self.assertNotIn("::warning::", diagnostic)
                self.assertNotIn("user:pass", diagnostic)
                self.assertLessEqual(len(diagnostic), 256)

    def test_signature_diagnostics_bound_and_classify_malformed_evidence(self):
        helper = self._helper()
        cases = (
            (None, "schema=invalid"),
            ([], "schema=invalid"),
            ({"invalid": None}, "invalid=malformed"),
            ({"invalid": [None, [], {"code": []}]}, "invalid=unknown"),
            ({"missing": {}}, "missing=malformed"),
            ({"error": []}, "error=unknown"),
            ({"invalid": [{"code": "E503"}] * 8}, "invalid=E503"),
            ({"invalid": [{"code": "E503"}] * 9}, "invalid=over-limit"),
        )
        for evidence, expected in cases:
            with self.subTest(expected=expected, evidence=evidence):
                self.assertIn(expected, helper._signature_failure_detail(evidence))

        class UnreadableOverLimit(list):
            def __iter__(self):
                raise AssertionError("over-limit diagnostic entries were traversed")

        self.assertIn("invalid=over-limit", helper._signature_failure_detail({
            "invalid": UnreadableOverLimit([None] * 9),
        }))
        maximal = {
            "invalid": [{"code": code} for code in (
                "EINTEGRITYSIGNATURE", "EATTESTATIONVERIFY", "ETIMEDOUT",
                "ECONNRESET", "EAI_AGAIN", "E503", "E502", "E504",
            )],
            "missing": None,
            "error": {"code": "EINTEGRITYSIGNATURE"},
        }
        diagnostic = "npm signature or provenance verification failed: " + helper._signature_failure_detail(maximal)
        self.assertLessEqual(len(diagnostic), 256)
        self.assertIn("EATTESTATIONVERIFY", diagnostic)

    def test_registry_authenticity_rejects_unsigned_or_invalid_packages(self):
        helper = self._helper()
        installed = subprocess.CompletedProcess(["npm", "install"], 0, "", "")
        for evidence in (
            {"invalid": [{"name": "@arbiterforge/ca-pi"}], "missing": []},
            {"invalid": [], "missing": ["@arbiterforge/ca-pi@0.10.0"]},
        ):
            audited = subprocess.CompletedProcess(
                ["npm", "audit", "signatures"], 0, json.dumps(evidence), ""
            )
            with self.subTest(evidence=evidence), mock.patch.object(
                helper.subprocess, "run", side_effect=[installed, audited]
            ), self.assertRaisesRegex(ValueError, "signature"):
                helper.verify_registry_authenticity("npm", "0.10.0")
        provenance_bundle = {
            "predicateType": "https://slsa.dev/provenance/v1",
            "bundle": {"dsseEnvelope": {"payload": "verified"}},
        }
        verified_evidence = {
            "invalid": [],
            "missing": [],
            "verified": [
                {
                    "name": "@arbiterforge/ca-pi",
                    "version": "0.10.0",
                    "location": "node_modules/@arbiterforge/ca-pi",
                    "registry": "https://registry.npmjs.org/",
                    "attestationBundles": [
                        {
                            "predicateType": "https://github.com/npm/attestation/tree/main/specs/publish/v0.1",
                            "bundle": {"dsseEnvelope": {"payload": "publish"}},
                        },
                        provenance_bundle,
                    ],
                }
            ],
        }
        audited = subprocess.CompletedProcess(
            ["npm", "audit", "signatures"],
            1,
            json.dumps(verified_evidence),
            "",
        )
        with mock.patch.object(
            helper.subprocess, "run", side_effect=[installed, audited]
        ), self.assertRaisesRegex(ValueError, "signature"):
            helper.verify_registry_authenticity("npm", "0.10.0")
        audited = subprocess.CompletedProcess(
            ["npm", "audit", "signatures"],
            0,
            json.dumps(verified_evidence),
            "",
        )
        with mock.patch.object(
            helper.subprocess, "run", side_effect=[installed, audited]
        ) as run:
            document = helper.verify_registry_authenticity("npm", "0.10.0")
        self.assertEqual(document, {"attestations": [provenance_bundle]})
        install_command = run.call_args_list[0].args[0]
        audit_command = run.call_args_list[1].args[0]
        self.assertEqual(install_command[:2], ["npm", "install"])
        self.assertIn("--ignore-scripts", install_command)
        self.assertIn("--save-exact", install_command)
        self.assertIn("@arbiterforge/ca-pi@0.10.0", install_command)
        self.assertIn(helper.SCOPED_REGISTRY_OPTION, install_command)
        self.assertEqual(audit_command[:3], ["npm", "audit", "signatures"])
        self.assertIn("--json", audit_command)
        self.assertIn("--include-attestations", audit_command)
        self.assertIn(helper.SCOPED_REGISTRY_OPTION, audit_command)
        for call in run.call_args_list:
            root = Path(call.kwargs["cwd"])
            npm_env = call.kwargs["env"]
            for name, leaf in (
                ("NPM_CONFIG_CACHE", "cache"),
                ("NPM_CONFIG_LOGS_DIR", "logs"),
                ("NPM_CONFIG_USERCONFIG", "user.npmrc"),
                ("NPM_CONFIG_GLOBALCONFIG", "global.npmrc"),
            ):
                self.assertEqual(Path(npm_env[name]), root / leaf)
            self.assertFalse(root.exists(), "the isolated npm state must be cleaned")

        hostile_evidence = []
        for field, value in (
            ("name", "@attacker/ca-pi"),
            ("version", "0.9.9"),
            ("location", "node_modules/attacker"),
            ("registry", "https://attacker.invalid/"),
        ):
            evidence = copy.deepcopy(verified_evidence)
            evidence["verified"][0][field] = value
            hostile_evidence.append((field, evidence, "wrong package identity"))
        evidence = copy.deepcopy(verified_evidence)
        evidence["verified"].append(copy.deepcopy(evidence["verified"][0]))
        hostile_evidence.append(("duplicate package", evidence, "one exact package"))
        for label, bundles in (
            ("missing provenance", []),
            ("duplicate provenance", [provenance_bundle, provenance_bundle]),
        ):
            evidence = copy.deepcopy(verified_evidence)
            evidence["verified"][0]["attestationBundles"] = bundles
            hostile_evidence.append((label, evidence, "ambiguous provenance"))
        for label, evidence, message in hostile_evidence:
            audited = subprocess.CompletedProcess(
                ["npm", "audit", "signatures"], 0, json.dumps(evidence), ""
            )
            with self.subTest(label=label), mock.patch.object(
                helper.subprocess, "run", side_effect=[installed, audited]
            ), self.assertRaisesRegex(ValueError, message):
                helper.verify_registry_authenticity("npm", "0.10.0")

    def test_present_publication_orchestration_binds_verified_bundle(self):
        helper = self._helper()
        tarball_bytes = b"exact-prebuilt-pi-package"
        integrity = "sha512-" + base64.b64encode(
            hashlib.sha512(tarball_bytes).digest()).decode("ascii")
        registry = subprocess.CompletedProcess(
            ["npm"],
            0,
            json.dumps(
                {
                    "version": "0.10.0",
                    "dist": {
                        "integrity": integrity,
                        "attestations": {
                            "url": "https://registry.npmjs.org/-/npm/v1/attestations/@arbiterforge%2fca-pi@0.10.0",
                            "provenance": {
                                "predicateType": "https://slsa.dev/provenance/v1"
                            },
                        },
                    },
                }
            ),
            "",
        )
        verified_document = {"attestations": [{"verified": True}]}
        source_sha = "a" * 40
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "plugins" / "ca-pi").mkdir(parents=True)
            root_manifest = {
                "name": "@arbiterforge/ca-pi",
                "version": "0.10.0",
                "repository": {
                    "type": "git",
                    "url": "git+https://github.com/arbiterForge/codeArbiter.git",
                },
                "publishConfig": {"access": "public", "provenance": True},
            }
            (repo / "package.json").write_text(json.dumps(root_manifest), encoding="utf-8")
            (repo / "plugins" / "ca-pi" / "package.json").write_text(
                json.dumps(
                    {
                        "name": "@arbiterforge/ca-pi",
                        "version": "0.10.0",
                        "private": True,
                    }
                ),
                encoding="utf-8",
            )
            release_json = repo / "release.json"
            release_json.write_text(
                json.dumps({"tag_name": "ca-pi-v0.10.0", "draft": False}),
                encoding="utf-8",
            )
            output = repo / "output.txt"
            tarball = repo / "arbiterforge-ca-pi-0.10.0.tgz"
            tarball.write_bytes(tarball_bytes)
            cohort = repo / "artifact-package-cohort.json"
            cohort.write_text(json.dumps({
                "format": "codearbiter.artifact-package-cohort/0.1.0",
                "source_commit": "a" * 40,
                "source_tree": "e" * 40,
                "workflow": ".github/workflows/ci.yml",
                "run_id": "123",
                "promotion_receipt_sha256": "d" * 64,
                "pi_packer": {"name": "npm", "version": "11.19.1", "qualification": "production",
                              "package_integrity": helper.NPM_PACKER_INTEGRITY,
                              "executable_sha256": "f" * 64},
                "packages": {
                    "claude": {}, "codex": {},
                    "pi": {"file": tarball.name, "version": "0.10.0",
                           "size": len(tarball_bytes),
                           "sha256": hashlib.sha256(tarball_bytes).hexdigest()},
                },
            }), encoding="utf-8")
            args = argparse.Namespace(
                repo=str(repo),
                trusted_repo=str(repo),
                tag="ca-pi-v0.10.0",
                expected_sha="a" * 40,
                trusted_sha="a" * 40,
                npm="npm",
                root_manifest="package.json",
                plugin_manifest="plugins/ca-pi/package.json",
                release_json=str(release_json),
                cohort=str(cohort),
                tarball=str(tarball),
                ci_run_id="123",
                output=str(output),
            )
            with mock.patch.object(helper, "validate_release_source_binding"), mock.patch.object(helper, "validate_git_identity"), mock.patch.object(
                helper, "registry_lookup", return_value=registry
            ), mock.patch.object(
                helper, "verify_registry_authenticity", return_value=verified_document
            ) as authenticity, mock.patch.object(
                helper, "validate_attestation_document", return_value=source_sha
            ) as semantic, mock.patch.object(helper, "validate_main_commit") as ancestry:
                self.assertEqual(helper.prepare(args), 0)
            authenticity.assert_called_once_with("npm", "0.10.0")
            semantic.assert_called_once_with(
                verified_document, "0.10.0", integrity, "a" * 40
            )
            ancestry.assert_not_called()
            output_values = dict(
                line.split("=", 1)
                for line in output.read_text(encoding="utf-8").splitlines()
            )
            self.assertEqual(output_values["skip"], "true")
            self.assertEqual(output_values["publication_mode"], "existing")

        for mode in ("new", "existing"):
            args = argparse.Namespace(
                repo="trusted",
                tag="ca-pi-v0.10.0",
                expected_sha="a" * 40,
                trusted_sha="a" * 40,
                npm="npm",
                integrity=integrity,
                publication_mode=mode,
                attempts=1,
                delay_seconds=0,
            )
            with self.subTest(mode=mode), mock.patch.object(helper, "validate_release_source_binding"), mock.patch.object(
                helper, "registry_lookup", return_value=registry
            ), mock.patch.object(
                helper, "verify_registry_authenticity", return_value=verified_document
            ) as authenticity, mock.patch.object(
                helper, "validate_attestation_document", return_value=source_sha
            ) as semantic, mock.patch.object(helper, "validate_main_commit") as ancestry:
                self.assertEqual(helper.verify(args), 0)
                authenticity.assert_called_once_with("npm", "0.10.0")
                semantic.assert_called_once_with(
                    verified_document, "0.10.0", integrity, "a" * 40
                )
                ancestry.assert_not_called()

        args.publication_mode = "new"
        with mock.patch.object(helper, "validate_release_source_binding"), mock.patch.object(
            helper, "registry_lookup", return_value=registry
        ), mock.patch.object(
            helper,
            "verify_registry_authenticity",
            side_effect=ValueError("signature failure"),
        ), self.assertRaisesRegex(ValueError, "signature failure"):
            helper.verify(args)

    def test_prebuilt_pi_package_rejects_cohort_context_packer_and_byte_drift(self):
        helper = self._helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tarball = root / "arbiterforge-ca-pi-0.10.0.tgz"
            tarball.write_bytes(b"prebuilt")
            base = {
                "format": "codearbiter.artifact-package-cohort/0.1.0",
                "source_commit": "a" * 40, "source_tree": "b" * 40,
                "workflow": ".github/workflows/ci.yml", "run_id": "123",
                "promotion_receipt_sha256": "c" * 64,
                "pi_packer": {"name": "npm", "version": "11.19.1",
                              "package_integrity": helper.NPM_PACKER_INTEGRITY,
                              "executable_sha256": "d" * 64, "qualification": "production"},
                "packages": {"claude": {}, "codex": {}, "pi": {
                    "file": tarball.name, "version": "0.10.0", "size": 8,
                    "sha256": hashlib.sha256(b"prebuilt").hexdigest()}},
            }
            cohort = root / "artifact-package-cohort.json"
            cohort.write_text(json.dumps(base), encoding="utf-8")
            self.assertEqual(
                helper.load_prebuilt_pi_package(
                    cohort, tarball, version="0.10.0", expected_sha="a" * 40,
                    ci_run_id="123")[0],
                str(tarball.resolve()),
            )
            mutations = (
                ("source_commit", "e" * 40),
                ("run_id", "124"),
                ("promotion_receipt_sha256", "short"),
            )
            for field, value in mutations:
                changed = copy.deepcopy(base); changed[field] = value
                cohort.write_text(json.dumps(changed), encoding="utf-8")
                with self.subTest(field=field), self.assertRaisesRegex(
                        ValueError, "exact production CI cohort"):
                    helper.load_prebuilt_pi_package(
                        cohort, tarball, version="0.10.0", expected_sha="a" * 40,
                        ci_run_id="123")
            cohort.write_text(json.dumps(base), encoding="utf-8")
            tarball.write_bytes(b"drifted!")
            with self.assertRaisesRegex(ValueError, "bytes drifted"):
                helper.load_prebuilt_pi_package(
                    cohort, tarball, version="0.10.0", expected_sha="a" * 40,
                    ci_run_id="123")

    def test_release_source_binding_rejects_cross_sha_before_publication(self):
        helper = self._helper()
        with self.assertRaisesRegex(ValueError, "must be identical"):
            helper.validate_release_source_binding(
                Path("trusted"), Path("candidate"), "a" * 40, "b" * 40
            )

    def test_release_source_binding_is_exact_and_refuses_continuation(self):
        helper = self._helper()
        heads = lambda repo, *args: subprocess.CompletedProcess(
            [], 0, (("b" if str(repo).endswith("trusted") else "a") * 40) + "\n", "")
        with mock.patch.object(helper, "_git", side_effect=heads):
            with self.assertRaisesRegex(ValueError, "continuation was removed"):
                helper.validate_release_source_binding(
                    Path("trusted"), Path("candidate"), "a" * 40, "b" * 40,
                    allow_continuation=True,
                )
            with self.assertRaisesRegex(ValueError, "must be identical"):
                helper.validate_release_source_binding(
                    Path("trusted"), Path("candidate"), "a" * 40, "b" * 40)
        same = lambda repo, *args: subprocess.CompletedProcess([], 0, "a" * 40 + "\n", "")
        with mock.patch.object(helper, "_git", side_effect=same):
            helper.validate_release_source_binding(
                Path("trusted"), Path("candidate"), "a" * 40, "a" * 40)

    def test_cold_receipt_schema_matches_real_producer_field_set(self):
        """COLD_FIELDS must track every field the real cold-execution receipt
        writer emits. 4b437153 added 9 fields to the writer's receipt without
        updating this allowlist, so every real receipt CI produced afterward
        failed the release-time exact-schema check and broke every release."""
        helper = self._helper()
        self.assertEqual(producer_cold_receipt_keys(), helper.COLD_FIELDS)
        self.assertEqual(producer_installed_workflow_format(), helper.INSTALLED_WORKFLOW_FORMAT)

    def test_context_qualified_pi_receipt_is_accepted_and_exact_matrix_rejects_schema_duplicate_and_member_digest_drift(self):
        helper = self._helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); trusted = root / "trusted"; packages = root / "packages"
            cold_root = root / "cold"; stage = root / "stage"; source = root / "source"
            for path in (trusted / "tools", packages, cold_root, stage, source):
                path.mkdir(parents=True, exist_ok=True)
            prefixes = {"claude": "plugins/ca/helpers/artifacts/",
                        "codex": "plugins/ca-codex/helpers/artifacts/",
                        "pi": "package/plugins/ca-pi/helpers/artifacts/"}
            platforms = sorted(helper.COLD_PLATFORMS)
            cohort = {"promotion_receipt_sha256": "c" * 64, "packages": {}}
            binary = b"binary"; binary_sha = hashlib.sha256(binary).hexdigest()
            for host, prefix in prefixes.items():
                from _artifactmanifestlib import CONTRACT
                manifest_data = {
                    "format": CONTRACT["format"], "version": "0.1.0",
                    "protocol": CONTRACT["protocol"],
                    "schema_version": CONTRACT["schema_version"],
                    "binaries": {
                        platform: {
                            "file": "ca-artifact-" + platform.replace("/", "-")
                                    + (".exe" if platform.startswith("windows/") else ""),
                            "sha256": binary_sha, "native_tested": True,
                        }
                        for platform in platforms
                    },
                }
                if host == "pi":
                    manifest_data["context_qualification"] = {
                        platform: {
                            "source_commit": "a" * 40, "workflow": CONTRACT["workflow"],
                            "run_id": "123", "binary_sha256": binary_sha,
                            "observation_sha256": "d" * 64, "module_sha256": "e" * 64,
                            "native_cases": CONTRACT["native_cases"],
                        }
                        for platform in platforms
                    }
                manifest = json.dumps(manifest_data, separators=(",", ":")).encode()
                self.assertEqual(helper.parse_release_manifest(manifest), manifest_data)
                manifest_sha = hashlib.sha256(manifest).hexdigest()
                archive_members = {prefix + "release.json": manifest}
                archive_members.update({prefix + entry["file"]: binary
                                        for entry in manifest_data["binaries"].values()})
                archive_path = packages / f"{host}.tgz"
                with tarfile.open(archive_path, "w:gz") as archive:
                    for name, data in archive_members.items():
                        info = tarfile.TarInfo(name); info.size = len(data)
                        archive.addfile(info, io.BytesIO(data))
                package_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
                cohort["packages"][host] = {
                    "file": archive_path.name, "sha256": package_sha,
                    "members": {name: {"sha256": hashlib.sha256(data).hexdigest()}
                                for name, data in archive_members.items()},
                }
                for platform in platforms:
                    cell = cold_root / f"{host}-{platform.replace('/', '-')}"
                    cell.mkdir()
                    receipt = {
                        "format": "codearbiter.artifact-cold-execution/0.3.0",
                        "source_commit": "a" * 40, "workflow": ".github/workflows/ci.yml",
                        "run_id": "123", "job": "artifact-package-cold", "host": host,
                        "platform": platform, "promotion_receipt_sha256": "c" * 64,
                        "package_sha256": package_sha, "manifest_sha256": manifest_sha,
                        "binary_sha256": binary_sha, "response_sha256": "d" * 64,
                        "operation": "capabilities", "repository_operations_available": True,
                        "runtime_downloads": False,
                        "installed_workflow_response_sha256": "e" * 64,
                        "installed_bridge_sha256": "f" * 64,
                        "installed_workflow_format": helper.INSTALLED_WORKFLOW_FORMAT,
                        "approval_evidence_mode": (
                            "synthetic-policy-event"
                            if host == "pi"
                            else "host-observed-prompt"
                        ),
                        "prerequisite_evidence_mode": (
                            "synthetic-policy-event"
                            if host == "pi"
                            else "host-observed-prompt"
                        ),
                        "interruption_reconciled": True, "redispatched": True,
                        "commit_proof": True, "finalization_proof": True,
                        "all_accepted_and_current": True, "markdown_shadow_count": 0,
                    }
                    if host == "pi":
                        receipt.update({
                            "context_workflow_scope": "candidate-preflight",
                            "context_installed_tests": helper.CONTEXT_COLD_TESTS,
                            "context_installed_output_sha256": "f" * 64,
                        })
                    (cell / "artifact-package-cold.json").write_text(json.dumps(receipt))
            (packages / "artifact-package-cohort.json").write_text(json.dumps(cohort))
            (trusted / "tools" / "build-host-packages.py").write_text(
                "import json\nfrom pathlib import Path\n"
                "def verify_artifact_release_packages(**kwargs):\n"
                " return json.loads((Path(kwargs['package_root'])/'artifact-package-cohort.json').read_text())\n"
            )
            kwargs = dict(package_root=packages, stage_root=stage, cold_root=cold_root,
                          source_repo=source, source_commit="a" * 40, ci_run_id="123",
                          npm_executable=root / "npm", trusted_repo=trusted,
                          workflow_sha="a" * 40)
            with mock.patch.object(helper, "validate_release_source_binding"):
                helper.verify_release_cohort(**kwargs)
            first = next(
                path for path in sorted(cold_root.glob("*/artifact-package-cold.json"))
                if json.loads(path.read_text())["host"] == "claude"
            )
            original = json.loads(first.read_text())
            for mutation, message in (
                ({**original, "extra": True}, "schema is not exact"),
                ({**original, "binary_sha256": "e" * 64}, "do not link"),
                ({**original, "interruption_reconciled": False}, "not bound to the exact cohort"),
                ({**original, "redispatched": False}, "not bound to the exact cohort"),
                ({**original, "commit_proof": False}, "not bound to the exact cohort"),
                ({**original, "finalization_proof": False}, "not bound to the exact cohort"),
                ({**original, "all_accepted_and_current": False}, "not bound to the exact cohort"),
                ({**original, "markdown_shadow_count": 1}, "not bound to the exact cohort"),
                ({**original, "markdown_shadow_count": False}, "not bound to the exact cohort"),
                ({**original, "installed_workflow_format": "wrong"}, "not bound to the exact cohort"),
                ({**original, "approval_evidence_mode": "wrong"}, "not bound to the exact cohort"),
                ({**original, "prerequisite_evidence_mode": "wrong"}, "not bound to the exact cohort"),
                ({**original, "installed_workflow_response_sha256": "e" * 65}, "not bound to the exact cohort"),
                ({**original, "installed_bridge_sha256": "E" * 64}, "not bound to the exact cohort"),
            ):
                first.write_text(json.dumps(mutation))
                with self.subTest(message=message), mock.patch.object(
                        helper, "validate_release_source_binding"), self.assertRaisesRegex(ValueError, message):
                    helper.verify_release_cohort(**kwargs)
                first.write_text(json.dumps(original))
            duplicate_key = json.dumps(original).replace(
                '"format":', '"format":"shadow","format":', 1)
            first.write_text(duplicate_key)
            with mock.patch.object(helper, "validate_release_source_binding"), \
                    self.assertRaisesRegex(ValueError, "duplicate JSON field"):
                helper.verify_release_cohort(**kwargs)
            first.write_text(json.dumps(original))
            duplicate = cold_root / "duplicate"; duplicate.mkdir()
            (duplicate / "artifact-package-cold.json").write_text(json.dumps(original))
            with mock.patch.object(helper, "validate_release_source_binding"), \
                    self.assertRaisesRegex(ValueError, "duplicate"):
                helper.verify_release_cohort(**kwargs)

    def test_historical_attestation_commit_must_remain_on_protected_main(self):
        helper = self._helper()
        repo = Path("trusted")
        with mock.patch.object(
            helper,
            "_git",
            return_value=subprocess.CompletedProcess(["git"], 0, "", ""),
        ) as git:
            helper.validate_main_commit(repo, "a" * 40)
            self.assertEqual(
                git.call_args.args[1:],
                ("merge-base", "--is-ancestor", "a" * 40, "origin/main"),
            )
        with mock.patch.object(
            helper,
            "_git",
            return_value=subprocess.CompletedProcess(["git"], 1, "", ""),
        ), self.assertRaisesRegex(ValueError, "protected main"):
            helper.validate_main_commit(repo, "b" * 40)

    def test_security_policy_and_workflow_guard_the_npm_secret_boundary(self):
        from project_knowledge import context_text
        policy = context_text("security-controls")
        workflow = self.WORKFLOW.read_text(encoding="utf-8")
        action = self.ACTION.read_text(encoding="utf-8")
        self.assertIn("### ca-pi npm publication boundary", policy)
        for claim in (
            "trusted publisher",
            "release.yml",
            "short-lived",
            "@arbiterforge/ca-pi",
            "OIDC provenance",
            "npm audit signatures",
            "npm@11.19.1",
            "https://registry.npmjs.org/npm/-/npm-11.19.1.tgz",
            "sha512-ztsxKxt/kkIaAs+2i0GU6I+DRmUdrNasxTZKJe9TCdSjKxlhah/4r/hl5ygMD6XAg1qZ9c2TNomR4qgOydp10g==",
            "path-containment",
            "credential-free",
        ):
            self.assertIn(claim, policy)
        self._assert_npm_secret_boundary(workflow, action)

    def _assert_npm_secret_boundary(self, workflow, action):
        self.assertNotIn("secrets: inherit", workflow)
        self.assertNotIn("secrets.NPMJS_TOKEN", workflow)
        pi_job = workflow.split("\n  release-pi:\n", 1)[1].split("\n  release-sandbox:\n", 1)[0]
        self.assertIn("id-token: write", pi_job)
        self.assertNotIn("npm-token:", pi_job)
        self.assertNotRegex(workflow, r"(?m)^env:")
        self.assertNotRegex(workflow, r"(?m)^defaults:")
        self.assertNotIn("self-hosted", workflow)
        self.assertNotIn("persist-credentials: true", workflow)
        self.assertEqual(workflow.count("uses: actions/checkout@"),
                         workflow.count("persist-credentials: false"))
        self.assertNotIn("NODE_AUTH_TOKEN:", action)
        self.assertNotIn("inputs.npm-token", action)
        self.assertNotIn("npm-token:", action)
        self.assertIn("node-version: '22.19.0'", action)
        publish_step = action.split("    - name: Publish @arbiterforge/ca-pi to npm", 1)[1].split(
            "\n    - name: ", 1
        )[0]
        self.assertIn("--ignore-scripts", publish_step)
        self.assertIn("--provenance", publish_step)
        # The reviewed npm CLI is fetched without redirects and pinned by integrity.
        self.assertIn("curl --disable", action)
        self.assertIn("--max-redirs 0", action)
        self.assertIn("sha512-ztsxKxt/kkIaAs+2i0GU6I+DRmUdrNasxTZKJe9TCdSjKxlhah/4r/hl5ygMD6XAg1qZ9c2TNomR4qgOydp10g==", action)

    def test_npm_secret_boundary_rejects_hostile_drift(self):
        workflow = self.WORKFLOW.read_text(encoding="utf-8")
        action = self.ACTION.read_text(encoding="utf-8")
        workflow_mutations = (
            workflow.replace("  release-sandbox:\n", "  release-sandbox:\n    secrets: inherit\n", 1),
            workflow.replace("  release-sandbox:\n",
                             "  release-sandbox:\n    env:\n      T: ${{ secrets.NPMJS_TOKEN }}\n", 1),
            workflow.replace("persist-credentials: false", "persist-credentials: true", 1),
            workflow.replace("runs-on: ubuntu-latest", "runs-on: self-hosted", 1),
            workflow.replace("\npermissions:\n", "\ndefaults:\n  run:\n    shell: evil\npermissions:\n", 1),
        )
        for mutation in workflow_mutations:
            self.assertNotEqual(mutation, workflow)
            with self.subTest(mutation="workflow"), self.assertRaises(AssertionError):
                self._assert_npm_secret_boundary(mutation, action)
        action_mutations = (
            action.replace("--ignore-scripts", "", 1),
            action.replace("curl --disable", "curl --location", 1),
            action.replace("--max-redirs 0", "--max-redirs 1", 1),
            action.replace("    - name: Read back the npm publication\n",
                           "    - name: Read back the npm publication\n      env:\n        NODE_AUTH_TOKEN: ${{ inputs.npm-token }}\n", 1),
        )
        for mutation in action_mutations:
            self.assertNotEqual(mutation, action)
            with self.subTest(mutation="action"), self.assertRaises(AssertionError):
                self._assert_npm_secret_boundary(workflow, mutation)

    def test_release_and_git_identity_require_exact_annotated_tag(self):
        helper = self._helper()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
                check=True,
            )
            (repo / "payload").write_text("one\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "payload"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "one"], check=True)
            sha = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
            ).strip()
            subprocess.run(
                ["git", "-C", str(repo), "tag", "-a", "ca-pi-v0.10.0", "-m", "release"],
                check=True,
            )
            helper.validate_git_identity(repo, "ca-pi-v0.10.0", sha, main_ref="HEAD")
            with self.assertRaises(ValueError):
                helper.validate_git_identity(repo, "ca-pi-v0.10.0", "b" * 40, main_ref="HEAD")
            (repo / "payload").write_text("two\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "commit", "-qam", "two"], check=True)
            with self.assertRaises(ValueError):
                helper.validate_git_identity(repo, "ca-pi-v0.10.0", sha, main_ref="HEAD")
            side_sha = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
            ).strip()
            subprocess.run(
                ["git", "-C", str(repo), "tag", "-a", "ca-pi-v0.10.2", "-m", "side"],
                check=True,
            )
            with self.assertRaisesRegex(ValueError, "not contained in protected main"):
                helper.validate_git_identity(
                    repo, "ca-pi-v0.10.2", side_sha, main_ref=sha
                )
            subprocess.run(["git", "-C", str(repo), "tag", "ca-pi-v0.10.1"], check=True)
            with self.assertRaisesRegex(ValueError, "must be an annotated tag"):
                helper.validate_git_identity(
                    repo, "ca-pi-v0.10.1", side_sha, main_ref="HEAD"
                )
        helper.validate_release_document(
            {"tag_name": "ca-pi-v0.10.0", "draft": False}, "ca-pi-v0.10.0"
        )
        for doc in (
            {"tag_name": "ca-pi-v0.10.0", "draft": True},
            {"tag_name": "ca-pi-v0.9.9", "draft": False},
            {},
        ):
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                helper.validate_release_document(doc, "ca-pi-v0.10.0")

    def test_remote_annotated_tag_identity_binds_direct_object_and_peeled_source(self):
        helper = self._helper()
        tag = "ca-pi-v0.10.0"
        source = "a" * 40
        object_sha = "b" * 40
        remote = (f"{object_sha}\trefs/tags/{tag}\n"
                  f"{source}\trefs/tags/{tag}^{{}}\n")
        self.assertEqual(
            helper.validate_remote_annotated_tag(
                remote, tag, source, expected_object=object_sha
            ),
            object_sha,
        )
        cases = (
            (f"{source}\trefs/tags/{tag}\n", None, "exact annotated tag"),
            (remote, "c" * 40, "object identity changed"),
            (f"{'c' * 40}\trefs/tags/{tag}\n{source}\trefs/tags/{tag}^{{}}\n",
             object_sha, "object identity changed"),
            (f"{object_sha}\trefs/tags/{tag}\n{'c' * 40}\trefs/tags/{tag}^{{}}\n",
             object_sha, "exact source"),
        )
        for observed, expected, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                helper.validate_remote_annotated_tag(
                    observed, tag, source, expected_object=expected
                )

PLATFORM_PACKAGE_PARTITIONS = ("package", "rpc", "rpc-observed", "shutdown", "publish")


def platform_package_suites():
    """Partition the full discovered suite without dropping or repeating cases."""
    suites = {name: unittest.TestSuite() for name in PLATFORM_PACKAGE_PARTITIONS}

    def cases(suite):
        for test in suite:
            if isinstance(test, unittest.TestSuite):
                yield from cases(test)
            else:
                yield test

    for case in cases(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])):
        if isinstance(case, NpmPublishContractTest):
            partition = "publish"
        elif case._testMethodName in (
            "test_real_rpc_shutdown_probe_uses_the_same_enforcement_failure_fixture",
            "test_real_rpc_shutdown_probe_uses_the_same_native_read_context_fixture",
        ):
            partition = "rpc-observed"
        elif "shutdown" in case._testMethodName or "post_exit_entry" in case._testMethodName:
            partition = "shutdown"
        elif "rpc" in case._testMethodName:
            partition = "rpc"
        else:
            partition = "package"
        suites[partition].addTest(case)
    return suites


class DebuggerInboxTests(unittest.TestCase):
    def test_collector_outcome_survives_final_wait_failure(self):
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        collector = native._collect
        owner_temp = tempfile.TemporaryDirectory
        for outcome, failure in (("deadline", "deadline"), ("output_limit", "output-limit"),
                                 ("debugger_failed", "worker-exit")):
            for error_kind in ("os-error", "timeout"):
                with self.subTest(outcome=outcome, error=error_kind), owner_temp() as directory:
                    root = Path(directory).resolve()
                    error = OSError(5, "PRIVATE_WAIT_ERROR") if error_kind == "os-error" else native.subprocess.TimeoutExpired("PRIVATE_WAIT_ARGV", 0)
                    if error_kind == "os-error": error.winerror = 233
                    process = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(), returncode=1,
                        poll=mock.Mock(return_value=1), wait=mock.Mock(side_effect=error),
                        kill=mock.Mock(), _handle=SimpleNamespace(Close=mock.Mock()))
                    kernel = SimpleNamespace(duplicate_query=mock.Mock(return_value=77), close=mock.Mock(), available=mock.Mock())
                    def real_collect(child, available, *, deadline, _diagnostic):
                        return collector(child, lambda stream: native.MAX_OUTPUT if outcome == "output_limit" else 0,
                            deadline=deadline, _diagnostic=_diagnostic,
                            _read=lambda stream, count: b"x" * count,
                            _clock=lambda: deadline + 1 if outcome == "deadline" else 0)
                    with mock.patch.object(native.tempfile, "TemporaryDirectory", side_effect=lambda **kwargs: owner_temp(dir=root, **kwargs)), \
                         mock.patch.object(native, "_tool_profile", return_value=("inbox-v1", root,
                             {name: "a" * 64 for name in native.TOOL_FILES["inbox-v1"]})), \
                         mock.patch.object(native.subprocess, "STARTUPINFO", side_effect=SimpleNamespace, create=True), \
                         mock.patch.object(native.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                         mock.patch.object(native.subprocess, "Popen", return_value=process), \
                         mock.patch.object(native, "_collect", side_effect=real_collect):
                        actual = native._debugger(33, kernel, time.monotonic() + 5,
                            binding={"handle": 11, "created": 44, "image": str(root / "inert-node.exe")})
                    diagnostic = actual["diagnostic"]
                    self.assertEqual(actual["status"], "cleanup_unknown")
                    self.assertEqual(diagnostic["primaryStatus"], outcome)
                    self.assertEqual(diagnostic["failure"], failure)
                    self.assertEqual(diagnostic["cleanupFailure"], {"operation": "worker-wait",
                        "exception": "os-error" if error_kind == "os-error" else "unexpected", "errno": 5 if error_kind == "os-error" else None,
                        "winerror": 233 if error_kind == "os-error" else None})
                    self.assertEqual(diagnostic["collectedBytes"], native.MAX_OUTPUT if outcome == "output_limit" else 0)
                    self.assertEqual(actual["truncated"], outcome == "output_limit")
                    self.assertNotIn("PRIVATE_", json.dumps(actual))
                    self.assertNotIn(str(root), json.dumps(actual))
                    self.assertLess(len(json.dumps(actual).encode()), native.MAX_JSON)
                    process.kill.assert_not_called()



    def test_final_owned_worker_cleanup_keeps_poll_and_wait_operations(self):
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        collector_temp = tempfile.TemporaryDirectory
        for operation in ("worker-poll", "worker-wait"):
            with self.subTest(operation=operation), collector_temp() as directory:
                root = Path(directory).resolve()
                error = OSError(5, "PRIVATE_FINAL_CLEANUP_CANARY"); error.winerror = 233
                process = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(),
                    poll=mock.Mock(side_effect=error) if operation == "worker-poll" else mock.Mock(return_value=None),
                    wait=mock.Mock(side_effect=error), kill=mock.Mock(), _handle=SimpleNamespace(Close=mock.Mock()))
                kernel = SimpleNamespace(duplicate_query=mock.Mock(return_value=77), close=mock.Mock(), available=mock.Mock())
                with mock.patch.object(native.tempfile, "TemporaryDirectory", side_effect=lambda **kwargs: collector_temp(dir=root, **kwargs)), \
                     mock.patch.object(native, "_tool_profile", return_value=("inbox-v1", root,
                         {name: "a" * 64 for name in native.TOOL_FILES["inbox-v1"]})), \
                     mock.patch.object(native.subprocess, "STARTUPINFO", side_effect=SimpleNamespace, create=True), \
                     mock.patch.object(native.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                     mock.patch.object(native.subprocess, "Popen", return_value=process), \
                     mock.patch.object(native, "_collect", return_value=("transport_failed", b"")):
                    actual = native._debugger(33, kernel, time.monotonic() + 5,
                        binding={"handle": 11, "created": 44, "image": str(root / "inert-node.exe")})
                self.assertEqual(actual["status"], "cleanup_unknown")
                self.assertEqual(actual["diagnostic"]["failure"], "transport")
                self.assertEqual(actual["diagnostic"]["primaryStatus"], "transport_failed")
                self.assertEqual(actual["diagnostic"]["cleanupFailure"], {"operation": operation,
                    "exception": "os-error", "errno": 5, "winerror": 233})
                self.assertNotIn("PRIVATE_FINAL_CLEANUP_CANARY", json.dumps(actual))
                self.assertEqual(process.kill.call_count, int(operation == "worker-wait"))

    def test_closed_transport_error_codes_reject_bool_range_and_exception_text(self):
        import _windows_rpc_timeout as native
        def diagnostic():
            return {"failure": None, "operation": None, "exception": None, "errno": None,
                "winerror": None, "primaryStatus": None, "cleanupFailure": None}
        for code, expected_errno, expected_winerror in ((True, None, None), (2**32, None, None),
                (-(2**31)-1, None, None), (5, 5, 5)):
            with self.subTest(code=code):
                row = diagnostic()
                error = OSError("PRIVATE_CODE_CANARY")
                error.errno = code; error.winerror = code
                native._transport_failure(row, "pipe-read", error, "transport_failed")
                self.assertEqual(row["errno"], expected_errno)
                self.assertEqual(row["winerror"], expected_winerror)
                self.assertEqual(row["exception"], "os-error")
                self.assertEqual(row["operation"], "pipe-read")
                self.assertEqual(row["primaryStatus"], "transport_failed")
                cleanup = PermissionError(13, "PRIVATE_SECONDARY_CANARY"); cleanup.winerror = 5
                native._transport_failure(row, "temporary-root-cleanup", cleanup, "cleanup_unknown", cleanup=True)
                native._transport_failure(row, "worker-final-cleanup", OSError(99, "PRIVATE_THIRD_CANARY"), "cleanup_unknown", cleanup=True)
                self.assertEqual(row["operation"], "pipe-read")
                self.assertEqual(row["primaryStatus"], "transport_failed")
                self.assertEqual(row["cleanupFailure"], {"operation": "temporary-root-cleanup",
                    "exception": "os-error", "errno": 13, "winerror": 5})
                self.assertNotIn("PRIVATE_", json.dumps(row))

    def test_pipe_known_winerror_is_retained_before_closed_transport(self):
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        kernel = object.__new__(native.WindowsKernel)
        kernel.api = SimpleNamespace(PeekNamedPipe=mock.Mock(return_value=False))
        with mock.patch.dict(sys.modules, {"msvcrt": SimpleNamespace(get_osfhandle=lambda descriptor: 77)}), \
             mock.patch.object(native.ctypes, "get_last_error", return_value=233, create=True):
            with self.assertRaises(OSError) as caught:
                kernel.available(SimpleNamespace(fileno=lambda: 1))
        self.assertEqual(getattr(caught.exception, "winerror", None), 233,
            "known PeekNamedPipe WinError was erased before closed transport attribution")

    def test_parent_retains_closed_transport_operation_and_primary_failure(self):
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        collector_temp = tempfile.TemporaryDirectory
        for mode in ("pipe-peek", "pipe-read", "worker-poll", "worker-wait", "worker-launch",
                     "request-write", "request-close", "temporary-root-cleanup", "worker-final-cleanup"):
            with self.subTest(operation=mode), collector_temp(prefix="ca-closed-diagnostic-fixture-") as directory:
                root = Path(directory).resolve()
                primary = OSError(5, "PRIVATE_TRANSPORT_CANARY", str(root / "private-error-path"))
                primary.winerror = 233
                secondary = PermissionError(13, "PRIVATE_CLEANUP_CANARY", str(root / "private-cleanup-path"))
                secondary.winerror = 5
                class Root:
                    def __init__(self, **kwargs): self.owner = collector_temp(dir=root, **kwargs)
                    def __enter__(self): return self.owner.__enter__()
                    def __exit__(self, *args):
                        self.owner.__exit__(*args)
                        if mode in ("pipe-peek", "temporary-root-cleanup"): raise secondary
                class Input(io.BytesIO):
                    refused = False
                    def write(self, value):
                        if mode == "request-write": raise primary
                        return super().write(value)
                    def close(self):
                        if mode == "request-close" and not self.refused:
                            self.refused = True
                            raise primary
                        super().close()
                response = bytearray(json.dumps(self._attribution_worker_result()).encode())
                polls = [0]
                def poll():
                    polls[0] += 1
                    if mode == "worker-poll" and polls[0] == 1: raise primary
                    return 0
                def wait(timeout):
                    if mode == "worker-wait": raise primary
                    return 0
                process = SimpleNamespace(stdin=Input(), stdout=io.BytesIO(), returncode=0,
                    poll=poll, wait=wait, kill=mock.Mock(),
                    _handle=SimpleNamespace(Close=mock.Mock(side_effect=primary if mode == "worker-final-cleanup" else None)))
                def available(stream):
                    if mode == "pipe-peek": raise primary
                    return 0 if mode in ("worker-poll", "worker-wait") else len(response)
                def read(stream, count):
                    if mode == "pipe-read": raise primary
                    value = bytes(response[:count]); del response[:count]; return value
                collect = native._collect
                def inert_collect(child, pipe_available, *, deadline, **kwargs):
                    return collect(child, pipe_available, deadline=deadline, _read=read, **kwargs)
                kernel = SimpleNamespace(duplicate_query=mock.Mock(return_value=77), close=mock.Mock(), available=available)
                with mock.patch.object(native.tempfile, "TemporaryDirectory", side_effect=Root), \
                     mock.patch.object(native, "_tool_profile", return_value=("inbox-v1", root,
                         {name: "a" * 64 for name in native.TOOL_FILES["inbox-v1"]})), \
                     mock.patch.object(native, "_regular", side_effect=lambda path, **kwargs: Path(path)), \
                     mock.patch.object(native, "_worker_environment", return_value={}), \
                     mock.patch.object(native.subprocess, "STARTUPINFO", side_effect=SimpleNamespace, create=True), \
                     mock.patch.object(native.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                     mock.patch.object(native.subprocess, "Popen", side_effect=primary if mode == "worker-launch" else None,
                                       return_value=process) as launch, \
                     mock.patch.object(native, "_collect", side_effect=inert_collect):
                    actual = native._debugger(33, kernel, time.monotonic() + 5,
                        binding={"handle": 11, "created": 44, "image": str(root / "inert-node.exe")})
                diagnostic = actual["diagnostic"]
                if mode == "pipe-peek":
                    self.assertEqual(diagnostic["failure"], "transport",
                        "secondary temporary cleanup must not overwrite the primary transport failure")
                self.assertEqual(diagnostic.get("operation"), mode, "closed failing operation was erased")
                self.assertEqual(diagnostic.get("exception"), "os-error")
                self.assertEqual(diagnostic.get("errno"), 13 if mode == "temporary-root-cleanup" else 5)
                self.assertEqual(diagnostic.get("winerror"), 5 if mode == "temporary-root-cleanup" else 233)
                self.assertEqual(diagnostic.get("workerSpawned"), mode != "worker-launch")
                self.assertIn(diagnostic.get("workerExited"), (None, True))
                self.assertIn(diagnostic.get("workerReturnCode"), (None, 0))
                self.assertIs(type(diagnostic.get("collectedBytes")), int)
                self.assertTrue(0 <= diagnostic["collectedBytes"] <= native.MAX_OUTPUT)
                self.assertEqual(set(diagnostic), {"phase", "failure", "elapsedMs", "remainingMs", "operation",
                    "exception", "errno", "winerror", "workerSpawned", "workerExited", "workerReturnCode",
                    "collectedBytes", "cleanupFailure", "primaryStatus"})
                if mode == "pipe-peek":
                    self.assertEqual(diagnostic["primaryStatus"], "transport_failed")
                    self.assertEqual(diagnostic["cleanupFailure"], {"operation": "temporary-root-cleanup",
                        "exception": "os-error", "errno": 13, "winerror": 5})
                self.assertNotIn("PRIVATE_TRANSPORT_CANARY", json.dumps(actual))
                self.assertNotIn("PRIVATE_CLEANUP_CANARY", json.dumps(actual))
                self.assertNotIn(str(root), json.dumps(actual))
                self.assertLess(len(json.dumps(actual).encode()), native.MAX_JSON)
                launch.assert_called_once()
                kernel.duplicate_query.assert_called_once_with(11)
                process.kill.assert_not_called()  # The inert worker already reports exited; no target exists.
    def test_warm_refusal_timeout_and_uncontained_helper_have_distinct_target_outcomes(self):
        import _windows_rpc_timeout as native
        import _boundedproc as bounded
        from types import SimpleNamespace
        current=sys.modules[__name__]
        for mode in ('refused','launch-error','timeout','uncontained','malformed'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as raw:
                root=Path(raw).resolve();cwd=root/'cwd';cwd.mkdir();retained=root/'retained';retained.mkdir();order=[]
                def preflight(argv,**kwargs):
                    order.append('preflight')
                    if mode=='launch-error':raise OSError('PRIVATE_WARM_CANARY')
                    def communicate(timeout):
                        if mode in ('timeout','uncontained') and timeout==5.0:raise subprocess.TimeoutExpired('owned-hash-only',5.0)
                        if mode=='refused':
                            return json.dumps({'schemaVersion':1,'kind':'protected-provider-warm-read','status':'unavailable',
                                'profile':None,'filesHashed':0,'phase':'provider-hash-dbgeng','failure':'refused','elapsedMs':1}),''
                        return ('{bad PRIVATE_WARM_CANARY' if mode=='malformed' else ''),''
                    return SimpleNamespace(returncode=0,communicate=communicate)
                def target(*args,**kwargs):order.append('target');raise RuntimeError('inert-target-stop')
                os_model=SimpleNamespace(name='nt',environ=os.environ)
                startup=lambda:SimpleNamespace(dwFlags=0,wShowWindow=0)
                with mock.patch.dict(os.environ,{'CA_PI_RPC_DIAGNOSTICS_DIR':str(retained)}), \
                     mock.patch.object(native,'os',os_model),mock.patch.object(bounded,'_VerifierProcess',side_effect=preflight), \
                     mock.patch.object(bounded,'terminate_tree',return_value='unconfirmed' if mode=='uncontained' else 'terminated'), \
                     mock.patch.object(current,'live_pi_cli',return_value=(sys.executable,root/'unused-cli')), \
                     mock.patch.object(current,'read_json',return_value={'packages':['inert']}), \
                     mock.patch.object(subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')), \
                     mock.patch.object(subprocess,'Popen',side_effect=target), \
                     mock.patch.object(subprocess,'STARTUPINFO',side_effect=startup,create=True), \
                     mock.patch.object(subprocess,'STARTF_USESHOWWINDOW',1,create=True), \
                     mock.patch.object(subprocess,'SW_HIDE',0,create=True):
                    if mode in ('uncontained','launch-error'):
                        with self.assertRaises((AssertionError,RuntimeError)) as caught:
                            run_rpc_commands(cwd,root/'agent',root/'home',_rpc_command=['inert-target'],_observe_shutdown=True)
                        self.assertIsInstance(caught.exception,AssertionError,'uncertain hash-helper ownership must block target spawn')
                        self.assertIn('containment unconfirmed; RPC target not spawned',str(caught.exception))
                        self.assertEqual(order,['preflight'])
                        files=list(retained.glob('rpc-native-warmup-*.json'));self.assertEqual(len(files),1)
                        value=json.loads(files[0].read_bytes());self.assertIsNone(value['processId'])
                        self.assertEqual(value['targetState'],'not-spawned');self.assertEqual(value['containment'],'unconfirmed')
                        self.assertNotIn('PRIVATE_WARM_CANARY',files[0].read_text())
                    else:
                        with self.assertRaisesRegex(RuntimeError,'inert-target-stop'):
                            run_rpc_commands(cwd,root/'agent',root/'home',_rpc_command=['inert-target'],_observe_shutdown=True)
                        self.assertEqual(order,['preflight','target'])

    def test_hash_only_warm_records_are_closed_not_authority_and_pid_associated(self):
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        original=native.os
        def reads(deadline,*,_progress):
            self.assertGreater(deadline,time.monotonic())
            self.assertLessEqual(deadline-time.monotonic(),5.0)
            _progress['phase']='provider-hash-dbghelp'
            return 'sdk-v1',Path('unused'),dict.fromkeys(('cdb.exe','dbgeng.dll','dbghelp.dll'),'PRIVATE_HASH_CANARY')
        with mock.patch.object(native,'os',SimpleNamespace(name='nt')), \
             mock.patch.object(native,'_tool_profile',side_effect=reads) as hashing, \
             mock.patch.object(native,'WindowsKernel',side_effect=AssertionError('no target query')), \
             mock.patch.object(native,'_debugger',side_effect=AssertionError('no debugger')):
            child=native.provider_warm_read()
        hashing.assert_called_once();self.assertEqual(child['status'],'complete')
        self.assertEqual(child['filesHashed'],3);self.assertNotIn('PRIVATE_HASH_CANARY',json.dumps(child))
        self.assertNotIn('hashes',child);self.assertNotIn('toolHashes',child)
        parent={**child,'kind':'protected-provider-warm-preflight','timed_out':False,'containment':'exited'}
        self.assertTrue(native._warm_valid(parent,supervised=True))
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve()
            fresh=root/'first-observed-case'
            retained=native.retain_preflight(parent,77,fresh)
            self.assertIsNotNone(retained,'first observed case must create its diagnostic directory')
            self.assertEqual(json.loads((fresh/retained).read_bytes())['processId'],77)
            first=native.retain_preflight(parent,77,root);second=native.retain_preflight(parent,77,root)
            self.assertIsNotNone(first);self.assertNotEqual(first,second)
            row=json.loads((root/first).read_bytes());self.assertEqual(row['processId'],77)
            self.assertEqual(row['targetState'],'spawned')
            for changed in ({**parent,'private':'PRIVATE_WARM_CANARY'},{**parent,'phase':[]},
                            {**parent,'filesHashed':True},{**parent,'containment':'unconfirmed'}):
                self.assertFalse(native._warm_valid(changed,supervised=True))
                self.assertIsNone(native.retain_preflight(changed,77,root))
        # Only the helper CLI/main is new; these authority functions must still
        # call full provider hashing, and never consume the warm record.
        source=Path(native.__file__).read_text(encoding='utf8')
        tree=ast.parse(source)
        for name in ('_debugger','_bound_tool_profile'):
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
            calls=[n for n in ast.walk(node) if isinstance(n,ast.Call)]
            self.assertTrue(any(isinstance(n.func,ast.Name) and n.func.id==('_tool_profile' if name=='_debugger' else '_digest') for n in calls))
            self.assertNotIn('preflight',ast.get_source_segment(source,node))
        ci=(REPO/'.github/workflows/ci.yml').read_text(encoding='utf8')
        self.assertEqual(ci.count('${{ runner.temp }}/ca-pi-rpc-diagnostics/rpc-native-warmup-*.json'),1)

    def test_owned_hash_only_control_uses_existing_deadline_cleanup_owner(self):
        import _boundedproc as bounded
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve();owned=[];start=bounded.start
            env={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','COMSPEC','PATHEXT')}
            env.update(PATH='',HOME=str(root),USERPROFILE=str(root),TEMP=str(root),TMP=str(root))
            def record(*args,**kwargs):
                child=start(*args,**kwargs);owned.append(child);return child
            with mock.patch.object(bounded,'start',side_effect=record):
                result=bounded.run([sys.executable,'-I','-S','-B','-X','utf8','-c',
                    'import time; print("owned-hash-control-ready",flush=True); time.sleep(10)'],
                    timeout=0.15,cwd=root,env=env,stdin=subprocess.DEVNULL)
            self.assertTrue(result.timed_out);self.assertIn(result.containment,('terminated','exited'))
            self.assertEqual(len(owned),1);self.assertIsNotNone(owned[0].poll())
            self.assertEqual(owned[0].stdin,None)

    def test_observed_windows_warm_preflight_precedes_owned_target_without_effect_substitution(self):
        import _windows_rpc_timeout as native
        import _boundedproc as bounded
        from types import SimpleNamespace
        current=sys.modules[__name__]
        cases = (
            (True, True, False, ['preflight', 'target']),
            (False, True, True, ['preflight', 'target']),
            (False, True, False, ['target']),
            (False, False, True, ['target']),
            (True, False, False, ['target']),
        )
        for observed, windows, retained, expect in cases:
            with self.subTest(observed=observed, windows=windows, retained=retained), tempfile.TemporaryDirectory() as raw:
                root=Path(raw).resolve();cwd=root/'cwd';cwd.mkdir();order=[]
                report={'schemaVersion':1,'kind':'protected-provider-warm-read','status':'complete',
                        'profile':'sdk-v1','filesHashed':3,'phase':'provider-hash-dbghelp','failure':None,'elapsedMs':1}
                def preflight(argv,**kwargs):
                    order.append('preflight')
                    self.assertEqual(argv,[sys.executable,'-I','-S','-B','-X','utf8',str(Path(native.__file__).resolve()),'--preflight-provider'])
                    self.assertEqual(kwargs['stdin'],subprocess.DEVNULL)
                    self.assertTrue(kwargs['close_fds'])
                    self.assertEqual(kwargs['env'].get('PATH'),'')
                    self.assertFalse(any(k in kwargs['env'] for k in ('GH_TOKEN','GITHUB_TOKEN','OPENAI_API_KEY','_NT_SYMBOL_PATH','PYTHONPATH')))
                    def communicate(timeout):
                        self.assertEqual(timeout,5.0)
                        return json.dumps(report),''
                    return SimpleNamespace(returncode=0,communicate=communicate)
                def target(*args,**kwargs):
                    order.append('target')
                    self.assertEqual(kwargs['env'].get('NODE_DISABLE_COMPILE_CACHE'), '1' if observed else None)
                    raise RuntimeError('inert-target-stop')
                environment = dict(os.environ)
                environment.pop('CA_PI_RPC_DIAGNOSTICS_DIR', None)
                if retained:
                    environment['CA_PI_RPC_DIAGNOSTICS_DIR'] = str(root / 'retained')
                os_model=SimpleNamespace(name='nt' if windows else 'posix',environ=os.environ)
                startup=lambda:SimpleNamespace(dwFlags=0,wShowWindow=0)
                with mock.patch.dict(os.environ, environment, clear=True), \
                     mock.patch.object(current, 'os', os_model), \
                     mock.patch.object(native,'os',os_model),mock.patch.object(bounded,'_VerifierProcess',side_effect=preflight), \
                     mock.patch.object(current,'live_pi_cli',return_value=(sys.executable,root/'unused-cli')), \
                     mock.patch.object(current,'read_json',return_value={'packages':['inert']}), \
                     mock.patch.object(subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')), \
                     mock.patch.object(subprocess,'Popen',side_effect=target), \
                     mock.patch.object(subprocess,'STARTUPINFO',side_effect=startup,create=True), \
                     mock.patch.object(subprocess,'STARTF_USESHOWWINDOW',1,create=True), \
                     mock.patch.object(subprocess,'SW_HIDE',0,create=True), \
                     mock.patch.object(subprocess,'CREATE_NEW_PROCESS_GROUP',0x200,create=True):
                    with self.assertRaisesRegex(RuntimeError,'inert-target-stop'):
                        run_rpc_commands(cwd,root/'agent',root/'home',_rpc_command=['inert-target'],_observe_shutdown=observed)
                self.assertEqual(order, expect, 'Windows diagnostic target must follow bounded hash-only preflight')

    def test_collector_provider_attribution_distinguishes_missing_refused_and_deadline(self):
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            selected = root / "cdb.exe"
            kernel = SimpleNamespace()
            original_digest = native._digest
            for failure in ("missing", "refused", "deadline", "os-error"):
                with self.subTest(failure=failure):
                    if selected.exists():
                        if selected.is_dir(): selected.rmdir()
                        else: selected.unlink()
                    if failure == "refused": selected.mkdir()
                    elif failure in ("deadline", "os-error"): selected.write_bytes(b"inert, never loaded")
                    def digest(path, deadline):
                        if failure == "os-error": raise OSError("PrivateFixtureValue")
                        return original_digest(path, deadline)
                    with mock.patch.object(native, "CDB", selected), \
                         mock.patch.object(native, "DEFAULT_CDB", selected), \
                         mock.patch.object(native, "_digest", side_effect=digest), \
                         mock.patch.object(native, "_system_directory") as inbox, \
                         mock.patch.object(native.subprocess, "Popen") as launch:
                        actual = native._debugger(33, kernel,
                            time.monotonic() - 1 if failure == "deadline" else time.monotonic() + 5,
                            binding={"handle": 11, "created": 44, "image": str(root / "node.exe")})
                    self.assertEqual(actual["status"], "unavailable")
                    self.assertIn("diagnostic", actual)
                    self.assertEqual(actual["diagnostic"]["phase"], "provider-hash-cdb")
                    self.assertEqual(actual["diagnostic"]["failure"], failure)
                    self.assertIsNone(actual["profile"])
                    self.assertIsNone(actual["worker"])
                    self.assertTrue(0 <= actual["diagnostic"]["elapsedMs"] <= 2**31 - 1)
                    self.assertTrue(0 <= actual["diagnostic"]["remainingMs"] <= 5000)
                    if failure == "deadline": self.assertEqual(actual["diagnostic"]["remainingMs"], 0)
                    inbox.assert_not_called()
                    launch.assert_not_called()
                    self.assertNotIn(str(root), json.dumps(actual))
                    self.assertNotIn("PrivateFixtureValue", json.dumps(actual))

    def test_current_instruction_projection_uses_actual_stack_frame_offsets(self):
        import _windows_dbgeng as sdk
        engine = object.__new__(sdk.Engine)
        large = False
        def call(name, index, types, *args):
            if (name, index) == ("systems", 9):
                sdk.C.cast(args[0], sdk.C.POINTER(sdk.U32)).contents.value = 16 if large else 1
            elif (name, index) == ("systems", 11):
                for index in range(args[1]): args[2][index] = index + 7
            elif (name, index) == ("control", 31):
                for index in range(24 if large else 1):
                    args[3][index].InstructionOffset = 0x1011
                    args[3][index].ReturnOffset = 0x2022
                sdk.C.cast(args[5], sdk.C.POINTER(sdk.U32)).contents.value = 24 if large else 1
            else:
                self.assertEqual((name, index), ("systems", 6))
            return 0
        engine.call = call
        engine.frame = lambda address: sdk.project_frame(
            b"node" if address == 0x2022 else b"kernelbase", address,
            0x2000 if address == 0x2022 else 0x1000, True)
        actual, truncated = engine.threads(time.monotonic() + 5, include_instruction=True)
        self.assertFalse(truncated)
        self.assertEqual(actual, [{"frames": [{"module": "node", "returnOffset": 0x22,
            "instructionModule": "kernelbase", "instructionOffset": 0x11}]}])
        legacy, _ = engine.threads(time.monotonic() + 5)
        self.assertEqual(legacy, [{"frames": [{"module": "node", "returnOffset": 0x22}]}])
        large = True
        capped, truncated = engine.threads(time.monotonic() + 5, include_instruction=True)
        self.assertTrue(truncated)
        self.assertLessEqual(len(capped), 16)
        self.assertTrue(all(len(row["frames"]) <= 24 for row in capped))
        self.assertLessEqual(len(json.dumps(capped, separators=(",", ":")).encode()), sdk.MAX_JSON - 2048)

    @staticmethod
    def _attribution_worker_result():
        import _windows_dbgeng as sdk
        return {"schemaVersion": 3, "profile": "inbox-v1", "status": "captured",
            "threads": [{"frames": [{"module": "node", "returnOffset": 16,
                "instructionModule": "kernelbase", "instructionOffset": 32}]}], "truncated": False,
            "pid": 33, "created": 44, "bound": True, "attached": True, "policy": sdk.POLICY,
            "detached": True, "hresult": 0, "phase": "detach", "elapsedMs": 4}

    def test_worker_v3_attribution_and_legacy_readers_remain_closed(self):
        import _windows_dbgeng as sdk
        good = self._attribution_worker_result()
        self.assertEqual(sdk.decode_result(json.dumps(good).encode(), 33, 44,
                                         profile="inbox-v1", version=3), good)
        legacy = copy.deepcopy(good)
        for key in ("phase", "elapsedMs"): legacy.pop(key)
        for frame in legacy["threads"][0]["frames"]:
            frame.pop("instructionModule"); frame.pop("instructionOffset")
        legacy["schemaVersion"] = 2
        self.assertEqual(sdk.decode_result(json.dumps(legacy).encode(), 33, 44, profile="inbox-v1"), legacy)
        self.assertIsNone(sdk.decode_result(json.dumps(legacy).encode(), 33, 44, profile="inbox-v1", version=3))
        legacy.pop("profile"); legacy["schemaVersion"] = 1
        self.assertEqual(sdk.decode_result(json.dumps(legacy).encode(), 33, 44), legacy)
        mutations = []
        for key, value in (("phase", "PrivateFixtureValue"), ("elapsedMs", True),
                           ("elapsedMs", 2**31), ("unexpected", "PrivateFixtureValue"),
                           ("policy", sdk.POLICY | sdk.ALLOW_NETWORK), ("detached", False)):
            mutations.append({**good, key: value})
        for key, value in (("instructionModule", "PrivateFixtureValue"), ("instructionOffset", True),
                           ("instructionOffset", 2**64), ("unexpected", "PrivateFixtureValue")):
            changed = copy.deepcopy(good)
            changed["threads"][0]["frames"][0][key] = value
            mutations.append(changed)
        unknown = copy.deepcopy(good)
        unknown["threads"][0]["frames"][0].update(instructionModule="Other", instructionOffset=None)
        self.assertEqual(sdk.decode_result(json.dumps(unknown).encode(), 33, 44), unknown)
        unknown["threads"][0]["frames"][0]["instructionOffset"] = 1
        mutations.append(unknown)
        for changed in mutations:
            with self.subTest(changed_keys=list(changed)):
                self.assertIsNone(sdk.decode_result(json.dumps(changed).encode(), 33, 44, profile="inbox-v1", version=3))

    def test_parent_preserves_validated_worker_failure_and_detach_fields(self):
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        collector_temp = tempfile.TemporaryDirectory
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for detached in (True, False):
                with self.subTest(detached=detached):
                    good = {**self._attribution_worker_result(), "status": "engine_failed" if detached else "cleanup_unknown",
                            "threads": [], "hresult": 0x80004005, "phase": "attach", "detached": detached}
                    kernel = SimpleNamespace(duplicate_query=mock.Mock(return_value=77), close=mock.Mock(), available=mock.Mock())
                    process = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(),
                        _handle=SimpleNamespace(Close=mock.Mock()), poll=lambda: 0)
                    with mock.patch.object(native.tempfile, "TemporaryDirectory",
                                           side_effect=lambda **kwargs: collector_temp(dir=root, **kwargs)), \
                         mock.patch.object(native, "_tool_profile", return_value=("inbox-v1", root,
                             {name: "a" * 64 for name in native.TOOL_FILES["inbox-v1"]})), \
                         mock.patch.object(native.subprocess, "STARTUPINFO", side_effect=SimpleNamespace, create=True), \
                         mock.patch.object(native.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                         mock.patch.object(native.subprocess, "Popen", return_value=process) as launch, \
                         mock.patch.object(native, "_collect", return_value=("captured", json.dumps(good).encode())):
                        actual = native._debugger(33, kernel, time.monotonic() + 5,
                            binding={"handle": 11, "created": 44, "image": str(root / "node.exe")})
                    self.assertEqual(actual["status"], good["status"])
                    self.assertEqual(actual["worker"], {key: good[key] for key in
                        ("bound", "attached", "detached", "hresult", "policy", "phase", "elapsedMs")})
                    self.assertEqual(actual["diagnostic"]["failure"], "engine" if detached else "cleanup")
                    self.assertEqual(actual["threads"], [])
                    self.assertEqual(launch.call_count, 1)
                    self.assertNotIn(str(root), json.dumps(actual))

    def test_worker_fixed_phase_distinguishes_provider_policy_and_stack_failure(self):
        import _windows_rpc_timeout as native
        import _windows_dbgeng as sdk
        from types import SimpleNamespace
        root = Path("inert-profile")
        request = {"schemaVersion": 3, "profile": "inbox-v1", "handle": 77, "pid": 33,
            "created": 44, "image": "inert-node.exe", "sdk": str(root),
            "hashes": {name: "a" * 64 for name in native.TOOL_FILES["inbox-v1"]},
            "deadline": time.monotonic() + 5}
        kernel = SimpleNamespace(snapshot=lambda handle: {"pid": 33, "created": 44,
            "state": "running", "image": request["image"]}, close=mock.Mock())
        owner = SimpleNamespace(IdentityDeadline=native.IdentityDeadline, WindowsKernel=lambda: kernel, _regular=lambda path, **kwargs: path,
                                _bound_tool_profile=lambda *args: root)
        for failure in ("provider-bind", "policy", "stack"):
            owner._bound_tool_profile = mock.Mock(side_effect=native.IdentityDeadline("PrivateFixtureValue")) if failure == "provider-bind" else lambda *args: root
            backend = SimpleNamespace(policy=lambda: sdk.ALLOW_NETWORK if failure == "policy" else sdk.POLICY,
                check=sdk.Engine.check, call=mock.Mock(return_value=0),
                threads=mock.Mock(side_effect=sdk.EngineFailure(0x80004005)), close=lambda: True)
            actual = sdk.run(request, owner, engine_factory=lambda path: backend)
            self.assertEqual(actual["status"], "deadline" if failure == "provider-bind" else "engine_failed")
            self.assertEqual(actual["phase"], failure)
            self.assertEqual(actual["detached"], failure != "provider-bind")
            self.assertEqual(actual["hresult"], None if failure == "provider-bind" else 0x80070005 if failure == "policy" else 0x80004005)
            self.assertIsNotNone(sdk.decode_result(json.dumps(actual).encode(), 33, 44, profile="inbox-v1", version=3))
            self.assertNotIn("PrivateFixtureValue", json.dumps(actual))
            if failure != "stack": backend.threads.assert_not_called()
            else: backend.threads.assert_called_once_with(mock.ANY, include_instruction=True)

    def test_dll_only_inbox_collector_uses_one_bound_inert_worker_without_cdb(self):
        import _windows_rpc_timeout as native
        import _windows_dbgeng as sdk
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            collector_temp = tempfile.TemporaryDirectory
            inbox = root / "protected-system"
            inbox.mkdir()
            for name in ("dbgeng.dll", "dbghelp.dll"):
                (inbox / name).write_bytes(("inert " + name).encode())
            image = root / "owned-node.exe"
            image.write_bytes(b"inert image, never executed")
            missing = root / "absent-sdk" / "cdb.exe"
            kernel = SimpleNamespace(
                duplicate_query=mock.Mock(return_value=77), close=mock.Mock(),
                snapshot=mock.Mock(return_value={"pid": 33, "created": 44,
                    "state": "running", "image": str(image)}), available=mock.Mock())
            api = SimpleNamespace(GetSystemDirectoryW=mock.Mock(
                side_effect=lambda buffer, count: self._fill_system_directory(buffer, count, inbox)))
            process = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(),
                                      _handle=SimpleNamespace(Close=mock.Mock()), poll=lambda: 0)
            requests = []
            class Backend:
                check = staticmethod(sdk.Engine.check)
                def __init__(self, path):
                    self_test.assertEqual(path, inbox)
                def policy(self):
                    return sdk.POLICY
                def call(self, *args):
                    return 0
                def threads(self, deadline, *, include_instruction=False):
                    row = {"module": "node", "returnOffset": 16}
                    if include_instruction:
                        row.update(instructionModule="kernelbase", instructionOffset=32)
                    return [{"frames": [row]}], False
                def close(self):
                    return True
            self_test = self
            # Preserve the actual encoded request after the parent's stdin close.
            class Input(io.BytesIO):
                def close(self):
                    if not self.closed and self.getvalue():
                        requests.append(json.loads(self.getvalue()))
                    super().close()
            process.stdin = Input()
            def collect(child, available, *, deadline, _diagnostic=None):
                self.assertIs(child, process)
                response = sdk.run(requests[-1], native, engine_factory=Backend)
                return "captured", json.dumps(response).encode()
            with mock.patch.object(native.tempfile, "TemporaryDirectory",
                                   side_effect=lambda **kwargs: collector_temp(dir=root, **kwargs)), \
                 mock.patch.object(native, "CDB", missing), \
                 mock.patch.object(native, "DEFAULT_CDB", missing, create=True), \
                 mock.patch.object(native.ctypes, "WinDLL", return_value=api, create=True), \
                 mock.patch.object(native, "WindowsKernel", return_value=kernel), \
                 mock.patch.object(native.subprocess, "STARTUPINFO", side_effect=SimpleNamespace, create=True), \
                 mock.patch.object(native.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                 mock.patch.object(native.subprocess, "Popen", return_value=process) as launch, \
                 mock.patch.object(native, "_collect", side_effect=collect), \
                 mock.patch.dict(os.environ, {"SystemRoot": str(root / "attacker"),
                     "WINDIR": str(root / "attacker"), "PATH": str(root / "attacker"),
                     "_NT_SYMBOL_PATH": "PrivateFixtureValue"}):
                actual = native._debugger(33, kernel, time.monotonic() + 5,
                    binding={"handle": 11, "created": 44, "image": str(image)})
            self.assertEqual(actual["status"], "captured", "DLL-only inbox must reach the bound worker")
            self.assertEqual(actual["profile"], "inbox-v1")
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(launch.call_args.kwargs["cwd"].parent, root)
            self.assertEqual(launch.call_args.kwargs["startupinfo"].lpAttributeList, {"handle_list": [77]})
            self.assertEqual(launch.call_args.kwargs["creationflags"], 0x08000000)
            self.assertEqual(set(actual["toolHashes"]), {"dbgeng.dll", "dbghelp.dll"})
            self.assertEqual(actual["toolHashes"], {name: hashlib.sha256((inbox / name).read_bytes()).hexdigest()
                                                    for name in ("dbgeng.dll", "dbghelp.dll")})
            self.assertNotIn("PrivateFixtureValue", json.dumps(actual))
            self.assertFalse((inbox / "cdb.exe").exists())
            kernel.duplicate_query.assert_called_once_with(11)
            self.assertEqual(kernel.close.call_args_list, [mock.call(77), mock.call(77)])
            process._handle.Close.assert_called_once_with()

    def test_profiles_preserve_sdk_precedence_and_refuse_partial_or_unsafe_files(self):
        import _windows_rpc_timeout as native
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            inbox, sdk_root = root / "inbox", root / "sdk"
            inbox.mkdir()
            sdk_root.mkdir()
            for folder, names in ((inbox, native.TOOL_FILES["inbox-v1"]),
                                  (sdk_root, native.TOOL_FILES["sdk-v1"])):
                for name in names:
                    (folder / name).write_bytes((folder.name + name).encode())
            selected = sdk_root / "cdb.exe"
            with mock.patch.object(native, "CDB", selected), \
                 mock.patch.object(native, "DEFAULT_CDB", selected), \
                 mock.patch.object(native, "_system_directory", return_value=inbox) as system:
                profile, actual, hashes = native._tool_profile(time.monotonic() + 5)
                self.assertEqual((profile, actual), ("sdk-v1", sdk_root))
                self.assertEqual(set(hashes), set(native.TOOL_FILES["sdk-v1"]))
                system.assert_not_called()
                for name in native.TOOL_FILES["sdk-v1"]:
                    with self.subTest(missing_sdk_member=name):
                        original = (sdk_root / name).read_bytes()
                        (sdk_root / name).unlink()
                        with self.assertRaises(OSError):
                            native._tool_profile(time.monotonic() + 5)
                        system.assert_not_called()
                        (sdk_root / name).write_bytes(original)
            with mock.patch.object(native, "CDB", root / "override-missing" / "cdb.exe"), \
                 mock.patch.object(native, "_system_directory") as system:
                with self.assertRaisesRegex(ValueError, "selected SDK unavailable"):
                    native._tool_profile(time.monotonic() + 5)
                system.assert_not_called()
            missing = root / "default-missing" / "cdb.exe"
            with mock.patch.object(native, "CDB", missing), \
                 mock.patch.object(native, "DEFAULT_CDB", missing), \
                 mock.patch.object(native, "_system_directory", return_value=inbox):
                profile, actual, hashes = native._tool_profile(time.monotonic() + 5)
                self.assertEqual((profile, actual), ("inbox-v1", inbox))
                self.assertEqual(set(hashes), {"dbgeng.dll", "dbghelp.dll"})
                for name in native.TOOL_FILES["inbox-v1"]:
                    with self.subTest(linked_inbox_member=name):
                        target = root / ("target-" + name)
                        (inbox / name).rename(target)
                        (inbox / name).symlink_to(target)
                        with self.assertRaisesRegex(ValueError, "unsupported file identity"):
                            native._tool_profile(time.monotonic() + 5)
                        (inbox / name).unlink()
                        target.rename(inbox / name)
                with self.assertRaisesRegex(ValueError, "identity bound"):
                    native._tool_profile(time.monotonic() - 1)
            linked = root / "linked-sdk"
            linked.symlink_to(sdk_root, target_is_directory=True)
            with mock.patch.object(native, "CDB", linked / "cdb.exe"), \
                 mock.patch.object(native, "_system_directory") as system:
                with self.assertRaisesRegex(ValueError, "unsupported file identity"):
                    native._tool_profile(time.monotonic() + 5)
                system.assert_not_called()
            # A missing SDK leaf must not hide a reparse ancestor.
            absent_below_link = linked / "missing" / "cdb.exe"
            with mock.patch.object(native, "CDB", absent_below_link), \
                 mock.patch.object(native, "DEFAULT_CDB", absent_below_link), \
                 mock.patch.object(native, "_system_directory", return_value=inbox) as system:
                with self.assertRaisesRegex(ValueError, "unsupported file identity"):
                    native._tool_profile(time.monotonic() + 5)
                system.assert_not_called()

    def test_system_directory_uses_typed_os_api_and_rejects_invalid_paths(self):
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            inbox = root / "protected"
            inbox.mkdir()
            for failure in (None, "zero", "oversize", "relative", "mismatch", "linked"):
                with self.subTest(failure=failure):
                    def query(buffer, count):
                        if failure == "zero":
                            return 0
                        if failure == "oversize":
                            return count
                        path = Path("relative") if failure == "relative" else inbox
                        if failure == "linked":
                            path = root / "link"
                            if not path.exists():
                                path.symlink_to(inbox, target_is_directory=True)
                        size = self._fill_system_directory(buffer, count, path)
                        return size + int(failure == "mismatch")
                    function = mock.Mock(side_effect=query)
                    api = SimpleNamespace(GetSystemDirectoryW=function)
                    with mock.patch.object(native.ctypes, "WinDLL", return_value=api, create=True) as loader, \
                         mock.patch.dict(os.environ, {"SystemRoot": "PrivateFixtureValue", "WINDIR": "PrivateFixtureValue", "PATH": "PrivateFixtureValue"}):
                        if failure is None:
                            self.assertEqual(native._system_directory(), inbox)
                        else:
                            with self.assertRaises(ValueError):
                                native._system_directory()
                    loader.assert_called_once_with("kernel32", use_last_error=True, winmode=0x800)
                    self.assertIs(function.restype, native.wintypes.UINT)
                    self.assertEqual(function.argtypes, [native.wintypes.LPWSTR, native.wintypes.UINT])

    def test_worker_rebinds_closed_profile_path_hashes_and_target_before_engine(self):
        import _windows_rpc_timeout as native
        import _windows_dbgeng as sdk
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            inbox, sdk_root, foreign = (root / name for name in ("inbox", "sdk", "foreign"))
            for folder in (inbox, sdk_root, foreign):
                folder.mkdir()
                for name in native.TOOL_FILES["sdk-v1"]:
                    (folder / name).write_bytes(("inert " + name).encode())
            image = root / "image.exe"
            image.write_bytes(b"inert")
            snapshot = {"pid": 33, "created": 44, "state": "running", "image": str(image)}
            kernel = SimpleNamespace(snapshot=mock.Mock(return_value=snapshot), close=mock.Mock())
            backend = SimpleNamespace(policy=lambda: sdk.POLICY, check=sdk.Engine.check,
                call=mock.Mock(return_value=0), threads=lambda deadline: ([{"frames": [{"module": "node", "returnOffset": 1}]}], False),
                close=lambda: True)
            for profile, folder in (("inbox-v1", inbox), ("sdk-v1", sdk_root)):
                request = {"schemaVersion": 2, "profile": profile, "handle": 77, "pid": 33, "created": 44,
                    "image": str(image), "sdk": str(folder), "hashes": {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                    for name in native.TOOL_FILES[profile]}, "deadline": time.monotonic() + 5}
                for failure in (None, "profile", "root", "extra", "missing", "hash", "tamper", "pid", "created", "image", "state", "deadline", "network", "cleanup"):
                    with self.subTest(profile=profile, failure=failure):
                        changed = copy.deepcopy(request)
                        changed["deadline"] = time.monotonic() + 5
                        state = dict(snapshot)
                        if failure == "profile": changed["profile"] = "PrivateFixtureValue"
                        if failure == "root": changed["sdk"] = str(foreign)
                        if failure == "extra": changed["hashes"]["other.dll"] = "a" * 64
                        if failure == "missing": changed["hashes"].pop("dbghelp.dll")
                        if failure == "hash": changed["hashes"]["dbgeng.dll"] = "b" * 64
                        if failure == "tamper": (folder / "dbgeng.dll").write_bytes(b"tampered")
                        if failure == "pid": state["pid"] = 99
                        if failure == "created": state["created"] = 55
                        if failure == "image": state["image"] = str(foreign / "dbgeng.dll")
                        if failure == "state": state["state"] = "signaled"
                        if failure == "deadline": changed["deadline"] = time.monotonic() - 1
                        kernel.snapshot.return_value = state
                        backend.policy = lambda: sdk.ALLOW_NETWORK if failure == "network" else sdk.POLICY
                        backend.close = lambda: failure != "cleanup"
                        factory = mock.Mock(return_value=backend)
                        with mock.patch.object(native, "CDB", sdk_root / "cdb.exe"), \
                             mock.patch.object(native, "_system_directory", return_value=inbox), \
                             mock.patch.object(native, "WindowsKernel", return_value=kernel):
                            actual = sdk.run(changed, native, engine_factory=factory)
                        if failure == "tamper": (folder / "dbgeng.dll").write_bytes(b"inert dbgeng.dll")
                        if failure is None:
                            self.assertEqual(actual["status"], "captured")
                            self.assertEqual(factory.call_args_list, [mock.call(folder)])
                            self.assertEqual(actual["profile"], profile)
                            self.assertIsNotNone(sdk.decode_result(json.dumps(actual).encode(), 33, 44, profile=profile))
                        else:
                            self.assertNotEqual(actual["status"], "captured")
                            self.assertEqual(actual["threads"], [])
                            if failure not in ("network", "cleanup"):
                                factory.assert_not_called()
                            if failure in ("pid", "created", "image", "state"):
                                self.assertEqual(actual["status"], "identity_refused")
                            if failure == "cleanup": self.assertEqual(actual["status"], "cleanup_unknown")
                        self.assertNotIn("PrivateFixtureValue", json.dumps(actual))

    def test_profile_transport_keeps_legacy_decoder_and_refuses_mismatches(self):
        import _windows_dbgeng as sdk
        old = {"schemaVersion": 1, "status": "captured", "threads": [{"frames": [
            {"module": "node", "returnOffset": 16}]}], "truncated": False,
            "pid": 33, "created": 44, "bound": True, "attached": True,
            "policy": sdk.POLICY, "detached": True, "hresult": 0}
        self.assertEqual(sdk.decode_result(json.dumps(old).encode(), 33, 44), old)
        self.assertIsNone(sdk.decode_result(json.dumps(old).encode(), 33, 44, profile="inbox-v1"))
        current = {**old, "schemaVersion": 2, "profile": "inbox-v1"}
        self.assertEqual(sdk.decode_result(json.dumps(current).encode(), 33, 44, profile="inbox-v1"), current)
        self.assertIsNone(sdk.decode_result(json.dumps(current).encode(), 33, 44, profile="sdk-v1"))
        for key, value in (("profile", "PrivateFixtureValue"), ("profile", None), ("schemaVersion", True),
                           ("schemaVersion", 3), ("policy", sdk.POLICY | sdk.ALLOW_NETWORK),
                           ("bound", False), ("detached", False), ("pid", 99), ("created", 55),
                           ("threads", [{"frames": [{"module": "private", "returnOffset": 1}]}])):
            with self.subTest(key=key, value_kind=type(value).__name__):
                self.assertIsNone(sdk.decode_result(json.dumps({**current, key: value}).encode(), 33, 44, profile="inbox-v1"))
        self.assertIsNone(sdk.decode_result(json.dumps({**current, "unexpected": 1}).encode(), 33, 44, profile="inbox-v1"))

    def test_collector_rejects_wrong_profile_legacy_or_malformed_worker_transport(self):
        import _windows_rpc_timeout as native
        import _windows_dbgeng as sdk
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            collector_temp = tempfile.TemporaryDirectory
            hashes = {name: "a" * 64 for name in native.TOOL_FILES["inbox-v1"]}
            good = self._attribution_worker_result()
            previous = copy.deepcopy(good)
            previous.pop("phase"); previous.pop("elapsedMs")
            previous["schemaVersion"] = 2
            for frame in previous["threads"][0]["frames"]:
                frame.pop("instructionModule"); frame.pop("instructionOffset")
            legacy = {k: v for k, v in previous.items() if k != "profile"}
            legacy["schemaVersion"] = 1
            vectors = (("captured", json.dumps(good).encode(), "captured"),
                       ("captured", json.dumps({**good, "profile": "sdk-v1"}).encode(), "transport_failed"),
                       ("captured", json.dumps(legacy).encode(), "transport_failed"),
                       ("captured", json.dumps(previous).encode(), "transport_failed"),
                       ("captured", b"PrivateFixtureValue", "transport_failed"),
                       ("deadline", b"PrivateFixtureValue", "deadline"),
                       ("output_limit", b"PrivateFixtureValue", "output_limit"))
            for transport, raw, expected in vectors:
                with self.subTest(expected=expected, raw_length=len(raw)):
                    kernel = SimpleNamespace(duplicate_query=mock.Mock(return_value=77), close=mock.Mock(), available=mock.Mock())
                    process = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(),
                        _handle=SimpleNamespace(Close=mock.Mock()), poll=lambda: 0)
                    with mock.patch.object(native.tempfile, "TemporaryDirectory",
                                           side_effect=lambda **kwargs: collector_temp(dir=root, **kwargs)), \
                         mock.patch.object(native, "_tool_profile", return_value=("inbox-v1", root, hashes)), \
                         mock.patch.object(native.subprocess, "STARTUPINFO", side_effect=SimpleNamespace, create=True), \
                         mock.patch.object(native.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                         mock.patch.object(native.subprocess, "Popen", return_value=process) as launch, \
                         mock.patch.object(native, "_collect", return_value=(transport, raw)):
                        actual = native._debugger(33, kernel, time.monotonic() + 5,
                            binding={"handle": 11, "created": 44, "image": str(root / "image.exe")})
                    self.assertEqual(actual["status"], expected)
                    self.assertEqual(actual["profile"], "inbox-v1")
                    self.assertEqual(launch.call_count, 1)
                    self.assertEqual(launch.call_args.kwargs["cwd"].parent, root)
                    self.assertEqual(launch.call_args.kwargs["startupinfo"].lpAttributeList, {"handle_list": [77]})
                    self.assertEqual(launch.call_args.kwargs["creationflags"], 0x08000000)
                    if expected != "captured": self.assertEqual(actual["threads"], [])
                    self.assertEqual(actual["truncated"], expected == "output_limit")
                    self.assertNotIn("PrivateFixtureValue", json.dumps(actual))
                    kernel.close.assert_called_once_with(77)
                    process._handle.Close.assert_called_once_with()

    @staticmethod
    def _fill_system_directory(buffer, count, path):
        value = str(path)
        if len(value) >= count:
            return len(value) + 1
        buffer.value = value
        return len(value)



class DebuggerPhaseProgressTests(unittest.TestCase):
    def test_owned_phase_worker_deadline_retains_last_announced_boundary_without_frames(self):
        import _windows_rpc_timeout as native
        from types import SimpleNamespace
        real_popen = subprocess.Popen
        real_startup = getattr(subprocess, "STARTUPINFO", SimpleNamespace)
        program = r"""# CA_OWNED_SDK_PHASE_WORKER
import json,os,sys,time
request=json.loads(sys.stdin.buffer.read(4097))
record={"schemaVersion":1,"pid":request["pid"],"created":request["created"],
        "profile":request["profile"],"workerPid":os.getpid(),"phase":"wait"}
sys.stdout.buffer.write(b"CA_SDK_PHASE "+json.dumps(record,separators=(",",":")).encode()+b"\n")
sys.stdout.buffer.flush()
time.sleep(10)
"""
        children=[];readers=[];pending=bytearray();lock=threading.Lock()
        class Worker:
            def __init__(self, child):
                self.child=child;self.pid=child.pid;self.stdin=child.stdin;self.stdout=child.stdout
                self._handle=SimpleNamespace(Close=mock.Mock())
            @property
            def returncode(self): return self.child.returncode
            def poll(self): return self.child.poll()
            def wait(self, timeout): return self.child.wait(timeout=timeout)
            def kill(self): return self.child.kill()
        def launch(argv, **kwargs):
            with mock.patch.object(subprocess,"STARTUPINFO",real_startup,create=True):
                child=real_popen([sys.executable,"-I","-S","-B","-c",program],cwd=kwargs["cwd"],
                    env=kwargs["env"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0)
            children.append(child)
            def drain():
                while chunk:=child.stdout.read(4096):
                    with lock: pending.extend(chunk)
            thread=threading.Thread(target=drain,daemon=True);thread.start();readers.append(thread)
            return Worker(child)
        def available(stream):
            with lock:return len(pending)
        def read(stream,count):
            with lock:
                raw=bytes(pending[:count]);del pending[:count];return raw
        collect=native._collect
        def collect_owned(child, probe, *, deadline, **kwargs):
            return collect(child,probe,deadline=deadline,_read=read,**kwargs)
        kernel=SimpleNamespace(duplicate_query=mock.Mock(return_value=77),close=mock.Mock(),available=available)
        try:
            with tempfile.TemporaryDirectory(prefix="ca-sdk-phase-test-") as directory:
                root=Path(directory).resolve();owner_temp=tempfile.TemporaryDirectory
                with mock.patch.object(native.tempfile,"TemporaryDirectory",side_effect=lambda **kw:owner_temp(dir=root,**kw)), \
                     mock.patch.object(native,"_tool_profile",return_value=("inbox-v1",root,{"dbgeng.dll":"a"*64,"dbghelp.dll":"b"*64})), \
                     mock.patch.object(native.subprocess,"STARTUPINFO",side_effect=SimpleNamespace,create=True), \
                     mock.patch.object(native.subprocess,"CREATE_NO_WINDOW",0x08000000,create=True), \
                     mock.patch.object(native.subprocess,"Popen",side_effect=launch), \
                     mock.patch.object(native,"_collect",side_effect=collect_owned):
                    started=time.monotonic()
                    result=native._debugger(33,kernel,started+1.0,
                        binding={"handle":11,"created":44,"image":str(root/"inert-node.exe")})
                self.assertTrue(result["diagnostic"]["workerSpawned"], "owned inert worker must actually launch")
                self.assertEqual(len(children),1)
                self.assertEqual(result["diagnostic"]["phase"],"sdk-wait",
                    "the last closed owned SDK phase was lost when final JSON never arrived")
                self.assertIn(result["status"],("deadline","cleanup_unknown"))
                self.assertEqual(result["diagnostic"]["primaryStatus"],"deadline")
                self.assertEqual(result["diagnostic"]["failure"],"deadline")
                self.assertEqual(result["threads"],[]);self.assertIsNone(result["worker"])
                self.assertEqual(native.SECONDS,5.0)
                self.assertLess(time.monotonic()-started,3.0)
                kernel.duplicate_query.assert_called_once_with(11)
                self.assertEqual(kernel.close.call_args_list,[mock.call(77)])
        finally:
            for child in children:
                if child.poll() is None:child.kill()
                child.wait(timeout=2)
                if child.stdout is not None and not child.stdout.closed:child.stdout.close()
            for reader in readers:reader.join(timeout=2);self.assertFalse(reader.is_alive())

    def test_progress_decoder_refuses_unbound_malformed_partial_and_unbounded_rows(self):
        import _windows_dbgeng as sdk
        good={"schemaVersion":1,"pid":33,"created":44,"profile":"inbox-v1","workerPid":123,"phase":"wait"}
        def encode(row):return b"CA_SDK_PHASE "+json.dumps(row,separators=(",",":")).encode()+b"\n"
        def decode(raw):return sdk.decode_progress(raw,33,44,profile="inbox-v1",worker_pid=123)
        self.assertEqual(decode(encode(good)),("wait",b""))
        self.assertEqual(decode(b'{"legacy":true}'),(None,b'{"legacy":true}'))
        bad=[b"",b"CA_SDK_PHASE {",b"CA_SDK_PHASE {broken}\n",b"CA_SDK_PHASE "+b"x"*300+b"\n",
             b'CA_SDK_PHASE {"schemaVersion":1,"schemaVersion":1,"pid":33,"created":44,"profile":"inbox-v1","workerPid":123,"phase":"wait"}\n']
        for key,value in (("schemaVersion",True),("pid",34),("pid",True),("created",45),("workerPid",124),
                          ("profile","sdk-v1"),("phase","PRIVATE_PHASE_CANARY"),("extra","PRIVATE_PHASE_CANARY")):
            bad.append(encode({**good,key:value}))
        bad.extend((encode(good)+encode(good),encode(good)+encode({**good,"phase":"attach"})))
        for raw in bad:
            with self.subTest(kind=hashlib.sha256(raw).hexdigest()[:8]):self.assertIsNone(decode(raw)[0])
        partial=b"CA_SDK_PHASE {"
        self.assertEqual(decode(encode(good)+partial),("wait",partial))
        with_final=encode(good)+b'{"legacy":true}'
        self.assertEqual(decode(with_final),("wait",b'{"legacy":true}'))
        self.assertIsNone(sdk.decode_progress(encode(good),33,44,profile="inbox-v1",worker_pid=None)[0])
        self.assertIsNone(sdk.decode_progress(encode(good),33,45,profile="inbox-v1",worker_pid=123)[0])

    def test_real_worker_phase_callbacks_precede_inert_boundaries_and_keep_final_schema(self):
        import _windows_dbgeng as sdk
        from types import SimpleNamespace
        request={"schemaVersion":3,"profile":"inbox-v1","handle":77,"pid":33,"created":44,
                 "image":"inert-node.exe","sdk":"inert-profile","hashes":{"dbgeng.dll":"a"*64,"dbghelp.dll":"b"*64},
                 "deadline":time.monotonic()+5,"progress":True}
        stream=io.BytesIO();emit=sdk._progress_writer(request,stream);self.assertIsNotNone(emit)
        emit("input");seen=[]
        def check_phase(expected):
            actual,tail=sdk.decode_progress(stream.getvalue(),33,44,profile="inbox-v1",worker_pid=os.getpid())
            self.assertEqual(actual,expected);self.assertEqual(tail,b"");seen.append(expected)
        def snapshot(handle):
            check_phase("identity")
            return {"pid":33,"created":44,"state":"running","image":"inert-node.exe"}
        kernel=SimpleNamespace(snapshot=snapshot,close=mock.Mock())
        def provider(*args):check_phase("provider-bind");return Path("inert-profile")
        def policy():check_phase("policy");return sdk.POLICY
        def call(name,index,*args):check_phase("attach" if name=="client" else "wait");return 0
        def threads(deadline,*,include_instruction):
            check_phase("stack")
            return [{"frames":[{"module":"node","returnOffset":1,"instructionModule":"kernelbase","instructionOffset":2}]}],False
        def close():check_phase("detach");return True
        engine=SimpleNamespace(check=sdk.Engine.check,policy=policy,call=call,threads=threads,close=close)
        def factory(path):check_phase("engine-create");return engine
        native=SimpleNamespace(WindowsKernel=lambda:kernel,_regular=lambda path,**kwargs:path,_bound_tool_profile=provider)
        result=sdk.run(request,native,engine_factory=factory,_progress=emit)
        self.assertEqual(seen,["identity","provider-bind","engine-create","policy","attach","wait","stack","detach"])
        self.assertEqual(result["status"],"captured")
        self.assertEqual(sdk.decode_result(json.dumps(result).encode(),33,44,profile="inbox-v1",version=3),result)
        self.assertEqual(set(result),{"schemaVersion","profile","phase","elapsedMs","status","threads","truncated",
                                     "pid","created","bound","attached","policy","detached","hresult"})
        raw=stream.getvalue();self.assertLessEqual(len(raw),sdk.MAX_PROGRESS_BYTES)
        self.assertEqual(len(raw.splitlines()),9)
        emit("PRIVATE_PHASE_CANARY");emit("wait");self.assertEqual(stream.getvalue(),raw)
        legacy=dict(request);legacy.pop("progress");self.assertIsNone(sdk._progress_writer(legacy,io.BytesIO()))
        refused={**request,"progress":False};self.assertIsNone(sdk._progress_writer(refused,io.BytesIO()))
        self.assertEqual(sdk.run(refused,native,engine_factory=factory)["status"],"input_refused")
        class Broken:
            def write(self,raw):raise OSError("PRIVATE_PHASE_CANARY")
            def flush(self):raise AssertionError("must not flush after failed write")
        writer=sdk._progress_writer(request,Broken());writer("input");writer("identity")

if __name__ == "__main__":
    if "--platform-partition" in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument("--platform-partition", choices=PLATFORM_PACKAGE_PARTITIONS, required=True)
        args = parser.parse_args()
        PLATFORM_PACKAGE_PARTITION = args.platform_partition
        result = unittest.TextTestRunner(verbosity=2).run(platform_package_suites()[PLATFORM_PACKAGE_PARTITION])
        raise SystemExit(0 if result.wasSuccessful() else 1)
    elif "--rpc-commands" in sys.argv:
        sys.argv = [
            sys.argv[0],
            "PiPackageTests.test_real_isolated_rpc_command_discovery_and_keyed_status",
        ]
    unittest.main(verbosity=2)
