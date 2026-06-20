# ca-sandbox — commands

The `ca-sandbox` plugin pulls an untrusted repo into a local, ephemeral, host-FS-isolated Docker box —
a Codespace equivalent you can explore and then burn. Every command is namespaced to the plugin —
invoke `/ca-sandbox:<name>`. It is a sibling of the `ca` governance plugin (ADR-0007), not part of it;
the two ship and version independently.

This table is the surface scan. A command body
(`${CLAUDE_PLUGIN_ROOT}/commands/<name>.md`) loads ONLY when that command is invoked — never bulk-read
the directory. Requires **Docker** and **nixpacks** on `PATH`.

## Lifecycle

| Command | Argument | Purpose |
|---|---|---|
| `/ca-sandbox:sandbox` | `"<repo url>" [--network …] [--with-claude] [--keep-volume]` | Create an isolated box: clone into a named volume, build a dep-cached image (`ca-sbx:<repo>-<dephash>`), run under structural isolation (no bind, no docker socket, never `--privileged`; cap-drop ALL, non-root, read-only root). Network defaults to `offline`. |
| `/ca-sandbox:sandbox-shell` | `"<id>"` | Open an interactive shell in a running box at `/work/repo`, as the non-root user on the read-only root. |
| `/ca-sandbox:sandbox-exec` | `"<id> -- <cmd>"` | Run one command in the box and capture a JSON result — `exitCode`, separate stdout/stderr, `truncated` past the byte cap. The scriptable seam. |
| `/ca-sandbox:sandbox-cp` | `"<id>:/work/<f> ./dest"` | Copy a file OUT to the host — host-initiated egress only (`docker cp`). A host→container bind is impossible by construction. |
| `/ca-sandbox:sandbox-destroy` | `["<id>"] [--keep-volume] [--prune]` | Tear the box down — remove container + named volume, leaving zero `ca.sandbox=1` objects. `--keep-volume` keeps the volume; `--prune` reclaims a leaked labeled object. Cached images retained. |

## The invariant

Every command upholds one load-bearing guarantee: **untrusted code in the box can never reach the host
filesystem.** It is enforced structurally — no host bind mount, no `/var/run/docker.sock` mount, never
`--privileged`, `--cap-drop ALL`, non-root user, read-only root — by the driver in
`${CLAUDE_PLUGIN_ROOT}/tools`, whose mount chokepoint (`${CLAUDE_PLUGIN_ROOT}/tools/mounts.ts`) throws
on any bind spec. Network defaults to `offline`; the IP allowlist is EXPERIMENTAL. File egress is
host-initiated `docker cp` out only. All five commands route to the `sandbox-lifecycle` skill
(`${CLAUDE_PLUGIN_ROOT}/skills/sandbox-lifecycle/SKILL.md`); `--with-claude` adds the hardened
`sandbox-claude-inside` routine (`${CLAUDE_PLUGIN_ROOT}/skills/sandbox-claude-inside/SKILL.md`).

## Glossary

- **box / sandbox** — one ephemeral, isolated Docker container holding a cloned repo at `/work/repo`.
- **`/deps`** — out-of-tree dependency dir baked into the image; the source volume mounts only at
  `/work/repo` so the mount never shadows deps (Spike A).
- **dephash** — the content hash of the dep manifest/lockfile set; an unchanged dephash is a cache hit
  (no rebuild), a manifest change forces a rebuild.
- **`ca.sandbox=1`** — the label every container and volume carries; teardown and `prune` find objects
  by it alone.
- **network policy** — `offline` (default), `clone-then-cut`, or `allowlist` (EXPERIMENTAL).
- **`--with-claude`** — run Claude Code inside the box under a hardened, offline-default token posture;
  the token volume is never co-mounted with an untrusted-code run.
