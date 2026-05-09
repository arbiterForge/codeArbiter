'use client'

import { useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Cube } from '@phosphor-icons/react'
import type { SolutionGraph as SolutionGraphType, FusionNode, FusionAdapter } from '../../types/solution'
import { FusionNodeCard } from './FusionNodeCard'
import { AdapterEdge } from './AdapterEdge'

const NODE_TYPES = { fusionNode: FusionNodeCard }
const EDGE_TYPES = { adapterEdge: AdapterEdge }

// Lay nodes out in a simple horizontal row; a proper auto-layout
// (dagre/elkjs) should replace this at Stage 2 when graphs get complex.
// SHORTCUT [S1]: Static positional layout.
// Payback trigger: when solutions have >3 nodes and layout collisions occur.
function buildLayout(fusionNodes: FusionNode[], adapters: FusionAdapter[]): {
  nodes: Node[]
  edges: Edge[]
} {
  const nodes: Node[] = fusionNodes.map((fn, i) => ({
    id: fn.id,
    type: 'fusionNode',
    position: { x: i * 240, y: 0 },
    data: fn,
  }))

  // Group adapters by source+target pair to calculate curvature offsets
  const pairCounts = new Map<string, number>()
  const pairIndex = new Map<string, number>()

  for (const adapter of adapters) {
    const key = `${adapter.sourceNodeId}::${adapter.targetNodeId}`
    pairCounts.set(key, (pairCounts.get(key) ?? 0) + 1)
  }

  const edges: Edge[] = adapters.map((adapter) => {
    const key = `${adapter.sourceNodeId}::${adapter.targetNodeId}`
    const idx = pairIndex.get(key) ?? 0
    pairIndex.set(key, idx + 1)
    const total = pairCounts.get(key) ?? 1

    // Fan multiple adapters symmetrically: 0 = straight, alternating ±offset
    const offset = total > 1 ? ((idx % 2 === 0 ? 1 : -1) * Math.ceil((idx + 1) / 2) * 60) : 0

    return {
      id: adapter.id,
      source: adapter.sourceNodeId,
      target: adapter.targetNodeId,
      type: 'adapterEdge',
      data: adapter,
      style: { strokeWidth: 1.5 },
      ...(offset !== 0 && {
        // Shift the edge vertically to create a fanned appearance
        sourceHandle: null,
        targetHandle: null,
        pathOptions: { offset },
      }),
    }
  })

  return { nodes, edges }
}

interface SolutionGraphProps {
  graph: SolutionGraphType
}

export function SolutionGraph({ graph }: SolutionGraphProps) {
  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => buildLayout(graph.nodes, graph.adapters),
    [graph],
  )

  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, , onEdgesChange] = useEdgesState(initialEdges)

  const onConnect = useCallback(() => undefined, [])

  if (graph.nodes.length === 0) {
    return (
      <div
        data-testid="solution-graph"
        className="flex-1 flex flex-col items-center justify-center gap-4 bg-zinc-950 rounded-xl border border-zinc-800 border-dashed"
      >
        <div className="p-3 rounded-xl bg-zinc-900 border border-zinc-800">
          <Cube size={24} weight="duotone" className="text-zinc-600" />
        </div>
        <div className="text-center">
          <p className="text-sm text-zinc-500">No nodes defined yet</p>
          <p className="text-xs text-zinc-600 mt-1 font-mono">/new-node to scaffold one</p>
        </div>
      </div>
    )
  }

  return (
    <div data-testid="solution-graph" className="flex-1 rounded-xl overflow-hidden border border-zinc-800">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        fitView
        colorMode="dark"
        className="bg-zinc-950"
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#27272a" />
        <Controls className="!bg-zinc-900 !border-zinc-800" />
      </ReactFlow>
    </div>
  )
}
