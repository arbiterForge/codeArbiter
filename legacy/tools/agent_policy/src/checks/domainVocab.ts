import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Finding } from '../types.js'
import { walkTs } from '../utils/walk.js'

// Matches declarations of reserved domain terms — type aliases, interfaces, and classes.
// Requires `=` or `{` on the same line after the term name, which distinguishes real
// declarations from import destructure members (`type Node,` has no `=` or `{`).
// The \b prevents matching prefixed names like FusionNode, NodeProps, AdapterEdge.
const VOCAB_PATTERN = /(?:export\s+)?(?:type|interface|class)\s+(?:Node|Adapter|Solution)\b[^={\n]*[={]/

// Files that contain the authoritative TypeScript encodings of the domain types.
// These are the canonical definitions — not violations of the vocab rule.
const ALLOWED_PATHS = ['src/schemas/solution.ts', 'src/types/solution.ts']

const SCANNED_DIRS = ['backend/src', 'frontend/src']

export function checkDomainVocab(rootDir: string): Finding[] {
  const findings: Finding[] = []

  for (const base of SCANNED_DIRS) {
    const dir = join(rootDir, base)
    try {
      for (const file of walkTs(dir)) {
        if (ALLOWED_PATHS.some((p) => file.replaceAll('\\', '/').endsWith(p))) continue
        const lines = readFileSync(file, 'utf8').split('\n')
        lines.forEach((line, i) => {
          if (VOCAB_PATTERN.test(line)) {
            findings.push({
              rule: 'domain-vocab',
              file,
              line: i + 1,
              message: `Reserved domain term declared as type/interface/class (rule 7 — see docs/domain.md)`,
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
