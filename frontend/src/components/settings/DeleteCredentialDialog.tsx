/**
 * v0.7.40 — Extracted from api-keys/page.tsx (was inline at line 647-744).
 *
 * Self-contained delete-credential dialog. Three deletion modes:
 *
 *   1. Plain delete — when the credential has no linked models, just
 *      remove the credential row.
 *   2. Delete + cascade — when the credential has linked models AND
 *      no migration target is selected, remove the credential and
 *      the models in one call (`delete_models: true`).
 *   3. Migrate + delete — when the credential has linked models AND
 *      a migration target IS selected, rebind those models to the
 *      chosen replacement credential, then delete the original.
 *
 * Migration targets are restricted to other credentials for the SAME
 * provider — moving an OpenAI credential's models to an Anthropic
 * credential would be incoherent.
 */
'use client'

import { useState } from 'react'
import { AlertCircle, Loader2 } from 'lucide-react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useDeleteCredential } from '@/lib/hooks/use-credentials'
import { useTranslation } from '@/lib/hooks/use-translation'
import { Credential } from '@/lib/api/credentials'

interface DeleteCredentialDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  credential: Credential
  allCredentials: Credential[]
}

export function DeleteCredentialDialog({
  open,
  onOpenChange,
  credential,
  allCredentials,
}: DeleteCredentialDialogProps) {
  const { t } = useTranslation()
  const deleteCredential = useDeleteCredential()
  const [migrateToId, setMigrateToId] = useState<string>('')

  const otherCredentials = allCredentials.filter(
    (c) => c.id !== credential.id && c.provider === credential.provider,
  )

  const handleDeleteWithModels = () => {
    deleteCredential.mutate(
      { credentialId: credential.id, options: { delete_models: true } },
      { onSuccess: () => onOpenChange(false) },
    )
  }

  const handleMigrate = () => {
    if (!migrateToId) return
    deleteCredential.mutate(
      { credentialId: credential.id, options: { migrate_to: migrateToId } },
      { onSuccess: () => onOpenChange(false) },
    )
  }

  const handleDeleteOnly = () => {
    deleteCredential.mutate(
      { credentialId: credential.id },
      { onSuccess: () => onOpenChange(false) },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('apiKeys.deleteConfig')}</DialogTitle>
          <DialogDescription>
            {t('apiKeys.deleteConfigConfirm').replace('{name}', credential.name)}
          </DialogDescription>
        </DialogHeader>

        {credential.model_count > 0 && (
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              This credential has {credential.model_count} linked model(s).
              {otherCredentials.length > 0 && (
                <div className="mt-2">
                  <Label>Migrate models to:</Label>
                  <Select value={migrateToId} onValueChange={setMigrateToId}>
                    <SelectTrigger className="mt-1">
                      <SelectValue placeholder="Select credential" />
                    </SelectTrigger>
                    <SelectContent>
                      {otherCredentials.map((c) => (
                        <SelectItem key={c.id} value={c.id}>
                          {c.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </AlertDescription>
          </Alert>
        )}

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          {credential.model_count > 0 && migrateToId && (
            <Button onClick={handleMigrate} disabled={deleteCredential.isPending}>
              {deleteCredential.isPending && (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              )}
              Migrate & Delete
            </Button>
          )}
          <Button
            variant="destructive"
            onClick={
              credential.model_count > 0
                ? handleDeleteWithModels
                : handleDeleteOnly
            }
            disabled={deleteCredential.isPending}
          >
            {deleteCredential.isPending && (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            )}
            {credential.model_count > 0
              ? 'Delete with Models'
              : t('common.delete')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
