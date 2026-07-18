# Pi install and parity-testing runbook

This runbook covers the Git-only `ca-pi` distribution and the evidence needed
to promote a commit. Pi 0.80.5 is the minimum supported host and Pi 0.80.10 is
the latest verified host in this release line. Node 22.19 or newer and Python 3
on `PATH` are required.

Task 12 documents the repeatable procedure. A local green run is not the final
promotion record: the committed Windows, macOS, and Linux cells for both
supported Pi versions are bound to the commit in the later promotion report.

## Install from a pinned Git tag

Use a release tag, never a moving branch:

```sh
pi install git:arbiterForge/codeArbiter@ca-pi-v<version>
pi list
pi config
```

For the initial release, `<version>` is `0.1.0`. `pi list` must show the pinned
Git source. In `pi config`, confirm that the package contributes one parent
extension and the generated `ca-*` skills. Use `-l` only when you deliberately
want a project-local Pi setting.

There is no npm release. npm packaging is a future spike, so package-manager
examples that name an npm source do not install `ca-pi` today.

The generated public catalog counts are:

- `ca: 39` Claude Code commands
- `ca-codex: 37` Codex CLI entry skills
- `ca-pi: 38` Pi entry skills

The source catalogs are [Claude](../plugins/ca/COMMANDS.md),
[Codex](../plugins/ca-codex/COMMANDS.md), and
[Pi](../plugins/ca-pi/COMMANDS.md).

## Establish an isolated test boundary

Start with an isolated home and a disposable enabled repository. Do not point
the harness at the operator's normal Pi configuration or authentication files.
The repository scripts create a dummy local provider and keep the deterministic
pass offline; no provider request or model spend is needed.

On PowerShell:

```powershell
$env:PI_CODING_AGENT_DIR = Join-Path $env:TEMP "ca-pi-evidence-home"
python .github/scripts/test_pi_platform_contract.py --fixtures-only
```

The fixture aggregate covers UTF-8 paths, LF and CRLF protocol framing,
generated package discovery, bridge/tool enforcement, child cancellation,
process cleanup, compaction, prune parity, and the relative benchmark. It must
finish without reading the real Pi home.

For a supported-version run, install the exact external Pi version with install
scripts disabled in the isolated environment, then run one of:

```sh
python .github/scripts/test_pi_platform_contract.py --pi-version 0.80.5
python .github/scripts/test_pi_platform_contract.py --pi-version 0.80.10
```

CI repeats those commands across Windows, macOS, and Linux. A separately
reported `latest` canary is nonblocking and never changes the supported floor or
ceiling by itself.

## Trusted live pass

Only after inspecting the disposable repository, grant Pi project trust for
that repository and start a new session. Keep the normal home isolated even for
a local opt-in credentialed pass. The evidence artifact contains result codes and timings only:
no prompts, task text, repository content, environment values,
provider responses, raw JSONL, stderr, credentials, or user-home paths.

Verify each observable surface:

1. **Package origin:** `pi list` names the pinned Git source; `pi config` shows
   only the expected parent extension and generated skills.
2. **Project trust:** an enabled but untrusted repository stays inert. After an
   affirmative trust decision and restart, repository-aware startup may run.
3. **Activation:** `/ca-doctor` reports the active `ca-pi` version and package
   path, Python/core/bridge health, command ownership, child fingerprint, and
   supported expansion fingerprints.
4. **Aliases:** invoke `/ca-init` and `/ca-doctor`; repeat one command through
   `/skill:ca-init` to prove the native fallback loads the skill body.
5. **Final mutation:** exercise the H-03 dry-run probe and the H-05/H-20
   fixtures. The final arguments reaching Pi's mutators must remain governed.
6. **Subagents:** exercise single, chain, and parallel dispatch. Confirm bounded
   results, distinct child PIDs, exact role tools, and no recursive dispatch.
7. **Cancellation:** cancel and time out a child with descendants; the process
   tree must be gone before the result returns.
8. **Status:** the extension-owned status key appears for an enabled trusted
   repository and clears at shutdown; it does not replace Pi's full footer.
9. **Compaction:** run `/ca-prune status`, a dry selection, and native
   compaction. The active Pi session must not be rewritten directly.
10. **Farm preview:** invoke `/ca-sprint --farm` only as an opted-in preview.
    Confirm that Pi resolves the shared checked-in farm backend and degrades
    visibly if it is missing or stale.
11. **Shared-state continuity:** write concurrent Claude/Pi, Codex/Pi, and Pi/Pi
    audit events in the fixture and require parseable `HOST: pi` attribution.
12. **Uninstall:** run `pi remove git:arbiterForge/codeArbiter@ca-pi-v<version>`
    (or the equivalent `pi uninstall` alias), confirm removal with `pi list`,
    and verify that the repository-owned `.codearbiter/` store remains.

## Read the doctor result correctly

The canonical origin diagnostic reports the active Pi CLI entry, imported
module, package root, and reported version. Its module-identity row proves
self-consistency with the operator-launched Pi runtime; it is not publisher
authenticity. Verify provenance from the pinned Git source, tag, and commit in
addition to checking `pi list` and `pi config`.

The `active-dispatch` doctor row remains a documented degradation on the
supported public extension API: the deterministic wrapper self-test cannot be
submitted through the active dispatcher. Promotion closes that gap with the
separate live dispatch evidence rather than overstating what doctor proved.

## Release and future work

`ca-pi` has independent SemVer. Tags use `ca-pi-v*`; the nested
`plugins/ca-pi/package.json`, generated root `package.json`, and
`plugins/ca-pi/CHANGELOG.md` must advance together. There is no npm release in
this release line.

Two ideas remain non-shipping future spikes: npm packaging, and a Pi-native
embedded farm worker built on the hardened child runner while retaining the
shared plan/result contract. The embedded farm worker future spike does not
change the current `--farm` preview route or add a second engine.
