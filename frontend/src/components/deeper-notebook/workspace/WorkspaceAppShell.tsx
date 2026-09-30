'use client'

import type { ReactNode } from 'react'

import { AdaptiveNavigator } from '@/components/deeper-notebook/shell/AdaptiveNavigator'
import { CommandBar } from '@/components/deeper-notebook/shell/CommandBar'
import { InstrumentDock } from '@/components/deeper-notebook/shell/InstrumentDock'
import { ShellUtilities } from '@/components/deeper-notebook/shell/ShellUtilities'

export function WorkspaceAppShell({ children }: { children: ReactNode }) {
  return (
    <div
      data-testid="visual-system-v2-shell"
      data-dn-visual-system="v2"
      className="dn-workspace-shell"
    >
      <InstrumentDock />
      <div className="dn-workspace-shell-body">
        <CommandBar />
        <AdaptiveNavigator />
        <section className="dn-workspace-canvas">{children}</section>
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
