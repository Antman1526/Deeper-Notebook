// v0.8.6 Item D — Vitest tests for the LauncherPrefsPage component.
//
// Four test cases:
// 1. Renders all four input fields.
// 2. Save button calls the mutation with the right diff (only changed fields).
// 3. Restart banner appears only after a successful mutation.
// 4. Frontend whitelist guard: unknown keys are never submitted.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import LauncherPrefsPage from './page'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock the hook module — we control what data comes back and capture mutate calls.
const mockMutate = vi.fn()
const mockData = { prefs: {} }
let mockIsPending = false

vi.mock('@/lib/hooks/use-launcher-prefs', () => ({
  useLauncherPrefs: () => ({
    data: mockData,
    isLoading: false,
  }),
  useUpdateLauncherPrefs: () => ({
    mutate: mockMutate,
    isPending: mockIsPending,
  }),
}))

// Mock translation — return the key so assertions work without real locale.
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    language: 'en-US',
    setLanguage: vi.fn(),
  }),
}))

// Mock AppShell to render children directly.
vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

// ---------------------------------------------------------------------------
// Test cases
// ---------------------------------------------------------------------------

describe('LauncherPrefsPage', () => {
  beforeEach(() => {
    mockMutate.mockReset()
    mockIsPending = false
    // Reset data to empty prefs between tests
    mockData.prefs = {}
  })

  it('renders all four input fields', () => {
    render(<LauncherPrefsPage />)

    expect(screen.getByTestId('draft-model-path')).toBeInTheDocument()
    expect(screen.getByTestId('draft-n-predict')).toBeInTheDocument()
    expect(screen.getByTestId('n-ctx')).toBeInTheDocument()
    expect(screen.getByTestId('n-ctx-max')).toBeInTheDocument()
  })

  it('submitting calls mutation with the correct diff payload', async () => {
    render(<LauncherPrefsPage />)

    // Change only the n_ctx field.
    const nCtxInput = screen.getByTestId('n-ctx')
    fireEvent.change(nCtxInput, { target: { value: '8192' } })

    const saveButton = screen.getByTestId('save-button')
    fireEvent.click(saveButton)

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledTimes(1)
    })

    const [payload] = mockMutate.mock.calls[0]
    // Only the changed field should be in the diff.
    expect(payload.prefs).toHaveProperty('ONP_CHAT_LLM_CTX', '8192')
    // Unchanged fields must NOT be present.
    expect(payload.prefs).not.toHaveProperty('ONP_CHAT_LLM_CTX_MAX')
    expect(payload.prefs).not.toHaveProperty('OPEN_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH')
  })

  it('restart banner appears only after a successful mutation', async () => {
    // Simulate a mutation that calls onSuccess.
    mockMutate.mockImplementation((_payload: unknown, { onSuccess }: { onSuccess: () => void }) => {
      onSuccess()
    })

    render(<LauncherPrefsPage />)

    // Banner must not be visible before save.
    expect(screen.queryByTestId('restart-banner')).not.toBeInTheDocument()

    // Trigger a change and save.
    fireEvent.change(screen.getByTestId('n-ctx'), { target: { value: '16384' } })
    fireEvent.click(screen.getByTestId('save-button'))

    await waitFor(() => {
      expect(screen.getByTestId('restart-banner')).toBeInTheDocument()
    })
  })

  it('only whitelisted keys are ever in the submitted payload', async () => {
    render(<LauncherPrefsPage />)

    // Change all four visible fields.
    fireEvent.change(screen.getByTestId('draft-model-path'), {
      target: { value: '/models/draft.gguf' },
    })
    fireEvent.change(screen.getByTestId('draft-n-predict'), {
      target: { value: '12' },
    })
    fireEvent.change(screen.getByTestId('n-ctx'), {
      target: { value: '8192' },
    })
    fireEvent.change(screen.getByTestId('n-ctx-max'), {
      target: { value: '65536' },
    })

    fireEvent.click(screen.getByTestId('save-button'))

    await waitFor(() => expect(mockMutate).toHaveBeenCalledTimes(1))

    const ALLOWED = new Set([
      'OPEN_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH',
      'OPEN_NOTEBOOK_LOCAL_DRAFT_N_PREDICT',
      'OPEN_NOTEBOOK_LOCAL_N_CTX',
      'ONP_CHAT_LLM_CTX',
      'ONP_CHAT_LLM_CTX_MAX',
    ])

    const [payload] = mockMutate.mock.calls[0]
    for (const key of Object.keys(payload.prefs)) {
      expect(ALLOWED.has(key)).toBe(true)
    }
  })
})
