import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { StepIndicator } from './deploy/StepIndicator'
import { Step1Configure, validateStep1, isStep1Valid } from './deploy/Step1Configure'
import { Step2Compliance, isStep2Valid } from './deploy/Step2Compliance'
import { Step3Confirm } from './deploy/Step3Confirm'
import { Step4Monitor } from './deploy/Step4Monitor'
import { useAuth } from '../lib/auth/useAuth'
import type { SolutionDetail } from '../types/solution'

export interface DeployFormData {
  keycloakRealm: string
  keycloakUrl: string
  adDomain: string
  replicaCount: string
  classification: 'none' | 'cui' | 'secret_ref' | ''
  deploymentTarget: 'on-prem' | 'cloud' | 'hybrid'
  dataDescription: string
}

const EMPTY_FORM: DeployFormData = {
  keycloakRealm: '',
  keycloakUrl: '',
  adDomain: '',
  replicaCount: '',
  classification: '',
  deploymentTarget: 'on-prem',
  dataDescription: '',
}

interface DeployWizardPageProps {
  solution: SolutionDetail
}

export function DeployWizardPage({ solution }: DeployWizardPageProps) {
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [formData, setFormData] = useState<DeployFormData>(EMPTY_FORM)
  const [step1Errors, setStep1Errors] = useState<Partial<Record<keyof DeployFormData, string>>>({})
  const [, setTouched] = useState<Partial<Record<keyof DeployFormData, boolean>>>({})

  const rawStep = parseInt(searchParams.get('step') ?? '1', 10)
  const step = isNaN(rawStep) || rawStep < 1 || rawStep > 4 ? 1 : rawStep

  // Guard: Confirm/Monitor (step 3+) require step 1 to be filled.
  // Step 2 is still an input step and is safe to reach with empty data.
  useEffect(() => {
    if (step >= 3 && !isStep1Valid(formData)) {
      setSearchParams({ step: '1' }, { replace: true })
    }
  }, [step, formData, setSearchParams])

  function goToStep(n: number) {
    setSearchParams({ step: String(n) })
  }

  function handleChange(patch: Partial<DeployFormData>) {
    setFormData((prev) => ({ ...prev, ...patch }))
  }

  function handleBlur(key: keyof DeployFormData) {
    setTouched((prev) => ({ ...prev, [key]: true }))
    const errs = validateStep1(formData)
    setStep1Errors(errs)
  }

  function handleNext() {
    if (step === 1) {
      const errs = validateStep1(formData)
      if (Object.keys(errs).length > 0) {
        setStep1Errors(errs)
        const allTouched = Object.fromEntries(
          Object.keys(errs).map((k) => [k, true])
        ) as Partial<Record<keyof DeployFormData, boolean>>
        setTouched(allTouched)
        return
      }
    }
    goToStep(step + 1)
  }

  function handleBack() {
    goToStep(step - 1)
  }

  function handleConfirm() {
    goToStep(4)
  }

  const canAdvance =
    step === 1 ? isStep1Valid(formData) :
    step === 2 ? isStep2Valid(formData) :
    false

  const isTerminal = step === 4

  return (
    <div className="flex flex-col gap-8 px-8 py-8 max-w-3xl w-full">
      {/* Header */}
      <div className="flex flex-col gap-1">
        <p className="text-xs font-mono text-zinc-600 uppercase tracking-widest">Deploy</p>
        <h1 className="text-xl font-semibold text-zinc-100">{solution.name}</h1>
      </div>

      <StepIndicator current={step} />

      {/* Step content */}
      <div>
        {step === 1 && (
          <Step1Configure
            formData={formData}
            onChange={handleChange}
            errors={step1Errors}
            onBlur={handleBlur}
          />
        )}
        {step === 2 && (
          <Step2Compliance
            formData={formData}
            onChange={handleChange}
          />
        )}
        {step === 3 && (
          <Step3Confirm
            solution={solution}
            formData={formData}
            onBack={handleBack}
            onConfirm={handleConfirm}
          />
        )}
        {step === 4 && (
          <Step4Monitor solution={solution} actorSub={user?.sub ?? 'unknown'} />
        )}
      </div>

      {/* Footer nav — hidden on step 3 (has own buttons) and step 4 */}
      {step !== 3 && !isTerminal && (
        <div className="flex items-center gap-3">
          {step > 1 && (
            <button
              onClick={handleBack}
              className="px-4 py-2 rounded-lg text-sm text-zinc-400 hover:text-zinc-200 border border-zinc-800 hover:border-zinc-700 transition-colors duration-150 active:scale-[0.98]"
            >
              Back
            </button>
          )}
          <button
            onClick={handleNext}
            disabled={!canAdvance}
            className="px-5 py-2 rounded-lg text-sm font-medium bg-accent text-zinc-950 hover:bg-accent-hover transition-colors duration-150 active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
