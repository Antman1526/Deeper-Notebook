'use client'

import { useSyncExternalStore } from 'react'

import {
  isResearchRunsEnabled,
  isSourceVisualsEnabled,
  subscribeRuntimeFeatures,
} from './features'

export function useResearchRunsEnabled(): boolean {
  return useSyncExternalStore(
    subscribeRuntimeFeatures,
    isResearchRunsEnabled,
    isResearchRunsEnabled,
  )
}

export function useSourceVisualsEnabled(): boolean {
  return useSyncExternalStore(
    subscribeRuntimeFeatures,
    isSourceVisualsEnabled,
    isSourceVisualsEnabled,
  )
}
