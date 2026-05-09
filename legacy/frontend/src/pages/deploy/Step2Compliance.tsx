import type { DeployFormData } from '../DeployWizardPage'

const CLASSIFICATIONS = [
  {
    value: 'none',
    label: 'None',
    description: 'No sensitive data. Publicly accessible information only.',
  },
  {
    value: 'cui',
    label: 'CUI',
    description: 'Controlled Unclassified Information — requires additional handling per 32 CFR 2002.',
  },
  {
    value: 'secret_ref',
    label: 'Secret Reference',
    description: 'Solution reads from Z-SECRETS. No plaintext secrets in config.',
  },
] as const

const TARGETS = ['on-prem', 'cloud', 'hybrid'] as const

interface Step2ComplianceProps {
  formData: DeployFormData
  onChange: (patch: Partial<DeployFormData>) => void
}

export function Step2Compliance({ formData, onChange }: Step2ComplianceProps) {
  return (
    <div data-testid="step-2" className="flex flex-col gap-6 max-w-xl">
      <div>
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">Compliance</h2>
        <p className="text-sm text-zinc-500">
          Declare the data classification and deployment context. This is recorded in
          the Z-AUDIT event at trigger time.
        </p>
      </div>

      {/* Classification */}
      <div className="flex flex-col gap-3">
        <p className="text-sm font-medium text-zinc-300">
          Data classification <span className="text-rose-500">*</span>
        </p>
        <div className="flex flex-col gap-2">
          {CLASSIFICATIONS.map(({ value, label, description }) => (
            <label
              key={value}
              className={[
                'flex items-start gap-3 p-3 rounded-lg border cursor-pointer',
                'transition-colors duration-150',
                formData.classification === value
                  ? 'border-accent/40 bg-accent/5'
                  : 'border-zinc-800 hover:border-zinc-700',
              ].join(' ')}
            >
              <input
                type="radio"
                name="classification"
                value={value}
                checked={formData.classification === value}
                onChange={() => onChange({ classification: value })}
                className="mt-0.5 accent-cyan-400"
              />
              <div>
                <span className="text-sm font-medium text-zinc-200">{label}</span>
                <p className="text-xs text-zinc-500 mt-0.5">{description}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* Deployment target */}
      <div className="flex flex-col gap-2">
        <label htmlFor="deploymentTarget" className="text-sm font-medium text-zinc-300">
          Deployment target <span className="text-rose-500">*</span>
        </label>
        <select
          id="deploymentTarget"
          value={formData.deploymentTarget}
          onChange={(e) => onChange({ deploymentTarget: e.target.value as typeof TARGETS[number] })}
          className={[
            'bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2',
            'text-sm text-zinc-100 outline-none font-mono',
            'focus:border-accent focus:ring-1 focus:ring-accent/20',
            'transition-colors duration-150',
          ].join(' ')}
        >
          {TARGETS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      {/* Data description */}
      <div className="flex flex-col gap-2">
        <label htmlFor="dataDescription" className="text-sm font-medium text-zinc-300">
          Brief description of data touched <span className="text-rose-500">*</span>
        </label>
        <textarea
          id="dataDescription"
          rows={3}
          value={formData.dataDescription}
          onChange={(e) => onChange({ dataDescription: e.target.value })}
          placeholder="e.g. Internal identity data — employee UPNs and group memberships. No CUI."
          className={[
            'bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2',
            'text-sm text-zinc-100 placeholder:text-zinc-600 outline-none resize-none',
            'focus:border-accent focus:ring-1 focus:ring-accent/20',
            'transition-colors duration-150',
          ].join(' ')}
        />
        <p className="text-xs text-zinc-600">Recorded verbatim in the Z-AUDIT event.</p>
      </div>
    </div>
  )
}

export function isStep2Valid(data: DeployFormData): boolean {
  return (
    !!data.classification &&
    !!data.deploymentTarget &&
    data.dataDescription.trim().length > 0
  )
}
