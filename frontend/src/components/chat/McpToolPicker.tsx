'use client'

/**
 * McpToolPicker.tsx — v0.8.42
 *
 * Compact popover above the chat input that lists every registered
 * MCP server with a checkbox. Unchecking a server adds its name to
 * `disabled_mcp_servers` on the NEXT chat request — implementing the
 * XDA-Developers / Pi-harness "load only what I need" pattern without
 * touching the persistent registry.enabled column.
 *
 * Design choices:
 *   - State lives on the parent hook (`useNotebookChat`) so navigating
 *     away and back resets it. Persistent per-conversation memory of
 *     "I unticked X" is intentionally NOT in this iteration —
 *     conversation state is on the API session row and would require
 *     a migration. A v0.8.42b could add `disabled_mcp_servers` to
 *     `chat_session` for sticky pref.
 *   - The picker is *additive*: a server that's `enabled=false` at the
 *     registry level is already not in `useMCPServers()` results, so
 *     this picker only sees servers that COULD bind tools. No
 *     overlap with the v0.8.0 admin Settings → MCP page.
 *   - Trigger is a tiny chip showing "N tools enabled" so the user
 *     sees the state at a glance and can click to expand.
 */

import React from 'react'
import { Wrench, CheckSquare } from 'lucide-react'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { useMCPServers } from '@/lib/hooks/use-mcp-servers'
import { useTranslation } from '@/lib/hooks/use-translation'

export interface McpToolPickerProps {
  /** Names currently disabled — controlled. Pass `useNotebookChat.disabledMcpServers`. */
  disabled: string[]
  /** Toggle a single server's enabled state. Pass `useNotebookChat.toggleDisabledMcpServer`. */
  onToggle: (name: string) => void
}

export function McpToolPicker({ disabled, onToggle }: McpToolPickerProps) {
  const { t } = useTranslation()
  const { data: rawServers = [] } = useMCPServers()
  // Show only registry-enabled servers — registry-disabled ones can't
  // bind tools regardless of our state.
  const servers = rawServers.filter(s => s.enabled)

  if (servers.length === 0) return null

  const enabledCount = servers.filter(
    s => !disabled.some(d => d.trim().toLowerCase() === (s.name || '').trim().toLowerCase()),
  ).length

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="gap-1.5 h-7 text-xs"
          data-testid="mcp-tool-picker-trigger"
        >
          <Wrench className="h-3 w-3" />
          {t('chat.mcpPicker.label', {
            defaultValue: '{{count}}/{{total}} tools',
            count: enabledCount,
            total: servers.length,
          })}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="start"
        className="w-72 p-3 space-y-2"
        data-testid="mcp-tool-picker-popover"
      >
        <div className="flex items-center gap-1.5 text-xs font-medium">
          <CheckSquare className="h-3 w-3" />
          {t('chat.mcpPicker.heading', {
            defaultValue: 'MCP tools for this turn',
          })}
        </div>
        <p className="text-[10px] text-muted-foreground">
          {t('chat.mcpPicker.helpText', {
            defaultValue:
              'Untick servers you do NOT want the model to call this turn. Reduces token cost when an unused tool would otherwise hang in context.',
          })}
        </p>
        <ul className="space-y-1.5 max-h-60 overflow-y-auto">
          {servers.map(s => {
            const isOff = disabled.some(
              d => d.trim().toLowerCase() === (s.name || '').trim().toLowerCase(),
            )
            return (
              <li key={s.id} className="flex items-center gap-2">
                <Checkbox
                  id={`mcp-pick-${s.id}`}
                  checked={!isOff}
                  onCheckedChange={() => onToggle(s.name)}
                  data-testid={`mcp-pick-${s.id}`}
                />
                <Label
                  htmlFor={`mcp-pick-${s.id}`}
                  className="text-xs cursor-pointer flex-1 min-w-0"
                >
                  <span className="truncate block">{s.name}</span>
                </Label>
              </li>
            )
          })}
        </ul>
      </PopoverContent>
    </Popover>
  )
}

export default McpToolPicker
