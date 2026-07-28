'use client'

// v0.8.80 — first-run sample notebook (improvement roadmap, Batch 2). One click
// seeds an example notebook + a bundled text source so a brand-new user sees
// value immediately instead of an empty list. Reuses the existing
// create-notebook / create-source mutations; the source's content is bundled
// (no network — fits the local-first ethos). Once the source is processed, the
// v0.8.74 starter-question chips appear automatically in the chat.
import { useCallback, useState } from 'react'

import { useCreateNotebook } from './use-notebooks'
import { useCreateSource } from './use-sources'

const SAMPLE_NOTEBOOK_NAME = 'Sample: Welcome to Deeper Notebook'
const SAMPLE_NOTEBOOK_DESCRIPTION =
  'A guided example notebook. Explore the source, then ask the AI about it.'
const SAMPLE_SOURCE_TITLE = 'Getting started with Deeper Notebook'
const SAMPLE_SOURCE_CONTENT = `# Getting started with Deeper Notebook

Deeper Notebook is a **local-first, privacy-focused research assistant** — an
alternative to Google's NotebookLM that runs on your own machine. Everything
here happens locally unless you choose to use a cloud AI provider.

## What you can do

- **Add sources** — PDFs, web pages, audio, video, or pasted text. Drop files
  straight onto the Sources panel, or use "Add source".
- **Chat with your sources** — ask questions and get answers grounded in the
  documents you've added. Answers include citations like [source:...]; click a
  citation to jump to the exact passage it's based on.
- **Ask & Search** — run a deeper multi-step search across everything in a
  notebook.
- **Studio** — generate study guides and other artifacts from your sources.
- **Podcasts** — turn a notebook into an AI-narrated audio overview.

## Privacy

Your notebooks, sources, and chats are stored locally in a database on this
computer. Local models (via llama.cpp / Ollama) keep everything offline; cloud
providers are optional and only used when you configure and select them.

## Try it now

This notebook already contains this page as a source. Open the chat on the right
and try one of the suggested questions — for example, ask **"What can I do with
Deeper Notebook?"** or **"How does Deeper Notebook handle privacy?"** The answer
will cite this document, and clicking the citation will highlight the passage it
came from.
`

export function useCreateSampleNotebook() {
  const createNotebook = useCreateNotebook()
  const createSource = useCreateSource()
  const [pending, setPending] = useState(false)

  const create = useCallback(async (): Promise<string | null> => {
    setPending(true)
    try {
      const nb = await createNotebook.mutateAsync({
        name: SAMPLE_NOTEBOOK_NAME,
        description: SAMPLE_NOTEBOOK_DESCRIPTION,
      })
      const id = (nb as { id: string }).id
      // Best-effort: if the source add fails, the notebook still exists and the
      // user lands on it (mutations surface their own error toasts).
      try {
        await createSource.mutateAsync({
          type: 'text',
          title: SAMPLE_SOURCE_TITLE,
          content: SAMPLE_SOURCE_CONTENT,
          notebooks: [id],
          async_processing: true,
        })
      } catch {
        /* notebook created; source add failed — still navigate to the notebook */
      }
      return id
    } catch {
      return null
    } finally {
      setPending(false)
    }
  }, [createNotebook, createSource])

  return { create, pending }
}
