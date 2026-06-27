---
title: SMARTS
description: "The structured, multi-lens scoring rubric codeArbiter uses when weighing options during autonomous runs, with every verdict recorded in an append-only sprint log."
---

When codeArbiter must weigh options, and especially when `/ca:sprint` decides "as the user"
during an autonomous run, it doesn't pick on vibes. It runs a structured, multi-lens scoring
rubric called **SMARTS** and records the verdict: the options weighed, the lens scores, the
chosen option, and a confidence flag. Low-confidence calls are exactly what the user reviews
afterward. Nothing hides behind autonomy. Every auto-decision lands in an append-only sprint
log.
