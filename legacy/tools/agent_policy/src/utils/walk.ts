import { readdirSync, statSync } from 'node:fs'
import { join, extname } from 'node:path'

const TS_EXTENSIONS = new Set(['.ts', '.tsx'])

export function* walkTs(dir: string): Generator<string> {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      yield* walkTs(full)
    } else if (TS_EXTENSIONS.has(extname(entry))) {
      yield full
    }
  }
}
