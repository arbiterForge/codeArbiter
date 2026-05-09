import { checkFusionStage } from './checks/fusionStage.js'
import { checkConfirmPlaceholders } from './checks/confirmPlaceholder.js'
import { checkDomainVocab } from './checks/domainVocab.js'

const rootDir = process.argv[2] ?? process.cwd()

const findings = [
  ...checkFusionStage(rootDir),
  ...checkConfirmPlaceholders(rootDir),
  ...checkDomainVocab(rootDir),
]

for (const f of findings) {
  const loc = f.line != null ? `:${f.line}` : ''
  console.error(`[${f.rule}] ${f.file}${loc} — ${f.message}`)
}

if (findings.length > 0) {
  console.error(`\nagent-policy-check: ${findings.length} violation(s) found`)
  process.exit(1)
} else {
  console.log('agent-policy-check: OK')
}
