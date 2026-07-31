'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { knowledgeNavigationApi } from '@/lib/api/knowledge-navigation'

export const knowledgeNavigationKeys = {
  root: ['knowledge-navigation'] as const,
  bookmarks: (filters: Record<string, unknown> = {}) => ['knowledge-navigation', 'bookmarks', filters] as const,
  folders: ['knowledge-navigation', 'folders'] as const,
  workspaces: ['knowledge-navigation', 'workspaces'] as const,
  workspace: (workspaceId: string) => ['knowledge-navigation', 'workspaces', workspaceId] as const,
}

export function useKnowledgeBookmarks(filters: Record<string, unknown> = {}) {
  return useQuery({ queryKey: knowledgeNavigationKeys.bookmarks(filters), queryFn: () => knowledgeNavigationApi.listBookmarks(filters) })
}
export function useKnowledgeFolders() {
  return useQuery({ queryKey: knowledgeNavigationKeys.folders, queryFn: knowledgeNavigationApi.listFolders })
}
export function useKnowledgeWorkspaces() {
  return useQuery({ queryKey: knowledgeNavigationKeys.workspaces, queryFn: knowledgeNavigationApi.listWorkspaces })
}
export function useKnowledgeWorkspace(workspaceId?: string) {
  return useQuery({ queryKey: knowledgeNavigationKeys.workspace(workspaceId ?? ''), queryFn: () => knowledgeNavigationApi.getWorkspace(workspaceId!), enabled: Boolean(workspaceId) })
}

function useCollectionMutation<T>(
  mutationFn: (input: T) => Promise<unknown>,
  invalidate: readonly unknown[],
) {
  const client = useQueryClient()
  return useMutation({
    mutationFn,
    retry: false,
    onSuccess: () => client.invalidateQueries({ queryKey: invalidate }),
  })
}
export function useCreateKnowledgeBookmark() { return useCollectionMutation(knowledgeNavigationApi.createBookmark, ['knowledge-navigation', 'bookmarks']) }
export function useUpdateKnowledgeBookmark() {
  return useCollectionMutation(({ bookmarkId, command }: { bookmarkId: string; command: Record<string, unknown> }) => knowledgeNavigationApi.updateBookmark(bookmarkId, command as never), ['knowledge-navigation', 'bookmarks'])
}
export function useDeleteKnowledgeBookmark() {
  return useCollectionMutation(({ bookmarkId, command }: { bookmarkId: string; command: Record<string, unknown> }) => knowledgeNavigationApi.deleteBookmark(bookmarkId, command), ['knowledge-navigation', 'bookmarks'])
}
export function useCreateKnowledgeFolder() { return useCollectionMutation(knowledgeNavigationApi.createFolder, knowledgeNavigationKeys.folders) }
export function useUpdateKnowledgeFolder() {
  return useCollectionMutation(({ folderId, command }: { folderId: string; command: Record<string, unknown> }) => knowledgeNavigationApi.updateFolder(folderId, command), knowledgeNavigationKeys.folders)
}
export function useDeleteKnowledgeFolder() {
  return useCollectionMutation(({ folderId, command }: { folderId: string; command: Record<string, unknown> }) => knowledgeNavigationApi.deleteFolder(folderId, command), knowledgeNavigationKeys.folders)
}
export function useCreateKnowledgeWorkspace() { return useCollectionMutation(knowledgeNavigationApi.createWorkspace, knowledgeNavigationKeys.workspaces) }
export function useUpdateKnowledgeWorkspace() {
  return useCollectionMutation(({ workspaceId, command }: { workspaceId: string; command: Record<string, unknown> }) => knowledgeNavigationApi.updateWorkspace(workspaceId, command), knowledgeNavigationKeys.workspaces)
}
export function useDuplicateKnowledgeWorkspace() {
  return useCollectionMutation(({ workspaceId, command }: { workspaceId: string; command: Record<string, unknown> }) => knowledgeNavigationApi.duplicateWorkspace(workspaceId, command), knowledgeNavigationKeys.workspaces)
}
export function useDeleteKnowledgeWorkspace() {
  return useCollectionMutation(({ workspaceId, command }: { workspaceId: string; command: Record<string, unknown> }) => knowledgeNavigationApi.deleteWorkspace(workspaceId, command), knowledgeNavigationKeys.workspaces)
}
export function useRestoreKnowledgeWorkspace() {
  return useMutation({ mutationFn: ({ workspaceId, revision }: { workspaceId: string; revision: number }) => knowledgeNavigationApi.restorePlan(workspaceId, revision), retry: false })
}
export function useRandomKnowledgeNote() {
  return useMutation({ mutationFn: (filters: Record<string, unknown> = {}) => knowledgeNavigationApi.randomNote(filters), retry: false })
}
