import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import type { Solution } from '../types/solution'
import { CatalogEmptyState } from './catalog/CatalogEmptyState'
import { CatalogSkeleton } from './catalog/CatalogSkeleton'

interface CatalogPageProps {
  solutions: Solution[]
  loading: boolean
}

const MATURITY_STYLES: Record<Solution['maturity'], string> = {
  prototype: 'text-amber-400 bg-amber-400/10 border-amber-400/20',
  mvp: 'text-cyan-400 bg-cyan-400/10 border-cyan-400/20',
  production: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20',
}

export function CatalogPage({ solutions, loading }: CatalogPageProps) {
  return (
    <div className="px-8 py-10 max-w-[1100px]">
      {/* Asymmetric header — left-aligned, no center bias */}
      <div className="mb-10">
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-100 mb-1">
          Solutions
        </h1>
        <p className="text-sm text-zinc-500">
          Redeployable platform units built on FUSION nodes and adapters.
        </p>
      </div>

      {loading && <CatalogSkeleton />}

      {!loading && solutions.length === 0 && <CatalogEmptyState />}

      {!loading && solutions.length > 0 && (
        <motion.div
          className="flex flex-col gap-0 divide-y divide-zinc-800/60"
          initial="hidden"
          animate="show"
          variants={{
            hidden: {},
            show: { transition: { staggerChildren: 0.06 } },
          }}
        >
          {solutions.map((sol) => (
            <motion.div
              key={sol.id}
              variants={{
                hidden: { opacity: 0, x: -8 },
                show: { opacity: 1, x: 0, transition: { type: 'spring', stiffness: 300, damping: 28 } },
              }}
              className="flex items-center justify-between py-4 group"
            >
              <Link to={`/solutions/${sol.id}`} className="flex flex-col gap-0.5 flex-1 min-w-0">
                <span className="text-sm font-medium text-zinc-100 group-hover:text-accent transition-colors duration-150">
                  {sol.name}
                </span>
                <span className="text-xs text-zinc-500">{sol.description}</span>
              </Link>

              <div className="flex items-center gap-3 shrink-0">
                <span
                  className={[
                    'text-xs font-mono px-2 py-0.5 rounded border',
                    MATURITY_STYLES[sol.maturity],
                  ].join(' ')}
                >
                  {sol.maturity}
                </span>
                <span className="text-xs font-mono text-zinc-600">{sol.version}</span>
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  )
}
