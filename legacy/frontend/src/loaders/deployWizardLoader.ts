import type { SolutionDetail } from '../types/solution'

// SHORTCUT [S1]: Returns same mock data as solutionLoader.
// Risk: LOW — internal dev only; no real solutions exist yet.
// Payback trigger: same as solutionLoader — when GET /api/v1/solutions/:id exists.
export async function deployWizardLoader({
  params,
}: {
  params: Record<string, string | undefined>
}): Promise<SolutionDetail> {
  const id = params.id ?? 'unknown'

  return {
    id,
    name: 'Identity Bridge',
    version: '1.2.0',
    maturity: 'mvp',
    description: 'AD-to-Keycloak federation adapter.',
    graph: {
      nodes: [
        {
          id: 'node-keycloak',
          nodeType: 'keycloak',
          label: 'Keycloak IdP',
          criticality: 'critical_path',
          status: 'healthy',
          version: '24.0.1',
        },
        {
          id: 'node-ad',
          nodeType: 'active-directory',
          label: 'Active Directory',
          criticality: 'critical_path',
          status: 'healthy',
          version: '2019',
        },
      ],
      adapters: [
        {
          id: 'adapter-ldap',
          sourceNodeId: 'node-ad',
          targetNodeId: 'node-keycloak',
          sourceType: 'active-directory',
          targetType: 'keycloak',
          label: 'ldap-sync',
          priorityTier: 1,
        },
      ],
    },
  }
}
