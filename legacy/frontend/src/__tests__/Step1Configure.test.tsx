import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Step1Configure, validateStep1, isStep1Valid } from '../pages/deploy/Step1Configure'
import type { DeployFormData } from '../pages/DeployWizardPage'

const VALID_DATA: DeployFormData = {
  keycloakRealm: 'gdit-internal',
  keycloakUrl: 'https://keycloak.internal',
  adDomain: 'corp.gdit.com',
  replicaCount: '2',
  classification: 'none',
  deploymentTarget: 'on-prem',
  dataDescription: '',
}

const EMPTY_DATA: DeployFormData = {
  keycloakRealm: '',
  keycloakUrl: '',
  adDomain: '',
  replicaCount: '',
  classification: '',
  deploymentTarget: 'on-prem',
  dataDescription: '',
}

// ── validateStep1 — pure function ────────────────────────────────────────────

describe('validateStep1 — happy path', () => {
  it('returns no errors for fully valid form data', () => {
    expect(validateStep1(VALID_DATA)).toEqual({})
  })
})

describe('validateStep1 — missing required fields', () => {
  it('returns error for missing keycloakRealm', () => {
    const errors = validateStep1({ ...VALID_DATA, keycloakRealm: '' })
    expect(errors.keycloakRealm).toBe('This field is required')
  })

  it('returns error for missing keycloakUrl', () => {
    const errors = validateStep1({ ...VALID_DATA, keycloakUrl: '' })
    expect(errors.keycloakUrl).toBe('This field is required')
  })

  it('returns error for missing adDomain', () => {
    const errors = validateStep1({ ...VALID_DATA, adDomain: '' })
    expect(errors.adDomain).toBe('This field is required')
  })

  it('returns error for missing replicaCount', () => {
    const errors = validateStep1({ ...VALID_DATA, replicaCount: '' })
    expect(errors.replicaCount).toBe('This field is required')
  })

  it('returns errors for all fields when form is empty', () => {
    const errors = validateStep1(EMPTY_DATA)
    expect(Object.keys(errors)).toHaveLength(4)
  })
})

describe('validateStep1 — keycloakUrl validation', () => {
  it('returns error for a non-URL string', () => {
    const errors = validateStep1({ ...VALID_DATA, keycloakUrl: 'not-a-url' })
    expect(errors.keycloakUrl).toBe('Must be a valid URL')
  })

  it('returns error for an ftp:// URL (not http/https)', () => {
    const errors = validateStep1({ ...VALID_DATA, keycloakUrl: 'ftp://keycloak.internal' })
    expect(errors.keycloakUrl).toBe('Must be an http(s) URL')
  })

  it('accepts an http:// URL', () => {
    const errors = validateStep1({ ...VALID_DATA, keycloakUrl: 'http://keycloak.internal' })
    expect(errors.keycloakUrl).toBeUndefined()
  })

  it('accepts an https:// URL', () => {
    const errors = validateStep1({ ...VALID_DATA, keycloakUrl: 'https://keycloak.internal' })
    expect(errors.keycloakUrl).toBeUndefined()
  })
})

describe('validateStep1 — replicaCount validation', () => {
  it('returns error for replicaCount below minimum (0)', () => {
    const errors = validateStep1({ ...VALID_DATA, replicaCount: '0' })
    expect(errors.replicaCount).toBe('Must be between 1 and 5')
  })

  it('returns error for replicaCount above maximum (6)', () => {
    const errors = validateStep1({ ...VALID_DATA, replicaCount: '6' })
    expect(errors.replicaCount).toBe('Must be between 1 and 5')
  })

  it('returns error for non-numeric replicaCount', () => {
    const errors = validateStep1({ ...VALID_DATA, replicaCount: 'abc' })
    expect(errors.replicaCount).toBe('Must be between 1 and 5')
  })

  it('accepts boundary value 1', () => {
    const errors = validateStep1({ ...VALID_DATA, replicaCount: '1' })
    expect(errors.replicaCount).toBeUndefined()
  })

  it('accepts boundary value 5', () => {
    const errors = validateStep1({ ...VALID_DATA, replicaCount: '5' })
    expect(errors.replicaCount).toBeUndefined()
  })
})

// ── isStep1Valid ─────────────────────────────────────────────────────────────

describe('isStep1Valid', () => {
  it('returns true for fully valid form data', () => {
    expect(isStep1Valid(VALID_DATA)).toBe(true)
  })

  it('returns false for empty form', () => {
    expect(isStep1Valid(EMPTY_DATA)).toBe(false)
  })

  it('returns false when a single required field is missing', () => {
    expect(isStep1Valid({ ...VALID_DATA, adDomain: '' })).toBe(false)
  })

  it('returns false when keycloakUrl is invalid', () => {
    expect(isStep1Valid({ ...VALID_DATA, keycloakUrl: 'not-a-url' })).toBe(false)
  })

  it('returns false when replicaCount is out of range', () => {
    expect(isStep1Valid({ ...VALID_DATA, replicaCount: '10' })).toBe(false)
  })
})

// ── Step1Configure component ─────────────────────────────────────────────────

describe('Step1Configure — rendering', () => {
  const noop = vi.fn()

  it('renders the step-1 container', () => {
    render(
      <Step1Configure formData={EMPTY_DATA} onChange={noop} errors={{}} onBlur={noop} />,
    )
    expect(screen.getByTestId('step-1')).toBeInTheDocument()
  })

  it('renders all four field labels', () => {
    render(
      <Step1Configure formData={EMPTY_DATA} onChange={noop} errors={{}} onBlur={noop} />,
    )
    expect(screen.getByLabelText(/keycloak realm/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/keycloak url/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/active directory domain/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/replica count/i)).toBeInTheDocument()
  })

  it('shows the current formData values in inputs', () => {
    render(
      <Step1Configure formData={VALID_DATA} onChange={noop} errors={{}} onBlur={noop} />,
    )
    expect(screen.getByDisplayValue('gdit-internal')).toBeInTheDocument()
    expect(screen.getByDisplayValue('https://keycloak.internal')).toBeInTheDocument()
    expect(screen.getByDisplayValue('corp.gdit.com')).toBeInTheDocument()
  })
})

describe('Step1Configure — error states', () => {
  const noop = vi.fn()

  it('shows an error message when keycloakRealm has an error', () => {
    render(
      <Step1Configure
        formData={EMPTY_DATA}
        onChange={noop}
        errors={{ keycloakRealm: 'This field is required' }}
        onBlur={noop}
      />,
    )
    expect(screen.getByText('This field is required')).toBeInTheDocument()
  })

  it('marks the errored input as aria-invalid', () => {
    render(
      <Step1Configure
        formData={EMPTY_DATA}
        onChange={noop}
        errors={{ keycloakUrl: 'Must be a valid URL' }}
        onBlur={noop}
      />,
    )
    const input = screen.getByLabelText(/keycloak url/i)
    expect(input).toHaveAttribute('aria-invalid', 'true')
  })

  it('calls onChange when an input value changes', () => {
    const handleChange = vi.fn()
    render(
      <Step1Configure formData={EMPTY_DATA} onChange={handleChange} errors={{}} onBlur={noop} />,
    )
    fireEvent.change(screen.getByLabelText(/keycloak realm/i), {
      target: { value: 'my-realm' },
    })
    expect(handleChange).toHaveBeenCalledWith({ keycloakRealm: 'my-realm' })
  })

  it('calls onBlur when an input loses focus', () => {
    const handleBlur = vi.fn()
    render(
      <Step1Configure formData={EMPTY_DATA} onChange={noop} errors={{}} onBlur={handleBlur} />,
    )
    fireEvent.blur(screen.getByLabelText(/keycloak realm/i))
    expect(handleBlur).toHaveBeenCalledWith('keycloakRealm')
  })
})
