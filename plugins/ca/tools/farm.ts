#!/usr/bin/env node
/**
 * farm.ts — codeArbiter's zero-LLM-token dispatcher.
 *
 * Papa Claude (your interactive Claude Code session) does the judgment work:
 * brainstorm -> spec -> write the FAILING tests into the repo -> emit plan.json.
 * Then he runs THIS script and walks away. No model calls happen in here — the
 * only model cost is the cheap Zen worker invoked per task.
 *
 * For each task the dispatcher:
 *   1. cuts an isolated git worktree off the *current integration HEAD*
 *      (so a task inherits the merged output of its dependencies),
 *   2. calls the Zen/DeepSeek API directly whose only job is to make the
 *      failing test pass,
 *   3. enforces filesInScope — any file outside the allowed set fails the task,
 *   4. enforces the gate deterministically (the test must go green, suite stays
 *      green, lint/types pass — whatever you put in gate.commands),
 *   5. retries with the gate failure fed back in, up to maxRetries,
 *   6. on success commits + merges into the integration branch via a dedicated
 *      integration worktree (never touches the main repo checkout),
 *   7. on exhaustion leaves the worktree in place and ESCALATES the task.
 *
 * It never merges to main — codeArbiter's PR-only rule is preserved. You review
 * the integration branch and open the PR yourself.
 */
import { spawn } from "node:child_process";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";

// --------------------------------------------------------------------------
// Types — the handoff contract. Claude emits plan.json conforming to this.
// --------------------------------------------------------------------------
type Task = {
  id: string;
  description: string;
  deps?: string[];
  filesInScope: string[];
  test: { path: string };
  gate: { commands: string[] };
  context?: string;
  maxRetries?: number;
};
type Plan = {
  meta: { name: string; repo?: string; model?: string; apiBaseUrl?: string };
  tasks: Task[];
};

const ENV = {
  // Model: plan.meta.model (set by subagent-driven-development before dispatch),
  // then FARM_MODEL env var override. Fails at startup if neither is set.
  model: process.env.FARM_MODEL ?? null,
  apiBaseUrl: process.env.FARM_API_BASE_URL ?? null,
  apiKey: process.env.FARM_API_KEY ?? null,
  concurrency: Number(process.env.FARM_CONCURRENCY ?? 4),
  maxRetries: Number(process.env.FARM_MAX_RETRIES ?? 2),
  base: process.env.FARM_BASE_BRANCH ?? "main",
  integration: process.env.FARM_INTEGRATION_BRANCH ?? "farm/integration",
  worktreeRoot: process.env.FARM_WORKTREE_ROOT ?? ".farm/worktrees",
  reportDir: process.env.FARM_REPORT_DIR ?? ".farm",
};

// --------------------------------------------------------------------------
// process helpers
// --------------------------------------------------------------------------
function run(cmd: string, args: string[], cwd?: string) {
  return new Promise<{ code: number; out: string }>((resolve) => {
    const c = spawn(cmd, args, { cwd, env: process.env });
    let out = "";
    c.stdout.on("data", (d) => (out += d));
    c.stderr.on("data", (d) => (out += d));
    c.on("close", (code) => resolve({ code: code ?? 1, out }));
  });
}
const git = (args: string[], cwd?: string) => run("git", args, cwd);

// --------------------------------------------------------------------------
// gate — pure determinism, no model
// --------------------------------------------------------------------------
async function runGate(cwd: string, commands: string[]) {
  for (const cmd of commands) {
    const r = await run("bash", ["-lc", cmd], cwd);
    if (r.code !== 0) return { ok: false as const, failed: cmd, tail: r.out.slice(-3500) };
  }
  return { ok: true as const };
}

// --------------------------------------------------------------------------
// worker — direct OpenAI-compatible API call (Bug #3 fix)
// Note: at implementation time, also check github.com/sst/opencode for any
// TypeScript SDK or MCP server — if a typed run_task() interface exists with
// structured file-change output, it's worth comparing against this approach.
// --------------------------------------------------------------------------
function buildPrompt(t: Task, priorFailure?: string) {
  return [
    `Implement exactly ONE task. Your only goal: make the failing test pass.`,
    ``,
    `TASK: ${t.description}`,
    t.context ? `\nCONTEXT:\n${t.context}\n` : ``,
    `The failing test is at: ${t.test.path}`,
    `Make it pass WITHOUT modifying, deleting, or weakening that test.`,
    ``,
    `You may ONLY create or edit these files:`,
    ...t.filesInScope.map((f) => `  - ${f}`),
    `Touch nothing else. Do not run git. Do not install global packages.`,
    ``,
    `Respond with ONLY the files you need to create or modify.`,
    `For each file, use this exact format:`,
    ``,
    `\`\`\`typescript`,
    `// path: src/example.ts`,
    `<complete file content here>`,
    `\`\`\``,
    ``,
    `Do not include any explanation outside the code blocks.`,
    priorFailure
      ? `\nYour previous attempt FAILED the gate. Fix it.\nGate output (tail):\n${priorFailure}`
      : ``,
  ].join("\n");
}

async function runWorker(
  cwd: string,
  prompt: string,
  model: string,
  apiBaseUrl: string,
  apiKey: string,
): Promise<{ ok: boolean; filesWritten: string[]; error?: string }> {
  let resp: Response;
  try {
    resp = await fetch(`${apiBaseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: [{ role: "user", content: prompt }],
      }),
    });
  } catch (e) {
    return { ok: false, filesWritten: [], error: `fetch failed: ${e}` };
  }

  if (!resp.ok) {
    const body = await resp.text().catch(() => "(unreadable)");
    return { ok: false, filesWritten: [], error: `API ${resp.status}: ${body.slice(0, 500)}` };
  }

  const data = await resp.json() as {
    choices?: Array<{ message?: { content?: string } }>;
  };
  const content = data.choices?.[0]?.message?.content ?? "";

  // Parse fenced code blocks with `// path: <file>` as first line
  const filesWritten: string[] = [];
  const blockRe = /```[a-z]*\n\/\/ path: ([^\n]+)\n([\s\S]*?)```/g;
  let match: RegExpExecArray | null;
  while ((match = blockRe.exec(content)) !== null) {
    const [, filePath, fileContent] = match;
    const absPath = path.resolve(cwd, filePath.trim());
    await mkdir(path.dirname(absPath), { recursive: true });
    await writeFile(absPath, fileContent);
    filesWritten.push(filePath.trim());
  }

  if (filesWritten.length === 0) {
    return { ok: false, filesWritten: [], error: "no parseable file blocks in response" };
  }

  return { ok: true, filesWritten };
}

// --------------------------------------------------------------------------
// drift check — Bug #1 fix
// Catches both modified tracked files and new untracked files.
// git status --porcelain groups untracked files by directory; use ls-files
// for new files to get individual paths.
// --------------------------------------------------------------------------
async function checkDrift(cwd: string, filesInScope: string[]): Promise<string[]> {
  // Modified/deleted tracked files
  const tracked = await git(["diff", "--name-only", "HEAD"], cwd);
  // New untracked files (individual paths, not directories)
  const untracked = await git(
    ["ls-files", "--others", "--exclude-standard", "-z"],
    cwd,
  );

  const changed: string[] = [];
  if (tracked.code === 0) {
    changed.push(...tracked.out.trim().split("\n").filter(Boolean));
  }
  if (untracked.code === 0) {
    changed.push(...untracked.out.split("\0").filter(Boolean));
  }

  const allowed = new Set(filesInScope);
  return changed.filter((f) => !allowed.has(f));
}

// --------------------------------------------------------------------------
// per-task lifecycle
// --------------------------------------------------------------------------
type Result = {
  id: string;
  status: "green" | "escalate";
  attempts: number;
  branch: string;
  worktree: string;
  note?: string;
};

// Integration merges happen inside a dedicated worktree — Bug #2 fix.
// mergeChain serializes access to that worktree.
let mergeChain: Promise<unknown> = Promise.resolve();
let integrationWorktree: string;

function withMergeLock<T>(fn: () => Promise<T>): Promise<T> {
  const next = mergeChain.then(fn, fn);
  mergeChain = next.catch(() => {});
  return next;
}

async function runTask(t: Task, model: string, apiBaseUrl: string, apiKey: string): Promise<Result> {
  const branch = `farm/${t.id}`;
  const wt = path.resolve(ENV.worktreeRoot, t.id);
  const limit = t.maxRetries ?? ENV.maxRetries;

  await git(["worktree", "add", "-b", branch, wt, ENV.integration]);

  let priorFailure: string | undefined;
  for (let attempt = 1; attempt <= limit + 1; attempt++) {
    const worker = await runWorker(wt, buildPrompt(t, priorFailure), model, apiBaseUrl, apiKey);

    if (!worker.ok) {
      priorFailure = `worker error: ${worker.error}`;
      continue;
    }

    // Bug #1 fix: enforce filesInScope
    const driftFiles = await checkDrift(wt, t.filesInScope);
    if (driftFiles.length > 0) {
      await git(["checkout", "."], wt);
      return {
        id: t.id,
        status: "escalate",
        attempts: attempt,
        branch,
        worktree: wt,
        note: `drift: ${driftFiles.join(", ")}`,
      };
    }

    const gate = await runGate(wt, t.gate.commands);

    if (gate.ok) {
      await git(["add", "-A"], wt);
      const commitResult = await git(
        ["-c", "commit.gpgsign=false", "commit", "-m", `farm(${t.id}): ${t.description}`],
        wt,
      );
      if (commitResult.code !== 0) {
        return {
          id: t.id,
          status: "escalate" as const,
          attempts: attempt,
          branch,
          worktree: wt,
          note: `commit failed: ${commitResult.out.slice(0, 200)}`,
        };
      }
      // Bug #2 fix: merge into dedicated integration worktree, not main checkout
      const merged = await withMergeLock(async () => {
        const m = await git(["merge", "--no-ff", "-m", `merge ${t.id}`, branch], integrationWorktree);
        if (m.code !== 0) {
          await git(["merge", "--abort"], integrationWorktree);
          return false;
        }
        return true;
      });
      if (!merged) {
        return {
          id: t.id,
          status: "escalate",
          attempts: attempt,
          branch,
          worktree: wt,
          note: "merge conflict vs integration branch",
        };
      }
      await git(["worktree", "remove", "--force", wt]).catch(() => {});
      return { id: t.id, status: "green", attempts: attempt, branch, worktree: wt };
    }
    priorFailure = `failed: ${gate.failed}\n${gate.tail}`;
  }
  // worktree intentionally left in place for Claude to inspect
  return {
    id: t.id,
    status: "escalate",
    attempts: limit + 1,
    branch,
    worktree: wt,
    note: priorFailure?.split("\n")[0],
  };
}

// --------------------------------------------------------------------------
// DAG scheduler with a concurrency cap
// --------------------------------------------------------------------------
async function main() {
  const planPath = process.argv[2] ?? "plan.json";
  const plan = JSON.parse(await readFile(planPath, "utf8")) as Plan;
  validate(plan);

  // Resolve model — no hardcoded default (Bug #3 design)
  const model = ENV.model ?? plan.meta.model;
  const apiBaseUrl = ENV.apiBaseUrl ?? plan.meta.apiBaseUrl;
  const apiKey = ENV.apiKey;

  if (!model) {
    console.error(
      "Error: No model configured.\n" +
      "Set FARM_MODEL env var, or run /ca:sprint --farm to trigger automatic model selection.\n" +
      "See .codearbiter/farm.md for setup instructions.",
    );
    process.exit(1);
  }
  if (!apiBaseUrl) {
    console.error(
      "Error: No API base URL configured.\n" +
      "Set FARM_API_BASE_URL env var or run /ca:sprint --farm.\n" +
      "See .codearbiter/farm.md for setup instructions.",
    );
    process.exit(1);
  }
  if (!apiKey) {
    console.error(
      "Error: FARM_API_KEY is not set.\n" +
      "See .codearbiter/farm.md for setup instructions.",
    );
    process.exit(1);
  }

  await mkdir(ENV.worktreeRoot, { recursive: true });
  await mkdir(ENV.reportDir, { recursive: true });

  // Reset integration branch to base
  const branchResult = await git(["branch", "-f", ENV.integration, ENV.base]);
  if (branchResult.code !== 0) {
    console.error(`Error: could not create integration branch '${ENV.integration}' from '${ENV.base}'.\n${branchResult.out}`);
    process.exit(1);
  }

  // Bug #2 fix: dedicated integration worktree — merges never touch main checkout
  integrationWorktree = path.resolve(".farm/integration-wt");
  await mkdir(path.dirname(integrationWorktree), { recursive: true });
  // Remove stale worktree if it exists
  await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {});
  const wtResult = await git(["worktree", "add", integrationWorktree, ENV.integration]);
  if (wtResult.code !== 0) {
    console.error(`Error: could not create integration worktree.\n${wtResult.out}`);
    process.exit(1);
  }

  const byId = new Map(plan.tasks.map((t) => [t.id, t]));
  const done = new Map<string, Result>();
  const escalated = new Set<string>();
  const pending = new Set(plan.tasks.map((t) => t.id));
  const running = new Map<string, Promise<{ id: string; r: Result }>>();

  const ready = () =>
    [...pending].filter((id) => {
      const deps = byId.get(id)!.deps ?? [];
      if (deps.some((d) => escalated.has(d))) return false;
      return deps.every((d) => done.get(d)?.status === "green");
    });

  while (pending.size > 0 || running.size > 0) {
    for (const id of ready()) {
      if (running.size >= ENV.concurrency) break;
      pending.delete(id);
      running.set(
        id,
        runTask(byId.get(id)!, model, apiBaseUrl, apiKey).then((r) => ({ id, r })),
      );
    }
    if (running.size === 0) break;
    const { id, r } = await Promise.race(running.values());
    running.delete(id);
    done.set(id, r);
    if (r.status === "escalate") escalated.add(id);
  }

  const blocked = [...pending].map((id) => ({ id }));
  await writeReport(plan, [...done.values()], blocked);

  // Teardown integration worktree
  await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {});

  const esc = [...done.values()].filter((r) => r.status === "escalate").length;
  const green = [...done.values()].filter((r) => r.status === "green").length;
  const exitCode = esc || blocked.length ? 2 : 0;
  const summary = [
    `\nDone. green=${green} escalate=${esc} blocked=${blocked.length}`,
    `Integration: ${ENV.integration}  ->  review & PR to ${ENV.base}`,
    `Report: ${path.join(ENV.reportDir, "farm-report.md")}`,
    "",
  ].join("\n");
  // Flush stdout before exiting so piped consumers see the output
  await new Promise<void>((resolve) =>
    process.stdout.write(summary, () => resolve()),
  );
  process.exit(exitCode);
}

function validate(plan: Plan) {
  const ids = new Set<string>();
  for (const t of plan.tasks) {
    if (ids.has(t.id)) throw new Error(`duplicate task id: ${t.id}`);
    ids.add(t.id);
  }
  for (const t of plan.tasks)
    for (const d of t.deps ?? [])
      if (!ids.has(d)) throw new Error(`task ${t.id} depends on unknown task ${d}`);
}

async function writeReport(plan: Plan, results: Result[], blocked: { id: string }[]) {
  await writeFile(
    path.join(ENV.reportDir, "farm-report.json"),
    JSON.stringify(
      { plan: plan.meta, results, blocked, ts: new Date().toISOString() },
      null,
      2,
    ),
  );
  const md = [
    `# Farm report — ${plan.meta.name}`,
    ``,
    `| task | status | attempts | branch | note |`,
    `| --- | --- | --- | --- | --- |`,
    ...results.map(
      (r) =>
        `| ${r.id} | ${r.status} | ${r.attempts} | ${r.branch} | ${r.note ?? ""} |`,
    ),
    ...blocked.map((b) => `| ${b.id} | blocked | 0 | — | dependency escalated |`),
    ``,
    `## Escalations — handle only these`,
    ...results
      .filter((r) => r.status === "escalate")
      .map(
        (r) =>
          `- **${r.id}** — worktree at \`${r.worktree}\`, branch \`${r.branch}\`. ${r.note ?? ""}`,
      ),
  ].join("\n");
  await writeFile(path.join(ENV.reportDir, "farm-report.md"), md);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
