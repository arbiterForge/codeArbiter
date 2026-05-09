'use client'

import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, XCircle, ArrowsClockwise } from '@phosphor-icons/react'
import type { SolutionDetail } from '../../types/solution'
import { emit } from '../../lib/audit'

type DeployStatus = 'queued' | 'provisioning' | 'configuring' | 'verifying' | 'success' | 'failed'

interface LogLine {
  ts: string
  level: 'info' | 'ok' | 'warn' | 'error'
  msg: string
}

export interface StageDefinition {
  status: DeployStatus
  duration: number
  logs: LogLine[]
}

const STAGES: StageDefinition[] = [
  {
    status: 'queued',
    duration: 900,
    logs: [{ ts: now(), level: 'info', msg: 'Deployment queued — waiting for Z-WORKER slot' }],
  },
  {
    status: 'provisioning',
    duration: 2200,
    logs: [
      { ts: now(), level: 'info', msg: 'TASK [pre-check : Verify connectivity]' },
      { ts: now(), level: 'ok', msg: 'ok: [keycloak-node-01]' },
      { ts: now(), level: 'info', msg: 'TASK [pre-check : Check AD reachability]' },
      { ts: now(), level: 'ok', msg: 'ok: [ad-node-01]' },
    ],
  },
  {
    status: 'configuring',
    duration: 2600,
    logs: [
      { ts: now(), level: 'info', msg: 'TASK [main : Apply Keycloak realm config]' },
      { ts: now(), level: 'ok', msg: 'changed: [keycloak-node-01]' },
      { ts: now(), level: 'info', msg: 'TASK [main : Configure LDAP federation]' },
      { ts: now(), level: 'ok', msg: 'changed: [keycloak-node-01]' },
      { ts: now(), level: 'info', msg: 'TASK [main : Set replica count → 2]' },
      { ts: now(), level: 'ok', msg: 'changed: [keycloak-node-01]' },
    ],
  },
  {
    status: 'verifying',
    duration: 1600,
    logs: [
      { ts: now(), level: 'info', msg: 'TASK [verify : Token endpoint health check]' },
      { ts: now(), level: 'ok', msg: 'ok: [keycloak-node-01] → HTTP 200' },
      { ts: now(), level: 'info', msg: 'TASK [verify : LDAP sync test]' },
      { ts: now(), level: 'ok', msg: 'ok: [keycloak-node-01] → 47 users synced' },
    ],
  },
  {
    status: 'success',
    duration: 0,
    logs: [
      { ts: now(), level: 'ok', msg: 'PLAY RECAP ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━' },
      { ts: now(), level: 'ok', msg: 'keycloak-node-01 : ok=8  changed=3  failed=0' },
      { ts: now(), level: 'ok', msg: 'Deployment complete. Audit event emitted to Z-AUDIT.' },
    ],
  },
]

function now() {
  return new Date().toISOString().replace('T', ' ').slice(0, 23)
}

const STATUS_LABEL: Record<DeployStatus, string> = {
  queued: 'Queued',
  provisioning: 'Provisioning',
  configuring: 'Configuring',
  verifying: 'Verifying',
  success: 'Success',
  failed: 'Failed',
}

const LOG_COLOR: Record<LogLine['level'], string> = {
  info: 'text-zinc-500',
  ok: 'text-emerald-400',
  warn: 'text-amber-400',
  error: 'text-rose-400',
}

interface Step4MonitorProps {
  solution: SolutionDetail
  actorSub: string
  stages?: StageDefinition[]
}

export function Step4Monitor({ solution, actorSub, stages = STAGES }: Step4MonitorProps) {
  const [status, setStatus] = useState<DeployStatus>('queued')
  const [logs, setLogs] = useState<LogLine[]>([])
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    let stageIdx = 0

    const advance = () => {
      if (cancelled || stageIdx >= stages.length) return
      const stage = stages[stageIdx]
      setStatus(stage.status)
      setLogs((prev) => [...prev, ...stage.logs])
      stageIdx++
      if (stageIdx < stages.length && stage.duration > 0) {
        setTimeout(advance, stage.duration)
      }
    }

    advance()
    return () => { cancelled = true }
  }, [stages])

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [logs])

  useEffect(() => {
    if (status !== 'success' && status !== 'failed') return
    void emit({
      ts: new Date().toISOString(),
      event_id: crypto.randomUUID(),
      action: 'deploy.solution',
      actor: { id: actorSub, type: 'user' },
      subject: { type: 'solution', id: solution.id, name: solution.name },
      outcome: status === 'success' ? 'success' : 'failure',
      ...(status === 'failed' && { reason: 'Deployment simulation ended in failed state' }),
      source: { request_id: crypto.randomUUID() },
      classification: 'none',
      // SHORTCUT [S1]: git_sha injected at build time via VITE_GIT_SHA; missing
      // in dev/test. Required for deploy.* per action registry. Payback: CI sets this.
      ...(import.meta.env.VITE_GIT_SHA && { git_sha: import.meta.env.VITE_GIT_SHA as string }),
      metadata: { schema_version: '1.0.0', product: 'fusion-core' },
      class_uid: 6001,
      severity_id: 2,
    })
  }, [status, solution, actorSub])

  const isTerminal = status === 'success' || status === 'failed'

  return (
    <div className="flex flex-col gap-5 max-w-2xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-zinc-100">{solution.name}</h2>
          <p className="text-xs text-zinc-500 font-mono mt-0.5">deployment monitor</p>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={status}
            data-testid="deploy-status"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ type: 'spring', stiffness: 300, damping: 25 }}
            className={[
              'flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-mono border',
              status === 'success'
                ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20'
                : status === 'failed'
                  ? 'text-rose-400 bg-rose-400/10 border-rose-400/20'
                  : 'text-cyan-400 bg-cyan-400/10 border-cyan-400/20',
            ].join(' ')}
          >
            {status === 'success' ? (
              <CheckCircle size={12} weight="fill" />
            ) : status === 'failed' ? (
              <XCircle size={12} weight="fill" />
            ) : (
              <ArrowsClockwise size={12} className="animate-spin" />
            )}
            {STATUS_LABEL[status]}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Progress track */}
      <div className="flex items-center gap-1">
        {(['queued', 'provisioning', 'configuring', 'verifying', 'success'] as DeployStatus[]).map(
          (s, i, arr) => {
            const stageOrder = ['queued', 'provisioning', 'configuring', 'verifying', 'success', 'failed']
            const currentIdx = stageOrder.indexOf(status)
            const thisIdx = stageOrder.indexOf(s)
            const done = currentIdx > thisIdx
            const active = currentIdx === thisIdx

            return (
              <div key={s} className="flex items-center flex-1">
                <div
                  className={[
                    'h-1 flex-1 rounded-full transition-colors duration-500',
                    done || active
                      ? status === 'success' ? 'bg-emerald-400' : 'bg-accent'
                      : 'bg-zinc-800',
                  ].join(' ')}
                />
                {i < arr.length - 1 && <div className="w-1" />}
              </div>
            )
          },
        )}
      </div>

      {/* Log output */}
      <div
        ref={logRef}
        data-testid="deploy-log"
        className={[
          'h-72 overflow-y-auto rounded-xl bg-zinc-950 border border-zinc-800 p-4',
          'flex flex-col gap-0.5 font-mono text-xs',
        ].join(' ')}
      >
        <AnimatePresence initial={false}>
          {logs.map((line, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 28 }}
              className="flex items-start gap-3"
            >
              <span className="text-zinc-700 shrink-0">{line.ts}</span>
              <span className={LOG_COLOR[line.level]}>{line.msg}</span>
            </motion.div>
          ))}
        </AnimatePresence>
        {!isTerminal && (
          <motion.span
            animate={{ opacity: [1, 0, 1] }}
            transition={{ duration: 1, repeat: Infinity }}
            className="text-zinc-700 mt-1"
          >
            ▊
          </motion.span>
        )}
      </div>
    </div>
  )
}
