/**
 * ONP v0.7.0 — Studio API client.
 *
 * Wraps POST /api/studio/generate with proper multipart handling. Uses the
 * shared apiClient (axios) so the auth interceptor + base-URL discovery
 * apply automatically — same path used by sourcesApi.upload.
 */
import apiClient from './client'

export type StudioMode = 'notebook' | 'podcast'

export interface StudioGenerateOptions {
  /** One or more files to ingest. Must be at least 1. */
  files: File[]
  /** Output mode. */
  mode: StudioMode
  /** Optional notebook title. Auto-generated from first filename if absent. */
  title?: string
  /** Required for podcast mode. */
  episode_profile_name?: string
  /** Required for podcast mode. */
  speaker_profile_name?: string
}

export interface StudioGenerateResponse {
  notebook_id: string
  mode: StudioMode
  /** Notebook mode: id of the generated study-notes Note. */
  note_id?: string
  /** Podcast mode: surreal_commands job id to poll for progress. */
  job_id?: string
  source_ids: string[]
  title: string
  /** Non-fatal issues during ingestion (e.g. one of several files
   *  couldn't be parsed). Frontend surfaces these as warnings. */
  warnings: string[]
}

export const studioApi = {
  /**
   * Submit a Studio generation request.
   *
   * The backend will:
   *   1. Create a Notebook record
   *   2. Stream each file to UPLOADS_FOLDER + create a Source record
   *   3. Parse each file via content_core (PDF/DOCX/PPTX/HTML/MD/TXT)
   *   4. For notebook mode: invoke the LLM with the combined parsed text
   *      and save the response as an AI-authored Note attached to the
   *      notebook
   *   5. For podcast mode: submit a podcast generation job against the
   *      newly-created notebook, return job_id
   *
   * Throws on HTTP errors; the caller's hook should display the message.
   */
  generate: async (opts: StudioGenerateOptions): Promise<StudioGenerateResponse> => {
    if (opts.files.length === 0) {
      throw new Error('At least one file is required')
    }
    if (opts.mode === 'podcast' && (!opts.episode_profile_name || !opts.speaker_profile_name)) {
      throw new Error('Podcast mode requires episode_profile_name + speaker_profile_name')
    }

    const formData = new FormData()
    for (const file of opts.files) {
      formData.append('files', file)
    }
    formData.append('mode', opts.mode)
    if (opts.title) formData.append('title', opts.title)
    if (opts.episode_profile_name) {
      formData.append('episode_profile_name', opts.episode_profile_name)
    }
    if (opts.speaker_profile_name) {
      formData.append('speaker_profile_name', opts.speaker_profile_name)
    }

    // apiClient's interceptor (client.ts) deletes Content-Type for
    // FormData, letting the browser set the multipart boundary itself.
    const response = await apiClient.post<StudioGenerateResponse>(
      '/studio/generate',
      formData,
    )
    return response.data
  },
}
