#!/usr/bin/env node
#!/usr/bin/env node

// farm.ts
import { spawn } from "node:child_process";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
var ENV = {
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
  reportDir: process.env.FARM_REPORT_DIR ?? ".farm"
};
function run(cmd, args, cwd) {
  return new Promise((resolve) => {
    const c = spawn(cmd, args, { cwd, env: process.env });
    let out = "";
    c.stdout.on("data", (d) => out += d);
    c.stderr.on("data", (d) => out += d);
    c.on("close", (code) => resolve({ code: code ?? 1, out }));
  });
}
var git = (args, cwd) => run("git", args, cwd);
async function runGate(cwd, commands) {
  for (const cmd of commands) {
    const r = await run("bash", ["-lc", cmd], cwd);
    if (r.code !== 0) return { ok: false, failed: cmd, tail: r.out.slice(-3500) };
  }
  return { ok: true };
}
function buildPrompt(t, priorFailure) {
  return [
    `Implement exactly ONE task. Your only goal: make the failing test pass.`,
    ``,
    `TASK: ${t.description}`,
    t.context ? `
CONTEXT:
${t.context}
` : ``,
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
    priorFailure ? `
Your previous attempt FAILED the gate. Fix it.
Gate output (tail):
${priorFailure}` : ``
  ].join("\n");
}
async function runWorker(cwd, prompt, model, apiBaseUrl, apiKey) {
  let resp;
  try {
    resp = await fetch(`${apiBaseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model,
        messages: [{ role: "user", content: prompt }]
      })
    });
  } catch (e) {
    return { ok: false, filesWritten: [], error: `fetch failed: ${e}` };
  }
  if (!resp.ok) {
    const body = await resp.text().catch(() => "(unreadable)");
    return { ok: false, filesWritten: [], error: `API ${resp.status}: ${body.slice(0, 500)}` };
  }
  const data = await resp.json();
  const content = data.choices?.[0]?.message?.content ?? "";
  const filesWritten = [];
  const blockRe = /```[a-z]*\n\/\/ path: ([^\n]+)\n([\s\S]*?)```/g;
  let match;
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
async function checkDrift(cwd, filesInScope) {
  const tracked = await git(["diff", "--name-only", "HEAD"], cwd);
  const untracked = await git(
    ["ls-files", "--others", "--exclude-standard", "-z"],
    cwd
  );
  const changed = [];
  if (tracked.code === 0) {
    changed.push(...tracked.out.trim().split("\n").filter(Boolean));
  }
  if (untracked.code === 0) {
    changed.push(...untracked.out.split("\0").filter(Boolean));
  }
  const allowed = new Set(filesInScope);
  return changed.filter((f) => !allowed.has(f));
}
var mergeChain = Promise.resolve();
var integrationWorktree;
function withMergeLock(fn) {
  const next = mergeChain.then(fn, fn);
  mergeChain = next.catch(() => {
  });
  return next;
}
async function runTask(t, model, apiBaseUrl, apiKey) {
  const branch = `farm/${t.id}`;
  const wt = path.resolve(ENV.worktreeRoot, t.id);
  const limit = t.maxRetries ?? ENV.maxRetries;
  await git(["worktree", "add", "-b", branch, wt, ENV.integration]);
  let priorFailure;
  for (let attempt = 1; attempt <= limit + 1; attempt++) {
    const worker = await runWorker(wt, buildPrompt(t, priorFailure), model, apiBaseUrl, apiKey);
    if (!worker.ok) {
      priorFailure = `worker error: ${worker.error}`;
      continue;
    }
    const driftFiles = await checkDrift(wt, t.filesInScope);
    if (driftFiles.length > 0) {
      await git(["checkout", "."], wt);
      return {
        id: t.id,
        status: "escalate",
        attempts: attempt,
        branch,
        worktree: wt,
        note: `drift: ${driftFiles.join(", ")}`
      };
    }
    const gate = await runGate(wt, t.gate.commands);
    if (gate.ok) {
      await git(["add", "-A"], wt);
      const commitResult = await git(
        ["-c", "commit.gpgsign=false", "commit", "-m", `farm(${t.id}): ${t.description}`],
        wt
      );
      if (commitResult.code !== 0) {
        return {
          id: t.id,
          status: "escalate",
          attempts: attempt,
          branch,
          worktree: wt,
          note: `commit failed: ${commitResult.out.slice(0, 200)}`
        };
      }
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
          note: "merge conflict vs integration branch"
        };
      }
      await git(["worktree", "remove", "--force", wt]).catch(() => {
      });
      return { id: t.id, status: "green", attempts: attempt, branch, worktree: wt };
    }
    priorFailure = `failed: ${gate.failed}
${gate.tail}`;
  }
  return {
    id: t.id,
    status: "escalate",
    attempts: limit + 1,
    branch,
    worktree: wt,
    note: priorFailure?.split("\n")[0]
  };
}
async function main() {
  const planPath = process.argv[2] ?? "plan.json";
  const plan = JSON.parse(await readFile(planPath, "utf8"));
  validate(plan);
  const model = ENV.model ?? plan.meta.model;
  const apiBaseUrl = ENV.apiBaseUrl ?? plan.meta.apiBaseUrl;
  const apiKey = ENV.apiKey;
  if (!model) {
    console.error(
      "Error: No model configured.\nSet FARM_MODEL env var, or run /ca:sprint --farm to trigger automatic model selection.\nSee .codearbiter/farm.md for setup instructions."
    );
    process.exit(1);
  }
  if (!apiBaseUrl) {
    console.error(
      "Error: No API base URL configured.\nSet FARM_API_BASE_URL env var or run /ca:sprint --farm.\nSee .codearbiter/farm.md for setup instructions."
    );
    process.exit(1);
  }
  if (!apiKey) {
    console.error(
      "Error: FARM_API_KEY is not set.\nSee .codearbiter/farm.md for setup instructions."
    );
    process.exit(1);
  }
  await mkdir(ENV.worktreeRoot, { recursive: true });
  await mkdir(ENV.reportDir, { recursive: true });
  const branchResult = await git(["branch", "-f", ENV.integration, ENV.base]);
  if (branchResult.code !== 0) {
    console.error(`Error: could not create integration branch '${ENV.integration}' from '${ENV.base}'.
${branchResult.out}`);
    process.exit(1);
  }
  integrationWorktree = path.resolve(".farm/integration-wt");
  await mkdir(path.dirname(integrationWorktree), { recursive: true });
  await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {
  });
  const wtResult = await git(["worktree", "add", integrationWorktree, ENV.integration]);
  if (wtResult.code !== 0) {
    console.error(`Error: could not create integration worktree.
${wtResult.out}`);
    process.exit(1);
  }
  const byId = new Map(plan.tasks.map((t) => [t.id, t]));
  const done = /* @__PURE__ */ new Map();
  const escalated = /* @__PURE__ */ new Set();
  const pending = new Set(plan.tasks.map((t) => t.id));
  const running = /* @__PURE__ */ new Map();
  const ready = () => [...pending].filter((id) => {
    const deps = byId.get(id).deps ?? [];
    if (deps.some((d) => escalated.has(d))) return false;
    return deps.every((d) => done.get(d)?.status === "green");
  });
  while (pending.size > 0 || running.size > 0) {
    for (const id2 of ready()) {
      if (running.size >= ENV.concurrency) break;
      pending.delete(id2);
      running.set(
        id2,
        runTask(byId.get(id2), model, apiBaseUrl, apiKey).then((r2) => ({ id: id2, r: r2 }))
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
  await git(["worktree", "remove", "--force", integrationWorktree]).catch(() => {
  });
  const esc = [...done.values()].filter((r) => r.status === "escalate").length;
  const green = [...done.values()].filter((r) => r.status === "green").length;
  const exitCode = esc || blocked.length ? 2 : 0;
  const summary = [
    `
Done. green=${green} escalate=${esc} blocked=${blocked.length}`,
    `Integration: ${ENV.integration}  ->  review & PR to ${ENV.base}`,
    `Report: ${path.join(ENV.reportDir, "farm-report.md")}`,
    ""
  ].join("\n");
  await new Promise(
    (resolve) => process.stdout.write(summary, () => resolve())
  );
  process.exit(exitCode);
}
function validate(plan) {
  const ids = /* @__PURE__ */ new Set();
  for (const t of plan.tasks) {
    if (ids.has(t.id)) throw new Error(`duplicate task id: ${t.id}`);
    ids.add(t.id);
  }
  for (const t of plan.tasks)
    for (const d of t.deps ?? [])
      if (!ids.has(d)) throw new Error(`task ${t.id} depends on unknown task ${d}`);
}
async function writeReport(plan, results, blocked) {
  await writeFile(
    path.join(ENV.reportDir, "farm-report.json"),
    JSON.stringify(
      { plan: plan.meta, results, blocked, ts: (/* @__PURE__ */ new Date()).toISOString() },
      null,
      2
    )
  );
  const md = [
    `# Farm report \u2014 ${plan.meta.name}`,
    ``,
    `| task | status | attempts | branch | note |`,
    `| --- | --- | --- | --- | --- |`,
    ...results.map(
      (r) => `| ${r.id} | ${r.status} | ${r.attempts} | ${r.branch} | ${r.note ?? ""} |`
    ),
    ...blocked.map((b) => `| ${b.id} | blocked | 0 | \u2014 | dependency escalated |`),
    ``,
    `## Escalations \u2014 handle only these`,
    ...results.filter((r) => r.status === "escalate").map(
      (r) => `- **${r.id}** \u2014 worktree at \`${r.worktree}\`, branch \`${r.branch}\`. ${r.note ?? ""}`
    )
  ].join("\n");
  await writeFile(path.join(ENV.reportDir, "farm-report.md"), md);
}
main().catch((e) => {
  console.error(e);
  process.exit(1);
});
