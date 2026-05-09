import { describe, it, expect } from 'vitest'
import { isStep2Valid } from '../pages/deploy/Step2Compliance'
import type { DeployFormData } from '../pages/DeployWizardPage'

// isStep2Valid guards the "Next" button on Step 2 of the deploy wizard.
// It checks three fields from DeployFormData:
//   - classification: must be truthy (one of 'none' | 'cui' | 'secret_ref')
//   - deploymentTarget: must be truthy (one of 'on-prem' | 'cloud' | 'hybrid')
//   - dataDescription: must be non-empty after trimming
//
// The component renders classification as radio buttons (no default selected —
// the user must actively pick one) and deploymentTarget as a <select> which
// always renders the first option as the initial value. That means
// deploymentTarget is typically pre-filled to 'on-prem' and will almost always
// be truthy, leaving classification and dataDescription as the practical gates.

function base(): DeployFormData {
  return {
    keycloakRealm: 'gdit-internal',
    keycloakUrl: 'https://keycloak.internal',
    adDomain: 'corp.gdit.com',
    replicaCount: '1',
    classification: 'none',
    deploymentTarget: 'on-prem',
    dataDescription: 'Internal identity data — employee UPNs only.',
  }
}

describe('isStep2Valid', () => {
  it('returns true when all three required fields are filled', () => {
    expect(isStep2Valid(base())).toBe(true)
  })

  it('accepts all valid classification values', () => {
    for (const classification of ['none', 'cui', 'secret_ref'] as const) {
      expect(isStep2Valid({ ...base(), classification })).toBe(true)
    }
  })

  it('accepts all valid deploymentTarget values', () => {
    for (const deploymentTarget of ['on-prem', 'cloud', 'hybrid'] as const) {
      expect(isStep2Valid({ ...base(), deploymentTarget })).toBe(true)
    }
  })

  it('returns false when classification is empty string', () => {
    // Empty string is falsy — the user has not selected a classification.
    expect(isStep2Valid({ ...base(), classification: '' as never })).toBe(false)
  })

  it('returns false when deploymentTarget is empty string', () => {
    expect(isStep2Valid({ ...base(), deploymentTarget: '' as never })).toBe(false)
  })

  it('returns false when dataDescription is empty', () => {
    expect(isStep2Valid({ ...base(), dataDescription: '' })).toBe(false)
  })

  it('returns false when dataDescription is whitespace only', () => {
    // The check is `data.dataDescription.trim().length > 0`, so a string of
    // only spaces or tabs does not satisfy the requirement.
    expect(isStep2Valid({ ...base(), dataDescription: '   ' })).toBe(false)
    expect(isStep2Valid({ ...base(), dataDescription: '\t\n' })).toBe(false)
  })

  it('returns true when dataDescription has meaningful content surrounded by whitespace', () => {
    expect(isStep2Valid({ ...base(), dataDescription: '  some data  ' })).toBe(true)
  })
})
