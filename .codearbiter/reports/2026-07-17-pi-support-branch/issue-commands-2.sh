#!/usr/bin/env bash
set -e
R=arbiterForge/codeArbiter
B="Branch: feat/pi-support · Tribunal run 2026-07-17-pi-support-branch · Finding:"
gh issue create -R $R -l sev:med -t "ca-pi: harden bridge.ts failure paths — killTree deadline + ready rejection guard (reliability-001/003)" -b "$B findings/reliability/reliability-001.json, reliability-003.json (group bridge-hardening)
bridge.ts:302-335 win32 taskkill spawnSync has no timeout/fallback/settle deadline (wedge). bridge.ts:172-199 ready=validatePaths() unhandled until first call() (crash)."
gh issue create -R $R -l sev:med -t "core: decompose pre-bash.py fat entry point into _bashguardlib (architecture-001)" -b "$B findings/architecture/architecture-001.json
core/pysrc/pre-bash.py 1,119 LOC; _run spans 765-1075; violates the repo thin-entrypoint convention; synced 3 hosts."
gh issue create -R $R -l sev:med -t "core: partition _hooklib.py god module (architecture-002)" -b "$B findings/architecture/architecture-002.json
1,201 LOC / 46 functions / 28 of 44 consumers. Partition along concern seams (_activationlib, _sensitivelib). Sequence after architecture-001."
gh issue create -R $R -l sev:med -t "core: _gitexec trusted-executable path validation untested (coverage-003)" -b "$B findings/coverage/coverage-003.json
core/pysrc/_gitexec.py:16-37 _trusted_environment_path has no direct unit test."
gh issue create -R $R -l sev:med -t "ci-impact: fail-safe except branch untested (coverage-004)" -b "$B findings/coverage/coverage-004.json
tools/ci-impact.py:422-448 fall-back-to-broad-validation branch never exercised; ReceiptCommandTest covers only success."
gh issue create -R $R -l sev:med -t "ca-pi: benchmark stubs BridgePort.call — real spawn cost unmeasured (performance-002)" -b "$B findings/performance/performance-002.json
benchmark-boundary.ts:40-45 resolves instantly instead of exercising BridgeClient/pi-bridge.py."
gh issue create -R $R -l sev:low -t "core: guard write_standup_marker in session-start.py (reliability-004)" -b "$B findings/reliability/reliability-004.json
session-start.py:864-872 unguarded write can fail the never-brick SessionStart hook."
gh issue create -R $R -l sev:low -t "tools: make sync-core.py vendored writes atomic (reliability-005)" -b "$B findings/reliability/reliability-005.json
sync-core.py:105-111 in-place write; interruption leaves truncated vendored hooks. temp+os.replace."
gh issue create -R $R -l sev:low -t "ca-pi: remove three dead exports in tools/src (architecture-003)" -b "$B findings/architecture/architecture-003.json
bridge.ts:406 resolvePythonExecutable, compaction.ts:453 compactionLimits, attestation.ts:4 export keyword. Rebuild bundles."
gh issue create -R $R -l sev:low -t "core: _gitexec/_prunepolicy missing Public API header convention (typesafety-002)" -b "$B findings/typesafety/typesafety-002.json
Add the mandated '# Public API: name(args) -> type' headers and arg/return contracts."
gh issue create -R $R -l decision -t "decision: per-call Python bridge spawn vs persistent worker (performance-001)" -b "$B findings/performance/performance-001.json
Every gated Pi tool call spawns a fresh Python bridge process (bridge.ts:269-338). Options: (a) accept per-call spawn as the cross-host standard cost model; (b) persistent bridge worker (daemon lifecycle + new security surface). ADR-candidate — resolve via /ca:adr. Downgraded from high: Claude Code pays the same per-call hook-spawn cost."
gh issue create -R $R -l documentation,sev:high -t "docs-site: Pi host has zero presence on the published site (6 gaps)" -b "$B findings/docs-pi/01-06
No Pi page, sidebar entry, install/trust/version/Windows/uninstall/troubleshooting content on the site; all lives in repo-root README/docs only. 3 high / 3 medium gap files enumerate the pages to add."
gh issue create -R $R -l documentation -t "docs-site: Claude Code journey gaps — site describes 2 hosts, repo ships 4 plugins (15 gaps)" -b "$B findings/docs-claude-code/01-15
overview/index/install stale on the 4-plugin reality; ca-sandbox has no page; 3 high / 7 medium / 5 low gap files enumerate."
gh issue create -R $R -l documentation -t "docs-site: Codex reference gaps — inline-role model and \$ca- syntax undocumented (3 gaps)" -b "$B findings/docs-codex/01-03
Reference section never states Codex runs roles inline vs Task-dispatch; command pages show only /ca: syntax; concurrent same-checkout guidance missing."
gh issue create -R $R -l documentation -t "docs-site: visuals roadmap — commit-gate phases, core fan-out, og:image (9 opportunities)" -b "$B findings/docs-visuals/01-09
Top three: commit-gate 9-phase SVG, core->three-host generation fan-out SVG, social-preview card. House-style hand-drawn SVG/mermaid; GPT-rendered art flagged as slop risk, not recommended."
