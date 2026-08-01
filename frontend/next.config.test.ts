import { realpathSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { resolveTurbopackRoot } from './next.config'

describe('resolveTurbopackRoot', () => {
  it('uses the current worktree node_modules target to locate its checkout', () => {
    const nodeModulesTarget = realpathSync(path.join(__dirname, 'node_modules'))

    expect(resolveTurbopackRoot(__dirname)).toBe(
      path.dirname(path.dirname(nodeModulesTarget)),
    )
  })

  it('uses the shared node_modules target to locate a nested worktree checkout', () => {
    const frontendDir = '/workspace/Deeper-Notebook/.worktrees/phase-1/frontend'

    expect(
      resolveTurbopackRoot(
        frontendDir,
        () => '/workspace/Deeper-Notebook/frontend/node_modules',
      ),
    ).toBe('/workspace/Deeper-Notebook')
  })

  it('uses the direct node_modules directory in a normal checkout', () => {
    const frontendDir = '/workspace/Deeper-Notebook/frontend'

    expect(
      resolveTurbopackRoot(
        frontendDir,
        () => '/workspace/Deeper-Notebook/frontend/node_modules',
      ),
    ).toBe('/workspace/Deeper-Notebook')
  })
})
