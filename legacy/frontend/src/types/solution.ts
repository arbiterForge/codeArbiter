export interface Solution {
  id: string
  name: string
  version: string
  maturity: 'prototype' | 'mvp' | 'production'
  description: string
}

export interface FusionNode extends Record<string, unknown> {
  id: string
  nodeType: string
  label: string
  criticality: 'critical_path' | 'non_critical'
  status: 'healthy' | 'degraded' | 'unknown'
  version: string
}

export interface FusionAdapter extends Record<string, unknown> {
  id: string
  sourceNodeId: string
  targetNodeId: string
  sourceType: string
  targetType: string
  label: string
  priorityTier: 1 | 2 | 3
}

export interface SolutionGraph {
  nodes: FusionNode[]
  adapters: FusionAdapter[]
}

export interface SolutionDetail extends Solution {
  graph: SolutionGraph
}
