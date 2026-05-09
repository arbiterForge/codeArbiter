import { Rocket } from '@phosphor-icons/react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import type { SolutionDetail } from '../types/solution'
import { SolutionGraph } from '../components/graph/SolutionGraph'

const MATURITY_STYLES = {
  prototype: 'text-amber-400 bg-amber-400/10 border-amber-400/20',
  mvp: 'text-cyan-400 bg-cyan-400/10 border-cyan-400/20',
  production: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20',
}

interface SolutionDetailPageProps {
  solution: SolutionDetail
}

export function SolutionDetailPage({ solution }: SolutionDetailPageProps) {
  const hasNodes = solution.graph.nodes.length > 0

  return (
    <div className="flex h-full min-h-[calc(100dvh-0px)]">
      {/* Metadata panel */}
      <motion.aside
        initial={{ opacity: 0, x: -12 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ type: 'spring', stiffness: 280, damping: 28 }}
        className="w-72 shrink-0 flex flex-col gap-6 px-8 py-10 border-r border-zinc-800 bg-zinc-900/50"
      >
        {/* Back link */}
        <Link
          to="/"
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors duration-150 font-mono"
        >
          ← Catalog
        </Link>

        {/* Identity */}
        <div className="flex flex-col gap-2">
          <h1 className="text-xl font-semibold tracking-tight text-zinc-100 leading-snug">
            {solution.name}
          </h1>
          <div className="flex items-center gap-2">
            <span
              className={[
                'text-xs font-mono px-2 py-0.5 rounded border',
                MATURITY_STYLES[solution.maturity],
              ].join(' ')}
            >
              {solution.maturity}
            </span>
            <span className="text-xs font-mono text-zinc-600">{solution.version}</span>
          </div>
        </div>

        <p className="text-sm text-zinc-400 leading-relaxed">{solution.description}</p>

        {/* Stats */}
        <div className="flex flex-col gap-0 divide-y divide-zinc-800">
          <div className="flex items-center justify-between py-3">
            <span className="text-xs text-zinc-500">Nodes</span>
            <span className="text-xs font-mono text-zinc-300">
              {solution.graph.nodes.length}
            </span>
          </div>
          <div className="flex items-center justify-between py-3">
            <span className="text-xs text-zinc-500">Adapters</span>
            <span className="text-xs font-mono text-zinc-300">
              {solution.graph.adapters.length}
            </span>
          </div>
          <div className="flex items-center justify-between py-3">
            <span className="text-xs text-zinc-500">Critical nodes</span>
            <span className="text-xs font-mono text-zinc-300">
              {solution.graph.nodes.filter((n) => n.criticality === 'critical_path').length}
            </span>
          </div>
        </div>

        {/* Deploy button */}
        <div className="mt-auto">
          <Link
            to={hasNodes ? `/solutions/${solution.id}/deploy` : '#'}
            tabIndex={hasNodes ? undefined : -1}
            aria-disabled={!hasNodes}
            className="block w-full"
          >
            <button
              disabled={!hasNodes}
              title={!hasNodes ? 'Add at least one node before deploying' : undefined}
              className={[
                'w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg',
                'text-sm font-medium transition-all duration-150',
                'active:scale-[0.98]',
                hasNodes
                  ? 'bg-accent text-zinc-950 hover:bg-accent-hover'
                  : 'bg-zinc-800 text-zinc-600 cursor-not-allowed',
              ].join(' ')}
            >
              <Rocket size={16} weight={hasNodes ? 'fill' : 'regular'} />
              Deploy Solution
            </button>
          </Link>
        </div>
      </motion.aside>

      {/* Graph canvas */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.25, delay: 0.1 }}
        className="flex-1 p-6"
      >
        <SolutionGraph graph={solution.graph} />
      </motion.div>
    </div>
  )
}
