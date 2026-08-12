import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api/sources', () => ({
  sourcesApi: { list: vi.fn().mockResolvedValue([]) },
}))

import { sourcesApi } from '@/lib/api/sources'

import { StudySourcePicker } from './StudySourcePicker'

describe('StudySourcePicker', () => {
  it('opens the existing source dialog instead of implementing a second uploader', () => {
    const openUpload = vi.fn()

    render(<StudySourcePicker links={[]} onOpenUpload={openUpload} onLinkSource={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Upload PDF or video' }))

    expect(openUpload).toHaveBeenCalledOnce()
  })

  it('renders existing sources without exposing paths or source bodies', () => {
    render(
      <StudySourcePicker
        links={[]}
        onOpenUpload={vi.fn()}
        onLinkSource={vi.fn()}
        sources={[
          {
            id: 'source:lecture',
            title: 'Lecture notes',
            source_type: 'upload',
            status: 'completed',
            full_text: 'private source body',
            asset: { file_path: '/private/lecture.pdf' },
          },
        ]}
      />,
    )

    expect(screen.getByText('Lecture notes')).toBeInTheDocument()
    expect(screen.queryByText('/private/lecture.pdf')).not.toBeInTheDocument()
    expect(screen.queryByText('private source body')).not.toBeInTheDocument()
  })

  it('composes the existing upload callback with linking for every returned source ID', async () => {
    const onLinkSource = vi.fn().mockResolvedValue(undefined)
    const onLinked = vi.fn()
    const openUpload = vi.fn((onCreated?: (sourceId: string) => void) => {
      onCreated?.('source:uploaded')
      onCreated?.('source:uploaded')
      onCreated?.('source:second')
    })

    render(
      <StudySourcePicker
        links={[]}
        sources={[]}
        onOpenUpload={openUpload}
        onLinkSource={onLinkSource}
        onSourceLinked={onLinked}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Upload PDF or video' }))

    await waitFor(() => {
      expect(onLinkSource).toHaveBeenNthCalledWith(1, 'source:uploaded')
      expect(onLinkSource).toHaveBeenNthCalledWith(2, 'source:second')
      expect(onLinked).toHaveBeenCalledWith('source:uploaded')
      expect(onLinked).toHaveBeenCalledWith('source:second')
      expect(onLinkSource).toHaveBeenCalledTimes(2)
      expect(onLinked).toHaveBeenCalledTimes(2)
    })
  })

  it('consumes the batch upload callback and links every returned source ID', async () => {
    const onLinkSource = vi.fn().mockResolvedValue(undefined)
    const onLinked = vi.fn()
    const openUpload = vi.fn(
      (
        _onCreated?: (sourceId: string) => void,
        onSourcesCreated?: (sourceIds: readonly string[]) => void,
      ) => {
        void onSourcesCreated?.(['source:first', 'source:second'])
      },
    )

    render(
      <StudySourcePicker
        links={[]}
        sources={[]}
        onOpenUpload={openUpload}
        onLinkSource={onLinkSource}
        onSourceLinked={onLinked}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Upload PDF or video' }))

    await waitFor(() => {
      expect(onLinkSource).toHaveBeenNthCalledWith(1, 'source:first')
      expect(onLinkSource).toHaveBeenNthCalledWith(2, 'source:second')
      expect(onLinked).toHaveBeenNthCalledWith(1, 'source:first')
      expect(onLinked).toHaveBeenNthCalledWith(2, 'source:second')
    })
  })

  it('distinguishes loading, empty, and fetch-error states with retry', async () => {
    const list = vi.mocked(sourcesApi.list)
    list.mockRejectedValueOnce(new Error('offline'))
    list.mockResolvedValueOnce([])

    const { unmount } = render(
      <StudySourcePicker links={[]} onOpenUpload={vi.fn()} onLinkSource={vi.fn()} />,
    )

    expect(screen.getByRole('status')).toHaveTextContent('Loading sources')
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Unable to load sources'))
    fireEvent.click(screen.getByRole('button', { name: 'Retry sources' }))
    await waitFor(() => expect(screen.getByText('No sources are available yet.')).toBeInTheDocument())
    unmount()
  })

  it('waits for linking, disables repeat clicks, and only calls the success callback after resolution', async () => {
    let resolveLink!: () => void
    const onLinkSource = vi.fn(
      () => new Promise<void>((resolve) => {
        resolveLink = resolve
      }),
    )
    const onLinked = vi.fn()

    render(
      <StudySourcePicker
        links={[]}
        onOpenUpload={vi.fn()}
        sources={[{ id: 'source:one', title: 'Lecture', source_type: 'text', extraction_quality: 'ok' }]}
        onLinkSource={onLinkSource}
        onSourceLinked={onLinked}
      />,
    )

    const linkButton = screen.getByRole('button', { name: 'Link Lecture' })
    fireEvent.click(linkButton)
    fireEvent.click(linkButton)
    expect(onLinkSource).toHaveBeenCalledOnce()
    expect(linkButton).toBeDisabled()
    expect(onLinked).not.toHaveBeenCalled()

    resolveLink()
    await waitFor(() => expect(onLinked).toHaveBeenCalledWith('source:one'))
  })

  it('does not claim a source is linked when persistence is not supplied', async () => {
    const onLinked = vi.fn()

    render(
      <StudySourcePicker
        links={[]}
        onOpenUpload={vi.fn()}
        onLinkSource={undefined as unknown as (sourceId: string) => void}
        sources={[{ id: 'source:one', title: 'Lecture', source_type: 'text', extraction_quality: 'ok' }]}
        onSourceLinked={onLinked}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Link Lecture' }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Unable to link source'))
    expect(screen.getByRole('button', { name: 'Link Lecture' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Lecture linked' })).not.toBeInTheDocument()
    expect(onLinked).not.toHaveBeenCalled()
  })

  it('surfaces link failures and does not call the post-link callback', async () => {
    const onLinkSource = vi.fn().mockRejectedValue(new Error('conflict'))
    const onLinked = vi.fn()

    render(
      <StudySourcePicker
        links={[]}
        onOpenUpload={vi.fn()}
        sources={[{ id: 'source:one', title: 'Lecture', source_type: 'text', extraction_quality: 'ok' }]}
        onLinkSource={onLinkSource}
        onSourceLinked={onLinked}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Link Lecture' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Unable to link source'))
    expect(onLinked).not.toHaveBeenCalled()
  })

  it('keeps source cards visible and supports retrying a failed link', async () => {
    const onLinkSource = vi.fn()
      .mockRejectedValueOnce(new Error('conflict'))
      .mockResolvedValueOnce(undefined)

    render(
      <StudySourcePicker
        links={[]}
        onOpenUpload={vi.fn()}
        sources={[{ id: 'source:one', title: 'Lecture', source_type: 'text', extraction_quality: 'ok' }]}
        onLinkSource={onLinkSource}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Link Lecture' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Unable to link source'))
    expect(screen.getByText('Lecture')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry link Lecture' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dismiss link error' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Retry link Lecture' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Lecture linked' })).toBeInTheDocument())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('retains an early batch failure and retry action after later links succeed', async () => {
    const onLinkSource = vi.fn()
      .mockRejectedValueOnce(new Error('first link failed'))
      .mockResolvedValueOnce(undefined)

    const openUpload = vi.fn(
      (
        _onCreated?: (sourceId: string) => void,
        onSourcesCreated?: (sourceIds: readonly string[]) => void,
      ) => {
        void onSourcesCreated?.(['source:first', 'source:second'])
      },
    )

    render(
      <StudySourcePicker
        links={[]}
        onOpenUpload={openUpload}
        sources={[
          { id: 'source:first', title: 'First source', source_type: 'text', extraction_quality: 'ok' },
          { id: 'source:second', title: 'Second source', source_type: 'text', extraction_quality: 'ok' },
        ]}
        onLinkSource={onLinkSource}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Upload PDF or video' }))

    await waitFor(() => expect(onLinkSource).toHaveBeenCalledTimes(2))
    expect(screen.getByText('First source')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry link First source' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Second source linked' })).toBeInTheDocument()
  })
})
