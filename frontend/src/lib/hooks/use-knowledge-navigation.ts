'use client'

import { useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  knowledgeNavigationApi,
  prepareKnowledgeNavigationCommand,
  type BookmarkFilters,
  type CreateBookmarkCommand,
  type CreateFolderCommand,
  type CreateWorkspaceCommand,
  type DeleteFolderCommand,
  type DuplicateWorkspaceCommand,
  type RandomNoteFilters,
  type RevisionCommand,
  type UpdateBookmarkCommand,
  type UpdateFolderCommand,
  type UpdateWorkspaceCommand,
} from '@/lib/api/knowledge-navigation'

type EventCommand<T extends { operationId: string }> = Omit<T, 'operationId'>

export const knowledgeNavigationKeys = {
  root: ['knowledge-navigation'] as const,
  bookmarksRoot: ['knowledge-navigation', 'bookmarks'] as const,
  bookmarks: (filters: BookmarkFilters = {}) => [
    'knowledge-navigation', 'bookmarks', filters,
  ] as const,
  folders: ['knowledge-navigation', 'folders'] as const,
  workspaces: ['knowledge-navigation', 'workspaces'] as const,
  workspace: (workspaceId: string) => [
    'knowledge-navigation', 'workspaces', workspaceId,
  ] as const,
}

export function useKnowledgeBookmarks(filters: BookmarkFilters = {}) {
  return useQuery({
    queryKey: knowledgeNavigationKeys.bookmarks(filters),
    queryFn: () => knowledgeNavigationApi.listBookmarks(filters),
  })
}

export function useKnowledgeFolders() {
  return useQuery({
    queryKey: knowledgeNavigationKeys.folders,
    queryFn: knowledgeNavigationApi.listFolders,
  })
}

export function useKnowledgeWorkspaces() {
  return useQuery({
    queryKey: knowledgeNavigationKeys.workspaces,
    queryFn: knowledgeNavigationApi.listWorkspaces,
  })
}

export function useKnowledgeWorkspace(workspaceId?: string) {
  return useQuery({
    queryKey: knowledgeNavigationKeys.workspace(workspaceId ?? ''),
    queryFn: () => knowledgeNavigationApi.getWorkspace(workspaceId!),
    enabled: Boolean(workspaceId),
  })
}

function usePreparedCollectionMutation<Input extends object, Prepared extends object, Result>(
  prepare: (input: Input) => Prepared,
  mutationFn: (prepared: Prepared) => Promise<Result>,
  invalidate: readonly string[],
) {
  const client = useQueryClient()
  const preparedInputs = useRef(new WeakMap<Input, Prepared>())
  return useMutation({
    mutationFn: (input: Input) => {
      let prepared = preparedInputs.current.get(input)
      if (!prepared) {
        prepared = prepare(input)
        preparedInputs.current.set(input, prepared)
      }
      return mutationFn(prepared)
    },
    onSuccess: () => client.invalidateQueries({ queryKey: invalidate }),
  })
}

export function useCreateKnowledgeBookmark() {
  return usePreparedCollectionMutation(
    (command: EventCommand<CreateBookmarkCommand>) =>
      prepareKnowledgeNavigationCommand(command),
    knowledgeNavigationApi.createBookmark,
    knowledgeNavigationKeys.bookmarksRoot,
  )
}

interface UpdateBookmarkInput {
  bookmarkId: string
  command: EventCommand<UpdateBookmarkCommand>
}
interface PreparedUpdateBookmarkInput {
  bookmarkId: string
  command: UpdateBookmarkCommand
}

export function useUpdateKnowledgeBookmark() {
  return usePreparedCollectionMutation(
    (input: UpdateBookmarkInput): PreparedUpdateBookmarkInput => Object.freeze({
      bookmarkId: input.bookmarkId,
      command: prepareKnowledgeNavigationCommand(input.command),
    }),
    ({ bookmarkId, command }) => knowledgeNavigationApi.updateBookmark(bookmarkId, command),
    knowledgeNavigationKeys.bookmarksRoot,
  )
}

interface RevisionEntityInput {
  command: EventCommand<RevisionCommand>
}
interface BookmarkRevisionInput extends RevisionEntityInput { bookmarkId: string }
interface PreparedBookmarkRevisionInput { bookmarkId: string; command: RevisionCommand }

export function useDeleteKnowledgeBookmark() {
  return usePreparedCollectionMutation(
    (input: BookmarkRevisionInput): PreparedBookmarkRevisionInput => Object.freeze({
      bookmarkId: input.bookmarkId,
      command: prepareKnowledgeNavigationCommand(input.command),
    }),
    ({ bookmarkId, command }) => knowledgeNavigationApi.deleteBookmark(bookmarkId, command),
    knowledgeNavigationKeys.bookmarksRoot,
  )
}

export function useCreateKnowledgeFolder() {
  return usePreparedCollectionMutation(
    (command: EventCommand<CreateFolderCommand>) =>
      prepareKnowledgeNavigationCommand(command),
    knowledgeNavigationApi.createFolder,
    knowledgeNavigationKeys.folders,
  )
}

interface UpdateFolderInput {
  folderId: string
  command: EventCommand<UpdateFolderCommand>
}
interface PreparedUpdateFolderInput { folderId: string; command: UpdateFolderCommand }

export function useUpdateKnowledgeFolder() {
  return usePreparedCollectionMutation(
    (input: UpdateFolderInput): PreparedUpdateFolderInput => Object.freeze({
      folderId: input.folderId,
      command: prepareKnowledgeNavigationCommand(input.command),
    }),
    ({ folderId, command }) => knowledgeNavigationApi.updateFolder(folderId, command),
    knowledgeNavigationKeys.folders,
  )
}

interface DeleteFolderInput {
  folderId: string
  command: EventCommand<DeleteFolderCommand>
}
interface PreparedDeleteFolderInput { folderId: string; command: DeleteFolderCommand }

export function useDeleteKnowledgeFolder() {
  return usePreparedCollectionMutation(
    (input: DeleteFolderInput): PreparedDeleteFolderInput => Object.freeze({
      folderId: input.folderId,
      command: prepareKnowledgeNavigationCommand(input.command),
    }),
    ({ folderId, command }) => knowledgeNavigationApi.deleteFolder(folderId, command),
    knowledgeNavigationKeys.folders,
  )
}

export function useCreateKnowledgeWorkspace() {
  return usePreparedCollectionMutation(
    (command: EventCommand<CreateWorkspaceCommand>) =>
      prepareKnowledgeNavigationCommand(command),
    knowledgeNavigationApi.createWorkspace,
    knowledgeNavigationKeys.workspaces,
  )
}

interface UpdateWorkspaceInput {
  workspaceId: string
  command: EventCommand<UpdateWorkspaceCommand>
}
interface PreparedUpdateWorkspaceInput { workspaceId: string; command: UpdateWorkspaceCommand }

export function useUpdateKnowledgeWorkspace() {
  return usePreparedCollectionMutation(
    (input: UpdateWorkspaceInput): PreparedUpdateWorkspaceInput => Object.freeze({
      workspaceId: input.workspaceId,
      command: prepareKnowledgeNavigationCommand(input.command),
    }),
    ({ workspaceId, command }) => knowledgeNavigationApi.updateWorkspace(workspaceId, command),
    knowledgeNavigationKeys.workspaces,
  )
}

interface DuplicateWorkspaceInput {
  workspaceId: string
  command: EventCommand<DuplicateWorkspaceCommand>
}
interface PreparedDuplicateWorkspaceInput {
  workspaceId: string
  command: DuplicateWorkspaceCommand
}

export function useDuplicateKnowledgeWorkspace() {
  return usePreparedCollectionMutation(
    (input: DuplicateWorkspaceInput): PreparedDuplicateWorkspaceInput => Object.freeze({
      workspaceId: input.workspaceId,
      command: prepareKnowledgeNavigationCommand(input.command),
    }),
    ({ workspaceId, command }) => knowledgeNavigationApi.duplicateWorkspace(workspaceId, command),
    knowledgeNavigationKeys.workspaces,
  )
}

interface WorkspaceRevisionInput extends RevisionEntityInput { workspaceId: string }
interface PreparedWorkspaceRevisionInput { workspaceId: string; command: RevisionCommand }

export function useDeleteKnowledgeWorkspace() {
  return usePreparedCollectionMutation(
    (input: WorkspaceRevisionInput): PreparedWorkspaceRevisionInput => Object.freeze({
      workspaceId: input.workspaceId,
      command: prepareKnowledgeNavigationCommand(input.command),
    }),
    ({ workspaceId, command }) => knowledgeNavigationApi.deleteWorkspace(workspaceId, command),
    knowledgeNavigationKeys.workspaces,
  )
}

export function useRestoreKnowledgeWorkspace() {
  return useMutation({
    mutationFn: ({ workspaceId, revision }: { workspaceId: string; revision: number }) =>
      knowledgeNavigationApi.restorePlan(workspaceId, revision),
  })
}

export function useRandomKnowledgeNote() {
  return useMutation({
    mutationFn: (filters: RandomNoteFilters = {}) => knowledgeNavigationApi.randomNote(filters),
  })
}
