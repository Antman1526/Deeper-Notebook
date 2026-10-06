import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RichText } from './RichText'

describe('RichText', () => {
  it('renders plain text unchanged', () => {
    const { container } = render(<p><RichText text="No tags here." /></p>)
    expect(container.innerHTML).toBe('<p>No tags here.</p>')
  })

  it('wraps tagged text and fills self-closing tags, wherever the translation puts them', () => {
    const { container } = render(
      <p>
        <RichText
          text="<key/> を押すと <em>どこからでも</em> 移動できます。"
          components={{ key: () => <kbd>⌘K</kbd>, em: (children) => <em>{children}</em> }}
        />
      </p>,
    )
    expect(container.innerHTML).toBe('<p><kbd>⌘K</kbd> を押すと <em>どこからでも</em> 移動できます。</p>')
  })

  it('keeps an unknown tag as its inner text instead of dropping words', () => {
    const { container } = render(<p><RichText text="Open <b>the</b> <x/>console" components={{}} /></p>)
    expect(container.textContent).toBe('Open the console')
  })

  it('shows the raw text of a malformed tag rather than losing it', () => {
    const { container } = render(<p><RichText text="a <link>b c" components={{ link: (children) => <a>{children}</a> }} /></p>)
    expect(container.textContent).toBe('a <link>b c')
  })
})
