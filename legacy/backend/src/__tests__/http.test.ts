import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { httpGet, httpPost } from '../common/http.js'

const TEST_URL = 'http://example.com/api'

describe('httpGet', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('ok', { status: 200 }))
  })

  afterEach(() => {
    fetchSpy.mockRestore()
    vi.useRealTimers()
  })

  it('makes a GET request to the target URL', async () => {
    const res = await httpGet(TEST_URL)
    expect(fetchSpy).toHaveBeenCalledOnce()
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(TEST_URL)
    expect(init.method).toBe('GET')
    expect(res.status).toBe(200)
  })

  it('attaches an AbortSignal to the fetch call', async () => {
    await httpGet(TEST_URL)
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })

  it('forwards caller-supplied headers', async () => {
    await httpGet(TEST_URL, { headers: { Authorization: 'Bearer tok' } })
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect((init.headers as Record<string, string>)['Authorization']).toBe('Bearer tok')
  })

  describe('timeout enforcement (SC-8)', () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })

    it('aborts the request after a custom timeoutMs and the promise rejects', async () => {
      fetchSpy.mockImplementation((_url: string, init?: RequestInit) => {
        let rejectFn!: (err: DOMException) => void
        const p = new Promise<Response>((_res, rej) => { rejectFn = rej })
        init?.signal?.addEventListener('abort', () =>
          rejectFn(new DOMException('The operation was aborted', 'AbortError')),
        )
        return p
      })
      // Hold both promises from the start so the rejection is never transiently unhandled
      const [result] = await Promise.allSettled([
        httpGet(TEST_URL, { timeoutMs: 200 }),
        vi.advanceTimersByTimeAsync(200),
      ])
      expect(result.status).toBe('rejected')
      expect((result as PromiseRejectedResult).reason.name).toBe('AbortError')
    })

    it('aborts after the default 10 000 ms when no timeoutMs is supplied', async () => {
      const abortSpy = vi.spyOn(AbortController.prototype, 'abort')
      fetchSpy.mockImplementation(() => new Promise<Response>((_res, _rej) => { void 0 }))
      void httpGet(TEST_URL)
      await vi.advanceTimersByTimeAsync(9_999)
      expect(abortSpy).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(1)
      expect(abortSpy).toHaveBeenCalledOnce()
      abortSpy.mockRestore()
    })

    it('clears the timer when fetch resolves before the deadline — no spurious abort', async () => {
      const abortSpy = vi.spyOn(AbortController.prototype, 'abort')
      fetchSpy.mockResolvedValue(new Response(null, { status: 200 }))
      await httpGet(TEST_URL, { timeoutMs: 5_000 })
      await vi.advanceTimersByTimeAsync(5_001)
      expect(abortSpy).not.toHaveBeenCalled()
      abortSpy.mockRestore()
    })

    it('clears the timer when fetch rejects before the deadline — no spurious abort', async () => {
      const abortSpy = vi.spyOn(AbortController.prototype, 'abort')
      fetchSpy.mockRejectedValue(new Error('network error'))
      await expect(httpGet(TEST_URL, { timeoutMs: 5_000 })).rejects.toThrow('network error')
      await vi.advanceTimersByTimeAsync(5_001)
      expect(abortSpy).not.toHaveBeenCalled()
      abortSpy.mockRestore()
    })
  })
})

describe('httpPost', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 201 }))
  })

  afterEach(() => {
    fetchSpy.mockRestore()
  })

  it('makes a POST request with JSON body', async () => {
    const payload = { foo: 'bar' }
    await httpPost('http://example.com/api', payload)
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://example.com/api')
    expect(init.method).toBe('POST')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual(payload)
  })
})
