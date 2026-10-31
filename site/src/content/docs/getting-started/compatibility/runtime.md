---
title: "Git Runtime and Dependencies"
description: "Which Git layouts and runtimes codeArbiter supports, the ADR lifecycle Git prerequisite, structured HTML workflow prerequisites, and third-party dependencies."
journey:
  level: "Reference"
  time: "Lookup"
  outcome: "Check a Git layout, runtime or dependency question against the supported boundary."
  prerequisites: []
  proof: "Your checkout layout, Git binary and runtime fall inside a supported row."
---

Detail behind the [Compatibility](/getting-started/compatibility/) requirements matrix: Git layouts
and runtimes, the structured HTML workflow, and what codeArbiter depends on.

## Git Runtime Boundary

Hook registration and linked-worktree metadata are supported when one native runtime owns the
checkout and continues to use it with that runtime's Git, Python, and hook shell.

| Repository use | Status | Evidence and boundary |
|---|---|---|
| Windows checkout and linked worktrees created and used by Git for Windows | Supported with Git's default worktree layout | Actual Git for Windows tests resolve and execute managed hooks from both the primary checkout and a linked worktree. Both native absolute and native relative worktree-admin pointers resolve to the primary marker root. Git for Windows' bundled `sh.exe` is the hook shell. A live Git 2.55.0 probe also resolved a primary and linked worktree through a localhost UNC share after that path was explicitly trusted by Git's `safe.directory` policy; without Git trust, resolution fails closed. This is not a general claim for every remote SMB server. |
| Linux checkout and linked worktrees created and used by native Linux Git | Supported with Git's default worktree layout | The hook suite runs on the Ubuntu CI cell. Paths and registry entries remain in one native dialect. |
| macOS checkout and linked worktrees created and used by native macOS Git | Supported with Git's default worktree layout | The hook suite runs on the macOS CI cell. Paths and registry entries remain in one native dialect. |
| WSL-owned checkout and worktrees used only by WSL | Not separately verified | This resembles the native Linux cell, but WSL is not a named, proven product cell yet. Do not promote that inference to a support claim without WSL-specific end-to-end evidence. |
| One physical repository or shared `.git` alternated between Windows Git and WSL Git | Unsupported | Registry paths, generated shell paths, and trusted executable identities use one runtime's path dialect. codeArbiter does not translate or maintain parallel runtime identities. |
| Windows-created linked worktree used through WSL, or the reverse | Unsupported | Foreign `.git` pointer paths are rejected rather than treated as relative local paths. In the directly tested Windows-to-WSL direction, WSL Git itself rejects the foreign worktree metadata before codeArbiter runs. |
| Linked worktree backed by `git init --separate-git-dir` | Unsupported | Git can resolve this layout, but it may not retain the user-supplied primary as the main worktree. codeArbiter escalates only when both the linked checkout and Git's reported main candidate own real `CONTEXT.md` files that independently satisfy the canonical activation parser; ordinary separate storage lacks that identity and marker writes stay local. A storage directory deliberately carrying its own enabled identity is inside the local-filesystem trust boundary, not a promoted support cell. |

`core.hooksPath` follows the selected Git binary, not a codeArbiter-specific subset. Doctor checks
the effective directory reported by that binary, requires both current executable managed shims
there, requires at least one live registered enforcer, and asks Git to run the managed `pre-push`
shim with empty input before reporting the backstop healthy.

### ADR lifecycle prerequisite

On Claude Code, Codex, and Pi, ADR lifecycle verification and its merge-method preflight require
Git %%fact=git.adrMinimum%%+ with `--no-lazy-fetch`. [Git 2.45 introduced this option](https://github.com/git/git/blob/v2.45.0/Documentation/RelNotes/2.45.0.txt)
to prevent implicit object retrieval from promisor remotes. This repository's CI lifecycle checker
uses the same requirement. It does not change the unrelated hook-registration paths above.

Every proof read retains the flag. If a read fails, the verifier checks the same selected
executable with `git --no-lazy-fetch --version`, without reading a repository. An unavailable
capability produces an upgrade prerequisite instead of a misleading invalid-ref error; a supported
Git's ordinary ref or object failure remains a proof failure. Enforcement checks the actual flag
capability, not a parsed version string, and never retries a proof read without the protection.
Missing committed objects still block verification: the verifier neither fetches them nor
substitutes current working-tree bytes.

## Structured HTML Workflow Prerequisites

New full feature and sprint work requires both the installation-pinned native
artifact helper and the installed host's production authority adapters. A native
engine capability is not a complete host-workflow qualification.

Claude Code and Codex have production approval, prerequisite, verification and
review adapters. Their required installed resources and hook registrations are
checked before HTML authoring. Missing or malformed resources produce
`HOST_WORKFLOW_UNAVAILABLE` before a new specification or plan is written.
Repair the package using the supported installation instructions rather than
copying files into its cache.

Pi lacks the production authority chain for this HTML path and stops at admission.
Existing Markdown pairs and the inline small feature lane remain on their existing
paths. Do not create a Markdown fallback for a new full-lane request.

The resource preflight does not establish enabled/trusted hooks or live host
behavior. Exact-version installed-host qualification and every actual approval,
verification and review gate remain required. See the
[artifact workflow contract](https://github.com/arbiterForge/codeArbiter/blob/main/core/surface/includes/artifacts.md)
for the current boundaries.

## Third-Party Dependencies

The Python hook core imports only the Python standard library. It requires no `pip install` or
third-party Python packages (ADR-0004).

Structured HTML workflows also execute the installation-pinned `ca-artifact` native binary,
built with Go. The bridge verifies its packaged manifest, native-platform qualification and
binary digest before execution. See the
[security policy](https://github.com/arbiterForge/codeArbiter/blob/main/SECURITY.md) and
[third-party notices](https://github.com/arbiterForge/codeArbiter/blob/main/THIRD_PARTY_NOTICES.md).

The farm dispatcher (`plugins/ca/tools/`) and Pi adapter (`plugins/ca-pi/tools/`) have their own
TypeScript build and test dependencies. Those packages do not add Python dependencies to the
enforcement hooks.

The docs site (`site/`) has its own, larger `package.json` (Astro, Starlight, vitest). That's a
dependency surface for **building this website**, never for using the plugin.
