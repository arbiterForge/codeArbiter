import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { checkFusionStage } from '../checks/fusionStage.js'

let tmpDir: string

beforeEach(() => {
  tmpDir = mkdtempSync(join(tmpdir(), 'fusion-stage-test-'))
})

afterEach(() => {
  rmSync(tmpDir, { recursive: true, force: true })
})

describe('checkFusionStage', () => {
  it('passes when .fusion/stage contains 1', () => {
    mkdirSync(join(tmpDir, '.fusion'))
    writeFileSync(join(tmpDir, '.fusion', 'stage'), '1')
    expect(checkFusionStage(tmpDir)).toHaveLength(0)
  })

  it('passes for all valid stages 2, 3, 4', () => {
    mkdirSync(join(tmpDir, '.fusion'))
    for (const s of ['2', '3', '4']) {
      writeFileSync(join(tmpDir, '.fusion', 'stage'), s)
      expect(checkFusionStage(tmpDir)).toHaveLength(0)
    }
  })

  it('passes when .fusion/stage has trailing whitespace', () => {
    mkdirSync(join(tmpDir, '.fusion'))
    writeFileSync(join(tmpDir, '.fusion', 'stage'), '1\n')
    expect(checkFusionStage(tmpDir)).toHaveLength(0)
  })

  it('fails when .fusion/stage file is missing', () => {
    const findings = checkFusionStage(tmpDir)
    expect(findings).toHaveLength(1)
    expect(findings[0]?.rule).toBe('fusion-stage')
    expect(findings[0]?.message).toMatch(/missing/)
  })

  it('fails when .fusion directory is missing', () => {
    const findings = checkFusionStage(tmpDir)
    expect(findings).toHaveLength(1)
  })

  it('fails when .fusion/stage contains a non-integer string', () => {
    mkdirSync(join(tmpDir, '.fusion'))
    writeFileSync(join(tmpDir, '.fusion', 'stage'), 'foo')
    const findings = checkFusionStage(tmpDir)
    expect(findings).toHaveLength(1)
    expect(findings[0]?.message).toMatch(/foo/)
  })

  it('fails when .fusion/stage is 0 (below range)', () => {
    mkdirSync(join(tmpDir, '.fusion'))
    writeFileSync(join(tmpDir, '.fusion', 'stage'), '0')
    expect(checkFusionStage(tmpDir)).toHaveLength(1)
  })

  it('fails when .fusion/stage is 5 (above range)', () => {
    mkdirSync(join(tmpDir, '.fusion'))
    writeFileSync(join(tmpDir, '.fusion', 'stage'), '5')
    expect(checkFusionStage(tmpDir)).toHaveLength(1)
  })

  it('fails when .fusion/stage is a float', () => {
    mkdirSync(join(tmpDir, '.fusion'))
    writeFileSync(join(tmpDir, '.fusion', 'stage'), '1.5')
    expect(checkFusionStage(tmpDir)).toHaveLength(1)
  })
})
