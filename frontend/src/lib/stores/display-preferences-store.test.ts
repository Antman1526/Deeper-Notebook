import { beforeEach, describe, expect, it } from 'vitest'

import { useDisplayPreferencesStore } from './display-preferences-store'

describe('display preferences store', () => {
  beforeEach(() => {
    localStorage.clear()
    useDisplayPreferencesStore.getState().reset()
  })

  it('starts with the approved display defaults', () => {
    expect(useDisplayPreferencesStore.getState()).toMatchObject({
      wallpaper: 'aurora',
      motion: 'system',
      transparency: 'frosted',
    })
  })

  it('persists allowlisted display updates', () => {
    useDisplayPreferencesStore.getState().setWallpaper('off')
    useDisplayPreferencesStore.getState().setMotion('reduced')
    useDisplayPreferencesStore.getState().setTransparency('solid')

    expect(useDisplayPreferencesStore.getState()).toMatchObject({
      wallpaper: 'off',
      motion: 'reduced',
      transparency: 'solid',
    })

    expect(JSON.parse(localStorage.getItem('dn-display-preferences-v1') ?? '{}')).toMatchObject({
      state: { wallpaper: 'off', motion: 'reduced', transparency: 'solid' },
    })
  })

  it('resets all display preferences to their defaults', () => {
    useDisplayPreferencesStore.getState().setWallpaper('static')
    useDisplayPreferencesStore.getState().setMotion('full')
    useDisplayPreferencesStore.getState().setTransparency('solid')

    useDisplayPreferencesStore.getState().reset()

    expect(useDisplayPreferencesStore.getState()).toMatchObject({
      wallpaper: 'aurora',
      motion: 'system',
      transparency: 'frosted',
    })
  })

  it('fails closed when persisted values are outside the allowlist', async () => {
    localStorage.setItem(
      'dn-display-preferences-v1',
      JSON.stringify({
        state: { wallpaper: 'animated', motion: 'ignore-os', transparency: 'glass' },
        version: 0,
      }),
    )

    await useDisplayPreferencesStore.persist.rehydrate()

    expect(useDisplayPreferencesStore.getState()).toMatchObject({
      wallpaper: 'aurora',
      motion: 'system',
      transparency: 'frosted',
    })
  })
})
