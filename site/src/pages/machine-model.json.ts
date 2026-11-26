import { loadMachine } from "../../scripts/machine/machine-model";

export const prerender = true;

/** The validated machine model the 3D viewer on /concepts/machine/ fetches when a reader starts it.
 *  Same build-time checks as the static page: a model that disagrees with the plugin sources never ships. */
export function GET(): Response {
  const { claims: _claims, ...model } = loadMachine();
  return new Response(JSON.stringify(model), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}
