# Command-route compatibility

A compatibility alias is an installed legacy route with a preferred canonical form. The legacy
route keeps its argument grammar, confirmation gates, side effects, durable outputs, and host
availability; its migration notice does not invoke or forward to another host command.

The registry permanently declares ca 2.17.0, ca-codex 0.9.0, and ca-pi 0.10.0 as the first-containing
candidates. Each payload's deprecation clock becomes effective only when GitHub's Release API confirms
an exact, non-draft Release for that candidate tag and the tag's commit contains both the matching
registry declaration and matching payload version.
A tag alone, a draft, unavailable API evidence, or any tag/Release/payload mismatch does not start a
clock. Published releases ca 2.16.0, ca-codex 0.8.0, and ca-pi 0.9.0 predate this registry and do not
contain the compatibility metadata. ca retains these routes through every 2.x release, with no removal
before a separately approved 3.0.0. ca-codex and ca-pi retain them through every later 0.x release,
with no removal before a separately approved 1.0.0. Passing a version floor never authorizes removal:
removal needs a new governed decision and fresh compatibility evidence.
## Explicitly retired capability: skill authoring

The maintainer explicitly approved removal of `new-skill` and `skill-author` on
2026-09-25 in PR #854. This one named exception supersedes the earlier
retain-every-route requirement for that workflow only. Its command, owning skill,
template and generated host entries are removed, not deprecated aliases. No
`extend skill` replacement or hidden callable routine is installed.

Requests to author or change repository resources use the applicable existing
change workflow and its authorization, verification and commit requirements.
CodeArbiter maintainers can read the format conventions in the source repository's
`core/surface/README.md`; that document is not an installed workflow.

This is an intentional command-compatibility break, not a claim that older
invocations continue to resolve. Existing installed older releases are unchanged.
The five other compatibility aliases and their publication clocks remain intact;
this retirement is not permission to remove any other entry.

## Reviewed single-owner entries

PR #854 composes `tribunal`, `threat-model`, `context-check`, `cleanup`, and `pr`
from their existing skill owners. These operations are retained, not retired or
renamed. Their explicit argument grammars, mode markers, compatibility clocks and
host availability remain unchanged. `status drift` and `pr --cleanup` reach the
same owners directly; PR watch mode retains its existing watcher resource.

The wrapper text is no longer an independent policy source. Drift and cleanup
retain their full operational body, and PR retains current acceptance/ancestry
preflight plus one shared opening procedure. Tests keep historical wrapper
fingerprints while checking these named migrations against the owning contracts.
This permission does not authorize an unrelated route removal or gate change.
