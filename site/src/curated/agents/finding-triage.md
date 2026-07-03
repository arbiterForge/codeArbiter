---
entity: agents/finding-triage
related: [skills/dispatching-parallel-agents, checkpoint-aggregator]
---

## Role

Post-processes every reviewer report from a checkpoint or review run: consolidates all findings and
classifies each as BLOCKS, DEFERRABLE, or NON_BLOCKING. It generates no findings of its own — it
unifies and classifies what the reviewer fleet already found. Runs sequentially after every reviewer
in the batch has reported, dispatched by `dispatching-parallel-agents`, and its output feeds
`checkpoint-aggregator`.

## Why this model tier

Ships `model: haiku`. Classifying an already-produced finding by severity and blocking status against
a fixed rule set is mechanical triage, not open-ended judgment.

## What it emits

A single unified triage report: one table row per finding under BLOCKS / DEFERRABLE / NON_BLOCKING,
with source reviewer, severity, description, and disposition, plus summary counts. Nothing is dropped
— every finding from every reviewer must appear.
