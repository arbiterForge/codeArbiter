---
name: sandbox-lifecycle
description: Create, inspect and explicitly destroy a Docker sandbox for an untrusted network repository. Runtime isolation uses named volumes, no host binds or socket, non-root, read-only root and offline networking. Shell exit detaches; named destroy and explicit prune have different scopes.
---

# sandbox-lifecycle

Use the packaged `${CLAUDE_PLUGIN_ROOT}/tools/sandbox.js` driver. The following workflow is agent guidance; the binary enforces URL validation, mount rejection, runtime hardening and scoped teardown. Reading this skill does not create an additional binary approval gate. Consumer projects do not need the maintainer's spike notes, decision files or source checkout. Do not create a consumer ADR to satisfy a missing maintainer reference.

## Pre-flight

Establish the repository URL and requested network policy. Supported sources are HTTPS, SSH and scp-style network remotes; local paths and transport helpers are refused. `docker info` must succeed before cloning. A failed observation is unavailable, not an empty registry.

Docker and Node 20.6+ are prerequisites. Probe an already installed nixpacks on the host, or its existing WSL bridge on Windows. The driver never installs a host builder. Missing nixpacks selects the packaged Dockerfile fallback for Node/Python; report that effective builder instead of stopping a supported fallback build. Unsupported stacks need a usable nixpacks; do not describe the Node/Python fallback as successful Go/Rust dependency support.

Ordinary sandbox runtime is offline. `offline` is the default; requests named `clone-then-cut` or `allowlist` currently also resolve to offline runtime because the ordinary runner has no networked policy enabled. Report requested and effective policy separately. The experimental network-plan helper is not an integrated ordinary-create allowlist. Never claim that requesting an allowlist enables it, or expand network access to make a failed command work.

`--with-claude` is a separate routine using `tools/claude-inside.js` and the sibling `sandbox-claude-inside` skill. Ordinary `sandbox create` has no such flag.

## Create

Run `node <plugin>/tools/sandbox.js create <url> [--net offline|clone-then-cut|allowlist]` under the user's authorization. Clone uses a temporary networked helper and a labeled Docker named volume at `/work/repo`. Clone/build may access registries; offline describes exploration runtime, not an air-gapped build.

The builder copies the checkout from that volume into a temporary host build-context directory. This staging directory exists during manifest inspection and image build and is removed in an owned finally path. A cleanup failure retains the exact directory/helper identity in the error. Source therefore reaches host staging; the running sandbox is given no host bind mount or Docker socket.

V2 cache tags are `ca-sbx:v2-<sha256>`. The identity includes dependency manifest/lockfile bytes, the effective builder and its observed version, target Docker platform and generated build templates/options. Temporary checkout basenames have no identity role. Reuse requires the cache-key label and an immutable image ID; existence alone is insufficient. Malformed toolchain/platform observations cannot authorize reuse. Old cache tags are left intact.

Dependencies live out of tree at `/deps`, with `NODE_PATH` and `PYTHONPATH`; the live source volume mounts at `/work/repo`. Runtime flags prohibit host binds, the Docker socket and privileged mode, and require non-root, dropped capabilities, read-only root, no-new-privileges and resource limits. These are driver-enforced controls; workflow prose is guidance.

Create returns exact sandbox/container/volume identities, builder notes, and requested/effective network policy. On failure, compensation has its own bounded observation budget independent of cancellation. Report verified absence or unknown cleanup with retained references; a killed Docker client does not establish that a container stopped.

## Interact

- `sandbox shell <id>` attaches to the named box. Shell exit detaches and leaves its container/volume running.
- `sandbox exec <id> -- <command> [args...]` returns command exit, captured output and truncation. Timeout, cancellation or raw output overflow also initiate exact-container stop and inspection. Process exit and containment are independent; unknown containment retains the target for inspection.
- `sandbox cp <id>:<container-path> <host-destination>` copies out only at host request. Do not add host binds or credentials as a convenience.

## Explicit teardown

`sandbox destroy <id> [--keep-volume]` targets that sandbox only. It removes labeled containers, then their volume; keep-volume preserves the requested source volume. Detaching a shell never performs destroy.

`sandbox prune` is a separate broad operation over the initially discovered plugin-labeled targets. Run it only when broad prune was requested. A named destroy must never automatically become prune. Other sandboxes and targets created after the prune snapshot remain intact. Missing target IDs are errors; no-ID destroy does not mean prune.

Report removed, deliberately kept, remaining and unknown resources separately. A removal/listing/verification failure is incomplete teardown with a nonzero CLI exit, not an empty successful scope. Cached images are retained, including old cache versions. Inspection and receipt repair do not authorize starting another sandbox or deleting unrelated resources.
