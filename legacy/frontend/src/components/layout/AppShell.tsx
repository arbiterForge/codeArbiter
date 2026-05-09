'use client'

import { Outlet } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { useLocation } from 'react-router-dom'
import { NavRail } from './NavRail'
import { AuthBypassBanner } from '../auth/AuthBypassBanner'
import { useAuth } from '../../lib/auth/useAuth'

const pageVariants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
}

export function AppShell() {
  const { isBypass } = useAuth()
  const location = useLocation()

  return (
    <div className="flex min-h-[100dvh] bg-zinc-950">
      {/* Nav rail — hidden on mobile, shown md+ */}
      <div className="hidden md:flex md:flex-col md:fixed md:inset-y-0 md:w-60">
        <NavRail stage={1} />
      </div>

      {/* Main content */}
      <div className="flex flex-col flex-1 md:pl-60">
        <AuthBypassBanner active={isBypass} />

        <main className="flex-1 overflow-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              variants={pageVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              transition={{ type: 'spring', stiffness: 280, damping: 30 }}
              className="h-full"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  )
}
