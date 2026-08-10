import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import PodcastsPage from './page'

vi.mock('@/components/layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/components/podcasts/EpisodesTab', () => ({ EpisodesTab: () => <div>Episodes</div> }))
vi.mock('@/components/podcasts/TemplatesTab', () => ({ TemplatesTab: () => <div>Templates</div> }))
vi.mock('@/lib/hooks/use-podcasts', () => ({ useEpisodeProfiles: () => ({ episodeProfiles: [] }), useSpeakerProfiles: () => ({ speakerProfiles: [] }) }))
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string) => ({ 'podcasts.listDesc': 'Optional audio from your notes.', 'podcasts.episodesTab': 'Episodes' })[key] ?? key }),
}))

describe('PodcastsPage', () => {
  it('places the existing episode workspace inside a Create folio', () => {
    render(<PodcastsPage />)
    expect(screen.getByRole('main', { name: 'Podcasts' })).toBeInTheDocument()
    expect(screen.getByText('Create')).toBeInTheDocument()
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Episodes')
  })
})
