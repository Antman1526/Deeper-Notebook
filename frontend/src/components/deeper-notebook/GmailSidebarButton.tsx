/**
 * GmailSidebarButton — compact entry point for the Gmail-digest integration.
 *
 * Three visual states (mirrors GmailIntegration.tsx):
 *   1. Not configured  → "Sign in with Gmail" (gray)
 *   2. Connected       → "Gmail · email@…" (green check)
 *   3. Error           → "Gmail · ⚠" (amber, hover for detail)
 *
 * Click → navigates to /settings/api-keys#email-digests (anchored to the
 * full setup panel). Polls the canonical Gmail status endpoint on mount so
 * the badge stays in sync after the user finishes the OAuth flow.
 */
'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

import { deeperNotebookFetch } from '@/lib/api/deeper-notebook'
import { Button } from '@/components/ui/button'
import { Mail, CheckCircle2 } from 'lucide-react'

interface GmailStatus {
  connected: boolean
  email_address: string | null
  has_client_credentials: boolean
}

interface GmailSidebarButtonProps {
  iconOnly?: boolean
}

export function GmailSidebarButton({ iconOnly = false }: GmailSidebarButtonProps) {
  const router = useRouter()
  const [status, setStatus] = useState<GmailStatus | null>(null)

  // ONP v0.6.1 — Adaptive polling: 60s while disconnected (state may change
  // any moment via OAuth popup), 5min once connected (state is stable; cuts
  // background traffic 5×). Re-arms whenever connectedness toggles.
  const connectedFlag = status?.connected === true
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const r = await deeperNotebookFetch(
          '/api/deeper-notebook/gmail/status',
        )
        if (!r.ok) return
        const data = (await r.json()) as GmailStatus
        if (!cancelled) setStatus(data)
      } catch {
        /* ignore — leave status null so the button is still clickable */
      }
    }
    load()
    const pollMs = connectedFlag ? 300_000 : 60_000
    const interval = setInterval(load, pollMs)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [connectedFlag])

  const goToSettings = () => {
    router.push('/settings/api-keys#email-digests')
  }

  const connected = status?.connected === true
  const label = connected
    ? (status?.email_address
        ? `Gmail · ${status.email_address.split('@')[0]}`
        : 'Gmail connected')
    : 'Sign in with Gmail'

  const iconColor = connected ? 'var(--dn-success, #14B870)' : 'currentColor'

  return (
    <Button
      variant={iconOnly ? 'ghost' : 'outline'}
      size={iconOnly ? 'icon' : 'default'}
      onClick={goToSettings}
      className={
        iconOnly
          ? 'h-9 w-full sidebar-menu-item'
          : 'w-full justify-start gap-2 sidebar-menu-item'
      }
      aria-label={label}
      title={connected
        ? `Connected as ${status?.email_address}`
        : 'Connect Gmail for activity digests'}
    >
      <div className="relative h-[1.2rem] w-[1.2rem]" style={{ color: iconColor }}>
        <Mail className="absolute inset-0 h-[1.2rem] w-[1.2rem]" />
        {connected && (
          <CheckCircle2 className="absolute bottom-[-2px] right-[-2px] h-[0.7rem] w-[0.7rem]"
            style={{ background: 'var(--background)', borderRadius: '50%' }} />
        )}
      </div>
      {!iconOnly && <span className="truncate">{label}</span>}
    </Button>
  )
}
