# `farm.ts` base-URL security review — 2026-07-20

## Scope and disposition

- Board item: `v2.security.0003` / SD-02.
- Review target: `plugins/ca/tools/farm.ts`, its shipped `farm.js` bundle,
  `farm.unit.test.ts`, and the TLS/secret claims in
  `.codearbiter/security-controls.md`.
- Base: `origin/main` at `b11f337` on branch `review/farm-base-url`.
- Durable defect: GitHub issue #353.
- Final verdict: **PASS after remediation**. The first review BLOCKED on two
  HIGH and two MEDIUM findings; the final independent security re-review found
  zero CRITICAL, HIGH, MEDIUM, or LOW findings.

## Initial findings

1. **HIGH — redirect downgrade/body forwarding.** Both POSTs used fetch's
   default automatic redirect behavior. A validated URL could return 307/308
   and forward the POST body to an unvalidated or cleartext destination.
2. **HIGH — credential-bearing URL disclosure.** HTTPS userinfo was accepted;
   Node fetch then rejected the request with the credential-bearing URL in its
   error. Rejected URLs were also reflected verbatim.
3. **MEDIUM — validation above, not at, network sinks.** The CLI and canary
   paths validated resolved configuration, but exported `httpWorker`/`runTask`
   and `makeEntitlementProbe` seams could reach fetch with caller-supplied
   external HTTP URLs.
4. **MEDIUM — provider-controlled diagnostics.** Raw response bodies and full
   base URLs could flow into stderr, retry prompts, results, or reports.
5. **LOW control drift.** The controls omitted the existing
   `FARM_DEFAULT_API_BASE_URL` precedence layer.

## SMARTS decisions

- **Redirect handling:** refuse redirects with `redirect: "error"` on both
  POSTs. This is the smallest securable and maintainable choice; manual redirect
  support would add hop limits, method reconstruction, and repeated validation
  without an accepted provider requirement.
- **Validation placement:** retain early config validation for operator feedback
  and repeat it at each fetch-producing boundary. The deliberate duplication is
  defense in depth for exported programmatic seams.
- **Diagnostics:** emit fixed validation messages, identify only a parsed
  endpoint origin, and consume provider bodies without logging or propagating
  them. This preserves actionable status/config guidance without treating
  attacker-controlled text as safe telemetry.

## Regression-first evidence

The pre-fix focused suite passed 166 tests because HTTPS userinfo acceptance was
explicitly expected and redirect/sink behavior was untested. New tests then
failed for the intended reasons:

- HTTPS userinfo was accepted and malformed URL contents were reflected.
- Direct external-HTTP worker/probe calls reached mocked fetch.
- Neither POST set a fail-closed redirect policy.
- Provider bodies reached stderr and parse errors; endpoint query credentials
  appeared in diagnostics.

After the minimal fix, 172 focused unit tests pass. Coverage includes:

- redirect refusal on both POST paths;
- boundary validation for the worker and entitlement probe;
- HTTP, HTTPS, and non-HTTP(S) userinfo rejection without reflection;
- malformed/control-bearing URL non-reflection;
- provider-body suppression in stderr, worker errors, and parse errors;
- sanitized-origin diagnostics; and
- preserved normal HTTPS plus bare `localhost`/`127.0.0.1` HTTP behavior.

## Final verification

- Farm: 198/198 Vitest tests pass.
- TypeScript: `npm run typecheck` passes.
- Bundle: two consecutive builds produced identical SHA-256
  `D3FE6B4F337FBB2A7E090767E20F7A3201416793DCE34DF7281BD426ED65A218`.
- Supply chain: `npm audit --omit=dev --audit-level=critical` reports zero
  vulnerabilities.
- Repository: all 15 commands listed in `.codearbiter/tech-stack.md` pass;
  the hook suite passes 967/967; plugin reference validation passes.
- Review fleet: security PASS (0 findings), coverage PASS, and call-site/
  architecture PASS.
- Whitespace: `git diff --check` passes.

## Resulting invariant

Every farm network boundary now validates the base URL, every farm POST refuses
automatic redirects, userinfo is rejected on every scheme, and neither raw
configuration nor provider-controlled bodies enter diagnostics. The generated
runtime bundle and current security-controls record match the TypeScript source.
