import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { DirectoryPicker } from './DirectoryPicker'

const legacyExports = `/Users/me/${'Open'}${'NotebookPlus'}-Exports`
import { useFsHome, useFsList, useFsMkdir } from '@/lib/hooks/use-fs'

vi.mock('@/lib/hooks/use-fs')

function makeHome() {
  return {
    data: {
      home: '/Users/me',
      desktop: '/Users/me/Desktop',
      documents: '/Users/me/Documents',
      downloads: '/Users/me/Downloads',
      default_exports: legacyExports,
    },
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useFsHome>
}

function makeList(
  entries: Array<{ name: string; path: string; is_dir: boolean }> = [],
  overrides: { truncated?: boolean; parent?: string | null } = {},
) {
  return {
    data: {
      path: '/Users/me',
      parent: overrides.parent === undefined ? '/Users' : overrides.parent,
      entries: entries.map((e) => ({ ...e, size: null, modified: null })),
      truncated: overrides.truncated ?? false,
      warnings: [],
    },
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useFsList>
}

describe('DirectoryPicker', () => {
  const baseProps = {
    open: true,
    onOpenChange: vi.fn(),
    onSelect: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useFsHome).mockReturnValue(makeHome())
    vi.mocked(useFsList).mockReturnValue(
      makeList([
        { name: 'Projects', path: '/Users/me/Projects', is_dir: true },
        { name: 'Notes', path: '/Users/me/Notes', is_dir: true },
      ]),
    )
    vi.mocked(useFsMkdir).mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ path: '/Users/me/NewFolder', created: true }),
      isPending: false,
    } as unknown as ReturnType<typeof useFsMkdir>)
  })

  it('renders shortcuts from /fs/home', () => {
    render(<DirectoryPicker {...baseProps} />)
    expect(screen.getByText('filesystem.home')).toBeInTheDocument()
    expect(screen.getByText('filesystem.desktop')).toBeInTheDocument()
    expect(screen.getByText('filesystem.defaultExports')).toBeInTheDocument()
  })

  it('renders directory entries', () => {
    render(<DirectoryPicker {...baseProps} />)
    expect(screen.getByText('Projects')).toBeInTheDocument()
    expect(screen.getByText('Notes')).toBeInTheDocument()
  })

  it('calls onSelect with the current path when Use This Location is clicked', () => {
    const onSelect = vi.fn()
    const onOpenChange = vi.fn()
    render(
      <DirectoryPicker
        {...baseProps}
        initialPath="/Users/me/Documents"
        onSelect={onSelect}
        onOpenChange={onOpenChange}
      />,
    )

    fireEvent.click(screen.getByText('filesystem.useThisLocation'))

    expect(onSelect).toHaveBeenCalledWith('/Users/me/Documents')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('creates a new folder via the mkdir mutation', async () => {
    const mkdirAsync = vi.fn().mockResolvedValue({ path: '/Users/me/NewFolder', created: true })
    vi.mocked(useFsMkdir).mockReturnValue({
      mutateAsync: mkdirAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useFsMkdir>)

    render(<DirectoryPicker {...baseProps} initialPath="/Users/me" />)

    fireEvent.click(screen.getByText('filesystem.newFolder'))

    const nameInput = screen.getByLabelText('filesystem.newFolderPrompt')
    fireEvent.change(nameInput, { target: { value: 'NewFolder' } })

    fireEvent.click(screen.getByText('filesystem.create'))

    await waitFor(() => {
      expect(mkdirAsync).toHaveBeenCalledWith('/Users/me/NewFolder')
    })
  })

  it('shows the truncated banner when the listing was capped', () => {
    vi.mocked(useFsList).mockReturnValue(
      makeList(
        [{ name: 'A', path: '/Users/me/A', is_dir: true }],
        { truncated: true },
      ),
    )
    render(<DirectoryPicker {...baseProps} initialPath="/Users/me" />)
    expect(screen.getByText(/filesystem\.truncated/)).toBeInTheDocument()
  })
})
