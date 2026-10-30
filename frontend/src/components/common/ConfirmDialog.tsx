'use client'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useTranslation } from '@/lib/hooks/use-translation'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { buttonVariants } from '@/components/ui/button'

interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  confirmText?: string
  confirmVariant?: 'default' | 'destructive'
  onConfirm: () => void
  isLoading?: boolean
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmText,
  confirmVariant = 'default',
  onConfirm,
  isLoading = false,
}: ConfirmDialogProps) {
  const { t } = useTranslation()
  const finalConfirmText = confirmText || t('common.confirm')

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      {/* A title-only confirmation opts out of aria-describedby rather than pointing it
          at an empty description. */}
      <AlertDialogContent {...(description ? {} : { 'aria-describedby': undefined })}>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {description ? <AlertDialogDescription>{description}</AlertDialogDescription> : null}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={isLoading}
            // v0.8.130 — Phase 4c: the destructive variant whole, so the label takes the
            // destructive foreground (it kept the primary button's, dark on red in dark themes).
            className={confirmVariant === 'destructive' ? buttonVariants({ variant: 'destructive' }) : ''}
          >
            {isLoading ? (
              <>
                <LoadingSpinner size="sm" className="mr-2" />
                {finalConfirmText}
              </>
            ) : (
              finalConfirmText
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}