import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ModelFleetBadge } from './ModelFleetBadge'

describe('ModelFleetBadge', () => {
  it('labels GGUF models as llama.cpp-ready local models', () => {
    render(<ModelFleetBadge runtime="gguf" />)

    expect(screen.getByText('GGUF')).toBeInTheDocument()
  })

  it('labels MLX repos as Apple Silicon local models', () => {
    render(<ModelFleetBadge runtime="mlx" />)

    expect(screen.getByText('MLX')).toBeInTheDocument()
  })

  it('labels Transformers repos as local model assets', () => {
    render(<ModelFleetBadge runtime="transformers" />)

    expect(screen.getByText('Transformers')).toBeInTheDocument()
    expect(screen.getByLabelText('Transformers local model runtime')).toBeInTheDocument()
  })

  it('uses a generic local runtime label for unknown inventory rows', () => {
    render(<ModelFleetBadge runtime="other" />)

    expect(screen.getByText('Local')).toBeInTheDocument()
  })
})
