'use client'

import {
  isEvidenceStudioEnabled,
  isModelFleetEnabled,
  isResearchRunsEnabled,
  isVisualRefreshEnabled,
} from '../../../src/lib/features'

export default function FeatureBuildContractPage() {
  return (
    <main id="feature-build-contract">
      evidence:{String(isEvidenceStudioEnabled())};
      visual:{String(isVisualRefreshEnabled())};
      model:{String(isModelFleetEnabled())};
      research:{String(isResearchRunsEnabled())}
    </main>
  )
}
