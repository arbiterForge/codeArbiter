# Spike A — deps/source layering (CONFIRM-06)

Status: RESOLVED. Spike executed and independently verified. Confidence: high (5/5) for
Node/Python (directly observed); go/rust inferred from the same docker-generic mechanism.

## Falsifiable question

When a nixpacks image bakes dependencies into the app dir (`/work/repo`) and we then mount the
live source named volume over that same dir, do the baked deps (`node_modules` / `site-packages`)
get shadowed and disappear? And which fix keeps **both** baked deps resolvable **and** source
live-editable in place — on Node **and** Python?

## What was empirically observed

Environment: Docker 29.5.3, Linux engine (OSType linux) on WSL2. nixpacks NOT installed
(`nixpacks: command not found`), so hand-written Dockerfiles mimicked what nixpacks bakes —
the shadowing is docker-generic volume-over-dir semantics, not nixpacks-specific.

**Shadowing is real and total, both runtimes.** With deps installed INTO `/work/repo` and a
source-only named volume mounted over it:

- Node: `docker run --rm -v ca-sbx-spike-vol-node:/work/repo ca-sbx-spike-node-naive`
  -> `Error: Cannot find module 'lodash'`, `code: 'MODULE_NOT_FOUND'`, RC=1;
  `ls /work/repo/node_modules` -> `No such file or directory`.
- Python: same shape -> `ModuleNotFoundError: No module named 'requests'`, RC=1.
- Negative control (no volume): Node prints `NODE_OK lodash.chunk=[[1,2],[3,4]]`, Python prints
  `PY_OK requests.__version__=2.31.0`, RC=0 — deps fine when not shadowed.

**All three candidate fixes resolve deps with the live volume mounted; only (a)/(b) keep source
live-editable in place:**

- (a) deps OUTSIDE the mount at `/deps` + `NODE_PATH=/deps/node_modules` /
  `PYTHONPATH=/deps/site-packages`, source via volume at `/work/repo` -> Node `NODE_OK`,
  Python `PY_OK`, RC=0 both.
- (b) deps-only base image (deps baked at `/deps`, not under `/work/repo`), source layered via the
  volume -> identical pass. Structurally the same family as (a): the discriminator is the install
  path, not the Dockerfile stage.
- (c) bake source+deps at `/work/repo`, mount the edit volume at a NON-shadowing subpath
  (`/work/edits`) -> `NODE_OK`, baked `node_modules` PRESENT, `/work/edits` writable, RC=0 — **but
  the source is baked read-only and is NOT live-editable in place** (needs `--refresh`/rebuild).

**Critical editability check (the half that makes the tool usable):** with fix (a), edited
`index.js` / `main.py` IN the volume and re-ran -> `EDITED_LIVE chunk=[[9,8],[7,6]]` and
`PY_EDITED_LIVE v=2.31.0`, deps still resolved, RC=0 both. So fix (a) gives BOTH live-editable
source AND surviving deps.

## Verifier's verdict

Confirmed. The verifier rebuilt the load-bearing trio (shadow + fix(a) + editability) from scratch
on an independently authored Dockerfile/volume set (prefix `ca-sbx-spike-verify-`) and reproduced
every observation exactly: shadow -> `MODULE_NOT_FOUND` RC=1; fix(a) with the same source-only
volume -> `NODE_OK` RC=0; edited-in-volume -> `EDITED_LIVE` RC=0. Tried to refute and could not.
The mechanism being docker-generic means the absence of nixpacks does not weaken it.

## Resolution / recommendation

Adopt **fix (a)/(b): install deps to a path OUTSIDE the volume mount point**.

- Node: build image installs to `/deps` (`WORKDIR /deps; COPY package.json; npm install;
  ENV NODE_PATH=/deps/node_modules`). `WORKDIR /work/repo`.
- Python: `pip install --target=/deps/site-packages; ENV PYTHONPATH=/deps/site-packages`.
- go/rust (inferred): `GOPATH`/`GOMODCACHE` outside the mount; `CARGO_HOME` + a target dir outside
  `/work/repo`.
- At run time mount the live source volume **only** at `/work/repo`
  (`--mount type=volume,source=ca-sbx-vol-<id>,target=/work/repo`). Because deps live at `/deps`
  and the volume covers `/work/repo`, the mount never shadows deps and source stays editable.

This is the only candidate satisfying BOTH halves of the invariant: deps survive AND source is
live-editable in place. Keep fix (c) as the documented `baked + --refresh` fallback with the loud
caveat that it is not live-editable in place.

**Dephash alignment:** deps resolve from the BUILD-TIME manifest baked into `/deps`. Editing
`package.json`/`requirements.txt` in the volume does NOT live-install new deps — exactly the spec's
model: a manifest/lockfile change bumps the dephash and triggers a rebuild; source-only edits do
not. Fix (a) aligns cleanly with criteria 4/5.

## Architecture impact

The plan/spec's default lifecycle is "mount the live repo volume over the app dir" (risk #1, plan
lines 82-92 and 164-168). That naive layout is the one that fails. **The architecture must adopt
the out-of-tree deps layout:** the build stage installs deps to `/deps` and exports
`NODE_PATH`/`PYTHONPATH` (and the go/rust equivalents) via image `ENV`; the run stage mounts the
source volume only at `/work/repo`. Spec risk #1 and the design lifecycle should be updated to say
"deps baked to `/deps` (out of tree), source volume at `/work/repo`" rather than "volume over the
app dir."

**One open nixpacks-integration wrinkle** (not blocking the architecture decision): nixpacks bakes
deps+source into the app dir by default, so wiring nixpacks in will require either a post-build
relocation (move `node_modules`/`.venv` to `/deps`, export `NODE_PATH`/`PYTHONPATH` via image ENV)
OR a nixpacks config/phase override targeting an out-of-tree dep dir. Nail this down when nixpacks
is actually wired.

**Driver note (from both runs):** `docker build --label` does NOT reliably attach the label to the
resulting image — the driver should track/discover sandbox images by namespaced repo **tag**, not
image label. On Windows + Git Bash, `MSYS_NO_PATHCONV=1` is needed for in-container paths passed to
`docker run`/`ls` (the TS driver shelling docker is the relevant surface).
