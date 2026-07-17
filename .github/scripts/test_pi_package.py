#!/usr/bin/env python3
"""Task 2 package, generation, and independent-release contract tests."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from queue import Empty, Queue

from pi_cli_resolver import resolve_pi_cli_path as _resolve_pi_cli_path


REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "ca-pi"
TOOLS = PLUGIN / "tools"


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


def run_rpc_commands(
    cwd: Path,
    agent_dir: Path,
    home: Path,
    *,
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
        [node, str(cli), "install", str(REPO.resolve()), "--no-approve"],
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
        provider.write_text(
            """import { createAssistantMessageEventStream } from '@earendil-works/pi-ai';

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
}
"""
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
    reader: threading.Thread | None = None
    try:
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
        if _on_process_started is not None:
            _on_process_started(process, reader)

        def send(record: dict) -> None:
            assert process.stdin is not None
            process.stdin.write(json.dumps(record, separators=(",", ":")) + "\n")
            process.stdin.flush()

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
                            else "/ca-btw  __CA_ALIAS_SENTINEL__  "
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
                break
            if line is None:
                break
            value = decode(line)
            records.append(value)
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
                break

        process.stdin.close()
        returncode = process.wait(timeout=10)
        reader.join(timeout=5)
        if reader.is_alive():
            raise AssertionError("Pi RPC stdout reader did not stop after process exit")
        while True:
            try:
                line = output.get_nowait()
            except Empty:
                break
            if line is not None:
                records.append(decode(line))
        stderr = process.stderr.read()
        if returncode != 0:
            raise AssertionError(f"Pi RPC exited {returncode}: {stderr[-2000:]}")
        if not any(record.get("id") == "commands" for record in records):
            raise AssertionError(f"Pi RPC did not answer get_commands: {records!r}; stderr={stderr[-2000:]}")
        if invoke_read_context and not any(record.get("id") == "state" for record in records):
            raise AssertionError(f"Pi RPC did not answer get_state: {records!r}; stderr={stderr[-2000:]}")
        if (invoke_alias or invoke_doctor or invoke_read_context) and not any(record.get("id") == "capture" for record in records):
            raise AssertionError(f"Pi RPC did not capture the alias turn: {records!r}; stderr={stderr[-2000:]}")
        if invoke_enforcement_fault and not any(record.get("type") == "agent_settled" for record in records):
            raise AssertionError(f"Pi RPC did not settle the fault-injection turn: {records!r}; stderr={stderr[-2000:]}")
        return records
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
        if process.stdout is not None and not process.stdout.closed:
            try:
                process.stdout.close()
            except OSError as error:
                cleanup_errors.append(f"stdout close failed: {error}")
        if reader is not None and reader.is_alive():
            reader.join(timeout=2)
            if reader.is_alive():
                cleanup_errors.append("stdout reader remained alive")
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


def load_build_host_packages():
    path = REPO / "tools" / "build-host-packages.py"
    spec = importlib.util.spec_from_file_location("build_host_packages", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        'pi-version: ["0.80.5", "0.80.6"]',
        "npm install --global @earendil-works/pi-coding-agent@${{ matrix.pi-version }} --ignore-scripts",
        "npm ci --ignore-scripts",
    ):
        if token not in matrix:
            violations.append(f"ca-pi-tools missing {token}")
    if re.search(r"(?m)^\s{8}run: npm test -- test/package\.test\.ts\s*$", matrix) is None:
        violations.append("ca-pi-tools does not execute the native package test")
    if re.search(
        r"(?m)^\s{8}run: npm test -- test/activation\.test\.ts test/commands\.test\.ts test/status\.test\.ts\s*$",
        matrix,
    ) is None:
        violations.append("ca-pi-tools does not execute the focused lifecycle tests")
    if re.search(
        r"(?m)^\s{8}run: python \.github/scripts/test_pi_package\.py --rpc-commands\s*$",
        matrix,
    ) is None:
        violations.append("ca-pi-tools does not execute the live package RPC test")

    latest = job("ca-pi-latest")
    if re.search(r"(?m)^    continue-on-error: true\s*$", latest) is None:
        violations.append("ca-pi-latest must remain explicitly nonblocking at job level")
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
    for dependency in ("ca-pi-tools", "ca-pi-latest", "version-bump-pi"):
        if dependency not in needs:
            violations.append(f"ci-passed.needs missing {dependency}")
    return violations


class PiPackageTests(unittest.TestCase):
    def test_local_prefix_pi_cli_resolves_package_above_dot_bin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / "prefix"
            executable = prefix / "node_modules" / ".bin" / "pi.cmd"
            cli = (
                prefix / "node_modules" / "@earendil-works"
                / "pi-coding-agent" / "dist" / "cli.js"
            )
            executable.parent.mkdir(parents=True)
            cli.parent.mkdir(parents=True)
            executable.write_text("@echo off\n", encoding="utf-8")
            cli.write_text("// fixture\n", encoding="utf-8")

            self.assertEqual(_resolve_pi_cli_path(executable), cli.resolve())

    def test_parent_embeds_exact_generated_hardened_child_fingerprint(self):
        child = (PLUGIN / "extensions" / "codearbiter-child.js").read_bytes()
        expected = hashlib.sha256(child).hexdigest()
        parent = (PLUGIN / "extensions" / "codearbiter.js").read_text(encoding="utf-8")
        self.assertIn(expected, parent)
        self.assertEqual(len(re.findall(re.escape(expected), parent)), 1)

    def test_root_manifest_is_private_dependency_free_pi_metadata(self):
        data = read_json(REPO / "package.json")
        self.assertEqual(data["name"], "ca-pi")
        self.assertEqual(data["version"], "0.1.0")
        self.assertIs(data["private"], True)
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
        self.assertEqual(data["name"], "ca-pi")
        self.assertEqual(data["version"], "0.1.0")
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
            },
        )
        self.assertEqual(
            data["devDependencies"],
            {
                "@types/node": "25.9.4",
                "esbuild": "0.28.1",
                "typescript": "5.9.3",
                "vitest": "4.1.9",
            },
        )
        self.assertNotIn("dependencies", data)

    def test_generated_root_manifest_matches_renderer_bytes(self):
        module = load_build_host_packages()
        host = module.host_descriptor("pi", str(REPO))
        expected = module.render_package(host, "0.1.0")
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
            ["windows-supervisor.js"],
        )
        supervisor = helpers / "windows-supervisor.js"
        text = supervisor.read_bytes().decode("utf-8", errors="strict")
        self.assertIn("STARTED", text)
        self.assertNotIn("sourceMappingURL", text)
        build = (TOOLS / "build.mjs").read_text(encoding="utf-8")
        self.assertIn('entryPoints: ["src/windows-supervisor.ts"]', build)
        self.assertIn('outfile: "../helpers/windows-supervisor.js"', build)
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
            "ca-pi: ${{ steps.filter.outputs.ca-pi }}",
            "- 'plugins/ca-pi/**'",
            "ca-pi-tools:",
            "version-bump-pi:",
            'os: [ubuntu-latest, windows-latest, macos-latest]',
            'pi-version: ["0.80.5", "0.80.6"]',
            "npm install --global @earendil-works/pi-coding-agent@${{ matrix.pi-version }} --ignore-scripts",
            "npm ci --ignore-scripts",
            "Test package, module identity, compatibility, and native binding",
            "Test activation, commands, and status lifecycle",
            "Test real package RPC activation and aliases",
            'python tools/build-host-packages.py --check --release-guard-base "$BASE_COMMIT"',
            "ca-pi-latest:",
            "- ca-pi-tools",
            "- ca-pi-latest",
            "- version-bump-pi",
        )
        for text in required:
            self.assertIn(text, ci)
        matrix_job = ci.split("  ca-pi-tools:", 1)[1].split("\n  ca-pi-latest:", 1)[0]
        self.assertEqual(matrix_job.count("--ignore-scripts"), 2)
        latest_job = ci.split("  ca-pi-latest:", 1)[1].split("\n  hooks:", 1)[0]
        self.assertIn("Report latest version and test installed runtime admission", latest_job)
        self.assertEqual(pi_ci_contract_violations(ci), [])

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

        focused_nooped = ci.replace(
            "        run: npm test -- test/activation.test.ts test/commands.test.ts test/status.test.ts\n",
            "        run: echo npm test -- test/activation.test.ts test/commands.test.ts test/status.test.ts\n",
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(focused_nooped),
            "every matrix cell must execute the focused lifecycle tests",
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

        latest_continue_commented = ci.replace(
            "    continue-on-error: true\n",
            "    # continue-on-error: true\n",
            1,
        )
        self.assertTrue(
            pi_ci_contract_violations(latest_continue_commented),
            "the latest canary must retain an active job-level nonblocking declaration",
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
        catalog = read_json(PLUGIN / "generated" / "command-catalog.json")
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
        skill_path = (PLUGIN / "skills" / "ca-btw" / "SKILL.md").resolve()
        raw_skill = skill_path.read_text(encoding="utf-8")
        self.assertTrue(raw_skill.startswith("---\n"))
        body = raw_skill.split("\n---\n", 1)[1].strip()
        expected = (
            f'<skill name="ca-btw" location="{skill_path}">\n'
            f"References are relative to {skill_path.parent}.\n\n"
            f"{body}\n</skill>\n\n __CA_ALIAS_SENTINEL__  "
        )
        self.assertEqual(expanded, expected)
        self.assertNotIn("/skill:ca-btw", expanded)

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
            "DEGRADED  active-dispatch: Supported Pi 0.80.5/0.80.6 public extension APIs cannot "
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

        expected_context = (
            "ADR-0015 (Model-visible read contract) governs this file"
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

    @unittest.skipUnless(os.name == "nt", "Windows executable search canary")
    def test_real_rpc_enabled_start_never_executes_project_git_and_installs_absolute_hook_identities(self):
        with tempfile.TemporaryDirectory(prefix="ca-pi-rpc-git-poison-") as directory:
            root = Path(directory)
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
                _after_install=poison_project_after_package_install,
            )
            hook_path = enabled / ".git" / "hooks" / "pre-commit"
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


if __name__ == "__main__":
    if "--rpc-commands" in sys.argv:
        sys.argv = [
            sys.argv[0],
            "PiPackageTests.test_real_isolated_rpc_command_discovery_and_keyed_status",
        ]
    unittest.main(verbosity=2)
