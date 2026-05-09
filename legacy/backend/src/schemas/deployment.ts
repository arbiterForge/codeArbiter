import { z } from 'zod'

export const DeploymentStatusSchema = z.enum([
  'queued',
  'provisioning',
  'configuring',
  'verifying',
  'success',
  'failed',
])

export const DeploymentSchema = z.object({
  id: z.string().uuid(),
  solutionId: z.string().uuid(),
  solutionName: z.string().min(1),
  status: DeploymentStatusSchema,
  actorSub: z.string().min(1),
  classification: z.enum(['none', 'cui', 'secret_ref']),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
})

export const CreateDeploymentBodySchema = z.object({
  classification: z.enum(['none', 'cui', 'secret_ref']).default('none'),
  deploymentTarget: z.enum(['on-prem', 'cloud', 'hybrid']).default('on-prem'),
  keycloakRealm: z.string().min(1),
  keycloakUrl: z.string().url(),
  adDomain: z.string().min(1),
  replicaCount: z.coerce.number().int().min(1).max(5),
})

export type Deployment = z.infer<typeof DeploymentSchema>
export type CreateDeploymentBody = z.infer<typeof CreateDeploymentBodySchema>
export type DeploymentStatus = z.infer<typeof DeploymentStatusSchema>
