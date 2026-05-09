// All outbound HTTP calls from the backend MUST use this client.
// Rationale: SC-8 (consistent timeouts + TLS enforcement), AU-12 (audit hook point).
// Verification: Semgrep rule denies bare fetch() outside this module.

const DEFAULT_TIMEOUT_MS = 10_000

interface RequestOptions extends RequestInit {
  timeoutMs?: number
}

export async function httpGet(url: string, options: RequestOptions = {}): Promise<Response> {
  return httpRequest(url, { ...options, method: 'GET' })
}

export async function httpPost(
  url: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<Response> {
  return httpRequest(url, {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    body: JSON.stringify(body),
  })
}

async function httpRequest(url: string, options: RequestOptions): Promise<Response> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options
  const controller = new AbortController()
  const timer = setTimeout(() => { controller.abort() }, timeoutMs)

  try {
    return await fetch(url, { ...fetchOptions, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}
