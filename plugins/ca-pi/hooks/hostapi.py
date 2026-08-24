#!/usr/bin/env python3
# codeArbiter — host-abstraction seam (ADR-0011, codex-support M1).
#
# The hooks were written against exactly one host: Claude Code. Every
# host-coupled assumption — which env var names the project dir, which env var
# names the plugin root, what the tool names in a PreToolUse payload mean,
# whether a statusline or a Read tool even exists — used to be inlined at each
# call site. This module is the ONE seam those assumptions flow through, so a
# second host (Codex CLI, M2) can ship its own `_host.py` beside the vendored
# hooks without forking any of them.
#
# Design (stdlib only, ADR-0004):
#   * `Host` is a plain class whose DEFAULTS are exactly today's Claude Code
#     behavior — the built-in fallback load_host() uses when no `_host.py`
#     exists. A different host subclasses Host and overrides what differs.
#   * `_host.py` (per-plugin, NOT part of the shared core) defines `HOST`,
#     the host instance for the plugin it ships in. load_host() loads it by
#     FILE PATH from this module's own directory — never via sys.path — so
#     the resolution cannot be hijacked by the caller's import state.
#   * Canonical tool categories: "EXEC" | "WRITE" | "EDIT" | "READ" | "OTHER".
#     Canonical tool-input shapes: {file_path, content} for WRITE,
#     {file_path, old_string, new_string} for EDIT, {command} for EXEC.
#     Claude Code's payloads already ARE the canonical shape, so the Claude
#     host passes tool_input through unchanged; a host whose native shape
#     differs (e.g. Codex's apply_patch) translates in normalize_tool_input.
#
# Behavioral contract for M1: under Claude Code, everything routed through
# this seam resolves to byte-identical results as the pre-seam inline code.

import json
import os
import re
import subprocess
import sys

from _gitexec import git_executable


class PluginRootError(RuntimeError):
    """A host adapter's installed package boundary cannot be authenticated."""


_VERSION_RE = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?(?:\+[0-9A-Za-z][0-9A-Za-z.-]*)?$")


def _safe_relative_path(value, label):
    """Reject an absolute or traversing adapter-relative path before joining."""
    if not isinstance(value, str) or not value:
        raise PluginRootError(f"{label} must be a non-empty relative path")
    normalized = os.path.normpath(value)
    if (os.path.isabs(value) or normalized == os.pardir or
            normalized.startswith(os.pardir + os.sep)):
        raise PluginRootError(f"{label} escapes the adapter: {value!r}")
    return normalized


def _inside(root, candidate):
    """Whether normalized ``candidate`` is contained by normalized ``root``."""
    try:
        return os.path.commonpath((root, candidate)) == root
    except ValueError:  # distinct Windows volumes are never contained
        return False


def resolve_plugin_root(authority_file, *, adapter_name, manifest_relpath,
                        anchor_relpath, environment=None, signal_names=(),
                        required_signal_names=(), legacy_signal_names=()):
    """Return the authenticated root of the executing adapter, or fail closed.

    The authority is the file/module that is already executing. Environment
    variables may only corroborate that exact real path; none can select a
    different, merely plausible package. ``anchor_relpath`` and the manifest
    are constrained inside that root so traversal and symlink escapes cannot
    authenticate an external file.
    """
    if not isinstance(adapter_name, str) or not adapter_name:
        raise PluginRootError("adapter name must be a non-empty string")
    manifest_relpath = _safe_relative_path(manifest_relpath, "manifest path")
    anchor_relpath = _safe_relative_path(anchor_relpath, "anchor path")
    env = os.environ if environment is None else environment

    source = os.path.realpath(os.path.abspath(authority_file))
    root = os.path.dirname(os.path.dirname(source))
    anchor = os.path.realpath(os.path.join(root, anchor_relpath))
    if not _inside(root, anchor) or anchor != source or not os.path.isfile(anchor):
        raise PluginRootError(
            f"executing adapter anchor is outside or missing from its package: {source}")

    manifest = os.path.realpath(os.path.join(root, manifest_relpath))
    if not _inside(root, manifest) or not os.path.isfile(manifest):
        raise PluginRootError(
            f"{adapter_name}: required manifest is missing or outside the adapter: {manifest}")
    try:
        with open(manifest, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise PluginRootError(
            f"{adapter_name}: required manifest is unreadable: {manifest} ({error})") from error
    name = data.get("name") if isinstance(data, dict) else None
    version = data.get("version") if isinstance(data, dict) else None
    if name != adapter_name:
        raise PluginRootError(
            f"adapter manifest mismatch at {manifest}: expected {adapter_name!r}, got {name!r}")
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        raise PluginRootError(
            f"adapter manifest has invalid version at {manifest}: {version!r}")

    for signal in required_signal_names:
        if not env.get(signal):
            raise PluginRootError(
                f"{adapter_name}: required {signal} is absent; executing root is {root}")
    for signal in signal_names:
        value = env.get(signal)
        if not value:
            continue
        claimed = os.path.realpath(os.path.abspath(value))
        if claimed != root:
            raise PluginRootError(
                f"{adapter_name}: {signal} root {claimed} disagrees with "
                f"executing adapter root {root}")
        if signal in legacy_signal_names:
            sys.stderr.write(
                f"codeArbiter: {signal} is deprecated for {adapter_name}; "
                "accepted only as matching corroboration.\n")
    return root


def git_toplevel(cwd=None):
    """`git rev-parse --show-toplevel`, run FROM `cwd` when given (`git -C
    cwd ...`) rather than the process's own cwd. Returns the resolved
    toplevel path, or None on any failure (not a repo, git missing, timeout,
    empty output) — callers decide the fallback.

    Shared by every Host.project_root payload-cwd leg (base Host and
    CodexHost, #260/reliability-005): a hook payload's `cwd` can be a repo
    SUBDIRECTORY (e.g. a Codex session started below the repo root), and the
    project root must be the repo TOPLEVEL, not that subdirectory verbatim —
    `.codearbiter/` state lives at the root."""
    args = [git_executable()]
    if cwd:
        args += ["-C", cwd]
    args += ["rev-parse", "--show-toplevel"]
    try:
        out = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=5,
        )
        if out.returncode == 0:
            top = out.stdout.strip()
            if top:
                return top
    except Exception:  # noqa: BLE001
        pass
    return None


def git_worktree_main_root(root):
    """When `root` (an already-resolved project root — a `project_root()`
    answer, NOT necessarily a fresh `git_toplevel` call) is itself the
    checkout of a LINKED git worktree, the MAIN checkout's root that owns the
    shared `.git` directory — else `None`.

    #604: `security-pass.py`/`migration-pass.py` and the H-09b/H-10b/H-14
    guards were found resolving DIFFERENT roots for GATE MARKERS in a
    linked-worktree session — a hook subprocess trusts a (possibly stale)
    `CLAUDE_PROJECT_DIR` naming the MAIN checkout, while `security-pass.py`
    run bare via Bash (no `CLAUDE_PROJECT_DIR` in that shell) fell through to
    `git_toplevel()`, which names the WORKTREE's own checkout — so a gate
    pass recorded by one was never seen by the other. `.codearbiter/
    .markers/` is gitignored, so a linked worktree's own checkout never has
    one freshly — the git-hook guard's diff/branch resolution already
    carries this exact split (`_bashguardlib._effective_exec_root`'s
    docstring, D-2: gate markers stay pinned to the main checkout regardless
    of the command's effective exec root).

    Deliberately NOT wired into `Host.project_root()` itself: `project_root()`
    also backs `security-pass.py`'s DIFF SCAN (`candidate_lines()`), which
    must stay worktree-local — escalating the general project root to "main"
    would bind digests to the wrong (unrelated, possibly dirty) tree and
    silently drop coverage for the diff actually being committed, the exact
    trap the issue this closes warns against. Callers that specifically need
    the gate-MARKER root call this as a targeted escalation on top of an
    already-resolved `project_root()` answer instead — e.g.
    `git_worktree_main_root(root) or root` — so every OTHER project_root()
    consumer (diff scans, `arbiter_active`, …) is entirely unaffected, and
    the two callers agree on marker location without `git_toplevel`'s own
    `git rev-parse` mechanism being replaced anywhere (deliberate: symlink/
    8.3 canonicalization, #125).

    Distinguishes a linked worktree from a submodule — both have a `.git`
    FILE, but only a worktree's `gitdir:` pointer names a path under
    `.git/worktrees/<name>`; a submodule's names `.git/modules/<name>`, which
    is not a "main root" to climb to and must fall through untouched (mirrors
    `_durabilitylib._gitfile_points_at_worktree`'s same distinction)."""
    git_meta = os.path.join(root, ".git")
    if not os.path.isfile(git_meta):
        return None
    try:
        with open(git_meta, encoding="utf-8", errors="replace") as f:
            pointer = f.read().strip()
    except OSError:
        return None
    if not pointer.startswith("gitdir: "):
        return None
    gitdir = pointer[len("gitdir: "):].strip().replace("\\", "/")
    marker = "/.git/worktrees/"
    idx = gitdir.find(marker)
    if idx == -1:
        return None  # not a linked worktree (e.g. a submodule) — nothing to climb to
    main_git_dir = gitdir[:idx + len("/.git")]
    return os.path.dirname(main_git_dir) or None


class Host:
    """One host's answers to the host-coupled questions the hooks ask.

    The base class IS the Claude Code host (name "claude"): its defaults are
    the exact pre-seam behavior of the inlined call sites, and load_host()
    falls back to a bare Host() when no per-plugin `_host.py` is present so
    nothing breaks on a partial install.
    """

    name = "claude"
    adapter_name = "ca"

    # Capability flags — what surfaces this host actually has. A hook that
    # heals/queries a statusline gates on has_statusline; a hook registered
    # for a Read tool gates on has_read_tool (Codex has neither).
    # has_prunable_transcript gates the prune ENGINE only (it rewrites
    # Claude-Code-format transcript JSONL); the audit staleness-warn sharing
    # that entry reads .codearbiter logs and runs on every host.
    has_statusline = True
    has_read_tool = True
    has_prunable_transcript = True

    # The noun the startup briefing uses for the command channel. Claude Code
    # namespaces plugin commands behind slash commands; a host without a
    # command namespace overrides this (and cmd_ref below).
    command_noun = "slash command"

    def cmd_ref(self, name):
        """The host-native spelling of governance command `name` in any
        RUNTIME-emitted string (startup briefing, block reason, doctor line,
        scaffold text). The markdown surface handles the same divergence at
        build time via {{CMD:name}} in tools/build-surface.py; this method is
        the runtime twin — the two must agree per host (codex-support M3)."""
        return "/ca:" + name

    # Native tool name -> canonical category. Anything unlisted is "OTHER".
    TOOL_MAP = {
        "Bash": "EXEC",
        "PowerShell": "EXEC",
        "Write": "WRITE",
        "Edit": "EDIT",
        "MultiEdit": "EDIT",
        "NotebookEdit": "EDIT",
        "Read": "READ",
    }

    def project_root(self, payload=None):
        """The project root. Resolution order (matches the pre-seam
        _hooklib.project_root exactly — see its docstring for the rationale):

          1. CLAUDE_PROJECT_DIR, when set and an existing directory — the
             harness's own authoritative signal, trusted first.
          2. the hook payload's `cwd`, when a payload is given and its cwd is
             an existing directory — climbed to the git TOPLEVEL from that
             cwd (git_toplevel), falling back to the cwd itself when that
             climb fails (not a git repo). No Claude call site passes a
             payload today (architecture-006, #260), so this leg is inert
             under Claude Code; it exists for hosts with no project-dir env
             var.
          3. `git rev-parse --show-toplevel` from the process cwd.
          4. the process cwd.

        Deliberately climbs no further than the WORKTREE's own toplevel in a
        linked-worktree session — a caller wanting the gate-MARKER root (which
        must agree on the MAIN checkout, #604) calls `marker_root()` instead;
        see its docstring for why the two must not be conflated."""
        env_root = os.environ.get("CLAUDE_PROJECT_DIR")
        if env_root and os.path.isdir(env_root):
            return env_root
        if payload:
            cwd = payload.get("cwd") if isinstance(payload, dict) else None
            if cwd and os.path.isdir(cwd):
                return git_toplevel(cwd) or cwd
        top = git_toplevel()
        if top:
            return top
        return os.getcwd()

    def marker_root(self, payload=None):
        """The root `.codearbiter/.markers/` gate passes (security-pass.py,
        migration-pass.py, and the H-09b/H-10b/H-14 guards) are written to
        and read from (#604).

        Identical to `project_root(payload)` in every case except one: when
        that resolves to a LINKED git worktree's own checkout, this escalates
        to the MAIN checkout that owns the shared `.git` directory instead
        (`git_worktree_main_root`) — `.codearbiter/.markers/` is gitignored,
        so a linked worktree's own checkout never has one freshly, and the
        git-hook guard already anchors every marker READ at the main
        checkout regardless of a command's real exec root (D-2,
        `_bashguardlib._effective_exec_root`'s docstring). This gives every
        marker WRITER that same answer even when it runs without
        `CLAUDE_PROJECT_DIR` set — `security-pass.py` invoked bare via a Bash
        tool call, rather than as a registered hook subprocess that inherits
        it from the harness — closing the loop without touching
        `project_root()` itself, which other callers (diff scans in
        particular) need to stay worktree-local."""
        root = self.project_root(payload)
        return git_worktree_main_root(root) or root

    def plugin_root(self):
        """The plugin payload root: CLAUDE_PLUGIN_ROOT when set, else derived
        from this file's own location (<root>/hooks/hostapi.py -> <root>) —
        exactly the pre-seam per-entry-script derivation, which resolved
        relative to a file in the same hooks/ directory."""
        return resolve_plugin_root(
            __file__, adapter_name=self.adapter_name,
            manifest_relpath=self.manifest_relpath(), anchor_relpath="hooks/hostapi.py",
            signal_names=("CLAUDE_PLUGIN_ROOT",),
        )

    def manifest_relpath(self):
        """The plugin manifest's path, relative to plugin_root() (#263,
        reliability-001/002 + observability-003): Claude Code's marketplace
        convention is `.claude-plugin/plugin.json` — the ONLY location this
        host ever reads or writes. A host whose manifest ships elsewhere
        (e.g. Codex's `.codex-plugin/`) overrides this so doctor.py's
        check_payload and _updatelib.installed_version resolve the manifest
        that ACTUALLY exists for the running host, instead of hard-coding the
        Claude path and reporting a healthy Codex install as UNHEALTHY /
        silently never firing the update-available notice."""
        return os.path.join(".claude-plugin", "plugin.json")

    def mcp_config_sources(self, project_root):
        """Where THIS host declares its MCP servers — `[(path, key), ...]`,
        each entry a configuration file and the mapping key under which that
        file declares servers (#270, tribunal appsec-002).

        MCP server tools (`mcp__<server>__<tool>`) sit OUTSIDE the write gate
        on every host: they miss Claude's `Write`/`Edit` matchers, and they
        carry no TOOL_MAP entry on Codex so they normalize to "OTHER" and
        match neither the write hooks nor the exec hook. That is ACCEPTED
        residual risk under ADR-0010 (see .codearbiter/security-controls.md),
        conditioned on the gap being *visible* to the consumer carrying it —
        this repo builds codeArbiter, so the risk never lands here. This seam
        is how `doctor.check_mcp` asks the ACTIVE host where to look, instead
        of hard-coding one host's layout; doctor counts what it finds and
        never reads, echoes, or names a server, command, or argument.

        Claude Code declares servers in two places, and BOTH have to be seen
        or the commonest real configuration reports as "none":
          * `<project>/.mcp.json` — the project scope, checked into the repo.
          * `~/.claude.json` — user scope (top-level `mcpServers`) and local
            scope (`projects.<path>.mcpServers`, same key, nested).

        Return `[]` to mean "this host's MCP configuration surface is not
        known" — doctor then reports NOTHING rather than guessing another
        host's paths. Overrides must not raise; doctor treats a raising seam
        as unknown, but a quiet seam is the contract.
        """
        home = os.path.expanduser("~")
        return [
            (os.path.join(project_root, ".mcp.json"), "mcpServers"),
            (os.path.join(home, ".claude.json"), "mcpServers"),
        ]

    def normalize_tool(self, tool_name):
        """Canonical category for a native tool name:
        "EXEC" | "WRITE" | "EDIT" | "READ" | "OTHER"."""
        return self.TOOL_MAP.get(tool_name or "", "OTHER")

    def normalize_tool_input(self, tool_name, tool_input):
        """The canonical tool-input dict for a native (tool_name, tool_input)
        pair. Claude Code's shapes already are the canonical ones
        ({file_path, content} / {file_path, old_string, new_string} /
        {command}), so this passes through unchanged; a host with a different
        native shape overrides this to translate."""
        return tool_input if isinstance(tool_input, dict) else {}

    def iter_file_ops(self, payload):
        """The canonical per-file operations a WRITE/EDIT-category hook payload
        performs (codex-support M2): a list of dicts, one per touched file —

            {"file_path":   the native path string,
             "kind":        "write" | "edit" | "delete",
             "content":     the file's FULL resulting content when knowable
                            (a Write / patch Add File), else None,
             "added_text":  the raw text this op introduces (content for a
                            write, new_string for an edit, joined + lines for
                            a patch hunk),
             "added_lines": added_text split into lines,
             "old_string":  the text this op's added_text replaces, when the
                            native shape carries one (Edit/MultiEdit's
                            old_string); "" when there is none to reason
                            about (Write, NotebookEdit, a patch hunk),
             "replace_all": True iff this op's native shape asked to replace
                            EVERY occurrence of old_string rather than one
                            (Edit's replace_all); always False otherwise,
             "batched":     True iff this op is one of several fanned from a
                            SINGLE tool call against the same file whose
                            per-op old_string/new_string cannot, on its own,
                            certify a property of the call AS A WHOLE (e.g.
                            MultiEdit's edits array — the edits apply as one
                            atomic batch, so no single entry's old_string/
                            new_string alone certifies something like "this
                            call is a pure append"); callers that need a
                            whole-call verdict must not trust an individual
                            batched op in isolation,
             "notebook":    True iff this op's target has no content/append/
                            frontmatter semantics worth reasoning about
                            (NotebookEdit) — a content-sensitive guard must
                            treat it as opaque rather than replaying it.}

        This is the seam the shared pre-write.py / pre-edit.py / post-write-
        edit.py entries iterate, so a host whose one write tool carries MANY
        file operations (Codex's apply_patch envelope) hits the same per-file
        guard logic as Claude's one-file-per-call Write/Edit/MultiEdit/
        NotebookEdit — and pre-edit.py's guards never have to branch on a
        native tool name to reconstruct these properties (ADR-0011, #261).

        The Claude mapping preserves the pre-seam behavior EXACTLY:
          * Edit -> one "edit" op carrying its own old_string/replace_all.
          * MultiEdit -> one "edit" op per edits[] entry, each carrying that
            entry's own old_string, "batched": True, and "replace_all": False
            (Claude's MultiEdit entries carry no per-edit replace_all field).
          * NotebookEdit -> one "edit" op, "notebook": True, empty old_string
            (NotebookEdit carries notebook_path and introduces no reasoned-
            about content).
          * Write — and ANY unrecognized/missing tool_name — -> one "write" op.
            The pre-seam pre-write.py never read tool_name at all (it guarded
            every payload carrying a file_path), so the default branch must
            not narrow that: an unrecognized payload is guarded as a write,
            with added_text falling back to new_string exactly as the
            pre-seam post-write-edit.py's `content or new_string` read did.
        """
        payload = payload if isinstance(payload, dict) else {}
        tool = payload.get("tool_name", "") or ""
        ti = payload.get("tool_input", {}) or {}
        if not isinstance(ti, dict):
            return []
        if tool == "MultiEdit":
            fpath = ti.get("file_path", "") or ""
            ops = []
            for e in ti.get("edits", []) or []:
                e = e or {}
                old = e.get("old_string", "") or ""
                new = e.get("new_string", "") or ""
                ops.append({"file_path": fpath, "kind": "edit", "content": None,
                            "added_text": new, "added_lines": new.splitlines(),
                            "old_string": old, "replace_all": False,
                            "batched": True, "notebook": False})
            return ops
        if tool == "Edit":
            fpath = ti.get("file_path", "") or ""
            old = ti.get("old_string", "") or ""
            new = ti.get("new_string", "") or ""
            return [{"file_path": fpath, "kind": "edit", "content": None,
                     "added_text": new, "added_lines": new.splitlines(),
                     "old_string": old, "replace_all": bool(ti.get("replace_all")),
                     "batched": False, "notebook": False}]
        if tool == "NotebookEdit":
            fpath = ti.get("notebook_path", "") or ""
            new = ti.get("new_source", "") or ""
            return [{"file_path": fpath, "kind": "edit", "content": None,
                     "added_text": new, "added_lines": new.splitlines(),
                     "old_string": "", "replace_all": False,
                     "batched": False, "notebook": True}]
        # Write, and the guard-everything default (see docstring).
        fpath = ti.get("file_path", "") or ""
        content = ti.get("content", "") or ""
        added = content or (ti.get("new_string", "") or "")
        return [{"file_path": fpath, "kind": "write", "content": content,
                 "added_text": added, "added_lines": added.splitlines(),
                 "old_string": "", "replace_all": False,
                 "batched": False, "notebook": False}]


class FailClosedHost(Host):
    """The host returned when a `_host.py` is PRESENT but fails to load.

    A broken `_host.py` means the plugin declared a host we could not
    construct, so we do NOT know whether this install is Claude, Codex, or a
    future host. Silently substituting the Claude-default `Host()` (as
    load_host once did on ANY failure) is unsafe: on a Codex install the base
    `iter_file_ops` cannot decompose an apply_patch envelope, so it yields an
    empty-path "write" op and every pre-write guard skips — the write gate
    silently fails OPEN (tribunal architecture-004 / typesafety-001, both
    reproduced). This host fails CLOSED instead: every write-batching payload
    resolves to a single "opaque" op, which pre-write.py blocks (H-21), and the
    capability flags are the conservative (absent-surface) values. load_host()
    emits a stderr breadcrumb when it returns this, so a broken host is never
    silent (observability-002)."""

    name = "unknown"
    has_statusline = False
    has_read_tool = False
    has_prunable_transcript = False

    def iter_file_ops(self, payload):
        # Host identity is unknown, so no payload can be safely mapped to
        # per-file ops. Force the fail-closed "opaque" op unconditionally;
        # pre-write blocks it (H-21) rather than guessing a host's semantics.
        return [{"file_path": "", "kind": "opaque", "content": None,
                 "added_text": "", "added_lines": [],
                 "old_string": "", "replace_all": False,
                 "batched": False, "notebook": False}]

    def mcp_config_sources(self, project_root):
        # Same reason as iter_file_ops: the host is unknown, so no config
        # path can be claimed. Reading ~/.claude.json here would report a
        # DIFFERENT host's MCP configuration as this install's. Diagnostics
        # fail quiet (#270) — the write-path guards are what fail closed.
        return []


def load_host(hooks_dir=None):
    """The Host instance for this plugin: `HOST` from the `_host.py` sitting
    beside this file (or in `hooks_dir`, an override for tests), loaded by
    explicit file path (each plugin ships its own `_host.py`; the shared core
    deliberately does not). The failure semantics distinguish two cases so a
    broken host can never silently degrade to the WRONG host's guards:

      * `_host.py` ABSENT -> the bare-core / partial-install fallback: return
        the built-in Claude default `Host()`, exactly as before. No plugin
        declared a host, so Claude defaults are the only meaningful answer and
        "degrade to today's behavior" is safe.
      * `_host.py` PRESENT but fails to load (syntax error, import error,
        unreadable, or no `HOST` symbol) -> a declared host we could not
        construct. Emit a stderr breadcrumb and return `FailClosedHost()`,
        which blocks every write rather than assuming Claude semantics
        (architecture-004 / observability-002 / typesafety-001). The old
        blanket fallback was only safe when the intended host IS Claude."""
    base = hooks_dir or os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "_host.py")
    if not os.path.isfile(path):
        return Host()
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_host", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.HOST
    except Exception as e:  # noqa: BLE001 — declared-but-broken host -> fail closed
        sys.stderr.write(
            "codeArbiter: _host.py is present but failed to load "
            "(%s: %s) — failing closed (writes blocked) rather than assuming "
            "the default host. Reinstall or fix the plugin's _host.py.\n"
            % (type(e).__name__, e)
        )
        return FailClosedHost()
