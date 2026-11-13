# ca-sandbox

A locally-hosted GitHub-Codespace equivalent for codeArbiter (ADR-0007). Pull a repo you're curious
about — including untrusted code — into an **ephemeral, isolated container**, explore or run it safely,
then tear it down. The cloned repo and all execution live inside the container; your host filesystem is
never mounted in.

This is an **infrastructure** plugin, a sibling to the `ca` governance plugin in the same marketplace.
It is independent of `ca`: CI is path-scoped and versions bump per-plugin.

## Requirements

Docker with a reachable daemon (`docker info`) and Node 20.6+ are required. An already installed nixpacks (host or existing Windows WSL bridge) is preferred. Both builders support Node/Python dependencies. The Nixpacks profile selects those providers explicitly, pins its base image and checks generated external image references. It refuses project `nixpacks.toml`/`nixpacks.json`, an existing `.nixpacks` output tree or `.ca-sandbox.nixpacks.Dockerfile` before generation, preserving those paths. Custom configurations and other provider stacks are unsupported. Without nixpacks the packaged Dockerfile fallback supports Node/Python dependencies. The driver never installs host tooling. Consumer projects need no maintainer spike notes or ADR files.

## Security model — the load-bearing invariant

Untrusted code in the box **cannot reach the host filesystem**. Enforced structurally:

- No bind mounts (the mount builder rejects any bind spec); the repo lives on a **named volume** at
  `/work/repo`, deps out-of-tree at `/deps`.
- No `/var/run/docker.sock` mount; never `--privileged`.
- `--cap-drop ALL`, `--security-opt no-new-privileges`, read-only root, non-root user, resource caps.

Getting work **out** is host-initiated only: `sandbox cp <id>:/work/<file> <hostDest>` (a `docker cp`
pull). The container is never given any path back into the host.

## Commands

```
sandbox create <url> [--net offline|clone-then-cut|allowlist]
sandbox shell <id> [--shell sh|bash]
sandbox exec <id> -- <cmd> [args...]
sandbox cp <id>:<containerPath> <hostDest>
sandbox destroy <id> [--keep-volume]
sandbox prune
```

State is label-only: the set of sandboxes IS the set of docker objects labeled `ca.sandbox=1`
(per-instance `ca.sandbox.id=<id>`). There is no JSON state file to drift.

> **Git Bash users:** a bare container path in `exec` (e.g. `exec <id> -- ls /work/repo`) is rewritten
> by MSYS path conversion *before* it reaches the CLI, becoming a Windows path. Wrap the command —
> `exec <id> -- sh -c 'ls /work/repo'` — or set `MSYS_NO_PATHCONV=1`. PowerShell and cmd are unaffected.

## Network policies and staging

Ordinary exploration runtime is **offline** (`--network none`). The accepted request names `clone-then-cut` and `allowlist` also currently resolve to offline; the experimental allowlist helper is not integrated into ordinary create. Results distinguish requested and effective policy. Clone/build helpers still fetch repositories and dependencies. Never expand network access incidentally.

The clone lives on a named volume. Build copies it into a temporary host build-context directory, removes that staging copy after use, and reports uncertain cleanup with its identity. The running sandbox has no host bind or socket; this does not mean source never touches host staging. Shell exit detaches; explicitly destroy the exact sandbox id when finished. Broad `sandbox prune` is separate and targets its discovery snapshot.

## Image caching

V2 cache tags are `ca-sbx:v2-<sha256>`, independent of the temporary checkout basename. The key includes manifest/lockfile content, effective builder/version, Docker target platform and build templates/options. Reuse verifies the cache-key label and immutable image ID. Old cache tags remain intact. Dependencies install at `/deps` with `NODE_PATH`/`PYTHONPATH` so the source volume at `/work/repo` does not shadow them.

## `--with-claude` (Claude Code inside the box)

Runs Claude Code inside the container, authenticated via an env-injected `CLAUDE_CODE_OAUTH_TOKEN`
(no host bind of `~/.claude`; session persisted on a named volume). **Caveat:** a token inside a box
running untrusted code is exfiltrable over any egress, so `--with-claude` defaults to offline /
Anthropic-domains-only and never co-mounts the token volume with an untrusted-code run.

## Development

The driver is TypeScript on Node 20, shipped as the built `tools/sandbox.js`.

```
cd tools
npm install
npm run typecheck
npm test          # docker-gated suites run serially (fileParallelism off)
npm run build     # rebuilds sandbox.js; the shipped artifact must be in sync
```

### Docker-required mode

Most of this suite spins real containers. Without a Docker daemon those suites
skip themselves, which is right on a laptop and wrong on CI: a green run that
exercised none of the container behaviour proves nothing about a driver whose
whole job is containing an **untrusted** repository. Two environment variables
make that explicit (issue #406):

| Variable | Effect |
| --- | --- |
| `CA_SANDBOX_REQUIRE_DOCKER=1` | An unavailable daemon **fails** the run instead of skipping. Set by the required CI job. |
| `CA_SANDBOX_DOCKER_SENTINEL=<path>` | Each real-container layer appends its name to `<path>` when it starts. |

CI sets both, then runs
`python .github/scripts/check_sandbox_docker_layers.py --sentinel <path>`, which
fails unless every layer the sources declare actually recorded a run. Locally,
leave both unset for the usual self-skipping behaviour.
