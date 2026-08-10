import type { ReactNode } from 'react'

export interface ResearchCoreFolioFrameProps {
  header: ReactNode
  index: ReactNode
  workspace: ReactNode
  lens?: ReactNode
  overlays?: ReactNode
}

/** Presentation-only frame; the caller retains all workspace state and actions. */
export function ResearchCoreFolioFrame({
  header,
  index,
  workspace,
  lens,
  overlays,
}: ResearchCoreFolioFrameProps) {
  return (
    <div className="research-core-folio flex min-h-0 flex-1 flex-col" data-testid="research-core-folio">
      <div className="research-core-folio__header" data-testid="research-core-folio-header">{header}</div>
      <div className="research-core-folio__spread min-h-0 flex-1" data-testid="research-core-folio-spread">
        <div className="research-core-folio__index min-h-0" data-testid="research-core-folio-index">{index}</div>
        <div className="research-core-folio__workspace min-h-0 min-w-0" data-testid="research-core-folio-workspace">{workspace}</div>
        {lens ? <div className="research-core-folio__lens min-h-0" data-testid="research-core-folio-lens">{lens}</div> : null}
      </div>
      {overlays ? <div data-testid="research-core-folio-overlays">{overlays}</div> : null}
    </div>
  )
}
