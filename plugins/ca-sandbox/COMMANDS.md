# ca-sandbox — commands

The `ca-sandbox` plugin clones an untrusted network repository into a Docker named
volume, builds a dependency image and starts an isolated exploration container.
It is a sibling of the `ca` governance plugin (ADR-0007); they ship and version
independently. Every command is namespaced as `/ca-sandbox:<name>`.

This catalog is the surface scan. Load the invoked command body
(`${CLAUDE_PLUGIN_ROOT}/commands/<name>.md`) and its
[sandbox-lifecycle](skills/sandbox-lifecycle/SKILL.md) instructions when needed;
do not bulk-read the command directory.

Docker and Node 20.6+ are required. An already installed Nixpacks, including the
existing Windows/WSL bridge, is optional. The driver never installs a host
builder implicitly. Missing Nixpacks selects the packaged Node/Python fallback;
the reviewed Nixpacks profile also supports Go with `go.mod` and bounded
non-workspace Rust with `Cargo.toml`. Custom Nixpacks configurations and Rust
manifests containing literal `workspace` or any backslash are refused. Report
the effective builder; fallback does not add Go/Rust support.

## Lifecycle

| Command | Argument | Purpose |
|---|---|---|
| `/ca-sandbox:sandbox` | `<repo url> [--net offline\|clone-then-cut\|allowlist]` | Clone into a named volume, inspect/build using temporary host staging, and start a structurally isolated box. Report requested and effective policy. |
| `/ca-sandbox:sandbox-shell` | `<id>` | Attach an interactive shell at `/work/repo` under the container's existing non-root, read-only-root isolation. Shell exit detaches and leaves the box running. |
| `/ca-sandbox:sandbox-exec` | `<id> -- <cmd> [args...]` | Run one command and report its real exit code, separate stdout/stderr, truncation and any independent containment outcome. |
| `/ca-sandbox:sandbox-cp` | `<id>:<container-path> <host-destination>` | Copy out at host request with `docker cp`; do not introduce a host bind or grant the container a writable host path. |
| `/ca-sandbox:sandbox-destroy` | `<id> [--keep-volume]` or explicit `--prune` request | Named destroy targets only that instance. A separately requested broad prune maps to the driver's `prune` subcommand and acts on its initial plugin-labeled snapshot. Cached images remain. |

The ordinary driver grammar is `sandbox.js create <url> [--net ...]`, `shell`,
`exec`, `cp`, `destroy <id> [--keep-volume]`, or `prune`. An omitted destroy ID is
an error. Neither `--network` nor `--with-claude` is an ordinary create flag.
Claude inside a token-only box uses the separate
[sandbox-claude-inside](skills/sandbox-claude-inside/SKILL.md) routine and
`tools/claude-inside.js`; do not implicitly launch it from ordinary create.

## Isolation, staging and network

The running exploration container has no host bind mount, Docker socket or
privileged mode. The driver uses named volumes/tmpfs, non-root execution,
`--cap-drop ALL`, a read-only root, `no-new-privileges` and resource limits.
[`mounts.ts`](tools/mounts.ts) is the mount constructor and rejects host binds.
Dependencies live at `/deps`; the live source volume mounts at `/work/repo`.

Build preparation temporarily copies source onto the host for manifest inspection
and image construction, then removes that owned staging directory. A failed or
unavailable cleanup must retain its exact references and be reported separately;
runtime no-host-bind isolation does not mean source never reaches host staging.

Ordinary runtime is offline for all currently accepted requested policy names:
`offline`, `clone-then-cut` and `allowlist`. Report that effective policy rather
than implying a richer request enabled egress. Clone/build can fetch remotely;
offline runtime is not an air-gapped build. Experimental network helpers are not
an integrated ordinary-create allowlist. Never widen network access to make a
failed command work.

## Cache and teardown

V2 cache tags are `ca-sbx:v2-<sha256>`. Identity includes the dependency-input
discriminator, effective builder and observed version, target platform and
material templates/options. Temporary checkout basenames have no identity role.
Reuse requires matching provenance and an observed immutable image ID; an equal
dependency hash or an existing tag alone is insufficient. Old cache tags remain
intact. Image pinning is not a reproducible Nix package-closure claim.

Shell exit detaches. Explicit named destroy removes only the selected labeled
container(s) and source volume; `--keep-volume` deliberately retains that volume.
Do not follow named destroy with automatic prune. Broad prune needs its own
requested scope, preserves unrelated/newly created instances, and retains cached
images. Report removed, kept, remaining and unknown resources separately. Failed
discovery/removal/verification is incomplete cleanup with nonzero exit, not proof
of an empty scope. Killing a Docker client alone does not prove its container
workload stopped.

## Glossary

- **box / sandbox** — one exploration container and its managed source volume.
- **`/deps`** — dependencies baked outside the live `/work/repo` source mount.
- **dephash** — the dependency-input discriminator used in cache identity; equality
  alone does not authorize image reuse.
- **`ca.sandbox=1`** — plugin ownership label used with the selected teardown scope;
  the label alone does not authorize a global sweep.
- **network policy** — requested name and effective capability are distinct;
  ordinary runtime currently remains offline.
- **Claude-inside** — a separate supported token-only routine with approved
  environment-token input, isolated home volume and no untrusted-source co-mount.
  Its machine-enforced guards and agent-guided phases are distinguished in the
  packaged skill; consumer projects need no maintainer spike files or new ADRs.
