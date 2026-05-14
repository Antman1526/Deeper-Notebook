/**
 * GmailIntegration — Email-digest setup panel for the Settings page.
 *
 * Three states:
 *   1. No OAuth credentials → show paste-credentials form with link to
 *      Google Cloud Console docs
 *   2. Credentials saved, not connected → "Connect Gmail" button (OAuth flow)
 *   3. Connected → show email, frequency picker, section toggles,
 *      "Send digest now" + "Disconnect" buttons
 *
 * Shadow-layer component — see components/onp/README.md.
 */
'use client'

import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Mail, CheckCircle2, Loader2, ExternalLink } from 'lucide-react'

interface GmailStatus {
  connected: boolean
  email_address: string | null
  has_client_credentials: boolean
  enabled: boolean
  frequency: string
  include_notebooks: boolean
  include_sources: boolean
  include_notes: boolean
  include_podcasts: boolean
  include_memory: boolean
  last_sent_at: string | null
}

export function GmailIntegration() {
  const [status, setStatus] = useState<GmailStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')

  // v0.6.3 — track mount state + active OAuth poller so we can cancel both
  // cleanly. Without this, setInterval / setTimeout / in-flight fetches
  // happily call setState on an unmounted component (React warning + leak).
  const mountedRef = useRef(true)
  const oauthPollRef = useRef<{
    interval: ReturnType<typeof setInterval> | null
    timeout: ReturnType<typeof setTimeout> | null
  }>({ interval: null, timeout: null })

  function stopOauthPolling() {
    if (oauthPollRef.current.interval) clearInterval(oauthPollRef.current.interval)
    if (oauthPollRef.current.timeout) clearTimeout(oauthPollRef.current.timeout)
    oauthPollRef.current.interval = null
    oauthPollRef.current.timeout = null
  }

  async function refresh() {
    try {
      const r = await fetch('/api/onp/gmail/status')
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = (await r.json()) as GmailStatus
      if (mountedRef.current) setStatus(data)
    } catch (e) {
      if (mountedRef.current) setError(e instanceof Error ? e.message : String(e))
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }

  useEffect(() => {
    mountedRef.current = true
    refresh()
    return () => {
      mountedRef.current = false
      stopOauthPolling()
    }
  }, [])

  async function saveCredentials() {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const r = await fetch('/api/onp/gmail/credentials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
      })
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        throw new Error(body.detail || `HTTP ${r.status}`)
      }
      setMessage('Credentials saved. Click "Connect Gmail" to authorize.')
      setClientId('')
      setClientSecret('')
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  function connectGmail() {
    // Open OAuth flow in a NEW window — the auth flow needs a different
    // browser context than the PyWebView main window (Google Sign-In blocks
    // embedded WebViews). The callback returns an HTML page that closes the
    // window automatically.
    stopOauthPolling()  // cancel any previous attempt

    const popup = window.open('/api/onp/gmail/connect', 'gmail_oauth',
                              'width=600,height=720')
    // v0.6.1 — if popup blocked, fall back to opening in the current window
    // (user will navigate back after OAuth completes).
    if (!popup || popup.closed || typeof popup.closed === 'undefined') {
      setError(
        'Popup blocked. Click "Connect Gmail" again with popups enabled, ' +
        'or open the OAuth URL directly: /api/onp/gmail/connect'
      )
      return
    }
    // Poll for connection status until we see connected=true. Stops on
    // success, user-closed popup, component unmount, or 90s timeout.
    setMessage('Waiting for Google sign-in to complete…')
    const interval = setInterval(async () => {
      // Bail fast if component unmounted between ticks
      if (!mountedRef.current) {
        stopOauthPolling()
        return
      }
      // Bail if user closed the popup (gives back ~85s of wasted requests)
      if (popup.closed) {
        stopOauthPolling()
        setMessage(null)
        return
      }
      try {
        const r = await fetch('/api/onp/gmail/status')
        if (!r.ok) return
        const data = (await r.json()) as GmailStatus
        if (!mountedRef.current) return
        setStatus(data)
        if (data.connected) {
          stopOauthPolling()
          setMessage(`Connected as ${data.email_address}`)
        }
      } catch { /* keep polling */ }
    }, 2000)
    // Belt-and-suspenders: stop polling after 90 s even if user abandoned
    const timeout = setTimeout(() => {
      stopOauthPolling()
      if (mountedRef.current) {
        setMessage((prev) => (prev?.startsWith('Waiting') ? null : prev))
      }
    }, 90_000)
    oauthPollRef.current = { interval, timeout }
  }

  async function updateSetting<K extends keyof GmailStatus>(key: K, value: GmailStatus[K]) {
    if (!status) return
    // Optimistic UI update — reverted by refresh() on failure.
    const previous = status
    setStatus({ ...status, [key]: value })
    try {
      const r = await fetch('/api/onp/gmail/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      })
      // v0.6.3 — fetch() only rejects on network error; HTTP errors come
      // through as ok=false and were previously silently ignored.
      if (!r.ok) {
        const body = await r.json().catch(() => ({} as { detail?: string }))
        throw new Error(body.detail || `HTTP ${r.status}`)
      }
    } catch (e) {
      if (!mountedRef.current) return
      setError(e instanceof Error ? e.message : String(e))
      setStatus(previous)  // roll back optimistic update
    }
  }

  async function disconnect() {
    if (!confirm('Disconnect Gmail? You can reconnect anytime.')) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const r = await fetch('/api/onp/gmail/disconnect', { method: 'POST' })
      if (!r.ok) {
        const body = await r.json().catch(() => ({} as { detail?: string }))
        throw new Error(body.detail || `HTTP ${r.status}`)
      }
      await refresh()
      if (mountedRef.current) setMessage('Disconnected.')
    } catch (e) {
      if (mountedRef.current) setError(e instanceof Error ? e.message : String(e))
    } finally {
      if (mountedRef.current) setBusy(false)
    }
  }

  // v0.6.1 — actually delete the OAuth client credentials. Previously the
  // 'Forget credentials' button toggled `enabled=false`, which was a no-op
  // when credentials existed but the user wasn't connected yet.
  async function forgetCredentials() {
    if (!confirm(
      'Forget the saved Google OAuth client_id / client_secret? You\'ll ' +
      'need to paste them again next time.'
    )) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const r = await fetch('/api/onp/gmail/credentials', { method: 'DELETE' })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      await refresh()
      setMessage('OAuth credentials cleared.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function sendTest() {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const r = await fetch('/api/onp/gmail/send-test', { method: 'POST' })
      const body = await r.json()
      if (!r.ok || !body.ok) {
        throw new Error(body.message || body.detail || `HTTP ${r.status}`)
      }
      setMessage(body.message || 'Sent.')
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Mail className="h-4 w-4" /> Email Digests</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-[var(--muted-foreground)]"><Loader2 className="inline h-3 w-3 animate-spin mr-1" /> Loading…</p>
        </CardContent>
      </Card>
    )
  }

  if (!status) {
    return (
      <Card>
        <CardHeader><CardTitle>Email Digests</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-[var(--destructive)]">{error || 'Failed to load status.'}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mail className="h-4 w-4" />
          Email Digests
          {status.connected && (
            <span className="ml-2 inline-flex items-center gap-1 text-xs text-[var(--onp-success,_#14B870)]">
              <CheckCircle2 className="h-3 w-3" /> Connected
            </span>
          )}
        </CardTitle>
        <CardDescription>
          Get a periodic digest of notebook activity sent to your Gmail.
          {status.connected && status.email_address && (
            <> Sending to <strong>{status.email_address}</strong>.</>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <p className="text-sm text-[var(--destructive)] p-2 rounded bg-[var(--destructive)]/10">
            {error}
          </p>
        )}
        {message && (
          <p className="text-sm text-[var(--onp-success,_#14B870)] p-2 rounded bg-[var(--onp-success-soft,_rgba(20,184,112,0.1))]">
            {message}
          </p>
        )}

        {!status.has_client_credentials ? (
          /* State 1 — paste OAuth credentials */
          <div className="space-y-3">
            <div className="text-sm space-y-2">
              <p>One-time setup: create a Google Cloud OAuth client.</p>
              <ol className="ml-5 list-decimal text-xs text-[var(--muted-foreground)] space-y-1">
                <li>Open <a href="https://console.cloud.google.com/apis/credentials" target="_blank" className="underline inline-flex items-center gap-0.5">Google Cloud Console <ExternalLink className="h-3 w-3" /></a></li>
                <li>Create an OAuth 2.0 Client ID (type: <em>Desktop app</em>)</li>
                <li>Add <code>http://localhost</code> to authorized redirect URIs (we'll match the port dynamically)</li>
                <li>Enable the <em>Gmail API</em> in your project</li>
                <li>Paste the Client ID + Secret below</li>
              </ol>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="gmail-client-id" className="text-xs">Client ID</Label>
              <Input id="gmail-client-id" value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder="123…apps.googleusercontent.com" className="h-8 text-xs" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="gmail-client-secret" className="text-xs">Client Secret</Label>
              <Input id="gmail-client-secret" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} type="password" placeholder="GOCSPX-…" className="h-8 text-xs" />
            </div>
            <Button onClick={saveCredentials} disabled={busy || !clientId || !clientSecret} size="sm">
              {busy ? <><Loader2 className="h-3 w-3 animate-spin mr-1" /> Saving…</> : 'Save credentials'}
            </Button>
          </div>
        ) : !status.connected ? (
          /* State 2 — credentials saved, not yet OAuth-authorized */
          <div className="space-y-3">
            <p className="text-sm">OAuth credentials saved. Click below to sign in with Gmail.</p>
            <div className="flex gap-2">
              <Button onClick={connectGmail} disabled={busy} size="sm">
                <Mail className="h-3 w-3 mr-1" /> Connect Gmail
              </Button>
              <Button onClick={forgetCredentials} disabled={busy} variant="ghost" size="sm">
                Forget credentials
              </Button>
            </div>
            <p className="text-xs text-[var(--muted-foreground)]">
              Opens a Google sign-in window. We request only <code>gmail.send</code>
              — never read access to your inbox.
            </p>
          </div>
        ) : (
          /* State 3 — connected */
          <div className="space-y-4">
            <div className="grid gap-2">
              <Label htmlFor="gmail-frequency" className="text-xs">Frequency</Label>
              <Select value={status.frequency} onValueChange={(v) => updateSetting('frequency' as keyof GmailStatus, v as never)}>
                <SelectTrigger id="gmail-frequency" className="h-8 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="daily">Daily</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                  <SelectItem value="manual">Manual only</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Include in digest</Label>
              {[
                ['include_notebooks', 'Notebooks created or updated'],
                ['include_sources', 'New sources (PDFs, links, transcripts)'],
                ['include_notes', 'New notes'],
                ['include_podcasts', 'Podcast episodes generated'],
                ['include_memory', 'Memory facts extracted from chat'],
              ].map(([key, label]) => (
                <label key={key} className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={status[key as keyof GmailStatus] as boolean}
                    onChange={(e) => updateSetting(key as keyof GmailStatus, e.target.checked as never)}
                  />
                  {label}
                </label>
              ))}
            </div>

            <div className="flex flex-wrap gap-2 pt-2">
              <Button onClick={sendTest} disabled={busy} size="sm" variant="outline">
                {busy ? <><Loader2 className="h-3 w-3 animate-spin mr-1" /> Sending…</> : 'Send digest now'}
              </Button>
              <Button onClick={disconnect} disabled={busy} size="sm" variant="ghost">
                Disconnect
              </Button>
            </div>

            {status.last_sent_at && (
              <p className="text-xs text-[var(--muted-foreground)]">
                Last sent: {new Date(status.last_sent_at).toLocaleString()}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
