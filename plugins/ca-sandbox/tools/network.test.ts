/**
 * network.test.ts — T-10. Covers AC-08.
 *
 * applyNetworkPolicy(policy, opts) resolves a ca-sandbox network policy into the
 * docker flags + post-start actions that enforce it. Three policies:
 *
 *   - offline       => --network none. Inside the box `curl github.com` fails
 *                      (no egress at all). The SOLID default.
 *   - clone-then-cut => the container comes up ON a network (so build/clone can
 *                      fetch deps), then the network is DETACHED. Post-cut egress
 *                      from inside the box fails. The SOLID default for "fetch at
 *                      build, then airgap".
 *   - egress-allowlist (EXPERIMENTAL) => a custom bridge network + --cap-add
 *                      NET_ADMIN --cap-add NET_RAW + an init-firewall script run
 *                      inside the box: default OUTPUT DROP, ACCEPT lo +
 *                      established/related + DNS (udp/tcp 53) + the resolved IPs
 *                      of the allowlisted hosts on 80/443. Owned fixed peers
 *                      prove allow/deny independently of public CDN availability.
 *                      Still EXPERIMENTAL (CDN drift + DNS-exfil hole).
 *
 * Two layers:
 *   1. PURE unit tests over the argv/script builders — no real docker. RED gate;
 *      runs everywhere.
 *   2. DOCKER-GATED integration (guarded by `docker info`) proving the three
 *      load-bearing AC-08 behaviors against real containers. Namespaced
 *      (ca-sbx-t10-*) + labeled (ca.sandbox.build=1) + cleaned up.
 */
import { describe, it, expect, afterAll } from "vitest";
import { dockerGate } from "./docker-gate.ts";
import { spawnSync } from "node:child_process";
import { isIPv4 } from "node:net";
import {
  applyNetworkPolicy,
  buildFirewallScript,
  ALLOWLIST_EXPERIMENTAL,
  type NetworkPolicy,
} from "./network.ts";

// --------------------------------------------------------------------------
// PURE unit layer — policy resolution + firewall script, no real docker.
// --------------------------------------------------------------------------
describe("applyNetworkPolicy — offline (AC-08, solid default)", () => {
  const plan = applyNetworkPolicy("offline");

  it("detaches the container from all networking via --network none", async () => {
    expect(plan.runArgs).toContain("--network");
    expect(plan.runArgs[plan.runArgs.indexOf("--network") + 1]).toBe("none");
  });

  it("adds no NET_ADMIN/NET_RAW caps and no firewall script (nothing to allow)", async () => {
    expect(plan.runArgs).not.toContain("--cap-add");
    expect(plan.firewallScript).toBeUndefined();
    expect(plan.experimental).toBe(false);
  });

  it("requires no post-start cut (it was never connected)", async () => {
    expect(plan.postStart).toEqual([]);
  });
});

describe("applyNetworkPolicy — clone-then-cut (AC-08, solid default)", () => {
  const plan = applyNetworkPolicy("clone-then-cut", { containerId: "deadbeefcafe" });

  it("brings the container UP on a network (so the clone/build can fetch)", async () => {
    // It must NOT be --network none at start — the whole point is egress is up
    // during clone/build.
    const i = plan.runArgs.indexOf("--network");
    if (i >= 0) expect(plan.runArgs[i + 1]).not.toBe("none");
  });

  it("schedules a post-start DETACH of the container from its network", async () => {
    // After clone/build, the network is cut: a `docker network disconnect`
    // targeting this container id.
    const flat = plan.postStart.map((a) => a.join(" "));
    expect(flat.some((c) => /network disconnect/.test(c))).toBe(true);
    expect(flat.some((c) => c.includes("deadbeefcafe"))).toBe(true);
    expect(plan.experimental).toBe(false);
  });
});

describe("applyNetworkPolicy — egress-allowlist (AC-08, EXPERIMENTAL)", () => {
  const plan = applyNetworkPolicy("egress-allowlist", {
    allowHosts: ["github.com"],
    networkName: "ca-sbx-t10-net",
  });

  it("is flagged EXPERIMENTAL (Spike C: CDN drift + DNS-exfil hole)", async () => {
    expect(plan.experimental).toBe(true);
    // The marker constant is exported and non-empty so docs/CLI can surface it.
    expect(ALLOWLIST_EXPERIMENTAL).toMatch(/experimental/i);
  });

  it("attaches the custom bridge network and adds NET_ADMIN + NET_RAW caps", async () => {
    const i = plan.runArgs.indexOf("--network");
    expect(i).toBeGreaterThanOrEqual(0);
    expect(plan.runArgs[i + 1]).toBe("ca-sbx-t10-net");
    const caps: string[] = [];
    plan.runArgs.forEach((a, idx) => {
      if (a === "--cap-add") caps.push(plan.runArgs[idx + 1]);
    });
    expect(caps).toContain("NET_ADMIN");
    expect(caps).toContain("NET_RAW");
  });

  it("emits an init-firewall script: default OUTPUT DROP + lo/established/DNS + resolved allow IPs", async () => {
    const fw = plan.firewallScript;
    expect(fw).toBeTruthy();
    const s = fw as string;
    // default-deny OUTPUT
    expect(s).toMatch(/iptables\s+-P\s+OUTPUT\s+DROP/);
    // loopback
    expect(s).toMatch(/-o\s+lo\b.*ACCEPT|ACCEPT.*-o\s+lo\b/);
    // established/related
    expect(s).toMatch(/ESTABLISHED,RELATED|RELATED,ESTABLISHED/);
    // DNS resolution must be allowed or nothing resolves
    expect(s).toMatch(/--dport\s+53/);
    // the allowlisted host must be resolved and its IPs pinned on 443
    expect(s).toMatch(/github\.com/);
    expect(s).toMatch(/--dport\s+443/);
  });

  it("requires at least one allow host", async () => {
    expect(() => applyNetworkPolicy("egress-allowlist", { allowHosts: [] })).toThrow();
  });
});

describe("buildFirewallScript — pure script builder", () => {
  it("pins each provided IP on 80 and 443 with ACCEPT rules", async () => {
    const s = buildFirewallScript(["1.2.3.4", "5.6.7.8"]);
    expect(s).toMatch(/-d\s+1\.2\.3\.4\b/);
    expect(s).toMatch(/-d\s+5\.6\.7\.8\b/);
    expect(s).toMatch(/--dport\s+80/);
    expect(s).toMatch(/--dport\s+443/);
    expect(s).toMatch(/-P\s+OUTPUT\s+DROP/);
  });

  it("refuses to build with no IPs (default-deny with nothing allowed is a footgun)", async () => {
    expect(() => buildFirewallScript([])).toThrow();
  });
});

describe("applyNetworkPolicy — unknown policy", () => {
  it("throws on an unrecognized policy", async () => {
    expect(() => applyNetworkPolicy("wide-open" as NetworkPolicy)).toThrow();
  });
});

type FirewallCounters = { dropped: number; allowed: { ip: string; port: number; packets: number }[] };

/** Fixed-field diagnostics for this fixture's actual OUTPUT chain, never raw process output. */
function firewallCounters(output: string): FirewallCounters | undefined {
  if (output.length > 16_384) return undefined;
  const policies = [...output.matchAll(/^:OUTPUT DROP \[(\d+):(\d+)\]$/gm)];
  if (policies.length !== 1) return undefined;
  const bounded = (text: string) => Number.isSafeInteger(Number(text)) && Number(text) >= 0;
  if (!bounded(policies[0][1]) || !bounded(policies[0][2])) return undefined;
  const allowed: FirewallCounters["allowed"] = [];
  for (const line of output.split("\n")) {
    if (!line.includes("-A OUTPUT")) continue;
    const rule = /^\[(\d+):(\d+)\] (-A OUTPUT .+)$/u.exec(line);
    if (rule === null || !bounded(rule[1]) || !bounded(rule[2])) return undefined;
    if (/^-A OUTPUT (?:-o lo|-m state --state (?:RELATED,ESTABLISHED|ESTABLISHED,RELATED)|-p (?:tcp|udp) -m (?:tcp|udp) --dport 53) -j ACCEPT$/u.test(rule[3])) continue;
    const destination = /^-A OUTPUT -d ([0-9.]+)(?:\/32)? -p tcp -m tcp --dport (80|443) -j ACCEPT$/u.exec(rule[3]);
    if (destination === null || !isIPv4(destination[1]) || allowed.length >= 64) return undefined;
    allowed.push({ ip: destination[1], port: Number(destination[2]), packets: Number(rule[1]) });
  }
  return { dropped: Number(policies[0][1]), allowed };
}

describe("allowlist fixture counter observations", () => {
  const rules = [
    "*filter", ":OUTPUT DROP [7:420]",
    "[1:60] -A OUTPUT -o lo -j ACCEPT",
    "[0:0] -A OUTPUT -m state --state RELATED,ESTABLISHED -j ACCEPT",
    "[0:0] -A OUTPUT -p udp -m udp --dport 53 -j ACCEPT",
    "[0:0] -A OUTPUT -p tcp -m tcp --dport 53 -j ACCEPT",
    "[2:120] -A OUTPUT -d 172.18.0.2/32 -p tcp -m tcp --dport 443 -j ACCEPT",
    "[3:180] -A OUTPUT -d 172.18.0.2/32 -p tcp -m tcp --dport 80 -j ACCEPT",
    "COMMIT", "",
  ].join("\n");

  it("retains only numeric DROP and exact destination-port ACCEPT counters", () => {
    expect(firewallCounters(rules)).toEqual({ dropped: 7, allowed: [
      { ip: "172.18.0.2", port: 443, packets: 2 },
      { ip: "172.18.0.2", port: 80, packets: 3 },
    ] });
  });

  it("refuses absent or permissive policy, unbounded counters and malformed destinations", () => {
    for (const bad of [
      rules.replace(":OUTPUT DROP [7:420]", ":OUTPUT ACCEPT [7:420]"),
      rules.replace(":OUTPUT DROP [7:420]", ""),
      rules.replace(":OUTPUT DROP [7:420]", ":OUTPUT DROP [7:420]\n:OUTPUT DROP [7:420]"),
      rules.replace("[7:420]", "[9007199254740992:420]"),
      rules.replaceAll("172.18.0.2/32", "999.18.0.2/32"),
      rules + "x".repeat(16_384),
    ]) expect(firewallCounters(bad)).toBeUndefined();
  });

  it("refuses unexpected wide OUTPUT acceptance instead of attributing a false deny", () => {
    expect(firewallCounters(rules.replace("COMMIT", "[0:0] -A OUTPUT -j ACCEPT\nCOMMIT"))).toBeUndefined();
  });
});

// --------------------------------------------------------------------------
// DOCKER-GATED integration layer (AC-08) — real containers, real curl.
// --------------------------------------------------------------------------
const d = dockerGate("network", { linux: true });

const NS = "ca-sbx-t10";
const DENV = { ...process.env, MSYS_NO_PATHCONV: "1" };
// curl-capable, iptables-capable tiny image. alpine has both (apk add) but we
// avoid network installs inside the box; use an image that already has curl.
// `curlimages/curl` has curl; for the firewall layer we need iptables too, so
// the allowlist test uses an image with both (built from alpine + apk at setup,
// done with egress UP before the firewall is applied).
const CURL_IMAGE = "curlimages/curl:latest";

function dk(args: string[], input?: string) {
  return spawnSync("docker", args, { encoding: "utf8", env: DENV, input, maxBuffer: 64 * 1024 * 1024 });
}

d("network policy [docker] — AC-08 real egress behavior", () => {
  const created = { containers: [] as string[], networks: [] as string[], images: [] as string[] };

  afterAll(() => {
    for (const c of created.containers) dk(["rm", "-f", c]);
    for (const n of created.networks) dk(["network", "rm", n]);
    for (const i of created.images) dk(["rmi", "-f", i]);
  });

  it("offline: curl github.com from inside FAILS (no egress)", async () => {
    const pull = dk(["pull", CURL_IMAGE]);
    expect(pull.status, pull.stderr).toBe(0);

    const plan = applyNetworkPolicy("offline");
    // Run a one-shot container under the offline plan's run args; curl must fail.
    const name = `${NS}-offline-${Date.now()}`;
    const r = dk([
      "run", "--rm", "--name", name,
      "--label", "ca.sandbox.build=1", "--label", "ca.sandbox=1",
      ...plan.runArgs,
      CURL_IMAGE,
      "-sS", "--max-time", "10", "https://github.com",
    ]);
    // --network none => curl cannot resolve/connect => non-zero exit.
    expect(r.status).not.toBe(0);
  }, 120_000);

  it("clone-then-cut: egress works at start, then post-cut egress FAILS", async () => {
    const name = `${NS}-cut-${Date.now()}`;
    // Start a long-lived container WITH network up (clone-then-cut start args).
    const plan = applyNetworkPolicy("clone-then-cut", { containerId: name });
    const startArgs = [
      "run", "-d", "--name", name,
      "--label", "ca.sandbox.build=1", "--label", "ca.sandbox=1",
      ...plan.runArgs,
      // entrypoint override: keep alive (curlimages/curl's entrypoint is curl)
      "--entrypoint", "sleep",
      CURL_IMAGE, "infinity",
    ];
    const start = dk(startArgs);
    expect(start.status, start.stderr).toBe(0);
    const id = start.stdout.trim();
    created.containers.push(id);

    // Egress is UP at start: curl github.com succeeds (the clone/build window).
    const before = dk(["exec", id, "curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "20", "https://github.com"]);
    expect(before.status, `pre-cut curl should succeed: ${before.stderr}`).toBe(0);

    // CUT: run the plan's post-start actions (docker network disconnect ...).
    for (const action of plan.postStart) {
      const cut = dk(action);
      expect(cut.status, `cut action failed: ${cut.stderr}`).toBe(0);
    }

    // Post-cut egress FAILS.
    const after = dk(["exec", id, "curl", "-sS", "-o", "/dev/null", "--max-time", "10", "https://github.com"]);
    expect(after.status, "post-cut egress must fail").not.toBe(0);
  }, 180_000);

  it("egress-allowlist (EXPERIMENTAL): admitted owned peers succeed and reachable unlisted peers are dropped", { timeout: 240_000, retry: 2 }, () => {
    // We need an image with curl + iptables + a resolver tool. Build a tiny one
    // (egress is up at build time). alpine has all via apk.
    const img = `${NS}-fw:${Date.now()}`;
    const dockerfile = [
      "FROM alpine:latest",
      "RUN apk add --no-cache curl iptables bind-tools",
    ].join("\n");
    const build = dk(["build", "-t", img, "-f", "-", "."], dockerfile);
    expect(build.status, build.stderr).toBe(0);
    created.images.push(img);

    // Own every endpoint on an internal bridge: no published host ports or CDN
    // dependency. Docker's assigned IPv4s remain fixed for these peers' lifetime.
    const net = `${NS}-net-${Date.now()}`;
    const mk = dk(["network", "create", "--internal", "--label", "ca.sandbox.build=1", net]);
    expect(mk.status, mk.stderr).toBe(0);
    created.networks.push(net);

    // Use the image's existing applet; missing capability is a hard failure,
    // never an install or another server implementation.
    const applets = dk(["run", "--rm", "--network", "none", img, "busybox", "--list"]);
    expect(applets.status, "existing BusyBox applet inventory must be readable").toBe(0);
    expect(applets.stdout.split(/\r?\n/u)).toContain("nc");
    const peers = [
      { alias: "ca-sbx-allowed", marker: "allowed-owned-peer" },
      { alias: "ca-sbx-denied", marker: "denied-owned-peer" },
    ].map(({ alias, marker }) => {
      const server = [
        "serve() { while :; do",
        `  printf 'HTTP/1.1 200 OK\\r\\nContent-Length: ${marker.length}\\r\\nConnection: close\\r\\n\\r\\n${marker}' | busybox nc -l -p \"$1\" -w 2;`,
        "done; }; serve 80 & serve 443 & wait",
      ].join("\n");
      const startPeer = dk([
        "run", "-d", "--network", net, "--network-alias", alias,
        "--label", "ca.sandbox.build=1", "--label", "ca.sandbox=1",
        "--entrypoint", "sh", img, "-c", server,
      ]);
      expect(startPeer.status, "owned endpoint must start").toBe(0);
      const peer = startPeer.stdout.trim();
      created.containers.push(peer);
      // Bounded service readiness, not a retry of any egress assertion.
      const ready = dk(["exec", peer, "sh", "-c", [
        "i=0; while [ \"$i\" -lt 100 ]; do",
        "awk '$4 == \"0A\" && $2 ~ /:(0050|01BB)$/ {p[substr($2,length($2)-3)]=1} END {exit !(p[\"0050\"] && p[\"01BB\"])}' /proc/net/tcp /proc/net/tcp6 && exit 0",
        "i=$((i+1)); sleep 0.01; done; exit 1",
      ].join("\n")]);
      expect(ready.status, "both owned TCP listeners must be ready").toBe(0);
      const address = dk(["inspect", "--format", `{{(index .NetworkSettings.Networks "${net}").IPAddress}}`, peer]);
      const ip = address.stdout.trim();
      expect(address.status).toBe(0);
      expect(isIPv4(ip), "owned peer must have a fixed IPv4 on this network").toBe(true);
      return { alias, marker, ip };
    });
    expect(peers[0].ip).not.toBe(peers[1].ip);

    const plan = applyNetworkPolicy("egress-allowlist", {
      allowHosts: [peers[0].alias],
      networkName: net,
    });
    expect(plan.experimental).toBe(true);

    // Start the box on the custom net WITH the NET_ADMIN/NET_RAW caps. Network
    // is up so we can resolve+apply the firewall, then it self-restricts.
    const name = `${NS}-allow-${Date.now()}`;
    const start = dk([
      "run", "-d", "--name", name,
      "--label", "ca.sandbox.build=1", "--label", "ca.sandbox=1",
      ...plan.runArgs,
      "--entrypoint", "sleep",
      img, "infinity",
    ]);
    expect(start.status, start.stderr).toBe(0);
    const id = start.stdout.trim();
    created.containers.push(id);

    const probe = (alias: string, port: number, seconds: number) => dk([
      "exec", id, "curl", "--ipv4", "--noproxy", "*", "-sS", "--max-time", String(seconds),
      `http://${alias}:${port}/`,
    ]);
    // Prove BOTH endpoints and both policy ports reachable before tightening.
    // HTTP on TCP443 tests the port rule only; no TLS/SNI/identity claim or -k.
    for (const peer of peers) for (const port of [80, 443]) {
      const before = probe(peer.alias, port, 25);
      expect(before.status, `owned pre-firewall endpoint ${peer.alias}:${port}`).toBe(0);
      expect(before.stdout).toBe(peer.marker);
    }

    // Apply the UNCHANGED production resolver/firewall inside the actual box.
    const fw = plan.firewallScript as string;
    const applied = dk(["exec", id, "sh", "-c", fw]);
    expect(applied.status, `firewall apply failed: ${applied.stdout}\n${applied.stderr}`).toBe(0);

    const counters = () => {
      const observed = dk(["exec", id, "iptables-save", "-c", "-t", "filter"]);
      expect(observed.status, "actual OUTPUT counters must be readable").toBe(0);
      const snapshot = firewallCounters(observed.stdout);
      expect(snapshot, "actual OUTPUT must be default-DROP with only expected ACCEPT rules").toBeDefined();
      expect(snapshot!.allowed.map(({ ip, port }) => `${ip}:${port}`).sort()).toEqual(
        [`${peers[0].ip}:80`, `${peers[0].ip}:443`].sort(),
      );
      return snapshot!;
    };
    for (const port of [80, 443]) {
      const initial = counters();
      const allowed = probe(peers[0].alias, port, 25);
      const accepted = counters();
      expect(allowed.status, `owned admitted endpoint; ${JSON.stringify({ initial, accepted })}`).toBe(0);
      expect(allowed.stdout).toBe(peers[0].marker);
      const packets = (snapshot: FirewallCounters) => snapshot.allowed.find((rule) => rule.port === port)!.packets;
      expect(packets(accepted)).toBeGreaterThan(packets(initial));

      // A reachable peer on the SAME bridge must now time out, with actual DROP
      // counter growth: not a DNS error, absent server, removed network or exit7.
      const blocked = probe(peers[1].alias, port, 10);
      const denied = counters();
      expect(blocked.status, `owned denied endpoint; ${JSON.stringify({ accepted, denied })}`).toBe(28);
      expect(denied.dropped).toBeGreaterThan(accepted.dropped);
    }
  });
});
