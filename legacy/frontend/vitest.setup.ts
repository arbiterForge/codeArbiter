import '@testing-library/jest-dom'
import { MotionGlobalConfig } from 'framer-motion'

// Skip Framer Motion animations in tests so AnimatePresence removes exit
// elements synchronously rather than waiting for an animation loop jsdom
// does not run.
MotionGlobalConfig.skipAnimations = true

// React Flow requires ResizeObserver which jsdom does not implement.
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
