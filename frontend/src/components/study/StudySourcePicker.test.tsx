import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { StudySourcePicker } from './StudySourcePicker'

describe('StudySourcePicker', () => {
  it('opens the existing source dialog instead of implementing a second uploader', () => {
    const openUpload = vi.fn()

    render(<StudySourcePicker links={[]} onOpenUpload={openUpload} />)

    fireEvent.click(screen.getByRole('button', { name: 'Upload PDF or video' }))

    expect(openUpload).toHaveBeenCalledOnce()
  })

  it('renders existing sources without exposing paths or source bodies', () => {
    render(
      <StudySourcePicker
        links={[]}
        onOpenUpload={vi.fn()}
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
})
