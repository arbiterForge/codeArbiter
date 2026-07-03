---
entity: skills/secret-handling
related: [crypto-compliance, commit-gate]
gates:
  - gate: approved source
    when: any secret-bearing value is introduced
    effect: it must originate from the project's approved secret store; a hardcoded literal, a plain environment variable, or an unlisted store all block
  - gate: sink and persistence check
    when: after sourcing
    effect: a secret reaching a logger, an error response, telemetry, an LLM prompt, or any storage outside the approved reference format blocks, as does one that outlives its request
---

## What it does

This is the check for any changed code that reads, writes, generates, stores, or passes a secret
— an API key, token, password, connection string, signing key, or certificate. It is dispatched
rather than invoked directly, most often from inside the commit gate, and treats anything of
uncertain secret status as a secret. A dedicated reviewer agent confirms every finding against the
project's documented security controls.

## Phases

1. Identify every secret-bearing candidate in the changed code and record where it comes from and
   everywhere it flows.
2. Confirm each one originates from the approved store through the approved access method, and
   dispatch a reviewer to confirm the sink findings.

## Exits

A clean pass records a gate marker the commit gate checks for before allowing a secret-touching
change through. Any BLOCK — an unapproved source, a prohibited sink, or a secret persisting past
its request — stops the change outright, and the marker is never recorded on that failing run.
