'use client'

/**
 * MessageCopyEditActions.tsx — v0.8.65g
 *
 * Per-message Copy + Edit controls for the "Chat with Notebook" panel.
 *   - Copy: writes the message text to the clipboard so it can be pasted /
 *     reused with the chatbot.
 *   - Edit: loads the message text back into the chat input (via `onEdit`) so
 *     the user can tweak and resend it.
 *
 * Human messages previously had NO actions (only AI messages had MessageActions
 * with Copy + Save-to-note). This adds Copy + Edit to human messages, and an
 * Edit-only control to AI messages (which already expose Copy).
 */

import { useState } from 'react'
import { Copy, Check, Pencil } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'

export interface MessageCopyEditActionsProps {
  /** The raw message text to copy / load into the input. */
  content: string
  /** Load `content` into the chat input for editing + resend. */
  onEdit: (content: string) => void
  /** Show the Copy button (default true). AI messages already have a Copy via
   *  MessageActions, so they pass `showCopy={false}` to avoid a duplicate. */
  showCopy?: boolean
}

export function MessageCopyEditActions({
  content,
  onEdit,
  showCopy = true,
}: MessageCopyEditActionsProps) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard API can be unavailable (insecure context / denied perms).
      // Best-effort: silently no-op rather than throwing into the render tree.
    }
  }

  return (
    <div className="flex items-center gap-1" data-testid="message-copy-edit">
      {showCopy && (
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-1.5 text-[10px] gap-1 text-muted-foreground hover:text-foreground"
          onClick={handleCopy}
          data-testid="message-copy"
          aria-label={t('chat.message.copy', { defaultValue: 'Copy' })}
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          {copied
            ? t('chat.message.copied', { defaultValue: 'Copied' })
            : t('chat.message.copy', { defaultValue: 'Copy' })}
        </Button>
      )}
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-1.5 text-[10px] gap-1 text-muted-foreground hover:text-foreground"
        onClick={() => onEdit(content)}
        data-testid="message-edit"
        aria-label={t('chat.message.edit', { defaultValue: 'Edit' })}
      >
        <Pencil className="h-3 w-3" />
        {t('chat.message.edit', { defaultValue: 'Edit' })}
      </Button>
    </div>
  )
}

export default MessageCopyEditActions
