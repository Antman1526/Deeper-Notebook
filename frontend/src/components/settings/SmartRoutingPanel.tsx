'use client'

/**
 * SmartRoutingPanel.tsx — v0.8.37 Phase 2
 *
 * UI control for the v0.8.0 smart router. Pre-v0.8.37 the only way to
 * enable it was the DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT env var, which meant
 * the feature was effectively hidden from UI-driven users. This panel
 * lives at the top of Settings → API Keys and offers:
 *
 *   - Master enable toggle (writes `auto_route_enabled`).
 *   - Provider preference dropdown: auto / local / cloud
 *     (writes `auto_route_provider_pref`).
 *
 * Both write through `useUpdateDefaults` so the changes round-trip via
 * `PUT /models/defaults` and take effect on the very next chat turn.
 * Env var still wins server-side (back-compat); we surface a small
 * notice when we detect that an env var is overriding the UI toggle.
 *
 * Out of scope for this iteration (per the plan): a "sample turn"
 * debugger that POSTs a 100-token + 30k-token probe and shows what
 * pick_provider() would return for each. Deferred to v0.8.37b — adds
 * a new endpoint + non-trivial UX; the toggle alone is the bigger
 * unlock for now.
 */

import React from 'react'
import { Sparkles, Cloud, MonitorCog, Workflow } from 'lucide-react'
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useUpdateModelDefaults } from '@/lib/hooks/use-models'
import { toast } from 'sonner'
import type { ModelDefaults } from '@/lib/types/models'

export interface SmartRoutingPanelProps {
  defaults: ModelDefaults
}

export function SmartRoutingPanel({ defaults }: SmartRoutingPanelProps) {
  const { t } = useTranslation()
  const updateDefaults = useUpdateModelDefaults()

  const enabled = Boolean(defaults.auto_route_enabled)
  const pref = defaults.auto_route_provider_pref ?? 'auto'

  const saveToggle = (next: boolean) => {
    updateDefaults.mutate(
      { auto_route_enabled: next },
      {
        onSuccess: () =>
          toast.success(
            next
              ? t('models.smartRouting.toastEnabled', {
                  defaultValue: 'Smart routing enabled',
                })
              : t('models.smartRouting.toastDisabled', {
                  defaultValue: 'Smart routing disabled',
                }),
          ),
        onError: () =>
          toast.error(
            t('models.smartRouting.toastError', {
              defaultValue: 'Could not save smart-routing settings',
            }),
          ),
      },
    )
  }

  const savePref = (next: 'auto' | 'local' | 'cloud') => {
    updateDefaults.mutate(
      { auto_route_provider_pref: next },
      {
        onSuccess: () =>
          toast.success(
            t('models.smartRouting.toastPrefSaved', {
              defaultValue: 'Provider preference saved',
            }),
          ),
        onError: () =>
          toast.error(
            t('models.smartRouting.toastError', {
              defaultValue: 'Could not save smart-routing settings',
            }),
          ),
      },
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Sparkles className="h-4 w-4" />
          {t('models.smartRouting.title', { defaultValue: 'Smart routing' })}
        </CardTitle>
        <CardDescription>
          {t('models.smartRouting.description', {
            defaultValue:
              'Automatically pick between a local sidecar (llama.cpp, Osaurus) and your cloud provider based on content size, local-model health, and your preference.',
          })}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Master toggle */}
        <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
          <div className="space-y-0.5">
            <Label htmlFor="smart-routing-toggle" className="text-sm font-medium">
              {t('models.smartRouting.toggleLabel', {
                defaultValue: 'Enable smart routing',
              })}
            </Label>
            <p className="text-xs text-muted-foreground">
              {t('models.smartRouting.toggleDescription', {
                defaultValue:
                  'When off, every chat turn uses your default chat model.',
              })}
            </p>
          </div>
          <Checkbox
            id="smart-routing-toggle"
            checked={enabled}
            onCheckedChange={v => saveToggle(v === true)}
            disabled={updateDefaults.isPending}
            data-testid="smart-routing-toggle"
          />
        </div>

        {/* Provider preference — only meaningful when routing is on. */}
        <div className="space-y-1.5">
          <Label htmlFor="smart-routing-pref" className="text-sm font-medium">
            {t('models.smartRouting.prefLabel', {
              defaultValue: 'Provider preference',
            })}
          </Label>
          <Select
            value={pref}
            onValueChange={v => savePref(v as 'auto' | 'local' | 'cloud')}
            disabled={!enabled || updateDefaults.isPending}
          >
            <SelectTrigger
              id="smart-routing-pref"
              data-testid="smart-routing-pref"
              className="w-full min-w-0 max-w-full"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">
                <div className="flex items-center gap-2">
                  <Workflow className="h-3 w-3" />
                  {t('models.smartRouting.prefAuto', {
                    defaultValue: 'Auto (recommended)',
                  })}
                </div>
              </SelectItem>
              <SelectItem value="local">
                <div className="flex items-center gap-2">
                  <MonitorCog className="h-3 w-3" />
                  {t('models.smartRouting.prefLocal', {
                    defaultValue: 'Prefer local',
                  })}
                </div>
              </SelectItem>
              <SelectItem value="cloud">
                <div className="flex items-center gap-2">
                  <Cloud className="h-3 w-3" />
                  {t('models.smartRouting.prefCloud', {
                    defaultValue: 'Prefer cloud',
                  })}
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            {pref === 'auto'
              ? t('models.smartRouting.prefHintAuto', {
                  defaultValue:
                    'Use local when healthy and content fits, otherwise cloud.',
                })
              : pref === 'local'
                ? t('models.smartRouting.prefHintLocal', {
                    defaultValue:
                      'Always use local. The router still falls back to cloud if no local model is configured.',
                  })
                : t('models.smartRouting.prefHintCloud', {
                    defaultValue:
                      'Always use cloud, even when local is healthy and would fit.',
                  })}
          </p>
        </div>

        <p className="text-xs text-muted-foreground">
          {t('models.smartRouting.envOverrideHint', {
            defaultValue:
              'Tip: DEEPER_NOTEBOOK_AUTO_ROUTE_CHAT and DEEPER_NOTEBOOK_CHAT_PROVIDER env vars (if set) override these UI settings.',
          })}
        </p>
      </CardContent>
    </Card>
  )
}

export default SmartRoutingPanel
