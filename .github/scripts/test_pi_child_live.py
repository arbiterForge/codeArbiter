#!/usr/bin/env python3
"""Task 6 Pi child isolation contract and deterministic live-fixture checks."""

from __future__ import annotations

import argparse
import http.server
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

from pi_cli_resolver import resolve_pi_cli_path


REPO = pathlib.Path(__file__).resolve().parents[2]
TASK_FILES = (
    "plugins/ca-pi/tools/src/child-env.ts",
    "plugins/ca-pi/tools/src/runner.ts",
    "plugins/ca-pi/tools/src/inference-broker.ts",
    "plugins/ca-pi/tools/src/attestation.ts",
    "plugins/ca-pi/tools/src/roles.ts",
    "plugins/ca-pi/tools/src/child-extension.ts",
    "plugins/ca-pi/generated/roles.json",
    "plugins/ca-pi/tools/test/fixtures/pi-0.80.5-help.txt",
    "plugins/ca-pi/tools/test/fixtures/pi-0.80.6-help.txt",
)
REQUIRED_FLAGS = (
    "--mode", "--no-approve", "--no-extensions", "--no-skills",
    "--no-prompt-templates", "--no-themes", "--no-context-files",
    "--no-session", "--offline", "--provider", "--model", "--tools",
    "--extension", "--append-system-prompt", "--skill",
)


class PiChildFixtureContract(unittest.TestCase):
    def test_task_6_files_exist(self) -> None:
        missing = [item for item in TASK_FILES if not (REPO / item).is_file()]
        self.assertEqual(missing, [], f"Task 6 files missing: {missing}")

    def test_pinned_help_has_every_isolation_flag_and_provider_boundary(self) -> None:
        help_805 = (REPO / TASK_FILES[-2]).read_text(encoding="utf-8")
        help_806 = (REPO / TASK_FILES[-1]).read_text(encoding="utf-8")
        self.assertEqual(help_805, help_806)
        for help_text in (help_805, help_806):
            for flag in REQUIRED_FLAGS:
                self.assertIn(flag, help_text)
            for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY", "PI_CODING_AGENT_DIR"):
                self.assertRegex(help_text, rf"(?m)^\s+{re.escape(name)}\s")

    def test_generated_roles_are_exact_and_nonrecursive(self) -> None:
        roles = json.loads((REPO / "plugins/ca-pi/generated/roles.json").read_text(encoding="utf-8"))
        by_name = {item["name"]: item for item in roles}
        canonical_agents = sorted(
            path for path in (REPO / "core/surface/agents").glob("*.md")
            if path.name != "INDEX.md"
        )
        self.assertEqual(len(roles), 28)
        self.assertEqual(sorted(by_name), [path.stem for path in canonical_agents])
        self.assertEqual(by_name["backend-author"]["tools"], ["read", "bash", "edit", "write"])
        self.assertEqual(by_name["backend-author"]["classification"], "author")
        self.assertEqual(by_name["backend-author"]["skillPaths"], ["routines/tdd/SKILL.md"])
        self.assertEqual(by_name["security-reviewer"]["classification"], "reviewer")
        for role in roles:
            self.assertTrue((REPO / "plugins/ca-pi" / role["charterPath"]).is_file())
            for skill_path in role["skillPaths"]:
                self.assertRegex(skill_path, r"^routines/[^/]+/SKILL\.md$")
                self.assertTrue((REPO / "plugins/ca-pi" / skill_path).is_file())
        self.assertFalse(any("dispatch" in json.dumps(item).lower() for item in roles))

    def test_task_6_sources_do_not_inspect_auth_stores_or_use_shell_launch(self) -> None:
        # ADR-0016 supersedes the ADR-0014 clause that made the operator auth store
        # wholly opaque to ca-pi. Exactly ONE file — child-env.ts — is the sanctioned
        # narrow secret-transport boundary; every other Task 6 source must still carry
        # no credential-store reference at all. Widening this exemption to a second
        # file requires a superseding ADR, not an edit here.
        transport = "plugins/ca-pi/tools/src/child-env.ts"
        self.assertIn(transport, TASK_FILES[:6])
        non_transport = [item for item in TASK_FILES[:6] if item != transport]
        sources = "\n".join((REPO / item).read_text(encoding="utf-8") for item in non_transport)
        self.assertNotRegex(sources, r"auth\.json|models\.json|\.aws[/\\]credentials|statSync|lstatSync")

        # The transport file may name auth.json, but never a foreign credential store,
        # and never a stat-then-open race in place of a retained handle.
        child_env = (REPO / transport).read_text(encoding="utf-8")
        self.assertNotRegex(child_env, r"\.aws[/\\]credentials|statSync|lstatSync")
        # ADR-0016's bounded-READ contract, asserted positively. The read survives #455 —
        # the parent still needs the operator credential to attach it upstream itself.
        self.assertIn("MAX_AUTH_FILE_BYTES", child_env)          # strict size bound
        self.assertIn("mkdtemp", child_env)                      # fresh private child root
        self.assertIn("input.provider", child_env)               # exact selected record only
        self.assertIn("sensitiveValues", child_env)              # scrub set for every exit path
        self.assertIn("truncate(0)", child_env)                  # projection scrubbed on cleanup

        # ADR-0017's credential-blind CONFIGURATION projection, asserted positively. It amends
        # only ADR-0016's "no Pi configuration" clause; credential projection is unchanged.
        self.assertIn("MAX_MODELS_FILE_BYTES", child_env)             # same strict size bound
        self.assertIn('open(join(agentDir, "models.json"), "r")', child_env)
        self.assertIn("PROJECTED_PROVIDER_KEYS", child_env)           # schema-pinned key allowlist
        self.assertIn("PURE_ENV_REFERENCE", child_env)                # $NAME/${NAME} values only
        self.assertIn("ChildConfigProjectionError", child_env)        # fail closed, value-free

        runner = (REPO / "plugins/ca-pi/tools/src/runner.ts").read_text(encoding="utf-8")
        process_tree = (REPO / "plugins/ca-pi/tools/src/process-tree.ts").read_text(encoding="utf-8")
        self.assertIn("spawnProcessTree", runner)
        self.assertIn("shell: false", process_tree)
        self.assertIn("CODEARBITER_SUBAGENT", sources)
        self.assertIn("codearbiter-internal-child-handshake", sources)
        self.assertIn("codeArbiter isolated child readiness", sources)

    def test_auth_json_projection_path_is_gone_not_merely_unused(self) -> None:
        # #455 AC-5. ADR-0016's auth.json PROJECTION clause is superseded outright: the
        # parent may still READ the operator store for the broker's upstream credential,
        # but nothing writes a credential file into the child's private agent dir, and the
        # provider credential environment variables no longer cross either. These
        # assertions fail if either path is reintroduced.
        child_env = (REPO / "plugins/ca-pi/tools/src/child-env.ts").read_text(encoding="utf-8")
        self.assertNotIn("authPath", child_env)
        self.assertNotIn("credentialHandle", child_env)
        self.assertNotRegex(child_env, r'open\([^)]*"auth\.json"[^)]*"wx"')
        self.assertNotRegex(child_env, r'PI_CODING_AGENT_DIR!?,\s*"auth\.json"')
        self.assertNotIn("copyDefined(child, input.parent, providerNames)", child_env)
        self.assertIn("BROKER_TOKEN_ENV_NAME", child_env)
        self.assertIn("PI_BUILTIN_UPSTREAM", child_env)
        self.assertIn("BROKER_INELIGIBLE_PROVIDERS", child_env)
        self.assertIn("ChildBrokerAuthorityError", child_env)

    def test_inference_broker_binds_loopback_only_streams_and_fails_closed(self) -> None:
        # #455 AC-4 and the "loopback only, OS-assigned port" hard requirement, asserted at
        # the source so a later edit cannot quietly widen the listener or start buffering.
        broker = (REPO / "plugins/ca-pi/tools/src/inference-broker.ts").read_text(encoding="utf-8")
        self.assertIn('host: "127.0.0.1", port: 0', broker)
        self.assertNotIn("0.0.0.0", broker)
        self.assertIn("codeArbiter inference broker failed closed.", broker)
        self.assertIn("timingSafeEqual", broker)
        self.assertIn("upstreamResponse.pipe(response)", broker)
        self.assertIn("request.pipe(forward)", broker)
        self.assertNotRegex(broker, r"await\s+\w*[Rr]esponse\.(text|json|arrayBuffer)\(")
        # The runner owns the listener's lifetime and the token's revocation.
        runner = (REPO / "plugins/ca-pi/tools/src/runner.ts").read_text(encoding="utf-8")
        self.assertIn("startInferenceBroker", runner)
        self.assertIn("isolation-broker", runner)
        self.assertIn("broker.revoke()", runner)
        self.assertIn("await closeBroker();", runner)

    def test_public_runner_has_no_shipping_test_injection_seam(self) -> None:
        tools = REPO / "plugins/ca-pi/tools"
        self.assertFalse((tools / "src/runner-core.ts").exists())
        self.assertFalse((tools / "test/support/runner-testkit.ts").exists())
        runner = (tools / "src/runner.ts").read_text(encoding="utf-8")
        signature = re.search(
            r"export async function runPiChild\(\s*request: PiChildRequest,\s*signal: AbortSignal,?\s*\)",
            runner,
        )
        self.assertIsNotNone(signature)
        self.assertNotRegex(runner, r"RunnerDependencies|spawnChild|testkit|runner-core")

    def test_built_child_is_enforcement_only_not_placeholder(self) -> None:
        child = (REPO / "plugins/ca-pi/extensions/codearbiter-child.js").read_text(encoding="utf-8")
        self.assertGreater(len(child.encode("utf-8")), 2_000)
        self.assertIn("codearbiter-internal-child-handshake", child)
        self.assertIn("mutation blocked", child)
        self.assertIn("ca-pi-child-attestation-v1", child)
        self.assertIn("codeArbiter isolated child readiness", child)
        self.assertNotIn("ca-dispatch", child)
        self.assertNotIn("FARM_API_KEY", child)
        self.assertNotRegex(child, r"runner-testkit|runner-core|RunnerDependencies")

    def test_built_parent_contains_production_runner_without_test_hooks(self) -> None:
        parent = (REPO / "plugins/ca-pi/extensions/codearbiter.js").read_text(encoding="utf-8")
        self.assertGreater(len(parent.encode("utf-8")), 10_000)
        self.assertIn("codearbiter_dispatch", parent)
        self.assertIn("ca-pi-child-attestation-v1", parent)
        self.assertIn("Pi child isolation failed safely", parent)
        self.assertNotRegex(
            parent,
            r"runner-testkit|runner-core|RunnerDependencies|spawnChild|"
            r"aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee|0123456789abcdef0123456789abcdef",
        )


def live_pi_cli() -> tuple[str, pathlib.Path]:
    """Resolve the installed Pi package to absolute Node + CLI identities."""
    executable = shutil.which("pi.cmd" if os.name == "nt" else "pi") or shutil.which("pi")
    if executable is None:
        raise AssertionError("Pi CLI is not available on PATH")
    node = shutil.which("node")
    if node is None:
        raise AssertionError("Node is not available on PATH")
    return str(pathlib.Path(node).resolve()), resolve_pi_cli_path(executable)


def runtime_help(node: str, cli: pathlib.Path, cwd: pathlib.Path, environment: dict[str, str]) -> str:
    completed = subprocess.run(
        [node, str(cli), "--help"], cwd=cwd, env=environment, text=True, encoding="utf-8",
        errors="replace", capture_output=True, check=False, timeout=30,
    )
    if completed.returncode != 0:
        raise AssertionError("installed Pi help probe failed")
    return completed.stdout


def live_help_contract(
    node: str,
    cli: pathlib.Path,
    cwd: pathlib.Path,
    environment: dict[str, str],
) -> None:
    version = subprocess.run(
        [node, str(cli), "--version"], cwd=cwd, env=environment, text=True, encoding="utf-8",
        errors="replace", capture_output=True, check=False, timeout=30,
    ).stdout.strip()
    if version not in {"0.80.5", "0.80.10"}:
        raise AssertionError(f"unsupported live Pi version: {version!r}")
    actual = runtime_help(node, cli, cwd, environment)
    for flag in REQUIRED_FLAGS:
        if flag not in actual:
            raise AssertionError(f"Pi {version} help drift: missing {flag}")


TASK_MARKERS = ("CA_PI_LIVE_TASK_ONE", "CA_PI_LIVE_TASK_TWO")
DISCOVERY_SENTINEL = "CA_PI_FORBIDDEN_AMBIENT_DISCOVERY_SENTINEL"
PROVIDER_KEY = "ca-pi-live-provider-key"
EXPECTED_TOOLS = ["read", "bash", "edit", "write"]


class DeterministicOpenAiServer:
    """Loopback-only OpenAI-compatible stream that requests one blocked H-03 call."""

    def __init__(self) -> None:
        self.requests: dict[str, list[dict]] = {marker: [] for marker in TASK_MARKERS}
        self.errors: list[str] = []
        self.lock = threading.Lock()
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
                try:
                    owner._handle(self)
                except Exception as exc:  # keep failure bounded and let the child fail closed
                    with owner.lock:
                        owner.errors.append(f"{type(exc).__name__}: {exc}")
                    body = b'{"error":{"message":"deterministic provider rejected request"}}'
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(body)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}/v1"

    def __enter__(self) -> "DeterministicOpenAiServer":
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @staticmethod
    def _stream(handler: http.server.BaseHTTPRequestHandler, chunks: list[dict]) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "close")
        handler.end_headers()
        for chunk in chunks:
            handler.wfile.write(f"data: {json.dumps(chunk, separators=(',', ':'))}\n\n".encode("utf-8"))
        handler.wfile.write(b"data: [DONE]\n\n")
        handler.wfile.flush()

    def _handle(self, handler: http.server.BaseHTTPRequestHandler) -> None:
        if handler.path != "/v1/chat/completions":
            raise AssertionError(f"unexpected provider route: {handler.path}")
        # #455 AC-3: the child holds only an ephemeral broker token, so the ONLY way the real
        # operator key reaches this upstream is the parent's loopback broker substituting it.
        if handler.headers.get("Authorization") != f"Bearer {PROVIDER_KEY}":
            raise AssertionError("selected-provider key was not passed only as the auth header")
        # ...and the child's token must never ride along on any header.
        for name, value in handler.headers.items():
            if re.fullmatch(r"(?:Bearer )?[0-9a-f]{64}", value or ""):
                raise AssertionError(f"child broker token reached the upstream provider on {name}")
        length = int(handler.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_048_576:
            raise AssertionError(f"provider request size is invalid: {length}")
        payload = json.loads(handler.rfile.read(length).decode("utf-8", "strict"))
        serialized = json.dumps(payload, separators=(",", ":"))
        marker = next((candidate for candidate in TASK_MARKERS if candidate in serialized), None)
        if marker is None:
            raise AssertionError("provider request did not retain its isolated task marker")
        if DISCOVERY_SENTINEL in serialized:
            raise AssertionError("ambient project/global Pi resources reached the child context")
        tools = [item.get("function", {}).get("name") for item in payload.get("tools", [])]
        if tools != EXPECTED_TOOLS:
            raise AssertionError(f"child model tool contract drifted: {tools!r}")
        if any(name in serialized.lower() for name in ("codearbiter_dispatch", "ca-dispatch", "farm")):
            raise AssertionError("recursive orchestration reached the isolated child")
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise AssertionError("provider messages are missing")
        tool_results = [message for message in messages if message.get("role") == "tool"]
        with self.lock:
            turn = len(self.requests[marker])
            self.requests[marker].append(payload)
        if turn == 0:
            if tool_results:
                raise AssertionError("first child turn already contained a tool result")
            chunks = [
                {
                    "id": f"chatcmpl-{marker}-tool", "object": "chat.completion.chunk", "created": 1,
                    "model": "gpt-test", "choices": [{"index": 0, "delta": {
                        "role": "assistant", "tool_calls": [{"index": 0, "id": f"call-{marker}",
                        "type": "function", "function": {"name": "bash", "arguments": '{"command":"git add -A"}'}}]
                    }, "finish_reason": None}],
                },
                {
                    "id": f"chatcmpl-{marker}-tool", "object": "chat.completion.chunk", "created": 1,
                    "model": "gpt-test", "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                },
            ]
        elif turn == 1:
            if len(tool_results) != 1:
                raise AssertionError(f"second child turn has {len(tool_results)} tool results")
            result_text = json.dumps(tool_results[0], separators=(",", ":"))
            if "H-03" not in result_text or "prohibited" not in result_text:
                raise AssertionError(f"child mutation did not return the shared H-03 block: {result_text!r}")
            final = f"live child complete: {marker}"
            chunks = [
                {
                    "id": f"chatcmpl-{marker}-done", "object": "chat.completion.chunk", "created": 2,
                    "model": "gpt-test", "choices": [{"index": 0, "delta": {"role": "assistant", "content": final},
                    "finish_reason": None}],
                },
                {
                    "id": f"chatcmpl-{marker}-done", "object": "chat.completion.chunk", "created": 2,
                    "model": "gpt-test", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
                },
            ]
        else:
            raise AssertionError(f"child made unexpected provider turn {turn + 1}")
        self._stream(handler, chunks)


def write_discovery_sentinels(project: pathlib.Path, agent_dir: pathlib.Path) -> None:
    resources = (
        project / "AGENTS.md",
        project / ".pi" / "AGENTS.md",
        project / ".pi" / "extensions" / "ambient.ts",
        project / ".pi" / "skills" / "ambient" / "SKILL.md",
        project / ".pi" / "prompts" / "ambient.md",
        agent_dir / "AGENTS.md",
        agent_dir / "extensions" / "ambient.ts",
        agent_dir / "skills" / "ambient" / "SKILL.md",
        agent_dir / "prompts" / "ambient.md",
    )
    for resource in resources:
        resource.parent.mkdir(parents=True, exist_ok=True)
        resource.write_text(DISCOVERY_SENTINEL + "\n", encoding="utf-8", newline="\n")


def resolve_harness_git() -> str:
    candidate = shutil.which("git.exe" if os.name == "nt" else "git") or shutil.which("git")
    if candidate is None:
        raise AssertionError("Git is not available on PATH")
    resolved = pathlib.Path(candidate).resolve()
    if not resolved.is_file() or not resolved.is_absolute():
        raise AssertionError(f"Git did not resolve to an absolute real file: {candidate}")
    return str(resolved)


def reviewed_tool_path(node: str, git: str) -> str:
    candidates = [pathlib.Path(node), pathlib.Path(git), pathlib.Path(sys.executable)]
    for name in (("py.exe", "python.exe", "python3.exe") if os.name == "nt" else ("python3", "python")):
        value = shutil.which(name)
        if value is not None:
            candidates.append(pathlib.Path(value).resolve())
    comspec = os.environ.get("ComSpec")
    if comspec:
        candidates.append(pathlib.Path(comspec).resolve())
    directories: list[str] = []
    identities: set[str] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if not resolved.is_file() or not resolved.is_absolute():
            raise AssertionError(f"reviewed tool is not an absolute real file: {candidate}")
        directory = str(resolved.parent)
        identity = os.path.normcase(directory)
        if identity not in identities:
            identities.add(identity)
            directories.append(directory)
    return os.pathsep.join(directories)


def isolated_runtime_env(root: pathlib.Path, tool_path: str) -> dict[str, str]:
    home = root / "home"
    temp = root / "temp"
    appdata = home / "appdata"
    localappdata = home / "localappdata"
    xdg = home / "xdg"
    session_dir = root / "sessions"
    agent_dir = root / "agent"
    for path in (home, temp, appdata, localappdata, xdg, session_dir, agent_dir):
        path.mkdir(parents=True, exist_ok=True)
    environment = {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(appdata),
        "LOCALAPPDATA": str(localappdata),
        "TEMP": str(temp),
        "TMP": str(temp),
        "TMPDIR": str(temp),
        "XDG_CONFIG_HOME": str(xdg),
        "XDG_CACHE_HOME": str(xdg / "cache"),
        "XDG_DATA_HOME": str(xdg / "data"),
        "PATH": tool_path,
        "PI_CODING_AGENT_DIR": str(agent_dir),
        "PI_CODING_AGENT_SESSION_DIR": str(session_dir),
        "PI_OFFLINE": "1",
        "PI_TELEMETRY": "0",
    }
    for name in ("ComSpec", "PATHEXT", "SystemRoot", "WINDIR"):
        if os.environ.get(name):
            environment[name] = os.environ[name]
    if os.name != "nt":
        environment.update({
            "USER": "ca-pi-live",
            "LOGNAME": "ca-pi-live",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "SHELL": os.environ.get("SHELL", "/bin/sh"),
        })
    return environment


def child_parent_env(root: pathlib.Path, agent_dir: pathlib.Path, tool_path: str) -> dict[str, str]:
    environment = isolated_runtime_env(root, tool_path)
    environment["PI_CODING_AGENT_DIR"] = str(agent_dir)
    environment["OPENAI_API_KEY"] = PROVIDER_KEY
    return environment


def write_model_config(agent_dir: pathlib.Path, project: pathlib.Path, base_url: str) -> None:
    agent_dir.mkdir(parents=True, exist_ok=True)
    document = {
        "providers": {
            "openai": {
                "baseUrl": base_url,
                "api": "openai-completions",
                "apiKey": "$OPENAI_API_KEY",
                "compat": {"supportsDeveloperRole": False, "supportsReasoningEffort": False},
                "models": [{
                    "id": "gpt-test", "name": "codeArbiter deterministic live model",
                    "reasoning": False, "input": ["text"], "contextWindow": 128_000,
                    "maxTokens": 4_096,
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                }],
            }
        }
    }
    (agent_dir / "models.json").write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    (agent_dir / "settings.json").write_text(
        json.dumps({"defaultProjectTrust": "always"}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (agent_dir / "trust.json").write_text(
        json.dumps({str(project.resolve()): True}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    # Pi always initializes its own auth backend. Seed only this disposable,
    # isolated store and prove ca-pi/the child leave its exact bytes untouched.
    (agent_dir / "auth.json").write_bytes(b"{}\n")


def live_request(
    node: str,
    cli: pathlib.Path,
    root: pathlib.Path,
    marker: str,
    base_url: str,
    git: str,
    tool_path: str,
) -> tuple[dict, pathlib.Path, pathlib.Path]:
    project = root / "project"
    agent_dir = root / "agent"
    project.mkdir(parents=True, exist_ok=True)
    (project / ".codearbiter").mkdir()
    (project / ".codearbiter" / "CONTEXT.md").write_text(
        "---\narbiter: enabled\n---\n", encoding="utf-8", newline="\n",
    )
    write_discovery_sentinels(project, agent_dir)
    write_model_config(agent_dir, project, base_url)
    subprocess.run(
        [git, "init", "-b", "feature/pi-live-child"], cwd=project,
        check=True, text=True, encoding="utf-8", errors="strict", capture_output=True, timeout=15,
    )
    (project / "mutation-sentinel.txt").write_text("must remain untracked\n", encoding="utf-8")
    package = REPO / "plugins/ca-pi"
    request = {
        "nodePath": node,
        "piCliPath": str(cli),
        "provider": "openai",
        "model": "gpt-test",
        "tools": EXPECTED_TOOLS,
        "cwd": str(project.resolve()),
        "childExtensionPath": str((package / "extensions/codearbiter-child.js").resolve()),
        "skillPaths": [str((package / "routines/tdd/SKILL.md").resolve())],
        "charterPath": str((package / "agents/backend-author.md").resolve()),
        "task": f"Return the deterministic completion after the requested tool result. {marker}",
        "parentEnv": child_parent_env(root, agent_dir, tool_path),
        "platform": "win32" if os.name == "nt" else sys.platform,
        "timeoutMs": 45_000,
    }
    return request, project, agent_dir


def build_runner_bundle(node: str, output: pathlib.Path) -> None:
    tools = REPO / "plugins/ca-pi/tools"
    esbuild = tools / "node_modules/esbuild/bin/esbuild"
    completed = subprocess.run(
        [node, str(esbuild), "src/runner.ts", "--bundle", "--platform=node", "--format=esm",
         "--target=node22", f"--outfile={output}"],
        cwd=tools, text=True, encoding="utf-8", errors="strict", capture_output=True, check=False, timeout=30,
    )
    if completed.returncode != 0 or not output.is_file():
        raise AssertionError(f"production runner harness bundle failed: {completed.stderr[-2000:]}")


def runner_helper(path: pathlib.Path, runner_bundle: pathlib.Path) -> None:
    runner_url = runner_bundle.resolve().as_uri()
    path.write_text(
        f"""let raw = '';
for await (const chunk of process.stdin) raw += chunk.toString('utf8');
const request = JSON.parse(raw);
process.argv[1] = request.piCliPath;
const {{ runPiChild }} = await import({json.dumps(runner_url)});
const result = await runPiChild(request, new AbortController().signal);
process.stdout.write(JSON.stringify(result));
""",
        encoding="utf-8",
        newline="\n",
    )


def live_child_contract(node: str, cli: pathlib.Path, git: str, tool_path: str) -> None:
    extension_root = REPO / "plugins/ca-pi/extensions"
    with tempfile.TemporaryDirectory(prefix=".ca-pi-live-runner-", dir=extension_root) as runner_td, \
            tempfile.TemporaryDirectory(prefix="ca-pi-task6-live-") as td, DeterministicOpenAiServer() as provider:
        runner_bundle = pathlib.Path(runner_td) / "runner.mjs"
        build_runner_bundle(node, runner_bundle)
        root = pathlib.Path(td)
        helper = root / "invoke-production-runner.mjs"
        runner_helper(helper, runner_bundle)
        fixtures = [
            live_request(node, cli, root / f"child-{index}", marker, provider.base_url, git, tool_path)
            for index, marker in enumerate(TASK_MARKERS, start=1)
        ]
        processes = [
            subprocess.Popen(
                [node, str(helper)], cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="strict",
                env=isolated_runtime_env(root / f"runner-{index}", tool_path),
            )
            for index, (_request, _project, _agent) in enumerate(fixtures, start=1)
        ]
        results: list[dict] = []
        runner_stderr: list[str] = []
        for process, (request, _project, _agent) in zip(processes, fixtures, strict=True):
            try:
                stdout, stderr = process.communicate(json.dumps(request), timeout=60)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                stdout, stderr = process.communicate(timeout=10)
                raise AssertionError(f"live production runner timed out: {stderr[-2000:]}") from exc
            if process.returncode != 0:
                raise AssertionError(f"live production runner exited {process.returncode}: {stderr[-4000:]}")
            try:
                results.append(json.loads(stdout))
                runner_stderr.append(stderr)
            except json.JSONDecodeError as exc:
                raise AssertionError(f"live production runner returned non-JSON: {stdout[-2000:]!r}") from exc

        if provider.errors:
            raise AssertionError(f"deterministic provider contract failed: {provider.errors!r}")
        for index, (marker, result) in enumerate(zip(TASK_MARKERS, results, strict=True)):
            expected_output = f"live child complete: {marker}"
            if result.get("terminal") != "completed" or result.get("output") != expected_output:
                raise AssertionError(
                    "live child did not complete through production runner: "
                    f"result={result!r} provider_turns={len(provider.requests[marker])} "
                    f"runner_stderr={runner_stderr[index][-4000:]!r}"
                )
            if not isinstance(result.get("pid"), int) or not result.get("correlationId"):
                raise AssertionError(f"live child omitted fresh-process identity: {result!r}")
            if len(provider.requests[marker]) != 2:
                raise AssertionError(f"live child provider turn count drifted: {marker} {len(provider.requests[marker])}")
        if results[0]["pid"] == results[1]["pid"]:
            raise AssertionError("two isolated child launches reused one PID")

        for request, project, agent_dir in fixtures:
            status = subprocess.run(
                [git, "status", "--porcelain", "--", "mutation-sentinel.txt"],
                cwd=project, check=True, text=True,
                encoding="utf-8", errors="strict", capture_output=True, timeout=15,
            ).stdout
            cached = subprocess.run(
                [git, "diff", "--cached", "--name-only"], cwd=project, check=True, text=True,
                encoding="utf-8", errors="strict", capture_output=True, timeout=15,
            ).stdout
            if status.strip() != "?? mutation-sentinel.txt" or cached.strip() != "":
                raise AssertionError(
                    f"blocked H-03 command changed the child project index: status={status!r} cached={cached!r}"
                )
            session_root = pathlib.Path(request["parentEnv"]["PI_CODING_AGENT_SESSION_DIR"])
            if list(session_root.rglob("*.jsonl")) or list(agent_dir.rglob("*.jsonl")):
                raise AssertionError("--no-session child persisted a session transcript")
            if (agent_dir / "auth.json").read_bytes() != b"{}\n":
                raise AssertionError("live child unexpectedly modified its isolated Pi auth store")
            settings = json.loads((agent_dir / "settings.json").read_text(encoding="utf-8"))
            saved_trust = json.loads((agent_dir / "trust.json").read_text(encoding="utf-8"))
            if settings.get("defaultProjectTrust") != "always" or saved_trust.get(str(project.resolve())) is not True:
                raise AssertionError("saved/default always-trust sentinel did not survive the isolated launch")

        invalid = dict(fixtures[0][0])
        invalid["nodePath"] = "node"
        degraded = subprocess.run(
            [node, str(helper)], cwd=REPO, input=json.dumps(invalid), text=True, encoding="utf-8",
            errors="strict", capture_output=True, check=False, timeout=30,
            env=isolated_runtime_env(root / "runner-degraded", tool_path),
        )
        if degraded.returncode != 0:
            raise AssertionError(f"degraded production probe crashed: {degraded.stderr[-2000:]}")
        degraded_result = json.loads(degraded.stdout)
        if degraded_result != {
            "terminal": "degraded",
            "diagnostic": "Pi child isolation failed safely; no inline promotion is available; run /ca-doctor.",
        }:
            raise AssertionError(f"failed isolation was not fixed degraded/no-inline: {degraded_result!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-only", action="store_true")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PiChildFixtureContract)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    if not args.fixture_only:
        node, cli = live_pi_cli()
        git = resolve_harness_git()
        tool_path = reviewed_tool_path(node, git)
        with tempfile.TemporaryDirectory(prefix="ca-pi-task6-help-") as help_td:
            help_root = pathlib.Path(help_td)
            help_cwd = help_root / "cwd"
            help_cwd.mkdir(parents=True, exist_ok=True)
            live_help_contract(
                node,
                cli,
                help_cwd,
                isolated_runtime_env(help_root / "environment", tool_path),
            )
        live_child_contract(node, cli, git, tool_path)
        print("Pi Task 6 live supported-version help and isolated-child contract: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
