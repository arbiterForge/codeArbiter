import { memo } from 'react'
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import type { FusionNode } from '../../types/solution'

const STATUS_DOT: Record<FusionNode['status'], string> = {
  healthy: 'bg-emerald-400',
  degraded: 'bg-amber-400',
  unknown: 'bg-zinc-600',
}

const STATUS_LABEL: Record<FusionNode['status'], string> = {
  healthy: 'Healthy',
  degraded: 'Degraded',
  unknown: 'Unknown',
}

export const FusionNodeCard = memo(function FusionNodeCard({
  data,
  selected,
}: NodeProps<Node<FusionNode>>) {
  const isCritical = data.criticality === 'critical_path'

  return (
    <div
      className={[
        'w-48 rounded-xl bg-zinc-900 p-4 flex flex-col gap-2',
        'border transition-colors duration-150',
        selected
          ? 'border-accent shadow-[0_0_0_1px_#22d3ee22]'
          : isCritical
            ? 'border-zinc-700 hover:border-zinc-600'
            : 'border-zinc-800 hover:border-zinc-700',
      ].join(' ')}
    >
      <Handle type="target" position={Position.Left} className="!bg-zinc-600 !border-zinc-700" />

      <div className="flex items-center justify-between">
        <span className="text-xs font-mono text-zinc-500 truncate">{data.nodeType}</span>
        {isCritical && (
          <span className="text-[10px] font-mono text-accent bg-accent/10 border border-accent/20 px-1.5 py-0.5 rounded">
            critical
          </span>
        )}
      </div>

      <span className="text-sm font-medium text-zinc-100 leading-snug">{data.label}</span>

      <div className="flex items-center gap-1.5 mt-1">
        <span
          className={['w-1.5 h-1.5 rounded-full shrink-0', STATUS_DOT[data.status]].join(' ')}
          aria-label={STATUS_LABEL[data.status]}
        />
        <span className="text-xs text-zinc-500 font-mono">{data.version}</span>
      </div>

      <Handle type="source" position={Position.Right} className="!bg-zinc-600 !border-zinc-700" />
    </div>
  )
})
