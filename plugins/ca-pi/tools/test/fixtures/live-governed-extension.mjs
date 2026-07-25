/**
 * live-governed-extension.mjs - codeArbiter's enforcement, loaded as a REAL Pi
 * extension by the installed host's own loader (issue #370).
 *
 * The installed Pi runtime discovers and evaluates this file exactly as it
 * evaluates `plugins/ca-pi/extensions/codearbiter.js`: through
 * `discoverAndLoadExtensions`, in declared order, with the host-built
 * ExtensionAPI. It installs the same `guardUnknownTools` + `wrapBuiltins`
 * enforcement the shipped bundle installs, imported from the canonical source
 * the bundle is built from, so the ordering and tool-registry semantics under
 * test belong to the real host and not to a hand-written double.
 *
 * The driving test hands over its judge and its built-in factories through a
 * single global control object. jiti loads this file in the caller's process,
 * so the handover is an ordinary object reference - nothing is serialized, and
 * no environment value, prompt, or credential is involved.
 */
import { compileBuiltinPermissionPolicy, guardUnknownTools, wrapBuiltins } from "../../src/tool-guard.ts";

export default async function liveGovernedExtension(pi) {
  const control = globalThis.__CA_LIVE_FINAL_ARGUMENT_CONTROL__;
  if (control === undefined) throw new Error("the live final-argument fixture control object is missing");
  const permissionPolicy = compileBuiltinPermissionPolicy(control.descriptor, control.actionClasses);
  if (permissionPolicy === undefined) throw new Error("the fixture permission policy did not compile");
  guardUnknownTools(pi, control.descriptor, control.wrapperSourcePath);
  wrapBuiltins(pi, control.bridge, {
    cwd: control.cwd,
    descriptor: control.descriptor,
    factories: control.factories,
    wrapperSourcePath: control.wrapperSourcePath,
    permissionPolicy,
    permissionAudit: control.permissionAudit,
    projectTrust: () => true,
  });
}
