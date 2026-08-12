'use client'

import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { useCreateNotebook } from '@/lib/hooks/use-notebooks'
import { useTranslation } from '@/lib/hooks/use-translation'

// v0.7.199 — factory pattern so the validation message is
// translated. Was hardcoded English "Name is required" — non-
// English users saw English text in the field-error.
const makeCreateNotebookSchema = (t: (key: string) => string) =>
  z.object({
    name: z.string().min(1, t('common.nameRequired')),
    description: z.string().optional(),
  })

type CreateNotebookFormData = z.infer<ReturnType<typeof makeCreateNotebookSchema>>

interface CreateNotebookDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateNotebookDialog({ open, onOpenChange }: CreateNotebookDialogProps) {
  const { t } = useTranslation()
  const createNotebook = useCreateNotebook()
  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
    reset,
  } = useForm<CreateNotebookFormData>({
    resolver: zodResolver(makeCreateNotebookSchema(t)),
    mode: 'onChange',
    defaultValues: {
      name: '',
      description: '',
    },
  })

  const closeDialog = () => onOpenChange(false)

  const onSubmit = async (data: CreateNotebookFormData) => {
    await createNotebook.mutateAsync(data)
    closeDialog()
    reset()
  }

  useEffect(() => {
    if (!open) {
      reset()
    }
  }, [open, reset])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-[480px]"
        onEscapeKeyDown={(event) => {
          event.preventDefault()
          closeDialog()
        }}
      >
        <DialogHeader>
          <DialogTitle>{t('notebooks.createNew')}</DialogTitle>
          <DialogDescription>
            {t('notebooks.createNewDesc')}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="notebook-name">{t('common.name')} *</Label>
            <Input
              id="notebook-name"
              {...register('name')}
              placeholder={t('notebooks.namePlaceholder')}
              autoComplete="off"
            />
            {errors.name && (
              <p className="text-sm text-destructive">{errors.name.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="notebook-description">{t('common.description')}</Label>
            <Textarea
              id="notebook-description"
              {...register('description')}
              placeholder={t('notebooks.descPlaceholder')}
              rows={4}
            />
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={closeDialog}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={!isValid || createNotebook.isPending}>
              {createNotebook.isPending ? t('common.creating') : t('notebooks.createNew')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
