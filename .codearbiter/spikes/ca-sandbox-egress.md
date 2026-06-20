# Spike C — egress allowlist tightness (CONFIRM-08)

Status: RESOLVED-WITH-CAVEAT (the caveat being: ship allowlist EXPERIMENTAL, not a guaranteed
control). Spike executed and independently verified. Confidence: high (5/5).

## Falsifiable question

Can a docker-native, iptables-based egress allowlist (default-deny OUTPUT + allow only resolved IPs
of named hosts) reliably restrict a container so an allowed host succeeds and a non-allowed host
fails — tightly enough to be a guaranteed v1 control for real package registries?

## What was empirically observed

Environment: Docker 29.5.3 Linux engine via WSL2. No Bash-sandbox override needed.

**Baselines:** `--network none` -> `curl example.com` rc=6 (could-not-resolve, no egress);
default bridge -> `curl example.com` http=200 (full egress).

**Allowlist mechanism works for the simple single-host case.** Custom bridge net +
`--cap-add NET_ADMIN --cap-add NET_RAW` + iptables (OUTPUT default DROP; ACCEPT lo,
established/related, udp/tcp 53 to the resolver, resolved allow-host IPs on 443/80). With
`ALLOW_HOSTS=github.com`: `curl https://github.com` -> http=200 (rc=0);
`curl https://example.com` -> `curl: (28) Connection timed out` (rc=28, http=000). The
github-yes / example-no falsifiable claim PASSED. `iptables -S` confirmed `-P OUTPUT DROP` with
exactly the claimed ACCEPT rules.

**But it is fiddly and leaky for real registries (all observed, not inferred):**

1. **CDN multi-IP drift breaks it.** `registry.npmjs.org` resolved to 12 Cloudflare IPs;
   `pypi.org` to 4 Fastly IPs. Deterministic demo: pin only `104.16.0.34`, then
   `curl --resolve registry.npmjs.org:443:104.16.5.34` (a different real npm IP) -> rc=28 timeout
   (DRIFTED IP BLOCKED); the pinned IP -> http=200. The instant DNS hands an IP not captured at
   firewall-apply time (TTL rotation, geo/anycast, stale cache), traffic is silently dropped.
2. **Multi-host gap.** `github.com` alone does NOT cover the clone path: `codeload.github.com` is a
   separate host -> rc=28 blocked when only github.com is allowed. Real allow sets must enumerate
   github.com + codeload.github.com + objects.githubusercontent.com + registry.npmjs.org + pypi.org
   + files.pythonhosted.org + crates.io + static.crates.io + proxy.golang.org + sum.golang.org —
   each a drifting CDN IP pool.
3. **DNS is an uninspected covert channel.** The ruleset must open udp/tcp 53 to the resolver before
   default-deny or nothing resolves — but from inside the locked box,
   `dig +short A secret-data-leak.example.org @127.0.0.11` returned rc=0 (the query left the box via
   the Docker embedded resolver). IP-layer allowlisting cannot close DNS exfil/tunneling and cannot
   bind a TLS SNI host to an IP (a container can resolve `attacker.com` to a pinned allowlist IP).

## Verifier's verdict

Confirmed. The verifier rebuilt the load-bearing github-succeeds / example-fails pair on an
independent image/network (`-verify` suffix) and reproduced it on first try: allowed host http=200,
non-allowed host rc=28 timeout (a DROP, not a reject — default-deny genuinely enforcing). The
verifier also independently reproduced the DNS-exfil finding (`dig A`/`dig TXT` of non-allowlisted
names via `@127.0.0.11` -> rc=0), which is what underpins the "experimental, not guaranteed"
recommendation. The pinned github IP differed by one octet (113.4 vs 113.3) — expected anycast
variation within the same GitHub /24, not a discrepancy. CDN-drift and multi-host enumeration
sub-claims were not separately re-run but are consistent with how anycast/CDN DNS works.

## Resolution / recommendation

**Ship the IP-based iptables allowlist as EXPERIMENTAL in v1** (do NOT make it a guaranteed control).
**Ship offline + clone-then-cut as the solid, recommended defaults** — both are guaranteed and were
clean in baselines. The allowlist mechanism is structurally sound (caps + default-deny works) but
too brittle for package registries (CDN IP drift) and provides no DNS-layer protection.

**The real v1.x fix is a hostname-aware forward proxy:** an egress HTTP/HTTPS CONNECT proxy that
allowlists by HOSTNAME (SNI/Host header) as the container's only egress route, with DNS pointed at
the proxy. A hostname proxy survives CDN IP drift, closes the DNS-tunnel hole (no raw 53 to the
box), and is the direction Anthropic's own devcontainer trends toward.

## Architecture impact

No change to the load-bearing FS-isolation invariant — egress tightness is defense-in-depth, not the
primary guarantee. This matches what the spec/plan already say: spec criterion 7 and plan lines
94-97 already mark allowlist experimental and ship offline + clone-then-cut as solid, so Spike C
**confirms the planned posture rather than forcing a change.** The one addition the findings
recommend: record the forward-proxy approach as the intended v1.x evolution of the allowlist (with
its two documented IP-allowlist weaknesses — CDN drift and the open-resolver DNS exfil channel —
as the rationale), so the experimental flag has a known upgrade path rather than being a dead end.
