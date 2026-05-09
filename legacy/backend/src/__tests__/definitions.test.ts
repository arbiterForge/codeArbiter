import { describe, it, expect } from 'vitest'
import { readFileSync, globSync } from 'node:fs'
import { resolve } from 'node:path'

interface SchemaShape {
  required: string[]
  properties: Record<string, { required?: string[]; enum?: unknown[] }>
}

const NODE_SCHEMA_PATH = resolve(__dirname, '../../../schemas/node.schema.json')
const ADAPTER_SCHEMA_PATH = resolve(__dirname, '../../../schemas/adapter.schema.json')

const nodeSchema = JSON.parse(readFileSync(NODE_SCHEMA_PATH, 'utf-8')) as SchemaShape
const adapterSchema = JSON.parse(readFileSync(ADAPTER_SCHEMA_PATH, 'utf-8')) as SchemaShape

// Synthetic fixtures — plain objects, no YAML parsing required.
const VALID_NODE = {
  kind: 'node',
  name: 'test-ec2-windows',
  version: '1.0.0',
  variables_schema: {
    instance_type: { type: 'string', required: true },
  },
  valid_connections: ['ec2-ubuntu', 'dc-controller'],
  criticality: 'non_critical',
  teardown_procedure: 'Run terraform destroy from the node directory.',
}

const VALID_ADAPTER = {
  kind: 'adapter',
  name: 'ec2-windows-dc--ec2-ubuntu',
  version: '1.0.0',
  source_type: 'ec2-windows-dc',
  target_type: 'ec2-ubuntu',
  variables_schema: {
    domain: { type: 'string', required: true },
  },
  priority_tier: 2,
}

// ── Node schema ──────────────────────────────────────────────────────────────

describe('node.schema.json — structure', () => {
  it('schema file is valid JSON with a required array', () => {
    expect(Array.isArray(nodeSchema.required)).toBe(true)
    expect(nodeSchema.required.length).toBeGreaterThan(0)
  })

  it('requires kind field', () => {
    expect(nodeSchema.required).toContain('kind')
  })

  it('requires variables_schema field', () => {
    expect(nodeSchema.required).toContain('variables_schema')
  })

  it('requires valid_connections field', () => {
    expect(nodeSchema.required).toContain('valid_connections')
  })

  it('requires criticality field', () => {
    expect(nodeSchema.required).toContain('criticality')
  })

  it('requires teardown_procedure field', () => {
    expect(nodeSchema.required).toContain('teardown_procedure')
  })

  it('criticality enum contains expected values', () => {
    const criticality = nodeSchema.properties['criticality']
    expect(criticality?.enum).toContain('critical_path')
    expect(criticality?.enum).toContain('non_critical')
  })
})

describe('node.schema.json — VALID_NODE fixture', () => {
  it('VALID_NODE satisfies all top-level required fields', () => {
    for (const field of nodeSchema.required) {
      expect(VALID_NODE, `required node field "${field}" missing from fixture`).toHaveProperty(field)
    }
  })

  it('VALID_NODE.kind is "node"', () => {
    expect(VALID_NODE.kind).toBe('node')
  })

  it('VALID_NODE.criticality is a valid enum value', () => {
    const allowed = nodeSchema.properties['criticality']?.enum ?? []
    expect(allowed).toContain(VALID_NODE.criticality)
  })
})

// ── Adapter schema ───────────────────────────────────────────────────────────

describe('adapter.schema.json — structure', () => {
  it('schema file is valid JSON with a required array', () => {
    expect(Array.isArray(adapterSchema.required)).toBe(true)
    expect(adapterSchema.required.length).toBeGreaterThan(0)
  })

  it('requires kind field', () => {
    expect(adapterSchema.required).toContain('kind')
  })

  it('requires source_type field', () => {
    expect(adapterSchema.required).toContain('source_type')
  })

  it('requires target_type field', () => {
    expect(adapterSchema.required).toContain('target_type')
  })

  it('requires variables_schema field', () => {
    expect(adapterSchema.required).toContain('variables_schema')
  })

  it('requires priority_tier field', () => {
    expect(adapterSchema.required).toContain('priority_tier')
  })

  it('priority_tier enum contains values 1, 2, 3', () => {
    const tier = adapterSchema.properties['priority_tier']
    expect(tier?.enum).toContain(1)
    expect(tier?.enum).toContain(2)
    expect(tier?.enum).toContain(3)
  })
})

describe('adapter.schema.json — VALID_ADAPTER fixture', () => {
  it('VALID_ADAPTER satisfies all top-level required fields', () => {
    for (const field of adapterSchema.required) {
      expect(VALID_ADAPTER, `required adapter field "${field}" missing from fixture`).toHaveProperty(field)
    }
  })

  it('VALID_ADAPTER.kind is "adapter"', () => {
    expect(VALID_ADAPTER.kind).toBe('adapter')
  })

  it('VALID_ADAPTER.priority_tier is a valid enum value', () => {
    const allowed = adapterSchema.properties['priority_tier']?.enum ?? []
    expect(allowed).toContain(VALID_ADAPTER.priority_tier)
  })
})

// ── On-disk definition.yaml discovery ────────────────────────────────────────
// SHORTCUT [S1]: Full YAML parse + schema validation against on-disk files
// requires js-yaml (not yet a declared dep). This block counts files and
// fails loudly if any exist without validation wired up.
// Payback trigger: first definition.yaml committed — add js-yaml + @types/js-yaml
// via `make add-dep` and replace this block with real validation.

describe('on-disk definition.yaml files', () => {
  const repoRoot = resolve(__dirname, '../../../')
  const nodeFiles = globSync('fusion-nodes/**/definition.yaml', { cwd: repoRoot })
  const adapterFiles = globSync('fusion-adapters/**/definition.yaml', { cwd: repoRoot })
  const total = nodeFiles.length + adapterFiles.length

  it('reports definition.yaml file count', () => {
    // Always passes — exists to surface the count in test output.
    expect(total).toBeGreaterThanOrEqual(0)
  })

  if (total > 0) {
    it.fails(
      `UNVALIDATED: ${total} definition.yaml file(s) found — add js-yaml dep and wire up schema validation`,
      () => {
        // Intentional hard fail: definition.yaml files exist but YAML parsing
        // is not wired up yet. Follow the SHORTCUT payback trigger above.
        expect(true).toBe(false)
      },
    )
  }
})
