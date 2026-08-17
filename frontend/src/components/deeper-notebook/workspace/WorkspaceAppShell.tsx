'use client'

import type { ReactNode } from 'react'

import { AdaptiveNavigator } from '@/components/deeper-notebook/shell/AdaptiveNavigator'
import { CommandBar } from '@/components/deeper-notebook/shell/CommandBar'
import { ContextLens } from '@/components/deeper-notebook/shell/ContextLens'
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
        <ContextLens />
      </div>
      <ShellUtilities />
      {/* v0.8.96 — FocusModeControl moved into CommandBar so it lays out beside
          the palette trigger instead of floating on top of it. */}
    </div>
  )
}
