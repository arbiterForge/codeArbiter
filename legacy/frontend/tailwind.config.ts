import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: '#22d3ee',
          hover: '#06b6d4',
        },
      },
      fontFamily: {
        sans: [
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'Cascadia Code',
          'JetBrains Mono',
          'Fira Code',
          'monospace',
        ],
      },
    },
  },
  plugins: [],
} satisfies Config
