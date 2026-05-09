import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    coverage: {
      provider: 'v8',
      thresholds: { lines: 60, functions: 60, branches: 60, statements: 60 },
      include: ['src/**/*.ts'],
      exclude: ['src/main.ts', 'src/**/__tests__/**', 'src/db/index.ts'],
    },
  },
})
