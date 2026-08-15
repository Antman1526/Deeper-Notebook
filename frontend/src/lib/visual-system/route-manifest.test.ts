import { readdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { SOURCE_GALLERY_CELLS, VISUAL_ROUTE_MANIFEST } from './route-manifest'

function findPageSources(directory: string, repositoryRoot: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const absolutePath = resolve(directory, entry.name)

    if (entry.isDirectory()) {
      return findPageSources(absolutePath, repositoryRoot)
    }

    if (entry.isFile() && entry.name === 'page.tsx') {
      return [absolutePath.slice(repositoryRoot.length + 1).replaceAll('\\', '/')]
    }

    return []
  })
}

describe('visual system route manifest', () => {
  it('covers every current app page source exactly once', () => {
    const repositoryRoot = resolve(process.cwd())
    const appRoot = resolve(repositoryRoot, 'src/app')
    const sourceRoutes = findPageSources(appRoot, repositoryRoot).sort()
    const manifestSources = VISUAL_ROUTE_MANIFEST.map((entry) => entry.source).sort()

    expect(manifestSources).toEqual(sourceRoutes)
    expect(VISUAL_ROUTE_MANIFEST).toHaveLength(22)
    expect(new Set(VISUAL_ROUTE_MANIFEST.map((entry) => entry.source)).size).toBe(22)
    expect(new Set(VISUAL_ROUTE_MANIFEST.map((entry) => entry.route)).size).toBe(22)
  })

  it('keeps deterministic browser fixtures for dynamic routes', () => {
    const byRoute = Object.fromEntries(
      VISUAL_ROUTE_MANIFEST.map((entry) => [entry.route, entry]),
    )

    expect(byRoute['/notebooks/[id]'].browserPath).toBe(
      '/notebooks/notebook-fixture-001',
    )
    expect(byRoute['/sources/[id]'].browserPath).toBe(
      '/sources/source-fixture-001',
    )
    expect(byRoute['/study/plans/[planId]'].browserPath).toBe(
      '/study/plans/study_plan%3Afixture',
    )
  })

  it('assigns the approved phase-one route boundary', () => {
    expect(VISUAL_ROUTE_MANIFEST.filter((entry) => entry.phase === 1).map((entry) => entry.route)).toEqual([
      '/login',
      '/',
      '/setup-wizard',
    ])
  })

  it('keeps every route on a deterministic browser path for the visual matrix', () => {
    expect(VISUAL_ROUTE_MANIFEST.every((entry) => entry.browserPath.startsWith('/'))).toBe(true)
    expect(VISUAL_ROUTE_MANIFEST.map((entry) => entry.browserPath)).toHaveLength(22)
    expect(new Set(VISUAL_ROUTE_MANIFEST.map((entry) => entry.browserPath)).size).toBe(22)
  })
})

describe('source gallery route manifest', () => {
  it('adds exact state cells without changing the 22-route Phase 1 matrix', () => {
    expect(VISUAL_ROUTE_MANIFEST).toHaveLength(22)
    expect(new Set(SOURCE_GALLERY_CELLS.map(cell => cell.id)).size).toBe(
      SOURCE_GALLERY_CELLS.length,
    )
    expect(new Set(SOURCE_GALLERY_CELLS.map(cell => cell.route))).toEqual(new Set([
      '/sources',
      '/notebooks/[id]',
      '/knowledge',
      '/search',
      '/capture',
    ]))
    expect(new Set(SOURCE_GALLERY_CELLS.map(cell => cell.state))).toEqual(new Set([
      'ready',
      'processing',
      'failed',
      'missing-corrupt',
      'compact',
      'feature-off',
    ]))
  })

  it('has an explicit feature-off rollback cell for every adopted route', () => {
    expect(
      SOURCE_GALLERY_CELLS
        .filter(cell => cell.state === 'feature-off')
        .map(cell => cell.route)
        .sort(),
    ).toEqual([
      '/capture',
      '/knowledge',
      '/notebooks/[id]',
      '/search',
      '/sources',
    ])
    expect(SOURCE_GALLERY_CELLS.every(cell => cell.browserPath.startsWith('/'))).toBe(true)
  })
})
