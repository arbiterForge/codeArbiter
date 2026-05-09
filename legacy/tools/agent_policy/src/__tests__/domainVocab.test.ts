import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { checkDomainVocab } from '../checks/domainVocab.js'

let tmpDir: string

beforeEach(() => {
  tmpDir = mkdtempSync(join(tmpdir(), 'fusion-vocab-test-'))
  mkdirSync(join(tmpDir, 'backend', 'src'), { recursive: true })
  mkdirSync(join(tmpDir, 'frontend', 'src'), { recursive: true })
})

afterEach(() => {
  rmSync(tmpDir, { recursive: true, force: true })
})

describe('checkDomainVocab', () => {
  it('passes for prefixed names like FusionNode, FusionAdapter, SolutionDetail', () => {
    writeFileSync(
      join(tmpDir, 'backend', 'src', 'types.ts'),
      'export interface FusionNode { id: string }\nexport type SolutionDetail = { name: string }\n',
    )
    expect(checkDomainVocab(tmpDir)).toHaveLength(0)
  })

  it('passes for single-line import statements that reference reserved names', () => {
    writeFileSync(
      join(tmpDir, 'frontend', 'src', 'graph.tsx'),
      "import type { Node } from '@xyflow/react'\n",
    )
    expect(checkDomainVocab(tmpDir)).toHaveLength(0)
  })

  it('passes for multi-line import destructures where reserved name is on its own line', () => {
    const content = [
      'import {',
      '  useNodesState,',
      '  type Node,',
      '  type Edge,',
      "} from '@xyflow/react'",
      '',
    ].join('\n')
    writeFileSync(join(tmpDir, 'frontend', 'src', 'graph.tsx'), content)
    expect(checkDomainVocab(tmpDir)).toHaveLength(0)
  })

  it('passes for canonical domain model files that declare the authoritative types', () => {
    mkdirSync(join(tmpDir, 'backend', 'src', 'schemas'), { recursive: true })
    mkdirSync(join(tmpDir, 'frontend', 'src', 'types'), { recursive: true })
    writeFileSync(
      join(tmpDir, 'backend', 'src', 'schemas', 'solution.ts'),
      'export type Solution = z.infer<typeof SolutionSchema>\n',
    )
    writeFileSync(
      join(tmpDir, 'frontend', 'src', 'types', 'solution.ts'),
      'export interface Solution { id: string }\n',
    )
    expect(checkDomainVocab(tmpDir)).toHaveLength(0)
  })

  it('passes for names with reserved words as substrings (NodeProps, AdapterEdge)', () => {
    writeFileSync(
      join(tmpDir, 'backend', 'src', 'ok.ts'),
      'export interface NodeProps { x: number }\nexport type AdapterEdge = string\n',
    )
    expect(checkDomainVocab(tmpDir)).toHaveLength(0)
  })

  it('passes when no source files exist', () => {
    expect(checkDomainVocab(tmpDir)).toHaveLength(0)
  })

  it('fails when a type is declared with the exact name Node', () => {
    writeFileSync(join(tmpDir, 'backend', 'src', 'bad.ts'), 'export type Node = { id: string }\n')
    const findings = checkDomainVocab(tmpDir)
    expect(findings).toHaveLength(1)
    expect(findings[0]?.rule).toBe('domain-vocab')
    expect(findings[0]?.file).toContain('bad.ts')
    expect(findings[0]?.line).toBe(1)
  })

  it('fails when an interface is declared with the exact name Adapter', () => {
    writeFileSync(
      join(tmpDir, 'frontend', 'src', 'bad.tsx'),
      'interface Adapter { name: string }\n',
    )
    const findings = checkDomainVocab(tmpDir)
    expect(findings).toHaveLength(1)
    expect(findings[0]?.rule).toBe('domain-vocab')
  })

  it('fails when a class is declared with the exact name Solution', () => {
    writeFileSync(join(tmpDir, 'backend', 'src', 'bad.ts'), 'class Solution { }\n')
    expect(checkDomainVocab(tmpDir)).toHaveLength(1)
  })

  it('fails for unexported declarations too (not just export)', () => {
    writeFileSync(join(tmpDir, 'backend', 'src', 'bad.ts'), 'type Node = { id: string }\n')
    expect(checkDomainVocab(tmpDir)).toHaveLength(1)
  })

  it('reports the correct line number', () => {
    const content = 'const x = 1\n\nexport interface Node { id: string }\n'
    writeFileSync(join(tmpDir, 'backend', 'src', 'bad.ts'), content)
    const findings = checkDomainVocab(tmpDir)
    expect(findings[0]?.line).toBe(3)
  })
})
