import { motion } from 'framer-motion'
import { Cube } from '@phosphor-icons/react'

export function CatalogEmptyState() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 200, damping: 24 }}
      className="flex flex-col items-start max-w-lg"
    >
      <div className="mb-6 p-3 rounded-xl bg-zinc-900 border border-zinc-800">
        <Cube size={28} weight="duotone" className="text-accent" />
      </div>

      <h2 className="text-2xl font-semibold tracking-tight text-zinc-100 mb-3">
        No solutions yet
      </h2>

      <p className="text-sm text-zinc-400 leading-relaxed mb-8 max-w-[52ch]">
        FUSION solutions bundle nodes, adapters, and deployment config into a single
        redeployable unit. Scaffold your first one to get started.
      </p>

      <div className="flex flex-col gap-3 w-full">
        <p className="text-xs text-zinc-500 uppercase tracking-widest font-mono">
          Run in your terminal
        </p>
        <div className="flex items-center gap-3 bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3">
          <code className="text-sm font-mono text-accent">/new-node</code>
          <span className="text-zinc-600 text-xs">—</span>
          <span className="text-zinc-400 text-xs">scaffold a new FUSION node definition</span>
        </div>
        <div className="flex items-center gap-3 bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3">
          <code className="text-sm font-mono text-zinc-300">/new-adapter</code>
          <span className="text-zinc-600 text-xs">—</span>
          <span className="text-zinc-400 text-xs">connect two node types with a typed contract</span>
        </div>
      </div>
    </motion.div>
  )
}
