import { ArrowLeft, Rocket, ShieldCheck } from '@phosphor-icons/react'
import { motion } from 'framer-motion'
import type { DeployFormData } from '../DeployWizardPage'
import type { SolutionDetail } from '../../types/solution'

interface Step3ConfirmProps {
  solution: SolutionDetail
  formData: DeployFormData
  onBack: () => void
  onConfirm: () => void
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between py-2.5 border-b border-zinc-800/60 last:border-0 gap-4">
      <span className="text-xs text-zinc-500 shrink-0">{label}</span>
      <span className="text-xs font-mono text-zinc-200 text-right break-all">{value}</span>
    </div>
  )
}

export function Step3Confirm({ solution, formData, onBack, onConfirm }: Step3ConfirmProps) {
  const auditPreview = {
    action: 'deploy.solution',
    'actor.id': '[authenticated via OIDC]',
    'actor.type': 'user',
    'subject.type': 'solution',
    'subject.id': solution.id,
    classification: formData.classification,
    'deployment_target': formData.deploymentTarget,
    outcome: 'pending → success | failure',
    git_sha: '[resolved at trigger]',
    'source.request_id': '[generated at trigger]',
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div>
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">Confirm Deployment</h2>
        <p className="text-sm text-zinc-500">
          Review the deployment parameters before triggering. This action cannot be undone
          without a separate teardown.
        </p>
      </div>

      {/* Summary */}
      <div data-testid="deploy-summary" className="flex flex-col gap-0 bg-zinc-900 rounded-xl border border-zinc-800 px-4 divide-y divide-zinc-800/60">
        <Row label="Solution" value={solution.name} />
        <Row label="Version" value={solution.version} />
        <Row label="Deployment target" value={formData.deploymentTarget} />
        <Row label="Classification" value={formData.classification} />
        <Row label="Keycloak realm" value={formData.keycloakRealm} />
        <Row label="Keycloak URL" value={formData.keycloakUrl} />
        <Row label="AD domain" value={formData.adDomain} />
        <Row label="Replica count" value={formData.replicaCount} />
        <Row label="Data description" value={formData.dataDescription} />
      </div>

      {/* Z-AUDIT event preview */}
      <div data-testid="audit-preview" className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck size={14} weight="fill" className="text-accent" />
          <span className="text-xs font-semibold text-zinc-400 tracking-widest uppercase">
            Z-AUDIT event preview
          </span>
        </div>
        <p className="text-xs text-zinc-600">
          The following event will be emitted to the append-only Z-AUDIT sink at trigger time.
          Fields marked <span className="text-zinc-400 font-mono">[resolved at trigger]</span> are
          populated by the backend.
        </p>
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', stiffness: 200, damping: 24, delay: 0.1 }}
          className={[
            'bg-zinc-950 border border-zinc-800 rounded-xl p-4',
            'text-xs font-mono leading-relaxed overflow-x-auto',
            'flex flex-col gap-0.5',
          ].join(' ')}
        >
          {Object.entries(auditPreview).map(([key, value]) => (
            <div key={key} className="flex gap-2">
              <span className="text-zinc-600 shrink-0">{`"${key}":`}</span>
              <span className="text-zinc-400">{value}</span>
            </div>
          ))}
        </motion.div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm text-zinc-400 hover:text-zinc-200 border border-zinc-800 hover:border-zinc-700 transition-colors duration-150 active:scale-[0.98]"
        >
          <ArrowLeft size={14} />
          Back
        </button>
        <button
          onClick={onConfirm}
          className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium bg-accent text-zinc-950 hover:bg-accent-hover transition-colors duration-150 active:scale-[0.98]"
        >
          <Rocket size={14} weight="fill" />
          Deploy Solution
        </button>
      </div>
    </div>
  )
}
