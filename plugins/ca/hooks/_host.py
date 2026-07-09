#!/usr/bin/env python3
# codeArbiter — the Claude Code host definition for THIS plugin (ADR-0011).
#
# Per-plugin, deliberately NOT part of the shared core (core/pysrc/): each
# plugin ships its own _host.py naming the host it targets, and
# hostapi.load_host() loads it by file path from the hooks directory. The
# ca plugin targets Claude Code, whose behavior is exactly hostapi.Host's
# built-in defaults (project_root = CLAUDE_PROJECT_DIR -> payload cwd ->
# git rev-parse -> cwd; plugin_root = CLAUDE_PLUGIN_ROOT -> file-relative;
# Bash/PowerShell -> EXEC, Write -> WRITE, Edit/MultiEdit/NotebookEdit ->
# EDIT, Read -> READ; tool_input passes through unchanged; statusline and
# Read tool both present) — so this subclass overrides nothing.
#
# The ca-codex sibling plugin (M2) ships a _host.py whose subclass overrides
# name/"codex", the tool map (exec tool "Bash"; writes/edits arrive as
# apply_patch), normalize_tool_input (patch -> canonical shapes),
# project_root (no project-dir env var; payload cwd first), and the
# capability flags (has_statusline=False, has_read_tool=False).

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402


class ClaudeHost(hostapi.Host):
    """Claude Code — hostapi.Host's defaults ARE this host's behavior."""


HOST = ClaudeHost()
