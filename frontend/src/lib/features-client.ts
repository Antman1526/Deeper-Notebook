'use client'

import { useSyncExternalStore } from 'react'

import {
  isEvidenceStudioEnabled,
  isModelFleetEnabled,
  isResearchRunsEnabled,
  isSourceVisualsEnabled,
  isStudyWorkbenchEnabled,
  isVisualRefreshEnabled,
  subscribeRuntimeFeatures,
} from './features'

const noopSubscribe = () => () => {}

function subscribe(listener: () => void): () => void {
  try {
    return typeof subscribeRuntimeFeatures === 'function'
      ? subscribeRuntimeFeatures(listener)
      : noopSubscribe()
  } catch {
    return noopSubscribe()
  }
}

export function useEvidenceStudioEnabled(): boolean {
  return useSyncExternalStore(
    subscribe,
    isEvidenceStudioEnabled,
    isEvidenceStudioEnabled,
  )
}

export function useVisualRefreshEnabled(): boolean {
  return useSyncExternalStore(
    subscribe,
    isVisualRefreshEnabled,
    isVisualRefreshEnabled,
  )
}

export function useModelFleetEnabled(): boolean {
  return useSyncExternalStore(
    subscribe,
    isModelFleetEnabled,
    isModelFleetEnabled,
  )
}

export function useResearchRunsEnabled(): boolean {
  return useSyncExternalStore(
    subscribe,
    isResearchRunsEnabled,
    isResearchRunsEnabled,
  )
}

export function useStudyWorkbenchEnabled(): boolean {
  return useSyncExternalStore(
    subscribe,
    isStudyWorkbenchEnabled,
    isStudyWorkbenchEnabled,
  )
}

export function useSourceVisualsEnabled(): boolean {
  return useSyncExternalStore(
    subscribe,
    isSourceVisualsEnabled,
    isSourceVisualsEnabled,
  )
}
