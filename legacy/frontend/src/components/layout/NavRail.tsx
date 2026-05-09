import { NavLink } from 'react-router-dom'
import { House, Rocket, ShieldCheck, Flag } from '@phosphor-icons/react'
import { motion } from 'framer-motion'

interface NavRailProps {
  stage: 1 | 2 | 3 | 4
}

const NAV_ITEMS = [
  { label: 'Catalog', to: '/', icon: House },
  { label: 'Deployments', to: '/deployments', icon: Rocket },
  { label: 'Audit', to: '/audit', icon: ShieldCheck },
  { label: 'Stage Gate', to: '/stage', icon: Flag },
] as const

export function NavRail({ stage }: NavRailProps) {
  return (
    <nav
      aria-label="Primary navigation"
      className="flex flex-col w-60 shrink-0 bg-zinc-900 border-r border-zinc-800 h-full"
    >
      {/* Wordmark */}
      <div className="px-6 py-5 border-b border-zinc-800">
        <span className="text-sm font-semibold tracking-widest text-zinc-100 uppercase">
          FUSION
        </span>
      </div>

      {/* Nav items */}
      <div className="flex-1 py-4 px-3 flex flex-col gap-1">
        {NAV_ITEMS.map(({ label, to, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors duration-150',
                isActive
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50',
              ].join(' ')
            }
          >
            {({ isActive }) => (
              <motion.span
                className="flex items-center gap-3 w-full"
                whileHover={{ x: 2 }}
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              >
                <Icon
                  size={18}
                  weight={isActive ? 'fill' : 'regular'}
                  className={isActive ? 'text-accent' : 'text-zinc-500'}
                />
                {label}
              </motion.span>
            )}
          </NavLink>
        ))}
      </div>

      {/* Stage badge */}
      <div className="px-6 py-4 border-t border-zinc-800 flex items-center gap-2">
        <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded bg-zinc-800 text-accent border border-accent/20">
          S{stage}
        </span>
        <span className="text-xs text-zinc-500">Prototype</span>
      </div>
    </nav>
  )
}
