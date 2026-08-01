import { describe, expect, it } from 'vitest'

import { groupEpisodesForLibrary } from './PodcastLibrary'

describe('groupEpisodesForLibrary', () => {
  it('separates current production, outline review, completed, and failed episodes', () => {
    const episode = (id: string, job_status: any, generation_stage?: string) => ({ id, name: id, job_status, generation_stage, episode_profile: { name: 'Local', num_segments: 3 }, speaker_profile: {}, briefing: '' })
    const groups = groupEpisodesForLibrary([
      episode('running', 'running'), episode('review', 'completed', 'awaiting_review'),
      episode('done', 'completed'), episode('failed', 'failed'),
    ] as any)

    expect(groups['Continue Production'].map(item => item.id)).toEqual(['running'])
    expect(groups['Ready to Review'].map(item => item.id)).toEqual(['review'])
    expect(groups.Completed.map(item => item.id)).toEqual(['done'])
    expect(groups['Needs Attention'].map(item => item.id)).toEqual(['failed'])
  })
})
