/**
 * Resolve a GitHub blob ref that exists when the documentation is published.
 *
 * GitHub Actions provides the exact commit SHA for production builds. Local
 * builds use `main`, which remains navigable while a release version is staged
 * but its tag has not been cut yet.
 */
export function repositorySourceRef(
  env: Record<string, string | undefined> = process.env,
): string {
  const sha = env.GITHUB_SHA?.trim();
  return sha && /^[0-9a-f]{40}$/i.test(sha) ? sha : "main";
}
