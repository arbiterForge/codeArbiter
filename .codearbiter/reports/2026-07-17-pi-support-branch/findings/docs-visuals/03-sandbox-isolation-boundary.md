# 03 — Sandbox isolation posture is a dense prose paragraph with no boundary diagram

**Value:** Medium

**Page(s):** `site/src/content/docs/enforcement.md` (## Sandbox Isolation for Untrusted Repositories)

## What to depict

The section lists five hardening properties in one sentence: non-root (`--user
1000:1000`), `--read-only` root, `--cap-drop ALL`, `--security-opt no-new-privileges`,
and a fail-closed network policy (default `--network none`), plus "no host bind mounts,
the docker socket is never mounted." This is a textbook container security-boundary
diagram: a box (the sandbox container) with each restriction shown as a labeled barrier,
and the two explicitly-absent attack surfaces (host bind mounts, docker socket) shown as
crossed-out non-connections to the host.

This is a comprehension win, not decoration — the current form makes a reader parse a
run-on sentence to build the mental model that a diagram would give in one glance.
Medium rather than high value because this section is read less often than the landing
page or getting-started flow (it's deep in the enforcement page for a security-conscious
subset of readers), but for that audience it matters a lot.

## Recommended form

Technical security-boundary diagram (container isolation style: host box, container box
inside it, flags labeled on the boundary, an explicit "no path" marker for bind
mounts/docker socket).

## GPT image vs. hand-drawn

Hand-drawn SVG. This is a precise security claim (specific flags, specific denials) —
an AI-generated image risks looking authoritative while being technically imprecise
(e.g., implying a capability isn't dropped, or a mount exists that doesn't). Follow the
existing `gate-model.svg` house style.
