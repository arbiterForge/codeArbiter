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
