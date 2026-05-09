import type { DeployFormData } from '../DeployWizardPage'

interface FieldConfig {
  key: keyof Pick<DeployFormData, 'keycloakRealm' | 'keycloakUrl' | 'adDomain' | 'replicaCount'>
  label: string
  type: 'text' | 'url' | 'number'
  placeholder: string
  hint: string
  required: boolean
  validate?: (v: string) => string | null
}

const FIELDS: FieldConfig[] = [
  {
    key: 'keycloakRealm',
    label: 'Keycloak Realm',
    type: 'text',
    placeholder: 'gdit-internal',
    hint: 'The realm name configured in your Keycloak instance.',
    required: true,
  },
  {
    key: 'keycloakUrl',
    label: 'Keycloak URL',
    type: 'url',
    placeholder: 'https://keycloak.internal',
    hint: 'Base URL of the Keycloak server. Must be reachable from Z-WORKER.',
    required: true,
    validate: (v) => {
      try {
        const url = new URL(v)
        if (!['https:', 'http:'].includes(url.protocol)) return 'Must be an http(s) URL'
        return null
      } catch {
        return 'Must be a valid URL'
      }
    },
  },
  {
    key: 'adDomain',
    label: 'Active Directory Domain',
    type: 'text',
    placeholder: 'corp.gdit.com',
    hint: 'FQDN of the AD domain to federate.',
    required: true,
  },
  {
    key: 'replicaCount',
    label: 'Replica Count',
    type: 'number',
    placeholder: '2',
    hint: 'Number of Keycloak replicas to provision (1–5).',
    required: true,
    validate: (v) => {
      const n = parseInt(v)
      if (isNaN(n) || n < 1 || n > 5) return 'Must be between 1 and 5'
      return null
    },
  },
]

interface Step1ConfigureProps {
  formData: DeployFormData
  onChange: (patch: Partial<DeployFormData>) => void
  errors: Partial<Record<keyof DeployFormData, string>>
  onBlur: (key: keyof DeployFormData) => void
}

export function Step1Configure({ formData, onChange, errors, onBlur }: Step1ConfigureProps) {
  return (
    <div data-testid="step-1" className="flex flex-col gap-6 max-w-xl">
      <div>
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">Configure</h2>
        <p className="text-sm text-zinc-500">
          Set the runtime variables for this solution. Values are passed to the Ansible
          playbook and never stored in plain text.
        </p>
      </div>

      <div className="flex flex-col gap-5">
        {FIELDS.map(({ key, label, type, placeholder, hint, required }) => {
          const error = errors[key]
          return (
            <div key={key} className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-zinc-300" htmlFor={key}>
                {label}
                {required && <span className="text-rose-500 ml-1">*</span>}
              </label>
              <input
                id={key}
                type={type}
                value={formData[key] ?? ''}
                placeholder={placeholder}
                onChange={(e) => onChange({ [key]: e.target.value })}
                onBlur={() => onBlur(key)}
                className={[
                  'bg-zinc-900 border rounded-lg px-3 py-2 text-sm text-zinc-100',
                  'placeholder:text-zinc-600 outline-none font-mono',
                  'transition-colors duration-150',
                  'focus:border-accent focus:ring-1 focus:ring-accent/20',
                  error ? 'border-rose-500/60' : 'border-zinc-700 hover:border-zinc-600',
                ].join(' ')}
                aria-describedby={error ? `${key}-error` : `${key}-hint`}
                aria-invalid={!!error}
              />
              {error ? (
                <p id={`${key}-error`} className="text-xs text-rose-400" role="alert">
                  {error}
                </p>
              ) : (
                <p id={`${key}-hint`} className="text-xs text-zinc-600">
                  {hint}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function validateStep1(data: DeployFormData): Partial<Record<keyof DeployFormData, string>> {
  const errors: Partial<Record<keyof DeployFormData, string>> = {}
  for (const field of FIELDS) {
    const value = data[field.key] ?? ''
    if (field.required && !value.trim()) {
      errors[field.key] = 'This field is required'
      continue
    }
    if (value && field.validate) {
      const err = field.validate(value)
      if (err) errors[field.key] = err
    }
  }
  return errors
}

export function isStep1Valid(data: DeployFormData): boolean {
  return Object.keys(validateStep1(data)).length === 0 &&
    FIELDS.filter((f) => f.required).every((f) => (data[f.key] ?? '').trim().length > 0)
}
