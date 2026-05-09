import { CheckCircle } from '@phosphor-icons/react'

const STEPS = ['Configure', 'Compliance', 'Confirm', 'Monitor'] as const

interface StepIndicatorProps {
  current: number
}

export function StepIndicator({ current }: StepIndicatorProps) {
  return (
    <nav aria-label="Deployment steps" className="flex items-center gap-0">
      {STEPS.map((label, i) => {
        const stepNum = i + 1
        const done = stepNum < current
        const active = stepNum === current

        return (
          <div key={label} className="flex items-center">
            <div className="flex items-center gap-2">
              <div
                className={[
                  'w-6 h-6 rounded-full flex items-center justify-center shrink-0 transition-colors duration-200',
                  done
                    ? 'bg-accent/20 border border-accent/40'
                    : active
                      ? 'bg-accent border border-accent'
                      : 'bg-zinc-800 border border-zinc-700',
                ].join(' ')}
              >
                {done ? (
                  <CheckCircle size={14} weight="fill" className="text-accent" />
                ) : (
                  <span
                    className={[
                      'text-[10px] font-mono font-semibold',
                      active ? 'text-zinc-950' : 'text-zinc-600',
                    ].join(' ')}
                  >
                    {stepNum}
                  </span>
                )}
              </div>
              <span
                className={[
                  'text-xs font-medium transition-colors duration-200',
                  active ? 'text-zinc-100' : done ? 'text-accent' : 'text-zinc-600',
                ].join(' ')}
              >
                {label}
              </span>
            </div>

            {i < STEPS.length - 1 && (
              <div
                className={[
                  'w-8 h-px mx-3 transition-colors duration-200',
                  done ? 'bg-accent/30' : 'bg-zinc-800',
                ].join(' ')}
              />
            )}
          </div>
        )
      })}
    </nav>
  )
}
