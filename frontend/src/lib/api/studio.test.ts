import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiGet = vi.fn()
const apiPost = vi.fn()
const apiPatch = vi.fn()
const apiDelete = vi.fn()

vi.mock('@/lib/api/client', () => ({
  default: {
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
    patch: (...args: unknown[]) => apiPatch(...args),
    delete: (...args: unknown[]) => apiDelete(...args),
  },
}))

import { studioApi } from './studio'

describe('studioApi artifact endpoints', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('generates notebook and podcast together when mode is both', async () => {
    apiPost.mockResolvedValue({
      data: {
        notebook_id: 'notebook:alpha',
        mode: 'both',
        note_id: 'note:study',
        job_id: 'job:podcast',
        source_ids: ['source:one'],
        title: 'Training pack',
        warnings: [],
      },
    })

    const result = await studioApi.generate({
      files: [new File(['hello'], 'training.mp4', { type: 'video/mp4' })],
      mode: 'both',
      title: 'Training pack',
      episode_profile_name: 'Default episode',
      speaker_profile_name: 'Default speakers',
    })

    expect(apiPost).toHaveBeenCalledWith('/studio/generate', expect.any(FormData))
    const formData = apiPost.mock.calls[0][1] as FormData
    expect(formData.get('mode')).toBe('both')
    expect(formData.get('episode_profile_name')).toBe('Default episode')
    expect(formData.get('speaker_profile_name')).toBe('Default speakers')
    expect(result.mode).toBe('both')
    expect(result.job_id).toBe('job:podcast')
  })

  it('generates from links without files', async () => {
    apiPost.mockResolvedValue({
      data: {
        notebook_id: 'notebook:links',
        mode: 'notebook',
        note_id: 'note:links',
        source_ids: ['source:link-a', 'source:link-b'],
        title: 'Link training',
        warnings: [],
      },
    })

    const result = await studioApi.generate({
      files: [],
      links: [
        'https://example.com/video',
        ' https://example.com/guide ',
      ],
      mode: 'notebook',
      title: 'Link training',
    })

    expect(apiPost).toHaveBeenCalledWith('/studio/generate', expect.any(FormData))
    const formData = apiPost.mock.calls[0][1] as FormData
    expect(formData.getAll('links')).toEqual([
      'https://example.com/video',
      'https://example.com/guide',
    ])
    expect(formData.get('mode')).toBe('notebook')
    expect(result.source_ids).toEqual(['source:link-a', 'source:link-b'])
  })

  it('lists durable artifacts for a notebook', async () => {
    apiGet.mockResolvedValue({
      data: [
        {
          id: 'studio_artifact:1',
          notebook_id: 'notebook:alpha',
          artifact_type: 'study_guide',
          title: 'Study guide',
          status: 'completed',
          source_ids: [],
          output_payload: {},
          citations: [],
          export_paths: {},
        },
      ],
    })

    const rows = await studioApi.listArtifacts('notebook:alpha')

    expect(apiGet).toHaveBeenCalledWith('/studio/notebooks/notebook%3Aalpha/artifacts', {
      headers: { 'x-skip-error-toast': '1' },
    })
    expect(rows[0].artifact_type).toBe('study_guide')
  })

  it('creates a durable artifact record', async () => {
    apiPost.mockResolvedValue({
      data: {
        id: 'studio_artifact:2',
        notebook_id: 'notebook:alpha',
        artifact_type: 'report',
        title: 'Report',
        status: 'pending',
        source_ids: ['source:one'],
        output_payload: {},
        citations: [],
        export_paths: {},
      },
    })

    const artifact = await studioApi.createArtifact({
      notebook_id: 'notebook:alpha',
      artifact_type: 'report',
      title: 'Report',
      source_ids: ['source:one'],
    })

    expect(apiPost).toHaveBeenCalledWith('/studio/artifacts', {
      notebook_id: 'notebook:alpha',
      artifact_type: 'report',
      title: 'Report',
      source_ids: ['source:one'],
    })
    expect(artifact.id).toBe('studio_artifact:2')
  })

  it('creates a Course Pack artifact record', async () => {
    apiPost.mockResolvedValue({
      data: {
        id: 'studio_artifact:course-pack',
        notebook_id: 'notebook:alpha',
        artifact_type: 'course_pack',
        title: 'Course Pack',
        status: 'pending',
        source_ids: ['source:video', 'source:pdf', 'source:link'],
        output_payload: {},
        citations: [],
        export_paths: {},
      },
    })

    const artifact = await studioApi.createArtifact({
      notebook_id: 'notebook:alpha',
      artifact_type: 'course_pack',
      title: 'Course Pack',
      source_ids: ['source:video', 'source:pdf', 'source:link'],
    })

    expect(apiPost).toHaveBeenCalledWith('/studio/artifacts', {
      notebook_id: 'notebook:alpha',
      artifact_type: 'course_pack',
      title: 'Course Pack',
      source_ids: ['source:video', 'source:pdf', 'source:link'],
    })
    expect(artifact.artifact_type).toBe('course_pack')
  })

  it('patches only provided artifact fields', async () => {
    apiPatch.mockResolvedValue({
      data: {
        id: 'studio_artifact:1',
        notebook_id: 'notebook:alpha',
        artifact_type: 'report',
        title: 'Final',
        status: 'completed',
        source_ids: [],
        output_payload: {},
        citations: [],
        export_paths: {},
      },
    })

    await studioApi.updateArtifact('studio_artifact:1', {
      title: 'Final',
      status: 'completed',
    })

    expect(apiPatch).toHaveBeenCalledWith('/studio/artifacts/studio_artifact%3A1', {
      title: 'Final',
      status: 'completed',
    })
  })

  it('patches artifact study progress in the output payload', async () => {
    const studyProgress = {
      version: 1,
      content_fingerprint: '10:abc',
      quiz: { index: 0, answers: { '0': 'B' } },
      updated_at: '2026-06-23T00:00:00.000Z',
    }
    apiPatch.mockResolvedValue({
      data: {
        id: 'studio_artifact:1',
        notebook_id: 'notebook:alpha',
        artifact_type: 'quiz',
        title: 'Quiz',
        status: 'completed',
        source_ids: [],
        output_payload: { study_progress: studyProgress },
        citations: [],
        export_paths: {},
      },
    })

    await studioApi.updateArtifact('studio_artifact:1', {
      output_payload: { study_progress: studyProgress },
    })

    expect(apiPatch).toHaveBeenCalledWith('/studio/artifacts/studio_artifact%3A1', {
      output_payload: { study_progress: studyProgress },
    })
  })

  it('deletes artifacts by id', async () => {
    apiDelete.mockResolvedValue({ data: { deleted: true, id: 'studio_artifact:1' } })

    const result = await studioApi.deleteArtifact('studio_artifact:1')

    expect(apiDelete).toHaveBeenCalledWith('/studio/artifacts/studio_artifact%3A1')
    expect(result.deleted).toBe(true)
  })

  it('lists revisions for an artifact', async () => {
    apiGet.mockResolvedValue({
      data: [
        {
          id: 'studio_artifact:revision',
          notebook_id: 'notebook:alpha',
          artifact_type: 'report',
          title: 'Report revision',
          status: 'completed',
          source_ids: ['source:one'],
          output_payload: { content: '# Previous' },
          citations: [],
          export_paths: {},
          revision_of_id: 'studio_artifact:1',
        },
      ],
    })

    const rows = await studioApi.listArtifactRevisions('studio_artifact:1')

    expect(apiGet).toHaveBeenCalledWith('/studio/artifacts/studio_artifact%3A1/revisions', {
      headers: { 'x-skip-error-toast': '1' },
    })
    expect(rows[0].revision_of_id).toBe('studio_artifact:1')
  })

  it('generates an artifact by id', async () => {
    apiPost.mockResolvedValue({
      data: {
        id: 'studio_artifact:1',
        notebook_id: 'notebook:alpha',
        artifact_type: 'report',
        title: 'Report',
        status: 'completed',
        source_ids: ['source:one'],
        output_payload: { content: '# Report' },
        citations: [],
        export_paths: {},
      },
    })

    const artifact = await studioApi.generateArtifact('studio_artifact:1')

    expect(apiPost).toHaveBeenCalledWith('/studio/artifacts/studio_artifact%3A1/generate')
    expect(artifact.status).toBe('completed')
    expect(artifact.output_payload.content).toBe('# Report')
  })

  it('creates an approval-gated workflow run for an artifact', async () => {
    apiPost.mockResolvedValue({
      data: {
        id: 'studio_workflow_run:1',
        artifact_id: 'studio_artifact:1',
        notebook_id: 'notebook:alpha',
        title: 'Generate Report',
        status: 'awaiting_approval',
        source_ids: ['source:one'],
        approval_required: true,
        steps: [
          { id: 'context', label: 'Context built', status: 'completed' },
          { id: 'privacy_gate', label: 'Privacy gate', status: 'pending' },
        ],
        command_id: null,
      },
    })

    const run = await studioApi.createWorkflowRun('studio_artifact:1', {
      title: 'Generate Report',
      source_ids: ['source:one'],
      approval_required: true,
    })

    expect(apiPost).toHaveBeenCalledWith(
      '/studio/artifacts/studio_artifact%3A1/workflow-runs',
      {
        title: 'Generate Report',
        source_ids: ['source:one'],
        approval_required: true,
      },
    )
    expect(run.status).toBe('awaiting_approval')
  })

  it('lists workflow runs for an artifact', async () => {
    apiGet.mockResolvedValue({
      data: [
        {
          id: 'studio_workflow_run:1',
          artifact_id: 'studio_artifact:1',
          notebook_id: 'notebook:alpha',
          title: 'Generate Report',
          status: 'queued',
          source_ids: [],
          approval_required: false,
          steps: [],
          command_id: null,
        },
      ],
    })

    const runs = await studioApi.listWorkflowRuns('studio_artifact:1')

    expect(apiGet).toHaveBeenCalledWith(
      '/studio/artifacts/studio_artifact%3A1/workflow-runs',
      { headers: { 'x-skip-error-toast': '1' } },
    )
    expect(runs[0].id).toBe('studio_workflow_run:1')
  })

  it('approves a workflow run checkpoint', async () => {
    apiPost.mockResolvedValue({
      data: {
        id: 'studio_workflow_run:1',
        artifact_id: 'studio_artifact:1',
        notebook_id: 'notebook:alpha',
        title: 'Generate Report',
        status: 'queued',
        source_ids: [],
        approval_required: false,
        steps: [
          { id: 'privacy_gate', label: 'Privacy gate', status: 'completed' },
        ],
        command_id: null,
      },
    })

    const run = await studioApi.approveWorkflowRun('studio_workflow_run:1')

    expect(apiPost).toHaveBeenCalledWith(
      '/studio/workflow-runs/studio_workflow_run%3A1/approve',
    )
    expect(run.status).toBe('queued')
  })
})
