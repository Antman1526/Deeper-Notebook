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
import { useMCPServers, useWebSearchStatus } from '@/lib/hooks/use-mcp-servers'
import { useTranslation } from '@/lib/hooks/use-translation'

// v0.8.65 — literal tool name the chat tool loop matches in
// `disabled_mcp_servers` to exclude the built-in web_search tool.
const WEB_SEARCH_TOOL_NAME = 'web_search'
// v0.8.82 — same convention for the built-in keyless scholarly_search tool.
const SCHOLARLY_SEARCH_TOOL_NAME = 'scholarly_search'

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

  // v0.8.65 — the built-in `web_search` tool isn't a registry row, so it never
  // appears in useMCPServers(). Surface it as a synthetic toggle when a
  // provider is configured (Serper/Tavily/SearXNG) so the user can see it's on
  // and untick it for a turn. onToggle('web_search') maps straight to the
  // exclude name the chat tool loop already honours (v0.8.64).
  const { data: webSearch } = useWebSearchStatus()
  const webSearchAvailable = !!webSearch?.enabled
  const webSearchOff = disabled.some(
    d => d.trim().toLowerCase() === WEB_SEARCH_TOOL_NAME,
  )
  // v0.8.82 — scholarly_search is keyless and bound by default, so it needs a
  // visible off-switch here just like web_search; an always-on network tool
  // must not be the one tool the picker can't untick.
  const scholarlyAvailable = !!webSearch?.scholarly_enabled
  const scholarlyOff = disabled.some(
    d => d.trim().toLowerCase() === SCHOLARLY_SEARCH_TOOL_NAME,
  )

  // Hide the picker only when there is genuinely nothing to toggle.
  if (servers.length === 0 && !webSearchAvailable && !scholarlyAvailable) return null

  const total =
    servers.length + (webSearchAvailable ? 1 : 0) + (scholarlyAvailable ? 1 : 0)
  const enabledCount =
    servers.filter(
      s => !disabled.some(d => d.trim().toLowerCase() === (s.name || '').trim().toLowerCase()),
    ).length +
    (webSearchAvailable && !webSearchOff ? 1 : 0) +
    (scholarlyAvailable && !scholarlyOff ? 1 : 0)

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
            total: total,
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
          {webSearchAvailable && (
            <li
              className="flex items-center gap-2"
              data-testid="mcp-pick-web-search-row"
            >
              <Checkbox
                id="mcp-pick-web-search"
                checked={!webSearchOff}
                onCheckedChange={() => onToggle(WEB_SEARCH_TOOL_NAME)}
                data-testid="mcp-pick-web-search"
              />
              <Label
                htmlFor="mcp-pick-web-search"
                className="text-xs cursor-pointer flex-1 min-w-0"
              >
                <span className="truncate block">
                  {t('chat.mcpPicker.webSearch', { defaultValue: 'Web search' })}
                  {webSearch?.provider ? ` (${webSearch.provider})` : ''}
                </span>
              </Label>
            </li>
          )}
          {scholarlyAvailable && (
            <li
              className="flex items-center gap-2"
              data-testid="mcp-pick-scholarly-search-row"
            >
              <Checkbox
                id="mcp-pick-scholarly-search"
                checked={!scholarlyOff}
                onCheckedChange={() => onToggle(SCHOLARLY_SEARCH_TOOL_NAME)}
                data-testid="mcp-pick-scholarly-search"
              />
              <Label
                htmlFor="mcp-pick-scholarly-search"
                className="text-xs cursor-pointer flex-1 min-w-0"
              >
                <span className="truncate block">
                  {t('chat.mcpPicker.scholarlySearch', {
                    defaultValue: 'Scholarly search (OpenAlex/arXiv)',
                  })}
                </span>
              </Label>
            </li>
          )}
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
        {(webSearchAvailable || scholarlyAvailable) && (
          // v0.8.65 — the built-in web_search tool (like all bound tools) only
          // fires if the active chat model supports function/tool calling.
          // Surface that so a user whose local model silently can't tool-call
          // understands why web search isn't happening (it isn't a config bug).
          <p
            className="text-[10px] text-muted-foreground border-t pt-2"
            data-testid="mcp-pick-web-search-hint"
          >
            {t('chat.mcpPicker.webSearchHint', {
              defaultValue:
                'Web search needs a chat model that supports tool calling — most cloud models do; many small local models do not.',
            })}
          </p>
        )}
      </PopoverContent>
    </Popover>
  )
}

export default McpToolPicker
