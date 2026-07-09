#!/usr/bin/env bash
set -euo pipefail
# Tribunal 2026-07-09-codex-support-branch — issue filing (idempotent).

gh issue create --title "Codex write gate silently fails open when _host.py fails to load" --label "sev:high,security,codex" --body-file "bodies/load-host-failopen.md"
gh issue create --title "Codex apply_patch fail-closed backstop is whole-envelope, not per-directive" --label "sev:med,security,codex" --body-file "bodies/parser-partial-op.md"
gh issue create --title "Dead run(host) parameter on all 20 seam entry points" --label "sev:med,codex" --body-file "bodies/dead-run-host-param.md"
gh issue create --title "Wire ca-codex into CI, release, and packaging enforcement gates" --label "sev:high,codex" --body-file "bodies/ci-release-packaging-wiring.md"
gh issue create --title "ca-codex ships ~15 unreachable entry scripts and a broken /ca-init first-run pointer" --label "sev:med,codex" --body-file "bodies/dead-vendored-entries.md"
gh issue create --title "Codex project_root: dead payload-cwd leg, wrong subdir root, and a git subprocess every invocation" --label "sev:med,codex" --body-file "bodies/project-root-seam.md"
gh issue create --title "Shared-core pre-edit.py branches on Claude-native tool names, bypassing the seam" --label "sev:low,codex" --body-file "bodies/pre-edit-native-names.md"
gh issue create --title "ORCHESTRATOR.md is hand-duplicated across plugins with no sync mechanism" --label "sev:med,codex" --body-file "bodies/orchestrator-duplicated.md"
gh issue create --title "Hardcoded .claude-plugin/plugin.json path breaks doctor and the update-notifier on ca-codex" --label "sev:med,codex" --body-file "bodies/manifest-path.md"
gh issue create --title "prune-transcript resolves root off-seam, silently dropping the CONFIRM-09 staleness WARN" --label "sev:low,codex" --body-file "bodies/prune-root-off-seam.md"
gh issue create --title "Dual-host git-hook shims fail open when one plugin is uninstalled" --label "sev:low,codex" --body-file "bodies/githook-shim-crossplugin.md"
gh issue create --title "CodexHost non-patch-tool defensive fallback branch is untested" --label "sev:low,codex" --body-file "bodies/fallback-branch-untested.md"
gh issue create --title "session-start has_statusline gate is not exercised end-to-end under a Codex host" --label "sev:med,codex" --body-file "bodies/has-statusline-gate-untested.md"
gh issue create --title "Startup banner and doctor never surface the resolved host name" --label "sev:med,codex" --body-file "bodies/no-host-marker-diagnostics.md"
gh issue create --title "[Decision] Coordination contract for two hosts sharing one .codearbiter/ store" --label "decision,codex" --body-file "bodies/shared-store-contract.md"
gh issue create --title "[Decision] Are Codex MCP file-write tools in scope for the write gate?" --label "decision,security,codex" --body-file "bodies/mcp-write-scope.md"
