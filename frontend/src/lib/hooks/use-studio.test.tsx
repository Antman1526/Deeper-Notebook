/* eslint-disable @typescript-eslint/no-explicit-any */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api/notebooks', () => ({
  notebooksApi: {
    create: vi.fn(),
  },
}))

vi.mock('@/lib/api/sources', () => ({
  sourcesApi: {
    create: vi.fn(),
  },
}))

vi.mock('@/lib/api/studio', () => ({
  studioApi: {
    generate: vi.fn(),
    createArtifact: vi.fn(),
    listArtifacts: vi.fn(),
    listArtifactRevisions: vi.fn(),
    updateArtifact: vi.fn(),
    deleteArtifact: vi.fn(),
    generateArtifact: vi.fn(),
    createWorkflowRun: vi.fn(),
    listWorkflowRuns: vi.fn(),
    approveWorkflowRun: vi.fn(),
  },
}))

import { notebooksApi } from '@/lib/api/notebooks'
import { sourcesApi } from '@/lib/api/sources'
import { studioApi } from '@/lib/api/studio'
import { useStudioCoursePack } from './use-studio'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return React.createElement(QueryClientProvider, { client: qc }, children)
}

describe('useStudioCoursePack', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('queues mixed files and links through Sources before creating a Course Pack artifact', async () => {
    vi.mocked(notebooksApi.create).mockResolvedValue({
      id: 'notebook:course',
      name: 'Onboarding',
      description: 'Instructor-ready Course Pack queued from Studio sources.',
      archived: false,
      created: '2026-06-23T00:00:00Z',
      updated: '2026-06-23T00:00:00Z',
      source_count: 0,
      note_count: 0,
    })
    vi.mocked(sourcesApi.create)
      .mockResolvedValueOnce({
        id: 'source:file',
        title: 'training.mp4',
        asset: null,
        full_text: '',
        embedded: false,
        embedded_chunks: 0,
        insights_count: 0,
        created: '2026-06-23T00:00:00Z',
        updated: '2026-06-23T00:00:00Z',
        status: 'queued',
      } as any)
      .mockResolvedValueOnce({
        id: 'source:link',
        title: 'https://example.com/policy',
        asset: null,
        full_text: '',
        embedded: false,
        embedded_chunks: 0,
        insights_count: 0,
        created: '2026-06-23T00:00:00Z',
        updated: '2026-06-23T00:00:00Z',
        status: 'queued',
      } as any)
    vi.mocked(studioApi.createArtifact).mockResolvedValue({
      id: 'studio_artifact:course',
      notebook_id: 'notebook:course',
      artifact_type: 'course_pack',
      title: 'Onboarding Course Pack',
      status: 'pending',
      source_ids: ['source:file', 'source:link'],
      output_payload: {},
      citations: [],
      export_paths: {},
    })

    const file = new File(['video'], 'training.mp4', { type: 'video/mp4' })
    const { result } = renderHook(() => useStudioCoursePack(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        files: [file],
        links: [' https://example.com/policy '],
        title: 'Onboarding',
      })
    })

    expect(notebooksApi.create).toHaveBeenCalledWith({
      name: 'Onboarding',
      description: 'Instructor-ready Course Pack queued from Studio sources.',
    })
    expect(sourcesApi.create).toHaveBeenNthCalledWith(1, expect.objectContaining({
      type: 'upload',
      file,
      notebooks: ['notebook:course'],
      notebook_id: 'notebook:course',
      source_type: 'upload',
      async_processing: true,
      provenance: expect.objectContaining({
        origin: 'studio_course_pack',
        workflow: 'course_pack',
        source_name: 'training.mp4',
      }),
    }))
    expect(sourcesApi.create).toHaveBeenNthCalledWith(2, expect.objectContaining({
      type: 'link',
      url: 'https://example.com/policy',
      notebooks: ['notebook:course'],
      notebook_id: 'notebook:course',
      source_type: 'link',
      async_processing: true,
      provenance: expect.objectContaining({
        origin: 'studio_course_pack',
        workflow: 'course_pack',
        source_url: 'https://example.com/policy',
      }),
    }))
    expect(studioApi.createArtifact).toHaveBeenCalledWith({
      notebook_id: 'notebook:course',
      artifact_type: 'course_pack',
      title: 'Onboarding Course Pack',
      source_ids: ['source:file', 'source:link'],
    })
  })
})
