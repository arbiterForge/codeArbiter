import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { checkConfirmPlaceholders } from '../checks/confirmPlaceholder.js'

let tmpDir: string

beforeEach(() => {
  tmpDir = mkdtempSync(join(tmpdir(), 'fusion-confirm-test-'))
  mkdirSync(join(tmpDir, 'backend', 'src'), { recursive: true })
  mkdirSync(join(tmpDir, 'frontend', 'src'), { recursive: true })
  mkdirSync(join(tmpDir, 'docs'), { recursive: true })
})

afterEach(() => {
  rmSync(tmpDir, { recursive: true, force: true })
})

describe('checkConfirmPlaceholders', () => {
  it('passes for a clean backend/src with no CONFIRM tokens', () => {
    writeFileSync(join(tmpDir, 'backend', 'src', 'clean.ts'), 'const x = 1\n')
    expect(checkConfirmPlaceholders(tmpDir)).toHaveLength(0)
  })

  it('passes when no source files exist at all', () => {
    expect(checkConfirmPlaceholders(tmpDir)).toHaveLength(0)
  })

  it('fails when a CONFIRM token appears in backend/src', () => {
    writeFileSync(
      join(tmpDir, 'backend', 'src', 'bad.ts'),
      '// [CONFIRM-05] resolve before deploy\nconst x = 1\n',
    )
    const findings = checkConfirmPlaceholders(tmpDir)
    expect(findings).toHaveLength(1)
    expect(findings[0]?.rule).toBe('confirm-placeholder')
    expect(findings[0]?.file).toContain('bad.ts')
    expect(findings[0]?.line).toBe(1)
  })

  it('fails when a CONFIRM token appears in frontend/src', () => {
    writeFileSync(
      join(tmpDir, 'frontend', 'src', 'widget.tsx'),
      'const label = "[CONFIRM-12] pending"\n',
    )
    const findings = checkConfirmPlaceholders(tmpDir)
    expect(findings).toHaveLength(1)
    expect(findings[0]?.file).toContain('widget.tsx')
    expect(findings[0]?.line).toBe(1)
  })

  it('reports the correct line number for mid-file occurrences', () => {
    const content = 'const a = 1\nconst b = 2\n// [CONFIRM-03]\nconst c = 3\n'
    writeFileSync(join(tmpDir, 'backend', 'src', 'mid.ts'), content)
    const findings = checkConfirmPlaceholders(tmpDir)
    expect(findings[0]?.line).toBe(3)
  })

  it('passes when CONFIRM token appears only in docs/', () => {
    writeFileSync(join(tmpDir, 'docs', 'open-questions.md'), '## [CONFIRM-05] unresolved\n')
    expect(checkConfirmPlaceholders(tmpDir)).toHaveLength(0)
  })

  it('reports multiple findings across multiple files', () => {
    writeFileSync(join(tmpDir, 'backend', 'src', 'a.ts'), '// [CONFIRM-01]\n')
    writeFileSync(join(tmpDir, 'frontend', 'src', 'b.ts'), '// [CONFIRM-02]\n')
    expect(checkConfirmPlaceholders(tmpDir)).toHaveLength(2)
  })
})
