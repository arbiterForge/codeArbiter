# Privacy Policy

**Effective date:** 2026-09-06

codeArbiter provides governance adapters for Claude Code, Codex, and Pi. The
adapters run on your machine and use your coding host's session and tools.
There is no codeArbiter account, analytics service, or hosted governance service.
Normal startup can contact your Git remote and GitHub's public Releases API;
model-assisted work uses the host or provider you configure.

This document describes the current local storage and data flows, including the
separate `ca-sandbox` infrastructure plugin.

## What the plugin stores, and where

The three governance adapters share your repository's `.codearbiter/` directory
for stage, specs, plans, ADRs, tasks, decision records, reports, and audit logs.
These files can contain project descriptions, paths, findings, and evidence.
They can be committed alongside your code and survive uninstalling the plugin.
Workflows read relevant files into the coding host's context, so repository-owned
storage does not mean the contents can never reach that host's model provider.

Local state also exists outside that directory. Integration records live under
the repository's Git common directory. Backstop files are installed or refreshed
in Git's effective hooks directory, which can be elsewhere when `core.hooksPath`
is configured.
The user-global `~/.codearbiter/` directory holds the target-keyed
`update-state.json` cache, derived token/cost usage ledgers and session shards
(`ledger.json` for the Claude statusline and `pi-usage-ledger.json` for Pi), and
pruning state or metrics when those features run. The status displays read these
local accounting records.

The optional Claude Code statusline updates the statusline entry in
`~/.claude/settings.json`, with backup and removal handling. Coding hosts also
maintain their own settings, credentials, and session records outside the
repository. Removing a codeArbiter adapter does not remove those host records.

## Startup network activity

SessionStart can launch a detached `git fetch --quiet --no-tags` against your
configured remote. Git uses your configured transport and credential helpers.
The fetch does not write to the remote, but it can update local remote-tracking
refs and Git objects. The startup briefing uses the last completed fetch and
does not wait for this background process.

A separate detached update check makes unauthenticated HTTPS GET requests to
the public GitHub Releases API, at most once per day per independently versioned
adapter. It reads up to ten pages of release metadata and stores a target-keyed
result in `~/.codearbiter/update-state.json`. Its requests contain HTTP headers
and release-list parameters, not repository contents or provider credentials.
Network or parsing failures keep the previous result or produce no notice. The
check reports available versions; it does not install updates.

See [the hook reference](./docs/hooks.md) for the event-level read, write, and
network contract.

## Host and provider execution

Claude Code, Codex, and Pi handle the model requests and session data associated
with ordinary coding work. Their configured tools, extensions, and providers
can have additional data flows. Those calls do not require `--farm`.

For isolated Pi child work, `ca-pi` starts a temporary listener on `127.0.0.1`.
The child receives a per-child ephemeral token and provider configuration that
points to that listener. The parent broker authenticates the token and forwards
inference requests to the selected upstream provider using the operator's
credential. Task context therefore reaches that provider. The provider credential
stays in the parent; it is not copied into the child's environment or `auth.json`.

Child setup uses private temporary home, agent, and session roots, including a
restricted `models.json`. Task prompts enter through stdin. Cleanup closes the
broker and scrubs/removes the temporary configuration; a cleanup failure is
reported as degraded. This is cooperative process isolation, not an OS sandbox.
A same-user process that obtains the ephemeral token can use the broker while
that child is alive.

## Optional farm and pruning features

### Pluggable execution farm (`/ca:sprint --farm`)

When you run a sprint with the `--farm` flag, the implementation step sends a
worker prompt to a third-party, OpenAI-compatible provider that **you** configure
and authenticate with `FARM_API_KEY`. The project does not operate that provider
endpoint.

The transmitted prompt contains the failing-test source and in-scope file context
for the task. Injected file context is byte-capped (`FARM_ENRICH_MAX_BYTES`,
default 131072), secret-bearing filenames are excluded, and detected secret
patterns are redacted. The API key comes from the environment and is sent in
the provider authentication header. The farm is dormant without `--farm` and
its configured key; this does not disable ordinary host or Pi child inference.

Farm reports default to `.farm/`, with `FARM_REPORT_DIR` selecting another
report root. Each run keeps JSON and Markdown receipts, a `farm-results.jsonl`
stream, and per-task raw source patches under `runs/<runId>/`. Top-level reports,
the results stream, and `diffs/` are latest-run convenience mirrors. These local
artifacts can contain project content, plan metadata, and task results; source
patches are stored without redaction so they remain applicable. Run artifacts
are not automatically pruned. Review them before sharing or committing them.

### Live transcript pruning, dry mode (`CODEARBITER_PRUNE=dry`)

In `dry` mode the pruner writes one JSONL row per decision to a local file at
`~/.codearbiter/metrics/prune-dry.jsonl` (relocatable with
`CODEARBITER_PRUNE_METRICS`). Each row records a timestamp, session identifier,
mode, tier, would-be reduction sizes, per-strategy savings and metric scopes,
a validation verdict, and the validation-error count. It contains **no transcript
bodies**, but the session identifier can come from the host or transcript
filename. The file is local; the pruner does not upload it.

If you choose to share that file to help promote the feature, you do so manually
by attaching it to a GitHub issue. That is your action, not the plugin's.

Other pruning modes can create local transcript copies or backups and update
`~/.codearbiter/prune-state.json`. Pi uses its host-native compaction path;
the host's session and provider behavior still applies.

## Separate sandbox infrastructure

`ca-sandbox` stores sandbox source and container state in Docker named volumes
and labeled Docker objects. Builds also copy source from a volume into a host
temporary directory named `ca-sbx-checkout-*` and attempt to remove it afterward;
failed removal can leave that copy on the host. Creating a sandbox uses a
temporary networked clone container; image acquisition and builds can also
contact registries and package sources. The sandbox execution container defaults
to offline networking, with other network policies selected explicitly. An
offline execution policy does not make the preceding clone or image acquisition
offline.

The optional `--with-claude` mode passes `CLAUDE_CODE_OAUTH_TOKEN` into its Claude
container and can retain Claude session/credential state in a separate named
volume. It uses offline or the experimental Anthropic-only egress policy and
refuses to mount that credential volume alongside untrusted source. Its provider
calls and container storage are separate from the governance adapters' state.

## Third parties

Your coding host, selected model providers, Git remote, GitHub, and any services
used by a configured sandbox handle the requests they receive under their own
terms and privacy policies. Review their settings and policies for retention and
use of that data. Material you choose to publish in commits, pull requests, or
issues is shared through those services.

## Changes

If this policy changes, the effective date above is updated and the change is
recorded in the repository history.

## Contact

Questions about this policy: open an issue at
<https://github.com/arbiterForge/codeArbiter/issues>.
