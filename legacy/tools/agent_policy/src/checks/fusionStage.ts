import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Finding } from '../types.js'

export function checkFusionStage(rootDir: string): Finding[] {
  const stagePath = join(rootDir, '.fusion', 'stage')
  try {
    const raw = readFileSync(stagePath, 'utf8').trim()
    const n = Number(raw)
    if (!Number.isInteger(n) || n < 1 || n > 4) {
      return [
        {
          rule: 'fusion-stage',
          file: stagePath,
          message: `.fusion/stage must be an integer 1–4, got: "${raw}"`,
        },
      ]
    }
    return []
  } catch {
    return [
      {
        rule: 'fusion-stage',
        file: stagePath,
        message: '.fusion/stage is missing or unreadable — every stage-gated CI check depends on this file',
      },
    ]
  }
}
