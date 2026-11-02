---
entity: skills/crypto-compliance
related: [secret-handling, commit-gate]
runs_inside: "The commit check (`/ca:commit`), which routes any staged change that touches hashing, signing, encryption, key derivation, secure randomness or TLS through it."
produces: "A pass or a block for the change. A clean pass is recorded so the commit check will accept a crypto-touching change, and any finding blocks it."
gates:
  - gate: banned-primitive scan
    when: any change touches hashing, signing, encryption, key derivation, security-relevant randomness, or TLS configuration
    effect: broken algorithms, disabled certificate verification, home-rolled crypto, or anything off the project's approved list blocks the change
---

## What it does

This is the check that stands between the codebase and a weak cryptographic choice. It runs
whenever changed code hashes, signs, encrypts, derives keys, generates security-relevant random
values, configures TLS, or pulls in a crypto library — most often dispatched from inside the
commit gate or the test-first gate rather than invoked directly. A dedicated reviewer agent
confirms every finding against the project's documented security controls.

## Phases

1. Scan every cryptographic operation in the change against the project's approved-primitive
   policy, rejecting broken algorithms, disabled certificate verification, and hand-built crypto
   outright, and dispatching a reviewer to confirm the findings.

## Exits

A clean pass records a gate marker that the commit gate later checks for before it will let a
crypto-touching change through. Any finding blocks the change outright — there is no partial
pass, and the marker is never recorded on a failing scan.
