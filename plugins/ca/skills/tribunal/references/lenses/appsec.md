# appsec — lens mandate

Executed by `tribunal-lens-reviewer` under the `appsec` assignment. Write contract + evidence discipline: `finding-record.md` — every finding needs `path:line` evidence; write it the moment it's found.

## Scope emphasis
The assigned path slice, weighted to trust-boundary crossings and request handlers.

## Required reading
- `${CLAUDE_PROJECT_DIR}/.codearbiter/security-controls.md` — trust boundaries and approved patterns; and `inventory.md` in the run dir for marked trust boundaries.

## Checklist
- Injection surface: user-controlled input reaching SQL (string concatenation, CWE-89), shell execution, filesystem path resolution, HTML/template rendering (XSS, CWE-79), or deserialization. Concatenating input into any query or command is critical regardless of how "clean" the input looks.
- Resource-level authorization: for every route/endpoint, is the authenticated user verified to own *this* resource? Missing resource-level authz (IDOR) is the highest-yield critical class and near-invisible to SAST.
- Missing input boundary validation (CWE-20): inputs used without null/type/range checks at boundaries.
- JWT: signature, expiry, issuer, and algorithm validated; no algorithm confusion.
- CORS: wildcard `*` origins. SSRF: server-side fetches of user-controlled URLs.

## Exposure
Count of sink sites inspected (query construction, command exec, path resolution, HTML/template render, deserialization).

## Out of scope
Secrets/crypto/deps (secrets-supply); generic error handling (reliability).
