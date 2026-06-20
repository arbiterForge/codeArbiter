/**
 * network.ts — ca-sandbox network policy (T-10, covers AC-08).
 *
 * applyNetworkPolicy(policy, opts) resolves a network posture into the docker
 * `run` flags + post-start actions + (for the allowlist) an in-container
 * init-firewall script that enforces it. Three policies, ordered by trust:
 *
 *   1. offline  — `--network none`. The container has NO network interface at
 *      all, so nothing inside can reach github (or anything). The SOLID default
 *      and a GUARANTEED control: there is simply no egress path.
 *
 *   2. clone-then-cut — the container starts ON a network so the build/clone can
 *      fetch dependencies, then `applyNetworkPolicy` hands back a post-start
 *      action (`docker network disconnect`) that DETACHES the container from its
 *      network once fetching is done. After the cut there is no interface, so
 *      post-run egress fails. Also a SOLID, GUARANTEED control — it is just
 *      "offline, after a fetch window".
 *
 *   3. egress-allowlist — EXPERIMENTAL. A custom bridge network +
 *      `--cap-add NET_ADMIN --cap-add NET_RAW` + an init-firewall script run
 *      INSIDE the box that sets `iptables -P OUTPUT DROP` and then ACCEPTs only:
 *      loopback, established/related, DNS (udp/tcp 53 to the resolver), and the
 *      resolved IPs of the allowlisted hosts on 80/443. With ALLOW_HOSTS=github.com,
 *      `curl github.com` succeeds and `curl example.com` fails.
 *
 *      *** EXPERIMENTAL — NOT a guaranteed control. *** Spike C
 *      (.codearbiter/spikes/ca-sandbox-egress.md, CONFIRM-08) proved this works
 *      for the single-host case but is BRITTLE for real registries:
 *        - CDN multi-IP drift: an IP resolved at firewall-apply time can rotate
 *          (TTL/anycast) and the new IP is silently DROPPED;
 *        - multi-host gaps: github.com alone does not cover codeload.github.com /
 *          objects.githubusercontent.com / the registry CDNs;
 *        - DNS is an uninspected covert channel: opening udp/tcp 53 (required for
 *          resolution) leaves a DNS-exfil/tunnel hole IP-layer rules cannot close,
 *          and an IP allowlist cannot bind a TLS SNI host to an IP.
 *      Use `offline` or `clone-then-cut` (both GUARANTEED) for anything that
 *      matters. The intended v1.x replacement is a hostname-aware forward proxy
 *      (allowlist by SNI/Host, DNS pointed at the proxy) — see Spike C resolution.
 *
 * Process/shell handling mirrors run.ts / farm.ts: pure argv/script builders here
 * (so the policy is unit-testable without docker), the caller shells docker.
 */

/** The three supported network policies. */
export type NetworkPolicy = "offline" | "clone-then-cut" | "egress-allowlist";

/**
 * The loud, surfaced marker for the experimental allowlist. Exported so the CLI
 * (T-15) and the prose surfaces (T-17) can warn the user uniformly. Mirrors the
 * Spike C resolution: works for a single host, brittle for registries, no DNS
 * protection — not a guaranteed control.
 */
export const ALLOWLIST_EXPERIMENTAL =
  "EXPERIMENTAL: the IP-based egress allowlist is NOT a guaranteed control. It is " +
  "brittle for real package registries (CDN IP drift silently drops rotated IPs, " +
  "multi-host CDNs are not covered by a single hostname) and provides NO DNS-layer " +
  "protection (the open udp/tcp 53 rule is a DNS-exfil/tunnel hole). Prefer " +
  "'offline' or 'clone-then-cut' (both guaranteed). The v1.x fix is a " +
  "hostname-aware forward proxy. See .codearbiter/spikes/ca-sandbox-egress.md.";

/** Options for applyNetworkPolicy, by policy. */
export type NetworkPolicyOptions = {
  /**
   * clone-then-cut: the container id (or name) to disconnect post-clone. When
   * absent, the post-start cut action targets the literal placeholder so the
   * caller can substitute the real id; supplying it makes `postStart` directly
   * runnable.
   */
  containerId?: string;
  /**
   * clone-then-cut / egress-allowlist: the docker network the container is
   * attached to (the network to disconnect from, or the custom bridge to use).
   * Defaults to "bridge" for clone-then-cut.
   */
  networkName?: string;
  /**
   * egress-allowlist (REQUIRED): the hostnames whose resolved IPs are allowed on
   * 80/443. At least one is required — a default-deny firewall with nothing
   * allowed is a footgun.
   */
  allowHosts?: string[];
};

/**
 * A resolved network plan. The caller splices `runArgs` into its `docker run`
 * argv, then (after the container is up and any clone/build is done) runs each
 * `postStart` action with `docker <args>` and, for the allowlist, executes
 * `firewallScript` inside the box.
 */
export type NetworkPlan = {
  /** Flags to splice into `docker run` (e.g. `--network none`, `--cap-add ...`). */
  runArgs: string[];
  /**
   * Actions to run AFTER the container is started (each is a full docker argv
   * minus the leading "docker"). clone-then-cut uses this to disconnect the
   * network once the clone/build window closes.
   */
  postStart: string[][];
  /**
   * For egress-allowlist: a shell script to run INSIDE the container (it resolves
   * the allow hosts and installs the iptables default-deny + allow ruleset).
   * Undefined for the other policies.
   */
  firewallScript?: string;
  /** True only for egress-allowlist — surface the EXPERIMENTAL warning. */
  experimental: boolean;
};

const DEFAULT_BRIDGE = "bridge";

/**
 * Build the in-container init-firewall script from a set of already-resolved
 * destination IPs. Pure (no resolution, no docker) so it is unit-testable; the
 * full applyNetworkPolicy firewall script resolves hostnames at runtime inside
 * the box and feeds the result through the same rule shape.
 *
 * Rule set (Spike C, the structurally-sound part):
 *   iptables -P OUTPUT DROP                 default-deny egress
 *   ACCEPT -o lo                            loopback
 *   ACCEPT established,related              return traffic
 *   ACCEPT udp/tcp --dport 53              DNS (required or nothing resolves)
 *   ACCEPT -d <ip> --dport 80, 443         each allowed IP on http/https
 *
 * @throws if no IPs are supplied (default-deny with nothing allowed is a footgun).
 */
export function buildFirewallScript(ips: ReadonlyArray<string>): string {
  if (!ips || ips.length === 0) {
    throw new Error(
      "ca-sandbox: buildFirewallScript requires at least one allow IP — a " +
        "default-deny OUTPUT chain with no ACCEPT rules blocks everything.",
    );
  }
  const lines: string[] = [
    "set -e",
    "# ca-sandbox egress-allowlist (EXPERIMENTAL — see ca-sandbox-egress.md).",
    "# Default-deny OUTPUT; ACCEPT loopback, established/related, DNS, allow IPs.",
    "iptables -P OUTPUT DROP",
    "iptables -A OUTPUT -o lo -j ACCEPT",
    "iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT",
    "iptables -A OUTPUT -p udp --dport 53 -j ACCEPT",
    "iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT",
  ];
  for (const ip of ips) {
    lines.push(`iptables -A OUTPUT -d ${ip} -p tcp --dport 443 -j ACCEPT`);
    lines.push(`iptables -A OUTPUT -d ${ip} -p tcp --dport 80 -j ACCEPT`);
  }
  return lines.join("\n") + "\n";
}

/**
 * Build the runtime init-firewall script for a set of HOSTNAMES. Resolution
 * happens INSIDE the box at apply time (so it uses the container's own resolver),
 * then the same default-deny + allow shape is installed. This is the script
 * stored on the plan for egress-allowlist; the caller runs it via
 * `docker exec <id> sh -c "<script>"` once the box is up.
 *
 * Resolution uses `getent ahostsv4` (musl/glibc) with a `nslookup` fallback so it
 * works on alpine (bind-tools) and debian-family images alike. Each resolved IPv4
 * is pinned on 80/443. DNS (udp/tcp 53) is opened FIRST so resolution can happen
 * before the policy tightens — though we resolve before flipping OUTPUT to DROP.
 */
function buildFirewallScriptForHosts(hosts: ReadonlyArray<string>): string {
  const hostList = hosts.map((h) => `'${h.replace(/'/g, "")}'`).join(" ");
  // Resolve each host to IPv4s, dedupe, then install the ruleset. We build the
  // allow rules into the chain BEFORE setting the default policy to DROP, so a
  // resolution failure can't lock us out before any ACCEPT exists.
  return [
    "set -e",
    "# ca-sandbox egress-allowlist (EXPERIMENTAL — see ca-sandbox-egress.md).",
    "# Resolve allow hosts inside the box, then default-deny OUTPUT with ACCEPTs",
    "# for loopback, established/related, DNS, and each resolved host IP on 80/443.",
    "resolve_ipv4() {",
    "  # $1 = hostname; print one IPv4 per line. getent first, nslookup fallback.",
    "  if command -v getent >/dev/null 2>&1; then",
    "    getent ahostsv4 \"$1\" 2>/dev/null | awk '{print $1}' | sort -u && return 0",
    "  fi",
    "  if command -v nslookup >/dev/null 2>&1; then",
    "    nslookup \"$1\" 2>/dev/null | awk '/^Address: /{print $2}' | grep -E '^[0-9.]+$' | sort -u && return 0",
    "  fi",
    "  return 1",
    "}",
    "# Base ACCEPTs (added before the DROP policy so we never self-lock).",
    "iptables -A OUTPUT -o lo -j ACCEPT",
    "iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT",
    "iptables -A OUTPUT -p udp --dport 53 -j ACCEPT",
    "iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT",
    `for host in ${hostList}; do`,
    '  ips=$(resolve_ipv4 "$host")',
    '  if [ -z "$ips" ]; then echo "ca-sandbox: could not resolve $host" >&2; exit 1; fi',
    '  for ip in $ips; do',
    '    iptables -A OUTPUT -d "$ip" -p tcp --dport 443 -j ACCEPT',
    '    iptables -A OUTPUT -d "$ip" -p tcp --dport 80 -j ACCEPT',
    '  done',
    "done",
    "# Tighten last: everything not explicitly accepted above is dropped.",
    "iptables -P OUTPUT DROP",
    "",
  ].join("\n");
}

/**
 * Resolve a ca-sandbox network policy into a runnable NetworkPlan.
 *
 * @param policy one of offline | clone-then-cut | egress-allowlist.
 * @param opts policy-specific options (allowHosts is required for the allowlist).
 * @throws on an unknown policy, an empty allow set for the allowlist, etc.
 */
export function applyNetworkPolicy(
  policy: NetworkPolicy,
  opts: NetworkPolicyOptions = {},
): NetworkPlan {
  switch (policy) {
    case "offline":
      // No interface at all — guaranteed no egress, nothing to cut.
      return {
        runArgs: ["--network", "none"],
        postStart: [],
        firewallScript: undefined,
        experimental: false,
      };

    case "clone-then-cut": {
      // Start ON a network (default bridge unless told otherwise) so the
      // clone/build can fetch, then schedule a disconnect that airgaps the box.
      const net = opts.networkName ?? DEFAULT_BRIDGE;
      const target = opts.containerId ?? "<container>";
      return {
        runArgs: ["--network", net],
        // After the fetch window, detach from the network: no interface => no
        // egress (guaranteed, same end-state as offline).
        postStart: [["network", "disconnect", net, target]],
        firewallScript: undefined,
        experimental: false,
      };
    }

    case "egress-allowlist": {
      const hosts = opts.allowHosts ?? [];
      if (hosts.length === 0) {
        throw new Error(
          "ca-sandbox: egress-allowlist requires at least one allowHosts entry — " +
            "a default-deny firewall with nothing allowed blocks all egress " +
            "(use 'offline' for that). " +
            ALLOWLIST_EXPERIMENTAL,
        );
      }
      // Custom bridge (the allowlist needs a non-default bridge so the firewall
      // rules apply cleanly) + the caps iptables inside the box needs.
      const net = opts.networkName ?? "ca-sbx-egress";
      return {
        runArgs: [
          "--network",
          net,
          "--cap-add",
          "NET_ADMIN",
          "--cap-add",
          "NET_RAW",
        ],
        postStart: [],
        firewallScript: buildFirewallScriptForHosts(hosts),
        experimental: true,
      };
    }

    default: {
      // Exhaustiveness: an unknown policy is a hard error, not a silent
      // pass-through (a typo must never weaken egress).
      const bad: never = policy;
      throw new Error(`ca-sandbox: unknown network policy ${JSON.stringify(bad)}`);
    }
  }
}
