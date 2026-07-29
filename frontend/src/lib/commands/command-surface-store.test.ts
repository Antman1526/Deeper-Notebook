import { beforeEach, describe, expect, it } from 'vitest'

import {
  requestCommandSurface,
  resetCommandSurfaceStore,
  useCommandSurfaceStore,
} from './command-surface-store'

beforeEach(() => {
  resetCommandSurfaceStore()
})

describe('command surface requests', () => {
  it('increments request identity and retains invocation focus', () => {
    const button = document.createElement('button')
    requestCommandSurface('slash', '/', button)
    expect(useCommandSurfaceStore.getState()).toMatchObject({
      requestId: 1,
      kind: 'slash',
      initialQuery: '/',
      invoker: button,
    })
  })

  it('uses a fresh request identity for each request', () => {
    requestCommandSurface('global')
    requestCommandSurface('quick-switcher', 'plan')
    expect(useCommandSurfaceStore.getState()).toMatchObject({
      requestId: 2,
      kind: 'quick-switcher',
      initialQuery: 'plan',
      invoker: null,
    })
  })
})
