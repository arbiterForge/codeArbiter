#!/usr/bin/env python3
"""Live proof for bounded Pi process-tree containment and cleanup."""

from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "plugins" / "ca-pi" / "tools" / "src" / "process-tree.ts"
SUPERVISOR = ROOT / "plugins" / "ca-pi" / "helpers" / "windows-supervisor.js"
NODE = shutil.which("node")
MAX_RUN_SECONDS = 45.0


FIXTURE_SOURCE = r'''
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";

const mode = process.argv[2];
if (process.env.CA_PI_FIXTURE_MARKER) writeFileSync(process.env.CA_PI_FIXTURE_MARKER, "spawned\n");
const stubborn = mode === "stubborn";
const hold = () => {
  if (stubborn && process.platform !== "win32") process.on("SIGTERM", () => {});
  setInterval(() => {}, 1_000);
};

if (mode === "leaf" || mode === "stubborn-leaf") {
  if (mode === "stubborn-leaf" && process.platform !== "win32") process.on("SIGTERM", () => {});
  setInterval(() => {}, 1_000);
} else if (mode === "middle" || mode === "stubborn-middle") {
  const childMode = mode === "stubborn-middle" ? "stubborn-leaf" : "leaf";
  const leaf = spawn(process.execPath, [process.argv[1], childMode], {
    detached: false,
    shell: false,
    stdio: "ignore",
    windowsHide: true,
  });
  leaf.once("spawn", () => process.stdout.write(JSON.stringify({ child: process.pid, grandchild: leaf.pid }) + "\n"));
  leaf.once("error", () => process.exit(31));
  if (mode === "stubborn-middle" && process.platform !== "win32") process.on("SIGTERM", () => {});
  setInterval(() => {}, 1_000);
} else if (mode === "root" || mode === "stubborn") {
  const middleMode = mode === "stubborn" ? "stubborn-middle" : "middle";
  const middle = spawn(process.execPath, [process.argv[1], middleMode], {
    detached: false,
    shell: false,
    stdio: ["ignore", "pipe", "inherit"],
    windowsHide: true,
  });
  let buffer = "";
  middle.stdout.setEncoding("utf8");
  middle.stdout.on("data", (chunk) => {
    buffer += chunk;
    const newline = buffer.indexOf("\n");
    if (newline < 0) return;
    process.stdout.write(JSON.stringify({ parent: process.pid, ...JSON.parse(buffer.slice(0, newline)) }) + "\n");
    middle.stdout.removeAllListeners("data");
  });
  middle.once("error", () => process.exit(32));
  hold();
} else if (mode === "root-first" || mode === "fast-nonzero") {
  const left = spawn(process.execPath, [process.argv[1], "leaf"], { detached: true, shell: false, stdio: "ignore", windowsHide: true });
  const right = spawn(process.execPath, [process.argv[1], "leaf"], { detached: true, shell: false, stdio: "ignore", windowsHide: true });
  Promise.all([
    new Promise((resolve, reject) => { left.once("spawn", resolve); left.once("error", reject); }),
    new Promise((resolve, reject) => { right.once("spawn", resolve); right.once("error", reject); }),
  ]).then(() => {
    process.stdout.write(
      JSON.stringify({ parent: process.pid, child: left.pid, grandchild: right.pid }) + "\n" +
        "FINAL_RECORD:" + "x".repeat(60_000) + ":END\n",
      () => process.exit(mode === "fast-nonzero" ? 23 : 0),
    );
  }, () => process.exit(33));
} else {
  process.exit(30);
}
'''


CONTROLLER_SOURCE = r'''
import { pathToFileURL } from "node:url";

const [modulePath, fixture, reason, mode] = process.argv.slice(2);
const admissionFailureCodes = new Map([
  ["process-tree launch identities are invalid", "identity-refused"],
  ["canonical Windows supervisor artifact unavailable", "supervisor-artifact-refused"],
  ["Windows inert supervisor failed to start", "supervisor-start-refused"],
  ["Windows Job Object holder refused containment", "job-attach-refused"],
  ["Windows parent-death leash unavailable", "parent-leash-refused"],
  ["Windows contained Pi launch was refused", "child-launch-refused"],
  ["Windows contained Pi exit watch was refused", "exit-watch-refused"],
]);
const childEnvironment = { ...process.env };
if (reason === "attach_refusal") {
  delete process.env.SystemRoot;
  delete process.env.WINDIR;
}
const { createProcessTreeCleanup, spawnProcessTree } = await import(pathToFileURL(modulePath).href);
const PID_HEADER_MAX_BYTES = 4_096;
const FIXTURE_OUTPUT_MAX_BYTES = 131_072;
function createFixtureOutputProtocol() {
  return { buffer: "", header: undefined, overflow: false, totalBytes: 0 };
}
function acceptFixtureOutput(protocol, chunk) {
  const chunkBytes = Buffer.byteLength(chunk, "utf8");
  if (protocol.totalBytes + chunkBytes > FIXTURE_OUTPUT_MAX_BYTES) {
    protocol.overflow = true;
    throw new Error("fixture output protocol overflow");
  }
  protocol.totalBytes += chunkBytes;
  protocol.buffer += chunk;
  if (protocol.header !== undefined) return;
  const newline = protocol.buffer.indexOf("\n");
  if (newline < 0) {
    if (Buffer.byteLength(protocol.buffer, "utf8") > PID_HEADER_MAX_BYTES) {
      throw new Error("fixture pid protocol overflow");
    }
    return;
  }
  const header = protocol.buffer.slice(0, newline);
  if (Buffer.byteLength(header, "utf8") > PID_HEADER_MAX_BYTES) {
    throw new Error("fixture pid protocol overflow");
  }
  protocol.header = JSON.parse(header);
}
if (reason === "parser_probe") {
  const combined = JSON.stringify({ parent: 11, child: 12, grandchild: 13 }) + "\n" +
    "FINAL_RECORD:" + "x".repeat(60_000) + ":END\n";
  const protocol = createFixtureOutputProtocol();
  acceptFixtureOutput(protocol, combined);
  if (protocol.header?.parent !== 11 || !protocol.buffer.includes(":END\n")) {
    throw new Error("combined fixture output was not retained");
  }
  for (const invalid of ["x".repeat(PID_HEADER_MAX_BYTES + 1), "not-json\n"]) {
    let refused = false;
    try { acceptFixtureOutput(createFixtureOutputProtocol(), invalid); }
    catch { refused = true; }
    if (!refused) throw new Error("invalid fixture header was accepted");
  }
  await new Promise((resolve) => process.stdout.write("PARSER_OK\n", resolve));
  process.exit(0);
}
let child;
let cleanup;
let phase = "launch-admission";
try {
  child = await spawnProcessTree(process.execPath, [fixture, mode], {
    cwd: process.cwd(), env: childEnvironment, stdio: ["pipe", "pipe", "pipe", "pipe"],
  });
  cleanup = createProcessTreeCleanup(child, { graceMs: 300, pollMs: 20, verifyMs: 3_000 });
  phase = "containment-ready";
  if (!await cleanup.ready()) throw new Error("containment not ready");
  phase = "pid-protocol";
  const output = createFixtureOutputProtocol();
  let outputFailure;
  let pidSettled = false;
  const pids = await new Promise((resolve, reject) => {
    let timer;
    const fail = (error) => {
      if (pidSettled) return;
      pidSettled = true;
      if (timer !== undefined) clearTimeout(timer);
      reject(error);
    };
    timer = setTimeout(() => fail(new Error("fixture pid protocol timed out")), 5_000);
    child.once("error", fail);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      try {
        acceptFixtureOutput(output, chunk);
        if (!pidSettled && output.header !== undefined) {
          pidSettled = true;
          clearTimeout(timer);
          resolve(output.header);
        }
      } catch (error) {
        outputFailure = error;
        if (!pidSettled) fail(error);
        else void cleanup.terminate("protocol_overflow");
      }
    });
  });
  process.stdout.write("PIDS " + JSON.stringify({ actualPid: child.pid, pids }) + "\n");
  if (reason === "hold") {
    setInterval(() => {}, 1_000);
  } else if (reason === "helper_failure") {
    phase = "helper-close";
    const code = await new Promise((resolve) => child.once("close", resolve));
    if (outputFailure !== undefined) throw outputFailure;
    process.stdout.write("FINAL " + JSON.stringify({ code, exitCode: child.exitCode, signalCode: child.signalCode }) + "\n");
  } else if (reason === "normal_close") {
    phase = "normal-close";
    const code = await new Promise((resolve) => child.once("close", resolve));
    if (outputFailure !== undefined) throw outputFailure;
    process.stdout.write("FINAL " + JSON.stringify({
      code, pids, actualPid: child.pid, normalClose: true,
      finalOutput: output.buffer.includes("FINAL_RECORD:") && output.buffer.includes(":END\n"),
    }) + "\n");
  } else {
    phase = "termination";
    const started = Date.now();
    const result = await new Promise((resolve) => {
      if (reason === "cancelled") {
        const controller = new AbortController();
        controller.signal.addEventListener("abort", () => void cleanup.terminate("cancelled").then(resolve), { once: true });
        setTimeout(() => controller.abort(), 25);
      } else {
        setTimeout(() => void cleanup.terminate("timeout").then(resolve), 25);
      }
    });
    if (outputFailure !== undefined) throw outputFailure;
    process.stdout.write("FINAL " + JSON.stringify({ durationMs: Date.now() - started, pids, actualPid: child.pid, result }) + "\n");
  }
} catch (error) {
  if (cleanup !== undefined) {
    try { await cleanup.terminate("startup_failure"); } catch {}
  }
  const message = error instanceof Error ? error.message : "";
  const code = phase === "launch-admission" ? " code=" + (admissionFailureCodes.get(message) ?? "unknown") : "";
  process.stderr.write("controller failure phase=" + phase + code + "\n");
  process.stdout.write("REFUSED\n");
}
'''


def _is_alive_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_alive_windows(pid: int) -> bool:
    query = 0x1000
    synchronize = 0x00100000
    wait_timeout = 0x00000102
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(query | synchronize, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error in (0, 87, 1168):
            return False
        raise OSError(error, f"OpenProcess failed for fixture pid {pid}")
    try:
        return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
    finally:
        kernel32.CloseHandle(handle)


def is_alive(pid: int) -> bool:
    return _is_alive_windows(pid) if os.name == "nt" else _is_alive_posix(pid)


def wait_gone(pids: list[int], timeout: float = 5.0) -> list[int]:
    deadline = time.monotonic() + timeout
    alive = list(pids)
    while alive and time.monotonic() < deadline:
        alive = [pid for pid in alive if is_alive(pid)]
        if alive:
            time.sleep(0.025)
    return [pid for pid in alive if is_alive(pid)]


def force_cleanup(pids: list[int]) -> None:
    if os.name == "nt":
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
        for pid in pids:
            subprocess.run([str(taskkill), "/PID", str(pid), "/T", "/F"], check=False,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        return
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError as error:
            if error.errno != errno.ESRCH:
                raise


def isolated_environment(directory: Path, label: str) -> dict[str, str]:
    home = directory / f"home-{label}"
    temp = directory / f"tmp-{label}"
    home.mkdir()
    temp.mkdir()
    environment = {
        "HOME": str(home), "USERPROFILE": str(home), "TEMP": str(temp), "TMP": str(temp),
        "TMPDIR": str(temp), "NODE_NO_WARNINGS": "1",
    }
    node_dir = str(Path(str(NODE)).resolve().parent)
    if os.name == "nt":
        system_root = str(Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve())
        environment.update({
            "APPDATA": str(home / "AppData" / "Roaming"), "LOCALAPPDATA": str(home / "AppData" / "Local"),
            "ComSpec": str(Path(system_root) / "System32" / "cmd.exe"),
            "PATH": os.pathsep.join([node_dir, str(Path(system_root) / "System32")]),
            "SystemRoot": system_root, "WINDIR": system_root,
        })
    else:
        environment["PATH"] = os.pathsep.join([node_dir, "/usr/bin", "/bin"])
    return environment


def parse_lines(completed: subprocess.CompletedProcess[str], variant: str) -> tuple[dict, dict]:
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    pids_line = next((line for line in lines if line.startswith("PIDS ")), None)
    final_line = next((line for line in lines if line.startswith("FINAL ")), None)
    if completed.returncode != 0 or pids_line is None or final_line is None:
        raise AssertionError(
            f"{variant} controller failed ({completed.returncode}): "
            f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
        )
    return json.loads(pids_line[5:]), json.loads(final_line[6:])


def run_parser_probe(directory: Path) -> None:
    completed = subprocess.run(
        [str(NODE), "--experimental-strip-types", str(directory / "controller.mjs"), str(MODULE),
         str(directory / "fixture.mjs"), "parser_probe", "combined"],
        cwd=ROOT, env=isolated_environment(directory, "parser-probe"), check=False,
        capture_output=True, text=True, timeout=MAX_RUN_SECONDS,
    )
    assert completed.returncode == 0 and completed.stdout.strip() == "PARSER_OK", completed


def run_variant(directory: Path, reason: str, mode: str) -> None:
    environment = isolated_environment(directory, f"{reason}-{mode}")
    command = [str(NODE), "--experimental-strip-types", str(directory / "controller.mjs"), str(MODULE),
               str(directory / "fixture.mjs"), reason, mode]
    try:
        completed = subprocess.run(
            command, cwd=ROOT, env=environment, check=False, capture_output=True, text=True,
            timeout=MAX_RUN_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        partial = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
        pid_line = next((line for line in partial.splitlines() if line.startswith("PIDS ")), None)
        native = None
        if pid_line is not None:
            payload = json.loads(pid_line[5:])
            native = {name: is_alive(int(pid)) for name, pid in payload["pids"].items()}
        raise AssertionError(
            f"{reason}/{mode} controller timed out: stdout={error.stdout!r} stderr={error.stderr!r} native={native!r}"
        ) from error
    header, observed = parse_lines(completed, f"{reason}/{mode}")
    pids = [int(header["pids"][name]) for name in ("parent", "child", "grandchild")]
    try:
        assert len(set(pids)) == 3 and all(pid > 0 for pid in pids), observed
        assert int(header["actualPid"]) == pids[0], "public pid must be actual Pi root"
        assert int(observed["actualPid"]) == pids[0], observed
        if reason == "normal_close":
            expected_code = 23 if mode == "fast-nonzero" else 0
            assert observed["normalClose"] is True and observed["code"] == expected_code, observed
            assert observed["finalOutput"] is True, "supervisor truncated final Pi stdout"
        else:
            assert observed["result"]["reason"] == reason, observed
            assert observed["result"]["state"] in ("terminated", "already_exited"), observed
            assert observed["result"]["verified"] is True, observed
            if mode == "stubborn":
                assert observed["result"]["escalated"] is True, observed
            assert observed["durationMs"] < 6_000, observed
        assert wait_gone(pids) == [], f"{reason}/{mode} left live fixture pids"
    finally:
        force_cleanup([pid for pid in pids if is_alive(pid)])


def _readline_with_timeout(stream, timeout: float) -> str:
    observed: queue.Queue[str] = queue.Queue(maxsize=1)
    threading.Thread(target=lambda: observed.put(stream.readline()), daemon=True).start()
    try:
        return observed.get(timeout=timeout)
    except queue.Empty as error:
        raise AssertionError("controller pid protocol timed out") from error


def terminate_controller_only(pid: int) -> None:
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x0001, False, pid)
        if not handle:
            raise OSError(ctypes.get_last_error(), "OpenProcess controller failed")
        try:
            if not kernel32.TerminateProcess(handle, 99):
                raise OSError(ctypes.get_last_error(), "TerminateProcess controller failed")
        finally:
            kernel32.CloseHandle(handle)
    else:
        os.kill(pid, signal.SIGKILL)


def windows_child_processes(parent_pid: int) -> list[tuple[int, str]]:
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_uint32), ("cntUsage", ctypes.c_uint32),
            ("th32ProcessID", ctypes.c_uint32), ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", ctypes.c_uint32), ("cntThreads", ctypes.c_uint32),
            ("th32ParentProcessID", ctypes.c_uint32), ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_uint32), ("szExeFile", ctypes.c_wchar * 260),
        ]
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    children: list[tuple[int, str]] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        present = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            if int(entry.th32ParentProcessID) == parent_pid:
                children.append((int(entry.th32ProcessID), entry.szExeFile.lower()))
            present = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return children


def terminate_windows_process(pid: int, exit_code: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x0001, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), f"OpenProcess failed for {pid}")
    try:
        if not kernel32.TerminateProcess(handle, exit_code):
            raise OSError(ctypes.get_last_error(), f"TerminateProcess failed for {pid}")
    finally:
        kernel32.CloseHandle(handle)


def run_controller_death(directory: Path) -> None:
    if os.name != "nt":
        return
    environment = isolated_environment(directory, "controller-death")
    process = subprocess.Popen(
        [str(NODE), "--experimental-strip-types", str(directory / "controller.mjs"), str(MODULE),
         str(directory / "fixture.mjs"), "hold", "stubborn"],
        cwd=ROOT, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    pids: list[int] = []
    try:
        line = _readline_with_timeout(process.stdout, 7.0)
        assert line.startswith("PIDS "), line
        header = json.loads(line[5:])
        pids = [int(header["pids"][name]) for name in ("parent", "child", "grandchild")]
        assert int(header["actualPid"]) == pids[0]
        terminate_controller_only(process.pid)
        process.wait(timeout=3)
        assert wait_gone(pids) == [], f"controller death left live fixture pids: {pids}"
    finally:
        if process.poll() is None:
            terminate_controller_only(process.pid)
        force_cleanup([pid for pid in pids if is_alive(pid)])


def run_helper_failure(directory: Path) -> None:
    if os.name != "nt":
        return
    environment = isolated_environment(directory, "helper-failure")
    process = subprocess.Popen(
        [str(NODE), "--experimental-strip-types", str(directory / "controller.mjs"), str(MODULE),
         str(directory / "fixture.mjs"), "helper_failure", "stubborn"],
        cwd=ROOT, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    pids: list[int] = []
    supervisor_pid: int | None = None
    try:
        line = _readline_with_timeout(process.stdout, 7.0)
        assert line.startswith("PIDS "), line
        header = json.loads(line[5:])
        pids = [int(header["pids"][name]) for name in ("parent", "child", "grandchild")]
        children = windows_child_processes(process.pid)
        helpers = [pid for pid, name in children if name in ("powershell.exe", "pwsh.exe")]
        supervisors = [pid for pid, name in children if name == "node.exe"]
        assert len(helpers) == 1 and len(supervisors) == 1, children
        supervisor_pid = supervisors[0]
        terminate_windows_process(helpers[0], 97)
        final_line = _readline_with_timeout(process.stdout, 7.0)
        assert final_line.startswith("FINAL "), final_line
        observed = json.loads(final_line[6:])
        assert observed["code"] != 0 and observed["exitCode"] != 0, observed
        process.wait(timeout=3)
        assert wait_gone([supervisor_pid, *pids]) == [], "holder failure left contained processes alive"
    finally:
        if process.poll() is None:
            terminate_controller_only(process.pid)
        candidates = ([supervisor_pid] if supervisor_pid is not None else []) + pids
        force_cleanup([pid for pid in candidates if is_alive(pid)])


def run_attach_failure(directory: Path) -> None:
    if os.name != "nt":
        return
    environment = isolated_environment(directory, "attach-refusal")
    marker = directory / "attach-refusal-spawned.txt"
    environment["CA_PI_FIXTURE_MARKER"] = str(marker)
    completed = subprocess.run(
        [str(NODE), "--experimental-strip-types", str(directory / "controller.mjs"), str(MODULE),
         str(directory / "fixture.mjs"), "attach_refusal", "root"],
        cwd=ROOT, env=environment, check=False, capture_output=True, text=True, timeout=MAX_RUN_SECONDS,
    )
    assert completed.returncode == 0 and completed.stdout.strip() == "REFUSED", completed
    assert completed.stderr.strip() == "controller failure phase=launch-admission code=job-attach-refused", completed
    assert not marker.exists(), "Pi fixture spawned after Job holder refusal"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-only", action="store_true")
    args = parser.parse_args()
    if NODE is None:
        raise AssertionError("Node is required for the Pi process-tree proof")
    if not MODULE.is_file():
        raise AssertionError(f"missing process-tree implementation: {MODULE}")
    if args.fixture_only:
        source = MODULE.read_text(encoding="utf-8")
        supervisor = (ROOT / "plugins" / "ca-pi" / "tools" / "src" / "windows-supervisor.ts").read_text(encoding="utf-8")
        for required in (
            "spawnProcessTree", "createProcessTreeCleanup", "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE",
            "ATTACHED", '"START\\n"', "windows-supervisor.js", '"/PID"', '"/T"',
            '"SIGTERM"', '"SIGKILL"', "shell: false", "windowsHide: true",
        ):
            if required not in source:
                raise AssertionError(f"process-tree static contract missing {required}")
        for required in ("parentLeash.resume()", "STARTED", "fd: 3", "fd: 4", "fd: 5", "fd: 6", "fd: 7"):
            if required not in supervisor:
                raise AssertionError(f"supervisor static contract missing {required}")
        print("pi process-tree fixture: ready")
        return 0
    if os.name == "nt" and not SUPERVISOR.is_file():
        raise AssertionError("built canonical Windows supervisor artifact is missing")
    with tempfile.TemporaryDirectory(prefix="ca-pi-process-tree-") as raw:
        directory = Path(raw)
        (directory / "fixture.mjs").write_text(FIXTURE_SOURCE, encoding="utf-8", newline="\n")
        (directory / "controller.mjs").write_text(CONTROLLER_SOURCE, encoding="utf-8", newline="\n")
        run_parser_probe(directory)
        if os.name == "nt":
            run_variant(directory, "normal_close", "root-first")
            run_variant(directory, "normal_close", "fast-nonzero")
        run_variant(directory, "cancelled", "root")
        run_variant(directory, "timeout", "root")
        run_variant(directory, "timeout", "stubborn")
        run_controller_death(directory)
        run_helper_failure(directory)
        run_attach_failure(directory)
    variants = 8 if os.name == "nt" else 3
    print(f"pi process-tree live proof: {variants}/{variants} variants passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
