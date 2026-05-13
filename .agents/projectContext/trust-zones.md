<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-10
File: trust-zones.md
-->

<!--PLACEHOLDER-->
<!-- Populated by decompose/context-creation skill. -->

# Trust Zones

## Zone Definitions

_List each trust zone with its name, short description, and what it contains._

| Zone | Description | Contains |
|---|---|---|
| _Zone name_ | _What it is_ | _Components in this zone_ |

## Allowed Zone Crossings

_List every permitted crossing between zones._

| From | To | Direction | Protocol | Justification |
|---|---|---|---|---|

## Default-Deny Rule

All zone crossings not listed above are default-deny. Any code crossing an undeclared boundary
must go through `/threat-model` before implementation.

## Egress Allowlist

_Path to the egress allowlist file if one exists, or list permitted external destinations here._
