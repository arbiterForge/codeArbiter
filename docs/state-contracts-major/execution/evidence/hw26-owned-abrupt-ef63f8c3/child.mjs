import fs from "node:fs";
import path from "node:path";
import { homedir, tmpdir } from "node:os";
import { createHash } from "node:crypto";
import { fileURLToPath, pathToFileURL } from "node:url";
import { syncBuiltinESMExports } from "node:module";
import childProcess from "node:child_process";
import net from "node:net";
import dgram from "node:dgram";
import http from "node:http";
import https from "node:https";

const fixture = fs.realpathSync(process.cwd());
const source = path.join(fixture, "source", "setup-disposable-home.ts");
const hash = (raw) => createHash("sha256").update(raw).digest("hex");
const original = Object.fromEntries(["mkdtempSync", "mkdirSync", "writeFileSync", "rmSync", "readFileSync", "realpathSync", "lstatSync"].map((name) => [name, fs[name].bind(fs)]));
const operations = [];
let childSpawns = 0;
let networkCalls = 0;
const within = (value) => {
  if (value instanceof URL) value = fileURLToPath(value);
  if (Buffer.isBuffer(value)) value = value.toString("utf8");
  if (typeof value !== "string") throw new Error("owned path must be a string");
  const absolute = path.resolve(value);
  const relative = path.relative(fixture, absolute);
  if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) throw new Error("owned path escape");
  let cursor = absolute;
  while (!fs.existsSync(cursor)) cursor = path.dirname(cursor);
  const resolved = original.realpathSync(cursor);
  const parentRelative = path.relative(fixture, resolved);
  if (parentRelative === ".." || parentRelative.startsWith(`..${path.sep}`) || path.isAbsolute(parentRelative)) throw new Error("owned ancestor escape");
  return absolute;
};
const environment = () => ({
  HOME: process.env.HOME ?? null,
  USERPROFILE: process.env.USERPROFILE ?? null,
  HOMEDRIVE: process.env.HOMEDRIVE ?? null,
  HOMEPATH: process.env.HOMEPATH ?? null,
  PI_CODING_AGENT_DIR: process.env.PI_CODING_AGENT_DIR ?? null,
  CODEARBITER_TEST_DISPOSABLE_HOME: process.env.CODEARBITER_TEST_DISPOSABLE_HOME ?? null,
  homedir: homedir(),
  tmpdir: tmpdir(),
});

for (const name of ["spawn", "spawnSync", "exec", "execSync", "execFile", "execFileSync", "fork"]) {
  childProcess[name] = () => { childSpawns += 1; throw new Error("no child process authority"); };
}
for (const [owner, names] of [[net, ["connect", "createConnection", "createServer"]], [dgram, ["createSocket"]], [http, ["request", "get", "createServer"]], [https, ["request", "get", "createServer"]]]) {
  for (const name of names) owner[name] = () => { networkCalls += 1; throw new Error("no network authority"); };
}
for (const name of ["mkdirSync", "writeFileSync", "rmSync"]) {
  fs[name] = (value, ...args) => {
    const absolute = within(value);
    operations.push({ operation: name, path: absolute });
    return original[name](value, ...args);
  };
}
fs.mkdtempSync = (prefix, ...args) => {
  within(prefix);
  const created = original.mkdtempSync(prefix, ...args);
  within(created);
  operations.push({ operation: "mkdtempSync", prefix, created });
  return created;
};
fs.readFileSync = (value, ...args) => {
  const absolute = within(value);
  operations.push({ operation: "readFileSync", path: absolute });
  return original.readFileSync(value, ...args);
};
syncBuiltinESMExports();

const before = environment();
for (const key of ["HOME", "USERPROFILE", "PI_CODING_AGENT_DIR", "tmpdir", "homedir"]) within(before[key]);
if (before.HOMEDRIVE !== null || before.HOMEPATH !== null) throw new Error("ambient home selector survived");
const sourceSha256 = hash(fs.readFileSync(source));
const setup = await import(pathToFileURL(source).href);
const after = environment();
const root = original.realpathSync(within(after.CODEARBITER_TEST_DISPOSABLE_HOME));
if (path.dirname(root) !== original.realpathSync(before.tmpdir)) throw new Error("setup root is outside owned TMP");
if (after.HOME !== root || after.USERPROFILE !== root || original.realpathSync(after.homedir) !== root) throw new Error("home redirection did not take effect");
if (after.HOMEDRIVE !== null || after.HOMEPATH !== null) throw new Error("fallback home selector present");
const authFile = within(path.join(after.PI_CODING_AGENT_DIR, "auth.json"));
const authBytes = fs.readFileSync(authFile);
if (authBytes.toString("utf8") !== JSON.stringify(setup.DUMMY_AUTH)) throw new Error("dummy auth differs from actual module export");
if (setup.DUMMY_AUTH.openai.key !== "dummy-disposable-home-not-a-credential") throw new Error("unexpected dummy fixture");
if (childSpawns !== 0 || networkCalls !== 0) throw new Error("forbidden capability attempted");
const record = {
  phase: "ready", pid: process.pid, platform: process.platform, nodeVersion: process.version,
  executable: process.execPath, sourceSha256, before, after, createdRoot: root,
  dummyAuth: { path: authFile, bytes: authBytes.length, sha256: hash(authBytes) },
  fsOperations: operations, childSpawns, networkCalls,
  environmentKeys: Object.keys(process.env).sort(),
};
setInterval(() => {}, 1000);
process.stdout.write(JSON.stringify(record) + "\n");
