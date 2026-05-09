import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Finding } from '../types.js'
import { walkTs } from '../utils/walk.js'

const CONFIRM_PATTERN = /\[CONFIRM-\d+\]/

const SCANNED_DIRS = ['backend/src', 'frontend/src']

export function checkConfirmPlaceholders(rootDir: string): Finding[] {
  const findings: Finding[] = []

  for (const base of SCANNED_DIRS) {
    const dir = join(rootDir, base)
    try {
      for (const file of walkTs(dir)) {
        const lines = readFileSync(file, 'utf8').split('\n')
        lines.forEach((line, i) => {
          if (CONFIRM_PATTERN.test(line)) {
            findings.push({
              rule: 'confirm-placeholder',
              file,
              line: i + 1,
              message: `Unresolved [CONFIRM-NN] token in source file (rule 17 — must not resolve by guessing or leave in source)`,
            })
          }
        })
      }
    } catch {
      // Directory doesn't exist yet — nothing to scan
    }
  }

  return findings
}
