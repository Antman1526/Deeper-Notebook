// v0.8.130 — Phase 4a of the 2026-09-30 UI audit: the copy added by Phases 0–3 (the
// rail and shell, the first run, the login frame) is translated, not hard-coded
// English. The keys must exist in every locale (index.test.ts checks parity) and the
// components must read them through t().

import { readFileSync } from 'fs'
import { join } from 'path'
import { describe, expect, it } from 'vitest'

import { enUS } from './en-US'

const SRC = join(__dirname, '..', '..')

const LITERALS: Record<string, string[]> = {
  'components/deeper-notebook/workspace/WorkspaceRail.tsx': [
    'aria-label="Primary"', 'aria-label="Destinations"', 'aria-label="Settings pages"',
    'Sign out?', 'You will need to sign in again',
  ],
  'components/deeper-notebook/workspace/WorkspaceAppShell.tsx': ['Skip to content'],
  'components/deeper-notebook/shell/CommandBar.tsx': ['aria-label="Menu"'],
  'components/deeper-notebook/workspace/WorkspaceAuthFrame.tsx': ['Welcome back', 'Enter your password'],
  'components/auth/LoginForm.tsx': ['Connection details'],
  'app/(dashboard)/setup-wizard/page.tsx': [
    'Getting ready', 'checks your local setup', 'Checking your setup', 'This takes a few seconds',
    'Everything is ready', 'Opening your notebooks', 'Almost ready', 'You can start now',
    'Waiting for the database', 'Your notebooks open once', "'Ready'", 'Needs attention',
    'Show details', 'Hide details', 'need attention', 'needs attention',
  ],
}

const KEYS = [
  'common.skipToContent', 'common.menu', 'navigation.primary', 'navigation.destinations',
  'navigation.settingsPages', 'auth.signOutTitle', 'auth.signOutDescription', 'auth.welcomeBack',
  'auth.welcomeDescription', 'auth.connectionDetails', 'setupWizard.firstRun.title',
  'setupWizard.firstRun.description', 'setupWizard.firstRun.loadingTitle',
  'setupWizard.firstRun.loadingBody', 'setupWizard.firstRun.healthyTitle',
  'setupWizard.firstRun.healthyBody', 'setupWizard.firstRun.degradedTitle',
  'setupWizard.firstRun.degradedBody', 'setupWizard.firstRun.notReadyTitle',
  'setupWizard.firstRun.notReadyBody', 'setupWizard.firstRun.attentionOne',
  'setupWizard.firstRun.attentionOther', 'setupWizard.firstRun.checkReady',
  'setupWizard.firstRun.checkNeedsAttention', 'setupWizard.firstRun.showDetails',
  'setupWizard.firstRun.hideDetails',
]

function lookup(key: string): unknown {
  return key.split('.').reduce<unknown>(
    (node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined),
    enUS,
  )
}

describe('UI audit copy is translated', () => {
  it.each(Object.entries(LITERALS))('%s has no hard-coded English for it', (file, literals) => {
    const source = readFileSync(join(SRC, file), 'utf8')
    expect(literals.filter((literal) => source.includes(literal))).toEqual([])
  })

  it('every key exists in en-US', () => {
    expect(KEYS.filter((key) => typeof lookup(key) !== 'string')).toEqual([])
  })
})
