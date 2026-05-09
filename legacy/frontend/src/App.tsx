import { createBrowserRouter, RouterProvider, useLoaderData } from 'react-router-dom'
import { AuthProvider } from './lib/auth/AuthProvider'
import { AppShell } from './components/layout/AppShell'
import { CatalogPage } from './pages/CatalogPage'
import { SolutionDetailPage } from './pages/SolutionDetailPage'
import { DeployWizardPage } from './pages/DeployWizardPage'
import { AuditLogPage } from './pages/AuditLogPage'
import { AuthCallbackPage } from './pages/AuthCallbackPage'
import { solutionLoader } from './loaders/solutionLoader'
import { deployWizardLoader } from './loaders/deployWizardLoader'
import { auditLoader } from './loaders/auditLoader'
import type { SolutionDetail } from './types/solution'
import type { AuditEvent } from './types/audit'

function SolutionDetailRoute() {
  const data = useLoaderData() as SolutionDetail
  return <SolutionDetailPage solution={data} />
}

function DeployWizardRoute() {
  const data = useLoaderData() as SolutionDetail
  return <DeployWizardPage solution={data} />
}

function AuditLogRoute() {
  const data = useLoaderData() as AuditEvent[]
  return <AuditLogPage events={data} />
}

const router = createBrowserRouter([
  {
    path: 'auth/callback',
    element: <AuthCallbackPage />,
  },
  {
    element: <AppShell />,
    children: [
      {
        index: true,
        element: <CatalogPage solutions={[]} loading={false} />,
      },
      {
        path: 'solutions/:id',
        loader: solutionLoader,
        element: <SolutionDetailRoute />,
      },
      {
        path: 'solutions/:id/deploy',
        loader: deployWizardLoader,
        element: <DeployWizardRoute />,
      },
      {
        path: 'audit',
        loader: auditLoader,
        element: <AuditLogRoute />,
      },
    ],
  },
])

export function App() {
  return (
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  )
}
