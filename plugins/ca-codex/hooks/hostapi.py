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

import os
import subprocess


class Host:
    """One host's answers to the host-coupled questions the hooks ask.

    The base class IS the Claude Code host (name "claude"): its defaults are
    the exact pre-seam behavior of the inlined call sites, and load_host()
    falls back to a bare Host() when no per-plugin `_host.py` is present so
    nothing breaks on a partial install.
    """

    name = "claude"

    # Capability flags — what surfaces this host actually has. A hook that
    # heals/queries a statusline gates on has_statusline; a hook registered
    # for a Read tool gates on has_read_tool (Codex has neither).
    # has_prunable_transcript gates the prune ENGINE only (it rewrites
    # Claude-Code-format transcript JSONL); the audit staleness-warn sharing
    # that entry reads .codearbiter logs and runs on every host.
    has_statusline = True
    has_read_tool = True
    has_prunable_transcript = True

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
             an existing directory (no Claude call site passes a payload
             today, so this leg is inert under Claude Code; it exists for
             hosts with no project-dir env var).
          3. `git rev-parse --show-toplevel` from the process cwd.
          4. the process cwd.
        """
        env_root = os.environ.get("CLAUDE_PROJECT_DIR")
        if env_root and os.path.isdir(env_root):
            return env_root
        if payload:
            cwd = payload.get("cwd") if isinstance(payload, dict) else None
            if cwd and os.path.isdir(cwd):
                return cwd
        try:
            out = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=5,
            )
            if out.returncode == 0:
                return out.stdout.strip()
        except Exception:  # noqa: BLE001
            pass
        return os.getcwd()

    def plugin_root(self):
        """The plugin payload root: CLAUDE_PLUGIN_ROOT when set, else derived
        from this file's own location (<root>/hooks/hostapi.py -> <root>) —
        exactly the pre-seam per-entry-script derivation, which resolved
        relative to a file in the same hooks/ directory."""
        env = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if env:
            return env
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

            {"file_path":  the native path string,
             "kind":       "write" | "edit" | "delete",
             "content":    the file's FULL resulting content when knowable
                           (a Write / patch Add File), else None,
             "added_text": the raw text this op introduces (content for a
                           write, new_string for an edit, joined + lines for
                           a patch hunk),
             "added_lines": added_text split into lines}

        This is the seam the shared pre-write.py / post-write-edit.py entries
        iterate, so a host whose one write tool carries MANY file operations
        (Codex's apply_patch envelope) hits the same per-file guard logic as
        Claude's one-file-per-call Write/Edit.

        The Claude mapping preserves the pre-seam behavior EXACTLY:
          * Edit / MultiEdit / NotebookEdit -> "edit" op(s) whose added_text is
            new_string (NotebookEdit carries notebook_path and introduces no
            reasoned-about content).
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
                new = (e or {}).get("new_string", "") or ""
                ops.append({"file_path": fpath, "kind": "edit", "content": None,
                            "added_text": new, "added_lines": new.splitlines()})
            return ops
        if tool in ("Edit", "NotebookEdit"):
            fpath = ti.get("file_path", "") or ti.get("notebook_path", "") or ""
            new = ti.get("new_string", "") or ""
            return [{"file_path": fpath, "kind": "edit", "content": None,
                     "added_text": new, "added_lines": new.splitlines()}]
        # Write, and the guard-everything default (see docstring).
        fpath = ti.get("file_path", "") or ""
        content = ti.get("content", "") or ""
        added = content or (ti.get("new_string", "") or "")
        return [{"file_path": fpath, "kind": "write", "content": content,
                 "added_text": added, "added_lines": added.splitlines()}]


def load_host():
    """The Host instance for this plugin: `HOST` from the `_host.py` sitting
    beside this file, loaded by explicit file path (each plugin ships its own
    `_host.py`; the shared core deliberately does not). Falls back to the
    built-in Claude defaults (a bare Host()) when `_host.py` is absent or
    fails to load, so a partial install degrades to today's behavior instead
    of breaking."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_host.py")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_host", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.HOST
    except Exception:  # noqa: BLE001 — no/broken _host.py -> Claude defaults
        return Host()
