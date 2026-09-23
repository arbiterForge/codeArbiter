# 01: Architecture breakdown

Illustrative greenfield planning document for a saved-search application. Authored
for documentation, not captured from a completed decompose interview. No approval
or initialized repository is claimed.

## Boundaries and responsibilities

The application UI owns the search list and the empty-state explanation. A
saved-search repository owns persistent name/query records and their order. A
pure export function owns CSV serialization of the records passed to it; it does
not authenticate users or write files. The UI owns delivery of the resulting
payload to the user.

```text
Person -> application UI -> saved-search repository
                    |
                    +-> CSV export function -> export payload
```

## Connections

The UI reads the repository through the application API. The export function is
a synchronous local call with ordered name/query records as input and CSV text
or an explicit empty result as output. No external export service is required.

## Open questions

[CONFIRM-01] Which persistence technology and deployment environment will the
application use? This architectural question remains unresolved in this example.
It must not be silently decided by the export demonstration.

## Review

Confirm ownership and trust boundaries before treating this as your project
architecture. The focused CSV fixture demonstrates only serialization, not the
complete application shown above.
