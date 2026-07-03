---
entity: skills/decompose
related: [commands/decompose, context-creation]
gates:
  - gate: layer completion
    when: within the six-layer interview
    effect: a layer never advances while an unresolved "later" item stands outside a recorded open question, and each completed layer is written to disk before the next one starts
  - gate: artifact approval
    when: after synthesis
    effect: you must explicitly approve all three architecture artifacts before any project document is populated
  - gate: initialization lock
    when: at the end
    effect: the project is not marked initialized while any draft decision record remains, or while the working draft directory still exists
---

## What it does

This is the greenfield counterpart to the brownfield back-fill: a structured interview for a
project with no source code yet. Invoked at startup on an empty project, or directly by the
decompose command, it walks you through six layers — vision, users and flows, functional scope,
technical shape, integrations, and risks — persisting every layer to disk as it closes so a lost
session never erases the earlier work, then turns the finished interview into the project's
foundational documents.

## Phases

1. Adopt the interview persona and state its rules of engagement.
2. Create or resume a durable draft directory that survives a session interruption.
3. Run the six-layer interview in order, writing each completed layer to disk immediately and
   drafting a decision record for every forced architectural trade-off as it's made.
4. Re-read every layer from disk and synthesize three architecture artifacts, then get your
   explicit approval on all three.
5. Re-read the approved artifacts and layers from disk, promote every draft decision to accepted,
   and populate the project's foundational documents.
6. Lock the project as initialized, remove the draft directory, and hand back to normal operation.

## Exits

A completed run leaves the project initialized with populated foundational documents, no draft
decision records outstanding, and the working draft directory removed — ready for feature work.
It never writes a project document before all six layers are solid on disk, and it never closes
while a draft directory or an unpromoted decision record remains.
