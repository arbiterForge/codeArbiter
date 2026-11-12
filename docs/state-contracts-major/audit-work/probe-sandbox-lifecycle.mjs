// Pure/injected effects only. No Docker command is started.
import { imageTag } from '../codeArbiter/plugins/ca-sandbox/tools/build.ts';
import { computeDepHash } from '../codeArbiter/plugins/ca-sandbox/tools/dephash.ts';
import { execInSandbox } from '../codeArbiter/plugins/ca-sandbox/tools/exec.ts';
import { listSandboxes } from '../codeArbiter/plugins/ca-sandbox/tools/registry.ts';
const key = computeDepHash([{ path: 'package.json', bytes: '{"name":"fixture"}' }]);
const calls = [];
const result = await execInSandbox('container', ['sleep', 'infinity'], {
  dockerRun: async (args) => { calls.push(args); return { code: 1, stdout: '', stderr: 'overflow', overflowed: true }; },
});
console.log(JSON.stringify({ commit: 'fd7eb34b2da439551443d09526ab48fd1d1bb9bf', runtime: process.version,
  cache: { key, tags: [imageTag('/tmp/ca-sbx-checkout-AAAAAA', key), imageTag('/tmp/ca-sbx-checkout-BBBBBB', key)] },
  overflow: { result, calls },
  failedListing: await listSandboxes(async () => ({ code: 1, stdout: '', stderr: 'Cannot connect to the Docker daemon' })),
}, null, 2));
