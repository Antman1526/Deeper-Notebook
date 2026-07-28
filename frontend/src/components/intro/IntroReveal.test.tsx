import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { IntroReveal, resetIntro } from './IntroReveal'

describe('IntroReveal active product identity', () => {
  beforeEach(() => {
    resetIntro()
    window.localStorage.clear()
  })

  it('exposes the canonical product name as the intro dialog name', async () => {
    render(<IntroReveal />)

    expect(
      await screen.findByRole('dialog', { name: 'Deeper Notebook' }),
    ).toBeVisible()
  })
})
