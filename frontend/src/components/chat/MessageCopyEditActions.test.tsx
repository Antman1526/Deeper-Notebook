import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) =>
    React.createElement('button', props, children),
}))

import { MessageCopyEditActions } from './MessageCopyEditActions'

const writeText = vi.fn().mockResolvedValue(undefined)

describe('MessageCopyEditActions', () => {
  beforeEach(() => {
    writeText.mockClear()
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
      writable: true,
    })
  })

  it('copies the message content to the clipboard', () => {
    render(<MessageCopyEditActions content="hello world" onEdit={() => {}} />)
    fireEvent.click(screen.getByTestId('message-copy'))
    expect(writeText).toHaveBeenCalledWith('hello world')
  })

  it('calls onEdit with the content when Edit is clicked (reuse for input)', () => {
    const onEdit = vi.fn()
    render(<MessageCopyEditActions content="reuse this prompt" onEdit={onEdit} />)
    fireEvent.click(screen.getByTestId('message-edit'))
    expect(onEdit).toHaveBeenCalledWith('reuse this prompt')
  })

  it('hides Copy when showCopy=false (AI messages already have Copy)', () => {
    render(<MessageCopyEditActions content="x" onEdit={() => {}} showCopy={false} />)
    expect(screen.queryByTestId('message-copy')).not.toBeInTheDocument()
    expect(screen.getByTestId('message-edit')).toBeInTheDocument()
  })

  it('shows Copy by default (human messages)', () => {
    render(<MessageCopyEditActions content="x" onEdit={() => {}} />)
    expect(screen.getByTestId('message-copy')).toBeInTheDocument()
    expect(screen.getByTestId('message-edit')).toBeInTheDocument()
  })
})
