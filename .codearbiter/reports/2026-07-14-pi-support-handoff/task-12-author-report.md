# Task 12 author report: Pi public documentation and release shape

Status: complete. The root orchestrator applied the reviewed `CONTEXT.md`
prose through the sanctioned H-18 override lane and independently proved the
activation frontmatter byte-identical. No staging, commit, push, tag, publish,
or release was performed by this author.

## Test-first evidence

- RED: `python .github/scripts/test_public_pi_docs.py` ran 10 structural tests
  and failed on the absent runbook, two-host vocabulary, missing Pi exception
  ledger, stale release prose, and absent Pi license coverage.
- RED: `python .github/scripts/check-plugin-refs.py ca-pi` exited 2 because
  `ca-pi` was not a known checked plugin.
- The first generated GREEN attempt caught a real catalog drift: the generated
  Pi `ca-prune` skill existed but `/ca-prune` was absent from Pi `COMMANDS.md`.
  The canonical `core/surface/COMMANDS.md` now renders the Pi-native row.
- Generation also exposed a real host-conditional bug: Pi's orchestrator had
  inherited Codex's `$ca-*` spelling and `codex-host-notes.md` through a broad
  `ELSE`. The canonical template now has separate Codex and Pi blocks.

## Implemented documentation surface

- Added `docs/pi-parity-testing.md`: pinned Git-only install, isolated home and
  dummy local provider boundary, trusted-live checklist, safe evidence schema,
  supported Pi 0.80.5/0.80.6 runs, origin/trust/activation/aliases/final-tool
  enforcement/dispatch/cancel/status/compaction/farm/shared-store/uninstall,
  independent `ca-pi-v*` release shape, and future spikes.
- Converted `docs/parity.md` to a three-governance-host evidence matrix with a
  machine-delimited exception ledger. It labels local Pi implementation versus
  the still-pending hosted six-cell promotion evidence.
- Updated README, architecture, hooks, tech stack, coding standards, the root
  changelog, and the Pi changelog with four-sibling/three-host vocabulary and
  source-backed boundaries.
- Added canonical `core/surface/includes/pi-host-notes.md`, generated only into
  `plugins/ca-pi/`, and corrected the Pi orchestrator command/host-note branch.
- Extended plugin-reference checking to `ca-pi` and license consistency to the
  nested and generated root Pi manifests. Added `AGPL-3.0-only` to both through
  the package generator.
- Module identity is documented as self-consistency with the operator-launched
  Pi runtime, not publisher authenticity. The canonical `pi list` and
  `pi config` origin checks are documented beside it.
- `--farm` remains `preview`. The current Pi path uses the shared checked-in
  backend. npm packaging and a Pi-native embedded farm worker remain future
  spikes, not current dependencies.

## H-18 governed handoff

The attempted prose-only `apply_patch` to `.codearbiter/CONTEXT.md` was blocked:

```text
BLOCKED [H-18]: This patch operation edits or deletes .codearbiter/CONTEXT.md
(#159) — the activation switch every enforcement hook reads — and its resulting
frontmatter cannot be verified from patch hunks. Failing closed; use the
sanctioned init path (or $ca-override).
```

The current LF-encoded frontmatter is 34 bytes, including the LF after the
closing delimiter:

```text
---
arbiter: enabled
stage: 2
---
```

SHA-256 before the intended prose edit:
`519c223415be8cd907ca2d696f56314996b8aa46170d029ff6bbbef2fe7b8bcd`.
The intended diff does not touch those bytes. The governed writer must recompute
the hash after the write and require the same value before accepting it.

Root resolution: after the six reviewed prose replacements, the frontmatter was
still 34 LF bytes with SHA-256
`519c223415be8cd907ca2d696f56314996b8aa46170d029ff6bbbef2fe7b8bcd`.

### Exact intended `CONTEXT.md` prose patch

```diff
@@
-The orchestration framework itself, plus siblings. This repo is a
-**marketplace of three plugins** (ADR-0007, ADR-0011): `ca`, the governance/orchestration
-plugin for Claude Code; `ca-codex`, the same governance kernel for Codex CLI (beta until
-live-Codex verification, ADR-0011); and `ca-sandbox`, an infrastructure plugin. This `.codearbiter/` directory is the v2
+The orchestration framework itself, plus siblings. This repo contains
+**four sibling plugins** (ADR-0007, ADR-0011, ADR-0013): `ca`, the governance/orchestration
+plugin for Claude Code; `ca-codex`, the same governance kernel for Codex CLI;
+`ca-pi`, the same kernel for Pi; and `ca-sandbox`, an infrastructure plugin. The
+first three are the **three governance hosts**. This `.codearbiter/` directory is the v2
@@
-Sibling plugins in one marketplace (ADR-0007, ADR-0011):
+Four sibling plugins in one repository (ADR-0007, ADR-0011, ADR-0013):
@@
 - **`ca-codex` (governance, Codex CLI host)** — the same kernel targeting Codex CLI.
@@
   verification (ADR-0011).
+- **`ca-pi` (governance, Pi host)** — the same generated kernel behind a thin
+  TypeScript extension and the shared stdlib-only Python core. The Git-installed
+  package is independently versioned, requires Node 22.19+ and Python 3, and
+  shares the project's `.codearbiter/` store with Claude Code and Codex CLI.
@@
-  (markdown templates), materialized into `plugins/ca/` and `plugins/ca-codex/` by
+  (markdown templates), materialized into `plugins/ca/`, `plugins/ca-codex/`, and
+  `plugins/ca-pi/` by
@@
 - `ca-codex` host adapter: `plugins/ca-codex/` — `.codex-plugin/` manifest, hook shims,
   generated skills/agents payloads.
+- `ca-pi` host adapter: `plugins/ca-pi/` — Git package metadata, generated policy
+  payloads, thin Python host shim, TypeScript extension sources, and built parent,
+  child, and Windows containment artifacts.
@@
-Not an enterprise compliance suite. Hosts are Claude Code and Codex CLI only; further
-hosts require a new ADR. Solo developer. `ca-sandbox` (ADR-0007) and `ca-codex`
-(ADR-0011) are deliberate, recorded exceptions, not precedent for arbitrary co-location.
+Not an enterprise compliance suite. Governance hosts are Claude Code, Codex CLI,
+and Pi; further hosts require a new ADR. Solo developer. `ca-sandbox` (ADR-0007),
+`ca-codex` (ADR-0011), and `ca-pi` (ADR-0013) are deliberate, recorded exceptions,
+not precedent for arbitrary co-location.
```

## Fresh verification

Green in the author's final run:

- plugin reference graph: `ca`, `ca-codex`, and `ca-pi` all intact;
- license declarations: live repository consistent; unit suite 23/23;
- `tools/build-surface.py --check`: Claude, Codex, and Pi synchronized;
- `tools/build-host-packages.py --check`: root/nested Pi metadata synchronized;
- `.github/scripts/test_pi_package.py`: 21/21;
- public Pi docs: 10/10 after the governed `CONTEXT.md` write.

The broader descriptor suite remains 9/13 during the sprint because its
Task-1-era independent oracle has not yet admitted the Task 6-10 non-policy Pi
files and has not learned the Pi-only role-frontmatter stripping rule. Those
four known failures predate this docs slice; Task 14 must close them rather than
mistaking this report for a full repository gate.

## Release to Tasks 13 and 14

`docs/pi-parity-testing.md` is ready for Task 13's committed six-cell evidence
procedure. Task 13 may add only completed,
sanitized promotion links/results to `docs/parity.md`; it must keep the latest
canary separate and nonblocking. Task 14 must rerun the public docs, generation,
reference, license, package, descriptor, and full repository gates.
