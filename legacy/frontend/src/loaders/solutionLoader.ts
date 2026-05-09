import type { SolutionDetail } from '../types/solution'

// SHORTCUT [S1]: Returns static mock data instead of calling Z-API.
// Risk: LOW — internal dev only, no real solutions exist yet.
// Payback trigger: when GET /api/v1/solutions/:id is implemented in Z-API.
// At that point, replace the return below with:
//   const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/v1/solutions/${id}`)
//   if (!res.ok) throw new Response('Not found', { status: res.status })
//   return res.json()
export async function solutionLoader({
  params,
}: {
  params: Record<string, string | undefined>
}): Promise<SolutionDetail> {
  const id = params.id ?? 'unknown'

  return {
    id,
    name: 'Sample Solution',
    version: '0.1.0',
    maturity: 'prototype',
    description: 'Placeholder — no solutions authored yet.',
    graph: { nodes: [], adapters: [] },
  }
}
