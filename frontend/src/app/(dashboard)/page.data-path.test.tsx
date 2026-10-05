import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { UNKNOWN_RUNTIME_SNAPSHOT } from '@/lib/api/runtime'

import DashboardPage from './page'

// v0.8.130 — Home's tip named ~/.deeper-notebook/ whatever folder the install really
// used (seen in a packaged run with a custom data folder). The page now takes the
// folder from /api/config. The presentation is replaced by a probe here because the
// shared test setup translates every string to its key, which drops the tip's markup.
const configFixture = vi.hoisted(() => ({ dataPath: null as string | null, fails: false }))

vi.mock('@/lib/config', () => ({
  getConfig: async () => {
    if (configFixture.fails) throw new Error('offline')
    return { apiUrl: '', version: 'test', buildTime: '', dataPath: configFixture.dataPath }
  },
}))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/lib/hooks/use-notebooks', () => ({ useNotebooks: () => ({ data: [], isLoading: false }) }))
vi.mock('@/lib/hooks/use-runtime-snapshot', () => ({
  useRuntimeSnapshot: () => ({ data: UNKNOWN_RUNTIME_SNAPSHOT, isLoading: false, refetch: vi.fn() }),
}))
vi.mock('@/lib/hooks/use-create-dialogs', () => ({
  useCreateDialogs: () => ({ openNotebookDialog: vi.fn(), openPodcastDialog: vi.fn() }),
}))
vi.mock('@/lib/features', () => ({ isVisualSystemV2Enabled: () => true }))
vi.mock('@/components/deeper-notebook/workspace/WorkspaceHome', () => ({
  WorkspaceHome: ({ dataPath }: { dataPath?: string }) => <code data-testid="data-path">{dataPath}</code>,
}))
vi.mock('@/components/deeper-notebook/horizon/IntelligenceHorizon', () => ({
  IntelligenceHorizon: () => null,
}))

describe('DashboardPage data folder', () => {
  beforeEach(() => {
    configFixture.dataPath = null
    configFixture.fails = false
  })

  it('names the folder this install really keeps its data in', async () => {
    configFixture.dataPath = '/Volumes/Research/notebook-data/'
    render(<DashboardPage />)
    expect(await screen.findByText('/Volumes/Research/notebook-data/')).toBeInTheDocument()
  })

  it('keeps the default folder name when the backend does not report one', async () => {
    render(<DashboardPage />)
    await Promise.resolve()
    expect(screen.getByTestId('data-path')).toHaveTextContent('~/.deeper-notebook/')
  })

  it('keeps the default folder name when the backend cannot be reached', async () => {
    configFixture.fails = true
    render(<DashboardPage />)
    await Promise.resolve()
    expect(screen.getByTestId('data-path')).toHaveTextContent('~/.deeper-notebook/')
  })
})
