# Privacy Policy

**Effective date:** 2026-06-14

codeArbiter collects no personal data, sends no telemetry, and makes no network
calls in its default operation. There is no account, no tracking, and no server
operated by this project. Everything runs locally in your Claude Code session.

This document explains what the plugin stores, where it stores it, and the two
opt-in features that can transmit or record data.

## What the plugin stores, and where

All project state lives in a single `.codearbiter/` directory at the root of
**your** repository: stage, specs, plans, ADRs, the decision log, and the
append-only audit logs. These are plain files committed alongside your code.
They stay in your repository under your control and survive uninstalling the
plugin. This project never receives a copy of them.

The optional statusline writes one entry into your global
`~/.claude/settings.json`. It backs up whatever was there and restores it when
you remove the statusline. Nothing in that file leaves your machine.

Hooks run on your machine as part of normal operation. By design, **no hook
makes a network call.** They read and write the local files described above and
shell out to `git`. Nothing is transmitted off your machine.

## Opt-in features that touch data

Both features below are off by default. codeArbiter never enables either on your
behalf. Each is turned on only by an explicit environment variable or command
flag that you set.

### Pluggable execution farm (`/ca:sprint --farm`)

When you run a sprint with the `--farm` flag, the implementation step sends a
worker prompt to a third-party, OpenAI-compatible provider that **you** configure
and authenticate with `FARM_API_KEY`. What you send and to whom is your choice;
this project operates no endpoint and receives nothing.

The transmitted prompt contains the failing-test source and in-scope file context
for the task. Before transmission it is byte-capped (`FARM_ENRICH_MAX_BYTES`,
default 131072) and scanned to redact secrets. `FARM_API_KEY` is never committed
to the repository, written to an audit file, or placed in a prompt.

If you do not pass `--farm`, no prompt is ever sent to any provider.

### Live transcript pruning, dry mode (`CODEARBITER_PRUNE=dry`)

In `dry` mode the pruner writes one JSONL row per decision to a local file at
`~/.codearbiter/metrics/prune-dry.jsonl` (relocatable with
`CODEARBITER_PRUNE_METRICS`). Each row records only would-be reduction sizes,
per-strategy savings, and a validation verdict. It contains **no transcript
content.** The file is local. Nothing is uploaded.

If you choose to share that file to help promote the feature, you do so manually
by attaching it to a GitHub issue. That is your action, not the plugin's.

## Third parties

The only data flow to a third party is the execution farm above, and only when
you opt in and configure the provider yourself. Your use of that provider is
governed by that provider's own terms and privacy policy. Claude Code itself is
governed by Anthropic's terms and privacy policy.

## Changes

If this policy changes, the effective date above is updated and the change is
recorded in the repository history.

## Contact

Questions about this policy: open an issue at
<https://github.com/arbiterForge/codeArbiter/issues>.
