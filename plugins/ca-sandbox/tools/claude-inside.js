#!/usr/bin/env node

// claude-inside-cli.ts
import path from "node:path";
import { fileURLToPath } from "node:url";

// mounts.ts
var BindMountRejectedError = class extends Error {
  constructor(detail) {
    super(
      `ca-sandbox: bind mount rejected \u2014 a sandbox container never gets a host bind mount (${detail}). Only type=volume and type=tmpfs mounts are permitted.`
    );
    this.name = "BindMountRejectedError";
  }
};
function looksLikeShorthand(value) {
  return typeof value === "string" && value.includes(":");
}
function renderSpec(spec, index) {
  if (typeof spec === "string") {
    throw new BindMountRejectedError(
      `spec[${index}] is a "-v host:container" shorthand string ${JSON.stringify(spec)}`
    );
  }
  if (spec === null || typeof spec !== "object") {
    throw new BindMountRejectedError(`spec[${index}] is not a mount spec object (${String(spec)})`);
  }
  const asRecord = spec;
  if ("v" in asRecord || "volume" in asRecord) {
    const sh = asRecord.v ?? asRecord.volume;
    throw new BindMountRejectedError(
      `spec[${index}] uses the "-v" shorthand (${JSON.stringify(sh)})` + (looksLikeShorthand(sh) ? " which expresses a host:container bind" : "")
    );
  }
  const type = asRecord.type;
  if (type === "bind") {
    throw new BindMountRejectedError(`spec[${index}] is an explicit type=bind mount`);
  }
  if (type !== "volume" && type !== "tmpfs") {
    throw new BindMountRejectedError(
      `spec[${index}] has unsupported mount type ${JSON.stringify(type)} (expected "volume" or "tmpfs")`
    );
  }
  const parts = [`type=${type}`];
  if (type === "volume") {
    const v = spec;
    if (!v.source) {
      throw new Error(`ca-sandbox: spec[${index}] type=volume requires a non-empty source`);
    }
    if (!v.target) {
      throw new Error(`ca-sandbox: spec[${index}] type=volume requires a non-empty target`);
    }
    parts.push(`source=${v.source}`, `target=${v.target}`);
    if (v.readonly) parts.push("readonly");
  } else {
    const t = spec;
    if (!t.target) {
      throw new Error(`ca-sandbox: spec[${index}] type=tmpfs requires a non-empty target`);
    }
    parts.push(`target=${t.target}`);
    if (t.readonly) parts.push("readonly");
  }
  return parts.join(",");
}
function buildMountArgs(specs) {
  if (!Array.isArray(specs)) {
    throw new Error("ca-sandbox: buildMountArgs expects an array of mount specs");
  }
  const values = specs.map((spec, i) => renderSpec(spec, i));
  const argv = [];
  for (const value of values) {
    argv.push("--mount", value);
  }
  return argv;
}

// network.ts
var ALLOWLIST_EXPERIMENTAL = "EXPERIMENTAL: the IP-based egress allowlist is NOT a guaranteed control. It is brittle for real package registries (CDN IP drift silently drops rotated IPs, multi-host CDNs are not covered by a single hostname) and provides NO DNS-layer protection (the open udp/tcp 53 rule is a DNS-exfil/tunnel hole). Prefer 'offline' or 'clone-then-cut' (both guaranteed). The v1.x fix is a hostname-aware forward proxy. See .codearbiter/spikes/ca-sandbox-egress.md.";
var DEFAULT_BRIDGE = "bridge";
function buildFirewallScriptForHosts(hosts) {
  const hostList = hosts.map((h) => `'${h.replace(/'/g, "")}'`).join(" ");
  return [
    "set -e",
    "# ca-sandbox egress-allowlist (EXPERIMENTAL \u2014 see ca-sandbox-egress.md).",
    "# Resolve allow hosts inside the box, then default-deny OUTPUT with ACCEPTs",
    "# for loopback, established/related, DNS, and each resolved host IP on 80/443.",
    "resolve_ipv4() {",
    "  # $1 = hostname; print one IPv4 per line. getent first, nslookup fallback.",
    "  if command -v getent >/dev/null 2>&1; then",
    `    getent ahostsv4 "$1" 2>/dev/null | awk '{print $1}' | sort -u && return 0`,
    "  fi",
    "  if command -v nslookup >/dev/null 2>&1; then",
    `    nslookup "$1" 2>/dev/null | awk '/^Address: /{print $2}' | grep -E '^[0-9.]+$' | sort -u && return 0`,
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
    "  for ip in $ips; do",
    '    iptables -A OUTPUT -d "$ip" -p tcp --dport 443 -j ACCEPT',
    '    iptables -A OUTPUT -d "$ip" -p tcp --dport 80 -j ACCEPT',
    "  done",
    "done",
    "# Tighten last: everything not explicitly accepted above is dropped.",
    "iptables -P OUTPUT DROP",
    ""
  ].join("\n");
}
function applyNetworkPolicy(policy, opts = {}) {
  switch (policy) {
    case "offline":
      return {
        runArgs: ["--network", "none"],
        postStart: [],
        firewallScript: void 0,
        experimental: false
      };
    case "clone-then-cut": {
      const net = opts.networkName ?? DEFAULT_BRIDGE;
      const target = opts.containerId ?? "<container>";
      return {
        runArgs: ["--network", net],
        // After the fetch window, detach from the network: no interface => no
        // egress (guaranteed, same end-state as offline).
        postStart: [["network", "disconnect", net, target]],
        firewallScript: void 0,
        experimental: false
      };
    }
    case "egress-allowlist": {
      const hosts = opts.allowHosts ?? [];
      if (hosts.length === 0) {
        throw new Error(
          "ca-sandbox: egress-allowlist requires at least one allowHosts entry \u2014 a default-deny firewall with nothing allowed blocks all egress (use 'offline' for that). " + ALLOWLIST_EXPERIMENTAL
        );
      }
      const net = opts.networkName ?? "ca-sbx-egress";
      return {
        runArgs: [
          "--network",
          net,
          "--cap-add",
          "NET_ADMIN",
          "--cap-add",
          "NET_RAW"
        ],
        postStart: [],
        firewallScript: buildFirewallScriptForHosts(hosts),
        experimental: true
      };
    }
    default: {
      const bad = policy;
      throw new Error(`ca-sandbox: unknown network policy ${JSON.stringify(bad)}`);
    }
  }
}

// docker.ts
import { spawnSync } from "node:child_process";
var DOCKER_ENV = { ...process.env, MSYS_NO_PATHCONV: "1" };
var DEFAULT_DOCKER_TIMEOUT_MS = 12e4;
var DOCKER_OPERATION_TIMEOUTS_MS = Object.freeze({
  inspect: 3e4,
  ps: 3e4,
  images: 3e4,
  version: 3e4,
  info: 3e4,
  volume: 6e4,
  stop: 6e4,
  kill: 6e4,
  rm: 6e4,
  rmi: 12e4,
  network: 6e4,
  cp: 6e5,
  run: 9e5,
  create: 3e5,
  start: 3e5,
  exec: 18e5,
  build: 18e5,
  buildx: 18e5,
  pull: 18e5
});
function timeoutForArgs(args) {
  return DOCKER_OPERATION_TIMEOUTS_MS[args[0] ?? ""] ?? DEFAULT_DOCKER_TIMEOUT_MS;
}
var DOCKER_TIMEOUT_EXIT_CODE = 124;
function runDocker(args, extra = {}, options = {}) {
  const timeout = options.timeoutMs ?? timeoutForArgs(args);
  const spawn = options.spawn ?? spawnSync;
  const r = spawn("docker", args, {
    encoding: "utf8",
    env: DOCKER_ENV,
    ...extra,
    timeout,
    killSignal: "SIGKILL"
  });
  const timedOut = r.error?.code === "ETIMEDOUT" || r.status === null && r.signal !== null && r.signal !== void 0;
  if (timedOut) {
    return {
      code: DOCKER_TIMEOUT_EXIT_CODE,
      stdout: r.stdout ?? "",
      stderr: `${r.stderr ?? ""}ca-sandbox: \`docker ${args[0] ?? ""}\` timed out after ${timeout}ms and was killed (issue #394).`,
      timedOut: true
    };
  }
  return {
    code: r.status ?? 1,
    stdout: r.stdout ?? "",
    stderr: r.stderr ?? (r.error ? String(r.error) : "")
  };
}
function defaultDockerRun(args) {
  return runDocker(args);
}

// run.ts
var SANDBOX_LABEL = "ca.sandbox=1";
var SANDBOX_USER = "1000:1000";
function hardeningFlags() {
  return [
    "--user",
    SANDBOX_USER,
    "--read-only",
    // --read-only makes a writable /tmp essential; the `--tmpfs <path>` short
    // form is the idiomatic, spec-named flag. (run.ts also renders a tmpfs /tmp
    // via buildMountArgs; the duplicate is harmless and robust across engines.)
    "--tmpfs",
    "/tmp",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
    "--pids-limit",
    "512",
    "--memory",
    "4g",
    "--cpus",
    "2"
  ];
}

// claude-inside.ts
var CLAUDE_HOME = "/home/sbx";
var TOKEN_ENV_VAR = "CLAUDE_CODE_OAUTH_TOKEN";
var ANTHROPIC_ALLOW_HOSTS = [
  "api.anthropic.com",
  "console.anthropic.com",
  "statsig.anthropic.com"
];
var TokenCoMountRejectedError = class extends Error {
  constructor(detail) {
    super(
      `ca-sandbox: refusing to co-mount the Claude token/credential volume with an untrusted-code run (${detail}). An OAuth token in a box running untrusted code is stealable (env + $HOME/.claude/.credentials.json); --with-claude NEVER shares the token volume with the source volume. Run Claude in its own box, offline or Anthropic-domains-only. See ca-sandbox-claude-auth.md.`
    );
    this.name = "TokenCoMountRejectedError";
  }
};
function resolveClaudeNetworkPlan(policy) {
  switch (policy) {
    case "offline":
      return { runArgs: applyNetworkPolicy("offline").runArgs };
    case "anthropic-only": {
      const plan = applyNetworkPolicy("egress-allowlist", {
        allowHosts: [...ANTHROPIC_ALLOW_HOSTS],
        networkName: "ca-sbx-claude-egress"
      });
      if (!plan.firewallScript) {
        throw new Error(
          "ca-sandbox: --with-claude refuses 'anthropic-only' without a firewall script - the posture grants NET_ADMIN/NET_RAW, so an unenforced allowlist is worse than no allowlist. Use 'offline', the guaranteed posture."
        );
      }
      return { runArgs: plan.runArgs, firewallScript: plan.firewallScript };
    }
    default: {
      const bad = policy;
      throw new Error(
        `ca-sandbox: --with-claude refuses egress policy ${JSON.stringify(bad)} \u2014 only 'offline' or 'anthropic-only' are permitted (a token-bearing box must never get wide-open egress). See ca-sandbox-claude-auth.md.`
      );
    }
  }
}
function buildClaudeRunArgs(opts) {
  const { image, token, homeVolume } = opts;
  if (!image) throw new Error("ca-sandbox: --with-claude requires a non-empty image");
  if (!token) throw new Error("ca-sandbox: --with-claude requires a non-empty token");
  if (!homeVolume) throw new Error("ca-sandbox: --with-claude requires a non-empty home volume");
  if (opts.sourceVolume) {
    throw new TokenCoMountRejectedError(
      `sourceVolume=${JSON.stringify(opts.sourceVolume)} alongside homeVolume=${JSON.stringify(
        homeVolume
      )}`
    );
  }
  const netPolicy = opts.netPolicy ?? "offline";
  const networkArgs = resolveClaudeNetworkPlan(netPolicy).runArgs;
  const mountSpecs = [
    { type: "volume", source: homeVolume, target: CLAUDE_HOME },
    { type: "tmpfs", target: "/tmp" }
  ];
  const mountArgs = buildMountArgs(mountSpecs);
  const labels = [SANDBOX_LABEL, ...opts.extraLabels ?? []];
  const labelArgs = labels.flatMap((l) => ["--label", l]);
  const nameArgs = opts.namePrefix ? ["--name", `${opts.namePrefix}-${Math.random().toString(16).slice(2, 10)}`] : [];
  const command = opts.command ?? ["sleep", "infinity"];
  return [
    "run",
    "-d",
    ...nameArgs,
    // Auth: env-inject the token + point HOME at the persisted claude home.
    "-e",
    `${TOKEN_ENV_VAR}=${token}`,
    "-e",
    `HOME=${CLAUDE_HOME}`,
    // Belt-and-braces: keep the autoupdater off at run time too (the image already
    // sets it, but a run-time override would otherwise re-enable it).
    "-e",
    "DISABLE_AUTOUPDATER=1",
    ...mountArgs,
    "--workdir",
    CLAUDE_HOME,
    // The SAME shared hardening block as the ordinary sandbox (architecture-002),
    // spliced from run.ts's hardeningFlags() so the token-bearing box can never
    // drift to a softer lockdown. Non-root + every capability dropped + read-only
    // root + tmpfs /tmp + no-new-privileges + resource caps. The image chowns
    // CLAUDE_HOME to this uid and the named volume mounts over HOME, so the
    // .claude credential store stays writable under the read-only root.
    ...hardeningFlags(),
    ...networkArgs,
    ...labelArgs,
    image,
    ...command
  ];
}
function claudeFirewallScript(opts) {
  return resolveClaudeNetworkPlan(opts.netPolicy ?? "offline").firewallScript;
}
function runClaudeInside(opts, dockerRun = defaultDockerRun) {
  const args = buildClaudeRunArgs(opts);
  const r = dockerRun(args);
  if (r.code !== 0) {
    throw new Error(
      `ca-sandbox: docker run failed for --with-claude image ${opts.image} (exit ${r.code})
${(r.stderr || r.stdout).slice(-2e3)}`
    );
  }
  const id = r.stdout.trim();
  const firewallScript = claudeFirewallScript(opts);
  if (firewallScript === void 0) return id;
  const applied = dockerRun(["exec", "--user", "root", id, "sh", "-c", firewallScript]);
  if (applied.code !== 0) {
    dockerRun(["rm", "-f", id]);
    throw new Error(
      `ca-sandbox: --with-claude could not apply the egress firewall to ${id} (exit ${applied.code}); the container has been destroyed rather than left running with NET_ADMIN and no rules around a live token.
${(applied.stderr || applied.stdout).slice(-2e3)}`
    );
  }
  return id;
}

// claude-inside-cli.ts
var USAGE_ERROR_EXIT = 2;
var NET_POLICIES = ["offline", "anthropic-only"];
var ClaudeCliError = class extends Error {
};
function parseClaudeCli(argv) {
  let image = "";
  let homeVolume = "";
  let netPolicy = "offline";
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    const value = () => {
      const v = argv[++i];
      if (v === void 0) throw new ClaudeCliError(`${flag} requires a value`);
      return v;
    };
    switch (flag) {
      case "--image":
        image = value();
        break;
      case "--home-volume":
        homeVolume = value();
        break;
      case "--net": {
        const v = value();
        if (!NET_POLICIES.includes(v)) {
          throw new ClaudeCliError(
            `--net must be one of ${NET_POLICIES.join(", ")} (got ${JSON.stringify(v)}). A token-bearing box never gets wide-open egress.`
          );
        }
        netPolicy = v;
        break;
      }
      // The token is env-only, deliberately. Naming the flag explicitly gives a
      // better refusal than "unknown flag" to someone reaching for the obvious
      // thing, and states WHY rather than just no.
      case "--token":
        throw new ClaudeCliError(
          `--token is refused: a process argument list is world-readable, so passing a credential there publishes it to every process on the host. Set ${TOKEN_ENV_VAR} in the environment instead.`
        );
      // The co-mount guard is structural in buildClaudeRunArgs; refusing the
      // flag here means the mistake is caught before a container is created.
      case "--source-volume":
        throw new ClaudeCliError(
          `--source-volume is refused: the token volume is NEVER co-mounted with an untrusted-code run (ADR-0007 / Spike B). Run the untrusted source in an ordinary sandbox instead.`
        );
      default:
        throw new ClaudeCliError(`unknown argument ${JSON.stringify(flag)}`);
    }
  }
  if (!image) throw new ClaudeCliError("--image is required");
  if (!homeVolume) throw new ClaudeCliError("--home-volume is required");
  return { image, homeVolume, netPolicy };
}
function usage() {
  return [
    "ca-sandbox claude-inside \u2014 start a Claude-Code-bearing sandbox box.",
    "",
    "  claude-inside --image <tag> --home-volume <name> [--net offline|anthropic-only]",
    "",
    `The OAuth token is read from ${TOKEN_ENV_VAR} in the environment. It is never`,
    "accepted on the command line: an argument list is world-readable.",
    "",
    "Sanctioned caller: the `sandbox-claude-inside` skill, whose five BLOCK gates",
    "(posture, image, token, run, teardown) are the reason this is not a",
    "`sandbox` subcommand."
  ].join("\n");
}
function runClaudeInsideCli(argv, env = process.env, deps = {}) {
  const out = deps.stdout ?? ((l) => process.stdout.write(`${l}
`));
  const err = deps.stderr ?? ((l) => process.stderr.write(`${l}
`));
  let parsed;
  try {
    parsed = parseClaudeCli(argv);
  } catch (e) {
    if (e instanceof ClaudeCliError) {
      err(`ca-sandbox: ${e.message}`);
      err(usage());
      return USAGE_ERROR_EXIT;
    }
    throw e;
  }
  const token = env[TOKEN_ENV_VAR];
  if (!token) {
    err(
      `ca-sandbox: ${TOKEN_ENV_VAR} is not set. The token is read from the environment and never from argv; see the sandbox-claude-inside skill for the approved store.`
    );
    return USAGE_ERROR_EXIT;
  }
  try {
    const id = (deps.run ?? runClaudeInside)(
      { image: parsed.image, homeVolume: parsed.homeVolume, netPolicy: parsed.netPolicy, token },
      deps.dockerRun ?? defaultDockerRun
    );
    out(id);
    return 0;
  } catch (e) {
    const prefix = e instanceof TokenCoMountRejectedError ? "co-mount refused" : "failed";
    err(`ca-sandbox: claude-inside ${prefix}: ${e instanceof Error ? e.message : String(e)}`);
    return 1;
  }
}
var _thisFile = fileURLToPath(import.meta.url);
var _entryFile = path.resolve(process.argv[1] ?? "");
if (_thisFile === _entryFile) {
  process.exit(runClaudeInsideCli(process.argv.slice(2)));
}
export {
  ClaudeCliError,
  USAGE_ERROR_EXIT,
  parseClaudeCli,
  runClaudeInsideCli,
  usage
};
