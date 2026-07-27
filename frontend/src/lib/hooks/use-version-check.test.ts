import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useVersionCheck } from './use-version-check'

const getConfigMock = vi.fn()
const toastInfoMock = vi.fn()

vi.mock('@/lib/config', () => ({
  getConfig: () => getConfigMock(),
}))
vi.mock('sonner', () => ({
  toast: { info: (...args: unknown[]) => toastInfoMock(...args) },
}))
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => key === 'advanced.updateAvailable'
      ? 'Update {version}'
      : key,
  }),
}))

describe('useVersionCheck', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    getConfigMock.mockResolvedValue({
      hasUpdate: true,
      latestVersion: '1.2.3',
    })
    vi.spyOn(window, 'open').mockImplementation(() => null)
  })

  it('opens the canonical Deeper Notebook release page', async () => {
    renderHook(() => useVersionCheck())
    await act(async () => {
      await Promise.resolve()
    })

    const options = toastInfoMock.mock.calls[0][1]
    options.action.onClick()

    expect(window.open).toHaveBeenCalledWith(
      'https://github.com/Antman1526/Deeper-Notebook/releases/latest',
      '_blank',
    )
  })
})
