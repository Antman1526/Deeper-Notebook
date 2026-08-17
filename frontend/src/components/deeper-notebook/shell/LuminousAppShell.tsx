'use client'

import type { ReactNode } from 'react'

import { AdaptiveNavigator } from './AdaptiveNavigator'
import { AuroraCartography } from './AuroraCartography'
import { CommandBar } from './CommandBar'
import { ContextLens } from './ContextLens'
import { InstrumentDock } from './InstrumentDock'
import { ShellUtilities } from './ShellUtilities'

export function LuminousAppShell({ children }: { children: ReactNode }) {
  return (
    <div className="dn-luminous-shell">
      <AuroraCartography />
      <InstrumentDock />
      <div className="dn-luminous-workspace">
        <CommandBar />
        <AdaptiveNavigator />
        <section className="dn-editorial-canvas">{children}</section>
        <ContextLens />
      </div>
      <ShellUtilities />
      {/* v0.8.96 — FocusModeControl moved into CommandBar so it lays out beside
          the palette trigger instead of floating on top of it. */}
    </div>
  )
}
