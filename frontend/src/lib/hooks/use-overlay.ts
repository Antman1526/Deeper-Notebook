import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  overlayApi,
  type CreateUniqueOverlayNote,
  type OverlayPage,
  type UpdateOverlayNote,
} from '@/lib/api/overlay'
import { vaultKeys } from '@/lib/hooks/use-vault'

export const overlayKeys = {
  all: ['overlay'] as const,
  notes: ['overlay', 'notes'] as const,
  page: (id: string) => ['overlay', 'notes', id] as const,
}

async function invalidateCreatedPage(client: ReturnType<typeof useQueryClient>, page: OverlayPage) {
  await Promise.all([
    client.invalidateQueries({ queryKey: overlayKeys.notes }),
    client.invalidateQueries({ queryKey: ['search'] }),
    client.invalidateQueries({ queryKey: vaultKeys.files(page.overlay.space_id) }),
  ])
  client.setQueryData(overlayKeys.page(page.overlay.id), page)
}

async function invalidateUpdatedPage(client: ReturnType<typeof useQueryClient>, page: OverlayPage) {
  await invalidateCreatedPage(client, page)
  await Promise.all([
    client.invalidateQueries({ queryKey: vaultKeys.backlinks(page.overlay.space_id, page.overlay.projected_note_id) }),
    client.invalidateQueries({ queryKey: vaultKeys.graph(page.overlay.space_id, page.overlay.projected_note_id) }),
  ])
}

export function useOverlayNotes() {
  return useQuery({ queryKey: overlayKeys.notes, queryFn: () => overlayApi.list() })
}

export function useOverlayPage(id?: string) {
  return useQuery({
    queryKey: overlayKeys.page(id ?? ''),
    queryFn: () => overlayApi.page(id!),
    enabled: Boolean(id),
  })
}

export function useTodayOverlayNote() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (dateKey: string) => overlayApi.daily(dateKey),
    onSuccess: (page) => invalidateCreatedPage(client, page),
  })
}

export function useCreateUniqueOverlayNote() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateUniqueOverlayNote) => overlayApi.unique(input),
    onSuccess: (page) => invalidateCreatedPage(client, page),
  })
}

export function useUpdateOverlayNote() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...input }: UpdateOverlayNote & { id: string }) => overlayApi.update(id, input),
    onSuccess: (page) => invalidateUpdatedPage(client, page),
  })
}
