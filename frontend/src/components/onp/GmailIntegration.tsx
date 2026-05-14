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

import { useEffect, useState } from 'react'

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

  async function refresh() {
    try {
      const r = await fetch('/api/onp/gmail/status')
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = (await r.json()) as GmailStatus
      setStatus(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
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
    window.open('/api/onp/gmail/connect', 'gmail_oauth', 'width=600,height=720')
    // Poll for connection status — refresh every 2s for 60s
    const interval = setInterval(refresh, 2000)
    setTimeout(() => clearInterval(interval), 60_000)
  }

  async function updateSetting<K extends keyof GmailStatus>(key: K, value: GmailStatus[K]) {
    if (!status) return
    setStatus({ ...status, [key]: value })
    try {
      await fetch('/api/onp/gmail/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      refresh()
    }
  }

  async function disconnect() {
    if (!confirm('Disconnect Gmail? You can reconnect anytime.')) return
    setBusy(true)
    try {
      await fetch('/api/onp/gmail/disconnect', { method: 'POST' })
      await refresh()
      setMessage('Disconnected.')
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
              <Button onClick={() => updateSetting('enabled' as keyof GmailStatus, false as never)} disabled={busy} variant="ghost" size="sm">
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
