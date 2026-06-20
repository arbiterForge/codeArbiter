/**
 * claude-inside.ts — `--with-claude`: run Claude Code INSIDE a ca-sandbox box
 * (T-14, covers AC-12).
 *
 * Spike B (.codearbiter/spikes/ca-sandbox-claude-auth.md, CONFIRM-07) proved the
 * mechanism this module wires:
 *
 *   - Claude Code authenticates from an ENV-INJECTED CLAUDE_CODE_OAUTH_TOKEN
 *     (auth-precedence #5, from `claude setup-token`) — NO host bind of ~/.claude
 *     is required. A dummy token reaches the API and is rejected server-side with
 *     a real `401 Invalid bearer token`, proving the env var IS the auth path (the
 *     CLI read it, built a bearer header, and sent it); a valid token would
 *     authenticate the same way.
 *   - Session/credential state persists across a container restart via a docker
 *     NAMED VOLUME mounted at the in-container HOME (the Linux credential store is
 *     `$HOME/.claude/.credentials.json`, which lives inside that volume).
 *   - The image PINS the CLI (`@anthropic-ai/claude-code@X.Y.Z`) and sets
 *     `DISABLE_AUTOUPDATER=1` for reproducible images.
 *
 * THE HARD DEFAULT (the load-bearing Spike B caveat). An OAuth token injected into
 * a box running UNTRUSTED code is stealable by that code if it has any egress —
 * the token sits in the process env and, once `claude` authenticates, on disk at
 * `$HOME/.claude/.credentials.json` inside the volume. Anthropic's own
 * devcontainer doc warns a malicious project can exfiltrate anything in the
 * container, including the Claude Code credentials in ~/.claude. Therefore
 * `--with-claude` is NOT a free option; it is hard-defaulted to a hardened posture
 * and this module enforces it BY CONSTRUCTION:
 *
 *   - egress is `offline` (default) or `anthropic-only` (the experimental
 *     Anthropic-domains allowlist) — never wide-open;
 *   - the token/credential volume is NEVER co-mounted with an untrusted-code run
 *     (a run that also mounts the source volume at /work/repo) — buildClaudeRunArgs
 *     THROWS (TokenCoMountRejectedError) on that combination.
 *
 * Like run.ts / network.ts this module is PURE argv/script builders (so the
 * posture is unit-testable without docker); the caller shells docker. Windows
 * (Spike A/B): set MSYS_NO_PATHCONV=1 when shelling docker so `-e HOME=/...` and
 * container paths are not mangled by Git Bash path conversion.
 */
import { spawnSync } from "node:child_process";
import { buildMountArgs, type MountSpec } from "./mounts.ts";
import { applyNetworkPolicy } from "./network.ts";
import { SANDBOX_USER } from "./run.ts";

/**
 * The PINNED Claude Code CLI version baked into the sandbox image. Pinned (never
 * `@latest`) + DISABLE_AUTOUPDATER=1 for reproducible images. 2.1.183 is the
 * version Spike B (CONFIRM-07) installed and observed cleanly in node:22-slim.
 */
export const CLAUDE_CODE_VERSION = "2.1.183";
/** The npm package the image installs at the pinned version. */
export const CLAUDE_CODE_PACKAGE = "@anthropic-ai/claude-code";
/** Base image — node:22-slim installs the CLI cleanly (Spike B). */
export const CLAUDE_BASE_IMAGE = "node:22-slim";
/**
 * In-container HOME for the claude run. The named volume mounts here, so the
 * credential store `$HOME/.claude/.credentials.json` (and the rest of the .claude
 * tree) persists across restart on the volume — no host bind (Spike B).
 */
export const CLAUDE_HOME = "/home/sbx";
/** The env var Claude Code reads as auth-precedence #5 (Spike B). */
export const TOKEN_ENV_VAR = "CLAUDE_CODE_OAUTH_TOKEN";
/** The lifecycle/registry label every sandbox container carries (AC-11). */
export const SANDBOX_LABEL = "ca.sandbox=1";

// On Windows + Git Bash, `-e HOME=/...` and container paths handed to docker get
// mangled by MSYS path conversion; MSYS_NO_PATHCONV=1 disables it (Spike A/B).
const DOCKER_ENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

/**
 * The ONLY egress postures `--with-claude` permits. Both keep a stealable token
 * from leaving the box: `offline` has no interface at all; `anthropic-only` is the
 * (experimental) Anthropic-domains allowlist. A wide-open / arbitrary policy is
 * deliberately NOT in this union — it is a type error, and the runtime guard in
 * buildClaudeRunArgs rejects it too.
 */
export type ClaudeNetPolicy = "offline" | "anthropic-only";

/**
 * The Anthropic API/auth domains the `anthropic-only` allowlist permits. These are
 * the hosts `claude` must reach to authenticate and run inference. The allowlist
 * machinery itself is EXPERIMENTAL (Spike C: CDN drift + DNS-exfil hole) — for a
 * token-bearing box `offline` is the only GUARANTEED posture, so `anthropic-only`
 * is offered as the deliberate, narrowed alternative for interactive use.
 */
export const ANTHROPIC_ALLOW_HOSTS: readonly string[] = [
  "api.anthropic.com",
  "console.anthropic.com",
  "statsig.anthropic.com",
];

/** Error thrown when the token volume would be co-mounted with untrusted code. */
export class TokenCoMountRejectedError extends Error {
  constructor(detail: string) {
    super(
      `ca-sandbox: refusing to co-mount the Claude token/credential volume with an ` +
        `untrusted-code run (${detail}). An OAuth token in a box running untrusted ` +
        `code is stealable (env + $HOME/.claude/.credentials.json); --with-claude ` +
        `NEVER shares the token volume with the source volume. Run Claude in its own ` +
        `box, offline or Anthropic-domains-only. See ca-sandbox-claude-auth.md.`,
    );
    this.name = "TokenCoMountRejectedError";
  }
}

/** Options for buildClaudeImageDockerfile. */
export type ClaudeImageOptions = {
  /** Base image to install onto (default node:22-slim, proven by Spike B). */
  baseImage?: string;
  /** Pinned CLI version (default CLAUDE_CODE_VERSION). */
  version?: string;
};

/**
 * Build the Dockerfile that bakes a PINNED Claude Code CLI with the autoupdater
 * disabled. Pure (returns a string) so the pinning/autoupdater invariants are
 * unit-testable; the caller `docker build`s it.
 *
 * The autoupdater is disabled via image ENV so the pinned version stays put across
 * every run of the image (a floating CLI would defeat reproducibility and could
 * pull an unreviewed version into a token-bearing box).
 */
export function buildClaudeImageDockerfile(opts: ClaudeImageOptions = {}): string {
  const base = opts.baseImage ?? CLAUDE_BASE_IMAGE;
  const version = opts.version ?? CLAUDE_CODE_VERSION;
  return [
    `FROM ${base}`,
    `# ca-sandbox --with-claude image (T-14 / AC-12). Spike B (CONFIRM-07).`,
    `# Pin the CLI + disable the autoupdater so the image is reproducible and a`,
    `# token-bearing box never silently pulls an unreviewed CLI version.`,
    `ENV DISABLE_AUTOUPDATER=1`,
    `ENV HOME=${CLAUDE_HOME}`,
    `RUN npm install -g ${CLAUDE_CODE_PACKAGE}@${version}`,
    // A writable, persisted HOME for the .claude state (the named volume mounts
    // here at run time; the dir must exist + be writable by the run user). The box
    // runs NON-ROOT (uid 1000 — buildClaudeRunArgs passes --user 1000:1000, and
    // USER below makes that the image default too), so CLAUDE_HOME is chowned to
    // 1000:1000: a first-mounted named volume inherits this ownership, so the
    // credential store is writable even under --read-only --cap-drop ALL.
    `RUN mkdir -p ${CLAUDE_HOME}/.claude && chown -R 1000:1000 ${CLAUDE_HOME}`,
    `USER 1000:1000`,
    "",
  ].join("\n");
}

/** Options for buildClaudeRunArgs. */
export type ClaudeRunOptions = {
  /** The built claude image tag. */
  image: string;
  /** The OAuth token to env-inject (DUMMY in tests; never logged). */
  token: string;
  /** The docker NAMED VOLUME backing the in-container HOME (persists .claude). */
  homeVolume: string;
  /**
   * Egress posture — `offline` (default, GUARANTEED) or `anthropic-only` (the
   * experimental Anthropic-domains allowlist). Never wide-open. The default is the
   * hard default of Spike B's caveat.
   */
  netPolicy?: ClaudeNetPolicy;
  /**
   * The untrusted source volume. Supplying it is a HARD ERROR: --with-claude never
   * co-mounts the token volume with an untrusted-code run (Spike B caveat). The
   * parameter exists so the guard can reject the mistake explicitly rather than
   * silently producing an unsafe argv.
   */
  sourceVolume?: string;
  /** Extra `key=value` labels in addition to ca.sandbox=1 (e.g. a build marker). */
  extraLabels?: string[];
  /** Optional `--name` prefix; the container is named `<prefix>-<short-random>`. */
  namePrefix?: string;
  /** Command to run in the box (default: a keep-alive `sleep infinity`). */
  command?: string[];
};

/**
 * Resolve the egress run-args for a `--with-claude` posture. `offline` => no
 * interface at all; `anthropic-only` => the experimental egress allowlist scoped to
 * the Anthropic domains (custom bridge + NET_ADMIN/NET_RAW caps). Anything else is
 * a hard error — a token-bearing box must never get wide-open egress.
 */
function resolveClaudeNetworkArgs(policy: ClaudeNetPolicy): string[] {
  switch (policy) {
    case "offline":
      return applyNetworkPolicy("offline").runArgs;
    case "anthropic-only": {
      // The Anthropic-domains allowlist. The allowlist machinery is EXPERIMENTAL
      // (Spike C); offline is the only GUARANTEED posture for a token-bearing box.
      // The firewall script must still be applied INSIDE the box by the caller
      // (network.ts owns it); here we only contribute the run-time flags.
      return applyNetworkPolicy("egress-allowlist", {
        allowHosts: [...ANTHROPIC_ALLOW_HOSTS],
        networkName: "ca-sbx-claude-egress",
      }).runArgs;
    }
    default: {
      // Exhaustiveness: a non-hardened policy is rejected, never passed through.
      const bad: never = policy;
      throw new Error(
        `ca-sandbox: --with-claude refuses egress policy ${JSON.stringify(bad)} — ` +
          `only 'offline' or 'anthropic-only' are permitted (a token-bearing box ` +
          `must never get wide-open egress). See ca-sandbox-claude-auth.md.`,
      );
    }
  }
}

/**
 * Assemble the full `docker run` argv (everything AFTER `docker`) for a
 * `--with-claude` box. Pure: builds the array, runs nothing. Enforces the hardened
 * posture by construction:
 *
 *   - the OAuth token is env-injected (`-e CLAUDE_CODE_OAUTH_TOKEN=...`) — the auth
 *     path, no host bind of ~/.claude;
 *   - HOME is set to the in-container claude home and backed by a NAMED VOLUME
 *     (via buildMountArgs, which throws on any bind) so .claude persists on the
 *     volume, never on the host;
 *   - egress is offline (default) or anthropic-only — never wide-open;
 *   - the structural isolation flags (non-root, read-only root, cap-drop, etc.)
 *     match run.ts so the token box is as locked-down as any sandbox.
 *
 * @throws if image / token / homeVolume is empty.
 * @throws TokenCoMountRejectedError if `sourceVolume` is supplied (the token
 *   volume must never be co-mounted with an untrusted-code run).
 * @throws on a non-hardened net policy.
 */
export function buildClaudeRunArgs(opts: ClaudeRunOptions): string[] {
  const { image, token, homeVolume } = opts;
  if (!image) throw new Error("ca-sandbox: --with-claude requires a non-empty image");
  if (!token) throw new Error("ca-sandbox: --with-claude requires a non-empty token");
  if (!homeVolume) throw new Error("ca-sandbox: --with-claude requires a non-empty home volume");

  // THE LOAD-BEARING GUARD: never co-mount the token volume with untrusted code.
  if (opts.sourceVolume) {
    throw new TokenCoMountRejectedError(
      `sourceVolume=${JSON.stringify(opts.sourceVolume)} alongside homeVolume=${JSON.stringify(
        homeVolume,
      )}`,
    );
  }

  const netPolicy: ClaudeNetPolicy = opts.netPolicy ?? "offline";
  const networkArgs = resolveClaudeNetworkArgs(netPolicy);

  // Mounts go through the ONE chokepoint (mounts.ts): the home named volume at
  // HOME (so .claude persists) and a tmpfs /tmp for a read-only root. No bind can
  // be hand-rolled here — buildMountArgs throws on any bind spec.
  const mountSpecs: MountSpec[] = [
    { type: "volume", source: homeVolume, target: CLAUDE_HOME },
    { type: "tmpfs", target: "/tmp" },
  ];
  const mountArgs = buildMountArgs(mountSpecs);

  const labels = [SANDBOX_LABEL, ...(opts.extraLabels ?? [])];
  const labelArgs = labels.flatMap((l) => ["--label", l]);

  const nameArgs = opts.namePrefix
    ? ["--name", `${opts.namePrefix}-${Math.random().toString(16).slice(2, 10)}`]
    : [];

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
    // Non-root + drop every capability: the SAME structural lockdown as run.ts so
    // the token-bearing box is no softer than an ordinary sandbox. The image
    // chowns CLAUDE_HOME to this uid, so the named-volume HOME is writable for the
    // .claude credential store even under the read-only root below.
    "--user",
    SANDBOX_USER,
    "--cap-drop",
    "ALL",
    // Read-only root + a tmpfs /tmp: the same structural lockdown as run.ts. (HOME
    // is writable because the named volume is mounted over it.)
    "--read-only",
    "--tmpfs",
    "/tmp",
    "--security-opt",
    "no-new-privileges",
    "--pids-limit",
    "512",
    "--memory",
    "4g",
    "--cpus",
    "2",
    ...networkArgs,
    ...labelArgs,
    image,
    ...command,
  ];
}

export type ClaudeRunResult = { code: number; stdout: string; stderr: string };

function defaultDockerRun(args: string[]): ClaudeRunResult {
  const r = spawnSync("docker", args, { encoding: "utf8", env: DOCKER_ENV });
  return {
    code: r.status ?? 1,
    stdout: r.stdout ?? "",
    stderr: r.stderr ?? (r.error ? String(r.error) : ""),
  };
}

/**
 * Start a `--with-claude` box and return the container id. Thin shell over
 * buildClaudeRunArgs (which holds every safety guarantee). The docker runner is
 * injectable so the dispatch is unit-testable without real docker.
 *
 * @throws every guarantee of buildClaudeRunArgs, plus on a non-zero `docker run`.
 */
export function runClaudeInside(
  opts: ClaudeRunOptions,
  dockerRun: (args: string[]) => ClaudeRunResult = defaultDockerRun,
): string {
  const args = buildClaudeRunArgs(opts);
  const r = dockerRun(args);
  if (r.code !== 0) {
    throw new Error(
      `ca-sandbox: docker run failed for --with-claude image ${opts.image} (exit ${r.code})\n` +
        `${(r.stderr || r.stdout).slice(-2000)}`,
    );
  }
  return r.stdout.trim();
}
