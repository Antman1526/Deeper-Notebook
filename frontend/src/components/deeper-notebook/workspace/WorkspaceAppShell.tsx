'use client'

import { useCallback, useState, type ReactNode } from 'react'

import { CommandBar } from '@/components/deeper-notebook/shell/CommandBar'
import { ShellUtilities } from '@/components/deeper-notebook/shell/ShellUtilities'
import { useTranslation } from '@/lib/hooks/use-translation'
import { WorkspaceRail } from './WorkspaceRail'

export function WorkspaceAppShell({ children }: { children: ReactNode }) {
  // v0.8.130 — Phase 3b: below 1024px the rail is a sheet opened from the command bar.
  const [railOpen, setRailOpen] = useState(false)
  const closeRail = useCallback(() => setRailOpen(false), [])
  const { t } = useTranslation()

  return (
    <div
      data-testid="visual-system-v2-shell"
      data-dn-visual-system="v2"
      className="dn-workspace-shell"
    >
      {/* v0.8.130 — Phase 3b: a skip link, first in the tab order. */}
      <a href="#dn-main" className="dn-skip-link">{t('common.skipToContent')}</a>
      {/* v0.8.130 — Phase 3b: one rail replaces the instrument dock and the notebook index. */}
      <WorkspaceRail open={railOpen} onClose={closeRail} />
      <div className="dn-workspace-shell-body">
        <CommandBar
          showBrand={false}
          focusShortcut={false}
          modelHealth
          onMenu={() => setRailOpen((open) => !open)}
          menuOpen={railOpen}
        />
        <section id="dn-main" tabIndex={-1} className="dn-workspace-canvas">{children}</section>
        {/* v0.8.130 — the Context lens (static placeholder copy on every route) is no longer
            mounted here. It reserved an empty 320px rail at 1536px+ and floated a button over
            content below that. The component and the shared shell.css rules stay for the
            Luminous and legacy rollback shells, and for when the lens has real content. */}
      </div>
      <ShellUtilities />
      {/* v0.8.96 — FocusModeControl moved into CommandBar so it lays out beside
          the palette trigger instead of floating on top of it. */}
    </div>
  )
}
