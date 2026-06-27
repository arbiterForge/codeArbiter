---
title: ADRs and the Decision Log
description: "How architecturally significant choices are captured as numbered, dated, user-attributed Architecture Decision Records with supersede chains and decision-health reporting."
---

Architecturally significant choices are written down as **Architecture Decision Records**:
numbered, dated, and attributed to the user who made them, stored under the project's
decision log. codeArbiter never authors an ADR as its own judgment; every record carries
explicit user attribution. The decision-lifecycle skill maintains supersede chains, so a
newer ADR can replace an older one, and it can report decision health: which records are
aging, unchallenged, or in conflict.
