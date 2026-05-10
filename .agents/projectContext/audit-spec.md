<!--PLACEHOLDER-->
<!-- Populated by decompose/context-creation skill. -->

# Audit Specification

## Auditable Event Set

_List every action that must produce an audit event._

| Action | Trigger | Required Fields | Notes |
|---|---|---|---|
| _action name_ | _what triggers it_ | _fields_ | |

## Required Always-Present Fields

_Fields that must appear on every audit event._

| Field | Type | Notes |
|---|---|---|

## Audit Event Sink

_Where audit events are sent (e.g., a logging service, a database table, an external sink)._

## Emit Function

_The canonical function/module to call for emitting audit events._

## Fail-Closed Policy

_What happens when an audit emit fails (fire-and-forget vs. fail the request)._

## Test Obligation

_How audit event emission must be tested._
