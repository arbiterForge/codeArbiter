import releaseApplicability from "../generated/release-applicability.json";

export const prerender = true;

export function GET(): Response {
  return new Response(`${JSON.stringify(releaseApplicability, null, 2)}\n`, {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}
