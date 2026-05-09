import { memo } from 'react'
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type Edge,
  type EdgeProps,
} from '@xyflow/react'
import type { FusionAdapter } from '../../types/solution'

const TIER_STYLE: Record<FusionAdapter['priorityTier'], string> = {
  1: 'border-zinc-600 text-zinc-300',
  2: 'border-zinc-700 text-zinc-400',
  3: 'border-zinc-800 text-zinc-500',
}

export const AdapterEdge = memo(function AdapterEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps<Edge<FusionAdapter>>) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })

  const tier = data?.priorityTier ?? 1

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={{ stroke: '#3f3f46' }} />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
          }}
          className="nodrag nopan"
        >
          <span
            className={[
              'inline-block text-[10px] font-mono px-2 py-0.5 rounded-full',
              'bg-zinc-950 border',
              TIER_STYLE[tier],
            ].join(' ')}
            title={`Priority tier ${tier}`}
          >
            {data?.label ?? 'adapter'}
          </span>
        </div>
      </EdgeLabelRenderer>
    </>
  )
})
