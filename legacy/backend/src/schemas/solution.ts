import { z } from 'zod'

// These schemas are the authoritative backend type definitions.
// The frontend's src/types/solution.ts MUST be kept in sync.
// SHORTCUT [S1]: sync is manual. Payback: extract to packages/fusion-schema shared workspace.

export const FusionNodeSchema = z.object({
  id: z.string().min(1),
  nodeType: z.string().min(1),
  label: z.string().min(1),
  criticality: z.enum(['critical_path', 'non_critical']),
  status: z.enum(['healthy', 'degraded', 'unknown']),
  version: z.string().min(1),
})

export const FusionAdapterSchema = z.object({
  id: z.string().min(1),
  sourceNodeId: z.string().min(1),
  targetNodeId: z.string().min(1),
  sourceType: z.string().min(1),
  targetType: z.string().min(1),
  label: z.string().min(1),
  priorityTier: z.union([z.literal(1), z.literal(2), z.literal(3)]),
})

export const SolutionGraphSchema = z.object({
  nodes: z.array(FusionNodeSchema),
  adapters: z.array(FusionAdapterSchema),
})

export const SolutionSchema = z.object({
  id: z.string().uuid(),
  name: z.string().min(1).max(256),
  version: z.string().regex(/^\d+\.\d+\.\d+$/),
  maturity: z.enum(['prototype', 'mvp', 'production']),
  description: z.string().max(1024),
})

export const SolutionDetailSchema = SolutionSchema.extend({
  graph: SolutionGraphSchema,
})

export type Solution = z.infer<typeof SolutionSchema>
export type SolutionDetail = z.infer<typeof SolutionDetailSchema>
export type FusionNode = z.infer<typeof FusionNodeSchema>
export type FusionAdapter = z.infer<typeof FusionAdapterSchema>
